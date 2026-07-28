"""[§6.3 / §6.4 / §14 M1] 업무 용어사전 + 데이터 요구사항 매칭.

## 왜 MDM 과 별도인가 (§6.1 "MDM 과 연결되나 별도 관리")

MDM 은 **값**이고(`RM-MHP-001` 의 단가 15,000), 용어사전은 **말**이다(현업이 부르는 이름과 그
계산 정의). 같은 값을 부서마다 다르게 부르고, 같은 말을 부서마다 다르게 계산한다. "가동률"이
부서마다 다르게 계산되는 것이 제조 현장의 실제 문제이고, 합의된 계산 정의를 적어두지 않으면
LLM 이 그때그때 지어낸다.

## §6.4 매칭 흐름을 그대로 구현한다

    업무 용어 → 동의어/유사어 확장 → 카탈로그 후보 검색 → MDM 연결 확인
             → 품질/최신성/권한 확인 → 데이터 요구사항 상태 갱신

⚠️ **자동 확정하지 않는다.** §6.4 가 "LLM 은 후보 검색·설명에만 사용한다. 최종 매칭 확정은
  데이터 오너 또는 승인된 규칙이 담당한다"고 못박았다. 그래서 `match_requirement()` 는 후보와
  근거만 만들고, 상태 갱신(`confirm_match`)은 사람이 하는 별도 행위다. 자동으로 'held' 로
  바꾸면 준비도 점수가 근거 없이 올라가고, 그건 착수 판단을 망친다.

⚠️ **미승인 동의어로 확정 매칭을 하지 않는다.** 확장 검색에는 쓰되 후보의 신뢰도를 낮추고
  근거에 표시한다 — "누가 이걸 같은 말이라고 했나"에 답할 수 없으면 확정의 근거가 못 된다.

LLM 0콜.
"""
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.master_data import MasterData, master_data

TERM_STATUS = ("draft", "approved", "retired")


