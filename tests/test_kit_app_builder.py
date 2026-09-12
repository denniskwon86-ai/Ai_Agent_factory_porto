"""★★★ **키트 청사진 → 실제 앱** 을 검증한다. (2026-08-23)

## 이 파일이 지키는 것

    ① 막힌 산출물로 앱을 **만들지 않는다** — 빈 화면이 「자료가 없다」로 읽힌다
    ② 준비도 판정을 **다시 하지 않는다** — 두 곳에서 판정하면 규칙이 갈라진다
    ③ 스키마를 **지어내지 않는다** — 계약과 실제 자료가 조용히 갈라진다
    ④ 같은 앱을 다시 만들면 **같은 자리를 이어받는다** — 레코드가 사라지지 않는다
    ⑤ 실체화 실패를 **「만들었는데 비었다」로 접지 않는다**

⚠️⚠️ 이 기능이 없어서 12분 여정의 「키트로 앱 생성」 칸이 한 번도 열린 적이 없었다.
  준비도 보드는 `READY` 를 그리는데 누를 것이 없었다 — **보여 주는 것과 되는 것이 달랐다.**
"""
import pytest

from core import kit_app_builder as kb
from core.data_preparation import readiness

BLUEPRINT = {"app_id": "APP-01", "name": "원료 도입계획·추적",
             "datasets": ["PRC-01", "LOG-02"]}

#: ★ 계약을 만들려면 **부르는 쪽이 정해야 하는 것**들. 기본값으로 숨기지 않는다.
CTX = {"project_id": "ki_1", "app_class": "departmental"}

#: 인증판이 들고 있는 스키마 대역. ⚠️ 여기서 «내 말로» 쓰지 않는다 —
#:   모양(`{name, type}`)은 `snapshot_service.infer_type` 이 내는 것과 같다.
SCHEMA = {"PRC-01": [{"name": "po_id", "type": "string"},
                     {"name": "as_of_date", "type": "date"}],
          "LOG-02": [{"name": "shipment_id", "type": "string"}]}


def _draft(blueprint=None, **kw):
    kw = {**CTX, "schema_for": lambda k: SCHEMA.get(k, [{"name": "a", "type": "string"}]), **kw}
    return kb.contract_from_blueprint(blueprint or BLUEPRINT, **kw)


def _approved(blueprint=None):
    """사람이 승인한 계약 대역. ⚠️ **시험에서만** 상태를 올린다 — 제품 코드는 절대
    스스로 승인하지 않는다(요청자가 승인자 자리에 앉는다)."""
    from core import app_runtime_contract as arc

    c = _draft(blueprint)
    c["status"] = arc.STATUS_APPROVED
    c["approval"] = {"status": "APPROVED", "approved_by": "approver@afs.invalid",
                     "approved_at": "2026-08-23T00:00:00+00:00",
                     "decision_ledger_id": "dl_test"}
    c["semantic_fingerprint"] = arc.semantic_fingerprint(c)
    #: ★★★ 대역이 **정본 스키마를 통과하는지** 여기서 확인한다. 안 하면 시험만
    #:   통과하는 계약으로 26건이 초록이 된다(fixture 가 계약을 대신 정의하는 함정).
    assert arc.validate(c) == [], arc.validate(c)
    return c


def _out(state, **kw):
    row = {"output": "APP-01", "state": state}
    row.update(kw)
    return [row]


# ── ③ 번역 ──────────────────────────────────────────────────────────────

def test_청사진을_런타임_계약으로_옮긴다():
    """★★★ 결과가 **정본 스키마를 통과해야** 한다.

    ⚠️⚠️ 종전 판은 `{app_id, name, revision, status, datasets}` 를 냈다. 정본 스키마는
      필수 13칸에 `additionalProperties: false` 다 — **계약이 아니었다.** 그런데도
      물질화까지 통과했다(실체화기가 `status` 만 본다). 스키마를 안 보고 내 말로 쓰면
      끝까지 아무도 안 막는다."""
    from core import app_runtime_contract as arc

    c = _draft()
    assert arc.validate(c) == [], arc.validate(c)
    assert c["task_id"] == "APP-01"
    #: ★ 이름은 문법에 맞게 접히고, 계약키는 **따로** 남는다.
    assert [d["name"] for d in c["datasets"]] == ["prc_01", "log_02"]
    assert [d["enterprise_contract_key"] for d in c["datasets"]] == ["PRC-01", "LOG-02"]
    for d in c["datasets"]:
        assert d["source_intent"] == kb.SOURCE_INTENT
        assert d["data_role"] == kb.ENTERPRISE_ACTUAL
        assert d["allowed_actions"] == ["read"]


