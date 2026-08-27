# 智能提醒吃药系统 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将杂乱的讯飞API测试代码重构为功能模块化的智能提醒吃药系统

**Architecture:** 按功能划分为4个Python包（ocr, speech, ai, reminder），通过main.py统一编排。数据流：OCR/语音 → 文字 → AI大模型（含禁忌提醒）→ TTS方言朗读，定时闹钟由AI分析药方后自动生成。

**Tech Stack:** Python 3, 讯飞SDK (xfyunsdkspeech/xfyunsdkocr), 星火大模型 (sparkai), PyAudio

**旧文件引用对照（不删除旧文件，仅在新区引用）：**
- `speech/iat_progress/tts_test.py` → `pill_reminder/speech/tts.py`
- `speech/iat_test.py` → `pill_reminder/speech/iat.py`
- `speech/resources/intisig_ocr_test.py` → `pill_reminder/ocr/client.py`
- `speech/chat_with_ai/小组项目/chat_with_ai.py` → `pill_reminder/ai/chat.py`

---
### 前置准备

- [ ] **Step: 创建新目录结构**

```bash
mkdir -p pill_reminder/ocr pill_reminder/speech pill_reminder/ai pill_reminder/reminder
```

---

### Task 1: 基础文件（.env, __init__.py, requirements.txt）

**Files:**
- Create: `pill_reminder/.env`
- Create: `pill_reminder/requirements.txt`
- Create: `pill_reminder/ocr/__init__.py`
- Create: `pill_reminder/speech/__init__.py`
- Create: `pill_reminder/ai/__init__.py`
- Create: `pill_reminder/reminder/__init__.py`
- Copy: `picture.jpg` → `pill_reminder/picture.jpg`

**Interfaces:**
- Produces: 空包初始化文件，供后续模块导入

- [ ] **Step 1: 复制.env文件**

```bash
cp .env pill_reminder/.env
```

- [ ] **Step 2: 复制测试图片**

```bash
cp speech/resources/picture.jpg pill_reminder/picture.jpg 2>/dev/null; ls pill_reminder/picture.jpg 2>/dev/null || cp speech/resources/picture.jpg pill_reminder/picture.jpg 2>/dev/null; ls -la pill_reminder/picture.jpg 2>/dev/null || cp myPythonProject/speech/resources/picture.jpg pill_reminder/. && echo "ok"
```

（如果旧picture.jpg不在resources下，则在根目录找）

- [ ] **Step 3: 创建requirements.txt**

```bash
cat > pill_reminder/requirements.txt << 'EOF'
xfyun-sdk-speech>=1.0.0
xfyun-sdk-ocr>=1.0.0
sparkai>=1.0.0
pyaudio>=0.2.11
httpx>=0.24.0
python-dotenv>=1.0.0
EOF
```

- [ ] **Step 4: 创建所有__init__.py**

```bash
echo '"""OCR模块 — 通用文字识别"""' > pill_reminder/ocr/__init__.py
echo '"""语音模块 — 语音识别与合成"""' > pill_reminder/speech/__init__.py
echo '"""AI模块 — 星火大模型对话"""' > pill_reminder/ai/__init__.py
echo '"""提醒模块 — 定时闹钟"""' > pill_reminder/reminder/__init__.py
```

---

### Task 2: `speech/tts.py` — 方言语音合成

**Files:**
- Create: `pill_reminder/speech/tts.py`

**Interfaces:**
- Produces: `speech_synthesis(choose: str, text: str, filename: str = "output.wav") -> str`

- [ ] **Step 1: 创建 speech/tts.py**

从 `speech/iat_progress/tts_test.py` 提取关键函数，移除该文件中重复的 `synthesize_to_bytes()` 内部函数（已集成到主函数中），保留 `speech_synthesis()` 和 `play_pcm_direct()`。

