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
    #: ★ [D-018 ③] 표시용 값. 화면은 `node_41402723bc90` 을 사람에게 보여줄 수 없으므로
    #  정본 id 와 함께 **업무 코드와 이름**을 내려준다. 이 둘을 저장하거나 판정에 쓰지 않는다 —
    #  판정은 `scope_node_id` 로만 한다(코드는 바뀔 수 있는 의미값이다).
    scope_code: str = ""
    scope_name: str = ""
    #: 요청 값이 어떤 형태로 들어왔는가(`ecm_node`·`ecm_code`·`department_mapped` 등).
    #  ⚠️ 이 값이 `ecm_node` 가 아니면 그 저장분은 **백필 대상**이다(D-018 ⑤).
    ref_kind: str = ""


def _actor_scopes(p: Any) -> List[str]:
    """주체의 조직 범위(ECM node) 집합. 부서 권한을 노드로 승격해 재사용한다(D-004·D-005).

    ★★★ [2026-08-05 실측 결함] **이 함수가 모든 사용자에게 빈 집합을 돌려주고 있었다.**

    원인: 부서 id 를 `resolve_scope_ref()` 로 노드로 바꾸는 경로만 있었는데, 실측하니 그
    리솔버가 `LS_MNM` · `MNM_BATTERY` · `production` 등 **모든 참조에 빈 문자열**을 돌려준다.
    그래서 `for` 루프가 전부 `continue` 되고 결과가 항상 `[]` 였다.

    그 결과 `resolve_effective_scope` 는 **범위를 명시하면 누구든 거부**했다(빈 집합에 속할 수
    없으므로). 실측한 영향:
      · `POST /planning/facts` · `/scenarios` · `/submissions` → `unrestricted` 가 아닌 **모든
        사용자에게 404**. 즉 경영계획을 현업 담당자가 쓸 수 없고 플랫폼 관리자만 쓸 수 있었다.
      · `GET /planning/cash-flow` · `/variance` → 같은 이유로 404.
    ⚠️ 반대로 범위를 **명시하지 않으면** 필터 없이 통과한다(`no_scope_requested`). 즉 통제가
      «전부 막힘 아니면 전부 열림» 으로 갈라져 있었고, 어느 쪽도 의도가 아니다.

    수정: **이미 확정된 노드 집합(`AccessScope.readable_scope_nodes`)을 먼저 쓴다.** 조직
    디렉터리가 스코프를 해석할 때 이미 계산해 들고 있는 값이고, `api.deps.viewer_visible_scopes`
    도 같은 원천을 본다 — 그래서 두 판정이 **한 원천으로 수렴**한다. 부서 id 해석은 그 값이
    없을 때의 폴백으로 남긴다(종전 동작 보존).

    ⚠️ `visible_scopes(n)` 은 기본값이 `include_descendants=False` 다 — 자기 + 조상만 펼치고
      **하위는 넣지 않는다.** 하향 열람은 경영진에게만 주는 규칙(사용자 결정 2026-07-30 ③)을
      이 함수가 우회하지 않게 하려면 이 기본값을 바꾸지 말 것.
    """
    if p is None:
        return []
    scope = getattr(p, "scope", None)
    out: List[str] = []
    try:
        from core.enterprise_context.scoping import resolve_scope_ref, visible_scopes
        # ① 확정된 노드 집합(정본). 여기 값이 있으면 부서 해석을 시도하지 않는다.
        for n in sorted(getattr(scope, "readable_scope_nodes", None) or ()):
            out.append(n)
            out.extend(visible_scopes(n))
        # ② 폴백 — 노드가 비어 있을 때만 부서 id 를 노드로 승격한다(종전 경로).
        if not out:
            dept_ids = sorted(getattr(scope, "readable_dept_ids", None) or ())
            if not dept_ids:
                primary = getattr(scope, "primary_dept_id", "") or ""
                dept_ids = [primary] if primary else []
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


