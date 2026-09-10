"""K1-c3 계약·공급사 비설치 보정 후보. 출력은 새 검토 JSON이며 제품에 적재하지 않는다."""
import argparse
import json
from pathlib import Path

from core.data_preparation.kit_procurement_reference_revision import plan_reference_revision

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logistics-candidate", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not args.report.resolve().is_relative_to((ROOT / "output").resolve()):
        parser.error("출력은 저장소 output/ 아래 새 파일만 허용합니다")
    try:
        report = plan_reference_revision(ROOT / "starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0", args.logistics_candidate)
        with args.report.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
        print(json.dumps({k: v for k, v in report.items() if k not in {"candidate_rows", "changes"}}, ensure_ascii=True, indent=2))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "UNAVAILABLE", "detail": str(exc)}, ensure_ascii=True))
        return 2
    return 1 if report["candidate_check"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
