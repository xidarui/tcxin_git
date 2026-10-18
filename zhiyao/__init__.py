"""知药 · 智能服药提醒系统

分层::

    zhiyao.ai        星火大模型对话
    zhiyao.ocr       讯飞通用文字识别
    zhiyao.speech    语音听写 / 方言合成
    zhiyao.reminder  闹钟调度
    zhiyao.db        MySQL 持久化
    zhiyao.web       FastAPI 网页版
    zhiyao.cli       命令行版

两个入口::

    python -m zhiyao.web.app      网页版  http://localhost:8000
    python -m zhiyao.cli          命令行版
"""

__version__ = "1.0.0"
