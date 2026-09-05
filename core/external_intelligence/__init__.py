"""[§12 / §14 M1] 외부환경 인텔리전스 — 원천 등록부 · 지표 마스터 · 관측값 · 등급 정책.

## 무엇을 만들고 무엇을 만들지 않았나 (2026-07-29 판단)

§12 는 수집기·스케줄러·정규화·사건 탐지까지 규정한다. 그런데 **승인된 외부 원천이 지금 하나도
없다.** 그 상태에서 수집기를 만들면 둘 중 하나가 된다 — 아무도 호출하지 않는 죽은 코드이거나,
"돌아가는 것처럼 보이려고" 값을 지어내는 경로. 둘 다 나쁘다.

**만든 것**: 원천 등록부, 지표 마스터, 관측값·전망 저장, **등급 정책 강제**, 결손 리포트.
**만들지 않은 것**: 수집기·스케줄러·웹 크롤러·사건 탐지 파이프라인.
  §12.4 가 "범용 웹 크롤러를 만들지 않는다"고 명시했고, 나머지는 실제 원천이 승인된 뒤에
  그 원천의 형태에 맞춰 만드는 것이 맞다. 지금은 **무엇이 없는지를 정확히 아는 것**이 산출물이다.

## 이 모듈이 강제하는 것 (§12.2)

| 등급 | 허용 | 금지 |
|---|---|---|
| `gold` 검증·확정 | 기준 계획, 공식 시뮬레이션, 경영 보고 | — |
| `silver` 잠정·전망 | 시나리오, 검토 자료 | **실제값·확정 계획으로 표시** |
| `bronze` 사건 후보 | 사건 감지, 근거 탐색 | **자동 수치 변경, 자동 의사결정** |

`resolve_value(..., purpose="baseline_plan")` 은 Gold 가 아니면 **값을 돌려주지 않는다.**
등급을 경고로만 두면 결국 쓰이고, 그 순간 "기사값으로 기준 계획이 바뀌는" §12.1 이 금지한
상황이 된다.

## `vintage` 는 필수다 (§12.5)

나중에 수정된 지표가 있어도 **특정 경영계획이 당시 어떤 발표값을 썼는지 재현**할 수 있어야
한다. vintage 없는 관측값은 받지 않는다.

저장소는 `data/external_intelligence.db` 로 분리한다(§12.3 명시 — 시계열 규모와 향후 이전).
"""
import json
import hashlib
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from core.paths import data_path

_DB_PATH = data_path("external_intelligence.db")

SOURCE_TYPES = ("API", "CSV", "RSS", "WEB", "REPORT", "PROVIDER_API")
# §12.4 원천 선택 우선순위 — 숫자가 작을수록 우선. 등록 시 자동 부여해 "왜 이 원천이
#   정본인가"를 사람이 매번 판단하지 않게 한다.
_SOURCE_PRIORITY = {"API": 1, "CSV": 2, "RSS": 3, "PROVIDER_API": 4, "REPORT": 5, "WEB": 6}
GRADES = ("gold", "silver", "bronze")
_GRADE_RANK = {g: i for i, g in enumerate(GRADES)}
QUALITY_STATUS = ("RAW", "VALIDATED", "REJECTED", "SUPERSEDED")

# §12.2 용도별 최소 등급. 이것이 이 모듈의 핵심 불변식이다.
PURPOSE_MIN_GRADE = {
    "baseline_plan": "gold",      # 기준 계획·공식 시뮬레이션·경영 보고
    "official_report": "gold",
    "scenario": "silver",         # 전망·공격·위험 시나리오
    "review": "silver",
    "detection": "bronze",        # 사건 감지·근거 탐색
}

