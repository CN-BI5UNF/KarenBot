"""Native coding-agent tools (Pi / DSH / Claude Code semantics).

These tools are for KarenBot's LLM only.  They do not start any agent TUI,
GUI or WebUI; they expose the same primitives (read/write/edit/bash/search)
directly, with a host or container backend.
"""

from __future__ import annotations

import json
from typing import Any

from features.coding_agent import HOST_MODE, AgentMode, normalize_mode
from features.coding_agent.backends import ContainerBackend, HostBackend
from features.coding_agent.types import (
    MAX_CUSTOM_TOOLS,
    MODE_LABELS,
    mode_supports,
    result_error,
)

from .base import ToolContext, tool
from .coding_schemas import (
    AgentApplyPatchArgs,
    AgentBashArgs,
    AgentEditArgs,
    AgentEmptyArgs,
    AgentGlobArgs,
    AgentGrepArgs,
    AgentLsArgs,
    AgentNotebookEditArgs,
    AgentPlanArgs,
    AgentReadArgs,
    AgentSpawnArgs,
    AgentTodoArgs,
    AgentToolCreateArgs,
    AgentToolDeleteArgs,
    AgentToolListArgs,
    AgentToolRunArgs,
    AgentWriteArgs,
)


def _container_mode(ctx: ToolContext) -> AgentMode:
    return normalize_mode(
        ctx.extras.get("agent_container_mode") or ctx.extras.get("agent_mode"),
        default=HOST_MODE,
    )


def _backend(ctx: ToolContext, target: str):
    target_text = str(target or "host").strip().lower()
    if target_text == "container":
        service = ctx.container
        if service is None:
            return None, result_error(
                "容器功能不可用；请先在容器页启用并启动容器。",
                code="agent_container_unavailable",
            )
        mode_text = ctx.extras.get("agent_container_mode")
        if mode_text is not None and str(mode_text).strip().lower() == "off":
            return None, result_error(
                "容器 Agent 模式未激活；请先在容器页选择 Pi/DSH/Claude Code。",
                code="agent_mode_not_active",
            )
        return ContainerBackend(service), None
    workspace = ctx.workspace_dir
    if workspace is None:
        return None, result_error(
            "本机 workspace 未配置，编码工具不可用。",
            code="agent_workspace_missing",
        )
    execution = str(ctx.extras.get("agent_host_execution") or "sandbox").strip().lower()
    if execution not in {"sandbox", "host"}:
        execution = "sandbox"
    sandbox_network = bool(ctx.extras.get("agent_sandbox_network", True))
    return (
        HostBackend(
            workspace,
            execution_mode=execution,
            sandbox_network=sandbox_network,
        ),
        None,
    )


