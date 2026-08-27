# 知药 · 前后端集成 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `pill_reminder/` 的 Python 后端能力（星火大模型 AI、讯飞 OCR、方言 TTS）通过 FastAPI 集成到 `index.html` 前端中

**Architecture:** 新增 `app.py`（FastAPI 服务器）挂载静态文件并提供 REST API；`index.html` 中 JS 函数从 mock/硬编码改为 fetch 调用后端 API；`pill_reminder/` 内部模块完全不动

**Tech Stack:** Python 3, FastAPI, uvicorn, 讯飞 SDK, 星火大模型 sparkai

## Global Constraints

- `pill_reminder/` 目录下所有 `.py` 文件和 `.env` 文件完全不动
- `index.html` 的 CSS 样式和 HTML 结构完全不动，只改 `<script>` 中的 JS 函数体
- 语音识别继续使用浏览器 Web Speech API（`speech/iat.py` 不进前端）
- 闹钟保持前端 `setInterval`（`reminder/alarm.py` 暂不集成）
- `picture.jpg` 保留在项目根目录
- API 密钥缺失时 app.py 启动日志警告，前端返回友好错误提示而非崩溃

---

### 前置准备

- [ ] **Step: 确认 Python 环境和依赖**

```bash
cd /c/Users/Administrator/Desktop/知药/项目/myPythonProject
python --version
pip list 2>/dev/null | grep -iE "fastapi|uvicorn|httpx|sparkai|dotenv|pyaudio" || echo "需要安装依赖"
```

---

### Task 1: 创建 FastAPI 服务器 `app.py`

**Files:**
- Create: `项目/myPythonProject/app.py`

**Interfaces:**
- Produces: FastAPI 应用，含 4 个 API 端点 + 静态文件挂载
  - `POST /api/chat` — AI 对话
  - `POST /api/ocr` — OCR 图片识别
  - `POST /api/tts` — 方言语音合成
  - `GET /api/voices` — 方言列表

- [ ] **Step 1: 创建 app.py**

