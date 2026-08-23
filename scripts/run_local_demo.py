# -*- coding: utf-8 -*-
"""★★★ [M0] **로컬 시연 서버** — 12분 여정을 이 기계에서 처음부터 걸을 수 있게 한다.

## 왜 필요한가

운영 `data/` 에는 키트 인스턴스도, 인증판도, 온톨로지 관계도 **0건**이다. 그래서 지금
이 저장소를 그대로 띄우면 시연을 시작할 수 없다 — 화면은 뜨지만 고를 것이 없다.

## ⚠️⚠️ 운영 `data/` 에 심지 않는다

이 저장소의 규칙이다(`scripts/pilot_demo_seed.py` 머리말): **시연 데이터를 운영
저장소에 심으면 그 순간 「실제 데이터」와 구분되지 않는다.**

★ 그래서 별도 뿌리(`demo_data/`)에 심고, 앱의 저장소 경로를 그쪽으로 돌려 띄운다.
  운영 `data/` 는 열지도 않는다 — 아래에서 직접 막는다.

## 무엇을 심는가

    조직        본사 → 제련공장(상위→하위 상속을 볼 수 있게)
    사용자      hikwon@lsmnm.com(시스템 관리자) · runner@afs.invalid(실행자)
    키트        KIT-MFG-NONFERROUS-PROCUREMENT 1.0.0 — **정본 파일**에서 읽는다
    인증판      필수 7종
    온톨로지    계약 + 관계 3건(제안→상신→승인, **실제 원장 사건**으로)
    기준선      배분·인식규칙·기준 인식일 봉인

## ⚠️ 심지 **않는** 것 — 계산 능력 실행 승인

사람이 화면에서 눌러야 한다(사용자 결정 2026-08-22). 그래서 이 스크립트가 심으면
「승인 화면이 실제로 도는가」를 확인할 수 없다 — 처음부터 승인된 상태로 시작하면
그 화면은 한 번도 안 눌린 채 시연이 끝난다.

사용:
    venv/Scripts/python.exe scripts/run_local_demo.py            # 있으면 그대로, 없으면 심고 기동
    venv/Scripts/python.exe scripts/run_local_demo.py --reset    # 비우고 다시 심는다
    venv/Scripts/python.exe scripts/run_local_demo.py --seed-only
    venv/Scripts/python.exe scripts/run_local_demo.py --port 8080

LLM 호출: 0건.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

#: 시연 뿌리. ⚠️ 운영 `data/` 와 **다른 디렉터리**여야 한다.
DEMO_ROOT = os.path.join(ROOT, "demo_data")
OPERATIONAL = os.path.join(ROOT, "data")

USER_ADMIN = "hikwon@lsmnm.com"          # ★ 승인된 실측 계정 하나
#: ★ 제안자와 승인자는 달라야 한다(자기 승인 금지). 합성 원장 행위자를 쓴다.
USER_PROPOSER = "proposer@afs.invalid"
USER_RUNNER = "runner@afs.invalid"
DEPT_HQ, DEPT_PLANT = "hq", "smelting"

CHAIN = (("shipment", "SHP-001", "inventory-snapshot", "INV-001"),
         ("inventory-snapshot", "INV-001", "production-plan", "PLAN-001"),
         ("production-plan", "PLAN-001", "sales-order", "SO-001"))


def say(msg: str) -> None:
    print(f"\n\033[1;36m▸ {msg}\033[0m")


def _point_stores_at_demo() -> None:
    """모든 저장소를 시연 뿌리로 돌린다. **운영 `data/` 를 열지 않는다.**

    ⚠️ 싱글턴의 `db_path` 를 갈아끼운다 — 시험이 쓰는 것과 같은 격리 방식이다.
      `core/paths.py` 는 뿌리를 `__file__` 기준으로 잡으므로 환경변수로는 못 바꾼다."""
    if os.path.abspath(DEMO_ROOT) == os.path.abspath(OPERATIONAL):
        raise SystemExit("시연 뿌리가 운영 data/ 와 같습니다 — 멈춥니다.")
    os.makedirs(DEMO_ROOT, exist_ok=True)

    import core.app_preview as ap
    from core.collaboration_store import collaboration_store
    from core.data_preparation import store as dp
    from core.decision_ledger import decision_ledger
    from core.enterprise_context.scenario_inputs import scenario_inputs

    dp.data_preparation_store.db_path = os.path.join(DEMO_ROOT, "data_preparation.db")
    dp.data_preparation_store._prepared_for = None
    decision_ledger.db_path = os.path.join(DEMO_ROOT, "decision_ledger.db")
    collaboration_store.db_path = os.path.join(DEMO_ROOT, "collaboration.db")
    scenario_inputs._repo.db_path = os.path.join(DEMO_ROOT, "enterprise_context.db")
    ap.db_path = lambda audience: os.path.join(DEMO_ROOT, "app_data_preview.db")


def _org():
    """조직도 — **상위→하위 상속**을 볼 수 있게 두 단으로 세운다."""
    import api.deps as deps
    import core.org_directory as orgmod
    import core.scope_policy as sp
    from core.org_directory import OrgDirectory

    org = OrgDirectory(db_path=os.path.join(DEMO_ROOT, "org.db"))
    #: ⚠️ 강제가 꺼져 있으면 `resolve_scope` 가 전원 무제한을 돌려준다 — 그 상태에서는
    #:   권한 경계가 하나도 안 보이고, 시연이 「전부 되는 것」처럼 끝난다.
    sp._read = lambda: {"org_enforce": True}
    orgmod.org_directory = org
    deps.org_directory = org
    return org


def seed() -> str:
    from core import calc_baseline as cb
    from core import demo_vertical_slice as dv
    from core.data_preparation import models as m
    from core.data_preparation import snapshot_service as svc
    from core.data_preparation import store as dp
    from core.decision_ledger import decision_ledger

    store = dp.data_preparation_store
    sl = dv.build_slice(scope_node_id="plant-afs-smelting-01")
    tenant, scope = dv.scope_of(sl)

    #: ⚠️ 문맥의 테넌트는 `config.ECM_DEFAULT_TENANT_ID` 가 정한다. 정본 CSV 의 테넌트와
    #:   다르면 화면이 자기 인스턴스를 못 본다 — 정본 쪽에 맞춘다.
    import config as cfg
    cfg.ECM_DEFAULT_TENANT_ID = tenant

    say("① 조직·사용자")
    org = _org()
    for dept, name, parent, node in ((DEPT_HQ, "본사", "", "corp-afs"),
                                     (DEPT_PLANT, "제련공장", DEPT_HQ, scope)):
        try:
            org.create_department(dept, name, parent_id=parent, scope_node_id=node,
                                  actor="demo-seed")
        except Exception:
            org.update_department(dept, parent_id=parent, scope_node_id=node,
                                  actor="demo-seed")
    org.upsert_user(USER_ADMIN, "권희권", primary_dept_id=DEPT_HQ, is_admin=True,
                    is_data_admin=True, actor="demo-seed")
    org.set_user_roles(USER_ADMIN, {DEPT_HQ: "manager"}, actor="demo-seed")
    org.upsert_user(USER_RUNNER, "실행자 (예시)", primary_dept_id=DEPT_PLANT,
                    actor="demo-seed")
    org.set_user_roles(USER_RUNNER, {DEPT_PLANT: "member"}, actor="demo-seed")
    print(f"  ✓ {DEPT_HQ}(corp-afs) → {DEPT_PLANT}({scope}) · 사용자 2명")

    say("② 정본 키트와 인증판")
    dv.register_kit(store)
    inst = store.create_instance(
        kit_id=dv.KIT_ID, version=dv.KIT_VERSION,
        kit_fingerprint=dv.kit_fingerprint(store),
        tenant_id=tenant, scope_node_id=scope, entity_mode="REAL",
        label="첫 수직 시연 — 비철 제련")
    for key in dv.SLICE_KEYS:
        rows, cols = sl[key]
        b = store.create_binding(
            instance_id=inst["instance_id"], dataset_contract_key=key,
            provider=m.PROVIDER_FILE_SNAPSHOT, config={}, tenant_id=tenant,
            scope_node_id=scope, entity_mode="REAL")
        for target in (m.VALIDATED, m.APPROVED, m.ACTIVE):
            b = store.transition(b["binding_id"], target)
        snap = svc.ingest(store, binding=b, payload=dv.csv_bytes(rows, cols),
                          file_name=f"{key}.csv",
                          workspace_root=os.path.join(DEMO_ROOT, "raw"))
        svc.run_pipeline(store, snap["snapshot_id"], rows, cols,
                         control={"row_count": len(rows)})
    print(f"  ✓ {inst['instance_id']} · 인증판 {len(dv.SLICE_KEYS)}종")

    say("③ 온톨로지 계약과 관계 3건")
    _seed_ontology(tenant, scope, decision_ledger)

    say("④ 계산 기준선 봉인")
    a = dv.assumptions(sl)
    cb.seal(store, instance_id=inst["instance_id"], tenant_id=tenant,
            entity_mode="REAL", scope_node_id=scope, actor=USER_ADMIN,
            rationale="첫 수직 시연 기준선",
            sales_allocation=a["sales_allocation"],
            recognition_span_days=a["recognition_span_days"],
            baseline_recognition=a["baseline_recognition"])
    print("  ✓ 배분·인식규칙·기준 인식일")

    print("\n⚠️ **계산 능력 실행 승인은 심지 않았다.** 「계산 실행 승인 · 시연 초기화」")
    print("   화면에서 사람이 눌러야 한다 — 심어 두면 그 화면이 도는지 확인할 수 없다.")
    return inst["instance_id"]


def _seed_ontology(tenant: str, scope: str, decision_ledger) -> None:
    from core import app_policy, ontology_resolve
    from core import ontology_runtime as ortm
    from core import path_calculation as pc
    from core.ontology_resolvers import product_approval_resolver
    from core.ontology_runtime import ObjectRef, OntologyRuntime, RelationProposal
    import api.routes.calculation_control as cal
    import api.routes.ontology_control as onto
    import core.org_directory as orgmod

    def resolver(ref, rctx):
        return ontology_resolve.found(app_policy.ResourceScope(
            tenant_id=tenant, entity_mode="REAL", scope_node_id=scope,
            owner_dept_id=DEPT_PLANT, binding_state=app_policy.BOUND))

    rt = OntologyRuntime(os.path.join(DEMO_ROOT, "ontology.db"), resolver,
                         product_approval_resolver)
    contract = {
        "contract_id": "G2-FIRST-VERTICAL-ONTOLOGY", "contract_version": "1.0.0",
        "status": "APPROVED",
        "relation_types": [{"id": "AFFECTS", "name_ko": "영향을 줌",
                            "inverse": "AFFECTED_BY", "quantitative": True}],
        "constraints": [{"subject": f"dataset:{s}", "relation": "AFFECTS",
                         "object": f"dataset:{o}", "evidence": ["승인된 지연 모형"],
                         "calculation_ref": ref}
                        for (s, _si, o, _oi), ref in zip(CHAIN, pc.SEGMENTS)],
        #: 자리표시자로 지문을 얻고 **실제 원장 사건** id 로 바꿔 설치한다.
        "approval": {"approved_by": USER_ADMIN, "decision_ledger_id": "placeholder",
                     "effective_from": "2026-01-01T00:00:00Z"},
    }
    fp = rt.validate_model_contract(contract)["contract_fingerprint"]
    ev = decision_ledger.append(
        event_type="ONTOLOGY_MODEL_APPROVED", subject_type="ontology_model_contract",
        subject_id=fp, actor_type="user", actor_id=USER_ADMIN, decision="APPROVED",
        rationale="첫 수직 온톨로지 계약 승인", tenant_id=tenant, entity_mode="REAL")
    contract["approval"]["decision_ledger_id"] = ev["event_id"]
    rt.install_model_contract(contract, USER_ADMIN)

    subj = app_policy.Subject(
        user_id=USER_ADMIN, scope=orgmod.org_directory.resolve_scope(USER_ADMIN),
        ctx={"tenant_id": tenant, "entity_mode": "REAL", "scope_node_id": scope},
        session_id="demo-seed", blocked_reason="")
    for (s_t, s_i, o_t, o_i), ref in zip(CHAIN, pc.SEGMENTS):
        made = rt.propose_relation(RelationProposal(
            subject=ObjectRef("dataset", s_t, s_i), relation_type_id="AFFECTS",
            object=ObjectRef("dataset", o_t, o_i), tenant_id=tenant,
            enterprise_scope_id=scope, entity_mode="REAL",
            owner_organization_id=DEPT_PLANT, effective_from="2026-01-01T00:00:00Z",
            origin="derived", evidence_refs=("SNAPSHOT:LOG-02:v1",),
            calculation_ref=ref), USER_PROPOSER, subj)
        rid = made["relation_id"]
        rt.submit(rid, USER_PROPOSER, subj)
        rev = decision_ledger.append(
            event_type="ONTOLOGY_RELATION_APPROVED", subject_type="ontology_relation",
            subject_id=rid, actor_type="user", actor_id=USER_ADMIN, decision="APPROVED",
            rationale="첫 수직 경로 관계 승인", tenant_id=tenant, entity_mode="REAL")
        rt.approve(rid, USER_ADMIN, rev["event_id"], subj)

    #: 제품 전역 런타임을 이 시연 런타임으로 돌린다.
    cal.ontology_runtime = rt
    ortm.ontology_runtime = rt
    onto.router.routes[:] = onto.create_router(rt).routes
    print(f"  ✓ 계약 1건 · 관계 {len(CHAIN)}건(승인)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="시연 뿌리를 비우고 다시 심는다")
    ap.add_argument("--seed-only", action="store_true")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()

    if args.reset:
        shutil.rmtree(DEMO_ROOT, ignore_errors=True)
        print(f"시연 뿌리를 비웠습니다: {DEMO_ROOT}")

    _point_stores_at_demo()
    print(f"시연 데이터 뿌리: {DEMO_ROOT}")
    print(f"운영 data/ 는 열지 않습니다: {OPERATIONAL}")

    #: ⚠️ `list_instances` 는 **보이는 범위만** 돌려준다 — 범위를 안 주면 빈 목록이다.
    #:   그 빈 목록을 「아직 안 심었다」로 읽고 다시 심었더니 관계가 중복돼 기간
    #:   겹침으로 죽었다. 여기서는 「심었는가」만 물으므로 저장소를 직접 센다.
    from core.data_preparation import store as dp

    with dp.data_preparation_store.transaction() as conn:
        existing = [dict(r) for r in conn.execute(
            "SELECT instance_id, scope_node_id FROM kit_instances "
            "WHERE status='active' ORDER BY created_at")]
    if existing:
        #: ⚠️ 이미 있으면 **다시 심지 않는다.** 두 번 심으면 인스턴스가 둘이 되고,
        #:   화면에서 어느 것이 진짜인지 알 수 없다.
        _org()
        print(f"\n이미 심어져 있습니다(인스턴스 {len(existing)}개). 다시 심으려면 --reset")
        inst = existing[0]["instance_id"]
        #: 온톨로지 런타임만 시연 파일로 돌린다.
        _rewire_ontology_only()
    else:
        inst = seed()

    if args.seed_only:
        print(f"\n인스턴스: {inst}")
        return 0

    say("기동")
    print(f"  화면: http://127.0.0.1:5173  (프런트는 따로 띄우십시오)")
    print(f"  서버: http://127.0.0.1:{args.port}")
    print(f"  로그인: {USER_ADMIN} · 초기 비밀번호는 `core/auth.py` 의 공통값")
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=args.port, reload=False)
    return 0


def _rewire_ontology_only() -> None:
    """이미 심어진 경우 — 온톨로지 런타임만 시연 파일로 돌린다."""
    from core import app_policy, ontology_resolve
    from core import ontology_runtime as ortm
    from core.ontology_resolvers import product_approval_resolver
    from core.ontology_runtime import OntologyRuntime
    import api.routes.calculation_control as cal
    import api.routes.ontology_control as onto
    from core import demo_vertical_slice as dv

    sl = dv.build_slice(scope_node_id="plant-afs-smelting-01")
    tenant, scope = dv.scope_of(sl)
    import config as cfg
    cfg.ECM_DEFAULT_TENANT_ID = tenant

    def resolver(ref, rctx):
        return ontology_resolve.found(app_policy.ResourceScope(
            tenant_id=tenant, entity_mode="REAL", scope_node_id=scope,
            owner_dept_id=DEPT_PLANT, binding_state=app_policy.BOUND))

    rt = OntologyRuntime(os.path.join(DEMO_ROOT, "ontology.db"), resolver,
                         product_approval_resolver)
    cal.ontology_runtime = rt
    ortm.ontology_runtime = rt
    onto.router.routes[:] = onto.create_router(rt).routes


if __name__ == "__main__":
    raise SystemExit(main())
