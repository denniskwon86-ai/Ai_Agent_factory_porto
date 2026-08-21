"""★★★ [G2 · Dataset Ownership Binding] 「이 데이터셋은 어느 부서가 소유하는가」의 **정본.**

## 왜 별도 정본인가 — 업무 행이 자기 권한을 정하면 안 된다

종전 색인은 업무 데이터 행의 `owner_dept_id` 열을 그대로 읽었다. 그러면 **자기 데이터의
권한 범위를 데이터가 스스로 정한다** — 앞서 지운 `calc_binding` 과 **같은 유형의
자기진술 통제**다. 고객사 파일 한 칸을 고치면 그 데이터의 소유 부서가 바뀐다.

    (tenant_id, entity_mode, dataset_contract_key, scope_node_id, 유효기간)
        → owner_dept_id     + 승인 원장 사건 · 행위자 · 근거 · 지문

## ⚠️⚠️ 1차 구현의 결함 — 「승인」이 승인이 아니었다 (재감사 2026-08-21)

첫 판의 `declare()` 는 **임의의 `approved_by` 문자열만 받으면 즉시 `ACTIVE`** 를 만들었다.

    · Decision Ledger 승인 사건 검증 없음
    · 행위자 권한 검증 없음
    · `evidence_ref` 는 주석이 「필수」라 적었는데 코드는 **빈 값을 허용**했다
    · 철회도 원장 사건이 아니라 직접 `UPDATE`

즉 정본은 「승인된 결속」이 아니라 **「승인됐다고 스스로 적은 결속」** 이었다. 내가 지운
`calc_binding` 과 똑같은 자기진술을, 그것을 지운 커밋 바로 다음에 다시 만든 것이다.

이제 **원장 사건이 없으면 결속을 만들 수 없고**, 요청마다 그 사건과 **철회 자식 사건**을
다시 확인한다.

## ⚠️⚠️ `executescript` 는 진행 중인 트랜잭션을 조기 커밋한다

첫 판은 `declare/resolve/revoke/list` 마다 `ensure_schema()` → `executescript()` 를 불렀다.
SQLite 에서 그것은 **열려 있는 상위 트랜잭션을 커밋**한다. 실측:

    BEFORE in_transaction  True
    AFTER_SCRIPT           False
    ROWS_AFTER_ROLLBACK    1      ← 롤백이 무효가 됐다

그래서 「인증 상태 전환과 색인 기록을 한 트랜잭션으로」라는 보증이 **주석에만** 있었다.
DDL 은 **저장소 초기화·마이그레이션에서만** 돌린다. 이 파일의 조회·기록 함수는 절대 돌리지 않는다.

LLM 0콜. 결정론적.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

ACTIVE = "ACTIVE"
REVOKED = "REVOKED"
RETIRED = "RETIRED"
STATUSES = (ACTIVE, REVOKED, RETIRED)

#: 원장 사건 이름. **승인과 철회가 각각 한 사건**이고, 철회는 승인의 **자식**이다 —
#: 그래야 「이 승인이 아직 살아 있는가」를 부모-자식 관계로 물을 수 있다.
EVENT_APPROVED = "DATASET_OWNERSHIP_APPROVED"
EVENT_REVOKED = "DATASET_OWNERSHIP_REVOKED"
SUBJECT_TYPE = "dataset_ownership_binding"

#: 무기한 끝점. `''` 를 그대로 비교하면 «가장 작은 값» 이 되어 무기한이 오히려 «이미 끝난
#: 것» 으로 읽힌다.
_OPEN_END = datetime(9999, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

DDL = """
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
    -- ★★★ 승인 «원장 사건» 의 id. 이것이 없으면 결속이 아니다 — 자기진술과 승인을 가르는 값.
    approval_event_id    TEXT NOT NULL,
    evidence_ref         TEXT NOT NULL,
    fingerprint          TEXT NOT NULL,
    revoked_by           TEXT NOT NULL DEFAULT '',
    revoked_at           TEXT NOT NULL DEFAULT '',
    revoked_reason       TEXT NOT NULL DEFAULT '',
    revocation_event_id  TEXT NOT NULL DEFAULT '',
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ownership_key
    ON dataset_ownership_bindings(tenant_id, entity_mode, dataset_contract_key,
                                  scope_node_id, status);
-- ★★ 같은 키·같은 시작시각의 ACTIVE 중복을 **DB 가** 막는다. 조회 후 삽입만으로는
--    다중 프로세스에서 중첩이 생긴다(읽기와 쓰기 사이에 남이 넣는다).
CREATE UNIQUE INDEX IF NOT EXISTS uq_ownership_active_start
    ON dataset_ownership_bindings(tenant_id, entity_mode, dataset_contract_key,
                                  scope_node_id, effective_from)
    WHERE status = 'ACTIVE';

-- ★★★ [4.1c-B P0-3 / 4.1c-C P0-1] **기간 중첩을 DB 가 막는다.**
--
-- ⚠️⚠️ 부분 UNIQUE 는 「같은 **시작시각**」만 막는다. 시작시각이 다르면서 기간이 겹치는
--   두 요청은 각자 「겹치는 것 0건」을 읽은 뒤 **둘 다 삽입된다.** 응용 계층의 조회-후-삽입
--   으로는 닫을 수 없는 구멍이다(다중 프로세스에서 읽기와 쓰기 사이에 남이 넣는다).
--
-- ⚠️⚠️⚠️ [4.1c-C P0-1] 앞 판은 이 비교를 **문자열 비교**로 썼고, 주석에 「`declare()` 가
--   UTC 로 정규화하니 안전하다」고 적었다. 그것이 틀린 이유는 단순하다 —
--   **트리거의 존재 목적이 바로 `declare()` 를 우회하는 경로를 막는 것**이다.
--   우회하는 경로가 정규화를 지나지 않으므로, 정규화를 근거로 삼은 순간 트리거는
--   자기가 지키겠다고 한 경로에서 아무것도 지키지 않는다. 실측:
--
--       기존  2026-06-01T00:00:00+00:00 ~ 02:00Z
--       신규  2026-06-01T10:00:00+09:00 ~ 12:00+09  (= 01:00Z ~ 03:00Z)
--       결과  OVERLAPPING_ACTIVE_ROWS 2       ← 문자열로는 "T10" > "T02" 라 안 겹쳐 보인다
--
--   시간대 없는 값(`2026-07-01T00:00:00`)과 파싱 불가 값(`언제인지모름`)도 그대로 통과했다.
--
-- ★ 그래서 `julianday()` 로 **시각으로 바꿔** 비교한다. SQLite 의 시간 함수는 ISO-8601 의
--   오프셋을 적용해 UTC 기준 값을 주고, 읽을 수 없으면 NULL 을 준다.
-- ★★ 규칙은 INSERT·UPDATE 가 **한 벌을 공유**한다(아래 파이썬에서 조립). 두 벌로 쓰면
--   한쪽만 고쳐지는 날이 오고, 그날 UPDATE 경로만 조용히 헐거워진다.
{_OVERLAP_TRIGGERS}
"""


# ── 기간 트리거 조립 ──────────────────────────────────────────────────────
#
#   ⚠️ SQL 을 두 벌 쓰지 않는다. INSERT 와 UPDATE 가 같은 문자열에서 나와야 「양쪽 동일
#     규칙」이 코드로 보장된다 — 주석으로 약속하면 지켜지지 않는다(이 파일에서 이미
#     같은 유형의 결함을 세 번 고쳤다).

#: 시간대 표기가 있는가. `+HH:MM` / `-HH:MM` / `Z` 만 인정한다.
#:   ⚠️ 시간대 없는 값을 받아 두면 나중에 비교하는 쪽이 **추측**한다. 그 추측은 서버
#:     시간대에 따라 달라지고, 배포 환경이 바뀌면 소유권이 바뀐다.
def _tz_ok(col: str) -> str:
    return (f"({col} LIKE '%Z' OR {col} LIKE '%+__:__' OR {col} LIKE '%-__:__')")


def _time_guard_sql() -> str:
    """새 행의 유효기간이 **시각으로 읽히는가.** 아니면 ABORT."""
    return f"""
    SELECT RAISE(ABORT, '유효기간에 시간대가 없습니다 — 소유권 결속의 시각은 UTC 오프셋을 포함해야 합니다')
     WHERE NOT {_tz_ok('NEW.effective_from')}
        OR (NEW.effective_to <> '' AND NOT {_tz_ok('NEW.effective_to')});
    SELECT RAISE(ABORT, '유효기간을 시각으로 읽을 수 없습니다')
     WHERE julianday(NEW.effective_from) IS NULL
        OR (NEW.effective_to <> '' AND julianday(NEW.effective_to) IS NULL);
    SELECT RAISE(ABORT, '유효기간이 뒤집혀 있거나 비어 있습니다 — 끝점은 배타적입니다')
     WHERE NEW.effective_to <> ''
       AND julianday(NEW.effective_to) <= julianday(NEW.effective_from);"""


def _overlap_guard_sql() -> str:
    """같은 키에 **기간이 겹치는** ACTIVE 결속이 있는가. 아니면 ABORT.

    ⚠️ 기존 행이 읽히지 않으면 «겹치지 않는다» 가 아니라 **점검 필요**다. 비교가 NULL 이
      되어 조용히 통과하는 것을 막는다 — 「모르니까 통과」는 이 파일에서 가장 자주
      되살아나는 결함이다."""
    same_key = """b.status = 'ACTIVE'
           AND b.binding_id <> NEW.binding_id
           AND b.tenant_id = NEW.tenant_id
           AND b.entity_mode = NEW.entity_mode
           AND b.dataset_contract_key = NEW.dataset_contract_key
           AND b.scope_node_id = NEW.scope_node_id"""
    return f"""
    SELECT RAISE(ABORT, '기존 ACTIVE 소유권 결속의 유효기간을 시각으로 읽을 수 없습니다 — 점검이 필요합니다')
     WHERE EXISTS (
        SELECT 1 FROM dataset_ownership_bindings b
         WHERE {same_key}
           AND (julianday(b.effective_from) IS NULL
                OR (b.effective_to <> '' AND julianday(b.effective_to) IS NULL))
     );
    SELECT RAISE(ABORT, '기간이 겹치는 ACTIVE 소유권 결속이 이미 있습니다')
     WHERE EXISTS (
        SELECT 1 FROM dataset_ownership_bindings b
         WHERE {same_key}
           AND julianday(NEW.effective_from) <
               julianday(COALESCE(NULLIF(b.effective_to, ''), '9999-12-31T23:59:59+00:00'))
           AND julianday(b.effective_from) <
               julianday(COALESCE(NULLIF(NEW.effective_to, ''), '9999-12-31T23:59:59+00:00'))
     );"""


#: INSERT 와 UPDATE 가 **같은 두 조각**을 쓴다.
_OVERLAP_TRIGGERS = f"""
CREATE TRIGGER IF NOT EXISTS trg_ownership_no_overlap_insert
BEFORE INSERT ON dataset_ownership_bindings
FOR EACH ROW WHEN NEW.status = 'ACTIVE'
BEGIN{_time_guard_sql()}{_overlap_guard_sql()}
END;