```python
"""
知药 · FastAPI 服务入口

启动方式: python app.py
访问地址: http://localhost:8000

集成了:
- POST /api/chat  → ai/chat.py  → 星火大模型
- POST /api/ocr  → ocr/client.py → 讯飞 OCR
- POST /api/tts  → speech/tts.py → 方言语音合成
- GET  /api/voices → 方言列表
"""
import os
import sys
import io
import logging

# 确保能找到 pill_reminder 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
import uvicorn

# 先加载 .env，让子模块的 load_dotenv() 继承已有环境变量
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pill_reminder', '.env')
load_dotenv(_env_path)

# 检查 API 凭证
_missing = [k for k in ['APP_ID', 'API_KEY', 'API_SECRET'] if not os.getenv(k)]
if _missing:
    logging.warning(f"⚠️ .env 缺失凭证: {', '.join(_missing)}，API 调用将返回错误")

# 导入后端模块
from pill_reminder.ai.chat import chat_with_context, clear_history
from pill_reminder.ocr.client import universal_ocr
from pill_reminder.speech.tts import speech_synthesis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="知药智能服药助手")

# ========================
#  Pydantic 请求/响应模型
# ========================

class ChatRequest(BaseModel):
    text: str = ""
    image_text: str = ""
    reset: bool = False

class ChatResponse(BaseModel):
    reply: str
    error: str | None = None

class OcrResponse(BaseModel):
    text_lines: list[str]
    text: str
    error: str | None = None

class TtsRequest(BaseModel):
    text: str
    voice: str = "x4_yezi"

class VoicesResponse(BaseModel):
    voices: dict[str, str]
    current: str

# 发音人数据
_VOICES = {
    "x4_yezi": "普通话",
    "x3_linlin": "闽南语",
    "x2_xiaobao": "内蒙古",
    "x3_yezi_sc": "四川话",
    "x4_xiaobei": "东北话",
    "x2_xiaokun": "河南话",
    "x3_xiaodu": "成都话",
}

# ========================
#  API 路由
# ========================

@app.get("/")
def index():
    """返回前端页面"""
    index_path = os.path.join(os.path.dirname(__file__), 'index.html')
    return FileResponse(index_path)

@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """AI 对话 — 调用星火大模型"""
    if req.reset:
        clear_history()
        return ChatResponse(reply="🧹 对话历史已重置", error=None)
    try:
        reply, _ = chat_with_context(text=req.text, image_text=req.image_text)
        return ChatResponse(reply=reply, error=None)
    except Exception as e:
        logger.error(f"Chat API 错误: {e}")
        return ChatResponse(reply="❌ AI服务暂时不可用，请稍后重试", error=str(e))

@app.post("/api/ocr", response_model=OcrResponse)
async def ocr(file: UploadFile = File(...)):
    """OCR 图片识别 — 上传图片，返回文字"""
    # 校验文件类型
    allowed = {'.jpg', '.jpeg', '.png', '.bmp'}
    ext = os.path.splitext(file.filename or '')[1].lower()
    if ext not in allowed:
        return OcrResponse(text_lines=[], text="", error=f"不支持的文件格式 {ext}，支持 jpg/png/bmp")

    # 校验文件大小 (10MB)
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        return OcrResponse(text_lines=[], text="", error="文件过大，请上传小于 10MB 的图片")

    # 保存到临时文件
    tmp_path = os.path.join(os.path.dirname(__file__), '_tmp_ocr' + ext)
    try:
        with open(tmp_path, 'wb') as f:
            f.write(contents)

        lines = universal_ocr(tmp_path)
        text = "\n".join(lines)
        return OcrResponse(text_lines=lines, text=text, error=None)
    except FileNotFoundError:
        return OcrResponse(text_lines=[], text="", error="图片文件不存在")
    except PermissionError as e:
        return OcrResponse(text_lines=[], text="", error=f"OCR授权失败: {e}")
    except ValueError as e:
        return OcrResponse(text_lines=[], text="", error=str(e))
    except Exception as e:
        logger.error(f"OCR API 错误: {e}")
        return OcrResponse(text_lines=[], text="", error=f"OCR识别失败: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

@app.post("/api/tts")
def tts(req: TtsRequest):
    """方言语音合成 — 返回 WAV 音频流"""
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="text 不能为空")
    if len(req.text) > 500:
        raise HTTPException(status_code=400, detail="text 超过 500 字限制")
    if req.voice not in _VOICES:
        raise HTTPException(status_code=400, detail=f"不支持的方言: {req.voice}")

    try:
        file_path = speech_synthesis(req.voice, req.text)
        with open(file_path, 'rb') as f:
            audio_data = f.read()
        # 清理临时文件
        try:
            os.remove(file_path)
        except OSError:
            pass
        return Response(content=audio_data, media_type="audio/wav")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"TTS API 错误: {e}")
        raise HTTPException(status_code=502, detail=f"语音合成失败: {e}")

@app.get("/api/voices", response_model=VoicesResponse)
def voices():
    """返回方言列表"""
    return VoicesResponse(voices=_VOICES, current="x4_yezi")

@app.get("/health")
def health():
    """健康检查"""
    missing = [k for k in ['APP_ID', 'API_KEY', 'API_SECRET'] if not os.getenv(k)]
    return {"status": "ok" if not missing else "degraded", "missing_keys": missing}

# ========================
#  启动
# ========================

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print(f"💊 知药智能服药助手启动!")
    print(f"   访问地址: http://localhost:{port}")
    print(f"   API文档:  http://localhost:{port}/docs")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
```

- [ ] **Step 2: 验证 app.py 启动**

```bash
cd /c/Users/Administrator/Desktop/知药/项目/myPythonProject
python app.py &
sleep 3
# 健康检查
curl -s http://localhost:8000/health
# 方言列表
curl -s http://localhost:8000/api/voices
# 首页返回 HTML
curl -s http://localhost:8000 | head -c 200
# 停止
kill %1 2>/dev/null
```

期望输出: 健康检查返回 JSON，方言列表返回 7 种方言，首页返回 HTML 片段

