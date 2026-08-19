"""★★★ [BDR-6] Provider Dispatch — **앱은 출처를 모른다.**

## 이 파일이 막으려는 네 가지

★★★ ① **모르는 출처가 우리 DB 로 폴백하는 것.** 사내 시스템에서 와야 할 숫자를
  빈 표에서 읽으면 앱은 그것을 「0건」으로 그린다. 그 화면은 오류를 내지 않는다.
★★★ ② **Native 밖에 쓰는 것.** 파일 판 위의 사본은 원천과 갈라지고, 갈라진 사실은
  아무도 모른다.
★★★ ③ **장애·만료·승인 전이 「없음」으로 접히는 것.** 「응답이 없었다」와 「없다」는
  다르다. 0건으로 접으면 사용자는 그것을 «삭제됨» 으로 읽는다.
★★★ ④ **출처 종류가 앱에 새어 나가는 것.** 알려 주는 순간 앱 코드가 출처별로
  분기하고, 출처를 바꾸는 일이 앱을 고치는 일이 된다.
"""
import pytest

from core import host_runtime_provider as prov
from core import host_runtime_sdk as sdk
from core.data_preparation import models as m
from core.data_preparation import readiness as r

NOW = "2026-08-18T00:00:00+00:00"


def _binding(state=m.ACTIVE):
    return {"binding_id": "b1", "state": state, "tenant_id": "t1",
            "scope_node_id": "n1", "entity_mode": "REAL"}


def _certified(certified_at="2026-08-17T00:00:00+00:00"):
    return {"snapshot_id": "ds_1", "state": m.DEMO_CERTIFIED, "certified_at": certified_at,
            "created_at": "2026-08-17T00:00:00+00:00", "raw_path": "x.csv",
            "checksum": "c" * 64, "data_kind": m.DATA_KIND_DEMO}


#: ⚠️ 「기본값」과 「명시한 None」을 구분한다. `binding=None` 을 기본값으로 덮으면
#:   «결속 없음» 시험이 조용히 «결속 있음» 을 검사한다(실제로 그렇게 틀렸다).
_UNSET = object()


def _resolve(intent="ENTERPRISE_READ", *, key="arrivals", binding=_UNSET,
             snapshots=_UNSET, **kw):
    return prov.resolve(source_intent=intent, dataset_contract_key=key,
                        binding=_binding() if binding is _UNSET else binding,
                        snapshots=[_certified()] if snapshots is _UNSET else snapshots,
                        now=kw.pop("now", NOW), **kw)


# ── ④ 표면 ───────────────────────────────────────────────────────────────
def test_the_provider_list_is_closed():
    assert prov.PROVIDERS == ("AFS_NATIVE", "FILE_SNAPSHOT", "CONNECTOR_QUERY", "DERIVED")


def test_what_the_app_gets_back_never_names_the_provider():
    """★★★ 출처 종류·결속 id·내부 경로는 나가지 않는다.

    ⚠️ 알려 주면 LLM 이 쓴 앱 코드가 출처별로 분기하기 시작하고, 그러면 출처를 바꾸는
      일이 앱을 고치는 일이 된다 — 이 층을 만든 이유가 사라진다."""
    meta = prov.public_meta(_resolve())
    assert set(meta) == {"as_of", "stale"}
    body = repr(meta)
    for leaked in ("FILE_SNAPSHOT", "AFS_NATIVE", "b1", "ds_1", "arrivals", ".csv"):
        assert leaked not in body, f"«{leaked}» 이 앱에 새어 나갔다"


def test_the_forbidden_surface_still_has_no_source_names():
    """⚠️ SDK 표면에 출처 관련 이름이 생기면 앱이 그것을 읽기 시작한다."""
    for name in sdk.SDK_SURFACE:
        for leaked in ("provider", "snapshot", "connector", "source"):
            assert leaked not in name.lower(), f"{name} 이 출처를 노출한다"


