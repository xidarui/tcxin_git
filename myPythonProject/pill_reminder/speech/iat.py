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

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

        input()
        stop_event.set()
        mic_stream.stop_stream()
        mic_stream.close()
        # 等待线程自然结束，最多3秒
        thread.join(timeout=3)
        # 若线程未结束，daemon=True 保证进程退出时不会挂起
        p.terminate()

        if thread_exception and not final_text:
            logger.warning(f"录音异常: {thread_exception}")

        return final_text

    except Exception as e:
        logger.error(f"语音识别失败: {str(e)}")
        return ""