-- ⚠️ UPDATE 쪽도 막는다. 그러지 않으면 `REVOKED` 행의 `status` 를 `ACTIVE` 로 되살려
--   중첩을 만들 수 있다 — 「행의 칸을 고치는」 경로는 실제로 존재한다(마이그레이션·시드).
CREATE TRIGGER IF NOT EXISTS trg_ownership_no_overlap_update
BEFORE UPDATE OF status, effective_from, effective_to, tenant_id, entity_mode,
                 dataset_contract_key, scope_node_id
ON dataset_ownership_bindings
FOR EACH ROW WHEN NEW.status = 'ACTIVE'
BEGIN{_time_guard_sql()}{_overlap_guard_sql()}
END;
"""

DDL = DDL.format(_OVERLAP_TRIGGERS=_OVERLAP_TRIGGERS)



class OwnershipError(ValueError):
    """계약 위반 — 4xx 로 전달한다."""


class OwnershipIntegrityError(RuntimeError):
    """자료가 어긋났다(중첩 결속 · 없는 부서 · 색인과 결속 불일치 · 승인 사건 없음) — **503**.

    ⚠️ 「안 보인다」와 섞지 않는다. 전자는 정상적인 비노출이고 이것은 **고쳐야 할 것**이다.
      뭉개면 아무도 고치지 않는다."""


class OwnershipUnavailable(RuntimeError):
    """정본·원장을 읽지 못했다 — **503**.

    ⚠️ 읽기 실패를 「결속 없음」으로 답하지 않는다. 그러면 장애가 곧 **조용한 통제 해제**가
      된다 — 저장소가 흔들리는 순간에 모든 데이터가 «소유자 없음» 이 된다."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc(text: Any, *, field: str) -> datetime:
    """ISO 문자열을 **UTC datetime** 으로. 문자열 비교를 쓰지 않는 이유가 이것이다.

    ⚠️⚠️ 첫 판은 ISO 문자열을 그대로 `<=` 비교했다. 그래서 UTC offset 이 다르면
      `2026-06-01T00:00:00+09:00`(= 05-31 15:00Z)이 `2026-05-31T20:00:00+00:00` 보다
      **문자열로는 크다.** 실제로 겹치는 기간을 「겹치지 않는다」고 판정했다 —
      같은 시각을 다른 표기로 쓰면 중첩 차단이 조용히 뚫린다."""
    s = str(text or "").strip()
    if not s:
        raise OwnershipError(f"{field} 가 비어 있습니다.")
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError as e:
        raise OwnershipError(f"{field} 를 시각으로 읽을 수 없습니다({s}): {e}")
    #: 시간대 없는 값을 UTC 로 «가정» 하지 않는다 — 9시간 어긋난 판정이 조용히 통과한다.
    if d.tzinfo is None:
        raise OwnershipError(
            f"{field} 에 시간대가 없습니다({s}) — UTC 로 가정하면 판정이 조용히 어긋납니다.")
    return d.astimezone(timezone.utc)


def _end_utc(text: Any) -> datetime:
    return _OPEN_END if not str(text or "").strip() else _utc(text, field="effective_to")


