# Agent 模式（Pi / DSH / Claude Code）

这是 KarenBot **自己实现的工具语义**，不是第三方 Agent 的 TUI/GUI/WebUI，也不会
启动 Pi、DeepSeek Harness 或 Claude Code 的命令行程序。模型通过 KarenBot 的工具
循环直接获得读写、搜索、补丁、命令、子 Agent 等能力。

两种执行位置：

- **本机（host）**：固定使用 Claude Code 语义，作用域是 AI workspace。
- **容器（container）**：在容器页安装并激活 `pi`、`dsh`、`claude_code` 之一；
  同一时间只能激活一个，可以同时安装多个。工具在容器 `/workspace` 内执行。

## 模式对照

| 能力 | Pi | DSH | Claude Code |
|---|---|---|---|
| 读/写/编辑/glob/grep/ls/bash | ✓ | ✓ | ✓ |
| unified diff 补丁 `agent_apply_patch` | — | ✓ | ✓ |
| 待办 `agent_todo` | — | ✓ | ✓ |
| 计划模式 `agent_enter_plan` / `agent_exit_plan` | — | ✓ | ✓ |
| 子 Agent `agent_spawn` | — | ✓ | ✓ |
| Jupyter 单元格 `agent_notebook_edit` | — | — | ✓ |
| 自定义工具 `agent_tool_*` | ✓ | ✓ | — |

Pi 最小化；DSH 侧重“万物皆可插件”，允许模型编写持久化 Python 工具；Claude Code
覆盖最完整。本机永远是 Claude Code，因此本机不支持自定义工具。

## 安装与激活

WebUI →「受控容器」→「Agent 模式」：

1. 点某个模式的「安装」。只写入 `/workspace/.karen-agents/<mode>/` 和 manifest，
   不会重建容器，也不会删除 `/workspace` 其它文件。原生工具不需要外部 CLI 或
   额外的包依赖；文件搜索和编辑均由 KarenBot 的 helper 完成。
2. 多个模式可以同时安装；点「激活」把配置切到该模式。激活前必须已安装。
3. 「停用」把 `active_mode` 设为 `off`；「卸载」只删除该模式自己的运行时目录，
   激活中的模式必须先停用。

安装的是 KarenBot 的辅助运行时，不是 Pi/DSH/Claude Code CLI。它们真正的工具
能力由 KarenBot 的工具层实现，所以不需要 TUI、GUI、WebUI、Node 或登录凭据。

配置路径：`features.container.agent`。

```yaml
features:
  container:
    agent:
      active_mode: off        # off | pi | dsh | claude_code
      host_execution: sandbox # sandbox | host
      sandbox_network: true   # sandbox 模式是否联网
```

接口：

- `GET /api/container/agents`
- `POST /api/container/agents/{mode}/install`
- `DELETE /api/container/agents/{mode}`
- `POST /api/container/agents/{mode}/activate`
- `POST /api/container/agents/deactivate`
- `PATCH /api/container/agents/host`

## 工具 schema 档位

Agent 模式推荐把 `behavior.tool_schema_profile` 设为 `agent`（需要重启 Runtime）。
它采用 Claude Code 式延迟加载：

1. 初始只加载少量核心工具：发送/提交发送/收尾、`tool_search`、`agent_read`、
   `agent_write`、`agent_edit`、`agent_bash`、`agent_glob`、`agent_grep`、`agent_ls`。
2. 需要其它工具时调用 `tool_search select=["agent_ls", ...]`（一次 1-3 个）。
   加载结果从**下一次模型请求**开始出现完整 schema。
3. 用 `tool_search query=关键词` 只发现候选，不会自动加载。
4. 未加载就调用会返回 `status=need_tool_search`；按 `next` 加载后重试即可，不是
   任务失败。
5. 加载状态按会话存在内存里，Runtime 重启清空；不同私聊/群聊互不影响。

`routed` 档位也包含 `coding` 工具集；`compact`/`full` 仍保留编码工具的 stub，
可由 `tool_search` 解锁，但不会获得上述核心常加载体验。

## 本机执行策略

- `sandbox`（默认）：`agent_bash` 通过 bubblewrap 执行，只读绑定系统目录与 venv，
  workspace 可写，隔离 PID/IPC/UTS/cgroup，默认联网；可关闭 `sandbox_network`。
- `host`：命令直接以当前用户权限执行，**可以控制整台电脑**。只应在明确需要时使用。
  文件类工具仍强制限制在 AI workspace 内，但 shell 命令不受 workspace 路径限制。

无 `bwrap` 时不会假装安全：`agent_bash` 返回明确的 `agent_sandbox_unavailable`，
需要安装 bubblewrap 或由用户显式切换到 host 模式。

## 容器执行

容器内工具通过只读的 `/workspace` 边界工作：host 侧做一次校验，容器内的 helper
再用 `realpath` 校验，拒绝 `..`、符号链接和越界路径。容器工具本身仍受容器的
非 root、只读根文件系统、默认无网络、资源上限约束。

`agent_bash` 的 `cwd` 必须在 `/workspace` 内；`target=container` 需要先在容器页
激活一个模式。`target=host` 不依赖容器是否启用。

## Pi / DSH 自定义工具

- `agent_tool_create(name, description, code)`：保存到
  `/workspace/.karen-agents/tools/<name>.py`。代码应只使用 Python 标准库，从 stdin
  读取一个 JSON 对象，向 stdout 输出结果；退出码非 0 表示失败。
- `agent_tool_list`、`agent_tool_run(name, arguments)`、`agent_tool_delete`。
- 工具名限制 `[A-Za-z][A-Za-z0-9_-]{0,63}`；单个工具最多 256 KiB，最多 64 个。
- 自定义工具没有独立的权限沙箱：它在容器里以当前容器用户运行，能访问容器内
  可访问的资源。只应运行模型自己编写或已经审阅过的代码。

## 子 Agent

`agent_spawn` 会启动一个**真实的后台子 Agent 循环**并同步等待结果，不是别名或空
壳。子 Agent 使用受限工具集（读取/写入/编辑/补丁/搜索/命令等），不会发送 QQ
消息或修改长期记忆。host 目标会把结论写入 `agent_tasks/<task>/` 下的结果文件；
container 目标在最终回复文本中返回结论。Pi 模式不支持子 Agent。

## 限制

- 不安装、不运行第三方 Agent CLI；因此没有它们的登录、插件市场和云端会话。
- 没有独立的 `AskUserQuestion` 工具：需要澄清时直接调用 `send_*` 提问并结束本轮，
  用户的下一条消息就是回答。
- `agent_apply_patch` 不处理重命名补丁和二进制文件；默认去掉一层 `a/`、`b/`
  前缀，可用 `strip=0..8` 调整。
- 计划模式只阻止写文件、编辑、命令、补丁、子 Agent 和自定义工具；只读检索仍可用。
- 自定义工具和 `agent_bash` 属于高风险能力，WebUI 会显示风险说明；不要把它们
  当作对抗恶意代码的绝对安全边界。
