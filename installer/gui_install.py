#!/usr/bin/env python3
"""KarenBot 安装引导 GUI（Tkinter）。

安装器只需要一个简单的原生向导：不嵌入浏览器、不依赖 GTK4，也不把
额外的浏览器运行时塞进安装包。Tkinter 随 CPython 提供，PyInstaller
可以把它打成 Windows/Linux 单文件。
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

try:
    from . import karen_install as core
except ImportError:  # 直接运行 installer/gui_install.py 或 PyInstaller 冻结时
    import karen_install as core

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from tkinter import font as tkfont
    from tkinter.scrolledtext import ScrolledText
except ImportError as exc:  # pragma: no cover - 缺少 python3-tk 的系统
    tk = None  # type: ignore[assignment]
    filedialog = None  # type: ignore[assignment]
    tkfont = None  # type: ignore[assignment]
    messagebox = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]
    ScrolledText = None  # type: ignore[assignment]
    _TK_ERROR: Exception | None = exc
else:
    _TK_ERROR = None

APP_TITLE = "KarenBot 安装引导"
DEFAULT_PROBE_URL = (
    "https://github.com/CN-BI5UNF/KarenBot/archive/refs/tags/"
    "v1.0.1-alpha.1.tar.gz"
)


def _enable_dpi_awareness() -> None:
    """Windows 高分屏下避免 Tk 被系统拉伸成模糊位图。"""
    if os.name != "nt":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001 - Windows 8.1 以下
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:  # noqa: BLE001
        pass


def _configure_fonts(root: tk.Tk) -> str:
    if tkfont is None:
        return "TkDefaultFont"
    try:
        families = set(tkfont.families(root))
    except tk.TclError:
        return "TkDefaultFont"
    candidates = (
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "Noto Sans CJK SC",
        "Noto Sans SC",
        "Source Han Sans SC",
        "WenQuanYi Micro Hei",
        "WenQuanYi Zen Hei",
        "DejaVu Sans",
    )
    family = next((name for name in candidates if name in families), "TkDefaultFont")
    if family != "TkDefaultFont":
        for name in (
            "TkDefaultFont",
            "TkTextFont",
            "TkMenuFont",
            "TkHeadingFont",
            "TkCaptionFont",
        ):
            try:
                tkfont.nametofont(name).configure(family=family, size=10)
            except tk.TclError:
                pass
    return family


def _print_console(text: str) -> None:
    stream = sys.stdout
    if stream is None:
        return
    try:
        print(text, file=stream, flush=True)
    except Exception:  # noqa: BLE001 - Windows windowed 版没有控制台
        pass


def _open_path(path: Path) -> None:
    if os.name == "nt":
        startfile = getattr(os, "startfile", None)
        if startfile is not None:
            startfile(str(path))
            return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
        return
    subprocess.Popen(["xdg-open", str(path)])


def _run_target(path: Path, cwd: Path) -> None:
    if os.name == "nt":
        _open_path(path)
        return
    subprocess.Popen([str(path)], cwd=str(cwd))


class InstallerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("780x680")
        self.root.minsize(740, 600)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.font_family = _configure_fonts(root)
        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._mirror_worker: threading.Thread | None = None
        self._mirror_window: tk.Toplevel | None = None
        self._mirror_tree: ttk.Treeview | None = None
        self._mirror_button: ttk.Button | None = None
        self._cancel = threading.Event()
        self._installed_dir: Path | None = None
        self._installed_frontend = "gui"
        self._delete_on_close = False
        self._build_vars()
        self._build_ui()
        self._update_source_state()
        self._poll_queue()

    def _build_vars(self) -> None:
        self.source_mode = tk.StringVar(value="source")
        self.source_path = tk.StringVar()
        self.archive_path = tk.StringVar()
        self.frontend = tk.StringVar(value="gui")
        self.install_dir = tk.StringVar(value=str(core.DEFAULT_INSTALL_DIR))
        self.create_shortcut = tk.BooleanVar(value=True)
        self.download_fonts = tk.BooleanVar(value=True)
        self.self_delete = tk.BooleanVar(
            value=bool(getattr(sys, "frozen", False))
        )
        self.mirror_url = tk.StringVar(value=DEFAULT_PROBE_URL)
        self.status = tk.StringVar(value="就绪")

    def _build_ui(self) -> None:
        header = tk.Frame(self.root, bg="#111827", height=66)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text=APP_TITLE,
            bg="#111827",
            fg="#f9fafb",
            font=(self.font_family, 16, "bold"),
        ).pack(anchor="w", padx=18, pady=(10, 0))
        tk.Label(
            header,
            text="选择安装来源与界面版本；安装器本身不内置应用包。",
            bg="#111827",
            fg="#cbd5e1",
            font=(self.font_family, 9),
        ).pack(anchor="w", padx=18, pady=(1, 0))

        body = ttk.Frame(self.root, padding=10)
        body.pack(fill="both", expand=True)

        self._build_source_section(body)
        self._build_frontend_section(body)
        self._build_install_section(body)
        self._build_options_section(body)

        # 先占住底部区域，避免小屏/高 DPI 时按钮被可伸缩的日志框挤出窗口。
        buttons = ttk.Frame(body)
        buttons.pack(side="bottom", fill="x")
        self.mirror_open_button = ttk.Button(
            buttons, text="镜像测速…", command=self._open_mirror_dialog
        )
        self.mirror_open_button.pack(side="left")
        self.open_button = ttk.Button(
            buttons,
            text="打开安装目录",
            command=self._open_install_dir,
            state="disabled",
        )
        self.open_button.pack(side="left", padx=(6, 0))
        self.launch_button = ttk.Button(
            buttons, text="启动", command=self._launch_installed, state="disabled"
        )
        self.launch_button.pack(side="left", padx=(6, 0))
        self.start_button = ttk.Button(
            buttons, text="开始安装", command=self._start_install
        )
        self.start_button.pack(side="right")
        self.cancel_button = ttk.Button(
            buttons,
            text="取消",
            command=self._cancel_install,
            state="disabled",
        )
        self.cancel_button.pack(side="right", padx=(0, 6))

        status_frame = ttk.Frame(body)
        status_frame.pack(side="bottom", fill="x", pady=(2, 4))
        self.progress = ttk.Progressbar(
            status_frame, mode="determinate", maximum=100
        )
        self.progress.pack(fill="x")
        ttk.Label(status_frame, textvariable=self.status).pack(anchor="w")

        log_frame = ttk.LabelFrame(body, text="安装日志", padding=5)
        log_frame.pack(fill="both", expand=True, pady=(0, 6))
        self.log_text = ScrolledText(
            log_frame, height=5, wrap="word", state="disabled"
        )
        self.log_text.pack(fill="both", expand=True)

        self._log_line(f"安装目录默认：{core.DEFAULT_INSTALL_DIR}")
        self._log_line("在线安装将在宿主拆分版发布后接入；当前请使用本地源码或安装包。")

    def _build_source_section(self, body: ttk.Frame) -> None:
        frame = ttk.LabelFrame(body, text="1. 安装来源", padding=8)
        frame.pack(fill="x", pady=(0, 6))
        frame.columnconfigure(1, weight=1)

        ttk.Radiobutton(
            frame,
            text="本地源码目录",
            variable=self.source_mode,
            value="source",
            command=self._update_source_state,
        ).grid(row=0, column=0, sticky="w", pady=2)
        self.source_entry = ttk.Entry(frame, textvariable=self.source_path)
        self.source_entry.grid(row=0, column=1, sticky="ew", padx=(8, 6), pady=2)
        self.source_button = ttk.Button(
            frame, text="浏览…", command=self._browse_source
        )
        self.source_button.grid(row=0, column=2, pady=2)

        ttk.Radiobutton(
            frame,
            text="本地安装包",
            variable=self.source_mode,
            value="archive",
            command=self._update_source_state,
        ).grid(row=1, column=0, sticky="w", pady=2)
        self.archive_entry = ttk.Entry(frame, textvariable=self.archive_path)
        self.archive_entry.grid(row=1, column=1, sticky="ew", padx=(8, 6), pady=2)
        self.archive_button = ttk.Button(
            frame, text="浏览…", command=self._browse_archive
        )
        self.archive_button.grid(row=1, column=2, pady=2)

        ttk.Label(
            frame,
            text="支持 tar.gz/zip；源码目录需含 backend/ 与 gui|webui/。",
            foreground="#64748b",
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(3, 0))

    def _build_frontend_section(self, body: ttk.Frame) -> None:
        frame = ttk.LabelFrame(body, text="2. 界面版本", padding=8)
        frame.pack(fill="x", pady=(0, 6))
        row = ttk.Frame(frame)
        row.pack(fill="x")
        ttk.Radiobutton(
            row,
            text="原生 GUI（GTK4，推荐桌面）",
            variable=self.frontend,
            value="gui",
        ).pack(side="left")
        ttk.Radiobutton(
            row,
            text="WebUI（浏览器控制台）",
            variable=self.frontend,
            value="webui",
        ).pack(side="left", padx=(18, 0))
        ttk.Label(
            frame,
            text="GUI 需要系统 GTK4/libadwaita；WebUI 通过浏览器打开。",
            foreground="#64748b",
        ).pack(anchor="w", pady=(3, 0))

    def _build_install_section(self, body: ttk.Frame) -> None:
        frame = ttk.LabelFrame(body, text="3. 安装位置", padding=8)
        frame.pack(fill="x", pady=(0, 6))
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="目录").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.install_dir).grid(
            row=0, column=1, sticky="ew", padx=(8, 6)
        )
        ttk.Button(frame, text="浏览…", command=self._browse_install_dir).grid(
            row=0, column=2
        )

    def _build_options_section(self, body: ttk.Frame) -> None:
        frame = ttk.LabelFrame(body, text="4. 选项", padding=8)
        frame.pack(fill="x", pady=(0, 6))
        row = ttk.Frame(frame)
        row.pack(fill="x")
        ttk.Checkbutton(
            row,
            text="创建快捷方式",
            variable=self.create_shortcut,
        ).pack(side="left")
        ttk.Checkbutton(
            row,
            text="下载中文字体（可选）",
            variable=self.download_fonts,
        ).pack(side="left", padx=(14, 0))
        delete = ttk.Checkbutton(
            row,
            text="完成后删除安装器",
            variable=self.self_delete,
        )
        if not getattr(sys, "frozen", False):
            delete.configure(state="disabled")
            self.self_delete.set(False)
        delete.pack(side="left", padx=(14, 0))

    def _open_mirror_dialog(self) -> None:
        if self._mirror_window is not None:
            try:
                if self._mirror_window.winfo_exists():
                    self._mirror_window.lift()
                    return
            except tk.TclError:
                pass
            self._mirror_window = None
        window = tk.Toplevel(self.root)
        window.title("GitHub 镜像测速")
        window.minsize(600, 360)
        window.transient(self.root)
        self.root.update_idletasks()
        x = self.root.winfo_rootx() + max(
            0, (self.root.winfo_width() - 680) // 2
        )
        y = self.root.winfo_rooty() + max(
            0, (self.root.winfo_height() - 430) // 2
        )
        window.geometry(f"680x430+{x}+{y}")
        self._mirror_window = window
        body = ttk.Frame(window, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        ttk.Label(body, text="资产 URL").grid(row=0, column=0, sticky="w")
        ttk.Entry(body, textvariable=self.mirror_url).grid(
            row=0, column=1, sticky="ew", padx=(8, 6)
        )
        self._mirror_button = ttk.Button(
            body, text="开始测速", command=self._start_mirror_test
        )
        self._mirror_button.grid(row=0, column=2)
        ttk.Label(
            body,
            text="并发探测前 256KB，按吞吐和首字节延迟排序；下载失败会自动换镜像。",
            foreground="#64748b",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 8))
        self._mirror_tree = ttk.Treeview(
            body,
            columns=("mirror", "speed", "latency", "state"),
            show="headings",
            height=8,
        )
        for column, title, width in (
            ("mirror", "镜像", 150),
            ("speed", "速度", 100),
            ("latency", "延迟", 80),
            ("state", "状态", 300),
        ):
            self._mirror_tree.heading(column, text=title)
            self._mirror_tree.column(column, width=width, anchor="w")
        self._mirror_tree.grid(
            row=2, column=0, columnspan=3, sticky="nsew"
        )
        body.rowconfigure(2, weight=1)
        ttk.Button(body, text="关闭", command=self._close_mirror_dialog).grid(
            row=3, column=2, sticky="e", pady=(8, 0)
        )
        window.protocol("WM_DELETE_WINDOW", self._close_mirror_dialog)

    def _close_mirror_dialog(self) -> None:
        window = self._mirror_window
        self._mirror_window = None
        self._mirror_tree = None
        self._mirror_button = None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

    def _update_source_state(self) -> None:
        source_mode = self.source_mode.get() == "source"
        self.source_entry.configure(
            state="normal" if source_mode else "disabled"
        )
        self.source_button.configure(
            state="normal" if source_mode else "disabled"
        )
        self.archive_entry.configure(
            state="disabled" if source_mode else "normal"
        )
        self.archive_button.configure(
            state="disabled" if source_mode else "normal"
        )

    def _browse_source(self) -> None:
        path = filedialog.askdirectory(title="选择 KarenBot 源码目录")
        if path:
            self.source_path.set(path)
            self.source_mode.set("source")
            self._update_source_state()

    def _browse_archive(self) -> None:
        path = filedialog.askopenfilename(
            title="选择安装包",
            filetypes=[
                ("KarenBot 安装包", "*.tar.gz *.tgz *.tar *.zip"),
                ("所有文件", "*.*"),
            ],
        )
        if path:
            self.archive_path.set(path)
            self.source_mode.set("archive")
            self._update_source_state()

    def _browse_install_dir(self) -> None:
        path = filedialog.askdirectory(title="选择安装目录")
        if path:
            self.install_dir.set(path)

    def _log_line(self, line: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _set_running(self, running: bool) -> None:
        self.start_button.configure(state="disabled" if running else "normal")
        self.cancel_button.configure(state="normal" if running else "disabled")
        if self._mirror_button is not None:
            self._mirror_button.configure(
                state="disabled" if running else "normal"
            )

    def _queue_log(self, line: str) -> None:
        self._queue.put(("log", line))

    def _queue_progress(self, done: int, total: int | None) -> None:
        self._queue.put(("progress", (done, total)))

    def _start_install(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        source_mode = self.source_mode.get()
        source_dir: Path | None = None
        archive: Path | None = None
        if source_mode == "source":
            source_dir = Path(self.source_path.get().strip()).expanduser()
            if not source_dir.is_dir():
                messagebox.showerror("路径无效", "请选择有效的源码目录。")
                return
        else:
            archive = Path(self.archive_path.get().strip()).expanduser()
            if not archive.is_file():
                messagebox.showerror("路径无效", "请选择有效的安装包。")
                return
        raw_dir = self.install_dir.get().strip()
        if not raw_dir:
            messagebox.showerror("路径无效", "安装目录不能为空。")
            return
        install_dir = Path(raw_dir).expanduser()
        if (install_dir / "app").exists() and not messagebox.askyesno(
            "覆盖安装",
            f"{install_dir / 'app'} 已存在。继续会替换应用目录，"
            "数据目录不会删除。是否继续？",
        ):
            return
        frontend = self.frontend.get()
        if os.name == "nt" and frontend == "gui" and source_dir is not None:
            messagebox.showwarning(
                "Windows 源码安装",
                "Windows 源码安装暂不支持 GTK4 GUI。\n"
                "请改用 WebUI，或使用包含运行环境的预构建安装包。",
            )
            return

        self._installed_dir = None
        self._installed_frontend = frontend
        self._delete_on_close = False
        self._cancel.clear()
        self._set_running(True)
        self.progress.stop()
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self.status.set("准备安装…")
        self._clear_log()
        self._log_line(f"来源：{source_dir or archive}")
        self._log_line(f"界面：{frontend}；安装目录：{install_dir}")
        core.set_log_sink(self._queue_log)
        core.set_progress_sink(self._queue_progress)
        self._worker = threading.Thread(
            target=self._run_install,
            kwargs={
                "frontend": frontend,
                "install_dir": install_dir,
                "source_dir": source_dir,
                "archive": archive,
                "venv": None,
                "skip_deps": False,
                "create_shortcut": self.create_shortcut.get(),
                "download_fonts": self.download_fonts.get(),
                "cancel_event": self._cancel,
            },
            daemon=True,
        )
        self._worker.start()

    def _run_install(self, **kwargs: Any) -> None:
        try:
            result = core.install(**kwargs)
        except core.InstallCancelled:
            self._queue.put(("cancelled", None))
        except core.InstallFailure as exc:
            self._queue.put(("error", exc.message))
        except Exception:  # noqa: BLE001
            self._queue.put(("error", traceback.format_exc()))
        else:
            self._queue.put(("done", str(result)))
        finally:
            core.set_log_sink(None)
            core.set_progress_sink(None)

    def _poll_queue(self) -> None:
        while True:
            try:
                kind, payload = self._queue.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._log_line(str(payload))
            elif kind == "progress":
                done, total = payload
                self._update_progress(int(done), total)
            elif kind == "done":
                self._on_done(Path(str(payload)))
            elif kind == "error":
                self._on_error(str(payload))
            elif kind == "cancelled":
                self._on_cancelled()
            elif kind == "mirror":
                self._show_mirrors(payload)
            elif kind == "mirror_error":
                self._on_mirror_error(str(payload))
        self.root.after(80, self._poll_queue)

    def _update_progress(self, done: int, total: int | None) -> None:
        if total and total > 0:
            if str(self.progress.cget("mode")) != "determinate":
                self.progress.stop()
            self.progress.configure(
                mode="determinate", maximum=total, value=done
            )
            self.status.set(
                f"下载中 {done / 1024 / 1024:.1f} / "
                f"{total / 1024 / 1024:.1f} MB"
            )
            return
        if str(self.progress.cget("mode")) != "indeterminate":
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
        self.status.set(f"已下载 {done / 1024 / 1024:.1f} MB")

    def _on_done(self, path: Path) -> None:
        self._worker = None
        self._set_running(False)
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=100, value=100)
        self.status.set("安装完成")
        self._installed_dir = path
        self.open_button.configure(state="normal")
        self.launch_button.configure(state="normal")
        self._log_line(f"安装完成：{path}")
        if self.self_delete.get() and getattr(sys, "frozen", False):
            self._delete_on_close = True
            self._log_line("关闭安装器窗口后会自删除。")
        target = core.launch_target(path, self._installed_frontend)
        messagebox.showinfo(
            "安装完成",
            f"KarenBot 已安装到：\n{path}\n\n启动入口：\n{target}",
        )

    def _on_error(self, message: str) -> None:
        self._worker = None
        self._set_running(False)
        self.progress.stop()
        self.status.set("安装失败")
        self._log_line("错误：" + message)
        messagebox.showerror("安装失败", message[:2000])

    def _on_cancelled(self) -> None:
        self._worker = None
        self._set_running(False)
        self.progress.stop()
        self.status.set("已取消")
        self._log_line("安装已取消。")

    def _cancel_install(self) -> None:
        if self._worker is None or not self._worker.is_alive():
            return
        self._cancel.set()
        self.cancel_button.configure(state="disabled")
        self.status.set("正在取消…")
        self._log_line("已请求取消；正在等待当前步骤结束。")

    def _start_mirror_test(self) -> None:
        if self._mirror_worker is not None and self._mirror_worker.is_alive():
            return
        url = self.mirror_url.get().strip()
        if not url.startswith(("http://", "https://")):
            messagebox.showerror("URL 无效", "请输入 http/https 资产地址。")
            return
        if self._mirror_button is not None:
            self._mirror_button.configure(state="disabled")
        self.status.set("镜像测速中…")
        self._log_line(f"开始镜像测速：{url}")
        self._mirror_worker = threading.Thread(
            target=self._run_mirror_test, args=(url,), daemon=True
        )
        self._mirror_worker.start()

    def _run_mirror_test(self, url: str) -> None:
        try:
            results = core.probe_mirrors(url, core.load_mirrors())
        except Exception as exc:  # noqa: BLE001
            self._queue.put(
                ("mirror_error", f"{type(exc).__name__}: {exc}")
            )
        else:
            self._queue.put(("mirror", results))

    def _show_mirrors(self, results: list[dict[str, Any]]) -> None:
        tree = self._mirror_tree
        if tree is not None:
            for row in tree.get_children():
                tree.delete(row)
        ordered = sorted(
            results,
            key=lambda item: (
                not bool(item.get("ok")),
                -float(item.get("speed") or 0),
                float(item.get("latency") or 999),
            ),
        )
        for item in ordered:
            if item.get("ok"):
                speed = f"{float(item.get('speed') or 0) / 1024:.1f} KB/s"
                latency = f"{float(item.get('latency') or 0):.2f}s"
                state = "可用"
            else:
                speed = "-"
                latency = "-"
                state = str(item.get("error") or "失败")[:120]
            if tree is not None:
                tree.insert(
                    "",
                    "end",
                    values=(
                        item.get("mirror", "?"),
                        speed,
                        latency,
                        state,
                    ),
                )
        if self._mirror_button is not None:
            self._mirror_button.configure(state="normal")
        available = sum(1 for item in results if item.get("ok"))
        self.status.set(f"镜像测速完成：{available}/{len(results)} 可用")
        self._log_line(f"镜像测速完成：{available}/{len(results)} 可用")

    def _on_mirror_error(self, message: str) -> None:
        if self._mirror_button is not None:
            self._mirror_button.configure(state="normal")
        self.status.set("镜像测速失败")
        self._log_line("镜像测速失败：" + message)
        messagebox.showerror("测速失败", message[:2000])

    def _open_install_dir(self) -> None:
        if self._installed_dir is None:
            return
        target = self._installed_dir
        if not target.exists():
            messagebox.showerror("目录不存在", str(target))
            return
        try:
            _open_path(target)
        except OSError as exc:
            messagebox.showerror("打开失败", str(exc))

    def _launch_installed(self) -> None:
        if self._installed_dir is None:
            return
        target = core.launch_target(
            self._installed_dir, self._installed_frontend
        )
        if not target.is_file():
            messagebox.showerror("启动入口不存在", str(target))
            return
        try:
            _run_target(target, self._installed_dir)
        except OSError as exc:
            messagebox.showerror("启动失败", str(exc))

    def _on_close(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            if not messagebox.askyesno(
                "安装进行中",
                "安装仍在进行，确定退出？未完成的临时文件会保留。",
            ):
                return
            self._cancel.set()
        if self._delete_on_close:
            core.self_delete_installer()
        self.root.destroy()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="karenbot-installer", description="KarenBot 安装引导 GUI"
    )
    parser.add_argument(
        "--check", action="store_true", help="只检查 Tk 与资源是否可用"
    )
    parser.add_argument(
        "--smoke-test", action="store_true", help="打开窗口后自动退出（CI）"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.check:
        _print_console(
            json.dumps(
                {
                    "ok": _TK_ERROR is None,
                    "tk": getattr(tk, "TkVersion", None),
                    "python": sys.version.split()[0],
                    "default_install_dir": str(core.DEFAULT_INSTALL_DIR),
                    "mirrors": len(core.load_mirrors()),
                    "tk_error": str(_TK_ERROR) if _TK_ERROR else "",
                },
                ensure_ascii=False,
            )
        )
        return 0 if _TK_ERROR is None else 2
    if _TK_ERROR is not None:
        _print_console(
            "缺少 Tkinter。Linux 请安装 python3-tk；"
            f"原始错误：{_TK_ERROR}"
        )
        return 2
    _enable_dpi_awareness()
    root = tk.Tk()
    try:
        InstallerApp(root)
    except Exception:  # noqa: BLE001
        text = traceback.format_exc()
        _print_console(text)
        try:
            messagebox.showerror("安装器启动失败", text[:2000])
        except Exception:  # noqa: BLE001
            pass
        root.destroy()
        return 1
    if args.smoke_test:
        root.after(500, root.destroy)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
