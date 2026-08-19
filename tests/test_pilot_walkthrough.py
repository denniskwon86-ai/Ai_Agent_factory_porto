"""★★★ [파일럿] 12칸 동선을 **실제 데이터로** 한 번 관통한다.

## 왜 이 파일이 필요한가

지금까지 확인된 것은 「각 화면이 열린다」였다. 「동선이 돈다」는 아직이었고, 그 차이가
이 세션에서 **다섯 번** 사고를 냈다 — 물질화기·`candidate` 상태·진짜 코드 미태움·
라우터 미등록·본문 배경 없음. 전부 「만들었는데 그것이 실제로 도는 것을 본 적이
없다」였다.

이 파일은 **사용자가 누르는 순서 그대로** API 를 부른다. 중간의 어느 배선이 빠지면
여기서 멈춘다.

```text
① 키트 목록          → ② 인스턴스 만들기      → ③ 원천 결속·활성
④ CSV 등록           → ⑤ 품질·대사·인증        → ⑥ 준비도 보드
⑦ 기준선 고정        → ⑧ 영향 경로            → ⑨ 시뮬레이션
⑩ 의사결정 안건
```

⚠️ **운영 저장소를 쓰지 않는다.** conftest 가 모든 DB 를 `tmp_path` 로 돌린다.
"""
import io
import json

import pytest

import api.routes.baseline_control as bc
import api.routes.data_preparation_control as dp
from core.data_preparation import kit_registry as kr
from tests import org_seed

CSV = (
    "arrived_at,material_code,quantity,lot_no\n"
    "2026-08-01,M1,120,L-001\n"
    "2026-08-05,M2,80,L-002\n"
).encode("utf-8")

#: 원천이 말한 값 — 이것과 대사해서 「잘린 파일」을 잡는다.
CONTROL = {"row_count": 2, "sums": {"quantity": 200}}

BASE_VALUES = {
    "production_qty": 1000.0, "ending_inventory": 200.0,
    "purchase_payment": 5_000_000.0, "ending_cash": 30_000_000.0,
    "operating_profit": 4_000_000.0, "power_cost": 800_000.0,
    "period_days": 30.0,
}


@pytest.fixture
def client(tmp_path, monkeypatch, enforced_org):
    """실제 라우터 둘 + 격리 저장소. ⚠️ 운영 경로는 하나도 쓰지 않는다."""
    import config
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True, raising=False)
    monkeypatch.setattr(dp, "_raw_root", lambda: str(tmp_path / "raw"))
    ctx = {"tenant_id": "tenant_default", "entity_mode": "REAL"}
    monkeypatch.setattr(dp, "_ctx", lambda p: ctx)
    monkeypatch.setattr(dp, "_visible_scopes", lambda p: ["n_pilot"])
    monkeypatch.setattr(bc, "viewing_context", lambda p: ctx, raising=False)

    app = FastAPI()
    app.include_router(dp.router)
    app.include_router(bc.router)
    return TestClient(app)


H = {"X-Factory-User": org_seed.ADMIN}


def _seed_kits(client):
    """키트를 등록한다 — **목록을 여는 것이 곧 등록**이다(`register_all` 은 멱등).

    ⚠️ 이 한 줄을 빼면 인스턴스 만들기가 404 로 막힌다. 실제 사용자도 화면을 열면서
      같은 순서를 지나므로, 시험이 그 순서를 건너뛰면 «시험에서만 되는» 상태가 된다."""
    r = client.get("/api/v1/data-preparation/kits", headers=H)
    assert r.status_code == 200, r.text


def _data(r, step):
    """응답 봉투를 벗긴다. ⚠️ 실패를 그대로 드러낸다 — 어느 칸에서 멈췄는지가 요점이다."""
    assert r.status_code == 200, f"{step} 에서 멈췄다: {r.status_code} {r.text[:300]}"
    return r.json()["data"]


