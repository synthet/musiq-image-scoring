import sys
import os
import json

# Add project root to path
sys.path.append(os.getcwd())

from modules import db
from modules.phases_policy import explain_phase_run_decision
from modules.phases import PhaseCode, PhaseStatus

def test_done_but_missing_data():
    image_id = 72128
    print(f"Testing policy for image_id={image_id} (Scoring)")
    
    # Manually mock the DB state for this test if needed, or just rely on current state.
    # Currently it is 'skipped'. Let's see what happens if we pretend it's 'done'.
    
    # We can't easily mock the DB without a transaction, but we can check the logic.
    # Let's just run it as is first.
    decision = explain_phase_run_decision(image_id, PhaseCode.SCORING)
    print("Current state (skipped):")
    print(json.dumps(decision, indent=2))
    
    # Now let's see what happens if we pass force_run=True (as pipeline might do)
    decision_force = explain_phase_run_decision(image_id, PhaseCode.SCORING, force_run=True)
    print("\nForce run requested:")
    print(json.dumps(decision_force, indent=2))

if __name__ == "__main__":
    test_done_but_missing_data()
