"""数据库 + API 冒烟测试

不依赖 pytest，在仓库根目录直接跑::

    python tests/test_db_smoke.py

加 --http 会额外测试 HTTP 接口（需要先启动网页版）::

    python -m zhiyao.web.app
    python tests/test_db_smoke.py --http --base http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

# 允许从任意工作目录直接运行：把仓库根加进 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zhiyao.db import ping, repo  # noqa: E402

PASS, FAIL = "[PASS]", "[FAIL]"
_failures = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global _failures
    print(f"{PASS if ok else FAIL} {name}" + (f"  {detail}" if detail else ""))
    if not ok:
        _failures += 1


def test_db() -> None:
    print("--- 数据库层 ---")
    repo.init_tables()
    check("建表", ping())

    # 1. 保存计划
    ids = repo.save_plans(
        [
            {"time": "07:30", "medication": "测试药A 2粒", "note": "空腹"},
            {"time": "19:45", "medication": "测试药B 1片", "note": ""},
        ]
    )
    check("save_plans 写入 2 条", len(ids) == 2, f"ids={ids}")

    # 2. 读回
    plans = repo.list_plans()
    times = sorted(p["time"] for p in plans)
    check("list_plans 读回时间", times == ["07:30", "19:45"], f"{times}")

    # 3. 中文没有乱码
    names = {p["medication"] for p in plans}
    check(
        "中文与剂量解析正确",
        "测试药A 2粒" in names,
        f"{sorted(names)}",
    )

    # 4. 幂等：同样内容再存一次，id 不变
    again = repo.save_plans(
        [
            {"time": "07:30", "medication": "测试药A 2粒", "note": "空腹"},
            {"time": "19:45", "medication": "测试药B 1片", "note": ""},
        ]
    )
    check("重复保存不产生新记录", sorted(again) == sorted(ids), f"{again} vs {ids}")

    # 5. 启停
    check("停用计划", repo.set_plan_enabled(ids[0], False))
    active = [p["id"] for p in repo.list_plans(active_only=True)]
    check("停用后不在启用列表", ids[0] not in active, f"active={active}")
    repo.set_plan_enabled(ids[0], True)

    # 6. 服药记录
    log_id = repo.record_dose("测试药A 2粒", status="pending")
    check("写入服药记录", log_id > 0, f"log_id={log_id}")
    check("标记已服", repo.mark_taken(log_id))
    latest = repo.list_dose_logs(1)[0]
    check(
        "状态变为 taken 且有时间",
        latest["status"] == "taken" and latest["taken_at"] is not None,
        f"{latest['status']} / {latest['taken_at']}",
    )

    # 7. 对话历史
    repo.clear_messages()
    repo.append_message("user", "我头疼吃什么药", source="text")
    repo.append_message("assistant", "建议先测量血压……", source="text")
    msgs = repo.get_messages(10)
    check("对话历史读写", len(msgs) == 2, f"{len(msgs)} 条")
    check("历史按时间正序", msgs[0]["role"] == "user", msgs[0]["role"])
    removed = repo.clear_messages()
    check("清空对话", removed == 2 and len(repo.get_messages(5)) == 0, f"删除 {removed} 条")

    # 8. 删除计划
    check("删除计划", repo.delete_plan(ids[1]))
    check(
        "删除后只剩 1 条",
        len(repo.list_plans()) == 1,
        f"{len(repo.list_plans())} 条",
    )
    check("统计接口", set(repo.stats()) >= {"medications", "plans", "dose_logs"})


def _req(method: str, url: str, body: dict | None = None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json; charset=utf-8")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_http(base: str) -> None:
    print("\n--- HTTP 接口 ---")
    try:
        health = _req("GET", f"{base}/health")
    except (urllib.error.URLError, ConnectionError) as exc:
        check("服务可达", False, f"{exc}（先启动 app.py 再跑 --http）")
        return

    check("GET /health", health.get("database") == "ok", json.dumps(health, ensure_ascii=False))

    plans = _req("POST", f"{base}/api/plans", [
        {"time": "08:15", "medication": "接口测试药 1粒", "note": "饭后"},
    ])
    check("POST /api/plans", len(plans) == 1, f"{len(plans)} 条")
    check(
        "接口返回中文正常",
        plans[0]["medication"] == "接口测试药 1粒",
        plans[0]["medication"],
    )

    pid = plans[0]["id"]
    off = _req("PATCH", f"{base}/api/plans/{pid}", {"enabled": False})
    check("PATCH 停用", off["enabled"] is False)
    on = _req("PATCH", f"{base}/api/plans/{pid}", {"enabled": True})
    check("PATCH 启用", on["enabled"] is True)

    stats = _req("GET", f"{base}/api/stats")
    check("GET /api/stats", stats["plans"] >= 1, json.dumps(stats, ensure_ascii=False))

    logs = _req("GET", f"{base}/api/logs?limit=5")
    check("GET /api/logs", isinstance(logs, list), f"{len(logs)} 条")

    today = _req("GET", f"{base}/api/today")
    check(
        "GET /api/today",
        isinstance(today, list) and any(t["medication"] == "接口测试药 1粒" for t in today),
        f"{len(today)} 条",
    )
    target = next(t for t in today if t["medication"] == "接口测试药 1粒")
    ck = _req("POST", f"{base}/api/checkin", {"plan_id": target["id"]})
    check("POST /api/checkin", ck["status"] == "taken", ck["status"])
    after = next(
        t for t in _req("GET", f"{base}/api/today") if t["id"] == target["id"]
    )
    check("打卡后为已服药", after["taken"] is True, after["taken"])

    deleted = _req("DELETE", f"{base}/api/plans/{pid}")
    check("DELETE /api/plans", deleted["deleted"] == pid)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", action="store_true", help="顺便测试 HTTP 接口")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    test_db()
    if args.http:
        test_http(args.base)

    print()
    if _failures:
        print(f"{FAIL} 共 {_failures} 项失败")
        sys.exit(1)
    print(f"{PASS} 全部通过")


if __name__ == "__main__":
    main()
