# KarenBot

> 让虚拟角色真正「活」起来的本地 AI 聊天智能体。

>本项目从binglang的https://github.com/binglang001/Debata_Agent 项目改进而来（虽然到现在几乎没啥关系了）

KarenBot 是一个可以长期运行在你自己电脑或服务器上的角色聊天框架：它把大语言模型、人格设定、长期记忆、QQ/Telegram 接入、工具调用和可视化控制台组合在一起，让角色不只是「一问一答」，而是能记住你、主动使用工具、参与群聊，并随着相处逐渐积累自己的上下文。

项目完全本地部署，模型请求直接发送给你配置的提供商；聊天记录、人格、密钥和知识库都保存在本机。

- 最新发行版：**v2.0.1-alpha.1**
- 支持平台：Windows 10/11 x64、Linux（x64 / arm64）
- 两种界面：原生 **GTK4 GUI** / 浏览器 **WebUI**
- 许可证：Apache-2.0

> v2 是统一发行版，默认同时更新后端与当前前端；也可以在更新页只更新其中一个组件。当前为 alpha 预览版，接口和数据格式仍可能变化，升级前请备份。

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
- [许可证](#许可证)

---

## KarenBot 是什么

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

## 主要功能

### 角色与记忆

- **多人格系统**：内置默认人格，也可以创建、导入自己的角色；每个人格有独立设定、知识和聊天上下文。
- **长期记忆**：对话历史、重要记忆、RAG 检索和归档存储，角色可以跨会话记住信息。
- **人格工作状态**：角色可以进入「工作」状态，临时切换到更适合执行任务的工具档位。
- **知识与黑话**：维护角色知道的知识条目、群聊黑话和设定，按人格隔离。
- **角色形象**：支持多张角色图片、预览图和图片发送。

### 聊天平台

- **QQ / OneBot 11**：支持 NapCat、LLOneBot、Lagrange、go-cqhttp 等实现。
  - 正向 / 反向 WebSocket；
  - HTTP API；
  - HTTP POST Webhook；
  - 多账号、Header/Query 鉴权、HMAC-SHA1 验签。
- **Telegram**：Bot API 长轮询 / Webhook，支持文本、图片、语音、视频、文件、引用、表情回应、撤回和 topic。
- **结构化消息**：文本、@、引用、图片、语音、视频、文件、表情、合并转发等统一消息段。
- **群聊控制**：黑白名单、群触发规则、群聊接收选择、群管工具。

### 模型与工具

- 支持 OpenAI 兼容接口、Anthropic、Google Gemini 等提供商；
- 按人格绑定模型，支持主模型、视觉模型、Embedding、TTS 等分工；
- 内置消息发送、群管理、搜索、识图、语音、知识库、RAG 记忆等工具；
- 可选受控 Docker 容器和编码 Agent 模式；
- 插件系统：可以添加后端插件或新的前端模块。

### 外部程序托管

KarenBot 可以在启动时拉起多个外部程序，例如 NapCat、SnowLuma、代理或其他依赖：

- 自定义名称、可执行文件、参数、工作目录和环境变量；
- 可配置端口探测：如果端口已有服务，就跳过启动且永不误杀；
- 可配置自动重启；
- 「随 KarenBot 关闭」只停止由 KarenBot 成功拉起的进程；
- 某个程序启动失败只记录错误并提醒，不影响 KarenBot 主程序。

### 两种界面

**GUI**：原生 GTK4 窗口，适合桌面长期使用。

- 总览、对话、记忆、人格、知识、黑话、模型、日志、容器、存储、黑白名单、群聊触发、设置；
- 主题、字体缩放、渲染回退；
- 本地回环 HTTP + 随机令牌连接后端，不暴露公网。

**WebUI**：浏览器访问，适合服务器、手机和平板。

- 与 GUI 对齐的页面和设置；
- 登录令牌、Hash 路由；
- 局域网内可直接用浏览器打开；
- 文件以浏览器下载/内嵌预览为主。

### 运行与更新

- v2 使用 **KarenBot 统一发行版**：后端 + 当前前端始终成套更新；
- 更新前逐个文件备份，失败整体回滚；
- 只覆盖程序文件，`data/`、`personas/`、`plugins/`、`config.yaml` 等用户数据不会被覆盖；
- 支持 Pre-release 手动选择，并给出明确风险提示。

---

## 安装

推荐使用官方安装器。安装器不内置应用包，会在线读取 KarenBot 主仓库的发行版清单，校验 SHA256 后组合安装。

### Windows 10/11（x64）

1. 打开安装器 Release：

   <https://github.com/CN-BI5UNF/KarenBot-Installer/releases>

2. 下载 `KarenBot-Installer.exe`：

   <https://github.com/CN-BI5UNF/KarenBot-Installer/releases/download/v1.1.3/KarenBot-Installer.exe>

3. 双击运行。如果 SmartScreen 提示未知发布者，选择「更多信息 → 仍要运行」。
4. 选择安装目录（默认 `C:\KarenBot`），界面选择 **GUI** 或 **WebUI**。
5. 来源选择 **在线安装**，等待下载和校验完成。
6. 安装完成后从桌面/开始菜单启动。

Windows 原生 GUI 使用预构建的 GTK4 便携运行时，不需要自己安装 GTK；WebUI 安装后会创建启动入口，用浏览器访问。

### Linux

最简单的安装方式是通过安装器的 `install.sh`：

```bash
curl -fL \
  https://github.com/CN-BI5UNF/KarenBot-Installer/releases/download/v1.1.3/install.sh \
  -o install.sh
KAREN_INSTALLER_REF=v1.1.3 bash install.sh
```

然后按菜单选择：

- **在线安装**；
- 界面：`GUI` 或 `WebUI`；
- 安装目录（默认 `~/.local/opt/karenbot`）。

也可以直接传参，跳过交互菜单：

```bash
# WebUI
KAREN_INSTALLER_REF=v1.1.3 bash install.sh --online --frontend webui --dir ~/.local/opt/karenbot

# 原生 GUI
KAREN_INSTALLER_REF=v1.1.3 bash install.sh --online --frontend gui --dir ~/.local/opt/karenbot
```

如果 `raw.githubusercontent.com` 访问不稳定，安装器 README 提供了多镜像一行式命令：

<https://github.com/CN-BI5UNF/KarenBot-Installer#linux-一行式安装cli>

Linux 原生 GUI 需要系统安装 GTK4、libadwaita 和 PyGObject：

```bash
# Debian / Ubuntu
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
```

只使用 WebUI 则不需要 GTK。

### 安装器会做什么

1. 解析 KarenBot 最新统一发行版（`modules.json`）；
2. 下载 **后端 + 你选择的前端** 组件包；
3. 校验大小和 SHA256；
4. 解压并组合成应用目录；
5. 从 KarenBot 主仓库补齐默认人格；
6. 创建虚拟环境、安装 Python 依赖（Windows 便携包跳过）；
7. 写入启动入口、快捷方式和卸载信息。

安装目录里的 `data/` 是运行数据，升级时不会删除。卸载时可以选择保留数据。

---

## 第一次启动

首次打开会进入配置向导，通常需要完成三件事：

### 1. 配置模型提供商

填写你使用的 API 地址、API Key 和模型名。KarenBot 支持 OpenAI 兼容接口、Anthropic、Gemini 等；也可以接中转站或本地兼容服务。

密钥会加密保存，不会写进普通配置文件。

### 2. 接入聊天平台

**QQ / OneBot 11**

先准备 NapCat、LLOneBot、Lagrange 或 go-cqhttp 等 OneBot 11 实现，然后在 KarenBot 中配置：

- 正向 WebSocket：填写协议端地址；
- 反向 WebSocket：让协议端连接 KarenBot；
- HTTP API / Webhook：按协议端文档填写地址、端口和鉴权。

也可以把 NapCat 配到「外部程序」列表里，让 KarenBot 启动时顺带拉起它。

**Telegram**

在 BotFather 创建 Bot，把 token 填进 KarenBot 的 Telegram 适配器即可。

### 3. 选择或创建人格

KarenBot 自带默认人格。你可以在「人格」页面创建自己的角色，填写设定、开场白、知识和形象；然后把人格绑定到对应聊天账号。

完成后启动 Runtime，打开对话页即可开始聊天。

---

## 运行方式

### GUI

从桌面快捷方式启动，或：

```bash
# Linux
~/.local/opt/karenbot/launch-gui.sh
```

GUI 会在本机回环地址启动后端，并用随机令牌连接；不需要额外开放端口。

### WebUI

从启动入口运行，或：

```bash
~/.local/opt/karenbot/launch-webui.sh
```

默认只监听本机。需要在局域网访问时，打开 WebUI 的 **设置 → 网络**，
启用“允许暴露在局域网中”并重启 WebUI；也可以在 `config.yaml` 设置
`webui.allow_lan: true`，或启动时显式加 `--host 0.0.0.0`。开启后仍然需要
访问令牌，不要把控制面直接暴露到公网。

### Headless / 服务器

后端支持无界面运行，适合长期挂在服务器上。具体参数见 `main.py --help` 和 `docs/`。

---

## 系统要求

| 项目 | 要求 |
|---|---|
| Windows | Windows 10/11 x64；原生 GUI 使用便携 GTK4 |
| Linux | x64 / arm64；GUI 需要 GTK4 + libadwaita + PyGObject |
| Python | 3.10+（开发/源码运行；安装器会处理运行环境） |
| 内存 | 建议 2 GB 以上；本地模型另算 |
| 磁盘 | GUI 约 1.2 GB，WebUI 约 400 MB（含依赖和缓存余量） |
| 网络 | 安装/更新需要访问 GitHub；模型请求需要访问你配置的提供商 |

---

## 仓库结构

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

## 开发与构建

```bash
git clone --recursive https://github.com/CN-BI5UNF/KarenBot.git
cd KarenBot

# 如果克隆时没有初始化 submodule
git submodule update --init --recursive

# 校验版本锁定
python scripts/verify_modules.py --tag v2.0.1-alpha.1

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

## 更新

### v2 用户

在 GUI/WebUI 的「设置 → 更新」中检查 KarenBot 统一发行版。

- 默认同时更新后端和当前前端；也可以只更新后端或只更新当前前端；
- 只更新前端时不需要重启后端（GUI 需完全退出重开，WebUI 刷新页面）；只更新后端时需要重启后端；
- 稳定版会自动提示；Pre-release 需要手动选择，并确认风险；
- 更新前逐文件备份到 `data/module_backups/`；
- 用户数据、人格、插件和配置不会被覆盖。

> 单组件更新后两端版本可能不一致。若出现接口错误，请再更新另一个组件，或选择「重新安装全部」。

### 0.1.x 用户

先安装过渡版，再升级 v2：

1. 后端 `v0.1.11-alpha.1`；
2. GUI/WebUI `v0.1.1-alpha.2`；
3. 重启应用；
4. 在更新页手动选择最新 v2 发行版（当前为 `v2.0.1-alpha.1`）。

详见 [`docs/transition.md`](docs/transition.md)。

### 1.0.x 用户

旧的「后端 + WebUI 绑定」版本已放弃支持。请备份数据后按新安装流程迁移；旧发行版仍保留在本仓库，并已复制归档到私有仓库 `CN-BI5UNF/Debata-Refactor`。

---

## 数据、安全与备份

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

## 常见问题

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

## 版本说明

| 版本 | 状态 |
|---|---|
| `v2.0.1-alpha.1` | 最新发行版（无渠道启动修复） |
| `v2.0.1-alpha` | 上一版（WebUI 局域网开关、快捷方式图标修复、工具档位移位） |
| `v2.0.0-alpha.1` | 上一版（支持后端/前端分开更新） |
| `v0.1.x` 模块线 | 需过渡补丁升级到 v2 |
| `v1.0.x` 绑定版 | 已停止支持，仅保留归档 |

v2 的组件版本、资产和更新规则见 [`docs/distribution.md`](docs/distribution.md)。

---

## 文档与反馈

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

## 许可证

Apache-2.0，详见 [`LICENSE`](LICENSE) 与 [`NOTICE`](NOTICE)。

---

喜欢就给一个start吧 Ciallo～(∠・ω< )⌒☆
