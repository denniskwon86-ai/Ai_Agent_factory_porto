"""[§7.3 / §7.4] Shadow Mode — 후보를 실제 데이터에 병렬 적용하되 **운영에는 쓰지 않는다**.

§7.3 5단계: 기준선 설정 → 병렬 실행 → 비교 → 검토 → 승격.

## 무엇을 만들고 무엇을 만들지 않았나

**만들지 않은 것: 범용 후보 실행기.** 이 시스템에는 "임의의 앱·규칙을 실행해 결과를 얻는"
능력이 없다. 없는 것을 있는 척 만들면 아무도 호출하지 않는 죽은 코드이거나, 돌아가는 것처럼
보이려고 값을 지어내는 경로가 된다(외부 인텔리전스 수집기에서 내린 것과 같은 판단).

**만든 것**: 두 실행 결과를 받아 **같은 입력이었는지 검증**하고, 비교하고, 사람의 검토를
거쳐 **범위를 제한해 승격**하는 게이트. 실제 실행 어댑터는 지금 실행 가능한 종류
(경영계획 시나리오) 하나만 붙였다. 다른 종류는 호출자가 결과를 넣는다(`record_side`).

## 이 모듈이 지키는 것

1. **같은 입력이 아니면 비교하지 않는다.** 기준선과 후보의 `input_hash` 가 다르면
   `comparable=false` 다. 다른 입력으로 낸 차이는 후보의 효과가 아니라 입력의 차이다 —
   그걸 개선으로 읽으면 잘못된 승격을 한다(`compare_scenarios.same_baseline` 과 같은 판단).
2. **측정하지 못한 지표는 0 이 아니라 `unmeasured` 다.** 0 으로 채우면 "후보가 오류 0건"으로
   읽힌다. 이 저장소의 관통 원칙이다.
3. **섀도우 결과는 운영값이 아니다.** 모든 응답이 그 사실을 명시하고, 승격 전에는
   `promotion_scope` 가 비어 있다 — 운영 경로가 이 값을 읽을 근거가 없다.
4. **검토 없이 승격할 수 없고, 검토자를 반드시 남긴다.** 계약 활성화·용어 승인과 같은 규칙.
5. **승격은 범위를 제한한다**(§7.3 "승인된 범위에서만 제한적 운영 적용"). 범위 없는 승격은
   거절한다 — "전체 적용"을 기본값으로 두면 제한적 적용이라는 개념이 사라진다.
6. **후보가 나빠도 승격을 막지는 않되, 악화 항목을 검토자가 명시적으로 인정하게 한다.**
   더 느리지만 싼 후보처럼 악화를 감수할 이유가 있을 수 있다. 다만 **모르고 승격하는 것**과
   **알고 승격하는 것**은 달라야 한다.

⚠️ 조직 범위(`enterprise_scope_id`)는 **필수**다. Shadow run 은 M2 이후의 신규 운영
  데이터이므로 D-014 개정("미지정=전사 공용은 레거시 공개 참조 데이터로 한정")이 그대로
  적용된다. 범위 없는 등록을 허용하면 그 예외가 곧 상태가 된다.

LLM 0콜.
"""
import hashlib
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_DB_PATH = os.path.join("data", "shadow_runs.db")

#: 후보의 종류. `planning_scenario` 만 실제 실행 어댑터가 있고 나머지는 결과 주입 방식이다.
CANDIDATE_KINDS = ("planning_scenario", "rule", "model", "app", "other")
RUN_STATUS = ("pending", "running", "completed", "failed", "aborted")
REVIEW_STATUS = ("pending_review", "approved", "rejected")
SIDES = ("baseline", "candidate")

#: 비교할 지표와 **개선 방향**. 방향을 모르면 무엇이 개선인지 판정할 수 없다.
#: `True` = 클수록 좋음, `False` = 작을수록 좋음.
METRIC_DIRECTION = {
    "kpi_value": True,          # §7.3 KPI
    "accuracy": True,
    "error_count": False,       # §7.3 오류
    "exception_count": False,   # §7.3 예외
    "cost_usd": False,          # §7.3 비용
    "user_edit_count": False,   # §7.3 사용자 수정량
    "latency_sec": False,
}

