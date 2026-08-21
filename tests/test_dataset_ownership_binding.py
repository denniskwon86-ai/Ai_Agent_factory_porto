"""★★★ [G2 · Dataset Ownership Binding] 「어느 부서가 이 데이터셋을 소유하는가」의 정본 회귀.

## 이 파일이 지키는 계약

    (tenant_id, entity_mode, dataset_contract_key, scope_node_id, 유효기간) → owner_dept_id

**업무 데이터 행이 선언하지 않는다.** 자기 데이터의 권한 범위를 데이터가 스스로 정하면
그것이 곧 자기진술 통제다 — 직전에 지운 `calc_binding` 과 같은 유형이다.

`object_scope_index.owner_dept_id` 는 정본이 아니라 **물질화된 결과**이고,
`owner_binding_id`·`owner_binding_fingerprint` 를 함께 봉인한다.

## 세는 규칙

★ **「안 보인다」와 「고쳐야 한다」를 가른다.** 결속 없음은 `RESOURCE_UNBOUND`(정상적인
  비노출), 중첩·없는 부서·원장 장애는 **503**(점검 필요)다. 뭉개면 아무도 고치지 않는다.
"""
import os
import sqlite3
import tempfile

import pytest

from core.data_preparation import ownership_binding as ob

T, M, K, S = "tenant_default", "REAL", "FND-01", "node_hq"
DEPT = "hq"


#: ★ 승인·철회 행위자. **실재하는 데이터 표준 승인자**여야 한다(4.1c-B P0-1·P0-4).
APPROVERS = ("approver@afs.invalid", "other@afs.invalid", "second@afs.invalid",
             "x@afs.invalid", "new@afs.invalid", "legacy@afs.invalid",
             "auditor@afs.invalid", "std@afs.invalid")


@pytest.fixture()
def org(monkeypatch, tmp_path):
    """★★★ **실제 조직도**를 세운다 — 부트스트랩이 아니고, 승인자는 실재하는 사용자다.

    ⚠️⚠️ [4.1c-B P0-1] 앞 판은 조직도를 세우지 않았다. 그래서 `resolve_scope()` 가
      부트스트랩 예외로 **미등록 사용자에게도 전권**을 주는 상태에서 모든 승인이 통과했다.
      즉 41건의 시험이 「승인 권한 검사」를 지나지 않고 초록이었다. 조직도를 세우는 순간
      그 41건이 빨개졌고, 그것이 구멍의 크기다.
    ⚠️ 임의 부서를 만들지 않는다 — `hq` 하나만 쓴다(실제 조직에 임의 배정 금지 규칙)."""
    from core.decision_ledger import decision_ledger
    from core.org_directory import OrgDirectory
    import core.org_directory as orgmod

    o = OrgDirectory(db_path=str(tmp_path / "org.db"))
    o.create_department(DEPT, "본사")
    for uid in APPROVERS:
        o.upsert_user(uid, uid.split("@")[0], primary_dept_id=DEPT,
                      is_data_admin=True, actor="seed")
    monkeypatch.setattr(orgmod, "org_directory", o)
    #: ⚠️ 원장도 격리한다. 실 원장에 시험 승인 사건을 쌓으면 제품 감사 이력에 섞인다.
    monkeypatch.setattr(decision_ledger, "db_path", str(tmp_path / "ledger.db"),
                        raising=False)
    return o


@pytest.fixture()
def conn(org):
    """격리 소유권 DB. 스키마는 **초기화에서만** 만든다."""
    path = os.path.join(tempfile.mkdtemp(), "own.db")
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    ob.ensure_schema(c)
    yield c
    c.close()


def _declare(conn, **kw):
    """★ 승인 **원장 사건**을 먼저 남기고 그 id 로 등록한다.

    ⚠️ 첫 판은 `approved_by` 문자열만 넘겼다 — 그것은 승인이 아니라 자기진술이다."""
    args = dict(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                owner_dept_id=DEPT, evidence_ref="FND-01/v1#seed")
    args.update(kw)
    actor = args.pop("approved_by", "approver@afs.invalid")
    ap = ob.approve(actor_id=actor, **args)
    return ob.declare(conn, approved_by=actor,
                      approval_event_id=ap["approval_event_id"],
                      effective_from=ap["effective_from"],
                      **{k: v for k, v in args.items() if k != "effective_from"})


def _resolve(conn, **kw):
    args = dict(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S)
    args.update(kw)
    return ob.resolve(conn, **args)


# ── ① 승인된 정확한 결속만 해석 ────────────────────────────────────────────

def test_승인된_결속만_해석된다(conn):
    b = _declare(conn)
    got = _resolve(conn)
    assert got and got["owner_dept_id"] == DEPT
    assert got["binding_id"] == b["binding_id"]
    assert got["approved_by"] == "approver@afs.invalid"
    #: ★ 근거가 없으면 나중에 아무도 뒤집을 수 없다 — 지문에 근거까지 들어간다.
    assert got["evidence_ref"] == "FND-01/v1#seed"


def test_승인자_없이는_만들_수_없다(conn):
    """★ 승인 **사건**부터 못 남긴다 — 행위자 없는 승인은 승인이 아니다."""
    with pytest.raises(ob.OwnershipError, match="행위자"):
        _declare(conn, approved_by="")


def test_승인_사건_id_없이는_등록할_수_없다(conn):
    """★★★ [재감사 P0-1] 결속 표의 `approved_by` 문자열만으로는 「승인됨」이 성립하지
    않는다 — 같은 호출자가 넣은 값을 같은 호출자가 읽는 **자기진술**이다.

    ⚠️ 첫 판이 정확히 이 모양이었다. 감사자가 "누가 언제 무슨 근거로 이 부서를 소유자로
      정했나" 를 물으면 답할 수 있는 곳(원장)이 없었다."""
    with pytest.raises(ob.OwnershipError, match="사건 id"):
        ob.declare(conn, tenant_id=T, entity_mode=M, dataset_contract_key=K,
                   scope_node_id=S, owner_dept_id=DEPT,
                   approved_by="approver@afs.invalid", evidence_ref="FND-01/v1#seed",
                   approval_event_id="")


def test_없는_승인_사건을_가리키면_무결성_오류(conn):
    with pytest.raises(ob.OwnershipIntegrityError, match="없습니다"):
        ob.declare(conn, tenant_id=T, entity_mode=M, dataset_contract_key=K,
                   scope_node_id=S, owner_dept_id=DEPT,
                   approved_by="approver@afs.invalid", evidence_ref="FND-01/v1#seed",
                   approval_event_id="evt_존재하지_않음")


def test_다른_부서의_승인_사건을_빌려_쓸_수_없다(conn, monkeypatch):
    """★★★ 승인 사건의 대상 지문에 **소유 부서까지** 들어간다.

    ⚠️ 부서를 지문에서 빼면 「구매부서 소유 승인」 사건 하나로 **재무부서 소유 결속**을
      세울 수 있다. 승인은 «무엇을» 승인했는지가 절반이다."""
    from core.org_directory import org_directory
    monkeypatch.setattr(org_directory, "get_department",
                        lambda d: {"dept_id": d, "status": "active"}, raising=False)
    ap = ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                    owner_dept_id="dept_purchase", actor_id="approver@afs.invalid",
                    evidence_ref="FND-01/v1#seed")
    with pytest.raises(ob.OwnershipIntegrityError, match="가리키지 않습니다"):
        ob.declare(conn, tenant_id=T, entity_mode=M, dataset_contract_key=K,
                   scope_node_id=S, owner_dept_id="dept_finance",
                   approved_by="approver@afs.invalid", evidence_ref="FND-01/v1#seed",
                   approval_event_id=ap["approval_event_id"],
                   effective_from=ap["effective_from"])


def test_다른_유형의_원장_사건은_승인이_아니다(conn):
    """⚠️ 아무 사건 id 하나로 승인을 주장할 수 있으면 원장을 붙인 의미가 없다."""
    from core.decision_ledger import decision_ledger
    other = decision_ledger.append(
        event_type="DECISION_RECORDED", subject_type="decision_case",
        subject_id="case_1", actor_type="user", actor_id="u@afs.invalid",
        decision="무관한 결정")
    with pytest.raises(ob.OwnershipIntegrityError, match="소유 승인이 아닙니다"):
        ob.declare(conn, tenant_id=T, entity_mode=M, dataset_contract_key=K,
                   scope_node_id=S, owner_dept_id=DEPT,
                   approved_by="approver@afs.invalid", evidence_ref="FND-01/v1#seed",
                   approval_event_id=other["event_id"])


def test_근거_없이는_만들_수_없다(conn):
    """★★ [재감사] 첫 판의 docstring 은 「승인자·근거 없이 만들 수 없다」고 적어 놓고
    코드는 빈 `evidence_ref` 를 통과시켰다 — **문서가 코드를 대신 주장하고 있었다.**"""
    with pytest.raises(ob.OwnershipError, match="evidence_ref|근거"):
        _declare(conn, evidence_ref="")


# ── ② 결속 없음 → UNBOUND ─────────────────────────────────────────────────

def test_결속이_없으면_None_이고_그것이_RESOURCE_UNBOUND_다(conn):
    """⚠️ 「없음」을 예외로 만들지 않는다. 정상적인 비노출이고, 호출부가 `RESOURCE_UNBOUND`
    로 답한다 — 503(점검 필요)과 섞으면 고칠 것이 없는데 고치라고 말하게 된다."""
    assert _resolve(conn) is None


# ── ③ 중복·유효기간 중첩 → 503 ────────────────────────────────────────────

def test_기간이_겹치는_두번째_ACTIVE_결속은_무결성_오류(conn):
    """★★★ 하나를 임의로 고르지 않는다. 그 선택은 근거가 없고, 다음 조회에서 다른 것이
    뽑힐 수도 있다 — 같은 질문에 다른 답을 주는 통제는 통제가 아니다."""
    _declare(conn, effective_from="2026-01-01T00:00:00+00:00")
    with pytest.raises(ob.OwnershipIntegrityError, match="겹치는"):
        _declare(conn, owner_dept_id=DEPT, approved_by="other@afs.invalid",
                 effective_from="2026-06-01T00:00:00+00:00")


def _without_overlap_triggers(conn):
    """기간 트리거를 잠시 걷어낸다 — **구버전 DB 를 정확히 재현하기 위해서다.**

    ⚠️ 이것은 「시험을 통과시키려고 통제를 끄는」 것이 아니다. `8ca029634`·`d9e86d06f`
      시절 DB 에는 이 트리거가 **없었다.** 그때 들어온 행이 실제로 남아 있고, 해석 쪽
      검사는 그 행을 상대한다. 트리거가 있는 DB 만 시험하면 그 상대를 만나지 못한다."""
    names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'trg_ownership%'")]
    for n in names:
        conn.execute(f"DROP TRIGGER {n}")
    return names


def test_해석_시점에_유효한_결속이_둘이면_503(conn):
    """★★★ **트리거가 없던 시절의 행이 실제로 있다** — 그래서 해석 쪽에도 검사가 있어야 한다.

    ⚠️ 층을 하나만 두면 그 층의 한계가 곧 전체의 한계가 된다. 트리거는 「지금 들어오는
      것」을, 해석 검사는 「이미 들어와 있는 것」을 막는다. 둘은 서로를 대신하지 않는다."""
    _declare(conn, effective_from="2026-01-01T00:00:00+00:00",
             effective_to="2026-06-01T00:00:00+00:00")
    ap = ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                    owner_dept_id=DEPT, actor_id="x@afs.invalid",
                    evidence_ref="FND-01/v0#legacy",
                    effective_from="2026-06-01T05:00:00+09:00")
    _without_overlap_triggers(conn)          # ← 구버전 DB 상태
    conn.execute(
        "INSERT INTO dataset_ownership_bindings (binding_id, tenant_id, entity_mode,"
        "dataset_contract_key, scope_node_id, owner_dept_id, effective_from, effective_to,"
        "status, approved_by, approved_at, approval_event_id, evidence_ref, fingerprint,"
        "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("own_dup", T, M, K, S, DEPT, "2026-06-01T05:00:00+09:00", "",
         ob.ACTIVE, "x@afs.invalid", "2026-05-31T20:00:00+00:00",
         ap["approval_event_id"], "FND-01/v0#legacy", ap["fingerprint"],
         "2026-05-31T20:00:00+00:00", "2026-05-31T20:00:00+00:00"))
    #: 두 결속이 동시에 유효한 순간. 하나를 임의로 고르지 않는다.
    with pytest.raises(ob.OwnershipIntegrityError, match="2건"):
        _resolve(conn, as_of="2026-05-31T21:00:00+00:00")


