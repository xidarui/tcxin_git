# 过程稿归档

这里的四份文档是项目开发早期的需求与实施计划，**属于历史记录，内容已过时**：

- `plans/` 两份：当时给 AI 编码代理的分步实施计划
- `specs/` 两份：当时的需求描述

保留它们只是为了追溯「为什么这么设计」。文档里的路径（`myPythonProject/`、`pill_reminder/`、
`app.py`、`main.py`）都是重构**之前**的目录结构，现在实际对应：

| 文档里写的 | 现在的位置 |
|---|---|
| `myPythonProject/` | 仓库根目录 |
| `pill_reminder/` | `zhiyao/` |
| `pill_reminder/main.py` | `zhiyao/cli.py` |
| `pill_reminder/db/` | `zhiyao/db/` |
| `app.py` | `zhiyao/web/app.py` |
| `index.html` | `zhiyao/web/static/index.html` |
| `picture.jpg` | `assets/samples/picture.jpg` |

看当前有效的说明请直接读 `README.md` 和 `docs/DATABASE.md`。
不需要溯源的话，整个 `docs/archive/` 目录可以安全删除。
