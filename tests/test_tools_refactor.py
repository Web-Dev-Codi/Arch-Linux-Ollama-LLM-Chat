"""Tests for refactored tools system (v2.0)."""

from __future__ import annotations

from pathlib import Path
import tempfile
import time
from unittest.mock import AsyncMock, Mock, patch

from pydantic import Field
import pytest

from src.ollama_chat.capability_cache import (
    CapabilityPersistence,
    ModelCapabilityCache,
)
from src.ollama_chat.chat import OllamaChat
from src.ollama_chat.tooling import ToolRegistry
from src.ollama_chat.tools.base import ParamsSchema, Tool, ToolContext, ToolResult
from src.ollama_chat.tools.registry import get_registry


# Test Tools
class DummyParams(ParamsSchema):
    text: str = Field(description="Text input")
    count: int = Field(default=1, description="Count")


class DummyTool(Tool):
    id = "dummy"
    description = "Dummy tool for testing"
    params_schema = DummyParams

    async def execute(self, params: DummyParams, ctx: ToolContext) -> ToolResult:
        return ToolResult(
            title="dummy",
            output=f"Got: {params.text} x{params.count}",
            metadata={"ok": True},
        )


class TestToolSchemaFormat:
    """Test that tools generate proper Ollama format schemas."""

    def test_to_ollama_schema_format(self) -> None:
        """Verify to_ollama_schema() returns correct structure."""
        tool = DummyTool()
        schema = tool.to_ollama_schema()

        # Check outer structure
        assert schema["type"] == "function"
        assert "function" in schema

        # Check function structure
        func = schema["function"]
        assert func["name"] == "dummy"
        assert func["description"] == "Dummy tool for testing"
        assert "parameters" in func

        # Check parameters structure
        params = func["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
        assert "text" in params["properties"]
        assert "count" in params["properties"]
        assert "required" in params
        assert "text" in params["required"]  # No default, so required

    def test_schema_caching(self) -> None:
        """Verify schema is cached with @cached_property."""
        tool = DummyTool()
        schema1 = tool.to_ollama_schema()
        schema2 = tool.to_ollama_schema()

        # Should be same object (cached)
        assert schema1 is schema2

    def test_schema_clean_pydantic_fields(self) -> None:
        """Verify Pydantic-specific fields are removed."""
        tool = DummyTool()
        schema = tool.to_ollama_schema()
        params = schema["function"]["parameters"]

        # These should not be present
        assert "$defs" not in params
        assert "$schema" not in params
        assert "definitions" not in params

        # These should be present
        assert "additionalProperties" in params
        assert params["additionalProperties"] is True

    def test_registry_build_ollama_tools(self) -> None:
        """Verify registry returns proper Ollama format."""
        registry = get_registry()
        tools = registry.build_ollama_tools()

        # All tools should have proper format
        for tool in tools:
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]
            assert "parameters" in tool["function"]


class TestCapabilityCache:
    """Test capability caching functionality."""

    def test_cache_staleness(self) -> None:
        """Verify cache staleness detection."""
        cache = ModelCapabilityCache(
            model_name="test",
            supports_tools=True,
            supports_vision=False,
            supports_thinking=True,
            raw_capabilities=["tools", "thinking"],
            timestamp=time.time() - 7200,  # 2 hours ago
        )

        # Should be stale with 1 hour max_age
        assert cache.is_stale(max_age_seconds=3600)

        # Should be fresh with 3 hour max_age
        assert not cache.is_stale(max_age_seconds=10800)

    def test_persistence_save_load(self) -> None:
        """Verify capability cache persists across restarts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "test_capabilities.json"

            # Create cache and store entry
            persistence = CapabilityPersistence(cache_file)
            cache_entry = ModelCapabilityCache(
                model_name="qwen3",
                supports_tools=True,
                supports_vision=False,
                supports_thinking=True,
                raw_capabilities=["tools", "thinking"],
                timestamp=time.time(),
            )
            persistence.set(cache_entry)

            # Verify file exists
            assert cache_file.exists()

            # Load in new instance
            persistence2 = CapabilityPersistence(cache_file)
            loaded = persistence2.get("qwen3")

            assert loaded is not None
            assert loaded.model_name == "qwen3"
            assert loaded.supports_tools is True
            assert loaded.supports_vision is False
            assert loaded.supports_thinking is True

    def test_persistence_invalidate(self) -> None:
        """Verify cache invalidation works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "test_capabilities.json"
            persistence = CapabilityPersistence(cache_file)

            cache_entry = ModelCapabilityCache(
                model_name="test_model",
                supports_tools=True,
                supports_vision=True,
                supports_thinking=True,
                raw_capabilities=["tools", "vision", "thinking"],
                timestamp=time.time(),
            )
            persistence.set(cache_entry)

            # Verify it's there
            assert persistence.get("test_model") is not None

            # Invalidate
            persistence.invalidate("test_model")

            # Should be gone
            assert persistence.get("test_model") is None


