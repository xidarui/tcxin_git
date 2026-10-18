"""环境自检与一键初始化

在仓库根目录执行::

    python setup_env.py                 # 自检 + 建表（最常用）
    python setup_env.py --check         # 只自检，不改任何东西
    python setup_env.py --demo          # 自检 + 建表 + 演示数据
    python setup_env.py --fix           # 没有 .env 时自动从 .env.example 复制一份
    python setup_env.py --create-db --admin-user root --admin-password 你的root密码
                                        # 用管理员账号建库 + 建业务账号

换一台电脑跑这个项目时，按顺序执行上面第 1 条和第 5 条即可。

输出刻意只用 ASCII 标记（OK / WARN / FAIL），
因为 Windows 控制台默认 GBK，打 emoji 会抛 UnicodeEncodeError。
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

# 需要的第三方库：(import 名, pip 包名)
REQUIRED_MODULES = [
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("pydantic", "pydantic"),
    ("dotenv", "python-dotenv"),
    ("httpx", "httpx"),
    ("sqlalchemy", "SQLAlchemy"),
    ("pymysql", "PyMySQL"),
    ("sparkai", "spark-ai-python"),
    ("xfyunsdkcore", "xfyunsdkcore"),
    ("xfyunsdkspeech", "xfyunsdkspeech"),
]

# (import 名, pip 包名, 缺失时的说明)
OPTIONAL_MODULES = [
    ("pyaudio", "pyaudio", "只影响命令行版的语音识别/播报，网页版不用它"),
]

MIN_PYTHON = (3, 10)


def _ok(msg: str) -> None:
    print(f"[ OK ] {msg}")


def _warn(msg: str) -> None:
    print(f"[WARN] {msg}")


def _fail(msg: str) -> None:
    print(f"[FAIL] {msg}")


def check_python() -> bool:
    print("== 1. Python 版本 ==")
    major, minor = sys.version_info[:2]
    if (major, minor) < MIN_PYTHON:
        _fail(f"当前 {major}.{minor}，需要 {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+（代码用了 X | None 写法）")
        return False
    _ok(f"Python {major}.{minor}，满足 >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}")
    return True


def check_env(fix: bool) -> bool:
    print("\n== 2. 配置文件 .env ==")
    from zhiyao.db import base

    env_path, example = base._ENV_PATH, base._ENV_EXAMPLE
    env_rel = os.path.relpath(env_path, _HERE)
    example_rel = os.path.relpath(example, _HERE)

    if base.ENV_EXISTS:
        _ok(f"已找到 {env_rel}")
    elif fix and os.path.isfile(example):
        shutil.copyfile(example, env_path)
        _warn(f"已从模板生成 {env_rel}，请打开它填入密钥和数据库密码")
        print("       填好后重新运行本脚本。")
        return False
    elif os.path.isfile(example):
        _fail(f"缺少 {env_rel}")
        print(f"       Windows:      copy {example_rel} {env_rel}")
        print(f"       macOS/Linux:  cp {example_rel} {env_rel}")
        print("       或者加 --fix 让本脚本自动复制")
        return False
    else:
        _fail("既没有 .env 也没有 .env.example，仓库可能不完整")
        return False

    # 讯飞密钥缺失不阻断流程：数据库能连上就能跑，只是 AI 功能不可用
    missing_keys = [k for k in ("APP_ID", "API_KEY", "API_SECRET") if not os.getenv(k)]
    if missing_keys:
        _warn(f".env 里还没填讯飞凭证: {', '.join(missing_keys)}")
        print("       不填也能跑起来，只是 AI 分析 / OCR / 语音会不可用")
        print("       申请地址: https://console.xfyun.cn/")
    else:
        _ok("讯飞凭证已填写")

    if not (os.getenv("DB_PASSWORD") or "").strip():
        _fail(".env 里 DB_PASSWORD 还是空的，数据库连不上")
        print("       账号已经建好 → 把密码填进 .env")
        print("       还没建账号   → 先填一个你想用的密码，再执行下面这条用 root 建库建账号")
        print("       python setup_env.py --create-db --admin-user root --admin-password 你的root密码")
        return False
    _ok("数据库连接参数已填写")
    return True


def check_deps() -> bool:
    print("\n== 3. Python 依赖 ==")
    missing = []
    for mod, pkg in REQUIRED_MODULES:
        if importlib.util.find_spec(mod) is None:
            missing.append(pkg)

    optional_missing = []
    for mod, pkg, why in OPTIONAL_MODULES:
        if importlib.util.find_spec(mod) is None:
            optional_missing.append((pkg, why))

    if missing:
        _fail("缺少依赖: " + ", ".join(missing))
        print(f"       执行: pip install -r {'requirements.txt'}")
        return False
    _ok(f"必需依赖齐全（{len(REQUIRED_MODULES)} 个）")

    for pkg, why in optional_missing:
        _warn(f"可选依赖 {pkg} 未安装 —— {why}")
        print(f"       想要的话: pip install {pkg}")
        print("       Windows 上装不上可以先跳过，网页版不受影响")
    return True


def _db_error() -> str:
    """连库失败时取驱动的第一行错误，给用户看真正的原因。"""
    from sqlalchemy import text
    from sqlalchemy.exc import SQLAlchemyError

    from zhiyao.db.base import get_engine

    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        lines = [ln.strip() for ln in str(exc).splitlines() if ln.strip()]
        return lines[0][:200] if lines else repr(exc)
    return ""


def check_db(create_tables: bool, demo: bool) -> bool:
    print("\n== 4. 数据库 ==")
    from zhiyao.db import repo
    from zhiyao.db.base import DB_HOST, DB_NAME, DB_PORT, DB_USER, ping

    print(f"       连接目标: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    if not ping():
        err = _db_error()
        if "Access denied" in err:
            _fail("账号或密码不对 —— " + err)
            print("       还没建账号的话，执行：")
            print("       python setup_env.py --create-db --admin-user root --admin-password 你的root密码")
        elif "Unknown database" in err:
            _fail("数据库还不存在 —— " + err)
            print("       执行: python setup_env.py --create-db --admin-user root --admin-password 你的root密码")
        elif "Can't connect" in err or "refused" in err.lower():
            _fail("MySQL 服务没起来 —— " + err)
            print("       Windows: 在 services.msc 里启动 MySQL80 服务")
            print("       macOS:   brew services start mysql")
        else:
            _fail("连不上数据库 —— " + (err or "未知原因"))
        return False
    _ok("连接正常")

    if create_tables:
        repo.init_tables()
        _ok("数据表已就绪")

    if demo:
        from zhiyao.db.init_db import seed_demo

        seed_demo()

    stats = repo.stats()
    print("       当前数据: " + "  ".join(f"{k}={v}" for k, v in stats.items()))
    return True


def create_database(admin_user: str, admin_password: str, admin_host: str, admin_port: int) -> bool:
    """用管理员账号建库 + 建业务账号（幂等，可重复执行）"""
    print("\n== 4a. 创建数据库与账号 ==")
    import pymysql

    from zhiyao.db.base import DB_NAME, DB_PASSWORD, DB_USER

    if not DB_PASSWORD:
        _fail(".env 里 DB_PASSWORD 为空，先填好再来建库")
        return False

    try:
        conn = pymysql.connect(
            host=admin_host,
            port=admin_port,
            user=admin_user,
            password=admin_password,
            charset="utf8mb4",
        )
    except Exception as exc:  # noqa: BLE001
        _fail(f"管理员账号连不上: {exc}")
        return False

    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
            )
            for host in ("localhost", "127.0.0.1"):
                cur.execute(
                    "CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s",
                    (DB_USER, host, DB_PASSWORD),
                )
                # 账号已存在时 CREATE USER 不会改密码，这里强制同步成 .env 里的值
                cur.execute(
                    "ALTER USER %s@%s IDENTIFIED BY %s",
                    (DB_USER, host, DB_PASSWORD),
                )
                cur.execute(
                    "GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, "
                    f"INDEX, REFERENCES ON `{DB_NAME}`.* TO %s@%s",
                    (DB_USER, host),
                )
        conn.commit()
    finally:
        conn.close()

    _ok(f"数据库 {DB_NAME} 与账号 {DB_USER} 已就绪")
    print(f"       账号密码已同步为 .env 里的 DB_PASSWORD")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="知药项目的环境自检与初始化")
    parser.add_argument("--check", action="store_true", help="只自检，不建表")
    parser.add_argument("--demo", action="store_true", help="顺便写入演示数据")
    parser.add_argument("--fix", action="store_true", help="没有 .env 时自动从模板复制")
    parser.add_argument("--create-db", action="store_true", help="用管理员账号建库建账号")
    parser.add_argument("--admin-user", default="root", help="管理员账号，默认 root")
    parser.add_argument("--admin-password", default="", help="管理员密码")
    parser.add_argument("--admin-host", default="127.0.0.1")
    parser.add_argument("--admin-port", type=int, default=3306)
    args = parser.parse_args()

    print("=" * 52)
    print("  知药 · 环境自检")
    print("=" * 52)

    if not check_python():
        sys.exit(1)

    env_ok = check_env(fix=args.fix)
    deps_ok = check_deps()

    if not env_ok:
        print("\n[STOP] 配置没准备好，先处理上面的问题")
        sys.exit(1)
    if not deps_ok:
        print("\n[STOP] 依赖没装全，先 pip install")
        sys.exit(1)

    if args.create_db:
        if not args.admin_password:
            _fail("--create-db 需要同时提供 --admin-password")
            sys.exit(1)
        create_database(
            args.admin_user, args.admin_password, args.admin_host, args.admin_port
        )

    db_ok = check_db(create_tables=not args.check, demo=args.demo and not args.check)

    print("\n" + "=" * 52)
    if db_ok:
        _ok("全部就绪")
        if not args.check:
            print("\n下一步：")
            print("   网页版   python -m zhiyao.web.app   -> http://localhost:8000")
            print("   命令行版 python -m zhiyao.cli")
    else:
        _fail("数据库还没通，见上面第 4 节的排查顺序")
        sys.exit(1)


if __name__ == "__main__":
    main()
