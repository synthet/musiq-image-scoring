
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules import db, phases_policy
from modules.phases import PhaseCode

def verify_data_driven_checks():
    print("--- Verifying Data-Driven Reliability Checks ---")
    
    # 1. Test image with missing metadata
    # (Existing image, but we'll mock its data if needed or find one)
    test_image_id = 67336 # Our target from before
    
    print(f"Testing image {test_image_id} for metadata completeness...")
    is_meta = db.is_image_metadata_complete(test_image_id)
    print(f"is_image_metadata_complete: {is_meta}")
    
    print(f"Testing image {test_image_id} for keywords completeness...")
    is_kw = db.is_image_keywords_complete(test_image_id)
    print(f"is_image_keywords_complete: {is_kw}")
    
    # 2. Verify Policy Decision
    print("\nVerifying policy decision for METADATA phase...")
    decision = phases_policy.explain_phase_run_decision(test_image_id, PhaseCode.METADATA)
    print(f"Decision for METADATA: should_run={decision['should_run']}, reason='{decision['reason']}'")
    
    print("\nVerifying policy decision for KEYWORDS phase...")
    decision = phases_policy.explain_phase_run_decision(test_image_id, PhaseCode.KEYWORDS)
    print(f"Decision for KEYWORDS: should_run={decision['should_run']}, reason='{decision['reason']}'")

    print("\n--- Verification Complete ---")

if __name__ == "__main__":
    verify_data_driven_checks()