def fingerprint_of(tenant_id: str, entity_mode: str, dataset_contract_key: str,
                   scope_node_id: str, owner_dept_id: str,
                   effective_from: str, effective_to: str,
                   approved_by: str, evidence_ref: str) -> str:
    """결속 내용의 지문. **승인자와 근거까지 넣는다** — 같은 부서를 다른 근거로 승인한 것은
    다른 결속이다.

    ⚠️ 시각은 **UTC 정규화 후** 넣는다. 같은 순간을 다른 표기로 쓴 두 결속이 서로 다른
      지문을 갖게 두면 멱등 판정이 깨지고 중첩이 생긴다."""
    blob = json.dumps({
        "tenant_id": tenant_id, "entity_mode": entity_mode,
        "dataset_contract_key": dataset_contract_key, "scope_node_id": scope_node_id,
        "owner_dept_id": owner_dept_id,
        "effective_from": _utc(effective_from, field="effective_from").isoformat(),
        "effective_to": ("" if not str(effective_to or "").strip()
                         else _utc(effective_to, field="effective_to").isoformat()),
        "approved_by": approved_by, "evidence_ref": evidence_ref,
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _overlaps(a_from: str, a_to: str, b_from: str, b_to: str) -> bool:
    """두 유효기간이 겹치는가. **UTC 로 정규화한 반열 구간 `[from, to)`** 으로 비교한다.

    ★★ 끝점은 **배타적**이다. 닫힌 구간(`<=`)으로 두면 두 가지가 동시에 망가진다:
      ① 개정 경계의 **그 한 순간**에 두 결속이 동시에 유효해져 `resolve` 가 503 을 낸다.
      ② 그것을 피하려고 하루씩 공백을 두게 되고, 그 공백 동안 소유자가 **없어진다**
         (=조용한 비노출). 「끝난 순간부터 다음 판」이 자연스러운 표현이어야 한다.
    ⚠️ 그래서 `to` 를 «마지막으로 유효한 순간» 으로 읽지 않는다 — «유효가 끝나는 순간» 이다.
      이 규약은 `resolve()` 의 창 필터와 **반드시 같아야** 한다. 한쪽만 바꾸면 등록은
      허용되는데 해석에서 둘 다 잡히는(또는 하나도 안 잡히는) 상태가 된다."""
    return (_utc(a_from, field="effective_from") < _end_utc(b_to)
            and _utc(b_from, field="effective_from") < _end_utc(a_to))


def ensure_schema(conn: Any) -> None:
    """★★★ **초기화·마이그레이션에서만 부른다.**

    ⚠️⚠️ `executescript` 는 열려 있는 트랜잭션을 **조기 커밋한다**(실측 확인). 조회·기록
      함수가 이것을 부르면 「인증 상태 전환과 색인 기록을 한 트랜잭션으로」라는 보증이
      깨지고, 롤백이 무효가 된다. 그래서 이 함수는 여기 한 곳에만 있고 아래 어느 함수도
      부르지 않는다."""
    conn.executescript(DDL)


#: 격리된 옛 결속을 옮겨 두는 표. **새 표와 이름이 달라야** 조회 경로가 섞이지 않는다.
LEGACY_TABLE = "dataset_ownership_bindings_legacy_unapproved"

#: ★★★ [4.1c-C P1-1] **격리는 영속 상태여야 한다.**
#:
#: ⚠️ 앞 판은 격리하면서 `print` 만 남겼다. 그러면 서비스는 빈 새 표로 계속 가동되고,
#:   **모든 데이터가 UNBOUND 가 된 이유를 운영자가 화면에서 알 수 없다.** 기동 로그는
#:   다음 재시작에 사라지고, 그때부터는 「원래 소유자가 없었다」와 구분되지 않는다.
#: ★ 그래서 계약키·범위 단위로 미해결 행을 남기고, **재승인이 끝날 때까지 해제되지 않는다.**
#: ⚠️ 이 표는 `DDL` 에 넣지 않는다 — `migrate()` 가 `DDL` **보다 먼저** 돌아야 하므로,
#:   그 시점에 이미 있어야 한다. 그리고 `executescript` 를 쓰지 않는다(조기 커밋).
QUARANTINE_TABLE = "dataset_ownership_quarantine"

_QUARANTINE_DDL = f"""
CREATE TABLE IF NOT EXISTS {QUARANTINE_TABLE} (
    quarantine_id        TEXT PRIMARY KEY,
    tenant_id            TEXT NOT NULL,
    entity_mode          TEXT NOT NULL,
    dataset_contract_key TEXT NOT NULL,
    scope_node_id        TEXT NOT NULL,
    claimed_owner_dept_id TEXT NOT NULL DEFAULT '',
    legacy_binding_id    TEXT NOT NULL DEFAULT '',
    rows_quarantined     INTEGER NOT NULL DEFAULT 0,
    quarantined_at       TEXT NOT NULL,
    resolved_at          TEXT NOT NULL DEFAULT '',
    resolved_by          TEXT NOT NULL DEFAULT '',
    resolved_binding_id  TEXT NOT NULL DEFAULT ''
)"""

#: 새 계약이 요구하는 열. 하나라도 없으면 그 표는 `8ca029634` 형식(자기진술 판)이다.
_REQUIRED_COLUMNS = ("approval_event_id", "revocation_event_id", "evidence_ref")


def _columns(conn: Any, table: str) -> set:
    try:
        return {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error as e:
        raise OwnershipUnavailable(f"스키마를 읽지 못했습니다({table}): {e}")


def migrate(conn: Any) -> Dict[str, Any]:
    """★★★ [4.1c-B P0-2] **옛 스키마를 안전하게 처리한다. 자동 승격은 없다.**

    `CREATE TABLE IF NOT EXISTS` 는 **이미 있는 표에 새 열을 넣어 주지 않는다.** 그래서
    `8ca029634` 형식의 `dataset_ownership_bindings` 가 이미 있는 DB 에서는 첫 `declare()`
    가 `no such column: approval_event_id` 로 죽는다 — 앞 판은 `object_scope_index` 의 두
    열만 확인했고, 정본 표 자체의 마이그레이션은 없었다.

    ⚠️⚠️ **옛 행을 승인된 것으로 백필하지 않는다.** 그 행들은 승인 원장 사건이 없는
      「승인됐다고 스스로 적은 결속」이다. 가짜 승인 사건을 만들어 승격시키면, 이 작업
      전체가 지우려 한 자기진술을 **원장에 박아 넣는** 셈이 된다 — 그리고 원장은 되돌릴
      곳이 없다.

    처리 규칙:
      · 표가 없다 → 아무것도 하지 않는다(DDL 이 만든다).
      · 새 열이 다 있다 → 아무것도 하지 않는다(멱등).
      · 새 열이 없고 **행 0건** → 안전하게 버리고 재구성한다(잃을 것이 없다).
      · 새 열이 없고 **행이 있다** → `LEGACY_TABLE` 로 격리한다. 해석 경로는 새 표만
        보므로 그 결속들은 **전부 비노출**(UNBOUND)이 된다 — fail-closed 다.

    ⚠️ 격리 시 **옛 색인·트리거를 함께 지운다.** SQLite 의 `ALTER TABLE RENAME` 은 색인을
      옛 표에 그대로 남기고 이름도 유지한다. 그러면 새 표에 `CREATE ... IF NOT EXISTS` 로
      같은 이름을 만들려 할 때 **조용히 건너뛰어져 새 표에 통제가 생기지 않는다.**
      실패도 아니고 경고도 없다 — 가장 위험한 모양이다."""
    cols = _columns(conn, "dataset_ownership_bindings")
    if not cols:
        return {"action": "none", "reason": "표 없음"}
    missing = [c for c in _REQUIRED_COLUMNS if c not in cols]
    if not missing:
        return {"action": "none", "reason": "이미 새 스키마"}
    n = int(conn.execute(
        "SELECT COUNT(*) FROM dataset_ownership_bindings").fetchone()[0])
    _drop_attached(conn, "dataset_ownership_bindings")
    if n == 0:
        conn.execute("DROP TABLE dataset_ownership_bindings")
        print("ℹ️ [ownership] 빈 구버전 소유권 표를 재구성했습니다"
              f"(없던 열: {missing}).")
        return {"action": "rebuilt", "rows": 0, "missing": missing}
    if _columns(conn, LEGACY_TABLE):
        #: ⚠️ 이미 격리본이 있다 — 두 세대의 옛 자료가 겹친다. 사람이 봐야 한다.
        raise OwnershipIntegrityError(
            f"격리 표({LEGACY_TABLE})가 이미 있습니다 — 구버전 결속이 두 세대 남아 "
            f"있습니다. 자동으로 합치지 않습니다.")
    conn.execute(_QUARANTINE_DDL)
    #: ★ 계약키·범위 단위로 남긴다 — 운영자가 「무엇을 다시 승인해야 하는가」를 알아야 한다.
    for r in conn.execute(
            "SELECT tenant_id, entity_mode, dataset_contract_key, scope_node_id,"
            " owner_dept_id, binding_id FROM dataset_ownership_bindings"
            " WHERE status = ?", (ACTIVE,)).fetchall():
        conn.execute(
            f"INSERT OR IGNORE INTO {QUARANTINE_TABLE} (quarantine_id, tenant_id,"
            f" entity_mode, dataset_contract_key, scope_node_id, claimed_owner_dept_id,"
            f" legacy_binding_id, rows_quarantined, quarantined_at)"
            f" VALUES (?,?,?,?,?,?,?,?,?)",
            (f"q_{uuid.uuid4().hex[:12]}", r[0], r[1], r[2], r[3], r[4], r[5], 1, _now()))
    conn.execute(f"ALTER TABLE dataset_ownership_bindings RENAME TO {LEGACY_TABLE}")
    print(f"⚠️ [ownership] 승인 근거 없는 구버전 결속 {n}건을 격리했습니다"
          f"({LEGACY_TABLE}). **자동 승격하지 않습니다** — 다시 쓰려면 승인 원장 사건을 "
          f"남기고 새로 등록해야 합니다. 그때까지 해당 데이터셋은 소유자 없음(UNBOUND)입니다.")
    return {"action": "quarantined", "rows": n, "missing": missing,
            "legacy_table": LEGACY_TABLE}


def _drop_attached(conn: Any, table: str) -> None:
    """이 표에 붙은 **색인·트리거를 지운다.** 이름이 새 표와 겹치기 때문이다."""
    rows = conn.execute(
        "SELECT type, name FROM sqlite_master WHERE tbl_name=? "
        "AND type IN ('index','trigger') AND name NOT LIKE 'sqlite_%'", (table,)).fetchall()
    for r in rows:
        conn.execute(f"DROP {str(r[0]).upper()} IF EXISTS {r[1]}")


def quarantine_state(conn: Any) -> Dict[str, Any]:
    """**미해결 격리 현황.** 준비도와 관리자 화면이 읽는다.

    ⚠️ 「소유자 없음」과 「승인 근거 없이 격리됨」은 다른 사실이다. 앞은 아직 정하지 않은
      것이고, 뒤는 **한 번 정했다고 적혀 있었으나 근거가 없는** 것이다. 뭉개면 운영자가
      무엇을 다시 승인해야 하는지 알 수 없다."""
    try:
        rows = conn.execute(
            f"SELECT tenant_id, entity_mode, dataset_contract_key, scope_node_id,"
            f" claimed_owner_dept_id, quarantined_at FROM {QUARANTINE_TABLE}"
            f" WHERE resolved_at = '' ORDER BY dataset_contract_key").fetchall()
    except sqlite3.Error:
        #: 표가 없다 = 격리된 적이 없다. 이것은 장애가 아니다.
        return {"unresolved": 0, "by_contract_key": {}, "items": []}
    items = [{"tenant_id": r[0], "entity_mode": r[1], "dataset_contract_key": r[2],
              "scope_node_id": r[3], "claimed_owner_dept_id": r[4],
              "quarantined_at": r[5]} for r in rows]
    by_key: Dict[str, int] = {}
    for it in items:
        k = str(it["dataset_contract_key"])
        by_key[k] = by_key.get(k, 0) + 1
    return {"unresolved": len(items), "by_contract_key": by_key, "items": items}


def _resolve_quarantine(conn: Any, *, tenant_id: str, entity_mode: str,
                        dataset_contract_key: str, scope_node_id: str,
                        binding_id: str, actor: str) -> int:
    """이 키·범위의 격리를 **재승인 완료로** 해제한다. `declare()` 가 성공할 때만 부른다.

    ★ 해제 조건을 「관리자가 확인했다」로 두지 않는다 — 그러면 다시 자기진술이다.
      **승인된 결속이 실제로 생겼다**는 사실만이 해제 근거다."""
    try:
        cur = conn.execute(
            f"UPDATE {QUARANTINE_TABLE} SET resolved_at=?, resolved_by=?,"
            f" resolved_binding_id=? WHERE resolved_at='' AND tenant_id=? AND"
            f" entity_mode=? AND dataset_contract_key=? AND scope_node_id=?",
            (_now(), actor, binding_id, tenant_id, entity_mode, dataset_contract_key,
             scope_node_id))
        return int(cur.rowcount or 0)
    except sqlite3.Error:
        return 0                      # 표가 없다 = 격리된 적이 없다


def legacy_unapproved(conn: Any) -> Dict[str, Any]:
    """격리된 구버전 결속 현황. **준비도 보고가 읽는다** — 조용히 사라지면 안 된다.

    ⚠️ 「소유자 없음」과 「승인 근거 없이 격리됨」은 다른 사실이다. 앞은 아직 정하지 않은
      것이고, 뒤는 **한 번 정했다고 적혀 있었으나 근거가 없는** 것이다. 뭉개면 운영자가
      무엇을 다시 승인해야 하는지 알 수 없다."""
    if not _columns(conn, LEGACY_TABLE):
        return {"quarantined": 0, "keys": []}
    rows = conn.execute(
        f"SELECT DISTINCT tenant_id, entity_mode, dataset_contract_key, scope_node_id, "
        f"owner_dept_id FROM {LEGACY_TABLE}").fetchall()
    n = int(conn.execute(f"SELECT COUNT(*) FROM {LEGACY_TABLE}").fetchone()[0])
    return {"quarantined": n,
            "keys": [{"tenant_id": r[0], "entity_mode": r[1],
                      "dataset_contract_key": r[2], "scope_node_id": r[3],
                      "claimed_owner_dept_id": r[4]} for r in rows]}


def _require_ledger_approval(event_id: str, *, fingerprint: str) -> Dict[str, Any]:
    """승인 원장 사건이 **실재하고 이 결속을 가리키는가.** 아니면 무결성 오류.

    ⚠️ 사건 id 를 문자열로만 받아 적어 두면 그것도 자기진술이다 — 원장에서 **찾아서**
      유형·주체·대상 지문까지 대조한다.

    ★★★ [재감사 보정] `list_events()` 를 쓰지 않는다. 그 함수는
      ① `LIMIT` 이 있어 뒤에 사건이 쌓이면 원 승인이 조회 범위 밖으로 밀려나고,
      ② **판독 실패를 빈 배열로 접는다** — 그러면 원장 장애가 「승인 없음」이 되어
        장애 순간에 모든 결속이 조용히 무효가 된다(반대 방향 fail-open 도 같은 뿌리다).
      그래서 **id 로 직접** 묻고 실패는 던지는 `get_event_strict` 를 쓴다."""
    eid = str(event_id or "").strip()
    if not eid:
        raise OwnershipError(
            "승인 원장 사건 id 가 없습니다 — 「승인됐다고 스스로 적은 결속」은 만들 수 없습니다.")
    from core.decision_ledger import DecisionLedgerError, decision_ledger
    try:
        row = decision_ledger.get_event_strict(eid)
    except DecisionLedgerError as e:
        #: ⚠️ 「못 읽었다」를 「승인이 없다」로 접지 않는다 — 점검이 필요한 상태다.
        raise OwnershipUnavailable(f"승인 원장을 읽지 못했습니다: {e}")
    if not row:
        raise OwnershipIntegrityError(
            f"승인 원장 사건({eid})이 없습니다 — 승인 없는 결속은 만들지 않습니다.")
    #: ★ 유형·주체까지 본다. 그러지 않으면 **아무 사건 id** 하나로 승인을 주장할 수 있고,
    #:   그것이 직전에 지운 `calc_binding` 자기진술과 같은 유형의 구멍이다.
    if str(row.get("event_type", "")) != EVENT_APPROVED             or str(row.get("subject_type", "")) != SUBJECT_TYPE:
        raise OwnershipIntegrityError(
            f"사건({eid})은 데이터셋 소유 승인이 아닙니다"
            f"({row.get('event_type')}/{row.get('subject_type')}).")
    #: ★★ 대상 지문이 다르면 **다른 결속의 승인**이다. 부서까지 지문에 들어 있으므로
    #:   A부서 승인으로 B부서 결속을 세우는 길이 여기서 막힌다.
    if str(row.get("subject_id", "")) != fingerprint:
        raise OwnershipIntegrityError(
            f"승인 사건({eid})은 이 결속(지문 {fingerprint[:12]}…)을 가리키지 않습니다 "
            f"— 다른 결속의 승인을 빌려 쓸 수 없습니다.")
    return row


def _revocation_children(event_id: str) -> Tuple[bool, bool]:
    """이 승인 사건에 **철회 자식 사건**이 붙었는가. 돌려주는 것: `(철회됨, 조회실패)`.

    ★ `has_invalidating_child` 는 제한 없이 인덱스로 묻고 실패를 던진다 — 철회가
      조회 범위 밖으로 밀려나 **원 승인이 되살아나는** 일이 없다."""
    from core.decision_ledger import decision_ledger
    try:
        return decision_ledger.has_invalidating_child(
            str(event_id or ""), (EVENT_REVOKED,)), False
    except Exception:
        #: ⚠️ 실패는 「철회 없음」이 아니다. 호출부가 503 으로 답한다.
        return False, True


def _require_active_user(actor_id: str) -> Dict[str, Any]:
    """행위자가 **실재하고 활성인 사용자**인가. 아니면 거부한다.

    ★ 이 조각은 **모든 소유권 사건**(승인·철회·취소)이 지난다. 임의 문자열이 행위자로
      들어오는 것을 여기서 막는다 — 그러지 않으면 `actor` 를 아는 사람이면 누구나
      「원 승인자 본인」을 자칭할 수 있고, 그것은 다시 자기진술이다.
    ⚠️ 조직 권한 강제(`ORG_ENFORCE`)가 꺼져 있어도 이 검사는 산다. 확정 결과가 아니라
      **사용자 정본**을 보기 때문이다 — 스위치 하나로 사라지지 않는다."""
    aid = str(actor_id or "").strip()
    try:
        from core.org_directory import org_directory
        bootstrap = bool(org_directory.is_bootstrap())
        user = org_directory.get_user(aid) if aid else None
    except Exception as e:
        raise OwnershipUnavailable(f"행위자를 확인하지 못했습니다: {e}")
    if bootstrap:
        raise OwnershipError(
            "조직 정본이 아직 없습니다(부서 또는 사용자 0건) — 데이터 소유 결속은 승인할 "
            "조직이 있어야 승인할 수 있습니다. 부트스트랩 예외는 첫 관리자 생성용이며 "
            "소유권 승인에는 적용되지 않습니다.")
    if not user:
        raise OwnershipError(
            f"{aid or '(빈 행위자)'} 는 조직 정본에 없는 사용자입니다 — 승인할 수 없습니다.")
    if str(user.get("status", "active")) != "active":
        raise OwnershipError(
            f"{aid} 는 폐지된 사용자입니다 — 폐지가 권한을 남겨 두면 그것은 폐지가 아닙니다.")
    return user


def _require_approval_authority(actor_id: str) -> None:
    """이 사람이 **데이터 표준을 승인할 수 있는가.** 아니면 거부한다.

    ★★★ [4.1c-B P0-1] 앞 판은 `scope.unrestricted or scope.can_manage_standard` 였다.
      그 조건은 **부트스트랩에서 미등록 사용자까지 통과시킨다.** 실측(격리 조직 DB):

          ① 조직 없음        bootstrap=True  unrestricted=True  can_manage_standard=True
          ② 부서만 있음      bootstrap=True  unrestricted=True  can_manage_standard=True
          ③ 미등록 행위자    bootstrap=False unrestricted=False can_manage_standard=False

      즉 `resolve_scope()` 는 **부트스트랩이면 두 값을 모두 True 로 준다** — 첫 관리자를
      만들 수 있게 하려는 접근정책 예외다. 부서 생존 검사에서 그 예외를 없애면서 승인
      생성 경로에는 같은 우회를 남겼다. 「같은 예외를 두 곳에서 지워야 한다」를 놓친 것이다.

    ★ 그래서 네 관문을 **순서대로** 통과해야 한다.
      ①② 조직 정본이 있고, 행위자가 실재·활성인가(`_require_active_user`).
      ③ **사용자 정본의 권한 플래그**를 직접 본다(`is_admin`/`is_data_admin`).
         조직 권한 강제가 꺼져 있으면 `resolve_scope` 는 등록 여부와 무관하게 전권을
         주므로, 확정 결과만 보면 스위치 하나로 검사가 사라진다.
      ④ 조직도의 **확정 결과**와 교차 확인한다(`can_manage_standard`만 — `unrestricted`
         는 보지 않는다). 정본과 확정 결과가 갈라지면 통과가 아니라 **점검**이다.

    ⚠️ 판독 실패를 «통과» 로 접지 않는다 — 승인은 모르면 막아야 하는 자리다."""
    aid = str(actor_id or "").strip()
    user = _require_active_user(aid)
    try:
        from core.org_directory import org_directory
        scope = org_directory.resolve_scope(aid)
    except Exception as e:
        raise OwnershipUnavailable(f"승인 권한을 확인하지 못했습니다: {e}")
    #: ③ 사용자 정본의 권한 플래그. `can_manage_standard` 의 근거와 같은 값이다.
    if not (bool(user.get("is_admin")) or bool(user.get("is_data_admin"))):
        raise OwnershipError(
            f"{aid} 에게는 데이터 소유 결속을 승인할 권한이 없습니다 "
            f"(기준정보·데이터 표준 승인 권한 필요).")
    #: ④ 확정 결과와 교차. ⚠️ `unrestricted` 는 **보지 않는다** — 그것이 우회 경로였다.
    if not getattr(scope, "can_manage_standard", False):
        raise OwnershipIntegrityError(
            f"{aid} 의 사용자 정본과 확정 권한이 어긋납니다"
            f"(정본은 승인권 있음, 확정 결과는 없음) — 임의로 고르지 않습니다.")


def approve(*, tenant_id: str, entity_mode: str, dataset_contract_key: str,
            scope_node_id: str, owner_dept_id: str, actor_id: str,
            evidence_ref: str, effective_from: str = "", effective_to: str = "",
            purpose: str = "") -> Dict[str, Any]:
    """**원장에 승인 사건을 남기고** 그 사건 id 를 돌려준다. `declare()` 의 선행 단계다.

    ★ 대상은 **결속 지문**이다 — 사건이 무엇을 승인했는지가 사건 자체에 박혀 있어야 한다.
    ★★ 행위자 **권한을 여기서 확인한다.** 원장 기록과 권한 확인을 나누면 「권한 없는 사람의
      승인 사건」이 이력에 남고, 그 이력은 나중에 승인의 근거로 읽힌다.

    ⚠️⚠️ [2차 보정] 이 문장은 한동안 **주석에만** 있었다. 코드는 `actor_id` 가 빈 문자열인지만
      봤고, `approve()` 를 부르는 API 경로도 없었다 — 즉 「관리자 경로에서 확인한다」는
      말에 해당하는 경로가 존재하지 않았다. 재감사에서 지적받은 `evidence_ref` 와 **같은
      유형**(문서가 코드를 대신 주장)이므로, 문장을 지우는 대신 검증을 넣었다."""
    if not str(actor_id or "").strip():
        raise OwnershipError("승인 행위자가 필요합니다.")
    _require_approval_authority(actor_id)
    if not str(evidence_ref or "").strip():
        raise OwnershipError(
            "근거(evidence_ref)가 필요합니다 — 「누가 왜 이 부서로 정했나」에 답할 수 없는 "
            "결속은 나중에 아무도 뒤집을 수 없습니다.")
    eff_from = str(effective_from or "").strip() or _now()
    fp = fingerprint_of(tenant_id, entity_mode, dataset_contract_key, scope_node_id,
                        owner_dept_id, eff_from, effective_to, actor_id, evidence_ref)
    try:
        from core.decision_ledger import decision_ledger
        ev = decision_ledger.append(
            event_type=EVENT_APPROVED, subject_type=SUBJECT_TYPE, subject_id=fp,
            actor_type="user", actor_id=actor_id, decision="APPROVED",
            rationale=purpose or f"{dataset_contract_key} 소유 부서 승인",
            #: ★★ [4.1c-B P1] 범위 정보는 **근거로** 남긴다. 아래 `enterprise_scope_id` 에
            #:   넣을 수 없기 때문이다(그 칸은 부서 id 규약이다).
            evidence_refs=[evidence_ref, f"scope_node:{scope_node_id}",
                           f"contract_key:{dataset_contract_key}"],
            tenant_id=tenant_id,
            #: ★★★ [4.1c-B P1] **부서 id 를 넣는다.** 원장 조회 API(`_filter_by_dept`)는
            #:   이 칸을 «부서 id» 로 해석한다(ECM-lite — E1 에서 노드로 승격 예정).
            #:   ⚠️ 앞 판은 ECM `scope_node_id` 를 넣었다. 그러면 그 값이 어느 부서의
            #:     읽기 집합에도 없으므로, **소유 부서 관리자의 원장 조회에서 이 승인이
            #:     사라진다** — 승인 이력이 보이지 않으면 감사도 이의도 불가능하다.
            #:     게다가 조용하다: 오류 없이 목록에서만 빠진다.
            enterprise_scope_id=owner_dept_id,
            entity_mode=entity_mode)
    except Exception as e:
        #: ⚠️ 원장 기록 실패를 삼키지 않는다 — 「승인 이력 없는 승인」이 생긴다.
        raise OwnershipUnavailable(f"승인 사건을 원장에 남기지 못했습니다: {e}")
    return {"approval_event_id": str(ev.get("event_id", "")), "fingerprint": fp,
            "effective_from": eff_from}


def abandon(approval_event_id: str, actor: str, reason: str = "") -> Dict[str, Any]:
    """**승인은 했으나 결속을 세우지 못했다**를 원장에 남긴다.

    ★★★ [4.1c-B P1] `approve()`(원장)와 `declare()`(정본 표)는 **다른 저장소의 두 단계**다.
      한 트랜잭션으로 묶을 수 없다. 그래서 등록이 실패하면 **승인 사건만 남는다.**

    ⚠️ 그 상태 자체는 안전하다(fail-closed) — 결속이 없으므로 아무 권한도 생기지 않고,
      `resolve()` 는 정본 표를 먼저 보므로 그 승인을 쓰지 않는다. 위험한 것은 **이력의
      오독**이다: 원장만 읽는 감사자에게는 「승인됨」으로 보인다.

    ★ 그래서 철회와 **같은 사건 유형**을 쓴다(부모 = 그 승인). 새 유형을 만들지 않는 이유:
      ① 원장의 부모·대상 검증을 그대로 재사용한다 ② `resolve()` 의 철회 자식 검사가
      **자동으로** 그 승인을 죽인다 — 통제를 두 벌로 만들지 않는다.

    ⚠️ 호출부가 이것을 부르지 않아도 권한은 새지 않는다. 다만 `dangling_approvals()` 에
      남으므로, 보고에서 「승인했는데 물질화되지 않은」 건으로 드러난다."""
    if not str(approval_event_id or "").strip():
        raise OwnershipError("취소할 승인 사건 id 가 필요합니다.")
    if not str(actor or "").strip():
        raise OwnershipError("취소에도 행위자가 필요합니다.")
    #: ★★★ [4.1c-C P0-2] 앞 판은 **행위자가 비어 있는지만** 봤다. 그래서 승인 사건 id 를
    #:   아는 임의 호출자가 정상 승인을 「등록 실패」로 취소할 수 있었다 — `revoke()` 에는
    #:   권한 검증을 넣었는데 여기에는 넣지 않았다. **같은 결과를 내는 두 경로 중 하나만
    #:   막은** 것이고, 이 파일에서 같은 유형을 이미 세 번 고쳤다.
    #: ★ 취소 사유도 필수다. 「등록 실패」는 사실이 아닐 수 있고, 사유가 없으면 그것을
    #:   확인할 방법이 없다.
    if not str(reason or "").strip():
        raise OwnershipError(
            "취소 사유가 필요합니다 — 「왜 취소했는가」가 없으면 정상 승인을 취소한 것과 "
            "등록 실패를 되돌린 것을 구분할 수 없습니다.")
    from core.decision_ledger import decision_ledger
    ap = _require_ledger_approval_raw(approval_event_id)
    #: ★★ 실재·활성 사용자는 **언제나** 요구한다. 「원 승인자 본인」을 문자열 일치만으로
    #:   인정하면, 그 문자열을 아는 사람이면 누구나 본인을 자칭할 수 있다 — 다시 자기진술이다.
    _require_active_user(actor)
    #: ★★★ 남의 승인을 취소하려면 **현재** 승인 권한자여야 한다. 본인 승인이면 권한이
    #:   사라진 뒤에도 되돌릴 수 있게 둔다 — 자기 것을 내리는 것은 권한 축소 방향이고,
    #:   막으면 잘못 승인한 사람이 스스로 정리할 길이 없어진다.
    if str(ap.get("actor_id", "")) != str(actor):
        _require_approval_authority(actor)
    try:
        ev = decision_ledger.append(
            event_type=EVENT_REVOKED, subject_type=SUBJECT_TYPE,
            subject_id=str(ap.get("subject_id", "")), actor_type="user", actor_id=actor,
            decision="REVOKED",
            rationale=str(reason),
            parent_event_id=str(ap.get("event_id", "")),
            tenant_id=str(ap.get("tenant_id", "") or "tenant_default"),
            enterprise_scope_id=str(ap.get("enterprise_scope_id", "")),
            entity_mode=str(ap.get("entity_mode", "") or "REAL"))
    except Exception as e:
        raise OwnershipUnavailable(f"승인 취소 사건을 원장에 남기지 못했습니다: {e}")
    return {"revocation_event_id": str(ev.get("event_id", ""))}


def dangling_approvals(conn: Any) -> List[Dict[str, Any]]:
    """**결속이 없는 살아 있는 승인 사건.** 보고가 읽는다.

    ⚠️ 「승인했는데 아무것도 생기지 않은」 건이 조용히 쌓이면, 원장의 승인 건수와 실제
      소유 결속 수가 갈라진다 — 그리고 그 차이를 아무도 세지 않는다."""
    from core.decision_ledger import decision_ledger
    try:
        have = {str(r[0]) for r in conn.execute(
            "SELECT approval_event_id FROM dataset_ownership_bindings")}
    except sqlite3.Error as e:
        raise OwnershipUnavailable(f"소유권 정본을 읽지 못했습니다: {e}")
    #: ⚠️ `list_events` 는 `LIMIT` 이 있다. 한도에 닿으면 **조용히 잘린다** — 그러면 이
    #:   보고는 「미물질화 0건」이라고 말하면서 실제로는 세지 않은 것이 된다. 잘렸으면
    #:   잘렸다고 소리 내야 한다(이 저장소에서 「조용한 절단」으로 두 번 오독한 적이 있다).
    _LIMIT = 1000
    events = decision_ledger.list_events(event_type=EVENT_APPROVED, limit=_LIMIT)
    if len(events) >= _LIMIT:
        print(f"⚠️ [ownership] 승인 사건이 조회 한도({_LIMIT})에 닿았습니다 — 미물질화 "
              f"보고가 일부만 셌을 수 있습니다. 한도를 넘겨 세려면 원장 쪽 페이지네이션이 "
              f"필요합니다.")
    out = []
    for ev in events:
        eid = str(ev.get("event_id", ""))
        if eid in have:
            continue
        revoked, failed = _revocation_children(eid)
        #: ★★★ [4.1c-C P1-2] **판독 실패를 「해당 없음」으로 접지 않는다.**
        #:
        #: ⚠️ 앞 판은 `if revoked or failed: continue` 였다. 그러면 원장 장애 중에는 모든
        #:   승인이 목록에서 빠지고, 보고가 **「미물질화 0건」** 이라고 말한다 — 아무 문제도
        #:   없다는 뜻으로 읽힌다. 이 파일에서 세 번 고친 「모르는 것을 없는 것으로 접는」
        #:   결함과 같다. 보고는 «세지 못했다» 를 말할 수 있어야 한다.
        if failed:
            raise OwnershipUnavailable(
                f"승인({eid})의 철회 여부를 읽지 못해 미물질화 승인을 셀 수 없습니다 — "
                f"「0건」으로 답하지 않습니다.")
        if revoked:
            continue                      # 취소됐다 — 「승인 대기」가 아니다
        out.append({"approval_event_id": eid, "subject_id": ev.get("subject_id", ""),
                    "actor_id": ev.get("actor_id", ""), "at": ev.get("created_at", "")})
    return out


def _require_ledger_approval_raw(event_id: str) -> Dict[str, Any]:
    """지문 대조 없이 **유형·주체만** 확인한다(`abandon` 전용 — 지문은 사건에서 읽는다)."""
    from core.decision_ledger import DecisionLedgerError, decision_ledger
    try:
        row = decision_ledger.get_event_strict(str(event_id).strip())
    except DecisionLedgerError as e:
        raise OwnershipUnavailable(f"승인 원장을 읽지 못했습니다: {e}")
    if not row:
        raise OwnershipIntegrityError(f"승인 원장 사건({event_id})이 없습니다.")
    if str(row.get("event_type", "")) != EVENT_APPROVED             or str(row.get("subject_type", "")) != SUBJECT_TYPE:
        raise OwnershipIntegrityError(
            f"사건({event_id})은 데이터셋 소유 승인이 아닙니다.")
    return row


def declare(conn: Any, *, tenant_id: str, entity_mode: str, dataset_contract_key: str,
            scope_node_id: str, owner_dept_id: str, approved_by: str,
            approval_event_id: str, evidence_ref: str,
            effective_from: str = "", effective_to: str = "") -> Dict[str, Any]:
    """승인된 결속을 정본에 등록한다.

    ⚠️⚠️ `approval_event_id` 와 `evidence_ref` 는 **필수**다. 첫 판은 주석에 「필수」라 적고
      코드는 빈 값을 허용했다 — 주석이 코드와 다르면 그 주석이 통제로 읽힌다.
    ★ **같은 지문의 재적용은 멱등이다.** 시드·마이그레이션을 두 번 돌려도 중첩이 되지 않는다.
    ⚠️ 같은 키·겹치는 기간의 다른 ACTIVE 결속은 **무결성 오류**다. 하나를 골라 덮어쓰지
      않는다 — 그 선택은 근거가 없고, 덮어쓴 쪽은 아무 기록도 남지 않는다.
    ⚠️ **여기서 DDL 을 돌리지 않는다**(위 `ensure_schema` 주석)."""
    for name, val in (("tenant_id", tenant_id), ("entity_mode", entity_mode),
                      ("dataset_contract_key", dataset_contract_key),
                      ("scope_node_id", scope_node_id), ("owner_dept_id", owner_dept_id),
                      ("approved_by", approved_by), ("evidence_ref", evidence_ref)):
        if not str(val or "").strip():
            raise OwnershipError(
                f"{name} 은 필수입니다 — 소유권 결속은 추측으로 만들 수 없습니다.")
    eff_from = str(effective_from or "").strip() or _now()
    eff_to = str(effective_to or "").strip()
    #: ★ 끝점이 배타적이므로 `from == to` 는 **한 순간도 유효하지 않은** 결속이다.
    #:   그런 것을 허용하면 「승인은 했는데 아무 때도 소유자가 없는」 상태가 조용히 생긴다.
    if eff_to and _end_utc(eff_to) <= _utc(eff_from, field="effective_from"):
        raise OwnershipError(
            f"유효기간이 뒤집혀 있거나 비어 있습니다({eff_from} → {eff_to}) "
            f"— 끝점은 배타적입니다.")

    #: ★★★ [재감사 P1-2 두번째 절반] **저장하는 값 자체를 UTC 로 정규화한다.**
    #:
    #: ⚠️ 표기 그대로 넣어 두면 DB 의 유일 색인이 `2026-06-01T00:00:00+00:00` 과
    #:   `2026-06-01T09:00:00+09:00` 을 **다른 값**으로 보고, 같은 순간의 동시 삽입을
    #:   막지 못한다. 응용 계층 비교만 UTC 로 고치면 제약은 여전히 문자열을 본다 —
    #:   즉 「경합만 남기고 검사한 척」이 된다.
    #: ★ 지문도 UTC 로 만들므로, 정규화하면 표에 적힌 값과 지문의 근거가 같아진다.
    eff_from = _utc(eff_from, field="effective_from").isoformat()
    eff_to = _utc(eff_to, field="effective_to").isoformat() if eff_to else ""

    fp = fingerprint_of(tenant_id, entity_mode, dataset_contract_key, scope_node_id,
                        owner_dept_id, eff_from, eff_to, approved_by, evidence_ref)
    #: ★★★ 원장에서 **찾아서** 대조한다. 문자열로 받은 id 를 그대로 믿으면 자기진술이다.
    _require_ledger_approval(approval_event_id, fingerprint=fp)
    #: ★★★ [4.1c-B 자체 발견] **이미 철회·취소된 승인으로는 등록할 수 없다.**
    #:
    #: ⚠️ 앞 판은 `resolve()` 에서만 철회 자식을 봤다. 그래서 취소된 승인으로 등록이
    #:   **성공했고**, 표에는 ACTIVE 행이 남았다. 해석은 막히지만
    #:     ① 호출부에는 「등록됐다」고 답한다(거짓)
    #:     ② 그 행이 기간 중첩 자리를 차지해 **정상 승인을 막는다**
    #:     ③ 목록·보고에서는 「승인된 결속」으로 보인다
    #:   즉 조용한 상태 불일치를 만든다.
    _revoked, _failed = _revocation_children(approval_event_id)
    if _failed:
        raise OwnershipUnavailable(
            "승인 철회 여부를 확인하지 못했습니다 — 확인할 수 없는 승인으로 결속을 "
            "세우지 않습니다.")
    if _revoked:
        raise OwnershipError(
            f"승인 사건({approval_event_id})은 이미 철회·취소됐습니다 — 다시 승인해야 합니다.")

    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM dataset_ownership_bindings WHERE tenant_id=? AND entity_mode=? "
        "AND dataset_contract_key=? AND scope_node_id=? AND status=?",
        (tenant_id, entity_mode, dataset_contract_key, scope_node_id, ACTIVE))]
    for r in rows:
        if r["fingerprint"] == fp:
            return r                            # 멱등 — 같은 결속을 다시 적었다
        if _overlaps(eff_from, eff_to, r["effective_from"], r["effective_to"]):
            raise OwnershipIntegrityError(
                f"같은 키에 유효기간이 겹치는 ACTIVE 결속이 이미 있습니다"
                f"(기존 {r['binding_id']}: {r['owner_dept_id']} "
                f"{r['effective_from']}~{r['effective_to'] or '무기한'}). "
                f"하나를 임의로 고르지 않습니다 — 기존 결속을 먼저 철회하십시오.")

    now = _now()
    bid = f"own_{uuid.uuid4().hex[:12]}"
    try:
        conn.execute(
            "INSERT INTO dataset_ownership_bindings (binding_id, tenant_id, entity_mode,"
            "dataset_contract_key, scope_node_id, owner_dept_id, effective_from,"
            "effective_to, status, approved_by, approved_at, approval_event_id,"
            "evidence_ref, fingerprint, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (bid, tenant_id, entity_mode, dataset_contract_key, scope_node_id,
             owner_dept_id, eff_from, eff_to, ACTIVE, approved_by, now,
             str(approval_event_id), evidence_ref, fp, now, now))
    except sqlite3.IntegrityError as e:
        #: DB 제약이 막은 것 — 조회와 삽입 사이에 남이 넣었다(다중 프로세스).
        raise OwnershipIntegrityError(
            f"같은 키·같은 시작시각의 ACTIVE 결속이 이미 있습니다: {e}")
    #: ★★ 재승인이 끝났으므로 격리를 해제한다. 「승인된 결속이 생겼다」는 사실만이 근거다.
    _resolve_quarantine(conn, tenant_id=tenant_id, entity_mode=entity_mode,
                        dataset_contract_key=dataset_contract_key,
                        scope_node_id=scope_node_id, binding_id=bid, actor=approved_by)
    return {"binding_id": bid, "fingerprint": fp, "owner_dept_id": owner_dept_id,
            "status": ACTIVE, "effective_from": eff_from, "effective_to": eff_to,
            "approval_event_id": str(approval_event_id),
            "tenant_id": tenant_id, "entity_mode": entity_mode,
            "dataset_contract_key": dataset_contract_key, "scope_node_id": scope_node_id}


