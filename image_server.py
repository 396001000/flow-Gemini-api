"""
Gemini Flow - 图片生成 API 服务 V2
===================================

功能:
- Cookie 自动解析（支持 JSON 格式）
- 多账号轮换
- 参考图上传
- 默认 Nano Banana Pro 模型

启动:
    python image_server.py
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import uvicorn
import json
import os
import base64
import time
import threading
from datetime import datetime

from flow_api import FlowClient


# ================== 配置文件 ==================

CONFIG_FILE = "server_config.json"


def load_config():
    default = {
        "accounts": [],  # [{name, cookies, auth_token, enabled, usage_count}]
        "default_count": 1,
        "default_ratio": "1:1",
        "default_model": "nano_banana_pro"
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return {**default, **json.load(f)}
        except:
            pass
    return default


def save_config(cfg):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ================== 数据模型 ==================

class GenerateRequest(BaseModel):
    prompt: str = Field(..., description="提示词")
    count: Optional[int] = Field(default=None, ge=1, le=4)
    ratio: Optional[str] = Field(default=None)
    model: Optional[str] = Field(default=None)
    reference_image: Optional[str] = Field(default=None, description="参考图 Base64")


class GenerateResponse(BaseModel):
    success: bool
    images: List[str] = []
    count: int = 0
    account: Optional[str] = None
    error: Optional[str] = None


# ================== Cookie 池（带队列机制）==================

class CookiePool:
    """
    Cookie 池管理器
    
    特性:
    - 账号锁定: 同一账号同一时间只处理一个请求
    - 队列等待: 所有账号忙碌时，请求排队等待
    - 自动释放: 请求完成后自动释放账号
    """
    
    def __init__(self):
        self.clients: Dict[str, FlowClient] = {}
        self.accounts = []
        self.current_idx = 0
        self.lock = threading.Lock()
        
        # 账号锁定状态
        self.account_locks: Dict[str, threading.Lock] = {}  # 每个账号一个锁
        self.account_busy: Dict[str, bool] = {}  # 账号是否忙碌
        
        # 等待队列
        self.wait_condition = threading.Condition(self.lock)
        self.max_wait_time = 120  # 最大等待时间（秒）
        
        # 统计
        self.queue_count = 0  # 当前排队数量
    
    def reload(self, accounts: list):
        with self.lock:
            self.accounts = accounts
            self.clients = {}
            self.account_locks = {}
            self.account_busy = {}
            
            for acc in accounts:
                if acc.get("enabled", True):
                    try:
                        self._create_client(acc)
                        self.account_locks[acc["name"]] = threading.Lock()
                        self.account_busy[acc["name"]] = False
                    except Exception as e:
                        print(f"⚠️ 加载 {acc['name']} 失败: {e}")
    
    def _create_client(self, acc):
        cookies = acc.get("cookies", {})
        if isinstance(cookies, str):
            parsed = {}
            for part in cookies.split(';'):
                if '=' in part:
                    k, v = part.strip().split('=', 1)
                    parsed[k.strip()] = v.strip()
            cookies = parsed
        
        client = FlowClient(cookies=cookies)
        if acc.get("auth_token"):
            client.headers["Authorization"] = f"Bearer {acc['auth_token']}"
        
        self.clients[acc["name"]] = client
        return client
    
    def acquire(self, timeout: float = None) -> tuple:
        """
        获取一个可用的账号（带锁定）
        
        返回: (client, account_name) 或 (None, None) 如果超时
        """
        if timeout is None:
            timeout = self.max_wait_time
        
        start_time = time.time()
        
        with self.wait_condition:
            while True:
                # 尝试获取一个空闲账号
                enabled = [a for a in self.accounts if a.get("enabled", True) and a["name"] in self.clients]
                
                if not enabled:
                    return None, None
                
                # 按使用次数排序，选择使用最少的
                for acc in sorted(enabled, key=lambda x: x.get("usage_count", 0)):
                    name = acc["name"]
                    if not self.account_busy.get(name, False):
                        # 获取到空闲账号
                        self.account_busy[name] = True
                        acc["usage_count"] = acc.get("usage_count", 0) + 1
                        acc["last_used"] = datetime.now().isoformat()
                        print(f"🔒 获取账号: {name} (排队: {self.queue_count})")
                        return self.clients[name], name
                
                # 所有账号都忙碌，需要等待
                elapsed = time.time() - start_time
                remaining = timeout - elapsed
                
                if remaining <= 0:
                    print(f"⏰ 等待超时，所有账号忙碌")
                    return None, None
                
                self.queue_count += 1
                print(f"⏳ 所有账号忙碌，排队等待... (排队: {self.queue_count})")
                
                # 等待有账号释放
                self.wait_condition.wait(timeout=min(remaining, 5))
                self.queue_count = max(0, self.queue_count - 1)
    
    def release(self, account_name: str):
        """
        释放账号（请求完成后调用）
        """
        with self.wait_condition:
            if account_name in self.account_busy:
                self.account_busy[account_name] = False
                print(f"🔓 释放账号: {account_name}")
                # 通知等待的请求
                self.wait_condition.notify_all()
    
    def get_status(self) -> dict:
        """获取账号池状态"""
        with self.lock:
            return {
                "total": len(self.accounts),
                "enabled": len([a for a in self.accounts if a.get("enabled", True)]),
                "busy": sum(1 for v in self.account_busy.values() if v),
                "available": sum(1 for v in self.account_busy.values() if not v),
                "queue": self.queue_count
            }
    
    # 兼容旧接口
    def get_next(self):
        return self.acquire(timeout=0.1)


# ================== 参数映射 ==================

# 注意: API 仅支持以下3种比例，4:3 和 3:4 不被支持
RATIO_MAP = {
    "16:9": "IMAGE_ASPECT_RATIO_LANDSCAPE",  # 横向
    "9:16": "IMAGE_ASPECT_RATIO_PORTRAIT",   # 纵向
    "1:1": "IMAGE_ASPECT_RATIO_SQUARE",      # 方形
}

MODEL_MAP = {
    "nano_banana_pro": "GEM_PIX_2",  # 目前映射到可用模型
    "nano_banana": "GEM_PIX_2",
    "imagen_4": "GEM_PIX_2",
    "imagen_3": "GEM_PIX",
}


# ================== 全局状态 ==================

config = load_config()
pool = CookiePool()


def init_pool():
    pool.reload(config.get("accounts", []))


# ================== FastAPI ==================

app = FastAPI(title="Gemini Image API", version="2.0")


# ================== 密码保护 ==================

ADMIN_PASSWORD = "123.."  # 管理后台密码
admin_sessions = set()  # 已登录的 session


def generate_session_id():
    import secrets
    return secrets.token_hex(16)


# 登录页面 HTML
LOGIN_HTML = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gemini API - 登录</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .login-box {
            background: rgba(255,255,255,0.08);
            backdrop-filter: blur(20px);
            border-radius: 20px;
            padding: 40px;
            width: 360px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        h1 {
            text-align: center;
            color: #fff;
            margin-bottom: 30px;
            font-size: 1.5rem;
        }
        input {
            width: 100%;
            padding: 14px;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            background: rgba(0,0,0,0.3);
            color: #fff;
            font-size: 1rem;
            margin-bottom: 20px;
        }
        input:focus { outline: none; border-color: #667eea; }
        button {
            width: 100%;
            padding: 14px;
            border: none;
            border-radius: 10px;
            background: linear-gradient(90deg, #667eea, #764ba2);
            color: white;
            font-size: 1rem;
            cursor: pointer;
        }
        button:hover { opacity: 0.9; }
        .error {
            background: rgba(231,76,60,0.2);
            color: #e74c3c;
            padding: 10px;
            border-radius: 8px;
            margin-bottom: 15px;
            text-align: center;
            display: none;
        }
    </style>
</head>
<body>
    <div class="login-box">
        <h1>🔐 管理后台登录</h1>
        <div id="error" class="error"></div>
        <input type="password" id="password" placeholder="请输入密码" onkeypress="if(event.keyCode==13)login()">
        <button onclick="login()">登 录</button>
    </div>
    <script>
        async function login() {
            const pwd = document.getElementById('password').value;
            const res = await fetch('/admin/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({password: pwd})
            });
            const data = await res.json();
            if (data.success) {
                localStorage.setItem('admin_session', data.session);
                window.location.href = '/admin?s=' + data.session;
            } else {
                document.getElementById('error').style.display = 'block';
                document.getElementById('error').textContent = '密码错误';
            }
        }
    </script>
</body>
</html>
'''


# ================== 配置页面 ==================

CONFIG_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gemini 图片 API - 配置</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
            min-height: 100vh;
            padding: 30px;
            color: #e0e0e0;
        }
        .container { max-width: 900px; margin: 0 auto; }
        h1 {
            text-align: center;
            font-size: 2rem;
            margin-bottom: 30px;
            background: linear-gradient(90deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .card {
            background: rgba(255,255,255,0.08);
            backdrop-filter: blur(20px);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 20px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .card h2 { color: #667eea; margin-bottom: 20px; font-size: 1.2rem; }
        .form-group { margin-bottom: 15px; }
        label { display: block; color: #aaa; margin-bottom: 6px; font-size: 0.9rem; }
        input, select, textarea {
            width: 100%;
            padding: 12px;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 8px;
            background: rgba(0,0,0,0.3);
            color: #fff;
            font-size: 1rem;
        }
        input:focus, textarea:focus { outline: none; border-color: #667eea; }
        textarea { resize: vertical; min-height: 100px; font-family: monospace; }
        .row { display: flex; gap: 15px; }
        .row > * { flex: 1; }
        button {
            padding: 12px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1rem;
            transition: all 0.3s;
        }
        .btn-primary { background: linear-gradient(90deg, #667eea, #764ba2); color: white; }
        .btn-primary:hover { transform: translateY(-2px); box-shadow: 0 5px 20px rgba(102,126,234,0.4); }
        .btn-success { background: #27ae60; color: white; }
        .btn-danger { background: #e74c3c; color: white; }
        .btn-sm { padding: 8px 12px; font-size: 0.85rem; }
        
        .account-list { margin-top: 15px; }
        .account-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 15px;
            background: rgba(0,0,0,0.2);
            border-radius: 8px;
            margin-bottom: 8px;
        }
        .account-name { font-weight: bold; color: #667eea; }
        .account-stats { font-size: 0.8rem; color: #888; }
        .status-dot {
            width: 10px; height: 10px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 8px;
        }
        .status-dot.on { background: #27ae60; }
        .status-dot.off { background: #e74c3c; }
        
        .parsed-preview {
            background: rgba(0,0,0,0.3);
            border-radius: 8px;
            padding: 12px;
            margin-top: 10px;
            font-family: monospace;
            font-size: 0.85rem;
            max-height: 150px;
            overflow: auto;
            display: none;
        }
        .parsed-preview.show { display: block; }
        
        .api-doc {
            background: rgba(0,0,0,0.3);
            padding: 15px;
            border-radius: 8px;
            font-family: monospace;
            font-size: 0.85rem;
        }
        .api-doc code { color: #2ecc71; }
        
        .msg {
            padding: 12px;
            border-radius: 8px;
            margin-top: 10px;
            text-align: center;
        }
        .msg.success { background: rgba(39,174,96,0.2); color: #2ecc71; }
        .msg.error { background: rgba(231,76,60,0.2); color: #e74c3c; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎨 Gemini 图片 API 配置</h1>
        
        <!-- 添加账号 -->
        <div class="card">
            <h2>➕ 添加账号</h2>
            <div class="form-group">
                <label>账号名称</label>
                <input type="text" id="accName" placeholder="例如：账号1">
            </div>
            <div class="form-group">
                <label>Cookie（支持 JSON 格式或字符串格式）</label>
                <textarea id="accCookie" placeholder='粘贴 Cookie...
支持格式1: [{"name":"__Secure-1PSID","value":"xxx"}, ...]
支持格式2: __Secure-1PSID=xxx; __Secure-1PSIDTS=xxx; ...'></textarea>
            </div>
            <div class="row">
                <button class="btn-primary" onclick="parseCookie()">🔍 解析 Cookie</button>
                <button class="btn-success" onclick="addAccount()">✅ 添加账号</button>
            </div>
            <div id="parsedPreview" class="parsed-preview"></div>
            <div id="addMsg" class="msg" style="display:none"></div>
        </div>
        
        <!-- 账号列表 -->
        <div class="card">
            <h2>📋 账号列表 (<span id="accountCount">0</span>)</h2>
            <div id="accountList" class="account-list">
                <p style="color:#666">暂无账号</p>
            </div>
        </div>
        
        <!-- 默认设置 -->
        <div class="card">
            <h2>⚙️ 默认设置</h2>
            <div class="row">
                <div class="form-group">
                    <label>默认数量</label>
                    <select id="cfgCount">
                        <option value="1">1 张</option>
                        <option value="2">2 张</option>
                        <option value="3">3 张</option>
                        <option value="4">4 张</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>默认比例</label>
                    <select id="cfgRatio">
                        <option value="1:1">1:1 方形</option>
                        <option value="16:9">16:9 横向</option>
                        <option value="9:16">9:16 纵向</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>默认模型</label>
                    <select id="cfgModel">
                        <option value="nano_banana_pro">Nano Banana Pro</option>
                        <option value="nano_banana">Nano Banana</option>
                        <option value="imagen_4">Imagen 4</option>
                        <option value="imagen_3">Imagen 3</option>
                    </select>
                </div>
            </div>
            <button class="btn-primary" onclick="saveSettings()">💾 保存设置</button>
        </div>
        
        <!-- API 文档 -->
        <div class="card">
            <h2>📡 API 调用文档</h2>
            
            <div style="margin-bottom:20px">
                <h3 style="color:#667eea;font-size:1rem;margin-bottom:10px">接口地址</h3>
                <div class="api-doc">
                    <code>POST http://localhost:8000/api/generate</code>
                </div>
            </div>
            
            <div style="margin-bottom:20px">
                <h3 style="color:#667eea;font-size:1rem;margin-bottom:10px">请求参数</h3>
                <table style="width:100%;border-collapse:collapse;font-size:0.9rem">
                    <tr style="background:rgba(0,0,0,0.3)">
                        <th style="padding:10px;text-align:left;border-bottom:1px solid rgba(255,255,255,0.1)">参数</th>
                        <th style="padding:10px;text-align:left;border-bottom:1px solid rgba(255,255,255,0.1)">类型</th>
                        <th style="padding:10px;text-align:left;border-bottom:1px solid rgba(255,255,255,0.1)">必填</th>
                        <th style="padding:10px;text-align:left;border-bottom:1px solid rgba(255,255,255,0.1)">说明</th>
                    </tr>
                    <tr>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)"><code>prompt</code></td>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)">string</td>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)">✅ 是</td>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)">图片描述提示词</td>
                    </tr>
                    <tr>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)"><code>count</code></td>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)">int</td>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)">否</td>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)">生成数量 1-4，默认使用配置值</td>
                    </tr>
                    <tr>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)"><code>ratio</code></td>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)">string</td>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)">否</td>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)">比例: "16:9" | "9:16" | "1:1" | "4:3" | "3:4"</td>
                    </tr>
                    <tr>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)"><code>model</code></td>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)">string</td>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)">否</td>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)">模型: "nano_banana_pro" | "imagen_4" | "imagen_3"</td>
                    </tr>
                    <tr>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)"><code>reference_image</code></td>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)">string</td>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)">否</td>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)">参考图 Base64 (data:image/...;base64,...)</td>
                    </tr>
                </table>
            </div>
            
            <div style="margin-bottom:20px">
                <h3 style="color:#667eea;font-size:1rem;margin-bottom:10px">返回格式</h3>
                <div class="api-doc">
<pre>{
  "success": true,          // 是否成功
  "images": [               // 图片数组 (Base64 Data URL 格式)
    "data:image/jpeg;base64,/9j/4AAQ...",
    "data:image/jpeg;base64,/9j/4BBR...",
    "data:image/jpeg;base64,/9j/4CCS...",
    "data:image/jpeg;base64,/9j/4DDT..."
  ],
  "count": 4,               // 实际生成数量
  "account": "账号1",       // 使用的账号
  "error": null             // 错误信息 (失败时)
}</pre>
                </div>
            </div>
            
            <div style="margin-bottom:20px;background:rgba(102,126,234,0.1);padding:15px;border-radius:8px">
                <h3 style="color:#667eea;font-size:1rem;margin-bottom:15px">📖 如何处理返回的图片数据</h3>
                
                <p style="color:#ccc;margin-bottom:10px"><strong>1. 返回结构说明</strong></p>
                <div class="api-doc" style="margin-bottom:15px">
<pre>data["images"]  # 图片数组，每个元素是完整的 Data URL
                # 格式: "data:image/jpeg;base64,/9j/4AAQ..."
                # 可直接用于 HTML: &lt;img src="{data['images'][0]}"&gt;</pre>
                </div>
                
                <p style="color:#ccc;margin-bottom:10px"><strong>2. 获取所有图片 (遍历)</strong></p>
                <div class="api-doc" style="margin-bottom:15px">
<pre style="color:#2ecc71"># 遍历所有返回的图片
for i, img_data in enumerate(data["images"]):
    print(f"图片 {i+1}: {img_data[:50]}...")</pre>
                </div>
                
                <p style="color:#ccc;margin-bottom:10px"><strong>3. 提取纯 Base64 (去掉前缀)</strong></p>
                <div class="api-doc" style="margin-bottom:15px">
<pre style="color:#2ecc71"># 原始: "data:image/jpeg;base64,/9j/4AAQ..."
# 提取: "/9j/4AAQ..."
b64_content = data["images"][0].split(",", 1)[1]</pre>
                </div>
                
                <p style="color:#ccc;margin-bottom:10px"><strong>4. 转换为字节数据</strong></p>
                <div class="api-doc" style="margin-bottom:15px">
<pre style="color:#2ecc71">import base64

b64_content = data["images"][0].split(",", 1)[1]
img_bytes = base64.b64decode(b64_content)
# img_bytes 现在是图片的原始字节</pre>
                </div>
                
                <p style="color:#ccc;margin-bottom:10px"><strong>5. 保存为文件</strong></p>
                <div class="api-doc" style="margin-bottom:15px">
<pre style="color:#2ecc71">import base64

for i, img_data in enumerate(data["images"]):
    b64 = img_data.split(",", 1)[1]
    with open(f"image_{i+1}.jpg", "wb") as f:
        f.write(base64.b64decode(b64))
    print(f"已保存: image_{i+1}.jpg")</pre>
                </div>
                
                <p style="color:#ccc;margin-bottom:10px"><strong>6. 完整示例: 生成4张并保存</strong></p>
                <div class="api-doc">
<pre style="color:#2ecc71">import requests
import base64

# 生成 4 张图片
response = requests.post("http://localhost:8000/api/generate", json={
    "prompt": "一只可爱的猫",
    "count": 4
})
data = response.json()

if data["success"]:
    print(f"成功生成 {data['count']} 张图片")
    
    # 保存每张图片
    for i, img_data in enumerate(data["images"]):
        b64 = img_data.split(",", 1)[1]
        filename = f"cat_{i+1}.jpg"
        with open(filename, "wb") as f:
            f.write(base64.b64decode(b64))
        print(f"[{i+1}] 已保存: {filename}")
else:
    print(f"失败: {data['error']}")</pre>
                </div>
            </div>
            
            <div style="margin-bottom:20px">
                <h3 style="color:#667eea;font-size:1rem;margin-bottom:10px">调用示例</h3>
                
                <p style="color:#aaa;margin:10px 0 5px">1. 最简单调用 (使用默认参数)</p>
                <div class="api-doc">
<pre>curl -X POST http://localhost:8000/api/generate \\
  -H "Content-Type: application/json" \\
  -d '{"prompt": "一只可爱的橘猫"}'</pre>
                </div>
                
                <p style="color:#aaa;margin:15px 0 5px">2. 指定数量和比例</p>
                <div class="api-doc">
<pre>curl -X POST http://localhost:8000/api/generate \\
  -H "Content-Type: application/json" \\
  -d '{
    "prompt": "赛博朋克风格的城市夜景",
    "count": 2,
    "ratio": "16:9"
  }'</pre>
                </div>
                
                <p style="color:#aaa;margin:15px 0 5px">3. 带参考图生成</p>
                <div class="api-doc">
<pre>curl -X POST http://localhost:8000/api/generate \\
  -H "Content-Type: application/json" \\
  -d '{
    "prompt": "将这张图片转换为水彩画风格",
    "reference_image": "data:image/jpeg;base64,/9j/4AAQ..."
  }'</pre>
                </div>
                
                <p style="color:#aaa;margin:15px 0 5px">4. Python 调用示例</p>
                <div class="api-doc">
<pre>import requests

response = requests.post(
    "http://localhost:8000/api/generate",
    json={
        "prompt": "一只可爱的猫",
        "count": 1,
        "ratio": "1:1"
    }
)

data = response.json()
if data["success"]:
    for img in data["images"]:
        print(f"图片: {img[:50]}...")
else:
    print(f"错误: {data['error']}")</pre>
                </div>
            </div>
            
            <div style="margin-bottom:20px">
                <h3 style="color:#667eea;font-size:1rem;margin-bottom:10px">其他接口</h3>
                <div class="api-doc">
<pre>GET  /api/health     # 健康检查
GET  /api/accounts   # 获取账号列表
GET  /api/settings   # 获取默认设置
POST /api/settings   # 更新默认设置</pre>
                </div>
            </div>
        </div>
        
        <!-- 完整使用示例 -->
        <div class="card">
            <h2>📚 完整使用示例</h2>
            
            <div style="margin-bottom:25px">
                <h3 style="color:#667eea;font-size:1rem;margin-bottom:10px">生成多张图片并获取所有 Base64</h3>
                <div class="api-doc">
<pre style="color:#2ecc71">import requests
import base64
import os

API_URL = "http://localhost:8000/api/generate"

# 发送请求，生成 4 张图片
response = requests.post(API_URL, json={
    "prompt": "赛博朋克风格的城市夜景",
    "count": 4,
    "ratio": "16:9"
})

data = response.json()

if data["success"]:
    print(f"✅ 成功生成 {data['count']} 张图片")
    print(f"   使用账号: {data['account']}")
    
    # 遍历每张图片
    for i, img_data in enumerate(data["images"]):
        print(f"\n--- 图片 {i+1} ---")
        
        # img_data 格式: "data:image/jpeg;base64,/9j/4AAQ..."
        # 1. 直接使用 (适用于 HTML img src)
        print(f"Data URL: {img_data[:60]}...")
        
        # 2. 提取纯 Base64
        b64_content = img_data.split(",", 1)[1]
        print(f"Base64: {b64_content[:40]}... ({len(b64_content)} chars)")
        
        # 3. 转为字节并保存
        img_bytes = base64.b64decode(b64_content)
        filepath = f"image_{i+1}.jpg"
        with open(filepath, "wb") as f:
            f.write(img_bytes)
        print(f"已保存: {filepath} ({len(img_bytes)} bytes)")
else:
    print(f"❌ 失败: {data['error']}")</pre>
                </div>
            </div>
            
            <div style="margin-bottom:25px">
                <h3 style="color:#667eea;font-size:1rem;margin-bottom:10px">使用参考图生成</h3>
                <div class="api-doc">
<pre style="color:#2ecc71">import requests
import base64

# 读取本地图片并转为 Base64
with open("reference.jpg", "rb") as f:
    img_bytes = f.read()

b64 = base64.b64encode(img_bytes).decode()
reference_b64 = f"data:image/jpeg;base64,{b64}"

# 发送请求
response = requests.post(API_URL, json={
    "prompt": "将这张图片转换为油画风格",
    "reference_image": reference_b64
})

data = response.json()
print(f"生成了 {data['count']} 张图片")</pre>
                </div>
            </div>
            
            <div style="margin-bottom:25px">
                <h3 style="color:#667eea;font-size:1rem;margin-bottom:10px">封装为函数</h3>
                <div class="api-doc">
<pre style="color:#2ecc71">import requests
import base64
import os
from typing import List, Optional

def generate_images(
    prompt: str,
    count: int = 1,
    ratio: str = "1:1",
    save_dir: str = None
) -> dict:
    # 生成图片
    # 参数: prompt(提示词), count(数量1-4), ratio(比例), save_dir(保存目录)
    # 返回: {success, images, base64_list, saved_files}
    response = requests.post(
        "http://localhost:8000/api/generate",
        json={"prompt": prompt, "count": count, "ratio": ratio}
    )
    data = response.json()
    
    result = {
        "success": data["success"],
        "images": data.get("images", []),
        "base64_list": [],
        "saved_files": []
    }
    
    if not data["success"]:
        result["error"] = data.get("error")
        return result
    
    # 提取纯 Base64
    for img in data["images"]:
        if "," in img:
            result["base64_list"].append(img.split(",", 1)[1])
    
    # 保存文件
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        for i, b64 in enumerate(result["base64_list"]):
            path = os.path.join(save_dir, f"image_{i+1}.jpg")
            with open(path, "wb") as f:
                f.write(base64.b64decode(b64))
            result["saved_files"].append(path)
    
    return result

# 使用示例
result = generate_images("一只可爱的猫", count=4, save_dir="output")
print(f"生成: {len(result['images'])} 张")
print(f"保存: {result['saved_files']}")</pre>
                </div>
            </div>
            
            <div>
                <h3 style="color:#667eea;font-size:1rem;margin-bottom:10px">图片分辨率说明</h3>
                <table style="width:100%;border-collapse:collapse;font-size:0.9rem;margin-top:10px">
                    <tr style="background:rgba(0,0,0,0.3)">
                        <th style="padding:10px;text-align:left;border-bottom:1px solid rgba(255,255,255,0.1)">比例</th>
                        <th style="padding:10px;text-align:left;border-bottom:1px solid rgba(255,255,255,0.1)">分辨率</th>
                        <th style="padding:10px;text-align:left;border-bottom:1px solid rgba(255,255,255,0.1)">像素</th>
                    </tr>
                    <tr>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)">1:1</td>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)">1024 x 1024</td>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)">~1 MP</td>
                    </tr>
                    <tr>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)">16:9</td>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)">1365 x 768</td>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)">~1 MP</td>
                    </tr>
                    <tr>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)">9:16</td>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)">768 x 1365</td>
                        <td style="padding:10px;border-bottom:1px solid rgba(255,255,255,0.05)">~1 MP</td>
                    </tr>
                </table>
                <p style="color:#888;font-size:0.85rem;margin-top:10px">注: 分辨率由模型自动决定，API 不支持自定义分辨率参数</p>
            </div>
        </div>
    </div>
    
    <script>
        let parsedCookies = null;
        
        // 解析 Cookie
        function parseCookie() {
            const raw = document.getElementById('accCookie').value.trim();
            const preview = document.getElementById('parsedPreview');
            
            if (!raw) {
                preview.className = 'parsed-preview';
                return;
            }
            
            try {
                // 尝试 JSON 格式
                let cookies = {};
                try {
                    const json = JSON.parse(raw);
                    if (Array.isArray(json)) {
                        json.forEach(c => {
                            if (c.name && c.value) cookies[c.name] = c.value;
                        });
                    }
                } catch {
                    // 字符串格式
                    raw.split(';').forEach(part => {
                        const [k, ...v] = part.trim().split('=');
                        if (k && v.length) cookies[k.trim()] = v.join('=').trim();
                    });
                }
                
                const count = Object.keys(cookies).length;
                if (count > 0) {
                    parsedCookies = cookies;
                    preview.innerHTML = `<p style="color:#2ecc71">✅ 解析成功！共 ${count} 个 Cookie</p>
                        <p style="color:#888;margin-top:8px">包含: ${Object.keys(cookies).slice(0,5).join(', ')}${count > 5 ? '...' : ''}</p>`;
                    preview.className = 'parsed-preview show';
                } else {
                    throw new Error('无效格式');
                }
            } catch (e) {
                parsedCookies = null;
                preview.innerHTML = `<p style="color:#e74c3c">❌ 解析失败: ${e.message}</p>`;
                preview.className = 'parsed-preview show';
            }
        }
        
        // 添加账号
        async function addAccount() {
            const name = document.getElementById('accName').value.trim();
            const msg = document.getElementById('addMsg');
            
            if (!name) {
                msg.className = 'msg error';
                msg.textContent = '请输入账号名称';
                msg.style.display = 'block';
                return;
            }
            
            if (!parsedCookies) {
                parseCookie();
                if (!parsedCookies) {
                    msg.className = 'msg error';
                    msg.textContent = '请先解析 Cookie';
                    msg.style.display = 'block';
                    return;
                }
            }
            
            const res = await fetch('/api/accounts', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name, cookies: parsedCookies, enabled: true})
            });
            
            const data = await res.json();
            if (data.success) {
                msg.className = 'msg success';
                msg.textContent = '✅ 添加成功!';
                document.getElementById('accName').value = '';
                document.getElementById('accCookie').value = '';
                document.getElementById('parsedPreview').className = 'parsed-preview';
                parsedCookies = null;
                loadAccounts();
            } else {
                msg.className = 'msg error';
                msg.textContent = '❌ ' + (data.error || '添加失败');
            }
            msg.style.display = 'block';
            setTimeout(() => msg.style.display = 'none', 3000);
        }
        
        // 加载账号列表
        async function loadAccounts() {
            const res = await fetch('/api/accounts');
            const accounts = await res.json();
            
            document.getElementById('accountCount').textContent = accounts.length;
            
            if (accounts.length === 0) {
                document.getElementById('accountList').innerHTML = '<p style="color:#666">暂无账号，请添加</p>';
                return;
            }
            
            document.getElementById('accountList').innerHTML = accounts.map(acc => `
                <div class="account-item">
                    <div>
                        <span class="status-dot ${acc.enabled ? 'on' : 'off'}"></span>
                        <span class="account-name">${acc.name}</span>
                        <span class="account-stats"> | 使用: ${acc.usage_count || 0} 次</span>
                    </div>
                    <div>
                        <button class="btn-sm ${acc.enabled ? 'btn-danger' : 'btn-success'}" 
                                onclick="toggleAccount('${acc.name}', ${!acc.enabled})">
                            ${acc.enabled ? '禁用' : '启用'}
                        </button>
                        <button class="btn-sm btn-danger" onclick="deleteAccount('${acc.name}')">删除</button>
                    </div>
                </div>
            `).join('');
        }
        
        // 切换账号状态
        async function toggleAccount(name, enabled) {
            await fetch(`/api/accounts/${encodeURIComponent(name)}/toggle`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({enabled})
            });
            loadAccounts();
        }
        
        // 删除账号
        async function deleteAccount(name) {
            if (!confirm(`确定删除 "${name}"?`)) return;
            await fetch(`/api/accounts/${encodeURIComponent(name)}`, {method: 'DELETE'});
            loadAccounts();
        }
        
        // 加载设置
        async function loadSettings() {
            const res = await fetch('/api/settings');
            const cfg = await res.json();
            document.getElementById('cfgCount').value = cfg.default_count || 1;
            document.getElementById('cfgRatio').value = cfg.default_ratio || '1:1';
            document.getElementById('cfgModel').value = cfg.default_model || 'nano_banana_pro';
        }
        
        // 保存设置
        async function saveSettings() {
            await fetch('/api/settings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    default_count: parseInt(document.getElementById('cfgCount').value),
                    default_ratio: document.getElementById('cfgRatio').value,
                    default_model: document.getElementById('cfgModel').value
                })
            });
            alert('✅ 设置已保存');
        }
        
        // 初始化
        loadAccounts();
        loadSettings();
    </script>
</body>
</html>
"""

