"""★★★ [P0-A/B] **테스트 전용 조직·사용자·역할 시드.**

## 왜 이 파일이 생겼나 (2026-08-15 실측)

깨끗한 checkout 에서 전체 회귀가 **255건 실패**했다. 코드 결함이 아니라 **하니스가 Git 에
없는 운영 데이터에 기대고 있었기 때문**이다:

| | 내 작업트리 | 깨끗한 checkout |
|---|---:|---:|
| 사용자 | 22명 | **0명** |
| 부서 | 12개 | **0개** |

`org_directory.is_bootstrap()` 은 「부서 0 또는 사용자 0」이면 **전원 무제한**을 돌려준다
(그것 자체는 옳다 — 조직을 세우기도 전에 잠기면 첫 관리자를 만들 수 없다). 그래서 깨끗한
환경에서는 **모든 권한 경계 시험이 아무것도 검증하지 못한 채 통과하거나 뒤집힌다.**

⚠️⚠️ 그래서 「3,488 passed」는 **코드만으로 재현되는 증거가 아니었다.** 같은 커밋이 폴더에
따라 다른 답을 냈고, 그 차이를 아무도 보지 못했다.

## 이 파일이 정하는 것

1. **테스트 신원은 합성이다.** `hikwon_17@lsmnm.com` 같은 **실제 인물 계정을 쓰지 않는다** —
   운영 조직도가 바뀌면 시험이 조용히 다른 것을 검증하게 되고, 실존 인물의 권한을 시험
   기대값으로 못박게 된다.
2. **기대 권한을 데이터와 같은 자리에 선언한다.** 「이 사람이 viewer 다」를 시험 파일마다
   주석으로 적으면 조직도가 바뀔 때 아무도 못 찾는다.
3. **강제 상태를 명시한다.** `org_enforce` 를 정하지 않으면 코드 기본값 `False` 로 떨어지고,
   그때 경계 시험은 **전부 무제한 모드에서 통과**한다(=아무것도 시험하지 않는다).

LLM 0콜.
"""
from __future__ import annotations

from typing import Any, Dict

#: ★ 합성 도메인. ⚠️ `.invalid` 는 예약 TLD 라 실제로 배달되지 않는다 — 시험 계정이
#:   실존 계정과 섞일 수 없게 하는 가장 싼 방법이다.
DOMAIN = "test.invalid"

#: 부서 — 상위 하나에 하위 둘. **상속을 시험할 수 있는 최소 모양**이다.
#: ⚠️ id 는 소문자다 — 제품 규칙이 `^[a-z0-9_-]{2,32}$` 다.
DEPT_ROOT = "t_root"
DEPT_A = "t_alpha"
DEPT_B = "t_beta"

DEPARTMENTS = (
    #: (dept_id, 이름, 상위)
    (DEPT_ROOT, "시험 본사", ""),
    (DEPT_A, "시험 알파사업부", DEPT_ROOT),
    (DEPT_B, "시험 베타사업부", DEPT_ROOT),
)

#: ★★★ **사용자와 기대 권한을 한 곳에 선언한다.**
#:   시험은 여기 적힌 이름으로만 신원을 만든다 — 「누가 무엇을 할 수 있는가」의 정본이
#:   시험 파일 주석이 아니라 이 표다.
ADMIN = f"t_admin@{DOMAIN}"          # 전권 관리자
EXEC = f"t_exec@{DOMAIN}"            # 임원 — 전사 열람
DATA_ADMIN = f"t_dataadmin@{DOMAIN}"  # 기준정보 관리자
AI_ADMIN = f"t_aiadmin@{DOMAIN}"     # 에이전트 자산 관리자
MANAGER_ROOT = f"t_manager_root@{DOMAIN}"  # 본사 manager — **상위 전체** 쓰기(관리자 플래그 없음)
MANAGER_A = f"t_manager_a@{DOMAIN}"  # 알파 관리자 — 알파 쓰기
MEMBER_A = f"t_member_a@{DOMAIN}"    # 알파 구성원 — 알파 쓰기
VIEWER_A = f"t_viewer_a@{DOMAIN}"    # 알파 열람자 — **쓰기 없음**
MEMBER_B = f"t_member_b@{DOMAIN}"    # 베타 구성원 — 알파를 볼 수 없다
NO_DEPT = f"t_nodept@{DOMAIN}"       # 부서 미배정 — 아무것도 볼 수 없다
UNKNOWN = f"t_unknown@{DOMAIN}"      # ⚠️ **등록하지 않는다**(미등록 사용자 시험용)

