# tcxin_git

「知药」智能服药提醒系统 —— 拍照识别药方 → AI 分析用药方案 → 方言语音播报 → 定时提醒吃药。

## 功能

- 📷 **拍照识别**：讯飞 OCR 读取药盒 / 说明书文字
- 🎤 **语音咨询**：讯飞语音听写，把说的话转成文字
- 🤖 **AI 分析**：星火大模型解析用法用量，并主动提示禁忌与药物相互作用
- 🗣️ **方言播报**：普通话 / 粤语 / 闽南语 / 四川话 / 东北话 / 河南话 / 成都话 / 内蒙古
- ⏰ **定时提醒**：从 AI 回复里解析服药时间，到点自动语音提醒
- 💾 **数据持久化**：提醒计划、服药记录、对话历史都存 MySQL，重启不丢；网页端的增删改和打卡都直接写库

两种用法：

- **网页版**：FastAPI + 单页前端，浏览器里操作
- **命令行版**：`pill_reminder/main.py`，终端菜单交互

## 目录结构

```
tcxin_git/
├── README.md
└── myPythonProject/
    ├── app.py                      FastAPI 服务入口（网页版）
    ├── index.html                  前端单页
    ├── sql/schema.sql              数据库 DDL（可直接导入）
    ├── tests/test_db_smoke.py      数据库 / 接口冒烟测试
    ├── docs/
    │   ├── DATABASE.md             数据库设计说明 ★
    │   └── superpowers/            需求与实现文档
    └── pill_reminder/
        ├── main.py                 命令行版入口
        ├── ai/chat.py              星火大模型对话
        ├── ocr/client.py           讯飞 OCR
        ├── speech/                 语音识别 / 方言合成
        ├── reminder/alarm.py       闹钟调度
        └── db/                     数据库层 ★
            ├── base.py             引擎与会话
            ├── models.py           4 张表的 ORM 定义
            ├── repo.py             增删改查
            └── init_db.py          初始化脚本
```

## 快速开始

### 1. 装依赖

```bash
pip install -r myPythonProject/pill_reminder/requirements.txt
```

### 2. 配密钥与环境变量

在 `myPythonProject/pill_reminder/.env` 里填：

```ini
# 讯飞开放平台凭证
APP_ID=your_app_id
API_KEY=your_api_key
API_SECRET=your_api_secret

# MySQL 连接（见 docs/DATABASE.md）
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=dev_app
DB_PASSWORD=your_password
DB_NAME=pill_reminder
```

### 3. 建库建表

见 [docs/DATABASE.md](myPythonProject/docs/DATABASE.md) 第三节。简版：

```sql
CREATE DATABASE pill_reminder CHARACTER SET utf8mb4;
CREATE USER 'dev_app'@'localhost' IDENTIFIED BY '你的密码';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, INDEX, REFERENCES
  ON pill_reminder.* TO 'dev_app'@'localhost';
```

```bash
cd myPythonProject
python -m pill_reminder.db.init_db --demo
```

### 4. 启动

网页版：

```bash
cd myPythonProject
python app.py
# 浏览器打开 http://localhost:8000
```

命令行版：

```bash
cd myPythonProject/pill_reminder
python main.py
```

### 5. 自测

```bash
cd myPythonProject
python tests/test_db_smoke.py
```

## 依赖

Python 3.13 · FastAPI · SQLAlchemy 2.0 · PyMySQL · 讯飞开放平台 SDK · 星火大模型

## 说明

本项目中的用药建议由大模型生成，**仅供参考，不能替代医嘱**。
