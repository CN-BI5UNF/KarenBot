"""Toolset catalog and routed schema profile."""

from __future__ import annotations

import json

import pytest
import tiktoken

from tests.integration_pipeline.helpers import _make_root_config
from tools import ToolContext, ToolRegistry, build_default_registry, get_default_specs
from tools.schemas import LoadToolsetArgs, ToolSearchArgs
from tools.tool_search_tools import tool_search
from tools.toolset_tools import list_toolsets, load_toolset
from tools.toolsets import (
    CORE_TOOL_NAMES,
    META_TOOL_NAMES,
    TOOLSETS,
    ToolsetSession,
    allowed_tool_names,
    resolve_toolset,
    toolsets_for_tool,
    unclassified_tools,
)


def _registry(profile: str = "routed"):
    cfg = _make_root_config()
    cfg.behavior.tool_schema_profile = profile
    return build_default_registry(cfg)


def _schema_names(reg: ToolRegistry, session: ToolsetSession | None = None) -> list[str]:
    if session is None:
        return [item["function"]["name"] for item in reg.get_schemas()]
    return [item["function"]["name"] for item in reg.get_routed_schemas(session)]


def test_every_registered_tool_is_classified_into_at_least_one_toolset():
    names = {spec.name for spec in get_default_specs()}
    assert unclassified_tools(names) == set()
    catalog_names = set().union(*(set(item.tools) for item in TOOLSETS))
    assert catalog_names <= names
    assert CORE_TOOL_NAMES <= names
    assert META_TOOL_NAMES <= CORE_TOOL_NAMES
    for item in TOOLSETS:
        assert item.tools, item.id
        assert item.title and item.description


def test_toolsets_allow_overlap_and_aliases():
    assert "messaging" in toolsets_for_tool("upload_file")
    assert "workspace" in toolsets_for_tool("upload_file")
    assert "control" in toolsets_for_tool("group_trigger_window")
    assert resolve_toolset("doc").id == "workspace"
    assert resolve_toolset("docker").id == "container"
    assert resolve_toolset("not-a-toolset") is None
    assert {"send_group_message", "read_file"}.issubset(
        allowed_tool_names({"messaging", "workspace"})
    )


def test_routed_profile_starts_with_core_and_loads_only_requested_toolsets():
    reg = _registry("routed")
    session = ToolsetSession()
    for name in reg.names():
        assert reg.get_spec(name).toolsets, name

    initial = _schema_names(reg, session)
    assert set(initial) == set(CORE_TOOL_NAMES)
    assert "read_file" not in initial
    assert "list_toolsets" in initial and "load_toolset" in initial

    session.load("workspace")
    loaded = _schema_names(reg, session)
    assert "read_file" in loaded
    assert "write_file" in loaded
    assert "list_emoji" not in loaded
    assert set(loaded) > set(initial)
    assert reg.get_routed_schemas(session) is reg.get_routed_schemas(session)


def test_compact_and_full_profiles_do_not_register_layer_one_meta_tools():
    for profile in ("compact", "full"):
        reg = _registry(profile)
        names = set(reg.names())
        assert "list_toolsets" not in names
        assert "load_toolset" not in names
        assert "write_file" in names


def test_routed_initial_schema_is_smaller_than_compact():
    routed = _registry("routed")
    compact = _registry("compact")
    encoding = tiktoken.get_encoding("o200k_base")

    def tokens(schemas):
        return sum(
            len(encoding.encode(json.dumps(schema, ensure_ascii=False, separators=(",", ":"))))
            for schema in schemas
        )

    routed_tokens = tokens(routed.get_routed_schemas(ToolsetSession()))
    compact_tokens = tokens(compact.get_schemas())
    assert routed_tokens < compact_tokens
    assert routed_tokens <= 3_500


def test_routed_schema_descriptions_are_actionable():
    """路由模式下每个工具都应有可读说明，meta 工具不能退化成工具名。"""
    reg = _registry("routed")
    schemas = {
        schema["function"]["name"]: schema["function"]
        for schema in reg.get_routed_schemas(ToolsetSession())
    }
    for name, function in schemas.items():
        description = function["description"].strip()
        assert description, name
        assert description != name, name
        assert len(description) >= 8, name

    assert "load_toolset" in schemas["list_toolsets"]["description"]
    assert "本会话内保持" in schemas["load_toolset"]["description"]
    assert "路由模式" in schemas["tool_search"]["description"]