#: ★ **가상 조직**(시나리오·복제) 코드. 실제 조직과 같은 이름이 **다른 실행 모드**에
#:   존재할 수 있다는 사실을 시험한다 — 그 둘을 섞으면 시나리오 수치가 실적으로 읽힌다.
VIRTUAL_CODE_B = "v_t_beta"

#: 부서 → ECM 노드 id. `seed_ecm()` 이 채운다.
#: ★ 시험이 «정본 범위 id» 를 필요로 할 때 여기서 가져간다 — 운영 ECM 을 뒤지지 않는다.
NODES: Dict[str, str] = {}

USERS: Dict[str, Dict[str, Any]] = {
    ADMIN:      {"name": "시험 관리자", "dept": DEPT_ROOT, "is_admin": True,
                 "roles": {DEPT_ROOT: "manager"}},
    EXEC:       {"name": "시험 임원", "dept": DEPT_ROOT, "is_executive": True,
                 "roles": {DEPT_ROOT: "viewer"}},
    DATA_ADMIN: {"name": "시험 기준정보관리자", "dept": DEPT_ROOT, "is_data_admin": True,
                 "roles": {DEPT_ROOT: "manager"}},
    AI_ADMIN:   {"name": "시험 AI관리자", "dept": DEPT_ROOT, "is_ai_admin": True,
                 "roles": {DEPT_ROOT: "manager"}},
    #: ★ 「부서 manager 인데 시스템 관리자는 아니다」 — 관리 범위가 조직 트리로만 정해지는
    #:   가장 흔한 자리다. 이 자리가 없으면 «관리 범위» 와 «관리자 플래그» 가 구분되지 않는다.
    MANAGER_ROOT: {"name": "시험 본사관리자", "dept": DEPT_ROOT, "roles": {DEPT_ROOT: "manager"}},
    MANAGER_A:  {"name": "시험 알파관리자", "dept": DEPT_A, "roles": {DEPT_A: "manager"}},
    MEMBER_A:   {"name": "시험 알파구성원", "dept": DEPT_A, "roles": {DEPT_A: "member"}},
    VIEWER_A:   {"name": "시험 알파열람자", "dept": DEPT_A, "roles": {DEPT_A: "viewer"}},
    MEMBER_B:   {"name": "시험 베타구성원", "dept": DEPT_B, "roles": {DEPT_B: "member"}},
    #: ⚠️ 부서도 역할도 없다. 「식별은 되지만 볼 것이 없는」 상태를 시험한다 —
    #:   그 상태를 «전사 공용» 으로 읽으면 D-014 위반이다.
    NO_DEPT:    {"name": "시험 미배정", "dept": "", "roles": {}},
}