---

### Task 2: 更新 `index.html` — `apiCall()` 包装、`speak()` TTS、方言设置

**Files:**
- Modify: `项目/myPythonProject/index.html`

**Interfaces:**
- Consumes: `POST /api/tts`, `GET /api/voices`
- Produces: 前端全局工具函数 `apiCall()`, 后端驱动的 `speak()`, 方言自动加载

- [ ] **Step 1: 在 APP 状态对象后添加 `apiCall()` 工具函数**

在 `index.html` 的 `<script>` 中，找到 `// ================================================================` 和 `//  工具函数` 部分。在 `toast()` 函数 **之后**、`speak()` 函数 **之前** 插入：

```js
// ================================================================
//  API 调用包装
// ================================================================
async function apiCall(url, options = {}) {
    const defaultHeaders = { 'Content-Type': 'application/json' };
    // 如果是 FormData，不设置 Content-Type（浏览器自动设）
    const isFormData = options.body instanceof FormData;
    const headers = isFormData ? (options.headers || {}) : { ...defaultHeaders, ...options.headers };
    const resp = await fetch(url, {
        headers,
        ...options,
    });
    if (!resp.ok) {
        const errText = await resp.text().catch(() => 'Unknown error');
        throw new Error(`HTTP ${resp.status}: ${errText}`);
    }
    const contentType = resp.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
        return resp.json();
    }
    return resp;
}
```

- [ ] **Step 2: 替换 `speak()` 函数**

**原函数**（约第 1389-1400 行）：
```js
function speak(text, callback) {
    if (!window.speechSynthesis) { if (callback) callback(); return; }
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = APP.dialect || 'zh-CN';
    utter.rate = APP.speechRate || 0.9;
    utter.volume = APP.volume || 0.9;
    utter.pitch = 1.0;
    utter.onend = () => { if (callback) callback(); };
    utter.onerror = () => { if (callback) callback(); };
    window.speechSynthesis.speak(utter);
}
```

**替换为：**
```js
async function speak(text, callback) {
    const voice = APP.dialectVoice || 'x4_yezi';
    try {
        const resp = await apiCall('/api/tts', {
            method: 'POST',
            body: JSON.stringify({ text, voice })
        });
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        audio.onended = () => { URL.revokeObjectURL(url); if (callback) callback(); };
        audio.onerror = () => { fallbackSpeak(text, callback); };
        audio.play().catch(() => fallbackSpeak(text, callback));
    } catch (e) {
        console.warn('TTS API 失败，降级为浏览器 TTS:', e);
        fallbackSpeak(text, callback);
    }
}

function fallbackSpeak(text, callback) {
    if (!window.speechSynthesis) { if (callback) callback(); return; }
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = 'zh-CN';
    utter.rate = 0.9;
    utter.volume = 0.9;
    utter.onend = () => { if (callback) callback(); };
    utter.onerror = () => { if (callback) callback(); };
    window.speechSynthesis.speak(utter);
}
```

- [ ] **Step 3: 在 `enterRole('assistant')` 中增加方言加载**

找到 `enterRole` 函数中的 `else` 分支（约第 1542-1562 行），在 `document.getElementById('dialectSelect').value = APP.dialect;` 这一行 **之前** 添加方言加载调用：

```js
loadVoices();
```

然后在任意位置（比如 `loadData()` 附近）添加 `loadVoices()` 函数：

```js
async function loadVoices() {
    try {
        const data = await apiCall('/api/voices');
        const select = document.getElementById('dialectSelect');
        if (!select) return;
        select.innerHTML = '';
        let firstKey = null;
        Object.entries(data.voices).forEach(([key, name]) => {
            if (!firstKey) firstKey = key;
            const opt = document.createElement('option');
            opt.value = key;
            opt.textContent = name;
            if (key === data.current) opt.selected = true;
            select.appendChild(opt);
        });
        // 同步 APP 中的方言代号
        APP.dialectVoice = data.current || firstKey;
    } catch (e) {
        console.warn('方言列表加载失败，使用默认值');
    }
}
```