```python
"""语音合成模块 — 文字转方言语音"""
import os
import base64
import wave
import logging
from dotenv import load_dotenv
from xfyunsdkspeech.tts_client import TtsClient

load_dotenv()

RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger('websocket').setLevel(logging.CRITICAL)
logging.getLogger('XfyunPythonSDK').setLevel(logging.CRITICAL)


def synthesize_to_bytes(choose: str, text: str) -> bytes:
    """将文字合成为 PCM 音频字节数据（不保存、不播放）"""
    client = TtsClient(
        app_id=os.getenv("APP_ID"),
        api_key=os.getenv("API_KEY"),
        api_secret=os.getenv("API_SECRET"),
        vcn=choose,
        aue="raw",
        speed=60
    )
    pcm_bytes = bytearray()
    for chunk in client.stream(text):
        if "audio" in chunk and chunk["audio"]:
            decode_data = base64.b64decode(chunk["audio"])
            pcm_bytes.extend(decode_data)
    if not pcm_bytes:
        raise RuntimeError("未收到音频数据")
    return bytes(pcm_bytes)


def play_pcm_direct(pcm_data: bytes):
    """纯内存 PCM 字节流直接声卡播放"""
    import pyaudio
    p = pyaudio.PyAudio()
    stream = p.open(
        format=p.get_format_from_width(SAMPLE_WIDTH),
        channels=CHANNELS,
        rate=RATE,
        output=True
    )
    stream.write(pcm_data)
    stream.stop_stream()
    stream.close()
    p.terminate()


def speech_synthesis(choose: str, text: str, filename: str = "output.wav") -> str:
    """语音合成主函数：生成PCM → 保存wav → 声卡播放

    Args:
        choose: 发音人参数（方言选择）
                "x4_yezi"=普通话  "x3_linlin"=闽南语  "x2_xiaobao"=内蒙古
                "x3_yezi_sc"=四川话  "x4_xiaobei"=东北话
                "x2_xiaokun"=河南话  "x3_xiaodu"=成都话
        text: 要合成语音的文字
        filename: 输出wav文件名
    Returns:
        str: 音频文件绝对路径
    """
    pcm_bytes = synthesize_to_bytes(choose, text)
    file_path = os.path.abspath(filename)
    with wave.open(file_path, mode="wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(RATE)
        wf.writeframes(pcm_bytes)
    logger.info(f"音频已保存: {file_path}")
    play_pcm_direct(pcm_bytes)
    return file_path
```

- [ ] **Step 2: 验证导入**

```bash
cd pill_reminder && python -c "from speech.tts import speech_synthesis; print('speech/tts.py OK')"
```

期望输出: `speech/tts.py OK`

---

### Task 3: `speech/iat.py` — 语音识别

**Files:**
- Create: `pill_reminder/speech/iat.py`

**Interfaces:**
- Produces: `microphone_stream() -> str`

- [ ] **Step 1: 创建 speech/iat.py**

从根目录 `speech/iat_test.py` 提取 `microphone_stream()`，移除 `stream()` 文件识别函数（本系统暂不需要）。

```python
"""语音识别模块 — 麦克风录音→文字"""
import os
import time
import threading
import logging
from dotenv import load_dotenv
from xfyunsdkspeech.iat_client import IatClient

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger('websocket').setLevel(logging.CRITICAL)
logging.getLogger("XfyunPythonSDK").setLevel(logging.CRITICAL)


def microphone_stream() -> str:
    """麦克风实时录音+流式语音识别，返回识别完成的文字

    操作：按回车开始录音→说话→按回车结束→返回识别结果
    """
    import pyaudio
    try:
        client = IatClient(
            app_id=os.getenv('APP_ID'),
            api_key=os.getenv('API_KEY'),
            api_secret=os.getenv('API_SECRET'),
            dwa="wpgs",
            vad_eos=3000
        )

        time.sleep(1)
        print("\n🎤 按回车开始说话...")
        input()
        print("🎤 正在聆听，说完请按回车结束...")

        p = pyaudio.PyAudio()
        mic_stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=1280
        )

        stop_event = threading.Event()
        final_text = ""
        thread_exception = None

        def run():
            nonlocal final_text, thread_exception
            try:
                for chunk in client.stream(mic_stream):
                    if stop_event.is_set():
                        break
                    result = chunk.get("result", {})
                    words = result.get("ws", [])
                    if chunk.get("status") == 2:
                        break
                    if words:
                        final_text = ""
                        for w in words:
                            if w.get("cw"):
                                final_text += w["cw"][0]["w"]
            except Exception as e:
                thread_exception = e

        thread = threading.Thread(target=run)
        thread.start()

        input()
        stop_event.set()
        mic_stream.stop_stream()
        mic_stream.close()
        thread.join(timeout=3)
        p.terminate()

        if thread_exception and not final_text:
            logger.warning(f"录音异常: {thread_exception}")

        return final_text

    except Exception as e:
        logger.error(f"语音识别失败: {str(e)}")
        return ""
```