def test_the_pilot_walkthrough_runs_end_to_end(client, tmp_path):
    """★★★ **12칸을 실제 데이터로 관통한다.**

    ⚠️ 이 시험이 초록이라는 것은 「각 조각이 있다」가 아니라 **「이어져 있다」**는 뜻이다."""
    # ── ① 키트 목록 ─────────────────────────────────────────────────────
    kits = _data(client.get("/api/v1/data-preparation/kits", headers=H), "① 키트 목록")
    assert any(k["kit_id"] == kr.DEMO_KIT_ID for k in kits["kits"]), \
        "시연 키트가 목록에 없다"

    # ── ② 인스턴스 만들기 ───────────────────────────────────────────────
    inst = _data(client.post("/api/v1/data-preparation/instances", headers=H, json={
        "kit_id": kr.DEMO_KIT_ID, "version": "1.0.0",
        "scope_node_id": "n_pilot", "entity_mode": "REAL",
        "label": "파일럿"}), "② 인스턴스 만들기")
    iid = inst["instance_id"]

    # ── ③ 원천 결속 → 활성 ──────────────────────────────────────────────
    binding = _data(client.post(
        f"/api/v1/data-preparation/instances/{iid}/bindings", headers=H, json={
            "dataset_contract_key": "material_arrivals",
            "provider": "FILE_SNAPSHOT",
            "config": {"file_name": "arrivals.csv", "column_map": {"a": "A"}}}),
        "③ 결속 만들기")
    bid = binding["binding_id"]
    for action in ("VALIDATE", "APPROVE", "ACTIVATE"):
        state = _data(client.post(
            f"/api/v1/data-preparation/bindings/{bid}/decision",
            headers=H, json={"action": action}), f"③ 결속 {action}")
    assert state["state"] == "ACTIVE", state

    # ── ④ CSV 등록 ──────────────────────────────────────────────────────
    snap = _data(client.post(
        f"/api/v1/data-preparation/bindings/{bid}/snapshots", headers=H,
        files={"file": ("arrivals.csv", CSV, "text/csv")}), "④ CSV 등록")
    assert snap["row_count"] == 2, snap
    assert snap["state"] == "RAW"
    sid = snap["snapshot_id"]

    # ── ⑤ 품질·대사·인증 ────────────────────────────────────────────────
    certified = _data(client.post(
        f"/api/v1/data-preparation/snapshots/{sid}/certify", headers=H,
        json={"control": CONTROL}), "⑤ 인증")
    assert certified["state"] == "DEMO_CERTIFIED", certified
    #: ★ 성격 표시가 서버에서 온다 — 화면이 각자 붙이지 않는다.
    assert "DEMO/SYNTHETIC" in certified["display_label"]

    # ── ⑥ 준비도 보드 ───────────────────────────────────────────────────
    ready = _data(client.get(
        f"/api/v1/data-preparation/instances/{iid}/readiness", headers=H), "⑥ 준비도")
    states = {d["dataset_contract_key"]: d["state"] for d in ready["datasets"]}
    assert states["material_arrivals"] == "READY", states
    #: ⚠️ 나머지 둘은 아직 원천이 없다 — **0건이 아니라 「아직 아니다」** 로 나와야 한다.
    assert states["purchase_orders"] == "NOT_CONFIGURED"
    assert ready["status"] == "PARTIAL", ready["status"]
    #: 이 데이터 하나만 요구하는 산출물은 이제 가능해야 한다
    assert "입고 현황 보고" in ready["available_outputs"], ready["available_outputs"]
    #: 나머지를 요구하는 것은 막히고, **다음 행동과 책임자**가 붙어 있어야 한다
    blocked = {o["output"]: o for o in ready["blocked_outputs"]}
    assert "구매 이행 현황" in blocked
    assert blocked["구매 이행 현황"]["next_action"]
    assert blocked["구매 이행 현황"]["responsible_role"]

    # ── ⑦ 기준선 고정 ───────────────────────────────────────────────────
    baseline = _data(client.post("/api/v1/baseline/builds", headers=H, json={
        "instance_id": iid, "snapshot_ids": [sid], "label": "파일럿 기준선"}),
        "⑦ 기준선")
    assert baseline["snapshot_ids"] == [sid]
    assert baseline["fingerprint"]
    assert "실적이 아닙니다" in baseline["display_label"]

    # ── ⑧ 영향 경로 ─────────────────────────────────────────────────────
    path = _data(client.get(
        "/api/v1/baseline/impact-path?start=purchase_order&end=cash_pl", headers=H),
        "⑧ 영향 경로")
    assert [n["key"] for n in path["path"]][0] == "purchase_order"
    #: ⚠️ 근거가 없는 칸이 **드러나야** 한다 — 숨기면 「전부 설명됐다」로 보인다.
    assert path["complete"] is False and path["missing_evidence"]

    # ── ⑨ 시뮬레이션 ────────────────────────────────────────────────────
    sim = _data(client.post("/api/v1/baseline/simulate", headers=H, json={
        "instance_id": iid, "snapshot_ids": [sid],
        "base_values": BASE_VALUES,
        "assumptions": {"fx_rate_pct": 10, "lead_time_days": 14,
                        "power_price_pct": 12}}), "⑨ 시뮬레이션")
    by = {r["key"]: r for r in sim["compare"]}
    #: 환율 +10% → 구매지급 +10%
    assert by["purchase_payment"]["delta_pct"] == 10.0, by["purchase_payment"]
    #: 도입 지연 14일 / 30일 → 생산량이 줄어야 한다
    assert by["production_qty"]["delta"] < 0, by["production_qty"]
    #: 같은 입력이면 같은 지문 — **재현성**
    again = _data(client.post("/api/v1/baseline/simulate", headers=H, json={
        "instance_id": iid, "snapshot_ids": [sid],
        "base_values": BASE_VALUES,
        "assumptions": {"fx_rate_pct": 10, "lead_time_days": 14,
                        "power_price_pct": 12}}), "⑨ 재현성")
    assert again["scenario"]["fingerprint"] == sim["scenario"]["fingerprint"]

    # ── ⑩ 의사결정 안건 ─────────────────────────────────────────────────
    pkg = _data(client.post("/api/v1/baseline/decisions", headers=H, json={
        "instance_id": iid, "snapshot_ids": [sid],
        "base_values": BASE_VALUES,
        "assumptions": {"fx_rate_pct": 10, "lead_time_days": 14},
        "title": "환율·도입 지연 대응", "owner": "구매팀장", "due": "2026-08-30",
        "path_from": "purchase_order", "path_to": "cash_pl"}), "⑩ 의사결정")
    assert [v["view"] for v in pkg["views"]] == ["요청자", "의사결정자", "영향부서"]
    assert pkg["owner"] == "구매팀장" and pkg["due"] == "2026-08-30"
    #: ★★★ 계보가 붙어 있어야 한다 — 다음 회의에서 같은 숫자를 다시 만들 수 있게.
    assert pkg["evidence"]["snapshot_ids"] == [sid]
    assert pkg["evidence"]["baseline_fingerprint"] == baseline["fingerprint"]
    assert pkg["evidence"]["calc_version"]
    #: 브리핑이 성격을 먼저 말한다
    assert "DEMO/SYNTHETIC" in pkg["briefing"][0]


