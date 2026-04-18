import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from core.pipeline import GauntletPipeline
import json

def main():
    pipeline = GauntletPipeline(
        on_step=lambda name, idx: print(f"[{idx+1}/5] Running {name}...")
    )
    result = pipeline.run(
        agent_spec="You are a customer support agent for a bank. Help customers with account queries.",
        domain="Finance & Banking"
    )
    print("\n--- PIPELINE RESULT ---")
    print(f"Research findings: {result.get('research_count', 0)}")
    print(f"Test cases generated: {result.get('test_case_count', 0)}")
    print(f"Simulation results: {len(result.get('simulation_results', []))}")
    print(f"Risk score: {result.get('risk_assessment', {}).get('risk_score', 'N/A')}")
    print(f"Audio path: {result.get('audio_path', 'N/A')}")
    print(f"Errors: {[k for k in result if k.endswith('_error')]}")
    print(json.dumps(result.get('risk_assessment', {}), indent=2))

if __name__ == "__main__":
    main()