def test_기간이_겹치지_않으면_나란히_둘_수_있다(conn):
    """★ 대조군 — 중첩 차단이 「기간 분리도 막는 것」이 되면 개정을 할 수 없다."""
    _declare(conn, effective_from="2026-01-01T00:00:00+00:00",
             effective_to="2026-03-31T00:00:00+00:00")
    _declare(conn, effective_from="2026-04-01T00:00:00+00:00",
             approved_by="second@afs.invalid")
    assert _resolve(conn, as_of="2026-02-01T00:00:00+00:00")["approved_by"] \
        == "approver@afs.invalid"
    assert _resolve(conn, as_of="2026-05-01T00:00:00+00:00")["approved_by"] \
        == "second@afs.invalid"


# ── ④⑤ 문맥·범위 교차 결속 차단 ──────────────────────────────────────────

@pytest.mark.parametrize("cross", [
    {"tenant_id": "tenant_other"},
    {"entity_mode": "VIRTUAL"},
    {"entity_mode": "SANDBOX"},
    {"scope_node_id": "node_other"},
    {"dataset_contract_key": "SLS-01"},
])
def test_다른_문맥_범위_계약의_결속은_재사용되지_않는다(conn, cross):
    """★★ 결속은 **그 문맥의 그 범위의 그 계약**에만 유효하다.

    ⚠️ 하나라도 넘어가면 「한 번 승인하면 어디서나 쓰인다」가 되고, 그것은 테넌트 경계를
      승인 하나로 무너뜨리는 것이다."""
    _declare(conn)
    assert _resolve(conn, **cross) is None


# ── ⑥ 철회 후 즉시 차단 ───────────────────────────────────────────────────

def test_철회하면_즉시_해석되지_않는다(conn):
    b = _declare(conn)
    assert _resolve(conn) is not None
    assert ob.revoke(conn, b["binding_id"], "auditor@afs.invalid", "근거 미비")
    assert _resolve(conn) is None, "철회했는데 계속 해석된다"


def test_철회_기록은_남는다(conn):
    """⚠️ 행을 지우지 않는다 — 무엇이 있었고 누가 왜 내렸는지는 남아야 한다."""
    b = _declare(conn)
    ob.revoke(conn, b["binding_id"], "auditor@afs.invalid", "근거 미비")
    rows = ob.list_bindings(conn, status=ob.REVOKED)
    assert len(rows) == 1 and rows[0]["revoked_by"] == "auditor@afs.invalid"
    assert rows[0]["revoked_reason"] == "근거 미비"


def test_철회에도_행위자가_필요하다(conn):
    b = _declare(conn)
    with pytest.raises(ob.OwnershipError):
        ob.revoke(conn, b["binding_id"], "")


# ── ⑦ 소유 부서 미존재·폐지 → 차단 ────────────────────────────────────────

def test_없는_부서를_가리키는_결속은_503(conn, monkeypatch):
    from core.org_directory import org_directory
    _declare(conn)
    monkeypatch.setattr(org_directory, "get_department", lambda d: None, raising=False)
    with pytest.raises(ob.OwnershipIntegrityError, match="없거나"):
        _resolve(conn)


def test_폐지된_부서를_가리키는_결속은_503(conn, monkeypatch):
    from core.org_directory import org_directory
    _declare(conn)
    monkeypatch.setattr(org_directory, "get_department",
                        lambda d: {"dept_id": d, "status": "retired"}, raising=False)
    with pytest.raises(ob.OwnershipIntegrityError):
        _resolve(conn)


# ── ⑧ 원장 판독 장애 → 503 ────────────────────────────────────────────────

def test_조직_원장_판독_장애는_503_이고_UNBOUND_가_아니다(conn, monkeypatch):
    """★★★ 읽기 실패를 「결속 없음」으로 답하면 **장애가 곧 조용한 통제 해제**가 된다 —
    저장소가 흔들리는 순간에 모든 데이터가 «소유자 없음» 이 된다."""
    from core.org_directory import org_directory
    _declare(conn)

    def _boom(_d):
        raise RuntimeError("원장 장애")

    monkeypatch.setattr(org_directory, "get_department", _boom, raising=False)
    with pytest.raises(ob.OwnershipUnavailable):
        _resolve(conn)


def test_소유권_저장소_판독_장애도_503(conn, monkeypatch):
    _declare(conn)
    conn.close()                                   # 닫힌 연결 = 저장소 장애
    with pytest.raises(ob.OwnershipUnavailable):
        _resolve(conn)


# ── ⑨ 동일 지문 재적용은 멱등 ─────────────────────────────────────────────

def test_같은_지문의_재적용은_멱등이다(conn):
    """★ 시드·마이그레이션을 두 번 돌려도 중첩이 되지 않는다."""
    a = _declare(conn, effective_from="2026-01-01T00:00:00+00:00")
    b = _declare(conn, effective_from="2026-01-01T00:00:00+00:00")
    assert a["binding_id"] == b["binding_id"]
    assert len(ob.list_bindings(conn, status=ob.ACTIVE)) == 1


# ── ⑫ SLS-01 은 UNBOUND 로 남는다 ─────────────────────────────────────────

def test_SLS_01_은_UNBOUND_로_남는다(conn):
    """★★★ FND-01 에 판매 소유 부서 근거가 **없다.** 시연을 위해 임의 부서에 귀속시키면,
    그 순간 「판매 데이터의 소유 부서」라는 거짓이 정본에 들어간다.

    ⚠️ 판매 부서를 추가하려면 FND-01 판·시드·계약 지문을 함께 올리는 **명시적 개정**으로
      처리한다 — 이 회귀는 그때 함께 고쳐져야 한다."""
    _declare(conn)                                  # FND-01 만 결속
    assert _resolve(conn, dataset_contract_key="SLS-01") is None


# ── 지문 계약 ─────────────────────────────────────────────────────────────

def test_지문은_승인자와_근거까지_구별한다():
    """⚠️ 같은 부서를 다른 근거로 승인한 것은 **다른 결속**이다. 지문이 같으면 멱등 판정이
    그 둘을 같은 것으로 보고 두 번째 승인을 조용히 삼킨다."""
    base = dict(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                owner_dept_id=DEPT, effective_from="2026-01-01T00:00:00+00:00",
                effective_to="", approved_by="a@afs.invalid", evidence_ref="v1")
    same = ob.fingerprint_of(**base)
    assert same == ob.fingerprint_of(**base)
    assert same != ob.fingerprint_of(**{**base, "approved_by": "b@afs.invalid"})
    assert same != ob.fingerprint_of(**{**base, "evidence_ref": "v2"})
    assert same != ob.fingerprint_of(**{**base, "owner_dept_id": "sales"})


def test_유효기간이_뒤집히면_거부한다(conn):
    with pytest.raises(ob.OwnershipError, match="뒤집"):
        _declare(conn, effective_from="2026-06-01T00:00:00+00:00",
                 effective_to="2026-01-01T00:00:00+00:00")


def test_무기한_끝점은_영원히_유효하다(conn):
    """⚠️ 빈 끝점을 그대로 비교하면 «가장 작은 값» 이 되어 무기한이 오히려 «이미 끝난 것» 으로
    읽힌다 — 그러면 모든 무기한 결속이 조용히 사라진다."""
    _declare(conn, effective_from="2026-01-01T00:00:00+00:00", effective_to="")
    assert _resolve(conn, as_of="2099-01-01T00:00:00+00:00") is not None


# ── ⑬ 날짜는 문자열이 아니라 시각이다 ────────────────────────────────────
#
#   ★★★ [재감사 P1-2] 첫 판은 유효기간 중첩을 **ISO 문자열 비교**로 판정했다. 그러면
#     같은 순간을 다른 표기로 쓴 두 결속이 「겹치지 않는다」로 통과한다:
#
#         2026-06-01T00:00:00+00:00  와  2026-06-01T09:00:00+09:00  은 **같은 순간**이다.
#
#   ⚠️ 이것은 이론적인 걱정이 아니다. 한국 시간대 화면에서 들어온 값과 서버가 만든 UTC
#     값이 같은 표에 섞이는 순간 생긴다 — 그러면 같은 데이터셋에 소유 부서가 둘이 되고,
#     둘 중 어느 것이 뽑히는지는 정렬 순서가 정한다.

def test_같은_순간을_다른_오프셋으로_적어도_중첩으로_잡는다(conn):
    """★★★ 문자열로 비교했다면 이 시험은 **통과해 버린다**(중첩을 못 잡는다)."""
    _declare(conn, effective_from="2026-06-01T00:00:00+00:00")
    with pytest.raises(ob.OwnershipIntegrityError, match="겹치는"):
        #: 같은 순간. 표기만 KST 다.
        _declare(conn, approved_by="other@afs.invalid",
                 effective_from="2026-06-01T09:00:00+09:00")


def test_오프셋이_다른_끝점도_같은_순간으로_읽는다(conn):
    """★ 끝점 쪽도 같다. 한쪽만 정규화하면 «끝난 뒤 시작하는» 결속이 겹침으로 잡힌다."""
    _declare(conn, effective_from="2026-01-01T00:00:00+00:00",
             effective_to="2026-04-01T09:00:00+09:00")     # = 2026-04-01T00:00Z
    #: 끝난 그 순간부터 시작하는 다음 판 — 겹치지 않는다(대조군).
    _declare(conn, approved_by="second@afs.invalid",
             effective_from="2026-04-01T00:00:00+00:00")
    assert _resolve(conn, as_of="2026-02-01T00:00:00+00:00")["approved_by"] \
        == "approver@afs.invalid"
    assert _resolve(conn, as_of="2026-05-01T00:00:00+00:00")["approved_by"] \
        == "second@afs.invalid"


def test_시간대_없는_시각은_거부한다(conn):
    """★★ 「어느 시간대인지 모르는 시각」을 받아 두면, 나중에 비교하는 사람이 **추측**한다.

    ⚠️ 그 추측은 서버 시간대에 따라 달라지고, 배포 환경이 바뀌면 소유권이 바뀐다."""
    with pytest.raises(ob.OwnershipError, match="시간대|UTC"):
        _declare(conn, effective_from="2026-06-01T00:00:00")


