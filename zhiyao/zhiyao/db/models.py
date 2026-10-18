"""ORM 模型 — 4 张表

设计思路（对应业务）：
    medication  药品       ：一种药一条记录，名称唯一
    alarm_plan  提醒计划   ：某药在某个时间点提醒，多对一指向 medication
    dose_log    服药记录   ：每次闹钟触发产生一条，记录"该吃/已吃/漏服"
    chat_message 对话历史  ：把原来存在内存里的 _global_history 落盘

关系： medication 1—N alarm_plan 1—N dose_log
"""
from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Medication(Base):
    """药品字典表"""

    __tablename__ = "medication"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, comment="药品名称"
    )
    dosage: Mapped[str] = mapped_column(
        String(100), default="", server_default="", comment="单次剂量，如 1粒/5ml"
    )
    note: Mapped[str] = mapped_column(
        Text, default="", comment="备注、注意事项"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    plans: Mapped[list["AlarmPlan"]] = relationship(
        back_populates="medication",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<Medication id={self.id} name={self.name!r}>"


class AlarmPlan(Base):
    """提醒计划表 — 每个 (药品, 时间) 一条"""

    __tablename__ = "alarm_plan"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    medication_id: Mapped[int] = mapped_column(
        ForeignKey("medication.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联药品",
    )
    remind_time: Mapped[time] = mapped_column(
        Time, nullable=False, comment="提醒时刻 HH:MM"
    )
    repeat_daily: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", comment="是否每天重复"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", comment="是否启用"
    )
    note: Mapped[str] = mapped_column(
        Text, default="", comment="如 饭后服用"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    medication: Mapped["Medication"] = relationship(back_populates="plans")
    # 注意：这里不配 delete-orphan。计划被删除时只把 dose_log.plan_id 置空
    # （由数据库外键 ON DELETE SET NULL 完成），历史服药记录要保留。
    logs: Mapped[list["DoseLog"]] = relationship(
        back_populates="plan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_alarm_plan_enabled", "enabled"),
        Index("ix_alarm_plan_time", "remind_time"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AlarmPlan id={self.id} time={self.remind_time}>"


class DoseLog(Base):
    """服药记录表 — 闹钟触发时写入"""

    __tablename__ = "dose_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("alarm_plan.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联计划，计划被删后置空以保留历史",
    )
    medication_name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="药品名快照，避免联表"
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="应服药时间"
    )
    taken_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="实际服药时间"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        server_default="pending",
        comment="pending 待服 / taken 已服 / missed 漏服 / skipped 跳过",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    plan: Mapped["AlarmPlan | None"] = relationship(back_populates="logs")

    __table_args__ = (
        Index("ix_dose_log_status", "status"),
        Index("ix_dose_log_scheduled", "scheduled_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DoseLog id={self.id} {self.medication_name} {self.status}>"


class ChatMessage(Base):
    """对话历史表 — 替代 chat.py 里的内存全局变量"""

    __tablename__ = "chat_message"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="system / user / assistant"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(
        String(20),
        default="text",
        server_default="text",
        comment="输入来源: text 文字 / ocr 拍照 / voice 语音 / mixed 混合",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_chat_message_created", "created_at"),)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ChatMessage {self.role}: {self.content[:20]!r}>"