_DDL = """
CREATE TABLE IF NOT EXISTS shadow_runs (
    run_id          TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    candidate_kind  TEXT NOT NULL,
    candidate_ref   TEXT DEFAULT '',
    baseline_ref    TEXT DEFAULT '',
    blueprint_id    TEXT DEFAULT '',
    scenario_ref    TEXT DEFAULT '',
    input_snapshot_ref TEXT DEFAULT '',
    evaluation_period  TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'pending',
    started_at      TEXT DEFAULT '',
    ended_at        TEXT DEFAULT '',
    baseline_json   TEXT DEFAULT '',       -- {metrics, input_hash, recorded_at}
    candidate_json  TEXT DEFAULT '',
    variance_json   TEXT DEFAULT '',
    review_status   TEXT NOT NULL DEFAULT 'pending_review',
    reviewed_by     TEXT DEFAULT '',
    reviewed_at     TEXT DEFAULT '',
    review_note     TEXT DEFAULT '',
    acknowledged_regressions TEXT DEFAULT '',   -- 검토자가 알고 받아들인 악화 항목
    promotion_scope TEXT DEFAULT '',            -- 빈 값 = 미승격(운영 적용 근거 없음)
    promoted_by     TEXT DEFAULT '',
    promoted_at     TEXT DEFAULT '',
    tenant_id       TEXT NOT NULL DEFAULT 'tenant_default',
    enterprise_scope_id TEXT NOT NULL,          -- 필수(D-014 개정)
    entity_mode     TEXT NOT NULL DEFAULT 'REAL',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shadow_scope
    ON shadow_runs(tenant_id, enterprise_scope_id, entity_mode, status);
CREATE INDEX IF NOT EXISTS idx_shadow_review ON shadow_runs(review_status, created_at DESC);
"""


