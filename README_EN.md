# KarenBot

> A long-running local character chat agent with personas, long-term memory, tools, and QQ/Telegram integrations.

KarenBot began as a rework of [Debata_Agent](https://github.com/binglang001/Debata_Agent) and now ships as an independent v2 unified distribution.

It is a character-chat framework built to run for a long time on your own computer or server. LLM providers, persona prompts, long-term memory, QQ/Telegram integrations, tool use, and a visual control console all live in one runtime — so a character does more than answer questions. It remembers your conversations, reaches for tools when they help, looks things up, sends images, joins group chats, and builds up its own context over time.

Everything is local-first: chat history, personas, keys, and knowledge stay on your machine, and model requests go only to the providers you configure.

- Current application release: [**v2.1.0-alpha**](https://github.com/CN-BI5UNF/KarenBot/releases/tag/v2.1.0-alpha)
- Official installer: [**v2.0.0-alpha**](https://github.com/CN-BI5UNF/KarenBot-Installer/releases/tag/v2.0.0-alpha)
- Supported platforms: Windows 10/11 x64, Linux (x64 / arm64)
- Frontends: native **GTK4 GUI** / browser **WebUI**
- License: Apache-2.0

> v2 is a unified distribution: the backend and the selected frontend are released and updated together, though either component can also be updated alone from the Updates page. `v2.1.0-alpha` is the current release but is still an alpha preview; interfaces and data formats may change, so back up before upgrading.

[简体中文 README](README.md)

---

## Contents

- [What KarenBot is](#what-karenbot-is)
- [Features](#features)
- [Installation](#installation)
- [First run](#first-run)
- [Running](#running)
- [Requirements](#requirements)
- [Repository layout](#repository-layout)
- [Development and builds](#development-and-builds)
- [Updates](#updates)
- [Data, security, and backups](#data-security-and-backups)
- [FAQ](#faq)
- [Releases](#releases)
- [Documentation and feedback](#documentation-and-feedback)
- [Contributing](#contributing)
- [License](#license)

---

## What KarenBot is

KarenBot consists of three components that can be combined as needed:

| Component | Role |
|---|---|
| **Backend** | Core runtime: persona agents, memory, tools, adapters, and the control API |
| **GUI** | Native GTK4 / libadwaita desktop console |
| **WebUI** | Browser console, local-only by default; enable LAN access to use it from a phone or tablet |

Both frontends share the same backend control plane, so configuration, state, and capabilities stay consistent. Install either one, or both.

It fits scenarios like these:

- a private AI character with long-term memory and a stable personality;
- a character that joins QQ groups or Telegram chats and takes part in everyday conversation;
- a character that can search, recognize images, speak, consult a knowledge base, and manage group chats;
- long-running deployments on a personal machine or small server, with all data under your control;
- custom play through plugins and your own personas.

## Features

### Personas and memory

- **Multiple personas**: a built-in default persona plus your own created or imported characters; each persona has its own prompt, knowledge, and chat context.
- **Long-term memory**: conversation history, important memories, RAG retrieval, and archived storage, so a character can remember information across sessions.
- **Persona work state**: a character can enter a "work" state and temporarily switch to a tool profile better suited to tasks.
- **Knowledge and slang**: per-persona knowledge entries, group slang, and world details, kept isolated from each other.
- **Character imagery**: multiple character images, previews, and image sending.

### Chat platforms

NapCat is one implementation in the QQ/OneBot 11 ecosystem, not the only platform KarenBot supports. The current protocol catalog:

| Integration | Status | Details |
|---|---|---|
| **OneBot 11** | Available | Compatible with NapCat, LLOneBot, Lagrange, go-cqhttp, and other implementations; supports forward/reverse WebSocket, HTTP API, and HTTP POST Webhook. |
| **Telegram Bot API** | Beta | Long polling and Webhook for private chats, groups, and Topics; long-running real-world regression is still being expanded. |
| **QQ Official Bot API v2** | Planned | Protocol documentation and configuration contracts exist, but no usable adapter ships in this version. |
| **Satori v1** | Planned | Intended to bridge Discord, Telegram, Feishu, and other platforms through a Satori server; no usable adapter ships in this version. |

The OneBot 11 adapter offers a strict standard mode (`onebot11`) and a NapCat extension-compatible mode (`napcat`); when the connected implementation lacks an extension, KarenBot degrades gracefully.

- **Structured messages**: text, mentions, replies, images, voice, video, files, reactions, and forwarded messages are normalized into message segments.
- **Group chat control**: allow/deny lists, group trigger rules, group receive selection, and group management tools.

### Models and tools

- OpenAI-compatible endpoints, Anthropic, Google Gemini, and other providers;
- models bound per persona, with separate main, vision, Embedding, and TTS models;
- built-in tools for sending messages, group management, search, vision, voice, knowledge bases, and RAG memory;
- optional controlled Docker containers and a coding-agent mode;
- a plugin system for backend plugins and new frontend modules.

### External program hosting

KarenBot can start companion programs such as NapCat, SnowLuma, proxies, or other dependencies at launch:

- custom name, executable, arguments, working directory, and environment variables;
- port probing: if something already serves the port, startup is skipped and the existing process is never killed;
- optional automatic restart;
- "stop with KarenBot" only stops processes that KarenBot successfully started;
- a failed program is logged and reported without affecting KarenBot itself.

### Two frontends

**GUI**: a native GTK4 window for long desktop sessions.

- Overview, conversations, memory, personas, knowledge, slang, models, logs, containers, storage, allow/deny lists, group triggers, and settings;
- themes, font scaling, and render fallback;
- connects to the backend over loopback HTTP with a random token, never exposed publicly.

**WebUI**: browser access for servers, phones, and tablets.

- pages and settings aligned with the GUI;
- login token and hash routing;
- opens directly in a browser on the local network;
- files are primarily downloaded or previewed in the browser.

### Runtime and updates

- v2 uses the **KarenBot unified distribution**: backend + current frontend updated as a set;
- every file is backed up before an update, and failures roll back as a whole;
- only program files are replaced; user data such as `data/`, `personas/`, `plugins/`, and `config.yaml` is left untouched;
- pre-releases can be selected manually, with an explicit risk notice.

## Installation

The recommended path is the official **[KarenBot Installer v2.0.0-alpha](https://github.com/CN-BI5UNF/KarenBot-Installer/releases/tag/v2.0.0-alpha)**. The installer and the application are released separately; the Linux commands below pin application `v2.1.0-alpha`. The installer downloads, verifies, and assembles the required components, while Windows GUI uses a prebuilt portable bundle.

### Windows 10/11 (x64)

1. Download installer `v2.0.0-alpha`:

   [KarenBot-Installer.exe](https://github.com/CN-BI5UNF/KarenBot-Installer/releases/download/v2.0.0-alpha/KarenBot-Installer.exe)

2. Run it; no Python installation is required. If SmartScreen warns about an unknown publisher, confirm the file came from the official release, then choose "More info → Run anyway".
3. Choose a short, writable ASCII path (the default is `C:\KarenBot`), and select **GUI** or **WebUI**.
4. Select **Online installation** and wait for the download and verification to finish.
5. Launch KarenBot from the desktop or Start Menu.

The Windows native GUI uses a separately downloaded portable GTK4 bundle, so you do not need to install GTK yourself. The application version inside that bundle depends on how it was built; to run `v2.1.0-alpha`, choose it under **Settings → Updates** after installation. Windows WebUI downloads a portable Python on demand and creates a browser launch entry.

### Linux (x64 / arm64)

You need Bash, curl, Python 3.10+, and `sha256sum`. On Debian / Ubuntu, start with
`sudo apt install curl python3 python3-venv`.
In the same terminal, download and verify the installer script and core for `v2.0.0-alpha`:

```bash
export KAREN_INSTALLER_REF=v2.0.0-alpha
export KAREN_INSTALLER_SHA256=0c5fa39a5a4ac15726cd70708c2e34488703dfec067d07efdb8594b197821309
curl -fL https://github.com/CN-BI5UNF/KarenBot-Installer/releases/download/v2.0.0-alpha/install.sh -o install.sh &&
printf '%s  %s\n' '624538f2c167b091ee32e17cdc2c9322e3c857f94619723b1e1fd7375d759d01' install.sh | sha256sum -c - &&
bash install.sh
```

Then follow the menu:

- **Online installation**;
- frontend: `GUI` or `WebUI`;
- install directory (default `~/.local/opt/karenbot`).

You can also pass the options directly in the same terminal to install KarenBot `v2.1.0-alpha` explicitly:

```bash
# WebUI
bash install.sh --online --frontend webui --tag v2.1.0-alpha --dir ~/.local/opt/karenbot

# Native GUI
bash install.sh --online --frontend gui --tag v2.1.0-alpha --dir ~/.local/opt/karenbot
```

If GitHub access is unreliable, follow the installer README's multi-mirror download and hash verification steps:

[Multi-mirror installation guide](https://github.com/CN-BI5UNF/KarenBot-Installer#github-访问不稳定时)

The Linux native GUI needs GTK4, libadwaita, and PyGObject from the system:

```bash
# Debian / Ubuntu
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
```

WebUI alone does not require GTK.

Linux desktop users can also download the
[x64 graphical installer](https://github.com/CN-BI5UNF/KarenBot-Installer/releases/latest/download/KarenBot-Installer-linux-x64)
or [arm64 graphical installer](https://github.com/CN-BI5UNF/KarenBot-Installer/releases/latest/download/KarenBot-Installer-linux-arm64)
from the installer release, `chmod +x` it, and run it in a desktop session. Servers and SSH sessions should use the CLI above.

### What the installer does

1. Resolves the unified distribution (`modules.json`) from `--tag` or the main repository's release feed — for Linux and Windows WebUI alike;
2. downloads the **backend + your selected frontend**; Windows GUI downloads a prebuilt portable application package;
3. verifies sizes and SHA256 values against the release manifest (Windows GUI uses `SHA256SUMS.txt`);
4. extracts and assembles the application directory;
5. fills in default personas from the KarenBot main repository;
6. creates a virtual environment and installs Python dependencies (skipped for the Windows portable bundle);
7. writes launch entries, shortcuts, and uninstall information.

The `data/` directory inside the install location holds runtime data. It is preserved during upgrades, and you can choose to keep it when uninstalling.

## First run

The first launch opens a setup wizard with three typical steps:

### 1. Configure a model provider

Enter the API URL, API key, and model name. KarenBot supports OpenAI-compatible endpoints, Anthropic, Gemini, relay services, and local compatible servers.

Keys are stored encrypted, not in the plain configuration file.

### 2. Connect a chat platform

**QQ / OneBot 11**

Prepare a OneBot 11 implementation such as NapCat, LLOneBot, Lagrange, or go-cqhttp, then configure KarenBot:

- Forward WebSocket: enter the implementation's address;
- Reverse WebSocket: let the implementation connect to KarenBot;
- HTTP API / Webhook: enter the address, port, and authentication as documented by the implementation.

You can also add NapCat to the **External programs** list so KarenBot starts it at launch.

**Telegram**

Create a bot with BotFather and enter its token in KarenBot's Telegram adapter.

### 3. Choose or create a persona

KarenBot ships with a default persona. Use the **Personas** page to create your own character — prompt, greeting, knowledge, and images — then bind the persona to the relevant chat account.

When setup is complete, start the Runtime and open the conversation page.

## Running

### GUI

Launch from the desktop shortcut, or run:

```bash
# Linux
~/.local/opt/karenbot/launch-gui.sh
```

The GUI starts the backend on a loopback address and connects with a random token; no extra ports need to be opened.

### WebUI

Launch from the startup entry, or run:

```bash
~/.local/opt/karenbot/launch-webui.sh
```

It listens on localhost by default. To allow LAN access, open **Settings → Network** in the WebUI, enable "Allow LAN access", and restart the WebUI. You can also set `webui.allow_lan: true` in `config.yaml`, or pass `--host 0.0.0.0` at startup. The access token is still required; never expose the control plane directly to the public Internet.

### Headless / servers

The backend runs without a UI, which suits long-running server deployments. See `main.py --help` and `docs/` for the available options.

## Requirements

| Item | Requirement |
|---|---|
| Windows | Windows 10/11 x64; the native GUI uses a portable GTK4 bundle |
| Linux | x64 / arm64; the GUI requires GTK4 + libadwaita + PyGObject |
| Python | 3.10+ for development and source runs; the installer prepares its runtime |
| Memory | 2 GB or more recommended; local models need additional memory |
| Disk | About 1.2 GB for the GUI and 400 MB for the WebUI, including dependencies and cache headroom |
| Network | GitHub access for installation and updates; access to your configured model provider |

## Repository layout

The KarenBot main repository is the unified distribution and assembly repository; the three components are maintained as submodules:

```text
KarenBot/
├── modules/
│   ├── KarenBot-backend/    # Core runtime + backend control plane
│   ├── KarenBot-GUI/        # GTK4 desktop frontend gui/
│   └── KarenBot-WebUI/      # Browser frontend webui/
├── personas/                # Default personas
├── scripts/
│   ├── assemble.py          # Assemble a runnable directory from submodules
│   ├── build_release_assets.py
│   └── verify_modules.py
├── modules.lock.json        # Component tags/commits pinned by this release
├── releases/                # Release notes
├── docs/
│   ├── distribution.md      # Installer asset contract
│   └── transition.md        # Upgrade path for older versions
└── README.md
```

Official releases are produced by GitHub Actions:

- `modules.json`
- `KarenBot-backend-<tag>.tar.gz`
- `KarenBot-GUI-<tag>.tar.gz`
- `KarenBot-WebUI-<tag>.tar.gz`

The installer selects "backend + one frontend" from the manifest; it never downloads GitHub source archives, which do not include submodules.

## Development and builds

```bash
git clone --recursive https://github.com/CN-BI5UNF/KarenBot.git
cd KarenBot

# If submodules were not initialized during clone
git submodule update --init --recursive

# Verify the version lock
python scripts/verify_modules.py --tag v2.1.0-alpha

# Assemble a runnable directory (tracked files only)
python scripts/assemble.py --frontend webui --output dist/app
# Or
python scripts/assemble.py --frontend gui --output dist/app
```

Then set up the assembled project like a regular Python application:

```bash
cd dist/app
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e .
.venv/bin/python main.py --frontend webui
```

The GUI on Linux additionally needs system GTK4/PyGObject; for Windows development, use the installer's portable bundle or a WSL/Linux environment.

Release flow, asset contracts, and submodule verification:

- [`docs/distribution.md`](docs/distribution.md)
- [`scripts/build_release_assets.py`](scripts/build_release_assets.py)
- [`.github/workflows/release.yml`](.github/workflows/release.yml)

## Updates

### v2 users

Check the KarenBot unified distribution under **Settings → Updates** in the GUI/WebUI.

- By default, the backend and the current frontend update together; you can also update only the backend or only the current frontend;
- a frontend-only update does not restart the backend (fully reopen the GUI or refresh the WebUI page); a backend update requires a backend restart;
- stable releases are offered automatically; pre-releases require manual selection and risk confirmation;
- files are backed up individually under `data/module_backups/` before updating;
- user data, personas, plugins, and configuration are never overwritten.

> Updating a single component can leave the two ends on different versions. If you hit interface errors, update the other component too, or choose "reinstall everything".

### 0.1.x users

Install the transition release first, then upgrade to v2:

1. Backend `v0.1.11-alpha.1`;
2. GUI/WebUI `v0.1.1-alpha.2`;
3. Restart the application;
4. Manually select the latest v2 release in the Updates page (currently `v2.1.0-alpha`).

See [`docs/transition.md`](docs/transition.md) for details.

### 1.0.x users

The old "backend + WebUI bound" release line is no longer supported. Back up your data and migrate using the new installation flow; the old releases remain in this repository and have been copied to the private `CN-BI5UNF/Debata-Refactor` archive.

## Data, security, and backups

- Runtime data lives under `data/` in the install directory by default; configuration, keys, personas, logs, and plugins are managed from the user directory.
- `config.yaml` may contain sensitive configuration; `secrets.enc` / `secrets.key` encrypt your keys and must not be shared.
- The control API requires a token by default and should listen only on localhost or a trusted LAN; never expose it directly to the public Internet.
- The updater only writes program files and never deletes user data, but backing up before an upgrade is still recommended:
  - `data/`
  - `personas/`
  - `plugins/`
  - `config.yaml`
  - `secrets.*`
- The installer verifies SHA256 values for release assets; third-party mirrors can speed up transfers but cannot replace publisher verification.
- Model providers receive the conversation content you send them; review each provider's data policy.

## FAQ

**Windows shows SmartScreen / unknown publisher**

The installer is not code-signed. Choose "More info → Run anyway", and only download from the official release.

**GitHub is slow or unreachable**

The installer tests several mirrors and can pin one; you can also pin a mirror in the installer/GUI. If all fail, configure a proxy or download `install.sh` / the installer manually from the release.

**The Linux GUI shows a black window or GTK errors**

Confirm that `python3-gi`, `gir1.2-gtk-4.0`, and `gir1.2-adw-1` are installed. The installer also provides `launch-gui-safe.sh`, a compatibility mode using Cairo software rendering.

**The WebUI will not open**

Check the listening address and port in the startup log; it is local-only by default. LAN access requires enabling "Allow LAN access" under **Settings → Network** and restarting the WebUI, or starting with `--host 0.0.0.0`; the access token is still required.

**QQ messages get no reply**

First confirm that the NapCat/LLOneBot implementation is connected, then check the OneBot 11 transport type, address, port, and token in KarenBot. Send a test message from the implementation's debug tools.

**Can I start KarenBot before connecting QQ/Telegram?**

Yes. Since `v2.0.1-alpha.1`, the Runtime enters a no-channel mode when no adapter is enabled: models, personas, memory, and local features work as usual, and enabling an adapter later restores message flow automatically.

**Do I need to restart after an update?**

A backend update requires a backend restart; a GUI update requires fully quitting and reopening the GUI; a WebUI update requires refreshing the page.

## Releases

| Version | Status |
|---|---|
| `v2.1.0-alpha` | Current release (security audit fixes, cross-platform stability, and hardened container exports) |
| `v2.0.1-alpha.1` | Previous release (no-channel startup fix) |
| `v2.0.1-alpha` | Previous release (WebUI LAN switch, shortcut icon fixes, tool profile move) |
| `v2.0.0-alpha.1` | Previous release (separate backend/frontend updates) |
| `v0.1.x` module line | Requires the transition patch to upgrade to v2 |
| `v1.0.x` bound line | Unsupported; kept for archival use only |

See [`docs/distribution.md`](docs/distribution.md) for v2 component versions, assets, and update rules.

## Documentation and feedback

- Main repository: <https://github.com/CN-BI5UNF/KarenBot>
- Installer: <https://github.com/CN-BI5UNF/KarenBot-Installer>
- Issues: <https://github.com/CN-BI5UNF/KarenBot/issues>
- Release notes: [`releases/`](releases/)

When filing an issue, please include:

- your operating system and version;
- how you installed KarenBot (installer / source / upgrading an older version);
- relevant logs (remove tokens, API keys, chat content, and other private data first);
- reproduction steps.

## Contributing

Issues and pull requests are welcome. Please keep tokens, API keys, chat logs, and other private data out of reports and commits, and include reproduction steps where possible.

## License

Apache-2.0. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE) for details.