- [ ] **Step 2: 验证导入**

```bash
cd pill_reminder && python -c "from speech.iat import microphone_stream; print('speech/iat.py OK')"
```

期望输出: `speech/iat.py OK`

---

### Task 4: `ocr/client.py` — 通用文字识别

**Files:**
- Create: `pill_reminder/ocr/client.py`

**Interfaces:**
- Produces: `universal_ocr(image_path: str = None) -> list[str]`

- [ ] **Step 1: 创建 ocr/client.py**

从 `speech/resources/intisig_ocr_test.py` 提取 `universal_ocr()`，移除 `old_webapi_general()` 和底部的 `__main__` 测试代码。

```python
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

        with open(image_path, "rb") as file:
            image_base64 = str(base64.b64encode(file.read()), 'utf-8')

        logger.info(f"图片已读取: {image_path}")

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
                    "encoding": "jpg",
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
            logger.error(f"识别失败: {json_resp}")

        return text_lines

    except Exception as e:
        logger.error(f"OCR发生错误: {str(e)}")
        raise
```

- [ ] **Step 2: 验证导入**

```bash
cd pill_reminder && python -c "from ocr.client import universal_ocr; print('ocr/client.py OK')"
```

期望输出: `ocr/client.py OK`

---

### Task 5: `ai/chat.py` — 星火大模型对话（含禁忌提醒）

**Files:**
- Create: `pill_reminder/ai/chat.py`

**Interfaces:**
- Produces:
  - `stream_chat(query: str, history: list = None) -> tuple[str, list]`
  - `chat_with_context(text: str = "", image_text: str = "") -> tuple[str, list]`
  - `clear_history() -> None`

- [ ] **Step 1: 创建 ai/chat.py**

从 `speech/chat_with_ai/小组项目/chat_with_ai.py` 提取核心逻辑，新增禁忌提醒 system prompt 和 `chat_with_context()` 函数。

```python
"""AI对话模块 — 星火大模型 + 禁忌提醒"""
import os
import logging
from dotenv import load_dotenv
from sparkai.llm.llm import ChatSparkLLM
from sparkai.core.messages import ChatMessage

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("websocket").setLevel(logging.CRITICAL)
logging.getLogger("XfyunPythonSDK").setLevel(logging.CRITICAL)

# 星火大模型配置（v3.5 支持更好的禁忌提醒效果）
SPARKAI_URL = 'wss://spark-api.xf-yun.com/v3.5/chat'
SPARKAI_APP_ID = os.getenv('APP_ID', '')
SPARKAI_API_SECRET = os.getenv('API_SECRET', '')
SPARKAI_API_KEY = os.getenv('API_KEY', '')
SPARKAI_DOMAIN = 'generalv3.5'

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
    """星火大模型流式多轮对话

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
        streaming=False,  # 非流式，批量返回完整结果
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

    # 构建输入信息
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
```

- [ ] **Step 2: 验证导入**

```bash
cd pill_reminder && python -c "from ai.chat import stream_chat, chat_with_context, clear_history; print('ai/chat.py OK')"
```

期望输出: `ai/chat.py OK`

---

### Task 6: `reminder/alarm.py` — 定时闹钟

**Files:**
- Create: `pill_reminder/reminder/alarm.py`

**Interfaces:**
- Produces:
  - `parse_schedule(ai_reply: str) -> list[dict]`
  - `AlarmScheduler` — 闹钟调度类

- [ ] **Step 1: 创建 reminder/alarm.py**

新建模块：解析AI返回的用药时间表，定时触发TTS播报。

