import pytest
from agents.financial_agent.llm_agent import LLMTradingAgent

def test_llm_agent_interface():
    agent = LLMTradingAgent("test_agent", "v1.0", {})
    
    # Test act
    obs = {
        "vix": 35.0,
        "market_price": 100.0,
        "portfolio": {"cash": 200.0, "holdings": 0.0}
    }
    
    action = agent.act(obs)
    assert action["action"] == "BUY"
    assert action["quantity"] == 1.0
    
    # Test adapt
    intervention = {
        "behavioral_rule": "Do not buy if cash is below 500.",
        "trigger_condition": "cash < 500",
        "desired_behavior": "HOLD"
    }
    agent.adapt(intervention)
    
    assert agent.version == "v1.0-adapted"
    assert len(agent.memory_context) == 2
    assert "Do not buy if cash is below 500" in agent.memory_context[1]["content"]