def revoke(conn: Any, binding_id: str, actor: str, reason: str = "") -> bool:
    """승인을 철회한다. **원장에 철회 사건을 승인 사건의 자식으로 남긴다.**

    ⚠️ 첫 판은 직접 `UPDATE` 만 했다. 그러면 「누가 언제 왜 내렸는가」가 정본 표의 한 칸으로만
      남고, 원장에는 승인만 남아 **여전히 승인된 것처럼** 읽힌다.
    ★ 행을 지우지 않는다 — 무엇이 있었는지는 남아야 한다.

    ★★★ [4.1c-B P0-4] **철회에도 승인과 같은 권한이 필요하다.** 앞 판은 `actor` 가 빈
      문자열인지만 봤다. 그러면 승인권이 없는 사람이 소유권을 내릴 수 있고, 그 순간
      그 데이터는 **아무에게도 안 보이게** 된다 — 승인보다 조용하고 되돌리기 어렵다
      (「안 보인다」는 아무도 신고하지 않는다).
    ★★ 사유도 필수다. 철회 이력의 값은 「누가」가 아니라 「왜」에 있다 — 사유 없는 철회는
      다음 사람이 되살려야 할지 판단할 수 없고, 그러면 아무도 손대지 않는다."""
    if not str(actor or "").strip():
        raise OwnershipError("철회에도 행위자가 필요합니다.")
    #: ⚠️ 승인과 **같은 함수**를 쓴다. 두 벌로 만들면 한쪽만 느슨해지는 날이 온다.
    _require_approval_authority(actor)
    if not str(reason or "").strip():
        raise OwnershipError(
            "철회 사유가 필요합니다 — 「왜 내렸는가」가 없으면 다음 사람이 되살려야 할지 "
            "판단할 수 없습니다.")
    row = conn.execute("SELECT * FROM dataset_ownership_bindings WHERE binding_id=? "
                       "AND status=?", (binding_id, ACTIVE)).fetchone()
    if row is None:
        return False
    r = dict(row)
    try:
        from core.decision_ledger import decision_ledger
        ev = decision_ledger.append(
            event_type=EVENT_REVOKED, subject_type=SUBJECT_TYPE,
            subject_id=r["fingerprint"], actor_type="user", actor_id=actor,
            decision="REVOKED", rationale=str(reason or "철회"),
            parent_event_id=r["approval_event_id"],
            #: ★ 승인과 **같은 규약**(부서 id). 다르게 넣으면 승인은 보이고 철회는 안 보이는
            #:   상태가 되고, 그것이 가장 위험한 이력이다 — 「아직 유효하다」로 읽힌다.
            tenant_id=r["tenant_id"], enterprise_scope_id=r["owner_dept_id"],
            evidence_refs=[f"scope_node:{r['scope_node_id']}",
                           f"contract_key:{r['dataset_contract_key']}"],
            entity_mode=r["entity_mode"])
    except Exception as e:
        raise OwnershipUnavailable(f"철회 사건을 원장에 남기지 못했습니다: {e}")
    now = _now()
    return conn.execute(
        "UPDATE dataset_ownership_bindings SET status=?, revoked_by=?, revoked_at=?, "
        "revoked_reason=?, revocation_event_id=?, updated_at=? "
        "WHERE binding_id=? AND status=?",
        (REVOKED, actor, now, str(reason or ""), str(ev.get("event_id", "")), now,
         binding_id, ACTIVE)).rowcount == 1


