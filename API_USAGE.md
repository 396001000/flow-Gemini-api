# Gemini 图片生成 API 使用文档

## 快速开始

### 1. 启动服务

```bash
python image_server.py
# 或指定端口
python image_server.py --port 8080
```

### 2. 配置 Cookie

访问 http://localhost:8000 配置页面，添加您的 Google 账号 Cookie。

### 3. 调用 API

```bash
curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "一只可爱的猫"}'
```

---

## API 接口详解

### 生成图片

**接口**: `POST /api/generate`

**请求参数**:

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `prompt` | string | ✅ | - | 图片描述提示词 |
| `count` | int | 否 | 配置值 | 生成数量 1-4 |
| `ratio` | string | 否 | 配置值 | 比例: "16:9", "9:16", "1:1", "4:3", "3:4" |
| `model` | string | 否 | 配置值 | 模型: "nano_banana_pro", "imagen_4", "imagen_3" |
| `reference_image` | string | 否 | - | 参考图 Base64 格式 |

**返回格式**:

```json
{
  "success": true,
  "images": [
    "data:image/jpeg;base64,/9j/4AAQ...",
    "data:image/jpeg;base64,/9j/4AAQ...",
    "data:image/jpeg;base64,/9j/4AAQ...",
    "data:image/jpeg;base64,/9j/4AAQ..."
  ],
  "count": 4,
  "account": "账号1",
  "error": null
}
```

**返回字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | bool | 是否成功 |
| `images` | array | 图片数组，每个元素是完整的 Data URL (可直接用于 img src) |
| `count` | int | 实际生成的图片数量 |
| `account` | string | 使用的账号名称 |
| `error` | string | 错误信息（失败时） |

---

## 完整使用示例

### Python 示例

```python
import requests
import base64
import os

API_URL = "http://localhost:8000/api/generate"

def generate_images(prompt, count=1, ratio="1:1", save_dir="output"):
    """
    生成图片并保存到本地
    
    参数:
        prompt: 提示词
        count: 生成数量 (1-4)
        ratio: 比例 ("1:1", "16:9", "9:16", "4:3", "3:4")
        save_dir: 保存目录
    
    返回:
        成功: 文件路径列表
        失败: None
    """
    # 发送请求
    response = requests.post(API_URL, json={
        "prompt": prompt,
        "count": count,
        "ratio": ratio
    })
    
    data = response.json()
    
    if not data["success"]:
        print(f"生成失败: {data['error']}")
        return None
    
    print(f"✅ 成功生成 {data['count']} 张图片 (账号: {data['account']})")
    
    # 创建保存目录
    os.makedirs(save_dir, exist_ok=True)
    
    # 保存每张图片
    saved_files = []
    for i, img_data in enumerate(data["images"]):
        # 从 Data URL 提取 Base64
        # 格式: data:image/jpeg;base64,/9j/4AAQ...
        if "," in img_data:
            b64_content = img_data.split(",", 1)[1]
        else:
            b64_content = img_data
        
        # 解码并保存
        img_bytes = base64.b64decode(b64_content)
        filepath = os.path.join(save_dir, f"image_{i+1}.jpg")
        
        with open(filepath, "wb") as f:
            f.write(img_bytes)
        
        print(f"  [{i+1}] 已保存: {filepath} ({len(img_bytes)} bytes)")
        saved_files.append(filepath)
    
    return saved_files


def generate_with_reference(prompt, reference_image_path):
    """
    使用参考图生成图片
    
    参数:
        prompt: 提示词
        reference_image_path: 参考图片文件路径
    """
    # 读取参考图并转为 Base64
    with open(reference_image_path, "rb") as f:
        img_bytes = f.read()
    
    # 判断图片类型
    if reference_image_path.lower().endswith(".png"):
        mime = "image/png"
    else:
        mime = "image/jpeg"
    
    # 构建 Data URL
    b64 = base64.b64encode(img_bytes).decode()
    reference_b64 = f"data:{mime};base64,{b64}"
    
    # 发送请求
    response = requests.post(API_URL, json={
        "prompt": prompt,
        "reference_image": reference_b64
    })
    
    return response.json()


# ========== 使用示例 ==========

if __name__ == "__main__":
    # 示例 1: 生成单张图片
    print("=== 示例 1: 生成单张图片 ===")
    result = generate_images("一只可爱的橘猫", count=1)
    
    # 示例 2: 生成4张图片
    print("\n=== 示例 2: 生成4张图片 ===")
    result = generate_images(
        prompt="赛博朋克风格的城市夜景",
        count=4,
        ratio="16:9",
        save_dir="cyberpunk_images"
    )
    
    # 示例 3: 直接使用返回的 Base64
    print("\n=== 示例 3: 直接处理 Base64 ===")
    response = requests.post(API_URL, json={"prompt": "一朵向日葵"})
    data = response.json()
    
    if data["success"]:
        for i, img in enumerate(data["images"]):
            print(f"图片 {i+1}: {img[:80]}...")
            # 可以直接用于:
            # - HTML: <img src="{img}">
            # - 发送给其他 API
            # - 保存到数据库
```

