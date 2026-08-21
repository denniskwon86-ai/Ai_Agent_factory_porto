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


@pytest.fixture()
def conn(monkeypatch):
    """격리 DB + **부서가 살아 있는 조직도.**

    ⚠️ 부트스트라핑이 아닌 상태로 세운다. 부트스트랩이면 부서 검사가 통째로 건너뛰어져
      「없는 부서」 계약을 시험할 수 없다 — 현실에 없는 모양으로 시험하는 셈이다."""
    from core.org_directory import org_directory
    monkeypatch.setattr(org_directory, "is_bootstrap", lambda: False)
    monkeypatch.setattr(org_directory, "get_department",
                        lambda d: {"dept_id": d, "status": "active"} if d == DEPT else None,
                        raising=False)
    path = os.path.join(tempfile.mkdtemp(), "own.db")
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    ob.ensure_schema(c)
    yield c
    c.close()


def _declare(conn, **kw):
    args = dict(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                owner_dept_id=DEPT, approved_by="approver@afs.invalid",
                evidence_ref="FND-01/v1#seed")
    args.update(kw)
    return ob.declare(conn, **args)


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
    with pytest.raises(ob.OwnershipError, match="approved_by"):
        _declare(conn, approved_by="")


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


def test_해석_시점에_유효한_결속이_둘이면_503(conn):
    """⚠️ `declare` 를 우회해 직접 넣힌 자료도 있을 수 있다 — 해석 쪽에서도 막는다.
    한쪽만 막으면 마이그레이션·시드가 그 구멍으로 들어온다."""
    _declare(conn, effective_from="2026-01-01T00:00:00+00:00")
    conn.execute(
        "INSERT INTO dataset_ownership_bindings (binding_id, tenant_id, entity_mode,"
        "dataset_contract_key, scope_node_id, owner_dept_id, effective_from, effective_to,"
        "status, approved_by, approved_at, evidence_ref, fingerprint, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("own_dup", T, M, K, S, DEPT, "2026-02-01T00:00:00+00:00", "",
         ob.ACTIVE, "x@afs.invalid", "2026-02-01T00:00:00+00:00", "", "fp_dup",
         "2026-02-01T00:00:00+00:00", "2026-02-01T00:00:00+00:00"))
    with pytest.raises(ob.OwnershipIntegrityError, match="2건"):
        _resolve(conn, as_of="2026-07-01T00:00:00+00:00")


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
