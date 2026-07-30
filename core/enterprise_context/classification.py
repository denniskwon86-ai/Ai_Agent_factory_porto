"""[M2 §2.1 / §6-2] 등급(classification) 판정 — **감추지 않고 가린다.**

## 사용자 결정 (2026-07-30)

> `CONFIDENTIAL` 자원은 **제목만 보이고 내용은 차단**한다.

두 대안 중 이쪽을 택한 이유가 동작에 그대로 반영된다:

  · **완전 비노출**은 가장 안전하지만 "분명히 있는데 안 보인다"는 문의를 만들고, 사용자는
    같은 자료를 **다시 만든다** — 중복은 그렇게 태어난다(프로그램 사용여부에서 겪은 것과 같다).
  · **제목만 노출**은 "이 자료가 있으니 권한을 요청하자"로 이어져 업무 흐름이 끊기지 않는다.
    대가는 제목 자체가 민감할 수 있다는 것이다(예: 'A사 인수 검토') — 그래서 제목을 남기는
    것은 **등급 판정의 결과**이고, 제목까지 감춰야 하는 자원은 `CONFIDENTIAL` 이 아니라
    범위(`ORG_PRIVATE`)로 막아야 한다. 두 축을 섞지 않는다.

## 범위(scope)와 등급(classification)은 다른 축이다

  · 범위 — **볼 수 있는 조직인가**. 아니면 목록에서 아예 빠진다(fail-closed).
  · 등급 — **볼 수 있는 등급인가**. 아니면 목록에는 남고 **내용이 가려진다**.

⚠️ 이 순서가 중요하다. 범위를 통과하지 못한 행은 등급 판정에 오지 않는다 — 타 조직 자원의
  제목을 보여주면 §3.3 의 은폐 경계가 무너진다. 가림은 **내 조직 자원에만** 적용된다.

## 주체의 등급을 어디서 얻는가

전용 사용자 등급 컬럼은 아직 없다. 새로 만드는 대신 기존 권한 해석(`AccessScope`)에서
파생한다 — 권한과 등급을 두 곳에서 관리하면 반드시 어긋난다.

  · 무제한(조직 미도입)·관리자·경영진·데이터 관리자 → `CONFIDENTIAL`
  · 그 외 식별된 사용자                              → `INTERNAL`
  · 식별되지 않은 주체                               → `PUBLIC`

⚠️ 이것은 **파생**이지 선언이 아니다. 실제 인사등급 체계가 오면 그때 컬럼으로 승격한다.
  파생 규칙을 여기 한 곳에 두는 이유는 그 승격이 한 곳 수정으로 끝나게 하기 위해서다.
"""
from typing import Any, Dict, Iterable, List, Optional, Set

PUBLIC = "PUBLIC"
INTERNAL = "INTERNAL"
CONFIDENTIAL = "CONFIDENTIAL"
#: 낮은 등급 → 높은 등급 순. 순서가 곧 서열이다.
CLEARANCES = (PUBLIC, INTERNAL, CONFIDENTIAL)
_RANK = {c: i for i, c in enumerate(CLEARANCES)}

#: 등급이 적히지 않은 행의 기본값. `PUBLIC` 으로 두면 미기재가 곧 공개가 된다 —
#: 관문 A 에서 "빈 값 = 전사 공용"을 폐기한 것과 같은 이유로 중간값을 기본으로 둔다.
DEFAULT_CLASSIFICATION = INTERNAL

#: 가려도 남기는 필드 — **식별에 필요한 최소**. "제목만 보인다"의 그 제목이다.
#: ⚠️ 여기에 필드를 더할 때는 "이 값이 내용인가 제목인가"를 물어야 한다. `definition`·
#:   `description`·`location`·`amount` 같은 것은 내용이므로 절대 들어오지 않는다.
KEEP_KEYS = frozenset({
    "name", "canonical_name", "title", "asset_type", "term_type", "contract_type",
    "status", "created_at", "updated_at", "classification", "scope_type",
    "owner_organization_id", "enterprise_scope_id", "tenant_id", "entity_mode",
})


#: 알 수 없는 등급의 서열 — **모든 열람 등급보다 높다.**
_UNKNOWN_RANK = len(CLEARANCES)


def rank(level: str) -> int:
    """**행의 등급** 서열. 모르는 값은 가장 높게 본다(아무도 내용을 못 본다).

    ★ 해석 실패를 통과로 두면 그게 곧 유출이다. 그리고 이렇게 두면 오타·오기입이 **저절로
      발견된다** — 내용이 안 보이니 누군가 신고한다. 조용히 `INTERNAL` 로 강등하면 잘못 적힌
      등급이 영원히 그 상태로 남는다."""
    return _RANK.get((level or "").strip().upper(), _UNKNOWN_RANK)


