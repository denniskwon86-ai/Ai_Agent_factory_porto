"""[ECM E3] 경쟁사 참조 모델 — **추정치를 공식 수치처럼 쓰지 않게 한다.**

설계서 §7.3 의 다섯 줄이 이 모듈의 전부다:

1. 공개 공시·공식 발표·계약상 이용 허용된 산업 데이터·검증된 조사자료만 입력한다.
2. 각 값에 `source` · `published_at` · `as_of_date` · `confidence` · `evidence_level` 을 기록한다.
3. **LLM 은 빈 칸을 사실처럼 채우지 않고 "확인 불가" 또는 가정 후보로 제시한다.**
4. 내부 실적과 경쟁사 추정치는 같은 차트에 둘 수 있으나 **색·범례·데이터 상태를 분리한다.**
5. 경쟁사 모델은 참조이며 **회계·경영의 공식 수치가 아니다.**

## 3번을 코드로 만드는 방법

"빈 칸을 채우지 말라"는 지침만으로는 지켜지지 않는다. 값을 넣을 자리가 하나뿐이면, 모르는 값을
만난 사람(또는 모델)은 결국 **그럴듯한 숫자**를 넣는다. 그래서 **"확인 불가"를 1급 상태로**
둔다(`mark_unverifiable`) — 모른다는 것을 기록할 수단이 있어야 지어내지 않는다.

⚠️ 그리고 근거 5종을 **선택 항목이 아니라 필수**로 둔다. 하나라도 비면 저장을 거부한다.
  경쟁사 숫자는 출처가 붙어 있지 않으면 몇 달 뒤에 내부 실적과 구분되지 않는다 — 그 순간
  "경쟁사는 우리보다 원가가 낮다"가 근거 없는 사실로 굳는다.

## 오래된 추정치

공시는 보통 연 1회 갱신된다. 1년이 넘은 값은 **최신 공시가 이미 나왔을 가능성이 크다**는
뜻이므로 `stale` 로 표시한다. 임계값은 아래 상수 한 곳에 있다 — 도메인 판단이 바뀌면 여기만 고친다.

LLM 0콜(이 모듈 자체는 계산·추정을 하지 않는다).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

#: §7.3 이 허용한 근거 종류. **이 목록에 없는 출처는 저장되지 않는다.**
#: "인터넷 검색", "업계 소문" 같은 것을 받기 시작하면 근거 필드는 장식이 된다.
EVIDENCE_LEVELS: Dict[str, str] = {
    "PUBLIC_FILING": "공개 공시(사업보고서·감사보고서 등)",
    "OFFICIAL_ANNOUNCEMENT": "공식 발표(보도자료·IR 자료)",
    "LICENSED_INDUSTRY_DATA": "계약상 이용이 허용된 산업 데이터",
    "VERIFIED_RESEARCH": "검증된 조사자료(출처·방법론 확인)",
}

#: 신뢰도. 숫자가 아니라 단계로 둔다 — "0.7" 은 계산에 쓰이기 시작하고, 그러면 추정치의
#: 불확실성이 확정 계산의 입력이 된다.
CONFIDENCE = ("HIGH", "MEDIUM", "LOW")
CONFIDENCE_KO = {"HIGH": "높음(공시 원문 확인)", "MEDIUM": "보통(2차 출처)",
                 "LOW": "낮음(단일 출처·추정)"}

#: 확인 불가 — 값이 아니라 **상태**다. 이 상태의 행에는 값을 넣지 않는다.
UNVERIFIABLE = "UNVERIFIABLE"

#: 공시는 보통 연 1회 갱신된다 → 1년이 넘으면 최신 공시가 이미 나왔을 가능성이 크다.
STALE_AFTER_DAYS = 365

_DDL = """
CREATE TABLE IF NOT EXISTS competitor_metrics (
    metric_id      TEXT PRIMARY KEY,
    tenant_id      TEXT NOT NULL DEFAULT 'tenant_default',
    entity_id      TEXT NOT NULL,
    metric_key     TEXT NOT NULL,
    value_json     TEXT NOT NULL DEFAULT 'null',
    unit           TEXT NOT NULL DEFAULT '',
    state          TEXT NOT NULL DEFAULT 'ESTIMATED',   -- ESTIMATED | UNVERIFIABLE
    source         TEXT NOT NULL DEFAULT '',
    published_at   TEXT NOT NULL DEFAULT '',
    as_of_date     TEXT NOT NULL DEFAULT '',
    confidence     TEXT NOT NULL DEFAULT '',
    evidence_level TEXT NOT NULL DEFAULT '',
    note           TEXT NOT NULL DEFAULT '',
    recorded_by    TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    UNIQUE (tenant_id, entity_id, metric_key, as_of_date)
);
CREATE INDEX IF NOT EXISTS idx_cm_entity ON competitor_metrics(entity_id);
"""


class CompetitorError(ValueError):
    """정책 위반 — 4xx 로 전달한다."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CompetitorReferenceStore:
    def __init__(self, repository=None):
        self._lock = threading.RLock()
        self._repo_override = repository

    @property
    def _repo(self):
        if self._repo_override is not None:
            return self._repo_override
        from core.enterprise_context.repository import ecm_repository
        return ecm_repository

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._repo.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout = 5000")
        except Exception:
            pass
        conn.executescript(_DDL)
        return conn

    # ── 경쟁사 모델 생성 ──────────────────────────────────────────────────
    def create_competitor(self, name_ko: str, evidence_ref: str, industry_code: str = "",
                          legal_name: str = "", tenant_id: str = "tenant_default",
                          actor: str = "") -> Dict[str, Any]:
        """경쟁사 참조 엔터티를 만든다. **이 모듈이 유일한 문이다.**

        ★ VIRTUAL 이 복제(`clone_service`)로만 만들어지는 것과 같은 구조다 — 일반 생성 경로
          (`POST /entities`)는 `REAL` 만 받는다. 그래야 "근거 없는 경쟁사 모델"이 만들어질 수 없다.
        ⚠️ `evidence_ref`(공개·승인된 근거)를 요구한다. 저장소도 같은 검사를 하지만(§2.1-4),
          여기서 먼저 막아 **왜** 필요한지 설명한다 — 400 만 던지면 사용자는 우회 방법을 찾는다."""
        if not (name_ko or "").strip():
            raise CompetitorError("경쟁사 이름(name_ko)은 필수입니다.")
        if not (evidence_ref or "").strip():
            raise CompetitorError(
                "경쟁사 모델에는 공개·승인된 근거(evidence_ref)가 필요합니다 — 근거 없는 경쟁사 "
                "모델은 추측의 집합이고, 그것이 시장 판단의 기준이 되면 되돌릴 수 없습니다(§7.3).")
        from core.enterprise_context.models import EnterpriseEntity
        e = self._repo.upsert_entity(EnterpriseEntity(
            tenant_id=tenant_id, entity_type="legal_entity",
            entity_mode="COMPETITOR_REFERENCE", name_ko=name_ko.strip(),
            legal_name=(legal_name or "").strip(), industry_code=industry_code,
            evidence_ref=evidence_ref.strip(), status="DRAFT"))
        self._audit(e.entity_id, actor, "경쟁사 모델 생성",
                    f"name={name_ko.strip()} 근거={evidence_ref.strip()[:80]}")
        d = e.model_dump()
        d["note"] = ("경쟁사 모델은 참조입니다 — 실제 회사와 같은 권한·운영 연결을 갖지 않고, "
                     "회계·경영의 공식 수치가 아닙니다(§7.3).")
        return d

    # ── 기록 ──────────────────────────────────────────────────────────────
    def record_metric(self, entity_id: str, metric_key: str, value: Any, source: str,
                      published_at: str, as_of_date: str, confidence: str,
                      evidence_level: str, unit: str = "", note: str = "",
                      tenant_id: str = "tenant_default", actor: str = "") -> Dict[str, Any]:
        """경쟁사 지표 1건. **근거 5종이 모두 있어야 저장된다**(§7.3).

        ⚠️ 하나라도 선택 항목으로 두면 그 필드는 비어 있게 되고, 몇 달 뒤에는 이 숫자가 내부
          실적과 구분되지 않는다 — "경쟁사는 우리보다 원가가 낮다"가 근거 없는 사실로 굳는다."""
        self._assert_competitor(entity_id)
        if not (metric_key or "").strip():
            raise CompetitorError("metric_key 는 필수입니다.")
        if value is None:
            raise CompetitorError(
                "값이 없으면 `mark_unverifiable()` 로 **확인 불가**를 기록하십시오 — 빈 값을 "
                "지표로 저장하면 나중에 누군가 그 칸을 채웁니다(§7.3-3).")
        missing = [n for n, v in (("source", source), ("published_at", published_at),
                                  ("as_of_date", as_of_date), ("confidence", confidence),
                                  ("evidence_level", evidence_level)) if not (v or "").strip()]
        if missing:
            raise CompetitorError(
                f"경쟁사 값에는 근거가 모두 필요합니다 — 빠진 항목: {missing} (§7.3-2). "
                f"출처 없는 추정치는 시간이 지나면 내부 실적과 구분되지 않습니다.")
        if evidence_level not in EVIDENCE_LEVELS:
            raise CompetitorError(
                f"허용된 근거 종류가 아닙니다: {evidence_level} — 가능: {sorted(EVIDENCE_LEVELS)}. "
                f"§7.3 은 공개 공시·공식 발표·계약상 허용 산업데이터·검증된 조사자료만 허용합니다.")
        if confidence not in CONFIDENCE:
            raise CompetitorError(f"confidence 는 {CONFIDENCE} 중 하나여야 합니다: {confidence}")
        self._check_date(published_at, "published_at")
        self._check_date(as_of_date, "as_of_date")
        return self._save(entity_id, metric_key, value, unit, "ESTIMATED", source,
                          published_at, as_of_date, confidence, evidence_level, note,
                          tenant_id, actor, reason="경쟁사 지표 기록")

    def mark_unverifiable(self, entity_id: str, metric_key: str, as_of_date: str,
                          note: str, tenant_id: str = "tenant_default",
                          actor: str = "") -> Dict[str, Any]:
        """**확인 불가**를 명시적으로 기록한다(§7.3-3).

        ★ 이것이 "LLM 이 빈 칸을 사실처럼 채우지 않는다"를 코드로 만드는 방법이다. 모른다고
          말할 자리가 있어야 지어내지 않는다. 값을 넣을 칸이 하나뿐이면 결국 그럴듯한 숫자가 들어간다.
        ⚠️ 사유(note)를 요구한다 — "확인 불가" 만 쌓이면 무엇을 더 찾아봐야 하는지 알 수 없다."""
        self._assert_competitor(entity_id)
        if not (metric_key or "").strip():
            raise CompetitorError("metric_key 는 필수입니다.")
        if not (note or "").strip():
            raise CompetitorError(
                "확인 불가 사유(note)는 필수입니다 — 무엇을 찾아봤고 왜 없었는지가 없으면 "
                "다음 사람이 같은 조사를 반복합니다.")
        self._check_date(as_of_date, "as_of_date")
        return self._save(entity_id, metric_key, None, "", UNVERIFIABLE, "", "",
                          as_of_date, "", "", note, tenant_id, actor,
                          reason="경쟁사 지표 확인 불가 기록")

    def _save(self, entity_id, metric_key, value, unit, state, source, published_at,
              as_of_date, confidence, evidence_level, note, tenant_id, actor,
              reason) -> Dict[str, Any]:
        mid = f"cmx_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO competitor_metrics (metric_id, tenant_id, entity_id, metric_key, "
                "value_json, unit, state, source, published_at, as_of_date, confidence, "
                "evidence_level, note, recorded_by, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(tenant_id, entity_id, metric_key, as_of_date) DO UPDATE SET "
                "value_json=excluded.value_json, unit=excluded.unit, state=excluded.state, "
                "source=excluded.source, published_at=excluded.published_at, "
                "confidence=excluded.confidence, evidence_level=excluded.evidence_level, "
                "note=excluded.note, recorded_by=excluded.recorded_by, "
                "updated_at=excluded.updated_at",
                (mid, tenant_id, entity_id, metric_key.strip(),
                 json.dumps(value, ensure_ascii=False), unit, state, (source or "").strip(),
                 (published_at or "").strip(), as_of_date.strip(), confidence, evidence_level,
                 (note or "").strip(), actor or "", now, now))
            conn.commit()
        self._audit(f"{entity_id}:{metric_key}", actor, reason,
                    f"state={state} as_of={as_of_date} 근거={evidence_level or '-'} "
                    f"신뢰도={confidence or '-'}")
        return self.get_metric(entity_id, metric_key.strip(), as_of_date.strip())

    def _assert_competitor(self, entity_id: str) -> None:
        """경쟁사 엔터티에만 기록한다.

        ⚠️ 실제/가상 엔터티에 이 표를 쓰기 시작하면 추정치가 실제 문맥에 섞인다 — §8.1 이
          물리적/논리적으로 분리하라고 한 그 경계다."""
        e = self._repo.get_entity(entity_id)
        if not e:
            raise CompetitorError(f"엔터티를 찾을 수 없습니다: {entity_id}")
        if e.entity_mode != "COMPETITOR_REFERENCE":
            raise CompetitorError(
                f"경쟁사 참조 엔터티에만 기록할 수 있습니다(현재 {e.entity_mode}) — 추정치가 "
                f"실제 문맥에 섞이면 어느 쪽이 사실인지 알 수 없게 됩니다.")

    @staticmethod
    def _check_date(v: str, field: str) -> None:
        try:
            date.fromisoformat((v or "").strip())
        except ValueError:
            raise CompetitorError(f"{field} 형식은 YYYY-MM-DD 입니다: {v}")

    # ── 조회 ──────────────────────────────────────────────────────────────
    def get_metric(self, entity_id: str, metric_key: str,
                   as_of_date: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM competitor_metrics WHERE entity_id=? AND "
                             "metric_key=? AND as_of_date=?",
                             (entity_id, metric_key, as_of_date)).fetchone()
        return self._row(r) if r else None

    def list_metrics(self, entity_id: str = "", metric_key: str = "",
                     today: str = "") -> List[Dict[str, Any]]:
        sql, params, where = "SELECT * FROM competitor_metrics", [], []
        if entity_id:
            where.append("entity_id=?"); params.append(entity_id)
        if metric_key:
            where.append("metric_key=?"); params.append(metric_key)
        if where:
            sql += " WHERE " + " AND ".join(where)
        with self._connect() as conn:
            rows = conn.execute(sql + " ORDER BY metric_key, as_of_date DESC",
                                tuple(params)).fetchall()
        return [self._row(r, today) for r in rows]

    def _row(self, r: sqlite3.Row, today: str = "") -> Dict[str, Any]:
        d = dict(r)
        try:
            d["value"] = json.loads(d.pop("value_json") or "null")
        except Exception:
            d["value"] = None
        d["evidence_level_ko"] = EVIDENCE_LEVELS.get(d["evidence_level"], "")
        d["confidence_ko"] = CONFIDENCE_KO.get(d["confidence"], "")
        # 나이와 신선도 — 오래된 추정치를 최신 실적 옆에 조용히 두면 안 된다.
        ref = date.fromisoformat(today) if today else datetime.now(timezone.utc).date()
        try:
            d["age_days"] = (ref - date.fromisoformat(d["as_of_date"])).days
        except Exception:
            d["age_days"] = None
        d["stale"] = bool(d["age_days"] is not None and d["age_days"] > STALE_AFTER_DAYS)
        d["official"] = False          # §7.3-5 — 회계·경영의 공식 수치가 아니다
        if d["state"] == UNVERIFIABLE:
            d["display"] = "확인 불가"
        elif d["stale"]:
            d["display"] = f"{d['value']} (기준 {d['as_of_date']} · 갱신 필요 가능)"
        else:
            d["display"] = f"{d['value']}"
        return d

    def coverage(self, entity_id: str, expected_keys: List[str] = None,
                 today: str = "") -> Dict[str, Any]:
        """이 경쟁사 모델이 **얼마나 채워졌고 무엇이 비었는지.**

        ★ 채워진 것만 보여주면 "이 정도면 비교 가능하다"고 판단하게 된다. 확인 불가와 미조사를
          구분해 세는 것이 요점이다 — 앞은 찾아봤고 없는 것, 뒤는 아직 안 본 것이다."""
        rows = self.list_metrics(entity_id, today=today)
        latest: Dict[str, Dict[str, Any]] = {}
        for r in rows:                      # as_of_date DESC 정렬이므로 첫 항목이 최신
            latest.setdefault(r["metric_key"], r)
        est = [k for k, v in latest.items() if v["state"] == "ESTIMATED"]
        unver = [k for k, v in latest.items() if v["state"] == UNVERIFIABLE]
        stale = [k for k, v in latest.items() if v["stale"] and v["state"] == "ESTIMATED"]
        missing = sorted(set(expected_keys or []) - set(latest))
        return {
            "entity_id": entity_id,
            "estimated": sorted(est), "unverifiable": sorted(unver),
            "stale": sorted(stale), "not_researched": missing,
            "summary": {"estimated": len(est), "unverifiable": len(unver),
                        "stale": len(stale), "not_researched": len(missing)},
            "note": ("확인 불가는 '찾아봤지만 없음'이고 미조사는 '아직 보지 않음'입니다 — "
                     "둘을 같게 세면 조사 진척을 알 수 없습니다."),
        }

    # ── 내부 실적과의 나란히 보기 (§7.3-4) ────────────────────────────────
    def compare_with_internal(self, entity_id: str, internal_values: Dict[str, Any],
                              internal_as_of: str = "", internal_mode: str = "ACTUAL",
                              today: str = "") -> Dict[str, Any]:
        """내부 실적과 경쟁사 추정치를 **나란히** 놓는다. 같은 값처럼 보이지 않게 한다.

        §7.3-4 는 같은 차트에 두는 것을 허용하지만 "색·범례·데이터 상태를 분리한다"고 했다.
        여기서는 각 셀에 `mode`·`confidence`·`evidence_level`·`official=False` 를 붙여 돌려준다 —
        화면이 그것을 근거로 다르게 그릴 수 있어야 §7.3-4 가 성립한다.
        ⚠️ **차이(delta)를 계산하지 않는다.** 확정 실적과 추정치의 차이는 숫자로 보이는 순간
          사실처럼 읽히고, 그 차이의 대부분은 추정 오차일 수 있다."""
        from core.enterprise_context.comparison import MODE_COMPETITOR, MODE_KO
        rows = self.list_metrics(entity_id, today=today)
        latest: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            latest.setdefault(r["metric_key"], r)

        out_rows = []
        for k in sorted(set(internal_values) | set(latest)):
            comp = latest.get(k)
            out_rows.append({
                "key": k,
                "internal": ({"value": internal_values[k], "mode": internal_mode,
                              "mode_ko": MODE_KO.get(internal_mode, internal_mode),
                              "as_of": internal_as_of, "official": True}
                             if k in internal_values else None),
                "competitor": ({"value": comp["value"], "mode": MODE_COMPETITOR,
                                "mode_ko": MODE_KO[MODE_COMPETITOR],
                                "state": comp["state"], "display": comp["display"],
                                "as_of": comp["as_of_date"], "source": comp["source"],
                                "published_at": comp["published_at"],
                                "confidence": comp["confidence"],
                                "confidence_ko": comp["confidence_ko"],
                                "evidence_level": comp["evidence_level"],
                                "evidence_level_ko": comp["evidence_level_ko"],
                                "stale": comp["stale"], "age_days": comp["age_days"],
                                "official": False}
                               if comp else None),
                # 차이를 주지 않는 이유를 행마다 남긴다 — 없으면 누군가 계산해서 채운다.
                "delta": None,
                "delta_note": "확정 실적과 추정치의 차이는 계산하지 않습니다(§7.3-5).",
            })
        notes = ["경쟁사 값은 **참조**이며 회계·경영의 공식 수치가 아닙니다(§7.3-5)."]
        if any(r["competitor"] and r["competitor"]["stale"] for r in out_rows):
            notes.append("⚠️ 기준일이 1년을 넘은 경쟁사 값이 있습니다 — 최신 공시가 나왔는지 "
                         "확인하십시오.")
        if any(r["competitor"] and r["competitor"]["state"] == UNVERIFIABLE for r in out_rows):
            notes.append("확인 불가 항목이 있습니다 — 빈 칸을 추정으로 채우지 마십시오(§7.3-3).")
        if any(r["internal"] is None for r in out_rows):
            notes.append("내부 값이 없는 항목이 있습니다 — 비교 기준이 없으므로 우열을 말할 수 "
                         "없습니다.")
        return {"entity_id": entity_id, "rows": out_rows, "notes": notes}

    @staticmethod
    def _audit(resource_id: str, actor: str, reason: str, detail: str) -> None:
        try:
            from core.enterprise_context import audit
            audit.record(audit.COMPETITOR_REFERENCE_CHANGED, resource_type="competitor_metric",
                         resource_id=resource_id, actor=actor or "", outcome="allowed",
                         reason=reason, detail=detail)
        except Exception as e:                                       # pragma: no cover
            print(f"⚠️ [competitor] 감사 기록 실패({resource_id}): {e}")


competitor_reference = CompetitorReferenceStore()
