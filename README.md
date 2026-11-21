# KarenBot

KarenBot 的**统一发行版与组装仓库**。v2 起，后端、GUI、WebUI 三个组件以 Git submodule
形式位于 `modules/`，正式安装和更新只使用本仓库的 GitHub Release。

> 旧 1.0.x「后端 + WebUI 绑定」版本已放弃支持；旧发行版仍保留在本仓库，并已复制归档到
> 私有仓库 `CN-BI5UNF/Debata-Refactor`。旧 0.1.x 模块化版本需先安装过渡补丁再升级到 v2。

## 仓库布局

```text
modules/KarenBot-backend/   # submodule: 核心程序 + 后端控制面
modules/KarenBot-GUI/       # submodule: GTK4 桌面前端 gui/
modules/KarenBot-WebUI/     # submodule: 浏览器前端 webui/
personas/                   # 默认人格（安装器仍从这里补齐）
scripts/assemble.py         # 从 submodule 组装可运行目录
scripts/build_release_assets.py  # 生成三个组件资产 + modules.json
scripts/verify_modules.py   # 校验 submodule 与 modules.lock.json
modules.lock.json           # 本发行版固定的组件 tag/commit
releases/                   # 发行说明
docs/distribution.md        # 给安装器的资产契约
docs/transition.md          # 0.1.x -> 过渡版 -> v2 升级路径
```

## 初始化

```bash
git clone --recursive https://github.com/CN-BI5UNF/KarenBot.git
cd KarenBot
# 已克隆但未初始化 submodule 时：
git submodule update --init --recursive
python scripts/verify_modules.py --tag v2.0.0-alpha
```

## 组装可运行目录

```bash
# 两个前端都组装（开发/检查用）
python scripts/assemble.py --output dist/app

# 只组装 GUI 或 WebUI
python scripts/assemble.py --frontend gui --output dist/app-gui
python scripts/assemble.py --frontend webui --output dist/app-webui
```

组装会复制各 submodule 的 tracked files，写入 `modules.json`，并保留本仓库的
`personas/`、`LICENSE`、`NOTICE`。它不会复制 `data/`、`config.yaml`、插件或其他用户数据。

## 发布

发布由 `.github/workflows/release.yml` 在推送 `v*` tag 时执行：

1. checkout 主仓库和全部 submodule；
2. `scripts/verify_modules.py --tag <tag>` 校验 lock/commit/VERSION；
3. `scripts/build_release_assets.py --tag <tag> --output dist` 生成：
   - `KarenBot-backend-<tag>.tar.gz`
   - `KarenBot-GUI-<tag>.tar.gz`
   - `KarenBot-WebUI-<tag>.tar.gz`
   - `modules.json`（含各资产 SHA256）
4. 创建 GitHub Release 并上传四个资产。

发布资产**不包含完整应用包**；安装器按 manifest 选择后端 + 一个前端进行组合。

## 更新

- 新安装：从本仓库 Release 下载 `modules.json` 与组件资产，按 manifest 校验后组合。
- 已安装的 0.1.x：先更新到过渡版（后端 `v0.1.11-alpha.1`，GUI/WebUI `v0.1.1-alpha.2`），
  再在更新页手动选择 `v2.0.0-alpha`。
- v2 更新器只认本仓库的统一发行版；选择任一组件版本都会同时更新后端与当前前端。

资产格式与安装器步骤见 [`docs/distribution.md`](docs/distribution.md)。

## 安全边界

- 不提交 `config.yaml`、`secrets.*`、聊天记录、日志、模型权重或用户数据。
- GitHub Release 资产由 `git archive` 从固定 commit 生成；安装器必须校验 `modules.json` 中的 SHA256。
- 更新仍然只写程序文件；`data/`、`personas/`、`plugins/`、`config.yaml` 不会被覆盖。

## 许可证

Apache-2.0，详见 `LICENSE` 与 `NOTICE`。
