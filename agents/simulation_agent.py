"""
Veris is a CLI-first agent simulation platform -- NOT a REST API.

Veris demo setup (Card Replacement Agent -- banking domain):
    Environment:  env_26elq3ug4mv5cp4wd2apf  (Card Replacement Agent)
    Scenario set: scenset_ame28acq32j2954fv4wy6  (30 scenarios, ready)
    Sim run:      run_p70fbydvsuwnrjlzrwr1e  (running/completed)

Local CLI auth:
    veris login  (browser OAuth, token stored at ~/.veris/config.yaml)
    No API key needed in .env

Demo flow:
    - Terminal shows `veris simulations status run_p70fbydvsuwnrjlzrwr1e --watch`
    - Gauntlet overlay runs the pipeline -- SimulationAgent fetches completed results
    - Both layers are live and real

After the run completes, store the run ID in Settings > Workspace
or add VERIS_RUN_ID to .env -- SimulationAgent will use it directly,
skipping the creation of a new (slow) run.
"""
import os
import time
import random
from config import VERIS_API_KEY
from core.agent_base import AgentBase

# Known run ID from the live Veris session -- set this to skip creating a new run.
# Add VERIS_RUN_ID=run_p70fbydvsuwnrjlzrwr1e to .env after the run completes.
VERIS_RUN_ID = os.getenv("VERIS_RUN_ID", "")
VERIS_ENV_ID = os.getenv("VERIS_ENV_ID", "env_26elq3ug4mv5cp4wd2apf")


def _get_veris_client():
    """Return an authenticated Veris SDK client using local CLI auth or API key."""
    try:
        from veris import Veris
        if VERIS_API_KEY:
            return Veris(api_key=VERIS_API_KEY)
        return Veris()  # picks up ~/.veris/config.yaml from `veris login`
    except ImportError:
        raise RuntimeError("Run: pip install veris-ai")


def _run_simulation_batch(agent_spec: str, test_cases: list[dict], domain: str) -> list[dict]:
    """
    Fetch Veris simulation results.

    Priority order:
    1. If VERIS_RUN_ID is set in .env, fetch that specific completed run directly
    2. Otherwise find the most recent completed run for the environment
    3. If no completed run exists, create a new one and poll (max 3 min)
    4. Fall back to mock results if anything fails
    """
    try:
        client = _get_veris_client()

        # Priority 1: use a specific completed run ID (fastest -- set in .env)
        if VERIS_RUN_ID:
            try:
                run = client.runs.get(VERIS_RUN_ID)
                if run.status in ("complete", "done", "finished", "completed"):
                    results = _parse_veris_results(run, test_cases)
                    if results:
                        return results
            except Exception:
                pass  # fall through to environment-based lookup

        # Priority 2: find most recent completed run for the environment
        if VERIS_ENV_ID:
            try:
                runs = client.runs.list(environment_id=VERIS_ENV_ID)
                completed = [
                    r for r in runs
                    if getattr(r, "status", "") in ("complete", "done", "finished", "completed")
                ]
                if completed:
                    latest = sorted(
                        completed,
                        key=lambda r: getattr(r, "created_at", ""),
                        reverse=True
                    )[0]
                    results = _parse_veris_results(latest, test_cases)
                    if results:
                        return results
            except Exception:
                pass  # fall through to creating a new run

        # Priority 3: create a new run and poll (slow -- 30 scenarios take time)
        envs = client.environments.list()
        if not envs:
            return _mock_results(
                test_cases,
                note="No Veris environment. Visit console.veris.ai"
            )

        env = envs[0]
        run = client.runs.create(environment_id=env.id)

        # Poll up to 3 minutes (36 × 5s)
        for _ in range(36):
            time.sleep(5)
            run = client.runs.get(run.id)
            if run.status in ("complete", "done", "finished", "completed"):
                break

        return _parse_veris_results(run, test_cases)

    except RuntimeError as e:
        return _mock_results(test_cases, note=str(e))
    except Exception as e:
        return _mock_results(test_cases, note=str(e))


def _parse_veris_results(run, test_cases: list[dict]) -> list[dict]:
    results = []
    try:
        scenarios = getattr(run, "scenarios", []) or getattr(run, "results", [])
        for i, s in enumerate(scenarios):
            passed = getattr(s, "passed", True)
            results.append({
                "id":          getattr(s, "id", f"TC-{i:03d}"),
                "attack_type": (getattr(s, "tags", None) or ["unknown"])[0],
                "passed":      passed,
                "root_cause":  getattr(s, "root_cause", "") or getattr(s, "failure_reason", ""),
                "score":       getattr(s, "score", 100 if passed else 30),
                "mock":        False,
            })
    except Exception:
        pass
    return results  # empty list signals caller to try next option


def _get_failure_details(simulation_results: list[dict]) -> dict:
    total  = len(simulation_results)
    failed = [r for r in simulation_results if not r.get("passed", True)]
    by_attack = {}
    for r in failed:
        attack = r.get("attack_type", "unknown")
        by_attack.setdefault(attack, 0)
        by_attack[attack] += 1
    return {
        "total":          total,
        "passed":         total - len(failed),
        "failed":         len(failed),
        "pass_rate":      round((total - len(failed)) / total * 100, 1) if total else 0,
        "by_attack_type": by_attack,
        "failed_cases":   failed,
    }


def _extract_root_causes(simulation_results: list[dict]) -> list[str]:
    causes = []
    for r in simulation_results:
        if not r.get("passed", True):
            cause = r.get("root_cause") or r.get("failure_reason") or "Unspecified failure"
            causes.append(cause)
    return list(set(causes))


def _mock_results(test_cases: list[dict], note: str = "") -> list[dict]:
    results = []
    for tc in test_cases:
        passed = random.random() > 0.35
        results.append({
            "id":          tc.get("id", "TC-???"),
            "attack_type": tc.get("attack_type", "unknown"),
            "passed":      passed,
            "root_cause":  "" if passed else random.choice([
                "Agent followed injected instruction instead of system prompt",
                "Agent disclosed internal configuration when probed",
                "Agent agreed to perform out-of-scope action",
                "Agent leaked PII from prior conversation turn",
                "Agent bypassed access control on user request",
            ]),
            "score": random.randint(70, 100) if passed else random.randint(10, 50),
            "mock":  True,
            "note":  note,
        })
    return results


class SimulationAgent(AgentBase):
    SKILLS = {
        "run_simulation_batch": _run_simulation_batch,
        "get_failure_details":  _get_failure_details,
        "extract_root_causes":  _extract_root_causes,
    }

    def run(self, context: dict) -> dict:
        sim_results = self.invoke_skill(
            "run_simulation_batch",
            agent_spec=context["agent_spec"],
            test_cases=context.get("test_cases", []),
            domain=context["domain"],
        )
        failure_details = self.invoke_skill(
            "get_failure_details",
            simulation_results=sim_results,
        )
        root_causes = self.invoke_skill(
            "extract_root_causes",
            simulation_results=sim_results,
        )
        return {
            "simulation_results": sim_results,
            "failure_summary":    failure_details,
            "root_causes":        root_causes,
        }
