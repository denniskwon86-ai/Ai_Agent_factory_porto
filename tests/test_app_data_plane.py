"""★★★ [트랙 I] 생성 앱 데이터 평면 — **저장이 되기 시작하는 지점의 계약을 고정한다.**

설계: `docs/design_app_data_plane_2026-08-08.md`

## 여기서 고정하는 가장 무거운 계약 셋

1. **감사 구분**(§6) — 데이터셋 «구조 변경» 은 원장에 남고, 레코드 단위 변경은 남지 않는다.
   ⚠️ 이 구분이 무너지는 방향은 둘 다 나쁘다. 레코드마다 원장을 쓰면 2,457건짜리 결정 이력이
   업무 로그에 파묻히고, 구조 변경을 안 남기면 «누가 이 앱의 필드를 지웠나» 에 답할 수 없다.

2. **식별 없는 쓰기 금지**(§5-2) — 트랙 H 가 「식별만으로 열리는 쓰기」 65건을 봉합했다.
   여기서 「식별조차 없는 쓰기」를 새로 만들면 그 작업이 통째로 무효가 된다.

3. **선언에 없는 필드 거부**(§4-1) — 「그냥 넣는다」로 두면 스키마가 의미를 잃고, I-5 카탈로그
   등재가 «이 앱은 이런 필드를 갖는다» 고 거짓을 말하게 된다.
"""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
from api.deps import Principal, current_principal
from core.app_data import (MAX_PAYLOAD_BYTES, MAX_TEXT_LEN, AppDataError, AppDataService,
                           normalize_schema, validate_payload)
from core.app_data_store import AppDataStore
from core.org_directory import AccessScope

SCHEMA = {"fields": [
    {"name": "item_code", "type": "string", "required": True, "label": "자재코드"},
    {"name": "qty", "type": "number", "required": True, "label": "수량"},
    {"name": "received", "type": "boolean", "label": "입고완료"},
    {"name": "due_date", "type": "date", "label": "납기"},
    {"name": "note", "type": "text", "label": "비고"},
]}


@pytest.fixture
def svc(tmp_path):
    return AppDataService(store=AppDataStore(db_path=str(tmp_path / "app_data.db")))


def _ds(svc, **kw):
    args = dict(release_id="REL_OK", name="arrivals", schema=SCHEMA, actor_id="kim")
    args.update(kw)
    return svc.create_dataset(**args)


def _row(**kw):
    base = {"item_code": "RM-MHP-001", "qty": 12.5}
    base.update(kw)
    return base


# ══ 스키마 선언 ═══════════════════════════════════════════════════════════
def test_schema_accepts_bare_list():
    """★ 생성기가 `fields` 봉투를 빠뜨리는 것은 흔하다. 그때 «스키마가 비었다» 로 처리하면
    모든 필드가 거부되는 앱이 조용히 만들어진다."""
    out = normalize_schema([{"name": "a", "type": "string"}])
    assert [f["name"] for f in out["fields"]] == ["a"]


def test_schema_rejects_empty():
    with pytest.raises(AppDataError, match="비어 있지 않은"):
        normalize_schema({"fields": []})


def test_schema_rejects_reserved_field_names():
    """★★ `created_by` 를 앱 필드로 허용하면 **감사 표시를 앱이 덮어쓸 수 있다.**

    화면에는 «누가 만들었나» 가 두 개가 되고, 그중 하나는 앱이 자유롭게 쓰는 값이다."""
    with pytest.raises(AppDataError, match="예약된 이름"):
        normalize_schema({"fields": [{"name": "created_by", "type": "string"}]})


def test_schema_rejects_duplicate_and_unknown_type():
    with pytest.raises(AppDataError, match="중복"):
        normalize_schema({"fields": [{"name": "a"}, {"name": "a"}]})
    with pytest.raises(AppDataError, match="type"):
        normalize_schema({"fields": [{"name": "a", "type": "money"}]})


# ══ 값 검증 ═══════════════════════════════════════════════════════════════
def test_unknown_field_is_rejected():
    """★★★ 선언에 없는 키를 받아 주면 스키마가 의미를 잃는다(§4-1)."""
    with pytest.raises(AppDataError, match="선언되지 않은"):
        validate_payload(SCHEMA, _row(hacked="x"))


def test_required_missing_is_rejected():
    with pytest.raises(AppDataError, match="필수"):
        validate_payload(SCHEMA, {"qty": 1})


def test_boolean_is_not_a_number():
    """★★ 파이썬에서 `bool` 은 `int` 의 하위형이다. 먼저 걸러내지 않으면 `True` 가 수량 1 로
    저장되고, 나중에 합계를 내면 아무도 원인을 못 찾는다."""
    with pytest.raises(AppDataError, match="숫자"):
        validate_payload(SCHEMA, _row(qty=True))


