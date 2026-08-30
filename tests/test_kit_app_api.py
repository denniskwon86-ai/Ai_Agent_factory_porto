"""★★★ 「키트로 앱 생성」 **API 종단.** (2026-08-23)

## 이 파일이 존재하는 이유

`kit_app_builder`·`kit_app_contract` 로 통제는 전부 섰다. 그런데 **제품에서 그것을
부를 방법이 없었다** — 준비도 보드는 `READY` 를 그리는데 누를 것이 없었다.
소유권 승인(4.1c-D)에서 이미 지적받은 「통제는 있는데 부르는 경로가 없다」와 같다.

그래서 여기서 고정하는 것은 **배선**이다(핵심 층은 `test_kit_app_contract.py` 가 한다):

    ① 세 경로가 실제로 초안·승인·물질화를 하는가
    ② **승인 권한이 라우트 층에서 갈리는가** — 만들 수 있는 사람 ≠ 승인할 수 있는 사람
    ③ 승인 없이 만들면 409 인가
    ④ 상태코드가 사실을 말하는가(4xx=고쳐라 · 503=사람이 정리하라)

## ★★★ 대조군을 먼저 세운다

⚠️ 조직 강제(`org_enforce`)를 켜지 않으면 `resolve_scope()` 가 **전원 무제한**을
  돌려주고, 그 상태에서 권한 시험은 전부 통과한다 — **아무것도 지키지 못한 채.**
"""
import pytest

#: ★★★ **자료가 들고 있는 값을 쓴다.** 내가 고른 값(`tenant_default`)을 쓰면
#:   `scope_index` 가 「tenant 이 원본과 다릅니다」로 막는다 — 옳은 거부다.
#: ⚠️ 시험 상수를 내 말로 정하면, 통과시키려고 그 통제를 끄고 싶어진다.
TENANT = "tenant-afs-demo-materials"
SCOPE = "plant-afs-smelting-01"
DEPT = "hq"
APP = "APP-01"

BUILDER = "builder@afs.invalid"        # project.run 만 — 만들 수 있다
APPROVER = "std@afs.invalid"           # is_data_admin — 승인할 수 있다


@pytest.fixture
def env(tmp_path, monkeypatch):
    """격리 저장소 + 격리 원장 + **실제 조직도**(강제 ON) + 인증된 정본 키트."""
    import core.org_directory as orgmod
    from core.data_preparation import store as dp
    from core.decision_ledger import decision_ledger
    from core.org_directory import OrgDirectory

    store = dp.data_preparation_store
    monkeypatch.setattr(store, "db_path", str(tmp_path / "dp.db"), raising=False)
    monkeypatch.setattr(store, "_prepared_for", None, raising=False)
    monkeypatch.setattr(decision_ledger, "db_path", str(tmp_path / "ledger.db"),
                        raising=False)

    #: ⚠️ `api.deps` 는 자기 모듈에 import 한 이름을 쓴다 — 두 곳을 함께 패치한다.
    import api.deps as deps
    org = OrgDirectory(db_path=str(tmp_path / "org.db"))
    org.create_department(DEPT, "본사", scope_node_id=SCOPE)
    org.upsert_user(APPROVER, "표준승인자", primary_dept_id=DEPT,
                    is_data_admin=True, actor="seed")
    org.upsert_user(BUILDER, "만드는사람", primary_dept_id=DEPT, actor="seed")
    org.set_user_roles(BUILDER, {DEPT: "manager"}, actor="seed")
    import core.scope_policy as sp
    monkeypatch.setattr(sp, "_read", lambda: {"org_enforce": True})
    monkeypatch.setattr(orgmod, "org_directory", org)
    monkeypatch.setattr(deps, "org_directory", org)

    #: 정본 키트를 심고 APP-01 이 요구하는 것만 인증까지 올린다.
    from core import demo_vertical_slice as dv
    from core.data_preparation import kit_registry, models as m
    from core.data_preparation import snapshot_service as svc

    dv.register_kit(store)
    inst = store.create_instance(
        kit_id=dv.KIT_ID, version=dv.KIT_VERSION,
        kit_fingerprint=dv.kit_fingerprint(store),
        tenant_id=TENANT, scope_node_id=SCOPE, entity_mode="REAL", label="api")
    kit = store.get_kit_version(dv.KIT_ID, dv.KIT_VERSION)
    needs = next(r["requires"] for r in kit_registry.outputs(kit.get("profile") or {})
                 if r["output"] == APP)
    for key in needs:
        rows, cols = dv.read_full(key)
        if not rows:
            continue
        b = store.create_binding(
            instance_id=inst["instance_id"], dataset_contract_key=key,
            provider=m.PROVIDER_FILE_SNAPSHOT, config={},
            tenant_id=TENANT, scope_node_id=SCOPE, entity_mode="REAL")
        for t in (m.VALIDATED, m.APPROVED, m.ACTIVE):
            b = store.transition(b["binding_id"], t)
        snap = svc.ingest(store, binding=b, payload=dv.csv_bytes(rows, cols),
                          file_name=f"{key}.csv", workspace_root=str(tmp_path / "raw"))
        svc.run_pipeline(store, snap["snapshot_id"], rows, cols,
                         control={"row_count": len(rows)})
    return {"store": store, "org": org, "ledger": decision_ledger,
            "instance_id": inst["instance_id"]}


