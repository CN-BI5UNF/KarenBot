# KarenBot

> A local AI chat agent that gives virtual characters memory, personality, and a life of their own.

[简体中文 README](README.md)

- Current application Latest: [v2.1.0-alpha](https://github.com/CN-BI5UNF/KarenBot/releases/tag/v2.1.0-alpha)
- Official installer: [v2.0.0-alpha](https://github.com/CN-BI5UNF/KarenBot-Installer/releases/tag/v2.0.0-alpha)
- Frontends: GTK4 GUI and WebUI
- License: Apache-2.0

---

## Overview

KarenBot is a chat-agent framework for running character-driven assistants on a local computer or server. It combines LLM providers, persona prompts, long-term memory, chat-platform adapters, tools, and GUI/WebUI controls so a character can remember conversations, use tools, and participate in group chats. Runtime data stays on the local machine by default; model requests go only to the providers you configure.

The project started from [Debata_Agent](https://github.com/binglang001/Debata_Agent) and is now an independent v2 unified distribution.

## Features

- **Personas and memory**: multiple personas, long-term memory, RAG retrieval, knowledge entries, group slang, and persona images.
- **Structured messages**: normalize text, mentions, replies, images, voice, video, files, reactions, and forwarded messages.
- **Models and tools**: OpenAI-compatible, Anthropic, and Google Gemini providers, plus search, vision, voice, knowledge-base, and group-management tools.
- **External programs**: manage protocol clients and other dependencies with port probing, optional auto-restart, and ownership-aware shutdown.
- **Plugins and containers**: extend the backend or frontend and optionally run controlled Docker/container coding agents.
- **Unified updates**: backend and selected frontend are assembled as one release; files are backed up before updates and restored on failure.

## Supported chat platforms and protocols

NapCat is one QQ/OneBot 11 implementation, not the only platform KarenBot supports. The protocol catalog in v2.1.0-alpha is:

| Integration | Status | Details |
|---|---|---|
| **OneBot 11** | Available | NapCat, LLOneBot, Lagrange, go-cqhttp, and other compatible implementations; forward/reverse WebSocket, HTTP API, and HTTP POST Webhook. |
| **Telegram Bot API** | Beta | Long polling and Webhook for private chats, groups, and Topics; long-term real-world regression is still being expanded. |
| **QQ Official Bot API v2** | Planned | Protocol documentation and configuration contracts exist, but no usable adapter is shipped in this version. |
| **Satori v1** | Planned | Intended to bridge Discord, Telegram, Feishu, and other platforms through a Satori server; no usable adapter is shipped in this version. |

The OneBot 11 adapter supports a strict standard mode (onebot11) and an extension-compatible NapCat mode (napcat). Platform-specific features are reduced when the connected implementation does not provide them.

## Components and frontends

| Component | Role |
|---|---|
| **Backend** | Runtime, persona agents, memory, tools, adapters, and control APIs. |
| **GUI** | Native GTK4/libadwaita desktop console. |
| **WebUI** | Browser console, local-only by default; enable LAN access to use it from a phone or tablet. |

Both frontends use the same backend control plane, so configuration and runtime state stay consistent. Install either frontend or both.

## Requirements

| Item | Requirement |
|---|---|
| Windows | Windows 10/11 x64; the installer supplies the GTK4 runtime for the GUI. |
| Linux | x64 or arm64; the GUI requires GTK4, libadwaita, and PyGObject. |
| Python | 3.10+ for source runs and development; the installer prepares its runtime. |
| Memory | 2 GB or more recommended; local models need additional memory. |
| Network | GitHub access for installation/updates and access to the configured model provider. |

WebUI does not require GTK. Linux ARM64 devices can run the WebUI; use the distribution's GTK4/PyGObject packages or choose WebUI when a desktop stack is unavailable.

## Installation

Use the official [KarenBot Installer v2.0.0-alpha](https://github.com/CN-BI5UNF/KarenBot-Installer/releases/tag/v2.0.0-alpha). The installer and application are released separately; the commands below pin application v2.1.0-alpha.

### Windows 10/11 (x64)

1. Download KarenBot-Installer.exe from the [installer release](https://github.com/CN-BI5UNF/KarenBot-Installer/releases/tag/v2.0.0-alpha).
2. Run it, choose **GUI** or **WebUI**, and select online installation.
3. Choose a short writable directory such as C:/KarenBot and wait for download, verification, and installation to finish.
4. Launch KarenBot from the desktop or Start Menu.

The Windows GUI receives its GTK4 runtime in the portable bundle. If SmartScreen warns about an unknown publisher, verify that the file came from the official release first.

### Linux (x64/arm64)

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

## First run

1. **Configure a model provider** with its API URL, API key, and model name. OpenAI-compatible, Anthropic, Gemini, relay, and local-compatible services are supported.
2. **Configure a chat integration** by choosing OneBot 11 or Telegram. OneBot 11 can connect to NapCat, LLOneBot, Lagrange, go-cqhttp, and other implementations through forward/reverse WebSocket, HTTP API, or Webhook. Telegram uses the token created with BotFather.
3. **Choose or create a persona**, set its prompt, knowledge, greeting, and images, then bind it to the chat account.

Start the Runtime and open the conversation page when setup is complete.

## Running

The installer creates launchers. With the default installation directory:

~~~bash
# Native GUI
~/.local/opt/karenbot/launch-gui.sh

# WebUI
~/.local/opt/karenbot/launch-webui.sh
~~~

WebUI listens on 127.0.0.1 by default. To allow LAN access, enable **Settings → Network → Allow LAN access**, set webui.allow_lan: true, or pass --host 0.0.0.0, then restart. Keep the access token enabled and do not expose the control plane directly to the public Internet.

The backend also supports headless server and SSH deployments; see main.py --help and docs/ for details.

## Updates

Check the unified distribution from **Settings → Updates** in GUI/WebUI. The current Latest application release is v2.1.0-alpha.

- By default, update the backend and selected frontend together; either component can also be updated alone.
- Restart the backend after a backend update, fully reopen GUI after a GUI update, and refresh the page after a WebUI update.
- Files are backed up individually under data/module_backups/; personas, plugins, configuration, and runtime data are not overwritten.
- Alpha releases may still require manual selection. Back up data before upgrading.

## Repository layout

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

## Development and builds

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

## Data, security, and backups

- Runtime data is stored under data/ by default; configuration, secrets, personas, logs, and plugins are user-managed.
- config.yaml, secrets.enc, and secrets.key may contain sensitive data. Do not commit or share them.
- The control API requires a token by default and should listen only on localhost or a trusted LAN.
- Back up data/, personas/, plugins/, config.yaml, and secrets.* before updates or uninstall.
- Mirrors can accelerate downloads but cannot replace SHA256 verification against official release metadata.
- Model providers receive the content sent to the model; review their data policies.

## FAQ

**QQ messages do not receive a reply.** Confirm that the OneBot 11 implementation is connected, then check adapter type, transport, address, port, and token. NapCat, LLOneBot, Lagrange, and go-cqhttp expose different extensions; use strict onebot11 mode when needed.

**Is Telegram stable?** The Telegram Bot API adapter is available but marked Beta in v2.1.0-alpha; platform coverage and long-running behavior may change.

**The Linux GUI fails to start.** Install python3-gi, gir1.2-gtk-4.0, and gir1.2-adw-1. On servers or ARM64 devices without a full desktop stack, use WebUI.

**WebUI cannot be opened.** Check the listening address and port in the startup log. It is local-only by default; LAN access must be enabled explicitly and should retain the access token.

## Releases

| Version | Status |
|---|---|
| v2.1.0-alpha | Current Latest; security hardening, cross-platform stability, and safer container exports. |
| v2.0.1-alpha.1 | Previous release; no-adapter startup fixes. |
| v2.0.1-alpha | Previous release; WebUI LAN switch and tool-profile fixes. |
| v2.0.0-alpha.1 | First v2 release with separate backend/frontend updates. |
| v1.0.x | Legacy bound release line; unsupported and kept for archival use. |

See [releases/v2.1.0-alpha.md](releases/v2.1.0-alpha.md) for the complete change list.

## Documentation and feedback

- Main repository: <https://github.com/CN-BI5UNF/KarenBot>
- Installer: <https://github.com/CN-BI5UNF/KarenBot-Installer>
- Issues: <https://github.com/CN-BI5UNF/KarenBot/issues>
- Distribution contract: [docs/distribution.md](docs/distribution.md)
- Migration guide: [docs/transition.md](docs/transition.md)

When filing an issue, include the operating system and version, installation method, relevant logs with tokens/API keys/chat content removed, and reproduction steps.

## License

KarenBot is released under the [Apache License 2.0](LICENSE). Upstream notices are preserved in [NOTICE](NOTICE).