def test_numeric_string_is_rejected_not_coerced():
    """★ 「"3" 을 3 으로 받아 준다」는 관용은 입력 경로마다 타입이 달라지게 만든다."""
    with pytest.raises(AppDataError, match="숫자"):
        validate_payload(SCHEMA, _row(qty="3"))


def test_bad_date_is_rejected():
    with pytest.raises(AppDataError, match="ISO 날짜"):
        validate_payload(SCHEMA, _row(due_date="2026년 8월 8일"))


def test_oversized_single_field_is_rejected():
    with pytest.raises(AppDataError, match="최대 길이"):
        validate_payload(SCHEMA, _row(note="가" * (MAX_TEXT_LEN + 1)))


def test_single_max_field_still_fits_in_a_record():
    """★★ 두 한계는 **서로 정합해야 한다.**

    초판은 `MAX_TEXT_LEN`(100,000자 = 한글 300KB) > `MAX_PAYLOAD_BYTES`(256KB) 라서,
    길이 제한 안의 값이 크기 제한으로 거부되는 구간이 있었다 — 사용자에게는 원인을 알 수 없는
    거부다. 정합성을 여기서 고정한다."""
    out = validate_payload(SCHEMA, _row(note="가" * MAX_TEXT_LEN))
    assert len(out["note"]) == MAX_TEXT_LEN


def test_oversized_payload_across_fields_is_rejected():
    """총량 제한은 **여러 필드의 합계**로 걸린다."""
    schema = {"fields": [{"name": f"t{i}", "type": "text"} for i in range(8)]}
    big = {f"t{i}": "가" * MAX_TEXT_LEN for i in range(8)}
    with pytest.raises(AppDataError, match="최대 크기"):
        validate_payload(normalize_schema(schema), big)


# ══ 데이터셋 ══════════════════════════════════════════════════════════════
def test_create_dataset_requires_actor(svc):
    """귀속 없는 데이터셋은 «이 데이터는 누구 책임인가» 에 답할 수 없다."""
    with pytest.raises(AppDataError, match="주체"):
        _ds(svc, actor_id="")


def test_dataset_name_is_unique_per_release(svc):
    _ds(svc)
    with pytest.raises(AppDataError, match="이미 있습니다"):
        _ds(svc)


def test_same_name_in_another_release_is_fine(svc):
    _ds(svc)
    other = _ds(svc, release_id="REL_OTHER")
    assert other["release_id"] == "REL_OTHER"


def test_find_dataset_is_scoped_by_release(svc):
    """★★★ 앱은 이름만 말한다(§7 규칙 4). 릴리스가 다르면 **찾히지 않아야** 한다 —
    이것이 «앱이 남의 데이터를 읽는» 경로를 원천 차단하는 지점이다."""
    _ds(svc)
    assert svc.find_dataset("REL_OK", "arrivals") is not None
    assert svc.find_dataset("REL_EVIL", "arrivals") is None


def test_retire_keeps_records(svc):
    """★ 폐지는 레코드를 지우지 않는다 — 물리 삭제하면 원장이 가리키는 대상이 사라진다."""
    ds = _ds(svc)
    svc.create_record(ds["dataset_id"], _row(), actor_id="kim")
    svc.retire_dataset(ds["dataset_id"], actor_id="kim")
    assert svc.count_records(ds["dataset_id"]) == 1
    with pytest.raises(AppDataError, match="폐지된"):
        svc.create_record(ds["dataset_id"], _row(), actor_id="kim")


def test_schema_change_reports_removed_fields(svc):
    """⚠️ 필드 제거는 기존 레코드의 값을 화면에서 사라지게 한다. 조용히 하지 않는다."""
    ds = _ds(svc)
    out = svc.update_schema(ds["dataset_id"],
                            {"fields": [{"name": "item_code", "required": True},
                                        {"name": "lot", "type": "string"}]},
                            actor_id="kim")
    assert set(out["removed_fields"]) == {"qty", "received", "due_date", "note"}
    assert out["added_fields"] == ["lot"]


# ══ 레코드 ════════════════════════════════════════════════════════════════
def test_record_roundtrip_and_attribution(svc):
    ds = _ds(svc)
    rec = svc.create_record(ds["dataset_id"], _row(note="긴급"), actor_id="kim")
    assert rec["payload"]["item_code"] == "RM-MHP-001"
    assert rec["created_by"] == "kim"          # 귀속은 봉투에 남는다(원장이 아니라)
    assert rec["deleted"] is False


