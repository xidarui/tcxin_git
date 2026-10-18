"""仓储层 — 把「业务语义」翻译成数据库操作

上层（zhiyao.cli / zhiyao.web.app / zhiyao.ai.chat）只调用这里的函数，
不直接碰 SQL 或 Session，换数据库时只改这一层。
"""
from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, time as dtime, timedelta
from typing import Any

from sqlalchemy import delete, select

from .base import Base, get_engine, session_scope
from .models import AlarmPlan, ChatMessage, DoseLog, Medication

logger = logging.getLogger(__name__)

# 表结构只需要建一次，用锁防止多线程同时 create_all
_init_lock = threading.Lock()
_tables_ready = False


def init_tables(force: bool = False) -> None:
    """建表（已存在则跳过）"""
    global _tables_ready
    with _init_lock:
        if _tables_ready and not force:
            return
        Base.metadata.create_all(get_engine())
        _tables_ready = True
        logger.info("数据表已就绪")


# ---------------------------------------------------------------- 工具函数
_DOSAGE_RE = re.compile(
    r"(\d+(?:\.\d+)?\s*(?:粒|片|袋|支|颗|毫升|ml|mg|g|丸|滴|喷|次|包))",
    re.IGNORECASE,
)


def split_medication_text(text: str) -> tuple[str, str]:
    """把 "头孢拉定 1粒" 拆成 ("头孢拉定", "1粒")

    拆不出来就把整段当药名，剂量留空。
    """
    text = (text or "").strip()
    if not text:
        return "未知药品", ""

    m = _DOSAGE_RE.search(text)
    if m:
        dosage = m.group(1).strip()
        name = (text[: m.start()] + text[m.end() :]).strip(" ,，。;；")
        if name:
            return name[:100], dosage[:100]

    head, _, tail = text.partition(" ")
    if tail:
        return head.strip()[:100], tail.strip()[:100]
    return text[:100], ""


def _fmt_time(value: Any) -> str:
    """TIME 列 → "HH:MM"（PyMySQL 有时返回 timedelta，这里统一处理）"""
    if isinstance(value, dtime):
        return f"{value.hour:02d}:{value.minute:02d}"
    if hasattr(value, "seconds"):  # datetime.timedelta
        total = int(value.total_seconds()) % 86400
        return f"{total // 3600:02d}:{(total % 3600) // 60:02d}"
    return str(value)[:5]


def _parse_time(value: Any) -> dtime | None:
    if isinstance(value, dtime):
        return value
    try:
        hh, mm = str(value).split(":")[:2]
        return dtime(int(hh), int(mm))
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------- 药品
def get_or_create_medication(
    name: str, dosage: str = "", note: str = ""
) -> Medication:
    """按名称取药，没有就建一条"""
    with session_scope() as s:
        med = s.scalar(select(Medication).where(Medication.name == name))
        if med is None:
            med = Medication(name=name, dosage=dosage, note=note)
            s.add(med)
            s.flush()
        elif dosage and med.dosage != dosage:
            med.dosage = dosage
        return med


def list_medications() -> list[dict]:
    with session_scope() as s:
        rows = s.scalars(select(Medication).order_by(Medication.id)).all()
        return [
            {
                "id": m.id,
                "name": m.name,
                "dosage": m.dosage,
                "note": m.note,
                "created_at": m.created_at,
            }
            for m in rows
        ]


# ---------------------------------------------------------------- 提醒计划
def save_plans(alarms: list[dict], replace_missing: bool = True) -> list[int]:
    """保存一组提醒计划（按 药品名+时间 做去重更新）

    Args:
        alarms: [{"time": "08:00", "medication": "头孢拉定 1粒", "note": ""}, ...]
        replace_missing: True 表示本次没出现的旧计划一律删除

    Returns:
        本次写入的计划 id 列表
    """
    init_tables()
    saved_ids: list[int] = []

    with session_scope() as s:
        existing = {
            (_fmt_time(p.remind_time), p.medication.name): p
            for p in s.scalars(select(AlarmPlan)).all()
        }
        seen: set[tuple[str, str]] = set()

        for alarm in alarms or []:
            hhmm = _fmt_time(alarm.get("time", ""))
            parsed = _parse_time(hhmm)
            if parsed is None:
                logger.warning("跳过无效提醒时间: %r", alarm.get("time"))
                continue

            name, dosage = split_medication_text(alarm.get("medication", ""))
            note = (alarm.get("note") or "").strip()

            med = s.scalar(select(Medication).where(Medication.name == name))
            if med is None:
                med = Medication(name=name, dosage=dosage)
                s.add(med)
                s.flush()
            elif dosage and med.dosage != dosage:
                med.dosage = dosage

            key = (hhmm, name)
            seen.add(key)
            plan = existing.get(key)
            if plan is None:
                plan = AlarmPlan(
                    medication_id=med.id,
                    remind_time=parsed,
                    note=note,
                    enabled=True,
                    repeat_daily=True,
                )
                s.add(plan)
            else:
                plan.note = note
                plan.enabled = True

            s.flush()
            saved_ids.append(plan.id)

        if replace_missing:
            for key, plan in existing.items():
                if key not in seen:
                    s.delete(plan)

    logger.info("已保存 %d 条提醒计划", len(saved_ids))
    return saved_ids


