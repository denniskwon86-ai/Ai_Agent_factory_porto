"""[CL-3] 대내외 보고 발간 — **내보낸 것은 되돌릴 수 없다.**

## 이 모듈이 존재하는 이유 (설계 §8 · 작업서 §CL-BE-04)

앞 단계(CL-2)까지는 회사 안에서 일어난다. 틀렸으면 다시 하면 된다. 발간은 다르다 — 대외로
나간 숫자는 회수해도 이미 읽힌 뒤다. 그래서 이 모듈의 규칙은 전부 **"나가기 전에 막는다"**
한 방향이다.

### 막는 것 넷

1. **렌더 실패를 발간 준비 완료로 두지 않는다**(§9 완료조건). 렌더가 실패했는데 상태가
   `RENDERED` 로 올라가면, 사람은 "만들어졌다"고 믿고 승인 버튼을 누른다. 그리고 승인된 것은
   내용이 없는 문서다. → 실패는 `DRAFT` 에 머물고 `render_error` 를 남긴다.
2. **EXTERNAL 은 두 승인 전에 API 자체가 막힌다.** 화면 버튼만 막으면 URL 을 아는 사람은
   그대로 게시할 수 있다. `EXECUTIVE` 와 `LEGAL_DISCLOSURE` 가 **둘 다** `APPROVED` 여야 한다.
   INTERNAL 승인 하나로 EXTERNAL 을 내보낼 수 없다.
3. **게시 실패를 성공으로 저장하지 않는다**(작업서 §5.1 `publication_distributions`).
   외부 어댑터가 실패했는데 `PUBLISHED` 로 기록하면, 아무 데도 안 나간 문서를 "발간했다"고
   믿는다. → 실패는 `FAILED` 배포 기록으로 남고 발간물은 `APPROVED` 에 머문다.
4. **발간 후 원천이 바뀌어도 덮어쓰지 않는다**(설계 §8.2-6). 정정판을 **새 버전**으로 만들고
   원본은 그대로 둔다. 읽은 사람이 본 문서가 사라지면 "무엇을 근거로 판단했는가"에 답할 수 없다.

### 제외 항목을 숨기지 않는다

대외 발간은 기밀·개인정보·재배포 금지 데이터를 빼야 한다(설계 §8.2-4). 그런데 **조용히 빼면
안 된다.** 무엇을 왜 뺐는지가 남지 않으면, 나중에 "이 보고서에 그 숫자가 왜 없는가"에 아무도
답할 수 없고, 다음 사람은 빠진 줄 모르고 그대로 인용한다.
→ `redaction_policy_json.excluded` 에 **항목과 사유를 함께** 남기고, 문서에도 그대로 싣는다
  (설계 §8.4 "공개 제외 항목과 제외 사유").

LLM 0콜 — 렌더링은 원천 데이터의 결정론적 투영이다.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Callable, Dict, List, Optional

from core.collaboration_store import canonical_json, collaboration_store, now_iso
from core.collaboration_events import (PUBLICATION_REVIEW_REQUESTED, PUBLICATION_UPDATED,
                                       collaboration_events)

# ── 상태 ─────────────────────────────────────────────────────────────────────
DRAFT = "DRAFT"
RENDERED = "RENDERED"
REVIEW_REQUESTED = "REVIEW_REQUESTED"
APPROVED = "APPROVED"
PUBLISHED = "PUBLISHED"
CORRECTED = "CORRECTED"
WITHDRAWN = "WITHDRAWN"

#: 독자. **INTERNAL 과 EXTERNAL 을 하나의 값으로 뭉개지 않는다** — 게이트가 다르다.
AUDIENCE_INTERNAL = "INTERNAL"
AUDIENCE_EXTERNAL = "EXTERNAL"
AUDIENCES = (AUDIENCE_INTERNAL, AUDIENCE_EXTERNAL)

#: 발간 유형(설계 §8.1).
PUB_TYPES = ("OPERATIONAL", "MANAGEMENT", "COMPANY_WIDE", "EXTERNAL_LIMITED", "EXTERNAL_PUBLIC")

#: 검토 종류. EXTERNAL 은 아래 둘이 **필수**다.
REVIEW_EXECUTIVE = "EXECUTIVE"
REVIEW_LEGAL = "LEGAL_DISCLOSURE"
REVIEW_SECURITY = "SECURITY"
REVIEW_DATA_OWNER = "DATA_OWNER"
REVIEW_TYPES = (REVIEW_EXECUTIVE, REVIEW_LEGAL, REVIEW_SECURITY, REVIEW_DATA_OWNER)
#: ★ 대외 발간의 두 관문. 하나만으로는 나갈 수 없다(작업서 §CL-BE-04).
EXTERNAL_REQUIRED_REVIEWS = (REVIEW_EXECUTIVE, REVIEW_LEGAL)

REVIEW_PENDING = "PENDING"
REVIEW_APPROVED = "APPROVED"
REVIEW_REJECTED = "REJECTED"
REVIEW_STATUSES = (REVIEW_PENDING, REVIEW_APPROVED, REVIEW_REJECTED)

#: 원천. **선택지를 열어 두지 않는다** — 어디서 왔는지 모르는 발간물은 근거를 되짚을 수 없다.
SOURCE_DECISION = "DECISION_CASE"
SOURCE_SIMULATION = "SIMULATION_RUN"
SOURCE_TYPES = (SOURCE_DECISION, SOURCE_SIMULATION)

#: 보안등급.
SECURITY_CLASSES = ("PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED")

#: 대외 발간에서 **반드시 빼야 하는** 항목 키. 원천 문서에 이 키가 있으면 제외하고 사유를 남긴다.
#: ⚠️ 목록을 늘리는 것은 쉽지만 줄이는 것은 위험하다 — 줄이려면 법무 검토를 근거로 남길 것.
EXTERNAL_REDACT_KEYS = (
    "financial_impact",   # 손익·현금은 공시 전 대외로 나갈 수 없다
    "dissent",            # 내부 반대 의견은 대외 문서의 내용이 아니다
    "compliance_risk",    # 규정 리스크 원문은 법무 검토 없이 나갈 수 없다
    "approval_conditions",  # 승인 조건은 내부 통제 정보다
    "open_risks",
)


class PublicationError(ValueError):
    """정책 위반 — 라우트가 400 으로 바꾼다."""


class PublicationNotFound(LookupError):
    """없거나 볼 수 없다 — 라우트가 **404** 로 바꾼다(존재를 알리지 않는다)."""


class RenderFailed(PublicationError):
    """렌더 실패. **상태를 올리지 않는다** — 실패한 문서를 승인 대기로 두면 빈 문서가 승인된다."""


_DDL = """
CREATE TABLE IF NOT EXISTS publications (
    publication_id   TEXT PRIMARY KEY,
    tenant_id        TEXT NOT NULL DEFAULT 'tenant_default',
    scope_id         TEXT NOT NULL DEFAULT '',
    title            TEXT NOT NULL,
    publication_type TEXT NOT NULL DEFAULT 'OPERATIONAL',
    audience         TEXT NOT NULL DEFAULT 'INTERNAL',
    security_class   TEXT NOT NULL DEFAULT 'INTERNAL',
    source_type      TEXT NOT NULL DEFAULT '',
    source_id        TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'DRAFT',
    document_version INTEGER NOT NULL DEFAULT 0,
    render_error     TEXT NOT NULL DEFAULT '',
    embargo_at       TEXT NOT NULL DEFAULT '',
    published_at     TEXT NOT NULL DEFAULT '',
    supersedes_id    TEXT NOT NULL DEFAULT '',
    withdrawn_reason TEXT NOT NULL DEFAULT '',
    created_by       TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pub_status ON publications(status);
CREATE INDEX IF NOT EXISTS idx_pub_scope ON publications(scope_id);

CREATE TABLE IF NOT EXISTS publication_versions (
    version_id       TEXT PRIMARY KEY,
    publication_id   TEXT NOT NULL,
    version_no       INTEGER NOT NULL,
    document_ast_json TEXT NOT NULL DEFAULT '{}',
    rendered_files_json TEXT NOT NULL DEFAULT '[]',
    evidence_hash    TEXT NOT NULL DEFAULT '',
    redaction_policy_json TEXT NOT NULL DEFAULT '{}',
    approval_snapshot_json TEXT NOT NULL DEFAULT '{}',
    supersedes_version_id TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pubver_pub ON publication_versions(publication_id);

CREATE TABLE IF NOT EXISTS publication_reviews (
    publication_id   TEXT NOT NULL,
    review_type      TEXT NOT NULL,
    reviewer_id      TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'PENDING',
    comment          TEXT NOT NULL DEFAULT '',
    document_version INTEGER NOT NULL DEFAULT 0,
    requested_at     TEXT NOT NULL DEFAULT '',
    reviewed_at      TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (publication_id, review_type)
);

CREATE TABLE IF NOT EXISTS publication_distributions (
    distribution_id  TEXT PRIMARY KEY,
    publication_id   TEXT NOT NULL,
    target           TEXT NOT NULL DEFAULT '',
    channel          TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'PENDING',
    external_ref     TEXT NOT NULL DEFAULT '',
    error            TEXT NOT NULL DEFAULT '',
    document_version INTEGER NOT NULL DEFAULT 0,
    published_at     TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pubdist_pub ON publication_distributions(publication_id);
"""


def evidence_hash(obj: Any) -> str:
    """근거 지문. 정렬된 canonical JSON 이므로 키 순서가 달라도 같은 지문이다."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()[:32]


class Publication:
    def __init__(self, store=None, ledger=None, decision_source=None):
        self._store_override = store
        self._ledger_override = ledger
        # 원천 조회를 주입 가능하게 둔다 — 테스트가 실제 Decision DB 에 의존하지 않게.
        self._decision_source = decision_source

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
        self._store.ensure_schema()
        conn = self._store._connect()
        try:
            conn.executescript(_DDL)
            conn.commit()
        finally:
            conn.close()

    # ── 생성 ──────────────────────────────────────────────────────────────
    def create(self, title: str, created_by: str, source_type: str, source_id: str,
               audience: str = AUDIENCE_INTERNAL, publication_type: str = "OPERATIONAL",
               security_class: str = "INTERNAL", scope_id: str = "", embargo_at: str = "",
               tenant_id: str = "tenant_default") -> Dict[str, Any]:
        """발간 초안을 만든다.

        ⚠️ 원천(`source_type`/`source_id`)을 **필수**로 받는다. 원천 없는 발간물은 숫자의 출처를
          되짚을 수 없고, 그때 보고서는 "누군가 적어 넣은 값"이 된다(설계 §8.2-5)."""
        self._ensure()
        if not (title or "").strip():
            raise PublicationError("제목은 필수입니다.")
        if not (created_by or "").strip():
            raise PublicationError("작성자가 필요합니다.")
        if source_type not in SOURCE_TYPES:
            raise PublicationError(f"source_type 은 {SOURCE_TYPES} 중 하나여야 합니다: {source_type}")
        if not (source_id or "").strip():
            raise PublicationError(
                "원천 ID 가 없습니다 — 원천 없는 발간물은 숫자의 출처를 되짚을 수 없습니다.")
        if audience not in AUDIENCES:
            raise PublicationError(f"audience 는 {AUDIENCES} 중 하나여야 합니다: {audience}")
        if publication_type not in PUB_TYPES:
            raise PublicationError(f"publication_type 은 {PUB_TYPES} 중 하나여야 합니다.")
        if security_class not in SECURITY_CLASSES:
            raise PublicationError(f"security_class 는 {SECURITY_CLASSES} 중 하나여야 합니다.")
        pid = f"pub_{uuid.uuid4().hex[:12]}"
        now = now_iso()
        self._store.execute(
            "INSERT INTO publications (publication_id, tenant_id, scope_id, title, "
            "publication_type, audience, security_class, source_type, source_id, status, "
            "document_version, embargo_at, created_by, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?,?,?)",
            (pid, tenant_id, scope_id, title.strip(), publication_type, audience, security_class,
             source_type, source_id.strip(), DRAFT, embargo_at, created_by, now, now))
        # ★★ 원장 기록이 실패하면 **행을 되돌린다.** 2026-08-04 실측에서 이것이 없어
        #   `PUBLICATION_CREATED` 미등록으로 원장이 거부했는데 발간물 행은 그대로 남았다 —
        #   원장에 없는 발간물이 DB 에 존재하게 되고, 그 순간 "모든 발간 이벤트를 원장에
        #   기록한다"는 규칙은 사실이 아니게 된다. 없는 편이 낫다.
        try:
            self._audit("PUBLICATION_CREATED", pid, created_by,
                        decision=f"{audience} 발간 초안: {title.strip()[:150]}",
                        rationale=f"원천 {source_type} {source_id}",
                        tenant_id=tenant_id, scope=scope_id)
        except Exception:
            self._store.execute("DELETE FROM publications WHERE publication_id=?", (pid,))
            raise
        return self.get(pid, created_by)

    # ── 조회 ──────────────────────────────────────────────────────────────
    def get(self, publication_id: str, user_id: str = "") -> Dict[str, Any]:
        self._ensure()
        row = self._store.one("SELECT * FROM publications WHERE publication_id=?",
                              (publication_id,))
        if not row:
            raise PublicationNotFound(publication_id)
        p = dict(row)
        p["versions"] = [self._version_row(v) for v in self._store.query(
            "SELECT * FROM publication_versions WHERE publication_id=? ORDER BY version_no DESC",
            (publication_id,))]
        p["current_version"] = p["versions"][0] if p["versions"] else None
        p["reviews"] = self._store.query(
            "SELECT * FROM publication_reviews WHERE publication_id=? ORDER BY review_type",
            (publication_id,))
        p["distributions"] = self._store.query(
            "SELECT * FROM publication_distributions WHERE publication_id=? ORDER BY created_at",
            (publication_id,))
        p["gates"] = self._gates(p)
        p["blockers"] = [g for g in p["gates"] if not g["passed"]]
        p["can_publish"] = not p["blockers"] and p["status"] == APPROVED
        return p

    def list(self, scope_id: str = "", audience: str = "", status: str = "") -> List[Dict[str, Any]]:
        """유형·독자·상태별 검색(설계 §10.3)."""
        self._ensure()
        sql = "SELECT * FROM publications WHERE 1=1"
        params: List[Any] = []
        if scope_id:
            sql += " AND scope_id=?"
            params.append(scope_id)
        if audience:
            sql += " AND audience=?"
            params.append(audience)
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY created_at DESC"
        rows = self._store.query(sql, tuple(params))
        out = []
        for r in rows:
            d = dict(r)
            d["gates"] = self._gates({**d, "reviews": self._store.query(
                "SELECT * FROM publication_reviews WHERE publication_id=?",
                (d["publication_id"],))})
            d["blockers"] = [g for g in d["gates"] if not g["passed"]]
            out.append(d)
        return out

    # ── 렌더 ──────────────────────────────────────────────────────────────
    def render(self, publication_id: str, actor: str,
               renderer: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
               ) -> Dict[str, Any]:
        """원천에서 구조화 문서를 만든다. **실패하면 상태를 올리지 않는다.**

        ★ 승인 이후에는 렌더하지 않는다. 승인된 문서의 내용이 나중에 바뀌면 승인자가 본 문서와
          발간된 문서가 달라지고, 그 승인은 아무것도 보증하지 않는다."""
        p = self.get(publication_id, actor)
        if p["status"] in (PUBLISHED, WITHDRAWN):
            raise PublicationError(f"{p['status']} 상태에서는 다시 렌더할 수 없습니다 — "
                                   f"정정판을 만드십시오.")
        if p["status"] == APPROVED:
            raise PublicationError(
                "승인된 문서는 다시 렌더할 수 없습니다 — 승인자가 본 문서와 발간될 문서가 "
                "달라집니다. 정정판을 만드십시오.")
        now = now_iso()
        try:
            source = self._load_source(p)
            doc = (renderer or self._default_render)(
                {"publication": p, "source": source})
            if not doc or not doc.get("sections"):
                raise RenderFailed(
                    "렌더 결과에 내용이 없습니다 — 원천에서 실을 수 있는 항목을 찾지 못했습니다.")
        except PublicationNotFound:
            # 원천이 사라졌다. 이것도 렌더 실패다 — 빈 문서를 만들지 않는다.
            err = f"원천 {p['source_type']} {p['source_id']} 을(를) 찾을 수 없습니다."
            self._fail_render(publication_id, err, now)
            raise RenderFailed(err)
        except PublicationError as e:
            self._fail_render(publication_id, str(e), now)
            raise
        except Exception as e:  # 어댑터·데이터 오류 전부 동일하게 다룬다
            err = f"렌더 실패: {type(e).__name__}: {e}"
            self._fail_render(publication_id, err, now)
            raise RenderFailed(err)

        redaction = doc.get("redaction", {"excluded": []})
        ver_no = int(p["document_version"] or 0) + 1
        vid = f"pv_{uuid.uuid4().hex[:12]}"
        prev = p["current_version"]["version_id"] if p["current_version"] else ""
        h = evidence_hash(doc.get("evidence", {}))
        self._store.executemany_tx([
            ("INSERT INTO publication_versions (version_id, publication_id, version_no, "
             "document_ast_json, rendered_files_json, evidence_hash, redaction_policy_json, "
             "approval_snapshot_json, supersedes_version_id, created_at) "
             "VALUES (?,?,?,?,?,?,?,'{}',?,?)",
             (vid, publication_id, ver_no, canonical_json(doc),
              canonical_json(doc.get("files", [])), h, canonical_json(redaction), prev, now)),
            ("UPDATE publications SET status=?, document_version=?, render_error='', updated_at=? "
             "WHERE publication_id=?", (RENDERED, ver_no, now, publication_id)),
            # ★ 문서가 새로 렌더되면 이전 승인은 **무효다.** 승인자가 본 문서가 아니기 때문이다.
            ("DELETE FROM publication_reviews WHERE publication_id=?", (publication_id,)),
        ])
        self._audit("PUBLICATION_RENDERED", publication_id, actor,
                    decision=f"v{ver_no} 렌더 완료",
                    rationale=f"제외 항목 {len(redaction.get('excluded', []))}건",
                    evidence=[{"evidence_hash": h, "version_id": vid}],
                    tenant_id=p["tenant_id"], scope=p["scope_id"])
        out = self.get(publication_id, actor)
        self._notify(PUBLICATION_UPDATED, out, actor)
        return out

    def _fail_render(self, publication_id: str, err: str, now: str) -> None:
        """★ 실패는 `DRAFT` 에 머무르고 사유를 남긴다. 상태를 올리면 빈 문서가 승인된다."""
        self._store.execute(
            "UPDATE publications SET status=?, render_error=?, updated_at=? WHERE publication_id=?",
            (DRAFT, err[:500], now, publication_id))

    # ── 승인 게이트 ───────────────────────────────────────────────────────
    def request_approval(self, publication_id: str, actor: str,
                         review_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """검토를 요청한다. **EXTERNAL 은 두 검토가 자동으로 포함된다.**

        ⚠️ 요청자가 대외 발간에서 법무 검토를 빼는 것을 허용하지 않는다 — 뺄 수 있으면 언젠가
          바쁜 날에 빠진다."""
        p = self.get(publication_id, actor)
        if p["status"] not in (RENDERED, REVIEW_REQUESTED):
            raise PublicationError(
                f"{p['status']} 상태에서는 검토를 요청할 수 없습니다 — 렌더 후에 요청합니다.")
        types = list(review_types or [])
        for t in types:
            if t not in REVIEW_TYPES:
                raise PublicationError(f"review_type 은 {REVIEW_TYPES} 중 하나여야 합니다: {t}")
        if p["audience"] == AUDIENCE_EXTERNAL:
            for t in EXTERNAL_REQUIRED_REVIEWS:
                if t not in types:
                    types.append(t)
        if not types:
            raise PublicationError("요청할 검토가 없습니다.")
        now = now_iso()
        stmts = [("INSERT OR IGNORE INTO publication_reviews (publication_id, review_type, "
                  "status, document_version, requested_at) VALUES (?,?,?,?,?)",
                  (publication_id, t, REVIEW_PENDING, p["document_version"], now))
                 for t in types]
        stmts.append(("UPDATE publications SET status=?, updated_at=? WHERE publication_id=?",
                      (REVIEW_REQUESTED, now, publication_id)))
        self._store.executemany_tx(stmts)
        self._audit("PUBLICATION_REVIEW_REQUESTED", publication_id, actor,
                    decision=f"검토 요청 {sorted(types)}",
                    rationale=f"{p['audience']} · v{p['document_version']}",
                    tenant_id=p["tenant_id"], scope=p["scope_id"])
        out = self.get(publication_id, actor)
        self._notify(PUBLICATION_REVIEW_REQUESTED, out, actor)
        return out

    def approve(self, publication_id: str, actor: str, review_type: str,
                status: str = REVIEW_APPROVED, comment: str = "") -> Dict[str, Any]:
        """검토자가 판정한다.

        ⚠️ 반려에는 사유가 필요하다 — 사유 없는 반려는 작성자가 무엇을 고쳐야 하는지 모른다."""
        p = self.get(publication_id, actor)
        if review_type not in REVIEW_TYPES:
            raise PublicationError(f"review_type 은 {REVIEW_TYPES} 중 하나여야 합니다.")
        if status not in (REVIEW_APPROVED, REVIEW_REJECTED):
            raise PublicationError(f"status 는 {REVIEW_APPROVED}/{REVIEW_REJECTED} 중 하나입니다.")
        row = self._store.one(
            "SELECT * FROM publication_reviews WHERE publication_id=? AND review_type=?",
            (publication_id, review_type))
        if not row:
            raise PublicationError(f"{review_type} 검토가 요청되지 않았습니다.")
        if status == REVIEW_REJECTED and not (comment or "").strip():
            raise PublicationError(
                "반려에는 사유가 필요합니다 — 사유 없는 반려는 무엇을 고쳐야 하는지 알려주지 "
                "못합니다.")
        # ★ 승인은 **그 버전에 대한 것**이다. 이후 다시 렌더되면 승인은 지워진다(render 참조).
        if int(row["document_version"] or 0) != int(p["document_version"] or 0):
            raise PublicationError(
                f"검토 요청 당시 문서(v{row['document_version']})와 현재 문서"
                f"(v{p['document_version']})가 다릅니다 — 다시 검토를 요청하십시오.")
        now = now_iso()
        self._store.execute(
            "UPDATE publication_reviews SET reviewer_id=?, status=?, comment=?, reviewed_at=? "
            "WHERE publication_id=? AND review_type=?",
            (actor, status, (comment or "").strip(), now, publication_id, review_type))
        after = self.get(publication_id, actor)
        # 모든 요청된 검토가 승인되면 APPROVED 로 올린다. 하나라도 반려면 올리지 않는다.
        if status == REVIEW_APPROVED and not after["blockers"] and after["status"] == REVIEW_REQUESTED:
            self._store.execute(
                "UPDATE publications SET status=?, updated_at=? WHERE publication_id=?",
                (APPROVED, now, publication_id))
        # ★ 승인과 반려를 **같은 이벤트로 남기지 않는다.** 원장에서 둘이 구분되지 않으면
        #   "법무가 승인했다"와 "법무가 반려했다"가 같은 줄로 보인다.
        self._audit("PUBLICATION_APPROVED" if status == REVIEW_APPROVED
                    else "PUBLICATION_REJECTED", publication_id, actor,
                    decision=f"{review_type}={status}",
                    rationale=(comment or "").strip()[:200],
                    tenant_id=p["tenant_id"], scope=p["scope_id"])
        out = self.get(publication_id, actor)
        self._notify(PUBLICATION_UPDATED, out, actor)
        return out

    # ── 게시 ──────────────────────────────────────────────────────────────
    def publish(self, publication_id: str, actor: str, targets: List[Dict[str, str]],
                adapter: Optional[Callable[[Dict[str, Any], Dict[str, str]], str]] = None
                ) -> Dict[str, Any]:
        """승인 완료 후 배포한다.

        ★★ **게시 실패를 성공으로 저장하지 않는다**(작업서 §5.1). 어댑터가 실패하면 배포 기록은
          `FAILED` 로 남고 발간물은 `APPROVED` 에 머문다 — 아무 데도 안 나간 문서를 "발간했다"고
          믿는 것이 이 규칙이 막는 사고다.
        ⚠️ 어댑터가 없으면 게시하지 않는다. 외부 시스템에 실제로 쓰는 일은 사람이 붙인 어댑터가
          있을 때만 일어난다(§3-7)."""
        p = self.get(publication_id, actor)
        # ★ 게이트를 **상태 검사보다 먼저** 본다. 순서가 반대면 "APPROVED 가 아닙니다"만 나오고,
        #   정작 중요한 이유("법무 검토가 아직입니다")는 사용자에게 도달하지 않는다.
        if p["blockers"]:
            raise PublicationError(
                "발간을 막는 조건이 있습니다: " + " / ".join(b["reason"] for b in p["blockers"]))
        if p["status"] != APPROVED:
            raise PublicationError(
                f"{p['status']} 상태에서는 발간할 수 없습니다 — 승인 완료 후에 발간합니다.")
        if not targets:
            raise PublicationError("배포 대상이 없습니다.")
        now = now_iso()
        results, failures = [], []
        for t in targets:
            did = f"pd_{uuid.uuid4().hex[:12]}"
            target = str(t.get("target", "")).strip()
            channel = str(t.get("channel", "")).strip()
            if not target:
                raise PublicationError("배포 대상(target)이 비어 있습니다.")
            if adapter is None:
                # 어댑터가 없으면 **실패로 기록한다.** '성공한 척'이 가장 위험하다.
                self._store.execute(
                    "INSERT INTO publication_distributions (distribution_id, publication_id, "
                    "target, channel, status, error, document_version, created_at) "
                    "VALUES (?,?,?,?,'FAILED',?,?,?)",
                    (did, publication_id, target, channel,
                     "게시 어댑터가 연결되지 않았습니다 — 외부 시스템에 실제로 보내지 못했습니다.",
                     p["document_version"], now))
                failures.append(target)
                continue
            try:
                ref = adapter(p, t) or ""
                self._store.execute(
                    "INSERT INTO publication_distributions (distribution_id, publication_id, "
                    "target, channel, status, external_ref, document_version, published_at, "
                    "created_at) VALUES (?,?,?,?,'PUBLISHED',?,?,?,?)",
                    (did, publication_id, target, channel, str(ref),
                     p["document_version"], now, now))
                results.append(target)
            except Exception as e:
                self._store.execute(
                    "INSERT INTO publication_distributions (distribution_id, publication_id, "
                    "target, channel, status, error, document_version, created_at) "
                    "VALUES (?,?,?,?,'FAILED',?,?,?)",
                    (did, publication_id, target, channel,
                     f"{type(e).__name__}: {e}"[:500], p["document_version"], now))
                failures.append(target)

        if results and not failures:
            self._store.execute(
                "UPDATE publications SET status=?, published_at=?, updated_at=? "
                "WHERE publication_id=?", (PUBLISHED, now, now, publication_id))
        self._audit("PUBLICATION_PUBLISHED" if results and not failures
                    else "PUBLICATION_PUBLISH_FAILED", publication_id, actor,
                    decision=f"성공 {len(results)} · 실패 {len(failures)}",
                    rationale=f"대상 {[t.get('target') for t in targets]}",
                    tenant_id=p["tenant_id"], scope=p["scope_id"])
        out = self.get(publication_id, actor)
        self._notify(PUBLICATION_UPDATED, out, actor)
        if failures:
            # ⚠️ 부분 실패를 성공으로 뭉개지 않는다. 어디로 안 나갔는지가 사용자가 할 일이다.
            out["note"] = (f"배포 실패 {len(failures)}건({', '.join(failures)}) — 발간 상태를 "
                           f"올리지 않았습니다. 원인을 해소한 뒤 다시 시도하십시오.")
        return out

    # ── 정정·회수 ─────────────────────────────────────────────────────────
    def correct(self, publication_id: str, actor: str, reason: str) -> Dict[str, Any]:
        """정정판을 만든다. **원본을 덮어쓰지 않는다**(설계 §8.2-6).

        ★ 새 발간물을 만들고 원본을 `CORRECTED` 로 표시한다. 원본이 사라지면 그것을 읽고 판단한
          사람이 무엇을 봤는지 아무도 말할 수 없다."""
        p = self.get(publication_id, actor)
        if p["status"] not in (PUBLISHED, CORRECTED):
            raise PublicationError(
                f"{p['status']} 상태에서는 정정판을 만들 수 없습니다 — 발간된 문서만 정정합니다.")
        if not (reason or "").strip():
            raise PublicationError(
                "정정 사유는 필수입니다 — 무엇이 왜 틀렸는지 없으면 읽은 사람이 자신의 판단을 "
                "고칠 수 없습니다.")
        new = self.create(
            title=f"{p['title']} (정정판)", created_by=actor, source_type=p["source_type"],
            source_id=p["source_id"], audience=p["audience"],
            publication_type=p["publication_type"], security_class=p["security_class"],
            scope_id=p["scope_id"], tenant_id=p["tenant_id"])
        now = now_iso()
        self._store.executemany_tx([
            ("UPDATE publications SET supersedes_id=?, updated_at=? WHERE publication_id=?",
             (publication_id, now, new["publication_id"])),
            ("UPDATE publications SET status=?, updated_at=? WHERE publication_id=?",
             (CORRECTED, now, publication_id)),
        ])
        self._audit("PUBLICATION_CORRECTED", publication_id, actor,
                    decision=f"정정판 {new['publication_id']} 생성",
                    rationale=reason.strip(),
                    evidence=[{"supersedes": publication_id}],
                    tenant_id=p["tenant_id"], scope=p["scope_id"])
        out = self.get(new["publication_id"], actor)
        out["note"] = ("원본은 보존되고 «정정됨»으로 표시됩니다 — 원본을 지우면 그것을 읽고 "
                       "판단한 사람이 무엇을 봤는지 말할 수 없습니다.")
        return out

    def withdraw(self, publication_id: str, actor: str, reason: str) -> Dict[str, Any]:
        """회수한다. **이력은 남는다.**

        ⚠️ 회수는 "없던 일"이 아니다. 이미 읽은 사람이 있고, 그 사람이 무엇을 읽었는지는 계속
          남아야 한다."""
        p = self.get(publication_id, actor)
        if p["status"] == WITHDRAWN:
            return p
        if not (reason or "").strip():
            raise PublicationError("회수 사유는 필수입니다 — 이미 읽은 사람에게 남는 기록입니다.")
        now = now_iso()
        self._store.execute(
            "UPDATE publications SET status=?, withdrawn_reason=?, updated_at=? "
            "WHERE publication_id=?", (WITHDRAWN, reason.strip(), now, publication_id))
        self._audit("PUBLICATION_WITHDRAWN", publication_id, actor,
                    decision="발간 회수", rationale=reason.strip(),
                    tenant_id=p["tenant_id"], scope=p["scope_id"])
        out = self.get(publication_id, actor)
        out["note"] = ("회수했습니다. 배포 이력과 버전은 그대로 남습니다 — 이미 읽은 사람이 "
                       "무엇을 읽었는지는 지울 수 없습니다.")
        self._notify(PUBLICATION_UPDATED, out, actor)
        return out

    # ── 내부 ──────────────────────────────────────────────────────────────
    @staticmethod
    def _gates(p: Dict[str, Any]) -> List[Dict[str, Any]]:
        """발간 게이트. **`passed: False` 가 하나라도 있으면 발간할 수 없다.**

        ★ 게이트를 '경고'가 아니라 목록으로 돌려주는 이유: 화면이 이유를 그대로 쓸 수 있어야
          한다. 버튼만 비활성화하면 사용자는 화면 고장으로 읽는다."""
        reviews = {r["review_type"]: r for r in (p.get("reviews") or [])}
        out: List[Dict[str, Any]] = []
        rendered = int(p.get("document_version") or 0) > 0
        out.append({
            "code": "RENDERED", "label": "문서 렌더링",
            "passed": rendered,
            "reason": "" if rendered else (
                p.get("render_error") or "아직 렌더되지 않았습니다 — 내용이 없는 문서는 승인·발간할 수 없습니다."),
        })
        required = list(EXTERNAL_REQUIRED_REVIEWS) if p.get("audience") == AUDIENCE_EXTERNAL else []
        for t in required:
            r = reviews.get(t)
            ok = bool(r and r["status"] == REVIEW_APPROVED)
            out.append({
                "code": f"REVIEW_{t}", "label": {"EXECUTIVE": "책임 임원 승인",
                                                 "LEGAL_DISCLOSURE": "법무·공시 검토"}[t],
                "passed": ok,
                "reason": "" if ok else (
                    f"{t} 검토가 요청되지 않았습니다 — 대외 발간에는 필수입니다." if not r
                    else f"{t} 검토가 «{r['status']}» 입니다."),
            })
        # 요청된 검토 중 반려가 있으면 독자와 무관하게 막는다.
        for t, r in reviews.items():
            if r["status"] == REVIEW_REJECTED:
                out.append({"code": f"REJECTED_{t}", "label": f"{t} 반려",
                            "passed": False,
                            "reason": f"{t} 검토가 반려됐습니다: {r['comment'] or '(사유 없음)'}"})
            elif t not in required and r["status"] == REVIEW_PENDING:
                out.append({"code": f"PENDING_{t}", "label": f"{t} 검토 대기",
                            "passed": False,
                            "reason": f"{t} 검토가 아직 끝나지 않았습니다."})
        return out

    def _load_source(self, p: Dict[str, Any]) -> Dict[str, Any]:
        """원천을 읽는다. 없으면 `PublicationNotFound` — 빈 문서를 만들지 않는다."""
        if self._decision_source is not None:
            src = self._decision_source(p["source_type"], p["source_id"])
            if not src:
                raise PublicationNotFound(p["source_id"])
            return src
        if p["source_type"] == SOURCE_DECISION:
            from core.decision_case import DecisionNotFound, decision_case
            try:
                return decision_case.get(p["source_id"], p["created_by"])
            except DecisionNotFound:
                raise PublicationNotFound(p["source_id"])
        raise PublicationError(
            f"{p['source_type']} 원천의 렌더러가 아직 없습니다 — 지어내지 않고 실패로 둡니다.")

    @staticmethod
    def _default_render(ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Decision Package → 구조화 문서. **LLM 0콜, 결정론적 투영.**

        ★ EXTERNAL 이면 민감 항목을 빼고 **무엇을 왜 뺐는지 함께 싣는다**(설계 §8.4).
          조용히 빼면 다음 사람은 빠진 줄 모르고 그대로 인용한다."""
        p = ctx["publication"]
        s = ctx["source"] or {}
        external = p["audience"] == AUDIENCE_EXTERNAL
        pkg = s.get("package") or {}
        sections, excluded = [], []
        for key, value in sorted(pkg.items()):
            if value in (None, "", [], {}):
                continue
            if external and key in EXTERNAL_REDACT_KEYS:
                excluded.append({"key": key,
                                 "reason": "대외 발간 제외 항목 — 내부 통제·손익·법무 정보"})
                continue
            sections.append({"key": key, "value": value})
        header = {
            "question": s.get("question", ""),
            "outcome": s.get("outcome", ""),
            "decided_by": s.get("decided_by", "") if not external else "(대외 문서에서는 개인을 표기하지 않습니다)",
            "baseline_id": s.get("baseline_id", ""),
            "package_version": s.get("package_version", 0),
        }
        if not header["question"] and not sections:
            raise RenderFailed("원천에서 실을 수 있는 항목을 찾지 못했습니다.")
        return {
            "title": p["title"], "audience": p["audience"],
            "security_class": p["security_class"],
            "header": header, "sections": sections,
            # ★ 근거 지문을 문서에 실어 둔다 — 발간본과 원천이 같은 것을 보고 있었는지
            #   나중에 확인할 수 있는 유일한 방법이다.
            "evidence": {"source_type": p["source_type"], "source_id": p["source_id"],
                         "source_evidence_hash": s.get("evidence_hash", ""),
                         "package_version": s.get("package_version", 0)},
            "redaction": {"policy": "EXTERNAL_DEFAULT" if external else "NONE",
                          "excluded": excluded},
            "files": [],
        }

    @staticmethod
    def _version_row(v: Dict[str, Any]) -> Dict[str, Any]:
        d = dict(v)
        for src, dst in (("document_ast_json", "document"),
                         ("rendered_files_json", "files"),
                         ("redaction_policy_json", "redaction"),
                         ("approval_snapshot_json", "approval_snapshot")):
            try:
                d[dst] = json.loads(d.pop(src) or "{}")
            except Exception:
                d[dst] = {}
        return d

    @staticmethod
    def _notify(event: str, pub: Dict[str, Any], actor: str) -> None:
        """[CL-4] 작성자·검토자에게만 알린다. **문서 본문을 싣지 않는다.**

        ⚠️ 알려진 한계: 검토 **요청** 시점에는 검토자가 누구인지 이 시스템이 모른다
          (`publication_reviews.reviewer_id` 는 판정한 뒤에 채워지고, 검토자를 지정하는
          계약이 아직 없다). 그래서 요청 알림은 **작성자와 이미 판정한 검토자에게만** 간다.
        ★ 모르는 수신자를 '전체'로 대체하지 않는다 — 그 순간 대외 발간 검토 요청이 전사에
          뿌려진다. 검토자 지정 계약이 생기면 그때 수신자가 넓어진다."""
        collaboration_events.emit(
            event, collaboration_events.publication_recipients(pub),
            {"id": pub["publication_id"], "status": pub["status"],
             "at": pub["updated_at"], "title": pub["title"],
             "actor": actor, "version": pub["document_version"]})

    def _audit(self, event: str, subject_id: str, actor: str, decision: str = "",
               rationale: str = "", evidence: Optional[List[Any]] = None,
               tenant_id: str = "tenant_default", scope: str = "") -> None:
        """원장 기록. **실패를 삼키지 않는다** — 근거 없는 발간이 남으면 안 된다."""
        self._ledger.append(event, subject_type="publication", subject_id=subject_id,
                            actor_type="user", actor_id=actor or "", decision=decision,
                            rationale=rationale, evidence_refs=evidence or [],
                            tenant_id=tenant_id, enterprise_scope_id=scope)


publication = Publication()
