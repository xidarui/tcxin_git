"""语音合成模块 — 文字转方言语音"""
import os
import base64
import wave
import logging
import threading
from dotenv import load_dotenv
from xfyunsdkspeech.tts_client import TtsClient

load_dotenv()

RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2

# 全局锁：防止多个闹钟同时播放语音导致声卡冲突
_tts_lock = threading.Lock()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger('websocket').setLevel(logging.CRITICAL)
logging.getLogger('XfyunPythonSDK').setLevel(logging.CRITICAL)


def synthesize_to_bytes(choose: str, text: str, speed: float = 0.9, volume: float = 0.9) -> bytes:
    """将文字合成为 PCM 音频字节数据（不保存、不播放）

    Args:
        choose: 发音人
        text: 要合成的文字
        speed: 语速 (0.5-1.8, 映射到讯飞 30-80)
        volume: 音量 (0.2-1.0, 映射到讯飞 20-100)
    """
    app_id = os.getenv("APP_ID")
    api_key = os.getenv("API_KEY")
    api_secret = os.getenv("API_SECRET")

    # 检查凭证是否有效
    if not app_id or not api_key or not api_secret:
        raise ValueError("TTS缺少API凭证，请检查 .env 文件中的 APP_ID、API_KEY、API_SECRET")

    # 映射前端值到讯飞API参数
    speed_val = max(0, min(100, int((speed - 0.5) * 66.7 + 20)))
    volume_val = max(0, min(100, int(volume * 100)))

    client = TtsClient(
        app_id=app_id,
        api_key=api_key,
        api_secret=api_secret,
        vcn=choose,
        aue="raw",
        speed=speed_val,
        volume=volume_val,
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


def speech_synthesis(choose: str, text: str, filename: str = "output.wav", play: bool = True, speed: float = 0.9, volume: float = 0.9) -> str:
    """语音合成主函数：生成PCM → 保存wav → 声卡播放（可选）

    Args:
        choose: 发音人参数（方言选择）
                "x4_yezi"=普通话  "x_xiaomei"=粤语  "x3_linlin"=闽南语
                "x2_xiaobao"=内蒙古  "x3_yezi_sc"=四川话  "x4_xiaobei"=东北话
                "x2_xiaokun"=河南话  "x3_xiaodu"=成都话
        text: 要合成语音的文字
        filename: 输出wav文件名
        play: 是否声卡播放（Web API 调用时设为 False）
        speed: 语速 (0.5-1.8)
        volume: 音量 (0.2-1.0)
    Returns:
        str: 音频文件绝对路径
    """
    with _tts_lock:
        if not text or not text.strip():
            raise ValueError("没有要合成的文字内容")
        pcm_bytes = synthesize_to_bytes(choose, text, speed, volume)
        file_path = os.path.abspath(filename)
        with wave.open(file_path, mode="wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(RATE)
            wf.writeframes(pcm_bytes)
        logger.info(f"音频已保存: {file_path}")
        if play:
            play_pcm_direct(pcm_bytes)
        return file_path
