"""Feature tool execution tests."""

from __future__ import annotations

import io
import json

import pytest
from PIL import Image
from pydantic import ValidationError

from features.vision.vision_service import VisionService
from providers.base import ProviderError
from tests.tools.helpers import FakeSendAdapter, _make_config
from tools import ToolContext, build_default_registry
from tools.feature_tools import send_voice_message
from tools.schemas import SendVoiceMessageArgs


def _png_bytes() -> bytes:
    image = Image.new("RGB", (32, 24), (20, 120, 200))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _write_png(path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_png_bytes())


def _data_url() -> str:
    import base64

    return "data:image/png;base64," + base64.b64encode(_png_bytes()).decode("ascii")


@pytest.mark.asyncio
async def test_describe_image_without_vision_service():
    """未注入 vision 时，describe_image 返回未启用错误。"""
    cfg = _make_config(vision_enabled=True)  # registry 启用，但 ctx 没塞 service
    reg = build_default_registry(cfg)
    ctx = ToolContext()  # 没注入 vision
    executor = reg.get_executor(ctx)
    result = await executor(
        "describe_image", {"image_url": "https://x.com/a.png"}
    )
    assert result["ok"] is False
    assert "未启用" in result["error"]


@pytest.mark.asyncio
async def test_describe_image_uses_main_model_vision_fallback():
    """独立视觉服务关闭时，主模型原生图片输入可兜底 describe_image。"""

    class FakeVision:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        async def describe(self, image_url: str, prompt: str = "") -> str:
            self.calls.append((image_url, prompt))
            return "fallback-ok"

    cfg = _make_config(vision_enabled=True)
    reg = build_default_registry(cfg)
    fallback = FakeVision()
    executor = reg.get_executor(ToolContext(main_vision=fallback))
    result = await executor(
        "describe_image",
        {"image_url": _data_url(), "question": "图里是什么"},
    )

    assert result["ok"] is True
    assert fallback.calls and fallback.calls[0][1] == "图里是什么"


@pytest.mark.asyncio
async def test_describe_image_accepts_workspace_path(tmp_path):
    class FakeVision:
        def __init__(self) -> None:
            self.image_url = ""

        async def describe(self, image_url: str, prompt: str = "") -> str:
            self.image_url = image_url
            return "ok"

    workspace = tmp_path / "workspace"
    _write_png(workspace / "incoming" / "a.png")

    cfg = _make_config(vision_enabled=True)
    reg = build_default_registry(cfg)
    vision = FakeVision()
    ctx = ToolContext(vision=vision, workspace_dir=workspace)
    executor = reg.get_executor(ctx)
    result = await executor("describe_image", {"image_url": "incoming/a.png"})

    assert result["ok"] is True
    assert vision.image_url.startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_describe_image_missing_workspace_path_does_not_call_vision(tmp_path):
    class FakeVision:
        def __init__(self) -> None:
            self.calls = 0

        async def describe(self, image_url: str, prompt: str = "") -> str:
            self.calls += 1
            raise AssertionError("缺失 workspace 图片不应调用视觉 provider")

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    cfg = _make_config(vision_enabled=True)
    reg = build_default_registry(cfg)
    vision = FakeVision()
    ctx = ToolContext(vision=vision, workspace_dir=workspace)
    executor = reg.get_executor(ctx)
    result = await executor("describe_image", {"image_url": "incoming/missing.jpg"})

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["brief"] == "图片引用不可用。"
    assert "workspace 图片不存在" in result["error"]
    assert "真实出现的 [图片 url=...]" in result["error"]
    assert "不要根据 msg_id 猜 incoming/img_*.jpg" in result["error"]
    assert result["data"]["image_ref"] == "incoming/missing.jpg"
    assert result["data"]["retry_hint"]
    assert vision.calls == 0


@pytest.mark.asyncio
async def test_describe_image_relative_path_without_workspace_does_not_call_vision():
    class FakeVision:
        def __init__(self) -> None:
            self.calls = 0

        async def describe(self, image_url: str, prompt: str = "") -> str:
            self.calls += 1
            raise AssertionError("未配置 workspace 时相对图片路径不应调用视觉 provider")

    cfg = _make_config(vision_enabled=True)
    reg = build_default_registry(cfg)
    vision = FakeVision()
    ctx = ToolContext(vision=vision)
    executor = reg.get_executor(ctx)
    result = await executor("describe_image", {"image_url": "incoming/a.jpg"})

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert "workspace 未配置" in result["error"]
    assert "真实出现的 [图片 url=...]" in result["error"]
    assert result["data"]["image_ref"] == "incoming/a.jpg"
    assert vision.calls == 0


