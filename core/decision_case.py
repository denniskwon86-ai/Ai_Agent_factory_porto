"""[CL-2] Decision Package — **세 관점은 같은 문서의 다른 렌더링이다.**

## 왜 하나의 Package 인가 (작업서 §3-5 · 도메인 §7.1)

요청자 검토서·의사결정자 검토서·영향부서 검토서를 **각각 독립 생성하면 숫자·가정·권고안이
달라진다.** 그리고 그 세 문서는 회의에 함께 올라간다 — 참석자들은 서로 다른 숫자를 보면서 같은
안건을 논의하고, 결정이 끝난 뒤에는 어느 숫자가 근거였는지 아무도 말할 수 없다.

★ 그래서 원본은 **하나**(`decision_cases`)이고, `render_view()` 가 관점별 **투영**을 만든다.
  세 관점은 같은 `package_version` 과 같은 `evidence_hash` 를 들고 나간다 — 그것이 "같은 문서"의
  증거다.

## 결정을 막는 세 가지 (§CL-BE-03)

1. **기준선 불일치** — 결정 시점의 근거가 생성 시점과 다르면 막는다.
2. **미검증 핵심 근거** — 핵심 근거에 검증되지 않은 항목이 있으면 막는다.
3. **승인 후 snapshot 변경** — 검토를 요청한 뒤 원천이 바뀌면 자동 갱신하지 않고
   `EVIDENCE_CHANGED` 로 표시한다(도메인 §6: "검토서 숫자를 자동 갱신하지 않는다").

⚠️ 세 번째가 가장 중요하다. 숫자를 조용히 갱신하면 참석자가 읽은 문서와 결정된 문서가 달라지고,
  그것은 회의록이 거짓이 된다는 뜻이다. 사람이 다시 보게 만드는 쪽이 느리지만 옳다.

## 효과측정

결정 **당시 기준선**과 비교한다. 그리고 **미측정을 0으로 표시하지 않는다**(§9) —
0 은 "효과가 없었다"이고 미측정은 "아직 모른다"다. 두 개를 같게 표시하면 실패한 결정과 측정하지
않은 결정이 같은 색으로 보인다.

## 외부 시스템

회의는 **요청**까지만 만든다. 외부 캘린더·메시지에 사용자 확인 없이 쓰지 않는다(§3-7) —
`external_ref` 는 사람이 실제로 만든 뒤에만 채워진다.

LLM 0콜.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from core.collaboration_store import canonical_json, collaboration_store, now_iso
from core.collaboration_events import (DECISION_REVIEW_REQUESTED, DECISION_UPDATED,
                                       collaboration_events)

DRAFT = "DRAFT"
REVIEW_REQUESTED = "REVIEW_REQUESTED"
IN_REVIEW = "IN_REVIEW"
MEETING_REQUESTED = "MEETING_REQUESTED"
EVIDENCE_CHANGED = "EVIDENCE_CHANGED"
DECIDED = "DECIDED"
ACTIONED = "ACTIONED"
EFFECT_MEASURED = "EFFECT_MEASURED"
CANCELLED = "CANCELLED"

#: 결정 가능한 상태. 그 밖에서 `decide` 를 부르면 막는다.
DECIDABLE_FROM = (REVIEW_REQUESTED, IN_REVIEW, MEETING_REQUESTED)

#: 참여자 역할 — §CL-BE-03 "요청자/결정자/영향부서 역할 분리".
#: ⚠️ 하나의 enum 으로 뭉개지 않는다. 요청자는 올린 사람, 결정자는 승인권자, 영향부서는 의견을
#:   내는 쪽이다. 섞으면 "누가 결정했는가"에 답할 수 없다.
ROLE_REQUESTER = "REQUESTER"
ROLE_DECIDER = "DECIDER"
ROLE_AFFECTED = "AFFECTED"
ROLES = (ROLE_REQUESTER, ROLE_DECIDER, ROLE_AFFECTED)

#: 범위 제한이 없는 열람자(플랫폼 관리자·조직 미도입). **`None` 과 다르다** —
#: `None` 은 «범위를 넘기지 않았다»(레거시)이고 이것은 «넘겼는데 전 범위»다.
#: `core/publication.py` 와 같은 규약이다(두 곳이 다르면 한쪽만 고쳐진다).
UNRESTRICTED = object()

#: 영향부서 의견(도메인 §7.5). "정보 부족"이 1급 선택지인 것이 요점이다 —
#: 그것이 없으면 모르는 부서가 '동의'를 누른다.
RESPONSE_AGREE = "AGREE"
RESPONSE_CONDITIONAL = "CONDITIONAL"
RESPONSE_DISAGREE = "DISAGREE"
RESPONSE_NEED_INFO = "NEED_INFO"
RESPONSES = (RESPONSE_AGREE, RESPONSE_CONDITIONAL, RESPONSE_DISAGREE, RESPONSE_NEED_INFO)

#: 결정 결과 — 조건부·보류가 별도로 있어야 "일단 승인"이 조건부를 삼키지 않는다.
OUTCOME_APPROVED = "APPROVED"
OUTCOME_CONDITIONAL = "CONDITIONAL"
OUTCOME_REJECTED = "REJECTED"
OUTCOME_DEFERRED = "DEFERRED"
OUTCOMES = (OUTCOME_APPROVED, OUTCOME_CONDITIONAL, OUTCOME_REJECTED, OUTCOME_DEFERRED)

VIEW_REQUESTER = "requester"
VIEW_DECIDER = "decider"
VIEW_AFFECTED = "affected"
VIEWS = (VIEW_REQUESTER, VIEW_DECIDER, VIEW_AFFECTED)

_DDL = """
CREATE TABLE IF NOT EXISTS decision_cases (
    decision_id      TEXT PRIMARY KEY,
    tenant_id        TEXT NOT NULL DEFAULT 'tenant_default',
    scope_id         TEXT NOT NULL DEFAULT '',
    simulation_run_id TEXT NOT NULL DEFAULT '',
    baseline_id      TEXT NOT NULL DEFAULT '',
    scenario_id      TEXT NOT NULL DEFAULT '',
    question         TEXT NOT NULL,
    package_json     TEXT NOT NULL DEFAULT '{}',
    evidence_json    TEXT NOT NULL DEFAULT '{}',
    evidence_hash    TEXT NOT NULL DEFAULT '',
    package_version  INTEGER NOT NULL DEFAULT 1,
    status           TEXT NOT NULL DEFAULT 'DRAFT',
    due_at           TEXT NOT NULL DEFAULT '',
    outcome          TEXT NOT NULL DEFAULT '',
    outcome_conditions TEXT NOT NULL DEFAULT '',
    decided_by       TEXT NOT NULL DEFAULT '',
    decided_at       TEXT NOT NULL DEFAULT '',
    created_by       TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_case_status ON decision_cases(status);

CREATE TABLE IF NOT EXISTS decision_participants (
    decision_id      TEXT NOT NULL,
    user_id          TEXT NOT NULL,
    role             TEXT NOT NULL,
    scope_id         TEXT NOT NULL DEFAULT '',
    response_status  TEXT NOT NULL DEFAULT '',
    response         TEXT NOT NULL DEFAULT '',
    responded_at     TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL,
    PRIMARY KEY (decision_id, user_id, role)
);

CREATE TABLE IF NOT EXISTS decision_meetings (
    meeting_id       TEXT PRIMARY KEY,
    decision_id      TEXT NOT NULL,
    title            TEXT NOT NULL,
    schedule         TEXT NOT NULL DEFAULT '',
    channel          TEXT NOT NULL DEFAULT '',
    agenda_json      TEXT NOT NULL DEFAULT '{}',
    status           TEXT NOT NULL DEFAULT 'REQUESTED',
    external_ref     TEXT NOT NULL DEFAULT '',
    requested_by     TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_meeting_case ON decision_meetings(decision_id);

CREATE TABLE IF NOT EXISTS decision_actions (
    action_id        TEXT PRIMARY KEY,
    decision_id      TEXT NOT NULL,
    owner_scope_id   TEXT NOT NULL DEFAULT '',
    owner_user_id    TEXT NOT NULL DEFAULT '',
    action           TEXT NOT NULL,
    due_at           TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'OPEN',
    measured_effect  TEXT NOT NULL DEFAULT '',
    measured_at      TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_action_case ON decision_actions(decision_id);
"""


class DecisionCaseError(ValueError):
    """정책 위반 — 4xx 로 전달한다."""


class DecisionNotFound(LookupError):
    """없거나 볼 수 없다 — 라우트가 **404** 로 바꾼다(존재를 알리지 않는다)."""


def evidence_hash(evidence: Any) -> str:
    """근거 지문. **정렬된 canonical JSON** 이므로 키 순서가 달라도 같은 지문이다."""
    return hashlib.sha256(canonical_json(evidence).encode("utf-8")).hexdigest()[:32]


class DecisionCase:
    def __init__(self, store=None, ledger=None):
        self._store_override = store
        self._ledger_override = ledger

    @property
    def _store(self):
        return self._store_override or collaboration_store

    @property
    def _ledger(self):
        if self._ledger_override is not None:
            return self._ledger_override
        from core.decision_ledger import decision_ledger
        return decision_ledger

    def _ensure(self) -> None:
        """CL-2 표를 보장한다. 재실행 가능하며 기존 데이터를 보존한다."""
        self._store.ensure_schema()
        conn = self._store._connect()
        try:
            conn.executescript(_DDL)
            conn.commit()
        finally:
            conn.close()

    # ── 생성 ──────────────────────────────────────────────────────────────
    def create(self, question: str, created_by: str, simulation_run_id: str = "",
               baseline_id: str = "", scenario_id: str = "", scope_id: str = "",
               package: Optional[Dict[str, Any]] = None,
               evidence: Optional[Dict[str, Any]] = None, due_at: str = "",
               tenant_id: str = "tenant_default") -> Dict[str, Any]:
        """시뮬레이션 결과에서 Decision Package 를 만든다.

        ⚠️ `question`(결정해야 하는 문장)을 요구한다. "검토 요청" 같은 제목만 있으면 참석자가
          무엇을 승인하는지 모르고, 회의록에는 "논의함"만 남는다."""
        self._ensure()
        if not (question or "").strip():
            raise DecisionCaseError(
                "결정 문장(question)은 필수입니다 — 무엇을 승인·기각하는지 한 문장으로 없으면 "
                "참석자는 무엇을 결정하는지 모릅니다.")
        if not (created_by or "").strip():
            raise DecisionCaseError("요청자(created_by)가 필요합니다.")
        pkg = package or {}
        ev = evidence or {}
        missing = [k for k in ("baseline", "options") if not pkg.get(k)]
        if missing:
            raise DecisionCaseError(
                f"Decision Package 에 {missing} 가 없습니다 — 기준선과 대안이 없으면 비교할 것이 "
                f"없고, 결정은 '하자/말자'만 남습니다(도메인 §7.2).")
        did = f"dec_{uuid.uuid4().hex[:12]}"
        now = now_iso()
        h = evidence_hash(ev)
        self._store.execute(
            "INSERT INTO decision_cases (decision_id, tenant_id, scope_id, simulation_run_id, "
            "baseline_id, scenario_id, question, package_json, evidence_json, evidence_hash, "
            "package_version, status, due_at, created_by, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,1,?,?,?,?,?)",
            (did, tenant_id, scope_id, simulation_run_id, baseline_id, scenario_id,
             question.strip(), canonical_json(pkg), canonical_json(ev), h, DRAFT,
             due_at, created_by, now, now))
        # 요청자는 참여자로 자동 등록된다 — 올린 사람이 목록에 없으면 누가 올렸는지 화면에서 사라진다.
        self._store.execute(
            "INSERT OR IGNORE INTO decision_participants (decision_id, user_id, role, scope_id, "
            "created_at) VALUES (?,?,?,?,?)", (did, created_by, ROLE_REQUESTER, scope_id, now))
        # ★★ 원장 기록이 실패하면 **행을 되돌린다**(CL-3 에서 실측한 결함과 같은 구조).
        #   원장에 없는 안건이 DB 에 남으면 "누가 무엇을 올렸나"에 답할 수 없고, 그 안건은
        #   그대로 회의에 올라간다.
        try:
            self._audit("DECISION_CASE_CREATED", did, created_by,
                        decision=question.strip()[:200],
                        rationale=f"시뮬레이션 {simulation_run_id or '(없음)'} 기반",
                        evidence=[{"evidence_hash": h, "baseline_id": baseline_id}],
                        tenant_id=tenant_id, scope=scope_id)
        except Exception:
            self._store.executemany_tx([
                ("DELETE FROM decision_participants WHERE decision_id=?", (did,)),
                ("DELETE FROM decision_cases WHERE decision_id=?", (did,)),
            ])
            raise
        return self.get(did, created_by)

    # ── 조회·투영 ─────────────────────────────────────────────────────────
    def _visible(self, row: Dict[str, Any], participants: List[Dict[str, Any]],
                 user_id: str, viewer_scopes) -> bool:
        """이 안건이 이 사람에게 보이는가.

        ★★★ [2026-08-08 실측 결함] 이 파일 머리말은 「참여자가 아닌 안건 → **404**」를
          규정하는데 **구현이 없었다.** 격리 저장소 실측:

              남남이 조회 → 성공(패키지·참여자·회의 전부) · 뷰 렌더 → 통과
              남남이 검토요청 → 통과 · 남남이 회의소집 → 통과

          특히 검토요청은 **남의 안건에 참여자를 임의로 넣는 것**이다. 결정·참여응답만
          `my_role` 을 봤고 나머지는 `get()` 을 그냥 지났다.
          `core/publication.py` 와 **같은 유형**이며 같은 방식으로 막는다.

        판정: 작성자 · **참여자** · 안건의 조직 범위가 열람자 범위에 있음 · 무제한 주체.
        ⚠️ 참여자를 넣은 이유: 안건은 여러 부서가 함께 보는 것이고, 참여자로 지정된 사람은
          자기 부서 밖 안건이라도 답해야 한다. 범위만 보면 그 사람이 자기 할 일을 못 본다."""
        if viewer_scopes is None:
            return True                      # 하위호환 — 라우트는 항상 범위를 넘긴다
        if viewer_scopes is UNRESTRICTED:
            return True
        uid = str(user_id or "").strip()
        if uid and uid == str(row.get("created_by") or ""):
            return True
        if uid and any(str(p.get("user_id") or "") == uid for p in participants):
            return True
        scope = str(row.get("scope_id") or "").strip()
        # ⚠️ 범위가 빈 안건은 «전사» 가 아니라 «미지정» 이다 — 작성자·참여자만 본다.
        return bool(scope) and scope in viewer_scopes

    def get(self, decision_id: str, user_id: str = "", today: str = "",
            viewer_scopes=None) -> Dict[str, Any]:
        """상세. **참여자·관계자가 아니면 404**(이 파일 머리말 §3-10 경계표).

        ★ 이 메서드가 **단일 판정 지점**이다 — `render_view`·`request_review`·
          `request_meeting`·`decide`·`create_actions`·`measure_effect` 가 전부 여기를 지난다."""
        self._ensure()
        row = self._store.one("SELECT * FROM decision_cases WHERE decision_id=?", (decision_id,))
        if not row:
            raise DecisionNotFound(decision_id)
        parts = self._store.query(
            "SELECT * FROM decision_participants WHERE decision_id=? ORDER BY role, user_id",
            (decision_id,))
        if not self._visible(dict(row), parts, user_id, viewer_scopes):
            # 403 이 아니라 404 — 403 은 «있지만 못 본다» 를 알려주므로 존재가 샌다.
            raise DecisionNotFound(decision_id)
        d = self._row(row, today)
        d["participants"] = parts
        d["meetings"] = [self._meeting_row(m) for m in self._store.query(
            "SELECT * FROM decision_meetings WHERE decision_id=? ORDER BY created_at DESC",
            (decision_id,))]
        d["actions"] = self._store.query(
            "SELECT * FROM decision_actions WHERE decision_id=? ORDER BY created_at", (decision_id,))
        d["my_role"] = next((p["role"] for p in d["participants"] if p["user_id"] == user_id), "")
        d["blockers"] = self._decide_blockers(d)
        d["can_decide"] = (d["my_role"] == ROLE_DECIDER and d["status"] in DECIDABLE_FROM
                           and not d["blockers"])
        return d

    def queue(self, user_id: str, today: str = "") -> List[Dict[str, Any]]:
        """내가 관여한 결정 목록. **본인이 참여자인 것만** 돌려준다."""
        self._ensure()
        rows = self._store.query(
            "SELECT c.* FROM decision_cases c JOIN decision_participants p "
            "ON p.decision_id = c.decision_id WHERE p.user_id=? "
            "GROUP BY c.decision_id ORDER BY c.created_at DESC", (user_id,))
        out = []
        for r in rows:
            d = self._row(r, today)
            d["my_role"] = (self._store.one(
                "SELECT role FROM decision_participants WHERE decision_id=? AND user_id=? LIMIT 1",
                (r["decision_id"], user_id)) or {}).get("role", "")
            out.append(d)
        return out

    def render_view(self, decision_id: str, view: str, user_id: str = "",
                    today: str = "",
                viewer_scopes=None) -> Dict[str, Any]:
        """관점별 **투영**. 데이터를 복제하지 않는다(§CL-BE-03).

        ★ 세 관점이 같은 `decision_id` · `package_version` · `evidence_hash` 를 들고 나간다 —
          그것이 "하나의 문서"라는 증거다. 화면은 이 세 값을 표시해 참석자가 같은 근거를 보고
          있음을 확인할 수 있어야 한다."""
        if view not in VIEWS:
            raise DecisionCaseError(f"view 는 {VIEWS} 중 하나여야 합니다: {view}")
        d = self.get(decision_id, user_id, today, viewer_scopes)
        pkg = d["package"]
        common = {
            "decision_id": d["decision_id"], "view": view,
            "package_version": d["package_version"], "evidence_hash": d["evidence_hash"],
            "question": d["question"], "status": d["status"], "due_at": d["due_at"],
            "baseline_id": d["baseline_id"], "simulation_run_id": d["simulation_run_id"],
            # 같은 근거를 보고 있는지 화면이 확인할 수 있게 항상 함께 낸다.
            "identity_note": ("세 관점은 같은 Decision Package 의 다른 렌더링입니다 — "
                              "package_version 과 evidence_hash 가 같아야 같은 문서입니다."),
        }
        if view == VIEW_REQUESTER:
            common["sections"] = _sections(pkg, [
                ("problem", "현업 문제와 배경"), ("why_simulated", "시뮬레이션을 수행한 이유"),
                ("recommendation", "요청자의 권고안"), ("asks", "요청 예산·정책·인력·설비·일정"),
                ("expected_effect", "기대효과"), ("open_risks", "미결 리스크"),
                ("followups", "요청자가 책임질 후속 행동"),
                ("impact_if_rejected", "반려·지연 시 업무 영향"),
            ])
        elif view == VIEW_DECIDER:
            common["sections"] = _sections(pkg, [
                ("executive_brief", "1페이지 요약"), ("baseline", "기준안(무행동 포함)"),
                ("options", "권고안·대안 비교"), ("financial_impact", "손익·현금·투자회수"),
                ("sensitivity", "최악/기준/최선과 민감도"),
                ("reversible", "되돌릴 수 있는 결정인가"),
                ("compliance_risk", "규정·안전·품질·평판 리스크"),
                ("dissent", "반대 의견과 불확실성"),
                ("approval_conditions", "승인 시 조건과 중간 점검 기준"),
            ])
            common["decision_form"] = {"outcomes": list(OUTCOMES),
                                       "requires_conditions_for": [OUTCOME_CONDITIONAL]}
        else:
            common["sections"] = _sections(pkg, [
                ("dept_changes", "바뀌는 업무·KPI·책임"), ("data_to_provide", "제공해야 할 데이터"),
                ("resource_impact", "인력·설비·재고·일정·원가 영향"),
                ("dependencies", "선행·후행 부서 의존성"),
                ("conflicts", "예상 충돌·병목·예외"),
            ])
            common["response_form"] = {"options": list(RESPONSES),
                                       "note": "'정보 부족'은 정당한 답입니다 — 모르는 상태로 "
                                               "동의하면 그 동의가 근거로 쓰입니다."}
        common["blockers"] = d["blockers"]
        return common

    # ── 검토·회의 ─────────────────────────────────────────────────────────
    def request_review(self, decision_id: str, actor: str, participants: List[Dict[str, str]],
                       today: str = "",
                viewer_scopes=None) -> Dict[str, Any]:
        """참여자에게 검토를 요청한다.

        ⚠️ **결정자가 없으면 요청할 수 없다.** 결정자 없는 안건은 회의만 만들고 아무것도 끝내지
          못한다 — 이 저장소가 '승인자 없는 승인'에서 겪은 유형이다."""
        d = self.get(decision_id, actor, today, viewer_scopes)
        if d["status"] not in (DRAFT, REVIEW_REQUESTED, EVIDENCE_CHANGED):
            raise DecisionCaseError(f"{d['status']} 상태에서는 검토를 요청할 수 없습니다.")
        rows = []
        now = now_iso()
        for p in participants or []:
            uid = str(p.get("user_id", "")).strip()
            role = str(p.get("role", "")).strip().upper()
            if not uid:
                raise DecisionCaseError("참여자 user_id 가 비어 있습니다.")
            if role not in ROLES:
                raise DecisionCaseError(f"role 은 {ROLES} 중 하나여야 합니다: {role}")
            rows.append((decision_id, uid, role, str(p.get("scope_id", "")), now))
        have_decider = any(r[2] == ROLE_DECIDER for r in rows) or any(
            p["role"] == ROLE_DECIDER for p in d["participants"])
        if not have_decider:
            raise DecisionCaseError(
                "결정자(DECIDER)가 지정되지 않았습니다 — 결정자 없는 안건은 회의만 만들고 "
                "아무것도 끝내지 못합니다.")
        stmts = [("INSERT OR IGNORE INTO decision_participants (decision_id, user_id, role, "
                  "scope_id, created_at) VALUES (?,?,?,?,?)", r) for r in rows]
        stmts.append(("UPDATE decision_cases SET status=?, updated_at=? WHERE decision_id=?",
                      (REVIEW_REQUESTED, now, decision_id)))
        self._store.executemany_tx(stmts)
        self._audit("DECISION_REVIEW_REQUESTED", decision_id, actor,
                    decision=f"참여자 {len(rows)}명에게 검토 요청",
                    rationale=d["question"][:200],
                    evidence=[{"evidence_hash": d["evidence_hash"]}],
                    tenant_id=d["tenant_id"], scope=d["scope_id"])
        out = self.get(decision_id, actor, today, viewer_scopes)
        # [CL-4] **참여자에게만** 알린다. 목록에 없는 사람은 안건의 존재도 몰라야 한다.
        self._notify(DECISION_REVIEW_REQUESTED, out, actor)
        return out

    def participant_response(self, decision_id: str, user_id: str, response_status: str,
                             response: str = "", today: str = "",
                viewer_scopes=None) -> Dict[str, Any]:
        """영향부서·결정자의 의견을 남긴다.

        ⚠️ 참여자가 아니면 `DecisionNotFound` 다 — 남의 안건에 의견을 남길 수 없고, 존재도
          알리지 않는다."""
        d = self.get(decision_id, user_id, today, viewer_scopes)
        if not d["my_role"]:
            raise DecisionNotFound(decision_id)
        if response_status not in RESPONSES:
            raise DecisionCaseError(f"response_status 는 {RESPONSES} 중 하나여야 합니다.")
        if response_status in (RESPONSE_CONDITIONAL, RESPONSE_DISAGREE, RESPONSE_NEED_INFO) \
                and not (response or "").strip():
            raise DecisionCaseError(
                "조건부·반대·정보 부족에는 내용이 필요합니다 — 이유 없는 반대는 결정자가 "
                "판단에 쓸 수 없습니다.")
        now = now_iso()
        self._store.execute(
            "UPDATE decision_participants SET response_status=?, response=?, responded_at=? "
            "WHERE decision_id=? AND user_id=?",
            (response_status, (response or "").strip(), now, decision_id, user_id))
        # 첫 응답이 오면 검토 중으로 옮긴다(요청만 하고 아무 응답이 없는 상태와 구분한다).
        if d["status"] == REVIEW_REQUESTED:
            self._store.execute("UPDATE decision_cases SET status=?, updated_at=? "
                                "WHERE decision_id=?", (IN_REVIEW, now, decision_id))
        out = self.get(decision_id, user_id, today, viewer_scopes)
        self._notify(DECISION_UPDATED, out, user_id)
        return out

    def request_meeting(self, decision_id: str, actor: str, title: str, schedule: str = "",
                        channel: str = "", today: str = "",
                viewer_scopes=None) -> Dict[str, Any]:
        """회의를 **요청**한다. 외부 캘린더에 쓰지 않는다(§3-7).

        ★ `external_ref` 는 사람이 실제로 캘린더를 만든 뒤에만 채워진다. 시스템이 먼저 만들면
          사용자가 모르는 초대가 나가고, 그것은 되돌릴 수 없다."""
        d = self.get(decision_id, actor, today, viewer_scopes)
        if d["status"] in (DECIDED, ACTIONED, EFFECT_MEASURED, CANCELLED):
            raise DecisionCaseError(f"{d['status']} 상태에서는 회의를 요청할 수 없습니다.")
        if not (title or "").strip():
            raise DecisionCaseError("회의 제목은 필수입니다.")
        mid = f"mtg_{uuid.uuid4().hex[:12]}"
        now = now_iso()
        # 안건 스냅샷 — 회의 시점에 무엇을 보고 있었는지 고정한다.
        agenda = {"question": d["question"], "package_version": d["package_version"],
                  "evidence_hash": d["evidence_hash"],
                  "participants": [{"user_id": p["user_id"], "role": p["role"]}
                                   for p in d["participants"]]}
        self._store.executemany_tx([
            ("INSERT INTO decision_meetings (meeting_id, decision_id, title, schedule, channel, "
             "agenda_json, status, external_ref, requested_by, created_at, updated_at) "
             "VALUES (?,?,?,?,?,?,'REQUESTED','',?,?,?)",
             (mid, decision_id, title.strip(), schedule, channel, canonical_json(agenda),
              actor, now, now)),
            ("UPDATE decision_cases SET status=?, updated_at=? WHERE decision_id=?",
             (MEETING_REQUESTED, now, decision_id)),
        ])
        self._audit("DECISION_MEETING_REQUESTED", decision_id, actor,
                    decision=f"회의 요청: {title.strip()[:120]}",
                    rationale=f"일정 {schedule or '미정'} · 채널 {channel or '미정'}",
                    evidence=[{"meeting_id": mid, "evidence_hash": d["evidence_hash"]}],
                    tenant_id=d["tenant_id"], scope=d["scope_id"])
        out = self.get(decision_id, actor, today, viewer_scopes)
        out["note"] = ("회의 **요청**만 기록했습니다. 외부 캘린더·메시지에는 아무것도 보내지 "
                       "않았습니다 — 실제 초대는 사람이 만들어야 합니다(§3-7).")
        self._notify(DECISION_UPDATED, out, actor)
        return out

    # ── 결정 ──────────────────────────────────────────────────────────────
    def decide(self, decision_id: str, actor: str, outcome: str, rationale: str,
               conditions: str = "", today: str = "",
                viewer_scopes=None) -> Dict[str, Any]:
        """결정을 기록한다. **막는 조건이 있으면 막는다**(§CL-BE-03)."""
        d = self.get(decision_id, actor, today, viewer_scopes)
        if d["my_role"] != ROLE_DECIDER:
            # 결정자가 아니면 존재를 알리지 않는다(권한 경계).
            raise DecisionNotFound(decision_id)
        # ★ 차단 이유를 **상태 검사보다 먼저** 말한다. 순서가 반대면 근거가 바뀐 경우에도
        #   "EVIDENCE_CHANGED 상태에서는 결정할 수 없습니다"만 나오고, 정작 중요한 이유
        #   ("참석자가 읽은 숫자와 다릅니다")는 사용자에게 도달하지 않는다.
        if d["blockers"]:
            raise DecisionCaseError(
                "결정을 막는 조건이 있습니다: " + " / ".join(b["reason"] for b in d["blockers"]))
        if d["status"] not in DECIDABLE_FROM:
            raise DecisionCaseError(
                f"{d['status']} 상태에서는 결정할 수 없습니다 — 검토 요청 후에 결정합니다.")
        if outcome not in OUTCOMES:
            raise DecisionCaseError(f"outcome 은 {OUTCOMES} 중 하나여야 합니다: {outcome}")
        if not (rationale or "").strip():
            raise DecisionCaseError(
                "결정 근거(rationale)는 필수입니다 — 근거 없는 승인은 나중에 설명할 수 없습니다.")
        if outcome == OUTCOME_CONDITIONAL and not (conditions or "").strip():
            raise DecisionCaseError(
                "조건부 승인에는 조건이 필요합니다 — 조건 없는 조건부는 그냥 승인이고, "
                "실행 단계에서 아무도 조건을 확인하지 않습니다.")
        now = now_iso()
        self._store.execute(
            "UPDATE decision_cases SET status=?, outcome=?, outcome_conditions=?, decided_by=?, "
            "decided_at=?, updated_at=? WHERE decision_id=?",
            (DECIDED, outcome, (conditions or "").strip(), actor, now, now, decision_id))
        self._audit("DECISION_RECORDED", decision_id, actor,
                    decision=f"{outcome}: {d['question'][:150]}",
                    rationale=rationale.strip(),
                    evidence=[{"evidence_hash": d["evidence_hash"],
                               "baseline_id": d["baseline_id"],
                               "conditions": (conditions or "").strip()}],
                    tenant_id=d["tenant_id"], scope=d["scope_id"])
        out = self.get(decision_id, actor, today, viewer_scopes)
        self._notify(DECISION_UPDATED, out, actor)
        return out

    def create_actions(self, decision_id: str, actor: str, actions: List[Dict[str, Any]],
                       today: str = "",
                viewer_scopes=None) -> Dict[str, Any]:
        """실행과제를 만든다. **담당·기한이 없으면 만들지 않는다.**

        ⚠️ 담당 없는 과제는 아무도 하지 않고, 기한 없는 과제는 언제 늦었는지 알 수 없다 —
          결정이 실행으로 이어지지 않는 가장 흔한 경로다."""
        d = self.get(decision_id, actor, today, viewer_scopes)
        if d["status"] not in (DECIDED, ACTIONED):
            raise DecisionCaseError(
                f"{d['status']} 상태에서는 실행과제를 만들 수 없습니다 — 결정 후에 만듭니다.")
        if not actions:
            raise DecisionCaseError("실행과제가 비어 있습니다.")
        now = now_iso()
        stmts = []
        for a in actions:
            act = str(a.get("action", "")).strip()
            owner = str(a.get("owner_user_id", "")).strip()
            due = str(a.get("due_at", "")).strip()
            if not act:
                raise DecisionCaseError("과제 내용(action)이 비어 있습니다.")
            if not owner:
                raise DecisionCaseError(f"'{act[:40]}' 의 담당자가 없습니다 — 담당 없는 과제는 "
                                        f"아무도 하지 않습니다.")
            if not due:
                raise DecisionCaseError(f"'{act[:40]}' 의 기한이 없습니다 — 기한 없는 과제는 "
                                        f"언제 늦었는지 알 수 없습니다.")
            try:
                date.fromisoformat(due)
            except ValueError:
                raise DecisionCaseError(f"기한 형식은 YYYY-MM-DD 입니다: {due}")
            stmts.append((
                "INSERT INTO decision_actions (action_id, decision_id, owner_scope_id, "
                "owner_user_id, action, due_at, status, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,'OPEN',?,?)",
                (f"act_{uuid.uuid4().hex[:12]}", decision_id,
                 str(a.get("owner_scope_id", "")).strip(), owner, act, due, now, now)))
        stmts.append(("UPDATE decision_cases SET status=?, updated_at=? WHERE decision_id=?",
                      (ACTIONED, now, decision_id)))
        self._store.executemany_tx(stmts)
        self._audit("DECISION_ACTION_CREATED", decision_id, actor,
                    decision=f"실행과제 {len(actions)}건 생성",
                    rationale=d["question"][:200],
                    tenant_id=d["tenant_id"], scope=d["scope_id"])
        out = self.get(decision_id, actor, today, viewer_scopes)
        self._notify(DECISION_UPDATED, out, actor)
        return out

    def measure_effect(self, decision_id: str, actor: str, action_id: str,
                       measured_effect: str, today: str = "",
                viewer_scopes=None) -> Dict[str, Any]:
        """효과를 기록한다. **결정 당시 기준선과 비교한다**(§9).

        ⚠️ 미측정을 0 으로 표시하지 않는다 — 0 은 "효과가 없었다"이고 미측정은 "아직 모른다"다.
          두 개를 같게 표시하면 실패한 결정과 측정하지 않은 결정이 같은 색으로 보인다."""
        d = self.get(decision_id, actor, today, viewer_scopes)
        row = self._store.one("SELECT * FROM decision_actions WHERE action_id=?", (action_id,))
        if not row or row["decision_id"] != decision_id:
            raise DecisionNotFound(action_id)
        if not (measured_effect or "").strip():
            raise DecisionCaseError(
                "측정값이 비어 있습니다 — 미측정으로 두십시오. 빈 값을 0 으로 저장하면 "
                "'효과 없음'과 '아직 모름'이 같아집니다.")
        now = now_iso()
        self._store.executemany_tx([
            ("UPDATE decision_actions SET measured_effect=?, measured_at=?, status='MEASURED', "
             "updated_at=? WHERE action_id=?",
             (measured_effect.strip(), now, now, action_id)),
            ("UPDATE decision_cases SET status=?, updated_at=? WHERE decision_id=?",
             (EFFECT_MEASURED, now, decision_id)),
        ])
        self._audit("DECISION_EFFECT_MEASURED", decision_id, actor,
                    decision=f"효과 측정: {measured_effect.strip()[:150]}",
                    rationale=f"결정 당시 기준선 {d['baseline_id'] or '(없음)'} 대비",
                    evidence=[{"action_id": action_id, "baseline_id": d["baseline_id"]}],
                    tenant_id=d["tenant_id"], scope=d["scope_id"])
        out = self.get(decision_id, actor, today, viewer_scopes)
        self._notify(DECISION_UPDATED, out, actor)
        return out

    # ── 근거 변경 감지 ────────────────────────────────────────────────────
    def refresh_evidence(self, decision_id: str, new_evidence: Dict[str, Any],
                         actor: str = "") -> Dict[str, Any]:
        """원천이 바뀌었을 때 호출한다. **숫자를 자동 갱신하지 않는다**(도메인 §6).

        ★ 대신 `EVIDENCE_CHANGED` 로 표시하고 사람이 다시 보게 만든다.
        ⚠️ 조용히 갱신하면 참석자가 읽은 문서와 결정된 문서가 달라진다 — 회의록이 거짓이 된다."""
        self._ensure()
        row = self._store.one("SELECT * FROM decision_cases WHERE decision_id=?", (decision_id,))
        if not row:
            raise DecisionNotFound(decision_id)
        new_hash = evidence_hash(new_evidence)
        if new_hash == row["evidence_hash"]:
            return self.get(decision_id, actor)
        now = now_iso()
        if row["status"] in (DECIDED, ACTIONED, EFFECT_MEASURED):
            # 이미 결정된 안건의 근거는 **바꾸지 않는다.** 결정의 근거가 사후에 달라지면
            # 그 결정을 설명할 수 없다. 새 안건을 만들어야 한다.
            raise DecisionCaseError(
                "이미 결정된 안건의 근거는 변경할 수 없습니다 — 결정의 근거가 사후에 달라지면 "
                "그 결정을 설명할 수 없습니다. 새 Decision Package 를 만드십시오.")
        self._store.execute(
            "UPDATE decision_cases SET evidence_json=?, evidence_hash=?, "
            "package_version=package_version+1, status=?, updated_at=? WHERE decision_id=?",
            (canonical_json(new_evidence), new_hash, EVIDENCE_CHANGED, now, decision_id))
        return self.get(decision_id, actor)

    # ── 공통 ──────────────────────────────────────────────────────────────
    @staticmethod
    def _decide_blockers(d: Dict[str, Any]) -> List[Dict[str, str]]:
        """결정을 막는 조건. **빈 목록이면 결정 가능**이다."""
        out: List[Dict[str, str]] = []
        if d["status"] == EVIDENCE_CHANGED:
            out.append({"code": "EVIDENCE_CHANGED",
                        "reason": ("검토 요청 후 근거가 바뀌었습니다 — 참석자가 읽은 숫자와 다릅니다. "
                                   "다시 검토를 요청하십시오.")})
        # 근거 지문 불일치 — 저장된 근거를 다시 계산해 비교한다(파일·스크립트로 고친 경우 탐지).
        if d["evidence"] and evidence_hash(d["evidence"]) != d["evidence_hash"]:
            out.append({"code": "EVIDENCE_HASH_MISMATCH",
                        "reason": "근거 내용이 등록 시점과 다릅니다(지문 불일치) — 재현할 수 없습니다."})
        unverified = [k for k, v in (d["evidence"] or {}).items()
                      if isinstance(v, dict) and v.get("verified") is False]
        if unverified:
            out.append({"code": "UNVERIFIED_EVIDENCE",
                        "reason": f"검증되지 않은 핵심 근거가 있습니다: {sorted(unverified)}"})
        if not d["baseline_id"]:
            out.append({"code": "NO_BASELINE",
                        "reason": "기준선이 없습니다 — 무엇과 비교해 결정하는지 알 수 없습니다."})
        # ⚠️ **중복을 제거한다.** 한 사람이 요청자이면서 결정자인 안건은 흔하고, 그때
        #   `participant_response` 는 그 사용자의 모든 역할 행을 함께 갱신한다(한 사람의 의견은
        #   하나다). 그대로 모으면 화면에 같은 이름이 두 번 찍히고 — 2026-08-04 화면 실측에서
        #   `['hikwon@lsmnm.com', 'hikwon@lsmnm.com']` 로 나왔다 — 읽는 사람은 두 사람이
        #   정보 부족을 답한 것으로 오해한다. 차단 사유는 **누가 몇 명인지**가 정보다.
        need_info = sorted({p["user_id"] for p in d.get("participants", [])
                            if p.get("response_status") == RESPONSE_NEED_INFO})
        if need_info:
            out.append({"code": "PARTICIPANT_NEEDS_INFO",
                        "reason": f"정보 부족을 답한 참여자가 있습니다: {need_info}"})
        return out

    @staticmethod
    def _row(row: Dict[str, Any], today: str = "") -> Dict[str, Any]:
        d = dict(row)
        for src, dst in (("package_json", "package"), ("evidence_json", "evidence")):
            try:
                d[dst] = json.loads(d.pop(src) or "{}")
            except Exception:
                d[dst] = {}
        d["overdue"] = False
        if d.get("due_at"):
            try:
                ref = date.fromisoformat(today) if today else datetime.now(timezone.utc).date()
                d["overdue"] = date.fromisoformat(d["due_at"]) < ref and d["status"] not in (
                    DECIDED, ACTIONED, EFFECT_MEASURED, CANCELLED)
            except ValueError:
                pass
        return d

    @staticmethod
    def _meeting_row(m: Dict[str, Any]) -> Dict[str, Any]:
        d = dict(m)
        try:
            d["agenda"] = json.loads(d.pop("agenda_json") or "{}")
        except Exception:
            d["agenda"] = {}
        d["external_created"] = bool(d.get("external_ref"))
        if not d["external_created"]:
            d["note"] = "외부 캘린더에는 아직 만들어지지 않았습니다 — 사람이 만들어야 합니다."
        return d

    @staticmethod
    def _notify(event: str, case: Dict[str, Any], actor: str) -> None:
        """[CL-4] 참여자에게만 알린다. **본문·참여자 명단을 싣지 않는다** — ID·상태·시각뿐이다.

        ★ 수신자를 `participants` 에서 계산한다. `queue()` 와 같은 규칙이어야 하며, 두 곳이
          갈라지면 알림이 목록보다 넓어진다(= 안 보이는 안건의 알림이 온다)."""
        collaboration_events.emit(
            event, collaboration_events.decision_recipients(case),
            {"id": case["decision_id"], "status": case["status"],
             "at": case["updated_at"], "title": case["question"],
             "actor": actor, "version": case["package_version"]})

    def _audit(self, event: str, subject_id: str, actor: str, decision: str = "",
               rationale: str = "", evidence: Optional[List[Any]] = None,
               tenant_id: str = "tenant_default", scope: str = "") -> None:
        """원장 기록. **실패를 삼키지 않는다** — 근거 없는 결정이 남으면 안 된다."""
        self._ledger.append(event, subject_type="decision_case", subject_id=subject_id,
                            actor_type="user", actor_id=actor or "", decision=decision,
                            rationale=rationale, evidence_refs=evidence or [],
                            tenant_id=tenant_id, enterprise_scope_id=scope)


def _sections(pkg: Dict[str, Any], spec: List[tuple]) -> List[Dict[str, Any]]:
    """관점별 섹션을 만든다. **없는 항목을 지어내지 않고 `missing` 으로 표시한다.**

    ⚠️ 빈 섹션을 숨기면 검토자는 그 항목이 검토됐다고 믿는다. 비어 있음을 보여야 "이건 아직
      안 채웠다"를 알 수 있다(도메인 §7.2 필수 내용 표)."""
    out = []
    for key, label in spec:
        val = pkg.get(key)
        out.append({"key": key, "label": label, "value": val,
                    "missing": val in (None, "", [], {})})
    return out


decision_case = DecisionCase()
