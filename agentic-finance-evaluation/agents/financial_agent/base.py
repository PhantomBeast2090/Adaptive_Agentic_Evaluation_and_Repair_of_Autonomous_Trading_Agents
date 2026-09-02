from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseTradingAgent(ABC):
    def __init__(self, agent_id: str, version: str):
        self.agent_id = agent_id
        self.version = version
        self.memory_context = []

    def reset(self) -> None:
        """
        Reset episode-local state without clearing persistent adaptation memory.
        Stateless agents can rely on this default implementation.
        """
        return None
        
    @abstractmethod
    def act(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Takes an observation from the environment and returns an action decision.
        Must be deterministic given the same observation and memory_context.
        
        Returns:
            Dict containing 'action' (BUY/SELL/HOLD), 'quantity', and 'rationale'
        """
        pass
        
    @abstractmethod
    def adapt(self, intervention: Dict[str, Any]) -> None:
        """
        Receives a structured intervention payload and updates the agent's memory_context.
        """
        pass