def _wrap(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return result_error("编码工具返回了无效结果", code="agent_invalid_result")
    result.setdefault("tool_result_format", "structured_json")
    return result


def _backend_error(error: dict[str, Any] | None) -> dict[str, Any] | None:
    return _wrap(error) if error is not None else None


def _state(ctx: ToolContext):
    return ctx.extras.get("agent_session")


def _mode_for_target(ctx: ToolContext, target: str) -> AgentMode:
    return HOST_MODE if str(target or "host") != "container" else _container_mode(ctx)


def _capability_error(ctx: ToolContext, target: str, capability: str) -> dict[str, Any] | None:
    mode = _mode_for_target(ctx, target)
    if mode_supports(mode, capability):
        return None
    return result_error(
        f"当前 {MODE_LABELS[mode]} 模式不支持 {capability} 工具。",
        code="agent_mode_unsupported",
        mode=mode,
    )


def _state_capability_error(ctx: ToolContext, capability: str) -> dict[str, Any] | None:
    """Check session-state tools against the currently active agent mode."""
    mode_text = ctx.extras.get("agent_container_mode")
    active = str(mode_text or "").strip().lower()
    mode = _container_mode(ctx) if active and active != "off" else HOST_MODE
    if mode_supports(mode, capability):
        return None
    return result_error(
        f"当前 {MODE_LABELS[mode]} 模式不支持 {capability}。",
        code="agent_mode_unsupported",
        mode=mode,
    )


def _custom_backend(ctx: ToolContext, target: str):
    """Resolve a backend for Pi/DSH custom tools (container only)."""
    target_text = str(target or "container").strip().lower()
    if target_text != "container":
        return None, result_error(
            "自定义工具只支持 container 的 Pi/DSH 模式；本机固定使用 Claude Code 语义。",
            code="agent_custom_tools_host_unsupported",
        )
    backend, error = _backend(ctx, "container")
    if error:
        return None, error
    mode = _container_mode(ctx)
    if not mode_supports(mode, "custom_tools"):
        return None, result_error(
            f"当前 {MODE_LABELS[mode]} 模式不支持编写自定义工具；请切换到 Pi 或 DSH。",
            code="agent_custom_tools_unsupported",
            mode=mode,
        )
    return backend, None


def _plan_denied(ctx: ToolContext) -> dict[str, Any] | None:
    state = _state(ctx)
    if state is not None and getattr(state, "mode", "coding") == "plan":
        return result_error(
            "当前处于计划模式，写文件/命令类工具被禁用；先 agent_exit_plan 提交计划。",
            code="agent_plan_mode_denied",
        )
    return None


@tool(
    name="agent_read",
    description=(
        "读取文件并返回带行号的文本。target=host 读本机 workspace，target=container "
        "读容器 /workspace。支持 offset/limit 分页、二进制检测和字节上限；图片请用 "
        "describe_image。需要修改文件前先用它确认原文。"
    ),
    args_model=AgentReadArgs,
    category="coding",
    search_tags=["read", "file", "coding", "agent", "读取"],
    examples=[{"path": "src/main.py", "offset": 1, "limit": 200, "target": "host"}],
)
async def agent_read(args: AgentReadArgs, ctx: ToolContext) -> dict[str, Any]:
    backend, error = _backend(ctx, args.target)
    if error:
        return _backend_error(error)  # type: ignore[return-value]
    assert backend is not None
    return _wrap(
        await backend.read(
            args.path,
            offset=args.offset,
            limit=args.limit,
            max_bytes=args.max_bytes,
        )
    )


@tool(
    name="agent_write",
    description=(
        "创建或完整覆盖一个文本文件（UTF-8，原子写入，自动创建父目录）。"
        "target=host/container 指定本机或容器。覆盖已有文件前应先用 agent_read 阅读；"
        "小范围修改优先用 agent_edit。"
    ),
    args_model=AgentWriteArgs,
    category="coding",
    risk_level="medium",
    search_tags=["write", "file", "coding", "agent", "写入"],
    examples=[{"path": "src/main.py", "content": "print('hi')\n", "target": "host"}],
)
async def agent_write(args: AgentWriteArgs, ctx: ToolContext) -> dict[str, Any]:
    denied = _plan_denied(ctx)
    if denied:
        return denied
    backend, error = _backend(ctx, args.target)
    if error:
        return _backend_error(error)  # type: ignore[return-value]
    assert backend is not None
    return _wrap(
        await backend.write(
            args.path,
            args.content,
            create_parents=args.create_parents,
        )
    )


@tool(
    name="agent_edit",
    description=(
        "对文件做精确字面替换。old_string 必须在原文中匹配；默认要求唯一匹配，"
        "replace_all=true 可替换全部。支持一次提交多个 edits，按原始文本校验并避免重叠。"
        "target=host/container 指定本机或容器。"
    ),
    args_model=AgentEditArgs,
    category="coding",
    risk_level="medium",
    search_tags=["edit", "replace", "file", "coding", "agent", "编辑"],
    examples=[
        {
            "path": "src/main.py",
            "edits": [{"old_string": "old", "new_string": "new"}],
            "target": "host",
        }
    ],
)
async def agent_edit(args: AgentEditArgs, ctx: ToolContext) -> dict[str, Any]:
    denied = _plan_denied(ctx)
    if denied:
        return denied
    backend, error = _backend(ctx, args.target)
    if error:
        return _backend_error(error)  # type: ignore[return-value]
    assert backend is not None
    payload = [edit.model_dump() for edit in args.edits]
    return _wrap(await backend.edit(args.path, payload))


@tool(
    name="agent_apply_patch",
    description=(
        "应用 unified diff 补丁（git diff / diff -u），支持一次修改多个文件、新建和删除。"
        "会严格校验上下文和路径，不会越出 workspace；失败时不会写入任何文件。"
        "dry_run=true 只预检。DSH/Claude Code 模式支持；Pi 模式不支持。"
        "target=host/container 指定本机或容器。"
    ),
    args_model=AgentApplyPatchArgs,
    category="coding",
    risk_level="medium",
    search_tags=["patch", "diff", "apply", "coding", "agent", "补丁"],
    examples=[
        {
            "patch": (
                "--- a/note.txt\n"
                "+++ b/note.txt\n"
                "@@ -1,1 +1,1 @@\n"
                "-old\n"
                "+new\n"
            ),
            "target": "host",
        }
    ],
)
async def agent_apply_patch(args: AgentApplyPatchArgs, ctx: ToolContext) -> dict[str, Any]:
    denied = _plan_denied(ctx)
    if denied:
        return denied
    unsupported = _capability_error(ctx, args.target, "apply_patch")
    if unsupported:
        return unsupported
    backend, error = _backend(ctx, args.target)
    if error:
        return _backend_error(error)  # type: ignore[return-value]
    assert backend is not None
    return _wrap(
        await backend.apply_patch(
            args.patch,
            strip=args.strip,
            dry_run=args.dry_run,
            timeout_seconds=args.timeout_seconds,
        )
    )


@tool(
    name="agent_bash",
    description=(
        "在 coding 环境执行 shell 命令，返回 exit_code/stdout/stderr。"
        "target=host 时按本机设置使用 bubblewrap 沙箱（默认联网）或直接 host 执行；"
        "target=container 时在容器 /workspace 内执行。cwd 必须在工作区内。"
        "超时默认 120 秒，输出有上限。"
    ),
    args_model=AgentBashArgs,
    category="coding",
    risk_level="high",
    search_tags=["bash", "shell", "command", "coding", "agent", "命令"],
    examples=[{"command": "ls -la", "cwd": ".", "target": "host"}],
)
async def agent_bash(args: AgentBashArgs, ctx: ToolContext) -> dict[str, Any]:
    denied = _plan_denied(ctx)
    if denied:
        return denied
    backend, error = _backend(ctx, args.target)
    if error:
        return _backend_error(error)  # type: ignore[return-value]
    assert backend is not None
    return _wrap(
        await backend.bash(
            args.command,
            cwd=args.cwd,
            timeout_seconds=args.timeout_seconds,
            stdin=args.stdin,
        )
    )


@tool(
    name="agent_glob",
    description=(
        "按 glob 模式查找文件（只返回文件，不跟随符号链接）。target=host/container。"
        "例如 **/*.py、src/**/*.ts。结果按修改时间倒序，受数量上限约束。"
    ),
    args_model=AgentGlobArgs,
    category="coding",
    search_tags=["glob", "find", "file", "coding", "agent", "查找"],
    examples=[{"pattern": "**/*.py", "path": ".", "target": "host"}],
)
async def agent_glob(args: AgentGlobArgs, ctx: ToolContext) -> dict[str, Any]:
    backend, error = _backend(ctx, args.target)
    if error:
        return _backend_error(error)  # type: ignore[return-value]
    assert backend is not None
    return _wrap(
        await backend.glob(
            args.pattern,
            path=args.path,
            limit=args.limit,
            include_hidden=args.include_hidden,
        )
    )


@tool(
    name="agent_grep",
    description=(
        "在文件内容中搜索正则或字面文本，可输出匹配内容、文件列表或计数。"
        "支持 ignore_case、context、head_limit/offset；跳过二进制和常见构建目录。"
        "target=host/container 指定本机或容器。"
    ),
    args_model=AgentGrepArgs,
    category="coding",
    search_tags=["grep", "search", "regex", "coding", "agent", "搜索"],
    examples=[{"pattern": "TODO", "glob": "*.py", "target": "host"}],
)
async def agent_grep(args: AgentGrepArgs, ctx: ToolContext) -> dict[str, Any]:
    backend, error = _backend(ctx, args.target)
    if error:
        return _backend_error(error)  # type: ignore[return-value]
    assert backend is not None
    return _wrap(
        await backend.grep(
            args.pattern,
            path=args.path,
            glob=args.glob,
            ignore_case=args.ignore_case,
            literal=args.literal,
            context=args.context,
            output_mode=args.output_mode,
            head_limit=args.head_limit,
            offset=args.offset,
        )
    )


@tool(
    name="agent_ls",
    description=(
        "列出目录内容，返回名称、类型、大小、修改时间、权限和符号链接目标；"
        "目录优先排序，不跟随符号链接。target=host/container。"
    ),
    args_model=AgentLsArgs,
    category="coding",
    search_tags=["ls", "list", "directory", "coding", "agent", "目录"],
    examples=[{"path": ".", "target": "host"}],
)
async def agent_ls(args: AgentLsArgs, ctx: ToolContext) -> dict[str, Any]:
    backend, error = _backend(ctx, args.target)
    if error:
        return _backend_error(error)  # type: ignore[return-value]
    assert backend is not None
    return _wrap(
        await backend.ls(
            args.path,
            limit=args.limit,
            include_hidden=args.include_hidden,
        )
    )


@tool(
    name="agent_tool_create",
    description=(
        "Pi/DSH 自定义工具：让 LLM 编写一个 Python 工具并保存到当前容器的 "
        ".karen-agents/tools。工具从 stdin 读取 JSON 参数对象，向 stdout 输出结果，"
        "退出码非 0 表示失败；只应使用 Python 标准库。创建后用 agent_tool_run 调用。"
        "host 固定 Claude Code 语义，不支持自定义工具。"
    ),
    args_model=AgentToolCreateArgs,
    category="coding",
    risk_level="high",
    search_tags=["custom", "tool", "plugin", "pi", "dsh", "自定义", "插件"],
    examples=[
        {
            "name": "count_words",
            "description": "统计文本中的单词数",
            "code": "import json, sys\nargs=json.load(sys.stdin)\nprint(len(args.get('text','').split()))\n",
            "target": "container",
        }
    ],
)
async def agent_tool_create(args: AgentToolCreateArgs, ctx: ToolContext) -> dict[str, Any]:
    denied = _plan_denied(ctx)
    if denied:
        return denied
    backend, error = _custom_backend(ctx, args.target)
    if error:
        return _backend_error(error)  # type: ignore[return-value]
    assert backend is not None
    try:
        compile(str(args.code), f"<custom-tool:{args.name}>", "exec")
    except (SyntaxError, ValueError) as exc:
        return result_error(f"自定义工具代码语法错误：{exc}", code="agent_custom_tool_syntax")
    listed = await backend.list_custom_tools()
    if listed.get("ok"):
        existing = {
            str(item.get("name") or "") for item in (listed.get("tools") or [])
        }
        if args.name in existing and not args.overwrite:
            return result_error(
                f"自定义工具已存在：{args.name}；如要替换请设置 overwrite=true。",
                code="agent_custom_tool_exists",
            )
        if args.name not in existing and len(existing) >= MAX_CUSTOM_TOOLS:
            return result_error(
                f"自定义工具数量已达到上限（{MAX_CUSTOM_TOOLS}）。",
                code="agent_custom_tools_limit",
            )
    result = await backend.write_custom_tool(args.name, args.code, args.description)
    if result.get("ok"):
        result["next"] = (
            "用 agent_tool_run 传入 arguments JSON 调用它；"
            "如果工具需要参数说明，请把说明写在 description 里。"
        )
    return _wrap(result)


@tool(
    name="agent_tool_list",
    description=(
        "列出当前容器中已保存的 Pi/DSH 自定义工具（名称、说明、大小、创建时间）。"
        "列出后用 agent_tool_run 调用。"
    ),
    args_model=AgentToolListArgs,
    category="coding",
    search_tags=["custom", "tool", "plugin", "list", "自定义", "插件"],
)
async def agent_tool_list(args: AgentToolListArgs, ctx: ToolContext) -> dict[str, Any]:
    backend, error = _custom_backend(ctx, args.target)
    if error:
        return _backend_error(error)  # type: ignore[return-value]
    assert backend is not None
    return _wrap(await backend.list_custom_tools())


@tool(
    name="agent_tool_run",
    description=(
        "执行一个已保存的 Pi/DSH 自定义工具，把 arguments 作为 JSON 从 stdin 传入。"
        "返回 exit_code、stdout、stderr；stdout 是合法 JSON 时会同时给出 output_json。"
        "超时默认 60 秒，最大 300 秒。"
    ),
    args_model=AgentToolRunArgs,
    category="coding",
    risk_level="high",
    search_tags=["custom", "tool", "plugin", "run", "自定义", "插件"],
    examples=[
        {"name": "count_words", "arguments": {"text": "hello world"}, "target": "container"}
    ],
)
async def agent_tool_run(args: AgentToolRunArgs, ctx: ToolContext) -> dict[str, Any]:
    denied = _plan_denied(ctx)
    if denied:
        return denied
    backend, error = _custom_backend(ctx, args.target)
    if error:
        return _backend_error(error)  # type: ignore[return-value]
    assert backend is not None
    return _wrap(
        await backend.run_custom_tool(
            args.name,
            args.arguments,
            timeout_seconds=args.timeout_seconds,
        )
    )


@tool(
    name="agent_tool_delete",
    description="删除当前容器中的一个 Pi/DSH 自定义工具及其说明文件。",
    args_model=AgentToolDeleteArgs,
    category="coding",
    risk_level="medium",
    search_tags=["custom", "tool", "plugin", "delete", "自定义", "插件"],
)
async def agent_tool_delete(args: AgentToolDeleteArgs, ctx: ToolContext) -> dict[str, Any]:
    denied = _plan_denied(ctx)
    if denied:
        return denied
    backend, error = _custom_backend(ctx, args.target)
    if error:
        return _backend_error(error)  # type: ignore[return-value]
    assert backend is not None
    return _wrap(await backend.delete_custom_tool(args.name))


def _find_notebook_cell(cells: list[Any], index: int | None, cell_id: str) -> int:
    """Resolve a notebook cell by id or 0-based index."""
    if cell_id:
        for position, cell in enumerate(cells):
            if isinstance(cell, dict) and str(cell.get("id") or "") == cell_id:
                return position
        return -1
    if index is None:
        return -1
    return index if 0 <= index < len(cells) else -1


@tool(
    name="agent_notebook_edit",
    description=(
        "编辑 Jupyter .ipynb 单元格：replace/insert/delete。按 cell_id 或 0-based "
        "cell_index 定位；insert 默认追加到末尾，cell_index=-1 也表示末尾。"
        "保留 notebook 其它字段，原子写回。仅 Claude Code 模式支持；"
        "target=host/container 指定本机或容器。"
    ),
    args_model=AgentNotebookEditArgs,
    category="coding",
    risk_level="medium",
    search_tags=["notebook", "jupyter", "ipynb", "cell", "coding", "笔记本"],
    examples=[
        {
            "path": "analysis.ipynb",
            "edit_mode": "replace",
            "cell_index": 0,
            "new_source": "print('hello')\n",
            "target": "host",
        }
    ],
)
async def agent_notebook_edit(
    args: AgentNotebookEditArgs, ctx: ToolContext
) -> dict[str, Any]:
    denied = _plan_denied(ctx)
    if denied:
        return denied
    unsupported = _capability_error(ctx, args.target, "notebook")
    if unsupported:
        return unsupported
    backend, error = _backend(ctx, args.target)
    if error:
        return _backend_error(error)  # type: ignore[return-value]
    assert backend is not None
    try:
        raw = await backend.read_raw(args.path)
    except Exception as exc:  # noqa: BLE001 - backend boundary
        return result_error(f"读取 notebook 失败：{exc}", code="agent_notebook_failed")
    if not raw.get("ok"):
        return _wrap(raw)
    try:
        notebook = json.loads(str(raw.get("content") or ""))
    except (json.JSONDecodeError, ValueError) as exc:
        return result_error(f"notebook 不是有效 JSON：{exc}", code="agent_notebook_invalid")
    if not isinstance(notebook, dict) or not isinstance(notebook.get("cells"), list):
        return result_error(
            "文件不是有效的 Jupyter notebook（缺少 cells 列表）",
            code="agent_notebook_invalid",
        )
    cells: list[Any] = notebook["cells"]
    index = _find_notebook_cell(cells, args.cell_index, args.cell_id)
    if args.edit_mode == "insert":
        if args.cell_index is not None and args.cell_index not in {-1, len(cells) - 1}:
            if not 0 <= args.cell_index < len(cells):
                return result_error("cell_index 越界", code="agent_notebook_invalid")
        position = (
            len(cells)
            if args.cell_index is None or args.cell_index == -1
            else args.cell_index + 1
        )
        cell: dict[str, Any] = {
            "cell_type": args.cell_type,
            "metadata": {},
            "source": args.new_source,
        }
        if args.cell_type == "code":
            cell["execution_count"] = None
            cell["outputs"] = []
        cells.insert(position, cell)
        action_index = position
    elif args.edit_mode == "replace":
        if index < 0:
            return result_error(
                "找不到要替换的单元格；请提供有效 cell_id 或 cell_index",
                code="agent_notebook_cell_missing",
            )
        if not isinstance(cells[index], dict):
            return result_error(
                "目标单元格不是对象", code="agent_notebook_invalid"
            )
        cells[index]["source"] = args.new_source
        action_index = index
    else:
        if index < 0:
            return result_error(
                "找不到要删除的单元格；请提供有效 cell_id 或 cell_index",
                code="agent_notebook_cell_missing",
            )
        if len(cells) <= 1:
            return result_error(
                "不能删除 notebook 的最后一个单元格", code="agent_notebook_invalid"
            )
        cells.pop(index)
        action_index = index
    content = json.dumps(notebook, ensure_ascii=False, indent=1) + "\n"
    written = await backend.write(args.path, content)
    if not written.get("ok"):
        return _wrap(written)
    return {
        "ok": True,
        "status": "done",
        "brief": f"notebook 已{args.edit_mode}第 {action_index} 个单元格。",
        "path": written.get("path", args.path),
        "action": args.edit_mode,
        "cell_index": action_index,
        "cell_count": len(cells),
        "tool_result_format": "structured_json",
    }


@tool(
    name="agent_spawn",
    description=(
        "启动一个真正的后台编码子 Agent 执行较大的代码任务，并等待结果返回。"
        "子 Agent 拥有受限的读写/搜索/命令/补丁工具，不会联系用户或修改记忆；"
        "target=host 使用本机 workspace，target=container 使用当前容器 /workspace。"
        "适合大范围调研、批量修改或独立验证；小任务直接自己做。"
        "DSH/Claude Code 支持；Pi 不支持。"
    ),
    args_model=AgentSpawnArgs,
    category="coding",
    risk_level="high",
    search_tags=["spawn", "subagent", "agent", "coding", "子智能体", "子代理"],
    examples=[
        {
            "prompt": "检查 src/ 中所有 Python 文件的异常处理，并修复明显的吞异常问题。",
            "max_loops": 10,
            "target": "host",
        }
    ],
)
async def agent_spawn(args: AgentSpawnArgs, ctx: ToolContext) -> dict[str, Any]:
    denied = _plan_denied(ctx)
    if denied:
        return denied
    unsupported = _capability_error(ctx, args.target, "spawn")
    if unsupported:
        return unsupported
    target = str(args.target or "host").strip().lower()
    if target == "container":
        _backend_value, error = _backend(ctx, "container")
        if error:
            return _backend_error(error)  # type: ignore[return-value]
    if ctx.agent_task_cb is None:
        return result_error(
            "当前运行时不支持子 Agent 任务", code="agent_spawn_unavailable"
        )
    sources = []
    if args.context.strip():
        sources.append({"type": "inline_text", "value": args.context})
    payload = {
        "prompt": args.prompt,
        "sources": sources,
        "output_format": "markdown",
        "output_name": args.output_name or "agent-spawn.md",
        "max_loops": args.max_loops,
        "coding_target": target,
    }
    result = await ctx.agent_task_cb(payload)
    return _wrap(result if isinstance(result, dict) else {})


@tool(
    name="agent_todo",
    description=(
        "完整替换当前会话的编码待办列表。每项包含 content 和 status"
        "（pending/in_progress/completed），最多 20 项。用于较长编码任务的进度管理。"
    ),
    args_model=AgentTodoArgs,
    category="coding",
    search_tags=["todo", "task", "plan", "coding", "待办"],
)
async def agent_todo(args: AgentTodoArgs, ctx: ToolContext) -> dict[str, Any]:
    unsupported = _state_capability_error(ctx, "todo")
    if unsupported:
        return unsupported
    state = _state(ctx)
    if state is None:
        return result_error("当前会话没有 Agent 状态", code="agent_state_unavailable")
    todos = state.replace_todos([item.model_dump() for item in args.todos])
    return {
        "ok": True,
        "status": "updated",
        "brief": f"已更新 {len(todos)} 项待办。",
        "todos": todos,
    }


@tool(
    name="agent_enter_plan",
    description=(
        "进入计划模式：只读分析，禁止写文件、编辑和执行命令。完成调研后调用 "
        "agent_exit_plan 提交计划。"
    ),
    args_model=AgentEmptyArgs,
    category="coding",
    search_tags=["plan", "planning", "coding", "计划"],
)
async def agent_enter_plan(args: AgentEmptyArgs, ctx: ToolContext) -> dict[str, Any]:
    unsupported = _state_capability_error(ctx, "plan")
    if unsupported:
        return unsupported
    state = _state(ctx)
    if state is None:
        return result_error("当前会话没有 Agent 状态", code="agent_state_unavailable")
    state.mode = "plan"
    return {
        "ok": True,
        "status": "plan_mode",
        "brief": "已进入计划模式；写文件和命令工具暂时禁用。",
        "allowed_tools": ["agent_read", "agent_glob", "agent_grep", "agent_ls", "agent_exit_plan"],
    }


@tool(
    name="agent_exit_plan",
    description=(
        "退出计划模式并提交计划正文（Markdown）。提交后恢复写文件/命令工具；"
        "计划会返回给模型，模型可用 send_* 发给用户确认。"
    ),
    args_model=AgentPlanArgs,
    category="coding",
    search_tags=["plan", "planning", "coding", "计划"],
)
async def agent_exit_plan(args: AgentPlanArgs, ctx: ToolContext) -> dict[str, Any]:
    unsupported = _state_capability_error(ctx, "plan")
    if unsupported:
        return unsupported
    state = _state(ctx)
    if state is None:
        return result_error("当前会话没有 Agent 状态", code="agent_state_unavailable")
    plan = state.set_plan(args.plan)
    return {
        "ok": True,
        "status": "plan_submitted",
        "brief": "计划已提交；已退出计划模式。",
        "plan": plan,
        "next": "把计划发给用户确认后再继续修改；用户反馈可直接作为下一轮输入。",
    }


__all__ = [
    "agent_apply_patch",
    "agent_bash",
    "agent_edit",
    "agent_enter_plan",
    "agent_exit_plan",
    "agent_glob",
    "agent_grep",
    "agent_ls",
    "agent_notebook_edit",
    "agent_read",
    "agent_spawn",
    "agent_todo",
    "agent_tool_create",
    "agent_tool_delete",
    "agent_tool_list",
    "agent_tool_run",
    "agent_write",
]