def clearance_rank(level: str) -> int:
    """**주체의 등급** 서열. 모르는 값은 가장 낮게 본다.

    ⚠️ 행과 주체는 실패 방향이 **반대**여야 한다. 같은 함수를 쓰면(모르는 값 = 최고 등급)
      주체 등급 문자열이 깨졌을 때 오히려 전부 보이게 된다 — 정확히 거꾸로다."""
    return _RANK.get((level or "").strip().upper(), _RANK[PUBLIC])


def classification_of(row: Dict[str, Any]) -> str:
    """행의 등급. 빈 값은 기본값이지만, **알 수 없는 값은 그대로 돌려준다.**

    ★ 알 수 없는 값을 기본값으로 바꿔 버리면 잘못 적힌 등급이 화면에서 정상으로 보이고,
      아무도 고치지 않는다. 원문을 남겨 눈에 띄게 한다."""
    lv = (row.get("classification") or "").strip().upper()
    if not lv:
        return DEFAULT_CLASSIFICATION
    return lv


def clearance_of_scope(scope: Any) -> str:
    """`AccessScope` 에서 주체의 등급을 **파생**한다(전용 컬럼이 생기면 여기만 고친다)."""
    if scope is None:
        return PUBLIC
    try:
        if (getattr(scope, "unrestricted", False) or getattr(scope, "is_admin", False)
                or getattr(scope, "is_executive", False)
                or getattr(scope, "is_data_admin", False)):
            return CONFIDENTIAL
        return INTERNAL if (getattr(scope, "user_id", "") or "").strip() else PUBLIC
    except Exception:
        return PUBLIC                                  # 해석 실패는 가장 낮은 등급으로


def may_see_content(row: Dict[str, Any], clearance: str) -> bool:
    """내용까지 볼 수 있는가. 등급이 낮으면 **행은 남고 내용이 가려진다.**"""
    return clearance_rank(clearance) >= rank(classification_of(row))


def redact(row: Dict[str, Any], clearance: str,
           keep: Optional[Set[str]] = None) -> Dict[str, Any]:
    """등급이 낮으면 내용을 제거하고 **가렸다는 사실을 행에 적는다.**

    ★ 조용히 비운 필드는 "값이 없음"과 구분되지 않는다. 그러면 사용자는 데이터가 비어 있다고
      믿고 다시 만들고, 감사에서는 "이 사용자가 값을 봤는가"에 답할 수 없다."""
    if may_see_content(row, clearance):
        return dict(row)
    keeps = keep or KEEP_KEYS
    out = {k: v for k, v in row.items()
           if k in keeps or k.endswith("_id")}
    out["redacted"] = True
    out["classification"] = classification_of(row)
    lv = out["classification"]
    unknown = lv not in _RANK
    out["redaction_reason"] = (
        f"등급 {lv} 자원입니다 — 제목·식별 정보만 표시되고 내용은 제공되지 않습니다"
        f"(현재 열람 등급: {(clearance or PUBLIC).upper()}). "
        + ("⚠️ 이 등급값은 **정의된 등급이 아닙니다**"
           f"(허용: {', '.join(CLEARANCES)}) — 잘못 기입된 것이므로 자료 관리자가 등급을 "
           "바로잡아야 합니다. 그때까지는 아무에게도 내용이 제공되지 않습니다."
           if unknown else
           "내용이 필요하면 자료 소유 조직에 열람 권한을 요청하십시오."))
    return out


def redact_all(rows: Iterable[Dict[str, Any]], clearance: str,
               keep: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    return [redact(r, clearance, keep) for r in rows]


def redaction_summary(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """몇 건이 가려졌는지 — **가림도 관측 대상**이다.

    ★ 가려진 건수를 세지 않으면 "등급 정책이 실제로 작동하는가"와 "과도하게 가리고 있는가"에
      둘 다 답할 수 없다. 과도한 가림은 사람들이 시스템 밖에서 자료를 주고받게 만든다."""
    rows = list(rows)
    hidden = [r for r in rows if r.get("redacted")]
    return {
        "total": len(rows), "redacted": len(hidden),
        "note": (f"{len(hidden)}건은 열람 등급이 낮아 **제목만** 표시됩니다(내용 차단). "
                 f"자료가 없는 것이 아니라 가려진 것입니다." if hidden else ""),
    }
