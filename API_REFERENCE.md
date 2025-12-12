# Google Labs Flow API 完整逆向分析文档

## 概述
- **基础域名**: `https://aisandbox-pa.googleapis.com`
- **Web API**: `https://labs.google/fx/api/trpc/`
- **API Key**: `AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY`
- **工具标识**: `PINHOLE`

---

## 核心 API 端点

| 功能 | API 端点 | 状态 |
|------|---------|------|
| 文生视频 | `video:batchAsyncGenerateVideoText` | ✅ 已捕获 |
| 图帧生视频（首尾帧） | `video:batchAsyncGenerateVideoStartAndEndImage` | ✅ 已捕获 |
| 素材生视频（多图参考） | `video:batchAsyncGenerateVideoReferenceImages` | ✅ 已捕获 |
| 获取媒体结果 | `/v1/media/{mediaId}` | ✅ 已捕获 |
| 创建项目 | `project.createProject` | ✅ 已捕获 |

---

## 1. 文生视频 API (Text-to-Video)

### 端点
```
POST https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoText
```

### 请求体
```json
{
  "clientContext": {
    "sessionId": ";{timestamp}",
    "projectId": "{uuid}",
    "tool": "PINHOLE",
    "userPaygateTier": "PAYGATE_TIER_ONE"
  },
  "requests": [
    {
      "aspectRatio": "VIDEO_ASPECT_RATIO_PORTRAIT",
      "seed": 6078,
      "textInput": {
        "prompt": "可爱猫猫"
      },
      "videoModelKey": "veo_3_1_t2v_fast_portrait",
      "metadata": {
        "sceneId": "{uuid}"
      }
    }
  ]
}
```

### 响应
```json
{
  "operations": [
    {
      "operation": {"name": "a13bd1b5a45cda8eb8124ef9629a023f"},
      "sceneId": "ba4c12ee-76f6-42ee-9d3a-a54c812dd91a",
      "status": "MEDIA_GENERATION_STATUS_PENDING"
    }
  ],
  "remainingCredits": 800
}
```

---

## 2. 图帧生视频 API (Image-to-Video with Start & End Frame)

### 端点
```
POST https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoStartAndEndImage
```

### 请求体
```json
{
  "clientContext": {
    "sessionId": ";1765461280641",
    "projectId": "3a0f827c-79b8-40ef-b80a-5658e96459a4",
    "tool": "PINHOLE",
    "userPaygateTier": "PAYGATE_TIER_ONE"
  },
  "requests": [
    {
      "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
      "seed": 6915,
      "textInput": {
        "prompt": "跑步者变成骑着摩托车"
      },
      "videoModelKey": "veo_3_1_i2v_s_fast_fl",
      "startImage": {
        "mediaId": "CAMaJDRkZjYzMjE2LTZhYjUtNDY5Ny1iZjg2LWNhMmVjMjc5ZDc1NCIDQ0FFKiQ5NDMzZGNkNy0xYWZjLTRmZmMtOWJlNC04YTY5NjNhYmEwOGE"
      },
      "endImage": {
        "mediaId": "CAMaJDMzMGUwNDY4LWI0Y2YtNDgwNC04ODEwLTMxMDFlZGY2Mjc4NSIDQ0FFKiQxMjQxY2Y2MC05MDQ0LTQyYmItOTc3Ni0wODNlNjMyYjVhMzQ"
      },
      "metadata": {
        "sceneId": "840a4a3f-0e9c-4eda-891b-30860c7a9be3"
      }
    }
  ]
}
```

### 响应
```json
{
  "operations": [
    {
      "operation": {"name": "d834334d6176828dfaa1fdb34de9b10a"},
      "sceneId": "840a4a3f-0e9c-4eda-891b-30860c7a9be3",
      "status": "MEDIA_GENERATION_STATUS_PENDING"
    }
  ],
  "remainingCredits": 780
}
```

---

## 3. 素材生视频 API (Reference Images to Video)

### 端点
```
POST https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoReferenceImages
```