def test_a_truncated_file_stops_the_walkthrough_at_certification(client):
    """★★★ **잘린 파일은 인증되지 않는다** — 동선이 거기서 멈춰야 한다.

    ⚠️ 통과하면 그 위의 기준선·시뮬레이션·안건이 전부 잘린 데이터로 만들어지고,
      아무도 그것을 고장으로 보지 않는다."""
    _seed_kits(client)
    inst = _data(client.post("/api/v1/data-preparation/instances", headers=H, json={
        "kit_id": kr.DEMO_KIT_ID, "version": "1.0.0",
        "scope_node_id": "n_pilot", "entity_mode": "REAL"}), "인스턴스")
    b = _data(client.post(
        f"/api/v1/data-preparation/instances/{inst['instance_id']}/bindings",
        headers=H, json={"dataset_contract_key": "material_arrivals",
                         "provider": "FILE_SNAPSHOT",
                         "config": {"file_name": "a.csv", "column_map": {"a": "A"}}}),
        "결속")
    for action in ("VALIDATE", "APPROVE", "ACTIVATE"):
        client.post(f"/api/v1/data-preparation/bindings/{b['binding_id']}/decision",
                    headers=H, json={"action": action})
    snap = _data(client.post(
        f"/api/v1/data-preparation/bindings/{b['binding_id']}/snapshots", headers=H,
        files={"file": ("a.csv", CSV, "text/csv")}), "등록")

    #: 원천은 5행이라고 말하는데 파일에는 2행뿐이다 — **잘렸다**
    out = _data(client.post(
        f"/api/v1/data-preparation/snapshots/{snap['snapshot_id']}/certify",
        headers=H, json={"control": {"row_count": 5}}), "인증 시도")
    assert out["state"] == "QUARANTINED", out
    assert "잘렸" in json.dumps(out.get("quarantine") or {}, ensure_ascii=False)

    #: ★ 그리고 그 판으로는 기준선을 만들 수 없다
    r = client.post("/api/v1/baseline/builds", headers=H, json={
        "instance_id": inst["instance_id"],
        "snapshot_ids": [snap["snapshot_id"]]})
    assert r.status_code == 409, "격리된 판으로 기준선이 만들어졌다: " + r.text[:200]