_DDL = """
CREATE TABLE IF NOT EXISTS external_sources (
    source_id    TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    source_type  TEXT NOT NULL,
    base_url     TEXT DEFAULT '',
    license_type TEXT DEFAULT '',
    allowed_usage TEXT DEFAULT '',
    collection_method TEXT DEFAULT '',
    refresh_frequency TEXT DEFAULT '',
    rate_limit   TEXT DEFAULT '',
    owner_department TEXT DEFAULT '',
    trust_grade  TEXT NOT NULL DEFAULT 'silver',
    enabled      INTEGER NOT NULL DEFAULT 0,   -- 승인 전에는 꺼져 있다
    priority     INTEGER NOT NULL DEFAULT 9,
    approved_by  TEXT DEFAULT '',
    note         TEXT DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_src_enabled ON external_sources(enabled, priority);

CREATE TABLE IF NOT EXISTS external_indicators (
    indicator_id  TEXT PRIMARY KEY,
    code          TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    category      TEXT DEFAULT '',
    canonical_term TEXT DEFAULT '',      -- 용어사전 연결(§6.4 매칭의 출발점)
    unit          TEXT DEFAULT '',
    frequency     TEXT DEFAULT '',
    geography_code TEXT DEFAULT '',
    required_grade TEXT NOT NULL DEFAULT 'gold',
    acceptable_latency TEXT DEFAULT '',
    vintage_required INTEGER NOT NULL DEFAULT 1,
    canonical_source_id TEXT DEFAULT '',
    backup_source_id    TEXT DEFAULT '',
    source_hint   TEXT DEFAULT '',
    purpose       TEXT DEFAULT '',
    gap_impact    TEXT DEFAULT '',
    next_action   TEXT DEFAULT '',
    origin        TEXT DEFAULT 'user',   -- user|playbook
    status        TEXT NOT NULL DEFAULT 'active',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS external_indicator_proposals (
    proposal_id   TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    category      TEXT DEFAULT '',
    canonical_term TEXT DEFAULT '',
    unit          TEXT DEFAULT '',
    frequency     TEXT DEFAULT '',
    required_grade TEXT NOT NULL DEFAULT 'gold',
    acceptable_latency TEXT DEFAULT '',
    source_hint   TEXT DEFAULT '',
    purpose       TEXT DEFAULT '',
    gap_impact    TEXT DEFAULT '',
    next_action   TEXT DEFAULT '',
    rationale     TEXT DEFAULT '',
    fingerprint   TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    proposed_by   TEXT NOT NULL,
    reviewed_by   TEXT DEFAULT '',
    review_reason TEXT DEFAULT '',
    reviewed_at   TEXT DEFAULT '',
    indicator_id  TEXT DEFAULT '',
    code          TEXT DEFAULT '',
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_external_indicator_proposal_status
    ON external_indicator_proposals(status, created_at DESC);

CREATE TABLE IF NOT EXISTS external_observations (
    observation_id TEXT PRIMARY KEY,
    indicator_id  TEXT NOT NULL,
    observed_at   TEXT NOT NULL,
    published_at  TEXT DEFAULT '',
    ingested_at   TEXT NOT NULL,
    value         REAL NOT NULL,
    unit          TEXT DEFAULT '',
    vintage       TEXT NOT NULL,          -- 필수(§12.5) — 재현성의 근거
    grade         TEXT NOT NULL DEFAULT 'silver',
    source_id     TEXT DEFAULT '',
    source_record_ref TEXT DEFAULT '',
    quality_status TEXT NOT NULL DEFAULT 'RAW',
    note          TEXT DEFAULT '',
    UNIQUE (indicator_id, observed_at, vintage, source_id)
);
CREATE INDEX IF NOT EXISTS idx_obs_ind ON external_observations(indicator_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS external_forecasts (
    forecast_id   TEXT PRIMARY KEY,
    indicator_id  TEXT NOT NULL,
    provider_name TEXT DEFAULT '',
    forecast_period TEXT NOT NULL,
    published_at  TEXT DEFAULT '',
    vintage       TEXT NOT NULL,
    value         REAL NOT NULL,
    lower_bound   REAL,
    upper_bound   REAL,
    confidence_level REAL,
    methodology_summary TEXT DEFAULT '',
    source_id     TEXT DEFAULT '',
    quality_status TEXT NOT NULL DEFAULT 'RAW',
    created_at    TEXT NOT NULL,
    UNIQUE (indicator_id, forecast_period, provider_name, vintage)
);
CREATE INDEX IF NOT EXISTS idx_fc_ind ON external_forecasts(indicator_id, forecast_period);
"""


