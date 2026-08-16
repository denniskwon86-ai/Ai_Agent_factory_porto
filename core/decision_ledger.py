"""Decision Ledger — 결정·가정·승인·근거의 **불변 이력** (마스터 명세서 §5.2 / M0 백로그 5).

## 왜 필요한가

제품의 차별점 첫 항목이 "**기업 의도와 결정의 보존** — 왜 이 앱·규칙·수치가 만들어졌는지 추적
가능해야 한다"(§1.3)다. 산출물만 남으면 6개월 뒤 "이 계획 수치가 왜 이렇게 됐나"에 답할 수 없다.
Ledger 는 그 답을 담는 곳이다.

## 설계 원칙 (§5.2)

1. **수정하지 않는다. 정정 이벤트로 보완한다.** 그래서 이 모듈에는 `update`/`delete` 가 **없다**.
   잘못 기록했으면 `parent_event_id` 로 정정 이벤트를 잇는다 — 틀린 기록도 "그때 그렇게
   판단했다"는 사실이므로 지우면 이력이 거짓이 된다.
2. **AI 의 추천과 사용자의 확정 결정을 구분한다.** `actor_type` 이 그 축이다.
3. **근거 없는 경영 수치는 '검증되지 않은 추정'으로 표시한다.** `evidence_refs` 가 비어 있으면
   `is_substantiated=False` 로 읽힌다 — 조회부가 근거 유무를 판단할 수 있어야 한다.

## 변조 탐지 (명세서에 없으나 추가)

"불변 이력"을 주장하려면 사후 변조를 알아챌 수단이 있어야 한다. 각 이벤트에
`prev_hash + 정규화된 payload` 의 SHA-256 을 `event_hash` 로 남겨 체인을 만든다.
⚠️ **한계를 정직하게 밝힌다**: 이것은 DB 파일을 직접 고치는 것을 *막지* 못한다. 체인을
재계산해 **불일치를 탐지**할 수 있을 뿐이다(중간 이벤트를 고치면 이후 전부 깨진다).
진짜 위조 방지는 외부 append-only 저장소나 서명이 필요하며 그건 이 단계의 범위가 아니다.

## 저장 위치

`data/decision_ledger.db` — `advisor.db` 에 두지 않는다. Ledger 는 Blueprint·프로젝트·릴리스·
시나리오·조직 문맥을 모두 참조하는 **전사 자산**인데 상담 DB 안에 있으면 상담 전용처럼 보인다
(ECM §6.2 는 조직 문맥 변경·프로필 변경·복제·권한부여·외부 연결·시나리오 실행도 대상으로 지정).
인프라 규약은 `master_data.py`·`advisor_store.py` 와 동일하다(멱등 DDL + WAL + 스레드 락).
"""
import hashlib
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from core.paths import data_path

_DB_PATH = data_path("decision_ledger.db")