def test_동시_삽입은_DB_제약이_막는다(conn):
    """★★★ [재감사 P1-3] 응용 계층의 중첩 검사만으로는 **동시 삽입**을 막지 못한다.

    두 요청이 각각 「겹치는 것 없음」을 읽은 뒤 둘 다 넣으면, 검사를 통과한 두 결속이
    남는다. 그래서 **부분 UNIQUE 색인**을 둔다 — 응용 검사를 우회한 경로(마이그레이션·
    시드·직접 SQL)도 여기서 막힌다.

    ⚠️ 응용 검사를 지우고 이 시험만 남기면 안 된다. 제약은 「같은 시작 시각」만 막고,
      **겹치지만 시작이 다른** 경우는 응용 검사가 잡는다 — 둘은 서로를 대신하지 않는다."""
    b = _declare(conn, effective_from="2026-01-01T00:00:00+00:00")
    row = dict(conn.execute("SELECT * FROM dataset_ownership_bindings "
                            "WHERE binding_id=?", (b["binding_id"],)).fetchone())
    #: 응용 검사를 **건너뛴** 직접 삽입 — 다른 결속 id, 같은 (문맥·계약·범위·시작).
    row["binding_id"] = "own_race"
    cols = ", ".join(row.keys())
    marks = ",".join("?" * len(row))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(f"INSERT INTO dataset_ownership_bindings ({cols}) VALUES ({marks})",
                     tuple(row.values()))


def test_철회된_결속은_같은_시작으로_다시_세울_수_있다(conn):
    """★ 대조군 — 제약이 `status='ACTIVE'` 부분 색인이어야 하는 이유.

    ⚠️ 전체 UNIQUE 로 두면 **철회한 뒤 다시 승인할 수 없다.** 그러면 운영자는 철회 대신
      행을 지우게 되고, 「무엇이 있었나」가 사라진다."""
    b = _declare(conn, effective_from="2026-01-01T00:00:00+00:00")
    ob.revoke(conn, b["binding_id"], "auditor@afs.invalid", "재승인 예정")
    again = _declare(conn, approved_by="second@afs.invalid",
                     effective_from="2026-01-01T00:00:00+00:00")
    assert again["binding_id"] != b["binding_id"]
    assert _resolve(conn)["approved_by"] == "second@afs.invalid"


# ── ⑭ 정본 표의 칸이 아니라 원장이 이긴다 ────────────────────────────────
#
#   ★★★ [재감사 P0-1 두번째 절반] 요청마다 원장을 다시 보는 이유는 **표의 칸을 고칠 수
#     있기 때문**이다. `status='ACTIVE'` 만 보고 답하면, 그 칸을 되살린 자료가 승인된
#     것처럼 통과한다 — 마이그레이션·시드·직접 SQL 은 실제로 그 칸을 만진다.
#
#   ⚠️ 이 회귀가 없으면 재검증 코드는 **아무것도 막지 않는다**(변이 시험에서 실측: 철회
#     자식 검사를 통째로 지워도 실패가 0건이었다. `revoke()` 가 status 를 내리므로 앞선
#     관문에서 먼저 걸렸고, 그래서 뒤쪽 검사는 시험된 적이 없었다).

def test_행의_status_를_되살려도_원장의_철회가_이긴다(conn):
    b = _declare(conn)
    ob.revoke(conn, b["binding_id"], "auditor@afs.invalid", "근거 미비")
    #: 정본 표의 칸만 되살린다 — 원장의 철회 자식 사건은 그대로다.
    conn.execute("UPDATE dataset_ownership_bindings SET status=? WHERE binding_id=?",
                 (ob.ACTIVE, b["binding_id"]))
    assert _resolve(conn) is None, "표의 칸을 고쳐 철회를 무효화했다"


def test_철회_조회가_실패하면_503_이고_유효로_읽지_않는다(conn, monkeypatch):
    """★★★ 「못 읽었다」를 「철회 없음」으로 접으면 **원장 장애가 곧 철회 무효화**다.

    ⚠️ 이것이 가장 조용한 실패다 — 장애 중에는 회수한 권한이 되살아나고, 장애가 끝나면
      증거가 사라진다."""
    from core.decision_ledger import decision_ledger
    _declare(conn)

    def _boom(*_a, **_k):
        raise RuntimeError("원장 장애")

    monkeypatch.setattr(decision_ledger, "has_invalidating_child", _boom, raising=False)
    with pytest.raises(ob.OwnershipUnavailable):
        _resolve(conn)


def test_저장되는_시각은_UTC_로_정규화된다(conn):
    """★★★ DB 유일 색인은 **문자열**을 본다. 표기 그대로 넣으면 같은 순간의 두 표기가
    다른 값이 되어, 응용 검사를 우회한 동시 삽입을 제약이 막지 못한다.

    ⚠️ 「비교만 UTC 로 고쳤다」는 절반이다 — 제약이 보는 값도 정규형이어야 한다."""
    b = _declare(conn, effective_from="2026-06-01T09:00:00+09:00",
                 effective_to="2026-07-01T09:00:00+09:00")
    row = dict(conn.execute("SELECT effective_from, effective_to FROM "
                            "dataset_ownership_bindings WHERE binding_id=?",
                            (b["binding_id"],)).fetchone())
    assert row["effective_from"] == "2026-06-01T00:00:00+00:00", row["effective_from"]
    assert row["effective_to"] == "2026-07-01T00:00:00+00:00", row["effective_to"]


def test_정규화되지_않은_기존_행과도_중첩을_잡는다(conn):
    """★★★ [변이 시험에서 발견] 저장값을 정규화한 뒤로는 **새 행끼리**의 비교가 이미
    정규형이라, 겹침 판정에서 UTC 변환이 일을 하지 않는다. 그래서 문자열 비교로 되돌려도
    시험이 전부 통과했다 — 통제가 있는지 없는지 시험이 답하지 못하는 상태다.

    ⚠️ 정규화 이전에 들어온 행은 실제로 있다: 마이그레이션·시드·직접 SQL. 그 행과 비교할
      때 UTC 변환이 없으면 같은 순간이 다른 값으로 읽히고 중첩이 통과한다."""
    #: 정규화 없이 KST 표기로 들어온 «옛» 행. 승인 사건은 정상적으로 남긴다.
    ap = ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                    owner_dept_id=DEPT, actor_id="legacy@afs.invalid",
                    evidence_ref="FND-01/v0#legacy",
                    effective_from="2026-06-01T09:00:00+09:00")
    conn.execute(
        "INSERT INTO dataset_ownership_bindings (binding_id, tenant_id, entity_mode,"
        "dataset_contract_key, scope_node_id, owner_dept_id, effective_from, effective_to,"
        "status, approved_by, approved_at, approval_event_id, evidence_ref, fingerprint,"
        "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("own_legacy", T, M, K, S, DEPT, "2026-06-01T09:00:00+09:00", "",   # ← 표기 그대로
         ob.ACTIVE, "legacy@afs.invalid", "2026-06-01T09:00:00+09:00",
         ap["approval_event_id"], "FND-01/v0#legacy", ap["fingerprint"],
         "2026-06-01T09:00:00+09:00", "2026-06-01T09:00:00+09:00"))
    #: ★★ **판별력 있는 모양**을 고른다. 두 구간이 모두 무기한이면 문자열 비교로도 겹침이
    #:   나오므로(첫 판이 그랬다), 「문자열로는 안 겹쳐 보이는데 실제로는 겹치는」 쪽을 쓴다:
    #:     · 옛 행 시작 = `2026-06-01T09:00:00+09:00` = **06-01 00:00Z**
    #:     · 새 결속    = 06-01 01:00Z ~ 05:00Z  → 실제로는 옛 행 안에 들어 있다
    #:   문자열로 보면 `"…T09…" < "…T05…"` 가 거짓이라 **겹치지 않는다**고 답한다.
    with pytest.raises(ob.OwnershipIntegrityError, match="겹치는"):
        _declare(conn, approved_by="new@afs.invalid",
                 effective_from="2026-06-01T01:00:00+00:00",
                 effective_to="2026-06-01T05:00:00+00:00")


def test_정규화되지_않은_기존_행도_해석된다(conn):
    """★ 해석 쪽 절반. 옛 표기 행을 못 읽으면 **소유자가 조용히 사라진다.**"""
    ap = ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                    owner_dept_id=DEPT, actor_id="legacy@afs.invalid",
                    evidence_ref="FND-01/v0#legacy",
                    effective_from="2026-06-01T09:00:00+09:00")
    conn.execute(
        "INSERT INTO dataset_ownership_bindings (binding_id, tenant_id, entity_mode,"
        "dataset_contract_key, scope_node_id, owner_dept_id, effective_from, effective_to,"
        "status, approved_by, approved_at, approval_event_id, evidence_ref, fingerprint,"
        "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("own_legacy2", T, M, K, S, DEPT, "2026-06-01T09:00:00+09:00", "",
         ob.ACTIVE, "legacy@afs.invalid", "2026-06-01T09:00:00+09:00",
         ap["approval_event_id"], "FND-01/v0#legacy", ap["fingerprint"],
         "2026-06-01T09:00:00+09:00", "2026-06-01T09:00:00+09:00"))
    #: UTC 기준으로 그 순간 직후 — 옛 표기를 문자열로 읽으면 «아직 시작 안 함» 이 된다.
    got = _resolve(conn, as_of="2026-06-01T01:00:00+00:00")
    assert got is not None and got["binding_id"] == "own_legacy2"


# ── ⑮ 승인 권한 ───────────────────────────────────────────────────────────

def _bare_org(tmp_path, monkeypatch, *, depts=(), users=()):
    """조직도를 **원하는 단계까지만** 세운다 — 부트스트랩 세 모양을 만들기 위한 도구."""
    from core.decision_ledger import decision_ledger
    from core.org_directory import OrgDirectory
    import core.org_directory as orgmod
    o = OrgDirectory(db_path=str(tmp_path / "bare_org.db"))
    for d in depts:
        o.create_department(d, d)
    for uid, is_da in users:
        o.upsert_user(uid, uid.split("@")[0], primary_dept_id=(depts[0] if depts else ""),
                      is_data_admin=is_da, actor="seed")
    monkeypatch.setattr(orgmod, "org_directory", o)
    monkeypatch.setattr(decision_ledger, "db_path", str(tmp_path / "bare_ledger.db"),
                        raising=False)
    return o


def _approve(actor):
    return ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                      owner_dept_id=DEPT, actor_id=actor, evidence_ref="FND-01/v1#seed")


def _ledger_empty():
    """승인 사건이 **하나도** 남지 않았는가.

    ⚠️ 거부만 확인하면 부족하다. 거부됐는데 이력에는 승인이 남아 있으면 그것이 더 나쁘다 —
      원장은 「무엇이 있었나」의 마지막 답이므로, 거짓이 들어가면 되돌릴 곳이 없다."""
    from core.decision_ledger import decision_ledger
    return decision_ledger.list_events(event_type=ob.EVENT_APPROVED) == []


# ── ⑮ 승인 권한 — 부트스트랩 우회 세 대조군 ──────────────────────────────
#
#   ★★★ [4.1c-B P0-1] 실측한 우회. `resolve_scope()` 는 **부트스트랩이면 미등록
#     사용자에게도** `unrestricted=True`·`can_manage_standard=True` 를 준다:
#
#       ① 조직 없음      bootstrap=True  unrestricted=True  can_manage_standard=True
#       ② 부서만 있음    bootstrap=True  unrestricted=True  can_manage_standard=True
#       ③ 미등록 행위자  bootstrap=False unrestricted=False can_manage_standard=False
#
#   그래서 `unrestricted or can_manage_standard` 는 ①②를 통과시켰다. 부서 생존 검사에서
#   같은 예외를 지우면서 **승인 생성 경로에는 남겨 둔** 것이다.

def test_조직이_없으면_아무도_승인할_수_없다(monkeypatch, tmp_path):
    _bare_org(tmp_path, monkeypatch)                     # 부서 0 · 사용자 0
    with pytest.raises(ob.OwnershipError, match="조직 정본이 아직 없습니다"):
        _approve("std@afs.invalid")
    assert _ledger_empty(), "거부했는데 승인 사건이 원장에 남았다"


