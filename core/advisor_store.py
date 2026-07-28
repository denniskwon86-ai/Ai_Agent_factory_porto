"""상담 세션 · Solution Blueprint 저장소 — 마스터 명세서 §4.5 / M0 백로그 2.

여기가 **사용자 데이터**가 처음 들어오는 지점이다. 플레이북(저작 설정)은 파일이지만 상담과
Blueprint 는 사용자가 만든 것이므로 조회·필터·이력이 필요하고, 따라서 DB 다.

저장 방식은 `core/master_data.py`·`core/org_directory.py` 와 **같은 규약**을 따른다(§18-4 조사 결과):
표준 sqlite3(동기) + `IF NOT EXISTS` 멱등 DDL + WAL + busy_timeout + 스레드 락. API 라우터가
`asyncio.to_thread` 로 감싼다. 새 인프라를 들이지 않는 이유는 운영·백업·마이그레이션 경로를
하나로 유지하기 위해서다.

⚠️ 명세서 §4.5 의 `tenant_id` 는 **넣지 않는다.** 이 제품에 아직 테넌트 개념이 없고(§2.2 가
  "운영용 멀티테넌트"를 미구현으로 명시), 쓰지 않는 컬럼을 두면 다음 작업자가 멀티테넌시가
  있다고 오해한다. 대신 실제로 존재하는 `owner_dept_id`(Phase 1~5 부서 권한)를 쓴다.
  테넌트가 도입되면 그때 컬럼을 추가한다 — 멱등 DDL 이라 추가가 안전하다.
"""
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.advisor_blueprint import SolutionBlueprint
from core.enterprise_context import EnterpriseContext, build_context, isolation_filter

_DB_PATH = os.path.join("data", "advisor.db")

# 상담 범위 — §4.3 F-DA-01
CONSULTATION_SCOPES = ("enterprise", "department", "project", "data", "simulation")
CONSULTATION_STATUSES = ("open", "blueprint_drafted", "closed")
BLUEPRINT_STATUSES = ("draft", "approved", "rejected")

