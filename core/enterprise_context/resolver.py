"""ECM 범위 해석 — `docs/design_enterprise_context_master.md` §6.1 / E1.

## 무엇을 해석하는가

① **범위 전개** — 어떤 노드를 선택했을 때 그 아래 어디까지가 포함되는가.
② **권한 가시성** — 요청자가 트리에서 무엇을 볼 수 있는가.
③ **문맥 해석** — `enterprise_scope_id` 가 부서 id 든 ECM `node_id` 든 같은 방식으로 다룬다
   (ECM-lite → E1 이행 경로. 기존 데이터를 마이그레이션 없이 살린다).

⚠️ **프로필 상속 병합은 여기 없다 — E2 다**(설계서 §11). E1 은 범위와 가시성까지다.

## 권한을 왜 `OPERATING_PARENT` 로만 상속하는가 (§6.1)

"상위 범위의 권한은 하위 **운영** 노드에 상속된다. 공유 서비스·연결 집계 관계는 자동
전체열람 권한을 만들지 않는다." 전사 재무조직이 여러 사업부를 **집계**할 수 있는 것과, 각
사업부의 운영 원천 데이터를 **열람**할 수 있는 것은 다른 문제다. 뭉개면 §13 위험표의
"전사 권한이 모든 상세 데이터 권한으로 비화"가 실현된다.

## 부서 권한을 재사용하는 이유 (§10.1)

E1 은 `scope_assignments` 를 새로 만들지 않고 기존 `org_directory` 의 부서 권한을 쓴다.
노드가 `dept_id` 로 부서에 매핑되어 있으면 그 부서 권한이 곧 그 노드의 권한이다. ECM 전용
권한 테이블 도입은 **E2(프로필 기반 생성·권한 강제)** 의 몫이며, 지금 새 권한 축을 만들면
Phase 1~5 에서 검증된 부서 권한과 두 갈래가 되어 어긋난다.
"""
from typing import Any, Dict, List, Optional, Set

from core.enterprise_context.models import (INHERITABLE_RELATIONS, REL_OPERATING_PARENT,
                                            STATUS_ACTIVE, OrganizationNode, ScopeNode)
from core.enterprise_context.repository import EcmRepository, ecm_repository

# 재귀 방어 상한. 저장소가 사이클을 막지만(`add_edge._reaches`), 조회 전용 경로가 손상된
# 데이터를 만나도 서버가 멈추지 않아야 한다.
_MAX_DEPTH = 32