def test_계약키를_이름칸에_그대로_넣지_않는다():
    """⚠️ `PRC-01` 은 이름 문법(`^[a-z][a-z0-9_]{0,63}$`)에 맞지 않는다."""
    assert kb.runtime_name("PRC-01") == "prc_01"
    assert kb.runtime_name("EXT-03") == "ext_03"


def test_두_계약키가_같은_이름으로_접히면_거부한다():
    """⚠️ 접히면 런타임이 어느 쪽인지 모른다 — 조용히 하나를 덮어쓴다."""
    with pytest.raises(kb.KitAppError) as err:
        _draft({"app_id": "APP-X", "datasets": ["PRC-01", "prc.01"]})
    assert "접힙니다" in str(err.value)


def test_app_class_를_추측하지_않는다():
    """★ `app_manifest` 가 「모르면 departmental 로 두지 않고 비워 둔다 — 추측한
    분류는 나중에 권한 판단의 근거로 쓰인다」라고 적어 두었다."""
    with pytest.raises(kb.KitAppError) as err:
        kb.contract_from_blueprint(BLUEPRINT, project_id="ki_1", app_class="")
    assert "app_class" in str(err.value)


def test_필드_이름을_조용히_고치지_않는다():
    """⚠️ 이름을 바꾸면 계약의 칸과 실제 자료의 칸이 갈라지고, 화면은 늘 빈 칸을 그린다."""
    with pytest.raises(kb.KitAppError) as err:
        _draft(schema_for=lambda k: [{"name": "PO Id", "type": "string"}])
    assert "인증 단계에서" in str(err.value)


def test_읽기_전용인데_중복입력_정책이_아무것도_안_막지_않는다():
    """★★★ Zero Duplicate Entry Gate — 권위 원천(ERP)이 있으면 **금지**다."""
    c = _draft()
    for d in c["datasets"]:
        assert d["duplicate_entry_policy"] == "DENY_IF_AUTHORITATIVE_SOURCE_EXISTS"


def test_스키마를_지어내지_않는다():
    """★★★ 필드는 **인증판이 들고 있다.** 여기서 만들어 넣으면 계약과 실제 자료가
    갈라지고, 그 갈림은 조용하다 — 화면은 있지도 않은 칸을 그린다.

    ★ 해석기가 없으면 필드가 없고, 그러면 **정본 스키마가 막는다**(`minItems: 1`).
      「비워 두고 나중에 채운다」가 통과하지 않는다는 것이 이 시험의 요지다."""
    with pytest.raises(kb.KitAppError) as err:
        kb.contract_from_blueprint(BLUEPRINT, **CTX)
    assert "정본 스키마" in str(err.value)

    #: 대조군 — 인증판에서 오면 그대로 들어간다(내가 만든 것이 아니다).
    c = _draft()
    assert [f["name"] for f in c["datasets"][0]["fields"]] == ["po_id", "as_of_date"]


@pytest.mark.parametrize("bad", [
    {"app_id": "", "datasets": ["PRC-01"]},
    {"app_id": "APP-01", "datasets": []},
    {"app_id": "APP-01"},
])
def test_모양이_안_맞으면_거부한다(bad):
    """⚠️ 데이터 없는 앱은 화면이 열리는데 한 줄도 안 보인다 — 사용자는 그것을
    「데이터가 없다」로 읽는다."""
    with pytest.raises(kb.KitAppError):
        kb.contract_from_blueprint(bad, **CTX)


def test_릴리스_식별자가_결정론적이다():
    """★ 같은 인스턴스·같은 앱은 **같은 자리**를 이어받는다. 새로 만들면 현업이 쌓은
    레코드가 승계되지 않는다 — 「앱을 개정하면 데이터가 사라진다」가 그것이다."""
    a = kb.release_id_for("ki_1", "APP-01")
    assert a == kb.release_id_for("ki_1", "APP-01")
    assert a != kb.release_id_for("ki_2", "APP-01")
    assert a != kb.release_id_for("ki_1", "APP-02")


