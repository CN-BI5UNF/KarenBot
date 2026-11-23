# 0.1.x → v2 升级路径

v2 把后端、GUI、WebUI 合并成 KarenBot 主仓库的统一发行版。由于 0.1.x 更新器只认识
三个组件仓库的独立 Release，必须经过一次过渡补丁。

## 1. 安装过渡补丁

| 组件 | 版本 | Release |
|---|---|---|
| 后端 | `v0.1.11-alpha.1` | `CN-BI5UNF/KarenBot-backend` |
| GUI | `v0.1.1-alpha.2` | `CN-BI5UNF/KarenBot-GUI` |
| WebUI | `v0.1.1-alpha.2` | `CN-BI5UNF/KarenBot-WebUI` |

三个 Release 都标记为稳定版。旧更新器会按组件提示/允许更新：

1. 先更新后端；
2. 再更新当前前端（GUI 或 WebUI）；
3. 重启后端；GUI 完全退出重开，WebUI 刷新页面。

只更新其中一个组件也可以：过渡后端保留了组件别名，旧前端仍能看到 KarenBot 统一发行版；
过渡前端在旧后端下会自动回退双组件列表。

## 2. 选择 v2

过渡版更新页会从 `CN-BI5UNF/KarenBot` 读取发行版：

- `v2.0.1-alpha.1` 是 **Pre-release**，不会自动提示；
- 在「更新 → KarenBot 发行版」中手动选择；
- 可同时更新后端与当前前端，也可只更新其中一个组件；
- 更新后后端有变化则重启后端；GUI 完全退出重开，WebUI 刷新页面。

## 3. 不要再做的事

- 不要单独从 `KarenBot-backend` / `KarenBot-GUI` / `KarenBot-WebUI` 的 v2 Release
  拼接组件；这些 Release 仅供源码回溯。
- 不要使用旧 1.0.x 的整仓更新器更新到 v2；旧绑定版本已放弃支持。
- 不要把 KarenBot 主仓库的源码 tar.gz 当安装包：它不包含 submodule 内容。