# ── §5.2 필수 이벤트 유형 ─────────────────────────────────────────────────
#   명세서가 열거한 10종 + ECM §6.2 가 요구하는 문맥·복제·권한 이벤트.
#   ⚠️ 미등록 유형은 거부한다 — 오타로 만든 유형이 조용히 쌓이면 집계가 조각난다.
EVENT_TYPES = (
    # 명세서 §5.2
    "REQUIREMENT_CONFIRMED",
    "BLUEPRINT_APPROVED",
    "BLUEPRINT_REJECTED",          # 승인만 남기면 반려 사유가 사라진다(§5.2 정신상 필요)
    "DATA_REQUIREMENT_ACCEPTED",
    "MASTER_VALUE_CHANGED",
    "DATA_CONTRACT_PUBLISHED",
    "WBS_APPROVED",
    "RELEASE_ACCEPTED",
    "SCENARIO_EXECUTED",
    "SHADOW_MODE_PASSED",
    "PRODUCTION_WRITE_APPROVED",
    # ECM §6.2 — 조직 문맥 변경·프로필 변경·복제·권한부여·외부 연결
    "ENTERPRISE_CONTEXT_CHANGED",
    "ENTERPRISE_PROFILE_CHANGED",
    "ENTITY_CLONED",
    "PERMISSION_GRANTED",
    "EXTERNAL_CONNECTION_APPROVED",
    # 파이프라인 연결
    "PROJECT_BOOTSTRAPPED",
    # [CL-1~CL-3 · 2026-08-03] 앱 전달–의사결정–발간 폐쇄루프.
    #   ⚠️ 운영 상태(`data/collaboration.db`)와 별도로 여기에 남기는 이유: 운영 표는 상태를
    #     **덮어쓴다**(PENDING → ACCEPTED). 누가 언제 무엇을 수락했는지는 덮어쓸 수 없는 곳에
    #     있어야 하고, 그것이 이 원장이다. 상태만 있으면 "왜 이 사람이 이 앱을 쓰고 있나"에
    #     답할 수 없다.
    "APP_DELIVERY_CREATED",
    "APP_DELIVERY_ACCEPTED",
    "APP_DELIVERY_REJECTED",
    "APP_DELIVERY_REVOKED",
    "DECISION_CASE_CREATED",
    "DECISION_REVIEW_REQUESTED",
    "DECISION_MEETING_REQUESTED",
    "DECISION_RECORDED",
    "DECISION_ACTION_CREATED",
    "DECISION_EFFECT_MEASURED",
    "PUBLICATION_CREATED",
    "PUBLICATION_RENDERED",
    "PUBLICATION_REVIEW_REQUESTED",
    "PUBLICATION_APPROVED",
    "PUBLICATION_REJECTED",
    "PUBLICATION_PUBLISHED",
    # ★ 게시 **실패**도 원장에 남긴다. 실패를 남기지 않으면 "왜 이 보고서가 안 나갔나"에
    #   답할 수 없고, 다음 사람은 이미 나갔다고 믿는다(작업서 §5.1 "게시 실패를 성공으로
    #   저장 금지"의 원장 쪽 절반이다).
    "PUBLICATION_PUBLISH_FAILED",
    "PUBLICATION_CORRECTED",
    "PUBLICATION_WITHDRAWN",
    # [트랙 I · 2026-08-08] 생성 앱 데이터 평면.
    #   ⚠️ **레코드 1건마다 원장 1건을 쓰지 않는다.** 업무 앱은 레코드를 대량으로 만든다 —
    #     하루 수천 건이 들어오면 «왜 이 결정을 했는가» 의 이력이 데이터 로그에 파묻힌다.
    #     → 데이터셋의 **구조 변경**(생성·스키마·폐지)만 여기에 남기고, 레코드 단위 변경은
    #       `app_records` 자신의 `created_by`/`updated_by`/`deleted_by` 로 귀속을 남긴다.
    #     이 구분은 `tests/test_app_data_plane.py` 가 고정한다.
    "APP_DATASET_CREATED",
    "APP_DATASET_SCHEMA_CHANGED",
    "APP_DATASET_RETIRED",
    # [I-4 4단계 · 설계 §3·§13] App Runtime Contract 검토 게이트.
    #   ⚠️ **자동 통과는 여기에 남기지 않는다.** 지문이 바뀌지 않아 사람을 부르지 않은
    #     일까지 «승인» 으로 쌓으면, 원장에서 승인 건수를 세는 순간 실제보다 많아지고
    #     그 숫자가 「우리는 계약을 N번 검토했다」로 읽힌다.
    #   `subject_id` 는 **계약 지문**이다 — 프로젝트가 아니라 «어느 계약을 승인했는가»
    #     가 남아야 하고, 지문이 바뀌면 그것은 다른 계약이다.
    "APP_CONTRACT_REVIEW_REQUESTED",
    "APP_CONTRACT_APPROVED",
    "APP_CONTRACT_REJECTED",
    "CORRECTION",                  # 정정 전용 — 반드시 parent_event_id 를 가진다
)

