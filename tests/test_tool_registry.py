import pytest
from backend.tools.registry import ToolRegistry, RiskLevel

def test_registry_registration_and_retrieval():
    registry = ToolRegistry()
    registry.register("test_tool", "A test tool", "testing", RiskLevel.SAFE)
    
    tool = registry.get_tool("test_tool")
    assert tool.name == "test_tool"
    assert tool.risk_level == RiskLevel.SAFE

def test_duplicate_registration_fails():
    registry = ToolRegistry()
    registry.register("test_tool", "A test tool", "testing", RiskLevel.SAFE)
    
    with pytest.raises(ValueError, match="already registered"):
        registry.register("test_tool", "Another tool", "testing", RiskLevel.SAFE)

def test_get_nonexistent_tool_fails():
    registry = ToolRegistry()
    with pytest.raises(KeyError, match="not found"):
        registry.get_tool("nonexistent")

def test_list_tools():
    registry = ToolRegistry()
    registry.register("tool1", "Tool 1", "cat1", RiskLevel.SAFE)
    registry.register("tool2", "Tool 2", "cat2", RiskLevel.DANGEROUS)
    
    tools = registry.list_tools()
    assert len(tools) == 2
    assert any(t.name == "tool1" for t in tools)
    assert any(t.name == "tool2" for t in tools)
