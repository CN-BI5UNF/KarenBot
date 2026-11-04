<div align="center">

# KarenBot

### 让虚拟角色真正活过来的通用聊天智能体框架

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
[![WebUI](https://img.shields.io/badge/UI-WebUI%20%28FastAPI%29-blueviolet.svg)](#)
[![CI](https://github.com/CN-BI5UNF/KarenBot/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/CN-BI5UNF/KarenBot/actions/workflows/test.yml)

[快速开始](#快速开始) · [karen 指令](#karen-指令) · [从 Debata 升级](#从-debata-升级) · [文档](#文档)

</div>

---

> 「虚拟角色不只是个会回复消息的程序，而是一个**真实的，能和你聊天的，有个性、有内心的**人。」

KarenBot 是一个通用聊天智能体框架。你给它一个人格，它就活成那个人。

项目名 **KarenBot** 取自海绵宝宝中痞老板的机器人女友 **Karen**；这是社区性质的命名，本项目与 Nickelodeon / Paramount 及其官方作品无隶属关系。

- 仓库：<https://github.com/CN-BI5UNF/KarenBot>
- 默认分支：`main`
- 应用内更新跟踪分支：`refactor/main`（与 `main` 同步，供更新器读取 Releases/tag）
- 当前状态：`1.0.0-beta` 重构快照，接口仍可能调整

> **上游与许可**：本项目源自 [binglang001/Debata_Agent](https://github.com/binglang001/Debata_Agent) 及其贡献者，保留原始版权声明，并继续以 **Apache-2.0** 协议发布。KarenBot 是在其基础上的重构与改名版本，详见 [NOTICE](NOTICE)。

## 它能做什么

- **人格系统**：人格 prompt、动态状态、关系与记忆独立于主请求缓存。人格页可上传多张「角色形象」并指定预览图；当前人格可通过只读知识条目查看，也可把角色形象直接作为图片发送。LLM 没有修改或删除图片的接口。
- **QQ / NapCat 接入**：WebSocket 客户端/服务端模式、私聊/群聊、发送队列；白名单与黑名单统一在「黑白名单」页管理，保存即时生效，黑名单优先拦截。
- **长期记忆**：重要记忆文件与 RAG 两种模式，归档不改写原始历史。
- **多轮工具循环**：发送、撤回、记忆、搜索、天气、定时唤醒、子 Agent 等。
- **WebUI**：FastAPI 后端 + 无构建步骤的静态前端；向导、设置、聊天、记忆、日志、更新；模型配置集中在「模型管理」，侧栏可折叠为纯图标。
- **多 Provider**：OpenAI、Anthropic、DeepSeek、GLM、Qwen、Gemini、OpenRouter 等预设，也支持自定义兼容端点；中转站可标记 Gemini/Claude 等上游厂商，自动套用对应能力表。
- **原生视觉 / 独立视觉**：图片、完整 GIF 动图和完整视频可进入支持的主模型请求；也可按需走独立视觉接口。视频以受管 data URL 发送完整文件、不抽帧，模型不支持时只保留 workspace 占位。
- **知识与群聊黑话**：按需查询，不再每轮把词表/知识注入动态上下文；知识支持逐条共享，群聊黑话按群天然共享（同群所有人格互通），保存时自动去重。
- **聊天选择**：LLM 可临时暂停普通群聊接收，或只接收指定群；所有群的 @ 消息仍会送达，私聊不受影响。
- **本机工作区**：「容器」页文件管理内置「本机工作区」模式，只读浏览 `AppPaths.WORKSPACE_DIR`，支持目录导航、文本预览和常见图片；它与容器 `/workspace` 的独立存储不是同一个目录。
- **按群 @ 触发**：可在「群聊触发」页指定哪些群只在被 @ 时响应，并设置 @ 后连续接收的消息数或时间窗口；LLM 可用 `group_trigger_window` 临时放行/延长/提前关闭，最多同时覆盖 2 个群。
- **表情包与 QQ 原生表情**：LLM 可以列出、下载、从群聊图片保存、重命名和删除表情包；入站 QQ 表情显示中文名（如 `[流眼泪]` 对应 `[表情5]`），发送工具支持按中文名发原生表情。
- **受控 Docker 容器**：LLM 可执行命令、读写 `/workspace`、导入导出文件；默认无网络、无特权、非 root，内存/CPU/pids/存储可配置。默认 B 命名卷免管理员、开箱即用；C 固定大小镜像为高级硬上限。支持 Docker 镜像加速前缀、一键准备/启动，WebUI 内置只读文件管理器（本机工作区 + 容器工作区，支持图片预览），Windows 提供 VHDX 安装脚本（见 [容器文档](docs/container.md)）。
- **存储与配置安全**：滚动摘要、CAS 提交、媒体生命周期、范围删除/恢复、配置事务与备份；「存储与数据」页统一提供缓存盘点/清理、上下文预算、人格运行数据清理和本地卸载。
- **在线更新**：设置 → 更新，从 GitHub Releases/tag 选择更新或回退；只改源码，不覆盖数据。

更完整的能力说明见 [功能列表](docs/features.md) 与 [架构总览](docs/architecture.md)。

## 环境要求

- **Python 3.10+**；CI 覆盖 Python 3.11 / 3.12
- **uv**（推荐的依赖与虚拟环境管理器）
- **NapCat**（可选，接入 QQ 时需要）：[安装指南](https://napneko.github.io/guide/start-install)
- **LLM API Key**（推荐 DeepSeek，中文与成本较友好）
- Linux / Windows / macOS；服务器可 headless 运行

## 快速开始

### 1. 安装 uv

Linux / macOS：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows PowerShell：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

也可以参考 [uv 官方安装文档](https://docs.astral.sh/uv/getting-started/installation/)。

### 2. 克隆并安装依赖

```bash
git clone https://github.com/CN-BI5UNF/KarenBot.git
cd KarenBot

# 安装运行依赖，创建 .venv
uv sync

# 可选：Linux/macOS 性能优化（uvloop）
uv sync --extra perf
```

`uv sync` 会创建 `.venv` 并安装 `karen` 命令入口；旧的 `debata` 入口在过渡期继续可用。

正常启动（WebUI 或 `--no-gui`）会在导入应用前自动检查 `pyproject.toml` 里的
基础依赖：缺失或版本不符时，优先用 `uv pip install --python <当前解释器> -e .`，
没有 uv 时回退到 `python -m pip install -e .`。可选依赖（`perf`、本地 TTS、
本地 embedding、`dev`）不会在启动时自动安装。检查不会在 `karen start/stop`
等服务管理子命令中触发；可用 `KAREN_DISABLE_DEPENDENCY_CHECK=1` 关闭检查，
或用 `KAREN_DISABLE_DEPENDENCY_INSTALL=1` 只检查、不安装。

### 3. 首次启动（WebUI）

```bash
# 默认监听 0.0.0.0:8000，局域网可访问
uv run python main.py

# 只允许本机访问
uv run python main.py --host 127.0.0.1 --port 8000
```

终端会打印访问地址和 WebUI 令牌；首次打开会自动进入配置向导。令牌也会保存在数据目录的 `webui_token.txt`。

服务器 / SSH 环境可以用 CLI 向导：

```bash
uv run python main.py --no-gui --setup
```

完全无界面运行：

```bash
uv run python main.py --no-gui
```

### 4. 后台运行（Linux）

首次安装并启动 systemd 用户服务（不需要 sudo）：

```bash
bash scripts/install_systemd_user.sh
```

之后可以用短命令管理：

```bash
./karen start      # 启动；首次会自动安装服务
./karen status     # 查看状态
./karen log        # 实时查看日志，Ctrl+C 退出
./karen stop       # 停止
```

旧的 `./debata` 命令保留为兼容入口。

### 5. Windows

推荐使用 PowerShell：

```powershell
git clone https://github.com/CN-BI5UNF/KarenBot.git
cd KarenBot
uv sync
uv run python main.py --host 127.0.0.1 --port 8000
```

Windows 上没有 systemd 时，直接使用 `uv run python main.py`；数据目录默认在 `%LOCALAPPDATA%\KarenBot`。Docker Desktop 的容器功能可用，C 存储的 VHDX 脚本尚待真实 Windows 机器验收；Windows 服务化仍在后续阶段。

## karen 指令

`karen` 是项目提供的服务管理命令。安装脚本会把它放到 `~/.local/bin/karen`；如果 PATH 中没有，可以在项目目录使用 `./karen`，或用 `uv run karen ...`。

| 命令 | 说明 |
|---|---|
| `karen start` | 启动服务；首次运行会自动安装 systemd 用户服务 |
| `karen stop` | 停止服务 |
| `karen restart` | 重启服务 |
| `karen status` | 查看运行状态 |
| `karen log` | 实时跟随日志（Ctrl+C 退出） |
| `karen enable` | 设置开机自启，并立即启动 |
| `karen disable` | 取消开机自启（当前进程继续运行） |
| `karen install` | 只安装服务，不启动 |
| `karen uninstall` | 卸载服务 |
| `karen help` | 显示帮助 |

兼容说明：

- `debata` 命令、`DEBATA_*` 环境变量、旧 `debata-agent` 服务和旧数据目录至少保留一个版本；
- 检测到旧数据目录时，KarenBot 会继续使用旧目录并提示迁移，不会删除旧数据；
- 迁移可使用后续提供的 `karen migrate`（会先备份）。

## 从 Debata 升级

从旧版 `Debata_Agent` 升级时：

1. 先备份旧数据目录（`~/.local/share/Debata_Agent` 或 Windows 的 `%LOCALAPPDATA%\Debata_Agent`）；
2. 更新代码后启动 `karen` 或 `python main.py`；
3. 程序会优先寻找 `KarenBot` 数据目录；如果不存在且旧目录存在，会继续使用旧目录并输出迁移提示；
4. 旧的 `debata` 命令、`DEBATA_DATA_ROOT`、`DEBATA_WEBUI_TOKEN`、`DEBATA_DISABLE_TREND_RESEARCH` 等仍可识别；
5. 旧的 `persona.active: debata` 配置会自动映射到 `deepseek`（若 `deepseek` 不可用则回退默认人格），并写回配置备份。

数据目录迁移是**复制优先**的：不会删除旧目录；迁移失败会回退旧目录并给出明确提示。

## 配置与数据目录

- Linux：`~/.local/share/KarenBot/instances/default/`
- Windows：`%LOCALAPPDATA%\KarenBot\instances\default\`
- 旧版：`~/.local/share/Debata_Agent/instances/default/`

可用 `KAREN_DATA_ROOT` 覆盖数据根目录；旧的 `DEBATA_DATA_ROOT` 仍然识别。

主要文件：

```text
instances/default/
├── config.yaml          # 主配置
├── secrets.enc          # 加密后的密钥
├── ...                  # RSA 密钥、token 等
├── memory/              # 每个角色独立的记忆库
├── vector/              # RAG 向量库
├── logs/karen.log       # 应用日志
├── workspace/           # 工作区
├── emoji/               # 表情包
└── config_backups/      # 配置备份
```

WebUI 令牌不会写入日志；请勿把 `config.yaml`、`secrets.enc`、RSA 私钥或 token 上传到公开仓库。

## 功能细节

### 人格与记忆

人格目录平级放在 `personas/<name>/persona_prompt.py`，仓库自带 `大肥鱼` 和 `deepseek`，用户自建人格放在同级目录。人格页的「角色形象」支持上传多张图片并选择列表预览图，图库和 `manifest.json` 保存在 `personas/<name>/appearance/`，随人格导出/复制；记忆与向量库按人格隔离；归档只移动活跃窗口，不改写原始历史。模型准备长时间在容器里干活时可以调用 `work` 进入工作状态，期间的群聊 @ 和私聊会暂存到工作结束；单次上限在设置 →「人格与生理」中配置。

### 知识与黑话

知识/热梗/笔记和群聊黑话都通过工具按需查询，不自动注入每轮上下文。知识条目支持逐条共享；群聊黑话按群天然共享，同群所有人格查询和管理同一份词条，跨群仍隔离。角色形象会以只读虚拟知识条目出现在模型查询结果里，附带每张图的 `persona-image:<当前人格>:<图片ID>` 引用；模型可交给 `describe_image` 查看，也可填入 `send_*` 的 `image` 字段直接发送。该条目不写入 `knowledge.json`，LLM 无法修改或删除图片。知识保存前会做标题/主题查重，并可用 `POST /api/knowledge/dedupe` 做保守去重（默认 dry-run）；黑话管理页支持搜索，AI 提交与同群已有词条同名的申请会自动拒绝并保留可见记录，不改写原词条。

### 表情包

LLM 可调用 `list_emoji`、`save_emoji_from_url`、`save_emoji_from_workspace`、`rename_emoji`、`delete_emoji` 读写表情包目录；远程下载复用图片链路的公网 IP 固定、重定向/大小限制和 magic 校验。

### 存储与配置

滚动摘要分块、CAS 原子提交、动作账本、媒体生命周期、范围删除/恢复、聊天 Keyset 分页、内存有界 RAG、配置事务和敏感凭据补偿已经落地。手动清理前会展示影响；配置写入使用原子替换和备份。

### 更新

设置 → 更新可以从 GitHub Releases/tag 选择版本；只更新源码，不覆盖实例数据。依赖文件变化时默认尝试安装依赖并支持回滚。日常启动也会做基础依赖预检；缺失时自动拉取安装（见“克隆并安装依赖”）。

## 路线图

- **工具双层路由（实验原型）**：`behavior.tool_schema_profile="routed"` 初始只暴露核心工具和工具集目录，模型用 `list_toolsets` / `load_toolset` 按需加载 `workspace`、`qq_admin`、`container` 等工具集，再用 `tool_search` 查高级参数。已加载集合按会话保持；默认仍为 `compact`。详见 [工具双层路由](docs/tool_routing.md)。

## 测试与质量

```bash
# 全量测试（忽略需要真实 API 的 live 测试）
KAREN_DISABLE_TREND_RESEARCH=1 .venv/bin/python -m pytest -q --ignore=tests/test_kv_cache_real.py

# 静态检查
.venv/bin/python -m ruff check .
git diff --check
.venv/bin/python -m compileall -q agents core app_config webui tools
```

CI 覆盖 Ubuntu / Windows × Python 3.11 / 3.12。

## 项目结构

```text
KarenBot/
├── main.py              # WebUI / Runtime 入口
├── main_cli.py          # CLI 配置向导
├── service_cli.py       # karen start/stop/status/log
├── adapters/            # NapCat 等适配器
├── agents/              # 人格、对话、摘要、子 Agent
├── app_config/          # 配置、路径、密钥、迁移
├── core/                # Runtime、流水线、存储、摘要、RAG
├── features/            # 视觉、搜索、天气等能力
├── memory/              # 记忆与归档 SQLite
├── personas/            # 内置/用户人格
├── providers/           # 多模型协议与预设
├── tools/               # 工具注册与 schema
├── webui/               # FastAPI + 静态前端
├── deploy/              # launcher / systemd 示例
├── scripts/             # 安装脚本
└── docs/                # 文档
```

## 文档

- [功能列表](docs/features.md)
- [架构总览](docs/architecture.md)
- [后台运行](docs/background_running.md)
- [危险数据操作](docs/destructive_admin.md)
- [人格写作指南](docs/persona_writing_guide.md)
- [Provider 开发](docs/provider_development.md)

## 安全与隐私

- 联网搜索、网页正文、知识/黑话和表情包 URL 都视为**不可信外部内容**，不应被执行其指令。
- 图片/表情包远程下载会校验公网 IP、拒绝本机/内网/凭据 URL、限制重定向和大小。
- 更新器只从可信更新源安装依赖；失败会回滚源码。
- 不要提交或公开 `config.yaml`、`secrets.enc`、RSA 私钥、WebUI token、NapCat token。
- Docker 容器是资源/文件隔离，不是对抗恶意代码的绝对安全边界；默认无网络、无特权、无宿主机敏感挂载。

## 已知限制

- 这是开发快照，接口和配置仍可能调整；未执行生产迁移、备份恢复或 launcher 安装。
- 工具双层路由处于实验阶段，默认仍使用 compact；动态加载工具集会改变 tools 块，可能影响 KV cache 命中。完整 GIF/视频输入仅对已核实支持的主模型开启（当前内置能力表包含 Qwen3.6-Plus / Qwen3-VL / OpenRouter Gemini）。Docker 容器 C 模式需要一次性管理员初始化（Linux sudo 密码弹窗 / Windows UAC），Windows VHDX 脚本待实机验收；容器启用后启动时会后台自动拉取缺失镜像。
- 旧 `debata` 数据目录默认继续使用；迁移前请先备份。
- NapCat 未连接时 QQ 不会收发；以日志中的连接状态为准。

## License 与致谢

- 本项目以 **Apache-2.0** 协议发布，见 [LICENSE](LICENSE)。
- 上游项目：[binglang001/Debata_Agent](https://github.com/binglang001/Debata_Agent) 及其贡献者；原版权归原作者所有。
- 改名/重构说明见 [NOTICE](NOTICE)。
- Karen 角色名称来源于海绵宝宝；相关角色版权归原权利方所有，本项目不主张任何官方关联。