# ── ① 막힌 것을 만들지 않는다 ───────────────────────────────────────────

def test_막힌_산출물로_앱을_만들지_않는다():
    """★★★ **이 파일의 핵심.**

    ⚠️⚠️ 「일부 데이터로라도 열어 주자」가 위험하다. 열린 앱은 **빈 화면**을 보여 주고,
      사용자는 그것을 「우리 회사에 자료가 없다」로 읽는다 — 실제로는 우리가 아직
      준비하지 못한 것이다."""
    with pytest.raises(kb.KitAppError) as err:
        kb.build(blueprint=BLUEPRINT, instance_id="ki_1",
                 outputs=_out(readiness.BLOCKED_OUTPUT,
                              user_message="«LOG-02» 데이터가 아직 준비되지 않았습니다.",
                              next_action="원천을 연결하십시오."),
                 actor_id="a@afs.invalid", store=None, app_data=None,
                 tenant_id="t", scope_node_id="s", entity_mode="VIRTUAL")
    #: ★ 준비도가 이미 만들어 둔 사유와 다음 행동을 **그대로** 전한다 — 여기서 새 문구를
    #:   지으면 같은 사실이 두 가지로 설명된다.
    assert "LOG-02" in str(err.value)
    assert "원천을 연결하십시오" in str(err.value)


def test_준비도에_없는_산출물은_만들지_않는다():
    """⚠️ 「찾지 못했다」를 «괜찮다» 로 읽지 않는다 — 오타 하나가 앱을 통과시킨다."""
    with pytest.raises(kb.KitAppError) as err:
        kb.build(blueprint=BLUEPRINT, instance_id="ki_1", outputs=[],
                 actor_id="a@afs.invalid", store=None, app_data=None,
                 tenant_id="t", scope_node_id="s", entity_mode="VIRTUAL")
    assert "확인하지 못했습니다" in str(err.value)


@pytest.mark.parametrize("missing", [
    {"instance_id": ""}, {"actor_id": ""},
])
def test_누가_어디에_만드는지_없으면_거부한다(missing):
    """⚠️ 만든 사람이 없으면 나중에 「이 앱은 왜 있나」에 답할 수 없다."""
    kw = dict(blueprint=BLUEPRINT, instance_id="ki_1",
              outputs=_out(readiness.AVAILABLE), actor_id="a@afs.invalid",
              store=None, app_data=None, tenant_id="t", scope_node_id="s",
              entity_mode="VIRTUAL")
    kw.update(missing)
    with pytest.raises(kb.KitAppError):
        kb.build(**kw)


# ── ② 판정을 다시 하지 않는다 ───────────────────────────────────────────

def test_준비도_판정을_스스로_다시_하지_않는다():
    """★ 상태는 `readiness` 가 정한다 — 두 곳에서 판정하면 규칙이 갈라지고, 갈라진
    규칙은 언젠가 한쪽만 고쳐진다.

    ★ 산문이 아니라 **구문 나무**를 본다(주석·문자열은 안 잡힌다)."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path(kb.__file__).read_text(encoding="utf-8"))
    called = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "evaluate_outputs" not in called, "빌더가 준비도를 스스로 다시 판정한다"
    assert "evaluate" not in called, "빌더가 준비도를 스스로 다시 판정한다"


def test_새_물질화기를_만들지_않는다():
    """⚠️ 두 벌이 되면 「어느 쪽이 진짜 앱인가」가 갈린다 — 기존 실체화기에 맡긴다."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path(kb.__file__).read_text(encoding="utf-8"))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "cm" in names, "기존 실체화기를 쓰지 않는다"
    called = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    for forbidden in ("create_dataset", "adopt_dataset"):
        assert forbidden not in called, f"빌더가 «{forbidden}» 를 직접 부른다"


# ── ④⑤ 실제 물질화 ─────────────────────────────────────────────────────

class _FakeResult:
    def __init__(self, names):
        self.datasets = [{"name": n} for n in names]


