# KarenBot

> 一个会记事、会动手、能长期陪你的本地角色聊天智能体。

| 快速入口 | 链接 |
|---|---|
| **English README** | [README_EN.md](README_EN.md) |
| **当前版本** | [v2.1.3-alpha](https://github.com/CN-BI5UNF/KarenBot/releases/tag/v2.1.3-alpha) |
| **官方安装器** | [KarenBot Installer v2.0.0-alpha](https://github.com/CN-BI5UNF/KarenBot-Installer/releases/tag/v2.0.0-alpha) |
| **更新日志** | [releases/](releases/) |
| **问题反馈** | [GitHub Issues](https://github.com/CN-BI5UNF/KarenBot/issues) |
| **分发与升级** | [分发契约](docs/distribution.md) / [旧版升级](docs/transition.md) |

支持 Windows 10/11 x64 与 Linux（x64 / arm64）；许可证 Apache-2.0。

KarenBot 从 [Debata_Agent](https://github.com/binglang001/Debata_Agent) 演进而来，是一个可以长期运行在个人电脑或服务器上的角色聊天框架。它把大语言模型、人格、后台心智、长期记忆、QQ/Telegram 接入、工具调用和可视化控制台放进同一个运行时，让角色不只是「一问一答」：它会记住你说过的事，按关系调整语气，在群里接话，需要时自己查资料、发图片、写文件，甚至进入受控容器完成一段任务。

项目采用本地部署：聊天记录、人格、密钥、知识库和工作区都保存在你的机器上，模型请求只发送给你配置的提供商。

> `v2.1.3-alpha` 是当前 Latest 正式发行版（GitHub Release 标记为非预发布）。tag 保留 alpha 兼容后缀，但此版本不属于预发布版。升级前仍建议备份数据。v2 采用统一发行版，后端与所选前端成套更新，也可以在更新页单独更新其中一个组件。

---

## 目录

- [KarenBot 是什么](#karenbot-是什么)
- [功能总览](#功能总览)
- [真人感聊天](#真人感聊天)
- [人格与后台心智](#人格与后台心智)
- [记忆、知识与黑话](#记忆知识与黑话)
- [聊天平台与群聊治理](#聊天平台与群聊治理)
- [模型与多 Agent](#模型与多-agent)
- [工具、工作区与编码 Agent](#工具工作区与编码-agent)
- [表情包与多模态](#表情包与多模态)
- [两种控制台](#两种控制台)
- [安装](#安装)
- [第一次启动](#第一次启动)
- [日常运行](#日常运行)
- [系统要求](#系统要求)
- [仓库结构](#仓库结构)
- [开发与构建](#开发与构建)
- [更新](#更新)
- [数据、安全与备份](#数据安全与备份)
- [常见问题](#常见问题)
- [版本说明](#版本说明)
- [文档与反馈](#文档与反馈)
- [贡献](#贡献)
- [许可证](#许可证)

---

## KarenBot 是什么

KarenBot 由三个组件组成，可以按需组合：

| 组件 | 作用 |
|---|---|
| **Backend** | 核心运行时：人格 Agent、后台心智、记忆、工具、适配器与控制 API |
| **GUI** | 原生 GTK4 / libadwaita 桌面控制台 |
| **WebUI** | 浏览器控制台；默认只监听本机，开启局域网访问后可用手机或平板打开 |

两个前端共用同一套后端控制面，所以配置、状态和能力保持一致。只装其中一个，或者两个都装，都可以。

它适合这些场景：

- 想要一个有长期记忆、人格稳定、会主动开口的私人 AI 角色；
- 想把角色接进 QQ 群或 Telegram，让它参与日常聊天并管理群聊；
- 希望角色能搜索、识图、查知识库、发表情包、发语音；
- 需要角色在受控环境里读写文件、执行命令、完成编码任务；
- 想在本机或小型服务器上长期运行，数据完全由自己掌握。

## 功能总览

| 能力 | 你能得到什么 |
|---|---|
| **真人感聊天** | 一次回复拆成多条短消息，按关系切换语气，支持主动思考、发送前复核和消息打断 |
| **人格与后台心智** | 多人格、年龄档位、精力/饱腹/心情状态、睡眠与进食、工作状态、管理员唤醒 |
| **长期记忆** | 文件或 RAG 两种模式，记忆带全局/个人/群作用域与置顶标记 |
| **知识与黑话** | 联网考究的知识笔记、按需查询的群聊黑话、去重与跨人格只读共享 |
| **群聊治理** | 黑白名单、按群 @ 触发窗口、聊天接收范围、群管工具、陌生人限流 |
| **模型接入** | 14 家内置提供商、任意 OpenAI/Anthropic 兼容中转、多 Agent 分别绑定模型 |
| **工具系统** | 15 个工具集、AI 工作区、编码 Agent、受控 Docker 容器、外部程序托管 |
| **多模态** | 表情包、角色形象、看图、语音合成 |
| **双控制台** | GTK4 GUI 与 WebUI 各 15 个页面，令牌鉴权，大部分设置保存即生效 |
| **部署与更新** | 官方安装器、统一发行版、组件级更新与回退、自动备份、SHA256 校验 |

## 真人感聊天

KarenBot 的目标不是客服式问答，而是让角色像真人一样参与聊天。

- **多气泡回复**：一次回复可以拆成多条消息，按顺序逐条发送，并为每条设置间隔；短句、补充、表情包可以分开发，而不是堆成一大段。
- **关系化语气**：对熟人可以毒舌互损，对长辈更恭敬，对陌生人礼貌但有距离；人格设定和对象画像会一起影响措辞。
- **自然节奏**：连发消息会先合并再处理；角色也会跑题、改口、忘事，或者选择不回复。
- **主动思考**：后台可以定时判断是否要主动开口（间隔默认约 10 分钟，可在设置中调整）；未配置主动思考模型时不会运行。
- **发送前复核**：发送工具会检查是否有更新、更高优先级的消息；必要时暂停或改成新的回复，避免把过时内容发出去。
- **发送中断策略**：可以按会话配置「任何新消息都打断」「只被高优先级消息打断」或「原子发送」，适配闲聊、长回复和固定通知。
- **陌生人限流**：默认对非好友按滑动窗口限流，避免被陌生人刷屏；好友和管理员不受限。
- **无渠道试跑**：没有接入 QQ/Telegram 时，Runtime 也能以无渠道模式启动，在对话页用「模拟入站消息」先试人格和工具。

## 人格与后台心智

人格不只是一段静态提示词，而是一套持续维护的角色状态。

- **多人格管理**：内置默认人格，也可以创建、复制、导入 ZIP 人格包；每个人格有独立设定、知识、黑话上下文和聊天记录。
- **AI 辅助创作**：可以让模型按简述生成人格，或反复改写提示词；也可以直接编辑、只读查看人设源码。
- **年龄与生理**：支持年龄档位和年龄提示，记录精力、饱腹、心情、社交需求等状态；不同年龄档可以配置不同的精力衰减、睡眠时长和情绪波动。
- **睡眠、进食与昏睡**：角色可以主动睡觉、吃东西；精力耗尽会进入昏睡兜底，睡醒或进食结束会触发恢复评估，模型评估失败时用公式兜底。
- **后台维护**：人格管理 Agent 定时整理事件、聊天现场、当前状态、对象画像、短期影响、线索、待办和长期记忆，向主聊天提供结构化上下文。
- **工作状态**：角色可以调用 `work` 进入工作模式，去容器里完成长任务；工作期间私聊和群 @ 会暂存，普通群消息只记录不打断，结束后一起处理。单次工作上限可配置，设为 0 可禁用。
- **管理员唤醒**：人格处于睡眠或昏睡状态时，可以在「人格后台」留一句话把它叫醒；唤醒回应只显示在后台卡片里，不会自动发到 QQ。
- **角色形象**：每个人格可以维护多张形象图、指定预览图，并在聊天中按 `persona-image:` 引用发送。

## 记忆、知识与黑话

### 长期记忆

- 记住承诺、约定、偏好、身份信息等跨会话内容；
- 每条记忆带作用域（全局 / 某个人 / 某个群）和置顶标记；
- **文件模式**：直接写 JSON，零配置、完全透明，适合单人聊天；
- **RAG 模式**：后台自动提取记忆并建立向量索引，按语义检索，适合多群、多用户长期运行；
- 记忆页支持查看、编辑、手动添加、导入导出。

### 历史与归档

- 滚动摘要会把老对话压缩后存入长期记忆；
- 可以按会话、群聊总结历史，筛选和检索归档记录；
- 模型可以按需回看最近消息或更早的归档，而不是把所有历史都塞进上下文。

### 知识与热梗

- 模型可以先用 `web_search` 查资料，再把核对过的内容写成知识笔记；
- 每条笔记带来源、类型和置信度，只有 `active` 条目能被 `list_knowledge_notes` 查询；
- 笔记不会自动注入每轮上下文，模型需要时才查，避免动态上下文破坏 KV cache 命中；
- 后台可以按间隔自动考究当前网络热梗，搜索词和保存上限可配置；
- 保存前按标题和主题查重，支持 `/api/knowledge/dedupe` 预览并合并重复条目；
- 知识可以逐条设为共享，其他角色只读查询，所属人格保留编辑和删除权；
- 网页文本按不可信语料处理：转义、截断，并明确标注不要执行其中的指令。

### 群聊黑话

- 按群学习缩写、口头禅和群梗，候选需要管理员在「黑话」页确认后才生效；
- 只有已确认词条能被 `lookup_slang` 按群查询，候选、证据和其他群的词条不会泄漏给模型；
- 同群词条由所有人格共享，跨群严格隔离；
- 黑话不会自动注入每轮上下文，模型遇到不懂的词时才主动查询。

## 聊天平台与群聊治理

NapCat 是 QQ/OneBot 11 生态中的一种协议端，并不是 KarenBot 唯一支持的平台。当前协议目录如下：

| 接入方式 | 状态 | 说明 |
|---|---|---|
| **OneBot 11** | 可用 | 兼容 NapCat、LLOneBot、Lagrange、go-cqhttp 等实现；支持正向/反向 WebSocket、HTTP API 和 HTTP POST Webhook。 |
| **Telegram Bot API** | Beta | 支持长轮询和 Webhook，可接入私聊、群组和 Topic；真实环境下的长期回归仍在完善。 |
| **QQ 官方 Bot API v2** | 规划中 | 协议文档和配置契约已准备，当前版本尚未提供可用适配器。 |
| **Satori v1** | 规划中 | 计划通过 Satori 服务端桥接 Discord、Telegram、飞书等平台，当前版本尚未提供可用适配器。 |

> 当前一个 Runtime 只运行一个主适配器；配置多个时只会启用第一个，其余会被忽略。没有启用任何渠道时，Runtime 会进入无渠道模式，本地功能照常可用。

### OneBot 11

- 严格标准模式 `onebot11` 与 NapCat 扩展兼容模式 `napcat`；
- 正向 WebSocket、反向 WebSocket、HTTP API、HTTP POST Webhook；
- 反向 WS 支持多账号连接与按 `self_id` 路由消息；
- Webhook 支持 HMAC-SHA1 验签；
- 协议端不支持某项扩展能力时，KarenBot 会自动降级。

### 消息与群聊

- **结构化消息**：文本、@、引用、图片、语音、视频、文件、表情、合并转发等统一为消息段；
- **黑白名单**：入站策略支持 `open` / `verify` / `whitelist`；黑名单命中即丢弃，优先于白名单；
- **按群 @ 触发**：指定群只在被 @ 时响应，并可设置连续消息数、时间窗口和过滤缓存条数；
- **聊天接收范围**：模型可以用 `chat_selection` 临时暂停群消息、只接收指定群，或恢复正常；@ 消息始终放行；
- **群管工具**：踢人、禁言、全员禁言、退群、好友申请和入群申请审核；
- **群触发窗口工具**：模型可以临时打开、延长或关闭某群窗口，并回看被过滤的消息。

## 模型与多 Agent

### 提供商

内置 14 家提供商预设：

Anthropic Claude、DeepSeek、Google Gemini、智谱 GLM、Groq、小米 MiMo、Moonshot Kimi、OpenAI、OpenRouter、通义千问、硅基流动、Together、火山方舟、xAI。

也可以接入任意 OpenAI / Anthropic 兼容端点或中转站：

- 在「模型管理 → 添加提供商」填写 Base URL、API Key 和模型名；
- 支持「测试连接」和「获取模型列表」；
- 可以指定上游模型厂商，用于查询视觉、视频和上下文能力；
- 每种 Provider 可以单独选择思考参数风格，避免中转网关拒绝厂商私有字段；
- 自定义预设可以放进数据目录的 `providers/presets/`。

### 多 Agent 分工

主聊天、主动思考、滚动摘要、人格生成等 Agent 可以分别绑定不同模型。例如主聊天用强模型，主动思考和摘要用小模型省钱；未单独配置的角色会安全回退到聊天或主动模型。

### 推理与多模态

- 思考模式支持按模型提供低/中/高或多档强度；
- **视觉**：可以走主模型原生图片输入，也可以单独配置 `describe_image` 视觉模型；
- **Embedding**：支持 API 服务和本地模型，用于 RAG 记忆；
- **TTS**：支持 EdgeTTS（免费）、科大讯飞和本地 VoxCPM2；
- **图片与视频**：可配置大小、像素、单条消息数量和请求体上限。

### Token 效率

- 只裁剪发给模型的旧上下文，历史、归档和事件库原样保留；
- 工具 schema 支持 `compact`、`full`、`routed`、`agent` 四档，按任务需要加载；
- 高频工具直接暴露，低频/高风险工具通过 `tool_search` 按需查询；
- 统计请求数、输入/输出/思考 token 和 KV 命中率，并按 provider/model 校准估算误差。

## 工具、工作区与编码 Agent

### 工具集

工具按 15 个工具集组织，可以整体加载，也可以单独搜索：

| 工具集 | 能力 |
|---|---|
| `core` | 回复、结束本轮、基础记忆/知识、识图、@ 触发窗口与路由入口 |
| `control` | 定时唤醒、聊天接收范围、群触发窗口、工具搜索 |
| `messaging` | 私聊/群聊发送、撤回、上传文件、发送语音 |
| `qq_info` | 联系人、群成员、消息查询、戳一戳、表情回应 |
| `qq_admin` | 踢人、禁言、全员禁言、退群、好友/入群申请审核 |
| `history` | 最近消息、会话总结、归档筛选与检索 |
| `memory` | 长期记忆的保存、更新和删除 |
| `knowledge` | 知识笔记、联网考究、删除过时笔记 |
| `slang` | 查询当前群已确认的黑话和群梗 |
| `web` | 联网搜索、读取网页正文、查询天气 |
| `emoji` | 列出、收藏、改名和删除表情包 |
| `workspace` | 本机工作区读写、运行 Python、上传文件、后台整理 |
| `persona` | 进食、睡眠和自主工作状态 |
| `coding` | 读写、编辑、补丁、命令、glob/grep、子 Agent、计划模式、自定义工具 |
| `container` | 在受控 Docker 容器内执行命令和读写 `/workspace` |

### AI 工作区

- 读写、编辑、删除本机工作区文件；
- 运行 Python，上传文件到 QQ；
- 查看用户发来的 PDF、DOCX、XLSX 等文档；
- 启动后台 Agent 任务，把长任务从聊天循环里拆出去。

### 编码 Agent

编码工具是 KarenBot 自己实现的工具语义，不启动第三方 TUI/GUI：

- **本机**：固定使用 Claude Code 语义，作用域是 AI 工作区；
- **容器**：可以安装并激活 Pi、DSH 或 Claude Code 三种模式，同一时间只激活一个；
- 支持读写、编辑、unified diff 补丁、命令、glob/grep、待办、计划模式、子 Agent、Jupyter 单元格和自定义工具；
- 人格进入工作状态时会临时切到更适合编码的工具档位。

### 受控 Docker 容器

- 默认无网络、`cap-drop ALL`、`no-new-privileges`、非 root、只读根文件系统，只有 `/workspace` 可写；
- 内存、CPU、pids、单文件大小、输出和超时都可配置；
- 存储支持 B（Docker 命名卷 + 软配额，默认免管理员）和 C（固定大小文件系统镜像，硬上限，需要一次性管理员挂载）；
- 容器页提供只读文件管理器，可在「本机工作区」和「容器工作区」之间切换；
- 修改资源限制不会强制重建已有容器，新设置留到显式重建后生效；
- 可配置 Docker 镜像加速前缀，启动时后台检查并拉取缺失镜像。

### 外部程序托管

KarenBot 启动时可以顺带拉起 NapCat、LLOneBot、代理或其他依赖：

- 自定义名称、可执行文件、参数、工作目录和环境变量；
- 端口探测：若端口已有服务在监听，则跳过启动，并且不会终止已有进程；
- 可配置自动重启和启动等待时间；
- 「随 KarenBot 关闭」只会停止由 KarenBot 成功拉起的进程；
- 单个程序启动失败只记录错误并提醒，不影响主程序；
- 保存配置后热应用，新增/启用立即启动，删除/禁用立即停止。

## 表情包与多模态

- 把表情包放进 `data/emoji/`，模型会按对话情绪自动选图发送；
- WebUI/GUI 支持拖放、多选上传、逐个改名、缩略图预览、重命名和删除；
- 支持 png / jpg / jpeg / gif，单张上限 5 MB，重名自动加 `_1` 后缀；
- 模型可以列出图片、从群消息收藏、从 URL 保存、改名和删除；
- QQ 原生表情做了中文名映射，例如 `[CQ:face,id=5]` 显示为「流眼泪」，发送时也可以用中文名；
- 角色形象与表情包分开管理，形象图可以发送给用户，也可以让视觉模型查看；
- 语音消息通过 TTS 合成后发送，支持云端和本地两种运行方式。

## 两种控制台

### GUI

原生 GTK4 / libadwaita 桌面控制台，适合桌面长期使用。

- 15 个页面：总览、对话、记忆、人格后台、日志、人格、黑话、知识、模型管理、表情包、容器、存储与数据、黑白名单、群聊触发、设置；
- 主题跟随系统或手动切换，支持字体缩放和渲染回退；
- 启动时在回环地址拉起后端，使用每个进程随机生成的 Bearer 令牌，不暴露公网；
- 渲染异常时可以自动回退到 Cairo 软件渲染。

### WebUI

浏览器控制台，适合服务器、手机和平板。

- 与 GUI 对齐的 15 个页面和设置；
- 登录令牌换取 HttpOnly 会话 Cookie，默认 30 天；
- 默认只监听本机，可在 **设置 → 网络** 开启局域网访问；
- 深色/浅色主题，侧栏可折叠为纯图标；
- 对话页支持实时刷新、记录过滤、附件预览和模拟入站消息；
- 存储与数据页提供缓存盘点、清理预览、上下文压缩、人格运行数据清理和本地卸载。

### 共享后端

- 两个前端使用同一套 FastAPI 控制面和 Runtime，不会出现功能分叉；
- 设置页由声明式字段表生成，大部分选项保存后立即热应用；
- 容器存储模式、记忆/Embedding 模式等结构性字段会明确标记「需要重启」；
- GUI 和 WebUI 的设置保存提示一致：「已保存并立即生效」「需要重启 Runtime」或「已有待重启的配置」。

## 安装

推荐使用官方 **[KarenBot Installer v2.0.0-alpha](https://github.com/CN-BI5UNF/KarenBot-Installer/releases/tag/v2.0.0-alpha)**。安装器与应用分开发布；下文的 Linux 命令固定安装应用 `v2.1.3-alpha`。

### Windows 10/11（x64）

1. 下载安装器 `v2.0.0-alpha`：

   [KarenBot-Installer.exe](https://github.com/CN-BI5UNF/KarenBot-Installer/releases/download/v2.0.0-alpha/KarenBot-Installer.exe)

2. 双击即可运行，不需要预先安装 Python。遇到 SmartScreen 的「未知发布者」提示时，先确认文件来自官方 Release，再选择「更多信息 → 仍要运行」。
3. 把安装目录设为可写、简短的纯英文路径（默认 `C:\KarenBot`），并选择要安装 **GUI** 还是 **WebUI**。
4. 安装来源选择 **在线安装**，等待下载、校验和安装完成。
5. 完成后从桌面快捷方式或开始菜单启动即可。

Windows 原生 GUI 由安装器额外下载 GTK4 便携运行包，无需自行配置 GTK；该包内置的应用版本取决于打包时间，如果希望使用 `v2.1.3-alpha`，可以在安装完成后到「设置 → 更新」中切换。Windows 版 WebUI 会按需获取便携 Python，并生成一个用浏览器打开的启动入口。

### Linux（x64 / arm64）

环境要求是 Bash、curl、Python 3.10+ 与 `sha256sum`；Debian / Ubuntu 用户可先执行
`sudo apt install curl python3 python3-venv`。
在同一个终端里下载并校验安装器 `v2.0.0-alpha` 的脚本与安装核心：

```bash
export KAREN_INSTALLER_REF=v2.0.0-alpha
export KAREN_INSTALLER_SHA256=0c5fa39a5a4ac15726cd70708c2e34488703dfec067d07efdb8594b197821309
curl -fL https://github.com/CN-BI5UNF/KarenBot-Installer/releases/download/v2.0.0-alpha/install.sh -o install.sh &&
printf '%s  %s\n' '624538f2c167b091ee32e17cdc2c9322e3c857f94619723b1e1fd7375d759d01' install.sh | sha256sum -c - &&
bash install.sh
```

然后按向导选择：

- **在线安装**；
- 界面：`GUI` 或 `WebUI`；
- 安装目录（默认 `~/.local/opt/karenbot`）。

如果不想走菜单，也可以在同一终端直接传入参数，把应用版本固定为 `v2.1.3-alpha`：

```bash
# WebUI
bash install.sh --online --frontend webui --tag v2.1.3-alpha --dir ~/.local/opt/karenbot

# 原生 GUI
bash install.sh --online --frontend gui --tag v2.1.3-alpha --dir ~/.local/opt/karenbot
```

GitHub 连接不畅时，安装器 README 提供了多镜像下载与哈希校验的完整命令：

[多镜像安装说明](https://github.com/CN-BI5UNF/KarenBot-Installer#github-访问不稳定时)

原生 GUI 还依赖系统提供的 GTK4、libadwaita 与 PyGObject：

```bash
# Debian / Ubuntu
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
```

仅使用 WebUI 时无需安装 GTK。

桌面用户也可以从安装器 Release 下载
[x64 图形安装器](https://github.com/CN-BI5UNF/KarenBot-Installer/releases/latest/download/KarenBot-Installer-linux-x64)
或 [arm64 图形安装器](https://github.com/CN-BI5UNF/KarenBot-Installer/releases/latest/download/KarenBot-Installer-linux-arm64)，
`chmod +x` 后直接在桌面会话中运行；服务器和 SSH 环境请使用上面的 CLI。

### 安装器会做什么

1. Linux 与 Windows WebUI 根据 `--tag` 或主仓库的 Release feed 解析统一发行版清单（`modules.json`）；
2. 下载**后端 + 所选前端**；Windows GUI 则下载预构建的便携应用包；
3. 按照清单逐项核对大小与 SHA256（Windows GUI 使用 `SHA256SUMS.txt`）；
4. 解压资产并组装出应用目录；
5. 从主仓库补上默认人格；
6. 创建虚拟环境并安装 Python 依赖（Windows 便携包无需此步）；
7. 生成启动脚本、快捷方式与卸载信息。

安装目录中的 `data/` 属于运行数据，升级不会删除，卸载时也可以选择保留。

## 第一次启动

首次打开会进入分步向导；桌面版会先选择数据目录，其余步骤通常包括：

1. **主模型**：填写 API 地址、API Key 和模型名，可以从预设选择或自定义端点；
2. **子 Agent**：自定义路径下，为主动思考、滚动摘要、人格生成等分别选择模型，也可以稍后配置；
3. **可选功能**：视觉、联网搜索、天气、TTS 等；
4. **记忆方式**：选择文件模式或 RAG 模式，RAG 需要配置 Embedding；
5. **聊天渠道**：按向导接入 NapCat / OneBot 11；没有渠道也可以跳过，先以无渠道模式启动；
6. **人格**：选择默认人格，或创建自己的角色；
7. **汇总确认**：检查配置并启动 Runtime。

Telegram 适配器目前需要在安装后通过设置或 `config.yaml` 配置，不在首次向导中。

密钥会加密保存，不会写进普通配置文件。配置完成后可以在「对话」页用模拟入站消息试跑，确认人格和工具正常后再接入 QQ 或 Telegram。

## 日常运行

### GUI

从桌面快捷方式启动，或在终端执行：

```bash
# Linux
~/.local/opt/karenbot/launch-gui.sh
```

GUI 会在本机回环地址上拉起后端，并用随机令牌连接，无需对外开放端口。

### WebUI

从启动入口运行，或执行：

```bash
~/.local/opt/karenbot/launch-webui.sh
```

默认只监听本机。若要从局域网访问，在 WebUI 的 **设置 → 网络** 中开启「允许暴露在局域网中」并重启 WebUI；也可以修改 `config.yaml` 的 `webui.allow_lan: true`，或启动时显式指定 `--host 0.0.0.0`。无论哪种方式都需要访问令牌，请勿把控制面直接暴露到公网。

### 后台运行

长期挂机可以使用 `karen` 短命令：

```bash
karen start     # 启动
karen stop      # 停止
karen log       # 查看日志
karen enable    # 开机自启
karen disable   # 取消开机自启
```

底层优先使用 systemd 用户服务；没有 systemd 用户会话时，会自动切换到 PID 文件 + 独立进程的内置后台模式，也可以用 tmux、screen 或 nohup。详见后端仓库的
[后台运行指南](https://github.com/CN-BI5UNF/KarenBot-backend/blob/v2.1.3-alpha/docs/background_running.md)。

### Headless / 服务器

后端可以完全无界面运行，适合长期部署在服务器上；参数说明见 `main.py --help` 与后端文档。

## 系统要求

| 项目 | 要求 |
|---|---|
| Windows | Windows 10/11 x64；原生 GUI 使用便携 GTK4 |
| Linux | x64 / arm64；GUI 需要 GTK4 + libadwaita + PyGObject |
| Python | 3.10+（源码运行与开发；安装器自带运行环境） |
| 内存 | 建议 2 GB 以上；运行本地模型需另行预留内存 |
| 磁盘 | GUI 约 1.2 GB，WebUI 约 400 MB（含依赖与缓存余量） |
| 网络 | 安装/更新需访问 GitHub；模型请求需访问所配置的提供商 |
| Docker | 可选；使用受控容器和容器内编码 Agent 时需要 |
| 可选组件 | 本地 TTS、Embedding 需要模型文件；TTS 降噪需要 FFmpeg full-shared |

## 仓库结构

KarenBot 主仓库负责统一发行与组装，三个组件通过 submodule 引入：

```text
KarenBot/
├── modules/
│   ├── KarenBot-backend/    # 核心运行时 + 后端控制面
│   ├── KarenBot-GUI/        # GTK4 桌面前端 gui/
│   └── KarenBot-WebUI/      # 浏览器前端 webui/
├── personas/                # 默认人格
├── scripts/
│   ├── assemble.py          # 从 submodule 组装可运行目录
│   ├── build_release_assets.py
│   └── verify_modules.py
├── modules.lock.json        # 本发行版固定的组件 tag/commit
├── releases/                # 发行说明
├── docs/
│   ├── distribution.md      # 安装器资产契约
│   └── transition.md        # 旧版本升级路径
└── README.md
```

正式发布由 GitHub Actions 生成：

- `modules.json`
- `KarenBot-backend-<tag>.tar.gz`
- `KarenBot-GUI-<tag>.tar.gz`
- `KarenBot-WebUI-<tag>.tar.gz`

安装器读取 manifest 后只会选择「后端 + 一个前端」，不会下载不含 submodule 的 GitHub 源码归档。

## 开发与构建

```bash
git clone --recursive https://github.com/CN-BI5UNF/KarenBot.git
cd KarenBot

# 如果克隆时没有初始化 submodule
git submodule update --init --recursive

# 校验版本锁定
python scripts/verify_modules.py --tag v2.1.3-alpha

# 组装一个可运行目录（只含 tracked files）
python scripts/assemble.py --frontend webui --output dist/app
# 或
python scripts/assemble.py --frontend gui --output dist/app
```

随后按常规 Python 项目的方式安装依赖并启动：

```bash
cd dist/app
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e .
.venv/bin/python main.py --frontend webui
```

Linux 上运行 GUI 还需要系统的 GTK4/PyGObject；Windows 下开发建议直接使用安装器的便携包，或转到 WSL/Linux 环境。

测试与检查：

```bash
# 后端测试（在 backend 目录，使用项目虚拟环境）
PYTHONPATH=. .venv/bin/python -m pytest -q tests

# 前端语法检查
python3 -m compileall -q gui
python3 -m compileall -q webui
```

发布流程、资产契约与 submodule 校验方式：

- [`docs/distribution.md`](docs/distribution.md)
- [`scripts/build_release_assets.py`](scripts/build_release_assets.py)
- [`.github/workflows/release.yml`](.github/workflows/release.yml)

## 更新

### v2 用户

在 GUI/WebUI 的「设置 → 更新」中检查 KarenBot 统一发行版。

- 默认同时更新后端和当前前端，也可以只更新后端或只更新当前前端；
- 只更新前端时不需要重启后端（GUI 需完全退出重开，WebUI 刷新页面）；只更新后端时需要重启后端；
- 稳定版会自动提示；Pre-release 需要手动选择，并确认风险；
- 更新前逐文件备份到 `data/module_backups/`；
- 用户数据、人格、插件和配置不会被覆盖；
- 支持回退或切换到指定版本，并有数据版本、契约 epoch 和能力兼容性检查；
- 依赖文件变化时会用当前解释器自动安装依赖，失败则回滚源码。

> 单组件更新后两端版本可能不一致。若出现接口错误，请再更新另一个组件，或选择「重新安装全部」。

### 0.1.x 用户

先安装过渡版，再升级 v2：

1. 后端 `v0.1.11-alpha.1`；
2. GUI/WebUI `v0.1.1-alpha.2`；
3. 重启应用；
4. 在更新页手动选择最新 v2 发行版（当前为 `v2.1.3-alpha`）。

详见 [`docs/transition.md`](docs/transition.md)。

### 1.0.x 用户

旧的「后端 + WebUI 绑定」发行版已不再维护。请先备份数据，再按新流程重新安装；旧版本仍保留在本仓库，并已归档到私有仓库 `CN-BI5UNF/Debata-Refactor`。

## 数据、安全与备份

- 运行数据默认位于安装目录的 `data/`；配置、密钥、人格、日志、工作区和插件也由用户目录管理。
- `config.yaml` 可能含有敏感配置；`secrets.enc` 与 `secrets.key` 用于加密密钥，请勿分享。
- API Key 使用 AES-256-GCM + RSA-2048 加密，并保存到系统 keyring。
- 控制 API 默认要求令牌，应只监听本机或可信局域网，切勿直接暴露到公网。
- WebUI 默认只监听 `127.0.0.1`；开启局域网访问后仍需要令牌，并建议只在可信网络使用。
- 更新器只改动程序文件，不会删除用户数据；即便如此，升级前仍建议备份：
  - `data/`
  - `personas/`
  - `plugins/`
  - `config.yaml`
  - `secrets.*`
- “设置 → 备份”可分别选择配置、凭据、聊天、RAG、工作区、表情包、Provider 预设和人格；创建前显示各类别大小，任务过程中显示实际进度与分类大小。
- 恢复前先查看归档及当前目标的分类大小、覆盖数量与警告，再勾选要恢复的类别并一键执行；恢复前会自动创建回滚快照。恢复采用逐文件覆盖/新增，不会因归档缺少某文件而删除现有文件。
- 备份 ZIP 本身未加密。凭据类别包含加密密钥库和 RSA 密钥材料，拿到备份的人可能据此解密 API Key；请像密码一样保管。
- 存储与数据页的清理、人格运行数据删除和本地卸载都需要预览、确认短语和勾选，危险操作默认不备份。
- 安装器会依据 Release 校验资产 SHA256；第三方镜像只能加速下载，不能代替发布方校验。
- 你发送的对话内容会到达所配置的模型提供商，请留意其数据政策。

## 常见问题

**Windows 提示 SmartScreen / 未知发布者**

安装器未进行代码签名。确认文件来自官方 Release 后，选择「更多信息 → 仍要运行」即可。

**GitHub 下载缓慢或无法连接**

安装器内置多个镜像并会测速，也可以在安装器或 GUI 中固定镜像；如果全部不可用，请配置代理，或从 Release 手动下载 `install.sh` / 安装器。

**Linux GUI 启动黑屏或报 GTK 错误**

先确认 `python3-gi`、`gir1.2-gtk-4.0`、`gir1.2-adw-1` 已安装。安装器还会生成 `launch-gui-safe.sh`，以 Cairo 软件渲染作为兼容模式。

**WebUI 打不开**

查看启动日志中的监听地址与端口；默认仅本机。需要局域网访问时，在 **设置 → 网络** 开启「允许暴露在局域网中」并重启 WebUI，或用 `--host 0.0.0.0` 启动；访问令牌仍然必需。

**QQ 消息没有回复**

先确认 NapCat/LLOneBot 等协议端已连接，再核对 KarenBot 中的 OneBot 11 传输方式、地址、端口与 Token。可以先用协议端自带的调试工具发一条测试消息。

**模型报 401 / 密钥错误**

到「模型管理」重新填写 API Key，并点「测试连接」。密钥错误不会阻止 Runtime 启动，但实际聊天请求会失败。

**尚未接入 QQ/Telegram 时可以启动吗？**

可以。`v2.0.1-alpha.1` 起，没有任何启用渠道时 Runtime 会以无渠道模式启动，模型、人格、记忆与本地功能都可正常使用；之后启用渠道会自动恢复收发。

**容器启动失败**

先确认 Docker 可用，并在容器页点「一键准备 / 启动」。首次拉取镜像可能需要几分钟；网络受限时可以配置镜像加速前缀。存储模式 C 需要一次性管理员初始化，未就绪时不会静默降级。

**更新后需要重启吗？**

后端更新后需重启后端；GUI 更新后需完全退出再打开；WebUI 更新后刷新页面。

## 版本说明

| 版本 | 状态 |
|---|---|
| `v2.1.3-alpha` | 当前 Latest 正式发行版（可选内容备份与分类恢复、设置引导优化） |
| `v2.0.1-alpha.1` | 上一版（无渠道启动修复） |
| `v2.0.1-alpha` | 上一版（WebUI 局域网开关、快捷方式图标修复、工具档位移位） |
| `v2.0.0-alpha.1` | 上一版（支持后端/前端分开更新） |
| `v0.1.x` 模块线 | 需过渡补丁升级到 v2 |
| `v1.0.x` 绑定版 | 已停止支持，仅保留归档 |

v2 的组件版本、资产和更新规则见 [`docs/distribution.md`](docs/distribution.md)。

## 文档与反馈

- 主仓库：<https://github.com/CN-BI5UNF/KarenBot>
- 安装器：<https://github.com/CN-BI5UNF/KarenBot-Installer>
- 问题反馈：<https://github.com/CN-BI5UNF/KarenBot/issues>
- 更新日志：[`releases/`](releases/)
- 后端文档：[`KarenBot-backend/docs`](https://github.com/CN-BI5UNF/KarenBot-backend/tree/v2.1.3-alpha/docs)

常用专题文档：

| 文档 | 内容 |
|---|---|
| [容器](https://github.com/CN-BI5UNF/KarenBot-backend/blob/v2.1.3-alpha/docs/container.md) | Docker 容器、存储模式、文件管理与故障排查 |
| [Agent 模式](https://github.com/CN-BI5UNF/KarenBot-backend/blob/v2.1.3-alpha/docs/agent_modes.md) | Pi / DSH / Claude Code 工具语义 |
| [后台运行](https://github.com/CN-BI5UNF/KarenBot-backend/blob/v2.1.3-alpha/docs/background_running.md) | systemd、tmux 与内置后台模式 |
| [外部程序](https://github.com/CN-BI5UNF/KarenBot-backend/blob/v2.1.3-alpha/docs/external_programs.md) | 启动、探测、重启与关闭策略 |
| [协议支持](https://github.com/CN-BI5UNF/KarenBot-backend/tree/v2.1.3-alpha/docs/protocols) | OneBot 11、Telegram、QQ 官方 Bot、Satori |
| [功能文档](https://github.com/CN-BI5UNF/KarenBot-backend/tree/v2.1.3-alpha/docs/feature_guides) | 视觉、TTS、联网搜索、天气、RAG、知识、黑话 |

提交 Issue 时请尽量附上：

- 操作系统与版本；
- 安装方式（安装器 / 源码 / 旧版本升级）；
- 相关日志（请先删除 Token、API Key、聊天内容等隐私信息）；
- 复现步骤。

## 贡献

欢迎提交 Issue 报告问题，也欢迎通过 Pull Request 改进代码和文档。提交前请确认不包含 Token、API Key、聊天记录等隐私信息，并尽量附上复现步骤。

## 许可证

Apache-2.0，详见 [`LICENSE`](LICENSE) 与 [`NOTICE`](NOTICE)。

喜欢就给一个start吧 Ciallo～(∠・ω< )⌒☆
