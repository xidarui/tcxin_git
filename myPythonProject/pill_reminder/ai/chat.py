"""AI对话模块 — 星火大模型 + 禁忌提醒"""
import os
import logging
import warnings

# 屏蔽 langchain 旧版 API 警告（spark-ai-python 依赖旧版 langchain）
warnings.filterwarnings("ignore", category=UserWarning, module="langchain")

from dotenv import load_dotenv
from sparkai.llm.llm import ChatSparkLLM
from sparkai.core.messages import ChatMessage

_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(_env_path)
load_dotenv()

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


def stream_chat(query: str, history: list = None) -> tuple:
    """星火大模型多轮对话

    Args:
        query: 用户提问文字
        history: 对话历史列表（含 system prompt），None 则新建

    Returns:
        (AI回复文字, 更新后的对话历史)
    """
    if history is None:
        history = [ChatMessage(role="system", content=_CONTRANDICATION_PROMPT)]

    history.append(ChatMessage(role="user", content=query))

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
        return ai_reply, history
    except Exception as e:
        logger.error(f"星火大模型请求失败: {str(e)}")
        return "抱歉，AI服务暂时不可用，请稍后重试。", history


def chat_with_context(text: str = "", image_text: str = "") -> tuple:
    """带上下文的增强版对话

    可同时传入语音识别文字和OCR文字，AI综合理解后回答。

    Args:
        text: 语音识别的文字（用户说的症状/问题）
        image_text: OCR识别的文字（图片中的药品信息）

    Returns:
        (AI回复文字, 更新后的对话历史)
    """
    global _global_history

    if _global_history is None:
        _global_history = [ChatMessage(role="system", content=_CONTRANDICATION_PROMPT)]

    parts = []
    if image_text:
        parts.append(f"【药品信息】\n{image_text}")
    if text:
        parts.append(f"【用户问题】\n{text}")
    if not parts:
        return "没有收到有效输入。", _global_history

    query = "\n\n".join(parts)
    return stream_chat(query, _global_history)


def clear_history():
    """清除对话历史"""
    global _global_history
    _global_history = None


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
    reply, _ = stream_chat(prompt, [ChatMessage(role="system", content=_CONTRANDICATION_PROMPT)])
    return reply