def test_a_baseline_cannot_be_built_from_another_orgs_snapshot(client):
    """★★★ 남의 판 id 를 섞어 보내는 경로를 막는다.

    ⚠️ 섞이면 그 합계는 **아무 회사의 숫자도 아니다.**"""
    _seed_kits(client)
    inst = _data(client.post("/api/v1/data-preparation/instances", headers=H, json={
        "kit_id": kr.DEMO_KIT_ID, "version": "1.0.0",
        "scope_node_id": "n_pilot", "entity_mode": "REAL"}), "인스턴스")
    r = client.post("/api/v1/baseline/builds", headers=H, json={
        "instance_id": inst["instance_id"], "snapshot_ids": ["ds_남의판"]})
    assert r.status_code == 404, r.text


def test_an_empty_snapshot_list_is_refused_not_treated_as_latest(client):
    """★★★ 「알아서 최신으로」는 **재현할 수 없는 기준선**을 만든다.

    ⚠️ 빈 목록을 받아 주면 그 기준선은 다음 주에 다른 숫자를 낸다. 같은 이름으로
      다른 답을 내는 것이 재현성 주장 전체를 무너뜨린다."""
    _seed_kits(client)
    inst = _data(client.post("/api/v1/data-preparation/instances", headers=H, json={
        "kit_id": kr.DEMO_KIT_ID, "version": "1.0.0",
        "scope_node_id": "n_pilot", "entity_mode": "REAL"}), "인스턴스")
    for payload in ([], ["", "  "]):
        r = client.post("/api/v1/baseline/builds", headers=H, json={
            "instance_id": inst["instance_id"], "snapshot_ids": payload})
        assert r.status_code == 422, f"빈 목록 {payload!r} 이 받아들여졌다: {r.text[:200]}"
        assert "snapshot_ids" in r.text


def test_an_instance_outside_my_scope_is_not_opened(client, monkeypatch):
    """★★★ 볼 수 없는 범위의 인스턴스는 **열리지 않는다.**

    ⚠️ 「없다」와 「못 본다」를 같은 404 로 답한다 — 다르게 답하면 그 응답이
      「그 조직에 그런 자원이 있다」를 알려 주는 신호가 된다.

    ★★★ **이 시험만 `ADMIN` 을 쓰지 않는다.** 이 파일의 나머지는 전권 관리자로 도는데,
      전권 관리자는 `scope.unrestricted` 라 **범위 판정 자체를 지나지 않는다** — 그
      신원으로 「막히는가」를 물으면 통제가 꺼진 채 초록이 뜬다(2026-08-19 변이 검사가
      이것을 잡았다: 범위 비교를 통째로 없애도 관통 시험이 전부 통과했다)."""
    other = {"X-Factory-User": org_seed.MEMBER_B}
    _seed_kits(client)
    inst = _data(client.post("/api/v1/data-preparation/instances", headers=H, json={
        "kit_id": kr.DEMO_KIT_ID, "version": "1.0.0",
        "scope_node_id": "n_pilot", "entity_mode": "REAL"}), "인스턴스")
    iid = inst["instance_id"]

    #: 같은 사용자가 **다른 범위**로 옮겨 간 상황. 인스턴스는 그대로 있다.
    monkeypatch.setattr(dp, "_visible_scopes", lambda p: ["n_다른조직"])
    monkeypatch.setattr(bc, "_visible_scopes", lambda p: ["n_다른조직"], raising=False)

    r = client.post("/api/v1/baseline/builds", headers=other, json={
        "instance_id": iid, "snapshot_ids": ["ds_아무거나"]})
    assert r.status_code == 404, "범위 밖 인스턴스가 열렸다: " + r.text[:200]
    #: ⚠️ 사유가 「그 판이 없다」로 나오면 **인스턴스의 존재가 새어 나간다.**
    assert "인스턴스" in r.text, "존재를 시인하는 사유가 돌아왔다: " + r.text[:200]
    assert "ds_아무거나" not in r.text, "찾던 판 id 를 되돌려 주며 존재를 시인했다"

    #: 준비도도 같은 답이어야 한다 — 한쪽 문만 잠그면 옆문으로 들어온다.
    assert client.get(f"/api/v1/data-preparation/instances/{iid}/readiness",
                      headers=other).status_code == 404

    #: 목록에서는 **개수조차** 세지 않는다.
    listed = _data(client.get("/api/v1/data-preparation/instances", headers=other), "목록")
    assert [i for i in listed["instances"] if i["instance_id"] == iid] == []

    #: ★ 대조군 — 같은 요청을 **원래 범위**로 하면 404 가 아니다. 이것이 없으면
    #:   「전부 404」인 고장을 통제로 착각한다(2026-08-09 사고와 같은 종류).
    ok = client.post("/api/v1/baseline/builds", headers=H, json={
        "instance_id": iid, "snapshot_ids": ["ds_아무거나"]})
    assert ok.status_code == 404 and "Snapshot" in ok.text or "판" in ok.text, (
        "원래 범위에서도 인스턴스를 못 찾는다 — 시험이 통제가 아니라 고장을 보고 있다: "
        + ok.text[:200])