class ShadowModeError(ValueError):
    """검증/정책 위반 등 4xx 로 전달할 도메인 오류."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _loads(raw, default):
    try:
        v = json.loads(raw) if raw else default
        return v if v is not None else default
    except Exception:
        return default


def snapshot_hash(payload: Any) -> str:
    """입력 스냅샷의 지문. **같은 입력이었는지**를 증명하는 유일한 수단이다.

    정렬된 JSON 을 해싱하므로 키 순서가 달라도 같은 입력이면 같은 지문이 나온다."""
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ShadowMode:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or _DB_PATH
        self._lock = threading.RLock()
        self._initialized_path = ""
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
        # ★ `db_path` 가 런타임에 바뀌면(테스트 격리·다중 테넌트) 그 경로에는 스키마가 없다.
        #   생성자에서 한 번만 초기화하면 "no such table" 로 조용히 죽는다(실측).
        #   경로가 바뀐 것을 여기서 알아채고 다시 만든다 — DDL 이 IF NOT EXISTS 라 무해하다.
        if self._initialized_path != self.db_path:
            conn.executescript(_DDL)
            conn.commit()
            self._initialized_path = self.db_path
        return conn

    def _init_db(self):
        with self._connect():
            pass

    # ── 1단계: 기준선 설정 ────────────────────────────────────────────────
    def create_run(self, name: str, candidate_kind: str, enterprise_scope_id: str,
                   candidate_ref: str = "", baseline_ref: str = "", blueprint_id: str = "",
                   scenario_ref: str = "", input_snapshot_ref: str = "",
                   evaluation_period: str = "", tenant_id: str = "tenant_default",
                   entity_mode: str = "REAL") -> dict:
        """Shadow run 을 연다. **아직 아무것도 실행하지 않은 상태**다.

        ⚠️ `enterprise_scope_id` 는 필수다 — D-014 개정에 따라 M2 이후 신규 운영 데이터는
          범위 지정 없이 등록할 수 없다. 여기서 예외를 허용하면 그 예외가 곧 상태가 된다."""
        if not (name or "").strip():
            raise ShadowModeError("name 은 필수입니다.")
        if candidate_kind not in CANDIDATE_KINDS:
            raise ShadowModeError(f"candidate_kind 는 {list(CANDIDATE_KINDS)} 중 하나여야 합니다.")
        if not (enterprise_scope_id or "").strip():
            raise ShadowModeError(
                "enterprise_scope_id 는 필수입니다 — Shadow run 은 신규 운영 데이터이므로 "
                "소유 조직 없이 등록할 수 없습니다(D-014 개정). 어느 조직의 실험인지 밝히십시오.")
        if not (evaluation_period or "").strip():
            raise ShadowModeError(
                "evaluation_period 는 필수입니다 — 평가 기간이 없으면 '언제의 데이터로 비교한 "
                "결과인가'에 답할 수 없고, 그 비교는 근거가 되지 못합니다(§7.3 기준선 설정).")

        rid = f"sh_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO shadow_runs(run_id,name,candidate_kind,candidate_ref,baseline_ref,"
                "blueprint_id,scenario_ref,input_snapshot_ref,evaluation_period,status,"
                "tenant_id,enterprise_scope_id,entity_mode,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,'pending',?,?,?,?,?)",
                (rid, name.strip(), candidate_kind, candidate_ref, baseline_ref, blueprint_id,
                 scenario_ref, input_snapshot_ref, evaluation_period,
                 tenant_id or "tenant_default", enterprise_scope_id.strip(),
                 entity_mode or "REAL", now, now))
        return self.get(rid)

    def get(self, run_id: str) -> Optional[dict]:
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM shadow_runs WHERE run_id=?", (run_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["baseline"] = _loads(d.pop("baseline_json", ""), None)
        d["candidate"] = _loads(d.pop("candidate_json", ""), None)
        d["variance"] = _loads(d.pop("variance_json", ""), None)
        d["acknowledged_regressions"] = _loads(d.get("acknowledged_regressions") or "", [])
        d["promoted"] = bool((d.get("promotion_scope") or "").strip())
        d["note"] = ("이 값은 **섀도우 결과이며 운영값이 아닙니다.** 승격되지 않은 결과를 "
                     "운영 판단에 쓰지 마십시오." if not d["promoted"] else
                     "승격된 범위에서만 운영 적용이 승인된 결과입니다.")
        return d

    def list_runs(self, scope_node_id: str = "", tenant_id: str = "",
                  entity_mode: str = "REAL", review_status: str = "",
                  # [§6-2] 등급이 낮으면 제목만 남기고 내용을 가린다(빈 값 = 가리지 않는다)
                  viewer_clearance: str = "") -> List[dict]:
        sql, params = "SELECT run_id FROM shadow_runs WHERE 1=1", []
        if review_status:
            sql += " AND review_status=?"
            params.append(review_status)
        with self._connect() as conn:
            ids = [r["run_id"] for r in conn.execute(
                sql + " ORDER BY created_at DESC", tuple(params)).fetchall()]
        rows = [self.get(i) for i in ids]
        # 등급만 주어진 호출도 처리한다 — 범위 없이 등급만 거는 화면이 있다.
        if not (scope_node_id or viewer_clearance):
            return rows
        from core.enterprise_context.scoping import filter_visible
        return filter_visible(rows, scope_node_id, tenant_id, entity_mode,
                              viewer_clearance=viewer_clearance)

    # ── 2단계: 병렬 실행 결과 기록 ────────────────────────────────────────
    def record_side(self, run_id: str, side: str, metrics: Dict[str, Any],
                    input_snapshot: Any = None, input_hash: str = "",
                    note: str = "") -> dict:
        """한쪽(기준선 또는 후보)의 실행 결과를 기록한다.

        ⚠️ `input_snapshot` 또는 `input_hash` 중 하나는 있어야 한다. 없으면 나중에 **같은
          입력이었는지 증명할 수 없고**, 그 비교는 "차이가 후보 때문인지 입력 때문인지"를
          구분하지 못한다.
        ⚠️ 지표 값에 `None` 을 넣으면 **미측정**으로 남는다(0 으로 바꾸지 않는다)."""
        if side not in SIDES:
            raise ShadowModeError(f"side 는 {list(SIDES)} 중 하나여야 합니다.")
        run = self.get(run_id)
        if not run:
            raise ShadowModeError(f"존재하지 않는 Shadow run 입니다: {run_id}")
        if run["review_status"] != "pending_review":
            raise ShadowModeError(
                "이미 검토가 끝난 run 의 결과는 바꿀 수 없습니다 — 검토 근거가 사후에 바뀌면 "
                "그 검토는 무효입니다.")
        if not isinstance(metrics, dict) or not metrics:
            raise ShadowModeError("metrics 는 비어 있지 않은 객체여야 합니다.")
        unknown = [k for k in metrics if k not in METRIC_DIRECTION]
        if unknown:
            raise ShadowModeError(
                f"개선 방향을 모르는 지표입니다: {unknown}. 방향을 모르면 무엇이 개선인지 "
                f"판정할 수 없습니다. 허용: {sorted(METRIC_DIRECTION)}")
        h = (input_hash or "").strip() or (snapshot_hash(input_snapshot)
                                           if input_snapshot is not None else "")
        if not h:
            raise ShadowModeError(
                "input_snapshot 또는 input_hash 가 필요합니다 — 같은 입력이었음을 증명할 수 "
                "없으면 비교 결과가 후보의 효과인지 입력 차이인지 구분되지 않습니다.")

        payload = {"metrics": metrics, "input_hash": h, "recorded_at": _now(), "note": note}
        col = "baseline_json" if side == "baseline" else "candidate_json"
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE shadow_runs SET {col}=?, status='running', "
                f"started_at=CASE WHEN started_at='' THEN ? ELSE started_at END, updated_at=? "
                f"WHERE run_id=?",
                (json.dumps(payload, ensure_ascii=False), now, now, run_id))
        return self.get(run_id)

    def run_planning_scenario(self, run_id: str, baseline_scenario_id: str,
                              candidate_scenario_id: str, org_id: str, period: str) -> dict:
        """[실행 어댑터 — 지금 실제로 실행 가능한 유일한 종류]

        경영계획 시나리오 두 개를 **같은 조직·같은 기간**으로 돌려 양쪽을 기록한다.
        `planning_engine.run_scenario` 가 이미 `input_hash` 를 주므로 그것을 그대로 쓴다 —
        지문을 다시 계산하면 두 개의 진실이 생긴다."""
        from core.planning_engine import run_scenario
        out = {}
        for side, sid in (("baseline", baseline_scenario_id), ("candidate", candidate_scenario_id)):
            r = run_scenario(sid, org_id, period)
            res = r.get("result") or {}
            # 계산이 불완전하면 값을 지어내지 않는다 — 미측정으로 남긴다.
            complete = bool(res.get("complete"))
            self.record_side(
                run_id, side,
                metrics={"kpi_value": res.get("operating_profit") if complete else None},
                input_hash=r.get("input_hash", ""),
                note=(f"scenario={sid}" + ("" if complete else " · 계산 불완전(미측정으로 기록)")))
            out[side] = {"scenario_id": sid, "input_hash": r.get("input_hash", ""),
                         "complete": complete}
        return {"run_id": run_id, "sides": out, **self.compare(run_id)}

    # ── 3단계: 비교 ───────────────────────────────────────────────────────
    def compare(self, run_id: str) -> dict:
        """두 결과를 비교한다. **같은 입력이 아니면 비교하지 않는다.**"""
        run = self.get(run_id)
        if not run:
            raise ShadowModeError(f"존재하지 않는 Shadow run 입니다: {run_id}")
        b, c = run["baseline"], run["candidate"]
        if not b or not c:
            missing = "기준선" if not b else "후보"
            return self._save_variance(run_id, {
                "comparable": False,
                "reason": f"{missing} 실행 결과가 아직 없습니다.",
                "note": "한쪽만으로는 비교가 성립하지 않습니다.",
            })
        if b["input_hash"] != c["input_hash"]:
            return self._save_variance(run_id, {
                "comparable": False,
                "reason": "기준선과 후보의 입력이 다릅니다.",
                "baseline_input_hash": b["input_hash"][:12],
                "candidate_input_hash": c["input_hash"][:12],
                "note": ("다른 입력으로 낸 차이는 후보의 효과가 아니라 **입력의 차이**입니다. "
                         "이것을 개선으로 읽으면 잘못된 승격을 합니다(§7.3 '같은 입력에 동시 실행')."),
            })

        improved, regressed, unmeasured, unchanged = [], [], [], []
        rows = []
        for m in sorted(set(b["metrics"]) | set(c["metrics"])):
            bv, cv = b["metrics"].get(m), c["metrics"].get(m)
            if bv is None or cv is None:
                # 0 으로 채우지 않는다 — "후보가 오류 0건"으로 읽힌다.
                unmeasured.append(m)
                rows.append({"metric": m, "baseline": bv, "candidate": cv,
                             "verdict": "unmeasured",
                             "why": ("한쪽 이상이 측정되지 않았습니다(0 이 아니라 미측정). "
                                     "이 지표로는 판정하지 않습니다.")})
                continue
            higher_is_better = METRIC_DIRECTION[m]
            delta = cv - bv
            if delta == 0:
                verdict = "unchanged"
                unchanged.append(m)
            elif (delta > 0) == higher_is_better:
                verdict = "improved"
                improved.append(m)
            else:
                verdict = "regressed"
                regressed.append(m)
            rows.append({
                "metric": m, "baseline": bv, "candidate": cv, "delta": delta,
                "delta_pct": (round(delta / bv * 100, 2) if bv else None),
                "higher_is_better": higher_is_better, "verdict": verdict,
            })

        return self._save_variance(run_id, {
            "comparable": True,
            "input_hash": b["input_hash"][:12],
            "evaluation_period": run["evaluation_period"],
            "metrics": rows,
            "improved": improved, "regressed": regressed,
            "unchanged": unchanged, "unmeasured": unmeasured,
            "verdict": ("regressed" if regressed else
                        ("improved" if improved else "no_difference")),
            "note": ("이 비교는 **섀도우 결과**입니다 — 운영값이 아닙니다. "
                     "미측정 지표는 판정에서 제외됐습니다(0 으로 치지 않습니다)."),
        })

    def _save_variance(self, run_id: str, variance: dict) -> dict:
        now = _now()
        done = bool(variance.get("comparable"))
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE shadow_runs SET variance_json=?, updated_at=?, "
                "status=CASE WHEN ? THEN 'completed' ELSE status END, "
                "ended_at=CASE WHEN ? THEN ? ELSE ended_at END WHERE run_id=?",
                (json.dumps(variance, ensure_ascii=False), now, done, done, now, run_id))
        return variance

    # ── 4단계: 검토 ───────────────────────────────────────────────────────
    def review(self, run_id: str, decision: str, reviewed_by: str, note: str = "",
               acknowledged_regressions: List[str] = None) -> dict:
        """데이터 오너·업무 오너가 차이를 승인/반려한다(§7.3 검토).

        ⚠️ 악화 항목이 있는데 인정 목록에 없으면 **승인할 수 없다.** 후보가 나쁜 것을 승격하는
          것 자체는 정당할 수 있지만(더 싸거나 빠르거나), **모르고 승격하는 것**과 **알고
          승격하는 것**은 달라야 한다."""
        if decision not in ("approved", "rejected"):
            raise ShadowModeError("decision 은 approved|rejected 여야 합니다.")
        if not (reviewed_by or "").strip():
            raise ShadowModeError(
                "reviewed_by 는 필수입니다 — 누가 이 차이를 승인했는지 없으면 승격의 근거가 "
                "사라집니다.")
        run = self.get(run_id)
        if not run:
            raise ShadowModeError(f"존재하지 않는 Shadow run 입니다: {run_id}")
        var = run["variance"] or self.compare(run_id)

        if decision == "approved":
            if not var.get("comparable"):
                raise ShadowModeError(
                    f"비교가 성립하지 않은 run 은 승인할 수 없습니다: {var.get('reason', '')}")
            ack = set(acknowledged_regressions or [])
            unack = [m for m in var.get("regressed", []) if m not in ack]
            if unack:
                raise ShadowModeError(
                    f"악화된 지표를 인정하지 않고 승인할 수 없습니다: {unack}. "
                    f"감수할 이유가 있다면 acknowledged_regressions 에 명시하십시오 — "
                    f"모르고 승격하는 것과 알고 승격하는 것은 다릅니다.")
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE shadow_runs SET review_status=?, reviewed_by=?, reviewed_at=?, "
                "review_note=?, acknowledged_regressions=?, updated_at=? WHERE run_id=?",
                (decision, reviewed_by, now, note,
                 json.dumps(sorted(acknowledged_regressions or []), ensure_ascii=False),
                 now, run_id))
        return self.get(run_id)

    # ── 5단계: 승격 ───────────────────────────────────────────────────────
    def promote(self, run_id: str, promotion_scope: str, promoted_by: str) -> dict:
        """승인된 범위에서만 제한적으로 운영 적용한다(§7.3 승격).

        ⚠️ `promotion_scope` 는 필수다. "전체 적용"을 기본값으로 두면 **제한적 적용이라는
          개념 자체가 사라진다.** 무엇에 적용하는지 적지 않은 승격은 통제되지 않는다."""
        if not (promotion_scope or "").strip():
            raise ShadowModeError(
                "promotion_scope 는 필수입니다 — §7.3 은 '승인된 범위에서만 제한적 운영 적용'을 "
                "규정합니다. 범위를 비우면 제한적 적용이 아니라 전면 적용이 됩니다.")
        if not (promoted_by or "").strip():
            raise ShadowModeError("promoted_by 는 필수입니다.")
        run = self.get(run_id)
        if not run:
            raise ShadowModeError(f"존재하지 않는 Shadow run 입니다: {run_id}")
        if run["review_status"] != "approved":
            raise ShadowModeError(
                f"검토가 승인되지 않은 run 은 승격할 수 없습니다(현재: {run['review_status']}). "
                f"검토 없는 승격은 §7.3 의 5단계를 건너뛰는 것입니다.")
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE shadow_runs SET promotion_scope=?, promoted_by=?, promoted_at=?, "
                "updated_at=? WHERE run_id=?",
                (promotion_scope.strip(), promoted_by, now, now, run_id))
        return self.get(run_id)

    def abort(self, run_id: str, reason: str = "") -> dict:
        run = self.get(run_id)
        if not run:
            raise ShadowModeError(f"존재하지 않는 Shadow run 입니다: {run_id}")
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE shadow_runs SET status='aborted', ended_at=?, review_note=?, "
                "updated_at=? WHERE run_id=?", (now, reason, now, run_id))
        return self.get(run_id)

    # ── 관측 ──────────────────────────────────────────────────────────────
    def summary(self, scope_node_id: str = "", tenant_id: str = "",
                entity_mode: str = "REAL") -> dict:
        rows = self.list_runs(scope_node_id, tenant_id, entity_mode)
        by_review, by_status = {}, {}
        incomparable = []
        for r in rows:
            by_review[r["review_status"]] = by_review.get(r["review_status"], 0) + 1
            by_status[r["status"]] = by_status.get(r["status"], 0) + 1
            v = r.get("variance") or {}
            if v and not v.get("comparable"):
                incomparable.append({"run_id": r["run_id"], "name": r["name"],
                                     "reason": v.get("reason", "")})
        return {
            "total": len(rows), "by_review_status": by_review, "by_status": by_status,
            "promoted": sum(1 for r in rows if r["promoted"]),
            "incomparable": incomparable,
            "note": ("승격되지 않은 결과는 운영값이 아닙니다. `incomparable` 은 같은 입력이 "
                     "아니어서 비교 자체가 성립하지 않은 run 입니다 — 실패가 아니라 "
                     "**판정 불가**이며, 입력을 맞춰 다시 돌려야 합니다."),
        }


shadow_mode = ShadowMode()
