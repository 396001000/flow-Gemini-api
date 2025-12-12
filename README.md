# 🎨 Gemini Image API

一个基于 Google Labs 的图片生成 API 服务，支持多账号管理、队列机制、可视化配置。

支持edge浏览器安装插件一键导入cookie
https://microsoftedge.microsoft.com/addons/detail/cookie%E8%8E%B7%E5%8F%96%E5%99%A8/iemdjnhgjmophfndencacnfiommpfjbm

也可以自行导入

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## ✨ 特性

- 🔐 **密码保护** - 管理后台需要密码登录
- 👥 **多账号管理** - 支持添加多个 Google 账号 Cookie
- 🔄 **智能轮换** - 自动选择使用次数最少的账号
- ⏳ **队列机制** - 所有账号忙碌时，请求自动排队等待
- 🎨 **可视化配置** - 美观的 Web 界面管理账号和设置
- 📡 **RESTful API** - 简单易用的 HTTP 接口
- 🐳 **Docker 支持** - 一键容器化部署

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动服务

```bash
python image_server.py --port 8000
```

### 3. 访问配置页面

打开浏览器访问 `http://localhost:8000`

- 默认密码：`123..`（可在代码中修改 `ADMIN_PASSWORD`）

### 4. 添加账号

1. 登录 [Google Labs](https://labs.google.com/)
2. 按 F12 打开开发者工具
3. 在 Network 标签页刷新页面
4. 复制任意请求的 `Cookie` 请求头
5. 粘贴到配置页面的 Cookie 输入框
6. 点击"添加账号"

## 📡 API 使用

### 生成图片

```bash
curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "一只可爱的猫"}'
```

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `prompt` | string | ✅ | 图片描述 |
| `count` | int | ❌ | 生成数量 1-4 |
| `ratio` | string | ❌ | 比例: `1:1`, `16:9`, `9:16` |
| `reference_image` | string | ❌ | 参考图 Base64 |

### 返回示例

```json
{
  "success": true,
  "images": [
    "data:image/jpeg;base64,/9j/4AAQ..."
  ],
  "count": 1,
  "account": "账号1"
}
```

### Python 调用示例

```python
import requests
import base64

response = requests.post(
    "http://localhost:8000/api/generate",
    json={
        "prompt": "赛博朋克风格的城市夜景",
        "count": 4,
        "ratio": "16:9"
    }
)

data = response.json()
if data["success"]:
    for i, img in enumerate(data["images"]):
        b64 = img.split(",")[1]
        with open(f"image_{i+1}.jpg", "wb") as f:
            f.write(base64.b64decode(b64))
```

## 🔧 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 登录页面 |
| `/admin` | GET | 管理后台 |
| `/api/generate` | POST | 生成图片 |
| `/api/health` | GET | 健康检查 + 队列状态 |
| `/api/accounts` | GET | 获取账号列表 |
| `/api/settings` | GET/POST | 获取/更新默认设置 |
| `/docs` | GET | Swagger API 文档 |

## 🐳 Docker 部署

```bash
# 构建镜像
docker build -t gemini-api .

# 运行容器
docker run -d \
  --name gemini-api \
  -p 8000:8000 \
  -v ./server_config.json:/app/server_config.json \
  gemini-api
```

## ☁️ 宝塔面板部署

详见 [部署指南_宝塔.md](部署指南_宝塔.md)

## ⚠️ 注意事项

### Cookie 与 IP 绑定

Google 的安全机制会检测 Cookie 使用的 IP。如果您在本地获取的 Cookie 拿到服务器上使用，可能会因为 IP 变化而失效（401 错误）。

**解决方案**：通过 SSH 隧道，让浏览器流量经过服务器，这样获取的 Cookie 就是绑定服务器 IP 的。

```bash
# 本地执行，建立 SSH 隧道
ssh -D 1080 -N root@您的服务器IP

# 然后配置浏览器使用 SOCKS5 代理 127.0.0.1:1080
# 在代理环境下登录 Google Labs 获取 Cookie
```

### 支持的 Cookie 格式

1. **JSON 格式**（EditThisCookie 导出）
   ```json
   [{"name":"__Secure-1PSID","value":"xxx"}, ...]
   ```

2. **字符串格式**（浏览器 F12 复制）
   ```
   __Secure-1PSID=xxx; __Secure-1PSIDTS=yyy; ...
   ```

### 支持的比例

| 比例 | 分辨率 |
|------|--------|
| `1:1` | 1024 x 1024 |
| `16:9` | 1365 x 768 |
| `9:16` | 768 x 1365 |

> ⚠️ 不支持 `4:3` 和 `3:4` 比例

## 📁 文件结构

```
├── image_server.py    # 主服务（含 Web UI 和 API）
├── flow_api.py        # Google API 封装
├── gemini_client.py   # Python SDK 客户端
├── requirements.txt   # 依赖列表
├── Dockerfile         # Docker 构建文件
├── API_USAGE.md       # 详细 API 文档
└── 部署指南_宝塔.md    # 宝塔面板部署教程
```

## 🔒 安全说明

- 管理后台有密码保护，API 接口无需认证
- 如需保护 API，建议配置 Nginx 反向代理 + Basic Auth
- Cookie 包含敏感信息，请勿泄露

## 📄 License

MIT License

## 🙏 致谢

- [Google Labs](https://labs.google.com/) - 提供图片生成能力
- [FastAPI](https://fastapi.tiangolo.com/) - 高性能 Web 框架

---

**⭐ 如果这个项目对你有帮助，请给个 Star！**
