"""Tests for the Agent Tool Registry and tool execution dispatching."""

import numpy as np
import pytest
from apps.agent.tool_registry import ToolRegistry, ToolDefinition


def test_default_tool_registry_initialization():
    registry = ToolRegistry.get_instance()
    tools = registry.list_tools()
    tool_names = [t["name"] for t in tools]

    assert "detect_water" in tool_names
    assert "detect_vegetation" in tool_names
    assert "detect_and_count_structures" in tool_names
    assert "calculate_area" in tool_names
    assert "calculate_ndvi" in tool_names
    assert "calculate_ndwi" in tool_names


def test_tool_registry_custom_registration():
    custom_registry = ToolRegistry()

    def dummy_handler(**kwargs):
        return {"status": "ok", "value": 42}

    tool = ToolDefinition(
        name="dummy_tool",
        description="A test tool",
        input_schema={"x": "integer"},
        output_schema={"value": "integer"},
        handler=dummy_handler,
    )

    custom_registry.register(tool)
    result = custom_registry.execute("dummy_tool")
    assert result["status"] == "ok"
    assert result["value"] == 42
    assert "latency_ms" in result
    assert result["tool"] == "dummy_tool"


def test_tool_registry_missing_tool():
    custom_registry = ToolRegistry()
    result = custom_registry.execute("non_existent_tool")
    assert result["status"] == "error"
    assert "not found" in result["error"]
