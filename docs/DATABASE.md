# 数据库设计说明

## 一、为什么加数据库

改造前的问题：

| 问题 | 现象 |
|---|---|
| 提醒计划存在内存里 | 程序一关，设好的闹钟全部消失 |
| 对话历史是模块级全局变量 `_global_history` | 重启后 AI 不记得刚才聊过什么 |
| 没有任何服药记录 | 无法回答「昨天早上的药吃了没」 |

改造后：提醒计划、服药记录、对话历史全部落到 MySQL，重启即恢复。

---

## 二、表结构

```
┌──────────────┐        ┌─────────────────┐        ┌──────────────┐
│  medication  │ 1    N │   alarm_plan    │ 1    N │   dose_log   │
│  药品字典     ├───────►│   提醒计划       ├───────►│  服药记录     │
└──────────────┘        └─────────────────┘        └──────────────┘
      id                      id                        id
      name (唯一)             medication_id ──┐          plan_id ──┐
      dosage                  remind_time     │          medication_name
      note                    repeat_daily    │          scheduled_at
      created_at              enabled         │          taken_at
                              note            │          status
                              created_at      │          created_at
                                              │
   ON DELETE CASCADE ◄───── 删药则删计划 ─────┘
   ON DELETE SET NULL ◄──── 删计划仍保留记录 ─────┘

┌────────────────┐
│ chat_message   │   对话历史（原 _global_history）
│ role           │   user / assistant
│ content        │
│ source         │   text / ocr / voice / mixed
│ created_at     │
└────────────────┘
```

### 关键设计取舍

1. **`dose_log.medication_name` 冗余存药品名**
   这是刻意的反范式：提醒计划被删掉之后，历史服药记录仍然要能显示"当时吃的是什么"，
   不能靠联表（那时计划已经不在了）。

2. **`dose_log.plan_id` 用 `ON DELETE SET NULL` 而不是级联删除**
   删掉一个有 30 天记录的提醒计划，不应该把 30 天的服药历史一起删掉。

3. **`medicine.name` 唯一 + 计划按 `(药品名, 时间)` 去重**
   `save_plans()` 是幂等的：重复保存同一批计划不会产生重复行，id 保持不变。

4. **用 `String` 存状态而不是 MySQL `ENUM`**
   以后想加 `postponed`（推迟）之类的状态，改代码即可，不用 `ALTER TABLE`。

---

## 三、环境准备

### 1. 建库建账号（用管理员账号执行一次）

```sql
CREATE DATABASE IF NOT EXISTS pill_reminder
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

CREATE USER IF NOT EXISTS 'dev_app'@'localhost' IDENTIFIED BY '你的密码';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, INDEX, REFERENCES
  ON pill_reminder.* TO 'dev_app'@'localhost';
FLUSH PRIVILEGES;
```

> 为什么不用 root：程序里长期持有 root 密码，等于任何能读到 `.env` 的进程都能删库。
> `dev_app` 只有这一个库的权限，出事影响面小。

### 2. 配 `.env`

在仓库根的 `.env` 里加：

```ini
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=dev_app
DB_PASSWORD=你的密码
DB_NAME=pill_reminder
DB_ECHO=0
```

`.env` 已经在 `.gitignore` 里，不会被推到 GitHub。

### 3. 建表

```bash
# 在仓库根目录执行
python -m zhiyao.db.init_db          # 建表
python -m zhiyao.db.init_db --demo   # 建表 + 演示数据
python -m zhiyao.db.init_db --check  # 只检查连接
```

也可以直接导入 `sql/schema.sql`（纯 DDL，方便交作业/写报告）。

---

## 四、代码结构

```
zhiyao/db/
├── __init__.py    对外导出
├── base.py        引擎、会话、session_scope()、ping()
├── models.py      4 张表的 ORM 定义
├── repo.py        仓储层：所有增删改查都在这里
└── init_db.py     初始化脚本（命令行入口）
```

分层原则：**上层只调用 `repo`，不碰 SQL 和 Session。**

`session_scope()` 统一处理事务：

```python
with session_scope() as session:
    session.add(obj)
# 正常结束自动 commit，抛异常自动 rollback，最后一定 close
```

---

## 五、接入点