_DDL = """
CREATE TABLE IF NOT EXISTS consultations (
    consultation_id TEXT PRIMARY KEY,
    user_id         TEXT DEFAULT '',
    owner_dept_id   TEXT DEFAULT '',
    -- [ECM-lite] 문맥 3키. 설계서 최상단 선행 규칙이 상담사를 명시적 적용 대상으로 지목한다.
    tenant_id           TEXT NOT NULL DEFAULT 'tenant_default',
    enterprise_scope_id TEXT DEFAULT '',
    entity_mode         TEXT NOT NULL DEFAULT 'REAL',
    scope           TEXT NOT NULL DEFAULT 'department',
    playbook_id     TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'open',
    initial_prompt  TEXT DEFAULT '',
    summary         TEXT DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_consult_dept ON consultations(owner_dept_id, status);
CREATE INDEX IF NOT EXISTS idx_consult_ctx ON consultations(tenant_id, entity_mode);

CREATE TABLE IF NOT EXISTS consultation_turns (
    turn_id             TEXT PRIMARY KEY,
    consultation_id     TEXT NOT NULL REFERENCES consultations(consultation_id),
    turn_no             INTEGER NOT NULL,
    speaker             TEXT NOT NULL,              -- advisor | user
    message             TEXT DEFAULT '',
    question_id         TEXT DEFAULT '',
    question_type       TEXT DEFAULT '',            -- choice | free
    option_set_json     TEXT DEFAULT '[]',
    selected_values_json TEXT DEFAULT '[]',
    created_at          TEXT NOT NULL,
    UNIQUE (consultation_id, turn_no)
);
CREATE INDEX IF NOT EXISTS idx_turns_consult ON consultation_turns(consultation_id, turn_no);

CREATE TABLE IF NOT EXISTS solution_blueprints (
    blueprint_id    TEXT PRIMARY KEY,
    consultation_id TEXT DEFAULT '',
    owner_dept_id   TEXT DEFAULT '',
    owner_user_id   TEXT DEFAULT '',
    -- [ECM-lite] §10.2 "프로젝트는 반드시 enterprise_scope_id 와 entity_mode 를 소유한다".
    --   Blueprint 가 프로젝트를 부트스트랩(M0-d)하므로 여기서부터 실어 넘겨야 한다.
    tenant_id           TEXT NOT NULL DEFAULT 'tenant_default',
    enterprise_scope_id TEXT DEFAULT '',
    entity_mode         TEXT NOT NULL DEFAULT 'REAL',
    title           TEXT DEFAULT '',
    business_domain TEXT DEFAULT '',
    playbook_id     TEXT DEFAULT '',
    payload_json    TEXT NOT NULL,                  -- SolutionBlueprint 전체(스키마 진실원본)
    readiness_score REAL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'draft',
    approved_by     TEXT DEFAULT '',
    approved_at     TEXT DEFAULT '',
    version         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bp_dept ON solution_blueprints(owner_dept_id, status);
CREATE INDEX IF NOT EXISTS idx_bp_ctx ON solution_blueprints(tenant_id, entity_mode);
CREATE INDEX IF NOT EXISTS idx_bp_consult ON solution_blueprints(consultation_id);

-- 데이터 요구사항을 **행으로도** 둔다. payload_json 안에 이미 있지만, "어느 부서가 어떤 데이터를
-- 몇 건 못 갖췄나"를 부서·용어로 질의해야 하기 때문이다(§4.4 데이터 보드, M1 카탈로그 매칭).
-- JSON 안에 있는 것은 검색되지 않는다.
CREATE TABLE IF NOT EXISTS blueprint_data_requirements (
    id               TEXT PRIMARY KEY,
    blueprint_id     TEXT NOT NULL REFERENCES solution_blueprints(blueprint_id),
    req_key          TEXT NOT NULL,
    canonical_term   TEXT NOT NULL,
    requirement_type TEXT DEFAULT '',
    necessity        TEXT DEFAULT '',
    data_kind        TEXT DEFAULT '',
    owner_department TEXT DEFAULT '',
    readiness_status TEXT DEFAULT 'missing',
    UNIQUE (blueprint_id, req_key)
);
CREATE INDEX IF NOT EXISTS idx_bpreq_dept ON blueprint_data_requirements(owner_department, readiness_status);
CREATE INDEX IF NOT EXISTS idx_bpreq_term ON blueprint_data_requirements(canonical_term);
"""


# [ECM-lite] 기존 DB 파일에 더해야 하는 컬럼. `_migrate_columns` 가 멱등 적용한다.
#   NOT NULL 컬럼을 ALTER 로 추가하려면 기본값이 있어야 한다(SQLite 제약) — 셋 다 있다.
_COLUMN_MIGRATIONS = {
    "consultations": [
        ("tenant_id", "TEXT NOT NULL DEFAULT 'tenant_default'"),
        ("enterprise_scope_id", "TEXT DEFAULT ''"),
        ("entity_mode", "TEXT NOT NULL DEFAULT 'REAL'"),
    ],
    "solution_blueprints": [
        ("tenant_id", "TEXT NOT NULL DEFAULT 'tenant_default'"),
        ("enterprise_scope_id", "TEXT DEFAULT ''"),
        ("entity_mode", "TEXT NOT NULL DEFAULT 'REAL'"),
    ],
}


class AdvisorStoreError(ValueError):
    """검증 실패 등 호출자에게 4xx 로 전달할 도메인 오류."""


