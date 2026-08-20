"""★★★ [파일럿] 화면 확인용 씨앗. 이 스크립트는 «자기가 속한 저장소» 에만 쓴다.

## 왜 워크트리에서 도는가

`core/paths.py` 는 데이터 뿌리를 **`__file__` 기준**으로 잡는다. 그래서 이 파일이
워크트리 사본 안에 있으면 여기서 만드는 모든 DB 는 **그 사본의 `data/`** 에 생긴다 —
운영 `data/` 는 규율이 아니라 **구조로** 닿지 않는다.

⚠️⚠️ 그러므로 운영 저장소에서 실행하지 말 것. 아래에서 직접 막는다.

## 무엇을 심는가

    키트 인스턴스 하나(원료 구매·도입 경영 키트)
    원천 결속 셋 — material_arrivals · purchase_orders 는 활성, supplier_master 는
      **일부러 비워 둔다**
    인증된 판 둘 · RAW 판 하나 · **격리된 판 하나**

★★★ 「전부 초록」인 화면은 아무것도 증명하지 않는다. 준비도 보드가 **READY · 인증
  대기 · 격리 · 원천 미지정**을 한 화면에서 보여 줄 수 있어야, 그 화면이 사람에게
  「다음에 무엇을 하라」고 말할 수 있는지 확인된다.

LLM 0콜.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import library_paths  # noqa: E402
from core.paths import PROJECT_ROOT  # noqa: E402

#: ⚠️⚠️ 안전장치. 운영 저장소에서 돌면 **아무것도 하지 않고 멈춘다.**
if os.path.basename(PROJECT_ROOT) != "pilot_wt":
    raise SystemExit(
        f"이 스크립트는 격리 워크트리(pilot_wt)에서만 돕니다. 지금 뿌리: {PROJECT_ROOT}\n"
        f"운영 저장소에 시연 데이터를 심으면 그 순간 «실제 데이터» 와 구분되지 않습니다.")

from core.data_preparation import kit_registry as kr  # noqa: E402
from core.data_preparation import models as m  # noqa: E402
from core.data_preparation import snapshot_service as ss  # noqa: E402
from core.data_preparation import source_binding as sb  # noqa: E402
from core.data_preparation.store import data_preparation_store as store  # noqa: E402

TENANT, SCOPE, MODE = "tenant_default", "node_hq", "REAL"

GOOD_ARRIVALS = (
    "arrived_at,material_code,quantity,lot_no\n"
    "2026-08-01,M1,120,L-001\n"
    "2026-08-05,M2,80,L-002\n"
    "2026-08-11,M1,95,L-003\n"
).encode("utf-8")

GOOD_ORDERS = (
    "ordered_at,material_code,quantity,unit_price\n"
    "2026-07-20,M1,200,15000\n"
    "2026-07-28,M2,120,22000\n"
).encode("utf-8")

#: ⚠️ 일부러 **잘린** 파일 — 원천은 5행이라 하는데 2행뿐이다.
TRUNCATED = (
    "arrived_at,material_code,quantity\n"
    "2026-08-01,M1,120\n"
    "2026-08-05,M2,80\n"
).encode("utf-8")


def _binding(inst, key, activate=True):
    b = store.create_binding(
        instance_id=inst["instance_id"], dataset_contract_key=key,
        provider=m.PROVIDER_FILE_SNAPSHOT,
        config={"file_name": f"{key}.csv", "column_map": {"a": "A"}},
        tenant_id=TENANT, scope_node_id=SCOPE, entity_mode=MODE)
    if activate:
        for step in ("validate", "approve", "activate"):
            getattr(sb, step)(store, b["binding_id"])
    return store.get_binding(b["binding_id"])


def _upload(binding, payload, name, raw_root):
    return ss.ingest(store, binding=binding, payload=payload, file_name=name,
                     workspace_root=raw_root)


#: 캡처 스크립트가 쓰는 계정·비밀번호. ⚠️ **격리 워크트리 전용**이다 — 운영 저장소에서
#: 이 스크립트가 돌지 않는 것이 위 안전장치의 요점이다.
ADMIN = "hikwon@lsmnm.com"
PASSWORD = "pass:"
DEPT = "hq"


def _seed_org() -> None:
    """조직·사용자·ECM 노드. **이것이 없으면 모든 요청이 범위 판정에서 거부된다.**

    ⚠️ 부서를 ECM 노드에 매어 두지 않으면 `readable_scope_nodes` 가 비고, 화면은
      「통제가 막았다」와 「환경이 덜 세워졌다」를 구분하지 못한다."""
    from core.auth import auth_store
    from core.enterprise_context.models import (STATUS_ACTIVE, EnterpriseEntity,
                                                OrganizationNode)
    from core.enterprise_context.repository import ecm_repository
    from core.org_directory import org_directory

    if not org_directory.get_department(DEPT):
        org_directory.create_department(DEPT, "본사", scope_node_id=SCOPE, actor="pilot")
    else:
        org_directory.update_department(DEPT, scope_node_id=SCOPE, actor="pilot")
    org_directory.upsert_user(ADMIN, "권희권 (예시)", primary_dept_id=DEPT, actor="pilot")
    org_directory.set_user_roles(ADMIN, {DEPT: "member"}, actor="pilot")
    auth_store.set_password(ADMIN, PASSWORD)

    ent = ecm_repository.upsert_entity(EnterpriseEntity(
        entity_id="ent_pilot", tenant_id=TENANT, name_ko="파일럿 법인",
        entity_kind="legal_entity", status=STATUS_ACTIVE))
    ecm_repository.upsert_node(OrganizationNode(
        node_id=SCOPE, entity_id=ent.entity_id, tenant_id=TENANT,
        node_type="business_division", code="HQ", name_ko="본사",
        dept_id=DEPT, status=STATUS_ACTIVE))
    print(f"· 조직·사용자 {ADMIN}")


PROJECT = "proj_pilot"
RELEASE = "rel_pilot"

#: ★★★ 앱 코드. **손으로 쓴 것이다** — LLM 을 부르지 않는다(이 스크립트는 LLM 0콜).
#:   생성기가 만드는 것과 같은 계약(`window.afs.data.*`)만 쓴다. 여기서 확인하려는 것은
#:   「생성기가 좋은 코드를 쓰는가」가 아니라 **「브리지가 실제 브라우저에서 도는가」**다.
#:
#: ⚠️ 앱은 자기 로그인도 자기 백엔드도 갖지 않는다. `release_id` 도 말하지 않는다 —
#:   부모가 붙인다(설계 §7-4). 그래서 아래 코드에 토큰·릴리스·사용자 식별자가 없다.
APP_CODE = """
export default function App() {
  const [rows, setRows] = React.useState(null);
  const [err, setErr] = React.useState('');

  React.useEffect(() => {
    // ★ 데이터셋 «이름» 만 말한다. 어디서 오는지(파일 판·연결·우리 DB)는 모른다.
    // ⚠️ SDK 표면은 schema·list·get·create·update·remove 뿐이다. 처음에 `query` 로
    //   적었다가 «is not a function» 을 받았다 — 표면을 늘려 쓰지 않는다.
    window.afs.ready
      .then(function () { return window.afs.data.list('arrivals', { limit: 50 }); })
      .then(function (r) { setRows(r.records || r.items || []); })
      .catch(function (e) {
        // ⚠️ 실패를 빈 목록으로 그리지 않는다 — 사용자가 「데이터가 없다」로 읽는다.
        setErr(String((e && e.code) || e));
      });
  }, []);

  if (err) {
    return React.createElement('div', { id: 'afs-app-error' },
      '데이터를 지금 읽지 못했습니다 (' + err + ') — 데이터가 없는 것이 아닙니다.');
  }
  if (rows === null) {
    return React.createElement('div', { id: 'afs-app-loading' }, '불러오는 중…');
  }
  return React.createElement('div', { id: 'afs-app-ok' },
    React.createElement('h3', null, '원료 입고 현황'),
    React.createElement('p', { id: 'afs-app-count' }, '읽은 행 수: ' + rows.length),
    React.createElement('ul', null, rows.map(function (r, i) {
      // ⚠️ 업무 값은 **`payload` 아래**에 있다. 행을 그대로 읽으면 행 수는 맞는데
      //   칸이 전부 빈다 — 처음에 그렇게 적어 «· ·» 만 나왔다.
      //   SDK 가 넘기는 것은 record_id · payload · created_at · updated_at · deleted 뿐이다.
      var v = r.payload || {};
      return React.createElement('li', { key: i },
        String(v.arrived_at || '') + ' · ' + String(v.material_code || '')
        + ' · ' + String(v.quantity || ''));
    })));
}
"""


def _runtime_contract() -> dict:
    """계약을 **실제 컴파일러로** 만든다 — 손으로 적으면 씨앗만 아는 모양이 생긴다."""
    from core import app_runtime_contract as arc
    from core.host_contract_compiler import compile_contract

    #: ⚠️ 스키마가 정하는 어휘를 쓴다 — 대문자 상수(`EVENT_TIME`)나 `datetime` 은
    #:   여기서 받지 않는다. 손으로 적으면 이런 어긋남이 난다(실제로 났다).
    fields = [
        {"name": "arrived_at", "type": "date", "required": True,
         "classification": "INTERNAL", "semantic_role": "event_time"},
        {"name": "material_code", "type": "string", "required": True,
         "classification": "INTERNAL"},
        {"name": "quantity", "type": "number", "required": True,
         "classification": "INTERNAL", "semantic_role": "quantity", "unit": "ton"},
    ]
    r = compile_contract({
        "app_class": "departmental",
        "datasets": [
            {"name": "arrivals", "purpose": "자재가 얼마나 들어왔는가",
             "allowed_actions": ["read"], "data_role": arc.ENTERPRISE_ACTUAL,
             "source_intent": arc.ENTERPRISE_READ,
             "enterprise_contract_key": "material_arrivals",
             "duplicate_entry_policy": arc.DENY_IF_AUTHORITATIVE_SOURCE_EXISTS,
             "fields": fields},
        ]}, project_id=PROJECT)
    if not r.ok:
        raise SystemExit(f"계약 컴파일 실패: {r.errors}")
    c = dict(r.contract)
    #: ⚠️ 승인 없이 두면 게이트가 증명을 발급하지 않는다 — 시연에서는 승인된 판을 심는다.
    c["status"] = arc.STATUS_APPROVED
    c["approval"] = {"status": "APPROVED", "approved_by": ADMIN,
                     "approved_at": "2026-08-19T00:00:00Z",
                     "decision_ledger_id": "evt_pilot"}
    return c


def _seed_candidate_release() -> None:
    """게시가 만들어 놓는 것 — 프로젝트 메타 · 릴리스 파일 · **후보 상태**.

    ★★★ 「운영 승격」 화면은 후보가 있어야 무엇이든 보여 줄 수 있다. 0건 화면만 찍으면
      다섯 검사가 사람이 읽을 만하게 나오는지 **한 번도 보지 못한 채** 끝난다.

    ⚠️ 여기서 검사를 통과시키려 하지 않는다. 물질화도 계약 승인도 하지 않은 판이라
      화면은 **막힌 이유들**을 보여 줄 것이고, 그것이 이 화면의 본래 일이다."""
    from core.paths import workspace_path
    from core.program_lifecycle import CANDIDATE, program_lifecycle

    root = workspace_path(PROJECT)
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "project_meta.json"), "w", encoding="utf-8") as f:
        json.dump({"owner_dept_id": DEPT, "owner_user_id": "", "visibility": "dept",
                   "tenant_id": TENANT, "enterprise_scope_id": SCOPE,
                   "entity_mode": MODE, "ownership_basis": "declared"},
                  f, ensure_ascii=False)

    rel_dir = library_paths.release_dir(RELEASE)
    os.makedirs(rel_dir, exist_ok=True)
    with open(os.path.join(rel_dir, "release.json"), "w", encoding="utf-8") as f:
        json.dump({
            "release_id": RELEASE, "project_id": PROJECT, "tenant_id": TENANT,
            "entity_mode": MODE, "enterprise_scope_id": SCOPE,
            "project_name": "원료 입고 현황 앱 (파일럿)",
            "owner_user_id": "", "owner_dept_id": DEPT, "visibility": "dept",
            "artifact_kind": "APP", "runtime_contract_profile": "v1",
            "created_at": "2026-08-19T06:00:00+00:00",
            "manifest": {"fingerprint": "fp_pilot", "valid": True, "manifest": {
                "version": "1.0", "app_class": "departmental",
                "capabilities": ["arrivals.read"], "required_capabilities": []}},
        }, f, ensure_ascii=False)

    program_lifecycle.set_status(RELEASE, CANDIDATE, actor="pilot",
                                 reason="파일럿 시연용 후보")
    print(f"· 후보 릴리스 {RELEASE} (프로젝트 {PROJECT})")


def _materialize_app(instance_id: str) -> None:
    """계약 → 앱 데이터셋 물질화. **후보는 Preview 평면**에 만든다(F-1).

    ★★★ 이것이 없으면 게이트가 「계약에 있는 데이터셋이 물질화되지 않았습니다」로 막고,
      앱은 데이터를 한 줄도 못 읽는다."""
    from core import app_preview, contract_materializer
    from core.data_preparation.store import data_preparation_store as store

    contract = _runtime_contract()
    rel_dir = library_paths.release_dir(RELEASE)
    with open(os.path.join(rel_dir, "release.json"), "r", encoding="utf-8") as f:
        body = json.load(f)
    body["runtime_contract"] = contract
    #: ★ 앱 코드는 미리보기 화면이 읽는 자리에 넣는다 — 종전 화면과 **같은 소스**다.
    #:   다른 곳에 넣으면 두 화면이 다른 앱을 보여 주고, 어느 쪽이 진짜인지 모른다.
    body["frontend_code_summary"] = APP_CODE
    with open(os.path.join(rel_dir, "release.json"), "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False)

    out = contract_materializer.materialize(
        contract, release_id=RELEASE, actor_id="pilot", store=store,
        app_data=app_preview.app_data_for(app_preview.AUDIENCE_PREVIEW),
        tenant_id=TENANT, scope_node_id=SCOPE, entity_mode=MODE)

    #: ★★★ 게시가 릴리스 파일에 남기는 **물질화 기록**을 같은 모양으로 남긴다.
    #:   ⚠️ 이것이 없으면 승격의 「데이터 준비도」 검사가 **어느 인스턴스를 물어야
    #:     하는지 모른다** — 그래서 「확인하지 못했습니다」로 막히고, 화면만 보면
    #:     데이터가 준비 안 된 것처럼 읽힌다(실제로 그렇게 막혔다).
    body["contract_materialization"] = {
        "state": "MATERIALIZED", "detail": "",
        "datasets": [d.get("name", "") for d in out.datasets],
        "sources": {r.name: r.enterprise_contract_key
                    for r in out.resolved if r.enterprise_contract_key},
        "instances": {r.name: r.kit_instance_id
                      for r in out.resolved if r.kit_instance_id},
    }
    with open(os.path.join(rel_dir, "release.json"), "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False)
    print("· 앱 데이터셋 물질화(Preview 평면) — arrivals")


def main() -> int:
    _seed_org()
    _seed_candidate_release()
    raw_root = os.path.join(PROJECT_ROOT, "data", "data_preparation")
    kr.register_all(store)
    kit = kr.resolve(store, kr.DEMO_KIT_ID, "1.0.0")
    if not kit:
        print("✗ 시연 키트를 찾지 못했습니다 — docs/data-kits/ 를 확인하십시오.")
        return 1

    inst = store.create_instance(
        kit_id=kr.DEMO_KIT_ID, version="1.0.0",
        kit_fingerprint=str(kit["fingerprint"]), tenant_id=TENANT,
        scope_node_id=SCOPE, entity_mode=MODE, label="파일럿 시연")
    print(f"· 키트 인스턴스 {inst['instance_id']}")

    # ── ① 정상 판 — 인증까지 ────────────────────────────────────────────
    b1 = _binding(inst, "material_arrivals")
    s1 = _upload(b1, GOOD_ARRIVALS, "arrivals.csv", raw_root)
    rows1 = [{"arrived_at": "2026-08-01", "material_code": "M1", "quantity": "120",
              "lot_no": "L-001"},
             {"arrived_at": "2026-08-05", "material_code": "M2", "quantity": "80",
              "lot_no": "L-002"},
             {"arrived_at": "2026-08-11", "material_code": "M1", "quantity": "95",
              "lot_no": "L-003"}]
    out1 = ss.run_pipeline(store, s1["snapshot_id"], rows1,
                           ["arrived_at", "material_code", "quantity", "lot_no"],
                           control={"row_count": 3, "sums": {"quantity": 295}})
    print(f"· 입고 판 {s1['snapshot_id']} → {out1['state']}")

    # ── ② 인증 대기 판 — 올리기만 하고 검사 안 함 ───────────────────────
    b2 = _binding(inst, "purchase_orders")
    s2 = _upload(b2, GOOD_ORDERS, "orders.csv", raw_root)
    print(f"· 구매주문 판 {s2['snapshot_id']} → {s2['state']} (검사 대기)")

    # ── ③ 격리 판 — **잘린 파일** ───────────────────────────────────────
    #: ★ 화면이 「격리」를 사유와 함께 보여 주는지 확인하려면 실제로 하나 필요하다.
    s3 = _upload(b2, TRUNCATED, "orders_truncated.csv", raw_root)
    rows3 = [{"arrived_at": "2026-08-01", "material_code": "M1", "quantity": "120"},
             {"arrived_at": "2026-08-05", "material_code": "M2", "quantity": "80"}]
    out3 = ss.run_pipeline(store, s3["snapshot_id"], rows3,
                           ["arrived_at", "material_code", "quantity"],
                           control={"row_count": 5})       # ⚠️ 원천은 5행이라 한다
    print(f"· 잘린 판 {s3['snapshot_id']} → {out3['state']}")

    # ── ④ supplier_master 는 **일부러 비운다** ──────────────────────────
    print("· supplier_master → 원천 미지정(의도적)")

    # ── ⑤ 생성 앱 — 계약을 물질화해 실제로 읽히게 한다 ──────────────────
    _materialize_app(inst["instance_id"])

    print()
    print("=== 화면에서 확인할 것 ===")
    print(f"  인스턴스 id : {inst['instance_id']}")
    print(f"  기준선용 판 : {s1['snapshot_id']}")
    print("  준비도 보드에 네 가지 상태가 함께 보여야 합니다 —")
    print("    READY(입고) · 검사 대기(구매주문) · 격리(잘린 판) · 원천 미지정(공급사)")
    print(f"  승격 화면 후보 : {RELEASE} — 다섯 검사에서 «막힌 이유» 가 보여야 합니다")
    print(f"  생성 앱        : 라이브러리에서 «{RELEASE}» 를 열면 입고 3행이 보여야 합니다")
    print("    ⚠️ 프런트에 VITE_AFS_HOST_RUNTIME=1 이 있어야 데이터 평면이 켜집니다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