# ── ① 폴백 없음 ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("intent", ["", "   ", "아무거나", "ENTERPRISE_WRITE", None])
def test_an_unknown_intent_never_falls_back_to_our_own_db(intent):
    """★★★ 「모르면 우리 DB」가 곧 조용한 오답이다."""
    assert prov.provider_for_intent(intent) == ""
    with pytest.raises(prov.ProviderError) as e:
        _resolve(intent)
    assert e.value.app_code == sdk.ERR_UNAVAILABLE
    assert e.value.provider != prov.NATIVE


def test_each_declared_intent_maps_to_exactly_one_provider():
    assert prov.provider_for_intent("AFS_NATIVE") == prov.NATIVE
    assert prov.provider_for_intent("ENTERPRISE_READ") == prov.FILE_SNAPSHOT
    assert prov.provider_for_intent("EXTERNAL_REFERENCE") == prov.CONNECTOR_QUERY
    assert prov.provider_for_intent("DERIVED_READ") == prov.DERIVED


def test_native_needs_no_binding_or_snapshot():
    res = prov.resolve(source_intent="AFS_NATIVE", dataset_contract_key="",
                       binding=None, snapshots=[], now=NOW)
    assert res.provider == prov.NATIVE and res.stale is False


@pytest.mark.parametrize("intent", ["EXTERNAL_REFERENCE", "DERIVED_READ"])
def test_an_unsupported_provider_says_so_instead_of_returning_nothing(intent):
    """★★★ 「아직 안 된다」를 「없다」로 답하면 앱이 화면에서 그 표를 지우고,
    사용자는 데이터가 사라졌다고 읽는다."""
    with pytest.raises(prov.ProviderError) as e:
        _resolve(intent)
    assert e.value.app_code == sdk.ERR_UNAVAILABLE
    assert e.value.reason == prov.NOT_YET_SUPPORTED
    assert e.value.app_code != sdk.ERR_NOT_FOUND


def test_a_declared_enterprise_source_without_a_contract_key_is_refused():
    """⚠️ 「사내 실적」이라 말했는데 어느 표인지 안 적혀 있다 — **우리 DB 로 가지 않는다.**"""
    with pytest.raises(prov.ProviderError) as e:
        _resolve(key="")
    assert e.value.app_code == sdk.ERR_UNAVAILABLE
    assert e.value.provider == prov.FILE_SNAPSHOT


# ── ② 쓰기 ───────────────────────────────────────────────────────────────
def test_only_native_is_writable():
    assert prov.WRITABLE_PROVIDERS == (prov.NATIVE,)
    assert prov.is_writable(prov.NATIVE) is True
    for p in (prov.FILE_SNAPSHOT, prov.CONNECTOR_QUERY, prov.DERIVED):
        assert prov.is_writable(p) is False


@pytest.mark.parametrize("bad", ["", "아무거나", None, "afs_native", "NATIVE"])
def test_an_unknown_provider_is_not_writable(bad):
    """★★★ fail-closed — 목록에 없으면 못 쓴다. 대소문자도 봐주지 않는다."""
    assert prov.is_writable(bad) is False
    with pytest.raises(prov.ProviderError):
        prov.assert_writable(bad)


def test_a_blocked_write_is_forbidden_not_not_found():
    """⚠️ 거부를 숨기면 개발자가 무엇을 고쳐야 하는지 모른 채 이름을 의심한다."""
    with pytest.raises(prov.ProviderError) as e:
        prov.assert_writable(prov.FILE_SNAPSHOT)
    assert e.value.app_code == sdk.ERR_FORBIDDEN
    assert "WRITE_NOT_ALLOWED" in e.value.reason


# ── ③ 장애·만료·승인 전 ──────────────────────────────────────────────────
@pytest.mark.parametrize("snapshots,binding,why", [
    ([], None, r.NOT_CONFIGURED),
    ([], _binding(), r.SOURCE_CONFIGURED),
    ([{"snapshot_id": "s", "state": m.RECONCILED, "created_at": "2026-08-01"}],
     _binding(), r.APPROVAL_PENDING),
    ([{"snapshot_id": "s", "state": m.QUARANTINED, "created_at": "2026-08-01",
       "quarantine": {"kind": m.QUARANTINE_RECONCILIATION}}], _binding(),
     r.RECONCILIATION_FAILED),
])
def test_an_unready_source_is_unavailable_never_an_empty_list(snapshots, binding, why):
    """★★★ **0건으로 그리지 않는다.** 준비 안 된 것과 없는 것은 다르다."""
    with pytest.raises(prov.ProviderError) as e:
        _resolve(binding=binding, snapshots=snapshots)
    assert e.value.app_code == sdk.ERR_UNAVAILABLE
    assert e.value.reason == why