class AdvisorStore:
    def __init__(self, db_path: str = _DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    # ── 인프라 (master_data.py 와 동일 규약) ──────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 5000")
        except Exception:
            pass
        return conn

    def _init_db(self):
        conn = self._connect()
        try:
            # ⚠️ 순서가 중요하다: **컬럼 마이그레이션이 DDL 보다 먼저**여야 한다.
            #   `_DDL` 에는 신규 컬럼을 참조하는 인덱스(`idx_consult_ctx`)가 있어서, 구 스키마
            #   DB 를 열면 컬럼이 생기기 전에 인덱스 생성이 `no such column` 으로 죽는다.
            #   구 DB 로 실제 열어보고 잡았다 — 신규 환경에서만 테스트하면 놓친다.
            #   신규 DB 에서는 테이블이 없어 마이그레이션이 통과(no-op)하고 DDL 이 전부 만든다.
            self._migrate_columns(conn)
            conn.executescript(_DDL)
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _migrate_columns(conn: sqlite3.Connection) -> None:
        """이미 만들어진 테이블에 신규 컬럼을 멱등하게 더한다.

        ⚠️ `CREATE TABLE IF NOT EXISTS` 는 **기존 테이블에 컬럼을 추가하지 않는다.** DDL 만
          고치면 새 환경에서는 되고 기존 환경에서는 조용히 `no such column` 이 난다 —
          `master_data._DDL` 이 멱등 마이그레이션이라 안심하고 넘어가기 쉬운 함정이다.
          SQLite 는 `ADD COLUMN IF NOT EXISTS` 가 없으므로 `PRAGMA table_info` 로 확인한다."""
        for table, columns in _COLUMN_MIGRATIONS.items():
            try:
                have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            except sqlite3.OperationalError:
                continue                      # 테이블 자체가 없으면 DDL 이 만든다
            if not have:
                continue
            for name, decl in columns:
                if name not in have:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")

    def _ensure_tables(self) -> bool:
        """`org_directory._ensure_tables` 와 같은 복원력 규약 — 상대 경로 DB 라 작업 디렉터리가
        바뀌면 다른 파일을 가리킨다. 조회 경로에서 한 번 복구를 시도한다."""
        try:
            self._init_db()
            return True
        except Exception:
            return False

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _uid(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:12]}"

    # ── 상담 세션 ─────────────────────────────────────────────────────────
    def create_consultation(self, user_id: str = "", owner_dept_id: str = "",
                            scope: str = "department", playbook_id: str = "",
                            initial_prompt: str = "",
                            ctx: Optional[EnterpriseContext] = None) -> Dict[str, Any]:
        if scope not in CONSULTATION_SCOPES:
            raise AdvisorStoreError(f"scope 는 {CONSULTATION_SCOPES} 중 하나여야 합니다.")
        # 문맥이 없으면 기본 테넌트·실제 문맥으로 귀속(단계적 도입 — 스위처 도입 전 하위호환).
        ctx = ctx or build_context(fallback_scope_id=owner_dept_id)
        cid = self._uid("cons")
        now = self._now()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO consultations (consultation_id, user_id, owner_dept_id, "
                "tenant_id, enterprise_scope_id, entity_mode, scope, "
                "playbook_id, status, initial_prompt, summary, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,'open',?,'',?,?)",
                (cid, user_id or "", owner_dept_id or "",
                 ctx.tenant_id, ctx.enterprise_scope_id, ctx.entity_mode,
                 scope, playbook_id or "", initial_prompt or "", now, now))
        return self.get_consultation(cid)

    def get_consultation(self, consultation_id: str) -> Optional[Dict[str, Any]]:
        for attempt in (0, 1):
            try:
                with self._connect() as conn:
                    r = conn.execute("SELECT * FROM consultations WHERE consultation_id=?",
                                     (consultation_id,)).fetchone()
                return dict(r) if r else None
            except sqlite3.OperationalError:
                if attempt == 0 and self._ensure_tables():
                    continue
                return None
        return None

    def list_consultations(self, dept_ids: Optional[List[str]] = None,
                           user_id: str = "", limit: int = 50,
                           ctx: Optional[EnterpriseContext] = None) -> List[Dict[str, Any]]:
        """`dept_ids=None` 이면 부서 필터 없음(무제한 권한). 빈 리스트면 아무것도 안 보인다.

        `ctx` 가 주어지면 **문맥 격리**도 적용한다 — 다른 테넌트·다른 상태(가상/경쟁사)의
        상담이 목록에 섞이면 안 된다(설계서 수용 기준 5)."""
        sql = "SELECT * FROM consultations"
        params: List[Any] = []
        where = []
        for k, v in isolation_filter(ctx).items():
            where.append(f"{k}=?"); params.append(v)
        if dept_ids is not None:
            if not dept_ids:
                # 읽을 부서가 없으면 자기 것만(개인 상담은 부서 미지정일 수 있다)
                where.append("(owner_dept_id='' AND user_id=?)")
                params.append(user_id or "")
            else:
                marks = ",".join("?" for _ in dept_ids)
                where.append(f"(owner_dept_id IN ({marks}) OR (owner_dept_id='' AND user_id=?))")
                params.extend(list(dept_ids) + [user_id or ""])
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, min(int(limit or 50), 500)))
        for attempt in (0, 1):
            try:
                with self._connect() as conn:
                    return [dict(r) for r in conn.execute(sql, params).fetchall()]
            except sqlite3.OperationalError:
                if attempt == 0 and self._ensure_tables():
                    continue
                return []
        return []

    def update_consultation(self, consultation_id: str, status: str = "",
                            summary: Optional[str] = None,
                            playbook_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if status and status not in CONSULTATION_STATUSES:
            raise AdvisorStoreError(f"status 는 {CONSULTATION_STATUSES} 중 하나여야 합니다.")
        sets, params = ["updated_at=?"], [self._now()]
        if status:
            sets.append("status=?"); params.append(status)
        if summary is not None:
            sets.append("summary=?"); params.append(summary)
        if playbook_id is not None:
            sets.append("playbook_id=?"); params.append(playbook_id)
        params.append(consultation_id)
        with self._lock, self._connect() as conn:
            conn.execute(f"UPDATE consultations SET {', '.join(sets)} WHERE consultation_id=?",
                         params)
        return self.get_consultation(consultation_id)

    # ── 대화 턴 ───────────────────────────────────────────────────────────
    def add_turn(self, consultation_id: str, speaker: str, message: str = "",
                 question_id: str = "", question_type: str = "",
                 option_set: Optional[List[Dict[str, Any]]] = None,
                 selected_values: Optional[List[str]] = None) -> Dict[str, Any]:
        """턴을 append 한다. `turn_no` 는 **DB 가 정한다** — 클라이언트가 보내면 동시 요청에서
        어긋나고, 대화 순서는 사후에 고칠 수 없는 이력이다."""
        if speaker not in ("advisor", "user"):
            raise AdvisorStoreError("speaker 는 advisor|user 여야 합니다.")
        now = self._now()
        tid = self._uid("turn")
        with self._lock, self._connect() as conn:
            if not conn.execute("SELECT 1 FROM consultations WHERE consultation_id=?",
                                (consultation_id,)).fetchone():
                raise AdvisorStoreError("존재하지 않는 상담입니다.")
            nxt = conn.execute("SELECT COALESCE(MAX(turn_no), 0) + 1 FROM consultation_turns "
                               "WHERE consultation_id=?", (consultation_id,)).fetchone()[0]
            conn.execute(
                "INSERT INTO consultation_turns (turn_id, consultation_id, turn_no, speaker, "
                "message, question_id, question_type, option_set_json, selected_values_json, "
                "created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (tid, consultation_id, nxt, speaker, message or "", question_id or "",
                 question_type or "", json.dumps(option_set or [], ensure_ascii=False),
                 json.dumps(selected_values or [], ensure_ascii=False), now))
            conn.execute("UPDATE consultations SET updated_at=? WHERE consultation_id=?",
                         (now, consultation_id))
        return {"turn_id": tid, "turn_no": nxt}

    def list_turns(self, consultation_id: str) -> List[Dict[str, Any]]:
        for attempt in (0, 1):
            try:
                with self._connect() as conn:
                    rows = conn.execute(
                        "SELECT * FROM consultation_turns WHERE consultation_id=? "
                        "ORDER BY turn_no", (consultation_id,)).fetchall()
                out = []
                for r in rows:
                    d = dict(r)
                    d["option_set"] = json.loads(d.pop("option_set_json") or "[]")
                    d["selected_values"] = json.loads(d.pop("selected_values_json") or "[]")
                    out.append(d)
                return out
            except sqlite3.OperationalError:
                if attempt == 0 and self._ensure_tables():
                    continue
                return []
        return []

    def collected_answers(self, consultation_id: str) -> Dict[str, List[str]]:
        """지금까지의 사용자 선택을 {질문 id: [선택 식별자]} 로 모은다.

        같은 질문에 다시 답하면 **마지막 답이 이긴다** — 사용자가 생각을 바꾼 것이고, 이력은
        턴 테이블에 그대로 남아 있으므로 잃는 정보가 없다."""
        answers: Dict[str, List[str]] = {}
        for t in self.list_turns(consultation_id):
            if t["speaker"] == "user" and t["question_id"] and t["selected_values"]:
                answers[t["question_id"]] = [str(v) for v in t["selected_values"]]
        return answers

    def collected_free_text(self, consultation_id: str) -> Dict[str, str]:
        """질문별 자유 입력(선택 없이 글로만 답한 것 포함)."""
        out: Dict[str, str] = {}
        for t in self.list_turns(consultation_id):
            if t["speaker"] == "user" and (t["message"] or "").strip():
                out[t["question_id"] or f"turn{t['turn_no']}"] = t["message"].strip()
        return out

    # ── Blueprint ─────────────────────────────────────────────────────────
    def save_blueprint(self, bp: SolutionBlueprint) -> SolutionBlueprint:
        """초안 저장. 같은 상담에 다시 조립하면 **새 버전**으로 남긴다(덮어쓰지 않는다) —
        §5.2 "이벤트는 수정 대신 정정으로 보완한다"와 같은 태도다."""
        now = self._now()
        if not bp.blueprint_id:
            # 신규일 때만 버전을 계산한다. 기존 Blueprint 를 다시 저장할 때도 올리면 내용이
            # 그대로인데 버전이 계속 오른다(같은 것을 두 번 저장하는 것은 개정이 아니다).
            bp.blueprint_id = self._uid("bp")
            bp.created_at = now
            if bp.consultation_id:
                prev = self.list_blueprints(consultation_id=bp.consultation_id)
                if prev:
                    bp.version = max(int(r["version"] or 1) for r in prev) + 1
        bp.updated_at = now
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO solution_blueprints (blueprint_id, consultation_id, owner_dept_id, "
                "owner_user_id, tenant_id, enterprise_scope_id, entity_mode, "
                "title, business_domain, playbook_id, payload_json, "
                "readiness_score, status, approved_by, approved_at, version, created_at, "
                "updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(blueprint_id) DO UPDATE SET payload_json=excluded.payload_json, "
                "tenant_id=excluded.tenant_id, enterprise_scope_id=excluded.enterprise_scope_id, "
                "entity_mode=excluded.entity_mode, "
                "title=excluded.title, readiness_score=excluded.readiness_score, "
                "status=excluded.status, version=excluded.version, updated_at=excluded.updated_at",
                (bp.blueprint_id, bp.consultation_id, bp.owner_dept_id, bp.owner_user_id,
                 bp.tenant_id or "tenant_default", bp.enterprise_scope_id, bp.entity_mode,
                 bp.title, bp.business_domain, bp.playbook_id,
                 bp.model_dump_json(), float(bp.readiness_score), bp.status,
                 bp.approved_by, bp.approved_at, int(bp.version),
                 bp.created_at or now, now))
            conn.execute("DELETE FROM blueprint_data_requirements WHERE blueprint_id=?",
                         (bp.blueprint_id,))
            for r in bp.data_requirements:
                conn.execute(
                    "INSERT INTO blueprint_data_requirements (id, blueprint_id, req_key, "
                    "canonical_term, requirement_type, necessity, data_kind, owner_department, "
                    "readiness_status) VALUES (?,?,?,?,?,?,?,?,?)",
                    (self._uid("bpr"), bp.blueprint_id, r.key, r.canonical_term,
                     r.requirement_type, r.necessity, r.data_kind, r.owner_department,
                     r.readiness_status))
        return bp

    def get_blueprint(self, blueprint_id: str) -> Optional[SolutionBlueprint]:
        for attempt in (0, 1):
            try:
                with self._connect() as conn:
                    r = conn.execute("SELECT payload_json FROM solution_blueprints "
                                     "WHERE blueprint_id=?", (blueprint_id,)).fetchone()
                if not r:
                    return None
                return SolutionBlueprint.model_validate_json(r["payload_json"])
            except sqlite3.OperationalError:
                if attempt == 0 and self._ensure_tables():
                    continue
                return None
            except Exception:
                return None      # 페이로드 손상 — 조회가 500 이 되지 않게 한다
        return None

    def get_blueprint_row(self, blueprint_id: str) -> Optional[Dict[str, Any]]:
        """권한 판정용 메타(페이로드 파싱 없이 소유 부서만 본다)."""
        try:
            with self._connect() as conn:
                r = conn.execute(
                    "SELECT blueprint_id, consultation_id, owner_dept_id, owner_user_id, status, "
                    # [ECM-lite] 문맥 3키도 반드시 가져온다 — 이걸 빼면 `_assert_same_context` 가
                    #   판정할 근거가 없어 **다른 문맥의 Blueprint 가 조용히 통과한다**(실측).
                    "tenant_id, enterprise_scope_id, entity_mode "
                    "FROM solution_blueprints WHERE blueprint_id=?", (blueprint_id,)).fetchone()
            return dict(r) if r else None
        except Exception:
            return None

    def list_blueprints(self, consultation_id: str = "",
                        dept_ids: Optional[List[str]] = None,
                        user_id: str = "", limit: int = 50,
                        ctx: Optional[EnterpriseContext] = None) -> List[Dict[str, Any]]:
        sql = ("SELECT blueprint_id, consultation_id, owner_dept_id, owner_user_id, "
               "tenant_id, enterprise_scope_id, entity_mode, title, "
               "business_domain, playbook_id, readiness_score, status, approved_by, "
               "approved_at, version, created_at, updated_at FROM solution_blueprints")
        where, params = [], []
        for k, v in isolation_filter(ctx).items():
            where.append(f"{k}=?"); params.append(v)
        if consultation_id:
            where.append("consultation_id=?"); params.append(consultation_id)
        if dept_ids is not None:
            if not dept_ids:
                where.append("(owner_dept_id='' AND owner_user_id=?)")
                params.append(user_id or "")
            else:
                marks = ",".join("?" for _ in dept_ids)
                where.append(f"(owner_dept_id IN ({marks}) OR (owner_dept_id='' AND owner_user_id=?))")
                params.extend(list(dept_ids) + [user_id or ""])
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY version DESC, updated_at DESC LIMIT ?"
        params.append(max(1, min(int(limit or 50), 500)))
        for attempt in (0, 1):
            try:
                with self._connect() as conn:
                    return [dict(r) for r in conn.execute(sql, params).fetchall()]
            except sqlite3.OperationalError:
                if attempt == 0 and self._ensure_tables():
                    continue
                return []
        return []

    def set_blueprint_decision(self, blueprint_id: str, status: str, actor: str,
                               reason: str = "") -> Optional[SolutionBlueprint]:
        """승인/반려. **승인은 사람의 확정이므로 출처 표시를 갱신한다**(§5.2·바이블 §9.3).

        ⚠️ `origin` 은 그대로 두고 `confirmed` 만 True 로 만든다 — AI 가 제안했던 것은 승인
          뒤에도 'AI 가 제안했던 것'이며, 그 사실을 지우면 결정의 계보가 끊긴다."""
        if status not in ("approved", "rejected"):
            raise AdvisorStoreError("status 는 approved|rejected 여야 합니다.")
        bp = self.get_blueprint(blueprint_id)
        if not bp:
            return None
        if bp.status == "approved" and status == "approved":
            raise AdvisorStoreError("이미 승인된 Blueprint 입니다.")
        now = self._now()
        bp.status = status
        if status == "approved":
            bp.approved_by, bp.approved_at, bp.rejected_reason = actor or "", now, ""
            for p in bp.provenance.values():
                p.confirmed = True
        else:
            bp.approved_by, bp.approved_at = "", ""
            bp.rejected_reason = reason or ""
        bp.updated_at = now
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE solution_blueprints SET payload_json=?, status=?, approved_by=?, "
                "approved_at=?, updated_at=? WHERE blueprint_id=?",
                (bp.model_dump_json(), bp.status, bp.approved_by, bp.approved_at, now,
                 blueprint_id))

        # ★ [M0-e] Decision Ledger 기록 (§5.2). 승인은 이 제품에서 가장 중요한 결정 이벤트다.
        #   ⚠️ 라우트가 아니라 **여기서** 기록한다: 승인 경로가 늘어나도(배치 승인·경영진 일괄
        #     승인 등) 기록이 자동으로 따라온다. 라우트에 두면 새 경로가 기록을 빠뜨린다 —
        #     이 프로젝트에서 반복된 배선 누락 유형이다.
        #   ⚠️ 기록 실패는 삼키지 않는다. 승인 이력이 없는 승인은 §1.3(의도와 결정의 보존)을
        #     정면으로 어긴다. 감사 저장소가 죽었으면 호출부가 알아야 한다.
        from core.decision_ledger import decision_ledger
        _gaps = [g.canonical_term for g in bp.blocking_gaps()]
        _unverified = bp.unverified_kpis()
        decision_ledger.append(
            event_type=("BLUEPRINT_APPROVED" if status == "approved" else "BLUEPRINT_REJECTED"),
            subject_type="blueprint", subject_id=blueprint_id,
            actor_type="user", actor_id=actor or "",
            decision=("승인" if status == "approved" else f"반려: {reason}"),
            # 무엇을 알면서 승인했는지가 근거의 핵심이다(§5.2 "근거 없는 수치는 추정으로 표시").
            rationale=(f"준비도 {bp.readiness_score}점/100"
                       + (f" · 미확보 필수 데이터 {len(_gaps)}건({', '.join(_gaps[:5])})" if _gaps else "")
                       + (f" · 공식·단위 미기재 지표 {len(_unverified)}건" if _unverified else "")),
            evidence_refs=[{"kind": "readiness", "score": bp.readiness_score,
                            "measurable_max": (bp.readiness or {}).get("measurable_max"),
                            "blocking_gaps": _gaps, "unverified_kpis": _unverified},
                           {"kind": "playbook", "playbook_id": bp.playbook_id},
                           {"kind": "consultation", "consultation_id": bp.consultation_id}],
            input_version_refs=[{"blueprint_version": bp.version}],
            tenant_id=bp.tenant_id or "tenant_default",
            enterprise_scope_id=bp.enterprise_scope_id, entity_mode=bp.entity_mode,
            blueprint_id=blueprint_id)
        return bp

    def requirement_rollup(self, dept_ids: Optional[List[str]] = None,
                           ctx: Optional[EnterpriseContext] = None) -> List[Dict[str, Any]]:
        """"어느 부서가 어떤 데이터를 몇 건 못 갖췄나" — §4.4 데이터 보드용 질의.

        이 질의가 요구사항을 **행으로 따로 둔 이유**다. payload_json 안에만 있으면 검색이 안 된다."""
        sql = ("SELECT owner_department, canonical_term, readiness_status, COUNT(*) AS n "
               "FROM blueprint_data_requirements r JOIN solution_blueprints b "
               "ON b.blueprint_id = r.blueprint_id")
        params: List[Any] = []
        where = []
        for k, v in isolation_filter(ctx).items():
            where.append(f"b.{k}=?"); params.append(v)
        if dept_ids is not None:
            if not dept_ids:
                return []
            marks = ",".join("?" for _ in dept_ids)
            where.append(f"b.owner_dept_id IN ({marks})")
            params.extend(dept_ids)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += (" GROUP BY owner_department, canonical_term, readiness_status "
                "ORDER BY owner_department, canonical_term")
        try:
            with self._connect() as conn:
                return [dict(r) for r in conn.execute(sql, params).fetchall()]
        except Exception:
            return []


advisor_store = AdvisorStore()
