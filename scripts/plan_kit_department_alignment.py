"""기존 부서 기반 전환 계획만 저장한다. DB 변경·설치 옵션을 제공하지 않는다."""
import argparse
import json
from pathlib import Path
import sqlite3

from core.data_preparation.kit_department_alignment import plan_alignment, read_organization
from core.data_preparation.kit_logistics_revision import plan_logistics_revision

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logistics-candidate", type=Path, required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not args.report.resolve().is_relative_to((ROOT / "output").resolve()):
        parser.error("출력은 output/ 아래 새 파일만 허용합니다")
    try:
        logistics = json.loads(args.logistics_candidate.read_text(encoding="utf-8-sig"))
        # 자기 지문만 맞춘 임의 후보를 원천으로 믿지 않는다.
        expected = plan_logistics_revision(ROOT / "starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0")
        if logistics != expected:
            raise ValueError("부모 후보가 현재 원천 키트와 다릅니다")
        organization = read_organization(ROOT / "data/master/master.db", ROOT / "data/enterprise_context.db")
        instance = json.loads((ROOT / "data/instance.json").read_text(encoding="utf-8-sig"))
        report = plan_alignment(organization, logistics, instance, as_of=args.as_of)
        with args.report.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
        print(json.dumps({k: report[k] for k in ("status", "affected_rows", "new_department_count",
                                                "target_tenant_id", "plan_fingerprint")}, ensure_ascii=True))
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        print(json.dumps({"status": "UNAVAILABLE", "detail": str(exc)}, ensure_ascii=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
