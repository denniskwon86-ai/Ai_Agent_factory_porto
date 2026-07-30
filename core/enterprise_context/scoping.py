"""[ECM E2] 조직 범위 가시성 — 카탈로그·용어사전·계약이 **공유하는 단 하나의** 판정 로직.

## 왜 공유 모듈인가

같은 규칙을 세 모듈에 복제하면 반드시 어긋난다. 이 프로젝트에서 이미 겪은 유형이다 —
`node_industry_code` 가 전역 리솔버를 쓰는 바람에 검증이 조용히 꺼졌고, 재시드가 바인딩을
건너뛰어 격리가 무너졌다. 권한·격리 판정은 **한 곳에만** 두고 거기서 고친다.

## 규칙 (D-003 과 동일 — 여기서 다시 정하지 않는다)

1. **상속은 `OPERATING_PARENT` 만 따른다.** 공유서비스·연결집계 관계는 읽기 권한을 주지 않는다.
   상위 조직의 것은 하위가 본다(전사 표준 → 사업부). 그 반대는 아니다.
2. **[관문 A · 2026-07-30] 범위가 빈 레코드는 기본 비노출이다(fail-closed).**
   종전 규칙("빈 값 = 전사 공용")은 폐기됐다 — 그것은 점진 도입 장치가 아니라 **유출 창구**였고,
   2026-07-29 에 기준정보에서 실제로 샜다(재시드가 바인딩을 건너뛰자 26건이 전 조직에 노출,
   LS전선 프롬프트에 MnM 기준정보가 들어갔다). 전사 공용은 **빈 값의 해석이 아니라 명시적
   상태**다:
     · `scope_type=ENTERPRISE_SHARED` + `approval_status=APPROVED` + 승인자 → 보인다
     · `scope_type=LEGACY_UNSCOPED` → 한시 예외로 보인다(**만료일 + 건수 관측 필수**)
     · 아무 표시도 없는 빈 범위 → **보이지 않는다**
   ⚠️ 승인 없는 `ENTERPRISE_SHARED` 를 통과시키면 승인 절차 자체가 장식이 된다.
3. **호출자가 범위를 주지 않으면 필터하지 않는다.** ECM 미도입 흐름을 막지 않는다.
   이 규칙이 관문 A 의 안전판이다 — 도입 전 사용자는 자기 데이터를 계속 전량 본다.
4. `entity_mode` 는 정확히 일치해야 한다 — REAL 문맥에 VIRTUAL 데이터가 섞이면 그게 곧 오염이다.

## 한시 예외(`LEGACY_UNSCOPED`)를 왜 남기는가

기존 데이터를 하루아침에 안 보이게 하면 도입이 멈춘다. 그러나 **통과시키는 것과 통과한 줄
모르는 것은 다르다** — 그래서 한시 예외에는 (ㄱ) 만료일(`LEGACY_GRANDFATHER_UNTIL`)과
(ㄴ) `coverage()` 의 별도 건수(`legacy_grandfathered`)가 붙는다. 만료 여부도 함께 보고하므로
"언제까지 봐줄 것인가"에 답하지 않은 채로 시간이 흐르는 일을 막는다.
"""
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Set

#: 명시적 전사 공용. 빈 범위를 전사 공용으로 **해석**하지 않는다 — 이 값이 적혀 있어야 한다.
ENTERPRISE_SHARED = "ENTERPRISE_SHARED"
#: 관문 A 이전에 만들어진 미지정 레코드. 한시 통과 + 건수 관측 대상.
LEGACY_UNSCOPED = "LEGACY_UNSCOPED"

#: 한시 예외 만료일. 지나도 자동으로 안 보이게 만들지는 않는다(운영 중 갑작스런 실명은
#: 그 자체가 사고다) — 대신 `coverage()` 가 `legacy_expired=True` 로 보고해 결정을 강제한다.
LEGACY_GRANDFATHER_UNTIL = "2026-12-31"


def visible_scopes(scope_node_id: str) -> Set[str]:
    """이 조직이 볼 수 있는 범위 집합 = 자기 자신 + 운영 상위 조상.

    조상 해석에 실패하면 **자기 자신만** 돌려준다(fail-closed). 실패를 '전부 보임'으로
    처리하면 리솔버 장애가 곧 전사 유출이 된다."""
    if not scope_node_id:
        return set()
    out = {scope_node_id}
    try:
        from core.enterprise_context.models import REL_OPERATING_PARENT
        from core.enterprise_context.resolver import ecm_resolver
        out |= set(ecm_resolver.ancestors(scope_node_id, REL_OPERATING_PARENT))
    except Exception as e:
        print(f"⚠️ [scoping] 조상 해석 실패 — 자기 범위만 적용(fail-closed): {e}")
    return out


def is_enterprise_shared(row: Dict[str, Any]) -> bool:
    """명시적 전사 공용 + **승인 이력**이 있는가.

    ★ `APPROVED` 라고 적혀 있는데 승인자가 비어 있으면 그것은 승인 이력이 아니다 — 누가
      승인했는지 없는 승인은 감사에서 근거가 되지 못하므로 통과시키지 않는다."""
    if (row.get("scope_type") or "").strip().upper() != ENTERPRISE_SHARED:
        return False
    if (row.get("approval_status") or "").strip().upper() != "APPROVED":
        return False
    return bool((row.get("approved_by") or "").strip())


def is_legacy_unscoped(row: Dict[str, Any]) -> bool:
    """관문 A 이전 데이터에 붙는 한시 예외 표시인가."""
    return (row.get("scope_type") or "").strip().upper() == LEGACY_UNSCOPED