def test_준비되면_실제로_만든다(monkeypatch):
    """★ 대조군 — 늘 막히기만 하면 그것은 기능이 아니다."""
    seen = {}

    def fake(contract, **kw):
        seen["contract"] = contract
        seen.update(kw)
        return _FakeResult([d["name"] for d in contract["datasets"]])

    monkeypatch.setattr(kb.cm, "materialize", fake)
    out = kb.build(blueprint=BLUEPRINT, approved_contract=_approved(), instance_id="ki_1",
                   outputs=_out(readiness.AVAILABLE), actor_id="a@afs.invalid",
                   store="STORE", app_data="APPDATA",
                   tenant_id="t", scope_node_id="s", entity_mode="VIRTUAL")
    assert out["app_id"] == "APP-01"
    assert out["datasets"] == ["prc_01", "log_02"]
    assert out["release_id"] == kb.release_id_for("ki_1", "APP-01")
    #: ★ 범위 세 값이 그대로 실체화기에 전달돼야 한다 — 여기서 지어내면 남의 조직에 만든다.
    assert (seen["tenant_id"], seen["scope_node_id"], seen["entity_mode"]) == (
        "t", "s", "VIRTUAL")


def test_경고_상태에서도_만들되_경고를_싣는다(monkeypatch):
    """⚠️ 「오래된 데이터」는 막을 일은 아니지만 **숨길 일도 아니다.**"""
    monkeypatch.setattr(kb.cm, "materialize",
                        lambda c, **k: _FakeResult([d["name"] for d in c["datasets"]]))
    out = kb.build(blueprint=BLUEPRINT, approved_contract=_approved(), instance_id="ki_1",
                   outputs=_out(readiness.AVAILABLE_WITH_WARNING,
                                user_message="«PRC-01» 데이터가 오래되었습니다."),
                   actor_id="a@afs.invalid", store=None, app_data=None,
                   tenant_id="t", scope_node_id="s", entity_mode="VIRTUAL")
    assert out["warning"], "경고를 삼켰다"
    assert "PRC-01" in out["warning"]


def test_실체화_실패를_빈_앱으로_접지_않는다(monkeypatch):
    """★★★ 실패 사유가 사람이 고칠 **유일한 실마리**다.

    ⚠️ 여기서 조용히 빈 결과를 돌려주면 화면에 앱이 생기고 데이터가 없다 —
      사용자는 그것을 「자료가 없다」로 읽는다."""
    def boom(contract, **kw):
        raise kb.cm.MaterializeError("PRC-01: 인증된 판이 없습니다.")

    monkeypatch.setattr(kb.cm, "materialize", boom)
    with pytest.raises(kb.KitAppError) as err:
        kb.build(blueprint=BLUEPRINT, approved_contract=_approved(), instance_id="ki_1",
                 outputs=_out(readiness.AVAILABLE), actor_id="a@afs.invalid",
                 store=None, app_data=None, tenant_id="t", scope_node_id="s",
                 entity_mode="VIRTUAL")
    assert "인증된 판이 없습니다" in str(err.value)


# ══════════════════════════════════════════════════════════════════════════
# 승인·스키마·어휘 — 실측에서 나온 관문들 (2026-08-23)
# ══════════════════════════════════════════════════════════════════════════

def test_승인되지_않은_계약으로는_만들지_않는다():
    """★★★ **요청자가 승인자 자리에 앉지 않는다.**

    ⚠️⚠️ 빌더가 `STATUS_APPROVED` 를 스스로 적으면 검토를 지나지 않은 권한이 DB 에
      들어가고, 그 결속은 다음 단계에서 «정상» 으로 봉인된다. 이 저장소가 이미 한 번
      잡은 결함이다."""
    from core import app_runtime_contract as arc

    assert _draft()["status"] == arc.STATUS_DRAFT
    assert _draft()["approval"] == {"status": "PENDING"}

    #: ① 계약을 아예 안 주면 — 물질화는 초안을 **대신 만들어 주지 않는다.**
    kw = dict(blueprint=BLUEPRINT, instance_id="ki_1",
              outputs=_out(readiness.AVAILABLE), actor_id="a@afs.invalid",
              store=None, app_data=None, tenant_id="t", scope_node_id="s",
              entity_mode="REAL")
    with pytest.raises(kb.KitAppError) as err:
        kb.build(**kw)
    assert "승인된 앱 계약이 없습니다" in str(err.value)

    #: ② 초안을 그대로 주면 — 상태를 올려 주지 않고 거부한다.
    with pytest.raises(kb.KitAppError) as err:
        kb.build(approved_contract=_draft(), **kw)
    assert "승인되지 않았습니다" in str(err.value)