class EcmResolver:
    def __init__(self, repo: EcmRepository = None):
        self.repo = repo or ecm_repository

    # ── ① 범위 전개 ───────────────────────────────────────────────────────
    def descendants(self, node_id: str, relation_type: str = REL_OPERATING_PARENT,
                    include_self: bool = True) -> List[str]:
        """`relation_type` 을 따라 내려간 모든 하위 노드 id."""
        out: List[str] = [node_id] if include_self else []
        seen: Set[str] = {node_id}
        frontier, depth = [node_id], 0
        while frontier and depth < _MAX_DEPTH:
            nxt = []
            for nid in frontier:
                for child in self.repo.children(nid, relation_type):
                    if child in seen:
                        continue
                    seen.add(child)
                    out.append(child)
                    nxt.append(child)
            frontier, depth = nxt, depth + 1
        return out

    def ancestors(self, node_id: str, relation_type: str = REL_OPERATING_PARENT) -> List[str]:
        """상위 체인(가까운 것부터). 프로필 상속 체인(E2)의 입력이 된다."""
        out: List[str] = []
        seen: Set[str] = {node_id}
        frontier, depth = [node_id], 0
        while frontier and depth < _MAX_DEPTH:
            nxt = []
            for nid in frontier:
                for parent in self.repo.parents(nid, relation_type):
                    if parent in seen:
                        continue
                    seen.add(parent)
                    out.append(parent)
                    nxt.append(parent)
            frontier, depth = nxt, depth + 1
        return out

    def consolidation_scope(self, node_id: str) -> List[str]:
        """연결 집계 범위 — **권한과 무관하다**(§6.1). 집계 대상 목록일 뿐이다.
        이 결과를 권한 판정에 쓰면 전사 조직이 모든 상세 데이터를 보게 된다."""
        return self.descendants(node_id, "CONSOLIDATION_SCOPE", include_self=False)

    def shared_service_consumers(self, node_id: str) -> List[str]:
        """이 공유서비스 조직이 서비스하는 대상. 역시 권한을 만들지 않는다."""
        return self.repo.children(node_id, "SHARED_SERVICE")

    # ── ② 권한 가시성 ─────────────────────────────────────────────────────
    def readable_node_ids(self, principal, tenant_id: str = "",
                          entity_mode: str = "REAL") -> Optional[Set[str]]:
        """요청자가 **데이터를 열람할 수 있는** 노드 집합. `None` = 무제한(필터하지 말라).

        판정 규칙:
          · 노드가 부서에 매핑돼 있으면(`dept_id`) 그 부서 읽기 권한을 따른다.
          · 매핑이 없는 노드(기업집단·법인 등)는 **그 자체로는 열람 권한을 주지 않는다** —
            대신 상속(`OPERATING_PARENT`)으로 하위의 매핑된 부서 권한이 위로 전달되지 않는다.
            열람은 항상 '부서에 매핑된 노드'에서 판정한다(fail-closed).
          · 트리 **표시**는 별개다(`visible_tree` 참조) — 경로가 끊기면 트리를 그릴 수 없으므로
            읽을 수 있는 노드의 조상은 '경로용'으로만 보여준다.
        """
        if getattr(principal.scope, "unrestricted", False):
            return None
        readable_depts = set(principal.scope.readable_dept_ids or ())
        out: Set[str] = set()
        for n in self.repo.list_nodes(tenant_id=tenant_id, status=STATUS_ACTIVE,
                                      entity_mode=entity_mode):
            if n.dept_id and n.dept_id in readable_depts:
                # 상위 부서 권한은 하위 운영 노드로 상속된다(§6.1) — 부서 자체의 상속은
                # `org_directory.resolve_scope` 가 이미 계산해 `readable_dept_ids` 에 담아 준다.
                out.update(self.descendants(n.node_id, REL_OPERATING_PARENT))
        return out

    def can_read_node(self, principal, node_id: str) -> bool:
        ids = self.readable_node_ids(principal)
        return True if ids is None else node_id in ids

    # ── 트리 ──────────────────────────────────────────────────────────────
    def visible_tree(self, principal, tenant_id: str = "",
                     entity_mode: str = "REAL") -> List[ScopeNode]:
        """화면용 기본 트리(§3.2). `default_parent_id` 로 만든다 — 엣지 그래프는 의미 관계이고
        트리는 보기용이라는 설계서 구분을 그대로 따른다.

        ⚠️ 읽을 수 있는 노드의 **조상은 경로 표시용으로만** 포함한다(`readable=False` 로 표시).
          조상을 빼면 트리가 조각나 사용자가 자기 조직의 위치를 알 수 없고, 조상을 열람 가능으로
          표시하면 권한이 부풀려진다. 둘을 구분해서 담는다."""
        nodes = self.repo.list_nodes(tenant_id=tenant_id, status=STATUS_ACTIVE,
                                     entity_mode=entity_mode)
        by_id = {n.node_id: n for n in nodes}
        readable = self.readable_node_ids(principal, tenant_id, entity_mode)

        if readable is None:
            keep = set(by_id)
            path_only: Set[str] = set()
        else:
            keep = set(readable) & set(by_id)
            path_only = set()
            for nid in list(keep):                      # 조상을 경로용으로 끌어올린다
                cur, depth = by_id.get(nid), 0
                while cur and cur.default_parent_id and depth < _MAX_DEPTH:
                    p = cur.default_parent_id
                    if p in keep or p in path_only:
                        break
                    if p in by_id:
                        path_only.add(p)
                    cur, depth = by_id.get(p), depth + 1

        shown = keep | path_only
        made: Dict[str, ScopeNode] = {}
        for nid in shown:
            n = by_id[nid]
            sn = ScopeNode(node_id=n.node_id, node_type=n.node_type, name_ko=n.name_ko,
                           code=n.code, dept_id=n.dept_id, entity_id=n.entity_id,
                           entity_mode=entity_mode, default_parent_id=n.default_parent_id)
            # 권한 없이 경로 표시만 하는 노드임을 명시한다(화면이 흐리게 그릴 수 있어야 한다).
            sn.__dict__["readable"] = nid in keep
            made[nid] = sn

        roots: List[ScopeNode] = []
        for nid, sn in made.items():
            parent = made.get(sn.default_parent_id)
            if parent is not None:
                parent.children.append(sn)
            else:
                roots.append(sn)

        def _depth(sn: ScopeNode, d: int = 0):
            sn.depth = d
            sn.children.sort(key=lambda x: (x.node_type, x.name_ko))
            for ch in sn.children:
                _depth(ch, d + 1)

        roots.sort(key=lambda x: (x.node_type, x.name_ko))
        for r in roots:
            _depth(r)
        return roots

    # ── ③ 문맥 해석 (ECM-lite → E1 이행) ──────────────────────────────────
    def resolve_scope_ref(self, scope_ref: str) -> Dict[str, Any]:
        """`enterprise_scope_id` 하나를 해석한다. **node_id · 조직 코드 · 부서 id 를 모두 받는다.**

        ECM-lite 단계에서 이 필드에 부서 id 를 담아 저장한 데이터가 이미 있다. E1 이 왔다고
        그것을 깨면 기존 상담·Blueprint·프로젝트의 범위가 전부 무효가 된다. 그래서 둘 다
        해석하고, 어느 쪽으로 해석됐는지(`kind`)를 함께 돌려준다 — 나중에 무엇을 승격해야
        하는지 알 수 있어야 한다(`context.EnterpriseContext.scope_kind` 와 같은 취지)."""
        if not scope_ref:
            return {"kind": "", "node_id": "", "dept_id": "", "name_ko": "", "resolved": False}
        node = self.repo.get_node(scope_ref)
        if node:
            return {"kind": "ecm_node", "node_id": node.node_id, "dept_id": node.dept_id,
                    "code": node.code, "name_ko": node.name_ko,
                    "node_type": node.node_type, "resolved": True}
        # ★ [2026-07-30] **조직 코드**도 해석한다. `organization_nodes.code` 에 의미 코드가
        #   들어 있는데(LS_MNM·MNM_BATTERY) 여기서 보지 않아 제3의 미해석 형태로 남아 있었다.
        #   해석되지 않으면 조상 해석이 실패해 자기 범위만 보게 되고(fail-closed), 사업부가
        #   전사 표준을 못 보는 상태가 **조용히** 만들어진다(실측: 참고문서 68건).
        #   dept_id 보다 **먼저** 본다 — 같은 dept_id 를 여러 노드가 공유하므로(실측: 4개 노드가
        #   `production`) 코드가 더 정확한 근거다.
        by_code = self.repo.find_node_by_code(scope_ref)
        if by_code:
            return {"kind": "ecm_code", "node_id": by_code.node_id,
                    "dept_id": by_code.dept_id, "code": by_code.code,
                    "name_ko": by_code.name_ko, "node_type": by_code.node_type,
                    "resolved": True}
        # ★ [2026-07-30] 부서 id 는 **여러 노드에 매달릴 수 있다.** 하나를 고르면 안 된다 —
        #   실측에서 `production` 하나에 형제 사업부 2개(배터리·동제련)와 공장 2개가 매달려
        #   있었고 `updated_at` 이 전부 같아 `LIMIT 1` 의 승자가 비결정적이었다. 그 상태로 한
        #   노드를 고르면 **tie-break 가 조직 권한을 결정한다** — 배터리 사용자가 동제련 문맥으로
        #   해석되거나 그 반대가 되고, 아무 오류도 나지 않는다.
        candidates = self.repo.find_nodes_by_dept(scope_ref)
        if len(candidates) > 1:
            print(f"⚠️ [ECM] 부서 '{scope_ref}' 가 노드 {len(candidates)}개에 매핑돼 있어 "
                  f"조직을 특정할 수 없습니다({', '.join(c.code for c in candidates)}) — "
                  f"부서 체계로만 해석합니다(상속 없음). 노드 매핑을 1:1 로 정리하십시오.")
            return {"kind": "department_ambiguous", "node_id": "", "dept_id": scope_ref,
                    "code": "", "name_ko": scope_ref, "resolved": False,
                    "candidates": [{"node_id": c.node_id, "code": c.code,
                                    "name_ko": c.name_ko, "node_type": c.node_type}
                                   for c in candidates]}
        mapped = candidates[0] if candidates else None
        if mapped:
            # 부서 id 인데 ECM 노드가 **하나** 매핑돼 있다 → 노드로 승격 가능한 상태
            return {"kind": "department_mapped", "node_id": mapped.node_id, "dept_id": scope_ref,
                    "code": mapped.code, "name_ko": mapped.name_ko,
                    "node_type": mapped.node_type, "resolved": True}
        # ECM 에 아직 없는 부서 — 기존 부서 체계로 계속 동작한다(하위호환)
        return {"kind": "department", "node_id": "", "dept_id": scope_ref,
                "name_ko": scope_ref, "resolved": False}


ecm_resolver = EcmResolver()
