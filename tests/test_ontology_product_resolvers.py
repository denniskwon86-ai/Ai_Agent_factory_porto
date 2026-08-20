"""★★★ [MVP-P0 ①-B] **제품 Resolver 를 실제 저장소로** 검증한다.

## 왜 이 파일이 필요한가 (2026-08-20 Supervisor 재감사)

이식과 함께 들어온 시험 23건은 **가짜 Resolver 를 주입한 시험용 앱**을 본다. 그것은
「올바른 Resolver 가 주어지면 동작한다」를 증명하지만 「제품에 올라간 것이 회사·조직·
승인 원장과 연결됐다」는 증명하지 않는다.

⚠️⚠️ 그 빈틈 때문에 **승인이 항상 거부되는 결함**이 회귀 4,291건 초록 아래에 숨어
  있었다 — `event["actor"]` 를 읽었는데 원장의 실제 필드는 `actor_id` 다. 「대조한다」고
  적혀 있었지만 대조되는 것이 없었다.

★ 그래서 여기서는 **진짜 원장**에 이벤트를 넣고 제품 Resolver 를 그대로 부른다.
"""
import threading

import pytest

from core import ontology_resolvers as R
from core.ontology_runtime import ObjectRef, OntologyRuntime


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """격리된 진짜 원장. ⚠️ 운영 원장을 쓰지 않는다."""
    from core.decision_ledger import DecisionLedger
    import core.decision_ledger as dl

    lg = DecisionLedger(db_path=str(tmp_path / "ledger.db"))
    monkeypatch.setattr(dl, "decision_ledger", lg, raising=False)
    return lg


def _approve(ledger, *, event_type, subject_type, subject_id, actor):
    return ledger.append(event_type=event_type, subject_type=subject_type,
                         subject_id=subject_id, actor_type="user", actor_id=actor,
                         decision="APPROVED", rationale="시험")


# ── 승인 판정 ────────────────────────────────────────────────────────────
def test_실제_원장_승인이_통과한다(ledger):
    """★★★ **이것이 종전에 항상 거짓이었다.** 필드 이름 하나(`actor` vs `actor_id`)로."""
    ev = _approve(ledger, event_type="ONTOLOGY_RELATION_APPROVED",
                  subject_type="ontology_relation", subject_id="rel_1", actor="u@x")
    assert R.product_approval_resolver(ev["event_id"], "RELATION_APPROVE", "u@x",
                                       "relation", "rel_1") is True


def test_다른_관계의_승인을_재사용할_수_없다(ledger):
    """★★★ 승인은 「누가」와 **「무엇을」**이 같이 있어야 승인이다.

    ⚠️ 대상을 안 보면 같은 행위자의 승인 하나로 **아무 관계나** 통과한다."""
    ev = _approve(ledger, event_type="ONTOLOGY_RELATION_APPROVED",
                  subject_type="ontology_relation", subject_id="rel_1", actor="u@x")
    assert R.product_approval_resolver(ev["event_id"], "RELATION_APPROVE", "u@x",
                                       "relation", "rel_다른것") is False


def test_범용_결정_이벤트는_온톨로지_승인이_아니다(ledger):
    """★★★ 종전에는 `DECISION_RECORDED` 를 관계 승인으로 받아들이려 했다.

    ⚠️ 그러면 원장은 승인 기록이 아니라 접속 기록이 된다."""
    ev = _approve(ledger, event_type="DECISION_RECORDED",
                  subject_type="ontology_relation", subject_id="rel_1", actor="u@x")
    assert R.product_approval_resolver(ev["event_id"], "RELATION_APPROVE", "u@x",
                                       "relation", "rel_1") is False


def test_대상_종류가_다르면_승인이_아니다(ledger):
    """⚠️ 관계 승인 이벤트로 **계약을 설치**할 수 없다."""
    ev = _approve(ledger, event_type="ONTOLOGY_RELATION_APPROVED",
                  subject_type="ontology_relation", subject_id="fp_계약", actor="u@x")
    assert R.product_approval_resolver(ev["event_id"], "MODEL_INSTALL", "u@x",
                                       "model_contract", "fp_계약") is False