def test_the_reason_reaching_the_app_is_a_code_not_the_readiness_sentence():
    """★★★ 준비도 문장에는 그 사람이 볼 수 없는 조직 내부 상태가 들어 있다.

    ⚠️ 앱에 흘리면 그 앱을 쓰는 사람이 볼 수 없는 사실이 앱 코드를 통해 새어나간다."""
    with pytest.raises(prov.ProviderError) as e:
        _resolve(snapshots=[{"snapshot_id": "s", "state": m.RECONCILED,
                             "created_at": "2026-08-01"}])
    assert e.value.app_code in sdk.APP_ERROR_CODES
    #: 사람이 읽는 안내 문장이 그대로 실려 나가지 않는다
    assert "인증" not in str(e.value) and "승인" not in str(e.value)


def test_a_stale_snapshot_is_refused_unless_the_caller_opts_in():
    """★★★ 기본이 켜져 있으면 만료가 **조용히 정상 응답**이 되고, 「언제 것인지 모르는
    숫자」가 공식 화면에 오른다."""
    old = [_certified("2026-01-01T00:00:00+00:00")]
    with pytest.raises(prov.ProviderError) as e:
        _resolve(snapshots=old, max_age_days=30)
    assert e.value.reason == r.STALE

    res = _resolve(snapshots=old, max_age_days=30, allow_stale=True)
    assert res.stale is True
    assert prov.public_meta(res)["stale"] is True, "만료 사실이 화면에 안 나간다"


def test_a_fresh_snapshot_is_not_marked_stale():
    """⚠️ 대조군 — 위 시험이 「전부 stale」로도 통과하지 않게 한다."""
    res = _resolve(max_age_days=30)
    assert res.stale is False
    assert res.as_of == "2026-08-17T00:00:00+00:00"


def test_the_resolution_carries_the_as_of_so_the_app_can_show_it():
    """⚠️ 「언제 것인가」가 없으면 사용자는 지금 것으로 읽는다."""
    assert prov.public_meta(_resolve())["as_of"] == "2026-08-17T00:00:00+00:00"


# ── 잘라 주되 총계를 준다 ────────────────────────────────────────────────
def test_paging_reports_the_total_not_just_the_page():
    """⚠️ 화면이 `len(rows)` 를 «전부» 로 읽으면 상한에 걸린 순간 사용자는
    「우리 데이터는 N건」으로 믿는다."""
    rows = [{"i": i} for i in range(10)]
    page, total = prov.snapshot_rows(rows, limit=3, offset=0)
    assert len(page) == 3 and total == 10
    page2, total2 = prov.snapshot_rows(rows, limit=3, offset=9)
    assert page2 == [{"i": 9}] and total2 == 10


def test_a_zero_limit_does_not_return_everything():
    """⚠️ `rows[0:0]` 도 `rows[0:]` 도 아니어야 한다 — 전자는 빈 목록(=없다),
    후자는 상한 무시다."""
    page, _ = prov.snapshot_rows([{"i": i} for i in range(10)], limit=0, offset=0)
    assert len(page) == 1


# ── [BDR-6] 실제 배선 ────────────────────────────────────────────────────
#
# ⚠️ 판정 함수 단위 시험만으로는 「실제 배선을 타지 않으면 그 초록은 거짓이다」를 막지
#   못한다. 여기서는 **진짜 라우터**를 태우고, 데이터셋은 **계약이 만든다**.
#
# ★★★ [Wave F-0] 릴리스가 승인된 계약을 들고 있다. 그래야 물질화가 정당하고, 계약과
#   결속이 어긋나면 증명 발급이 막힌다 — 그 대조가 이 절의 전제다.
import json                                                          # noqa: E402

