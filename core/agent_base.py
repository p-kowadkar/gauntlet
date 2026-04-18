from abc import ABC, abstractmethod
from typing import Any


class AgentBase(ABC):
    """
    Every Gauntlet agent inherits from this.

    SKILLS is the bounded registry. The LLM picks which skill to call
    from this dict -- nothing outside it executes. This is enforced at
    runtime by invoke_skill(), which raises ValueError on unknown names.
    """

    SKILLS: dict[str, callable] = {}

    @abstractmethod
    def run(self, context: dict) -> dict:
        pass

    def invoke_skill(self, name: str, **kwargs) -> Any:
        if name not in self.SKILLS:
            raise ValueError(
                f"Skill '{name}' not in registry for "
                f"{self.__class__.__name__}. "
                f"Available: {list(self.SKILLS.keys())}"
            )
        return self.SKILLS[name](**kwargs)

    def list_skills(self) -> list[str]:
        return list(self.SKILLS.keys())
