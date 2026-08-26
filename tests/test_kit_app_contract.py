"""★★★ 앱 계약의 **초안 → 승인 → 물질화**. (2026-08-23)

## 이 파일이 지키는 것

    ① **만든 사람은 승인할 수 없다** — 응용에서, 그리고 DB 트리거로도
    ② 근거 없는 승인은 없다 — 「왜 이 앱을 열었나」에 답할 수 없으면 뒤집지도 못한다
    ③ 원장에 남기지 못하면 **상태를 올리지 않는다**
    ④ 재시도가 이력을 부풀리지 않는다(멱등)
    ⑤ 승인된 계약을 조용히 덮지 않는다 — 내용이 바뀌면 **개정을 올린다**

⚠️⚠️ 이 흐름이 없어서 「키트로 앱 생성」은 통제를 다 지나고도 **부를 방법이 없었다.**
  승인 관문은 서 있는데 누를 것이 없었다 — 소유권 승인이 없던 것과 같은 결함이다.

## ★★★ 대조군을 먼저 세운다

⚠️ `seeded_org` 없이 이 시험을 돌리면 `is_bootstrap()` 이 전원 무제한을 주고, 그보다
  먼저 **권한 관문이 「조직 정본이 없다」로 막는다.** 실측에서 실제로 그랬다 — 자기
  승인이 막힌 줄 알았는데 **다른 이유로** 막혀 있었다. 「막혔다」를 세기 전에 **무엇이
  막았는지**를 봐야 한다.
"""
import json
import os

import pytest

from core import kit_app_contract as kac
from core.data_preparation import kit_registry, models as m
from core.data_preparation import snapshot_service as svc

TENANT, SCOPE, MODE = "tenant-afs-demo-materials", "plant-afs-smelting-01", "REAL"


@pytest.fixture()
def flow(tmp_path, seeded_org):
    """정본 키트를 심고 인증판까지 올린 인스턴스 하나.

    ★ 청사진도 **정본 파일에서** 읽는다. 내 말로 쓴 청사진을 쓰면 이 시험은 100%
      초록인데 제품에서는 안 돈다(fixture 가 계약을 대신 정의하는 함정)."""
    from core import demo_vertical_slice as dv
    from core.data_preparation.store import data_preparation_store as store
    from tests import org_seed

    dv.register_kit(store)
    inst = store.create_instance(
        kit_id=dv.KIT_ID, version=dv.KIT_VERSION,
        kit_fingerprint=dv.kit_fingerprint(store),
        tenant_id=TENANT, scope_node_id=SCOPE, entity_mode=MODE, label="계약흐름")

    #: 청사진이 요구하는 것만 인증한다 — 전부 심으면 느리고, 이 시험의 요지도 아니다.
    bp = json.load(open(os.path.join(dv.kit_root(), "app_blueprints", "APP-01.json"),
                        encoding="utf-8"))
    for key in bp["datasets"]:
        rows, cols = dv.read_full(key)
        if not rows:
            continue
        b = store.create_binding(
            instance_id=inst["instance_id"], dataset_contract_key=key,
            provider=m.PROVIDER_FILE_SNAPSHOT, config={},
            tenant_id=TENANT, scope_node_id=SCOPE, entity_mode=MODE)
        for t in (m.VALIDATED, m.APPROVED, m.ACTIVE):
            b = store.transition(b["binding_id"], t)
        snap = svc.ingest(store, binding=b, payload=dv.csv_bytes(rows, cols),
                          file_name=f"{key}.csv",
                          workspace_root=str(tmp_path / "raw"))
        svc.run_pipeline(store, snap["snapshot_id"], rows, cols,
                         control={"row_count": len(rows)})

    kit = store.get_kit_version(dv.KIT_ID, dv.KIT_VERSION)
    return {"store": store, "instance_id": inst["instance_id"], "blueprint": bp,
            "labels": kit_registry.dataset_labels(kit.get("profile") or {}),
            #: ★ 만드는 사람은 **권한이 없는 구성원**이다. 승인자와 확실히 다른 사람이어야
            #:   ①이 진짜로 시험된다.
            "builder": org_seed.MEMBER_A, "approver": org_seed.DATA_ADMIN,
            "other_approver": org_seed.ADMIN}


