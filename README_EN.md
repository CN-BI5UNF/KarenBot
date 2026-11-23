# KarenBot

> A local character chat agent that remembers, acts, and keeps you company over the long run.

| Quick access | Link |
|---|---|
| **简体中文 README** | [README.md](README.md) |
| **Current release** | [v2.1.0-alpha](https://github.com/CN-BI5UNF/KarenBot/releases/tag/v2.1.0-alpha) |
| **Official installer** | [KarenBot Installer v2.0.0-alpha](https://github.com/CN-BI5UNF/KarenBot-Installer/releases/tag/v2.0.0-alpha) |
| **Release notes** | [releases/](releases/) |
| **Issues** | [GitHub Issues](https://github.com/CN-BI5UNF/KarenBot/issues) |
| **Distribution and upgrades** | [Distribution contract](docs/distribution.md) / [Legacy upgrade path](docs/transition.md) |

Supports Windows 10/11 x64 and Linux (x64 / arm64); licensed under Apache-2.0.

KarenBot began as a rework of [Debata_Agent](https://github.com/binglang001/Debata_Agent) and is now a character-chat framework built to run for a long time on a personal computer or server. It combines an LLM runtime, personas, a background mind, long-term memory, QQ/Telegram integrations, tool use, and a visual control console in one application. A character does more than answer questions: it remembers what you told it, adjusts tone by relationship, joins group conversations, looks things up, sends images, writes files, and can even enter a controlled container to finish a task.

Everything is local-first: chat history, personas, keys, knowledge, and workspaces stay on your machine, and model requests go only to the providers you configure.

> `v2.1.0-alpha` is the current release but is still an alpha preview; interfaces and data formats may change, so back up before upgrading. v2 is a unified distribution: the backend and the selected frontend update together, though either component can also be updated alone from the Updates page.

---

## Contents

- [What KarenBot is](#what-karenbot-is)
- [Feature overview](#feature-overview)
- [Human-like conversation](#human-like-conversation)
- [Personas and background mind](#personas-and-background-mind)
- [Memory, knowledge, and slang](#memory-knowledge-and-slang)
- [Chat platforms and group management](#chat-platforms-and-group-management)
- [Models and multi-agent](#models-and-multi-agent)
- [Tools, workspace, and coding agents](#tools-workspace-and-coding-agents)
- [Emoji and multimodal](#emoji-and-multimodal)
- [Two consoles](#two-consoles)
- [Installation](#installation)
- [First run](#first-run)
- [Running day to day](#running-day-to-day)
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
| **Backend** | Core runtime: persona agents, background mind, memory, tools, adapters, and the control API |
| **GUI** | Native GTK4 / libadwaita desktop console |
| **WebUI** | Browser console, local-only by default; enable LAN access to use it from a phone or tablet |

Both frontends share the same backend control plane, so configuration, state, and capabilities stay consistent. Install either one, or both.

It fits scenarios like these:

- a private AI character with long-term memory, a stable personality, and the ability to start conversations;
- a character that joins QQ groups or Telegram chats, takes part in everyday conversation, and helps manage the group;
- a character that can search, recognize images, consult knowledge, send emoji, and speak;
- a character that can read and write files, run commands, and complete coding tasks in a controlled environment;
- long-running deployments on a personal machine or small server, with all data under your control.

## Feature overview

| Capability | What you get |
|---|---|
| **Human-like conversation** | Replies split into multiple short messages, tone that shifts by relationship, proactive thinking, pre-send review, and interruption handling |
| **Personas and background mind** | Multiple personas, age brackets, energy/satiety/mood, sleep and eating, work state, and admin wake-up |
| **Long-term memory** | File-based or RAG memory with global/person/group scopes and pinned entries |
| **Knowledge and slang** | Web-researched knowledge notes, on-demand group slang, deduplication, and read-only sharing |
| **Group management** | Allow/deny lists, per-group @ trigger windows, chat receive scope, group admin tools, stranger rate limits |
| **Model access** | 14 built-in providers, any OpenAI/Anthropic-compatible relay, and per-agent model binding |
| **Tools** | 15 toolsets, an AI workspace, coding agents, a controlled Docker container, and external program hosting |
| **Multimodal** | Emoji, character images, vision, and speech synthesis |
| **Two consoles** | A GTK4 GUI and a WebUI with 15 pages each, token auth, and mostly hot-applied settings |
| **Deployment and updates** | Official installer, unified releases, component-level updates and rollback, automatic backups, and SHA256 verification |

## Human-like conversation

KarenBot aims for a character that participates in chat, not a customer-service bot.

- **Multi-bubble replies**: a single reply can be split into several messages, sent in order with a configurable delay between them, so short lines, follow-ups, and emoji arrive separately instead of as one wall of text.
- **Relationship-aware tone**: a character can tease close friends, speak respectfully to elders, and stay polite but distant with strangers; persona prompts and user profiles both shape the wording.
- **Natural rhythm**: rapid consecutive messages are merged before processing; characters can digress, change their mind, forget things, or choose not to reply.
- **Proactive thinking**: a background loop can periodically decide whether to speak first (about every 10 minutes by default, configurable); it does not run unless a proactive-thinking model is configured.
- **Pre-send review**: the send tool checks for newer, higher-priority messages and can pause or replace a reply so stale content is not delivered.
- **Interruption policies**: per-conversation policies can interrupt on any new message, only on high-priority messages, or use atomic delivery, matching casual chat, long replies, and fixed notifications.
- **Stranger rate limits**: non-friends are rate-limited by default; friends and admins are exempt.
- **No-channel trial mode**: without QQ/Telegram, the Runtime still starts in no-channel mode, and the conversation page can inject simulated inbound messages to test personas and tools.

## Personas and background mind

A persona is more than a static prompt; it is a continuously maintained character state.

- **Multiple personas**: a built-in default plus your own created, copied, or ZIP-imported personas; each has its own prompt, knowledge, slang context, and chat history.
- **AI-assisted authoring**: generate a persona from a short description, rewrite it iteratively, edit the prompt directly, or inspect the persona source read-only.
- **Age and physiology**: age brackets and age hints, with energy, satiety, mood, and social needs tracked; different age brackets can configure different energy decay, sleep duration, and mood volatility.
- **Sleep, eating, and collapse**: characters can sleep and eat on their own; when energy runs out they enter a collapse state, and waking or finishing a meal triggers a model-based recovery assessment with a formula fallback.
- **Background maintenance**: the persona-management agent periodically organizes events, chat scenes, current state, user profile, short-term effects, clues, todos, and long-term memories into structured context for the main chat agent.
- **Work state**: a character can call `work` to enter work mode for long tasks in a container; private messages and group mentions are queued, ordinary group messages are only recorded, and everything is processed together afterwards. The maximum work duration is configurable, and 0 disables the state.
- **Admin wake-up**: when a persona is sleeping or collapsed, an admin can leave a wake-up line in the persona console; the response appears only in the wake-up card and is never sent to QQ automatically.
- **Character images**: each persona can keep multiple appearance images, choose a preview image, and send images through `persona-image:` references.

## Memory, knowledge, and slang

### Long-term memory

- Remembers promises, appointments, preferences, and identity details across sessions;
- Each memory has a scope (global / person / group) and a pinned flag;
- **File mode**: plain JSON, zero configuration, fully transparent, suitable for one-on-one chat;
- **RAG mode**: background extraction and vector indexing with semantic retrieval, suitable for many groups and users over time;
- The memory page supports viewing, editing, manual additions, import, and export.

### History and archives

- Rolling summaries compress old conversations into long-term memory;
- Conversations and groups can be summarized, and archived records filtered and searched;
- The model can look back at recent messages or older archives on demand instead of stuffing all history into context.

### Knowledge and memes

- The model can use `web_search` to research a topic, then save verified findings as knowledge notes;
- Each note carries source, type, and confidence; only `active` entries are returned by `list_knowledge_notes`;
- Notes are not injected into every turn; the model queries them on demand, preserving KV-cache hits;
- A background task can research current internet memes on a schedule, with configurable search terms and note limits;
- Notes are deduplicated by title and topic, with `/api/knowledge/dedupe` to preview and merge duplicates;
- Knowledge can be shared per entry; other personas get read-only access while the owner keeps edit and delete rights;
- Web text is treated as untrusted data: escaped, truncated, and explicitly marked as instructions not to follow.

### Group slang

- Learns abbreviations, catchphrases, and in-jokes per group; candidates take effect only after an admin confirms them on the Slang page;
- Only confirmed entries can be queried by `lookup_slang`; candidates, evidence, and other groups' entries never leak to the model;
- Entries are shared by all personas in the same group and strictly isolated across groups;
- Slang is not injected into every turn; the model looks it up only when it encounters an unfamiliar term.

## Chat platforms and group management

NapCat is one implementation in the QQ/OneBot 11 ecosystem, not the only platform KarenBot supports. The current protocol catalog:

| Integration | Status | Details |
|---|---|---|
| **OneBot 11** | Available | Compatible with NapCat, LLOneBot, Lagrange, go-cqhttp, and other implementations; supports forward/reverse WebSocket, HTTP API, and HTTP POST Webhook. |
| **Telegram Bot API** | Beta | Long polling and Webhook for private chats, groups, and Topics; long-running real-world regression is still being expanded. |
| **QQ Official Bot API v2** | Planned | Protocol documentation and configuration contracts exist, but no usable adapter ships in this version. |
| **Satori v1** | Planned | Intended to bridge Discord, Telegram, Feishu, and other platforms through a Satori server; no usable adapter ships in this version. |

> A Runtime currently runs one primary adapter; if several are configured, only the first enabled one is used and the rest are ignored. With no adapter enabled, the Runtime starts in no-channel mode and local features remain available.

### OneBot 11

- Strict standard mode `onebot11` and NapCat extension-compatible mode `napcat`;
- Forward WebSocket, reverse WebSocket, HTTP API, and HTTP POST Webhook;
- Reverse WS supports multiple accounts and routes messages by `self_id`;
- Webhook supports HMAC-SHA1 signature verification;
- When an implementation lacks an extension, KarenBot degrades gracefully.

### Messages and groups

- **Structured messages**: text, mentions, replies, images, voice, video, files, reactions, and forwarded messages become message segments;
- **Allow/deny lists**: inbound policy supports `open` / `verify` / `whitelist`; blacklist hits are dropped first, ahead of the whitelist;
- **Per-group @ triggers**: listed groups respond only when mentioned, with configurable consecutive-message counts, time windows, and filter-cache size;
- **Chat receive scope**: the model can use `chat_selection` to pause group messages, receive only selected groups, or restore normal delivery; mentions always pass;
- **Group admin tools**: kick, mute, whole-group mute, leave, friend requests, and group join request approval;
- **Group trigger window tools**: the model can open, extend, or close a group window and look back at filtered messages.

## Models and multi-agent

### Providers

Fourteen built-in provider presets:

Anthropic Claude, DeepSeek, Google Gemini, Zhipu GLM, Groq, Xiaomi MiMo, Moonshot Kimi, OpenAI, OpenRouter, Qwen, SiliconFlow, Together, Volcengine Ark, and xAI.

You can also connect any OpenAI / Anthropic-compatible endpoint or relay:

- Add a provider under **Model management → Add provider** with its base URL, API key, and model name;
- Test the connection and fetch the model list;
- Optionally declare the upstream model vendor for vision, video, and context capability tables;
- Choose a thinking-parameter style per provider so relay gateways do not reject vendor-specific fields;
- Drop custom presets into `providers/presets/` in the data directory.

### Multi-agent roles

The main chat, proactive thinking, rolling summary, and persona-generation agents can bind different models. For example, use a strong model for chat and small models for proactive checks and summaries; unconfigured roles fall back safely to the chat or proactive model.

### Reasoning and multimodal

- Thinking modes expose low/medium/high or more granular levels depending on the model;
- **Vision**: use native image input on the main model, or configure a separate `describe_image` vision model;
- **Embedding**: API services or local models for RAG memory;
- **TTS**: EdgeTTS (free), iFlytek, or local VoxCPM2;
- **Images and video**: configurable byte, pixel, per-message count, and request-body limits.

### Token efficiency

- Only old context sent to the model is trimmed; history, archives, and the event store remain intact;
- Tool schemas support `compact`, `full`, `routed`, and `agent` profiles, loading tools as needed;
- High-frequency tools are exposed directly; low-frequency or high-risk tools are queried through `tool_search`;
- Request counts, input/output/thinking tokens, and KV hit rate are tracked and calibrated per provider/model.

## Tools, workspace, and coding agents

### Toolsets

Tools are organized into 15 toolsets that can be loaded as a group or searched individually:

| Toolset | Capability |
|---|---|
| `core` | Replying, ending a turn, basic memory/knowledge, vision, @ trigger windows, and routing entry points |
| `control` | Scheduled wake-ups, chat receive scope, group trigger windows, tool search |
| `messaging` | Private/group sending, recall, file upload, voice messages |
| `qq_info` | Contacts, group members, message lookup, poke, reactions |
| `qq_admin` | Kick, mute, whole-group mute, leave, friend/group request approval |
| `history` | Recent messages, conversation summaries, archive filtering and search |
| `memory` | Save, update, and delete long-term memories |
| `knowledge` | Knowledge notes, web research, deletion of stale notes |
| `slang` | Query confirmed slang and in-jokes for the current group |
| `web` | Web search, page fetching, weather |
| `emoji` | List, save, rename, and delete emoji |
| `workspace` | Local workspace read/write, Python execution, file upload, background tasks |
| `persona` | Eating, sleeping, and autonomous work state |
| `coding` | Read/write/edit, patches, commands, glob/grep, subagents, plan mode, custom tools |
| `container` | Execute commands and read/write `/workspace` inside a controlled Docker container |

### AI workspace

- Read, write, edit, and delete files in the local workspace;
- Run Python and upload files to QQ;
- Read PDF, DOCX, XLSX, and other documents users send;
- Start background agent tasks that run outside the chat loop.

### Coding agents

Coding tools are KarenBot's own tool semantics; they do not launch third-party TUIs or GUIs:

- **Host**: always uses Claude Code semantics, scoped to the AI workspace;
- **Container**: install and activate one of Pi, DSH, or Claude Code at a time;
- Supports read/write/edit, unified diff patches, commands, glob/grep, todos, plan mode, subagents, Jupyter cells, and custom tools;
- Entering work state temporarily switches the persona to a coding-oriented tool profile.

### Controlled Docker container

- No network by default, `cap-drop ALL`, `no-new-privileges`, non-root, read-only root filesystem, and only `/workspace` writable;
- Memory, CPU, pids, per-file size, output, and timeouts are configurable;
- Storage supports B (Docker named volume with a soft quota, the default, no admin required) and C (fixed-size filesystem image with a hard limit, requiring one-time admin mounting);
- The container page provides a read-only file manager with local-workspace and container-workspace modes;
- Changing resource limits does not force a rebuild; new settings apply after an explicit rebuild;
- A Docker image mirror prefix can be configured, and missing images are pulled in the background at startup.

### External program hosting

KarenBot can start NapCat, LLOneBot, proxies, or other dependencies at launch:

- Custom name, executable, arguments, working directory, and environment variables;
- Port probing: if something already serves the port, startup is skipped and the existing process is never killed;
- Optional automatic restart and startup wait time;
- "Stop with KarenBot" only stops processes that KarenBot successfully started;
- A failed program is logged and reported without affecting the main application;
- Configuration is hot-applied: new or enabled entries start immediately, removed or disabled entries stop immediately.

## Emoji and multimodal

- Put emoji files in `data/emoji/`; the model picks and sends them based on conversation mood;
- The WebUI/GUI supports drag-and-drop, multi-select upload, per-file renaming, thumbnails, renaming, and deletion;
- PNG / JPG / JPEG / GIF are supported, up to 5 MB each; duplicate names get a `_1` suffix;
- The model can list emoji, save one from a group message or a URL, rename it, and delete it;
- QQ native faces are mapped to Chinese names, for example `[CQ:face,id=5]` displays as "流眼泪" and can be sent by name;
- Character appearance images are managed separately from emoji and can be sent to users or inspected by the vision model;
- Voice messages are synthesized through TTS, with cloud and local options.

## Two consoles

### GUI

A native GTK4 / libadwaita desktop console for long desktop sessions.

- 15 pages: Overview, Chats, Memory, Persona mind, Logs, Personas, Slang, Knowledge, Models, Emoji, Container, Storage & data, Allow/deny lists, Group triggers, and Settings;
- Follows the system theme or switches manually, with font scaling and render fallback;
- Starts the backend on loopback with a per-process random Bearer token, never exposed publicly;
- Automatically falls back to Cairo software rendering if GPU rendering fails.

### WebUI

A browser console for servers, phones, and tablets.

- The same 15 pages and settings as the GUI;
- Login token exchanged for an HttpOnly session cookie, valid for 30 days by default;
- Local-only by default; LAN access can be enabled under **Settings → Network**;
- Dark/light themes and a sidebar that collapses to icons;
- The conversation page supports live refresh, record filtering, attachment preview, and simulated inbound messages;
- Storage & data provides cache inventory, cleanup previews, context compaction, persona runtime data cleanup, and local uninstall.

### Shared backend

- Both frontends use the same FastAPI control plane and Runtime, so features never diverge;
- Settings pages are generated from a declarative field table, and most options apply immediately;
- Structural fields such as container storage mode and memory/Embedding mode are explicitly marked "restart required";
- GUI and WebUI show the same save states: "saved and applied", "Runtime restart required", or "restart pending".

## Installation

The recommended path is the official **[KarenBot Installer v2.0.0-alpha](https://github.com/CN-BI5UNF/KarenBot-Installer/releases/tag/v2.0.0-alpha)**. The installer and the application are released separately; the Linux commands below pin application `v2.1.0-alpha`.

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

1. Linux and Windows WebUI resolve the unified distribution (`modules.json`) from `--tag` or the main repository's release feed;
2. downloads the **backend + your selected frontend**; Windows GUI downloads a prebuilt portable application package;
3. verifies sizes and SHA256 values against the release manifest (Windows GUI uses `SHA256SUMS.txt`);
4. extracts and assembles the application directory;
5. fills in default personas from the KarenBot main repository;
6. creates a virtual environment and installs Python dependencies (skipped for the Windows portable bundle);
7. writes launch entries, shortcuts, and uninstall information.

The `data/` directory inside the install location holds runtime data. It is preserved during upgrades, and you can choose to keep it when uninstalling.

## First run

The first launch opens a step-by-step wizard; the desktop version first asks for a data directory, and the remaining steps are:

1. **Main model**: enter the API URL, API key, and model name, choosing a preset or a custom endpoint;
2. **Sub-agents**: on the custom path, optionally bind models for proactive thinking, rolling summaries, and persona generation;
3. **Optional features**: vision, web search, weather, and TTS;
4. **Memory mode**: file-based or RAG; RAG requires Embedding configuration;
5. **Chat integration**: connect NapCat / OneBot 11 through the wizard; you can skip this and start in no-channel mode;
6. **Persona**: choose the default persona or create your own;
7. **Summary**: review the configuration and start the Runtime.

The Telegram adapter is currently configured after installation through Settings or `config.yaml`, not in the first-run wizard.

Keys are stored encrypted, not in the plain configuration file. After setup, use simulated inbound messages on the conversation page to test the persona and tools before connecting QQ or Telegram.

## Running day to day

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

### Background operation

For long-running deployments, use the `karen` shortcuts:

```bash
karen start     # start
karen stop      # stop
karen log       # show logs
karen enable    # enable at boot
karen disable   # disable at boot
```

The commands prefer a systemd user service. Without a systemd user session, they fall back to a PID-file + detached-process mode; tmux, screen, and nohup also work. See the backend's
[background running guide](https://github.com/CN-BI5UNF/KarenBot-backend/blob/v2.1.0-alpha/docs/background_running.md).

### Headless / servers

The backend runs fully headless, which suits long-running server deployments. See `main.py --help` and the backend documentation for options.

## Requirements

| Item | Requirement |
|---|---|
| Windows | Windows 10/11 x64; the native GUI uses a portable GTK4 bundle |
| Linux | x64 / arm64; the GUI requires GTK4 + libadwaita + PyGObject |
| Python | 3.10+ for development and source runs; the installer prepares its runtime |
| Memory | 2 GB or more recommended; local models need additional memory |
| Disk | About 1.2 GB for the GUI and 400 MB for the WebUI, including dependencies and cache headroom |
| Network | GitHub access for installation and updates; access to your configured model provider |
| Docker | Optional; required for the controlled container and container-based coding agents |
| Optional components | Local TTS and Embedding need model files; TTS denoising needs FFmpeg full-shared |

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

Tests and checks:

```bash
# Backend tests (in the backend directory, using the project virtualenv)
PYTHONPATH=. .venv/bin/python -m pytest -q tests

# Frontend syntax checks
python3 -m compileall -q gui
python3 -m compileall -q webui
```

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
- user data, personas, plugins, and configuration are never overwritten;
- you can roll back or switch to a specific version, with data-version, contract-epoch, and capability checks;
- if dependency files change, dependencies are installed with the current interpreter; failures roll back the source.

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

- Runtime data lives under `data/` in the install directory by default; configuration, keys, personas, logs, workspaces, and plugins are managed from the user directory.
- `config.yaml` may contain sensitive configuration; `secrets.enc` / `secrets.key` encrypt your keys and must not be shared.
- API keys use AES-256-GCM + RSA-2048 encryption and are stored in the system keyring.
- The control API requires a token by default and should listen only on localhost or a trusted LAN; never expose it directly to the public Internet.
- The WebUI listens on `127.0.0.1` by default; LAN access still requires the token and should be enabled only on trusted networks.
- The updater only writes program files and never deletes user data, but backing up before an upgrade is still recommended:
  - `data/`
  - `personas/`
  - `plugins/`
  - `config.yaml`
  - `secrets.*`
- Settings provide one-click backup of configuration, encryption keys, chat history, RAG data, workspaces, and personas; backups contain sensitive credentials, so store them safely.
- Cleanup, persona runtime data deletion, and local uninstall on the Storage & data page require a preview, a confirmation phrase, and a checkbox; dangerous operations do not back up by default.
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

**The model returns 401 / an invalid key error**

Re-enter the API key under **Model management** and click **Test connection**. An invalid key does not prevent the Runtime from starting, but chat requests will fail.

**Can I start KarenBot before connecting QQ/Telegram?**

Yes. Since `v2.0.1-alpha.1`, the Runtime enters a no-channel mode when no adapter is enabled: models, personas, memory, and local features work as usual, and enabling an adapter later restores message flow automatically.

**The container fails to start**

Confirm Docker is available and click **Prepare / start** on the container page. The first image pull can take several minutes; configure an image mirror prefix if the network is restricted. Storage mode C requires a one-time admin initialization and never silently degrades.

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
- Backend docs: [`KarenBot-backend/docs`](https://github.com/CN-BI5UNF/KarenBot-backend/tree/v2.1.0-alpha/docs)

Topic guides:

| Document | Contents |
|---|---|
| [Container](https://github.com/CN-BI5UNF/KarenBot-backend/blob/v2.1.0-alpha/docs/container.md) | Docker container, storage modes, file manager, troubleshooting |
| [Agent modes](https://github.com/CN-BI5UNF/KarenBot-backend/blob/v2.1.0-alpha/docs/agent_modes.md) | Pi / DSH / Claude Code tool semantics |
| [Background running](https://github.com/CN-BI5UNF/KarenBot-backend/blob/v2.1.0-alpha/docs/background_running.md) | systemd, tmux, and built-in background mode |
| [External programs](https://github.com/CN-BI5UNF/KarenBot-backend/blob/v2.1.0-alpha/docs/external_programs.md) | Startup, probing, restart, and shutdown policies |
| [Protocols](https://github.com/CN-BI5UNF/KarenBot-backend/tree/v2.1.0-alpha/docs/protocols) | OneBot 11, Telegram, QQ Official Bot, Satori |
| [Feature guides](https://github.com/CN-BI5UNF/KarenBot-backend/tree/v2.1.0-alpha/docs/feature_guides) | Vision, TTS, web search, weather, RAG, knowledge, slang |

When filing an issue, please include:

- your operating system and version;
- how you installed KarenBot (installer / source / upgrading an older version);
- relevant logs (remove tokens, API keys, chat content, and other private data first);
- reproduction steps.

## Contributing

Issues and pull requests are welcome. Please keep tokens, API keys, chat logs, and other private data out of reports and commits, and include reproduction steps where possible.

## License

Apache-2.0. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE) for details.