def list_plans(active_only: bool = False) -> list[dict]:
    """列出提醒计划，返回可直接喂给 AlarmScheduler 的结构"""
    init_tables()
    with session_scope() as s:
        stmt = select(AlarmPlan).order_by(AlarmPlan.remind_time)
        if active_only:
            stmt = stmt.where(AlarmPlan.enabled.is_(True))
        plans = s.scalars(stmt).all()
        out = []
        for p in plans:
            med = p.medication
            label = f"{med.name} {med.dosage}".strip() if med else "未知药品"
            out.append(
                {
                    "id": p.id,
                    "time": _fmt_time(p.remind_time),
                    "medication": label,
                    "note": p.note or "",
                    "enabled": bool(p.enabled),
                    "repeat_daily": bool(p.repeat_daily),
                }
            )
        return out


def load_plan_dicts(active_only: bool = True) -> list[dict]:
    """给 AlarmScheduler 用的计划字典

    必须带 plan_id：闹钟触发时要把记录挂到具体计划上，
    否则两条同药不同时间的计划在「今天吃没吃」上会串到一起。
    """
    return [
        {
            "plan_id": p["id"],
            "time": p["time"],
            "medication": p["medication"],
            "note": p["note"],
        }
        for p in list_plans(active_only=active_only)
    ]


def set_plan_enabled(plan_id: int, enabled: bool) -> bool:
    init_tables()
    with session_scope() as s:
        plan = s.get(AlarmPlan, plan_id)
        if plan is None:
            return False
        plan.enabled = bool(enabled)
        return True


def delete_plan(plan_id: int) -> bool:
    init_tables()
    with session_scope() as s:
        plan = s.get(AlarmPlan, plan_id)
        if plan is None:
            return False
        s.delete(plan)
        return True


# ---------------------------------------------------------------- 服药记录
def record_dose(
    medication_name: str,
    scheduled_at: datetime | None = None,
    plan_id: int | None = None,
    status: str = "pending",
) -> int:
    """写入一条服药记录（闹钟触发时调用）"""
    init_tables()
    with session_scope() as s:
        log = DoseLog(
            plan_id=plan_id,
            medication_name=medication_name[:100],
            scheduled_at=scheduled_at or datetime.now(),
            status=status,
        )
        s.add(log)
        s.flush()
        return log.id


def mark_taken(log_id: int) -> bool:
    """标记某条记录为已服药"""
    init_tables()
    with session_scope() as s:
        log = s.get(DoseLog, log_id)
        if log is None:
            return False
        log.status = "taken"
        log.taken_at = datetime.now()
        return True


def list_dose_logs(limit: int = 50) -> list[dict]:
    init_tables()
    with session_scope() as s:
        rows = s.scalars(
            select(DoseLog).order_by(DoseLog.scheduled_at.desc()).limit(limit)
        ).all()
        return [
            {
                "id": r.id,
                "plan_id": r.plan_id,
                "medication_name": r.medication_name,
                "scheduled_at": r.scheduled_at,
                "taken_at": r.taken_at,
                "status": r.status,
            }
            for r in rows
        ]


# ---------------------------------------------------------------- 对话历史
def append_message(role: str, content: str, source: str = "text") -> int:
    """存一条对话消息"""
    init_tables()
    with session_scope() as s:
        msg = ChatMessage(role=role, content=content, source=source)
        s.add(msg)
        s.flush()
        return msg.id


def get_messages(limit: int = 50) -> list[dict]:
    """取最近 N 条消息（按时间正序返回，方便直接拼回对话）"""
    init_tables()
    with session_scope() as s:
        rows = s.scalars(
            select(ChatMessage).order_by(ChatMessage.id.desc()).limit(limit)
        ).all()
        rows.reverse()
        return [
            {
                "id": r.id,
                "role": r.role,
                "content": r.content,
                "source": r.source,
                "created_at": r.created_at,
            }
            for r in rows
        ]