def is_visible(row: Dict[str, Any], scope_node_id: str, tenant_id: str = "",
               entity_mode: str = "REAL", visible: Optional[Set[str]] = None) -> bool:
    """레코드 한 건이 이 문맥에서 보이는가."""
    if tenant_id and (row.get("tenant_id") or "tenant_default") != tenant_id:
        return False
    if (row.get("entity_mode") or "REAL") != entity_mode:
        return False
    if not scope_node_id:
        return True                                    # 범위 미지정 호출 — 필터하지 않는다
    owner = (row.get("enterprise_scope_id") or "").strip()
    if owner:
        return owner in (visible if visible is not None else visible_scopes(scope_node_id))
    # ── 범위가 비어 있다 ─────────────────────────────────────────────────
    # [관문 A] 여기서 True 를 돌려주던 것이 유출 경로였다. 빈 값은 **아무 말도 하지 않은
    #   것**이고, "아무 말도 없음"을 "전 조직에 공개"로 읽으면 안 된다. 통과는 명시적으로
    #   적힌 두 상태에만 준다.
    if is_enterprise_shared(row):
        return True
    if is_legacy_unscoped(row):
        return True                                    # 한시 예외 — coverage() 가 센다
    return False


def filter_visible(rows: Iterable[Dict[str, Any]], scope_node_id: str = "",
                   tenant_id: str = "", entity_mode: str = "REAL") -> List[Dict[str, Any]]:
    """목록에 가시성 필터를 건다. 조상 해석은 **한 번만** 한다(행마다 리솔버를 때리지 않게)."""
    vis = visible_scopes(scope_node_id) if scope_node_id else set()
    return [r for r in rows
            if is_visible(r, scope_node_id, tenant_id, entity_mode, vis)]


def coverage(rows: Iterable[Dict[str, Any]], label: str = "레코드") -> Dict[str, Any]:
    """범위 미지정 건수를 **상태별로** 센다.

    ★ [관문 A] 이제 미지정은 노출이 아니라 **비노출**이다. 그래서 세는 목적이 바뀌었다:
      종전엔 "조용히 새는 건수"였고, 지금은 **"조용히 사라진 건수"** 다. 둘 다 조용하면
      위험하다 — 안 보이는 이유를 모르면 사용자는 데이터가 지워진 줄 안다.

    한시 예외(`legacy_grandfathered`)를 별도로 세는 이유: 통과시키는 것과 통과한 줄 모르는
    것은 다르다. 만료일이 지났는지(`legacy_expired`)도 함께 보고해, 결정하지 않은 채로
    시간이 흐르지 않게 한다."""
    rows = list(rows)
    total = len(rows)
    unscoped = [r for r in rows if not (r.get("enterprise_scope_id") or "").strip()]
    shared = [r for r in unscoped if is_enterprise_shared(r)]
    legacy = [r for r in unscoped if is_legacy_unscoped(r)]
    pending = [r for r in unscoped
               if (r.get("scope_type") or "").strip().upper() == ENTERPRISE_SHARED
               and not is_enterprise_shared(r)]
    hidden = [r for r in unscoped if not is_enterprise_shared(r) and not is_legacy_unscoped(r)]
    expired = date.today().isoformat() > LEGACY_GRANDFATHER_UNTIL
    return {
        "total": total,
        "scoped": total - len(unscoped),
        "unscoped": len(unscoped),
        "coverage_ratio": round((total - len(unscoped)) / total, 4) if total else 1.0,
        # ── 관문 A 이후의 상태별 내역 ──
        "enterprise_shared": len(shared),
        "enterprise_shared_pending": len(pending),
        "legacy_grandfathered": len(legacy),
        "hidden_unscoped": len(hidden),
        "legacy_grandfather_until": LEGACY_GRANDFATHER_UNTIL,
        "legacy_expired": expired,
        "note": (
            f"범위가 지정되지 않은 {label} 는 **기본적으로 보이지 않습니다**(관문 A · "
            f"fail-closed). 전사 공용으로 쓰려면 `scope_type=ENTERPRISE_SHARED` + 승인 "
            f"이력이 필요하고, 그렇지 않으면 소유 조직을 지정하십시오."
            + (f" 한시 예외 {len(legacy)}건은 {LEGACY_GRANDFATHER_UNTIL} 까지만 통과합니다."
               if legacy else "")
            + (" ⚠️ **한시 예외 만료일이 지났습니다** — 범위를 지정하거나 만료일을 다시 "
               "정하십시오." if expired and legacy else "")
            + (f" ⚠️ 승인 대기 중인 전사 공용 {len(pending)}건은 보이지 않습니다."
               if pending else "")
            + (f" ⚠️ 아무 표시도 없는 미지정 {len(hidden)}건은 보이지 않습니다 — 데이터가 "
               f"지워진 것이 아니라 범위 미지정으로 가려진 것입니다." if hidden else "")),
    }


def resolve_scope_ref(scope_ref: str) -> str:
    """부서 id 든 ECM node_id 든 노드로 정규화한다(D-005 — 두 형태 공존).

    해석 실패는 빈 문자열이다. 원본을 그대로 쓰면 존재하지 않는 범위에 갇혀 아무것도 안 보인다."""
    if not scope_ref:
        return ""
    try:
        from core.enterprise_context.resolver import ecm_resolver
        return ecm_resolver.resolve_scope_ref(scope_ref).get("node_id", "") or ""
    except Exception as e:
        print(f"⚠️ [scoping] 범위 해석 실패 '{scope_ref}': {e}")
        return ""