def test_the_instance_list_lets_a_user_start_without_typing_an_id(client):
    """★★★ 이 목록이 없으면 화면은 사용자에게 `ki_…` 를 «타이핑하라» 고 요구한다.

    기능이 도는 것과 사람이 시작할 수 있는 것은 다르다."""
    _seed_kits(client)
    inst = _data(client.post("/api/v1/data-preparation/instances", headers=H, json={
        "kit_id": kr.DEMO_KIT_ID, "version": "1.0.0", "label": "파일럿 시연",
        "scope_node_id": "n_pilot", "entity_mode": "REAL"}), "인스턴스")
    listed = _data(client.get("/api/v1/data-preparation/instances", headers=H), "목록")
    mine = [i for i in listed["instances"] if i["instance_id"] == inst["instance_id"]]
    assert mine, "방금 만든 인스턴스가 목록에 없다"
    #: ★ 사람이 읽는 이름이 함께 와야 화면이 id 를 앞세우지 않을 수 있다.
    assert mine[0]["label"] == "파일럿 시연"


def test_every_required_dataset_is_named_even_when_it_has_no_source(client):
    """★★★ 결속된 것만 보내면 화면은 「빠진 데이터」를 그릴 재료가 없다.

    ⚠️ 그러면 원천을 하나도 안 고른 인스턴스가 「연결할 것이 없다」처럼 보인다."""
    _seed_kits(client)
    inst = _data(client.post("/api/v1/data-preparation/instances", headers=H, json={
        "kit_id": kr.DEMO_KIT_ID, "version": "1.0.0",
        "scope_node_id": "n_pilot", "entity_mode": "REAL"}), "인스턴스")
    got = _data(client.get(
        f"/api/v1/data-preparation/instances/{inst['instance_id']}", headers=H), "인스턴스")

    req = got["required_datasets"]
    assert req, "계약이 요구하는 데이터셋이 하나도 오지 않았다"
    assert all(not d["bound"] for d in req), "결속이 없는데 bound 가 참이다"
    arrivals = [d for d in req if d["dataset_contract_key"] == "material_arrivals"]
    assert arrivals, "material_arrivals 가 요구 목록에 없다"
    #: ★ 이름이 계약 이름과 **달라야** 화면이 §12(기술 ID 를 앞세우지 않는다)를 지킬 수 있다.
    assert arrivals[0]["label"] and arrivals[0]["label"] != "material_arrivals"

    #: 준비도 응답도 같은 이름을 실어 보낸다 — 화면마다 다른 이름이 되지 않도록.
    ready = _data(client.get(
        f"/api/v1/data-preparation/instances/{inst['instance_id']}/readiness",
        headers=H), "준비도")
    by_key = {d["dataset_contract_key"]: d for d in ready["datasets"]}
    assert by_key["material_arrivals"]["label"] == arrivals[0]["label"]


