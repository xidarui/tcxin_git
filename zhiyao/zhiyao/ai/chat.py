"""AI对话模块 — 星火大模型 + 禁忌提醒"""
import os
import logging
import warnings

# 屏蔽 langchain 旧版 API 警告（spark-ai-python 依赖旧版 langchain）
warnings.filterwarnings("ignore", category=UserWarning, module="langchain")

from dotenv import load_dotenv
from sparkai.llm.llm import ChatSparkLLM
from sparkai.core.messages import ChatMessage

from ..db import repo as db_repo
from ..paths import ENV_FILE

load_dotenv(str(ENV_FILE))

# spark-ai-python v0.4.5 要求 IFLYTEK_SPARK_ 前缀的环境变量
# 从现有的 APP_ID/API_KEY/API_SECRET 映射过去
if os.getenv('APP_ID') and not os.getenv('IFLYTEK_SPARK_APP_ID'):
    os.environ['IFLYTEK_SPARK_APP_ID'] = os.getenv('APP_ID', '')
    os.environ['IFLYTEK_SPARK_API_KEY'] = os.getenv('API_KEY', '')
    os.environ['IFLYTEK_SPARK_API_SECRET'] = os.getenv('API_SECRET', '')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("websocket").setLevel(logging.CRITICAL)
logging.getLogger("XfyunPythonSDK").setLevel(logging.CRITICAL)

# 星火大模型配置（v3.5）
SPARKAI_URL = 'wss://spark-api.xf-yun.com/v3.1/chat'
SPARKAI_APP_ID = os.getenv('APP_ID', '')
SPARKAI_API_SECRET = os.getenv('API_SECRET', '')
SPARKAI_API_KEY = os.getenv('API_KEY', '')
SPARKAI_DOMAIN = 'generalv3'

# 全局对话历史
_global_history = None


# 禁忌提醒系统提示词
_CONTRANDICATION_PROMPT = """你是一个专业的药师助手，请遵循以下规则：

1. 当用户提到药品名称、症状或展示药品信息时，主动分析并提醒相关的【禁忌症】和【不良反应】。
2. 如果检测到可能的药物相互作用（如头孢+酒精、感冒药重复服用等），必须明确警告。
3. 回答时注意：先回答用户问题，再补充禁忌提醒。
4. 对于不确定的医学信息，明确说明"建议咨询医生"。
5. 回答应简洁、清晰，适合语音播报。
6. 当分析药方时，提取出具体的服用时间、剂量信息。
"""


def stream_chat(
    query: str, history: list = None, persist: bool = True, source: str = "text"
) -> tuple:
    """星火大模型多轮对话

    Args:
        query: 用户提问文字
        history: 对话历史列表（含 system prompt），None 则新建
        persist: 是否把这一轮问答写进数据库（内部调用如药方分析时置 False）
        source: 输入来源，text / ocr / voice / mixed

    Returns:
        (AI回复文字, 更新后的对话历史)
    """
    if history is None:
        history = [ChatMessage(role="system", content=_CONTRANDICATION_PROMPT)]

    history.append(ChatMessage(role="user", content=query))

    # 先存用户提问：即使后面模型调用失败，也能看到用户问过什么
    if persist:
        try:
            db_repo.append_message("user", query, source=source)
        except Exception as exc:  # noqa: BLE001 - 数据库故障不能影响对话
            logger.warning(f"保存用户消息失败: {exc}")

    spark = ChatSparkLLM(
        spark_api_url=SPARKAI_URL,
        spark_app_id=SPARKAI_APP_ID,
        spark_api_key=SPARKAI_API_KEY,
        spark_api_secret=SPARKAI_API_SECRET,
        spark_llm_domain=SPARKAI_DOMAIN,
        streaming=False,
    )

    try:
        response = spark.generate([history])
        ai_reply = response.generations[0][0].text
        history.append(ChatMessage(role="assistant", content=ai_reply))
        if persist:
            try:
                db_repo.append_message("assistant", ai_reply, source=source)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"保存AI回复失败: {exc}")
        return ai_reply, history
    except Exception as e:
        logger.error(f"星火大模型请求失败: {str(e)}")
        return "抱歉，AI服务暂时不可用，请稍后重试。", history


def _restore_history_from_db(limit: int = 20) -> list:
    """从数据库读回最近的对话，让「关掉程序再打开」也能接着聊"""
    history = [ChatMessage(role="system", content=_CONTRANDICATION_PROMPT)]
    try:
        rows = db_repo.get_messages(limit=limit)
    except Exception as exc:  # noqa: BLE001 - 数据库不可用时退回空历史
        logger.warning(f"读取历史对话失败，本轮从空上下文开始: {exc}")
        return history

    for row in rows:
        if row["role"] in ("user", "assistant") and row["content"]:
            history.append(ChatMessage(role=row["role"], content=row["content"]))

    if len(history) > 1:
        logger.info(f"已从数据库恢复 {len(history) - 1} 条历史消息")
    return history


def chat_with_context(
    text: str = "", image_text: str = "", source: str | None = None
) -> tuple:
    """带上下文的增强版对话

    可同时传入语音识别文字和OCR文字，AI综合理解后回答。

    Args:
        text: 语音识别的文字（用户说的症状/问题）
        image_text: OCR识别的文字（图片中的药品信息）
        source: 输入来源标签，None 则自动推断

    Returns:
        (AI回复文字, 更新后的对话历史)
    """
    global _global_history

    if _global_history is None:
        _global_history = _restore_history_from_db()

    parts = []
    if image_text:
        parts.append(f"【药品信息】\n{image_text}")
    if text:
        parts.append(f"【用户问题】\n{text}")
    if not parts:
        return "没有收到有效输入。", _global_history

    if source is None:
        if image_text and text:
            source = "mixed"
        elif image_text:
            source = "ocr"
        else:
            source = "text"

    query = "\n\n".join(parts)
    return stream_chat(query, _global_history, source=source)


def clear_history(clear_db: bool = True):
    """清除对话历史（内存 + 数据库）"""
    global _global_history
    _global_history = None
    if clear_db:
        try:
            removed = db_repo.clear_messages()
            logger.info(f"已从数据库删除 {removed} 条历史消息")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"清空数据库对话历史失败: {exc}")


def analyze_medication_schedule(ocr_text: str) -> str:
    """分析药品信息，提取用法用量

    Args:
        ocr_text: OCR识别的药品说明书/药方文字

    Returns:
        str: AI分析的用药建议（含时间和剂量）
    """
    prompt = f"""请分析以下药品信息，提取出完整的用法用量信息。
请按此格式输出：
【药品名称】xxx
【用法用量】xxx
【服用时间】推荐几点服用
【注意事项】xxx

如果信息不完整，请根据常识补充建议，但注明"此为AI建议，请遵医嘱"。

药品信息：
{ocr_text}"""
    reply, _ = stream_chat(
        prompt,
        [ChatMessage(role="system", content=_CONTRANDICATION_PROMPT)],
        persist=False,  # 这是内部用的结构化分析，不算用户对话，不写库
    )
    return reply
