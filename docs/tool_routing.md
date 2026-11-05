# 工具双层路由

`behavior.tool_schema_profile="routed"` 是实验性的工具暴露模式，用于在工具数量变多时
减少每轮固定 schema token。默认仍是 `compact`，切换后需要重启 Runtime。

## 两层结构

1. **工具集层（粗粒度）**：`list_toolsets` 返回可用工具集，`load_toolset(name)`
   激活其中一个集合。初始只暴露核心工具和这两个入口；加载后，下一次模型请求才会
   出现该工具集的紧凑 schema。
2. **单工具层（细粒度）**：加载后的工具使用紧凑 schema；需要高级可选字段、完整
   JSON schema 或风险说明时，继续用 `tool_search detail=full`。

因此 routed 不是替换 `tool_search`，而是在它之前增加一层工具集路由。

## 初始核心工具

routed 初始始终暴露回复、收尾和常用上下文工具：发送/提交发送、`no_action`、
最近聊天、长期记忆、图片理解、联网搜索、黑话/知识查询、`group_trigger_window`、
`tool_search`、`list_toolsets`、`load_toolset`。实测初始 schema 约 2,980 tokens
（当前完整功能配置）；compact 档在测试配置约 5,063 tokens，启用容器等额外工具时
约 5,683 tokens（随功能开关变化）。

## 提示设计

- 初始核心工具的 `short_description` 先写用途，再写关键限制；参数细节仍由
  `tool_search detail=full` 展开。stub 工具的用途写在描述里，`tool_search` 要求
  由占位参数 `_tool_search_required` 和 `<tool_search_policy>` 统一表达，避免每个
  工具重复一句“先用 tool_search”。
- routed 加载后的工具使用简短描述，便于模型快速判断；风险等级不会因为压缩 schema
  而丢失，`tool_search` 会返回 `risk_level`、`toolsets` 和 `loaded`。
- `list_toolsets` 提示按任务加载 **1-2 个** 真正需要的集合；核心工具已经可用时
  不要为了“多一个工具”加载整个集合。未加载调用返回 `need_toolset` 不是失败，
  按 `next` 加载后重试一次即可。
- `tool_search` 对已加载工具返回“可直接调用”；对未加载工具返回需要加载的工具集。
  参数示例（workspace、容器、上传、触发窗口等）随工具元数据返回。

## 工具集目录

| id | 内容 |
|---|---|
| `core` | 始终可用的核心工具 |
| `control` | 定时唤醒、群聊接收范围、@ 触发窗口、工具检索 |
| `messaging` | 发送、撤回、上传文件、语音 |
| `qq_info` | 联系人/群/成员、单条消息、转发、戳一戳、表情回应 |
| `qq_admin` | 踢人、禁言、全员禁言、退群、好友/入群申请 |
| `history` | 最近聊天、群历史/会话总结、归档筛选/检索 |
| `memory` | 长期重要记忆 |
| `knowledge` | 知识/热梗笔记 |
| `slang` | 群聊黑话 |
| `web` | 联网搜索、网页正文、天气 |
| `emoji` | 表情包管理 |
| `workspace` | workspace 文件、Python、上传、后台资料整理 |
| `persona` | 进食、睡眠、工作状态 |
| `coding` | 本机/容器编码工具、补丁、待办、计划、子 Agent、自定义工具 |
| `container` | 受控 Docker 容器 |

允许重叠：例如 `upload_file` 同时属于 `messaging` 和 `workspace`，加载任一集合
即可使用。`list_toolsets` 会按当前功能开关过滤（例如未启用容器时不会出现
`container` 集合）。`doc`、`files`、`qq`、`admin`、`docker` 等是 `load_toolset`
的兼容别名。

## 生命周期与执行门禁

- 已加载集合按会话（`private:*` / `group:*` / 系统会话）隔离，并在同一 Runtime
  进程内跨模型轮保持；重启后清空，回到核心集合。
- 未加载工具的调用会被 executor 拒绝，返回 `status=need_toolset`，提示先
  `list_toolsets` / `load_toolset`。这不是任务失败，模型可以加载后继续。
- `tool_search` 始终可用，返回结果会带 `loaded` 和 `toolsets`；未加载工具会附带
  需要加载的集合。
- 已加载集合在当前会话内不会重复加载；可用 `list_toolsets` 查看状态。

## 配置与取舍

- 切换到 routed：设置 →「工具 schema 档位」选择 `routed`，或修改
  `behavior.tool_schema_profile: routed`，重启 Runtime。
- 切回 `compact` / `full`：原有行为完全保留。
- 代价：模型可能需要先花一轮 `load_toolset`；动态增加工具会改变请求的 tools 块，
  可能降低 KV cache 命中。建议按实际任务测量 prompt/cached tokens 后再决定是否
  长期使用。
- 子 Agent（`start_agent_task`）仍使用自己固定的工具集，不参与会话 routed 状态。

## agent 档位

`behavior.tool_schema_profile="agent"` 是给编码任务准备的 Claude Code 式延迟加载：

- 初始只暴露 `send_private_messages`、`send_group_message`、`commit_send_attempt`、
  `no_action`、`tool_search` 和
  `agent_read/agent_write/agent_edit/agent_bash/agent_glob/agent_grep/agent_ls`。
- 其余工具（包括 `agent_ls`、`agent_todo`、`agent_apply_patch`、`agent_spawn`、
  `agent_notebook_edit`、自定义工具和全部非编码工具）用
  `tool_search select=["工具名"]` 加载；下一次模型请求才会出现其 schema。
- 未加载调用返回 `status=need_tool_search`。加载集合按会话隔离，只存在内存中。
- 该档位不使用 `list_toolsets` / `load_toolset`；工具级 ToolSearch 取代工具集层。
- 编码工具本身仍按 `agent_container_mode` 判断 Pi/DSH/Claude Code 能力；本机固定
  Claude Code 语义。详见 [`agent_modes.md`](agent_modes.md)。
