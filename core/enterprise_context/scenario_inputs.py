"""[ECM E3] 가정 세트 · 기준선 스냅샷 · 계산 결과 — **계산의 입력과 출력을 고정한다.**

## 왜 필요한가

§8.1 은 모든 실행 요청이 `baseline_snapshot_id` · `assumption_set_id` ·
`calculation_model_version` 을 갖고, **산출 결과도 같은 키를 갖는다**고 못 박았다.
그런데 E3 를 구현할 때 그 두 id 는 **문자열로만 통과**하고 있었다 — 키는 있고 대상이 없었다.

⚠️ 그 상태의 문제는 조용하다: 시나리오를 만들고 계산까지 할 수 있지만, 나중에 "이 숫자는
  무슨 가정으로 어떤 기준선과 비교해 나왔나"에 답할 수 없다. 답할 수 없는 숫자는 근거가 아니라
  주장이고, 경영 판단에 쓰이면 그때부터 사실처럼 취급된다(비협상 3: 모든 값은 상태와 근거를 갖는다).

## 이 모듈이 지키는 네 가지

1. **근거 없는 가정은 저장하지 않는다.** 가정값마다 근거(`evidence`)를 요구한다 — 근거 없는
   가정은 추측이고, 추측이 계산에 들어가면 결과가 사실처럼 보인다.
2. **계산에 쓰인 입력은 동결된다.** 결과를 기록하는 순간 그 가정 세트와 스냅샷은 잠긴다.
   수정은 **새 버전**으로만 한다 — 입력이 나중에 바뀌면 과거 결과의 근거가 사라진다.
3. **승인된 것만 계산에 쓴다.** DRAFT 가정·스냅샷으로 계산하면 기준선이 흔들리고, 같은 계산이
   어제와 오늘 다른 답을 낸다(§4.4 의 "승인된 것이 이긴다"와 같은 규율).
4. **가상 값이 실제 기준선으로 스며들지 않는다.** 시나리오에서 나온 값을 `REAL` 스냅샷으로
   등록하려는 시도는 거부한다 — 그것이 §8.3 "가상 결과를 실제에 자동 반영하지 않는다"의
   저장소 쪽 방어선이다.

## 계산은 누가 하는가

이 모듈은 **계산하지 않는다.** 결정론적 계산 엔진(`core/planning_*`)이 계산하고, 결과를
`record_result()` 로 등록한다. LLM 은 계산값을 만들지 않는다(§8.2).

LLM 0콜.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DRAFT = "DRAFT"
APPROVED = "APPROVED"
SUPERSEDED = "SUPERSEDED"

_DDL = """
CREATE TABLE IF NOT EXISTS assumption_sets (
    assumption_set_id TEXT PRIMARY KEY,
    tenant_id      TEXT NOT NULL DEFAULT 'tenant_default',
    scope_node_id  TEXT NOT NULL DEFAULT '',
    name           TEXT NOT NULL,
    purpose        TEXT NOT NULL,
    values_json    TEXT NOT NULL DEFAULT '{}',
    evidence_json  TEXT NOT NULL DEFAULT '{}',
    status         TEXT NOT NULL DEFAULT 'DRAFT',
    version        INTEGER NOT NULL DEFAULT 1,
    supersedes     TEXT NOT NULL DEFAULT '',
    frozen         INTEGER NOT NULL DEFAULT 0,
    created_by     TEXT NOT NULL DEFAULT '',
    approved_by    TEXT NOT NULL DEFAULT '',
    approved_at    TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS baseline_snapshots (
    snapshot_id    TEXT PRIMARY KEY,
    tenant_id      TEXT NOT NULL DEFAULT 'tenant_default',
    scope_node_id  TEXT NOT NULL DEFAULT '',
    name           TEXT NOT NULL,
    as_of          TEXT NOT NULL,              -- 이 집계가 '언제 기준'인가
    source         TEXT NOT NULL,              -- 어디서 온 집계인가(근거)
    entity_mode    TEXT NOT NULL DEFAULT 'REAL',
    values_json    TEXT NOT NULL DEFAULT '{}',
    checksum       TEXT NOT NULL DEFAULT '',
    status         TEXT NOT NULL DEFAULT 'DRAFT',
    frozen         INTEGER NOT NULL DEFAULT 0,
    created_by     TEXT NOT NULL DEFAULT '',
    approved_by    TEXT NOT NULL DEFAULT '',
    approved_at    TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scenario_results (
    result_id      TEXT PRIMARY KEY,
    tenant_id      TEXT NOT NULL DEFAULT 'tenant_default',
    scenario_id    TEXT NOT NULL,
    snapshot_id    TEXT NOT NULL,
    assumption_set_id TEXT NOT NULL,
    calculation_model_version TEXT NOT NULL,
    values_json    TEXT NOT NULL DEFAULT '{}',
    computed_by    TEXT NOT NULL DEFAULT '',
    computed_at    TEXT NOT NULL,
    UNIQUE (scenario_id, snapshot_id, assumption_set_id, calculation_model_version)
);
CREATE INDEX IF NOT EXISTS idx_result_scenario ON scenario_results(scenario_id);
"""


class ScenarioInputError(ValueError):
    """정책 위반 — 4xx 로 전달한다."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _checksum(values: Dict[str, Any]) -> str:
    """내용 지문. **같은 id 로 내용이 바뀌면 다른 스냅샷이다** — 재현 불가를 감지한다."""
    canon = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:32]


class ScenarioInputStore:
    def __init__(self, repository=None, clone=None):
        self._lock = threading.RLock()
        self._repo_override = repository
        self._clone_override = clone

    # 저장소·복제서비스를 **호출 시점에** 얻는다 — 값으로 바인딩하면 테스트 monkeypatch 가 안 먹는다.
    @property
    def _repo(self):
        if self._repo_override is not None:
            return self._repo_override
        from core.enterprise_context.repository import ecm_repository
        return ecm_repository

    @property
    def _clone(self):
        if self._clone_override is not None:
            return self._clone_override
        from core.enterprise_context.clone_service import clone_service
        return clone_service

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._repo.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout = 5000")
        except Exception:
            pass
        conn.executescript(_DDL)
        return conn

    # ── 가정 세트 ─────────────────────────────────────────────────────────
    def create_assumption_set(self, name: str, purpose: str, values: Dict[str, Any],
                              evidence: Dict[str, str], scope_node_id: str = "",
                              tenant_id: str = "tenant_default", actor: str = "",
                              supersedes: str = "", version: int = 1) -> Dict[str, Any]:
        """가정값 묶음을 만든다(DRAFT). **가정값마다 근거가 있어야 한다.**

        ⚠️ 근거를 선택 항목으로 두면 아무도 채우지 않는다. 그리고 근거 없는 가정은 계산을 통과한
          뒤 결과 숫자로만 남아, 나중에는 그 숫자가 어디서 왔는지 아무도 모른다."""
        if not (name or "").strip():
            raise ScenarioInputError("가정 세트 이름(name)은 필수입니다.")
        if not (purpose or "").strip():
            raise ScenarioInputError(
                "가정 세트의 목적(purpose)은 필수입니다 — 목적 없는 가정은 재사용도 폐기도 "
                "판단할 수 없습니다.")
        if not values:
            raise ScenarioInputError("가정값(values)이 비어 있습니다.")
        ev = {k: str(v).strip() for k, v in (evidence or {}).items() if str(v).strip()}
        missing = [k for k in values if k not in ev]
        if missing:
            raise ScenarioInputError(
                f"근거(evidence)가 없는 가정값이 있습니다: {sorted(missing)} — 근거 없는 가정은 "
                f"추측이고, 추측이 계산에 들어가면 결과가 사실처럼 보입니다(비협상 3).")
        aid = f"asm_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO assumption_sets (assumption_set_id, tenant_id, scope_node_id, name, "
                "purpose, values_json, evidence_json, status, version, supersedes, frozen, "
                "created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?,?)",
                (aid, tenant_id, scope_node_id, name.strip(), purpose.strip(),
                 json.dumps(values, ensure_ascii=False), json.dumps(ev, ensure_ascii=False),
                 DRAFT, int(version), supersedes, actor or "", now, now))
            conn.commit()
        self._audit(aid, actor, "가정 세트 생성", f"항목={len(values)}건 목적={purpose.strip()[:60]}")
        return self.get_assumption_set(aid)

    def approve_assumption_set(self, assumption_set_id: str, actor: str = "") -> Dict[str, Any]:
        """승인. **승인된 가정만 계산에 쓸 수 있다.**"""
        a = self._require_assumption(assumption_set_id)
        if a["status"] == SUPERSEDED:
            raise ScenarioInputError("대체된(SUPERSEDED) 가정 세트는 승인할 수 없습니다.")
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE assumption_sets SET status=?, approved_by=?, approved_at=?, "
                         "updated_at=? WHERE assumption_set_id=?",
                         (APPROVED, actor or "", now, now, assumption_set_id))
            conn.commit()
        self._audit(assumption_set_id, actor, "가정 세트 승인", "이후 계산에 사용 가능")
        return self.get_assumption_set(assumption_set_id)

    def revise_assumption_set(self, assumption_set_id: str, values: Dict[str, Any],
                              evidence: Dict[str, str], actor: str = "",
                              purpose: str = "") -> Dict[str, Any]:
        """개정 — **새 버전을 만든다. 원본을 고치지 않는다.**

        ⚠️ 동결된(계산에 쓰인) 가정 세트를 제자리에서 고치면 과거 결과의 근거가 사라진다.
          "그때 무슨 가정이었나"에 답할 수 없는 결과는 근거가 아니다."""
        cur = self._require_assumption(assumption_set_id)
        new = self.create_assumption_set(
            name=cur["name"], purpose=(purpose or cur["purpose"]), values=values,
            evidence=evidence, scope_node_id=cur["scope_node_id"],
            tenant_id=cur["tenant_id"], actor=actor,
            supersedes=assumption_set_id, version=int(cur["version"]) + 1)
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE assumption_sets SET status=?, updated_at=? "
                         "WHERE assumption_set_id=?", (SUPERSEDED, _now(), assumption_set_id))
            conn.commit()
        self._audit(new["assumption_set_id"], actor, "가정 세트 개정",
                    f"v{cur['version']}→v{new['version']} 원본={assumption_set_id}"
                    f"{' (동결본 — 원본 보존)' if cur['frozen'] else ''}")
        return self.get_assumption_set(new["assumption_set_id"])

    def get_assumption_set(self, assumption_set_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM assumption_sets WHERE assumption_set_id=?",
                             (assumption_set_id,)).fetchone()
        return self._row(r, ("values", "evidence")) if r else None

    def list_assumption_sets(self, status: str = "", scope_node_id: str = "") -> List[Dict[str, Any]]:
        sql, params, where = "SELECT * FROM assumption_sets", [], []
        if status:
            where.append("status=?"); params.append(status)
        if scope_node_id:
            where.append("scope_node_id=?"); params.append(scope_node_id)
        if where:
            sql += " WHERE " + " AND ".join(where)
        with self._connect() as conn:
            rows = conn.execute(sql + " ORDER BY created_at DESC", tuple(params)).fetchall()
        return [self._row(r, ("values", "evidence")) for r in rows]

    def _require_assumption(self, aid: str) -> Dict[str, Any]:
        a = self.get_assumption_set(aid)
        if not a:
            raise ScenarioInputError(f"가정 세트를 찾을 수 없습니다: {aid}")
        return a

    # ── 기준선 스냅샷 ─────────────────────────────────────────────────────
    def create_snapshot(self, name: str, as_of: str, values: Dict[str, Any], source: str,
                        scope_node_id: str = "", entity_mode: str = "REAL",
                        tenant_id: str = "tenant_default", actor: str = "") -> Dict[str, Any]:
        """기준선 집계를 스냅샷으로 고정한다(DRAFT).

        `as_of`(언제 기준)와 `source`(어디서 온 집계)를 요구한다 — 둘 중 하나가 없으면 그 숫자는
        비교 기준으로 쓸 수 없다. "작년 실적"과 "이번 달 추정"을 같은 칼럼에서 비교하는 순간
        결과는 의미를 잃는다."""
        if not (name or "").strip():
            raise ScenarioInputError("스냅샷 이름(name)은 필수입니다.")
        if not (as_of or "").strip():
            raise ScenarioInputError(
                "기준 시점(as_of)은 필수입니다 — 언제 기준인지 모르는 집계는 비교 기준이 "
                "될 수 없습니다.")
        if not (source or "").strip():
            raise ScenarioInputError(
                "출처(source)는 필수입니다 — 어디서 온 집계인지 없으면 근거가 되지 못합니다.")
        if not values:
            raise ScenarioInputError("스냅샷 값(values)이 비어 있습니다.")
        # ★★ 가상에서 나온 값이 실제 기준선으로 스며드는 것을 막는다(§8.3 저장소 쪽 방어선).
        src = source.strip()
        if entity_mode == "REAL" and (src.startswith("scenario:") or src.startswith("scn_")):
            raise ScenarioInputError(
                "시나리오에서 나온 값을 실제(REAL) 기준선으로 등록할 수 없습니다 — 가상 결과를 "
                "실제에 반영하려면 승격 요청을 통해 사람이 승인해야 합니다(§8.3).")
        sid = f"snap_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO baseline_snapshots (snapshot_id, tenant_id, scope_node_id, name, "
                "as_of, source, entity_mode, values_json, checksum, status, frozen, created_by, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?,?)",
                (sid, tenant_id, scope_node_id, name.strip(), as_of.strip(), src, entity_mode,
                 json.dumps(values, ensure_ascii=False), _checksum(values), DRAFT,
                 actor or "", now, now))
            conn.commit()
        self._audit(sid, actor, "기준선 스냅샷 생성",
                    f"as_of={as_of} source={src[:60]} 항목={len(values)}건 mode={entity_mode}")
        return self.get_snapshot(sid)

    def approve_snapshot(self, snapshot_id: str, actor: str = "") -> Dict[str, Any]:
        s = self._require_snapshot(snapshot_id)
        if not s["checksum_ok"]:
            raise ScenarioInputError(
                "스냅샷 내용이 등록 시점과 다릅니다(체크섬 불일치) — 승인할 수 없습니다.")
        now = _now()
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE baseline_snapshots SET status=?, approved_by=?, approved_at=?, "
                         "updated_at=? WHERE snapshot_id=?",
                         (APPROVED, actor or "", now, now, snapshot_id))
            conn.commit()
        self._audit(snapshot_id, actor, "기준선 스냅샷 승인", "이후 계산의 기준선으로 사용 가능")
        return self.get_snapshot(snapshot_id)

    def get_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM baseline_snapshots WHERE snapshot_id=?",
                             (snapshot_id,)).fetchone()
        if not r:
            return None
        d = self._row(r, ("values",))
        # 내용이 등록 시점과 같은가 — 다르면 재현이 불가능하므로 소리 내어 알린다.
        d["checksum_ok"] = (_checksum(d["values"]) == d["checksum"])
        if not d["checksum_ok"]:
            d["warning"] = ("⚠️ 등록 시점과 내용이 다릅니다 — 이 스냅샷으로 계산한 결과는 "
                            "재현할 수 없습니다.")
        return d

    def list_snapshots(self, status: str = "", entity_mode: str = "") -> List[Dict[str, Any]]:
        sql, params, where = "SELECT snapshot_id FROM baseline_snapshots", [], []
        if status:
            where.append("status=?"); params.append(status)
        if entity_mode:
            where.append("entity_mode=?"); params.append(entity_mode)
        if where:
            sql += " WHERE " + " AND ".join(where)
        with self._connect() as conn:
            ids = [r[0] for r in conn.execute(sql + " ORDER BY created_at DESC",
                                              tuple(params)).fetchall()]
        return [self.get_snapshot(i) for i in ids]

    def _require_snapshot(self, sid: str) -> Dict[str, Any]:
        s = self.get_snapshot(sid)
        if not s:
            raise ScenarioInputError(f"스냅샷을 찾을 수 없습니다: {sid}")
        return s

    # ── 계산 결과 ─────────────────────────────────────────────────────────
    def record_result(self, scenario_id: str, snapshot_id: str, assumption_set_id: str,
                      calculation_model_version: str, values: Dict[str, Any],
                      actor: str = "", tenant_id: str = "tenant_default") -> Dict[str, Any]:
        """결정론적 계산 결과를 등록한다. **등록하는 순간 입력이 동결된다.**

        ★ 이 모듈은 계산하지 않는다 — 엔진이 계산하고 결과를 여기에 남긴다(§8.2: LLM 은 계산값을
          만들지 않는다). 여기서 하는 일은 "이 결과가 어떤 입력에서 나왔는가"를 잠그는 것이다."""
        scn = self._clone.get_scenario(scenario_id)
        if not scn:
            raise ScenarioInputError(f"시나리오를 찾을 수 없습니다: {scenario_id}")
        if scn["status"] == "CLOSED":
            raise ScenarioInputError("종료된 시나리오에는 결과를 기록할 수 없습니다.")
        if scn["expired"]:
            raise ScenarioInputError(
                f"만료된 시나리오에는 결과를 기록할 수 없습니다(만료 {scn['valid_until']}).")
        if not (calculation_model_version or "").strip():
            raise ScenarioInputError(
                "계산 모델 버전(calculation_model_version)은 필수입니다 — 어떤 모델이 낸 숫자인지 "
                "없으면 재현할 수 없습니다(§8.1).")
        if not values:
            raise ScenarioInputError("결과 값(values)이 비어 있습니다.")
        a = self._require_assumption(assumption_set_id)
        if a["status"] != APPROVED:
            raise ScenarioInputError(
                f"승인되지 않은 가정 세트로는 계산 결과를 기록할 수 없습니다"
                f"(현재 {a['status']}) — 승인 전 가정으로 낸 숫자는 기준이 될 수 없습니다.")
        s = self._require_snapshot(snapshot_id)
        if s["status"] != APPROVED:
            raise ScenarioInputError(
                f"승인되지 않은 기준선으로는 계산 결과를 기록할 수 없습니다(현재 {s['status']}).")
        if not s["checksum_ok"]:
            raise ScenarioInputError("기준선 내용이 등록 시점과 다릅니다(체크섬 불일치).")

        rid = f"res_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self._lock, self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO scenario_results (result_id, tenant_id, scenario_id, snapshot_id, "
                    "assumption_set_id, calculation_model_version, values_json, computed_by, "
                    "computed_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (rid, tenant_id, scenario_id, snapshot_id, assumption_set_id,
                     calculation_model_version.strip(),
                     json.dumps(values, ensure_ascii=False), actor or "", now))
            except sqlite3.IntegrityError:
                raise ScenarioInputError(
                    "같은 입력 조합(시나리오·기준선·가정·모델버전)의 결과가 이미 있습니다 — "
                    "결정론적 계산은 같은 입력에 같은 답을 냅니다. 입력을 바꾸거나 기존 결과를 "
                    "보십시오.")
            # ★ 입력 동결 — 이 시점 이후 두 입력은 제자리에서 바뀔 수 없다.
            conn.execute("UPDATE assumption_sets SET frozen=1, updated_at=? "
                         "WHERE assumption_set_id=?", (now, assumption_set_id))
            conn.execute("UPDATE baseline_snapshots SET frozen=1, updated_at=? "
                         "WHERE snapshot_id=?", (now, snapshot_id))
            conn.commit()
        self._audit(rid, actor, "계산 결과 기록(입력 동결)",
                    f"scenario={scenario_id} snapshot={snapshot_id} "
                    f"assumptions={assumption_set_id} model={calculation_model_version} "
                    f"항목={len(values)}건")
        return self.get_result(rid)

    def get_result(self, result_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM scenario_results WHERE result_id=?",
                             (result_id,)).fetchone()
        return self._row(r, ("values",)) if r else None

    def list_results(self, scenario_id: str = "") -> List[Dict[str, Any]]:
        sql, params = "SELECT * FROM scenario_results", ()
        if scenario_id:
            sql += " WHERE scenario_id=?"; params = (scenario_id,)
        with self._connect() as conn:
            rows = conn.execute(sql + " ORDER BY computed_at DESC", params).fetchall()
        return [self._row(r, ("values",)) for r in rows]

    # ── 공통 ──────────────────────────────────────────────────────────────
    @staticmethod
    def _row(r: sqlite3.Row, json_fields) -> Dict[str, Any]:
        d = dict(r)
        for f in json_fields:
            try:
                d[f] = json.loads(d.pop(f + "_json") or "{}")
            except Exception:
                d[f] = {}
        if "frozen" in d:
            d["frozen"] = bool(d["frozen"])
        return d

    @staticmethod
    def _audit(resource_id: str, actor: str, reason: str, detail: str) -> None:
        try:
            from core.enterprise_context import audit
            audit.record(audit.SCENARIO_INPUT_CHANGED, resource_type="scenario_input",
                         resource_id=resource_id, actor=actor or "", outcome="allowed",
                         reason=reason, detail=detail)
        except Exception as e:                                       # pragma: no cover
            print(f"⚠️ [scenario_inputs] 감사 기록 실패({resource_id}): {e}")


scenario_inputs = ScenarioInputStore()