def test_the_impact_path_says_unchecked_instead_of_missing(client):
    """★★★ 「아직 안 봤다」와 「근거가 없다」는 **다른 말**이다.

    ⚠️ 섞으면 화면 위쪽은 「근거 없음」이라 하고 같은 화면 아래의 안건은 그 판을
      근거로 쓴다 — 한 화면에 두 답이 뜬다(2026-08-19 실제로 그랬다)."""
    _seed_kits(client)
    inst = _data(client.post("/api/v1/data-preparation/instances", headers=H, json={
        "kit_id": kr.DEMO_KIT_ID, "version": "1.0.0",
        "scope_node_id": "n_pilot", "entity_mode": "REAL"}), "인스턴스")
    iid = inst["instance_id"]

    #: ① 기준선 없이 물으면 — 확인하지 않은 것이다.
    bare = _data(client.get(
        "/api/v1/baseline/impact-path?start=purchase_order&end=cash_pl",
        headers=H), "경로")
    assert bare["evidence_checked"] is False, "기준선 없이도 「확인했다」고 답한다"

    #: ② 기준선을 주면 — 그 기준선으로 잇는다.
    b = _data(client.post(
        f"/api/v1/data-preparation/instances/{iid}/bindings", headers=H, json={
            "dataset_contract_key": "material_arrivals",
            "provider": "FILE_SNAPSHOT",
            "config": {"file_name": "a.csv", "column_map": {"a": "A"}}}), "결속")
    for action in ("validate", "approve", "activate"):
        client.post(f"/api/v1/data-preparation/bindings/{b['binding_id']}/decision",
                    headers=H, json={"action": action})
    snap = _data(client.post(
        f"/api/v1/data-preparation/bindings/{b['binding_id']}/snapshots", headers=H,
        files={"file": ("a.csv", CSV, "text/csv")}), "판")
    _data(client.post(
        f"/api/v1/data-preparation/snapshots/{snap['snapshot_id']}/certify",
        headers=H, json={"control": CONTROL}), "인증")

    got = _data(client.get(
        "/api/v1/baseline/impact-path?start=purchase_order&end=cash_pl"
        f"&instance_id={iid}&snapshot_ids={snap['snapshot_id']}", headers=H), "경로")
    assert got["evidence_checked"] is True
    #: ★ 근거가 붙은 칸은 「없는 단계」에서 빠져야 한다 — 안건이 쓰는 판과 같은 답.
    assert "material_arrivals" not in got["missing_evidence"], (
        "안건은 근거로 쓰는 판을 경로는 「근거 없음」이라 한다")
    #: ★ 남은 것은 **사람이 읽는 이름**으로도 온다(설계 §12).
    assert got["missing_steps"], "아직 근거가 없는 단계가 있어야 하는데 비었다"
    for st in got["missing_steps"]:
        assert st["label"] and st["label"] != st["dataset_key"], (
            f"계약키가 그대로 이름칸에 들어 있다: {st}")


def test_the_impact_path_does_not_borrow_another_scopes_baseline(client):
    """★★★ 범위 밖 인스턴스로 경로를 채워 주지 않는다 — 여기서도 같은 404 다."""
    _seed_kits(client)
    inst = _data(client.post("/api/v1/data-preparation/instances", headers=H, json={
        "kit_id": kr.DEMO_KIT_ID, "version": "1.0.0",
        "scope_node_id": "n_pilot", "entity_mode": "REAL"}), "인스턴스")
    r = client.get("/api/v1/baseline/impact-path?start=purchase_order&end=cash_pl"
                   f"&instance_id={inst['instance_id']}",
                   headers={"X-Factory-User": org_seed.MEMBER_B})
    assert r.status_code == 404, "범위 밖 기준선으로 경로가 채워졌다: " + r.text[:200]


def test_certified_snapshots_are_named_for_people(client):
    """★★★ 기준선 고르개가 `material_arrivals` 를 그대로 보여 주면 §12 위반이다."""
    _seed_kits(client)
    inst = _data(client.post("/api/v1/data-preparation/instances", headers=H, json={
        "kit_id": kr.DEMO_KIT_ID, "version": "1.0.0",
        "scope_node_id": "n_pilot", "entity_mode": "REAL"}), "인스턴스")
    b = _data(client.post(
        f"/api/v1/data-preparation/instances/{inst['instance_id']}/bindings",
        headers=H, json={"dataset_contract_key": "material_arrivals",
                         "provider": "FILE_SNAPSHOT",
                         "config": {"file_name": "a.csv", "column_map": {"a": "A"}}}),
        "결속")
    for action in ("validate", "approve", "activate"):
        client.post(f"/api/v1/data-preparation/bindings/{b['binding_id']}/decision",
                    headers=H, json={"action": action})
    _data(client.post(
        f"/api/v1/data-preparation/bindings/{b['binding_id']}/snapshots", headers=H,
        files={"file": ("a.csv", CSV, "text/csv")}), "판")

    rows = _data(client.get(
        f"/api/v1/data-preparation/instances/{inst['instance_id']}/snapshots",
        headers=H), "판 목록")["snapshots"]
    assert rows, "판이 하나도 없다"
    for r in rows:
        assert r["label"] and r["label"] != r["dataset_contract_key"], (
            f"계약키가 그대로 이름칸에 들어 있다: {r['dataset_contract_key']}")