@pytest.mark.asyncio
async def test_describe_image_prefers_workspace_over_remote_url(tmp_path, monkeypatch):
    class FakeVision:
        def __init__(self) -> None:
            self.image_url = ""

        async def describe(self, image_url: str, prompt: str = "") -> str:
            self.image_url = image_url
            return "ok"

    async def fail_download(*args, **kwargs):
        raise AssertionError("workspace 已存在时不应下载远程图片")

    monkeypatch.setattr(
        "features.vision.image_assets._download_image",
        fail_download,
    )

    workspace = tmp_path / "workspace"
    _write_png(workspace / "incoming" / "a.png")

    cfg = _make_config(vision_enabled=True)
    reg = build_default_registry(cfg)
    vision = FakeVision()
    ctx = ToolContext(vision=vision, workspace_dir=workspace)
    executor = reg.get_executor(ctx)
    result = await executor(
        "describe_image",
        {
            "image_url": (
                "[图片 url=https://multimedia.nt.qq.com.cn/download?"
                "appid=1407&amp;fileid=x&amp;rkey=y workspace=incoming/a.png]"
            )
        },
    )

    assert result["ok"] is True
    assert vision.image_url.startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_describe_image_missing_workspace_marker_fails_before_provider(tmp_path):
    class FakeVision:
        def __init__(self) -> None:
            self.calls = 0

        async def describe(self, image_url: str, prompt: str = "") -> str:
            self.calls += 1
            raise AssertionError("缺失 workspace 标记不应回退透传给视觉 provider")

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    cfg = _make_config(vision_enabled=True)
    reg = build_default_registry(cfg)
    vision = FakeVision()
    ctx = ToolContext(vision=vision, workspace_dir=workspace)
    executor = reg.get_executor(ctx)
    result = await executor(
        "describe_image",
        {
            "image_url": (
                "[图片 url=https://example.com/a.jpg "
                "workspace=incoming/missing.jpg]"
            )
        },
    )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert "workspace 图片不存在" in result["error"]
    assert "优先使用 workspace=" in result["error"]
    assert "改为直接传消息中真实出现的 url= 图片 URL" in result["error"]
    assert result["data"]["image_ref"] == "incoming/missing.jpg"
    assert result["data"]["message_url"] == "example.com/..."
    assert result["data"]["workspace_path"] == "incoming/missing.jpg"
    assert vision.calls == 0


@pytest.mark.asyncio
async def test_describe_image_localizes_qq_image_url(monkeypatch):
    class FakeVision:
        def __init__(self) -> None:
            self.image_url = ""

        async def describe(self, image_url: str, prompt: str = "") -> str:
            self.image_url = image_url
            return "ok"

    async def fake_download(image_url: str, limits):
        assert image_url.startswith("https://multimedia.nt.qq.com.cn/download?")
        return _png_bytes()

    monkeypatch.setattr(
        "features.vision.image_assets._download_image",
        fake_download,
    )

    cfg = _make_config(vision_enabled=True)
    reg = build_default_registry(cfg)
    vision = FakeVision()
    ctx = ToolContext(vision=vision)
    executor = reg.get_executor(ctx)
    result = await executor(
        "describe_image",
        {"image_url": "https://multimedia.nt.qq.com.cn/download?appid=1407&fileid=x&rkey=y"},
    )

    assert result["ok"] is True
    assert vision.image_url.startswith("data:image/png;base64,")
    assert result["data"]["image_ref"] == "multimedia.nt.qq.com.cn/..."
    assert "rkey" not in json.dumps(result, ensure_ascii=False)