### JavaScript/Node.js 示例

```javascript
const fetch = require('node-fetch');
const fs = require('fs');

const API_URL = 'http://localhost:8000/api/generate';

async function generateImages(prompt, count = 1, ratio = '1:1') {
    const response = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, count, ratio })
    });
    
    const data = await response.json();
    
    if (!data.success) {
        throw new Error(data.error);
    }
    
    console.log(`✅ 生成 ${data.count} 张图片`);
    
    // 处理每张图片
    data.images.forEach((imgBase64, index) => {
        // 提取 Base64 内容
        const base64Data = imgBase64.split(',')[1];
        
        // 保存为文件
        const buffer = Buffer.from(base64Data, 'base64');
        fs.writeFileSync(`image_${index + 1}.jpg`, buffer);
        console.log(`  保存: image_${index + 1}.jpg`);
    });
    
    return data;
}

// 使用
generateImages('一只可爱的猫', 4, '1:1')
    .then(data => console.log('完成!'))
    .catch(err => console.error('错误:', err));
```

### cURL 示例

```bash
# 生成单张图片
curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "一只可爱的猫"}' \
  | jq '.images[0]' > image.txt

# 生成4张图片并解析
curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "风景画", "count": 4}' \
  | jq -r '.images[]' | head -1 | cut -d',' -f2 | base64 -d > image.jpg

# 查看返回的图片数量
curl -s -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "测试", "count": 4}' \
  | jq '.count'
```

---

## 其他 API 接口

### 健康检查

```
GET /api/health
```

返回:
```json
{
  "status": "ok",
  "accounts": 2,
  "enabled": 2
}
```

### 获取账号列表

```
GET /api/accounts
```

返回:
```json
[
  {
    "name": "账号1",
    "enabled": true,
    "usage_count": 10
  }
]
```

### 获取默认设置

```
GET /api/settings
```

返回:
```json
{
  "default_count": 1,
  "default_ratio": "1:1",
  "default_model": "nano_banana_pro"
}
```

### 更新默认设置

```
POST /api/settings
Content-Type: application/json

{
  "default_count": 2,
  "default_ratio": "16:9",
  "default_model": "imagen_4"
}
```

---

## 图片分辨率说明

当前模型输出的分辨率（由模型自动决定）:

| 比例 | 分辨率 | 像素 |
|------|--------|------|
| 1:1 | 1024 x 1024 | ~1 MP |
| 16:9 | 1365 x 768 | ~1 MP |
| 9:16 | 768 x 1365 | ~1 MP |

**注意**: API 不支持自定义分辨率参数，分辨率由模型自动决定。

---

## 错误处理

### 常见错误

| 错误信息 | 原因 | 解决方案 |
|----------|------|----------|
| "没有可用账号" | 未添加 Cookie | 访问配置页面添加账号 |
| "Cookie 已过期" | Cookie 失效 | 重新获取并添加 Cookie |
| "400 Bad Request" | 参数错误 | 检查 prompt 是否为空 |

### 错误响应格式

```json
{
  "success": false,
  "images": [],
  "count": 0,
  "account": "账号1",
  "error": "错误信息描述"
}
```

---

## 最佳实践

1. **批量生成**: 一次请求最多生成 4 张图片
2. **错误重试**: 建议实现重试机制（3次）
3. **账号轮换**: 添加多个账号可自动轮换避免限流
4. **保存图片**: 及时保存返回的 Base64，避免丢失