def test_부서만_있고_사용자가_없으면_승인할_수_없다(monkeypatch, tmp_path):
    """⚠️ 이 모양이 실제로 존재한다 — FND-01 부서만 적재하고 사용자를 아직 안 만든 단계다.
    바로 그때 임의 문자열이 승인자가 될 수 있었다."""
    _bare_org(tmp_path, monkeypatch, depts=(DEPT,))
    with pytest.raises(ob.OwnershipError, match="조직 정본이 아직 없습니다"):
        _approve("std@afs.invalid")
    assert _ledger_empty()


def test_미등록_사용자는_승인할_수_없다(monkeypatch, tmp_path):
    _bare_org(tmp_path, monkeypatch, depts=(DEPT,),
              users=(("real@afs.invalid", True),))
    with pytest.raises(ob.OwnershipError, match="조직 정본에 없는 사용자"):
        _approve("아무도아님@afs.invalid")
    assert _ledger_empty()


def test_권한_플래그가_없는_실사용자도_승인할_수_없다(monkeypatch, tmp_path):
    """★ 실재·활성만으로는 부족하다 — 승인권은 별개 축이다."""
    _bare_org(tmp_path, monkeypatch, depts=(DEPT,),
              users=(("plain@afs.invalid", False),))
    with pytest.raises(ob.OwnershipError, match="권한이 없습니다"):
        _approve("plain@afs.invalid")
    assert _ledger_empty()


def test_폐지된_승인자는_승인할_수_없다(monkeypatch, tmp_path):
    """⚠️ 폐지가 권한을 남겨 두면 그것은 폐지가 아니다(조직도에서 이미 한 번 실측된 결함)."""
    o = _bare_org(tmp_path, monkeypatch, depts=(DEPT,),
                  users=(("gone@afs.invalid", True), ("keep@afs.invalid", True)))
    o.delete_user("gone@afs.invalid", actor="seed")   # 폐지(행은 남고 status=retired)
    with pytest.raises(ob.OwnershipError):
        _approve("gone@afs.invalid")
    assert _ledger_empty()


def test_권한_있는_실사용자는_승인한다(monkeypatch, tmp_path):
    """★★ **대조군.** 이것이 빨개지면 위 다섯은 「전부 막는 검사」일 뿐이다."""
    _bare_org(tmp_path, monkeypatch, depts=(DEPT,),
              users=(("std@afs.invalid", True),))
    ap = _approve("std@afs.invalid")
    assert ap["approval_event_id"]


def test_정본과_확정_권한이_어긋나면_점검이다(monkeypatch, tmp_path):
    """★ 사용자 정본에는 승인권이 있는데 확정 결과에는 없다 — 어느 쪽도 임의로 고르지 않는다."""
    import core.org_directory as orgmod
    o = _bare_org(tmp_path, monkeypatch, depts=(DEPT,),
                  users=(("std@afs.invalid", True),))

    class _NoStd:
        can_manage_standard = False
        unrestricted = True          # ⚠️ 이 값에 기대면 안 된다 — 그것이 우회 경로였다

    monkeypatch.setattr(o, "resolve_scope", lambda _u="": _NoStd(), raising=False)
    with pytest.raises(ob.OwnershipIntegrityError, match="어긋납니다"):
        _approve("std@afs.invalid")
    assert _ledger_empty()


def test_행위자_판독_실패는_통과가_아니다(monkeypatch):
    """⚠️ 조직도가 흔들리는 순간에 승인이 열리면, 장애가 곧 승인 통제 해제다."""
    import core.org_directory as orgmod

    class _Boom:
        def is_bootstrap(self):
            raise RuntimeError("조직도 장애")

    monkeypatch.setattr(orgmod, "org_directory", _Boom())
    with pytest.raises(ob.OwnershipUnavailable, match="행위자를 확인하지 못했습니다"):
        _approve("std@afs.invalid")


def test_확정_권한_판독_실패도_통과가_아니다(monkeypatch, tmp_path):
    """★ 두 조각을 **각각** 시험한다. 앞 조각(실재·활성)이 통과한 뒤 뒤 조각
    (`resolve_scope`)이 실패하는 경로가 따로 있다 — 하나만 시험하면 나머지가 열린다."""
    o = _bare_org(tmp_path, monkeypatch, depts=(DEPT,),
                  users=(("std@afs.invalid", True),))

    def _boom(_u=""):
        raise RuntimeError("권한 해석 장애")

    monkeypatch.setattr(o, "resolve_scope", _boom, raising=False)
    with pytest.raises(ob.OwnershipUnavailable, match="승인 권한을 확인하지 못했습니다"):
        _approve("std@afs.invalid")
    assert _ledger_empty()


# ── ㉒ 승인 취소 권한 ─────────────────────────────────────────────────────
#
#   ★★★ [4.1c-C P0-2] `abandon()` 은 행위자가 비어 있는지만 봤다. 그래서 승인 사건 id 를
#     아는 **임의 호출자가 정상 승인을 「등록 실패」로 취소**할 수 있었다. `revoke()` 에는
#     권한 검증을 넣고 여기에는 넣지 않았다 — 같은 결과를 내는 두 경로 중 하나만 막은 것이다.

def _seed_approval(tmp_path, monkeypatch, *, extra=()):
    """승인 하나를 남긴 조직도. 돌려주는 것: `(조직도, 승인결과)`."""
    o = _bare_org(tmp_path, monkeypatch, depts=(DEPT,),
                  users=(("std@afs.invalid", True), *extra))
    return o, _approve("std@afs.invalid")


def test_임의_행위자는_승인을_취소할_수_없다(monkeypatch, tmp_path):
    """★★★ 감사에서 지적된 우회 그대로다."""
    _o, ap = _seed_approval(tmp_path, monkeypatch)
    with pytest.raises(ob.OwnershipError, match="조직 정본에 없는 사용자"):
        ob.abandon(ap["approval_event_id"], "지나가던사람@afs.invalid", "등록 실패")


def test_권한_없는_실사용자도_남의_승인을_취소할_수_없다(monkeypatch, tmp_path):
    """★ 실재·활성만으로는 부족하다 — 취소는 승인을 무효로 만드는 행위다."""
    _o, ap = _seed_approval(tmp_path, monkeypatch,
                            extra=(("plain@afs.invalid", False),))
    with pytest.raises(ob.OwnershipError, match="권한이 없습니다"):
        ob.abandon(ap["approval_event_id"], "plain@afs.invalid", "등록 실패")


def test_취소에는_사유가_필요하다(monkeypatch, tmp_path):
    """⚠️ 사유가 없으면 「정상 승인을 취소한 것」과 「등록 실패를 되돌린 것」을 구분할 수 없다."""
    _o, ap = _seed_approval(tmp_path, monkeypatch)
    with pytest.raises(ob.OwnershipError, match="취소 사유"):
        ob.abandon(ap["approval_event_id"], "std@afs.invalid", "")


def test_현재_권한자는_남의_승인을_취소할_수_있다(monkeypatch, tmp_path):
    """★★ **대조군.** 취소 경로가 아예 막히면 잘못된 승인을 정리할 수 없다."""
    _o, ap = _seed_approval(tmp_path, monkeypatch,
                            extra=(("other_admin@afs.invalid", True),))
    out = ob.abandon(ap["approval_event_id"], "other_admin@afs.invalid", "중복 승인 정리")
    assert out["revocation_event_id"]


def test_원_승인자는_권한을_잃어도_자기_승인을_취소할_수_있다(monkeypatch, tmp_path):
    """★★ 자기 것을 내리는 것은 **권한 축소 방향**이다. 막으면 잘못 승인한 사람이 스스로
    정리할 길이 없어지고, 그러면 아무도 정리하지 않는다.

    ⚠️ 다만 **실재·활성** 검사는 그대로 지난다 — 문자열 일치만으로 「본인」을 인정하면
      그 문자열을 아는 사람이면 누구나 본인을 자칭할 수 있고, 그것은 다시 자기진술이다."""
    o, ap = _seed_approval(tmp_path, monkeypatch)
    #: 승인 뒤 권한이 회수됐다(직책 변경). 계정은 살아 있다.
    o.upsert_user("std@afs.invalid", "표준승인자", primary_dept_id=DEPT,
                  is_data_admin=False, actor="seed")
    out = ob.abandon(ap["approval_event_id"], "std@afs.invalid", "내가 잘못 승인했다")
    assert out["revocation_event_id"]


def test_폐지된_원_승인자는_취소할_수_없다(monkeypatch, tmp_path):
    """⚠️ 폐지가 권한을 남겨 두면 그것은 폐지가 아니다 — 「본인」 예외에도 적용된다."""
    #: ⚠️ 다른 사용자를 남겨 둔다. 유일한 사용자를 폐지하면 조직이 **부트스트랩으로
    #:   되돌아가** 앞 관문이 먼저 걸리고, 이 시험은 자기가 노린 분기를 지나지 않는다
    #:   (실측: 「폐지된 사용자」가 아니라 「조직 정본이 아직 없습니다」가 나왔다).
    o, ap = _seed_approval(tmp_path, monkeypatch,
                           extra=(("keep@afs.invalid", True),))
    o.delete_user("std@afs.invalid", actor="seed")
    with pytest.raises(ob.OwnershipError, match="폐지된 사용자"):
        ob.abandon(ap["approval_event_id"], "std@afs.invalid", "정리")


def test_미물질화_보고는_원장_장애를_숨기지_않는다(conn, monkeypatch):
    """★★★ [4.1c-C P1-2] 앞 판은 철회 조회가 실패하면 그 승인을 **목록에서 빼** 버렸다.
    그러면 원장 장애 중에 보고가 「미물질화 0건」이라고 말한다 — 아무 문제 없다는 뜻이다.

    ⚠️ 「모르는 것을 없는 것으로 접는」 결함을 이 파일에서 네 번째로 고친다."""
    from core.decision_ledger import decision_ledger
    ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
               owner_dept_id=DEPT, actor_id="approver@afs.invalid",
               evidence_ref="FND-01/v1#seed")

    def _boom(*_a, **_k):
        raise RuntimeError("원장 장애")

    monkeypatch.setattr(decision_ledger, "has_invalidating_child", _boom, raising=False)
    with pytest.raises(ob.OwnershipUnavailable, match="셀 수 없습니다"):
        ob.dangling_approvals(conn, tenant_id=T, entity_mode=M, unrestricted=True)


def test_미물질화_보고는_한도에_닿으면_부분_결과를_주지_않는다(conn, monkeypatch):
    """★★★ [4.1c-E P0-2] 앞 판은 한도에 닿으면 **경고를 찍고 부분 결과를 돌려줬다.**

    ⚠️ 경고는 호출부가 그 값을 전체로 쓰는 것을 막지 못한다 — 실제로 그렇게 썼다. 부분
      결과를 「미물질화 N건」으로 보고하면 그 숫자가 「우리는 N건을 확인했다」로 읽힌다.
    ★ 그래서 예외다. 세는 자리에서는 **모른다는 사실 자체를 알아야** 한다."""
    from core.decision_ledger import decision_ledger
    #: 한도(2)보다 많은 승인을 만든다.
    for i in range(3):
        ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key=f"K-{i}",
                   scope_node_id=S, owner_dept_id=DEPT,
                   actor_id="approver@afs.invalid", evidence_ref=f"ev-{i}")
    with pytest.raises(ob.OwnershipUnavailable, match="셀 수 없습니다"):
        ob.dangling_approvals(conn, tenant_id=T, entity_mode=M, unrestricted=True,
                              limit=2)
    #: ★ 대조군 — 한도 안이면 정상적으로 센다.
    got = ob.dangling_approvals(conn, tenant_id=T, entity_mode=M, unrestricted=True,
                                limit=50)
    assert len(got) == 3