- [ ] **Step 4: 在 `saveSettings()` 中保存方言代号**

修改 `saveSettings()` 函数（约第 1973-1978 行）：

**原函数：**
```js
function saveSettings() {
    APP.dialect = document.getElementById('dialectSelect').value;
    saveData();
    toast('已保存设置');
    speak('设置已保存');
}
```

**替换为：**
```js
function saveSettings() {
    const voiceKey = document.getElementById('dialectSelect').value;
    APP.dialectVoice = voiceKey;
    // 从 VOICES 映射找对应的语言标签（给浏览器语音识别用）
    const voiceMap = {
        'x4_yezi': 'zh-CN', 'x3_linlin': 'zh-HK',
        'x2_xiaobao': 'zh-CN', 'x3_yezi_sc': 'zh-CN',
        'x4_xiaobei': 'zh-CN', 'x2_xiaokun': 'zh-CN', 'x3_xiaodu': 'zh-CN'
    };
    APP.dialect = voiceMap[voiceKey] || 'zh-CN';
    saveData();
    toast('已保存设置');
    speak('设置已保存');
}
```

- [ ] **Step 5: 验证 TTS + 方言功能**

```bash
cd /c/Users/Administrator/Desktop/知药/项目/myPythonProject
python app.py
```

浏览器打开 `http://localhost:8000`，登录后进入**辅助端** → 切换到**家人**标签 → 检查方言下拉菜单是否显示 7 种方言 → 切换方言 → 点"保存" → 退出到角色选择 → 进入**老人端** → 界面上应显示 7 个选项且可选择

---

### Task 3: 更新 `index.html` — AI 对话和拍照识别

**Files:**
- Modify: `项目/myPythonProject/index.html`

**Interfaces:**
- Consumes: `POST /api/chat`, `POST /api/ocr`

- [ ] **Step 1: 替换 `processVoiceQuery()` 函数**

**原函数**（约第 1767-1801 行，整个 `processVoiceQuery` 函数体）：
```js
function processVoiceQuery(query) {
    const answerDiv = document.getElementById('voiceAnswer');
    const textEl = document.getElementById('answerText');
    const tagsEl = document.getElementById('answerTags');
    answerDiv.classList.remove('hidden');
    const lower = query.toLowerCase();
    let answer = '', tags = [];
    if (lower.includes('降压') || lower.includes('血压')) {
        answer = '💊 降压药（氨氯地平）：一次1片，一日1次，晨起服用。注意：低血压患者慎用，服药期间定期监测血压。';
        tags = ['✅ 晨起服用', '⚠️ 监测血压'];
    } else if ... // 所有硬编码分支
    ...
}
```

**替换为：**
```js
async function processVoiceQuery(query) {
    const answerDiv = document.getElementById('voiceAnswer');
    const textEl = document.getElementById('answerText');
    const tagsEl = document.getElementById('answerTags');
    answerDiv.classList.remove('hidden');
    textEl.textContent = '⏳ AI思考中，请稍候...';
    tagsEl.innerHTML = '';
    try {
        const data = await apiCall('/api/chat', {
            method: 'POST',
            body: JSON.stringify({ text: query })
        });
        textEl.textContent = data.reply;
        // 从回复中提取标签
        const tags = [];
        // 提取 ✅ 开头的建议
        const safeMatch = data.reply.match(/✅[^。\n]*/);
        if (safeMatch) tags.push({ text: safeMatch[0].trim(), cls: 'tag-safe' });
        // 提取 ⚠️ 开头的警告
        const warnMatch = data.reply.match(/⚠️[^。\n]*/);
        if (warnMatch) tags.push({ text: warnMatch[0].trim(), cls: 'tag-danger' });
        // 提取 🚫 开头的禁忌
        const banMatch = data.reply.match(/🚫[^。\n]*/);
        if (banMatch) tags.push({ text: banMatch[0].trim(), cls: 'tag-danger' });
        // 如果提取不到标签，用默认标签
        if (tags.length === 0) {
            if (data.reply.includes('咨询医生') || data.reply.includes('禁忌') || data.reply.includes('禁用')) {
                tags.push({ text: '💡 咨询医生', cls: 'tag-danger' });
            } else {
                tags.push({ text: '✅ 参考建议', cls: 'tag-safe' });
            }
        }
        tagsEl.innerHTML = tags.map(t => `<span class="tag ${t.cls}">${t.text}</span>`).join('');
        speak(data.reply);
        document.getElementById('voiceStatusText').textContent = '✅ 已回答，可继续提问';
    } catch (e) {
        textEl.textContent = '😅 网络开小差了，请稍后重试';
        tagsEl.innerHTML = '';
        document.getElementById('voiceStatusText').textContent = '❌ 回答失败，请重试';
    }
}
```