from core import app_runtime_contract as arc                         # noqa: E402
from core import contract_materializer as cm                         # noqa: E402
from core.data_preparation import snapshot_service as ss             # noqa: E402
from core.data_preparation import source_binding as sb               # noqa: E402

H_USER = {"X-Factory-User": "u@x", "X-Session-Token": "sess_raw_1",
          "X-Enterprise-Scope": "node_hq"}
R = "/api/v1/appdata/runtime"
TENANT, SCOPE, MODE = "tenant_default", "node_hq", "REAL"
CONTRACT_KEY = "arrivals"

ENTERPRISE_CSV = (
    "arrived_at,material_code,quantity\n"
    "2026-01-05,M1,10\n"
    "2026-01-06,M2,5\n"
).encode("utf-8")

SOURCE_ROWS = [{"arrived_at": "2026-01-05", "material_code": "M1", "quantity": "10"},
               {"arrived_at": "2026-01-06", "material_code": "M2", "quantity": "5"}]

_FIELDS = [{"name": "quantity", "type": "number", "required": False,
            "classification": "INTERNAL"}]

#: ★★★ **하나의 계약**을 릴리스와 물질화가 함께 쓴다 — 따로 적으면 반드시 갈라지고,
#:   갈린 순간 게이트가 증명 발급을 막는다(그것이 이 시험을 처음 빨갛게 만든 것이다).
#:
#: ★★★ 그리고 그 계약을 **실제 컴파일러로 만든다.** 손으로 적으면 스키마가 요구하는
#:   것을 빠뜨리고(실측: `runtime_contract_version`·`purpose`), 그 계약은 게이트에서
#:   「읽을 수 없습니다」로 막힌다 — 시험만 아는 계약 모양이 생기는 것도 같은 병이다.
def _build_contract():
    from core.host_contract_compiler import compile_contract

    draft = {
        "app_class": "departmental",
        "datasets": [
            {"name": "arrivals", "purpose": "자재가 얼마나 들어왔는가",
             "allowed_actions": ["read"], "data_role": arc.ENTERPRISE_ACTUAL,
             "source_intent": arc.ENTERPRISE_READ,
             "enterprise_contract_key": CONTRACT_KEY,
             "duplicate_entry_policy": arc.DENY_IF_AUTHORITATIVE_SOURCE_EXISTS,
             "fields": _FIELDS},
            {"name": "memo", "purpose": "원천에 없는 대응 메모",
             "allowed_actions": ["read", "create"],
             "data_role": arc.NATIVE_SUPPLEMENT, "source_intent": arc.AFS_NATIVE,
             "duplicate_entry_policy": arc.NO_DUPLICATE_CHECK_REQUIRED,
             "fields": _FIELDS},
        ]}
    r = compile_contract(draft, project_id="proj_a")
    assert r.ok, r.errors
    c = dict(r.contract)
    c["status"] = arc.STATUS_APPROVED
    #: ⚠️ 승인 블록의 필드 이름은 스키마가 정한다(`approved_by`·`approved_at`).
    #:   임의 이름을 넣으면 계약이 통째로 「읽을 수 없습니다」가 된다.
    #: ⚠️ `decision_ledger_id` 도 필수다 — **승인에는 결정 원장 id 가 남아야 한다.**
    #:   그것이 없으면 「누가 언제 승인했나」에 답할 수 없고, 계약은 승인되지 않은 것과
    #:   같아진다.
    c["approval"] = {"status": "APPROVED", "approved_by": "u@x",
                     "approved_at": "2026-08-18T00:00:00Z",
                     "decision_ledger_id": "evt_test_approval"}
    return c


CONTRACT = _build_contract()


