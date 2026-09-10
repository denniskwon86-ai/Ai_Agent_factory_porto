"""Usage: python -m scripts.audit_business_kit_initial_data --profile quick

Prints JSON only; exits 1 on data defects and 2 when inspection cannot run.
Does not regenerate samples or touch live stores.
"""
import argparse
import json
from pathlib import Path

from core.data_preparation.kit_sample_audit import audit_package


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("quick", "full"), default="quick")
    parser.add_argument("--kit-root", type=Path, default=Path(__file__).resolve().parents[1]
                        / "starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0")
    args = parser.parse_args()
    try:
        report = audit_package(args.kit_root, args.profile)
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "UNAVAILABLE", "detail": str(exc)}, ensure_ascii=True))
        return 2
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 1 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