def test_원장_목록_판독_장애는_0건이_아니다(conn, monkeypatch):
    """★★★ [4.1c-E P0-2] `list_events()` 는 SQLite 판독 실패를 **빈 배열**로 접는다.
    앞 판의 회귀는 `has_invalidating_child()` 장애만 시험해서 이 경로를 잡지 못했다.

    ⚠️ 「사건이 없다」와 「못 읽었다」가 같은 모양이면, 장애 중에 보고가 「0건」이라고
      말한다 — 아무 문제도 없다는 뜻으로 읽힌다."""
    from core.decision_ledger import DecisionLedgerError, decision_ledger

    def _boom(**kw):
        raise DecisionLedgerError("원장을 읽지 못했습니다(주입)")

    monkeypatch.setattr(decision_ledger, "list_events_strict", _boom, raising=False)
    with pytest.raises(ob.OwnershipUnavailable, match="셀 수 없습니다"):
        ob.dangling_approvals(conn, tenant_id=T, entity_mode=M, unrestricted=True)


def test_미물질화_보고는_테넌트를_넘지_않는다(conn):
    """★★★ [4.1c-E P0-1] 실측된 누설: A 관리자가 B 조직의 승인 ID·행위자·지문·건수를
    볼 수 있었다. 결속과 격리는 걸렀는데 **이 목록만 안 걸렀다.**"""
    ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
               owner_dept_id=DEPT, actor_id="approver@afs.invalid", evidence_ref="내것")
    ob.approve(tenant_id="tenant_남의회사", entity_mode=M, dataset_contract_key="SLS-01",
               scope_node_id="NODE_남", owner_dept_id=DEPT,
               actor_id="approver@afs.invalid", evidence_ref="남의것")
    got = ob.dangling_approvals(conn, tenant_id=T, entity_mode=M, unrestricted=True)
    assert len(got) == 1, f"테넌트를 넘어 {len(got)}건이 보인다"
    #: ★ 지문까지 확인한다 — 건수만 맞고 다른 테넌트 것이 섞이면 더 나쁘다.
    blob = str(got)
    assert "남의것" not in blob


def test_미물질화_보고는_부서_범위도_거른다(conn, org):
    """★★ 테넌트가 같아도 **부서 범위**가 다르면 보이지 않는다. 원장 조회 API 와 같은
    규칙(`visible_events`)을 쓴다 — 두 벌이면 새로 만드는 쪽이 느슨해진다."""
    org.create_department("dept_other", "다른부서")
    ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
               owner_dept_id=DEPT, actor_id="approver@afs.invalid", evidence_ref="내것")
    ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key="SLS-01",
               scope_node_id=S, owner_dept_id="dept_other",
               actor_id="approver@afs.invalid", evidence_ref="다른부서것")
    got = ob.dangling_approvals(conn, tenant_id=T, entity_mode=M,
                                readable_dept_ids={DEPT}, actor_id="reader@afs.invalid")
    assert len(got) == 1 and "다른부서것" not in str(got)


def _legacy_db(tmp_path, *, rows=0):
    """`8ca029634` 형식 DB 를 만든다. `rows` 건의 **자기진술 결속**을 넣는다."""
    c = sqlite3.connect(str(tmp_path / "legacy.db"))
    c.row_factory = sqlite3.Row
    c.executescript(_LEGACY_DDL)
    for i in range(rows):
        c.execute(
            "INSERT INTO dataset_ownership_bindings (binding_id, tenant_id, entity_mode,"
            "dataset_contract_key, scope_node_id, owner_dept_id, effective_from,"
            "effective_to, status, approved_by, approved_at, evidence_ref, fingerprint,"
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"own_old_{i}", T, M, f"KEY-{i}", S, "구버전선언부서",
             "2026-01-01T00:00:00+00:00", "", ob.ACTIVE, "누군가@afs.invalid",
             "2026-01-01T00:00:00+00:00", "", f"fp_old_{i}",
             "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"))
    c.commit()
    return c


def test_구버전_표에서는_등록이_실패한다는_사실을_먼저_고정한다(tmp_path):
    """★★ **대조군 먼저.** 마이그레이션이 없으면 실제로 무엇이 깨지는지 확인한다 —
    이것을 고정하지 않으면 마이그레이션 회귀가 「무엇을 고쳤는지」 말하지 못한다."""
    c = _legacy_db(tmp_path)
    cols = {r[1] for r in c.execute("PRAGMA table_info(dataset_ownership_bindings)")}
    assert "approval_event_id" not in cols
    with pytest.raises(sqlite3.OperationalError, match="approval_event_id"):
        c.execute("SELECT approval_event_id FROM dataset_ownership_bindings")
    c.close()


def test_빈_구버전_표는_안전하게_재구성된다(org, tmp_path):
    c = _legacy_db(tmp_path, rows=0)
    res = ob.migrate(c)
    c.executescript(ob.DDL)
    assert res["action"] == "rebuilt", res
    cols = {r[1] for r in c.execute("PRAGMA table_info(dataset_ownership_bindings)")}
    assert {"approval_event_id", "revocation_event_id"} <= cols
    #: ★ 재구성 뒤 **등록이 실제로 된다** — 스키마만 맞추고 못 쓰면 고친 것이 아니다.
    b = _declare(c)
    assert _resolve(c)["binding_id"] == b["binding_id"]
    c.close()


def test_행이_있는_구버전_표는_격리되고_자동_승격되지_않는다(org, tmp_path):
    """★★★ 자동 백필 금지. 옛 행은 **소유자 없음**이 되어야 한다."""
    from core.decision_ledger import decision_ledger
    c = _legacy_db(tmp_path, rows=3)
    res = ob.migrate(c)
    c.executescript(ob.DDL)
    assert res["action"] == "quarantined" and res["rows"] == 3, res

    #: ① 새 표는 비어 있다 — 옛 결속이 넘어오지 않았다.
    assert c.execute("SELECT COUNT(*) FROM dataset_ownership_bindings").fetchone()[0] == 0
    #: ② 옛 행은 **사라지지 않았다.** 무엇이 있었는지는 남아야 한다.
    rep = ob.legacy_unapproved(c)
    assert rep["quarantined"] == 3
    assert rep["keys"][0]["claimed_owner_dept_id"] == "구버전선언부서"
    #: ③ 해석은 **소유자 없음**이다(UNBOUND) — 503 이 아니다. 고칠 것은 승인이지 저장소가 아니다.
    assert ob.resolve(c, tenant_id=T, entity_mode=M, dataset_contract_key="KEY-0",
                      scope_node_id=S) is None
    #: ④ ★★★ **가짜 승인 사건이 만들어지지 않았다.** 이것이 이 시험의 핵심이다.
    assert decision_ledger.list_events(event_type=ob.EVENT_APPROVED) == []
    c.close()


def test_격리_뒤에도_새_표의_통제가_살아_있다(org, tmp_path):
    """★★★ **조용한 통제 소실을 막는다.**

    SQLite 의 `ALTER TABLE RENAME` 은 색인을 옛 표에 그대로 남기고 **이름도 유지**한다.
    그러면 새 표에 `CREATE ... IF NOT EXISTS` 로 같은 이름을 만들려 할 때 조용히
    건너뛰어지고 — **새 표에 유일 색인도 트리거도 생기지 않는다.** 실패도 경고도 없다.

    ⚠️ 이 함정은 마이그레이션을 쓰면서 실제로 밟을 수 있었다. 이름이 겹치는 것을 미리
      지우지 않았다면, 마이그레이션이 성공한 DB 에서만 중첩 차단이 사라졌을 것이다."""
    c = _legacy_db(tmp_path, rows=2)
    ob.migrate(c)
    c.executescript(ob.DDL)
    attached = {r[0]: r[1] for r in c.execute(
        "SELECT name, tbl_name FROM sqlite_master WHERE type IN ('index','trigger') "
        "AND name NOT LIKE 'sqlite_%'")}
    assert attached.get("uq_ownership_active_start") == "dataset_ownership_bindings", attached
    assert attached.get("trg_ownership_no_overlap_insert") == "dataset_ownership_bindings", \
        attached
    #: ★ 이름이 붙어 있는 것으로 끝내지 않는다 — **실제로 막는지** 누른다.
    _declare(c, effective_from="2026-01-01T00:00:00+00:00")
    with pytest.raises((ob.OwnershipIntegrityError, sqlite3.IntegrityError)):
        _declare(c, approved_by="second@afs.invalid",
                 effective_from="2026-03-01T00:00:00+00:00")
    c.close()


def test_마이그레이션은_멱등이다(org, tmp_path):
    c = _legacy_db(tmp_path, rows=2)
    ob.migrate(c); c.executescript(ob.DDL)
    second = ob.migrate(c)
    assert second["action"] == "none", second
    assert ob.legacy_unapproved(c)["quarantined"] == 2, "두 번째 실행이 격리본을 건드렸다"
    c.close()


def test_격리본이_두_세대면_사람이_봐야_한다(org, tmp_path):
    """⚠️ 자동으로 합치면 어느 세대의 주장인지 알 수 없게 된다."""
    c = _legacy_db(tmp_path, rows=1)
    ob.migrate(c)
    c.executescript(_LEGACY_DDL)              # 옛 형식 표가 또 생겼다(구버전 코드 재기동)
    c.execute("INSERT INTO dataset_ownership_bindings (binding_id, tenant_id, entity_mode,"
              "dataset_contract_key, scope_node_id, owner_dept_id, effective_from,"
              "status, approved_by, approved_at, fingerprint, created_at, updated_at)"
              " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
              ("own_old_9", T, M, "KEY-9", S, "또다른부서", "2026-01-01T00:00:00+00:00",
               ob.ACTIVE, "누군가@afs.invalid", "2026-01-01T00:00:00+00:00", "fp_old_9",
               "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"))
    with pytest.raises(ob.OwnershipIntegrityError, match="두 세대"):
        ob.migrate(c)
    c.close()


def test_제품_저장소_초기화가_구버전_표를_스스로_처리한다(org, tmp_path, monkeypatch):
    """★★★ **제품이 실제로 부르는 경로**로 확인한다.

    ⚠️⚠️ [변이 시험에서 발견] 위 마이그레이션 회귀들은 `ob.migrate()` 를 **직접** 불렀다.
      그래서 `store._ready()` 의 호출을 통째로 지워도 실패가 0건이었다 — 마이그레이션은
      작동하지만 **아무도 부르지 않는** 상태를 시험이 통과시켰다. 「통제는 있는데 부르는
      경로가 없다」는 이 저장소에서 이미 한 번 있었던 결함 유형이다.

    ★ 그래서 옛 형식 DB 파일을 **제품 싱글턴의 경로에 두고**, 평소처럼 트랜잭션을 열어
      초기화가 스스로 처리하는지 본다."""
    from core.data_preparation import store as dp
    path = str(tmp_path / "prod_legacy.db")
    c = sqlite3.connect(path)
    c.executescript(_LEGACY_DDL)
    c.execute("INSERT INTO dataset_ownership_bindings (binding_id, tenant_id, entity_mode,"
              "dataset_contract_key, scope_node_id, owner_dept_id, effective_from,"
              "status, approved_by, approved_at, fingerprint, created_at, updated_at)"
              " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
              ("own_prod_old", T, M, "LOG-02", S, "구버전선언부서",
               "2026-01-01T00:00:00+00:00", ob.ACTIVE, "누군가@afs.invalid",
               "2026-01-01T00:00:00+00:00", "fp_prod_old",
               "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"))
    c.commit(); c.close()

    store = dp.data_preparation_store
    monkeypatch.setattr(store, "db_path", path, raising=False)
    monkeypatch.setattr(store, "_prepared_for", None, raising=False)

    #: 평소처럼 트랜잭션을 연다 — 초기화가 여기서 돈다.
    with store.transaction() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(dataset_ownership_bindings)")}
        assert "approval_event_id" in cols, "제품 초기화가 구버전 표를 그대로 두었다"
        assert conn.execute("SELECT COUNT(*) FROM dataset_ownership_bindings"
                            ).fetchone()[0] == 0, "옛 결속이 새 표로 넘어왔다"
        assert ob.legacy_unapproved(conn)["quarantined"] == 1, "옛 행이 사라졌다"
        #: ★ 그리고 등록이 실제로 된다 — 옛 스키마에서는 `no such column` 으로 죽던 자리다.
        ap = ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key="LOG-02",
                        scope_node_id=S, owner_dept_id=DEPT,
                        actor_id="approver@afs.invalid", evidence_ref="FND-01/v1#seed")
        ob.declare(conn, tenant_id=T, entity_mode=M, dataset_contract_key="LOG-02",
                   scope_node_id=S, owner_dept_id=DEPT,
                   approved_by="approver@afs.invalid", evidence_ref="FND-01/v1#seed",
                   approval_event_id=ap["approval_event_id"],
                   effective_from=ap["effective_from"])