def test_다른_사람의_승인으로_내_행위를_통과시키지_못한다(ledger):
    ev = _approve(ledger, event_type="ONTOLOGY_RELATION_APPROVED",
                  subject_type="ontology_relation", subject_id="rel_1", actor="approver@x")
    assert R.product_approval_resolver(ev["event_id"], "RELATION_APPROVE", "actor@x",
                                       "relation", "rel_1") is False


def test_철회된_승인은_더_이상_유효하지_않다(ledger):
    """★★★ 승인 뒤에 철회가 붙으면 그 승인은 죽는다.

    ⚠️ 원장은 지우지 않는다 — 그래서 «철회 이벤트가 가리키는가» 로 판정해야 한다."""
    ev = _approve(ledger, event_type="ONTOLOGY_RELATION_APPROVED",
                  subject_type="ontology_relation", subject_id="rel_1", actor="u@x")
    assert R.product_approval_resolver(ev["event_id"], "RELATION_APPROVE", "u@x",
                                       "relation", "rel_1") is True
    ledger.append(event_type="ONTOLOGY_APPROVAL_REVOKED",
                  subject_type="ontology_relation", subject_id="rel_1",
                  actor_type="user", actor_id="u@x", decision="REVOKED",
                  rationale="철회", parent_event_id=ev["event_id"])
    assert R.product_approval_resolver(ev["event_id"], "RELATION_APPROVE", "u@x",
                                       "relation", "rel_1") is False


def test_대상이_없으면_승인하지_않는다(ledger):
    ev = _approve(ledger, event_type="ONTOLOGY_RELATION_APPROVED",
                  subject_type="ontology_relation", subject_id="rel_1", actor="u@x")
    assert R.product_approval_resolver(ev["event_id"], "RELATION_APPROVE", "u@x") is False


def test_없는_이벤트는_승인이_아니다(ledger):
    assert R.product_approval_resolver("evt_없음", "RELATION_APPROVE", "u@x",
                                       "relation", "rel_1") is False


# ── 범위 해석 ────────────────────────────────────────────────────────────
def test_ecm_노드는_소속_법인의_실행모드를_따른다(tmp_path, monkeypatch):
    """★★★ [P1-2] 가상 조직 노드를 **REAL 로 판정하면 안 된다.**

    ⚠️ 시나리오 관계와 실제 관계가 섞이면, 가정으로 만든 사실이 실적으로 읽힌다."""
    from core.enterprise_context.models import (STATUS_ACTIVE, EnterpriseEntity,
                                                OrganizationNode)
    from core.enterprise_context.repository import ecm_repository

    #: ⚠️ conftest 가 저장소 경로를 tmp 로 옮기므로 **스키마를 다시 만든다.**
    #:   안 하면 `no such table` 이고, 그것을 「없다」로 읽으면 시험이 통제가 아니라
    #:   하니스 고장을 보게 된다.
    ecm_repository._init_db()

    #: ⚠️ 제품 규칙: **가상 법인은 원본(base_entity_id)이 있어야 한다.** 계보 없는
    #:   가상 조직은 「어느 실제 조직에서 나왔나」에 답할 수 없다 — 그 거부는 옳다.
    base = ecm_repository.upsert_entity(EnterpriseEntity(
        entity_id="ent_real_t", tenant_id="tenant_default", name_ko="실제 법인(시험)",
        entity_type="legal_entity", entity_mode="REAL", status=STATUS_ACTIVE))
    ent = ecm_repository.upsert_entity(EnterpriseEntity(
        entity_id="ent_virtual_t", tenant_id="tenant_default", name_ko="가상 법인(시험)",
        entity_type="legal_entity", entity_mode="VIRTUAL",
        base_entity_id=base.entity_id, status=STATUS_ACTIVE))
    ecm_repository.upsert_node(OrganizationNode(
        node_id="node_virtual_t", entity_id=ent.entity_id, tenant_id="tenant_default",
        node_type="business_division", code="VT", name_ko="가상 사업부(시험)",
        status=STATUS_ACTIVE))

    scope = R.product_object_scope_resolver(
        ObjectRef("ecm", "organization_node", "node_virtual_t"))
    assert scope is not None, "노드를 찾지 못했다 — 시험 전제가 깨졌다"
    assert scope.entity_mode == "VIRTUAL", (
        f"가상 조직을 «{scope.entity_mode}» 로 판정했다 — 시나리오가 실적으로 섞인다")