def _draft(flow, actor=None):
    return kac.draft(flow["store"], blueprint=flow["blueprint"],
                     instance_id=flow["instance_id"], actor_id=actor or flow["builder"],
                     tenant_id=TENANT, scope_node_id=SCOPE, entity_mode=MODE,
                     app_class="departmental", labels=flow["labels"])


# ── 대조군 ──────────────────────────────────────────────────────────────

def test_승인_권한_관문이_먼저_막지_않는지_확인한다(flow):
    """★★★ **이 파일의 첫 시험.**

    ⚠️⚠️ 실측(2026-08-23): 조직을 안 심고 돌렸더니 자기 승인 시험이 초록이었다.
      그런데 사유는 「조직 정본이 아직 없습니다」였다 — **자기 승인 통제는 한 번도
      실행되지 않았다.** 「막혔다」를 세기 전에 무엇이 막았는지 봐야 한다."""
    from core.data_preparation import ownership_binding as _ob

    #: 승인자는 관문을 **지나야** 한다. 안 지나면 아래 시험들이 전부 거짓 초록이다.
    _ob.require_approval_authority(flow["approver"])

    #: 대조군 — 권한 없는 사람은 여기서 막힌다(다른 사유·다른 예외).
    with pytest.raises(Exception):
        _ob.require_approval_authority(flow["builder"])


# ── ① 자기 승인 ─────────────────────────────────────────────────────────

def test_만든_사람은_자기_계약을_승인할_수_없다(flow):
    """★★★ 요청자가 승인자 자리에 앉으면 승인은 **절차의 이름만** 남는다."""
    d = _draft(flow, actor=flow["approver"])          # 승인 권한자가 «만든» 경우
    with pytest.raises(kac.ContractFlowError) as err:
        kac.approve(flow["store"], instance_id=flow["instance_id"], app_id="APP-01",
                    revision=d["revision"], actor_id=flow["approver"],
                    rationale="내가 만들었으니 내가 승인")
    assert "만든 사람은 승인할 수 없습니다" in str(err.value)


def test_응용을_건너뛴_자기승인을_DB_가_막는다(flow):
    """★★★ **층마다 다른 가정에 선다.**

    ⚠️⚠️ 응용에만 두면 다음 호출 경로가 그 검사를 건너뛴다 — 이 저장소에서 이미
      「예외를 한 곳만 지웠다」로 겪은 일이다.
    ★ 그리고 트리거는 응용의 정규화를 **믿지 않는다** — 공백·대소문자가 달라도 같은
      사람이다. 통제가 자기가 막을 것에 기대면 그것은 층이 아니다."""
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError) as err:
        with flow["store"].transaction() as conn:
            conn.execute(
                "INSERT INTO kit_app_contracts (contract_row_id, instance_id, app_id, "
                " revision, status, semantic_fingerprint, contract_json, drafted_by, "
                " drafted_at, approved_by, updated_at) "
                "VALUES ('x','i','A',1,'APPROVED','fp','{}','  Same@X ','t','same@x','t')")
    assert "자기 계약을 승인할 수 없습니다" in str(err.value)


# ── ② 근거 ──────────────────────────────────────────────────────────────

def test_근거_없는_승인은_없다(flow):
    """⚠️ 「왜 이 앱을 열었나」에 답할 수 없는 승인은 나중에 아무도 뒤집지 못한다."""
    d = _draft(flow)
    with pytest.raises(kac.ContractFlowError) as err:
        kac.approve(flow["store"], instance_id=flow["instance_id"], app_id="APP-01",
                    revision=d["revision"], actor_id=flow["approver"], rationale="   ")
    assert "승인 근거가 필요합니다" in str(err.value)


