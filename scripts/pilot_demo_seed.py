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
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


def main() -> int:
    _seed_org()
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

    print()
    print("=== 화면에서 확인할 것 ===")
    print(f"  인스턴스 id : {inst['instance_id']}")
    print(f"  기준선용 판 : {s1['snapshot_id']}")
    print("  준비도 보드에 네 가지 상태가 함께 보여야 합니다 —")
    print("    READY(입고) · 검사 대기(구매주문) · 격리(잘린 판) · 원천 미지정(공급사)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
