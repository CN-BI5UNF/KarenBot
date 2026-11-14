# 安装引导 GUI 技术选型（Tkinter）

结论：安装器 GUI 使用 **Python 标准库 Tkinter + ttk**，不嵌入浏览器，
不采用 Tauri/WebView2/Electron，也不依赖被安装应用的 GTK4 运行时。
Linux 继续以 CLI 安装脚本为主，Windows 使用 PyInstaller 打包的 GUI。

## 为什么不用 WebView / 重型框架

| 方案 | 结论 |
|---|---|
| Tauri 2 + WebView2 | 不采用。需要 Rust 工具链和 WebView2 运行时，安装器为了一个向导引入两层新依赖，收益不大 |
| Electron | 不采用。100MB+、内存高、启动慢 |
| PySide6 / Qt | 不采用。安装器再带一套 Qt，体积和打包复杂度都高 |
| GTK4 / libadwaita | 不采用。安装器不能依赖自己正在安装的运行时；Windows 上 GTK4 便携打包也复杂 |
| WinUI 3 / WPF | 不采用。Windows 体验好，但自包含 .NET 体积大，且不能复用到 Linux |
| 纯浏览器本地页 | 不采用。窗口、端口、自删除和进度都不好控制 |
| **Tkinter + ttk** | **采用**。随 CPython 提供，无额外运行时；单文件 exe 小、启动快；跨 Windows/Linux；界面朴素但符合“简易安装引导”的定位 |

代价是 Tkinter 的视觉不如 Web 技术精致。这个安装器只需要选择来源、路径、
进度和日志，不需要动画或复杂布局，因此这个取舍是合适的。

## 结构

```text
installer/
  karen_install.py          # 安装核心：测速、下载、校验、解压、venv、快捷方式
  gui_install.py            # Tkinter 向导，复用同一核心
  KarenBot-Installer.spec   # PyInstaller 单文件构建
  mirrors.json              # GitHub 直连 + 公共前缀镜像
  install.sh                # Linux CLI 包装器
  README.md                 # 使用与构建说明
  gui-architecture.md       # 本文
```

## GUI 功能

1. 选择本地源码目录或本地 tar/zip 安装包；
2. 选择原生 GUI（GTK4）或 WebUI；
3. 选择安装目录；
4. 可选创建快捷方式、下载 Noto 中文字体、安装后自删除；
5. 独立“镜像测速”窗口：并发探测前 256KB，按吞吐和首字节延迟排序；
6. 后台线程执行安装，UI 通过队列更新日志/进度，不阻塞 Tk 主循环；
7. 取消按钮设置协作式取消事件，下载和阶段切换会尽快停止；
8. 完成后可打开安装目录或启动应用。

## Windows 兼容性

- **Per-user 安装**：默认 `%LOCALAPPDATA%\Programs\KarenBot`，快捷方式写入
  当前用户的开始菜单/桌面，不触发 UAC。
- **高 DPI**：启动 Tk 前调用 `SetProcessDpiAwareness(1)`，避免系统位图拉伸；
  优先使用 Microsoft YaHei UI。
- **快捷方式**：PowerShell + `WScript.Shell` 创建 `.lnk`，不需要额外依赖。
- **启动器**：源码模式写 `.cmd`，预构建包直接指向 `.exe`。
- **自删除**：Windows 不能删除正在运行的 exe；安装完成后由 `cmd` 延迟删除。
  源码运行时默认不删除安装器脚本。
- **预构建包**：识别 `KarenBot.exe` / `KarenBot-GUI.exe` /
  `KarenBot-WebUI.exe`，跳过 venv 和依赖安装。Windows 源码安装暂不支持
  GTK4 GUI，需等 Windows GTK4 便携构建完成。

## Linux 兼容性

- CLI 仍是主要入口；GUI 需要 `python3-tk` 和可用的中文字体。
- 启动器写 `.sh`，快捷方式写 `~/.local/share/applications/*.desktop`。
- GUI 安装继续使用系统 PyGObject/GTK4；venv 带 `--system-site-packages`，
  并在安装后检查 `Gtk 4.0` / `Adw 1`。

## 构建与分发

`.github/workflows/build-installer.yml` 在 **公开仓库的免费标准 runner** 上构建：

- `windows-latest`：PyInstaller windowed 单文件 exe；
- `ubuntu-24.04`：PyInstaller 单文件（console 保留，便于终端和 CI）；
- `workflow_dispatch` 手动触发；推送 `installer-v*` tag 时自动附加到 Release。

不构建 macOS（公开仓库也按 10 倍分钟计费，当前不需要）。安装器不内置
KarenBot/Python/GTK 包；只负责安装引导。

## 签名与 SmartScreen

当前不购买 Authenticode 证书。未签名 exe 在 Windows 上可能触发 SmartScreen
“更多信息 → 仍要运行”。后续可以申请面向开源项目的免费签名服务，或购买
证书；这不影响功能开发。

## 当前阶段

- 已支持：本地源码/安装包安装、镜像测速、字体下载、快捷方式、自删除、
  Windows/Linux 单文件构建。
- 待接入：在线 Release 组装。需要先把宿主仓库的 `backend/` 拆分布局发布，
  再把 `KarenBot-backend` + `KarenBot-GUI|WebUI` 模块 tarball 叠加到宿主上；
  当前公开宿主 tag 仍是旧 `webui/` 布局，贸然在线安装会得到不兼容的组合。
- 待构建：Windows GTK4 便携应用包。安装器已能识别并安装预构建包，但应用
  本身的 Windows 构建链是独立任务。