@pytest.fixture(autouse=True)
def _ctx(monkeypatch):
    import api.routes.data_preparation_control as dpc
    monkeypatch.setattr(dpc, "viewing_context",
                        lambda p: {"tenant_id": TENANT, "entity_mode": "REAL",
                                   "scope_node_id": SCOPE})


def _client(env, user_id):
    """★★★ **실제 `resolve_scope()` 가 돌려주는 객체**를 쓴다 — 손으로 만들면
    판정기가 아니라 내가 답을 정한다(4.1c-B P1-1 에서 지적된 패턴)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import api.routes.data_preparation_control as dpc
    from api.deps import Principal, current_principal

    app = FastAPI()
    app.include_router(dpc.router)
    scope = env["org"].resolve_scope(user_id)
    app.dependency_overrides[current_principal] = lambda: Principal(
        user_id=user_id, scope=scope)
    return TestClient(app, raise_server_exceptions=False)


def _base(env):
    return f"/api/v1/data-preparation/instances/{env['instance_id']}/apps"


def _data(res):
    """★ 봉투를 벗긴다 — `{status, data}` 를 그대로 읽으면 `None` 이 나오고, 그 `None`
    로 「막혔다」고 결론 내린 적이 이 저장소에서 네 번 있었다."""
    assert res.status_code == 200, f"{res.status_code} {res.text[:400]}"
    body = res.json()
    assert body.get("status") == "success", body
    return body["data"]


# ── 대조군 ──────────────────────────────────────────────────────────────

def test_두_사람의_권한이_실제로_다르다(env):
    """★★★ **이 파일의 첫 시험.**

    ⚠️⚠️ 만드는 사람과 승인하는 사람이 같은 권한을 갖고 있으면, 아래 직무 분리
      시험들은 전부 초록인 채 **아무것도 지키지 못한다.** 「막혔다」를 세기 전에
      두 배역이 정말 다른지 본다."""
    a = env["org"].resolve_scope(APPROVER)
    b = env["org"].resolve_scope(BUILDER)
    assert a.can_manage_standard is True
    assert b.can_manage_standard is False, "만드는 사람이 승인 권한을 갖고 있다"


# ── ① 목록 ──────────────────────────────────────────────────────────────

def test_목록이_준비도와_계약_상태를_한_줄에_싣는다(env):
    c = _client(env, BUILDER)
    rows = _data(c.get(_base(env)))["apps"]
    row = next(r for r in rows if r["app_id"] == APP)
    assert row["readiness_state"], "준비도 상태가 비었다"
    #: ★ 계약이 아직 없다 — **`null` 이지 빈 문자열이 아니다.** 「없음」과 「초안」은
    #:   다른 사실이고, 뭉개면 화면이 다음 할 일을 말할 수 없다.
    assert row["contract_status"] is None
    assert row["contract_revision"] is None


# ── ② 초안 ──────────────────────────────────────────────────────────────

def test_초안을_만들면_승인_대기_상태다(env):
    c = _client(env, BUILDER)
    out = _data(c.post(f"{_base(env)}/{APP}/contract", json={"app_class": "departmental"}))
    assert out["status"] == "DRAFT"
    assert out["drafted_by"] == BUILDER
    assert out["approved_by"] == ""
    #: ★ 필드가 인증판에서 왔는지 — 비어 있으면 정본 스키마가 막았을 것이다.
    assert sum(len(d["fields"]) for d in out["contract"]["datasets"]) > 0


def test_app_class_를_안_주면_거부한다(env):
    """⚠️ 추측한 분류는 나중에 **권한 판단의 근거**로 쓰인다."""
    c = _client(env, BUILDER)
    res = c.post(f"{_base(env)}/{APP}/contract", json={})
    assert res.status_code == 422, res.text[:300]
    assert "app_class" in res.text


def test_키트에_없는_산출물은_404(env):
    c = _client(env, BUILDER)
    res = c.post(f"{_base(env)}/APP-99/contract", json={"app_class": "departmental"})
    assert res.status_code == 404


# ── ③ 승인 ──────────────────────────────────────────────────────────────

def test_만드는_사람은_승인_경로를_지나지_못한다(env):
    """★★★ 직무 분리가 **라우트 층에서** 갈린다."""
    c = _client(env, BUILDER)
    d = _data(c.post(f"{_base(env)}/{APP}/contract", json={"app_class": "departmental"}))
    res = c.post(f"{_base(env)}/{APP}/contract/approve",
                 json={"revision": d["revision"], "rationale": "내가 승인"})
    assert res.status_code == 403, res.text[:300]

    #: ★ 그리고 상태는 그대로여야 한다 — 막혔다고 말하면서 올라가 있으면 최악이다.
    from core import kit_app_contract as kac
    assert kac.approved(env["store"], env["instance_id"], APP) is None


def test_다른_사람이_승인하면_원장_사건이_남는다(env):
    d = _data(_client(env, BUILDER).post(f"{_base(env)}/{APP}/contract",
                                         json={"app_class": "departmental"}))
    out = _data(_client(env, APPROVER).post(
        f"{_base(env)}/{APP}/contract/approve",
        json={"revision": d["revision"], "rationale": "원료 도입계획 추적 화면 개설"}))
    assert out["status"] == "APPROVED"
    assert out["approved_by"] == APPROVER
    assert out["ledger_event_id"]

    #: ★ 원장에서 실제로 조회되는가 — 응답만 보고 끝내지 않는다.
    #: ★ **무결성 검사가 있는 쪽**으로 읽는다 — `get_event_strict` 는 사슬을 확인한다.
    ev = env["ledger"].get_event_strict(out["ledger_event_id"])
    assert ev and ev["event_type"] == "APP_CONTRACT_APPROVED"
    #: ★ 대상은 **계약 지문**이다 — 앱 이름이 아니다(「같은 이름 다른 계약」 방지).
    assert ev["subject_id"] == out["semantic_fingerprint"]
    assert ev["subject_type"] == "app_contract"


def test_근거_없는_승인은_422(env):
    d = _data(_client(env, BUILDER).post(f"{_base(env)}/{APP}/contract",
                                         json={"app_class": "departmental"}))
    res = _client(env, APPROVER).post(f"{_base(env)}/{APP}/contract/approve",
                                      json={"revision": d["revision"], "rationale": " "})
    assert res.status_code == 422
    assert "근거" in res.text


def test_원장이_죽으면_503_이고_상태는_그대로다(env, monkeypatch):
    """⚠️ 409·422 로 답하면 「입력을 고쳐 다시 하라」로 읽힌다 — 사람이 정리할 상태다."""
    from core.decision_ledger import decision_ledger

    d = _data(_client(env, BUILDER).post(f"{_base(env)}/{APP}/contract",
                                         json={"app_class": "departmental"}))
    monkeypatch.setattr(decision_ledger, "append",
                        lambda **kw: (_ for _ in ()).throw(RuntimeError("down")))
    res = _client(env, APPROVER).post(
        f"{_base(env)}/{APP}/contract/approve",
        json={"revision": d["revision"], "rationale": "개설"})
    assert res.status_code == 503, res.text[:300]

    from core import kit_app_contract as kac
    assert kac.approved(env["store"], env["instance_id"], APP) is None


# ── ④ 물질화 ────────────────────────────────────────────────────────────

def test_승인_없이_만들면_409(env):
    """★★★ 「일부라도 열어 주자」가 위험하다 — 열린 앱은 **빈 화면**을 보여 주고,
    사용자는 그것을 「우리 회사에 자료가 없다」로 읽는다."""
    _data(_client(env, BUILDER).post(f"{_base(env)}/{APP}/contract",
                                     json={"app_class": "departmental"}))
    res = _client(env, BUILDER).post(f"{_base(env)}/{APP}/build")
    assert res.status_code == 409, res.text[:300]
    assert "승인" in res.text


def test_승인된_계약으로_실제_앱이_만들어진다(env):
    """★★★ **여정의 빈 칸이 열렸는지.** 조각의 합이 아니라 관통이다."""
    d = _data(_client(env, BUILDER).post(f"{_base(env)}/{APP}/contract",
                                         json={"app_class": "departmental"}))
    _data(_client(env, APPROVER).post(
        f"{_base(env)}/{APP}/contract/approve",
        json={"revision": d["revision"], "rationale": "개설"}))
    out = _data(_client(env, BUILDER).post(f"{_base(env)}/{APP}/build"))

    from core import kit_app_builder as kb
    assert out["release_id"] == kb.release_id_for(env["instance_id"], APP)
    assert len(out["datasets"]) == len(d["contract"]["datasets"])
    #: ★ 이름은 문법에 맞게 접혀 있다 — 계약키를 그대로 쓰지 않는다.
    assert all("-" not in n and n == n.lower() for n in out["datasets"])

    #: ★★★ 목록이 그 사실을 그대로 말하는가 — 화면이 보는 것은 이 응답이다.
    rows = _data(_client(env, BUILDER).get(_base(env)))["apps"]
    row = next(r for r in rows if r["app_id"] == APP)
    assert row["contract_status"] == "APPROVED"
    assert row["approved_by"] == APPROVER
    #: ⚠️⚠️ [2026-08-23 실측] 종전에는 여기까지였다. 그래서 「앱 만들기」가 200 을
    #:   받아도 목록은 **아무 변화가 없었고**, 화면은 눌리지 않은 것처럼 보였다.
    assert row["release_id"] == kb.release_id_for(env["instance_id"], APP)
    assert row["built_datasets"] == len(out["datasets"]), row


def test_만들기_전에는_만들어지지_않았다고_말한다(env):
    """★ 대조군 — 「만들어졌다」가 늘 참이면 그 칸은 아무것도 말하지 않는다."""
    d = _data(_client(env, BUILDER).post(f"{_base(env)}/{APP}/contract",
                                         json={"app_class": "departmental"}))
    _data(_client(env, APPROVER).post(
        f"{_base(env)}/{APP}/contract/approve",
        json={"revision": d["revision"], "rationale": "개설"}))
    rows = _data(_client(env, BUILDER).get(_base(env)))["apps"]
    row = next(r for r in rows if r["app_id"] == APP)
    assert row["built_datasets"] == 0, row


def test_남의_인스턴스는_404(env):
    """★ 없는 것과 못 보는 것을 **같은 404** 로 — 다르게 답하면 존재를 알려 준다."""
    c = _client(env, BUILDER)
    res = c.post(f"/api/v1/data-preparation/instances/ki_nope/apps/{APP}/contract",
                 json={"app_class": "departmental"})
    assert res.status_code == 404


# ── 운영 승격 ────────────────────────────────────────────────────────────
#
# ⚠️⚠️ [2026-08-24 실측] 여기까지가 또 빈 칸이었다. 앱을 만들면 데이터셋은 **시연
#   평면**에 물질화되고, 그 상태의 앱을 열면 표만 보이고 **레코드가 0** 이다.
#   실제 업무 데이터를 읽으려면 운영으로 올려야 하는데 부를 경로가 없었다.
#
# ★★★ 승격은 `factory_control` 과 **같은 `release_promotion.promote()`** 를 쓴다 —
#   다섯 관문을 그대로 본다. 면제를 만들면 그 면제가 곧 게이트의 구멍이다.

def _approve_and_build(env, app_id=APP):
    d = _data(_client(env, BUILDER).post(f"{_base(env)}/{app_id}/contract",
                                         json={"app_class": "departmental"}))
    _data(_client(env, APPROVER).post(
        f"{_base(env)}/{app_id}/contract/approve",
        json={"revision": d["revision"], "rationale": "개설"}))
    return _data(_client(env, BUILDER).post(f"{_base(env)}/{app_id}/build"))


def test_만들면_후보_판이다(env):
    """★★★ **대조군.** 「만들었다」와 「운영이다」가 늘 같으면 승격은 아무 뜻이 없다.

    ⚠️ 미기록을 `active` 로 그리지 않는다 — `program_lifecycle` 은 하위호환상 미기록을
      `active` 로 답하지만, 「아직 안 만들었다」와 「운영이다」는 다른 사실이다."""
    rows = _data(_client(env, BUILDER).get(_base(env)))["apps"]
    assert next(r for r in rows if r["app_id"] == APP)["lifecycle_state"] == "", \
        "만들기 전인데 사용여부가 붙어 있다"

    _approve_and_build(env)
    rows = _data(_client(env, BUILDER).get(_base(env)))["apps"]
    assert next(r for r in rows if r["app_id"] == APP)["lifecycle_state"] == "candidate"


def test_만들지_않은_앱은_승격할_수_없다(env):
    """⚠️ 「지금 상태에서 할 수 없는 일」은 409 다 — 404 면 앱 자체가 없는 것으로 읽힌다."""
    res = _client(env, APPROVER).post(f"{_base(env)}/{APP}/promote",
                                      json={"reason": "올려 보자"})
    assert res.status_code == 409, res.text[:200]


def test_사유_없이는_승격할_수_없다(env):
    _approve_and_build(env)
    res = _client(env, APPROVER).post(f"{_base(env)}/{APP}/promote", json={"reason": "  "})
    #: ★ 본문 검증(422)이든 승격 거부(409)든 **상태는 그대로여야 한다.**
    assert res.status_code in (409, 422), res.text[:200]
    rows = _data(_client(env, BUILDER).get(_base(env)))["apps"]
    assert next(r for r in rows if r["app_id"] == APP)["lifecycle_state"] == "candidate"


def test_만드는_사람은_운영에_올리지_못한다(env):
    """★★★ 만드는 권한(`project.run`)과 **운영에 올리는 권한**은 다르다.

    ⚠️ 되돌려도 이미 그 숫자를 본 사람이 있다 — 계약 승인과 같은 무게의 결정이다."""
    _approve_and_build(env)
    res = _client(env, BUILDER).post(f"{_base(env)}/{APP}/promote",
                                     json={"reason": "내가 만들었으니 내가 올린다"})
    assert res.status_code == 403, f"{res.status_code} {res.text[:200]}"
    rows = _data(_client(env, BUILDER).get(_base(env)))["apps"]
    assert next(r for r in rows if r["app_id"] == APP)["lifecycle_state"] == "candidate"


def test_승격하면_운영이_되고_다섯_관문이_전부_기록된다(env):
    """★★★ **여정의 마지막 칸.** 여기까지 와야 앱이 인증된 업무 데이터를 읽는다."""
    _approve_and_build(env)
    out = _data(_client(env, APPROVER).post(
        f"{_base(env)}/{APP}/promote", json={"reason": "제련공장 운영 개시"}))

    assert out["status"] == "active", out
    #: ★ 무엇을 보고 올렸는지가 남는다 — 「통과했다」만으로는 나중에 되짚을 수 없다.
    names = [c["name"] for c in out["checks"]]
    assert len(names) == 5, names
    assert all(c["ok"] for c in out["checks"]), out["checks"]
    #: ★★★ 그리고 **승격 시점의 데이터 판**이 봉인된다 — 원천이 바뀌면 도는 앱이
    #:   승인받은 것과 다른 숫자를 그리는데, 아무 오류도 나지 않기 때문이다.
    assert out["data_fingerprint"], out

    rows = _data(_client(env, BUILDER).get(_base(env)))["apps"]
    assert next(r for r in rows if r["app_id"] == APP)["lifecycle_state"] == "active"


def test_코드_없는_키트앱은_호스트_실행_선언을_봉인한다(env):
    """빈 디렉터리를 면제하지 않는다 — 매니페스트 결속이 없으면 정적 관문이 막아야 한다."""
    out = _approve_and_build(env)
    from core import library_paths
    from core import release_promotion as rp
    import json

    path = library_paths.release_json(out["release_id"])
    with open(path, "r", encoding="utf-8") as fh:
        release = json.load(fh)
    assert release["execution_surface"] == rp.HOST_DECLARATIVE
    assert rp._check_static([library_paths.release_dir(out["release_id"])], release).ok

    release["manifest"]["fingerprint"] = "tampered"
    assert not rp._check_static(
        [library_paths.release_dir(out["release_id"])], release).ok


def test_승격은_같은_승격기를_쓴다():
    """★★★ **면제를 만들지 않았는지**를 잠근다.

    ⚠️ 키트 앱 전용 라우트를 따로 두는 순간 「이 경로만 검사를 줄이자」가 쉬워진다.
      그러면 승격 게이트는 있는데 지나가는 문이 둘이 되고, 하나만 지켜진다."""
    import inspect

    import api.routes.data_preparation_control as dpc

    src = inspect.getsource(dpc.promote_app)
    assert "release_promotion.promote" in src, "공용 승격기를 쓰지 않는다"
    for skipped in ("NOT_APPLICABLE", "no_business_data", "skip"):
        assert skipped not in src, f"승격 검사를 우회하는 표식이 있다: {skipped}"
