# KarenBot 安装引导器

当前阶段提供 **Linux CLI + 跨平台 Tkinter GUI**，用于本地源码/离线安装包、
镜像测速、字体下载、快捷方式和自删除。安装器不内置任何应用包，也不编译
deb/exe；真正的在线 Release 组装等宿主拆分布局发布后再接入。

## 快速开始

### Linux CLI（主要入口）

```bash
# 本地源码安装（开发和本机验证）
python3 installer/karen_install.py \
  --frontend gui \
  --source-dir /path/to/KarenBot-GUI \
  --dir ~/.local/opt/karenbot \
  --no-shortcut

# 本地 tar/zip 安装包
python3 installer/karen_install.py --frontend gui --archive /path/to/karen.tar.gz

# 只测镜像速度
python3 installer/karen_install.py --probe-url \
  https://github.com/CN-BI5UNF/KarenBot/archive/refs/tags/v1.0.1-alpha.1.tar.gz
```

### GUI

```bash
# Linux 需要 Tkinter（Debian/Ubuntu）
sudo apt install python3-tk
python3 installer/gui_install.py
```

Windows 使用 GitHub Actions 产出的 `KarenBot-Installer.exe`，不需要本机
Python；也可以在本机用 PyInstaller 构建（见下文）。Linux GUI 是可选入口，
终端用户仍推荐 CLI 或直接使用 `install.sh`。

GUI 功能：

- 本地源码目录 / 本地 tar/zip；
- 原生 GUI 或 WebUI；
- 安装目录、快捷方式、中文字体、安装后自删除；
- 独立镜像测速窗口（并发探测前 256KB，按吞吐和首字节延迟排序）；
- 后台安装、进度、日志、取消、打开目录/启动。

## 常用参数

| 参数 | 说明 |
|---|---|
| `--frontend gui\|webui` | 选择原生 GUI 或 WebUI |
| `--dir` | 安装目录，Linux 默认 `~/.local/opt/karenbot`，Windows 默认 `%LOCALAPPDATA%\Programs\KarenBot` |
| `--source-dir` | 从本地源码安装（测试/离线） |
| `--archive` | 从本地 tar/zip 安装包安装 |
| `--venv` | 复用已有 venv（测试用） |
| `--skip-deps` | 跳过 venv/依赖安装（测试用） |
| `--no-fonts` | 不下载 Noto 中文字体 |
| `--no-shortcut` | 不创建快捷方式 |
| `--self-delete` | 安装后删除安装器自身 |
| `--keep-installer` | 打包版安装后保留安装器（覆盖默认自删除） |
| `--probe-url` | 只对镜像做测速并退出 |

## 镜像

`mirrors.json` 维护 GitHub 直连和公共前缀镜像。测速并发请求实际资产的前
256KB，按吞吐和首字节延迟排序；下载失败自动换下一个镜像。字体下载也走同一
套逻辑，失败不会阻塞安装。

第三方镜像能看到下载请求，也可能篡改内容。安装器对有 SHA256 的资产会校验；
没有官方哈希的 Release tarball 只能靠结构和运行检查。敏感环境请优先使用
`direct`，或在后续 Release manifest 中补齐哈希。

## 字体

默认下载 Noto Sans SC / Noto Serif SC 可变字体到：

- Linux：`$XDG_DATA_HOME/KarenBot/fonts`
- Windows：`%LOCALAPPDATA%\KarenBot\fonts`

并生成只追加该目录的 `fonts.conf`。GUI 没有字体时会回退到系统字体。

## 构建（GitHub Actions，免费）

`.github/workflows/build-installer.yml` 使用公开仓库的免费标准 runner：

- `windows-latest` → `KarenBot-Installer.exe`（x64，windowed，无黑框）；
- `ubuntu-24.04` → `KarenBot-Installer`（x64，保留 console）；
- `ubuntu-24.04-arm` → `KarenBot-Installer`（arm64，保留 console）；
- `workflow_dispatch` 手动触发；
- 推送 `installer-v*` tag 时自动把两个产物附加到 GitHub Release。

不构建 macOS（公开仓库也按 10 倍分钟计费，当前不需要）。构建产物未签名，
Windows 可能提示 SmartScreen，可选择“更多信息 → 仍要运行”；后续可申请
开源签名服务或购买证书。

本地构建仅用于验证：

```bash
python -m pip install pyinstaller
python -m PyInstaller installer/KarenBot-Installer.spec --noconfirm --clean
python installer/gui_install.py --check
python installer/gui_install.py --smoke-test   # Linux 需要 DISPLAY/xvfb
```

## 安全边界

- 解压拒绝 `..`、绝对路径、符号链接和设备文件；
- 下载支持 SHA256 校验，失败自动换镜像；
- Windows 默认 per-user 安装，不触发 UAC；
- 安装器只替换 `<install>/app`，不删除用户数据目录；
- 自删除只在打包版默认开启；源码运行默认保留脚本。

## 当前限制

- **在线 Release 安装尚未接入**：宿主仓库当前的公开 tag 仍是旧 `webui/`
  布局，而模块仓库提供 `backend/` / `gui/` / `webui/`。需要先把宿主拆分布局
  发布，再叠加模块 tarball；现在贸然在线组装会得到不兼容组合。
- **Windows 源码 GUI 不支持**：GTK4/PyGObject 需要 Windows 便携运行时；
  GUI 可安装预构建包，WebUI 源码安装需要系统 Python。
- **Windows GTK4 应用包尚未构建**：安装器已能识别预构建 `.exe` 包，但应用
  本身的 Windows 构建链是独立任务。
- GUI 是简易向导，不是完整安装器设计系统；Linux 仍以 CLI 为主。
