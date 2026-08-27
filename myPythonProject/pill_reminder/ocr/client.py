"""通用文字识别模块 — 图片→文字"""
import json
import logging
import os
import base64
import httpx
from dotenv import load_dotenv
from xfyunsdkcore.signature import Signature

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

UNIVERSAL_OCR_URL = "https://api.xf-yun.com/v1/private/sf8e6aca1"
SERVICE_ID = "sf8e6aca1"


def universal_ocr(image_path: str = None) -> list[str]:
    """通用文字识别

    Args:
        image_path: 图片路径，默认使用项目根目录的 picture.jpg

    Returns:
        list[str]: 识别到的文本行列表
    """
    text_lines = []
    app_id = os.getenv('APP_ID')
    api_key = os.getenv('API_KEY')
    api_secret = os.getenv('API_SECRET')

    if not app_id or not api_key or not api_secret:
        raise ValueError("请在 .env 文件中配置 APP_ID、API_KEY 和 API_SECRET")

    try:
        if image_path is None:
            image_path = os.path.abspath(os.path.join(
                os.path.dirname(__file__), '..', 'picture.jpg'
            ))
        elif not os.path.isabs(image_path):
            image_path = os.path.abspath(image_path)

        if not os.path.exists(image_path):
            raise FileNotFoundError(f"图片文件不存在: {image_path}")

        # 从文件扩展名推断图片编码格式
        _, ext = os.path.splitext(image_path)
        ext = ext.lower().lstrip('.')
        encoding_map = {
            'jpg': 'jpg', 'jpeg': 'jpg',
            'png': 'png', 'bmp': 'bmp',
            'gif': 'gif',
        }
        image_encoding = encoding_map.get(ext, 'jpg')
        if image_encoding == 'jpg':
            encode_format = 'jpg'
        else:
            encode_format = image_encoding

        with open(image_path, "rb") as file:
            image_base64 = str(base64.b64encode(file.read()), 'utf-8')

        logger.info(f"图片已读取: {image_path} (格式: {encode_format})")

        body = {
            "header": {
                "app_id": app_id,
                "status": 3,
            },
            "parameter": {
                SERVICE_ID: {
                    "category": "ch_en_public_cloud",
                    "result": {
                        "encoding": "utf8",
                        "format": "json",
                        "compress": "raw",
                    }
                }
            },
            "payload": {
                f"{SERVICE_ID}_data_1": {
                    "encoding": encode_format,
                    "image": image_base64,
                    "status": 3
                }
            }
        }

        signed_url = Signature.create_signed_url(
            UNIVERSAL_OCR_URL, api_key, api_secret, "POST"
        )
        logger.info("签名 URL 已生成")

        with httpx.Client(timeout=120) as http_client:
            resp = http_client.post(signed_url, json=body)
        json_resp = json.loads(resp.text)

        if json_resp.get("header", {}).get("code") == 0:
            logger.info("识别成功！")
            payload = json_resp.get("payload", {})
            result_key = f"{SERVICE_ID}_data_1"
            if result_key not in payload:
                result_key = "result"
            if payload and result_key in payload:
                result_data = payload[result_key]
                text_base64 = result_data.get("text", "")
                if text_base64:
                    text = base64.b64decode(text_base64).decode("utf-8")
                    result_json = json.loads(text)
                    pages = result_json.get("pages", [])
                    for page in pages:
                        lines = page.get("lines", [])
                        for line in lines:
                            line_text = line.get("content", "")
                            if line_text:
                                text_lines.append(line_text)
                    logger.info(f"识别文本列表: {text_lines}")
        else:
            code = json_resp.get("header", {}).get("code")
            message = json_resp.get("header", {}).get("message", "")
            logger.error(f"识别失败: {json_resp}")
            if code in (11200, 11201) or "licc" in message.lower():
                raise PermissionError(
                    f"OCR服务授权失败（{code}: {message}）。\n"
                    f"💡 请登录讯飞开放平台 → 控制台 → 找到应用APP_ID={app_id}\n"
                    f"   → 确保已开通「通用文字识别」服务"
                )

        return text_lines

    except PermissionError:
        raise
    except Exception as e:
        logger.error(f"OCR发生错误: {str(e)}")
        raise