# ── ㉓ 격리는 영속 상태이고 재승인으로만 풀린다 ───────────────────────────

def test_격리는_재시작_뒤에도_남는다(org, tmp_path):
    """★★★ [4.1c-C P1-1] 기동 로그는 다음 재시작에 사라진다. 그러면 「원래 소유자가
    없었다」와 「승인 근거가 없어 격리됐다」가 구분되지 않는다.

    ⚠️ 운영자에게 남는 것은 「데이터가 안 보인다」 뿐이고, 이유는 어디에도 없다."""
    c = _legacy_db(tmp_path, rows=2)
    ob.migrate(c); c.executescript(ob.DDL); c.commit(); c.close()
    #: 재시작 — 같은 파일을 다시 연다.
    c2 = sqlite3.connect(str(tmp_path / "legacy.db"))
    st = ob.quarantine_state(c2)
    assert st["unresolved"] == 2, st
    assert set(st["by_contract_key"]) == {"KEY-0", "KEY-1"}
    assert st["items"][0]["claimed_owner_dept_id"] == "구버전선언부서"
    c2.close()


def test_격리는_재승인으로만_풀린다(org, tmp_path):
    """★★★ 해제 근거는 **승인된 결속이 실제로 생겼다**는 사실뿐이다.

    ⚠️ 「관리자가 확인했다」로 풀 수 있게 두면 그것이 다시 자기진술이다 — 이 작업이
      지우려 한 것과 같은 모양이다."""
    c = _legacy_db(tmp_path, rows=2)
    ob.migrate(c); c.executescript(ob.DDL)
    assert ob.quarantine_state(c)["unresolved"] == 2

    #: KEY-0 만 재승인한다.
    ap = ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key="KEY-0",
                    scope_node_id=S, owner_dept_id=DEPT,
                    actor_id="approver@afs.invalid", evidence_ref="FND-01/v1#재승인")
    ob.declare(c, tenant_id=T, entity_mode=M, dataset_contract_key="KEY-0",
               scope_node_id=S, owner_dept_id=DEPT, approved_by="approver@afs.invalid",
               evidence_ref="FND-01/v1#재승인",
               approval_event_id=ap["approval_event_id"],
               effective_from=ap["effective_from"])
    st = ob.quarantine_state(c)
    assert st["unresolved"] == 1, "재승인한 키가 풀리지 않았다"
    assert set(st["by_contract_key"]) == {"KEY-1"}, "다른 키까지 함께 풀렸다"
    c.close()


def test_다른_범위의_재승인은_격리를_풀지_않는다(org, tmp_path):
    """⚠️ 계약키만 보고 풀면 **다른 조직 범위의 승인 하나가 전사 격리를 해제**한다."""
    c = _legacy_db(tmp_path, rows=1)
    ob.migrate(c); c.executescript(ob.DDL)
    ap = ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key="KEY-0",
                    scope_node_id="node_다른범위", owner_dept_id=DEPT,
                    actor_id="approver@afs.invalid", evidence_ref="FND-01/v1#다른범위")
    ob.declare(c, tenant_id=T, entity_mode=M, dataset_contract_key="KEY-0",
               scope_node_id="node_다른범위", owner_dept_id=DEPT,
               approved_by="approver@afs.invalid", evidence_ref="FND-01/v1#다른범위",
               approval_event_id=ap["approval_event_id"],
               effective_from=ap["effective_from"])
    assert ob.quarantine_state(c)["unresolved"] == 1, "다른 범위 승인이 격리를 풀었다"
    c.close()

def test_승인권_없는_사람은_철회할_수_없다(conn, monkeypatch, tmp_path):
    """★★★ [4.1c-B P0-4] 철회는 승인보다 **조용하다.** 소유권이 내려가면 그 데이터는
    아무에게도 안 보이게 되고, 「안 보인다」는 아무도 신고하지 않는다.

    ⚠️ 앞 판은 `actor` 가 빈 문자열인지만 봤다 — 즉 아무 문자열이나 철회할 수 있었다."""
    b = _declare(conn)
    org = __import__("core.org_directory", fromlist=["org_directory"]).org_directory
    org.upsert_user("plain@afs.invalid", "권한없음", primary_dept_id=DEPT,
                    is_data_admin=False, actor="seed")
    with pytest.raises(ob.OwnershipError, match="권한이 없습니다"):
        ob.revoke(conn, b["binding_id"], "plain@afs.invalid", "임의 철회")
    #: ★ 거부만으로 부족하다 — **결속이 그대로 살아 있는지**까지 본다.
    assert _resolve(conn) is not None, "거부됐는데 결속이 내려갔다"


def test_철회에는_사유가_필요하다(conn):
    """★ 철회 이력의 값은 「누가」가 아니라 「왜」에 있다."""
    b = _declare(conn)
    with pytest.raises(ob.OwnershipError, match="사유"):
        ob.revoke(conn, b["binding_id"], "auditor@afs.invalid", "")
    assert _resolve(conn) is not None


def test_소유권_승인_사건은_다른_주체로_남길_수_없다(org):
    """★★★ [4.1c-B P0-4] 원장이 **대상 종류**를 못박는다.

    ⚠️ 앞 판은 이름만 허용목록에 넣었다. 그러면 소유권 승인을 `app_dataset` 주체로 남겨
      두고 나중에 그 사건으로 결속을 통과시킬 수 있다 — 온톨로지에서 이미 막은 구멍을
      새 유형에 다시 낸 것이다."""
    from core.decision_ledger import DecisionLedgerError, decision_ledger
    with pytest.raises(DecisionLedgerError, match="subject_type"):
        decision_ledger.append(
            event_type=ob.EVENT_APPROVED, subject_type="app_dataset",
            subject_id="fp", actor_type="user", actor_id="std@afs.invalid",
            decision="APPROVED")


def test_소유권_철회는_부모를_가리켜야_한다(org):
    """⚠️ 부모 없는 철회는 아무것도 무효로 만들지 못하면서 «철회했다» 는 기록만 남긴다."""
    from core.decision_ledger import DecisionLedgerError, decision_ledger
    with pytest.raises(DecisionLedgerError, match="parent_event_id"):
        decision_ledger.append(
            event_type=ob.EVENT_REVOKED, subject_type=ob.SUBJECT_TYPE,
            subject_id="fp", actor_type="user", actor_id="std@afs.invalid",
            decision="REVOKED")


def test_소유권_철회의_부모는_소유권_승인이어야_한다(org):
    """★ 다른 승인 사건을 부모로 삼으면, 그 승인이 소유권 철회로 죽는다 —
    도메인이 다른 승인끼리 서로를 무효화하는 길이다."""
    from core.decision_ledger import DecisionLedgerError, decision_ledger
    other = decision_ledger.append(
        event_type="DECISION_RECORDED", subject_type="decision_case",
        subject_id="case_1", actor_type="user", actor_id="std@afs.invalid",
        decision="무관한 결정")
    with pytest.raises(DecisionLedgerError, match="parent_event_id 는"):
        decision_ledger.append(
            event_type=ob.EVENT_REVOKED, subject_type=ob.SUBJECT_TYPE,
            subject_id="fp", actor_type="user", actor_id="std@afs.invalid",
            decision="REVOKED", parent_event_id=other["event_id"])


def test_소유권_철회의_대상은_부모와_같아야_한다(conn):
    """★★ 부모 연결만 보면 **다른 결속 지문을 적은 철회**로도 원 승인을 무효화할 수 있다.
    그러면 감사에서 두 기록이 서로 다른 대상을 가리킨다."""
    from core.decision_ledger import DecisionLedgerError, decision_ledger
    b = _declare(conn)
    row = dict(conn.execute("SELECT approval_event_id FROM dataset_ownership_bindings "
                            "WHERE binding_id=?", (b["binding_id"],)).fetchone())
    with pytest.raises(DecisionLedgerError, match="철회 대상이 원 승인과 다릅니다"):
        decision_ledger.append(
            event_type=ob.EVENT_REVOKED, subject_type=ob.SUBJECT_TYPE,
            subject_id="fp_다른지문", actor_type="user", actor_id="std@afs.invalid",
            decision="REVOKED", parent_event_id=row["approval_event_id"])


# ── ⑰ 다중 프로세스 경쟁 — 서로 다른 시작시각, 겹치는 기간 ──────────────
#
#   ★★★ [4.1c-B P0-3] 부분 UNIQUE 는 「같은 **시작시각**」만 막는다. 시작시각이 다르면서
#     기간이 겹치는 두 요청은 각자 「겹치는 것 0건」을 읽은 뒤 **둘 다 삽입된다.**
#     앞 판의 회귀는 같은 시작시각 직접 삽입만 검사해서 이 구멍을 시험하지 않았다.
#
#   ⚠️ 응용 계층의 조회-후-삽입으로는 닫을 수 없다. 읽기와 쓰기 사이에 남이 넣는다.


# ── ⑰ 다중 프로세스 경쟁 — 서로 다른 시작시각, 겹치는 기간 ──────────────
#
#   ★★★ [4.1c-B P0-3] 부분 UNIQUE 는 「같은 **시작시각**」만 막는다. 시작시각이 다르면서
#     기간이 겹치는 두 요청은 각자 「겹치는 것 0건」을 읽은 뒤 **둘 다 삽입된다.**
#     앞 판의 회귀는 같은 시작시각 직접 삽입만 검사해서 이 구멍을 시험하지 않았다.
#
#   ⚠️ 응용 계층의 조회-후-삽입으로는 닫을 수 없다. 읽기와 쓰기 사이에 남이 넣는다.

def _own_db(tmp_path):
    path = str(tmp_path / "race.db")
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    ob.ensure_schema(c)
    c.close()
    return path


def _open(path):
    c = sqlite3.connect(path, timeout=5)
    c.row_factory = sqlite3.Row
    return c


