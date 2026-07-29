"""[ECM E2] 조직 범위 가시성 — 카탈로그·용어사전·계약이 **공유하는 단 하나의** 판정 로직.

## 왜 공유 모듈인가

같은 규칙을 세 모듈에 복제하면 반드시 어긋난다. 이 프로젝트에서 이미 겪은 유형이다 —
`node_industry_code` 가 전역 리솔버를 쓰는 바람에 검증이 조용히 꺼졌고, 재시드가 바인딩을
건너뛰어 격리가 무너졌다. 권한·격리 판정은 **한 곳에만** 두고 거기서 고친다.

## 규칙 (D-003 과 동일 — 여기서 다시 정하지 않는다)

1. **상속은 `OPERATING_PARENT` 만 따른다.** 공유서비스·연결집계 관계는 읽기 권한을 주지 않는다.
   상위 조직의 것은 하위가 본다(전사 표준 → 사업부). 그 반대는 아니다.
2. **범위가 빈 레코드는 전사 공용으로 통과한다**(점진 도입). 도입 전 기능이 통째로 멈추면
   아무도 도입하지 않는다.
   ⚠️ 단 이것은 **유출 창구이기도 하다** — 2026-07-29 에 기준정보에서 실제로 그렇게 샜다.
   그래서 `coverage()` 로 **미지정 건수를 상시 셀 수 있게** 함께 제공한다. 규칙이 위험한 게
   아니라 조용한 노출이 위험하다.
3. **호출자가 범위를 주지 않으면 필터하지 않는다.** ECM 미도입 흐름을 막지 않는다.
4. `entity_mode` 는 정확히 일치해야 한다 — REAL 문맥에 VIRTUAL 데이터가 섞이면 그게 곧 오염이다.
"""
from typing import Any, Dict, Iterable, List, Optional, Set


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
    if not owner:
        return True                                    # 전사 공용(점진 도입) — coverage 로 관측
    return owner in (visible if visible is not None else visible_scopes(scope_node_id))


def filter_visible(rows: Iterable[Dict[str, Any]], scope_node_id: str = "",
                   tenant_id: str = "", entity_mode: str = "REAL") -> List[Dict[str, Any]]:
    """목록에 가시성 필터를 건다. 조상 해석은 **한 번만** 한다(행마다 리솔버를 때리지 않게)."""
    vis = visible_scopes(scope_node_id) if scope_node_id else set()
    return [r for r in rows
            if is_visible(r, scope_node_id, tenant_id, entity_mode, vis)]


def coverage(rows: Iterable[Dict[str, Any]], label: str = "레코드") -> Dict[str, Any]:
    """범위 미지정(= 전 조직 노출) 건수를 센다.

    ★ 점진 도입 규칙을 유지하는 대가로 **반드시** 함께 제공해야 하는 관측이다. 노출이 조용하면
      아무도 모르고, 그 상태가 기준정보에서 실제 사고가 됐다."""
    rows = list(rows)
    unscoped = [r for r in rows if not (r.get("enterprise_scope_id") or "").strip()]
    total = len(rows)
    return {
        "total": total,
        "scoped": total - len(unscoped),
        "unscoped": len(unscoped),
        "coverage_ratio": round((total - len(unscoped)) / total, 4) if total else 1.0,
        "note": (f"범위가 지정되지 않은 {label} 는 **모든 조직에** 보입니다(점진 도입 규칙). "
                 f"의도한 전사 공용이면 정상이고, 아니면 소유 조직을 지정하십시오."),
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