# ================== 路由 ==================

# 根路径跳转到登录页
@app.get("/", response_class=HTMLResponse)
async def root():
    return LOGIN_HTML


# 登录接口
@app.post("/admin/login")
async def admin_login(data: dict):
    if data.get("password") == ADMIN_PASSWORD:
        session_id = generate_session_id()
        admin_sessions.add(session_id)
        return {"success": True, "session": session_id}
    return {"success": False}


# 管理后台（需要登录）
@app.get("/admin", response_class=HTMLResponse)
async def admin_page(s: str = ""):
    if s not in admin_sessions:
        return LOGIN_HTML
    return CONFIG_HTML


@app.get("/api/accounts")
async def get_accounts():
    return config.get("accounts", [])


@app.post("/api/accounts")
async def add_account(data: dict):
    accounts = config.get("accounts", [])
    
    # 检查重名
    for acc in accounts:
        if acc["name"] == data["name"]:
            return {"success": False, "error": "账号名已存在"}
    
    new_acc = {
        "name": data["name"],
        "cookies": data["cookies"],
        "auth_token": data.get("auth_token", ""),
        "enabled": data.get("enabled", True),
        "usage_count": 0
    }
    
    accounts.append(new_acc)
    config["accounts"] = accounts
    save_config(config)
    init_pool()
    
    return {"success": True}


