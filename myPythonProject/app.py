"""
知药 · FastAPI 服务入口

启动方式: python app.py
访问地址: http://localhost:8000

集成了:
- POST /api/chat  → ai/chat.py  → 星火大模型
- POST /api/ocr  → ocr/client.py → 讯飞 OCR
- POST /api/tts  → speech/tts.py → 方言语音合成
- GET  /api/voices → 方言列表
"""
import os
import sys
import uuid
import logging

# 确保能找到 pill_reminder 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from dotenv import load_dotenv
import uvicorn

# 先加载 .env，让子模块的 load_dotenv() 继承已有环境变量
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pill_reminder', '.env')
load_dotenv(_env_path)

# 检查 API 凭证
_missing = [k for k in ['APP_ID', 'API_KEY', 'API_SECRET'] if not os.getenv(k)]
if _missing:
    logging.warning(f"⚠️ .env 缺失凭证: {', '.join(_missing)}，API 调用将返回错误")

# 导入后端模块
from pill_reminder.ai.chat import chat_with_context, clear_history
from pill_reminder.ocr.client import universal_ocr
from pill_reminder.speech.tts import speech_synthesis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="知药智能服药助手")

# ========================
#  Pydantic 请求/响应模型
# ========================

class ChatRequest(BaseModel):
    text: str = ""
    image_text: str = ""
    reset: bool = False

class ChatResponse(BaseModel):
    reply: str
    error: str | None = None

class OcrResponse(BaseModel):
    text_lines: list[str]
    text: str
    error: str | None = None

class TtsRequest(BaseModel):
    text: str
    voice: str = "x4_yezi"
    speed: float = 0.9
    volume: float = 0.9

class VoicesResponse(BaseModel):
    voices: dict[str, str]
    current: str

# 发音人数据
_VOICES = {
    "x4_yezi": "普通话",
    "x_xiaomei": "粤语",
    "x3_linlin": "闽南语",
    "x2_xiaobao": "内蒙古",
    "x3_yezi_sc": "四川话",
    "x4_xiaobei": "东北话",
    "x2_xiaokun": "河南话",
    "x3_xiaodu": "成都话",
}

# ========================
#  API 路由
# ========================

@app.get("/")
def index():
    """返回前端页面"""
    index_path = os.path.join(os.path.dirname(__file__), 'index.html')
    return FileResponse(index_path)

@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """AI 对话 — 调用星火大模型"""
    if req.reset:
        clear_history()
        return ChatResponse(reply="🧹 对话历史已重置", error=None)
    try:
        reply, _ = chat_with_context(text=req.text, image_text=req.image_text)
        return ChatResponse(reply=reply, error=None)
    except Exception as e:
        logger.error(f"Chat API 错误: {e}")
        return ChatResponse(reply="❌ AI服务暂时不可用，请稍后重试", error=str(e))

@app.post("/api/ocr", response_model=OcrResponse)
async def ocr(file: UploadFile = File(...)):
    """OCR 图片识别 — 上传图片，返回文字"""
    # 校验文件类型
    allowed = {'.jpg', '.jpeg', '.png', '.bmp'}
    ext = os.path.splitext(file.filename or '')[1].lower()
    if ext not in allowed:
        return OcrResponse(text_lines=[], text="", error=f"不支持的文件格式 {ext}，支持 jpg/png/bmp")

    # 先检查 Content-Length 再读内存（防 OOM）
    max_bytes = 10 * 1024 * 1024
    content_length = file.size or 0
    if content_length > max_bytes:
        return OcrResponse(text_lines=[], text="", error="文件过大，请上传小于 10MB 的图片")

    contents = await file.read()
    if len(contents) > max_bytes:
        return OcrResponse(text_lines=[], text="", error="文件过大，请上传小于 10MB 的图片")

    # 保存到临时文件（UUID 防并发冲突）
    tmp_name = f'_tmp_ocr_{uuid.uuid4().hex}{ext}'
    tmp_path = os.path.join(os.path.dirname(__file__), tmp_name)
    try:
        with open(tmp_path, 'wb') as f:
            f.write(contents)

        lines = universal_ocr(tmp_path)
        text = "\n".join(lines)
        return OcrResponse(text_lines=lines, text=text, error=None)
    except FileNotFoundError:
        return OcrResponse(text_lines=[], text="", error="图片文件不存在")
    except PermissionError as e:
        return OcrResponse(text_lines=[], text="", error=f"OCR授权失败: {e}")
    except ValueError as e:
        return OcrResponse(text_lines=[], text="", error=str(e))
    except Exception as e:
        logger.error(f"OCR API 错误: {e}")
        return OcrResponse(text_lines=[], text="", error=f"OCR识别失败: {e}")
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

@app.post("/api/tts")
def tts(req: TtsRequest):
    """方言语音合成 — 返回 WAV 音频流"""
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="text 不能为空")
    if len(req.text) > 500:
        raise HTTPException(status_code=400, detail="text 超过 500 字限制")
    if req.voice not in _VOICES:
        raise HTTPException(status_code=400, detail=f"不支持的方言: {req.voice}")

    try:
        tmp_name = f'_tmp_tts_{uuid.uuid4().hex}.wav'
        file_path = speech_synthesis(req.voice, req.text, filename=tmp_name, play=False, speed=req.speed, volume=req.volume)
        with open(file_path, 'rb') as f:
            audio_data = f.read()
        # 清理临时文件
        try:
            os.remove(file_path)
        except OSError:
            pass
        return Response(content=audio_data, media_type="audio/wav")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"TTS API 错误: {e}")
        raise HTTPException(status_code=502, detail=f"语音合成失败: {e}")

@app.get("/api/voices", response_model=VoicesResponse)
def voices():
    """返回方言列表"""
    return VoicesResponse(voices=_VOICES, current="x4_yezi")

@app.get("/health")
def health():
    """健康检查"""
    missing = [k for k in ['APP_ID', 'API_KEY', 'API_SECRET'] if not os.getenv(k)]
    return {"status": "ok" if not missing else "degraded", "missing_keys": missing}

# ========================
#  启动
# ========================

if __name__ == "__main__":
    # PORT 环境变量可能被设为无效值（如 "0"），此时回退到默认端口
    try:
        port_env = os.getenv("PORT", "")
        port = int(port_env) if port_env and int(port_env) > 0 else 8000
    except (ValueError, TypeError):
        port = 8000
    print(f"[知药] 智能服药助手启动!")
    print(f"   访问地址: http://localhost:{port}")
    print(f"   API文档:  http://localhost:{port}/docs")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