class ExternalIntelligenceError(ValueError):
    """검증/정책 위반 등 4xx 로 전달할 도메인 오류."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExternalIntelligence:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or _DB_PATH
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self):
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
        except sqlite3.Error:
            pass
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript(_DDL)

    # ── 원천 등록부 (§12.4) ───────────────────────────────────────────────
    def register_source(self, name: str, source_type: str, base_url: str = "",
                        license_type: str = "", allowed_usage: str = "",
                        refresh_frequency: str = "", owner_department: str = "",
                        trust_grade: str = "silver", note: str = "",
                        source_id: str = "") -> dict:
        """원천을 등록한다. **등록만으로는 쓰이지 않는다** — `approve_source()` 가 켜야 한다.

        ⚠️ 기본이 `enabled=0` 인 이유: §12.4 는 "승인된 원천만 등록하고 수집한다"고 못박았다.
          등록 즉시 활성이면 누구나 원천을 늘려 기준 계획의 근거를 바꿀 수 있다."""
        if source_type not in SOURCE_TYPES:
            raise ExternalIntelligenceError(f"source_type 은 {list(SOURCE_TYPES)} 중 하나여야 합니다.")
        if trust_grade not in GRADES:
            raise ExternalIntelligenceError(f"trust_grade 는 {list(GRADES)} 중 하나여야 합니다.")
        if not (name or "").strip():
            raise ExternalIntelligenceError("name 은 필수입니다.")
        sid = source_id or f"src_{uuid.uuid4().hex[:10]}"
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO external_sources(source_id,name,source_type,base_url,license_type,"
                "allowed_usage,collection_method,refresh_frequency,rate_limit,owner_department,"
                "trust_grade,enabled,priority,approved_by,note,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,'',?,'',?,?,0,?,'',?,?,?)",
                (sid, name.strip(), source_type, base_url, license_type, allowed_usage,
                 refresh_frequency, owner_department, trust_grade,
                 _SOURCE_PRIORITY.get(source_type, 9), note, now, now))
        return self.get_source(sid)

    def approve_source(self, source_id: str, approved_by: str) -> dict:
        """원천 승인 = "이 출처의 값을 회사 계획에 쓴다"는 결정. 승인자를 반드시 남긴다."""
        if not (approved_by or "").strip():
            raise ExternalIntelligenceError(
                "approved_by 는 필수입니다 — 누가 이 출처를 신뢰하기로 했는지 없으면 근거가 없습니다.")
        with self._lock, self._connect() as conn:
            if not conn.execute("UPDATE external_sources SET enabled=1, approved_by=?, "
                                "updated_at=? WHERE source_id=?",
                                (approved_by, _now(), source_id)).rowcount:
                raise ExternalIntelligenceError(f"존재하지 않는 원천입니다: {source_id}")
        return self.get_source(source_id)

    def get_source(self, source_id: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM external_sources WHERE source_id=?",
                             (source_id,)).fetchone()
        return dict(r) if r else None

    def list_sources(self, enabled_only: bool = False) -> List[dict]:
        sql = "SELECT * FROM external_sources"
        if enabled_only:
            sql += " WHERE enabled=1"
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(sql + " ORDER BY priority, name").fetchall()]

    # ── 지표 마스터 (§12.5) ───────────────────────────────────────────────
    @staticmethod
    def _proposal_material(payload: dict) -> dict:
        keys = ("name", "category", "canonical_term", "unit", "frequency",
                "required_grade", "acceptable_latency", "source_hint", "purpose",
                "gap_impact", "next_action", "rationale")
        return {key: str(payload.get(key, "") or "").strip() for key in keys}

    @classmethod
    def _proposal_fingerprint(cls, payload: dict) -> str:
        raw = json.dumps(cls._proposal_material(payload), ensure_ascii=False,
                         sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _proposal_row(row: sqlite3.Row) -> dict:
        return dict(row)

    @staticmethod
    def _indicator_code_from_proposal(proposal_id: str) -> str:
        from core.system_ids import is_system_id
        if not is_system_id(proposal_id, "external_indicator"):
            raise ExternalIntelligenceError("대외지표 제안 식별자가 발급 규칙과 일치하지 않습니다.")
        return "EXT-" + proposal_id.split("_", 1)[1].upper()

    def propose_indicator(self, payload: dict, proposed_by: str) -> dict:
        material = self._proposal_material(payload)
        if not proposed_by.strip():
            raise ExternalIntelligenceError("제안자 식별이 필요합니다.")
        if not material["name"]:
            raise ExternalIntelligenceError("지표 명칭은 필수입니다.")
        if material["required_grade"] not in GRADES:
            raise ExternalIntelligenceError(
                f"required_grade 는 {list(GRADES)} 중 하나여야 합니다.")
        from core.system_ids import allocate
        proposal_id = allocate("external_indicator")[0]
        fingerprint = self._proposal_fingerprint(material)
        now = _now()
        with self._lock, self._connect() as conn:
            if conn.execute(
                "SELECT 1 FROM external_indicators WHERE status='active' "
                "AND lower(trim(name))=? LIMIT 1",
                (material["name"].casefold(),)).fetchone():
                raise ExternalIntelligenceError("같은 명칭의 확정 대외지표가 이미 존재합니다.")
            if conn.execute(
                "SELECT 1 FROM external_indicator_proposals WHERE status='pending' "
                "AND lower(trim(name))=? LIMIT 1", (material["name"].casefold(),)).fetchone():
                raise ExternalIntelligenceError("같은 명칭의 검토 대기 지표 제안이 이미 존재합니다.")
            conn.execute(
                "INSERT INTO external_indicator_proposals("
                "proposal_id,name,category,canonical_term,unit,frequency,required_grade,"
                "acceptable_latency,source_hint,purpose,gap_impact,next_action,rationale,"
                "fingerprint,status,proposed_by,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',?,?)",
                (proposal_id, *[material[k] for k in (
                    "name", "category", "canonical_term", "unit", "frequency",
                    "required_grade", "acceptable_latency", "source_hint", "purpose",
                    "gap_impact", "next_action", "rationale")],
                 fingerprint, proposed_by.strip(), now))
            row = conn.execute(
                "SELECT * FROM external_indicator_proposals WHERE proposal_id=?",
                (proposal_id,)).fetchone()
        return self._proposal_row(row)

    def list_indicator_proposals(self, status: str = "pending") -> List[dict]:
        wanted = (status or "pending").strip().lower()
        if wanted not in {"pending", "approved", "rejected", "all"}:
            raise ExternalIntelligenceError(
                "status 는 pending·approved·rejected·all 중 하나여야 합니다.")
        with self._connect() as conn:
            if wanted == "all":
                rows = conn.execute(
                    "SELECT * FROM external_indicator_proposals ORDER BY created_at DESC").fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM external_indicator_proposals WHERE status=? "
                    "ORDER BY created_at DESC", (wanted,)).fetchall()
        return [self._proposal_row(row) for row in rows]

    def approve_indicator_proposal(self, proposal_id: str, approved_by: str,
                                   expected_fingerprint: str, reason: str = "") -> dict:
        if not approved_by.strip():
            raise ExternalIntelligenceError("승인자 식별이 필요합니다.")
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT * FROM external_indicator_proposals WHERE proposal_id=?",
                    (proposal_id,)).fetchone()
                if not row:
                    raise ExternalIntelligenceError("존재하지 않는 대외지표 제안입니다.")
                if row["status"] != "pending":
                    raise ExternalIntelligenceError("검토 대기 상태의 지표 제안만 승인할 수 있습니다.")
                if row["proposed_by"] == approved_by.strip():
                    raise ExternalIntelligenceError("제안자는 자신의 대외지표 제안을 승인할 수 없습니다.")
                if not expected_fingerprint or row["fingerprint"] != expected_fingerprint:
                    raise ExternalIntelligenceError("검토한 내용과 현재 지표 제안의 지문이 다릅니다.")
                if conn.execute(
                    "SELECT 1 FROM external_indicators WHERE lower(trim(name))=? AND status='active'",
                    (row["name"].strip().casefold(),)).fetchone():
                    raise ExternalIntelligenceError("같은 명칭의 확정 대외지표가 이미 존재합니다.")
                indicator_id = proposal_id
                code = self._indicator_code_from_proposal(proposal_id)
                now = _now()
                conn.execute(
                    "INSERT INTO external_indicators("
                    "indicator_id,code,name,category,canonical_term,unit,frequency,required_grade,"
                    "acceptable_latency,source_hint,purpose,gap_impact,next_action,origin,status,"
                    "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'approved_proposal',"
                    "'active',?,?)",
                    (indicator_id, code, row["name"], row["category"], row["canonical_term"],
                     row["unit"], row["frequency"], row["required_grade"],
                     row["acceptable_latency"], row["source_hint"], row["purpose"],
                     row["gap_impact"], row["next_action"], now, now))
                conn.execute(
                    "UPDATE external_indicator_proposals SET status='approved',reviewed_by=?,"
                    "review_reason=?,reviewed_at=?,indicator_id=?,code=? WHERE proposal_id=?",
                    (approved_by.strip(), reason.strip(), now, indicator_id, code, proposal_id))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return {"proposal": next(p for p in self.list_indicator_proposals("approved")
                                  if p["proposal_id"] == proposal_id),
                "indicator": self.get_indicator(code)}

    def reject_indicator_proposal(self, proposal_id: str, reviewed_by: str,
                                  reason: str, expected_fingerprint: str) -> dict:
        if not reviewed_by.strip():
            raise ExternalIntelligenceError("검토자 식별이 필요합니다.")
        if not reason.strip():
            raise ExternalIntelligenceError("반려 사유는 필수입니다.")
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM external_indicator_proposals WHERE proposal_id=?",
                (proposal_id,)).fetchone()
            if not row:
                raise ExternalIntelligenceError("존재하지 않는 대외지표 제안입니다.")
            if row["status"] != "pending":
                raise ExternalIntelligenceError("검토 대기 상태의 지표 제안만 반려할 수 있습니다.")
            if row["proposed_by"] == reviewed_by.strip():
                raise ExternalIntelligenceError("제안자는 자신의 대외지표 제안을 반려할 수 없습니다.")
            if not expected_fingerprint or row["fingerprint"] != expected_fingerprint:
                raise ExternalIntelligenceError("검토한 내용과 현재 지표 제안의 지문이 다릅니다.")
            now = _now()
            conn.execute(
                "UPDATE external_indicator_proposals SET status='rejected',reviewed_by=?,"
                "review_reason=?,reviewed_at=? WHERE proposal_id=?",
                (reviewed_by.strip(), reason.strip(), now, proposal_id))
            updated = conn.execute(
                "SELECT * FROM external_indicator_proposals WHERE proposal_id=?",
                (proposal_id,)).fetchone()
        return self._proposal_row(updated)

    def upsert_indicator(self, code: str, name: str, **kw) -> dict:
        if not (code or "").strip() or not (name or "").strip():
            raise ExternalIntelligenceError("code 와 name 은 필수입니다.")
        grade = kw.get("required_grade", "gold")
        if grade not in GRADES:
            raise ExternalIntelligenceError(f"required_grade 는 {list(GRADES)} 중 하나여야 합니다.")
        now = _now()
        cols = ("category", "canonical_term", "unit", "frequency", "geography_code",
                "acceptable_latency", "canonical_source_id", "backup_source_id",
                "source_hint", "purpose", "gap_impact", "next_action", "origin")
        vals = {c: kw.get(c, "") for c in cols}
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT indicator_id FROM external_indicators WHERE code=?",
                               (code,)).fetchone()
            iid = row["indicator_id"] if row else f"ind_{uuid.uuid4().hex[:10]}"
            if row:
                conn.execute(
                    "UPDATE external_indicators SET name=?, required_grade=?, "
                    "vintage_required=?, updated_at=?, "
                    + ", ".join(f"{c}=?" for c in cols) + " WHERE indicator_id=?",
                    (name, grade, 1 if kw.get("vintage_required", True) else 0, now,
                     *[vals[c] for c in cols], iid))
            else:
                conn.execute(
                    "INSERT INTO external_indicators(indicator_id,code,name,required_grade,"
                    "vintage_required,status,created_at,updated_at," + ",".join(cols) + ") "
                    "VALUES(?,?,?,?,?, 'active',?,?," + ",".join("?" * len(cols)) + ")",
                    (iid, code, name, grade, 1 if kw.get("vintage_required", True) else 0,
                     now, now, *[vals[c] for c in cols]))
        return self.get_indicator(code)

    def get_indicator(self, reference: str) -> Optional[dict]:
        """내부 코드를 우선 해석하고, 사용자 입력에는 확정 지표 명칭도 허용한다.

        화면·CSV 작성자에게 내부 코드를 요구하지 않는다. 이름이 중복되면 임의로 고르지 않고
        명확히 실패시켜 잘못된 지표에 관측값이 결속되는 것을 막는다.
        """
        value = str(reference or "").strip()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM external_indicators WHERE code=?", (value,)).fetchone()
            if row:
                return dict(row)
            rows = conn.execute(
                "SELECT * FROM external_indicators WHERE status='active' "
                "AND lower(trim(name))=lower(trim(?)) ORDER BY indicator_id",
                (value,)).fetchall()
        if len(rows) > 1:
            raise ExternalIntelligenceError(
                "같은 명칭의 확정 대외지표가 여러 건입니다. 데이터 관리자가 중복을 정리해야 합니다.")
        return dict(rows[0]) if rows else None

    def list_indicators(self) -> List[dict]:
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM external_indicators WHERE status='active' ORDER BY code").fetchall()]

    def seed_from_playbooks(self) -> dict:
        """플레이북이 선언한 외부지표를 등록부에 옮긴다(멱등, LLM 0콜).

        ★ 지표를 **창작하지 않는다.** 플레이북(`requirement_type='external'`)이 이미 무엇이
          필요한지·어떤 등급이어야 하는지·허용 지연이 얼마인지 적어 두었다. 여기서 새로 지어내면
          두 곳이 어긋나고, 어느 쪽이 요구사항인지 알 수 없게 된다."""
        made, seen = [], set()
        try:
            from core.advisor_playbook import list_playbooks, load_playbook
            # `list_playbooks()` 는 요약만 준다 — 요구사항 본문은 개별 로드해야 한다.
            books = [load_playbook(b["playbook_id"]) for b in list_playbooks()]
        except Exception as e:
            return {"seeded": 0, "error": f"플레이북을 읽을 수 없습니다: {e}", "indicators": []}
        for b in books:
            if b is None:
                continue
            for r in (getattr(b, "data_requirements", None) or []):
                r = r if isinstance(r, dict) else r.model_dump()
                if r.get("requirement_type") != "external" or r.get("key") in seen:
                    continue
                seen.add(r["key"])
                ext = r.get("external") or {}
                self.upsert_indicator(
                    code=r["key"], name=r.get("canonical_term") or r["key"],
                    canonical_term=r.get("canonical_term", ""),
                    required_grade=ext.get("grade", "gold"),
                    acceptable_latency=ext.get("acceptable_latency", ""),
                    vintage_required=bool(ext.get("vintage_required", True)),
                    source_hint=ext.get("canonical_source_hint", ""),
                    purpose=r.get("purpose", ""), gap_impact=r.get("gap_impact", ""),
                    next_action=r.get("next_action", ""),
                    frequency=r.get("expected_grain", ""), origin="playbook")
                made.append(r["key"])
        return {"seeded": len(made), "indicators": made,
                "note": ("플레이북이 선언한 요구사항을 그대로 옮깁니다. 지표를 창작하지 않습니다 — "
                         "두 곳이 어긋나면 어느 쪽이 요구사항인지 알 수 없습니다.")}

    # ── 관측값·전망 ───────────────────────────────────────────────────────
    def record_observation(self, indicator_code: str, observed_at: str, value: float,
                           vintage: str, grade: str = "silver", source_id: str = "",
                           published_at: str = "", unit: str = "",
                           source_record_ref: str = "", quality_status: str = "RAW",
                           note: str = "") -> dict:
        """실제 관측값을 기록한다.

        ⚠️ `vintage` 필수(§12.5). 없으면 나중에 수정된 지표가 있을 때 **특정 경영계획이 당시
          어떤 발표값을 썼는지 재현할 수 없다.**
        ⚠️ **승인되지 않은 원천의 값은 받지 않는다.** §12.4 "승인된 원천만 등록하고 수집한다"."""
        ind = self.get_indicator(indicator_code)
        if not ind:
            raise ExternalIntelligenceError(f"등록되지 않은 지표입니다: {indicator_code}")
        if grade not in GRADES:
            raise ExternalIntelligenceError(f"grade 는 {list(GRADES)} 중 하나여야 합니다.")
        if quality_status not in QUALITY_STATUS:
            raise ExternalIntelligenceError(f"quality_status 는 {list(QUALITY_STATUS)} 중 하나여야 합니다.")
        if ind["vintage_required"] and not (vintage or "").strip():
            raise ExternalIntelligenceError(
                "vintage 는 필수입니다 — 없으면 '이 계획이 당시 어떤 발표값을 썼는지'를 "
                "재현할 수 없습니다(§12.5).")
        if source_id:
            src = self.get_source(source_id)
            if not src:
                raise ExternalIntelligenceError(f"존재하지 않는 원천입니다: {source_id}")
            if not src["enabled"]:
                raise ExternalIntelligenceError(
                    f"승인되지 않은 원천입니다: {src['name']}. 먼저 승인하십시오(§12.4).")
            if _GRADE_RANK[grade] < _GRADE_RANK[src["trust_grade"]]:
                raise ExternalIntelligenceError(
                    f"원천의 신뢰등급({src['trust_grade']})보다 높은 등급({grade})으로 기록할 수 "
                    f"없습니다 — 출처보다 값이 더 신뢰될 수는 없습니다.")
        oid = f"obs_{uuid.uuid4().hex[:12]}"
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO external_observations(observation_id,indicator_id,observed_at,"
                "published_at,ingested_at,value,unit,vintage,grade,source_id,source_record_ref,"
                "quality_status,note) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(indicator_id,observed_at,vintage,source_id) DO UPDATE SET "
                "value=excluded.value, grade=excluded.grade, "
                "quality_status=excluded.quality_status, note=excluded.note",
                (oid, ind["indicator_id"], observed_at, published_at, _now(), float(value),
                 unit or ind["unit"], vintage, grade, source_id, source_record_ref,
                 quality_status, note))
            r = conn.execute(
                "SELECT * FROM external_observations WHERE indicator_id=? AND observed_at=? "
                "AND vintage=? AND source_id=?",
                (ind["indicator_id"], observed_at, vintage, source_id)).fetchone()
        return dict(r)

    def list_observations(self, indicator_code: str, limit: int = 50) -> List[dict]:
        ind = self.get_indicator(indicator_code)
        if not ind:
            return []
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM external_observations WHERE indicator_id=? "
                "ORDER BY observed_at DESC, vintage DESC LIMIT ?",
                (ind["indicator_id"], int(limit))).fetchall()]

    # ── 등급 정책 강제 — 이 모듈의 핵심 (§12.2) ──────────────────────────
    def resolve_value(self, indicator_code: str, purpose: str = "baseline_plan",
                      as_of: str = "", vintage: str = "") -> dict:
        """용도에 맞는 값을 돌려준다. **등급이 안 되면 값을 주지 않는다.**

        ★ 경고만 하고 값을 주면 결국 쓰인다. 그 순간 §12.1 이 금지한 "검증 없이 기사·시장
          전망값으로 기준 계획을 바꾸는" 상황이 된다. 그래서 `allowed=False` 일 때 `value` 는
          아예 `None` 이다.
        ★ `vintage` 를 주면 **그 시점 발표값**을 돌려준다 — 과거 계획의 재현 경로다."""
        if purpose not in PURPOSE_MIN_GRADE:
            raise ExternalIntelligenceError(
                f"purpose 는 {list(PURPOSE_MIN_GRADE)} 중 하나여야 합니다.")
        ind = self.get_indicator(indicator_code)
        if not ind:
            return {"indicator_code": indicator_code, "allowed": False, "value": None,
                    "reason": "등록되지 않은 지표입니다.",
                    "next_action": "지표를 등록하거나 플레이북에서 시드하십시오."}

        need = PURPOSE_MIN_GRADE[purpose]
        rows = self.list_observations(indicator_code, limit=200)
        if vintage:
            rows = [r for r in rows if r["vintage"] == vintage]
        if as_of:
            rows = [r for r in rows if r["observed_at"] <= as_of]
        usable = [r for r in rows
                  if r["quality_status"] in ("VALIDATED", "RAW")
                  and _GRADE_RANK[r["grade"]] <= _GRADE_RANK[need]]

        if not rows:
            return {"indicator_code": indicator_code, "allowed": False, "value": None,
                    "required_grade": need, "reason": "관측값이 없습니다.",
                    "gap_impact": ind["gap_impact"], "next_action": ind["next_action"]}
        if not usable:
            best = min(rows, key=lambda r: _GRADE_RANK[r["grade"]])
            return {
                "indicator_code": indicator_code, "allowed": False, "value": None,
                "required_grade": need, "available_grade": best["grade"],
                "reason": (f"'{purpose}' 용도는 최소 '{need}' 등급이 필요한데 보유한 최상위 등급은 "
                           f"'{best['grade']}' 입니다. §12.2 상 시나리오·검토에는 쓸 수 있으나 "
                           f"기준 계획·공식 수치로는 쓸 수 없습니다."),
                "next_action": ind["next_action"] or "승인된 공식 원천을 등록하십시오.",
            }
        # 같은 시점이면 더 높은 등급 → 더 최근 vintage 순
        usable.sort(key=lambda r: (_GRADE_RANK[r["grade"]], r["observed_at"], r["vintage"]),
                    reverse=False)
        best = sorted(usable, key=lambda r: (r["observed_at"], r["vintage"]), reverse=True)
        best = sorted(best, key=lambda r: _GRADE_RANK[r["grade"]])[0]
        return {
            "indicator_code": indicator_code, "allowed": True, "value": best["value"],
            "unit": best["unit"], "grade": best["grade"], "observed_at": best["observed_at"],
            "vintage": best["vintage"], "source_id": best["source_id"],
            "quality_status": best["quality_status"], "required_grade": need,
            "note": ("이 값은 표시할 때 실제값(Actual)·전망(Forecast)·계획 가정·시나리오를 "
                     "구분해 표기해야 합니다(§12.2)."),
        }

    # ── 결손 리포트 — 지금 단계의 진짜 산출물 ────────────────────────────
    def readiness_report(self) -> dict:
        """어떤 외부지표가 **아직 쓸 수 없는지**를 정확히 알려준다.

        수집기를 만들지 않은 지금, 이것이 이 모듈의 실질 산출물이다. "무엇이 없는지 정확히
        아는 것"이 없는 것을 있는 척하는 것보다 낫다."""
        out, ready, blocked = [], 0, 0
        for ind in self.list_indicators():
            res = self.resolve_value(ind["code"], purpose="baseline_plan")
            item = {"code": ind["code"], "name": ind["name"],
                    "required_grade": ind["required_grade"],
                    "acceptable_latency": ind["acceptable_latency"],
                    "canonical_source_id": ind["canonical_source_id"],
                    "source_hint": ind["source_hint"],
                    "usable_for_baseline": res["allowed"],
                    "reason": res.get("reason", ""),
                    "gap_impact": ind["gap_impact"], "next_action": ind["next_action"]}
            out.append(item)
            ready += 1 if res["allowed"] else 0
            blocked += 0 if res["allowed"] else 1
        return {
            "total": len(out), "usable_for_baseline": ready, "blocked": blocked,
            "indicators": sorted(out, key=lambda x: (x["usable_for_baseline"], x["code"])),
            "approved_sources": len(self.list_sources(enabled_only=True)),
            "note": ("수집기·스케줄러는 만들지 않았습니다 — 승인된 원천이 없는 상태의 수집기는 "
                     "죽은 코드이거나 값을 지어내는 경로가 됩니다(§12.4 '범용 웹 크롤러를 만들지 "
                     "않는다'). 지금 필요한 것은 원천 승인이며, 그 목록이 위 `next_action` 입니다."),
        }


external_intelligence = ExternalIntelligence()
