# KarenBot

> 可长期运行的本地角色聊天智能体，支持人格、长期记忆、工具调用与 QQ/Telegram 接入。

KarenBot 从 [Debata_Agent](https://github.com/binglang001/Debata_Agent) 项目演进而来，如今是一个独立的 v2 统一发行版。

它是一个可以长期运行在个人电脑或服务器上的角色聊天框架：大语言模型、人格设定、长期记忆、QQ/Telegram 接入、工具调用和可视化控制台统一在同一个运行时中。角色因此不再只是「一问一答」——它会记住你们的对话，在合适的时候调用工具、查阅知识库、发送图片，也能在群聊中参与话题，并随着相处逐步积累自己的上下文。

项目采用本地部署：聊天记录、人格、密钥和知识库都保存在你的机器上，模型请求只发送给你配置的提供商。

- 当前应用版本：[**v2.1.0-alpha**](https://github.com/CN-BI5UNF/KarenBot/releases/tag/v2.1.0-alpha)
- 官方安装器：[**v2.0.0-alpha**](https://github.com/CN-BI5UNF/KarenBot-Installer/releases/tag/v2.0.0-alpha)
- 支持平台：Windows 10/11 x64、Linux（x64 / arm64）
- 两种界面：原生 **GTK4 GUI** / 浏览器 **WebUI**
- 许可证：Apache-2.0

> v2 是统一发行版：后端与所选前端成套发布、成套更新，也可以在更新页只更新其中一个组件。`v2.1.0-alpha` 虽已是当前最新版本，但仍属 alpha 预览版，接口与数据格式可能继续调整；升级前请先备份。

[English README](README_EN.md)

---

## 目录

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
- [贡献](#贡献)
- [许可证](#许可证)

---

## KarenBot 是什么

KarenBot 由三个组件构成，可以按需组合：

| 组件 | 作用 |
|---|---|
| **Backend** | 核心运行时：人格 Agent、记忆、工具、适配器与控制 API |
| **GUI** | 原生 GTK4 / libadwaita 桌面控制台 |
| **WebUI** | 浏览器控制台；默认只监听本机，开启局域网访问后可用手机或平板打开 |

两个前端共用同一套后端控制面，所以配置、状态和功能保持一致。只装其中一个，或者两个都装，都可以。

它适合这些场景：

- 想要一个有长期记忆、人格稳定的私人 AI 角色；
- 想把角色接进 QQ 群或 Telegram，让它参与日常聊天；
- 希望角色能搜索、识图、语音、查知识库、管理群聊；
- 需要在本机或小型服务器上长期运行，数据完全由自己掌握；
- 喜欢通过插件和自定义人格扩展玩法。

## 主要功能

### 角色与记忆

- **多人格**：内置默认人格，也可以创建、导入自己的角色；每个人格拥有独立设定、知识和聊天上下文。
- **长期记忆**：对话历史、重要记忆、RAG 检索和归档存储，角色能够跨会话记住信息。
- **人格工作状态**：角色可以进入「工作」状态，临时切换到更适合执行任务的工具档位。
- **知识与黑话**：按人格维护知识条目、群聊黑话和设定，彼此隔离。
- **角色形象**：支持多张角色图片、预览图和图片发送。

### 聊天平台

NapCat 是 QQ/OneBot 11 生态中的一种协议端，并不是 KarenBot 唯一支持的平台。当前协议目录如下：

| 接入方式 | 状态 | 说明 |
|---|---|---|
| **OneBot 11** | 可用 | 兼容 NapCat、LLOneBot、Lagrange、go-cqhttp 等实现；支持正向/反向 WebSocket、HTTP API 和 HTTP POST Webhook。 |
| **Telegram Bot API** | Beta | 支持长轮询和 Webhook，可接入私聊、群组和 Topic；真实环境下的长期回归仍在完善。 |
| **QQ 官方 Bot API v2** | 规划中 | 协议文档和配置契约已准备，当前版本尚未提供可用适配器。 |
| **Satori v1** | 规划中 | 计划通过 Satori 服务端桥接 Discord、Telegram、飞书等平台，当前版本尚未提供可用适配器。 |

OneBot 11 适配器提供严格标准模式（`onebot11`）和 NapCat 扩展兼容模式（`napcat`）；当协议端不支持某些扩展能力时，KarenBot 会自动降级。

- **结构化消息**：文本、@、引用、图片、语音、视频、文件、表情、合并转发等统一为消息段。
- **群聊控制**：黑白名单、群触发规则、群聊接收选择与群管工具。

### 模型与工具

- 支持 OpenAI 兼容接口、Anthropic、Google Gemini 等提供商；
- 模型按人格绑定，主模型、视觉模型、Embedding、TTS 可以分别配置；
- 内置消息发送、群管理、搜索、识图、语音、知识库、RAG 记忆等工具；
- 可选受控 Docker 容器与编码 Agent 模式；
- 插件系统同时支持后端插件和前端模块扩展。

### 外部程序托管

KarenBot 启动时可以顺带拉起 NapCat、SnowLuma、代理等依赖程序：

- 自定义名称、可执行文件、参数、工作目录和环境变量；
- 端口探测：若端口已有服务在监听，则跳过启动，并且不会终止已有进程；
- 可配置自动重启；
- 「随 KarenBot 关闭」只会停止由 KarenBot 成功拉起的进程；
- 某个程序启动失败只记录错误并提醒，不影响 KarenBot 主程序。

### 两种界面

**GUI**：原生 GTK4 窗口，适合桌面长期使用。

- 总览、对话、记忆、人格、知识、黑话、模型、日志、容器、存储、黑白名单、群聊触发、设置；
- 主题、字体缩放、渲染回退；
- 通过本机回环 HTTP + 随机令牌连接后端，不暴露公网。

**WebUI**：浏览器访问，适合服务器、手机和平板。

- 页面和设置与 GUI 对齐；
- 登录令牌、Hash 路由；
- 局域网内可直接用浏览器打开；
- 文件以浏览器下载和内嵌预览为主。

### 运行与更新

- v2 使用 **KarenBot 统一发行版**：后端 + 当前前端成套更新；
- 更新前逐文件备份，失败整体回滚；
- 只覆盖程序文件，`data/`、`personas/`、`plugins/`、`config.yaml` 等用户数据保持不动；
- 支持手动选择 Pre-release，并给出明确的风险提示。

## 安装

推荐使用官方 **[KarenBot Installer v2.0.0-alpha](https://github.com/CN-BI5UNF/KarenBot-Installer/releases/tag/v2.0.0-alpha)**。安装器与应用分开发布；下文的 Linux 命令固定安装应用 `v2.1.0-alpha`。安装器会下载、校验并组装所需组件，Windows GUI 则使用预构建的便携包。

### Windows 10/11（x64）

1. 下载安装器 `v2.0.0-alpha`：

   [KarenBot-Installer.exe](https://github.com/CN-BI5UNF/KarenBot-Installer/releases/download/v2.0.0-alpha/KarenBot-Installer.exe)

2. 双击即可运行，不需要预先安装 Python。遇到 SmartScreen 的「未知发布者」提示时，先确认文件来自官方 Release，再选择「更多信息 → 仍要运行」。
3. 把安装目录设为可写、简短的纯英文路径（默认 `C:\KarenBot`），并选择要安装 **GUI** 还是 **WebUI**。
4. 安装来源选择 **在线安装**，等待下载、校验和安装完成。
5. 完成后从桌面快捷方式或开始菜单启动即可。

Windows 原生 GUI 由安装器额外下载 GTK4 便携运行包，无需自行配置 GTK；该包内置的应用版本取决于打包时间，如果希望使用 `v2.1.0-alpha`，可以在安装完成后到「设置 → 更新」中切换。Windows 版 WebUI 会按需获取便携 Python，并生成一个用浏览器打开的启动入口。

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

如果不想走菜单，也可以在同一终端直接传入参数，把应用版本固定为 `v2.1.0-alpha`：

```bash
# WebUI
bash install.sh --online --frontend webui --tag v2.1.0-alpha --dir ~/.local/opt/karenbot

# 原生 GUI
bash install.sh --online --frontend gui --tag v2.1.0-alpha --dir ~/.local/opt/karenbot
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

1. 根据 `--tag` 或主仓库的 Release feed 解析统一发行版清单（`modules.json`），Linux 与 Windows WebUI 都走这条路径；
2. 下载**后端 + 所选前端**；Windows GUI 则下载预构建的便携应用包；
3. 按照清单逐项核对大小与 SHA256（Windows GUI 使用 `SHA256SUMS.txt`）；
4. 解压资产并组装出应用目录；
5. 从主仓库补上默认人格；
6. 创建虚拟环境并安装 Python 依赖（Windows 便携包无需此步）；
7. 生成启动脚本、快捷方式与卸载信息。

安装目录中的 `data/` 属于运行数据，升级不会删除，卸载时也可以选择保留。

## 第一次启动

首次打开会进入配置向导，一般只需要完成三件事：

### 1. 配置模型提供商

填入 API 地址、API Key 与模型名。OpenAI 兼容接口、Anthropic、Gemini 都可以，也支持中转站和本地兼容服务。

密钥会加密存储，不会出现在普通配置文件里。

### 2. 接入聊天平台

**QQ / OneBot 11**

先准备好 NapCat、LLOneBot、Lagrange 或 go-cqhttp 等 OneBot 11 实现，再回到 KarenBot 配置连接方式：

- 正向 WebSocket：填入协议端地址；
- 反向 WebSocket：让协议端主动连到 KarenBot；
- HTTP API / Webhook：按协议端文档填写地址、端口与鉴权信息。

也可以把 NapCat 加入「外部程序」列表，让 KarenBot 启动时一并拉起。

**Telegram**

在 BotFather 中创建 Bot，把拿到的 Token 填入 KarenBot 的 Telegram 适配器。

### 3. 选择或创建人格

KarenBot 自带默认人格；也可以在「人格」页面新建角色，写好设定、开场白、知识与形象，再绑定到对应的聊天账号。

配置完成后启动 Runtime，进入对话页就能开始聊天。

## 运行方式

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

### Headless / 服务器

后端可以无界面运行，适合长期部署在服务器上；参数说明见 `main.py --help` 与 `docs/`。

## 系统要求

| 项目 | 要求 |
|---|---|
| Windows | Windows 10/11 x64；原生 GUI 使用便携 GTK4 |
| Linux | x64 / arm64；GUI 需要 GTK4 + libadwaita + PyGObject |
| Python | 3.10+（源码运行与开发；安装器自带运行环境） |
| 内存 | 建议 2 GB 以上；运行本地模型需另行预留内存 |
| 磁盘 | GUI 约 1.2 GB，WebUI 约 400 MB（含依赖与缓存余量） |
| 网络 | 安装/更新需访问 GitHub；模型请求需访问所配置的提供商 |

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
python scripts/verify_modules.py --tag v2.1.0-alpha

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

发布流程、资产契约与 submodule 校验方式：

- [`docs/distribution.md`](docs/distribution.md)
- [`scripts/build_release_assets.py`](scripts/build_release_assets.py)
- [`.github/workflows/release.yml`](.github/workflows/release.yml)

## 更新

### v2 用户

在 GUI/WebUI 的「设置 → 更新」中检查 KarenBot 统一发行版。

- 默认后端与当前前端一起更新，也可以只更新后端或只更新当前前端；
- 只更新前端时不必重启后端（GUI 需完全退出后重开，WebUI 刷新页面即可）；只更新后端时则必须重启；
- 稳定版会自动提示，Pre-release 必须手动选择并确认风险；
- 更新前会把每个文件备份到 `data/module_backups/`；
- 用户数据、人格、插件与配置不会被覆盖。

> 只更新一个组件时，两端版本可能不一致；若遇到接口报错，请把另一个组件也更新，或选择「重新安装全部」。

### 0.1.x 用户

先安装过渡版，再升级到 v2：

1. 后端 `v0.1.11-alpha.1`；
2. GUI/WebUI `v0.1.1-alpha.2`；
3. 重启应用；
4. 在更新页手动选择最新 v2 发行版（当前为 `v2.1.0-alpha`）。

详见 [`docs/transition.md`](docs/transition.md)。

### 1.0.x 用户

旧的「后端 + WebUI 绑定」发行版已不再维护。请先备份数据，再按新流程重新安装；旧版本仍保留在本仓库，并已归档到私有仓库 `CN-BI5UNF/Debata-Refactor`。

## 数据、安全与备份

- 运行数据默认位于安装目录的 `data/`；配置、密钥、人格、日志与插件同样由用户目录管理。
- `config.yaml` 可能含有敏感配置；`secrets.enc` 与 `secrets.key` 用于加密密钥，请勿分享。
- 控制 API 默认要求令牌，应只监听本机或可信局域网，切勿直接暴露到公网。
- 更新器只改动程序文件，不会删除用户数据；即便如此，升级前仍建议备份：
  - `data/`
  - `personas/`
  - `plugins/`
  - `config.yaml`
  - `secrets.*`
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

**尚未接入 QQ/Telegram 时可以启动吗？**

可以。`v2.0.1-alpha.1` 起，没有任何启用渠道时 Runtime 会以无渠道模式启动，模型、人格、记忆与本地功能都可正常使用；之后启用渠道会自动恢复收发。

**更新后需要重启吗？**

后端更新后需重启后端；GUI 更新后需完全退出再打开；WebUI 更新后刷新页面。

## 版本说明

| 版本 | 状态 |
|---|---|
| `v2.1.0-alpha` | 当前最新版本（安全审计修复、跨平台稳定性和容器导出加固） |
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