@pytest.mark.asyncio
async def test_describe_image_qq_download_failure_does_not_call_vision(monkeypatch):
    class FakeVision:
        async def describe(self, image_url: str, prompt: str = "") -> str:
            raise AssertionError("QQ 临时图片本地化失败后不应继续调用视觉 provider")

    async def fake_download(image_url: str, limits) -> None:
        assert image_url == (
            "https://multimedia.nt.qq.com.cn/download?appid=1407&fileid=x&rkey=y"
        )
        from features.vision.image_assets import ImageAssetError

        raise ImageAssetError("图片下载失败", code="image_source_unavailable")

    monkeypatch.setattr(
        "features.vision.image_assets._download_image",
        fake_download,
    )

    cfg = _make_config(vision_enabled=True)
    reg = build_default_registry(cfg)
    ctx = ToolContext(vision=FakeVision())
    executor = reg.get_executor(ctx)
    result = await executor(
        "describe_image",
        {
            "image_url": (
                "https://multimedia.nt.qq.com.cn/download?"
                "appid=1407&amp;fileid=x&amp;rkey=y"
            )
        },
    )

    assert result["ok"] is False
    assert result["error"] == "图片下载失败"
    assert result["data"]["image_ref"] == "multimedia.nt.qq.com.cn/..."


@pytest.mark.asyncio
async def test_describe_image_failure_result_is_compact(monkeypatch):
    async def fake_download(image_url: str, limits):
        return _png_bytes()

    monkeypatch.setattr(
        "features.vision.image_assets._download_image",
        fake_download,
    )

    class FailingVision:
        async def describe(self, image_url: str, prompt: str = "") -> dict:
            raise RuntimeError(
                "vision_volcengine: API 错误: Error code: 400 - "
                "{'error': {'code': 'InvalidParameter', 'message': "
                "'Error while downloading: https://multimedia.nt.qq.com.cn/download?"
                "appid=1407&fileid=SECRET&rkey=SECRET, status code: 400 "
                "Request id: abc', 'param': 'image_url', 'type': 'BadRequest'}}"
            )

    cfg = _make_config(vision_enabled=True)
    reg = build_default_registry(cfg)
    ctx = ToolContext(vision=FailingVision())
    executor = reg.get_executor(ctx)
    result = await executor("describe_image", {"image_url": "https://example.com/a.png"})

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["brief"] == "图片理解失败。"
    assert result["summary"] == "图片识别失败"
    assert result["error"] == "视觉服务无法读取图片链接"
    dumped = json.dumps(result, ensure_ascii=False)
    assert "SECRET" not in dumped
    assert "Request id" not in dumped
    assert "vision_volcengine" not in dumped
    assert "InvalidParameter" not in dumped


@pytest.mark.asyncio
async def test_describe_image_accepts_current_persona_image_reference(tmp_path):
    class FakeVision:
        def __init__(self) -> None:
            self.image_url = ""

        async def describe(self, image_url: str, prompt: str = "") -> str:
            self.image_url = image_url
            return "一只蓝白色的角色"

    class FakeImageStore:
        def __init__(self, path) -> None:
            self.path = path

        def resolve(self, name: str, image_id: str | None = None):
            if name != "alice":
                raise ValueError("人格不存在")
            if image_id not in {None, "a_0123456789abcdef"}:
                raise ValueError("角色形象不存在")
            return self.path

    image = tmp_path / "appearance.png"
    _write_png(image)
    cfg = _make_config(vision_enabled=True)
    reg = build_default_registry(cfg)
    vision = FakeVision()
    ctx = ToolContext(
        vision=vision,
        extras={
            "persona_image_store": FakeImageStore(image),
            "persona_name": "alice",
        },
    )
    executor = reg.get_executor(ctx)
    result = await executor(
        "describe_image",
        {"image_url": "persona-image:alice:a_0123456789abcdef", "question": "她长什么样"},
    )

    assert result["ok"] is True
    assert vision.image_url.startswith("data:image/png;base64,")
    assert result["description"] == "一只蓝白色的角色"


@pytest.mark.asyncio
async def test_describe_image_rejects_other_persona_image_reference(tmp_path):
    class FakeVision:
        async def describe(self, image_url: str, prompt: str = "") -> str:
            raise AssertionError("跨人格形象不应调用视觉 provider")

    cfg = _make_config(vision_enabled=True)
    reg = build_default_registry(cfg)
    ctx = ToolContext(
        vision=FakeVision(),
        extras={"persona_image_store": object(), "persona_name": "alice"},
    )
    executor = reg.get_executor(ctx)
    result = await executor(
        "describe_image",
        {"image_url": "persona-image:bob"},
    )

    assert result["ok"] is False
    assert "当前人格" in result["error"]