ACTOR_TYPES = ("user", "agent", "system")
SUBJECT_TYPES = ("blueprint", "consultation", "project", "release", "scenario",
                 "master_record", "data_contract", "enterprise_entity", "permission",
                 "external_connection", "wbs_task",
                 # [CL-1~CL-3] 폐쇄루프 주체 — 전달·결정·발간은 릴리스나 프로젝트가 아니다.
                 #   같은 subject_type 으로 뭉개면 "이 릴리스에 무슨 일이 있었나"와 "이 전달이
                 #   어떻게 됐나"를 구분할 수 없다.
                 "app_delivery", "decision_case", "publication",
                 # [트랙 I] 생성 앱이 쌓는 업무 데이터의 그릇. 릴리스와 구분한다 —
                 #   «이 릴리스가 어떻게 됐나» 와 «이 앱의 데이터에 무슨 일이 있었나» 는
                 #   다른 질문이고, 뭉개면 둘 다 답할 수 없다.
                 "app_dataset",
                 # [I-4 4단계] 계약은 릴리스도 데이터셋도 아니다 — «이 릴리스가 어떻게
                 #   됐나» 와 «이 계약이 언제 어떤 지문으로 승인됐나» 는 다른 질문이다.
                 "app_contract")


class DecisionLedgerError(ValueError):
    """검증 실패 — 라우트가 4xx 로 바꾼다."""


_DDL = """
CREATE TABLE IF NOT EXISTS decision_ledger_events (
    event_id        TEXT PRIMARY KEY,
    seq             INTEGER NOT NULL,           -- 체인 순서(자기 증가)
    tenant_id       TEXT NOT NULL DEFAULT 'tenant_default',
    enterprise_scope_id TEXT DEFAULT '',
    entity_mode     TEXT NOT NULL DEFAULT 'REAL',
    project_id      TEXT DEFAULT '',
    blueprint_id    TEXT DEFAULT '',
    event_type      TEXT NOT NULL,
    subject_type    TEXT NOT NULL,
    subject_id      TEXT NOT NULL,
    actor_type      TEXT NOT NULL,              -- user | agent | system
    actor_id        TEXT DEFAULT '',
    decision        TEXT DEFAULT '',            -- 무엇을 결정했는가
    rationale       TEXT DEFAULT '',            -- 왜
    evidence_refs_json       TEXT DEFAULT '[]', -- 근거(데이터셋·버전·테스트 결과)
    input_version_refs_json  TEXT DEFAULT '[]',
    output_version_refs_json TEXT DEFAULT '[]',
    parent_event_id TEXT DEFAULT '',            -- 정정 대상
    prev_hash       TEXT DEFAULT '',
    event_hash      TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    UNIQUE (seq)
);
CREATE INDEX IF NOT EXISTS idx_ledger_subject ON decision_ledger_events(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_ledger_type ON decision_ledger_events(event_type, created_at);
CREATE INDEX IF NOT EXISTS idx_ledger_ctx ON decision_ledger_events(tenant_id, entity_mode);
CREATE INDEX IF NOT EXISTS idx_ledger_project ON decision_ledger_events(project_id);
CREATE INDEX IF NOT EXISTS idx_ledger_blueprint ON decision_ledger_events(blueprint_id);
"""

# 해시에 넣는 필드와 순서. ⚠️ 이 목록을 바꾸면 **기존 체인이 전부 깨진다**(재계산 값이 달라짐).
#   바꿔야 하면 버전을 올려 새 체인을 시작하고 기존 체인은 그대로 보존할 것.
_HASH_FIELDS = ("seq", "tenant_id", "enterprise_scope_id", "entity_mode", "project_id",
                "blueprint_id", "event_type", "subject_type", "subject_id", "actor_type",
                "actor_id", "decision", "rationale", "evidence_refs_json",
                "input_version_refs_json", "output_version_refs_json", "parent_event_id",
                "created_at")