- [ ] **Step 2: 确认 `quickQuestion()` 无需改动**

`quickQuestion()` 函数（约第 1804-1807 行）目前直接调用 `processVoiceQuery(q)`。

因为 `processVoiceQuery` 改为 `async`，调用方 `quickQuestion` 也需要是 `async`，但**调用方式不变**（`onclick` 中可以直接调用 async 函数，浏览器会处理返回值）。将 `quickQuestion` 改为 `async`：

```js
async function quickQuestion(q) {
    document.getElementById('voiceStatusText').textContent = `🗣️ 你问: "${q}"`;
    await processVoiceQuery(q);
}
```

- [ ] **Step 3: 替换 `triggerCamera()` 函数**

**原函数**（约第 1812-1843 行，整个 `triggerCamera` 函数体）：
```js
function triggerCamera() {
    const loading = document.getElementById('drugResultLoading');
    const result = document.getElementById('drugResult');
    const fail = document.getElementById('drugResultFail');
    result.classList.add('hidden');
    fail.classList.add('hidden');
    loading.classList.remove('hidden');
    toast('📸 正在识别药品...');
    setTimeout(() => {
        loading.classList.add('hidden');
        if (Math.random() > 0.15) {
            result.classList.remove('hidden');
            // ... mock 渲染
        } else {
            fail.classList.remove('hidden');
        }
    }, 1500);
}
```