def test_routed_risk_hints_cover_dangerous_tools():
    """路由模式不能把高风险/中风险工具降成 low。"""
    reg = _registry("routed")
    assert reg.get_spec("set_group_ban").risk_level == "high"
    assert reg.get_spec("run_python").risk_level == "medium"
    assert reg.get_spec("delete_file").risk_level == "medium"


def test_compact_stub_descriptions_explain_the_tool():
    """stub 描述先说明用途；tool_search 的要求由占位参数表达。"""
    reg = _registry("compact")
    schemas = {
        schema["function"]["name"]: schema["function"]
        for schema in reg.get_schemas()
    }
    for name, expected in (
        ("read_file", "读取 workspace"),
        ("run_python", "执行 Python"),
        ("set_group_ban", "高风险"),
    ):
        description = schemas[name]["description"]
        assert expected in description
        assert "tool_search" not in description
        assert "_tool_search_required" in schemas[name]["parameters"]["properties"]


@pytest.mark.asyncio
async def test_executor_rejects_unloaded_tools_until_toolset_is_loaded():
    reg = _registry("routed")
    session = ToolsetSession()
    ctx = ToolContext(
        extras={"tool_registry": reg, "toolset_session": session}
    )
    executor = reg.get_executor(ctx)

    blocked = await executor("run_python", {"code": "print(1)"})
    assert blocked["ok"] is False
    assert blocked["status"] == "need_toolset"

    session.load("workspace")
    allowed = await executor("run_python", {"code": "print(1)"})
    assert allowed["status"] != "need_toolset"


@pytest.mark.asyncio
async def test_tool_search_reports_load_state_and_toolsets():
    reg = _registry("routed")
    session = ToolsetSession()
    ctx = ToolContext(
        extras={"tool_registry": reg, "toolset_session": session}
    )

    result = await tool_search(ToolSearchArgs(tool_name="read_file"), ctx)
    assert result["loaded"] is False
    assert result["toolsets"] == ["workspace"]
    assert "load_toolset" in result["next"]

    session.load("workspace")
    result = await tool_search(ToolSearchArgs(tool_name="read_file"), ctx)
    assert result["loaded"] is True
    assert "已加载" in result["next"]


@pytest.mark.asyncio
async def test_list_and_load_toolset_meta_tools():
    reg = _registry("routed")
    session = ToolsetSession()
    ctx = ToolContext(
        extras={"tool_registry": reg, "toolset_session": session}
    )

    listed = await list_toolsets(None, ctx)  # type: ignore[arg-type]
    assert listed["ok"] is True
    assert listed["loaded_toolsets"] == []
    assert "不要加载全部" in listed["next"]
    ids = {item["id"] for item in listed["toolsets"]}
    assert {"core", "workspace", "qq_admin"} <= ids
    assert "container" not in ids  # feature disabled in the test config

    loaded = await load_toolset(LoadToolsetArgs(name="doc"), ctx)
    assert loaded["ok"] is True
    assert loaded["toolset"] == "workspace"
    assert "read_file" in loaded["added_tools"]
    assert session.loaded_ids() == ["workspace"]

    again = await load_toolset(LoadToolsetArgs(name="workspace"), ctx)
    assert again["status"] == "already_loaded"

    missing = await load_toolset(LoadToolsetArgs(name="nope"), ctx)
    assert missing["ok"] is False
    assert missing["status"] == "not_found"


def test_routed_profile_accepts_alias_and_rejects_unknown():
    session = ToolsetSession()
    assert session.load("files") is True
    assert session.load("files") is False
    with pytest.raises(ValueError):
        session.load("unknown")


def test_routed_profile_is_valid_config_and_settings_choice():
    from app_config.schema import BehaviorConfig
    from webui.settings_spec import field_map

    assert BehaviorConfig(tool_schema_profile="routed").tool_schema_profile == "routed"
    spec = field_map()["behavior.tool_schema_profile"]
    values = [value for value, _label in spec["options"]]
    assert "routed" in values
    assert "load_toolset" in spec["help"]


def test_routed_prompt_policy_is_only_injected_in_routed_mode():
    from agents.behavior_prompt import build_tool_use_protocol

    normal = build_tool_use_protocol("file")
    routed = build_tool_use_protocol("file", tool_routing=True)
    assert "toolset_routing_policy" not in normal
    assert "toolset_routing_policy" in routed
    assert "load_toolset" in routed
