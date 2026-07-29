"""[M4] 실적·계획 데이터 등록 (§17.2 기능 2 "최근 3년 실적 연결 또는 파일 등록"). LLM 0콜.

## 이 모듈이 가장 조심하는 것

파일 등록은 **조용히 틀리기 가장 쉬운 경로**다. 엑셀 한 장에 오타가 하나 있으면 그 숫자가
그대로 경영 보고서에 들어가고, 아무 오류도 나지 않는다. 그래서 여기서는 **먼저 검증하고
나중에 저장한다** — 부분 저장을 하지 않는다.

> **한 행이라도 문제가 있으면 전부 거부한다(all-or-nothing).**

부분 저장을 허용하면 "127행 중 119행 저장됨" 같은 상태가 남는데, 그때 그 데이터는
**맞는 것도 틀린 것도 아닌 상태**가 된다. 나중에 누가 봐도 무엇이 들어갔는지 알 수 없다.

## 검증 항목

1. **필수 열** — org_id, account_code, period, value_kind, amount
2. **미등록 계정** — 계정을 먼저 등록해야 한다. 자동 생성하면 오타가 새 계정이 된다.
3. **`value_kind`** — 기본값을 채우지 않는다(§11.3). 빈 칸은 오류다.
4. **숫자 형식** — "1,000" 같은 천단위 구분은 허용하되, 해석 불가는 오류로 남긴다.
5. **중복 행** — 같은 (조직·계정·기간·종류)가 두 번 오면 어느 쪽이 맞는지 알 수 없다.

## 미리보기(dry-run)가 기본이다

`commit=False` 가 기본값이다. 무엇이 들어갈지 먼저 보여주고, 사용자가 확인한 뒤에 저장한다.
경영 데이터에서 "일단 넣고 고치자"는 나중에 무엇이 원본인지 알 수 없게 만든다.
"""
import csv
import io
from typing import Any, Dict, List, Optional, Tuple

from core.planning_model import VALUE_KINDS, PlanningError, planning_store

#: 필수 열. 순서는 자유지만 이름은 고정한다 — 열 이름을 추측하면 조용히 틀린 열을 읽는다.
REQUIRED_COLUMNS = ("org_id", "account_code", "period", "value_kind", "amount")
OPTIONAL_COLUMNS = ("currency", "source_ref", "owner_organization_id",
                    "scope_type", "classification")


def _parse_amount(raw: str) -> Tuple[Optional[float], str]:
    """숫자 해석. 천단위 구분·공백은 허용하고, 해석 불가는 **오류로 남긴다**(0 으로 바꾸지 않는다)."""
    s = str(raw or "").strip().replace(",", "").replace(" ", "")
    if not s:
        return None, "값이 비어 있습니다"
    # 회계 표기 (1,000) = -1000
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    try:
        v = float(s)
        return (-v if neg else v), ""
    except ValueError:
        return None, f"숫자로 해석할 수 없습니다: {raw!r}"