def test_빌더가_스스로_승인_상태를_적지_않는다():
    """★ 산문이 아니라 **구문 나무**로 본다 — 주석의 설명은 잡히지 않는다."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path(kb.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "STATUS_APPROVED":
            #: 비교에 쓰는 것은 괜찮다. **대입**이 문제다.
            parent_assign = any(
                isinstance(a, ast.Assign) and any(
                    isinstance(t, ast.Subscript) for t in a.targets)
                for a in ast.walk(tree))
            assert parent_assign is not None
    src = Path(kb.__file__).read_text(encoding="utf-8")
    assert '"status"] = arc.STATUS_APPROVED' not in src
    assert "'status'] = arc.STATUS_APPROVED" not in src


def _certified_schema_store(tmp_path, key, schema):
    """스키마 검사도 실제 결속·보류 계약을 가진 임시 저장소를 사용한다."""
    from core.data_preparation.store import DataPreparationStore
    from core.data_preparation import models as m
    store = DataPreparationStore(str(tmp_path / "schema.db"))
    context = dict(tenant_id="test", scope_node_id="test", entity_mode="REAL")
    binding = store.create_binding(instance_id="ki_1", dataset_contract_key=key,
                                   provider=m.PROVIDER_FILE_SNAPSHOT, config={}, **context)
    snap = store.create_snapshot(instance_id="ki_1", binding_id=binding["binding_id"],
                                 dataset_contract_key=key, schema=schema, **context)
    for state in (m.PROFILED, m.STANDARDIZED, m.RECONCILED, m.DEMO_CERTIFIED):
        store.advance_snapshot(snap["snapshot_id"], state, certified_by="schema-test@afs.invalid")
    return store


def test_예약된_칸은_앱_필드가_되지_않는다(tmp_path):
    """★★★ `record_id` 같은 이름을 앱이 쓰면 **감사 표시를 위조**할 수 있다.

    ⚠️ 말없이 버리지도 않는다 — 무엇을 뺐는지 남긴다."""
    store = _certified_schema_store(tmp_path, "PRC-01", [{"name": "record_id", "type": "string"},
                                                       {"name": "po_id", "type": "string"}])
    out = kb.fields_from_certified(store, "ki_1", "PRC-01")
    assert [f["name"] for f in out] == ["po_id"], out


def test_모르는_형을_string_으로_뭉개지_않는다(tmp_path):
    """⚠️ 「모르면 string」은 **날짜 열을 글자 열로** 만들고, 기간 필터가 조용히 안 먹는다."""
    store = _certified_schema_store(tmp_path, "X", [{"name": "c", "type": "geo_point"}])
    with pytest.raises(kb.KitAppError) as err:
        kb.fields_from_certified(store, "ki_1", "X")
    assert "변환 표" in str(err.value)


def test_형_변환표가_두_어휘를_잇는다():
    """★ 인증판은 `datetime` 을 내고 앱은 `date` 만 받는다 — 표로 못박는다."""
    assert kb.FIELD_TYPE_MAP["datetime"] == "date"
    assert kb.FIELD_TYPE_MAP["number"] == "number"
    assert kb.FIELD_TYPE_MAP["unknown"] == "string"


def test_인증되지_않은_판의_스키마는_쓰지_않는다():
    """⚠️ 검토를 지나지 않은 모양으로 앱을 만들면, 그 앱은 승인된 적 없는 칸을 그린다."""
    class _Store:
        def list_snapshots(self, _i):
            return [{"dataset_contract_key": "X", "state": "RECONCILED",
                     "snapshot_id": "ds_1",
                     "schema": [{"name": "c", "type": "string"}]}]

    assert kb.fields_from_certified(_Store(), "ki_1", "X") == []
