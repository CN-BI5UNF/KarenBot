"""Pydantic argument models for native coding-agent tools."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .schemas import _ToolArgs

AgentTarget = Literal["host", "container"]


class _TargetArgs(_ToolArgs):
    target: AgentTarget = Field(
        default="host",
        description=(
            "执行位置：host=本机 AI workspace（Claude Code 语义）；"
            "container=当前容器 /workspace（使用容器页当前激活的 Agent 模式）。"
        ),
    )


class AgentReadArgs(_TargetArgs):
    path: str = Field(..., min_length=1, max_length=1024, description="文件路径。")
    offset: int = Field(default=1, ge=1, description="起始行（1-based）。")
    limit: int = Field(default=2000, ge=1, le=20000, description="最多读取行数。")
    max_bytes: int = Field(
        default=51200, ge=1024, le=1048576, description="单次返回字节上限。"
    )


class AgentWriteArgs(_TargetArgs):
    path: str = Field(..., min_length=1, max_length=1024, description="文件路径。")
    content: str = Field(
        ..., max_length=8 * 1024 * 1024, description="完整文件内容（UTF-8）。"
    )
    create_parents: bool = Field(default=True, description="是否自动创建父目录。")


class AgentEditItem(_ToolArgs):
    old_string: str = Field(..., min_length=1, description="要替换的原始文本，必须精确匹配。")
    new_string: str = Field(default="", description="替换后的文本。")
    replace_all: bool = Field(default=False, description="是否替换全部匹配。")


class AgentEditArgs(_TargetArgs):
    path: str = Field(..., min_length=1, max_length=1024, description="文件路径。")
    edits: list[AgentEditItem] = Field(
        ..., min_length=1, max_length=50, description="按顺序应用的字面替换列表。"
    )


class AgentBashArgs(_TargetArgs):
    command: str = Field(
        ..., min_length=1, max_length=64 * 1024, description="要执行的 shell 命令。"
    )
    cwd: str = Field(default=".", max_length=1024, description="工作目录，必须在 workspace 内。")
    timeout_seconds: float = Field(
        default=120.0, ge=1.0, le=600.0, description="超时秒数，默认 120。"
    )
    stdin: str = Field(default="", max_length=1024 * 1024, description="可选 stdin 文本。")


class AgentGlobArgs(_TargetArgs):
    pattern: str = Field(
        ..., min_length=1, max_length=256, description="glob 模式，如 **/*.py。"
    )
    path: str = Field(default=".", max_length=1024, description="搜索根目录。")
    limit: int = Field(default=200, ge=1, le=2000, description="最多返回文件数。")
    include_hidden: bool = Field(default=False, description="是否包含隐藏文件。")


class AgentGrepArgs(_TargetArgs):
    pattern: str = Field(..., min_length=1, max_length=4096, description="正则或字面搜索内容。")
    path: str = Field(default=".", max_length=1024, description="搜索根目录。")
    glob: str = Field(default="", max_length=256, description="可选文件名 glob 过滤。")
    ignore_case: bool = Field(default=False, description="忽略大小写。")
    literal: bool = Field(default=False, description="按字面文本而不是正则匹配。")
    context: int = Field(default=0, ge=0, le=20, description="匹配行前后上下文行数。")
    output_mode: Literal["content", "files_with_matches", "count"] = Field(
        default="content", description="输出内容、文件列表或计数。"
    )
    head_limit: int = Field(default=100, ge=1, le=500, description="最多返回结果数。")
    offset: int = Field(default=0, ge=0, description="跳过前 N 条结果。")


class AgentLsArgs(_TargetArgs):
    path: str = Field(default=".", max_length=1024, description="目录路径。")
    limit: int = Field(default=500, ge=1, le=2000, description="最多返回条目数。")
    include_hidden: bool = Field(default=True, description="是否包含隐藏文件。")


class AgentTodoItem(_ToolArgs):
    content: str = Field(..., min_length=1, max_length=200, description="待办内容。")
    status: Literal["pending", "in_progress", "completed"] = Field(
        default="pending", description="待办状态。"
    )


class AgentTodoArgs(_ToolArgs):
    todos: list[AgentTodoItem] = Field(
        ..., max_length=20, description="完整替换当前待办列表。"
    )


class AgentPlanArgs(_ToolArgs):
    plan: str = Field(..., min_length=1, max_length=16384, description="计划正文（Markdown）。")


class AgentEmptyArgs(_ToolArgs):
    """No parameters."""


class _CustomToolTargetArgs(_ToolArgs):
    target: AgentTarget = Field(
        default="container",
        description=(
            "自定义工具只支持 container 的 Pi/DSH 模式；"
            "host 固定 Claude Code 语义，不支持编写自定义工具。"
        ),
    )


class AgentApplyPatchArgs(_TargetArgs):
    patch: str = Field(
        ...,
        min_length=1,
        max_length=1024 * 1024,
        description=(
            "unified diff 文本（git diff / diff -u）。支持修改、新建和删除文件；"
            "默认去除第一层路径前缀（a/、b/）。"
        ),
    )
    strip: int = Field(
        default=1, ge=0, le=8, description="去除路径前缀的层数；标准 git diff 用 1。"
    )
    dry_run: bool = Field(default=False, description="只校验补丁，不写入文件。")
    timeout_seconds: float = Field(
        default=120.0, ge=1.0, le=600.0, description="超时秒数。"
    )


class AgentNotebookEditArgs(_TargetArgs):
    path: str = Field(
        ..., min_length=1, max_length=1024, description=".ipynb 文件路径。"
    )
    edit_mode: Literal["replace", "insert", "delete"] = Field(
        ..., description="替换、插入或删除某个单元格。"
    )
    cell_index: int | None = Field(
        default=None,
        ge=-(2**31),
        le=2**31 - 1,
        description="单元格 0-based 下标；insert 时表示插入到它后面，-1 表示末尾。",
    )
    cell_id: str = Field(
        default="", max_length=256, description="可选单元格 id；与 cell_index 二选一。"
    )
    cell_type: Literal["code", "markdown"] = Field(
        default="code", description="insert 时新单元格类型；replace 保持原类型。"
    )
    new_source: str = Field(
        default="", max_length=1024 * 1024, description="新单元格源码（replace/insert）。"
    )


class AgentSpawnArgs(_TargetArgs):
    prompt: str = Field(
        ..., min_length=1, max_length=16384, description="交给子 Agent 的完整任务说明。"
    )
    context: str = Field(
        default="", max_length=65536, description="可选的附加资料（会作为内联文本传入）。"
    )
    max_loops: int = Field(
        default=8, ge=1, le=30, description="子 Agent 最大工具循环次数。"
    )
    output_name: str = Field(
        default="", max_length=128, description="结果文件名（默认 agent-spawn.md）。"
    )


class AgentToolCreateArgs(_CustomToolTargetArgs):
    name: str = Field(
        ...,
        pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$",
        description="工具名（字母开头，可含数字、_、-，最长 64）。",
    )
    description: str = Field(
        default="", max_length=1000, description="工具用途说明，供后续模型选择。"
    )
    code: str = Field(
        ...,
        min_length=1,
        max_length=256 * 1024,
        description=(
            "Python 3 源码。运行时从 stdin 读取一个 JSON 对象作为参数，"
            "向 stdout 输出结果；退出码非 0 表示失败。只能使用标准库。"
        ),
    )
    overwrite: bool = Field(default=False, description="是否覆盖同名工具。")


class AgentToolListArgs(_CustomToolTargetArgs):
    """List custom tools."""


class AgentToolRunArgs(_CustomToolTargetArgs):
    name: str = Field(
        ...,
        pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$",
        description="要执行的自定义工具名。",
    )
    arguments: dict[str, Any] = Field(
        default_factory=dict, description="传给工具的 JSON 参数对象。"
    )
    timeout_seconds: float = Field(
        default=60.0, ge=1.0, le=300.0, description="执行超时秒数。"
    )


class AgentToolDeleteArgs(_CustomToolTargetArgs):
    name: str = Field(
        ...,
        pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$",
        description="要删除的自定义工具名。",
    )


__all__ = [
    "AgentApplyPatchArgs",
    "AgentBashArgs",
    "AgentEditArgs",
    "AgentEditItem",
    "AgentEmptyArgs",
    "AgentGlobArgs",
    "AgentGrepArgs",
    "AgentLsArgs",
    "AgentNotebookEditArgs",
    "AgentPlanArgs",
    "AgentReadArgs",
    "AgentSpawnArgs",
    "AgentTodoArgs",
    "AgentTodoItem",
    "AgentToolCreateArgs",
    "AgentToolDeleteArgs",
    "AgentToolListArgs",
    "AgentToolRunArgs",
    "AgentWriteArgs",
]