def validate_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """저장 전 전수 검증. **부분 통과를 만들지 않는다** — 문제가 있으면 전부 거부한다."""
    if not rows:
        return {"ok": False, "errors": [{"row": 0, "why": "행이 하나도 없습니다."}],
                "valid_rows": [], "summary": {}}

    known_accounts = {a["account_code"] for a in planning_store.list_accounts()}
    errors: List[Dict[str, Any]] = []
    valid: List[Dict[str, Any]] = []
    seen: Dict[Tuple[str, str, str, str], int] = {}

    for i, raw in enumerate(rows, start=1):
        row = {(k or "").strip(): (v if v is None else str(v).strip())
               for k, v in raw.items()}
        missing = [c for c in REQUIRED_COLUMNS if not row.get(c)]
        if missing:
            errors.append({"row": i, "why": f"필수 열 누락: {', '.join(missing)}"})
            continue

        vk = row["value_kind"].upper()
        if vk not in VALUE_KINDS:
            errors.append({"row": i, "why": f"value_kind 가 {'|'.join(VALUE_KINDS)} 가 아닙니다: "
                                            f"{row['value_kind']!r}"})
            continue
        if row["account_code"] not in known_accounts:
            # 자동 생성하지 않는다 — 오타가 새 계정이 되면 손익이 조용히 갈라진다.
            errors.append({"row": i, "why": f"등록되지 않은 계정입니다: {row['account_code']} "
                                            f"(계정을 먼저 등록하십시오)"})
            continue

        amount, why = _parse_amount(row["amount"])
        if amount is None:
            errors.append({"row": i, "why": why})
            continue

        key = (row["org_id"], row["account_code"], row["period"], vk)
        if key in seen:
            errors.append({"row": i, "why": f"중복 행입니다({seen[key]}행과 동일한 "
                                            f"조직·계정·기간·종류) — 어느 값이 맞는지 알 수 없습니다."})
            continue
        seen[key] = i

        valid.append({
            "org_id": row["org_id"], "account_code": row["account_code"],
            "period": row["period"], "value_kind": vk, "amount": amount,
            "currency": row.get("currency") or "KRW",
            "source_ref": row.get("source_ref") or "",
            "owner_organization_id": row.get("owner_organization_id") or "",
            "scope_type": row.get("scope_type") or "ORG_PRIVATE",
            "classification": row.get("classification") or "INTERNAL",
        })

    by_kind: Dict[str, int] = {}
    for v in valid:
        by_kind[v["value_kind"]] = by_kind.get(v["value_kind"], 0) + 1

    return {
        "ok": not errors,
        "errors": errors,
        "valid_rows": valid,
        "summary": {
            "total": len(rows), "valid": len(valid), "rejected": len(errors),
            "by_value_kind": by_kind,
            "orgs": sorted({v["org_id"] for v in valid}),
            "periods": sorted({v["period"] for v in valid}),
        },
        "note": ("문제가 있는 행이 하나라도 있으면 **아무것도 저장하지 않습니다** — "
                 "부분 저장은 '맞는 것도 틀린 것도 아닌' 데이터를 남깁니다."),
    }


def import_rows(rows: List[Dict[str, Any]], commit: bool = False,
                source_ref: str = "") -> Dict[str, Any]:
    """검증 후 저장. **`commit=False` 가 기본**이다(미리보기).

    경영 데이터에서 "일단 넣고 고치자"는 나중에 무엇이 원본인지 알 수 없게 만든다."""
    report = validate_rows(rows)
    report["committed"] = False
    if not report["ok"]:
        return report
    if not commit:
        report["note"] = ("검증만 했습니다(미리보기). 저장하려면 commit=true 로 다시 "
                          "호출하십시오 — 무엇이 들어갈지 먼저 확인하는 것이 기본값입니다.")
        return report

    written = 0
    for v in report["valid_rows"]:
        planning_store.put_fact(
            org_id=v["org_id"], account_code=v["account_code"], period=v["period"],
            value_kind=v["value_kind"], amount=v["amount"], currency=v["currency"],
            source_ref=v["source_ref"] or source_ref,
            owner_organization_id=v["owner_organization_id"],
            scope_type=v["scope_type"], classification=v["classification"])
        written += 1
    report["committed"] = True
    report["written"] = written
    report["note"] = f"{written}건을 저장했습니다."
    return report


def parse_csv(text: str) -> List[Dict[str, Any]]:
    """CSV → 행 목록. BOM·빈 줄을 걸러낸다(엑셀 저장 파일의 흔한 형태)."""
    if not (text or "").strip():
        raise PlanningError("빈 파일입니다.")
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if not reader.fieldnames:
        raise PlanningError("헤더 행이 없습니다.")
    cols = {(c or "").strip() for c in reader.fieldnames}
    missing = [c for c in REQUIRED_COLUMNS if c not in cols]
    if missing:
        raise PlanningError(
            f"필수 열이 없습니다: {', '.join(missing)}. "
            f"필요한 열: {', '.join(REQUIRED_COLUMNS)} "
            f"(선택: {', '.join(OPTIONAL_COLUMNS)})")
    return [r for r in reader if any((v or "").strip() for v in r.values())]