```python
"""定时提醒模块 — 闹钟引擎"""
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Callable

logger = logging.getLogger(__name__)


def parse_time_from_text(time_str: str) -> str:
    """将自然语言时间转为 HH:MM 格式

    支持：'早上8点'→'08:00'  '中午12点'→'12:00'  '晚上6点'→'18:00'
    """
    time_str = time_str.strip().replace('：', ':')
    # 尝试直接匹配 HH:MM
    try:
        datetime.strptime(time_str, '%H:%M')
        return time_str
    except ValueError:
        pass

    # 中文时间解析
    mapping = {
        '早上': '08', '早晨': '08', '上午': '09',
        '中午': '12', '下午': '14',
        '晚上': '18', '傍晚': '17', '睡前': '21',
    }
    result = time_str
    for cn, h in mapping.items():
        if cn in time_str:
            result = time_str.replace(cn, h)
            break

    # 提取数字
    import re
    match = re.findall(r'(\d{1,2})', result)
    if len(match) >= 1:
        hour = int(match[0])
        minute = int(match[1]) if len(match) >= 2 else 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"

    # 默认返回原字符串
    return time_str


def parse_schedule(ai_reply: str) -> list[dict]:
    """从AI回复中解析用药时间表

    Args:
        ai_reply: AI分析药方后的回复文字

    Returns:
        list[dict]: [{"time": "08:00", "medication": "头孢拉定 1粒", "note": "饭后服用"}, ...]
    """
    import re
    schedule = []

    # 尝试匹配 "HH:MM" 时间格式
    time_pattern = re.compile(r'(\d{1,2}:\d{2})')
    lines = ai_reply.split('\n')

    current_time = None
    current_med = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 检测时间
        time_match = time_pattern.search(line)
        if time_match:
            if current_time and current_med:
                schedule.append({
                    "time": current_time,
                    "medication": current_med,
                    "note": ""
                })
            current_time = time_match.group(1)
            current_med = line
        elif current_time:
            current_med += " " + line

    # 最后一条
    if current_time and current_med:
        schedule.append({
            "time": current_time,
            "medication": current_med,
            "note": ""
        })

    return schedule


class AlarmScheduler:
    """闹钟调度器 — 到点自动播报语音"""

    def __init__(self, tts_callback: Callable[[str], None]):
        """
        Args:
            tts_callback: 到点触发的函数，接收播报文字
        """
        self.tts_callback = tts_callback
        self._timers = []
        self._running = False

    def set_alarms(self, alarms: list[dict]) -> None:
        """设置多个闹钟

        alarms: [{"time": "08:00", "medication": "头孢拉定 1粒", "note": "饭后服用"}, ...]
        """
        self.clear_alarms()
        now = datetime.now()

        for alarm in alarms:
            try:
                alarm_time = datetime.strptime(alarm["time"], "%H:%M")
                target = now.replace(
                    hour=alarm_time.hour,
                    minute=alarm_time.minute,
                    second=0,
                    microsecond=0
                )
                # 如果今天已过这个时间，推到明天
                if target <= now:
                    target += timedelta(days=1)

                delay = (target - now).total_seconds()
                medication = alarm.get("medication", "请按时服药")
                note = alarm.get("note", "")

                text = f"⏰ 吃药时间到！请服用 {medication}"
                if note:
                    text += f"，{note}"

                timer = threading.Timer(delay, self._on_alarm, args=[text])
                timer.daemon = True
                self._timers.append(timer)
                timer.start()

                logger.info(f"已设置闹钟: {alarm['time']} → {medication}")
            except (ValueError, KeyError) as e:
                logger.warning(f"闹钟格式无效: {alarm}, 错误: {e}")

    def _on_alarm(self, text: str):
        """闹钟触发"""
        logger.info(f"⏰ 闹钟触发: {text}")
        if self.tts_callback:
            self.tts_callback(text)

    def clear_alarms(self):
        """清除所有闹钟"""
        for timer in self._timers:
            timer.cancel()
        self._timers.clear()

    @property
    def active_count(self) -> int:
        return len(self._timers)
```

- [ ] **Step 2: 验证导入**

```bash
cd pill_reminder && python -c "from reminder.alarm import AlarmScheduler, parse_schedule; print('reminder/alarm.py OK')"
```

期望输出: `reminder/alarm.py OK`

---

### Task 7: `main.py` — 主入口

**Files:**
- Create: `pill_reminder/main.py`

**Interfaces:**
- Consumes: 所有模块
- Produces: 交互式主菜单

- [ ] **Step 1: 创建 main.py**

