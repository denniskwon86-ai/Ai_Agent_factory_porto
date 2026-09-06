"""[DAO-9] 계보 질의 — 「이 숫자는 어디서 왔나」에 답한다.

설계서 §6.2 가 요구하는 질문은 하나다.

> "2026년 12월 15일 실행한 A공장 손익 시뮬레이션은, 어떤 환율·원자재 가격·전력비 가정·
>  사내 실적을 사용했는가?"

이 모듈이 그 답의 마지막 구간을 만든다:

    값 → 업무키 → 격리 적재행 → raw_object → checksum → source

## ★★★ 값만 돌려주지 않는다

`answer()` 는 **값과 출처를 함께** 돌려준다. 값만 주면 화면이 그것을 어디서든 쓰게 되고,
그때부터 「그 계획이 당시 어떤 발표값을 썼는가」는 아무도 재현하지 못한다.

⚠️ 그래서 이 모듈에는 「값만 주는」 함수가 없다. 있으면 그 함수가 쓰인다.

## ★★★ 정정공시 뒤에도 옛 답을 재현한다

`as_of` 를 주면 **그 시점에 발표돼 있던 판**으로 답한다. 지금 현행인 값이 아니라, 그때
사람이 볼 수 있었던 값이다. 그것이 재현이고, 지금 값으로 답하는 것은 사후 보정이다.

## 공개 자료임을 답에 실어 보낸다

`data_origin` 이 `PUBLIC_DISCLOSED` 면 `not_for_internal_actual=True` 를 함께 준다.
공시 재무제표는 사실이지만 **내부 매입·고객·BOM 실적을 대체하지 않는다.**
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from core.external_intelligence import acquisition_models as am


class ProvenanceError(ValueError):
    """질의를 만들 수 없다 — 4xx 로 전달한다."""


@dataclass(frozen=True)
class Answer:
    """값 하나와 **그 값이 어디서 왔는지**. 둘은 떨어지지 않는다."""
    found: bool
    value: Any = None
    unit: str = ""
    #: 언제의 값인가
    period: str = ""
    published_at: str = ""
    vintage_date: str = ""
    #: 어디서 왔나
    source_id: str = ""
    trust_grade: str = ""
    data_origin: str = ""
    raw_object_ref: str = ""
    checksum: str = ""
    business_key: str = ""
    contract_key: str = ""
    #: 이 값을 무엇에 쓰면 안 되는가
    not_for_internal_actual: bool = False
    #: 이 답이 대체된 판 위에 서 있지 않은지
    superseded_by: str = ""
    #: 같은 자리에 다른 판이 몇 개 있었나(정정 이력의 깊이)
    other_vintages: Tuple[str, ...] = ()
    reason: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "found": self.found, "value": self.value, "unit": self.unit,
            "period": self.period, "published_at": self.published_at,
            "vintage_date": self.vintage_date, "source_id": self.source_id,
            "trust_grade": self.trust_grade, "data_origin": self.data_origin,
            "raw_object_ref": self.raw_object_ref, "checksum": self.checksum,
            "business_key": self.business_key, "contract_key": self.contract_key,
            "not_for_internal_actual": self.not_for_internal_actual,
            "superseded_by": self.superseded_by,
            "other_vintages": list(self.other_vintages), "reason": self.reason,
        }


def _rows_for(store, *, contract_key: str, limit: int = 5000) -> List[Dict[str, Any]]:
    return list(store.staged_rows(contract_key=contract_key, limit=limit))


def answer(store, *, contract_key: str, match: Mapping[str, Any],
           value_field: str = "amount", as_of: str = "",
           unit_field: str = "currency") -> Answer:
    """`match` 를 만족하는 행 하나를 찾아 **값과 출처를 함께** 돌려준다.

    ⚠️ 여러 판이 있으면 (정정공시) **가장 최근 발표본**을 고르되, `as_of` 가 있으면 그
      시점까지 발표된 것 중 최신을 고른다."""
    if not str(contract_key or "").strip():
        raise ProvenanceError("계약 키가 필요합니다.")
    if not match:
        #: ★★★ 빈 조건은 「전부」가 아니다. 아무거나 하나를 돌려주면 그 값이 근거가 된다.
        raise ProvenanceError("조회 조건이 비어 있습니다 — 빈 조건은 «전부»가 아니라 오류입니다.")

    cutoff = str(as_of or "").strip()
    candidates: List[Dict[str, Any]] = []
    for row in _rows_for(store, contract_key=contract_key):
        payload = dict(row.get("payload") or {})
        if not all(str(payload.get(k, "")) == str(v) for k, v in match.items()):
            continue
        published = str(payload.get("published_at") or row.get("as_of_date") or "")
        if cutoff and published and published > cutoff:
            continue          # 그때는 아직 발표되지 않았다
        candidates.append({"row": row, "payload": payload, "published": published})

    if not candidates:
        return Answer(found=False, contract_key=contract_key,
                      reason=("조건에 맞는 값이 없습니다 — 아직 수집되지 않았거나, "
                              "as_of 시점에는 발표되지 않았습니다."))

    candidates.sort(key=lambda c: (c["published"], str(c["payload"].get("rcept_no") or "")))
    chosen = candidates[-1]
    payload, row = chosen["payload"], chosen["row"]
    origin = str(row.get("data_origin") or "")
    return Answer(
        found=True,
        value=payload.get(value_field),
        unit=str(payload.get(unit_field) or ""),
        period=str(payload.get("bsns_year") or ""),
        published_at=chosen["published"],
        vintage_date=str(payload.get("vintage_date") or chosen["published"]),
        source_id=str(payload.get("source_id") or ""),
        trust_grade=str(payload.get("trust_grade") or ""),
        data_origin=origin,
        raw_object_ref=str(row.get("raw_object_ref") or ""),
        checksum=str(row.get("checksum") or ""),
        business_key=str(row.get("business_key") or ""),
        contract_key=contract_key,
        #: ★★★ 공개 자료는 사실이지만 내부 실적이 아니다.
        not_for_internal_actual=origin not in am.ORIGINS_FOR_INTERNAL_ACTUAL,
        superseded_by=str(row.get("superseded_by") or ""),
        other_vintages=tuple(sorted({c["published"] for c in candidates
                                     if c["published"] != chosen["published"]})),
        reason="",
    )


def series(store, *, contract_key: str, match: Mapping[str, Any],
           period_field: str = "bsns_year", value_field: str = "amount",
           as_of: str = "") -> List[Answer]:
    """기간별 값 목록. **각 항목이 자기 출처를 들고 있다.**

    ⚠️ 값만 담은 배열을 돌려주지 않는다 — 배열이 되는 순간 출처가 떨어져 나가고,
      그래프에 그려진 뒤에는 아무도 되짚지 않는다."""
    periods = sorted({str((r.get("payload") or {}).get(period_field) or "")
                      for r in _rows_for(store, contract_key=contract_key)} - {""})
    out = []
    for period in periods:
        found = answer(store, contract_key=contract_key,
                       match=dict(match, **{period_field: period}),
                       value_field=value_field, as_of=as_of)
        if found.found:
            out.append(found)
    return out


def verify_chain(store, raw_store, ans: Answer) -> Dict[str, Any]:
    """답의 계보가 **지금도 성립하는지** 확인한다.

    값 → 원문 참조 → 파일 존재 → 체크섬 일치. 한 고리라도 끊기면 그 답은 근거가 없다."""
    if not ans.found:
        return {"ok": False, "reason": "NOT_FOUND"}
    if not ans.raw_object_ref:
        return {"ok": False, "reason": "NO_RAW_OBJECT",
                "detail": "값은 있는데 원문 참조가 없습니다 — 계보가 끊겼습니다."}
    verified = raw_store.verify(ans.raw_object_ref)
    if not verified.get("ok"):
        return {"ok": False, "reason": verified.get("reason") or "CHECKSUM_MISMATCH",
                "detail": "원문이 사라졌거나 바뀌었습니다.", "raw": verified}
    if ans.checksum and verified.get("expected") != ans.checksum:
        return {"ok": False, "reason": "CHECKSUM_DRIFT",
                "detail": "적재행이 기억하는 체크섬과 원문의 것이 다릅니다."}
    return {"ok": True, "raw_object_ref": ans.raw_object_ref, "checksum": ans.checksum,
            "source_id": ans.source_id}


def account_mapping_preview(rows: Sequence[Mapping[str, Any]], *,
                            internal_accounts: Sequence[Mapping[str, Any]]
                            ) -> Dict[str, Any]:
    """공개 계정과 내부 계정의 **연결 미리보기**(지시 10).

    ★★★ 이것은 **제안이지 매핑이 아니다.** 이름이 비슷하다는 것은 근거가 아니고, 계정
      대응은 업무 판단이다. 그래서 모든 항목이 `requires_human_approval` 이고, 자신 있는
      것과 없는 것을 **가르지 않는다** — 가르면 「자신 있는 쪽」이 자동 승인된다.
    """
    public_accounts: Dict[str, str] = {}
    for r in rows:
        payload = dict(r.get("payload") or r)
        code = str(payload.get("account_id") or "")
        if code:
            public_accounts.setdefault(code, str(payload.get("account_nm") or ""))

    internal = [{"code": str(a.get("code") or a.get("account_code") or ""),
                 "name": str(a.get("name") or a.get("account_name") or "")}
                for a in internal_accounts]

    suggestions = []
    for code, name in sorted(public_accounts.items()):
        matches = [i for i in internal if i["name"] and name and
                   (i["name"] in name or name in i["name"])]
        suggestions.append({
            "public_account_id": code, "public_account_name": name,
            "candidate_internal": [m["code"] for m in matches[:3]],
            "basis": ("계정명 문자열 겹침" if matches else "겹치는 내부 계정명 없음"),
            #: ⚠️ 예외 없이 전부 사람 승인이다.
            "requires_human_approval": True,
        })
    return {
        "suggestions": suggestions,
        "public_account_count": len(public_accounts),
        "internal_account_count": len(internal),
        "notice": ("이것은 제안이며 매핑이 아닙니다. 계정명이 겹친다는 것은 같은 계정이라는 "
                   "근거가 아닙니다 — 회계 담당이 항목마다 승인해야 매핑이 됩니다."),
    }