@pytest.mark.asyncio
async def test_describe_image_accepts_data_url_and_returns_compact_ref():
    class FakeVision:
        def __init__(self) -> None:
            self.image_url = ""

        async def describe(self, image_url: str, prompt: str = "") -> str:
            self.image_url = image_url
            return "ok"

    cfg = _make_config(vision_enabled=True)
    reg = build_default_registry(cfg)
    vision = FakeVision()
    ctx = ToolContext(vision=vision)
    executor = reg.get_executor(ctx)
    result = await executor("describe_image", {"image_url": _data_url()})

    assert result["ok"] is True
    assert vision.image_url.startswith("data:image/png;base64,")
    assert result["data"]["image_ref"].startswith("data-image:")
    dumped = json.dumps(result, ensure_ascii=False)
    assert "data:image" not in dumped
    assert len(dumped) < 5000


@pytest.mark.asyncio
async def test_describe_image_bad_data_url_does_not_call_vision():
    class FakeVision:
        async def describe(self, image_url: str, prompt: str = "") -> str:
            raise AssertionError("坏 data URL 不应调用视觉 provider")

    cfg = _make_config(vision_enabled=True)
    reg = build_default_registry(cfg)
    ctx = ToolContext(vision=FakeVision())
    executor = reg.get_executor(ctx)
    result = await executor(
        "describe_image",
        {"image_url": "data:image/png;base64,not-base64!"},
    )

    assert result["ok"] is False
    assert "编码无效" in result["error"]
    assert result["data"]["image_ref"].startswith("data-image:")


@pytest.mark.asyncio
async def test_vision_service_propagates_provider_error():
    class FailingProvider:
        name = "vision"

        async def chat_completion(self, *args, **kwargs):
            raise ProviderError("raw provider failure")

    service = VisionService(FailingProvider(), model="vision-model")

    with pytest.raises(ProviderError):
        await service.describe("data:image/png;base64,ZmFrZQ==")


@pytest.mark.asyncio
async def test_describe_image_long_description_saved_once(tmp_path):
    class FakeVision:
        async def describe(self, image_url: str, prompt: str = "") -> dict:
            return {
                "summary": "胡桃和魈表情包",
                "description": "完整描述 " * 500,
            }

    workspace = tmp_path / "workspace"
    _write_png(workspace / "incoming" / "a.png")

    cfg = _make_config(vision_enabled=True)
    reg = build_default_registry(cfg)
    ctx = ToolContext(
        vision=FakeVision(),
        workspace_dir=workspace,
        tool_result_budgets={
            "describe_image": {
                "inline_budget_tokens": 256,
                "artifact_threshold_tokens": 256,
                "hard_cap_tokens": 512,
            }
        },
    )
    executor = reg.get_executor(ctx)
    result = await executor("describe_image", {"image_url": "incoming/a.png"})

    assert result["ok"] is True
    assert result["status"] == "artifact"
    assert result["summary"] == "胡桃和魈表情包"
    assert "description" not in result
    assert result["full_saved"] == "incoming/a.desc.md"
    assert result["artifact"]["path"] == "incoming/a.desc.md"
    assert (workspace / "incoming" / "a.desc.md").read_text(encoding="utf-8").startswith("完整描述")
    first = dict(result)
    second = await executor("describe_image", {"image_url": "incoming/a.png"})
    assert second == first


@pytest.mark.asyncio
async def test_web_search_without_service():
    cfg = _make_config(web_search_enabled=True)
    reg = build_default_registry(cfg)
    ctx = ToolContext()
    executor = reg.get_executor(ctx)
    result = await executor("web_search", {"query": "x"})
    assert result["ok"] is False
    assert "未启用" in result["error"]


@pytest.mark.asyncio
async def test_web_search_condenses_long_results():
    class FakeSearch:
        async def search(self, query: str) -> str:
            return "\n\n".join(
                f"{i}. 标题 {i}\n" + ("摘要内容 " * 80) + f"\nhttps://example.com/{i}"
                for i in range(1, 8)
            )

    cfg = _make_config(web_search_enabled=True)
    reg = build_default_registry(cfg)
    ctx = ToolContext(
        web_search=FakeSearch(),
        tool_result_budgets={},
        tool_result_soft_limit_tokens=80,
        tool_result_hard_cap_tokens=500,
    )
    executor = reg.get_executor(ctx)
    result = await executor("web_search", {"query": "测试"})

    assert result["ok"] is True
    assert "preview" not in result
    assert result["_condensed"]["reason"] == "搜索结果过长已保留高位结果摘要"
    assert "1. 标题 1" in result["result"]
    assert "https://example.com/1" in result["result"]
    assert "7. 标题 7" not in result["result"]