@pytest.mark.parametrize("namespace", ["dataset", "mdm", "external", "g4",
                                       "decision", "knowledge"])
def test_배선되지_않은_namespace_는_장애로_올라온다(namespace):
    """★★★ [P0-3] 미배선을 `None` 으로 두면 «그 객체가 안 보인다» 가 된다.

    ⚠️ 그러면 런타임이 경로를 조용히 지우고 화면은 「영향 경로 없음」을 그린다 —
      사용자는 그것을 **사실**로 읽는다. 배선이 없는 것은 사실이 아니라 우리 쪽
      미완성이므로, **503 으로 드러나야** 한다."""
    with pytest.raises(R.OntologyResolverError):
        R.product_object_scope_resolver(ObjectRef(namespace, "some_type", "some_id"))


def test_없는_객체와_저장소_장애를_다르게_답한다(monkeypatch):
    """★★★ [P0-3] **대조군.** 「없다」와 「못 읽었다」가 같아지면 통제가 사라진다.

    · 없는 조직 노드   → `None`(경로에서 지운다 — 존재를 누설하지 않는다)
    · 저장소가 흔들림  → `OntologyResolverError`(→ 503)"""
    from core.enterprise_context.repository import ecm_repository

    #: ① 없는 것은 없는 것이다.
    assert R.product_object_scope_resolver(
        ObjectRef("ecm", "organization_node", "node_없는것_확실히")) is None

    #: ② 저장소 장애는 «없음» 이 아니다.
    def boom(_node_id):
        raise RuntimeError("저장소가 응답하지 않습니다")

    monkeypatch.setattr(ecm_repository, "get_node", boom)
    with pytest.raises(R.OntologyResolverError):
        R.product_object_scope_resolver(ObjectRef("ecm", "organization_node", "node_x"))


def test_철회_뒤_무관한_이벤트가_쌓여도_되살아나지_않는다(ledger):
    """★★★ [P0-2] `list_events()` 는 `LIMIT` 이 있다.

    ⚠️ 철회 뒤에 무관한 이벤트가 **100건 넘게** 쌓이면 철회가 조회 범위 밖으로 밀려나고
      **원 승인이 되살아난다.** 전용 API 는 제한 없이 인덱스로 묻는다."""
    ev = _approve(ledger, event_type="ONTOLOGY_RELATION_APPROVED",
                  subject_type="ontology_relation", subject_id="rel_1", actor="u@x")
    ledger.append(event_type="ONTOLOGY_APPROVAL_REVOKED",
                  subject_type="ontology_relation", subject_id="rel_1",
                  actor_type="user", actor_id="u@x", decision="REVOKED",
                  rationale="철회", parent_event_id=ev["event_id"])

    #: 무관한 이벤트를 101건 쌓는다 — 종전 구현이면 여기서 철회가 밀려난다.
    for n in range(101):
        ledger.append(event_type="DECISION_RECORDED", subject_type="decision_case",
                      subject_id=f"case_{n}", actor_type="user", actor_id="other@x",
                      decision="RECORDED", rationale="무관")

    assert R.product_approval_resolver(ev["event_id"], "RELATION_APPROVE", "u@x",
                                       "relation", "rel_1") is False, (
        "철회가 조회 범위 밖으로 밀려나 승인이 되살아났다")


