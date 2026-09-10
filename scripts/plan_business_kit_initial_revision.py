"""조직·BOM·창고·수량 후보 명세만 출력한다. 원본·DB 수정 명령은 없다."""
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
    parser.add_argument("--repair-warehouses", action="store_true",
                        help="full 근거로 누락 창고·옛 기초재고 fallback 보정 후보만 생성 (원본/DB 불변)")
    parser.add_argument("--rebuild-stock", action="store_true",
                        help="명시적 질량 환산·유효 이동별 재고 재산출 후보와 부족 원인 생성 (미해결 품목은 보류)")
    parser.add_argument("--rebuild-production", action="store_true",
                        help="배치·생산량을 보존한 다중 원료 투입 후보 생성 (BOM 단위·EA 정책 불명확 시 보류)")
    parser.add_argument("--kit-root", type=Path, default=Path(__file__).resolve().parents[1]
                        / "starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0")
    args = parser.parse_args()
    try:
        report = plan_package_revision(args.kit_root, args.profile,
                                       resolve_exact_bom_copies=args.resolve_exact_bom_copies,
                                       repair_warehouses=args.repair_warehouses, rebuild_stock=args.rebuild_stock,
                                       rebuild_production=args.rebuild_production)
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
        summary = {key: value for key, value in report.items()
                   if key not in {"changes", "held", "remaining_issues", "source_files"}}
        # The new report retains every quantity issue; console output is only a counted summary.
        summary["quantity_flow"] = {key: value for key, value in report["quantity_flow"].items() if key != "issues"}
        if report.get("stock_revision"):
            stock = report["stock_revision"]
            summary["stock_revision"] = {key: value for key, value in stock.items()
                                         if key not in {"stock_inputs", "shortages", "production_input_contract"}}
            summary["stock_revision"]["shortage_bucket_count"] = len(stock["shortages"])
            summary["stock_revision"]["production_input_contract"] = {
                key: value for key, value in stock["production_input_contract"].items() if key != "issues"}
        print(json.dumps(summary, ensure_ascii=True, indent=2))
    else:
        print(json.dumps(report, ensure_ascii=True, indent=2))
    return 1 if report["candidate_check"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