def _describe(requested_scope: str, tenant_id: str, entity_mode: str) -> dict:
    """[D-018 ①③] 요청 값을 **정본 `node_id` + 표시용 코드·이름**으로 해석한다.

    ⚠️ 해석 실패·모호함은 `node_id` 가 비어 나온다. 그때 원본을 `node_id` 자리에 넣지 않는다 —
      그러면 「해석된 정본」과 「해석 못 한 원본」이 같은 필드에 섞이고, 그 값이 그대로 저장되면
      백필(D-018 ⑤)이 무엇을 고쳐야 하는지 알 수 없게 된다."""
    try:
        from core.enterprise_context.resolver import ecm_resolver
        r = ecm_resolver.resolve_scope_ref(requested_scope, tenant_id=tenant_id,
                                           entity_mode=entity_mode)
        return {"node_id": r.get("node_id") or "", "code": r.get("code") or "",
                "name_ko": r.get("name_ko") or "", "kind": r.get("kind") or ""}
    except Exception as e:
        print(f"⚠️ [scope_guard] 범위 해석 실패(원본으로 비교): {requested_scope} — {e}")
        return {"node_id": "", "code": "", "name_ko": "", "kind": "unresolved_error"}


def resolve_effective_scope(p: Any, requested_scope: str = "", tenant_id: str = "",
                            entity_mode: str = "") -> EffectiveScope:
    """요청 범위를 인증 주체의 범위 안에서 교차 검증한다.

    - 무제한 주체(조직 미도입) → 요청을 그대로 통과(하위호환 계약)
    - 요청 없음 → 필터 없음(종전 동작). 주체의 범위로 **자동 축소하지 않는다** — 조용한
      동작 변경은 "왜 결과가 줄었는지" 아무도 모르게 만든다. 축소가 필요하면 호출부가 명시한다.
    - 요청 있음 → 주체의 가시 범위에 속할 때만 허용, 아니면 `denied`

    ★ [D-018 ③④] `tenant_id`·`entity_mode` 는 **요청 값 해석에만** 쓰인다(코드는 그 문맥에서만
      유일하다). 주체의 범위 계산에는 넣지 않는다 — 주체가 볼 수 있는 조직은 그 사람의 소속이
      정하는 것이고, 요청 문맥이 그것을 넓히면 «문맥을 바꿔 권한을 얻는» 경로가 생긴다.
    ★ 통과 시 `scope_code`·`scope_name`·`ref_kind` 를 함께 실어 보낸다 — 화면이 정본 해시를
      사람에게 보여줄 수 없고(③), `ref_kind != "ecm_node"` 는 그 저장분이 백필 대상임을 뜻한다(⑤).
    """
    actor = str(getattr(p, "user_id", "") or "")
    scope = getattr(p, "scope", None)
    unrestricted = bool(getattr(scope, "unrestricted", False)) if scope is not None else True

    if unrestricted:
        # ⚠️ 무제한 주체도 **정규화는 한다.** 통과시키는 것과 원본을 그대로 저장하는 것은 다르다 —
        #   관리자가 코드로 보낸 값이 그대로 저장되면 백필 대상이 계속 늘어난다.
        d = _describe(requested_scope, tenant_id, entity_mode) if requested_scope else {}
        return EffectiveScope(scope_node_id=(d.get("node_id") or requested_scope or ""),
                              actor=actor, allowed_scopes=["*"], reason="unrestricted",
                              scope_code=d.get("code", ""), scope_name=d.get("name_ko", ""),
                              ref_kind=d.get("kind", ""))
    if not requested_scope:
        return EffectiveScope(scope_node_id="", actor=actor,
                              allowed_scopes=_actor_scopes(p), reason="no_scope_requested")

    allowed = _actor_scopes(p)
    d = _describe(requested_scope, tenant_id, entity_mode)
    # 해석되지 않으면 원본으로 비교한다(D-005 하위호환 — 코드로 저장된 기존 행이 아직 있다).
    requested_node = d["node_id"] or requested_scope

    if requested_node in allowed:
        return EffectiveScope(scope_node_id=requested_node, actor=actor,
                              allowed_scopes=allowed, reason="verified",
                              scope_code=d["code"], scope_name=d["name_ko"],
                              ref_kind=d["kind"])
    return EffectiveScope(scope_node_id="", actor=actor, allowed_scopes=allowed,
                          denied=True, reason="requested_scope_not_in_actor_scopes",
                          ref_kind=d["kind"])
