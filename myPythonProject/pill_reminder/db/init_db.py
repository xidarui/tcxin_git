"""数据库初始化脚本

用法::

    python -m pill_reminder.db.init_db          # 建表
    python -m pill_reminder.db.init_db --demo   # 建表 + 塞几条演示数据
    python -m pill_reminder.db.init_db --check  # 只测连接和表状态
    python -m pill_reminder.db.init_db --reset  # 删表重建（会影响已有数据）

注意：输出刻意只用 ASCII 标记（OK / FAIL / WARN），
因为 Windows 控制台默认是 GBK，打 emoji 会直接抛 UnicodeEncodeError。
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta

from . import repo
from .base import DB_HOST, DB_NAME, DB_PORT, DB_USER, ping


def show_status() -> None:
    print(f"连接目标 : {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    if not ping():
        print("[FAIL] 数据库连不上，请检查 MySQL 服务是否启动、.env 里的账号密码是否正确")
        sys.exit(1)
    print("[ OK ] 数据库连接正常")
    for key, value in repo.stats().items():
        print(f"   {key:<14} {value}")


def seed_demo() -> None:
    """塞几条演示数据，方便打开网页就有内容"""
    repo.init_tables()
    repo.save_plans(
        [
            {"time": "08:00", "medication": "阿莫西林 1粒", "note": "饭后服用"},
            {"time": "12:30", "medication": "维生素C 1片", "note": "随餐"},
            {"time": "21:00", "medication": "阿莫西林 1粒", "note": "睡前"},
        ]
    )
    for name in ("阿莫西林 1粒", "维生素C 1片"):
        repo.record_dose(name, datetime.now() - timedelta(hours=2), status="missed")

    taken_id = repo.record_dose(
        "阿莫西林 1粒", datetime.now() - timedelta(minutes=30), status="pending"
    )
    repo.mark_taken(taken_id)
    print("[ OK ] 演示数据已写入")


def main() -> None:
    parser = argparse.ArgumentParser(description="初始化服药提醒系统的数据库")
    parser.add_argument("--demo", action="store_true", help="顺便写入演示数据")
    parser.add_argument("--check", action="store_true", help="只检查，不建表")
    parser.add_argument("--reset", action="store_true", help="清空所有表后重建")
    args = parser.parse_args()

    if args.reset:
        from .base import Base, get_engine

        Base.metadata.drop_all(get_engine())
        print("[WARN] 已删除所有表")

    if not args.check:
        repo.init_tables()
        print("[ OK ] 数据表已创建 / 已存在")

    if args.demo:
        seed_demo()

    show_status()


if __name__ == "__main__":
    main()
