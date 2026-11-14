#!/usr/bin/env python3
"""KarenBot Linux 安装引导器（CLI 核心）。

设计约束：
- 安装器本身不内置任何应用包；只负责选择来源、下载、校验、解压、建 venv、
  创建快捷方式。
- 支持 ``--source-dir`` / ``--archive`` 做离线/本地测试，不依赖 GitHub。
- 真正的 Release 下载流程后续接入现有 backend/gui/webui 模块仓库。
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn
from xml.sax.saxutils import escape as xml_escape

APP_NAME = "KarenBot"
IS_WINDOWS = os.name == "nt"
if IS_WINDOWS:
    _LOCALAPPDATA = Path(
        os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
    )
    DEFAULT_INSTALL_DIR = _LOCALAPPDATA / "Programs" / "KarenBot"
else:
    DEFAULT_INSTALL_DIR = Path.home() / ".local" / "opt" / "karenbot"
def _resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    bundled = base / name
    if bundled.is_file():
        return bundled
    return Path(__file__).with_name(name)


MIRRORS_FILE = _resource_path("mirrors.json")
USER_AGENT = "KarenBot-Installer/0.1"
PROBE_BYTES = 256 * 1024
FONT_SOURCES = (
    {
        "name": "NotoSansSC-VF.otf",
        "url": "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/Variable/OTF/Subset/NotoSansSC-VF.otf",
        "sha256": "d13ed01ec8aa45d6178999b648e96fb92150683e9f8e2a581f2acf208dcbe44b",
    },
    {
        "name": "NotoSerifSC-VF.otf",
        "url": "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Serif/Variable/OTF/Subset/NotoSerifSC-VF.otf",
        "sha256": "71b4d3ded2d90ff43bb75a4e48cdbe170f0b8d5486dc89ff87f2a1728b56da64",
    },
)
_MIRROR_CACHE: list[dict[str, Any]] | None = None
_LOG_SINK: Callable[[str], None] | None = None
_PROGRESS_SINK: Callable[[int, int | None], None] | None = None


class InstallFailure(SystemExit):
    """安装失败；保留 ``SystemExit`` 兼容 CLI 和既有测试。"""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(code)
        self.message = message


class InstallCancelled(Exception):
    """用户在 GUI/CLI 中取消安装。"""


def set_log_sink(sink: Callable[[str], None] | None) -> None:
    """GUI 用：把安装日志转发到 UI；None 恢复 stdout。"""
    global _LOG_SINK
    _LOG_SINK = sink


def set_progress_sink(sink: Callable[[int, int | None], None] | None) -> None:
    """GUI 用：下载进度 (已下载字节, 总字节或 None)。"""
    global _PROGRESS_SINK
    _PROGRESS_SINK = sink


def log(message: str) -> None:
    line = f"[karen-install] {message}"
    sink = _LOG_SINK
    if sink is not None:
        try:
            sink(line)
        except Exception:  # noqa: BLE001 - UI 已退出时不能影响安装
            pass
        return
    stream = sys.stdout
    if stream is not None:
        try:
            print(line, file=stream, flush=True)
        except Exception:  # noqa: BLE001 - windowed 冻结版可能没有 stdout
            pass


def fail(message: str, code: int = 1) -> NoReturn:
    text = f"[karen-install] 错误：{message}"
    sink = _LOG_SINK
    if sink is not None:
        try:
            sink(text)
        except Exception:  # noqa: BLE001
            pass
    else:
        stream = sys.stderr
        if stream is not None:
            try:
                print(text, file=stream, flush=True)
            except Exception:  # noqa: BLE001
                pass
    raise InstallFailure(message, code)


def _check_cancel(cancel_event: Any | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise InstallCancelled()


def _emit_progress(done: int, total: int | None) -> None:
    sink = _PROGRESS_SINK
    if sink is None:
        return
    try:
        sink(done, total)
    except Exception:  # noqa: BLE001
        pass


def _creation_flags() -> int:
    """GUI 冻结版在 Windows 上不要为 pip/venv 弹黑框。"""
    if IS_WINDOWS and getattr(sys, "frozen", False):
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return 0


def run(command: list[str], *, cwd: Path | None = None) -> None:
    log("执行：" + " ".join(command))
    subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        check=True,
        creationflags=_creation_flags(),
    )


def load_mirrors() -> list[dict[str, Any]]:
    global _MIRROR_CACHE
    if _MIRROR_CACHE is not None:
        return _MIRROR_CACHE
    try:
        data = json.loads(MIRRORS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log(f"读取镜像列表失败，使用 GitHub 直连：{exc}")
        _MIRROR_CACHE = [{"name": "direct", "kind": "direct", "enabled": True}]
        return _MIRROR_CACHE
    mirrors = [
        item
        for item in data.get("mirrors", [])
        if isinstance(item, dict) and item.get("enabled", True)
    ]
    _MIRROR_CACHE = mirrors or [{"name": "direct", "kind": "direct", "enabled": True}]
    return _MIRROR_CACHE


def mirrored_url(url: str, mirror: dict[str, Any]) -> str:
    if mirror.get("kind") != "prefix":
        return url
    prefix = str(mirror.get("prefix") or "").rstrip("/")
    if not prefix:
        return url
    if prefix.endswith("https://github.com"):
        if url.startswith("https://github.com"):
            return prefix + url[len("https://github.com") :]
        return prefix + "/" + url.split("://", 1)[-1]
    return prefix + "/" + url


def _request(url: str, *, headers: dict[str, str] | None = None, timeout: float = 15) -> urllib.request.Request:
    values = {"User-Agent": USER_AGENT}
    if headers:
        values.update(headers)
    return urllib.request.Request(url, headers=values)


def probe_mirror(url: str, mirror: dict[str, Any], *, timeout: float = 10) -> dict[str, Any]:
    target = mirrored_url(url, mirror)
    started = time.perf_counter()
    try:
        request = _request(
            target,
            headers={"Range": f"bytes=0-{PROBE_BYTES - 1}"},
            timeout=timeout,
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            first_byte = time.perf_counter() - started
            data = response.read(PROBE_BYTES)
        elapsed = max(time.perf_counter() - started, 0.001)
        speed = len(data) / elapsed
        return {
            "ok": True,
            "mirror": mirror.get("name", "?"),
            "url": target,
            "latency": first_byte,
            "bytes": len(data),
            "elapsed": elapsed,
            "speed": speed,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "mirror": mirror.get("name", "?"),
            "url": target,
            "error": f"{type(exc).__name__}: {exc}",
            "speed": 0.0,
            "latency": 999.0,
        }


def probe_mirrors(
    url: str, mirrors: list[dict[str, Any]], *, timeout: float = 10
) -> list[dict[str, Any]]:
    """并发探测所有镜像，返回完整结果（含失败项），供 GUI 表格展示。"""
    if not mirrors:
        return []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(8, len(mirrors))
    ) as pool:
        return list(
            pool.map(lambda item: probe_mirror(url, item, timeout=timeout), mirrors)
        )


def rank_mirrors(url: str, mirrors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    log(f"测速 {url}")
    results = probe_mirrors(url, mirrors)
    good = [item for item in results if item.get("ok")]
    good.sort(key=lambda item: (-item["speed"], item["latency"]))
    for item in results:
        if item.get("ok"):
            log(
                f"  {item['mirror']}: {item['speed'] / 1024:.1f} KB/s, "
                f"首字节 {item['latency']:.2f}s"
            )
        else:
            log(f"  {item['mirror']}: 失败 {item.get('error')}")
    return good


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(
    url: str,
    destination: Path,
    *,
    expected_sha256: str = "",
    cancel_event: Any | None = None,
    ranked: list[dict[str, Any]] | None = None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    candidates = ranked if ranked is not None else rank_mirrors(url, load_mirrors())
    if not candidates:
        fail("所有镜像都不可用；可以检查网络或手动指定 --mirror direct")
    errors: list[str] = []
    for candidate in candidates:
        target = candidate["url"]
        temp = destination.with_suffix(destination.suffix + ".part")
        try:
            _check_cancel(cancel_event)
            log(f"下载 {target}")
            with urllib.request.urlopen(
                _request(target), timeout=30
            ) as response, temp.open("wb") as handle:
                total = 0
                length = response.headers.get("Content-Length")
                expected_total = int(length) if length and length.isdigit() else None
                _emit_progress(0, expected_total)
                last_report = 0.0
                while True:
                    _check_cancel(cancel_event)
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    total += len(chunk)
                    _emit_progress(total, expected_total)
                    now = time.monotonic()
                    if now - last_report >= 1.0:
                        log(f"  已下载 {total / 1024 / 1024:.1f} MB")
                        last_report = now
            if expected_sha256:
                actual = sha256_file(temp)
                if actual.lower() != expected_sha256.lower():
                    temp.unlink(missing_ok=True)
                    errors.append(f"{candidate['mirror']}: SHA256 不匹配")
                    continue
            temp.replace(destination)
            log(
                f"下载完成：{destination}"
                f"（{destination.stat().st_size / 1024 / 1024:.1f} MB）"
            )
            return destination
        except InstallCancelled:
            temp.unlink(missing_ok=True)
            raise
        except Exception as exc:  # noqa: BLE001
            temp.unlink(missing_ok=True)
            errors.append(f"{candidate['mirror']}: {type(exc).__name__}: {exc}")
    fail("下载失败：\n" + "\n".join(errors))


def _safe_tar_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with tarfile.open(archive, "r:*") as tar:
        for member in tar.getmembers():
            target = (destination / member.name).resolve()
            if target != root and root not in target.parents:
                fail(f"压缩包包含越界路径：{member.name}")
            if member.issym() or member.islnk():
                fail(f"压缩包包含链接，拒绝解压：{member.name}")
            if member.isdev():
                fail(f"压缩包包含设备文件，拒绝解压：{member.name}")
        tar.extractall(destination)


def _safe_zip_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            target = (destination / info.filename).resolve()
            if target != root and root not in target.parents:
                fail(f"压缩包包含越界路径：{info.filename}")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                fail(f"压缩包包含符号链接，拒绝解压：{info.filename}")
        zf.extractall(destination)


def extract_archive(archive: Path, destination: Path) -> None:
    if archive.suffix.lower() in {".zip"}:
        _safe_zip_extract(archive, destination)
    else:
        _safe_tar_extract(archive, destination)


_PREBUILT_NAMES = {
    "gui": ("karenbot.exe", "karenbot-gui.exe", "karen-gui.exe"),
    "webui": ("karenbot.exe", "karenbot-webui.exe", "karen-webui.exe"),
}


def _prebuilt_executable(app_root: Path, frontend: str | None = None) -> Path | None:
    """识别预构建应用包（Windows .exe / Linux 无后缀可执行文件）。"""
    if not app_root.is_dir():
        return None
    names = set(_PREBUILT_NAMES.get(frontend or "", ()))
    names.update(_PREBUILT_NAMES["gui"])
    names.update(_PREBUILT_NAMES["webui"])
    for path in app_root.iterdir():
        if not path.is_file():
            continue
        lowered = path.name.casefold()
        if lowered in names:
            return path
        if IS_WINDOWS and lowered.endswith(".exe"):
            stem = lowered[:-4]
            if stem in {name[:-4] for name in names}:
                return path
    return None


def _find_app_root(directory: Path) -> Path:
    candidates = [directory, *[p for p in directory.iterdir() if p.is_dir()]]
    for candidate in candidates:
        if (candidate / "backend").is_dir() and (
            (candidate / "gui").is_dir() or (candidate / "webui").is_dir()
        ):
            return candidate
        if _prebuilt_executable(candidate) is not None:
            return candidate
    fail("安装包中找不到 backend/ + gui|webui/，也没有可识别的 KarenBot 可执行文件")


_IGNORE = shutil.ignore_patterns(
    ".git",
    ".venv",
    "data",
    "__pycache__",
    "*.pyc",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".karen-run",
    ".debata-run",
    "build",
    "dist",
    "release",
    "module_backups",
    "backups",
    "*.log",
)


def _validate_frontend(app_root: Path, frontend: str) -> None:
    required = ["backend"] + (["gui"] if frontend == "gui" else ["webui"])
    missing = [name for name in required if not (app_root / name).is_dir()]
    if missing:
        fail(f"安装源缺少目录：{', '.join(missing)}")


def _venv_python(venv: Path) -> Path:
    if IS_WINDOWS:
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _base_python() -> Path:
    """冻结版 exe 不能 `-m venv` 自己，必须找系统 Python。"""
    if not getattr(sys, "frozen", False):
        return Path(sys.executable)
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found:
            return Path(found)
    fail(
        "当前是打包版安装器，但系统找不到 Python 3.10+。\n"
        "请先安装 Python，或使用包含完整运行环境的预构建安装包。"
    )


def _create_venv(venv: Path, *, frontend: str) -> None:
    if venv.exists():
        log(f"复用已有 venv：{venv}")
        return
    base = _base_python()
    uv = shutil.which("uv")
    if uv:
        command = [uv, "venv", "--python", str(base), str(venv)]
        if frontend == "gui" and not IS_WINDOWS:
            command.insert(2, "--system-site-packages")
        run(command)
        return
    command = [str(base), "-m", "venv", str(venv)]
    if frontend == "gui" and not IS_WINDOWS:
        command.insert(3, "--system-site-packages")
    run(command)


def _install_dependencies(venv: Path, app_root: Path) -> None:
    python = _venv_python(venv)
    uv = shutil.which("uv")
    if uv:
        run([uv, "pip", "install", "--python", str(python), "-e", str(app_root)])
    else:
        run([str(python), "-m", "pip", "install", "-e", str(app_root)])


def _check_gui_runtime(venv: Path) -> None:
    if IS_WINDOWS:
        fail(
            "Windows 源码安装暂不支持原生 GUI：GTK4/PyGObject 需要预构建运行环境。\n"
            "请改用 WebUI，或使用包含 GTK4 运行时的 Windows 预构建安装包。"
        )
    python = _venv_python(venv)
    result = subprocess.run(
        [
            str(python),
            "-c",
            "import gi; gi.require_version('Gtk','4.0'); gi.require_version('Adw','1')",
        ],
        capture_output=True,
        text=True,
        creationflags=_creation_flags(),
    )
    if result.returncode != 0:
        fail(
            "GUI 需要系统 GTK4/libadwaita/PyGObject。Debian/Ubuntu 请安装：\n"
            "  sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1\n"
            f"检测输出：{result.stderr.strip()}"
        )


def _font_dir() -> Path:
    if IS_WINDOWS:
        base = Path(
            os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        )
        return base / "KarenBot" / "fonts"
    data_home = Path(
        os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    )
    return data_home / "KarenBot" / "fonts"


def _write_fontconfig(root: Path) -> None:
    cache = root / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    if IS_WINDOWS:
        windows_root = str(
            os.environ.get("WINDIR") or r"C:\Windows"
        ).replace("\\", "/")
        windows_fonts = Path(windows_root) / "Fonts"
        include = f"  <dir>{xml_escape(windows_fonts.as_posix())}</dir>\n"
    else:
        include = '  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>\n'
    (root / "fonts.conf").write_text(
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n'
        "<fontconfig>\n"
        f"{include}"
        f"  <dir>{xml_escape(root.as_posix())}</dir>\n"
        f"  <cachedir>{xml_escape(cache.as_posix())}</cachedir>\n"
        "</fontconfig>\n",
        encoding="utf-8",
    )


def install_fonts(cancel_event: Any | None = None) -> None:
    root = _font_dir()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log(f"字体目录不可写，跳过字体下载：{exc}")
        return
    for item in FONT_SOURCES:
        _check_cancel(cancel_event)
        target = root / item["name"]
        if target.is_file():
            log(f"字体已存在：{item['name']}")
            continue
        try:
            download(
                item["url"],
                target,
                expected_sha256=item["sha256"],
                cancel_event=cancel_event,
            )
        except InstallCancelled:
            raise
        except SystemExit:
            log(f"字体下载失败（可选）：{item['name']}")
    _write_fontconfig(root)
    log(f"字体目录：{root}")


def _write_launchers(
    install_dir: Path,
    app_root: Path,
    venv: Path,
    frontend: str,
    *,
    prebuilt_exe: Path | None = None,
) -> None:
    if IS_WINDOWS:
        _write_windows_launchers(
            install_dir, app_root, venv, frontend, prebuilt_exe=prebuilt_exe
        )
        return
    if prebuilt_exe is not None:
        gui_body = (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"cd {str(app_root)!r}\n"
            f"exec {str(prebuilt_exe)!r} \"$@\"\n"
        )
        webui_body = gui_body
    else:
        gui_body = (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"cd {str(app_root)!r}\n"
            f"exec {str(_venv_python(venv))!r} -m gui \"$@\"\n"
        )
        webui_body = (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"cd {str(app_root)!r}\n"
            f"exec {str(_venv_python(venv))!r} main.py --host 127.0.0.1 --port 8000 \"$@\"\n"
        )
    gui = install_dir / "launch-gui.sh"
    gui.write_text(gui_body, encoding="utf-8")
    webui = install_dir / "launch-webui.sh"
    webui.write_text(webui_body, encoding="utf-8")
    for path in (gui, webui):
        path.chmod(0o755)


def _write_windows_launchers(
    install_dir: Path,
    app_root: Path,
    venv: Path,
    frontend: str,
    *,
    prebuilt_exe: Path | None = None,
) -> None:
    if prebuilt_exe is not None:
        gui_body = (
            "@echo off\r\n"
            f'cd /d "{app_root}"\r\n'
            f'"{prebuilt_exe}" %*\r\n'
        )
        webui_body = gui_body
    else:
        python = _venv_python(venv)
        gui_body = (
            "@echo off\r\n"
            f'cd /d "{app_root}"\r\n'
            f'"{python}" -m gui %*\r\n'
        )
        webui_body = (
            "@echo off\r\n"
            f'cd /d "{app_root}"\r\n'
            f'"{python}" main.py --host 127.0.0.1 --port 8000 %*\r\n'
        )
    (install_dir / "launch-gui.cmd").write_text(
        gui_body, encoding="utf-8", newline=""
    )
    (install_dir / "launch-webui.cmd").write_text(
        webui_body, encoding="utf-8", newline=""
    )


def launch_target(install_dir: Path, frontend: str) -> Path:
    suffix = ".cmd" if IS_WINDOWS else ".sh"
    return install_dir / f"launch-{frontend}{suffix}"


def _powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _windows_shortcut_script(
    target: Path, working_dir: Path, name: str, icon: Path | None = None
) -> str:
    icon_line = ""
    if icon is not None:
        icon_line = (
            f"$s.IconLocation = {_powershell_quote(str(icon))}\n"
        )
    return (
        "$ErrorActionPreference = 'Stop'\n"
        "$ws = New-Object -ComObject WScript.Shell\n"
        "$dirs = @(\n"
        "  [Environment]::GetFolderPath('Programs'),\n"
        "  [Environment]::GetFolderPath('Desktop')\n"
        ")\n"
        "foreach ($dir in $dirs) {\n"
        "  if (-not $dir) { continue }\n"
        f"  $path = Join-Path $dir {_powershell_quote(name)}\n"
        "  $s = $ws.CreateShortcut($path)\n"
        f"  $s.TargetPath = {_powershell_quote(str(target))}\n"
        f"  $s.WorkingDirectory = {_powershell_quote(str(working_dir))}\n"
        f"{icon_line}"
        "  $s.Description = 'KarenBot'\n"
        "  $s.Save()\n"
        "}\n"
    )


def _install_shortcut(
    install_dir: Path, frontend: str, *, target: Path | None = None
) -> Path | None:
    if IS_WINDOWS:
        return _install_windows_shortcut(install_dir, frontend, target=target)
    applications = Path.home() / ".local" / "share" / "applications"
    applications.mkdir(parents=True, exist_ok=True)
    exec_target = target or launch_target(install_dir, frontend)
    if frontend == "gui":
        name = "karenbot-gui.desktop"
        entry = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=KarenBot GUI\n"
            "Comment=KarenBot 原生 GTK4 控制台\n"
            f"Exec={exec_target}\n"
            f"Path={install_dir}\n"
            "Icon=applications-system\n"
            "Terminal=false\n"
            "Categories=Utility;Chat;\n"
            "StartupNotify=true\n"
        )
    else:
        name = "karenbot-webui.desktop"
        entry = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=KarenBot WebUI\n"
            "Comment=启动 KarenBot WebUI\n"
            f"Exec={exec_target}\n"
            f"Path={install_dir}\n"
            "Icon=applications-system\n"
            "Terminal=true\n"
            "Categories=Utility;Chat;\n"
            "StartupNotify=false\n"
        )
    path = applications / name
    path.write_text(entry, encoding="utf-8")
    path.chmod(0o644)
    log(f"桌面快捷方式：{path}")
    return path


def _install_windows_shortcut(
    install_dir: Path, frontend: str, *, target: Path | None = None
) -> Path | None:
    exec_target = target or launch_target(install_dir, frontend)
    name = "KarenBot GUI.lnk" if frontend == "gui" else "KarenBot WebUI.lnk"
    icon = exec_target if exec_target.suffix.lower() == ".exe" else None
    script = _windows_shortcut_script(exec_target, install_dir, name, icon)
    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            check=True,
            capture_output=True,
            text=True,
            creationflags=_creation_flags(),
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        log(f"创建 Windows 快捷方式失败（可手动创建）：{exc}")
        return None
    log(f"已创建开始菜单/桌面快捷方式：{name}")
    return None


def _write_modules_manifest(
    app_root: Path,
    frontend: str,
    *,
    installer: str = "local-source",
    components: dict[str, Any] | None = None,
) -> None:
    manifest = app_root / "modules.json"
    if manifest.is_file() and components is None:
        return
    manifest.write_text(
        json.dumps(
            {
                "schema": 1,
                "frontend": frontend,
                "components": components or {},
                "installer": installer,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def install(
    *,
    frontend: str,
    install_dir: Path,
    source_dir: Path | None,
    archive: Path | None,
    venv: Path | None,
    skip_deps: bool,
    create_shortcut: bool,
    download_fonts: bool,
    cancel_event: Any | None = None,
) -> Path:
    _check_cancel(cancel_event)
    install_dir = install_dir.expanduser().resolve()
    install_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".karen-install-", dir=str(install_dir)))
    try:
        installer_kind = "local-source"
        if source_dir is not None:
            source = source_dir.expanduser().resolve()
            if not source.is_dir():
                fail(f"源码目录不存在：{source}")
            if (
                source == install_dir
                or source in install_dir.parents
                or install_dir in source.parents
            ):
                fail("安装目录和源码目录不能互相包含；请换一个安装目录。")
            log(f"复制源码：{source}")
            shutil.copytree(source, staging / "app", ignore=_IGNORE)
        elif archive is not None:
            installer_kind = "local-archive"
            archive = archive.expanduser().resolve()
            if not archive.is_file():
                fail(f"压缩包不存在：{archive}")
            log(f"解压安装包：{archive}")
            extract_root = staging / "extract"
            extract_archive(archive, extract_root)
            app_root = _find_app_root(extract_root)
            shutil.copytree(app_root, staging / "app", ignore=_IGNORE)
        else:
            fail("当前版本先支持 --source-dir / --archive；Release 下载流程待接入模块仓库")
        _check_cancel(cancel_event)
        app_root = staging / "app"
        prebuilt = _prebuilt_executable(app_root, frontend)
        if prebuilt is None:
            _validate_frontend(app_root, frontend)
        else:
            installer_kind = "prebuilt-archive"
            log(f"检测到预构建应用：{prebuilt.name}，跳过 venv/依赖安装")
            skip_deps = True
        _write_modules_manifest(app_root, frontend, installer=installer_kind)

        target_app = install_dir / "app"
        old_app = install_dir / "app.old"
        if old_app.exists():
            shutil.rmtree(old_app, ignore_errors=True)
        if target_app.exists():
            target_app.rename(old_app)
        app_root.rename(target_app)

        prebuilt_target: Path | None = None
        if prebuilt is not None:
            prebuilt_target = target_app / prebuilt.name
            if not prebuilt_target.is_file():
                prebuilt_target = _prebuilt_executable(target_app, frontend)
            if prebuilt_target is not None and not IS_WINDOWS:
                # zip 解压通常不保留 Unix 可执行位。
                prebuilt_target.chmod(
                    prebuilt_target.stat().st_mode | 0o755
                )

        target_venv = (
            venv.expanduser().resolve() if venv else install_dir / "venv"
        )
        _check_cancel(cancel_event)
        if not skip_deps:
            _create_venv(target_venv, frontend=frontend)
            _install_dependencies(target_venv, target_app)
            if frontend == "gui":
                _check_gui_runtime(target_venv)
        else:
            log("跳过依赖安装（--skip-deps）")
        if download_fonts:
            install_fonts(cancel_event=cancel_event)
        _check_cancel(cancel_event)
        _write_launchers(
            install_dir,
            target_app,
            target_venv,
            frontend,
            prebuilt_exe=prebuilt_target,
        )
        shortcut_target = prebuilt_target or launch_target(install_dir, frontend)
        if create_shortcut:
            _install_shortcut(install_dir, frontend, target=shortcut_target)
        if old_app.exists():
            shutil.rmtree(old_app, ignore_errors=True)
        log(f"安装完成：{install_dir}")
        log(f"启动：{shortcut_target}")
        return install_dir
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def interactive_frontend(current: str | None) -> str:
    if current in {"gui", "webui"}:
        return current
    if not sys.stdin.isatty():
        return "gui"
    print("选择界面：")
    print("  1. 原生 GUI（GTK4，推荐桌面用户）")
    print("  2. WebUI（浏览器控制台）")
    choice = input("请输入 1/2 [1]：").strip() or "1"
    return "webui" if choice == "2" else "gui"


def installer_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return Path(__file__).resolve()


def self_delete_installer() -> None:
    path = installer_path()
    if IS_WINDOWS and getattr(sys, "frozen", False):
        # Windows 不能删除正在运行的 exe，交给退出后的 cmd 延迟处理。
        command = f'timeout /t 2 /nobreak >nul & del /f /q "{path}"'
        try:
            subprocess.Popen(
                ["cmd", "/c", command],
                creationflags=_creation_flags(),
                close_fds=True,
            )
            log("安装器将在退出后自删除")
        except OSError as exc:
            log(f"安装器自删除安排失败（可手动删除）：{exc}")
        return
    try:
        path.unlink()
        log("安装器已自删除")
    except OSError as exc:
        log(f"安装器自删除失败（可手动删除）：{exc}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="karen-install", description="KarenBot 安装引导器"
    )
    parser.add_argument("--frontend", choices=("gui", "webui"))
    parser.add_argument("--dir", default=str(DEFAULT_INSTALL_DIR), help="安装目录")
    parser.add_argument(
        "--source-dir", default="", help="本地源码目录（测试/离线）"
    )
    parser.add_argument(
        "--archive", default="", help="本地 tar/zip 安装包（测试/离线）"
    )
    parser.add_argument("--venv", default="", help="复用已有 venv（测试）")
    parser.add_argument(
        "--skip-deps", action="store_true", help="跳过 venv/依赖安装"
    )
    parser.add_argument(
        "--no-shortcut", action="store_true", help="不创建快捷方式"
    )
    parser.add_argument(
        "--no-fonts", action="store_true", help="不下载 Noto 中文字体"
    )
    parser.add_argument(
        "--self-delete", action="store_true", help="安装完成后删除安装器自身"
    )
    parser.add_argument(
        "--keep-installer", action="store_true", help="安装后保留安装器自身"
    )
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--probe-url", default="", help="只测试镜像速度")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.probe_url:
        rank_mirrors(args.probe_url, load_mirrors())
        return 0
    if args.non_interactive:
        frontend = args.frontend or "gui"
    else:
        frontend = interactive_frontend(args.frontend)
    install_dir = Path(args.dir).expanduser()
    if args.dry_run:
        print(
            json.dumps(
                {
                    "frontend": frontend,
                    "install_dir": str(install_dir),
                    "source_dir": args.source_dir,
                    "archive": args.archive,
                    "venv": args.venv,
                    "skip_deps": args.skip_deps,
                    "download_fonts": not args.no_fonts,
                    "self_delete": args.self_delete,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    install(
        frontend=frontend,
        install_dir=install_dir,
        source_dir=Path(args.source_dir) if args.source_dir else None,
        archive=Path(args.archive) if args.archive else None,
        venv=Path(args.venv) if args.venv else None,
        skip_deps=args.skip_deps,
        create_shortcut=not args.no_shortcut,
        download_fonts=not args.no_fonts,
    )
    should_delete = args.self_delete or (
        getattr(sys, "frozen", False) and not args.keep_installer
    )
    if should_delete:
        self_delete_installer()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
