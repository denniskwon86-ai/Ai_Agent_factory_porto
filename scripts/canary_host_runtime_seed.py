"""★★★ [G1-B 4] **격리 카나리 — 씨앗.** 이 스크립트는 «자기가 속한 저장소» 에만 쓴다.

## 왜 워크트리에서 도는가

`core/paths.py` 는 데이터 뿌리를 **`__file__` 기준**으로 잡는다(「작업 공간마다 자기 데이터를
갖는다」). 그래서 이 파일이 워크트리 사본 안에 있으면, 여기서 만드는 모든 DB 는 **그 사본의
`data/`** 에 생긴다 — 운영 `data/` 는 규율이 아니라 **구조로** 닿지 않는다.

⚠️⚠️ 그러므로 **운영 저장소에서 실행하지 말 것.** 아래에서 그것을 직접 막는다.

## 무엇을 심는가

    부서 hq · 사용자 둘(주체·타인) · ECM 노드 node_hq(=hq)
    릴리스 셋 — 정상 / 읽기전용 선언 / 다른 앱
    소유(ownership) 미러 · 조직 강제 정책 on
    세션 둘(주체·타인) — 로그인 화면을 거치지 않고 서버가 직접 발급한다

★ 세션을 서버가 직접 만드는 이유: 카나리는 **데이터 평면 통제**를 보는 것이지 로그인
  화면을 보는 것이 아니다. 그리고 사람이 비밀번호를 입력하는 절차를 자동화에 끼워 넣지
  않는다.

LLM 0콜.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.paths import PROJECT_ROOT, data_path  # noqa: E402

#: ⚠️⚠️ 안전장치. 운영 저장소에서 돌면 **아무것도 하지 않고 멈춘다.**
if os.path.basename(PROJECT_ROOT) != "canary_wt":
    raise SystemExit(
        f"이 스크립트는 격리 워크트리(canary_wt)에서만 돕니다. 지금 뿌리: {PROJECT_ROOT}\n"
        f"운영 저장소에 카나리 데이터를 심으면 그 순간 «관측 표본» 이 오염됩니다.")

TENANT = "tenant_default"
MODE = "REAL"
DEPT = "hq"
NODE = "node_hq"
ME = "canary@lsmnm.com"
OTHER = "canary_other@lsmnm.com"

RELEASES = {
    #: 읽기·쓰기·삭제를 선언한 앱 — 여섯 작업을 전부 눌러 볼 대상
    "rel_canary": ["orders.read", "orders.create", "orders.delete"],
    #: 읽기만 선언 — 「선언 밖은 못 한다」
    "rel_canary_ro": ["orders.read"],
    #: ★★★ 같은 사용자가 볼 수 있는 **다른 앱** — 공격자 역할.
    #: ⚠️ [교차검토 87] 읽기만 주면 쓰기 주입이 403 인 것이 «귀속 격리» 가 아니라 **단순
    #:   권한 거부**다. 그것으로는 아무것도 증명하지 못한다. B 에도 쓰기·삭제를 준다 —
    #:   「할 수 있는데도 남의 것에는 못 닿는다」여야 격리다.
    "rel_canary_other": ["orders.read", "orders.create", "orders.delete"],
}


def _release(rid, caps, project):
    d = os.path.join(PROJECT_ROOT, "library", rid)
    os.makedirs(d, exist_ok=True)
    doc = {
        "release_id": rid, "project_id": project, "project_name": rid,
        "tenant_id": TENANT, "entity_mode": MODE, "enterprise_scope_id": NODE,
        "owner_user_id": "", "owner_dept_id": DEPT, "visibility": "dept",
        "frontend_code_summary": "",
        "manifest": {"fingerprint": f"fp_{rid}", "valid": True, "manifest": {
            "version": "1.0", "app_class": "departmental", "auth_mode": "host_inherited",
            "capabilities": caps, "required_capabilities": [],
            "host_auth_required": True, "standalone_auth": False}},
    }
    with open(os.path.join(d, "release.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    return doc


def main():
    from core.auth import auth_store
    from core.enterprise_context.models import STATUS_ACTIVE, EnterpriseEntity, OrganizationNode
    from core.enterprise_context.repository import ecm_repository
    from core.org_directory import org_directory
    from core import scope_policy

    os.makedirs(data_path(), exist_ok=True)

    # ── 조직 ──────────────────────────────────────────────────────────────
    #: 다시 돌려도 되게 둔다 — 카나리는 여러 번 세운다.
    #: ★★★ 부서를 **ECM 노드에 매어 둔다**(D-018). 이것이 없으면 `readable_scope_nodes` 가
    #:   비고, 조직 범위 판정이 전부 거부로 떨어진다 — 카나리가 「통제가 동작한다」와
    #:   「환경이 덜 세워졌다」를 구분하지 못하게 된다(실제로 첫 실행에서 그렇게 막혔다).
    if not org_directory.get_department(DEPT):
        org_directory.create_department(DEPT, "본사", scope_node_id=NODE, actor="canary")
    else:
        org_directory.update_department(DEPT, scope_node_id=NODE, actor="canary")
    org_directory.upsert_user(ME, "카나리 주체", primary_dept_id=DEPT, actor="canary")
    org_directory.upsert_user(OTHER, "카나리 타인", primary_dept_id=DEPT, actor="canary")
    #: ★ 소속만으로는 **읽기만** 된다(`_writable_from_roles`: viewer 는 읽기만). 카나리는
    #:   쓰기·삭제 표본도 만들어야 하므로 역할을 준다 — 「환경이 덜 세워져서 막힌 것」과
    #:   「통제가 막은 것」을 구분하기 위해서다.
    org_directory.set_user_roles(ME, {DEPT: "member"}, actor="canary")
    org_directory.set_user_roles(OTHER, {DEPT: "member"}, actor="canary")

    # ── ECM 노드 ──────────────────────────────────────────────────────────
    #: ★ 조직 범위 판정(`_scope_covers`)이 이 노드를 찾지 못하면 **모든 요청이 거부**된다.
    ent = ecm_repository.upsert_entity(EnterpriseEntity(
        entity_id="ent_canary", tenant_id=TENANT, name_ko="카나리 법인",
        entity_kind="legal_entity", status=STATUS_ACTIVE))
    ecm_repository.upsert_node(OrganizationNode(
        node_id=NODE, entity_id=ent.entity_id, tenant_id=TENANT,
        node_type="business_division", code="HQ", name_ko="본사",
        dept_id=DEPT, status=STATUS_ACTIVE))

    # ── 릴리스 · 소유 미러 ────────────────────────────────────────────────
    for rid, caps in RELEASES.items():
        _release(rid, caps, "proj_other" if rid == "rel_canary_other" else "proj_canary")
        org_directory.set_ownership("release", rid, dept_id=DEPT, visibility="dept")

    # ── 조직 강제 ─────────────────────────────────────────────────────────
    #: ⚠️ 이것을 켜지 않으면 부트스트랩 무제한이 되어 **카나리가 아무것도 증명하지 못한다.**
    scope_policy.set_org_enforce(True, actor="canary", reason="격리 카나리")

    # ── 세션 ──────────────────────────────────────────────────────────────
    s_me = auth_store.create_session(ME)
    #: ★ 같은 사람의 **두 번째 세션** — 「다른 세션에서 재사용」 시나리오를 만든다.
    s_me2 = auth_store.create_session(ME)
    s_other = auth_store.create_session(OTHER)

    out = {
        "root": PROJECT_ROOT, "tenant": TENANT, "mode": MODE, "scope": NODE,
        "me": ME, "other": OTHER,
        "session_me": s_me["token"], "session_me_2": s_me2["token"],
        "session_other": s_other["token"],
        "releases": list(RELEASES),
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
