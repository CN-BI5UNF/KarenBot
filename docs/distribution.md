# KarenBot v2 分发契约

本文件面向安装器/镜像站维护者。v2 起，`CN-BI5UNF/KarenBot` 是唯一正式安装与更新入口；
三个组件仓库只作为 submodule 源码和源码回溯。

## Release 资产

每个 `v*` Release 必须包含四个资产：

```text
modules.json
KarenBot-backend-<tag>.tar.gz
KarenBot-GUI-<tag>.tar.gz
KarenBot-WebUI-<tag>.tar.gz
```

`<tag>` 例如 `v2.1.0-alpha`。资产由 `.github/workflows/release.yml` 调用
`scripts/build_release_assets.py` 从 `modules.lock.json` 固定的 commit 生成。

## modules.json

```json
{
  "schema": 1,
  "release": "v2.1.0-alpha",
  "components": {
    "backend": {
      "repo": "CN-BI5UNF/KarenBot-backend",
      "tag": "v2.1.0-alpha",
      "version": "2.1.0-alpha",
      "asset": "KarenBot-backend-v2.1.0-alpha.tar.gz",
      "sha256": "64 位十六进制",
      "size": 123456
    },
    "gui": { "...": "同上" },
    "webui": { "...": "同上" }
  }
}
```

`modules.json` 本身不携带签名；安装器应从 GitHub Release 官方地址下载，并按
`sha256` 校验三个组件资产。第三方镜像只能加速传输，不能替代校验。

## 安装器步骤

1. 解析用户选择的 tag；默认使用最新稳定 Release，alpha/beta 需用户显式选择。
2. 从 `https://github.com/CN-BI5UNF/KarenBot/releases/download/<tag>/modules.json`
   下载 manifest。
3. 根据用户选择的前端（`gui` 或 `webui`）下载：
   - `backend` 资产；
   - 对应前端资产。
4. 按 manifest 的 `size` 与 `sha256` 校验；不匹配立即中止，不写安装目录。
5. 解压两个资产（各自带一个顶层目录）：
   - 后端内容作为应用根；
   - 把前端资产中的 `gui/` 或 `webui/` 合并到应用根。
6. 从 KarenBot 主仓库 `personas/`（或现有 personas 资产）补齐默认人格；不要用组件
   资产里的空 `personas/` 覆盖用户人格。
7. 写入安装目录的 `modules.json`：
   ```json
   {
     "schema": 1,
     "frontend": "gui",
     "distribution": {"repo": "CN-BI5UNF/KarenBot", "tag": "v2.1.0-alpha"},
     "components": {
       "backend": {"repo": "...", "dir": "backend", "tag": "v2.1.0-alpha", "version": "2.1.0-alpha"},
       "gui": {"repo": "...", "dir": "gui", "tag": "v2.1.0-alpha", "version": "2.1.0-alpha"}
     }
   }
   ```
8. 安装依赖并启动对应前端。

## 禁止事项

- **不要**用 `https://github.com/CN-BI5UNF/KarenBot/archive/refs/tags/<tag>.tar.gz`
  代替组件资产：GitHub 源码归档不包含 submodule 内容。
- **不要**让安装器只安装后端或只安装一个前端；首次安装必须同时安装后端与所选前端。
  已安装用户可以在更新页选择单独更新某个组件。
- **不要**在没有 manifest 哈希的情况下从第三方镜像安装。
- 旧 1.0.x 安装器不兼容 v2；0.1.x 安装器必须先升级到过渡版，或由用户更新安装器后重装。

## 过渡版

0.1.x 用户的升级路径：

1. 安装后端 `v0.1.11-alpha.1` 与 GUI/WebUI `v0.1.1-alpha.2`（稳定过渡补丁）；
2. 重启应用；
3. 在更新页手动选择 `v2.1.0-alpha`（Pre-release）；
4. 更新器默认同时写后端与当前前端，也可以在更新页只选择其中一个组件。

过渡版的后端更新器只读取 KarenBot 主仓库的 `modules.json` 发行版；它不会再从三个
组件仓库拼装版本。