def seed_ecm(repo, directory) -> Dict[str, str]:
    """★★★ 시험 조직도에 대응하는 **ECM 노드**를 심고 부서에 연결한다.

    ⚠️ 이것이 없으면 부서의 `scope_node_id` 가 비어 자원이 «미바인딩» 이 되고, D-014 에 따라
      **모든 쓰기가 막힌다.** 그러면 시험은 「권한이 없어서 막혔다」와 「범위가 없어서 막혔다」를
      구분하지 못한 채 빨강이 된다 — 두 사실은 고치는 방법이 다르다.

    ★ 운영 ECM 에서 복사하지 않는다(`ecm_org_seed` 는 그렇게 한다). 시험 조직은 **자기
      노드**를 갖는다 — 운영 조직도가 바뀌어도 시험이 흔들리지 않는다."""
    from core.enterprise_context.models import (REL_OPERATING_PARENT, STATUS_ACTIVE,
                                                EnterpriseEntity, OrganizationEdge,
                                                OrganizationNode)
    #: ⚠️ conftest 는 **경로만** tmp 로 바꾼다(스키마는 만들지 않는다). 읽기를 한 번 해서
    #:   DDL 을 돌리지 않으면 첫 쓰기가 «no such table» 로 죽는다.
    repo.list_nodes()
    ent = repo.upsert_entity(EnterpriseEntity(
        entity_id="t_entity", tenant_id="tenant_default", entity_mode="REAL",
        legal_name="시험 법인", name_ko="시험 법인", status=STATUS_ACTIVE))
    out: Dict[str, str] = {}
    for dept_id, name, parent in DEPARTMENTS:
        node = repo.upsert_node(OrganizationNode(
            node_id=f"node_{dept_id}", entity_id=ent.entity_id, tenant_id="tenant_default",
            #: ★ 코드를 부서 id 와 **같게** 둔다 — 운영이 그렇다(LS_MNM 부서 = LS_MNM 노드).
            #:   어긋나면 «부서로 매핑됨» 과 «ECM 코드» 가 갈려 정규화 시험이 뒤집힌다.
            node_type="business_division", code=dept_id, name_ko=name,
            default_parent_id=(f"node_{parent}" if parent else ""),
            dept_id=dept_id, status=STATUS_ACTIVE))
        out[dept_id] = node.node_id
        directory.update_department(dept_id, scope_node_id=node.node_id, actor="test-seed")

    #: ★ 가상 조직 하나 — 같은 조직의 **VIRTUAL** 판이다.
    #: ⚠️ 실제/가상을 구분하지 못하면 시나리오 값이 실적 자리에 들어간다(BDR §데이터 역할).
    v_ent = repo.upsert_entity(EnterpriseEntity(
        entity_id="t_entity_v", tenant_id="tenant_default", entity_mode="VIRTUAL",
        legal_name="시험 법인(가상)", name_ko="시험 법인(가상)",
        base_entity_id=ent.entity_id, status=STATUS_ACTIVE))
    v_node = repo.upsert_node(OrganizationNode(
        node_id="node_t_beta_v", entity_id=v_ent.entity_id, tenant_id="tenant_default",
        node_type="business_division", code=VIRTUAL_CODE_B, name_ko="시험 베타(가상)",
        dept_id="", status=STATUS_ACTIVE))
    out[VIRTUAL_CODE_B] = v_node.node_id

    #: ★★★ **조상 해석은 엣지가 한다.** `default_parent_id` 는 화면 기본 트리일 뿐이다
    #:   (ECM 설계 §3.1 — 「진짜 관계는 엣지에 있다」).
    #: ⚠️ 엣지를 빼면 상위 상속이 끊겨 «사업부가 전사 표준을 못 본다» 가 되고, 그 실패는
    #:   「통제가 잘 동작한다」로 오독된다 — 실제로 그렇게 보였다.
    for dept_id, _name, parent in DEPARTMENTS:
        if not parent:
            continue
        repo.add_edge(OrganizationEdge(
            edge_id=f"edge_{parent}_{dept_id}", tenant_id="tenant_default",
            from_node_id=out[parent], to_node_id=out[dept_id],
            relation_type=REL_OPERATING_PARENT, status=STATUS_ACTIVE))
    directory._invalidate()
    NODES.clear()
    NODES.update(out)
    return out


def seed(directory) -> Dict[str, Any]:
    """조직도를 심는다. **격리된 저장소에만** 부른다.

    ⚠️ 운영 저장소에 대고 부르면 실제 조직도에 시험 계정이 들어간다. 호출 전에
      `org_directory.db_path` 가 `tmp_path` 인지 확인하는 것은 호출자(conftest) 책임이다."""
    for dept_id, name, parent in DEPARTMENTS:
        if not directory.get_department(dept_id):
            directory.create_department(dept_id, name, parent_id=parent, actor="test-seed")
    for uid, spec in USERS.items():
        directory.upsert_user(
            uid, spec["name"], primary_dept_id=spec.get("dept", ""),
            is_executive=bool(spec.get("is_executive")), is_admin=bool(spec.get("is_admin")),
            is_data_admin=bool(spec.get("is_data_admin")),
            is_ai_admin=bool(spec.get("is_ai_admin")), actor="test-seed")
        directory.set_user_roles(uid, spec.get("roles") or {}, actor="test-seed")
    return {"departments": [d[0] for d in DEPARTMENTS], "users": list(USERS)}