def test_원장_판독_실패는_승인이_아니다(ledger, monkeypatch):
    """⚠️ 「모르니까 유효」는 승인 판정에서 가장 위험한 기본값이다."""
    ev = _approve(ledger, event_type="ONTOLOGY_RELATION_APPROVED",
                  subject_type="ontology_relation", subject_id="rel_1", actor="u@x")
    assert R.product_approval_resolver(ev["event_id"], "RELATION_APPROVE", "u@x",
                                       "relation", "rel_1") is True

    def boom(*a, **kw):
        raise RuntimeError("원장을 읽을 수 없습니다")

    #: ★★★ [2026-08-20 재감사] **`False` 가 아니라 예외다.**
    #:   `False` 로 접으면 원장 장애가 「승인이 무효다」(400)로 보이고, 사용자는
    #:   승인을 다시 요청하지만 문제는 저장소이므로 몇 번을 해도 같다. → 503 이어야 한다.
    monkeypatch.setattr(ledger, "has_invalidating_child", boom)
    with pytest.raises(Exception) as exc:
        R.product_approval_resolver(ev["event_id"], "RELATION_APPROVE", "u@x",
                                    "relation", "rel_1")
    assert not isinstance(exc.value, AssertionError)


def test_대상을_받지_않는_판정기는_주입될_수_없다(tmp_path):
    """★★★ [P0-1] 3인자 폴백을 없앴다.

    ⚠️ 폴백이 있으면 **대상 대조 없는 승인**이 다시 허용되고, Resolver 내부의
      `TypeError` 까지 「옛 계약이구나」로 오인된다. 지금은 배선 결함이 503 으로 드러난다."""
    from core.ontology_runtime import OntologyIntegrityError

    def three_arg(ledger_id, action, actor):        # 대상을 받지 않는다
        return True

    rt = OntologyRuntime(str(tmp_path / "o.db"), lambda ref: None, three_arg)
    with pytest.raises(OntologyIntegrityError):
        rt._assert_approval("evt", "RELATION_APPROVE", "u@x",
                            target_type="relation", target_id="rel_1")


def test_막힌_사유를_세어_둔다():
    """⚠️ 로그만 남기면 아무도 세지 않는다 — 「왜 경로가 비었나」에 답할 수 있어야 한다."""
    before = R.stats.snapshot().get("mdm_not_wired", 0)
    with pytest.raises(R.OntologyResolverError):
        R.product_object_scope_resolver(ObjectRef("mdm", "material", "M1"))
    assert R.stats.snapshot().get("mdm_not_wired", 0) == before + 1


