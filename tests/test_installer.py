"""Linux 安装引导器的本地/离线测试。"""

from __future__ import annotations

import http.server
import io
import socketserver
import tarfile
import threading
from pathlib import Path

import pytest

from installer import karen_install as installer


@pytest.fixture
def local_server(tmp_path):
    payload = b"karen-installer-test" * 4096
    file_path = tmp_path / "asset.bin"
    file_path.write_bytes(payload)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(tmp_path), **kwargs)

        def log_message(self, *_args):
            return

    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}/asset.bin", payload
        finally:
            server.shutdown()


def test_mirrored_url_direct_and_prefix():
    direct = {"name": "direct", "kind": "direct"}
    prefix = {"name": "p", "kind": "prefix", "prefix": "https://mirror.test/https://github.com"}
    url = "https://github.com/owner/repo/archive/v1.tar.gz"
    assert installer.mirrored_url(url, direct) == url
    assert installer.mirrored_url(url, prefix) == (
        "https://mirror.test/https://github.com/owner/repo/archive/v1.tar.gz"
    )


def test_download_from_local_server(local_server, tmp_path, monkeypatch):
    url, payload = local_server
    monkeypatch.setattr(
        installer, "_MIRROR_CACHE", [{"name": "direct", "kind": "direct", "enabled": True}]
    )
    destination = tmp_path / "downloaded.bin"
    installer.download(url, destination)
    assert destination.read_bytes() == payload


def test_download_verifies_sha256(local_server, tmp_path, monkeypatch):
    url, _payload = local_server
    monkeypatch.setattr(
        installer, "_MIRROR_CACHE", [{"name": "direct", "kind": "direct", "enabled": True}]
    )
    destination = tmp_path / "bad.bin"
    with pytest.raises(SystemExit):
        installer.download(url, destination, expected_sha256="0" * 64)


def test_safe_tar_extract_rejects_traversal(tmp_path):
    archive = tmp_path / "evil.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        data = b"x"
        info = tarfile.TarInfo("../evil.txt")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    with pytest.raises(SystemExit):
        installer._safe_tar_extract(archive, tmp_path / "out")


def test_find_app_root(tmp_path):
    root = tmp_path / "bundle"
    (root / "backend").mkdir(parents=True)
    (root / "gui").mkdir()
    assert installer._find_app_root(root) == root


def test_install_local_source_builds_launchers(tmp_path):
    source = tmp_path / "source"
    (source / "backend").mkdir(parents=True)
    (source / "gui").mkdir()
    (source / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    install_dir = tmp_path / "install"
    installer.install(
        frontend="gui",
        install_dir=install_dir,
        source_dir=source,
        archive=None,
        venv=Path(__file__).resolve().parents[1] / ".venv",
        skip_deps=True,
        create_shortcut=False,
        download_fonts=False,
    )
    assert (install_dir / "app" / "backend").is_dir()
    launcher = (install_dir / "launch-gui.sh").read_text(encoding="utf-8")
    assert f"cd '{install_dir / 'app'}'" in launcher
    assert "-m gui" in launcher


def test_install_fonts_writes_fontconfig(tmp_path, monkeypatch):
    root = tmp_path / "fonts"
    monkeypatch.setattr(installer, "_font_dir", lambda: root)

    def fake_download(url, destination, expected_sha256="", **_kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"font")
        return destination

    monkeypatch.setattr(installer, "download", fake_download)
    installer.install_fonts()
    assert (root / "NotoSansSC-VF.otf").is_file()
    assert (root / "NotoSerifSC-VF.otf").is_file()
    assert (root / "fonts.conf").is_file()


def test_probe_mirrors_returns_failures(local_server):
    url, _payload = local_server
    mirrors = [
        {"name": "direct", "kind": "direct", "enabled": True},
        {
            "name": "broken",
            "kind": "prefix",
            "prefix": "http://127.0.0.1:1",
            "enabled": True,
        },
    ]
    results = installer.probe_mirrors(url, mirrors, timeout=2)
    assert len(results) == 2
    assert any(item.get("ok") for item in results)
    assert any(not item.get("ok") for item in results)


def test_venv_python_layout(monkeypatch):
    venv = Path("/tmp/karen-venv")
    monkeypatch.setattr(installer, "IS_WINDOWS", False)
    assert installer._venv_python(venv) == venv / "bin" / "python"
    monkeypatch.setattr(installer, "IS_WINDOWS", True)
    assert installer._venv_python(venv) == venv / "Scripts" / "python.exe"


def test_install_archive_with_prebuilt_executable(tmp_path):
    import zipfile

    archive = tmp_path / "KarenBot-Windows.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("KarenBot-GUI.exe", b"fake-exe")
        zf.writestr("runtime/data.txt", "ok")
    install_dir = tmp_path / "install"
    installer.install(
        frontend="gui",
        install_dir=install_dir,
        source_dir=None,
        archive=archive,
        venv=None,
        skip_deps=False,
        create_shortcut=False,
        download_fonts=False,
    )
    app = install_dir / "app"
    assert (app / "KarenBot-GUI.exe").is_file()
    assert (app / "KarenBot-GUI.exe").stat().st_mode & 0o111
    assert not (install_dir / "venv").exists()
    launcher = (install_dir / "launch-gui.sh").read_text(encoding="utf-8")
    assert "KarenBot-GUI.exe" in launcher
    manifest = (app / "modules.json").read_text(encoding="utf-8")
    assert '"installer": "prebuilt-archive"' in manifest


def test_windows_shortcut_script_quotes_paths():
    script = installer._windows_shortcut_script(
        Path(r"C:\Program Files\KarenBot\KarenBot-GUI.exe"),
        Path(r"C:\Users\O'Brien\KarenBot"),
        "KarenBot GUI.lnk",
        Path(r"C:\Program Files\KarenBot\KarenBot-GUI.exe"),
    )
    assert "GetFolderPath('Desktop')" in script
    assert "O''Brien" in script
    assert "New-Object -ComObject WScript.Shell" in script


def test_install_local_source_writes_manifest(tmp_path):
    source = tmp_path / "source"
    (source / "backend").mkdir(parents=True)
    (source / "gui").mkdir()
    install_dir = tmp_path / "install"
    installer.install(
        frontend="gui",
        install_dir=install_dir,
        source_dir=source,
        archive=None,
        venv=Path(__file__).resolve().parents[1] / ".venv",
        skip_deps=True,
        create_shortcut=False,
        download_fonts=False,
    )
    manifest = (install_dir / "app" / "modules.json").read_text(encoding="utf-8")
    assert '"installer": "local-source"' in manifest


def test_windows_launchers_use_scripts_python(monkeypatch, tmp_path):
    monkeypatch.setattr(installer, "IS_WINDOWS", True)
    app = tmp_path / "app"
    app.mkdir()
    venv = tmp_path / "venv"
    installer._write_launchers(tmp_path, app, venv, "gui")
    raw = (tmp_path / "launch-gui.cmd").read_bytes()
    text = raw.decode("utf-8")
    assert "python.exe" in text
    assert "-m gui" in text
    assert b"\r\n" in raw


def test_install_rejects_source_inside_install_dir(tmp_path):
    source = tmp_path / "source"
    (source / "backend").mkdir(parents=True)
    (source / "gui").mkdir()
    install_dir = source / "install-target"
    with pytest.raises(SystemExit):
        installer.install(
            frontend="gui",
            install_dir=install_dir,
            source_dir=source,
            archive=None,
            venv=None,
            skip_deps=True,
            create_shortcut=False,
            download_fonts=False,
        )
