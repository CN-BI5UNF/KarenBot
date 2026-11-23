# KarenBot

> 让虚拟角色真正“活”起来的本地 AI 聊天智能体。<br>
> A local AI chat agent that gives virtual characters memory, personality, and a life of their own.

本项目从 [Debata_Agent](https://github.com/binglang001/Debata_Agent) 项目改进而来，目前已发展为独立的 v2 统一发行版。

KarenBot 是一个可以长期运行在你自己电脑或服务器上的角色聊天框架：它把大语言模型、人格设定、长期记忆、QQ/Telegram 接入、工具调用和可视化控制台组合在一起，让角色不只是「一问一答」，而是能记住你、主动使用工具、参与群聊，并随着相处逐渐积累自己的上下文。

项目完全本地部署，模型请求直接发送给你配置的提供商；聊天记录、人格、密钥和知识库都保存在本机。

- 当前应用 Latest / Current application Latest：[**v2.1.0-alpha**](https://github.com/CN-BI5UNF/KarenBot/releases/tag/v2.1.0-alpha)
- 官方安装器 / Official installer：[**v2.0.0-alpha**](https://github.com/CN-BI5UNF/KarenBot-Installer/releases/tag/v2.0.0-alpha)
- 支持平台 / Supported systems：Windows 10/11 x64、Linux（x64 / arm64）
- 两种界面 / Frontends：原生 **GTK4 GUI** / 浏览器 **WebUI**
- 许可证 / License：Apache-2.0

> v2 是统一发行版，默认同时更新后端与当前前端；也可以在更新页只更新其中一个组件。v2.1.0-alpha 虽然是当前 Latest，仍属于 alpha 预览版，接口和数据格式可能变化，升级前请备份。

[简体中文](#中文) · [English](#english)

---

## 中文

### 目录

- [KarenBot 是什么](#karenbot-是什么)
- [主要功能](#主要功能)
- [安装](#安装)
- [第一次启动](#第一次启动)
- [运行方式](#运行方式)
- [系统要求](#系统要求)
- [仓库结构](#仓库结构)
- [开发与构建](#开发与构建)
- [更新](#更新)
- [数据、安全与备份](#数据安全与备份)
- [常见问题](#常见问题)
- [版本说明](#版本说明)
- [文档与反馈](#文档与反馈)
- [许可证](#许可证)

---

### KarenBot 是什么

KarenBot 由三部分组成：

| 组件 | 作用 |
|---|---|
| **Backend** | 核心运行时、人格 Agent、记忆、工具、适配器和控制 API |
| **GUI** | 原生 GTK4 / libadwaita 桌面控制台 |
| **WebUI** | 浏览器控制台，默认仅本机；可在设置中开启局域网访问后用手机/平板打开 |

两个前端共用同一套后端控制面，所以功能、配置和状态保持一致。你可以只安装其中一个，也可以两个都安装。

它适合这些场景：

- 想要一个**有长期记忆和人格**的私人 AI 角色；
- 把角色接入 QQ 群或 Telegram，参与日常聊天；
- 给角色配置搜索、识图、语音、知识库、群管等工具；
- 在本机或小型服务器上长期运行，数据完全由自己掌握；
- 用插件和自定义人格扩展自己的玩法。

---

### 主要功能

#### 角色与记忆

- **多人格系统**：内置默认人格，也可以创建、导入自己的角色；每个人格有独立设定、知识和聊天上下文。
- **长期记忆**：对话历史、重要记忆、RAG 检索和归档存储，角色可以跨会话记住信息。
- **人格工作状态**：角色可以进入「工作」状态，临时切换到更适合执行任务的工具档位。
- **知识与黑话**：维护角色知道的知识条目、群聊黑话和设定，按人格隔离。
- **角色形象**：支持多张角色图片、预览图和图片发送。

#### 聊天平台

NapCat 是 QQ/OneBot 11 生态中的一个协议端，不是 KarenBot 唯一支持的平台。当前协议目录如下：

| 接入方式 | 状态 | 说明 |
|---|---|---|
| **OneBot 11** | 可用 | 支持 NapCat、LLOneBot、Lagrange、go-cqhttp 及其他兼容实现；支持正向/反向 WebSocket、HTTP API 和 HTTP POST Webhook。 |
| **Telegram Bot API** | Beta | 支持长轮询和 Webhook，可接入私聊、群组和 Topic；真实环境的长期回归仍在完善。 |
| **QQ 官方 Bot API v2** | 规划中 | 协议文档和配置契约已准备，当前版本尚未提供可用适配器。 |
| **Satori v1** | 规划中 | 计划通过 Satori 服务端桥接 Discord、Telegram、飞书等平台，当前版本尚未提供可用适配器。 |

OneBot 11 适配器可以选择严格标准模式（`onebot11`），也可以选择带有 NapCat 扩展兼容能力的模式（`napcat`）。平台特有能力会根据协议端实际支持情况降级。

- **结构化消息**：文本、@、引用、图片、语音、视频、文件、表情、合并转发等统一消息段。
- **群聊控制**：黑白名单、群触发规则、群聊接收选择、群管工具。

#### 模型与工具

- 支持 OpenAI 兼容接口、Anthropic、Google Gemini 等提供商；
- 按人格绑定模型，支持主模型、视觉模型、Embedding、TTS 等分工；
- 内置消息发送、群管理、搜索、识图、语音、知识库、RAG 记忆等工具；
- 可选受控 Docker 容器和编码 Agent 模式；
- 插件系统：可以添加后端插件或新的前端模块。

#### 外部程序托管

KarenBot 可以在启动时拉起多个外部程序，例如 NapCat、SnowLuma、代理或其他依赖：

- 自定义名称、可执行文件、参数、工作目录和环境变量；
- 可配置端口探测：如果端口已有服务，就跳过启动且永不误杀；
- 可配置自动重启；
- 「随 KarenBot 关闭」只停止由 KarenBot 成功拉起的进程；
- 某个程序启动失败只记录错误并提醒，不影响 KarenBot 主程序。

#### 两种界面

**GUI**：原生 GTK4 窗口，适合桌面长期使用。

- 总览、对话、记忆、人格、知识、黑话、模型、日志、容器、存储、黑白名单、群聊触发、设置；
- 主题、字体缩放、渲染回退；
- 本地回环 HTTP + 随机令牌连接后端，不暴露公网。

**WebUI**：浏览器访问，适合服务器、手机和平板。

- 与 GUI 对齐的页面和设置；
- 登录令牌、Hash 路由；
- 局域网内可直接用浏览器打开；
- 文件以浏览器下载/内嵌预览为主。

#### 运行与更新

- v2 使用 **KarenBot 统一发行版**：后端 + 当前前端始终成套更新；
- 更新前逐个文件备份，失败整体回滚；
- 只覆盖程序文件，`data/`、`personas/`、`plugins/`、`config.yaml` 等用户数据不会被覆盖；
- 支持 Pre-release 手动选择，并给出明确风险提示。

---

### 安装

推荐使用官方 **[KarenBot Installer v2.0.0-alpha](https://github.com/CN-BI5UNF/KarenBot-Installer/releases/tag/v2.0.0-alpha)**。
安装器与 KarenBot 应用分别发布；当前应用 Latest 为 `v2.1.0-alpha`。
安装器会下载并校验所需的应用组件或 Windows GUI 便携包。

#### Windows 10/11（x64）

1. 下载安装器 `v2.0.0-alpha`：

   [KarenBot-Installer.exe](https://github.com/CN-BI5UNF/KarenBot-Installer/releases/download/v2.0.0-alpha/KarenBot-Installer.exe)

2. 双击运行，无需预装 Python。如果 SmartScreen 提示未知发布者，确认文件来自官方 Release 后选择「更多信息 → 仍要运行」。
3. 选择可写的纯英文短路径（默认系统盘的 `C:\KarenBot`），界面选择 **GUI** 或 **WebUI**。
4. 来源选择 **在线安装**，等待下载和校验完成。
5. 安装完成后从桌面 / 开始菜单启动。

Windows 原生 GUI 使用独立下载的 GTK4 便携包，不需要自己安装 GTK；包内应用版本
取决于该包的构建版本，如需 `v2.1.0-alpha`，可在安装完成后进入「设置 → 更新」选择。
Windows WebUI 按需下载便携 Python，并创建浏览器访问的启动入口。

#### Linux（x64 / arm64）

需要 Bash、curl、Python 3.10+ 和 `sha256sum`。Debian / Ubuntu 可先运行
`sudo apt install curl python3 python3-venv`。
在同一个终端下载并校验安装器 `v2.0.0-alpha` 的脚本与安装核心：

```bash
export KAREN_INSTALLER_REF=v2.0.0-alpha
export KAREN_INSTALLER_SHA256=0c5fa39a5a4ac15726cd70708c2e34488703dfec067d07efdb8594b197821309
curl -fL https://github.com/CN-BI5UNF/KarenBot-Installer/releases/download/v2.0.0-alpha/install.sh -o install.sh &&
printf '%s  %s\n' '624538f2c167b091ee32e17cdc2c9322e3c857f94619723b1e1fd7375d759d01' install.sh | sha256sum -c - &&
bash install.sh
```

然后按菜单选择：

- **在线安装**；
- 界面：`GUI` 或 `WebUI`；
- 安装目录（默认 `~/.local/opt/karenbot`）。

也可以在同一个终端直接传参，明确安装 KarenBot `v2.1.0-alpha`：

```bash
# WebUI
bash install.sh --online --frontend webui --tag v2.1.0-alpha --dir ~/.local/opt/karenbot

# 原生 GUI
bash install.sh --online --frontend gui --tag v2.1.0-alpha --dir ~/.local/opt/karenbot
```

GitHub 访问不稳定时，使用安装器 README 的多镜像下载与哈希校验命令：

[多镜像安装说明](https://github.com/CN-BI5UNF/KarenBot-Installer#github-访问不稳定时)

Linux 原生 GUI 需要系统安装 GTK4、libadwaita 和 PyGObject：

```bash
# Debian / Ubuntu
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
```

只使用 WebUI 则不需要 GTK。

Linux 桌面用户也可下载安装器 Release 中的
[x64 图形安装器](https://github.com/CN-BI5UNF/KarenBot-Installer/releases/latest/download/KarenBot-Installer-linux-x64)
或 [arm64 图形安装器](https://github.com/CN-BI5UNF/KarenBot-Installer/releases/latest/download/KarenBot-Installer-linux-arm64)，
执行 `chmod +x` 后在桌面会话中运行；服务器 / SSH 使用上面的 CLI。

#### 安装器会做什么

1. Linux / Windows WebUI 按 `--tag` 或主仓库 Release feed 解析统一发行版（`modules.json`）；
2. 下载 **后端 + 你选择的前端**；Windows GUI 下载预构建的便携应用包；
3. 按发行清单校验大小和 SHA256（Windows GUI 使用 `SHA256SUMS.txt`）；
4. 解压并组合成应用目录；
5. 从 KarenBot 主仓库补齐默认人格；
6. 创建虚拟环境、安装 Python 依赖（Windows 便携包跳过）；
7. 写入启动入口、快捷方式和卸载信息。

安装目录里的 `data/` 是运行数据，升级时不会删除。卸载时可以选择保留数据。

---

### 第一次启动

首次打开会进入配置向导，通常需要完成三件事：

#### 1. 配置模型提供商

填写你使用的 API 地址、API Key 和模型名。KarenBot 支持 OpenAI 兼容接口、Anthropic、Gemini 等；也可以接中转站或本地兼容服务。

密钥会加密保存，不会写进普通配置文件。

#### 2. 接入聊天平台

**QQ / OneBot 11**

先准备 NapCat、LLOneBot、Lagrange 或 go-cqhttp 等 OneBot 11 实现，然后在 KarenBot 中配置：

- 正向 WebSocket：填写协议端地址；
- 反向 WebSocket：让协议端连接 KarenBot；
- HTTP API / Webhook：按协议端文档填写地址、端口和鉴权。

也可以把 NapCat 配到「外部程序」列表里，让 KarenBot 启动时顺带拉起它。

**Telegram**

在 BotFather 创建 Bot，把 token 填进 KarenBot 的 Telegram 适配器即可。

#### 3. 选择或创建人格

KarenBot 自带默认人格。你可以在「人格」页面创建自己的角色，填写设定、开场白、知识和形象；然后把人格绑定到对应聊天账号。

完成后启动 Runtime，打开对话页即可开始聊天。

---

### 运行方式

#### GUI

从桌面快捷方式启动，或：

```bash
# Linux
~/.local/opt/karenbot/launch-gui.sh
```

GUI 会在本机回环地址启动后端，并用随机令牌连接；不需要额外开放端口。

#### WebUI

从启动入口运行，或：

```bash
~/.local/opt/karenbot/launch-webui.sh
```

默认只监听本机。需要在局域网访问时，打开 WebUI 的 **设置 → 网络**，
启用“允许暴露在局域网中”并重启 WebUI；也可以在 `config.yaml` 设置
`webui.allow_lan: true`，或启动时显式加 `--host 0.0.0.0`。开启后仍然需要
访问令牌，不要把控制面直接暴露到公网。

#### Headless / 服务器

后端支持无界面运行，适合长期挂在服务器上。具体参数见 `main.py --help` 和 `docs/`。

---

### 系统要求

| 项目 | 要求 |
|---|---|
| Windows | Windows 10/11 x64；原生 GUI 使用便携 GTK4 |
| Linux | x64 / arm64；GUI 需要 GTK4 + libadwaita + PyGObject |
| Python | 3.10+（开发/源码运行；安装器会处理运行环境） |
| 内存 | 建议 2 GB 以上；本地模型另算 |
| 磁盘 | GUI 约 1.2 GB，WebUI 约 400 MB（含依赖和缓存余量） |
| 网络 | 安装/更新需要访问 GitHub；模型请求需要访问你配置的提供商 |

---

### 仓库结构

KarenBot 主仓库是统一发行版与组装仓库，三个组件以 submodule 维护：

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

安装器按 manifest 选择后端 + 一个前端，不会直接下载不含 submodule 的 GitHub 源码归档。

---

### 开发与构建

```bash
git clone --recursive https://github.com/CN-BI5UNF/KarenBot.git
cd KarenBot

# 如果克隆时没有初始化 submodule
git submodule update --init --recursive

# 校验版本锁定
python scripts/verify_modules.py --tag v2.1.0-alpha

# 组装一个可运行目录（只含 tracked files）
python scripts/assemble.py --frontend webui --output dist/app
# 或
python scripts/assemble.py --frontend gui --output dist/app
```

然后按常规 Python 项目安装依赖并启动：

```bash
cd dist/app
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e .
.venv/bin/python main.py --frontend webui
```

GUI 在 Linux 上还需要系统 GTK4/PyGObject；Windows 开发请使用安装器的便携包或 WSL/Linux 环境。

发布流程、资产契约和 submodule 校验见：

- [`docs/distribution.md`](docs/distribution.md)
- [`scripts/build_release_assets.py`](scripts/build_release_assets.py)
- [`.github/workflows/release.yml`](.github/workflows/release.yml)

---

### 更新

#### v2 用户

在 GUI/WebUI 的「设置 → 更新」中检查 KarenBot 统一发行版。

- 默认同时更新后端和当前前端；也可以只更新后端或只更新当前前端；
- 只更新前端时不需要重启后端（GUI 需完全退出重开，WebUI 刷新页面）；只更新后端时需要重启后端；
- 稳定版会自动提示；Pre-release 需要手动选择，并确认风险；
- 更新前逐文件备份到 `data/module_backups/`；
- 用户数据、人格、插件和配置不会被覆盖。

> 单组件更新后两端版本可能不一致。若出现接口错误，请再更新另一个组件，或选择「重新安装全部」。

#### 0.1.x 用户

先安装过渡版，再升级 v2：

1. 后端 `v0.1.11-alpha.1`；
2. GUI/WebUI `v0.1.1-alpha.2`；
3. 重启应用；
4. 在更新页手动选择最新 v2 发行版（当前为 `v2.1.0-alpha`）。

详见 [`docs/transition.md`](docs/transition.md)。

#### 1.0.x 用户

旧的「后端 + WebUI 绑定」版本已放弃支持。请备份数据后按新安装流程迁移；旧发行版仍保留在本仓库，并已复制归档到私有仓库 `CN-BI5UNF/Debata-Refactor`。

---

### 数据、安全与备份

- 运行数据默认在安装目录的 `data/`；配置、密钥、人格、日志和插件也由用户目录管理。
- `config.yaml` 可能包含敏感配置；`secrets.enc` / `secrets.key` 用于加密密钥，不要分享。
- 控制 API 默认需要令牌，只应监听本机或可信局域网；不要直接暴露到公网。
- 更新器只写程序文件，不删除用户数据；但升级前仍建议备份：
  - `data/`
  - `personas/`
  - `plugins/`
  - `config.yaml`
  - `secrets.*`
- 安装器会校验 Release 资产的 SHA256；第三方镜像只能加速传输，不能替代发布方校验。
- 角色使用的模型提供商会收到你发送的对话内容；请阅读对应提供商的数据政策。

---

### 常见问题

**Windows 提示 SmartScreen / 未知发布者**

安装器未做代码签名。选择「更多信息 → 仍要运行」；只从官方 Release 下载。

**GitHub 下载很慢或连不上**

安装器内置多个镜像测速；也可以在安装器/GUI 中固定镜像。若全部失败，请配置代理，或从 Release 手动下载 `install.sh` / 安装器。

**Linux GUI 启动黑屏或报 GTK 错误**

确认已安装 `python3-gi`、`gir1.2-gtk-4.0`、`gir1.2-adw-1`。安装器还提供 `launch-gui-safe.sh` 兼容模式（Cairo 软件渲染）。

**WebUI 打不开**

确认启动日志中的监听地址和端口；默认只监听本机。局域网访问需要在
**设置 → 网络** 开启“允许暴露在局域网中”并重启 WebUI，或显式用
`--host 0.0.0.0` 启动；开启后仍需要访问令牌。

**QQ 没有反应**

先确认 NapCat/LLOneBot 等协议端已经连上，再检查 KarenBot 的 OneBot 11 传输方式、地址、端口和 token 是否一致。可以先用协议端的调试工具发送一条测试消息。

**更新后需要重启吗？**

后端更新后必须重启后端；GUI 前端更新后要完全退出并重新打开；WebUI 更新后刷新页面。

---

### 版本说明

| 版本 | 状态 |
|---|---|
| `v2.1.0-alpha` | 当前 Latest（安全审计修复、跨平台稳定性和容器导出加固） |
| `v2.0.1-alpha.1` | 上一版（无渠道启动修复） |
| `v2.0.1-alpha` | 上一版（WebUI 局域网开关、快捷方式图标修复、工具档位移位） |
| `v2.0.0-alpha.1` | 上一版（支持后端/前端分开更新） |
| `v0.1.x` 模块线 | 需过渡补丁升级到 v2 |
| `v1.0.x` 绑定版 | 已停止支持，仅保留归档 |

v2 的组件版本、资产和更新规则见 [`docs/distribution.md`](docs/distribution.md)。

---

### 文档与反馈

- 主仓库：<https://github.com/CN-BI5UNF/KarenBot>
- 安装器：<https://github.com/CN-BI5UNF/KarenBot-Installer>
- 问题反馈：<https://github.com/CN-BI5UNF/KarenBot/issues>
- 更新日志：[`releases/`](releases/)

提交 Issue 时请附上：

- 操作系统和版本；
- 安装方式（安装器 / 源码 / 旧版本升级）；
- 相关日志（注意先删除 token、API Key、聊天内容等隐私信息）；
- 复现步骤。

---

### 许可证

Apache-2.0，详见 [`LICENSE`](LICENSE) 与 [`NOTICE`](NOTICE)。

---

## English

### Overview

KarenBot is a chat-agent framework for running character-driven assistants on a local computer or server. It combines LLM providers, persona prompts, long-term memory, chat-platform adapters, tools, and GUI/WebUI controls so a character can remember conversations, use tools, and participate in group chats. Runtime data stays on the local machine by default; model requests go only to the providers you configure.

The project started from [Debata_Agent](https://github.com/binglang001/Debata_Agent) and is now an independent v2 unified distribution.

### Features

- **Personas and memory**: multiple personas, long-term memory, RAG retrieval, knowledge entries, group slang, and persona images.
- **Structured messages**: normalize text, mentions, replies, images, voice, video, files, reactions, and forwarded messages.
- **Models and tools**: OpenAI-compatible, Anthropic, and Google Gemini providers, plus search, vision, voice, knowledge-base, and group-management tools.
- **External programs**: manage protocol clients and other dependencies with port probing, optional auto-restart, and ownership-aware shutdown.
- **Plugins and containers**: extend the backend or frontend and optionally run controlled Docker/container coding agents.
- **Unified updates**: backend and selected frontend are assembled as one release; files are backed up before updates and restored on failure.

### Supported chat platforms and protocols

NapCat is one QQ/OneBot 11 implementation, not the only platform KarenBot supports. The protocol catalog in v2.1.0-alpha is:

| Integration | Status | Details |
|---|---|---|
| **OneBot 11** | Available | NapCat, LLOneBot, Lagrange, go-cqhttp, and other compatible implementations; forward/reverse WebSocket, HTTP API, and HTTP POST Webhook. |
| **Telegram Bot API** | Beta | Long polling and Webhook for private chats, groups, and Topics; long-term real-world regression is still being expanded. |
| **QQ Official Bot API v2** | Planned | Protocol documentation and configuration contracts exist, but no usable adapter is shipped in this version. |
| **Satori v1** | Planned | Intended to bridge Discord, Telegram, Feishu, and other platforms through a Satori server; no usable adapter is shipped in this version. |

The OneBot 11 adapter supports a strict standard mode (onebot11) and an extension-compatible NapCat mode (napcat). Platform-specific features are reduced when the connected implementation does not provide them.

### Components and frontends

| Component | Role |
|---|---|
| **Backend** | Runtime, persona agents, memory, tools, adapters, and control APIs. |
| **GUI** | Native GTK4/libadwaita desktop console. |
| **WebUI** | Browser console, local-only by default; enable LAN access to use it from a phone or tablet. |

Both frontends use the same backend control plane, so configuration and runtime state stay consistent. Install either frontend or both.

### Requirements

| Item | Requirement |
|---|---|
| Windows | Windows 10/11 x64; the installer supplies the GTK4 runtime for the GUI. |
| Linux | x64 or arm64; the GUI requires GTK4, libadwaita, and PyGObject. |
| Python | 3.10+ for source runs and development; the installer prepares its runtime. |
| Memory | 2 GB or more recommended; local models need additional memory. |
| Network | GitHub access for installation/updates and access to the configured model provider. |

WebUI does not require GTK. Linux ARM64 devices can run the WebUI; use the distribution's GTK4/PyGObject packages or choose WebUI when a desktop stack is unavailable.

### Installation

Use the official [KarenBot Installer v2.0.0-alpha](https://github.com/CN-BI5UNF/KarenBot-Installer/releases/tag/v2.0.0-alpha). The installer and application are released separately; the commands below pin application v2.1.0-alpha.

#### Windows 10/11 (x64)

1. Download KarenBot-Installer.exe from the [installer release](https://github.com/CN-BI5UNF/KarenBot-Installer/releases/tag/v2.0.0-alpha).
2. Run it, choose **GUI** or **WebUI**, and select online installation.
3. Choose a short writable directory such as C:/KarenBot and wait for download, verification, and installation to finish.
4. Launch KarenBot from the desktop or Start Menu.

The Windows GUI receives its GTK4 runtime in the portable bundle. If SmartScreen warns about an unknown publisher, verify that the file came from the official release first.

#### Linux (x64/arm64)

The CLI requires Bash, curl, Python 3.10+, and sha256sum. On Debian/Ubuntu:

~~~bash
sudo apt install curl python3 python3-venv
~~~

Download and verify the installer:

~~~bash
curl -fL https://github.com/CN-BI5UNF/KarenBot-Installer/releases/download/v2.0.0-alpha/install.sh -o install.sh &&
printf '%s  %s\n' '624538f2c167b091ee32e17cdc2c9322e3c857f94619723b1e1fd7375d759d01' install.sh | sha256sum -c - &&
KAREN_INSTALLER_REF=v2.0.0-alpha \
KAREN_INSTALLER_SHA256=0c5fa39a5a4ac15726cd70708c2e34488703dfec067d07efdb8594b197821309 \
bash install.sh --online --frontend webui --tag v2.1.0-alpha --dir ~/.local/opt/karenbot
~~~

Replace --frontend webui with --frontend gui for the native GUI. The Linux GUI also needs:

~~~bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
~~~

When GitHub access is unreliable, use the [installer README's mirror and verification instructions](https://github.com/CN-BI5UNF/KarenBot-Installer#github-访问不稳定时). Do not skip SHA256 verification.

The installer downloads the backend and selected frontend, verifies sizes and SHA256 values from the release manifest, creates the runtime environment, and preserves user data such as data/, personas/, plugins/, and configuration files.

### First run

1. **Configure a model provider** with its API URL, API key, and model name. OpenAI-compatible, Anthropic, Gemini, relay, and local-compatible services are supported.
2. **Configure a chat integration** by choosing OneBot 11 or Telegram. OneBot 11 can connect to NapCat, LLOneBot, Lagrange, go-cqhttp, and other implementations through forward/reverse WebSocket, HTTP API, or Webhook. Telegram uses the token created with BotFather.
3. **Choose or create a persona**, set its prompt, knowledge, greeting, and images, then bind it to the chat account.

Start the Runtime and open the conversation page when setup is complete.

### Running

The installer creates launchers. With the default installation directory:

~~~bash
# Native GUI
~/.local/opt/karenbot/launch-gui.sh

# WebUI
~/.local/opt/karenbot/launch-webui.sh
~~~

WebUI listens on 127.0.0.1 by default. To allow LAN access, enable **Settings → Network → Allow LAN access**, set webui.allow_lan: true, or pass --host 0.0.0.0, then restart. Keep the access token enabled and do not expose the control plane directly to the public Internet.

The backend also supports headless server and SSH deployments; see main.py --help and docs/ for details.

### Updates

Check the unified distribution from **Settings → Updates** in GUI/WebUI. The current Latest application release is v2.1.0-alpha.

- By default, update the backend and selected frontend together; either component can also be updated alone.
- Restart the backend after a backend update, fully reopen GUI after a GUI update, and refresh the page after a WebUI update.
- Files are backed up individually under data/module_backups/; personas, plugins, configuration, and runtime data are not overwritten.
- Alpha releases may still require manual selection. Back up data before upgrading.

### Repository layout

~~~text
KarenBot/
├── modules/
│   ├── KarenBot-backend/    # Runtime and backend control plane
│   ├── KarenBot-GUI/        # GTK4 desktop frontend
│   └── KarenBot-WebUI/      # Browser frontend
├── personas/                # Default personas
├── scripts/                 # Assembly, release, and verification scripts
├── modules.lock.json        # Locked component tags/commits
├── releases/                # Release notes
├── docs/                    # Distribution and migration docs
└── README.md
~~~

### Development and builds

~~~bash
git clone --recursive https://github.com/CN-BI5UNF/KarenBot.git
cd KarenBot
git submodule update --init --recursive

python scripts/verify_modules.py --tag v2.1.0-alpha
python scripts/assemble.py --frontend webui --output dist/app
# Or: python scripts/assemble.py --frontend gui --output dist/app
~~~

Run the assembled application with a regular Python environment:

~~~bash
cd dist/app
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e .
.venv/bin/python main.py --frontend webui
~~~

Before submitting changes, run:

~~~bash
python -m pytest -q tests
git diff --check
~~~

See [docs/distribution.md](docs/distribution.md) for release assets and the component READMEs/CHANGELOG.md for module-specific changes.

### Data, security, and backups

- Runtime data is stored under data/ by default; configuration, secrets, personas, logs, and plugins are user-managed.
- config.yaml, secrets.enc, and secrets.key may contain sensitive data. Do not commit or share them.
- The control API requires a token by default and should listen only on localhost or a trusted LAN.
- Back up data/, personas/, plugins/, config.yaml, and secrets.* before updates or uninstall.
- Mirrors can accelerate downloads but cannot replace SHA256 verification against official release metadata.
- Model providers receive the content sent to the model; review their data policies.

### FAQ

**QQ messages do not receive a reply.** Confirm that the OneBot 11 implementation is connected, then check adapter type, transport, address, port, and token. NapCat, LLOneBot, Lagrange, and go-cqhttp expose different extensions; use strict onebot11 mode when needed.

**Is Telegram stable?** The Telegram Bot API adapter is available but marked Beta in v2.1.0-alpha; platform coverage and long-running behavior may change.

**The Linux GUI fails to start.** Install python3-gi, gir1.2-gtk-4.0, and gir1.2-adw-1. On servers or ARM64 devices without a full desktop stack, use WebUI.

**WebUI cannot be opened.** Check the listening address and port in the startup log. It is local-only by default; LAN access must be enabled explicitly and should retain the access token.

### Releases

| Version | Status |
|---|---|
| v2.1.0-alpha | Current Latest; security hardening, cross-platform stability, and safer container exports. |
| v2.0.1-alpha.1 | Previous release; no-adapter startup fixes. |
| v2.0.1-alpha | Previous release; WebUI LAN switch and tool-profile fixes. |
| v2.0.0-alpha.1 | First v2 release with separate backend/frontend updates. |
| v1.0.x | Legacy bound release line; unsupported and kept for archival use. |

See [releases/v2.1.0-alpha.md](releases/v2.1.0-alpha.md) for the complete change list.

### Documentation and feedback

- Main repository: <https://github.com/CN-BI5UNF/KarenBot>
- Installer: <https://github.com/CN-BI5UNF/KarenBot-Installer>
- Issues: <https://github.com/CN-BI5UNF/KarenBot/issues>
- Distribution contract: [docs/distribution.md](docs/distribution.md)
- Migration guide: [docs/transition.md](docs/transition.md)

When filing an issue, include the operating system and version, installation method, relevant logs with tokens/API keys/chat content removed, and reproduction steps.

### License

KarenBot is released under the [Apache License 2.0](LICENSE). Upstream notices are preserved in [NOTICE](NOTICE).

---

喜欢就给一个start吧 Ciallo～(∠・ω< )⌒☆
