"""발주·물류 5종의 비설치 후보 JSON 작성. 원본·DB 쓰기·자동 인증 기능 없음."""
import argparse
import json
from pathlib import Path

from core.data_preparation.kit_logistics_revision import plan_logistics_revision


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit-root", type=Path, default=Path(__file__).resolve().parents[1]
                        / "starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0")
    parser.add_argument("--report", type=Path, help="후보 전체를 새 JSON으로 저장. 기존 파일 덮어쓰기 금지")
    args = parser.parse_args()
    try:
        report = plan_logistics_revision(args.kit_root)
        if args.report:
            with args.report.open("x", encoding="utf-8") as stream:
                json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        summary = {k: v for k, v in report.items() if k not in {"candidate_rows", "inspection"}}
        summary["inspection"] = {k: v for k, v in report["inspection"].items() if k != "issues"}
        print(json.dumps(summary, ensure_ascii=True, indent=2))
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "UNAVAILABLE", "detail": str(exc)}, ensure_ascii=True))
        return 2
    return 1 if report["candidate_check"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
