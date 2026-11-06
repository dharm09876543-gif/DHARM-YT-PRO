"""Config files check karein: python scripts/validate_config.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import validate_all  # noqa: E402

errors = validate_all()
if errors:
    print("Config mein galtiyan:")
    for e in errors:
        print("  -", e)
    sys.exit(1)
print("Config theek hai.")