# ── ③ 원장 ──────────────────────────────────────────────────────────────

def test_원장에_못_남기면_상태를_올리지_않는다(flow, monkeypatch):
    """★★★ 「승인 이력 없는 승인」이 남으면 누가 왜 열었는지 답할 수 없다."""
    from core.decision_ledger import decision_ledger

    d = _draft(flow)
    monkeypatch.setattr(decision_ledger, "append",
                        lambda **kw: (_ for _ in ()).throw(RuntimeError("원장 down")))
    with pytest.raises(kac.LedgerUnavailable):
        kac.approve(flow["store"], instance_id=flow["instance_id"], app_id="APP-01",
                    revision=d["revision"], actor_id=flow["approver"], rationale="개설")
    #: ★ 상태가 그대로여야 한다 — 여기서 APPROVED 면 승인 없는 앱이 열린다.
    assert kac.approved(flow["store"], flow["instance_id"], "APP-01") is None
    assert kac.latest(flow["store"], flow["instance_id"], "APP-01")["status"] == \
        kac.STATUS_DRAFT


def test_승인하면_원장_사건_id_가_계약에_박힌다(flow):
    """★ 대조군 — 늘 막히기만 하면 그것은 기능이 아니다."""
    from core import app_runtime_contract as arc

    d = _draft(flow)
    a = kac.approve(flow["store"], instance_id=flow["instance_id"], app_id="APP-01",
                    revision=d["revision"], actor_id=flow["approver"],
                    rationale="원료 도입계획 추적 화면 개설")
    assert a["status"] == kac.STATUS_APPROVED
    assert a["approved_by"] == flow["approver"]
    assert a["ledger_event_id"]
    ap = a["contract"]["approval"]
    assert ap["status"] == "APPROVED"
    assert ap["decision_ledger_id"] == a["ledger_event_id"]
    #: ★★★ 승인 봉투가 바뀌었으니 **지문도 따라갔어야** 한다.
    assert arc.validate(a["contract"]) == [], arc.validate(a["contract"])
    assert a["semantic_fingerprint"] == arc.semantic_fingerprint(a["contract"])


# ── ④ 멱등 ──────────────────────────────────────────────────────────────

def test_같은_초안을_다시_만들어도_개정이_늘지_않는다(flow):
    """⚠️ 네트워크 재시도만으로 이력이 부풀면 「무엇이 바뀌었나」를 못 읽는다."""
    a, b = _draft(flow), _draft(flow)
    assert (a["revision"], a["semantic_fingerprint"]) == \
           (b["revision"], b["semantic_fingerprint"])
    assert len(kac.list_for_instance(flow["store"], flow["instance_id"])) == 1


def test_같은_승인을_두_번_해도_원장_사건은_하나다(flow):
    d = _draft(flow)
    kw = dict(instance_id=flow["instance_id"], app_id="APP-01", revision=d["revision"],
              actor_id=flow["approver"], rationale="개설")
    a = kac.approve(flow["store"], **kw)
    b = kac.approve(flow["store"], **kw)
    assert a["ledger_event_id"] == b["ledger_event_id"]


# ── ⑤ 개정 ──────────────────────────────────────────────────────────────

def test_승인된_계약을_조용히_덮지_않는다(flow):
    """★★★ 덮으면 **승인이 다른 내용을 가리킨다** — 그리고 그 갈림은 조용하다."""
    d = _draft(flow)
    a = kac.approve(flow["store"], instance_id=flow["instance_id"], app_id="APP-01",
                    revision=d["revision"], actor_id=flow["approver"], rationale="개설")

    #: 내용을 바꾼다 — 데이터셋 하나를 뺀다.
    flow["blueprint"] = {**flow["blueprint"],
                         "datasets": flow["blueprint"]["datasets"][:3]}
    d2 = _draft(flow)
    assert d2["revision"] == d["revision"] + 1, "개정을 올리지 않았다"
    assert d2["status"] == kac.STATUS_DRAFT

    #: ★ 승인된 것은 그대로 살아 있다 — 새 개정이 승인되기 전까지 도는 앱은 옛 계약이다.
    still = kac.approved(flow["store"], flow["instance_id"], "APP-01")
    assert still["revision"] == d["revision"]
    assert still["semantic_fingerprint"] == a["semantic_fingerprint"]
    assert still["semantic_fingerprint"] != d2["semantic_fingerprint"]


