"""[M2 관문 B-4] 서버측 범위 계산 — **클라이언트가 보낸 범위는 요청이지 권한이 아니다.**

## 무엇이 문제였나 (2026-07-29 실측)

`POST /api/v1/mcp/resolve  { "scope_node_id": "BATTERY", ... }`

라우트가 요청 본문의 범위를 **그대로 믿었다.** 즉 아무나 남의 조직 코드를 적어 보내면 그
범위로 조회됐다. 인증 주체와 무관하게 동작하므로, 조직 격리를 아무리 촘촘히 만들어도
그 앞단에서 통째로 우회된다.

## 신뢰 경계

```
[클라이언트]  scope_node_id="SMELTING"        ← 요청(신뢰하지 않음)
      │
[서버] Principal(인증 주체)
      → org_directory.resolve_scope(user_id)      # 부서 권한 (기존 자산)
      → scoping.resolve_scope_ref(dept → node)    # D-005 이중 형태 해석 (기존 자산)
      → scoping.visible_scopes(node)              # 운영 상속 (기존 자산)
      → 교차 검증: requested ∈ visible ?
           yes → requested 로 조회(경영진 드릴다운 허용)
           no  → 거부 + 감사 기록
```

**새로 만든 것은 교차 검증 한 겹뿐이다.** 나머지는 전부 이미 있는 자산을 잇는다.

## 왜 요청 범위를 아예 안 받지 않는가

상위 조직 사용자가 하위 조직 문맥으로 조회하는 것은 **정당한 사용**이다(경영진 드릴다운).
요청을 막으면 그 기능이 사라진다. 그래서 **"요청은 받되 검증한다"** 로 간다.

## 무제한 주체(조직 미도입)

`scope.unrestricted` 는 조직을 아직 도입하지 않은 상태의 하위호환 계약이다. 이때는 요청 범위를
그대로 통과시킨다 — 여기서 막으면 조직을 세우기도 전에 전 API 가 잠긴다.
"""
from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass(frozen=True)
class EffectiveScope:
    """교차 검증 결과. `denied` 면 호출부는 **404 로 은폐하고 감사에 남긴다**."""
    scope_node_id: str = ""          # 검증을 통과한 실효 범위(빈 값 = 범위 필터 없음)
    actor: str = ""
    allowed_scopes: List[str] = field(default_factory=list)   # 서버가 계산한 값
    denied: bool = False
    reason: str = ""


def _actor_scopes(p: Any) -> List[str]:
    """주체의 조직 범위(ECM node) 집합. 부서 권한을 노드로 승격해 재사용한다(D-004·D-005)."""
    if p is None:
        return []
    scope = getattr(p, "scope", None)
    dept_ids = sorted(getattr(scope, "readable_dept_ids", None) or ())
    if not dept_ids:
        primary = getattr(scope, "primary_dept_id", "") or ""
        dept_ids = [primary] if primary else []
    out: List[str] = []
    try:
        from core.enterprise_context.scoping import resolve_scope_ref, visible_scopes
        for d in dept_ids:
            node = resolve_scope_ref(d)
            if not node:
                continue
            out.append(node)
            out.extend(visible_scopes(node))
    except Exception as e:
        # 해석 실패를 '전부 허용'으로 처리하면 리솔버 장애가 곧 전사 유출이 된다.
        print(f"⚠️ [scope_guard] 주체 범위 해석 실패 — 빈 집합으로 처리(fail-closed): {e}")
        return []
    return sorted(set(out))


def resolve_effective_scope(p: Any, requested_scope: str = "") -> EffectiveScope:
    """요청 범위를 인증 주체의 범위 안에서 교차 검증한다.

    - 무제한 주체(조직 미도입) → 요청을 그대로 통과(하위호환 계약)
    - 요청 없음 → 필터 없음(종전 동작). 주체의 범위로 **자동 축소하지 않는다** — 조용한
      동작 변경은 "왜 결과가 줄었는지" 아무도 모르게 만든다. 축소가 필요하면 호출부가 명시한다.
    - 요청 있음 → 주체의 가시 범위에 속할 때만 허용, 아니면 `denied`
    """
    actor = str(getattr(p, "user_id", "") or "")
    scope = getattr(p, "scope", None)
    unrestricted = bool(getattr(scope, "unrestricted", False)) if scope is not None else True

    if unrestricted:
        return EffectiveScope(scope_node_id=requested_scope or "", actor=actor,
                              allowed_scopes=["*"], reason="unrestricted")
    if not requested_scope:
        return EffectiveScope(scope_node_id="", actor=actor,
                              allowed_scopes=_actor_scopes(p), reason="no_scope_requested")

    allowed = _actor_scopes(p)
    requested_node = requested_scope
    try:
        from core.enterprise_context.scoping import resolve_scope_ref
        requested_node = resolve_scope_ref(requested_scope) or requested_scope
    except Exception:
        pass

    if requested_node in allowed:
        return EffectiveScope(scope_node_id=requested_node, actor=actor,
                              allowed_scopes=allowed, reason="verified")
    return EffectiveScope(scope_node_id="", actor=actor, allowed_scopes=allowed,
                          denied=True, reason="requested_scope_not_in_actor_scopes")
