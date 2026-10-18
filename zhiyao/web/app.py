"""
知药 · FastAPI 服务入口（网页版）

启动方式::

    python -m zhiyao.web.app          # 在仓库根目录执行

访问地址: http://localhost:8000

集成了:
- POST /api/chat   → zhiyao.ai.chat      星火大模型
- POST /api/ocr    → zhiyao.ocr.client   讯飞 OCR
- POST /api/tts    → zhiyao.speech.tts   方言语音合成
- GET  /api/voices → 方言列表
- 其余 /api/plans /api/logs /api/history 见 zhiyao/db
"""
import os
import sys
import uuid
import logging
from datetime import datetime

# 支持直接 `python zhiyao/web/app.py` 运行：把仓库根加进 sys.path
if __package__ in (None, ""):  # pragma: no cover
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from dotenv import load_dotenv
import uvicorn

from zhiyao.paths import ENV_FILE, INDEX_HTML

# 先加载 .env，让子模块的 load_dotenv() 继承已有环境变量
load_dotenv(str(ENV_FILE))

# 检查 API 凭证
_missing = [k for k in ['APP_ID', 'API_KEY', 'API_SECRET'] if not os.getenv(k)]
if _missing:
    logging.warning(f"⚠️ .env 缺失凭证: {', '.join(_missing)}，API 调用将返回错误")

# 导入后端模块
from zhiyao.ai.chat import chat_with_context, clear_history
from zhiyao.ocr.client import universal_ocr
from zhiyao.speech.tts import speech_synthesis
from zhiyao.db import repo as db_repo
from zhiyao.reminder.alarm import AlarmScheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="知药智能服药助手")

# ========================
#  数据库 & 闹钟初始化
# ========================

_db_ready = True
try:
    db_repo.init_tables()
    logger.info("数据库已就绪")
except Exception as _e:  # noqa: BLE001 - 数据库挂了服务仍要能起，只是相关接口报错
    _db_ready = False
    logger.warning(f"数据库初始化失败，数据相关接口将不可用: {_e}")


def _alarm_tts(text: str) -> None:
    """闹钟到点 → 服务器本机声卡播报"""
    try:
        speech_synthesis("x4_yezi", text)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"闹钟语音播报失败: {exc}")