**替换为：**
```js
async function triggerCamera() {
    const loading = document.getElementById('drugResultLoading');
    const result = document.getElementById('drugResult');
    const fail = document.getElementById('drugResultFail');
    result.classList.add('hidden');
    fail.classList.add('hidden');

    // 创建文件选择器
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = 'image/*,image/jpeg,image/png';
    fileInput.capture = 'environment';  // 移动端优先后置摄像头
    fileInput.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        loading.classList.remove('hidden');
        toast('📸 正在识别药品...');

        try {
            // Step 1: OCR 识别
            const formData = new FormData();
            formData.append('file', file);
            const ocrResp = await fetch('/api/ocr', {
                method: 'POST',
                body: formData
            });
            const ocrData = await ocrResp.json();

            if (ocrData.error) {
                throw new Error(ocrData.error);
            }
            if (!ocrData.text || ocrData.text.trim() === '') {
                loading.classList.add('hidden');
                fail.classList.remove('hidden');
                document.querySelector('#drugResultFail') &&
                    (document.querySelector('#drugResultFail').textContent = '😅 未识别到文字，请拍药盒正面');
                speak('没看清，请重新拍一下药盒正面');
                toast('😅 未识别到文字');
                return;
            }

            // Step 2: AI 分析识别结果
            const chatResp = await apiCall('/api/chat', {
                method: 'POST',
                body: JSON.stringify({ image_text: ocrData.text })
            });

            // Step 3: 渲染结果
            loading.classList.add('hidden');
            result.classList.remove('hidden');
            document.getElementById('drugResultName').textContent = `💊 识别结果`;
            document.getElementById('drugResultInfo').textContent = ocrData.text;

            // 找到或创建 AI 回复展示区
            let aiInfoEl = document.querySelector('.drug-result-card .drug-ai-reply');
            if (!aiInfoEl) {
                aiInfoEl = document.createElement('div');
                aiInfoEl.className = 'drug-info drug-ai-reply';
                aiInfoEl.style.marginTop = '12px';
                aiInfoEl.style.padding = '12px';
                aiInfoEl.style.background = '#f0f6ff';
                aiInfoEl.style.borderRadius = '16px';
                aiInfoEl.style.fontSize = '26px';
                aiInfoEl.style.color = 'var(--blue)';
                const cardBody = document.querySelector('.drug-result-card');
                if (cardBody) {
                    cardBody.insertBefore(aiInfoEl, cardBody.querySelector('.tag-safe')?.parentNode || null);
                }
            }
            aiInfoEl.textContent = chatData.reply;

            // 安全标签
            const tagContainer = document.querySelector('.drug-result-card .tag-safe')?.parentNode;
            if (tagContainer) {
                const safeTags = tagContainer.querySelectorAll('.tag-safe, .tag-danger');
                safeTags.forEach(t => t.remove());
                if (chatData.reply.includes('✅') || !chatData.reply.includes('⚠️')) {
                    tagContainer.innerHTML = '<span class="tag tag-safe">✅ 安全服用</span>';
                } else {
                    tagContainer.innerHTML = '<span class="tag tag-danger">⚠️ 请遵医嘱</span>';
                }
            }

            // 保存识别名称供"加入提醒"用
            APP._lastOcrDrugName = ocrData.text.split('\n')[0] || '识别药品';
            APP._lastOcrDrugAi = chatData.reply;

            speak(chatData.reply);
            toast('✅ 识别成功');
        } catch (err) {
            loading.classList.add('hidden');
            fail.classList.remove('hidden');
            document.querySelector('#drugResultFail') &&
                (document.querySelector('#drugResultFail').textContent = '😅 ' + err.message);
            toast('😅 识别失败，请重拍');
        }
    };
    fileInput.click();
}
```

- [ ] **Step 4: 更新 `addToReminderFromDrug()` 使用真实识别结果**

找到 `addToReminderFromDrug()` 函数（约第 1845-1864 行），修改为从 `APP._lastOcrDrugName` 读取药名：

**原函数：**
```js
function addToReminderFromDrug() {
    const nameEl = document.getElementById('drugResultName');
    const name = nameEl.textContent.replace('💊 ', '');
    ...
}
```

**替换为：**
```js
function addToReminderFromDrug() {
    const name = APP._lastOcrDrugName || document.getElementById('drugResultName').textContent.replace('💊 ', '') || '识别药品';
    const now = new Date();
    const hour = (now.getHours() + 1) % 24;  // 建议一小时后
    const minute = now.getMinutes();
    const time = `${String(hour).padStart(2,'0')}:${String(minute).padStart(2,'0')}`;
    APP.medications.push({
        id: generateId(),
        name: name,
        time: time,
        date: getToday(),
        taken: false,
    });
    saveData();
    renderReminderList();
    renderElderlyReminders();
    updateTodayStats();
    toast(`✅ 已加入提醒：${name} ${time}`);
    speak(`已加入吃药提醒`);
}
```

- [ ] **Step 5: 在函数暴露列表中增加新的全局函数**

在文件末尾（约第 2086-2115 行 `window.xxx = xxx` 部分），增加 `apiCall` 和 `loadVoices`：

```js
window.apiCall = apiCall;
window.loadVoices = loadVoices;
```

- [ ] **Step 6: 验证 AI 对话 + OCR 功能**

```bash
cd /c/Users/Administrator/Desktop/知药/项目/myPythonProject
python app.py &
# 测试 chat API
curl -s -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"text":"降压药一次吃几片？"}' | python -c "import sys,json; d=json.load(sys.stdin); print(d['reply'][:80])"
# 测试 OCR API（用项目中的图片）
curl -s -X POST http://localhost:8000/api/ocr \
  -F "file=@picture.jpg" | python -c "import sys,json; d=json.load(sys.stdin); print('text_lines:', d['text_lines'])"
# 停止
kill %1 2>/dev/null
```