### 请求体
```json
{
  "clientContext": {
    "sessionId": ";1765461280641",
    "projectId": "3a0f827c-79b8-40ef-b80a-5658e96459a4",
    "tool": "PINHOLE",
    "userPaygateTier": "PAYGATE_TIER_ONE"
  },
  "requests": [
    {
      "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
      "metadata": {
        "sceneId": "aafce40d-ae42-494f-a898-3ef31ea1d864"
      },
      "referenceImages": [
        {
          "imageUsageType": "IMAGE_USAGE_TYPE_ASSET",
          "mediaId": "CAMaJDg5NmE3ODk0LTY1ODItNDA3NS1iNWMwLTZiZmE3MDljNDRmNSIDQ0FFKiQyNmJkOWM4NS1jOTk5LTQ0YjQtOGJiYi1hNTgyMTI3NDMyN2M"
        },
        {
          "imageUsageType": "IMAGE_USAGE_TYPE_ASSET",
          "mediaId": "CAMaJDRkZjYzMjE2LTZhYjUtNDY5Ny1iZjg2LWNhMmVjMjc5ZDc1NCIDQ0FFKiQ5NDMzZGNkNy0xYWZjLTRmZmMtOWJlNC04YTY5NjNhYmEwOGE"
        },
        {
          "imageUsageType": "IMAGE_USAGE_TYPE_ASSET",
          "mediaId": "CAMaJGRmOGI4MmJkLTUzYjAtNDgwZi05OTBjLTk5ZmIwYjIwYjNjZiIDQ0FFKiRjMWNkODU0Ny1kOGIyLTQ3MGUtOWE2MS01NGZlNTM4NjJiZDY"
        }
      ],
      "seed": 17050,
      "textInput": {
        "prompt": "赛场上跑步"
      },
      "videoModelKey": "veo_3_0_r2v_fast"
    }
  ]
}
```

### 响应
```json
{
  "operations": [
    {
      "operation": {"name": "9f8782f5c3f7053274acc5ec17d7c63e"},
      "sceneId": "aafce40d-ae42-494f-a898-3ef31ea1d864",
      "status": "MEDIA_GENERATION_STATUS_PENDING"
    }
  ],
  "remainingCredits": 760
}
```

---

## 4. 获取媒体结果 API

### 端点
```
GET https://aisandbox-pa.googleapis.com/v1/media/{mediaGenerationId}?key={API_KEY}&clientContext.tool=PINHOLE&returnUriOnly=true
```

### 响应示例
```json
{
  "name": "...",
  "video": {
    "seed": 19804,
    "mediaGenerationId": "...",
    "prompt": "一个美丽的少女在夕阳下",
    "fifeUrl": "https://storage.googleapis.com/ai-sandbox-videofx/video/{mediaKey}?...",
    "servingBaseUri": "https://storage.googleapis.com/ai-sandbox-videofx/image/{mediaKey}?...",
    "model": "veo_3_1_t2v_fast_portrait",
    "aspectRatio": "VIDEO_ASPECT_RATIO_PORTRAIT",
    "isLooped": false,
    "mediaVisibility": "PRIVATE"
  },
  "mediaGenerationId": {
    "mediaType": "VIDEO",
    "projectId": "...",
    "workflowId": "...",
    "workflowStepId": "CAE",
    "mediaKey": "7bdffad3-68b3-4b1a-aae2-e2fe20fd3588"
  }
}
```

---

## 5. 创建项目 API

### 端点
```
POST https://labs.google/fx/api/trpc/project.createProject
```

### 请求体
```json
{
  "json": {
    "projectTitle": "Dec 11 - 21:30",
    "toolName": "PINHOLE"
  }
}
```

### 响应
```json
{
  "result": {
    "data": {
      "json": {
        "result": {
          "projectId": "7720028a-7192-4ed5-8193-af88bf095134",
          "projectInfo": {"projectTitle": "Dec 11 - 21:30"}
        },
        "status": 200
      }
    }
  }
}
```

---

## 6. 视频模型列表

### 文生视频 (Text-to-Video)
| 模型 Key | 显示名称 | 比例 | Credit | 时长 |
|---------|---------|------|--------|------|
| `veo_3_1_t2v_fast_portrait` | Veo 3.1 - Fast | 9:16 | 20 | 8s |
| `veo_3_1_t2v_fast` | Veo 3.1 - Fast | 16:9 | 20 | 8s |
| `veo_3_1_t2v_portrait` | Veo 3.1 - Quality | 9:16 | 100 | 8s |
| `veo_3_1_t2v` | Veo 3.1 - Quality | 16:9 | 100 | 8s |

