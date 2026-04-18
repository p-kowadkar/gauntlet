from typing import Callable
from agents.research_agent    import ResearchAgent
from agents.adversarial_agent import AdversarialAgent
from agents.simulation_agent  import SimulationAgent
from agents.risk_agent        import RiskAgent
from agents.voice_agent       import VoiceAgent


class GauntletPipeline:
    """
    Runs all 5 agents in sequence.

    State is cumulative: each agent's output dict is merged into
    the shared context, so every downstream agent sees all upstream
    results. The on_step callback fires before each agent runs,
    letting the UI update the progress indicator.

    Each agent is wrapped in a try/except so a single agent failure
    does not abort the pipeline -- the error is recorded in context
    and downstream agents continue with whatever state is available.
    """

    def __init__(self, on_step: Callable[[str, int], None] = None):
        self.on_step = on_step or (lambda name, idx: None)
        self.agents = [
            ("Research",    ResearchAgent()),
            ("Adversarial", AdversarialAgent()),
            ("Simulation",  SimulationAgent()),
            ("Risk",        RiskAgent()),
            ("Voice",       VoiceAgent()),
        ]

    def run(self, agent_spec: str, domain: str) -> dict:
        context = {
            "agent_spec": agent_spec,
            "domain":     domain,
        }
        for idx, (name, agent) in enumerate(self.agents):
            self.on_step(name, idx)
            try:
                result = agent.run(context)
                context.update(result)
            except Exception as e:
                # Log the failure and continue -- downstream agents
                # receive whatever state was accumulated so far
                context[f"{name.lower()}_error"] = str(e)
        return context