def test_서로_다른_시작시각의_겹치는_결속을_두_연결이_동시에_넣지_못한다(org, tmp_path):
    """★★★ **실제 경쟁 순서를 재현한다.** 두 연결이 각각 「겹치는 것 없음」을 읽고,
    한쪽이 먼저 커밋한 뒤 다른 쪽이 삽입한다 — 응용 검사는 이미 지났다.

    ⚠️ 시작시각을 **다르게** 둔다. 같게 두면 부분 UNIQUE 가 잡아 버려서 이 시험은
      「기간 중첩 차단」이 아니라 「같은 시작시각 차단」을 검사하게 된다(앞 판이 그랬다)."""
    path = _own_db(tmp_path)
    a_from = "2026-01-01T00:00:00+00:00"
    b_from = "2026-03-01T00:00:00+00:00"      # ← 다른 시작시각, 그러나 기간은 겹친다

    ap_a = ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                      owner_dept_id=DEPT, actor_id="approver@afs.invalid",
                      evidence_ref="FND-01/v1#a", effective_from=a_from)
    ap_b = ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                      owner_dept_id=DEPT, actor_id="second@afs.invalid",
                      evidence_ref="FND-01/v1#b", effective_from=b_from)

    c1, c2 = _open(path), _open(path)
    try:
        #: ① 두 연결이 각각 조회한다 — **둘 다 0건**을 본다. 여기가 경쟁의 출발점이다.
        for c in (c1, c2):
            assert list(c.execute(
                "SELECT 1 FROM dataset_ownership_bindings WHERE status='ACTIVE'")) == []
        #: ② 한쪽이 먼저 넣고 커밋한다.
        ob.declare(c1, tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                   owner_dept_id=DEPT, approved_by="approver@afs.invalid",
                   evidence_ref="FND-01/v1#a", approval_event_id=ap_a["approval_event_id"],
                   effective_from=a_from)
        c1.commit()
        #: ③ 다른 쪽이 넣는다. 응용 검사는 이미 지났고 — **DB 가 막아야 한다.**
        with pytest.raises((sqlite3.IntegrityError, ob.OwnershipIntegrityError)):
            ob.declare(c2, tenant_id=T, entity_mode=M, dataset_contract_key=K,
                       scope_node_id=S, owner_dept_id=DEPT,
                       approved_by="second@afs.invalid", evidence_ref="FND-01/v1#b",
                       approval_event_id=ap_b["approval_event_id"], effective_from=b_from)
            c2.commit()
        c2.rollback()
        #: ④ 결과적으로 **한 건만** 남았는가.
        n = _open(path).execute("SELECT COUNT(*) FROM dataset_ownership_bindings "
                                "WHERE status='ACTIVE'").fetchone()[0]
        assert n == 1, f"겹치는 ACTIVE 결속이 {n}건 남았다 — 경쟁이 열려 있다"
    finally:
        c1.close(); c2.close()


def test_철회된_행을_ACTIVE_로_되살려_중첩을_만들지_못한다(conn):
    """★★ INSERT 만 막으면 «칸을 고쳐 되살리는» 경로가 남는다. 마이그레이션·시드는
    실제로 그 칸을 만진다."""
    a = _declare(conn, effective_from="2026-01-01T00:00:00+00:00",
                 effective_to="2026-06-01T00:00:00+00:00")
    ob.revoke(conn, a["binding_id"], "auditor@afs.invalid", "재검토")
    _declare(conn, approved_by="second@afs.invalid",
             effective_from="2026-03-01T00:00:00+00:00")
    with pytest.raises(sqlite3.IntegrityError, match="겹치는"):
        conn.execute("UPDATE dataset_ownership_bindings SET status='ACTIVE' "
                     "WHERE binding_id=?", (a["binding_id"],))


def test_겹치지_않으면_두_연결이_나란히_넣을_수_있다(org, tmp_path):
    """★★ **대조군.** 트리거가 「전부 막는 트리거」면 개정을 할 수 없다."""
    path = _own_db(tmp_path)
    ap_a = ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                      owner_dept_id=DEPT, actor_id="approver@afs.invalid",
                      evidence_ref="FND-01/v1#a",
                      effective_from="2026-01-01T00:00:00+00:00",
                      effective_to="2026-04-01T00:00:00+00:00")
    ap_b = ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                      owner_dept_id=DEPT, actor_id="second@afs.invalid",
                      evidence_ref="FND-01/v1#b",
                      effective_from="2026-04-01T00:00:00+00:00")
    c1, c2 = _open(path), _open(path)
    try:
        ob.declare(c1, tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                   owner_dept_id=DEPT, approved_by="approver@afs.invalid",
                   evidence_ref="FND-01/v1#a", approval_event_id=ap_a["approval_event_id"],
                   effective_from="2026-01-01T00:00:00+00:00",
                   effective_to="2026-04-01T00:00:00+00:00")
        c1.commit()
        ob.declare(c2, tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                   owner_dept_id=DEPT, approved_by="second@afs.invalid",
                   evidence_ref="FND-01/v1#b", approval_event_id=ap_b["approval_event_id"],
                   effective_from="2026-04-01T00:00:00+00:00")
        c2.commit()
        n = _open(path).execute("SELECT COUNT(*) FROM dataset_ownership_bindings "
                                "WHERE status='ACTIVE'").fetchone()[0]
        assert n == 2, f"기간이 분리된 두 결속을 나란히 둘 수 없다({n}건)"
    finally:
        c1.close(); c2.close()


def test_응용_검사가_통과해도_DB_가_중첩을_막는다(org, tmp_path, monkeypatch):
    """★★★ **트리거가 실제로 부담하는 몫**을 시험한다.

    ⚠️⚠️ [변이 시험에서 발견] 앞서 쓴 두 연결 회귀는 **트리거를 시험하지 않았다.**
      `declare()` 가 삽입 직전에 다시 조회하므로, 상대가 커밋한 뒤에는 **응용 검사가 먼저**
      잡는다 — 트리거를 통째로 무력화해도 실패가 0건이었다. 「경쟁을 재현했다」고 믿은
      시험이 실은 응용 검사만 확인하고 있었다.

    ★ 트리거의 몫은 **응용 검사가 통과한 다음**이다. 그 상태를 만드는 방법이 실제로 있다:
      ① 다중 프로세스에서 조회와 삽입이 다른 트랜잭션이다(둘 사이에 남이 커밋한다)
      ② 마이그레이션·시드가 응용을 지나지 않고 직접 INSERT 한다
      ③ 응용 검사에 결함이 생긴다(오늘 실제로 그런 결함을 두 번 고쳤다)
      세 경우 모두 「응용 검사는 통과했다」로 같으므로, 그 상태를 직접 만들어 시험한다."""
    path = _own_db(tmp_path)
    a_from = "2026-01-01T00:00:00+00:00"
    b_from = "2026-03-01T00:00:00+00:00"      # 다른 시작시각 · 겹치는 기간
    ap_a = ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                      owner_dept_id=DEPT, actor_id="approver@afs.invalid",
                      evidence_ref="FND-01/v1#a", effective_from=a_from)
    ap_b = ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                      owner_dept_id=DEPT, actor_id="second@afs.invalid",
                      evidence_ref="FND-01/v1#b", effective_from=b_from)
    c1, c2 = _open(path), _open(path)
    try:
        ob.declare(c1, tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                   owner_dept_id=DEPT, approved_by="approver@afs.invalid",
                   evidence_ref="FND-01/v1#a", approval_event_id=ap_a["approval_event_id"],
                   effective_from=a_from)
        c1.commit()
        #: ★ 「응용 검사가 통과한 상태」를 만든다 — 낡은 스냅숏을 읽은 것과 같은 상태다.
        monkeypatch.setattr(ob, "_overlaps", lambda *a, **k: False)
        with pytest.raises(ob.OwnershipIntegrityError, match="같은 시작시각|겹치는"):
            ob.declare(c2, tenant_id=T, entity_mode=M, dataset_contract_key=K,
                       scope_node_id=S, owner_dept_id=DEPT,
                       approved_by="second@afs.invalid", evidence_ref="FND-01/v1#b",
                       approval_event_id=ap_b["approval_event_id"], effective_from=b_from)
        c2.rollback()
        n = _open(path).execute("SELECT COUNT(*) FROM dataset_ownership_bindings "
                                "WHERE status='ACTIVE'").fetchone()[0]
        assert n == 1, f"응용 검사를 지나자 겹치는 결속이 {n}건 들어왔다"
    finally:
        c1.close(); c2.close()


def test_응용_검사가_통과해도_기간이_분리되면_들어온다(org, tmp_path, monkeypatch):
    """★★ 위 시험의 **대조군.** 트리거가 「전부 막는 트리거」면 위 초록은 의미가 없다."""
    path = _own_db(tmp_path)
    ap_a = ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                      owner_dept_id=DEPT, actor_id="approver@afs.invalid",
                      evidence_ref="FND-01/v1#a",
                      effective_from="2026-01-01T00:00:00+00:00",
                      effective_to="2026-04-01T00:00:00+00:00")
    ap_b = ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                      owner_dept_id=DEPT, actor_id="second@afs.invalid",
                      evidence_ref="FND-01/v1#b",
                      effective_from="2026-04-01T00:00:00+00:00")
    c1, c2 = _open(path), _open(path)
    try:
        ob.declare(c1, tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                   owner_dept_id=DEPT, approved_by="approver@afs.invalid",
                   evidence_ref="FND-01/v1#a",
                   approval_event_id=ap_a["approval_event_id"],
                   effective_from="2026-01-01T00:00:00+00:00",
                   effective_to="2026-04-01T00:00:00+00:00")
        c1.commit()
        monkeypatch.setattr(ob, "_overlaps", lambda *a, **k: False)
        ob.declare(c2, tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                   owner_dept_id=DEPT, approved_by="second@afs.invalid",
                   evidence_ref="FND-01/v1#b", approval_event_id=ap_b["approval_event_id"],
                   effective_from="2026-04-01T00:00:00+00:00")
        c2.commit()
        n = _open(path).execute("SELECT COUNT(*) FROM dataset_ownership_bindings "
                                "WHERE status='ACTIVE'").fetchone()[0]
        assert n == 2, f"기간이 분리됐는데 트리거가 막았다({n}건)"
    finally:
        c1.close(); c2.close()


# ── ⑱ 구버전 스키마(8ca029634) 마이그레이션 ──────────────────────────────
#
#   ★★★ [4.1c-B P0-2] `CREATE TABLE IF NOT EXISTS` 는 **이미 있는 표에 새 열을 넣어
#     주지 않는다.** 그래서 옛 형식 표가 있는 DB 에서는 첫 `declare()` 가
#     `no such column: approval_event_id` 로 죽는다.
#
#   ⚠️ 그리고 옛 행을 **승인된 것으로 백필하면 안 된다.** 그 행들은 승인 원장 사건이 없는
#     「승인됐다고 스스로 적은 결속」이다. 가짜 승인 사건을 만들어 승격시키면 이 작업이
#     지우려 한 자기진술을 **원장에 박아 넣는** 셈이고, 원장은 되돌릴 곳이 없다.

#: `8ca029634` 시점의 정본 표 — `approval_event_id`·`revocation_event_id` 가 없고
#: `evidence_ref` 도 선택이었다. **실제 사본**으로 시험한다(모양을 추측하지 않는다).
_LEGACY_DDL = """
CREATE TABLE IF NOT EXISTS dataset_ownership_bindings (
    binding_id           TEXT PRIMARY KEY,
    tenant_id            TEXT NOT NULL,
    entity_mode          TEXT NOT NULL,
    dataset_contract_key TEXT NOT NULL,
    scope_node_id        TEXT NOT NULL,
    owner_dept_id        TEXT NOT NULL,
    effective_from       TEXT NOT NULL,
    effective_to         TEXT NOT NULL DEFAULT '',
    status               TEXT NOT NULL DEFAULT 'ACTIVE',
    approved_by          TEXT NOT NULL,
    approved_at          TEXT NOT NULL,
    evidence_ref         TEXT NOT NULL DEFAULT '',
    revoked_by           TEXT NOT NULL DEFAULT '',
    revoked_at           TEXT NOT NULL DEFAULT '',
    revoked_reason       TEXT NOT NULL DEFAULT '',
    fingerprint          TEXT NOT NULL,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ownership_key
    ON dataset_ownership_bindings(tenant_id, entity_mode, dataset_contract_key,
                                  scope_node_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ownership_active_start
    ON dataset_ownership_bindings(tenant_id, entity_mode, dataset_contract_key,
                                  scope_node_id, effective_from);
"""


# ── ⑲ 원장 조회에서 승인 이력이 사라지지 않는다 ──────────────────────────