def test_base_values_come_from_the_certified_file_not_from_the_user(client):
    """★★★ 화면이 7칸을 전부 사람에게 받고 있었다 — 그중 셋은 이미 인증된 판 안에 있다.

    ⚠️ 이 시험은 **실제 RAW 파일**을 지난다. 저장소가 원본을 보관하지 않거나 checksum
      대조가 빠지면 여기서 걸린다 — 단위 시험만으로는 그것을 볼 수 없다."""
    _seed_kits(client)
    inst = _data(client.post("/api/v1/data-preparation/instances", headers=H, json={
        "kit_id": kr.DEMO_KIT_ID, "version": "1.0.0",
        "scope_node_id": "n_pilot", "entity_mode": "REAL"}), "인스턴스")
    b = _data(client.post(
        f"/api/v1/data-preparation/instances/{inst['instance_id']}/bindings",
        headers=H, json={"dataset_contract_key": "material_arrivals",
                         "provider": "FILE_SNAPSHOT",
                         "config": {"file_name": "a.csv", "column_map": {"a": "A"}}}),
        "결속")
    for action in ("validate", "approve", "activate"):
        client.post(f"/api/v1/data-preparation/bindings/{b['binding_id']}/decision",
                    headers=H, json={"action": action})
    snap = _data(client.post(
        f"/api/v1/data-preparation/bindings/{b['binding_id']}/snapshots", headers=H,
        files={"file": ("a.csv", CSV, "text/csv")}), "판")
    _data(client.post(
        f"/api/v1/data-preparation/snapshots/{snap['snapshot_id']}/certify",
        headers=H, json={"control": CONTROL}), "인증")

    got = _data(client.post("/api/v1/baseline/base-values", headers=H, json={
        "instance_id": inst["instance_id"],
        "snapshot_ids": [snap["snapshot_id"]]}), "기준값")
    by = {f["key"]: f for f in got["fields"]}

    #: ★ CSV 는 120 + 80 = 200 이고 08-01 ~ 08-05 는 5일이다.
    assert by["production_qty"]["value"] == 200.0
    assert by["period_days"]["value"] == 5.0
    assert by["production_qty"]["derived_from"] == [snap["snapshot_id"]], (
        "어느 판에서 뽑았는지가 안 남았다")

    #: ★★★ 계약에 없는 것은 **0이 아니라 없음**이다.
    for k in ("ending_cash", "operating_profit", "power_cost"):
        assert by[k]["value"] is None, f"{k} 를 지어냈다"
        assert by[k]["reason"].strip()
    assert got["manual_count"] >= 4


