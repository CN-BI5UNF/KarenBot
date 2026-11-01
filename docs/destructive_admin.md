# 危险数据操作：人格清理与本地卸载

WebUI「存储与数据」页集中放置不可逆操作；人格页另有「清理运行数据」入口。
所有操作都先由后端生成影响预览，再要求勾选确认、输入确认短语，并带一次性
预览令牌和幂等键。前端弹窗只是提示，真正的确认在服务端完成。

## 人格运行数据清理

入口：人格页 →「清理运行数据」。人格定义保留，仍可切换和使用该人格。

删除：

- `DATA_DIR/memory/<persona>/`：聊天历史、归档、重要记忆、滚动摘要、事件、
  用量、人格状态，以及目录内的旧 JSON/SQLite 文件、备份和隔离清单；
- `DATA_DIR/vector/<persona>/`：RAG 向量库；
- `knowledge.json` 中该人格 `shared=false` 的私有知识条目。

保留：

- `personas/<persona>/` 人格定义、头像、提示词备份；
- 共享知识、群共享黑话；
- workspace、日志、表情包、模型、全局配置/密钥；
- 其他角色数据、备份库。

执行时会暂停 Runtime（如果正在运行），完成后自动恢复。清理当前人格时会创建
一个空的 `<persona>.db`，避免下次启动触发兼容门禁或旧数据导入。清理前会在
`maintenance/persona_cleanup/` 写入按人格哈希命名的标记，阻止全局
`logs/model_usage.jsonl` 把用量数据重新导入该人格。

可在弹窗中勾选「创建完整备份」；备份写到配置的备份目录（默认 `~/Karen_Backups/`），包含目标人格的 memory/vector 和私有知识。默认不备份，删除不可恢复。

## 本地完全卸载

入口：「存储与数据」→「检查影响并卸载」。会停止服务并删除：

- 项目源码、`.git`、`.venv`/`venv`、项目内数据目录和运行状态；
- 当前数据根、已知旧/新数据根；
- 程序识别的备份：默认 `~/Karen_Backups`、配置的备份目录、
  `~/Karen_Uninstall_Backups`；
- 启动器（`~/.local/bin/karen`、`~/.local/bin/debata`，仅当内容引用本项目）；
- systemd 用户 unit 及 enable 链接（仅当引用本项目）；
- `~/.config/karenbot.env` / `debata-agent.env`（存在时）。

明确保留：

- `~/Debata_BeiFen`、`~/debata-backups` 等开发备份；
- GitHub 远端、NapCat、Docker、系统 keyring；
- 卸载审计目录 `~/.local/state/karenbot/uninstall/`；
- 如果勾选可选备份，`~/Karen_Uninstall_Backups/<plan_id>/`。

可选备份使用现有备份服务生成用户数据包，另生成项目源码 zip（含 `.git` 和未提交
文件，排除 `.venv`、缓存和运行目录），放在 `~/Karen_Uninstall_Backups/<plan_id>/`；
如果该备份库本身是删除目标，助手会保留这个子目录。备份不是加密的，包含密钥材料；
未勾选时本机不会保留任何数据副本。

删除由复制到目标之外的 stdlib-only 助手执行。后端先返回任务并退出，助手等待
后端 PID 消失，复验目标 inode、备份哈希和路径边界，再按“启动项 → 备份库 →
数据根 → 项目源码”的顺序删除，并写审计 JSON/日志。WebUI 断开后无法再确认结果，
请保存返回的审计路径。

当前自动卸载仅支持 Linux 非 systemd 管理（含没有可用 systemd 用户 bus 的内置
后台模式）。systemd 用户/系统服务、Windows、macOS 会显示手动步骤，不生成可执行
预览。完整卸载后 GitHub 远端仍在；NapCat、Docker 等外部资源不会被修改。

## API

所有接口都需要 WebUI 鉴权，并额外要求 `X-Karen-Admin: 1` 与同源请求。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/admin/personas/{name}/cleanup/preview` | 生成人格清理影响预览 |
| POST | `/api/admin/personas/{name}/cleanup/execute` | 创建清理任务 |
| POST | `/api/admin/uninstall/preview` | 生成卸载预览/平台支持信息 |
| POST | `/api/admin/uninstall/execute` | 创建卸载任务并调度助手 |
| GET | `/api/admin/jobs?limit=20` | 最近的危险操作任务 |
| GET | `/api/admin/jobs/{job_id}` | 任务状态/结果 |
| POST | `/api/admin/jobs/{job_id}/cancel` | 在删除开始前请求取消 |

预览令牌只以 SHA-256 指纹存储；任务元数据保存在
`DATA_DIR/maintenance/admin.sqlite3`。执行请求不能携带任意文件路径。

## 限制与恢复

- 人格清理只覆盖当前实例；其他实例、迁移快照、外部备份不会自动清理。
- 工作区中直接由 AI 创建的文件不归属于某个人格；清理人格不会删除它们。
- 全量卸载不删除开发备份、keyring、NapCat、Docker、GitHub 和 shell 历史。
- 完全卸载是不可逆的；未勾选备份时没有本机恢复材料。
- 审计/还原信息在 `~/.local/state/karenbot/uninstall/`，其中不含消息正文或密钥。
