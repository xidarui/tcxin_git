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
    ├── setup_env.py                环境自检 + 一键建表 ★
    ├── sql/schema.sql              数据库 DDL（可直接导入）
    ├── tests/test_db_smoke.py      数据库 / 接口冒烟测试
    ├── docs/
    │   ├── DATABASE.md             数据库设计说明 ★
    │   └── superpowers/            需求与实现文档
    └── pill_reminder/
        ├── main.py                 命令行版入口
        ├── .env.example            配置模板（复制成 .env 后填写）
        ├── requirements.txt        依赖清单
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

## 在别的电脑上跑起来

换一台电脑时，按这 5 步走，顺序别乱：

### 0. 先确认这台机器有什么

| 需要 | 版本 | 检查命令 |
|---|---|---|
| Python | 3.10+ | `python --version` |
| MySQL Server | 8.0.13+ | `mysql --version` |
| Git | 任意 | `git --version` |

MySQL 必须是 **8.0.13 及以上**——建表语句用了 `COLLATE utf8mb4_0900_ai_ci`，5.7 不认。
装 MySQL 时记得勾上「MySQL Server」，光装 MySQL Workbench 是连不上的。

```bash
git clone https://github.com/xidarui/tcxin_git.git
cd tcxin_git/myPythonProject
```

### 1. 装依赖

```bash
pip install -r pill_reminder/requirements.txt
```

> `pyaudio` 只为命令行版的语音识别/播报服务，Windows 上编译经常失败。
> 装不上就先跳过，网页版完全不受影响，自检脚本会把它标成「可选」而不是报错。

### 2. 生成配置文件

```bash
copy pill_reminder\.env.example pill_reminder\.env        # Windows
cp pill_reminder/.env.example pill_reminder/.env          # macOS / Linux
```

然后打开 `.env` 填三样东西：讯飞 `APP_ID/API_KEY/API_SECRET`、数据库 `DB_USER/DB_PASSWORD`。

没有讯飞账号也能先跑：数据库能连上就能启动，只是 AI 分析和语音功能不可用。

### 3. 建库、建账号、建表

**推荐**：一条命令搞定（用你本机 MySQL 的 root 账号建库 + 建业务账号 + 建表）：

```bash
python setup_env.py --create-db --admin-user root --admin-password 你的root密码
```

**如果数据库已经建好了**，直接自检 + 建表：

```bash
python setup_env.py
```

想看它到底查了什么、不改任何东西：

```bash
python setup_env.py --check
```

想顺便灌几条演示数据：

```bash
python setup_env.py --demo
```

手动建也行（把密码换成你自己的）：

```sql
CREATE DATABASE pill_reminder CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER 'dev_app'@'localhost' IDENTIFIED BY '你的密码';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, INDEX, REFERENCES
  ON pill_reminder.* TO 'dev_app'@'localhost';
```

```bash
python -m pill_reminder.db.init_db --demo
```

### 4. 启动

网页版：

```bash
python app.py
# 浏览器打开 http://localhost:8000
```

命令行版：

```bash
cd pill_reminder
python main.py
```

### 5. 自测（可选）

```bash
python tests/test_db_smoke.py
```

## 常见问题

**启动就报 `Access denied for user 'dev_app'`**
`.env` 没填、或密码不对、或那个账号还没建。先跑 `python setup_env.py`，它会明确告诉你卡在哪一步。

**报 `Unknown collation: utf8mb4_0900_ai_ci`**
MySQL 是 5.7 或更老。要么升级到 8.0.13+，要么把 `models.py` 和 `schema.sql` 里的这个 collation 去掉。

**控制台报 `UnicodeEncodeError: 'gbk' codec can't encode character`**
Windows 控制台默认 GBK 编码。先执行 `chcp 65001` 切到 UTF-8，或者设环境变量 `PYTHONIOENCODING=utf-8`。
项目里的脚本已经只用 ASCII 标记输出，正常不会踩到。

**网页能打开但数据不落库**
页面顶部统计里会出现「仅本机」而不是「已存数据库」，说明 `/api/health` 返回了 `db_ready: false`——回头查数据库连接。

## 依赖

Python 3.10+ · FastAPI · SQLAlchemy 2.0 · PyMySQL · 讯飞开放平台 SDK · 星火大模型 · MySQL 8.0.13+

## 说明

本项目中的用药建议由大模型生成，**仅供参考，不能替代医嘱**。