def _alarm_on_fire(alarm: dict) -> None:
    """闹钟触发 → 写一条待服药记录"""
    try:
        db_repo.record_dose(
            alarm.get("medication", "未知药品"),
            plan_id=alarm.get("plan_id"),
            status="pending",
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(f"写服药记录失败: {exc}")


_scheduler = AlarmScheduler(_alarm_tts, on_fire=_alarm_on_fire)


def _reload_alarms() -> int:
    """把数据库里启用的提醒计划重新装载到调度器，返回装载数量"""
    if not _db_ready:
        return 0
    try:
        plans = db_repo.load_plan_dicts(active_only=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"读取提醒计划失败: {exc}")
        return 0
    _scheduler.set_alarms(plans)
    return len(plans)

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

# 启动时恢复上次保存的提醒计划（数据库不可用则跳过）
try:
    _restored = _reload_alarms()
    if _restored:
        logger.info(f"已从数据库恢复 {_restored} 个提醒计划")
except Exception as _e:  # noqa: BLE001
    logger.warning(f"恢复提醒计划失败: {_e}")


# ========================
#  数据库相关 Pydantic 模型
# ========================

class PlanIn(BaseModel):
    time: str
    medication: str
    note: str = ""


class PlanOut(BaseModel):
    id: int
    time: str
    medication: str
    note: str = ""
    enabled: bool = True
    repeat_daily: bool = True


class PlanToggle(BaseModel):
    enabled: bool


class LogOut(BaseModel):
    id: int
    plan_id: int | None = None
    medication_name: str
    scheduled_at: datetime | None = None
    taken_at: datetime | None = None
    status: str


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    source: str
    created_at: datetime | None = None


class CheckinIn(BaseModel):
    plan_id: int


class TodayOut(BaseModel):
    id: int
    time: str
    medication: str
    note: str = ""
    taken: bool = False
    status: str = "pending"
    log_id: int | None = None


def _require_db() -> None:
    """数据库不可用时就返回 503，而不是抛一堆 500"""
    if not _db_ready:
        raise HTTPException(status_code=503, detail="数据库不可用，请检查 MySQL 服务")

# ========================
#  API 路由
# ========================

@app.get("/")
def index():
    """返回前端页面"""
    index_path = str(INDEX_HTML)
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
    return {
        "status": "ok" if not missing else "degraded",
        "missing_keys": missing,
        "database": "ok" if _db_ready else "unavailable",
        "armed_alarms": _scheduler.active_count,
    }


# ========================
#  数据库接口：提醒计划 / 服药记录 / 对话历史
# ========================

@app.get("/api/plans", response_model=list[PlanOut], tags=["数据库"])
def get_plans(active_only: bool = False):
    """查询所有提醒计划"""
    _require_db()
    return db_repo.list_plans(active_only=active_only)


@app.post("/api/plans", response_model=list[PlanOut], tags=["数据库"])
def create_plans(items: list[PlanIn]):
    """整批保存提醒计划

    覆盖式语义：本次列表里没有的旧计划会被删除，并同步重新装载闹钟。
    """
    _require_db()
    db_repo.save_plans([i.model_dump() for i in items])
    _reload_alarms()
    return db_repo.list_plans()


@app.patch("/api/plans/{plan_id}", response_model=PlanOut, tags=["数据库"])
def toggle_plan(plan_id: int, body: PlanToggle):
    """启用 / 停用某个提醒计划"""
    _require_db()
    if not db_repo.set_plan_enabled(plan_id, body.enabled):
        raise HTTPException(status_code=404, detail=f"计划 {plan_id} 不存在")
    _reload_alarms()
    for plan in db_repo.list_plans():
        if plan["id"] == plan_id:
            return plan
    raise HTTPException(status_code=404, detail=f"计划 {plan_id} 不存在")


@app.delete("/api/plans/{plan_id}", tags=["数据库"])
def remove_plan(plan_id: int):
    """删除某个提醒计划（历史服药记录会保留，plan_id 置空）"""
    _require_db()
    if not db_repo.delete_plan(plan_id):
        raise HTTPException(status_code=404, detail=f"计划 {plan_id} 不存在")
    _reload_alarms()
    return {"deleted": plan_id}


@app.get("/api/logs", response_model=list[LogOut], tags=["数据库"])
def get_logs(limit: int = 50):
    """查询服药记录"""
    _require_db()
    return db_repo.list_dose_logs(limit=max(1, min(limit, 500)))


@app.post("/api/logs/{log_id}/taken", tags=["数据库"])
def mark_log_taken(log_id: int):
    """把某条记录标记为「已服药」"""
    _require_db()
    if not db_repo.mark_taken(log_id):
        raise HTTPException(status_code=404, detail=f"记录 {log_id} 不存在")
    return {"id": log_id, "status": "taken", "taken_at": datetime.now()}


@app.get("/api/history", response_model=list[MessageOut], tags=["数据库"])
def get_chat_history(limit: int = 50):
    """查询对话历史"""
    _require_db()
    return db_repo.get_messages(limit=max(1, min(limit, 200)))


@app.delete("/api/history", tags=["数据库"])
def clear_chat_history():
    """清空对话历史（内存 + 数据库）"""
    _require_db()
    removed = db_repo.clear_messages()
    clear_history(clear_db=False)
    return {"deleted": removed}


@app.get("/api/stats", tags=["数据库"])
def get_stats():
    """各表行数汇总"""
    _require_db()
    return db_repo.stats()


@app.get("/api/today", response_model=list[TodayOut], tags=["数据库"])
def get_today():
    """前端主用接口：今天的提醒计划 + 是否已服药"""
    _require_db()
    return db_repo.get_today_status()


@app.post("/api/checkin", tags=["数据库"])
def do_checkin(body: CheckinIn):
    """网页端点「已服药」时调用，落到 dose_log 表"""
    _require_db()
    result = db_repo.checkin(body.plan_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"计划 {body.plan_id} 不存在")
    return result

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