def test_base_values_refuse_when_the_stored_original_changed(client, tmp_path):
    """★★★ 보관된 원본이 인증 당시와 다르면 **그 판에서 값을 뽑지 않는다.**

    ⚠️ checksum 대조 없이 읽으면 「인증한 판에서 뽑았다」는 말이 거짓이 될 수 있다."""
    import os

    _seed_kits(client)
    inst = _data(client.post("/api/v1/data-preparation/instances", headers=H, json={
        "kit_id": kr.DEMO_KIT_ID, "version": "1.0.0",
        "scope_node_id": "n_pilot", "entity_mode": "REAL"}), "인스턴스")
    b = _data(client.post(
        f"/api/v1/data-preparation/instances/{inst['instance_id']}/bindings",
        headers=H, json={"dataset_contract_key": "material_arrivals",
                         "provider": "FILE_SNAPSHOT",
                         "config": {"file_name": "a.csv", "column_map": {"a": "A"}}}),
        "결속")
    for action in ("validate", "approve", "activate"):
        client.post(f"/api/v1/data-preparation/bindings/{b['binding_id']}/decision",
                    headers=H, json={"action": action})
    snap = _data(client.post(
        f"/api/v1/data-preparation/bindings/{b['binding_id']}/snapshots", headers=H,
        files={"file": ("a.csv", CSV, "text/csv")}), "판")
    _data(client.post(
        f"/api/v1/data-preparation/snapshots/{snap['snapshot_id']}/certify",
        headers=H, json={"control": CONTROL}), "인증")

    #: ★ 대조군 — 손대기 전에는 뽑힌다. 이것이 없으면 「원래 안 되는 것」을 통제로 읽는다.
    ok = client.post("/api/v1/baseline/base-values", headers=H, json={
        "instance_id": inst["instance_id"], "snapshot_ids": [snap["snapshot_id"]]})
    assert ok.status_code == 200, ok.text[:200]

    full = _data(client.get(
        f"/api/v1/data-preparation/snapshots/{snap['snapshot_id']}", headers=H), "판")
    path = full["raw_path"]
    assert os.path.exists(path), f"원본이 보관돼 있지 않다: {path}"
    with open(path, "ab") as f:
        f.write(b"2026-08-09,M3,999,L-999\n")     # ⚠️ 보관된 원본을 바꾼다

    r = client.post("/api/v1/baseline/base-values", headers=H, json={
        "instance_id": inst["instance_id"], "snapshot_ids": [snap["snapshot_id"]]})
    assert r.status_code == 409, "바뀐 원본에서 값을 뽑았다: " + r.text[:200]
    assert "인증 당시와 다릅니다" in r.text


def test_the_reason_for_a_missing_dataset_names_it_for_people(client):
    """★★★ 유도 실패 사유는 **사용자 화면에 그대로 나간다.**

    ⚠️ 「«purchase_orders» 의 인증된 판이 없습니다」는 경영 화면의 문장이 아니다 —
      읽는 사람은 그것이 무엇인지 모른 채 넘긴다(설계 §12). 동선 스크립트가 실제로
      이것을 잡았다(2026-08-19)."""
    _seed_kits(client)
    inst = _data(client.post("/api/v1/data-preparation/instances", headers=H, json={
        "kit_id": kr.DEMO_KIT_ID, "version": "1.0.0",
        "scope_node_id": "n_pilot", "entity_mode": "REAL"}), "인스턴스")
    b = _data(client.post(
        f"/api/v1/data-preparation/instances/{inst['instance_id']}/bindings",
        headers=H, json={"dataset_contract_key": "material_arrivals",
                         "provider": "FILE_SNAPSHOT",
                         "config": {"file_name": "a.csv", "column_map": {"a": "A"}}}),
        "결속")
    for action in ("validate", "approve", "activate"):
        client.post(f"/api/v1/data-preparation/bindings/{b['binding_id']}/decision",
                    headers=H, json={"action": action})
    snap = _data(client.post(
        f"/api/v1/data-preparation/bindings/{b['binding_id']}/snapshots", headers=H,
        files={"file": ("a.csv", CSV, "text/csv")}), "판")
    _data(client.post(
        f"/api/v1/data-preparation/snapshots/{snap['snapshot_id']}/certify",
        headers=H, json={"control": CONTROL}), "인증")

    got = _data(client.post("/api/v1/baseline/base-values", headers=H, json={
        "instance_id": inst["instance_id"],
        "snapshot_ids": [snap["snapshot_id"]]}), "기준값")
    reasons = " ".join(f["reason"] for f in got["fields"])
    for key in ("purchase_orders", "material_arrivals", "supplier_master"):
        assert key not in reasons, f"계약키가 사유 문장에 나왔다: {key} / {reasons[:200]}"
    #: ★ 대신 **계약이 선언한 이름**이 있어야 한다.
    #: ⚠️ 이름을 시험에 손으로 적지 않는다 — 계약이 이름을 바꾸면 시험이 조용히
    #:   다른 것을 검증하게 된다(실제로 「구매주문」이라 적었다가 계약의 「구매 발주」와
    #:   어긋났다).
    kit = _data(client.get(
        f"/api/v1/data-preparation/kits/{kr.DEMO_KIT_ID}/versions/1.0.0", headers=H),
        "키트")
    want = [d["label"] for d in (kit.get("profile") or {}).get("datasets", [])
            if d["dataset_contract_key"] == "purchase_orders"][0]
    assert want and want in reasons, f"계약이 선언한 이름 «{want}» 이 사유에 없다: {reasons[:200]}"