# ── 지연 초기화 동시성 ───────────────────────────────────────────────────
def test_동시_최초_접근에_no_such_table_이_나지_않는다(tmp_path):
    """★★★ [P1-1] 준비 표시를 **스키마 생성 전에** 세우면 경쟁이 생긴다.

    ⚠️ ① A 가 표시 → ② 아직 표 없음 → ③ B 가 「준비됨」으로 보고 → ④ **빈 DB 에 질의**.
      사용자에게는 «온톨로지가 고장» 으로 보인다."""
    rt = OntologyRuntime(str(tmp_path / "race.db"))
    errors = []
    ready = threading.Barrier(8)

    def go():
        try:
            ready.wait(timeout=10)
            rt.model_status()
        except Exception as exc:            # pragma: no cover - 실패 시에만
            errors.append(repr(exc))

    threads = [threading.Thread(target=go) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not errors, "동시 최초 접근에서 실패했습니다:\n  " + "\n  ".join(errors[:4])


# ── 후속 보정 회귀 (2026-08-20 재감사) ──────────────────────────────────
def test_빈_실행문맥은_자료_불일치이지_비노출이_아니다(monkeypatch):
    """★★★ `entity_mode` 가 비어 있는 것은 **자료 불일치**다.

    ⚠️ `None`(=안 보인다)로 두면 화면이 「영향 경로 없음」을 그리고 사람은 그것을
      사실로 읽는다 — 실제로는 REAL/VIRTUAL 을 모르는 상태다."""
    from core.enterprise_context.repository import ecm_repository

    class _Node:
        node_id, entity_id, tenant_id, dept_id, status = "n1", "e1", "t", "d", "ACTIVE"

    class _Entity:
        entity_mode = ""            # ⚠️ 비어 있다

    monkeypatch.setattr(ecm_repository, "get_node", lambda _i: _Node())
    monkeypatch.setattr(ecm_repository, "get_entity", lambda _i: _Entity())
    with pytest.raises(R.OntologyResolverError):
        R.product_object_scope_resolver(ObjectRef("ecm", "organization_node", "n1"))


def test_원장_판독_실패는_이벤트_없음과_구분된다(ledger, monkeypatch):
    """★★★ `get_event()` 는 DB 장애를 `None` 으로 접는다 — 승인 판정에서는 그것이
    「승인 이벤트가 없다」와 같아진다.

    ⚠️ 승인처럼 «모르면 막아야 하는» 자리는 **모른다는 사실 자체를** 알아야 한다."""
    ev = _approve(ledger, event_type="ONTOLOGY_RELATION_APPROVED",
                  subject_type="ontology_relation", subject_id="rel_1", actor="u@x")
    assert R.product_approval_resolver(ev["event_id"], "RELATION_APPROVE", "u@x",
                                       "relation", "rel_1") is True

    def boom(_eid):
        from core.decision_ledger import DecisionLedgerError
        raise DecisionLedgerError("원장을 읽지 못했습니다")

    #: ★★★ 예외가 **그대로 올라온다** — 런타임이 503 으로 바꾼다.
    monkeypatch.setattr(ledger, "get_event_strict", boom)
    before = R.stats.snapshot().get("approval_ledger_unreadable", 0)
    with pytest.raises(Exception):
        R.product_approval_resolver(ev["event_id"], "RELATION_APPROVE", "u@x",
                                    "relation", "rel_1")
    #: ★ 그리고 그 사유가 «없음» 이 아니라 «못 읽음» 으로 세어져야 한다.
    assert R.stats.snapshot().get("approval_ledger_unreadable", 0) == before + 1


def test_모델_계약_승인도_철회할_수_있다(ledger):
    """★★★ 철회 주체를 `ontology_relation` 으로 고정하면 **잘못 설치된 계약을 되돌릴
    방법이 없다.**"""
    ev = _approve(ledger, event_type="ONTOLOGY_MODEL_APPROVED",
                  subject_type="ontology_model_contract", subject_id="fp_계약",
                  actor="u@x")
    assert R.product_approval_resolver(ev["event_id"], "MODEL_INSTALL", "u@x",
                                       "model_contract", "fp_계약") is True

    ledger.append(event_type="ONTOLOGY_APPROVAL_REVOKED",
                  subject_type="ontology_model_contract", subject_id="fp_계약",
                  actor_type="user", actor_id="u@x", decision="REVOKED",
                  rationale="계약 철회", parent_event_id=ev["event_id"])
    assert R.product_approval_resolver(ev["event_id"], "MODEL_INSTALL", "u@x",
                                       "model_contract", "fp_계약") is False


def test_부모_없는_철회는_기록될_수_없다(ledger):
    """⚠️ 부모 없는 철회는 아무것도 무효로 만들지 못하면서 「철회했다」는 기록만 남긴다."""
    from core.decision_ledger import DecisionLedgerError

    with pytest.raises(DecisionLedgerError):
        ledger.append(event_type="ONTOLOGY_APPROVAL_REVOKED",
                      subject_type="ontology_relation", subject_id="rel_1",
                      actor_type="user", actor_id="u@x", decision="REVOKED",
                      rationale="부모 없음")


def test_원장_장애는_승인_무효가_아니라_503_이_된다(ledger, monkeypatch, tmp_path):
    """★★★ [2026-08-20 재감사 P0-1] 장애를 `False` 로 접으면 **400 처럼 보인다.**

    ⚠️ 사용자는 「승인을 안 받았구나」로 읽고 승인을 다시 요청한다. 실제 문제는
      저장소이므로 몇 번을 해도 같다 — 그 화면은 사람을 잘못된 곳으로 보낸다."""
    from core.ontology_runtime import OntologyIntegrityError, OntologyRuntime

    ev = _approve(ledger, event_type="ONTOLOGY_RELATION_APPROVED",
                  subject_type="ontology_relation", subject_id="rel_1", actor="u@x")

    def boom(_eid):
        from core.decision_ledger import DecisionLedgerError
        raise DecisionLedgerError("원장을 읽지 못했습니다")

    monkeypatch.setattr(ledger, "get_event_strict", boom)
    rt = OntologyRuntime(str(tmp_path / "o.db"), lambda ref: None,
                         R.product_approval_resolver)
    with pytest.raises(OntologyIntegrityError):
        rt._assert_approval(ev["event_id"], "RELATION_APPROVE", "u@x",
                            target_type="relation", target_id="rel_1")


def test_철회는_원_승인과_같은_대상이어야_한다(ledger):
    """★★★ [2026-08-20 재감사 P1] 부모 연결만 보면 **다른 관계 id 를 적은 철회**로도
    원 승인을 무효화할 수 있다.

    ⚠️ 그러면 「무엇이 철회됐는가」가 이력에서 어긋나고, 감사에서 두 기록이 서로 다른
      대상을 가리킨다."""
    from core.decision_ledger import DecisionLedgerError

    ev = _approve(ledger, event_type="ONTOLOGY_RELATION_APPROVED",
                  subject_type="ontology_relation", subject_id="rel_1", actor="u@x")

    #: ① 다른 관계 id 로는 철회할 수 없다.
    with pytest.raises(DecisionLedgerError):
        ledger.append(event_type="ONTOLOGY_APPROVAL_REVOKED",
                      subject_type="ontology_relation", subject_id="rel_다른것",
                      actor_type="user", actor_id="u@x", decision="REVOKED",
                      rationale="엉뚱한 대상", parent_event_id=ev["event_id"])

    #: ② 대상 종류가 달라도 안 된다.
    with pytest.raises(DecisionLedgerError):
        ledger.append(event_type="ONTOLOGY_APPROVAL_REVOKED",
                      subject_type="ontology_model_contract", subject_id="rel_1",
                      actor_type="user", actor_id="u@x", decision="REVOKED",
                      rationale="종류 불일치", parent_event_id=ev["event_id"])

    #: ③ 온톨로지 승인이 아닌 부모도 안 된다.
    other = ledger.append(event_type="DECISION_RECORDED", subject_type="decision_case",
                          subject_id="case_1", actor_type="user", actor_id="u@x",
                          decision="RECORDED", rationale="무관")
    with pytest.raises(DecisionLedgerError):
        ledger.append(event_type="ONTOLOGY_APPROVAL_REVOKED",
                      subject_type="ontology_relation", subject_id="rel_1",
                      actor_type="user", actor_id="u@x", decision="REVOKED",
                      rationale="엉뚱한 부모", parent_event_id=other["event_id"])

    #: ★ 대조군 — 같은 대상이면 철회된다.
    ledger.append(event_type="ONTOLOGY_APPROVAL_REVOKED",
                  subject_type="ontology_relation", subject_id="rel_1",
                  actor_type="user", actor_id="u@x", decision="REVOKED",
                  rationale="정상 철회", parent_event_id=ev["event_id"])
    assert R.product_approval_resolver(ev["event_id"], "RELATION_APPROVE", "u@x",
                                       "relation", "rel_1") is False
