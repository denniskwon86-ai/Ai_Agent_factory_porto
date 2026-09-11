"""실적 인증 정책 — **관리자가 화면에서 바꿀 수 있는 값**만 여기 둔다. (2026-09-11)

## 왜 상수가 아니라 저장소인가

「경영관리팀장이 최종 승인한다」와 「대사 증거는 SAP 기준으로 적는다」는 **회사마다·시기마다
다르다.** 코드 상수로 두면 바꾸는 데 배포가 필요하고, 그러면 사람들은 아예 안 바꾸거나
(맞지 않는 정책을 그냥 쓰거나) 규칙을 우회한다.

`core/model_routing_policy.py` · `core/scope_policy.py` 와 **같은 규약**을 쓴다:

    1. **기본값은 코드에 남는다.** 저장소가 없거나 깨져도 동작이 멈추지 않는다.
    2. **변경은 이력에 남는다.** 누가·언제·왜 바꿨는지 없으면 되돌릴 근거가 없다.
    3. **되돌릴 수 있다.** 이전 값을 함께 남긴다.
    4. **호출 시점에 읽는다.** 캐시하면 화면에서 바꿔도 재시작해야 한다.

## ★★★ 검토는 «단계» 가 아니라 «종류» 다

사용자 질문(2026-09-11): 「부서장 → 경영관리팀장 2단이면 복잡해지지 않나」.

복잡해지지 않는다 — `core/publication.py` 가 이미 같은 문제를 풀어 뒀다:

    REVIEW_TYPES = (EXECUTIVE, LEGAL_DISCLOSURE, SECURITY, DATA_OWNER)
    EXTERNAL_REQUIRED_REVIEWS = (EXECUTIVE, LEGAL_DISCLOSURE)   ← 유형별로 «필요한 종류»

★ 검토는 **병렬 확인**이지 순차 결재가 아니다. 순차로 만들면 부서장이 휴가 갈 때
  **전체가 멈추고**, 조직 개편 때마다 결재선이 코드 변경이 된다.
  필요한 «종류» 만 정하고 순서는 사람에게 맡긴다.

## ⚠️ 여기서 «하지 않는» 것

★★★ **이 정책은 「누가 승인권자인가」를 정하지 않는다.** 그것은 조직 정본
  (`organization_nodes` · 사용자 권한 플래그)이 정하고, `ownership_binding.
  _require_approval_authority()` 가 네 관문으로 검사한다. 여기 있는 것은
  **「어떤 «종류» 의 서명이 필요한가」**와 **「그 종류를 맡는 자리가 무엇이라 불리는가」**다.

⚠️ 두 개를 뭉개면 화면에서 아무 이름이나 넣고 그 사람이 승인권자가 된다.

LLM 0콜.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.paths import data_path

_PATH = data_path("actual_certification_policy.json")

#: 어느 값이 이겼는지 — 화면이 그대로 보여 준다.
SOURCE_STORE = "store"
SOURCE_CODE = "code"

#: 서명 «종류». `publication.REVIEW_TYPES` 와 **같은 어휘를 쓴다** — 두 벌로 만들면
#: 한쪽만 늘어나는 날이 온다.
REVIEW_DATA_OWNER = "DATA_OWNER"
REVIEW_EXECUTIVE = "EXECUTIVE"
REVIEW_KINDS = (REVIEW_DATA_OWNER, REVIEW_EXECUTIVE)

#: 실적의 «용도». 어디에 쓰는 실적이냐에 따라 필요한 서명 종류가 다르다.
USE_OPERATIONAL = "OPERATIONAL"      # 부서 안에서 쓰는 실적
USE_MANAGEMENT = "MANAGEMENT"        # 전사 경영 보고에 올라가는 실적
USE_KINDS = (USE_OPERATIONAL, USE_MANAGEMENT)

#: ★★★ 코드 기본값. **저장소가 없거나 깨져도 이 값으로 돈다.**
#:
#: ⚠️ 사용자 지시(2026-09-11): 「우선은 경영관리팀장 승인으로 해 놓고 나중에 화면에서
#:   바꿀 수 있게」 · 「대사 증거도 SAP ERP 기준 추천안으로 초기 설정」.
#:   그래서 **초기값이지 정답이 아니다** — 화면에서 바꾸라고 만든 값이다.
DEFAULTS: Dict[str, Any] = {
    #: 용도별로 «필요한 서명 종류». 부서 운영용은 소유 부서만, 경영 보고용은 둘 다.
    "required_reviews": {
        USE_OPERATIONAL: [REVIEW_DATA_OWNER],
        USE_MANAGEMENT: [REVIEW_DATA_OWNER, REVIEW_EXECUTIVE],
    },
    #: 각 종류를 «맡는 자리» 의 이름. ⚠️ 사람 이름이 아니라 **자리** 다 —
    #: 실제 승인권은 조직 정본이 정한다(이 파일 머리말 참조).
    "reviewer_titles": {
        REVIEW_DATA_OWNER: "데이터 소유 부서장",
        #: ★ 초기값은 «경영관리팀장». 담당임원으로 바꾸려면 화면에서 바꾼다.
        REVIEW_EXECUTIVE: "경영관리팀장",
    },
    #: 대사 증거 — 「무엇과 맞춰 봤는가」.
    #: ⚠️⚠️ 제품이 «형식» 을 강제하지 않는다. ERP 마다 다르고, 강제하는 순간 그 ERP
    #:   전용이 된다. 아래는 **적는 요령을 보여 주는 추천안**이고 검증하는 것은
    #:   「빈 값이 아닌가」 하나뿐이다.
    "reconciliation": {
        "source_system": "SAP ERP",
        #: 무엇을 적으면 좋은지 — 화면이 이 목록을 «안내 문구» 로 그린다.
        "recommended_fields": [
            "회계연도·전기기간 (예: 2026/08)",
            "마감 확정 시각 또는 마감 배치 식별자",
            "대사한 계정과 금액 (예: 4000 100,000 / 5000 90,000)",
            "대사 결과 (일치 / 차이와 사유)",
        ],
        #: 화면의 입력 상자에 회색으로 뜰 예시.
        "example": ("SAP FI 2026/08 마감(2026-09-05 확정) · "
                    "계정 4000 100,000 / 5000 90,000 대사 일치"),
        #: ★ 이것만이 «검증되는» 값이다. 나머지는 안내다.
        "min_length": 10,
    },
}


class ActualCertificationPolicyError(ValueError):
    """정책 값 검증 실패 — 4xx 로 전달한다."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read() -> Dict[str, Any]:
    try:
        with open(_PATH, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        return doc if isinstance(doc, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}                                  # 없거나 깨졌으면 코드 기본값으로


def _write(doc: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(_PATH) or ".", exist_ok=True)
    with open(_PATH, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)


def _stored(key: str) -> Optional[Any]:
    value = _read().get(key)
    return value if isinstance(value, dict) else None


def effective() -> Dict[str, Any]:
    """지금 실제로 적용되는 정책과 **어느 값이 이겼는지.**

    ★ 화면은 값만이 아니라 `source` 를 함께 그려야 한다 — 안 그리면 관리자가 바꾸고
      「바꿨다」고 믿는데 저장이 안 된 상태를 볼 수 없다."""
    out: Dict[str, Any] = {}
    for key in ("required_reviews", "reviewer_titles", "reconciliation"):
        stored = _stored(key)
        #: ⚠️ 저장소 값으로 **통째로 갈아치우지 않는다.** 부분 저장을 허용하면 코드에
        #:   새 항목이 생겼을 때 저장소를 쓴 회사에서만 그 항목이 «사라진다».
        merged = dict(DEFAULTS[key])
        if stored:
            merged.update(stored)
        out[key] = merged
        out.setdefault("sources", {})[key] = SOURCE_STORE if stored else SOURCE_CODE
    out["code_defaults"] = json.loads(json.dumps(DEFAULTS, ensure_ascii=False))
    return out


def required_reviews(use_kind: str) -> List[str]:
    """이 용도의 실적에 **필요한 서명 종류**. 인증 관문이 부르는 자리.

    ⚠️ **호출 시점에 읽는다.** 캐시하면 화면에서 바꿔도 재시작해야 한다."""
    kind = str(use_kind or "").strip().upper()
    if kind not in USE_KINDS:
        raise ActualCertificationPolicyError(
            f"실적 용도는 {USE_KINDS} 중 하나여야 합니다(받은 값: {use_kind!r}). "
            f"「어디에 쓰는 실적인가」가 필요한 서명 종류를 정합니다.")
    return list(effective()["required_reviews"].get(kind) or [])


def reviewer_title(review_kind: str) -> str:
    """이 서명 종류를 맡는 «자리» 의 이름. 화면이 「누구에게 요청하나」를 그릴 때 쓴다."""
    return str(effective()["reviewer_titles"].get(str(review_kind or "").upper()) or "")


def assert_reconciliation_evidence(text: str) -> str:
    """대사 증거가 «있는가». ⚠️ **형식은 검사하지 않는다.**

    ★★★ ERP 마다 마감본을 특정하는 방법이 다르다. 제품이 형식을 정하면 그 ERP 전용이
      되고, 안 맞는 회사에서는 «아무 말이나» 적게 된다 — 그러면 검사가 있으나 마나다.
      여기서 막는 것은 **빈 값**과 **너무 짧아 아무 정보도 없는 값** 둘뿐이다.

    ⚠️ 「숫자가 맞는가」를 이 함수가 판정하지 «않는다». 그것은 사람이 ERP 마감본과
      맞춰 본 결과이고, 여기 적히는 것은 그 «결과의 기록» 이다."""
    value = str(text or "").strip()
    rec = effective()["reconciliation"]
    if not value:
        raise ActualCertificationPolicyError(
            f"대사 증거가 필요합니다 — 「무엇과 맞춰 봤는가」가 없으면 이 판이 실적이라는 "
            f"근거가 없습니다. 예: {rec.get('example')}")
    if len(value) < int(rec.get("min_length") or 0):
        raise ActualCertificationPolicyError(
            f"대사 증거가 너무 짧습니다({len(value)}자) — 어느 마감본과 무엇을 맞췄는지 "
            f"알 수 있어야 합니다. 권장 항목: {', '.join(rec.get('recommended_fields') or [])}")
    return value


def history(limit: int = 20) -> List[Dict[str, Any]]:
    rows = _read().get("history") or []
    return rows[-limit:][::-1] if isinstance(rows, list) else []


def update(key: str, value: Dict[str, Any], actor: str, reason: str = "") -> Dict[str, Any]:
    """정책 한 항목을 바꾼다(관리자 전용 — 권한 검사는 API 계층).

    ⚠️ `actor` 를 요구한다 — 「경영관리팀장」을 「담당임원」으로 바꾸는 것은 **책임자를
      바꾸는 일**이고, 누가 바꿨는지 없으면 되돌릴 근거가 없다."""
    if key not in DEFAULTS:
        raise ActualCertificationPolicyError(
            f"바꿀 수 있는 항목은 {tuple(DEFAULTS)} 입니다(받은 값: {key!r}).")
    if not isinstance(value, dict) or not value:
        raise ActualCertificationPolicyError("값은 비어 있지 않은 객체여야 합니다.")
    if not str(actor or "").strip():
        raise ActualCertificationPolicyError(
            "actor 는 필수입니다 — 누가 정책을 바꿨는지 없으면 되돌릴 근거가 없습니다.")

    if key == "required_reviews":
        for use_kind, kinds in value.items():
            if str(use_kind).upper() not in USE_KINDS:
                raise ActualCertificationPolicyError(
                    f"실적 용도는 {USE_KINDS} 중 하나여야 합니다: {use_kind!r}")
            if not isinstance(kinds, list) or not kinds:
                raise ActualCertificationPolicyError(
                    f"«{use_kind}» 의 필요 서명이 비었습니다 — 서명이 하나도 없는 인증은 "
                    f"인증이 아닙니다. 없애려면 그 용도를 쓰지 마십시오.")
            for kind in kinds:
                if str(kind).upper() not in REVIEW_KINDS:
                    raise ActualCertificationPolicyError(
                        f"서명 종류는 {REVIEW_KINDS} 중 하나여야 합니다: {kind!r}")
            #: ★★★ 소유 부서 서명은 **뺄 수 없다.** 「이 숫자가 우리 부서 것이 맞다」는
            #:   실적 인증의 바닥이고, 그것 없이 임원만 서명하면 임원은 무엇을 근거로
            #:   누르는가에 답할 수 없다.
            if REVIEW_DATA_OWNER not in [str(k).upper() for k in kinds]:
                raise ActualCertificationPolicyError(
                    f"«{use_kind}» 에서 {REVIEW_DATA_OWNER} 를 뺄 수 없습니다 — "
                    f"「이 숫자가 우리 부서 것이 맞다」는 실적 인증의 바닥입니다.")
    if key == "reviewer_titles":
        for kind, title in value.items():
            if str(kind).upper() not in REVIEW_KINDS:
                raise ActualCertificationPolicyError(
                    f"서명 종류는 {REVIEW_KINDS} 중 하나여야 합니다: {kind!r}")
            if not str(title or "").strip():
                raise ActualCertificationPolicyError(
                    f"«{kind}» 의 자리 이름이 비었습니다 — 화면이 「누구에게 요청하나」를 "
                    f"그릴 수 없습니다.")
    if key == "reconciliation":
        if "min_length" in value:
            try:
                length = int(value["min_length"])
            except (TypeError, ValueError):
                raise ActualCertificationPolicyError("min_length 는 정수여야 합니다.")
            if length < 1:
                raise ActualCertificationPolicyError(
                    "min_length 를 0 으로 두면 빈 값이 통과합니다 — 그러면 대사 증거를 "
                    "요구하는 의미가 사라집니다.")

    doc = _read()
    before = doc.get(key)
    doc[key] = value
    rows = doc.get("history")
    doc["history"] = (rows if isinstance(rows, list) else []) + [{
        "at": _now(), "actor": actor.strip(), "key": key,
        "before": before, "after": value, "reason": str(reason or "").strip(),
    }]
    _write(doc)
    return effective()
