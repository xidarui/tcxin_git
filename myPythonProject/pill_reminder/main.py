"""智能提醒吃药系统 — 主入口"""
import os
import sys
import logging
import warnings

# 屏蔽 langchain 旧版 API 警告（spark-ai-python 依赖的旧版 langchain 触发）
warnings.filterwarnings("ignore", category=UserWarning, module="langchain")

# 确保能找到同目录下的包
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
    except ValueError as e:
        logger.error(f"语音播报配置错误: {str(e)}")
        print(f"[语音播报配置错误] {e}")
        print(f"💡 提示：请确认 .env 文件中的 APP_ID、API_KEY、API_SECRET 是否正确")
    except Exception as e:
        logger.error(f"语音播报失败: {str(e)}")
        print(f"[语音播报失败] {e}")
        print(f"💡 提示：TTS服务可能未开通，请联系讯飞平台确认 APP_ID 已开通语音合成服务")
        print(f"📝 文字内容: {text}")


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
        reply, _ = chat_with_context(image_text=image_text)
        print(f"\n🤖 AI回答:\n{reply}\n")
        speak(reply)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        print("请确认 picture.jpg 文件存在。")
    except PermissionError as e:
        print(f"❌ {e}")
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
        except PermissionError as e:
            print(f"❌ OCR授权失败: {e}")
            return
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
    except PermissionError as e:
        print(f"❌ OCR授权失败: {e}")
        return
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
        print("6. 🧹 重置对话")
        print("0. 🚪 退出")
        print("-" * 30)

        try:
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
            elif choice == "6":
                clear_history()
                print("🧹 对话历史已重置")
            elif choice == "0":
                speak("感谢您的使用！祝您康健相伴，福寿无忧！")
                print("感谢使用，再见！")
                break
            else:
                print("无效输入，请重新选择。")
        except Exception as e:
            logger.error(f"程序异常: {str(e)}")
            print(f"❌ 发生未预期错误: {e}，请重试。")


if __name__ == "__main__":
    main()