def clear_messages() -> int:
    """清空对话历史，返回删除条数"""
    init_tables()
    with session_scope() as s:
        result = s.execute(delete(ChatMessage))
        return result.rowcount or 0


# ---------------------------------------------------------------- 网页端同步
def get_today_status(target: datetime | None = None) -> list[dict]:
    """今天的提醒计划 + 每条是否已服药

    这是给网页端一步到位的接口：前端不用自己拼「计划 + 记录」，
    直接拿到「8:00 阿莫西林 1粒 已吃」这样的列表。
    """
    init_tables()
    now = target or datetime.now()
    day_start = datetime.combine(now.date(), dtime.min)
    day_end = day_start + timedelta(days=1)

    with session_scope() as s:
        plans = s.scalars(
            select(AlarmPlan)
            .where(AlarmPlan.enabled.is_(True))
            .order_by(AlarmPlan.remind_time)
        ).all()

        logs = s.scalars(
            select(DoseLog).where(
                DoseLog.scheduled_at >= day_start,
                DoseLog.scheduled_at < day_end,
            )
        ).all()

        by_plan = {log.plan_id: log for log in logs if log.plan_id}

        # 按药名兜底只对「今天只出现一次」的药名生效。
        # 否则 08:00 和 21:00 都吃阿莫西林时，一条打卡会把两条都标成已吃。
        name_plans: dict[str, int] = {}
        for plan in plans:
            med = plan.medication
            label = f"{med.name} {med.dosage}".strip() if med else "未知药品"
            name_plans[label] = name_plans.get(label, 0) + 1

        by_name: dict[str, DoseLog] = {}
        for log in logs:
            if name_plans.get(log.medication_name) == 1:
                by_name.setdefault(log.medication_name, log)

        result: list[dict] = []
        for plan in plans:
            med = plan.medication
            label = f"{med.name} {med.dosage}".strip() if med else "未知药品"
            log = by_plan.get(plan.id) or by_name.get(label)
            result.append(
                {
                    "id": plan.id,
                    "time": _fmt_time(plan.remind_time),
                    "medication": label,
                    "note": plan.note or "",
                    "taken": bool(log and log.status == "taken"),
                    "status": log.status if log else "pending",
                    "log_id": log.id if log else None,
                }
            )
        return result


def checkin(plan_id: int) -> dict | None:
    """网页端「确认已服药」：把今天这条计划的记录标成 taken（没有就补一条）"""
    init_tables()
    now = datetime.now()
    day_start = datetime.combine(now.date(), dtime.min)
    day_end = day_start + timedelta(days=1)

    with session_scope() as s:
        plan = s.get(AlarmPlan, plan_id)
        if plan is None:
            return None

        med = plan.medication
        label = f"{med.name} {med.dosage}".strip() if med else "未知药品"

        log = s.scalar(
            select(DoseLog)
            .where(
                DoseLog.plan_id == plan_id,
                DoseLog.scheduled_at >= day_start,
                DoseLog.scheduled_at < day_end,
            )
            .order_by(DoseLog.id.desc())
        )

        if log is None:
            log = DoseLog(
                plan_id=plan_id,
                medication_name=label[:100],
                scheduled_at=now,
                taken_at=now,
                status="taken",
            )
            s.add(log)
        else:
            log.status = "taken"
            log.taken_at = now

        s.flush()
        return {
            "id": log.id,
            "plan_id": plan_id,
            "medication_name": log.medication_name,
            "status": log.status,
            "taken_at": log.taken_at,
        }


# ---------------------------------------------------------------- 统计
def stats() -> dict:
    """给首页/健康检查用的汇总数字"""
    init_tables()
    from sqlalchemy import func

    with session_scope() as s:
        return {
            "medications": s.scalar(select(func.count()).select_from(Medication)) or 0,
            "plans": s.scalar(select(func.count()).select_from(AlarmPlan)) or 0,
            "active_plans": s.scalar(
                select(func.count())
                .select_from(AlarmPlan)
                .where(AlarmPlan.enabled.is_(True))
            )
            or 0,
            "dose_logs": s.scalar(select(func.count()).select_from(DoseLog)) or 0,
            "messages": s.scalar(select(func.count()).select_from(ChatMessage)) or 0,
        }