期望输出: chat 返回 AI 回答（非硬编码），OCR 返回图片中的文字行

---

### Task 4: 更新依赖 + 端到端验证

**Files:**
- Modify: `项目/myPythonProject/pill_reminder/requirements.txt`

- [ ] **Step 1: 更新 requirements.txt 增加 FastAPI 依赖**

在 `pill_reminder/requirements.txt` 末尾追加：

```
fastapi>=0.110.0
uvicorn>=0.29.0
python-multipart>=0.0.9
```

- [ ] **Step 2: 安装新增依赖**

```bash
cd /c/Users/Administrator/Desktop/知药/项目/myPythonProject
pip install fastapi uvicorn python-multipart
```

- [ ] **Step 3: 启动服务并完整测试**

```bash
cd /c/Users/Administrator/Desktop/知药/项目/myPythonProject
python app.py
```

浏览器打开 `http://localhost:8000`，逐项验证：

| 功能 | 操作 | 预期结果 |
|------|------|----------|
| 登录 | 使用 13800008888 / 123456 | 进入角色选择 |
| 进入老人端 | 点击"老人端" | 看到语音问药、拍照识药、吃药提醒、SOS |
| 语音问药 | 点击快速提问"降压药一次吃几片？" | AI回答，带安全标签，语音播报 |
| 拍照识药 | 点击拍照区域，选择 picture.jpg | 显示识别文字 + AI分析 |
| 吃药提醒 | 点击"吃药提醒" | 显示今日计划 |
| 返回 + 辅助端 | 切换到辅助端 | 显示健康看板 |
| 方言设置 | 切换到"家人"标签 | 下拉菜单显示7种方言 |
| 药库查询 | 输入"阿莫西林"搜索 | 从AI获取信息 |

- [ ] **Step 4: 错误处理验证**

```bash
# 模拟 API 密钥缺失（启动时应有警告）
cd /c/Users/Administrator/Desktop/知药/项目/myPythonProject
APP_ID="" python app.py &
sleep 2
# 应有日志警告
curl -s http://localhost:8000/health
# chat 应返回友好错误
curl -s -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d '{"text":"test"}'
kill %1 2>/dev/null
```

期望输出: health 返回 `{"status": "degraded"}`，chat 返回 `{"reply": "❌ ..."}` 而非崩溃

---

## 自审检查

**1. 规格覆盖:**
- ✅ FastAPI 服务器 + API 路由 → Task 1 `app.py`
- ✅ 方言 TTS `/api/tts` → Task 1 路由 + Task 2 `speak()` 替换
- ✅ 方言列表 `/api/voices` → Task 1 路由 + Task 2 `loadVoices()`
- ✅ AI 对话 `/api/chat` → Task 1 路由 + Task 3 `processVoiceQuery()` 替换
- ✅ OCR `/api/ocr` → Task 1 路由 + Task 3 `triggerCamera()` 替换
- ✅ 全局错误处理 → Task 2 `apiCall()` + `speak()` 降级 + Task 1 异常捕获
- ✅ 依赖更新 → Task 4
- ✅ 端到端测试 → Task 4

**2. 占位符检查:** ✅ 无 TBD/TODO，所有代码完整

**3. 类型一致性:**
- `apiCall(url, options) -> Promise` → Task 2 定义，Task 3 调用 ✓
- `speak(text, callback?)` → Task 2 定义，全项目各处调用 ✓
- `processVoiceQuery(query)` → Task 3 定义（async），Task 3 `quickQuestion()` 调用 ✓
- `triggerCamera()` → Task 3 定义（async），HTML `onclick` 调用 ✓
- `loadVoices()` → Task 2 定义，Task 2 `enterRole()` 调用 ✓
- `POST /api/chat` → Task 1 定义，Task 3 消费 ✓
- `POST /api/ocr` → Task 1 定义，Task 3 消费 ✓
- `POST /api/tts` → Task 1 定义，Task 2 消费 ✓
- `GET /api/voices` → Task 1 定义，Task 2 消费 ✓
