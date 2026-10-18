# 知药 · 前后端集成设计方案

## 概述

将现有的 Python 后端能力（星火大模型 AI 对话、讯飞 OCR 图片识别、方言语音合成）集成到 `index.html` 前端页面中。保留前端完整的适老化 UI/UX 设计，用真实后端 API 替换现有的 mock/模拟数据。

## 架构

```
浏览器 (index.html)
    │
    ├─ 静态页面 ──→ FastAPI (app.py)
    │                   │
    │                   ├─ ai/chat.py      星火大模型 v3.5
    │                   ├─ ocr/client.py   讯飞通用文字识别
    │                   └─ speech/tts.py   讯飞方言语音合成
    │
    └─ API 调用（fetch）──→ FastAPI ──→ 各模块
```

- **后端框架**: FastAPI（异步，自动文档，静态文件挂载）
- **前端**: 纯 HTML/CSS/JS，零框架依赖
- **语音识别**: 浏览器 Web Speech API（保留现有实现）
- **启动方式**: `python app.py` → 浏览器访问 `http://localhost:8000`

## 目录结构变化

```
myPythonProject/
├── app.py                  ← 新增：FastAPI 主入口
├── index.html              ← 修改：JS 函数体替换为 API 调用
├── picture.jpg             ← 保留
└── pill_reminder/          ← 完全不变
    ├── main.py
    ├── ai/chat.py
    ├── ocr/client.py
    ├── speech/tts.py
    ├── speech/iat.py
    ├── reminder/alarm.py
    └── .env
```

## API 接口

### POST `/api/chat` — AI 对话

请求:
```json
{ "text": "降压药一次吃几片？", "image_text": "", "reset": false }
```

响应:
```json
{ "reply": "💊 降压药（氨氯地平）：一次1片，一日1次，晨起服用。", "error": null }
```

底层调用 `ai/chat.py:chat_with_context()`，支持多轮对话记忆。

### POST `/api/ocr` — 拍照识别

请求: `multipart/form-data; file=<图片二进制>`

响应:
```json
{ "text_lines": ["阿莫西林", "0.5g"], "text": "阿莫西林\n0.5g", "error": null }
```

底层调用 `ocr/client.py:universal_ocr()`，支持 jpg/png/bmp，上限 10MB。

### POST `/api/tts` — 方言语音合成

请求:
```json
{ "text": "您好，欢迎使用知药", "voice": "x4_yezi" }
```

响应: `audio/wav` 二进制流

底层调用 `speech/tts.py:speech_synthesis()`，支持 7 种方言。

### GET `/api/voices` — 方言列表

响应:
```json
{ "voices": { "x4_yezi": "普通话", "x3_linlin": "闽南语", ... }, "current": "x4_yezi" }
```

## 前端改动（只改 JS，不改 CSS/HTML）

| 函数 | 改动内容 |
|------|----------|
| `speak()` | 浏览器 speechSynthesis → fetch `/api/tts` + Audio 播放 |
| `processVoiceQuery()` | 硬编码 if/else → fetch `/api/chat` |
| `quickQuestion()` | 同步调 `processVoiceQuery` → 异步调 `/api/chat`（无需改签名） |
| `triggerCamera()` | `setTimeout` mock → `<input type=file>` → `/api/ocr` → 渲染结果 |
| `searchDrugs()` | 前端 mock 过滤 → 可选：通过 `/api/chat` 智能检索 |
| 方言设置 | 3 选项 → 从 `/api/voices` 加载 7 种方言 |
| 新增 `apiCall()` | 统一 fetch 包装，含错误处理和 toast 提示 |

## 错误处理

- 3 级体系：可恢复（自动重试）/ 需提示（Toast）/ 致命（功能降级）
- `speak()` 失败时降级为浏览器原生 TTS 普通话播报
- OCR 失败时复用现有 `#drugResultFail` 提示元素
- API 密钥缺失时启动日志警告，前端调用返回友好提示

## 启动方式

```bash
cd 项目/myPythonProject
pip install fastapi uvicorn python-multipart
python app.py
# 打开 http://localhost:8000
```

## 未纳入范围

- 数据库（当前使用 localStorage 持久化，不做改动）
- 用户注册登录的后端化（保留前端 localStorage mock）
- `speech/iat.py`（语音识别保持浏览器原生）
- `reminder/alarm.py`（闹钟暂保持前端 `setInterval`，后续可扩展）
- 现有 CSS 样式和 HTML 结构全部保留不动