| 位置 | 改动 |
|---|---|
| `zhiyao/reminder/alarm.py` | 新增 `on_fire` 回调参数，闹钟一响就写 `dose_log` |
| `zhiyao/cli.py` | 启动时 `_restore_alarms()` 恢复计划；设置闹钟后 `save_plans()` 落库；新增菜单 7 查看服药记录 |
| `zhiyao/ai/chat.py` | 每轮问答写 `chat_message`；启动时从库里恢复最近 20 条上下文；`clear_history()` 同时清库 |
| `zhiyao/web/app.py` | 新增 11 个 REST 接口；启动时自动装载闹钟 |
| `zhiyao/web/static/index.html` | 新增同步层：进角色时拉 `/api/today`，增删改后整批回写，打卡写 `dose_log` |

### 前端同步策略

`index.html` 里新增了一个 `DB` 状态对象和几个函数：

| 函数 | 触发时机 | 作用 |
|---|---|---|
| `dbRefreshAll()` | 登录后进入角色 | 拉今天的计划 + 服药记录，整体刷新界面 |
| `dbPushPlans()` | 新增 / 删除 / 修改提醒后 | 把当前列表整批 `POST /api/plans`，再拉回来拿最新 plan id |
| `dbCheckin(item)` | 点「已服药」 | `POST /api/checkin` 写一条 `dose_log` |
| `dbLoadHistory()` | 进入角色 / 打卡后 | `GET /api/logs` 填充历史列表 |

**降级策略**：任一接口失败就置 `DB.online = false`，界面自动退回 `localStorage`，
只在统计栏显示「💾 仅本机」，功能不中断。连上时显示「☁️ 已存数据库」。

> 注意：`localStorage` 仍然保留，作用从「数据源」降级为「离线缓存」。

**容错**：所有数据库调用都包了 try/except。**MySQL 没启动时程序照常运行**，
只是退化成原来的内存模式，并打印警告——不会因为数据库挂了整个应用起不来。

---

## 六、REST 接口

服务启动后访问 `http://localhost:8000/docs` 可以看到自动生成的交互式文档。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/today` | **网页端主接口**：今天的计划 + 每条是否已服药 |
| POST | `/api/checkin` | **网页端打卡**：`{"plan_id": 7}`，写 `dose_log` |
| GET | `/api/plans?active_only=false` | 查询提醒计划 |
| POST | `/api/plans` | 批量保存（覆盖式，未出现的旧计划会删除） |
| PATCH | `/api/plans/{id}` | 启用 / 停用 |
| DELETE | `/api/plans/{id}` | 删除计划 |
| GET | `/api/logs?limit=50` | 查询服药记录 |
| POST | `/api/logs/{id}/taken` | 标记为已服药 |
| GET | `/api/history?limit=50` | 查询对话历史 |
| DELETE | `/api/history` | 清空对话历史 |
| GET | `/api/stats` | 各表行数汇总 |

示例：

```bash
curl -X POST http://localhost:8000/api/plans \
  -H "Content-Type: application/json" \
  -d '[{"time":"08:00","medication":"阿莫西林 1粒","note":"饭后"}]'
```

---

## 七、自测

```bash
# 在仓库根目录执行

# 只测数据库层
python tests/test_db_smoke.py

# 数据库层 + HTTP 接口（需先启动网页版）
python -m zhiyao.web.app
python tests/test_db_smoke.py --http --base http://127.0.0.1:8000
```

全部通过会打印 `[PASS] 全部通过`。

---

## 八、常见问题

**Q: 报 `Access denied for user 'dev_app'`**
A: `.env` 里的密码和建账号时设的不一致，或者账号只建在了 `localhost` 但程序连的是 `127.0.0.1`
（MySQL 里这两个是不同的 host 记录，两个都要建）。

**Q: 报 `Unknown database 'pill_reminder'`**
A: 库还没建，跑一下第三节的 `CREATE DATABASE`。

**Q: 中文变成问号**
A: 连接串必须带 `?charset=utf8mb4`，`base.py` 里已经带了；手动用客户端时记得 `--default-character-set=utf8mb4`。

**Q: 控制台报 `UnicodeEncodeError: 'gbk' codec`**
A: Windows 控制台默认 GBK，输出 emoji 会崩。临时解决：`chcp 65001` 或设 `PYTHONIOENCODING=utf-8`。
`init_db.py` 已经刻意只用 ASCII 标记，不会有这个问题。
