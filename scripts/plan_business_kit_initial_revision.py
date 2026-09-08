"""조직·BOM 후보 명세만 출력한다. 원본·DB 수정 명령은 없다."""
import argparse
import json
from pathlib import Path

from core.data_preparation.kit_sample_revision import plan_package_revision


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("quick", "full"), default="quick")
    parser.add_argument("--resolve-exact-bom-copies", action="store_true",
                        help="full의 유일한 BOM과 내용이 완전히 같은 복제만 검토 후보에서 제외")
    parser.add_argument("--report", type=Path, help="검토 명세 JSON을 새 파일로 저장 (기존 파일 덮어쓰기 금지)")
    parser.add_argument("--kit-root", type=Path, default=Path(__file__).resolve().parents[1]
                        / "starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0")
    args = parser.parse_args()
    try:
        report = plan_package_revision(args.kit_root, args.profile,
                                       resolve_exact_bom_copies=args.resolve_exact_bom_copies)
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "UNAVAILABLE", "detail": str(exc)}, ensure_ascii=True))
        return 2
    if args.report:
        try:
            with args.report.open("x", encoding="utf-8") as stream:
                json.dump(report, stream, ensure_ascii=False, indent=2)
        except OSError as exc:
            print(json.dumps({"status": "UNAVAILABLE", "detail": str(exc)}, ensure_ascii=True))
            return 2
        print(json.dumps({key: value for key, value in report.items()
                          if key not in {"changes", "held", "remaining_issues", "source_files"}},
                         ensure_ascii=True, indent=2))
    else:
        print(json.dumps(report, ensure_ascii=True, indent=2))
    return 1 if report["candidate_check"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
