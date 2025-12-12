"""
Gemini 图片生成 API 客户端
===========================

完整的 Python SDK，用于调用 Gemini 图片生成 API

使用方法:
    from gemini_client import GeminiImageClient
    
    client = GeminiImageClient("http://localhost:8000")
    images = client.generate("一只可爱的猫", count=2)
"""

import requests
import base64
import os
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class GenerationResult:
    """生成结果"""
    success: bool
    images: List[str]  # Base64 Data URL 列表
    count: int
    account: Optional[str]
    error: Optional[str]
    
    def get_base64_list(self) -> List[str]:
        """获取纯 Base64 内容列表（不含 data:image 前缀）"""
        result = []
        for img in self.images:
            if "," in img:
                result.append(img.split(",", 1)[1])
            else:
                result.append(img)
        return result
    
    def get_bytes_list(self) -> List[bytes]:
        """获取图片字节数据列表"""
        return [base64.b64decode(b64) for b64 in self.get_base64_list()]
    
    def save_all(self, directory: str = ".", prefix: str = "image") -> List[str]:
        """保存所有图片到目录"""
        os.makedirs(directory, exist_ok=True)
        paths = []
        for i, img_bytes in enumerate(self.get_bytes_list()):
            path = os.path.join(directory, f"{prefix}_{i+1}.jpg")
            with open(path, "wb") as f:
                f.write(img_bytes)
            paths.append(path)
        return paths


class GeminiImageClient:
    """Gemini 图片生成客户端"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/api/generate"
    
    def generate(
        self,
        prompt: str,
        count: int = None,
        ratio: str = None,
        model: str = None,
        reference_image: str = None
    ) -> GenerationResult:
        """
        生成图片
        
        参数:
            prompt: 图片描述提示词 (必填)
            count: 生成数量 1-4 (可选，默认使用服务器配置)
            ratio: 比例 "16:9", "9:16", "1:1", "4:3", "3:4" (可选)
            model: 模型 "nano_banana_pro", "imagen_4", "imagen_3" (可选)
            reference_image: 参考图 Base64 或文件路径 (可选)
        
        返回:
            GenerationResult 对象
        """
        payload = {"prompt": prompt}
        
        if count is not None:
            payload["count"] = count
        if ratio is not None:
            payload["ratio"] = ratio
        if model is not None:
            payload["model"] = model
        
        # 处理参考图
        if reference_image:
            if os.path.isfile(reference_image):
                # 如果是文件路径，读取并转换
                payload["reference_image"] = self._file_to_base64(reference_image)
            else:
                # 假设已经是 Base64
                payload["reference_image"] = reference_image
        
        try:
            response = requests.post(self.api_url, json=payload, timeout=120)
            data = response.json()
            
            return GenerationResult(
                success=data.get("success", False),
                images=data.get("images", []),
                count=data.get("count", 0),
                account=data.get("account"),
                error=data.get("error")
            )
        except Exception as e:
            return GenerationResult(
                success=False,
                images=[],
                count=0,
                account=None,
                error=str(e)
            )
    
    def _file_to_base64(self, filepath: str) -> str:
        """将文件转换为 Base64 Data URL"""
        with open(filepath, "rb") as f:
            content = f.read()
        
        # 判断 MIME 类型
        ext = os.path.splitext(filepath)[1].lower()
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp"
        }
        mime = mime_map.get(ext, "image/jpeg")
        
        b64 = base64.b64encode(content).decode()
        return f"data:{mime};base64,{b64}"
    
    def health(self) -> dict:
        """健康检查"""
        try:
            response = requests.get(f"{self.base_url}/api/health", timeout=5)
            return response.json()
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def get_settings(self) -> dict:
        """获取默认设置"""
        response = requests.get(f"{self.base_url}/api/settings")
        return response.json()
    
    def update_settings(self, count: int = None, ratio: str = None, model: str = None) -> dict:
        """更新默认设置"""
        payload = {}
        if count is not None:
            payload["default_count"] = count
        if ratio is not None:
            payload["default_ratio"] = ratio
        if model is not None:
            payload["default_model"] = model
        
        response = requests.post(f"{self.base_url}/api/settings", json=payload)
        return response.json()


# ============== 使用示例 ==============

if __name__ == "__main__":
    # 创建客户端
    client = GeminiImageClient("http://localhost:8000")
    
    # 检查服务状态
    print("=== 健康检查 ===")
    health = client.health()
    print(f"状态: {health}")
    
    # 示例 1: 生成单张图片
    print("\n=== 示例 1: 生成单张图片 ===")
    result = client.generate("一只可爱的橘猫")
    
    if result.success:
        print(f"✅ 成功! 生成 {result.count} 张图片")
        print(f"   账号: {result.account}")
        
        # 获取第一张图片的不同格式
        print(f"   Data URL (前80字符): {result.images[0][:80]}...")
        print(f"   纯 Base64 (前50字符): {result.get_base64_list()[0][:50]}...")
        print(f"   字节大小: {len(result.get_bytes_list()[0])} bytes")
    else:
        print(f"❌ 失败: {result.error}")
    
    # 示例 2: 生成4张图片并保存
    print("\n=== 示例 2: 生成4张图片并保存 ===")
    result = client.generate(
        prompt="赛博朋克风格的城市夜景",
        count=4,
        ratio="16:9"
    )
    
    if result.success:
        print(f"✅ 成功! 生成 {result.count} 张图片")
        
        # 保存所有图片
        saved_paths = result.save_all(directory="output", prefix="cyberpunk")
        for path in saved_paths:
            print(f"   已保存: {path}")
    else:
        print(f"❌ 失败: {result.error}")
    
    # 示例 3: 遍历处理每张图片
    print("\n=== 示例 3: 遍历处理每张图片 ===")
    result = client.generate("风景画", count=2)
    
    if result.success:
        # 方式 1: 遍历 Data URL (可直接用于 HTML img src)
        for i, data_url in enumerate(result.images):
            print(f"图片 {i+1} Data URL: {data_url[:60]}...")
        
        # 方式 2: 遍历纯 Base64
        for i, b64 in enumerate(result.get_base64_list()):
            print(f"图片 {i+1} Base64: {b64[:40]}... ({len(b64)} chars)")
        
        # 方式 3: 遍历字节数据
        for i, img_bytes in enumerate(result.get_bytes_list()):
            print(f"图片 {i+1} 大小: {len(img_bytes)} bytes")
    
    # 示例 4: 错误处理
    print("\n=== 示例 4: 错误处理 ===")
    result = client.generate("")  # 空提示词会失败
    
    if not result.success:
        print(f"预期的错误: {result.error}")
    
    print("\n=== 完成 ===")