class GlossaryError(ValueError):
    """검증/충돌 등 4xx 로 전달할 도메인 오류."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(s: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", " ", (s or "").lower()).strip()


class BusinessGlossary:
    def __init__(self, md: MasterData = None):
        self.md = md or master_data

    def _connect(self):
        return self.md._connect()

    # ── 용어 ──────────────────────────────────────────────────────────────
    def create_term(self, canonical_name: str, definition: str = "", calculation: str = "",
                    domain: str = "", owner_dept_id: str = "", master_code: str = "",
                    synonyms: List[str] = None, term_id: str = "") -> dict:
        if not (canonical_name or "").strip():
            raise GlossaryError("canonical_name 은 필수입니다.")
        tid = term_id or f"term_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self.md._lock, self._connect() as conn:
            if conn.execute("SELECT term_id FROM business_terms "
                            "WHERE canonical_name=? AND status<>'retired'",
                            (canonical_name.strip(),)).fetchone():
                raise GlossaryError(f"이미 등록된 용어입니다: {canonical_name}")
            conn.execute(
                "INSERT INTO business_terms(term_id,canonical_name,definition,calculation,domain,"
                "owner_dept_id,master_code,status,approved_by,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,'draft','',?,?)",
                (tid, canonical_name.strip(), definition, calculation, domain, owner_dept_id,
                 master_code, now, now))
            for s in (synonyms or []):
                if (s or "").strip():
                    conn.execute("INSERT OR IGNORE INTO term_synonyms"
                                 "(term_id,synonym,language,confidence,approved_by,created_at) "
                                 "VALUES(?,?,'ko',1.0,'',?)", (tid, s.strip(), now))
        return self.get_term(tid)

    def get_term(self, term_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM business_terms WHERE term_id=?",
                               (term_id,)).fetchone()
            if not row:
                return None
            out = dict(row)
            out["synonyms"] = [dict(r) for r in conn.execute(
                "SELECT synonym,language,confidence,approved_by FROM term_synonyms "
                "WHERE term_id=? ORDER BY synonym", (term_id,)).fetchall()]
        return out

    def list_terms(self, domain: str = "", status: str = "",
                   include_retired: bool = False) -> List[dict]:
        sql, params = "SELECT * FROM business_terms WHERE 1=1", []
        if not include_retired:
            sql += " AND status<>'retired'"
        for col, val in (("domain", domain), ("status", status)):
            if val:
                sql += f" AND {col}=?"
                params.append(val)
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(sql + " ORDER BY canonical_name",
                                                  tuple(params)).fetchall()]

    def approve_term(self, term_id: str, approved_by: str) -> dict:
        """승인 = "이 정의로 전사가 같은 말을 쓴다"는 선언. 승인자를 반드시 남긴다."""
        if not (approved_by or "").strip():
            raise GlossaryError("approved_by 는 필수입니다 — 누가 승인했는지 없으면 근거가 없습니다.")
        with self.md._lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE business_terms SET status='approved', approved_by=?, updated_at=? "
                "WHERE term_id=? AND status<>'retired'", (approved_by, _now(), term_id))
            if not cur.rowcount:
                raise GlossaryError(f"존재하지 않거나 폐기된 용어입니다: {term_id}")
        return self.get_term(term_id)

    def retire_term(self, term_id: str) -> bool:
        with self.md._lock, self._connect() as conn:
            return conn.execute(
                "UPDATE business_terms SET status='retired', updated_at=? "
                "WHERE term_id=? AND status<>'retired'", (_now(), term_id)).rowcount > 0

    # ── 동의어 ────────────────────────────────────────────────────────────
    def add_synonym(self, term_id: str, synonym: str, language: str = "ko",
                    confidence: float = 1.0, approved_by: str = "") -> dict:
        if not (synonym or "").strip():
            raise GlossaryError("synonym 은 필수입니다.")
        with self.md._lock, self._connect() as conn:
            if not conn.execute("SELECT 1 FROM business_terms WHERE term_id=?",
                                (term_id,)).fetchone():
                raise GlossaryError(f"존재하지 않는 용어입니다: {term_id}")
            conn.execute(
                "INSERT INTO term_synonyms(term_id,synonym,language,confidence,approved_by,"
                "created_at) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(term_id,synonym) DO UPDATE SET language=excluded.language, "
                "confidence=excluded.confidence, approved_by=excluded.approved_by",
                (term_id, synonym.strip(), language, float(confidence), approved_by, _now()))
        return self.get_term(term_id)

    def approve_synonym(self, term_id: str, synonym: str, approved_by: str) -> dict:
        if not (approved_by or "").strip():
            raise GlossaryError("approved_by 는 필수입니다.")
        with self.md._lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE term_synonyms SET approved_by=? WHERE term_id=? AND synonym=?",
                (approved_by, term_id, synonym))
            if not cur.rowcount:
                raise GlossaryError(f"존재하지 않는 동의어입니다: {term_id}/{synonym}")
        return self.get_term(term_id)

    # ── §6.4 1~2단계: 용어 해석 + 동의어 확장 ─────────────────────────────
    def expand(self, text: str, approved_only: bool = False) -> dict:
        """업무 용어를 정본명 + 동의어로 확장한다.

        반환의 `unapproved` 는 **확장에는 썼지만 확정 근거로는 약한** 동의어다. 섞어서 돌려주면
        나중에 "이 매칭의 근거가 승인된 것이었나"를 되짚을 수 없다."""
        q = _norm(text)
        if not q:
            return {"query": text, "terms": [], "words": [], "unapproved": []}
        matched, words, unapproved = [], set(), set()
        for t in self.list_terms():
            names = [(t["canonical_name"], True)]
            with self._connect() as conn:
                syns = conn.execute(
                    "SELECT synonym, approved_by FROM term_synonyms WHERE term_id=?",
                    (t["term_id"],)).fetchall()
            for s in syns:
                if approved_only and not s["approved_by"]:
                    continue
                names.append((s["synonym"], bool(s["approved_by"])))
            hit = any(_norm(n) and (_norm(n) in q or q in _norm(n)) for n, _ in names)
            if not hit:
                continue
            matched.append({"term_id": t["term_id"], "canonical_name": t["canonical_name"],
                            "status": t["status"], "master_code": t["master_code"],
                            "calculation": t["calculation"], "owner_dept_id": t["owner_dept_id"]})
            for n, approved in names:
                words.add(n)
                if not approved:
                    unapproved.add(n)
        return {"query": text, "terms": matched, "words": sorted(words),
                "unapproved": sorted(unapproved)}

    # ── §6.4 전체 흐름 ────────────────────────────────────────────────────
    def match_requirement(self, canonical_term: str, catalog=None) -> dict:
        """상담사가 "필요하다"고 한 데이터를 카탈로그에서 찾는다(§6.4).

        ⚠️ **확정하지 않는다.** 후보와 근거, 그리고 '무엇이 확정을 막고 있나'(`blockers`)를
          만든다. 확정은 `confirm_match()` 로 사람이 한다."""
        from core.data_catalog import data_catalog
        cat = catalog or data_catalog

        exp = self.expand(canonical_term)
        # 용어가 등록돼 있지 않아도 원문으로는 찾아본다 — 용어사전이 비어 있다고 매칭이 통째로
        #   멈추면 도입 초기에 아무것도 못 한다(점진 도입).
        search_words = exp["words"] or [canonical_term]

        seen, candidates = {}, []
        for w in search_words:
            for hit in cat.search_assets(w):
                prev = seen.get(hit["asset_id"])
                if prev:
                    prev["score"] = max(prev["score"], hit["score"])
                    if w not in prev["matched_via"]:
                        prev["matched_via"].append(w)
                    continue
                hit = dict(hit)
                hit["matched_via"] = [w]
                seen[hit["asset_id"]] = hit
                candidates.append(hit)

        term = exp["terms"][0] if exp["terms"] else None
        for c in candidates:
            blockers = []
            if not c["governance_ready"]:
                blockers.append("자산에 책임자 또는 갱신주기가 없다(§6.4 5단계 확인 불가)")
            if term and term["master_code"]:
                linked = any(f.get("master_code") == term["master_code"]
                             for f in (cat.get_asset(c["asset_id"]) or {}).get("fields", []))
                if not linked:
                    blockers.append(
                        f"용어가 가리키는 기준정보({term['master_code']})와 연결된 필드가 없다"
                        f"(§6.4 4단계)")
            if set(c["matched_via"]) & set(exp["unapproved"]):
                blockers.append("승인되지 않은 동의어로 매칭됐다 — 확정 근거로는 약하다")
            c["blockers"] = blockers
            c["confirmable"] = not blockers
        candidates.sort(key=lambda c: (len(c["blockers"]), -c["score"], c["name"]))

        return {
            "canonical_term": canonical_term,
            "resolved_term": term,
            "expanded_words": exp["words"],
            "unapproved_words": exp["unapproved"],
            "candidates": candidates,
            "confirmable_count": sum(1 for c in candidates if c["confirmable"]),
            "note": ("후보와 근거만 제시합니다. **최종 매칭 확정은 데이터 오너 또는 승인된 "
                     "규칙의 몫입니다**(§6.4). 자동으로 준비도를 올리지 않습니다."),
        }

    # ── §6.4 6단계: 요구사항 상태 갱신 (사람의 확정 행위) ─────────────────
    def confirm_match(self, blueprint_id: str, req_key: str, asset_id: str,
                      confirmed_by: str, readiness_status: str = "held",
                      store=None, catalog=None) -> dict:
        """사람이 매칭을 확정하고 데이터 요구사항 상태를 갱신한다.

        ⚠️ `confirmed_by` 는 필수다 — 누가 "이 자산이 그 데이터다"라고 했는지 없으면 준비도
          점수의 근거가 사라진다. 준비도는 착수 판단에 쓰이므로 근거 없는 상향이 가장 위험하다."""
        if not (confirmed_by or "").strip():
            raise GlossaryError("confirmed_by 는 필수입니다 — 확정자 없는 매칭은 근거가 없습니다.")
        if readiness_status not in ("held", "needs_verification", "missing"):
            raise GlossaryError("readiness_status 는 held|needs_verification|missing 이어야 합니다.")
        from core.data_catalog import data_catalog
        cat = catalog or data_catalog
        if not cat.get_asset(asset_id):
            raise GlossaryError(f"존재하지 않는 자산입니다: {asset_id}")

        from core.advisor_store import advisor_store
        st = store or advisor_store
        with st._connect() as conn:
            cur = conn.execute(
                "UPDATE blueprint_data_requirements SET readiness_status=? "
                "WHERE blueprint_id=? AND req_key=?", (readiness_status, blueprint_id, req_key))
            if not cur.rowcount:
                raise GlossaryError(f"존재하지 않는 데이터 요구사항입니다: {blueprint_id}/{req_key}")
            conn.commit()
        return {"blueprint_id": blueprint_id, "req_key": req_key, "asset_id": asset_id,
                "readiness_status": readiness_status, "confirmed_by": confirmed_by}


business_glossary = BusinessGlossary()