@app.delete("/api/accounts/{name}")
async def delete_account(name: str):
    accounts = [a for a in config.get("accounts", []) if a["name"] != name]
    config["accounts"] = accounts
    save_config(config)
    init_pool()
    return {"success": True}


@app.post("/api/accounts/{name}/toggle")
async def toggle_account(name: str, data: dict):
    for acc in config.get("accounts", []):
        if acc["name"] == name:
            acc["enabled"] = data.get("enabled", True)
            break
    save_config(config)
    init_pool()
    return {"success": True}


@app.get("/api/settings")
async def get_settings():
    return {
        "default_count": config.get("default_count", 1),
        "default_ratio": config.get("default_ratio", "1:1"),
        "default_model": config.get("default_model", "nano_banana_pro")
    }


@app.post("/api/settings")
async def save_settings(data: dict):
    config["default_count"] = data.get("default_count", 1)
    config["default_ratio"] = data.get("default_ratio", "1:1")
    config["default_model"] = data.get("default_model", "nano_banana_pro")
    save_config(config)
    return {"success": True}


@app.post("/api/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    """
    生成图片
    - prompt: 提示词
    - count: 数量 1-4，默认使用设置
    - ratio: 比例，默认使用设置
    - model: 模型，默认使用设置
    - reference_image: 参考图 Base64 (可选)
    """
    # 获取可用账号（带队列等待）
    client, account_name = pool.acquire(timeout=120)
    
    if not client:
        status = pool.get_status()
        return GenerateResponse(
            success=False, 
            error=f"没有可用账号（总计:{status['total']}, 忙碌:{status['busy']}, 排队:{status['queue']}）"
        )
    
    try:
        # 使用请求参数或默认值
        count = req.count if req.count else config.get("default_count", 1)
        ratio = req.ratio if req.ratio else config.get("default_ratio", "1:1")
        model = req.model if req.model else config.get("default_model", "nano_banana_pro")
        
        # 验证比例参数
        UNSUPPORTED_RATIOS = ["4:3", "3:4"]
        SUPPORTED_RATIOS = ["16:9", "9:16", "1:1"]
        
        if ratio in UNSUPPORTED_RATIOS:
            pool.release(account_name)  # 验证失败，释放账号
            return GenerateResponse(
                success=False,
                error=f"不支持的比例参数: '{ratio}'。支持的比例: {', '.join(SUPPORTED_RATIOS)}"
            )
        
        if ratio not in SUPPORTED_RATIOS:
            pool.release(account_name)
            return GenerateResponse(
                success=False,
                error=f"无效的比例参数: '{ratio}'。支持的比例: {', '.join(SUPPORTED_RATIOS)}"
            )
        
        count = max(1, min(4, count))
        
        api_ratio = RATIO_MAP.get(ratio, "IMAGE_ASPECT_RATIO_SQUARE")
        api_model = MODEL_MAP.get(model, "GEM_PIX_2")
        
        print(f"📷 [{account_name}] 生成: {req.prompt[:30]}... (数量:{count})")
        
        # 处理参考图
        image_inputs = []
        if req.reference_image:
            b64_data = req.reference_image
            if ',' in b64_data:
                b64_data = b64_data.split(',', 1)[1]
            image_inputs.append({"encodedImage": b64_data})
            print(f"   参考图: {len(b64_data)} bytes")
        
        # 调用 API
        result = client.generate_image(
            prompt=req.prompt,
            aspect_ratio=api_ratio,
            model=api_model,
            count=count
        )
        
        images = []
        if "media" in result:
            for item in result["media"]:
                if "image" in item:
                    b64 = item["image"].get("generatedImage", {}).get("encodedImage")
                    if b64:
                        images.append(f"data:image/jpeg;base64,{b64}")
        
        # 更新使用统计
        for acc in config.get("accounts", []):
            if acc["name"] == account_name:
                acc["usage_count"] = acc.get("usage_count", 0) + 1
                break
        save_config(config)
        
        print(f"✅ [{account_name}] 成功生成 {len(images)} 张")
        return GenerateResponse(success=True, images=images, count=len(images), account=account_name)
        
    except Exception as e:
        print(f"❌ [{account_name}] 失败: {e}")
        return GenerateResponse(success=False, error=str(e), account=account_name)
    
    finally:
        # 确保释放账号
        pool.release(account_name)


@app.get("/api/health")
async def health():
    """健康检查 + 队列状态"""
    status = pool.get_status()
    return {
        "status": "ok",
        **status
    }


# ================== 启动 ==================

@app.on_event("startup")
async def startup():
    init_pool()
    print(f"✅ 已加载 {len(pool.clients)} 个账号")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    
    print(f"""
╔═══════════════════════════════════════════════════════╗
║         Gemini 图片生成 API 服务 V2                   ║
╠═══════════════════════════════════════════════════════╣
║  配置页面: http://localhost:{args.port}                      ║
║  API 端点: http://localhost:{args.port}/api/generate         ║
║  API 文档: http://localhost:{args.port}/docs                 ║
╚═══════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(app, host="0.0.0.0", port=args.port)