def test_optional_fields_are_filled_with_none(svc):
    """선언된 필드는 값이 없어도 키가 있어야 한다 — 화면이 «필드가 없다» 와 «값이 없다» 를
    구분할 수 있어야 한다."""
    ds = _ds(svc)
    rec = svc.create_record(ds["dataset_id"], _row(), actor_id="kim")
    assert rec["payload"]["note"] is None and "received" in rec["payload"]


def test_partial_update_cannot_bypass_required(svc):
    """★★ 부분 수정 경로로 필수를 우회할 수 있으면 그 제약은 없는 것과 같다."""
    ds = _ds(svc)
    rec = svc.create_record(ds["dataset_id"], _row(), actor_id="kim")
    with pytest.raises(AppDataError, match="필수"):
        svc.update_record(rec["record_id"], {"item_code": ""}, actor_id="lee")


def test_partial_update_keeps_untouched_fields(svc):
    ds = _ds(svc)
    rec = svc.create_record(ds["dataset_id"], _row(note="원본"), actor_id="kim")
    out = svc.update_record(rec["record_id"], {"qty": 99}, actor_id="lee")
    assert out["payload"]["note"] == "원본" and out["payload"]["qty"] == 99
    assert out["updated_by"] == "lee" and out["created_by"] == "kim"


def test_delete_is_logical_and_hides_from_list(svc):
    """★ 물리 삭제는 제공하지 않는다(§4-2)."""
    ds = _ds(svc)
    rec = svc.create_record(ds["dataset_id"], _row(), actor_id="kim")
    svc.delete_record(rec["record_id"], actor_id="kim")
    rows, total = svc.list_records(ds["dataset_id"])
    assert rows == [] and total == 0
    rows2, total2 = svc.list_records(ds["dataset_id"], include_deleted=True)
    assert total2 == 1 and rows2[0]["deleted_by"] == "kim"
    with pytest.raises(AppDataError, match="삭제된"):
        svc.update_record(rec["record_id"], {"qty": 1}, actor_id="kim")


def test_list_reports_total_separately_from_page(svc):
    """★★ 화면이 `len(rows)` 를 «전부» 로 읽으면, 상한에 걸린 순간 사용자는 «우리 데이터는
    이게 전부» 로 믿는다. 목록 길이와 총계는 다른 값이다."""
    ds = _ds(svc)
    for i in range(5):
        svc.create_record(ds["dataset_id"], _row(item_code=f"C{i}"), actor_id="kim")
    rows, total = svc.list_records(ds["dataset_id"], limit=2)
    assert len(rows) == 2 and total == 5


def test_import_does_not_create_the_database(tmp_path):
    """import 부작용으로 DB 를 만들면 테스트가 경로를 바꿔치기할 틈이 없다."""
    p = tmp_path / "never.db"
    AppDataStore(db_path=str(p))
    assert not p.exists()


# ══ 라우트 — 권한과 감사 ══════════════════════════════════════════════════
@pytest.fixture
def client(tmp_path, monkeypatch):
    """실물 라우터 + tmp 저장소. 사용자는 의존성 오버라이드로 바꾼다."""
    import api.deps as deps
    import api.routes.app_data_control as adc

    svc = AppDataService(store=AppDataStore(db_path=str(tmp_path / "route.db")))
    monkeypatch.setattr(adc, "app_data_service", svc, raising=False)

    ledger: list = []
    monkeypatch.setattr(adc, "_ledger",
                        lambda ev, did, actor, decision="", rationale="", evidence=None,
                        tenant_id="", scope="": ledger.append(
                            {"event": ev, "dataset_id": did, "actor": actor}),
                        raising=False)

    # 권한 강제를 켠다 — 꺼진 상태에서는 판정 함수가 아무것도 막지 않으므로(하위호환 계약)
    # 이 테스트가 조용히 무의미해진다.
    monkeypatch.setattr(config, "ORG_ENFORCE", True, raising=False)
    owners = {"REL_OK": {"dept_id": "hq", "owner_user_id": ""},
              "REL_SIBLING": {"dept_id": "hq", "owner_user_id": ""},   # 같은 부서의 다른 앱
              "REL_OTHER": {"dept_id": "finance", "owner_user_id": ""}}
    monkeypatch.setattr(deps.org_directory, "get_ownership",
                        lambda kind, rid: owners.get(rid) if kind == "release" else None,
                        raising=False)
    # ★ 관문 A(`visibility_block_reason`)는 **등록된 사용자**만 통과시킨다. 그것을 끄지 않고
    #   사용자를 등록해서 넘는다 — 끄면 이 파일의 권한 테스트가 그 관문을 검증하지 못한다.
    users = {"kim": {"user_id": "kim", "status": "active"},
             "lee": {"user_id": "lee", "status": "active"}}
    monkeypatch.setattr(deps.org_directory, "get_user",
                        lambda uid: users.get((uid or "").strip()), raising=False)

    app = FastAPI()
    app.include_router(adc.router)
    state = {"uid": "kim", "read": {"hq"}, "write": {"hq"}}

    def _principal():
        return Principal(user_id=state["uid"],
                         scope=AccessScope(user_id=state["uid"], unrestricted=False,
                                           readable_dept_ids=frozenset(state["read"]),
                                           writable_dept_ids=frozenset(state["write"])))
    app.dependency_overrides[current_principal] = _principal
    c = TestClient(app)
    c.state = state
    c.ledger = ledger
    c.svc = svc
    return c