### 图帧生视频 - 首帧 (Start Image)
| 模型 Key | 显示名称 | 比例 | Credit |
|---------|---------|------|--------|
| `veo_3_1_i2v_s_fast_portrait` | Veo 3.1 - Fast | 9:16 | 20 |
| `veo_3_1_i2v_s_fast` | Veo 3.1 - Fast | 16:9 | 20 |
| `veo_3_1_i2v_s_portrait` | Veo 3.1 - Quality | 9:16 | 100 |
| `veo_3_1_i2v_s` | Veo 3.1 - Quality | 16:9 | 100 |

### 图帧生视频 - 首尾帧 (Start & End Image)
| 模型 Key | 显示名称 | 比例 | Credit |
|---------|---------|------|--------|
| `veo_3_1_i2v_s_fast_fl` | Veo 3.1 - Fast | 16:9 | 20 |
| `veo_3_1_i2v_s_fast_portrait_fl` | Veo 3.1 - Fast | 9:16 | 20 |
| `veo_3_1_i2v_s_fl` | Veo 3.1 - Quality | 16:9 | 100 |
| `veo_3_1_i2v_s_portrait_fl` | Veo 3.1 - Quality | 9:16 | 100 |

### 素材生视频 (Reference Images)
| 模型 Key | 显示名称 | 比例 | Credit |
|---------|---------|------|--------|
| `veo_3_0_r2v_fast` | Veo 3.1 - Fast | 16:9 | 20 |

---

## 7. 常量定义

### 比例
| 常量 | 说明 |
|------|------|
| `VIDEO_ASPECT_RATIO_LANDSCAPE` | 16:9 横屏 |
| `VIDEO_ASPECT_RATIO_PORTRAIT` | 9:16 竖屏 |

### 状态
| 常量 | 说明 |
|------|------|
| `MEDIA_GENERATION_STATUS_PENDING` | 等待中 |
| `MEDIA_GENERATION_STATUS_RUNNING` | 生成中 |
| `MEDIA_GENERATION_STATUS_COMPLETE` | 已完成 |
| `MEDIA_GENERATION_STATUS_FAILED` | 失败 |

### 图片使用类型
| 常量 | 说明 |
|------|------|
| `IMAGE_USAGE_TYPE_ASSET` | 资源图片 |

---

## 8. 认证

需要以下 Cookie：
- `__Secure-next-auth.session-token` (必需)
- `__Host-next-auth.csrf-token`
- `__Secure-next-auth.callback-url`
- `email`

---

## 9. API 调用流程

### 生成视频流程
1. 创建项目（可选）: `project.createProject`
2. 发起生成请求: `video:batchAsyncGenerateVideoText` / `...StartAndEndImage` / `...ReferenceImages`
3. 获取 operation ID
4. 轮询查询结果: `/v1/media/{mediaId}`
5. 获取视频 URL: `fifeUrl`

### 批量生成
可以在 `requests` 数组中添加多个请求，一次性生成多个视频。

---

## 更新日志
- 2025-12-11: 初始逆向分析
- 2025-12-11: 补充图帧生视频、素材生视频 API
- 2025-12-11: 补充历史记录查询 API

---

## 10. 历史记录查询（获取 Media ID）

### User History
**Endpoint:** `media.fetchUserHistoryDirectly`
**Method:** `TRPC Query`

**Input:**
```json
{
  "json": {
    "type": "ASSET_MANAGER", // Use "PINHOLE" for VIDEO history, "ASSET_MANAGER" for IMAGE history
    "pageSize": 20,
    "responseScope": "RESPONSE_SCOPE_UNSPECIFIED",
    "cursor": null,
    "projectId": "OPTIONAL_PROJECT_ID" // Optional filter
  },
  "meta": {
    "values": {
      "cursor": ["undefined"]
    }
  }
}
```

**Notes:**
- **CRITICAL:** To fetch generated videos, you MUST use `type: "PINHOLE"`. The default `ASSET_MANAGER` only returns images.
- The `name` field in the returned workflow items (starting with `CAUS`) is the Media ID needed for `GET /v1/media/{id}`.

### 响应结构
返回 `result.data.json.result.userWorkflows` 数组。
关键字段：`name` (用于 GET /v1/media/{name})。