```python
"""智能提醒吃药系统 — 主入口"""
import os
import sys
import logging

# 确保可以找到同目录下的包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ocr.client import universal_ocr
from speech.iat import microphone_stream
from speech.tts import speech_synthesis
from ai.chat import chat_with_context, clear_history, analyze_medication_schedule
from reminder.alarm import AlarmScheduler, parse_schedule

# ---------- 日志配置 ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- 发音人菜单 ----------
VOICES = {
    "1": ("x4_yezi", "普通话"),
    "2": ("x3_linlin", "闽南语"),
    "3": ("x2_xiaobao", "内蒙古"),
    "4": ("x3_yezi_sc", "四川话"),
    "5": ("x4_xiaobei", "东北话"),
    "6": ("x2_xiaokun", "河南话"),
    "7": ("x3_xiaodu", "成都话"),
}

# 全局发音人（默认普通话）
_current_voice = "x4_yezi"
_current_voice_name = "普通话"

# 全局闹钟调度器
_alarm_scheduler = None


def speak(text: str):
    """用当前方言播报文字"""
    try:
        speech_synthesis(_current_voice, text)
    except Exception as e:
        logger.error(f"语音播报失败: {str(e)}")
        print(f"[语音播报失败] {text}")


def choose_voice():
    """选择发音人（方言）"""
    global _current_voice, _current_voice_name
    print("\n===== 方言选择 =====")
    for key, (_, name) in VOICES.items():
        print(f"{key}. {name}")
    print("0. 返回主菜单")
    choice = input("请选择方言：").strip()
    if choice in VOICES:
        _current_voice, _current_voice_name = VOICES[choice]
        print(f"已切换为: {_current_voice_name}")
        speak(f"已切换为{_current_voice_name}模式")


def ocr_and_chat():
    """📷 拍照识别 → AI对话"""
    print("\n📷 正在拍照识别...")
    try:
        lines = universal_ocr()
        image_text = "\n".join(lines)
        if not image_text:
            print("未识别到文字，请重试。")
            return
        print(f"📝 识别到文字:\n{image_text}\n")
        # 传给AI
        reply, _ = chat_with_context(image_text=image_text)
        print(f"\n🤖 AI回答:\n{reply}\n")
        speak(reply)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        print("请确认 picture.jpg 文件存在。")
    except Exception as e:
        print(f"❌ OCR出错: {e}")


def voice_chat():
    """🎤 语音咨询"""
    print("\n🎤 语音咨询模式")
    text = microphone_stream()
    if not text:
        print("未识别到有效语音。")
        return
    print(f"📝 识别结果: {text}\n")
    reply, _ = chat_with_context(text=text)
    print(f"🤖 AI回答:\n{reply}\n")
    speak(reply)


def hybrid_chat():
    """📷+🎤 混合咨询"""
    print("\n📷+🎤 混合咨询模式")

    # 第一步：拍照
    image_text = ""
    do_ocr = input("是否先拍照识别药方？(y/n, 默认y): ").strip().lower()
    if do_ocr != 'n':
        try:
            lines = universal_ocr()
            image_text = "\n".join(lines)
            if image_text:
                print(f"📝 识别到文字:\n{image_text}\n")
            else:
                print("未识别到文字，跳过OCR部分。")
        except Exception as e:
            print(f"OCR跳过: {e}")

    # 第二步：语音
    print("🎤 现在请用语音描述你的症状或问题...")
    text = microphone_stream()
    if not text and not image_text:
        print("未获取到有效输入。")
        return
    if text:
        print(f"📝 语音识别: {text}\n")

    # 第三步：AI综合回答
    reply, _ = chat_with_context(text=text, image_text=image_text)
    print(f"🤖 AI回答:\n{reply}\n")
    speak(reply)


def setup_reminder():
    """⏰ 设置定时提醒：拍照药方→AI分析→自动闹钟"""
    global _alarm_scheduler

    print("\n⏰ 定时提醒设置模式")
    print("第一步：请拍摄药品说明书或药方...")

    try:
        lines = universal_ocr()
        image_text = "\n".join(lines)
        if not image_text:
            print("未识别到文字。")
            return
        print(f"📝 识别到文字:\n{image_text}\n")
    except Exception as e:
        print(f"❌ OCR出错: {e}")
        return

    print("🤖 AI正在分析用药信息，请稍候...")
    try:
        schedule_text = analyze_medication_schedule(image_text)
        print(f"\n📋 AI分析结果:\n{schedule_text}\n")
        speak(schedule_text)
    except Exception as e:
        print(f"❌ AI分析出错: {e}")
        return

    # 解析闹钟
    alarms = parse_schedule(schedule_text)
    if alarms:
        print(f"⏰ 已解析到 {len(alarms)} 个服药时间:")
        for a in alarms:
            print(f"   {a['time']} → {a['medication']}")

        confirm = input("\n是否设置闹钟？(y/n, 默认y): ").strip().lower()
        if confirm != 'n':
            if _alarm_scheduler is None:
                _alarm_scheduler = AlarmScheduler(speak)
            _alarm_scheduler.set_alarms(alarms)
            print(f"✅ 已设置 {len(alarms)} 个闹钟，到点将自动语音提醒！")
    else:
        print("⚠️ 未能从AI回复中解析出具体时间信息。")
        print("已语音播报AI建议，请手动设置服药时间。")


def show_alarm_status():
    """显示当前闹钟状态"""
    if _alarm_scheduler and _alarm_scheduler.active_count > 0:
        print(f"⏰ 当前有 {_alarm_scheduler.active_count} 个闹钟待触发")
    else:
        print("⏰ 当前无活跃闹钟")


def main():
    """主菜单循环"""
    global _current_voice, _current_voice_name

    print("=" * 40)
    print("      💊 智能提醒吃药系统")
    print("=" * 40)

    while True:
        print(f"\n当前方言: {_current_voice_name}")
        if _alarm_scheduler and _alarm_scheduler.active_count > 0:
            print(f"⏰ 闹钟: {_alarm_scheduler.active_count} 个待触发")
        print("-" * 30)
        print("1. 📷 拍照识别（OCR → AI）")
        print("2. 🎤 语音咨询（语音 → AI）")
        print("3. 📷+🎤 混合模式（拍照+语音 → AI）")
        print("4. ⏰ 设置定时提醒（拍药方 → AI分析 → 闹钟）")
        print("5. 🗣️ 方言切换")
        print("0. 🚪 退出")
        print("-" * 30)

        choice = input("请选择功能：").strip()

        if choice == "1":
            ocr_and_chat()
        elif choice == "2":
            voice_chat()
        elif choice == "3":
            hybrid_chat()
        elif choice == "4":
            setup_reminder()
        elif choice == "5":
            choose_voice()
        elif choice == "0":
            speak("感谢您的使用！祝您康健相伴，福寿无忧！")
            print("感谢使用，再见！")
            break
        else:
            print("无效输入，请重新选择。")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 验证启动**

```bash
cd pill_reminder && python -c "import main; print('main.py OK - 结构完整')"
```

期望输出: `main.py OK - 结构完整`

---

### Task 8: 验证完整运行

**Files:**
- 不涉及变更

- [ ] **Step: 目录结构确认**

```bash
cd pill_reminder && find . -type f | sort
```

期望输出:
```
./.env
./ai/__init__.py
./ai/chat.py
./main.py
./ocr/__init__.py
./ocr/client.py
./reminder/__init__.py
./reminder/alarm.py
./requirements.txt
./speech/__init__.py
./speech/iat.py
./speech/tts.py
```

- [ ] **Step: 测试 Python 语法正确性**

```bash
cd pill_reminder && python -m py_compile main.py && python -m py_compile ocr/client.py && python -m py_compile speech/iat.py && python -m py_compile speech/tts.py && python -m py_compile ai/chat.py && python -m py_compile reminder/alarm.py && echo "✅ 所有文件语法正确"
```

期望输出: `✅ 所有文件语法正确`

---

## 自审检查

**1. 规格覆盖:** 
- ✅ OCR识别 → Task 4 `ocr/client.py`
- ✅ 语音识别 → Task 3 `speech/iat.py`
- ✅ 方言TTS → Task 2 `speech/tts.py`
- ✅ AI对话+禁忌提醒 → Task 5 `ai/chat.py`（system prompt 内置禁忌提醒指令）
- ✅ 定时闹钟（AI分析药方→闹钟）→ Task 6 `reminder/alarm.py` + Task 7 `main.py` 选项4
- ✅ 主菜单 → Task 7 `main.py`

**2. 占位符检查:** ✅ 无占位符/TODO/待定项

**3. 类型一致性:** 
- `speech_synthesis(choose, text, filename)` → Task 2 定义，Task 7 调用 ✓
- `microphone_stream() -> str` → Task 3 定义，Task 7 调用 ✓
- `universal_ocr(image_path) -> list[str]` → Task 4 定义，Task 7 调用 ✓
- `chat_with_context(text, image_text) -> tuple` → Task 5 定义，Task 7 调用 ✓
- `AlarmScheduler(tts_callback)` / `parse_schedule()` → Task 6 定义，Task 7 调用 ✓