@pytest.fixture
def client(monkeypatch, tmp_path):
    """실제 앱 + 격리 저장소. **릴리스가 승인된 계약을 들고 있다.**"""
    import config
    import core.library_paths as library_paths
    from core.app_capability_token import app_capability_tokens
    from core.org_directory import org_directory
    from core.policy_shadow import policy_shadow

    lib = tmp_path / "library"
    (lib / "rel_ok").mkdir(parents=True)
    (lib / "rel_ok" / "release.json").write_text(json.dumps({
        "release_id": "rel_ok", "project_id": "proj_a", "tenant_id": TENANT,
        "entity_mode": MODE, "enterprise_scope_id": SCOPE,
        "owner_user_id": "", "owner_dept_id": "hq", "visibility": "dept",
        "runtime_contract_profile": "v1",
        #: ★ 릴리스에 봉인된 계약 — 게이트는 이것과 물질화를 대조한다.
        "runtime_contract": CONTRACT,
        "manifest": {"fingerprint": "fp_rel_ok", "valid": True, "manifest": {
            "version": "1.0", "app_class": "departmental",
            "capabilities": ["arrivals.read", "memo.read", "memo.create"],
            "required_capabilities": []}},
    }, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(library_paths, "release_dir",
                        lambda rid: str(lib / str(rid)), raising=False)
    monkeypatch.setattr(config, "ORG_ENFORCE", True, raising=False)
    monkeypatch.setattr(config, "ORG_TRUST_HEADER", True, raising=False)

    class _Scope:
        readable_dept_ids = frozenset({"hq"})
        writable_dept_ids = frozenset({"hq"})
        unrestricted = False
        can_manage_standard = False
        primary_dept_id = "hq"
        readable_scope_nodes = frozenset({"node_hq"})

        def can_read(self, d):
            return d in self.readable_dept_ids

        def can_write(self, d):
            return d in self.writable_dept_ids

    monkeypatch.setattr(org_directory, "resolve_scope", lambda uid="": _Scope())
    monkeypatch.setattr(org_directory, "is_bootstrap", lambda: False)
    monkeypatch.setattr(org_directory, "get_user",
                        lambda uid: {"user_id": uid, "status": "active"} if uid else None)
    monkeypatch.setattr(org_directory, "get_ownership",
                        lambda kind, rid: {"dept_id": "hq", "owner_user_id": "",
                                           "visibility": "dept"})

    app_capability_tokens._tokens.clear()
    policy_shadow.reset()

    from fastapi.testclient import TestClient
    from main import app
    c = TestClient(app)
    c.raw_root = str(tmp_path / "raw")
    return c


@pytest.fixture
def dp():
    """업무 데이터 저장소. ⚠️ conftest 가 경로를 격리한다 — 라우터가 import 하는 것과
    **같은 객체**여야 하므로 여기서 새로 만들지 않는다."""
    from core.data_preparation.store import data_preparation_store

    return data_preparation_store


def _tok(c, release_id="rel_ok"):
    r = c.post(R + "/proof", json={"release_id": release_id}, headers=H_USER)
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def _h(tok):
    return {**H_USER, "X-App-Proof": tok}


def _source(dp, raw_root, *, scope=SCOPE, tenant=TENANT, mode=MODE, certify=True):
    """그 계약키를 제공하는 원천 하나 — 필요하면 인증판까지."""
    inst = dp.create_instance(kit_id="k", version="1.0.0", kit_fingerprint="f",
                              tenant_id=tenant, scope_node_id=scope, entity_mode=mode)
    b = dp.create_binding(instance_id=inst["instance_id"],
                          dataset_contract_key=CONTRACT_KEY,
                          provider=m.PROVIDER_FILE_SNAPSHOT,
                          config={"file_name": "a.csv", "column_map": {"a": "A"}},
                          tenant_id=tenant, scope_node_id=scope, entity_mode=mode)
    for step in ("validate", "approve", "activate"):
        getattr(sb, step)(dp, b["binding_id"])
    if not certify:
        return inst, b, None
    snap = ss.ingest(dp, binding=dp.get_binding(b["binding_id"]), payload=ENTERPRISE_CSV,
                     file_name="a.csv", workspace_root=raw_root)
    out = ss.run_pipeline(dp, snap["snapshot_id"], SOURCE_ROWS,
                          ["arrived_at", "material_code", "quantity"],
                          control={"row_count": 2, "sums": {"quantity": 15}})
    assert out["state"] == m.DEMO_CERTIFIED, out
    return inst, b, out


def _materialize(**kw):
    """**실제 물질화 경로.** 결속 표를 직접 쓰지 않는다.

    ★★★ 시험이 표를 직접 UPDATE 하면 「계약이 그 값을 채우지 않는다」를 영원히 못
      잡는다 — Wave E 가 실제로 그렇게 통과했다."""
    from core.app_data import app_data_service
    from core.data_preparation.store import data_preparation_store

    return cm.materialize(CONTRACT, release_id="rel_ok", actor_id="u@x",
                          store=data_preparation_store, app_data=app_data_service,
                          tenant_id=kw.get("tenant", TENANT),
                          scope_node_id=kw.get("scope", SCOPE),
                          entity_mode=kw.get("mode", MODE))


def _ready(client, dp, **kw):
    """원천 → 물질화까지 끝난 상태."""
    inst, b, snap = _source(dp, client.raw_root, **kw)
    _materialize()
    return inst, b, snap


def test_the_contract_is_what_creates_the_datasets(client, dp):
    """★★★ [Wave F-0] **승인이 무언가를 만든다.** 관리 API 로 만들지 않는다."""
    from core.app_data import app_data_service

    _ready(client, dp)
    names = {d["name"] for d in app_data_service.list_datasets("rel_ok")}
    assert names == {"arrivals", "memo"}


def test_the_same_sdk_call_reads_a_file_snapshot(client, dp):
    """★★★ Gate E — **같은 표면**으로 파일 판을 읽는다. 앱은 어느 쪽인지 모른다."""
    _ready(client, dp)
    r = client.get(R + "/datasets/arrivals/records", headers=_h(_tok(client)))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["total"] == 2, data
    assert data["as_of"], "「언제 것인가」가 없다"
    assert data["stale"] is False


def test_the_same_sdk_call_writes_native_supplement(client, dp):
    """⚠️ 대조군 — 위 시험이 「전부 막힘」으로도 통과하지 않게 한다."""
    _ready(client, dp)
    r = client.post(R + "/datasets/memo/records", headers=_h(_tok(client)),
                    json={"payload": {"quantity": 1}})
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("method,path,body", [
    ("post", "/datasets/arrivals/records", {"payload": {"quantity": 1}}),
    ("put", "/datasets/arrivals/records/0", {"payload": {"quantity": 1}}),
    ("delete", "/datasets/arrivals/records/0", None),
])
def test_writing_to_enterprise_data_is_blocked(client, dp, method, path, body):
    """★★★ Gate E — **기업/파일 데이터 write 차단.**

    ⚠️ 파일 판 위의 사본은 원천과 갈라지고, 갈라진 사실은 아무도 모른다."""
    _ready(client, dp)
    kw = {"headers": _h(_tok(client))}
    if body is not None:
        kw["json"] = body
    r = getattr(client, method)(R + path, **kw)
    assert r.status_code == 403, method + " 이 통과했다: " + r.text[:160]


def test_a_source_that_breaks_after_the_app_was_made_is_not_an_empty_table(client, dp):
    """★★★ Gate E — **장애·만료·승인 전 상태 오독 0.**

    ★ [Wave F-0] 이제 원천이 없으면 앱이 **아예 만들어지지 않는다.** 그래서 현실적인
      상황은 「만든 뒤 깨진다」다 — 인증판이 회수되거나 결속이 종료되는 경우.
    ⚠️ 그때 0건으로 답하면 앱은 「데이터가 없다」를 그리고, 그 화면 위에서 합계 0인
      보고서가 만들어진다."""
    inst, b, snap = _ready(client, dp)
    #: 인증을 회수한다 — 판은 있지만 더는 공식이 아니다
    dp.advance_snapshot(snap["snapshot_id"], m.REVOKED)

    r = client.get(R + "/datasets/arrivals/records", headers=_h(_tok(client)))
    assert r.status_code == 503, "「아직 아니다」가 「없다」로 답해졌다: " + str(r.status_code)
    assert "records" not in r.text, "빈 목록이 나갔다"


def test_a_tampered_raw_file_stops_the_read(client, dp):
    """★★★ 「우리가 인증한 그 파일」이라는 전제가 깨지면 **읽지 않는다.**"""
    _, _, snap = _ready(client, dp)
    with open(snap["raw_path"], "ab") as f:
        f.write(b"2026-01-07,M3,99\n")

    r = client.get(R + "/datasets/arrivals/records", headers=_h(_tok(client)))
    assert r.status_code != 200, "변조된 원본을 그대로 읽었다"


def test_the_response_never_names_the_provider(client, dp):
    """★★★ Gate E — 출처 종류·내부 식별자가 앱에 나가지 않는다."""
    inst, _, snap = _ready(client, dp)
    body = client.get(R + "/datasets/arrivals/records",
                      headers=_h(_tok(client))).text
    for leaked in ("FILE_SNAPSHOT", "AFS_NATIVE", "raw_path",
                   inst["instance_id"], snap["snapshot_id"], "binding_id"):
        assert leaked not in body, "«" + leaked + "» 이 앱에 새어 나갔다"


def test_a_source_store_failure_is_reported_as_a_store_failure(client, dp, monkeypatch):
    """★★★ 원천 저장소 장애를 **결속이 없는 것**으로 바꾸지 않는다.

    ⚠️ 둘 다 앱에게는 같은 코드로 접히지만, **운영자에게는 전혀 다른 사실**이다."""
    from core.data_preparation.store import data_preparation_store as store
    from core.enterprise_context import audit

    _ready(client, dp)
    tok = _tok(client)

    def _boom(*a, **k):
        raise RuntimeError("디스크가 응답하지 않습니다")

    monkeypatch.setattr(store, "active_binding", _boom, raising=False)
    seen = []
    monkeypatch.setattr(audit, "record",
                        lambda **kw: seen.append(kw.get("detail", "")), raising=False)

    r = client.get(R + "/datasets/arrivals/records", headers=_h(tok))
    assert r.status_code != 200, "장애 중에 200 을 답했다"
    assert any("원천 판독 실패" in d for d in seen), \
        "저장소 장애가 «결속 없음» 으로 기록됐다: " + repr(seen)


def test_the_error_body_never_carries_the_readiness_reason(client, dp):
    """★★★ 거부 **사유**는 감사에만 남고 앱에는 고정 문장만 간다."""
    _, _, snap = _ready(client, dp)
    dp.advance_snapshot(snap["snapshot_id"], m.REVOKED)

    r = client.get(R + "/datasets/arrivals/records", headers=_h(_tok(client)))
    assert r.status_code != 200
    for leaked in ("SOURCE_CONFIGURED", "NOT_CONFIGURED", "APPROVAL_PENDING",
                   "QUARANTINED", "UNAVAILABLE", "dispatch:"):
        assert leaked not in r.text, "«" + leaked + "» 이 앱 화면까지 갔다"


@pytest.mark.parametrize("field,value", [
    ("tenant", "tenant_other"), ("scope", "node_다른곳"), ("mode", "VIRTUAL"),
])
def test_an_app_cannot_be_made_against_a_source_in_another_scope(client, dp, field, value):
    """★★★ 범위 세 필드를 **하나씩** 어긋내 본다.

    ★ [Wave F-0] 이제 이것은 **물질화에서** 막힌다 — 그 편이 낫다. 만들어진 뒤
      런타임에서 막히면 사용자는 앱이 고장 났다고 생각한다.
    ⚠️ 셋을 한꺼번에만 시험하면 판정이 그중 하나만 봐도 통과한다(Wave E 실측)."""
    _source(dp, client.raw_root, **{field: value})
    with pytest.raises(cm.MaterializeError) as e:
        _materialize()
    assert "arrivals" in str(e.value)
    assert value not in str(e.value), "범위 식별자가 사유에 실렸다"
