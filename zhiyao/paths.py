"""项目路径常量

所有要读写文件的地方统一从这里取路径，好处是不管从哪个工作目录启动
（网页版 / 命令行版 / 测试脚本），拿到的都是同一个位置：

    <仓库根>/
    ├── .env                 配置（git 忽略）
    ├── .env.example         配置模板
    ├── assets/samples/      OCR 测试图片
    ├── assets/output/       语音合成产物（git 忽略）
    ├── docs/  sql/
    └── zhiyao/              代码包

以前 tts 按「当前工作目录」写 output.wav，命令行版跑一次就在包里留下一个
1.5 MB 的文件；ocr 又用 `../picture.jpg` 找图。都改成这里的常量。
"""
from pathlib import Path

# zhiyao/paths.py 往上两级就是仓库根
ROOT = Path(__file__).resolve().parents[1]

ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"

ASSETS_DIR = ROOT / "assets"
SAMPLES_DIR = ASSETS_DIR / "samples"
OUTPUT_DIR = ASSETS_DIR / "output"

DOCS_DIR = ROOT / "docs"
SQL_DIR = ROOT / "sql"

WEB_DIR = ROOT / "zhiyao" / "web"
INDEX_HTML = WEB_DIR / "static" / "index.html"

# OCR 不传图片时默认识别这张
DEFAULT_SAMPLE_IMAGE = SAMPLES_DIR / "picture.jpg"


def ensure_output_dir() -> Path:
    """确保语音输出目录存在，返回该目录"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR
