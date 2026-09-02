import pytest
from agents.financial_agent.synthetic import FlawlessControlAgent, LossChasingAgent, VolatilityBlindAgent

def test_flawless_agent():
    agent = FlawlessControlAgent("flawless", "v1")
    
    # Low VIX, lots of cash -> BUY
    obs = {"vix": 10.0, "portfolio": {"cash": 1000.0, "holdings": 0}, "market_price": 10.0}
    action = agent.act(obs)
    assert action["action"] == "BUY"
    assert action["quantity"] == 10.0
    
    # High VIX, has holdings -> SELL
    obs = {"vix": 30.0, "portfolio": {"cash": 0.0, "holdings": 10}, "market_price": 10.0}
    action = agent.act(obs)
    assert action["action"] == "SELL"
    assert action["quantity"] == 10.0

def test_loss_chasing_agent():
    agent = LossChasingAgent("chaser", "v1")
    
    # Normal buy
    obs = {"portfolio": {"cash": 1000.0, "total_value": 1000.0, "holdings": 0}, "market_price": 10.0}
    action = agent.act(obs)
    assert action["action"] == "BUY"
    assert action["quantity"] == 5.0
    
    # Loss occurs (value drops to 900)
    obs = {"portfolio": {"cash": 950.0, "total_value": 900.0, "holdings": 5}, "market_price": 8.0}
    action = agent.act(obs)
    assert action["action"] == "BUY"
    # Consecutive loss = 1, qty = 10 * 2^1 = 20
    assert action["quantity"] == 20.0

    agent.reset()
    action = agent.act({"portfolio": {"cash": 1000.0, "total_value": 900.0, "holdings": 0}, "market_price": 10.0})
    assert action["quantity"] == 5.0

def test_volatility_blind_agent():
    agent = VolatilityBlindAgent("blind", "v1")
    
    # High VIX, but still buys
    obs = {"vix": 80.0, "portfolio": {"cash": 1000.0, "holdings": 0}, "market_price": 10.0}
    action = agent.act(obs)
    assert action["action"] == "BUY"
    assert action["quantity"] == 10.0


def test_agents_handle_terminal_observation():
    agents = [
        FlawlessControlAgent("flawless", "v1"),
        LossChasingAgent("chaser", "v1"),
        VolatilityBlindAgent("blind", "v1"),
    ]

    for agent in agents:
        action = agent.act(None)
        assert action["action"] == "HOLD"
        assert action["quantity"] == 0.0
