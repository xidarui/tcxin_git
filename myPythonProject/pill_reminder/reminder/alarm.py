"""定时提醒模块 — 闹钟引擎"""
import logging
import re
import threading
from datetime import datetime, timedelta
from typing import Callable

logger = logging.getLogger(__name__)


def parse_time_from_text(time_str: str) -> str:
    """将自然语言时间转为 HH:MM 格式"""
    time_str = time_str.strip().replace('：', ':')
    # 尝试直接匹配 HH:MM
    try:
        datetime.strptime(time_str, '%H:%M')
        return time_str
    except ValueError:
        pass

    # 中文时间映射
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
    match = re.findall(r'(\d{1,2})', result)
    if len(match) >= 1:
        hour = int(match[0])
        minute = int(match[1]) if len(match) >= 2 else 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"

    return time_str


def parse_schedule(ai_reply: str) -> list[dict]:
    """从AI回复中解析用药时间表

    优先匹配 HH:MM 格式，其次尝试中文自然语言时间解析。

    Args:
        ai_reply: AI分析药方后的回复文字

    Returns:
        list[dict]: [{"time": "08:00", "medication": "头孢拉定 1粒", "note": ""}, ...]
    """
    schedule = []
    time_pattern = re.compile(r'(\d{1,2}:\d{2})')
    lines = ai_reply.split('\n')

    current_time = None
    current_med = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 先尝试匹配 HH:MM 格式
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

    if current_time and current_med:
        schedule.append({
            "time": current_time,
            "medication": current_med,
            "note": ""
        })

    # 如果 HH:MM 没解析到任何结果，尝试自然语言解析
    if not schedule:
        natural_time = parse_time_from_text(ai_reply)
        if natural_time and re.match(r'\d{2}:\d{2}', natural_time):
            schedule.append({
                "time": natural_time,
                "medication": ai_reply.replace('\n', ' ').strip()[:80],
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
                if target <= now:
                    target += timedelta(days=1)

                delay = (target - now).total_seconds()
                medication = alarm.get("medication", "请按时服药")
                note = alarm.get("note", "")

                text = f"⏰ 吃药时间到！请服用 {medication}"
                if note:
                    text += f"，{note}"

                # 使用带标识的定时器，方便追踪已触发的闹钟
                alarm_id = {"fired": False, "timer": None}
                def on_alarm_with_cleanup(tid=alarm_id, t=text):
                    tid["fired"] = True
                    logger.info(f"⏰ 闹钟触发: {t}")
                    if self.tts_callback:
                        self.tts_callback(t)

                timer = threading.Timer(delay, on_alarm_with_cleanup)
                timer.daemon = True
                alarm_id["timer"] = timer
                self._timers.append(alarm_id)
                timer.start()

                logger.info(f"已设置闹钟: {alarm['time']} → {medication}")
            except (ValueError, KeyError) as e:
                logger.warning(f"闹钟格式无效: {alarm}, 错误: {e}")

    def clear_alarms(self):
        """清除所有闹钟"""
        for item in self._timers:
            if item["timer"] and not item["fired"]:
                item["timer"].cancel()
        self._timers.clear()

    @property
    def active_count(self) -> int:
        return sum(1 for item in self._timers if not item["fired"])
