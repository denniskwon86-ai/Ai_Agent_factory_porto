"""R01.1 — 승인 대상 앱 하나(APP-03)의 **실제** Host 소비 경로. 격리 runner 전용.

## 무엇이 실제이고 무엇이 합성인가

- 합성: **자료만.** 인증할 RAW 는 **키트 정본의 합성 샘플**(`samples/quick/<key>.csv`) 앞
  `SAMPLE_ROWS` 행이다 — 열·순서·업무키가 정본 계약(`contracts/<key>.contract.json`)과 같다.
  바꾸는 것은 행 안의 `tenant_id`·`scope_node_id` 두 칸뿐이고, 시험 문맥(`.invalid` 조직)으로
  다시 묶는다. ⚠️ [Codex §15 검토] 첫 판은 모든 키를 `amount` 한 칸으로 만들어 «Host 연결» 만
  확인했고 업무 계약은 확인하지 못했다.
- 실제: 설치(B2) · 인증 서명(B0) · 계약 작성/승인(작성자 MEMBER_A ≠ 승인자 ADMIN) ·
  `POST build/v2`(실제 게시 → 실제 미리보기 평면 물질화) · `POST promote`(실제 승격 게이트 →
  운영 평면 물질화) · `POST /appdata/runtime/proof` · `GET/POST /datasets/.../records`.
  신원은 **제품 세션**(`auth_store.create_session` → `X-Session-Token`)이다. 신뢰 헤더·
  dependency override·principal 주입은 없다.
- 저장소는 대역이 아니다. 제품 싱글턴이 여는 **경로만** tmp 로 돌린다(같은 클래스의 실제
  인스턴스). `_plane`·`prov.resolve`·`_dispatch` 는 건드리지 않는다.

## 왜 쓰기→재조회가 아니라 «읽기 + 쓰기 거절 분리» 인가 (§14.3-B-4)

대상 7앱의 정본 계약은 전부 `ENTERPRISE_READ`·`allowed_actions=["read"]` 다
(`kit_app_builder.contract_from_blueprint`). APP-02 입력은 정본 문서가 「Native 입력 루프」
후속으로 보류했다. **쓰기 요구가 있는 대상 계약이 없으므로 쓰기를 억지로 열지 않는다.**

## 쓰기 거절은 관문이 셋이다 — 앞 관문이 뒤를 가린다

정책 판정(`_judge`, 증명 capability) → 계약 행동(`_assert_contract_action`) → provider
(`_assert_native_write`). 제품 경로에서는 첫 관문이 막으므로 뒤의 둘은 **보이지 않는다.**
그래서 대조 시험 두 건이 앞 관문을 하나씩 걷어 내고 **다음 관문이 스스로 막는지** 본다.
그 두 건은 제품 동작의 증거가 아니라 «층이 층인가» 의 대조군이다.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

import pytest

from tests import org_seed as org
from tests.test_b2_installation import _apply, _plan, _prepared, _read
from tests.test_b3_kit_contract_v2 import (TEMPLATES, DATA_KEYS, approve, database, draft,  # noqa: F401
    enforced_org, installation, workspace)
from tests.test_b3_process_context import build as process_build

APP = "APP-03"
KEY = "INV-01"
PREFIX = "/api/v1/data-preparation/instances/{instance_id}/apps/" + APP + "/"
RUNTIME = "/api/v1/appdata/runtime"
#: 키트 정본(읽기 전용). 대상 앱 설계도·데이터셋 계약·합성 샘플이 모두 여기 있다.
KIT = Path(__file__).resolve().parents[1] / "starter_kits" / "KIT-MFG-NONFERROUS-PROCUREMENT" / "1.0.0"
SAMPLE_ROWS = 3
SCOPE_COLUMNS = ("tenant_id", "scope_node_id")


def canonical_contract(key):
    """정본 데이터셋 계약 — 필드 이름(순서 포함)과 업무키의 기준."""
    return json.loads((KIT / "contracts" / f"{key}.contract.json").read_text(encoding="utf-8-sig"))


def canonical_fields(key):
    return [f["name"] for f in canonical_contract(key)["schema"]["fields"]]


def app_fields(key):
    """정본 필드 중 **앱에 가는 것.** 제품 규칙에서 유도한다 — 손으로 적지 않는다.

    `record_id`·`created_at` 같은 **플랫폼 예약 이름**은 레코드 봉투 칸이라 앱 필드가 될 수
    없다(`kit_app_builder.fields_from_certified`, `app_data.RESERVED_FIELD_NAMES`). 앱이 같은
    이름을 쓰면 «누가 언제 만들었나» 를 덮어쓸 수 있기 때문이다."""
    from core.app_data import RESERVED_FIELD_NAMES
    return [name for name in canonical_fields(key) if name not in RESERVED_FIELD_NAMES]


def sample_rows(key, context):
    """정본 샘플 앞 `SAMPLE_ROWS` 행. 행 안의 조직 범위만 시험 문맥으로 다시 묶는다.

    ⚠️ 샘플의 조직 값은 키트 데모 조직이다. 그대로 두면 «시험 문맥의 판인데 행은 다른 조직»
      이 된다. 다른 칸은 손대지 않는다 — 손대면 그 fixture 가 계약을 대신 정의한다."""
    with (KIT / "samples" / "quick" / f"{key}.csv").open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = list(reader.fieldnames or [])
        rows = [dict(row) for _, row in zip(range(SAMPLE_ROWS), reader)]
    assert columns == canonical_fields(key), f"{key}: 샘플 열이 정본 계약과 다르다"
    assert len(rows) == SAMPLE_ROWS
    for row in rows:
        row.update({name: str(context[name]) for name in SCOPE_COLUMNS})
    return columns, rows


def raw_certified(w, key, raw_root):
    """`metadata_certified` 와 같은 결속·소유·인증 절차. 다른 점은 **판을 제품 수집으로 만든다**는 것.

    ⚠️ 원래 fixture 는 RAW 없이 판 행만 만든다 — 그 판은 `_serve_snapshot` 이 RAW 지문을
      대조할 때 503 이 된다. 실제 조회를 보려면 **실제 RAW 가 있는 판**이어야 한다.
    ★ RAW 는 정본 열·업무키를 가진 합성 샘플이다(`sample_rows`)."""
    from core.data_preparation import certification_subject as cs, models as m, ownership_binding as ob
    from core.data_preparation import snapshot_service as ss
    store = w["store"]
    binding = store.create_binding(instance_id=w["instance_id"], dataset_contract_key=key,
        provider=m.PROVIDER_FILE_SNAPSHOT, config={}, created_by=org.MANAGER_A, **w["context"])
    for stage in (m.VALIDATED, m.APPROVED, m.ACTIVE):
        binding = store.transition(binding["binding_id"], stage)
    args = dict(**w["context"], dataset_contract_key=key, owner_dept_id=org.DEPT_A,
                evidence_ref="test-only-r01-owner")
    approved = ob.approve(**args, actor_id=org.ADMIN)
    with store.transaction() as conn:
        ob.declare(conn, **args, approved_by=org.ADMIN, approval_event_id=approved["approval_event_id"],
                   effective_from=approved["effective_from"])
    columns, source = sample_rows(key, w["context"])
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(source)
    raw = buffer.getvalue().encode("utf-8")
    snapshot = ss.ingest(store, binding=binding, payload=raw, file_name=f"{key}.csv",
                         workspace_root=str(raw_root), created_by=org.MANAGER_A,
                         data_kind=m.DATA_KIND_REAL)
    assert snapshot["raw_path"] and Path(snapshot["raw_path"]).resolve().is_relative_to(Path(raw_root).resolve())
    #: 인증 단계도 수집과 **같은 파서**가 읽은 행을 쓴다 — 손으로 적은 행이 아니다.
    parsed = ss.parse_csv(raw, file_name=f"{key}.csv")
    assert parsed.columns == columns and parsed.rows == source
    sid, rows = snapshot["snapshot_id"], parsed.rows
    ss.profile(store, sid, rows, parsed.columns)
    ss.standardize(store, sid, rows)
    ss.reconcile(store, sid, rows, {"row_count": len(rows)})
    args = dict(actor=org.MANAGER_A, context=w["context"], use_kind="OPERATIONAL",
                period_from="2026-08-01", period_to="2026-08-31")
    preview = cs.preview(store, sid, **args)
    signed = cs.sign(store, sid, **args, review_kind="DATA_OWNER",
        reconciliation_evidence="합성 RAW 총계와 원천 대사 일치 확인", subject_id=preview["subject_id"],
        expected_subject_digest=preview["digest"], client_request_id="r01-raw-" + sid)
    assert signed["certified"]
    return {"binding": binding, "snapshot_id": sid, "raw_path": snapshot["raw_path"],
            "checksum": hashlib.sha256(raw).hexdigest(), "rows": source}


def raw_kit(installation, monkeypatch, raw_root):
    """`cold_kit` 과 같은 설치·정책·고정 문맥. **캐시를 쓰지 않는다.**

    ⚠️ `cached_kit` 의 캐시 키는 세션에 하나다 — 다른 cold 함수를 넘겨도 먼저 만든
      메타데이터 판을 돌려받는다. 그래서 여기서는 매번 cold 로 만든다."""
    from core.data_preparation import certification_authority as ca
    from core.decision_ledger import decision_ledger
    from core.enterprise_context.process_context import ProcessContextService
    w = installation
    prepared = _prepared(w, _plan(w, business_kit_ids=["BK-03", "BK-04"]))
    approved = _apply(w, prepared)
    doc = _read(w)["payload"]
    w = {**w, "approved": approved, "instance_id": doc["template_sources"][0]["kit_instance_ref"],
         "ids": {n["template_key"]: n["process_id"] for n in doc["nodes"]},
         "ctx": ProcessContextService(w["svc"].repo, w["store"])}
    monkeypatch.setattr(decision_ledger, "db_path", str(w["root"] / "r01-ledger.db"))
    monkeypatch.setattr(decision_ledger, "_prepared_for", None)
    policy = {"required_reviews": {"OPERATIONAL": ["DATA_OWNER"], "MANAGEMENT": ["DATA_OWNER", "EXECUTIVE"]},
        "grants": {"DATA_OWNER": [{"dept_id": org.DEPT_A, "role": "manager", "scope_node_id": org.NODES[org.DEPT_A]}],
                   "EXECUTIVE": [{"dept_id": org.DEPT_ROOT, "role": "viewer", "scope_node_id": org.NODES[org.DEPT_ROOT]}]},
        "delegations": [], "allow_same_actor": False, "min_evidence_length": 10}
    ca.approve_policy(w["store"], tenant_id=w["context"]["tenant_id"], entity_mode="REAL",
        context_root_id=w["boundary"].context_root_id, actor=org.ADMIN,
        evidence_ref="test-only-r01-policy", document=policy)
    w["data"] = {key: raw_certified(w, key, raw_root) for key in DATA_KEYS}
    w["fixed"] = process_build(w, [w["ids"][key] for key in TEMPLATES])
    assert "GENERATE" in w["fixed"]["permitted_actions"]
    return w


@pytest.fixture
def host(installation, monkeypatch, tmp_path):
    """실제 앱(`main.app`) + 제품 세션 + 격리 경로. 싱글턴은 **같은 클래스의 실제 인스턴스**로만 바꾼다."""
    import config
    import core.app_data as app_data_module
    from core import app_preview, library_paths
    from core.app_data import AppDataService
    from core.app_data_store import AppDataStore
    from core.auth import auth_store
    from core.org_directory import org_directory
    from core.program_lifecycle import program_lifecycle
    from core.project_visibility import resolve_viewing_context
    from core.scope_policy import org_enforce

    monkeypatch.setattr(library_paths, "_LIBRARY_DIR", str(tmp_path / "library"))
    preview = AppDataService(AppDataStore(db_path=str(tmp_path / "app_data_preview.db")))
    operational = AppDataService(AppDataStore(db_path=str(tmp_path / "app_data.db")))
    monkeypatch.setattr(app_preview, "_preview_service", preview)
    monkeypatch.setattr(app_data_module, "app_data_service", operational)
    monkeypatch.setattr(program_lifecycle, "db_path", str(tmp_path / "program_lifecycle.db"))
    monkeypatch.setattr(auth_store, "db_path", str(tmp_path / "auth.db"))
    w = raw_kit(installation, monkeypatch, tmp_path / "raw")
    #: ★ 격리가 «주장» 이 아니라 사실인지 — 앱이 실제로 여는 평면이 방금 둔 그 인스턴스인가.
    assert app_preview.app_data_for(app_preview.AUDIENCE_OPERATIONAL) is operational
    assert app_preview.app_data_for(app_preview.AUDIENCE_PREVIEW) is preview
    #: ★ 대조군이 진짜인지 먼저 — 개발용 신뢰 헤더가 꺼져 있고 조직 강제가 켜져 있다.
    assert getattr(config, "ORG_TRUST_HEADER", False) is False
    assert org_enforce() is True
    org_directory._invalidate()
    scope = w["context"]["scope_node_id"]
    for actor in (org.MEMBER_A, org.ADMIN, org.VIEWER_A):
        assert resolve_viewing_context(actor, scope) == w["context"], actor

    from fastapi.testclient import TestClient
    from main import app
    assert not app.dependency_overrides
    client = TestClient(app)

    def session(actor):
        token = auth_store.create_session(actor)["token"]
        assert auth_store.resolve(token) == actor
        return {"X-Session-Token": token, "X-Enterprise-Scope": scope}

    yield {**w, "client": client, "session": session, "preview": preview, "operational": operational,
           "library": tmp_path / "library"}
    org_directory._invalidate()


def _ok(response):
    assert response.status_code == 200, response.text[:400]
    return response.json()["data"]


def _operate(h):
    """승인 → 실제 build → 실제 운영 전환 → 열람자 증명. 앱을 «연» 상태를 돌려준다."""
    from core import kit_app_builder as kb, library_paths
    from core.program_lifecycle import program_lifecycle
    c, url = h["client"], PREFIX.format(instance_id=h["instance_id"])
    row = approve(h, draft(h))
    assert row["drafted_by"] == org.MEMBER_A and row["approved_by"] == org.ADMIN
    built = _ok(c.post(url + "build/v2", headers=h["session"](org.MEMBER_A),
                       json={"revision": row["revision"], "expected_fingerprint": row["semantic_fingerprint"]}))
    release_id = built["release_id"]
    assert release_id == kb.release_id_for(h["instance_id"], APP)
    #: 게시는 실제 파일이다 — 격리한 library 아래에 있다.
    published = Path(library_paths.release_json(release_id)).resolve()
    assert published.is_file() and published.is_relative_to(h["library"].resolve()), published
    assert h["preview"].find_dataset(release_id, kb.runtime_name(KEY)), "미리보기 평면에 물질화되지 않았다"
    assert not h["operational"].find_dataset(release_id, kb.runtime_name(KEY)), "승격 전에 운영 평면이 찼다"
    #: 후보 판은 REAL 문맥에서 증명이 나오지 않는다 — 승격 전 열람은 막혀야 한다.
    early = c.post(RUNTIME + "/proof", json={"release_id": release_id}, headers=h["session"](org.VIEWER_A))
    assert early.status_code in (403, 404), early.text[:200]
    promoted = _ok(c.post(url + "promote", headers=h["session"](org.ADMIN),
                          json={"reason": "R01.1 합성 자료 실제 경로 확인"}))
    assert program_lifecycle.effective_status(release_id) == promoted["status"]
    ds = h["operational"].find_dataset(release_id, kb.runtime_name(KEY))
    assert ds, "운영 전환이 운영 평면에 물질화하지 않았다"
    viewer = h["session"](org.VIEWER_A)
    proof = _ok(c.post(RUNTIME + "/proof", json={"release_id": release_id}, headers=viewer))
    #: ★ 증명의 `app_id` 는 릴리스의 `project_id` 다(`app_proof.app_facts`). 키트 릴리스는
    #:   `project_id == release_id` 이고, 청사진 식별자(APP-03)는 게시 파일의 `app_id` 에 있다.
    import json
    assert json.loads(published.read_text(encoding="utf-8"))["app_id"] == APP
    assert proof["app_id"] == release_id and proof["release_id"] == release_id
    return release_id, ds, {**viewer, "X-App-Proof": proof["token"]}, proof


def test_app03_real_build_promote_proof_and_snapshot_read(host):
    """★★★ R01.1 읽기 한 경로 — **실제** 게시·승격·증명·판 조회, 그리고 같은 경로 재조회."""
    from core import kit_app_builder as kb
    release_id, ds, headers, proof = _operate(host)
    c, name = host["client"], kb.runtime_name(KEY)
    assert all(not cap.endswith((".create", ".update", ".delete", ".write")) for cap in proof["capabilities"]), \
        "읽기 전용 계약인데 쓰기 capability 가 나갔다"

    names = app_fields(KEY)
    #: ★ 앱에서 빠지는 것은 예약 이름뿐이다 — 그 밖의 정본 필드가 하나라도 빠지면 여기서 드러난다.
    assert set(canonical_fields(KEY)) - set(names) == {"record_id"}
    source = [{k: v for k, v in row.items() if k in names} for row in host["data"][KEY]["rows"]]
    first = _ok(c.get(f"{RUNTIME}/datasets/{name}/records", headers=headers))
    assert first["total"] == len(source) == SAMPLE_ROWS and first["stale"] is False and first["as_of"]
    served = [{k: str(v) for k, v in r["payload"].items()} for r in first["records"]]
    #: ★ 업무 계약 — 앱에 가는 정본 필드가 빠짐·추가 없이 오고, 값이 정본 샘플 그대로다.
    assert [sorted(p) for p in served] == [sorted(names)] * len(source), "정본 필드와 다른 칸이 왔다"
    assert served == source, "정본 샘플과 다른 값을 돌려줬다(다른 판을 읽었다)"
    #: 업무키가 살아 있고 행을 가른다.
    business_keys = canonical_contract(KEY)["business_keys"]
    assert business_keys
    for bk in business_keys:
        values = [p[bk] for p in served]
        assert all(values) and len(set(values)) == len(values), bk
    #: 행 안의 조직 범위가 지금 보는 문맥이다.
    assert all(p[k] == str(host["context"][k]) for p in served for k in SCOPE_COLUMNS)
    #: 게시된 계약의 필드 목록이 정본과 같다 — 계약 필드는 인증판 스키마에서 온다.
    from core import library_paths
    contract = json.loads(Path(library_paths.release_json(release_id)).read_text(encoding="utf-8"))["runtime_contract"]
    dataset = next(d for d in contract["datasets"] if d["enterprise_contract_key"] == KEY)
    assert [f["name"] for f in dataset["fields"]] == names
    #: 앱은 출처를 모른다 — 응답에 provider·결속·판 id·경로가 없다.
    body = repr(first)
    for leaked in ("FILE_SNAPSHOT", "AFS_NATIVE", host["data"][KEY]["snapshot_id"],
                   host["data"][KEY]["binding"]["binding_id"], ".csv"):
        assert leaked not in body, leaked
    #: 같은 앱 읽기 경로로 다시 — 목록과 단건이 같은 값을 말한다.
    again = _ok(c.get(f"{RUNTIME}/datasets/{name}/records", headers=headers))
    assert again["records"] == first["records"]
    one = _ok(c.get(f"{RUNTIME}/datasets/{name}/records/0", headers=headers))
    assert {k: str(v) for k, v in one["payload"].items()} == source[0]
    #: 운영 평면의 결속이 그 계약키·그 출처 의도를 말한다.
    binding = host["operational"].binding_for(release_id, ds["dataset_id"])
    assert binding["enterprise_contract_key"] == KEY and binding["source_intent"] == "ENTERPRISE_READ"


def test_app03_write_is_refused_on_the_same_path_without_native_fallback(host, monkeypatch):
    """★★★ 같은 소비 흐름의 쓰기 — **명시 거절**(403), Native 평면에 한 줄도 생기지 않는다.
    그리고 원천(RAW)이 깨지면 «0건» 이 아니라 503 이다."""
    from api.routes import app_data_runtime as route
    from core import app_policy, host_runtime_sdk as sdk, kit_app_builder as kb
    release_id, ds, headers, _ = _operate(host)
    c, name, plane = host["client"], kb.runtime_name(KEY), host["operational"]
    reasons, writes = [], []
    real_fail = route._fail
    monkeypatch.setattr(route, "_fail", lambda code, **kw: (reasons.append((code, kw.get("audit_reason", ""))),
                                                           real_fail(code, **kw))[1])
    real_create = plane.create_record
    monkeypatch.setattr(plane, "create_record", lambda *a, **k: (writes.append(a), real_create(*a, **k))[1])

    for method, path in (("post", f"/datasets/{name}/records"), ("put", f"/datasets/{name}/records/0"),
                         ("delete", f"/datasets/{name}/records/0")):
        kw = {"headers": headers}
        if method != "delete":
            kw["json"] = {"payload": {"unrestricted_quantity": 5}}
        r = getattr(c, method)(RUNTIME + path, **kw)
        assert r.status_code == 403, f"{method} 이 막히지 않았다: {r.text[:200]}"
    assert writes == [] and plane.count_records(ds["dataset_id"]) == 0, "판 위에 Native 사본이 생겼다"
    #: 제품 경로에서 막은 것은 **첫 관문(정책 판정)** 이다 — 증명에 쓰기 capability 가 없다.
    assert len(reasons) == 3 and all(code == sdk.ERR_FORBIDDEN for code, _ in reasons), reasons
    assert not any(app_policy.DENY_DATASET_ACTION in why or "WRITE_NOT_ALLOWED" in why for _, why in reasons), \
        "뒤 관문이 막았다 — 앞 관문이 열려 있다는 뜻이다"

    #: 거절 뒤에도 같은 경로 읽기는 그대로다.
    names = app_fields(KEY)
    source = [{k: v for k, v in row.items() if k in names} for row in host["data"][KEY]["rows"]]
    after = _ok(c.get(f"{RUNTIME}/datasets/{name}/records", headers=headers))["records"]
    assert [{k: str(v) for k, v in r["payload"].items()} for r in after] == source
    #: 원천 실패 경계 — RAW 가 바뀌면 빈 목록이 아니라 503 이다. 정본 행 하나의 업무키 값을 바꾼다.
    reasons.clear()
    raw = Path(host["data"][KEY]["raw_path"])
    bk = canonical_contract(KEY)["business_keys"][0]
    original = source[0][bk]
    assert raw.read_bytes().count(original.encode()) == 1
    raw.write_bytes(raw.read_bytes().replace(original.encode(), b"TAMPERED-KEY", 1))
    broken = c.get(f"{RUNTIME}/datasets/{name}/records", headers=headers)
    assert broken.status_code == 503, broken.text[:200]
    assert "TAMPERED-KEY" not in broken.text
    assert (sdk.ERR_UNAVAILABLE, "RAW_CHECKSUM_MISMATCH") in reasons, reasons


def test_each_write_gate_refuses_on_its_own_when_earlier_ones_are_peeled(host, monkeypatch):
    """⚠️ **대조군이다 — 제품 동작의 증거가 아니다.** 앞 관문을 걷어 내고 다음 관문이 스스로 막는지 본다.

    ① 정책 판정을 WRITE 에 한해 통과시킨다 → **계약 행동** 관문이 막아야 한다.
    ② 계약 행동도 통과시킨다 → **provider** 관문이 FILE_SNAPSHOT 쓰기를 막아야 한다.
      Native 로 떨어지면(폴백) 운영 평면에 줄이 생긴다 — 그것이 이 대조가 잡으려는 것이다.
    (두 단계를 한 흐름에서 차례로 본다 — 승인·게시·승격 한 번에 약 1분 반이 든다.)"""
    from api.routes import app_data_runtime as route
    from core import app_policy, kit_app_builder as kb
    release_id, ds, headers, _ = _operate(host)
    c, name, plane = host["client"], kb.runtime_name(KEY), host["operational"]
    reasons, writes = [], []
    real_fail, real_judge, real_contract = route._fail, route._judge, route._assert_contract_action
    monkeypatch.setattr(route, "_fail", lambda code, **kw: (reasons.append(kw.get("audit_reason", "")),
                                                           real_fail(code, **kw))[1])
    real_create = plane.create_record
    monkeypatch.setattr(plane, "create_record", lambda *a, **k: (writes.append(a), real_create(*a, **k))[1])

    def attempt():
        reasons.clear()
        r = c.post(f"{RUNTIME}/datasets/{name}/records", headers=headers,
                   json={"payload": {"unrestricted_quantity": 5}})
        assert r.status_code == 403, r.text[:200]
        assert writes == [] and plane.count_records(ds["dataset_id"]) == 0, "Native 로 떨어져 썼다"
        return list(reasons)

    monkeypatch.setattr(route, "_judge", lambda p, proof, action, **kw: None if action == app_policy.WRITE
                        else real_judge(p, proof, action, **kw))
    assert attempt() == [f"{app_policy.DENY_DATASET_ACTION}:create"]
    monkeypatch.setattr(route, "_assert_contract_action", lambda proof, ds, need, **kw: None
                        if need == "create" else real_contract(proof, ds, need, **kw))
    assert attempt() == ["WRITE_NOT_ALLOWED_FOR_PROVIDER:FILE_SNAPSHOT"]