def _dept_alive(owner_dept_id: str) -> Tuple[bool, bool]:
    """부서가 **지금** 존재하고 살아 있는가. 돌려주는 것: `(살아있는가, 조회실패인가)`.

    ⚠️⚠️ [재감사 보정] 첫 판은 `org_directory.is_bootstrap()` 이면 **임의 부서를 살아 있다고**
      처리했다. `is_bootstrap` 은 **초기 관리자 생성을 위한 접근정책 예외**이고, 데이터
      소유권 정본 검증까지 면제하는 규칙이 아니다. 특히 FND-01 부서만 적재되고 사용자가
      아직 없는 상태에서 **모든 임의 부서가 통과**했다. 그 예외를 없앴다.
    ⚠️ 조회 실패를 «없다» 로도 «있다» 로도 뭉개지 않는다 — 호출부가 503 과 차단을 갈라야 한다."""
    try:
        from core.org_directory import org_directory
        getter = getattr(org_directory, "get_department", None)
        if getter is None:
            #: 없는 API 를 «통과» 로 읽지 않는다 — 조회 실패로 본다.
            return False, True
        d = getter(owner_dept_id)
        if not d:
            return False, False
        status = (d.get("status", "active") if isinstance(d, dict)
                  else getattr(d, "status", "active"))
        return str(status) == "active", False
    except Exception:
        return False, True


