"""Work-mode tool profile hot-switch and same-message grace handling."""

from types import SimpleNamespace

from core.message_pipeline import MessagePipeline


class _FakeRegistry:
    def __init__(self, label, profile, names, *, agent_names=None):
        self.label = label
        self.schema_profile = profile
        self._names = set(names)
        self._agent_names = set(agent_names if agent_names is not None else names)
        self.calls = []

    def __contains__(self, name):
        return name in self._names

    def agent_tool_names(self, session):
        return list(self._agent_names)

    def get_schemas(self):
        return [{"function": {"name": name}} for name in sorted(self._names)]

    def get_agent_schemas(self, session):
        return [
            {"function": {"name": name}} for name in sorted(self._agent_names)
        ]

    def get_executor(self, ctx):
        async def executor(tool_name, raw_args, *, tool_call_id=None):
            self.calls.append(tool_name)
            return {"ok": True, "registry": self.label}

        return executor


def _pipeline(*, agent, old):
    pipeline = MessagePipeline.__new__(MessagePipeline)
    pipeline.tool_registry = agent
    pipeline._tool_profile_override = "agent"
    pipeline._tool_profile_grace_registry = old
    pipeline._tool_profile_restore_notice = ""
    return pipeline


async def test_same_message_old_profile_tool_uses_grace_registry():
    agent = _FakeRegistry(
        "agent", "agent", {"agent_read", "work"}, agent_names={"agent_read", "work"}
    )
    old = _FakeRegistry("compact", "compact", {"read_file", "work"})
    pipeline = _pipeline(agent=agent, old=old)
    session = SimpleNamespace(loaded_tools=set())
    ctx = SimpleNamespace(extras={"toolset_session": session})

    executor = pipeline._dynamic_tool_executor(ctx)
    result = await executor("read_file", {})

    assert result == {"ok": True, "registry": "compact"}
    assert old.calls == ["read_file"]
    assert agent.calls == []


async def test_agent_core_tool_does_not_fall_back_to_grace():
    agent = _FakeRegistry(
        "agent", "agent", {"agent_read", "read_file"}, agent_names={"agent_read"}
    )
    old = _FakeRegistry("compact", "compact", {"read_file", "work"})
    pipeline = _pipeline(agent=agent, old=old)
    session = SimpleNamespace(loaded_tools=set())
    ctx = SimpleNamespace(extras={"toolset_session": session})

    executor = pipeline._dynamic_tool_executor(ctx)
    result = await executor("agent_read", {})

    assert result == {"ok": True, "registry": "agent"}
    assert agent.calls == ["agent_read"]
    assert old.calls == []


def test_tools_provider_clears_grace_after_next_request():
    agent = _FakeRegistry(
        "agent", "agent", {"agent_read"}, agent_names={"agent_read"}
    )
    old = _FakeRegistry("compact", "compact", {"read_file"})
    pipeline = _pipeline(agent=agent, old=old)
    session = SimpleNamespace(loaded_tools=set())

    provider = pipeline._tools_provider_for(session)
    names = {schema["function"]["name"] for schema in provider()}

    assert names == {"agent_read"}
    assert pipeline._tool_profile_grace_registry is None


async def test_unknown_tool_without_grace_uses_current_registry():
    agent = _FakeRegistry(
        "agent", "agent", {"agent_read"}, agent_names={"agent_read"}
    )
    old = _FakeRegistry("compact", "compact", {"read_file"})
    pipeline = _pipeline(agent=agent, old=old)
    pipeline._tool_profile_grace_registry = None
    session = SimpleNamespace(loaded_tools=set())
    ctx = SimpleNamespace(extras={"toolset_session": session})

    executor = pipeline._dynamic_tool_executor(ctx)
    result = await executor("read_file", {})

    assert result == {"ok": True, "registry": "agent"}
    assert agent.calls == ["read_file"]
    assert old.calls == []