def test_새_개정이_승인되면_옛_승인은_밀려난다(flow):
    """★ 한 앱에 승인된 계약은 **하나뿐**이다 — 둘이면 어느 쪽이 도는 앱인지 모른다."""
    d = _draft(flow)
    kac.approve(flow["store"], instance_id=flow["instance_id"], app_id="APP-01",
                revision=d["revision"], actor_id=flow["approver"], rationale="개설")
    flow["blueprint"] = {**flow["blueprint"],
                         "datasets": flow["blueprint"]["datasets"][:3]}
    d2 = _draft(flow)
    a2 = kac.approve(flow["store"], instance_id=flow["instance_id"], app_id="APP-01",
                     revision=d2["revision"], actor_id=flow["approver"],
                     rationale="데이터셋 축소 개정")
    assert a2["revision"] == d2["revision"]
    rows = {r["revision"]: r["status"]
            for r in kac.list_for_instance(flow["store"], flow["instance_id"])}
    assert rows[d["revision"]] == kac.STATUS_SUPERSEDED
    assert rows[d2["revision"]] == kac.STATUS_APPROVED


# ── 종단 ────────────────────────────────────────────────────────────────

def test_승인된_계약으로_실제_앱이_만들어진다(flow):
    """★★★ **여정의 빈 칸이 열렸는지**를 본다. 조각의 합이 아니라 관통이다.

    ⚠️ 「계약이 승인됐다」까지만 보면 화면에는 여전히 누를 것이 없다."""
    from datetime import datetime, timezone

    from core import app_preview, kit_app_builder as kb
    from core import demo_vertical_slice as dv
    from core.data_preparation import readiness

    store = flow["store"]
    iid = flow["instance_id"]
    d = _draft(flow)
    a = kac.approve(store, instance_id=iid, app_id="APP-01", revision=d["revision"],
                    actor_id=flow["approver"], rationale="개설")

    kit = store.get_kit_version(dv.KIT_ID, dv.KIT_VERSION)
    profile = kit.get("profile") or {}
    keys = kit_registry.dataset_keys(profile)
    snaps = {k: [] for k in keys}
    for row in store.list_snapshots(iid):
        k = str(row.get("dataset_contract_key") or "")
        if k in snaps:
            snaps[k].append(row)
    ev = readiness.evaluate_instance(
        contract_keys=keys, bindings={k: store.active_binding(iid, k) for k in keys},
        snapshots=snaps, outputs=kit_registry.outputs(profile),
        now=datetime.now(timezone.utc).isoformat(timespec="seconds"), max_age_days=None,
        scope={"tenant_id": TENANT, "scope_node_id": SCOPE, "entity_mode": MODE})

    out = kb.build(blueprint=flow["blueprint"], approved_contract=a["contract"],
                   instance_id=iid, outputs=ev.get("outputs") or [],
                   actor_id=flow["approver"], store=store,
                   app_data=app_preview.app_data_for(app_preview.AUDIENCE_PREVIEW),
                   tenant_id=TENANT, scope_node_id=SCOPE, entity_mode=MODE)
    assert out["release_id"] == kb.release_id_for(iid, "APP-01")
    assert len(out["datasets"]) == len(flow["blueprint"]["datasets"])
    #: ★ 이름은 문법에 맞게 접혀 있고, 계약키는 계약 안에 그대로 남아 있다.
    assert all(n == n.lower() and "-" not in n for n in out["datasets"])