class TestCapabilityFiltering:
    """Test that API requests filter based on model capabilities."""

    @pytest.mark.asyncio
    async def test_tools_filtered_when_not_supported(self) -> None:
        """Verify tools are not sent if model doesn't support them."""
        mock_client = Mock()
        mock_client.show = AsyncMock(
            return_value={"capabilities": ["vision"]}  # No tools
        )
        mock_client.chat = AsyncMock(
            return_value=AsyncMock(__aiter__=lambda self: iter([]))
        )

        chat = OllamaChat(
            host="http://localhost:11434",
            model="llama2",
            system_prompt="Test",
            client=mock_client,
        )

        # Get capability cache
        caps = await chat._ensure_capability_cache()

        # Should detect no tool support
        assert not caps.supports_tools
        assert caps.supports_vision

    @pytest.mark.asyncio
    async def test_thinking_filtered_when_not_supported(self) -> None:
        """Verify thinking is not sent if model doesn't support it."""
        mock_client = Mock()
        mock_client.show = AsyncMock(
            return_value={"capabilities": ["tools"]}  # No thinking
        )
        mock_client.chat = AsyncMock(
            return_value=AsyncMock(__aiter__=lambda self: iter([]))
        )

        chat = OllamaChat(
            host="http://localhost:11434",
            model="llama2",
            system_prompt="Test",
            client=mock_client,
        )

        caps = await chat._ensure_capability_cache()

        assert caps.supports_tools
        assert not caps.supports_thinking

    @pytest.mark.asyncio
    async def test_cache_hit_uses_cached_data(self) -> None:
        """Verify capability cache avoids redundant /api/show calls."""
        mock_client = Mock()
        mock_client.show = AsyncMock(
            return_value={"capabilities": ["tools", "thinking", "vision"]}
        )

        chat = OllamaChat(
            host="http://localhost:11434",
            model="qwen3",
            system_prompt="Test",
            client=mock_client,
        )

        # First call should hit /api/show
        caps1 = await chat._ensure_capability_cache()
        assert mock_client.show.call_count == 1

        # Second call should use cache
        caps2 = await chat._ensure_capability_cache()
        assert mock_client.show.call_count == 1  # No additional call

        # Should be same object
        assert caps1 is caps2


class TestToolExecutionOptimization:
    """Test that fast tools avoid thread pool overhead."""

    @pytest.mark.asyncio
    async def test_fast_tools_run_directly(self) -> None:
        """Verify fast tools don't use asyncio.to_thread."""
        mock_registry = Mock()
        mock_registry.execute = Mock(return_value="result")
        mock_registry.is_empty = False
        mock_registry.build_tools_list = Mock(return_value=[])

        mock_client = Mock()
        mock_client.show = AsyncMock(return_value={"capabilities": ["tools"]})
        mock_client.chat = AsyncMock(
            return_value=AsyncMock(
                __aiter__=lambda self: iter(
                    [
                        # Model calls "read" tool
                        Mock(
                            message=Mock(
                                thinking=None,
                                content="",
                                tool_calls=[
                                    Mock(
                                        function=Mock(
                                            name="read",
                                            arguments={"path": "test.txt"},
                                            index=None,
                                        )
                                    )
                                ],
                            )
                        )
                    ]
                )
            )
        )

        chat = OllamaChat(
            host="http://localhost:11434",
            model="qwen3",
            system_prompt="Test",
            client=mock_client,
        )

        # Patch asyncio.to_thread to detect if it's called
        with patch("asyncio.to_thread") as mock_to_thread:
            chunks = []
            async for chunk in chat.send_message("test", tool_registry=mock_registry):
                chunks.append(chunk)

            # read is in FAST_SYNC_TOOLS, should NOT use to_thread
            assert mock_to_thread.call_count == 0
            # Should call execute directly
            assert mock_registry.execute.call_count == 1


class TestToolRegistry:
    """Test ToolRegistry schema building."""

    def test_build_tools_list_returns_proper_format(self) -> None:
        """Verify build_tools_list returns Ollama-formatted schemas."""
        registry = ToolRegistry()

        # Register a callable
        def test_tool(arg: str) -> str:
            """Test tool."""
            return f"got: {arg}"

        registry.register(test_tool)

        tools = registry.build_tools_list()

        assert len(tools) == 1
        tool_schema = tools[0]

        # Verify format
        assert tool_schema["type"] == "function"
        assert "function" in tool_schema
        assert tool_schema["function"]["name"] == "test_tool"
        assert "parameters" in tool_schema["function"]


class TestBackwardCompatibility:
    """Test that legacy code still works."""

    def test_legacy_schema_method_still_works(self) -> None:
        """Verify schema() method still works for backward compat."""
        tool = DummyTool()
        legacy_schema = tool.schema()

        # Should have old format (without "type": "function" wrapper)
        assert "name" in legacy_schema
        assert "description" in legacy_schema
        assert "parameters" in legacy_schema

    def test_tool_spec_still_works(self) -> None:
        """Verify ToolSpec still works after migration to tooling.py."""
        from src.ollama_chat.tooling import ToolSpec

        spec = ToolSpec(
            name="test",
            description="Test tool",
            parameters_schema={
                "type": "object",
                "properties": {"arg": {"type": "string"}},
                "required": ["arg"],
            },
            handler=lambda args: f"got: {args['arg']}",
        )

        schema = spec.as_ollama_tool()

        # Should have correct format
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "test"


class TestModelSwitch:
    """Test that caches invalidate on model switch."""

    @pytest.mark.asyncio
    async def test_set_model_invalidates_cache(self) -> None:
        """Verify set_model clears capability cache."""
        mock_client = Mock()
        mock_client.show = AsyncMock(
            return_value={"capabilities": ["tools", "thinking"]}
        )

        chat = OllamaChat(
            host="http://localhost:11434",
            model="qwen3",
            system_prompt="Test",
            client=mock_client,
        )

        # Cache capabilities for qwen3
        await chat._ensure_capability_cache()
        assert chat._current_capability_cache is not None
        assert chat._current_capability_cache.model_name == "qwen3"

        # Switch model
        chat.set_model("llama2")

        # Cache should be invalidated
        assert chat._current_capability_cache is None
        assert chat._formatted_tools_cache is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
