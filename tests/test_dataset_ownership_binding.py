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
def conn(monkeypatch, tmp_path):
    """격리 DB + 살아 있는 부서 + **격리 원장.**

    ★★ [재감사 보정] 부트스트랩 예외를 세우지 **않는다** — 코드에서 없앴다. `is_bootstrap`
      은 초기 관리자 생성을 위한 **접근정책 예외**이고, 데이터 소유권 정본 검증까지 면제하는
      규칙이 아니다. 첫 판은 그 예외 하나로 임의 부서가 전부 통과했다.
    ⚠️ 원장도 격리한다. 실 원장에 시험 승인 사건을 쌓으면 그 이력이 제품 감사에 섞인다."""
    from core.decision_ledger import decision_ledger
    from core.org_directory import org_directory
    monkeypatch.setattr(org_directory, "get_department",
                        lambda d: {"dept_id": d, "status": "active"} if d == DEPT else None,
                        raising=False)
    monkeypatch.setattr(decision_ledger, "db_path", str(tmp_path / "ledger.db"),
                        raising=False)
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


def test_해석_시점에_유효한_결속이_둘이면_503(conn):
    """⚠️ `declare` 를 우회해 직접 넣힌 자료도 있을 수 있다 — 해석 쪽에서도 막는다.
    한쪽만 막으면 마이그레이션·시드가 그 구멍으로 들어온다."""
    _declare(conn, effective_from="2026-01-01T00:00:00+00:00")
    ap = ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                    owner_dept_id=DEPT, actor_id="x@afs.invalid",
                    evidence_ref="FND-01/v1#dup", effective_from="2026-02-01T00:00:00+00:00")
    conn.execute(
        "INSERT INTO dataset_ownership_bindings (binding_id, tenant_id, entity_mode,"
        "dataset_contract_key, scope_node_id, owner_dept_id, effective_from, effective_to,"
        "status, approved_by, approved_at, approval_event_id, evidence_ref, fingerprint,"
        "created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("own_dup", T, M, K, S, DEPT, "2026-02-01T00:00:00+00:00", "",
         ob.ACTIVE, "x@afs.invalid", "2026-02-01T00:00:00+00:00",
         ap["approval_event_id"], "FND-01/v1#dup", ap["fingerprint"],
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

def test_승인_권한이_없으면_승인_사건도_남지_않는다(monkeypatch, tmp_path):
    """★★★ [2차 보정] 첫 판은 「행위자 권한은 여기서 확인한다」고 **주석에만** 적어 두고
    코드는 빈 문자열 검사만 했다. `approve()` 를 부르는 API 경로도 없었으니, 실제로는
    **아무도 권한을 보지 않았다.**

    ⚠️ 권한 없는 사람의 승인 사건이 원장에 남으면, 그 이력이 나중에 승인의 근거로 읽힌다 —
      원장은 「무엇이 있었나」의 마지막 답이므로 거짓이 들어가면 되돌릴 곳이 없다."""
    from core.decision_ledger import decision_ledger
    from core.org_directory import OrgDirectory
    import core.org_directory as orgmod
    import core.scope_policy as sp

    org = OrgDirectory(db_path=str(tmp_path / "org.db"))
    org.create_department(DEPT, "본사")
    org.upsert_user("nobody@afs.invalid", "권한없음", primary_dept_id=DEPT, actor="seed")
    org.upsert_user("std@afs.invalid", "표준승인자", primary_dept_id=DEPT,
                    is_data_admin=True, actor="seed")
    monkeypatch.setattr(sp, "_read", lambda: {"org_enforce": True})
    monkeypatch.setattr(orgmod, "org_directory", org)
    monkeypatch.setattr(decision_ledger, "db_path", str(tmp_path / "ledger.db"),
                        raising=False)

    with pytest.raises(ob.OwnershipError, match="권한이 없습니다"):
        ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                   owner_dept_id=DEPT, actor_id="nobody@afs.invalid",
                   evidence_ref="FND-01/v1#seed")
    #: ⚠️ 거부만으로는 부족하다 — **원장에 사건이 남지 않았는지**까지 본다. 남았다면
    #:   「거부됐지만 이력에는 승인이 있는」 상태이고, 그것이 더 나쁘다.
    assert decision_ledger.list_events(event_type=ob.EVENT_APPROVED) == []

    #: 대조군 — 권한 있는 사람은 통과한다. 없으면 위 검사는 「전부 막는 검사」다.
    ap = ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                    owner_dept_id=DEPT, actor_id="std@afs.invalid",
                    evidence_ref="FND-01/v1#seed")
    assert ap["approval_event_id"]


def test_권한_판독_실패는_통과가_아니다(monkeypatch):
    """⚠️ 조직도가 흔들리는 순간에 승인이 열리면, 장애가 곧 승인 통제 해제다."""
    import core.org_directory as orgmod

    class _Boom:
        def resolve_scope(self, _uid=""):
            raise RuntimeError("조직도 장애")

    monkeypatch.setattr(orgmod, "org_directory", _Boom())
    with pytest.raises(ob.OwnershipUnavailable, match="권한을 확인하지 못했습니다"):
        ob.approve(tenant_id=T, entity_mode=M, dataset_contract_key=K, scope_node_id=S,
                   owner_dept_id=DEPT, actor_id="std@afs.invalid",
                   evidence_ref="FND-01/v1#seed")
