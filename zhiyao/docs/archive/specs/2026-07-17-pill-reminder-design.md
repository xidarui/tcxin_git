# 智能提醒吃药系统 — 重构设计方案

## 概述

对现有杂乱的项目代码进行重构，以功能模块化方式组织代码，构建一个完整的"智能提醒吃药系统"：支持拍照识别药品说明书、语音输入症状、AI对话（含禁忌提醒）、方言语音播报、以及基于AI分析药方的定时闹钟。

## 系统流程

```
         ┌── 拍照(药方/说明书) ──→ [OCR模块] ──→ 文字 ──┐
用户输入 ─┤                                              ├──→ [AI大模型] ──→ AI回答+禁忌提醒 ──→ [TTS方言朗读]
         └── 说话(症状描述) ──→ [语音识别] ──→ 文字 ──┘                              │
                                                                                     ↓
                                                                              [定时闹钟] ← AI分析用量
```

## 目录结构

```
myPythonProject/pill_reminder/       ← 全新项目目录
├── main.py                          ← 主入口
├── .env                             ← API密钥（从旧根目录复制）
├── requirements.txt                 ← 依赖清单
├── picture.jpg                      ← OCR测试图片（保留）
│
├── ocr/                             ← 通用文字识别
│   ├── __init__.py
│   └── client.py
│
├── speech/                          ← 语音能力
│   ├── __init__.py
│   ├── iat.py                       ← 语音识别（麦克风→文字）
│   └── tts.py                       ← 语音合成（文字→方言播放）
│
├── ai/                              ← 大模型对话
│   ├── __init__.py
│   └── chat.py                      ← 星火对话 + 禁忌提醒
│
└── reminder/                        ← 定时提醒
    ├── __init__.py
    └── alarm.py                     ← 闹钟引擎 + AI分析用量
```

## 模块接口设计

### 1. `ocr/client.py` — 通用文字识别
- 来源：`speech/resources/intisig_ocr_test.py`
- 暴露函数：
  - `universal_ocr(image_path: str = None) -> list[str]` — 识别图片文字

### 2. `speech/iat.py` — 语音识别
- 来源：`speech/iat_test.py`（根目录版本，更稳定）
- 暴露函数：
  - `microphone_stream() -> str` — 麦克风录音→识别文字

### 3. `speech/tts.py` — 方言语音合成
- 来源：`speech/iat_progress/tts_test.py`（支持发音人参数）
- 暴露函数：
  - `speech_synthesis(choose: str, text: str, filename: str = "output.wav") -> str`

### 4. `ai/chat.py` — AI对话（含禁忌提醒）
- 来源：`speech/chat_with_ai/小组项目/chat_with_ai.py`
- 暴露函数：
  - `stream_chat(query: str, history: list = None) -> tuple[str, list]` — 多轮对话
  - `chat_with_context(text: str, image_text: str = "") -> tuple[str, list]` — 混合输入版
- 新增能力：system prompt中内置禁忌提醒指令

### 5. `reminder/alarm.py` — 定时提醒
- 新建模块
- 暴露函数：
  - `analyze_medication(ocr_text: str) -> list[dict]` — AI分析药方
  - `schedule_alarms(alarms: list[dict]) -> None` — 设置定时闹钟

### 6. `main.py` — 主菜单
```
===== 智能提醒吃药系统 =====
1. 📷 拍照识别（OCR）
2. 🎤 语音咨询
3. 📷+🎤 混合咨询（拍药单+说话）
4. ⏰ 设置定时提醒（拍药方→AI分析→自动闹钟）
0. 🚪 退出
============================
```

## 数据流

1. **OCR路径**: 拍照片 → `ocr/client.py:universal_ocr()` → 文字列表 → `ai/chat.py:chat_with_context(image_text=文字)`
2. **语音路径**: 说话 → `speech/iat.py:microphone_stream()` → 文字 → `ai/chat.py:chat_with_context(text=文字)`
3. **混合路径**: OCR文字 + 语音文字 → 一起传入 `chat_with_context()`
4. **提醒路径**: OCR药方 → `reminder/alarm.py:analyze_medication()` → AI返回时间表 → `schedule_alarms()` → 到点TTS播报

## 依赖

- `xfyun` SDK套件（`xfyunsdkspeech`, `xfyunsdkocr`, `xfyunsdkcore`）
- `sparkai` — 星火大模型
- `pyaudio` — 音频输入输出
- `httpx` — HTTP请求
- `python-dotenv` — 环境变量
- `python-dateutil` — 时间解析（可选）

## 未纳入范围

- 旧目录下的无关测试文件（igr_test.py, ise_test.py, lfasr_test.py, qbh_test.py, rtasr_test.py）保留不动，不迁移
- `chat_with_ai/node/` 中的 Node.js 第三方包保留不动