_HASH_VERSION = "v1"


def _compute_hash(row: Dict[str, Any], prev_hash: str) -> str:
    """정규화된 payload + 이전 해시 → SHA-256. 필드 순서를 고정해 재현 가능하게 만든다."""
    payload = _HASH_VERSION + "|" + prev_hash + "|" + "|".join(
        str(row.get(k, "")) for k in _HASH_FIELDS)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class DecisionLedger:
    def __init__(self, db_path: Optional[str] = None):
        """⚠️⚠️ 기본 경로를 **호출 시점에** 해석하고, **파일은 아직 열지 않는다.**

        세 가지가 함께 있어야 격리가 성립한다(2026-08-17 실측 사고):

        ① 예전 시그니처는 `db_path: str = _DB_PATH` 였다. 파이썬은 기본 인자를
           **모듈을 읽을 때 한 번** 평가하므로, 나중에 `_DB_PATH` 를 임시 경로로
           바꿔도 굳어 버린 옛 값이 쓰인다.
        ② `db_path or _DB_PATH` 도 안 된다. **빈 문자열이 운영 원장으로 떨어진다** —
           경로 계산이 빈 값을 낸 바로 그때 운영 파일이 열린다. `None` 만 「지정하지
           않음」으로 인정한다. 빈 문자열은 **잘못된 값**이고, 잘못된 값의 올바른
           결말은 폴백이 아니라 실패다.
        ③ 예전에는 여기서 `_init_db()` 를 불렀다. 모듈 끝의 전역 싱글턴이 **import
           되는 순간** 운영 파일을 만들고 열었다 — autouse fixture 는 그보다 **늦다.**
           수집 단계에서 이미 늦은 것이다. 그래서 실제 사용 직전까지 미룬다."""
        self.db_path = _DB_PATH if db_path is None else db_path
        self._lock = threading.Lock()
        #: 어떤 경로로 스키마를 준비했는지. `db_path` 가 나중에 바뀌면(격리) 다시 준비한다.
        self._prepared_for: Optional[str] = None

    def _ready(self) -> None:
        """첫 사용 직전에 스키마를 준비한다. **`__init__` 에서 부르지 않는다.**

        ⚠️ import 시점에 파일을 만들면 「테스트가 시작되기 전에 이미 운영 파일을
          건드린 상태」가 된다. 그 뒤에 무엇을 격리해도 늦다."""
        if self._prepared_for != self.db_path:
            self._init_db()
            self._prepared_for = self.db_path

    # ── 인프라 (master_data.py 와 동일 규약) ──────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 5000")
        except Exception:
            pass
        return conn

    def _init_db(self):
        conn = self._connect()
        try:
            conn.executescript(_DDL)
            conn.commit()
        finally:
            conn.close()

    def _ensure_tables(self) -> bool:
        try:
            self._init_db()
            return True
        except Exception:
            return False

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── 기록 (append only — update/delete 는 의도적으로 없다) ──────────────
    def append(self, event_type: str, subject_type: str, subject_id: str,
               actor_type: str = "system", actor_id: str = "",
               decision: str = "", rationale: str = "",
               evidence_refs: Optional[List[Any]] = None,
               input_version_refs: Optional[List[Any]] = None,
               output_version_refs: Optional[List[Any]] = None,
               parent_event_id: str = "",
               tenant_id: str = "tenant_default", enterprise_scope_id: str = "",
               entity_mode: str = "REAL",
               project_id: str = "", blueprint_id: str = "") -> Dict[str, Any]:
        """이벤트 1건을 이력 끝에 붙인다.

        ⚠️ **기록 실패는 삼키지 않는다.** 텔레메트리는 부가 기능이라 실패를 삼켰지만, Ledger 는
          "왜 이 결정을 했는가"의 유일한 근거다. 조용히 누락되면 승인 이력이 없는 승인이 생긴다.
          호출부가 감사 실패를 인지하고 판단할 수 있도록 예외를 올린다."""
        self._ready()
        if event_type not in EVENT_TYPES:
            raise DecisionLedgerError(f"등록되지 않은 event_type 입니다: {event_type}")
        if subject_type not in SUBJECT_TYPES:
            raise DecisionLedgerError(f"등록되지 않은 subject_type 입니다: {subject_type}")
        if actor_type not in ACTOR_TYPES:
            raise DecisionLedgerError(f"actor_type 은 {ACTOR_TYPES} 중 하나여야 합니다.")
        if not subject_id:
            raise DecisionLedgerError("subject_id 는 필수입니다.")
        if event_type == "CORRECTION" and not parent_event_id:
            # 정정인데 대상이 없으면 무엇을 정정하는지 알 수 없다 — 이력이 거짓이 된다.
            raise DecisionLedgerError("CORRECTION 이벤트는 parent_event_id 가 필수입니다.")

        row = {
            "event_id": f"dle_{uuid.uuid4().hex[:14]}",
            "tenant_id": tenant_id or "tenant_default",
            "enterprise_scope_id": enterprise_scope_id or "",
            "entity_mode": entity_mode or "REAL",
            "project_id": project_id or "",
            "blueprint_id": blueprint_id or "",
            "event_type": event_type,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "actor_type": actor_type,
            "actor_id": actor_id or "",
            "decision": decision or "",
            "rationale": rationale or "",
            "evidence_refs_json": json.dumps(evidence_refs or [], ensure_ascii=False,
                                             sort_keys=True),
            "input_version_refs_json": json.dumps(input_version_refs or [], ensure_ascii=False,
                                                  sort_keys=True),
            "output_version_refs_json": json.dumps(output_version_refs or [], ensure_ascii=False,
                                                   sort_keys=True),
            "parent_event_id": parent_event_id or "",
            "created_at": self._now(),
        }
        # ⚠️ `db_path` 가 상대 경로라 **작업 디렉터리가 바뀌면 다른 파일을 가리킨다**(테스트가 tmp
        #   로 chdir 하는 경우, 서비스가 다른 cwd 로 기동되는 경우). 그 파일에는 테이블이 없어
        #   `no such table` 이 난다 — `org_directory._ensure_tables` 에서 실측된 것과 같은 문제다.
        #   한 번 스키마를 만들고 재시도한다. 그래도 실패하면 **예외를 올린다**(삼키지 않는다) —
        #   감사 기록 누락은 호출부가 알아야 한다.
        for attempt in (0, 1):
            try:
                with self._lock, self._connect() as conn:
                    if parent_event_id and not conn.execute(
                            "SELECT 1 FROM decision_ledger_events WHERE event_id=?",
                            (parent_event_id,)).fetchone():
                        raise DecisionLedgerError(
                            f"존재하지 않는 parent_event_id 입니다: {parent_event_id}")
                    last = conn.execute("SELECT seq, event_hash FROM decision_ledger_events "
                                        "ORDER BY seq DESC LIMIT 1").fetchone()
                    row["seq"] = (int(last["seq"]) + 1) if last else 1
                    row["prev_hash"] = last["event_hash"] if last else ""
                    row["event_hash"] = _compute_hash(row, row["prev_hash"])
                    cols = ", ".join(row.keys())
                    marks = ", ".join("?" for _ in row)
                    conn.execute(
                        f"INSERT INTO decision_ledger_events ({cols}) VALUES ({marks})",
                        tuple(row.values()))
                return self._to_public(row)
            except sqlite3.OperationalError:
                if attempt == 0 and self._ensure_tables():
                    continue
                raise
        raise DecisionLedgerError("감사 기록에 실패했습니다.")   # 도달 불가(방어)

    # ── 조회 ──────────────────────────────────────────────────────────────
    @staticmethod
    def _to_public(r: Dict[str, Any]) -> Dict[str, Any]:
        d = dict(r)
        for k in ("evidence_refs", "input_version_refs", "output_version_refs"):
            try:
                d[k] = json.loads(d.pop(f"{k}_json") or "[]")
            except Exception:
                d[k] = []
        # §5.2 — 근거가 없는 결정은 '검증되지 않은 추정'으로 읽혀야 한다. 조회부가 판단할 수
        #   있도록 파생 플래그를 준다(저장하지 않는다 — 규칙이므로 언제든 재계산 가능).
        d["is_substantiated"] = bool(d.get("evidence_refs"))
        return d

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        self._ready()
        for attempt in (0, 1):
            try:
                with self._connect() as conn:
                    r = conn.execute("SELECT * FROM decision_ledger_events WHERE event_id=?",
                                     (event_id,)).fetchone()
                return self._to_public(dict(r)) if r else None
            except sqlite3.OperationalError:
                if attempt == 0 and self._ensure_tables():
                    continue
                return None
            except Exception:
                return None
        return None

    def list_events(self, subject_type: str = "", subject_id: str = "",
                    event_type: str = "", project_id: str = "", blueprint_id: str = "",
                    tenant_id: str = "", entity_mode: str = "",
                    limit: int = 100) -> List[Dict[str, Any]]:
        self._ready()
        sql = "SELECT * FROM decision_ledger_events"
        where, params = [], []
        for col, val in (("subject_type", subject_type), ("subject_id", subject_id),
                         ("event_type", event_type), ("project_id", project_id),
                         ("blueprint_id", blueprint_id), ("tenant_id", tenant_id),
                         ("entity_mode", entity_mode)):
            if val:
                where.append(f"{col}=?")
                params.append(val)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY seq DESC LIMIT ?"
        params.append(max(1, min(int(limit or 100), 1000)))
        for attempt in (0, 1):
            try:
                with self._connect() as conn:
                    return [self._to_public(dict(r))
                            for r in conn.execute(sql, params).fetchall()]
            except sqlite3.OperationalError:
                if attempt == 0 and self._ensure_tables():
                    continue
                return []
        return []

    def subject_history(self, subject_type: str, subject_id: str) -> List[Dict[str, Any]]:
        self._ready()
        """한 대상의 결정 이력(오래된 것부터). "왜 이렇게 됐나"에 답하는 기본 조회."""
        rows = self.list_events(subject_type=subject_type, subject_id=subject_id, limit=1000)
        return sorted(rows, key=lambda r: r["seq"])

    # ── 변조 탐지 ─────────────────────────────────────────────────────────
    def verify_chain(self) -> Dict[str, Any]:
        self._ready()
        """해시 체인을 재계산해 불일치를 찾는다.

        ⚠️ **한계**: 이것은 DB 파일 직접 조작을 *막지* 못한다. 탐지만 한다. 중간 이벤트를 고치면
          그 이후 전부 불일치로 뜨므로 어디서부터 손댔는지는 알 수 있다. 진짜 위조 방지는 외부
          append-only 저장소나 서명이 필요하며 이 단계의 범위가 아니다."""
        try:
            with self._connect() as conn:
                rows = [dict(r) for r in conn.execute(
                    "SELECT * FROM decision_ledger_events ORDER BY seq").fetchall()]
        except Exception as e:
            return {"ok": False, "checked": 0, "broken": [], "error": str(e)}
        broken, prev = [], ""
        for r in rows:
            expected = _compute_hash(r, prev)
            if r["event_hash"] != expected or (r.get("prev_hash") or "") != prev:
                broken.append({"event_id": r["event_id"], "seq": r["seq"]})
            prev = r["event_hash"]      # 체인은 저장된 값으로 이어간다(이후 전부 깨져 보이게)
        return {"ok": not broken, "checked": len(rows), "broken": broken,
                "hash_version": _HASH_VERSION,
                "limitation": "직접 DB 조작을 막지는 못하며 불일치 탐지만 가능합니다."}


decision_ledger = DecisionLedger()
