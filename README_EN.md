<div align="center">

# KarenBot

**A chatbot framework that makes virtual characters feel alive**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
[![WebUI](https://img.shields.io/badge/UI-WebUI%20%28FastAPI%29-blueviolet.svg)](#)
[![CI](https://github.com/CN-BI5UNF/KarenBot/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/CN-BI5UNF/KarenBot/actions/workflows/test.yml)

[Quick start](#quick-start) · [karen commands](#karen-commands) · [Upgrading from Debata](#upgrading-from-debata) · [Docs](#docs)

</div>

---

> "A virtual character is not just a program that replies to messages. It is a person with a personality, an inner world, and a life of its own."

KarenBot is a general-purpose chat-agent framework. Give it a persona and it becomes that person.

The project is named **KarenBot** after **Karen**, Plankton's robot girlfriend in SpongeBob SquarePants. The name is community-inspired; this project is not affiliated with Nickelodeon, Paramount, or their official works.

- Repository: <https://github.com/CN-BI5UNF/KarenBot>
- Default branch: `main`
- In-app update branch: `refactor/main`
- Status: `1.0.1-alpha.1` refactor snapshot; interfaces may still change

> **Upstream and license**: KarenBot is derived from [binglang001/Debata_Agent](https://github.com/binglang001/Debata_Agent) and its contributors. Original copyright notices are retained. KarenBot is released under **Apache-2.0**. See [NOTICE](NOTICE).

## Features

- Persona prompts, dynamic state, relationships, and per-persona memory. The persona backend can wake a sleeping/collapsed persona with a WebUI-only "wake-up" line.
- QQ / NapCat integration (private and group chats, send queue).
- Long-term memory and archival without rewriting raw history.
- Multi-turn tool loop: messaging, recall, memory, search, weather, wake-ups, sub-agents.
- Persona character images: upload a gallery of appearances on the Personas page, choose a preview image, inspect them through a read-only virtual knowledge entry, and send them directly as images. The model has no write/delete path for the gallery.
- One merged black/white list page controls inbound policy, whitelist IDs, and blacklist IDs; saving applies both immediately and blacklist still wins.
- WebUI built with FastAPI and dependency-free static assets; model configuration lives in Model Management, and the sidebar collapses to icons.
- Multi-provider support: OpenAI, Anthropic, DeepSeek, GLM, Qwen, Gemini, OpenRouter, custom compatible endpoints; relays can declare a Gemini/Claude/OpenAI vendor for capability lookup.
- Native vision paths for images, complete animated GIFs, and complete videos where the selected main model supports them; standalone vision remains available. Videos are sent as managed data URLs without frame extraction; unsupported models receive a workspace placeholder only.
- On-demand knowledge and group-slang lookup; knowledge supports per-entry sharing, while slang is shared by every persona in the same group. The slang page supports search; AI applications whose term duplicates an existing group entry are auto-rejected and kept visible instead of overwriting it.
- **Chat selection**: the model can temporarily pause ordinary group messages or accept only selected groups. @-mentions still arrive, and private chats are never filtered.
- **Per-group @ triggers**: choose groups that only respond after an @ mention and set a message-count and/or duration window plus a per-group memory cap for filtered messages. The model can call `group_trigger_window` to open, extend, or close transient windows and use `history_limit` to include the latest filtered messages, with at most two LLM-opened groups at once.
- **Two-layer tool routing (experimental)**: `behavior.tool_schema_profile="routed"` exposes core tools plus `list_toolsets` / `load_toolset`; loaded toolsets use compact schemas and `tool_search` remains the per-tool detail layer. State is per conversation, and the default profile stays `compact`.
- **Storage & data**: one page for storage inventory/cache cleanup, context budget, previewed persona runtime cleanup, and local source uninstall, with optional external backup and an independent uninstall helper.
- LLM-managed emoji folder tools plus native QQ face adaptation: inbound faces show Chinese names (e.g. `[流眼泪]` for `[表情5]`) and send tools accept face names.
- Controlled Docker container: command execution, `/workspace` file tools, import/export, and a built-in read-only container file manager (root by default, with a `/workspace` shortcut) with directory navigation and bounded text previews; no network/privileges/non-root by default, with memory, CPU, pids, and storage limits. B named-volume soft quota is the default and needs no administrator; C fixed-size storage is an advanced hard limit. It supports Docker registry-mirror prefixes, one-click prepare/start, and background image pulls. First C-mode enable opens a Linux sudo-password dialog (stdin only, never stored) or a Windows UAC prompt. Windows includes a VHDX setup script (see [container docs](docs/container.md)).
- Bounded summaries, CAS commits, media lifecycle, scoped deletion/recovery, transactional config writes.
- In-app updates from GitHub Releases/tags; source-only updates do not overwrite data.

## Requirements

- Python 3.10+ (CI covers 3.11 and 3.12)
- [uv](https://docs.astral.sh/uv/)
- [NapCat](https://napneko.github.io/guide/start-install) for QQ integration (optional)
- An LLM API key (DeepSeek is a good default for Chinese and cost)
- Linux, Windows, or macOS; headless servers are supported

## Quick start

```bash
git clone https://github.com/CN-BI5UNF/KarenBot.git
cd KarenBot
uv sync
uv run python main.py
```

The WebUI listens on `0.0.0.0:8000` by default. Use `--host 127.0.0.1` for local-only access. The terminal prints the WebUI token; the first launch opens the setup wizard.

Normal launches check the base dependencies declared in `pyproject.toml` before importing the app. Missing or out-of-range packages are installed editable with the running interpreter (`uv pip install --python <interpreter> -e .`, falling back to pip). Optional extras and local-model dependencies are never installed implicitly. Set `KAREN_DISABLE_DEPENDENCY_CHECK=1` to skip the check or `KAREN_DISABLE_DEPENDENCY_INSTALL=1` to check without installing.

For servers or SSH sessions:

```bash
uv run python main.py --no-gui --setup
```

Linux background service:

```bash
bash scripts/install_systemd_user.sh
./karen start
./karen status
./karen log
./karen stop
```

The legacy `./debata` command is kept as a compatibility wrapper during the transition.

Windows:

```powershell
git clone https://github.com/CN-BI5UNF/KarenBot.git
cd KarenBot
uv sync
uv run python main.py --host 127.0.0.1 --port 8000
```

The Windows data directory defaults to `%LOCALAPPDATA%\KarenBot`. Docker Desktop containers are supported; the C-mode VHDX script still needs real-Windows validation, and Windows service integration is planned for a later phase. Complete GIF/video input is enabled only for main models verified in the capability table (currently Qwen3.6-Plus, Qwen3-VL, and OpenRouter Gemini).

## karen commands

| Command | Description |
|---|---|
| `karen start` | Start; installs the systemd user service on first run |
| `karen stop` | Stop the service |
| `karen restart` | Restart the service |
| `karen status` | Show status |
| `karen log` | Follow logs |
| `karen enable` | Enable boot autostart and start now |
| `karen disable` | Disable boot autostart |
| `karen install` | Install the service without starting |
| `karen uninstall` | Uninstall the service |
| `karen help` | Show help |

Compatibility: the old `debata` command, `DEBATA_*` environment variables, `debata-agent` service name, and legacy data directory remain recognized for at least one release. Old data is never deleted automatically.

## Upgrading from Debata

1. Back up the old data directory (`~/.local/share/Debata_Agent` or `%LOCALAPPDATA%\Debata_Agent`).
2. Update the source and start `karen` or `python main.py`.
3. KarenBot prefers its new data directory. If it does not exist and the legacy directory does, KarenBot keeps using the legacy directory and prints a migration notice.
4. Legacy `debata`, `DEBATA_DATA_ROOT`, `DEBATA_WEBUI_TOKEN`, and `DEBATA_DISABLE_TREND_RESEARCH` are still recognized.
5. An old `persona.active: debata` is migrated to `deepseek` (or the default persona if deepseek is unavailable) and written back with a config backup.

Migration is copy-first: the old directory is preserved, and failures fall back to it.

## Data directory

- Linux: `~/.local/share/KarenBot/instances/default/`
- Windows: `%LOCALAPPDATA%\KarenBot\instances\default/`
- Legacy: `~/.local/share/Debata_Agent/instances/default/`

`KAREN_DATA_ROOT` overrides the data root; the legacy `DEBATA_DATA_ROOT` is still accepted. Never commit `config.yaml`, `secrets.enc`, RSA private keys, or WebUI/NapCat tokens.

## Testing

```bash
KAREN_DISABLE_TREND_RESEARCH=1 .venv/bin/python -m pytest -q --ignore=tests/test_kv_cache_real.py
.venv/bin/python -m ruff check .
git diff --check
```

CI runs Ubuntu/Windows × Python 3.11/3.12.

## Documentation

- [Features](docs/features.md)
- [Architecture](docs/architecture.md)
- [Background running](docs/background_running.md)
- [Destructive data operations](docs/destructive_admin.md)
- [Persona writing guide](docs/persona_writing_guide.md)
- [Provider development](docs/provider_development.md)

## Security and privacy

- Web content, knowledge/slang entries, and emoji URLs are untrusted external content.
- Remote media downloads enforce public-IP resolution, redirect and size limits, and reject credential URLs.
- Updates only use trusted sources and roll back source changes on failure.
- Never expose configuration, secrets, RSA keys, or tokens.
- Docker containers are resource/file isolation, not an absolute security boundary; keep networking, capabilities, and host mounts disabled by default.

## Known limitations

- Development snapshot: interfaces may change; production migration, restore drills, and launcher installation are not performed automatically.
- Toolset routing is experimental and off by default; dynamic toolset loading can change the tools block and may reduce KV-cache hits. Complete GIF/video input is limited to verified main models (currently Qwen3.6-Plus, Qwen3-VL, and OpenRouter Gemini). Docker C-mode storage requires a one-time administrator setup (Linux sudo-password dialog / Windows UAC), and the Windows VHDX script is pending real-machine validation.
- The legacy data directory is used by default until an explicit migration.
- Without a connected NapCat, QQ messages will not flow.

## License and attribution

- Apache-2.0; see [LICENSE](LICENSE).
- Upstream: [binglang001/Debata_Agent](https://github.com/binglang001/Debata_Agent) and its contributors. Original copyright remains with the upstream authors.
- Rename/refactor notice: [NOTICE](NOTICE).
- The name "Karen" refers to a SpongeBob character; all character rights belong to their respective owners. This project claims no official affiliation.