def test_소유_부서_관리자의_원장_조회에_승인이_보인다(conn):
    """★★★ [4.1c-B P1] 원장 조회 API 는 `enterprise_scope_id` 를 **부서 id** 로 해석한다.

    ⚠️ 앞 판은 그 칸에 ECM `scope_node_id` 를 넣었다. 그 값은 어느 부서의 읽기 집합에도
      없으므로 **소유 부서 관리자의 조회에서 승인 사건이 조용히 빠진다** — 오류 없이
      목록에서만 사라진다. 승인 이력이 보이지 않으면 감사도 이의도 할 수 없다.

    ★ 그래서 시험은 **제품의 필터 함수**를 그대로 태운다. 값만 비교하면 「그 값이 실제로
      통과하는가」는 여전히 모른다."""
    from api.routes.ledger_control import _filter_by_dept
    from core.decision_ledger import decision_ledger
    _declare(conn)
    rows = decision_ledger.list_events(event_type=ob.EVENT_APPROVED)
    assert rows, "승인 사건이 없다"

    class _Scope:
        unrestricted = False
        readable_dept_ids = frozenset({DEPT})

    class _P:
        scope = _Scope()
        user_id = "reader@afs.invalid"          # ⚠️ 행위자가 **아닌** 사람이어야 한다

    seen = _filter_by_dept(rows, _P())
    assert len(seen) == len(rows), \
        "소유 부서 관리자의 원장 조회에서 승인 사건이 빠졌다 — 범위 칸 규약이 어긋났다"


def test_다른_부서_사람에게는_승인이_보이지_않는다(conn):
    """★★ **대조군.** 위 시험이 「전부 보인다」로 통과하면 아무것도 지키지 못한다."""
    from api.routes.ledger_control import _filter_by_dept
    from core.decision_ledger import decision_ledger
    _declare(conn)
    rows = decision_ledger.list_events(event_type=ob.EVENT_APPROVED)

    class _Scope:
        unrestricted = False
        readable_dept_ids = frozenset({"남의부서"})

    class _P:
        scope = _Scope()
        user_id = "reader@afs.invalid"

    assert _filter_by_dept(rows, _P()) == []


def test_철회도_같은_범위_규약을_쓴다(conn):
    """★★★ 승인은 보이고 철회는 안 보이면, 그 이력은 「아직 유효하다」로 읽힌다 —
    가장 위험한 어긋남이다."""
    from api.routes.ledger_control import _filter_by_dept
    from core.decision_ledger import decision_ledger
    b = _declare(conn)
    ob.revoke(conn, b["binding_id"], "auditor@afs.invalid", "근거 미비")

    class _Scope:
        unrestricted = False
        readable_dept_ids = frozenset({DEPT})

    class _P:
        scope = _Scope()
        user_id = "reader@afs.invalid"

    for kind in (ob.EVENT_APPROVED, ob.EVENT_REVOKED):
        rows = decision_ledger.list_events(event_type=kind)
        assert rows and len(_filter_by_dept(rows, _P())) == len(rows), kind


# ── ⑳ 승인만 남는 상태 ────────────────────────────────────────────────────


# ── ⑳ 승인만 남는 상태 ────────────────────────────────────────────────────

def test_승인만_남고_결속이_없으면_권한이_생기지_않는다(conn):
    """★★★ [4.1c-B P1] `approve()`(원장)와 `declare()`(정본 표)는 다른 저장소의 두 단계라
    한 트랜잭션으로 묶을 수 없다 — 등록이 실패하면 승인 사건만 남는다.

    ⚠️ 그 상태 자체는 안전해야 한다(fail-closed). 「원장에 승인이 있으니 유효」로 읽으면
      **등록되지 않은 승인이 권한이 된다.**

    ⚠️ **이 시험은 변이 검사로 포착되지 않는다**(정직하게 적는다). `resolve()` 는 정본 표를
      먼저 보므로 「원장을 먼저 보는」 코드가 애초에 없고, 그것을 없애는 변이를 만들 수
      없다. 즉 이것은 통제 회귀가 아니라 **계약 서술**이다 — 나중에 누가 «원장에 승인이
      있으면 통과» 를 추가하려 할 때 이 시험이 그것을 막는다."""
    ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
               owner_dept_id=DEPT, actor_id="approver@afs.invalid",
               evidence_ref="FND-01/v1#seed")
    assert _resolve(conn) is None, "결속 없는 승인이 권한이 됐다"


def test_승인만_남은_건은_보고에_드러난다(conn):
    """⚠️ 조용히 쌓이면 원장의 승인 건수와 실제 결속 수가 갈라지고, 아무도 그 차이를 세지 않는다."""
    ap = ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                    owner_dept_id=DEPT, actor_id="approver@afs.invalid",
                    evidence_ref="FND-01/v1#seed")
    dangling = ob.dangling_approvals(conn, tenant_id=T, entity_mode=M, unrestricted=True)
    assert [d["approval_event_id"] for d in dangling] == [ap["approval_event_id"]]


def test_취소하면_보고에서도_사라지고_되살릴_수_없다(conn):
    """★ 취소는 **철회와 같은 사건**이다. 그래서 `resolve` 의 철회 자식 검사가 자동으로
    그 승인을 죽인다 — 통제를 두 벌로 만들지 않는다."""
    ap = ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                    owner_dept_id=DEPT, actor_id="approver@afs.invalid",
                    evidence_ref="FND-01/v1#seed")
    ob.abandon(ap["approval_event_id"], "approver@afs.invalid", "등록 실패")
    assert ob.dangling_approvals(conn, tenant_id=T, entity_mode=M, unrestricted=True) == []
    #: ★★ 취소된 승인으로는 **등록도 안 된다** — 그러지 않으면 취소가 무의미하다.
    with pytest.raises(ob.OwnershipError):
        ob.declare(conn, tenant_id=T, entity_mode=M, dataset_contract_key=K,
                   scope_node_id=S, owner_dept_id=DEPT,
                   approved_by="approver@afs.invalid", evidence_ref="FND-01/v1#seed",
                   approval_event_id=ap["approval_event_id"],
                   effective_from=ap["effective_from"])


def test_등록된_승인은_보고에_들어가지_않는다(conn):
    """★★ **대조군.** 이것이 빨개지면 위 보고는 「전부 미완」이라고 말하는 셈이다."""
    _declare(conn)
    assert ob.dangling_approvals(conn, tenant_id=T, entity_mode=M, unrestricted=True) == []


# ── ㉔ 마이그레이션 원자성 ────────────────────────────────────────────────
#
#   ★★★ [4.1c-C P1-3] `migrate()` 다음에 `executescript(DDL)` 가 돈다. `executescript` 는
#     **열려 있는 트랜잭션을 먼저 커밋한다**(이 파일에서 실측한 그 성질이다). 즉 rename 은
#     DDL 실행 전에 커밋되고, DDL 이 실패하면 **격리는 됐는데 새 표가 없는** 상태가 남는다.
#
#   ⚠️ 그 상태를 「있을 리 없다」로 두지 않는다. 확인할 것은 세 가지다:
#     ① 그 상태에서 서비스가 조용히 오답을 주지 않는가(fail-closed 인가)
#     ② 재시작하면 결정론적으로 복구되는가
#     ③ 격리 **자체가** 실패하면(색인 제거 실패 등) 옛 표가 그대로 남는가(롤백)

def test_DDL_이_실패해도_격리는_되돌릴_수_없지만_상태는_안전하다(org, tmp_path):
    """★★ ①②를 함께 본다. 「되돌릴 수 없다」를 숨기지 않고, 그 상태가 **안전한지**를 본다."""
    c = _legacy_db(tmp_path, rows=2)
    ob.migrate(c)
    with pytest.raises(sqlite3.OperationalError):
        c.executescript("CREATE TABLE (((;")          # DDL 실패 주입
    #: ① 새 표가 없다 — 그런데 조용히 「소유자 없음」을 답하지 않는다.
    assert ob._columns(c, "dataset_ownership_bindings") == set()
    with pytest.raises(ob.OwnershipUnavailable):
        ob.resolve(c, tenant_id=T, entity_mode=M, dataset_contract_key="KEY-0",
                   scope_node_id=S)
    #: ★ 격리 상태는 남아 있다 — 운영자가 이유를 알 수 있다.
    assert ob.quarantine_state(c)["unresolved"] == 2
    c.commit(); c.close()

    #: ② 재시작 = 같은 파일에 초기화를 다시 돌린다. 결정론적으로 복구되어야 한다.
    c2 = sqlite3.connect(str(tmp_path / "legacy.db"))
    again = ob.migrate(c2)
    assert again["action"] == "none", again          # 옛 표는 이미 없다
    c2.executescript(ob.DDL)
    assert {"approval_event_id", "revocation_event_id"} <= \
        ob._columns(c2, "dataset_ownership_bindings")
    #: ★★ 그리고 격리 상태는 **두 번 쌓이지 않는다.**
    assert ob.quarantine_state(c2)["unresolved"] == 2
    #: ★ 복구 뒤에는 등록이 된다.
    ap = ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key="KEY-0",
                    scope_node_id=S, owner_dept_id=DEPT,
                    actor_id="approver@afs.invalid", evidence_ref="FND-01/v1#복구")
    ob.declare(c2, tenant_id=T, entity_mode=M, dataset_contract_key="KEY-0",
               scope_node_id=S, owner_dept_id=DEPT, approved_by="approver@afs.invalid",
               evidence_ref="FND-01/v1#복구", approval_event_id=ap["approval_event_id"],
               effective_from=ap["effective_from"])
    assert ob.quarantine_state(c2)["unresolved"] == 1
    c2.close()


def test_격리_도중_실패하면_옛_표가_그대로_남는다(org, tmp_path, monkeypatch):
    """★★★ ③ — `migrate()` **안에서** 실패하면 아무것도 옮겨지지 않아야 한다.

    ⚠️ 여기서 반쯤 진행되면 최악이다: 색인·트리거는 지워졌는데 표는 옛 이름 그대로 남고,
      그러면 다음 기동에서 **통제 없는 표**로 서비스가 돈다."""
    c = _legacy_db(tmp_path, rows=2)

    def _boom(_conn, _table):
        raise sqlite3.OperationalError("색인 제거 실패")

    monkeypatch.setattr(ob, "_drop_attached", _boom)
    with pytest.raises(sqlite3.OperationalError):
        ob.migrate(c)
    c.rollback()
    #: 옛 표가 그대로 있고, 옛 색인도 살아 있다.
    assert ob._columns(c, "dataset_ownership_bindings")
    assert ob._columns(c, ob.LEGACY_TABLE) == set(), "반쯤 옮겨졌다"
    idx = [r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'")]
    assert "uq_ownership_active_start" in idx, "색인만 지워지고 표는 남았다"
    c.close()


def test_격리_뒤_새_표가_없는_동안_등록도_막힌다(org, tmp_path):
    """⚠️ 「없으면 만든다」로 넘기면, 그 순간 **트리거 없는 표**가 생긴다 —
    통제가 빠진 표로 서비스가 계속 돌게 되고, 아무도 그것을 모른다."""
    c = _legacy_db(tmp_path, rows=1)
    ob.migrate(c)                                    # 새 표를 만들지 않는다
    ap = ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key="KEY-0",
                    scope_node_id=S, owner_dept_id=DEPT,
                    actor_id="approver@afs.invalid", evidence_ref="FND-01/v1#x")
    with pytest.raises(sqlite3.OperationalError):
        ob.declare(c, tenant_id=T, entity_mode=M, dataset_contract_key="KEY-0",
                   scope_node_id=S, owner_dept_id=DEPT,
                   approved_by="approver@afs.invalid", evidence_ref="FND-01/v1#x",
                   approval_event_id=ap["approval_event_id"],
                   effective_from=ap["effective_from"])
    c.close()