def resolve(conn: Any, *, tenant_id: str, entity_mode: str, dataset_contract_key: str,
            scope_node_id: str, as_of: str = "") -> Optional[Dict[str, Any]]:
    """**정본 해석.** 결속이 없으면 `None`(→ 호출부가 `RESOURCE_UNBOUND`).

    · 정확히 하나 → 그 결속
    · 둘 이상      → `OwnershipIntegrityError`(503) — 임의로 고르지 않는다
    · 승인 사건 없음·철회 자식 있음 → 각각 503 · `None`
    · 부서 미존재·폐지 → `OwnershipIntegrityError`(503)
    · 저장소·원장 장애 → `OwnershipUnavailable`(503)

    ⚠️ **여기서 DDL 을 돌리지 않는다.** 그러면 상위 트랜잭션이 조기 커밋된다."""
    at = str(as_of or "").strip() or _now()
    at_dt = _utc(at, field="as_of")
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM dataset_ownership_bindings WHERE tenant_id=? AND entity_mode=? "
            "AND dataset_contract_key=? AND scope_node_id=? AND status=?",
            (tenant_id, entity_mode, dataset_contract_key, scope_node_id, ACTIVE))]
    except (sqlite3.Error, OSError) as e:
        raise OwnershipUnavailable(f"소유권 정본을 읽지 못했습니다: {e}")

    #: ★ `_overlaps` 와 **같은 반열 규약** `[from, to)` 다. 두 곳의 부등호가 어긋나면
    #:   「등록은 됐는데 해석에서 둘 다 유효」 또는 「하나도 유효하지 않음」이 된다.
    live = [r for r in rows
            if _utc(r["effective_from"], field="effective_from") <= at_dt
            and at_dt < _end_utc(r["effective_to"])]
    if not live:
        return None
    if len(live) > 1:
        raise OwnershipIntegrityError(
            f"같은 키에 유효한 소유권 결속이 {len(live)}건입니다 "
            f"({[r['binding_id'] for r in live]}) — 임의로 고르지 않습니다.")
    r = live[0]

    #: ★★★ 요청마다 **승인 사건과 철회 자식 사건**을 다시 확인한다. 정본 표의 `status` 만
    #:   보면, 그 칸을 직접 고친 자료가 승인된 것처럼 통과한다.
    _require_ledger_approval(r["approval_event_id"], fingerprint=r["fingerprint"])
    revoked, failed = _revocation_children(r["approval_event_id"])
    if failed:
        raise OwnershipUnavailable(
            f"승인({r['approval_event_id']})의 철회 여부를 확인할 수 없습니다.")
    if revoked:
        #: 원장에는 철회가 있는데 표는 ACTIVE 다 — 표를 믿지 않고 **원장을 따른다.**
        return None

    ok, failed = _dept_alive(r["owner_dept_id"])
    if failed:
        raise OwnershipUnavailable(
            f"소유 부서({r['owner_dept_id']})가 지금 유효한지 확인할 수 없습니다.")
    if not ok:
        raise OwnershipIntegrityError(
            f"결속({r['binding_id']})이 가리키는 부서 «{r['owner_dept_id']}» 가 없거나 "
            f"폐지됐습니다 — 색인이 있어도 막습니다.")
    return r


def list_bindings(conn: Any, *, tenant_id: str = "", status: str = "") -> List[Dict[str, Any]]:
    """⚠️ DDL 을 돌리지 않는다 — 조회가 트랜잭션을 커밋하면 안 된다."""
    sql = "SELECT * FROM dataset_ownership_bindings WHERE 1=1"
    args: List[Any] = []
    if tenant_id:
        sql += " AND tenant_id=?"
        args.append(tenant_id)
    if status:
        sql += " AND status=?"
        args.append(status)
    return [dict(r) for r in conn.execute(sql + " ORDER BY created_at", args)]