@pytest.mark.asyncio
async def test_web_search_failure_string_is_not_ok():
    class FailingSearch:
        async def search(self, query: str) -> str:
            return "（免费搜索失败：network down）"

    cfg = _make_config(web_search_enabled=True)
    reg = build_default_registry(cfg)
    executor = reg.get_executor(ToolContext(web_search=FailingSearch()))
    result = await executor("web_search", {"query": "测试"})

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert "network down" in result["error"]


@pytest.mark.asyncio
async def test_weather_failure_string_is_not_ok():
    class FailingWeather:
        async def query(self, city: str, days: int = 1) -> str:
            return "地理编码失败：ConnectError: network down"

    cfg = _make_config(weather_enabled=True)
    reg = build_default_registry(cfg)
    executor = reg.get_executor(ToolContext(weather=FailingWeather()))
    result = await executor("get_weather", {"city": "北京"})

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert "ConnectError" in result["error"]


@pytest.mark.asyncio
async def test_weather_partial_forecast_failure_keeps_realtime_ok():
    class PartialWeather:
        async def query(self, city: str, days: int = 1) -> str:
            return "北京 实时：晴，20°C\n（预报查询失败：timeout）"

    cfg = _make_config(weather_enabled=True)
    reg = build_default_registry(cfg)
    executor = reg.get_executor(ToolContext(weather=PartialWeather()))
    result = await executor("get_weather", {"city": "北京", "days": 3})

    assert result["ok"] is True
    assert "warning" in result
    assert "预报" in result["warning"]


@pytest.mark.asyncio
async def test_web_fetch_without_service():
    cfg = _make_config(web_search_enabled=True)
    reg = build_default_registry(cfg)
    ctx = ToolContext()
    executor = reg.get_executor(ctx)
    result = await executor("web_fetch", {"url": "https://example.com/a"})
    assert result["ok"] is False
    assert "未启用" in result["error"]


@pytest.mark.asyncio
async def test_web_fetch_returns_truncated_markdown():
    class FakeFetch:
        async def fetch(self, url: str, *, timeout_seconds=None):
            assert url == "https://example.com/a"
            return {"title": "示例", "url": url, "content": "x" * 2000}

    cfg = _make_config(web_search_enabled=True)
    reg = build_default_registry(cfg)
    ctx = ToolContext(web_fetch=FakeFetch())
    executor = reg.get_executor(ctx)
    result = await executor(
        "web_fetch", {"url": "https://example.com/a", "max_chars": 500}
    )
    assert result["ok"] is True
    assert result["title"] == "示例"
    assert len(result["content"]) == 500
    assert result["truncated"] is True


@pytest.mark.asyncio
async def test_weather_without_service():
    cfg = _make_config(weather_enabled=True)
    reg = build_default_registry(cfg)
    ctx = ToolContext()
    executor = reg.get_executor(ctx)
    result = await executor("get_weather", {"city": "北京"})
    assert result["ok"] is False
    assert "未启用" in result["error"]


def test_send_voice_message_requires_style_prompt():
    with pytest.raises(ValidationError):
        SendVoiceMessageArgs.model_validate(
            {"target_type": "private", "target_id": 1, "text": "你好"}
        )


@pytest.mark.asyncio
async def test_send_voice_message_sends_immediately(tmp_path):
    class FakeTTS:
        async def synthesize(self, text, *, prompt):
            path = tmp_path / "voice.wav"
            path.write_bytes(b"RIFF")
            return path

    adapter = FakeSendAdapter()
    ctx = ToolContext(tts=FakeTTS(), adapter=adapter)
    args = SendVoiceMessageArgs(
        target_type="private",
        target_id=123,
        text="语音测试",
        prompt="年轻女性，自然口语",
    )

    result = await send_voice_message(args, ctx)

    assert result["ok"] is True
    assert result["sent"]["msg_id"] == "100"
    assert ctx.collected == []
    assert len(adapter.voice_sent) == 1
    target, audio_path = adapter.voice_sent[0]
    assert target.scope == "private"
    assert target.target_id == "123"
    assert audio_path.name == "voice.wav"