def _mkds(c, **kw):
    body = {"release_id": "REL_OK", "name": "arrivals", "schema": SCHEMA}
    body.update(kw)
    return c.post("/api/v1/appdata/datasets", json=body)


def test_schema_alias_survives_pydantic_v2(client):
    """★★ `class Config: fields` 는 pydantic v2 에서 **조용히 무시된다.** 별칭이 죽으면
    생성기가 보낸 `schema` 가 버려지고 «필드 선언이 없다» 로 거부되는데, 오류 메시지가
    원인을 가리키지 않아 아무도 못 찾는다. 별칭이 살아 있는지 여기서 고정한다."""
    r = _mkds(client)
    assert r.status_code == 200, r.text
    assert len(r.json()["schema"]["fields"]) == 5


def test_anonymous_cannot_write(client):
    """★★★ 트랙 H 계승 — 식별조차 없는 쓰기를 새로 만들지 않는다."""
    client.state["uid"] = ""
    assert _mkds(client).status_code == 401


def test_anonymous_write_is_blocked_on_every_write_route(client):
    """★ 라우트 하나만 막으면 나머지가 뒷문이 된다. **쓰기 전 경로**를 확인한다."""
    ds = _mkds(client).json()
    rec = client.post(f"/api/v1/appdata/datasets/{ds['dataset_id']}/records",
                      json={"payload": _row()}).json()
    client.state["uid"] = ""
    calls = [
        client.post(f"/api/v1/appdata/datasets/{ds['dataset_id']}/records",
                    json={"payload": _row()}),
        client.put(f"/api/v1/appdata/records/{rec['record_id']}", json={"payload": {"qty": 1}}),
        client.delete(f"/api/v1/appdata/records/{rec['record_id']}"),
        client.put(f"/api/v1/appdata/datasets/{ds['dataset_id']}/schema",
                   json={"schema": SCHEMA}),
        client.delete(f"/api/v1/appdata/datasets/{ds['dataset_id']}"),
    ]
    assert [r.status_code for r in calls] == [401] * 5


def test_cannot_write_to_another_department_app(client):
    """★★ 남의 부서 앱의 데이터에 쓸 수 없다."""
    r = _mkds(client, release_id="REL_OTHER")
    assert r.status_code == 403


def test_can_read_but_not_write_when_only_readable(client):
    """★ 읽기와 쓰기는 다르다 — 볼 수 있다고 바꿀 수 있는 것이 아니다."""
    ds = _mkds(client).json()
    client.state["write"] = set()          # 읽기만 남긴다
    assert client.get(f"/api/v1/appdata/datasets/{ds['dataset_id']}").status_code == 200
    assert client.post(f"/api/v1/appdata/datasets/{ds['dataset_id']}/records",
                       json={"payload": _row()}).status_code == 403


# ── 감사 구분 (§6) ────────────────────────────────────────────────────────
def test_dataset_structure_changes_are_audited(client):
    """★★★ 구조 변경은 원장에 남는다 — «누가 이 앱의 필드를 지웠나» 에 답해야 한다."""
    ds = _mkds(client).json()
    client.put(f"/api/v1/appdata/datasets/{ds['dataset_id']}/schema",
               json={"schema": {"fields": [{"name": "item_code", "required": True}]}})
    client.delete(f"/api/v1/appdata/datasets/{ds['dataset_id']}")
    assert [e["event"] for e in client.ledger] == [
        "APP_DATASET_CREATED", "APP_DATASET_SCHEMA_CHANGED", "APP_DATASET_RETIRED"]
    assert all(e["actor"] == "kim" for e in client.ledger)


def test_record_writes_are_not_audited_to_the_ledger(client):
    """★★★ 레코드마다 원장을 쓰면 2,457건짜리 **결정 이력이 업무 로그에 파묻힌다**(§6).

    귀속은 사라지지 않는다 — `created_by`/`updated_by`/`deleted_by` 가 레코드에 남는다."""
    ds = _mkds(client).json()
    client.ledger.clear()
    rec = client.post(f"/api/v1/appdata/datasets/{ds['dataset_id']}/records",
                      json={"payload": _row()}).json()
    client.put(f"/api/v1/appdata/records/{rec['record_id']}", json={"payload": {"qty": 3}})
    client.delete(f"/api/v1/appdata/records/{rec['record_id']}")
    assert client.ledger == []                       # 원장에는 없고
    row = client.svc.get_record(rec["record_id"])
    assert row["created_by"] == "kim" and row["deleted_by"] == "kim"   # 레코드에는 있다


def test_ledger_subject_type_is_app_dataset():
    """릴리스로 뭉개면 «이 릴리스가 어떻게 됐나» 와 «이 앱의 데이터» 를 구분할 수 없다."""
    from core.decision_ledger import EVENT_TYPES, SUBJECT_TYPES
    assert "app_dataset" in SUBJECT_TYPES
    for ev in ("APP_DATASET_CREATED", "APP_DATASET_SCHEMA_CHANGED", "APP_DATASET_RETIRED"):
        assert ev in EVENT_TYPES


# ── personal 앱 격리 ──────────────────────────────────────────────────────
def test_personal_app_data_is_not_visible_to_others(client):
    """★★ 개인용 앱이 부서 공유물이 되면, 사용자가 그렇게 알고 만든 것이 아니게 된다."""
    ds = _mkds(client, name="memo", app_class="personal").json()
    client.state["uid"] = "lee"            # 같은 부서의 다른 사람
    assert client.get(f"/api/v1/appdata/datasets/{ds['dataset_id']}").status_code == 403
    listed = client.get("/api/v1/appdata/datasets?release_id=REL_OK").json()
    assert [d["name"] for d in listed["datasets"]] == []      # 목록에서는 조용히 감춘다


def test_departmental_app_is_shared_within_department(client):
    """★ 반대로 부서 앱은 같은 부서 사람에게 보여야 한다 — 격리가 과하면 협업이 죽는다."""
    ds = _mkds(client, app_class="departmental").json()
    client.state["uid"] = "lee"
    assert client.get(f"/api/v1/appdata/datasets/{ds['dataset_id']}").status_code == 200


def test_by_name_lookup_does_not_leak_across_releases(client):
    """★★★ 앱이 이름만 말하는 구조의 서버 쪽 절반(§7 규칙 4).

    ⚠️ 대상은 **읽을 수 있는** 다른 릴리스여야 한다(같은 부서 `REL_SIBLING`). 못 읽는
      릴리스로 시험하면 부서 권한에서 먼저 걸려 «이름 격리» 를 검증하지 못한다 — 통제 두 개가
      겹칠 때 뒤엣것이 검증됐다고 믿는 흔한 착시다."""
    _mkds(client)
    r = client.get("/api/v1/appdata/datasets/by-name?release_id=REL_SIBLING&name=arrivals")
    assert r.status_code == 404, "같은 부서라도 다른 앱의 데이터셋은 이름으로 찾히면 안 된다"
    ok = client.get("/api/v1/appdata/datasets/by-name?release_id=REL_OK&name=arrivals")
    assert ok.status_code == 200


def test_cannot_read_another_department_app(client):
    """부서 통제는 그것대로 따로 확인한다(위 테스트와 겹치지 않게)."""
    assert client.get(
        "/api/v1/appdata/datasets?release_id=REL_OTHER").status_code == 403


def test_record_list_exposes_truncation(client):
    """★ 잘렸다는 사실을 응답이 스스로 말한다."""
    ds = _mkds(client).json()
    for i in range(3):
        client.post(f"/api/v1/appdata/datasets/{ds['dataset_id']}/records",
                    json={"payload": _row(item_code=f"C{i}")})
    body = client.get(
        f"/api/v1/appdata/datasets/{ds['dataset_id']}/records?limit=2").json()
    assert body["count"] == 2 and body["total"] == 3 and body["truncated"] is True


def test_bad_payload_is_400_with_reason(client):
    """검증 실패는 500 이 아니라 **고칠 수 있는 400** 이어야 한다."""
    ds = _mkds(client).json()
    r = client.post(f"/api/v1/appdata/datasets/{ds['dataset_id']}/records",
                    json={"payload": {"item_code": "A", "qty": 1, "ghost": 1}})
    assert r.status_code == 400 and "선언되지 않은" in r.json()["detail"]
