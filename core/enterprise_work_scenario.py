"""부서별 업무 시뮬레이션 결과를 하나의 전사 시나리오로 결속한다.

이 저장소는 ECM 가상회사 시나리오나 단일 기준선 ``scenario_results`` 와 다르다.
경로 계산은 여러 인증판과 관계 승인을 함께 쓰므로 단일 snapshot/assumption 칸에
넣으면 근거가 사라진다. 여기서는 계산하지 않고, 제품 계산 경로가 봉인한 구간 결과를
부서 앱별 append-only 기여로 보존한다.

LLM 0콜.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

OPEN = "OPEN"
CLOSED = "CLOSED"

APP_SEGMENTS = {
    "APP-01": ("procurement", "CALC.LOGISTICS.ARRIVAL_DELAY.v1"),
    "APP-03": ("production", "CALC.INVENTORY.MATERIAL_SHORTAGE.v1"),
    "APP-06": ("sales", "CALC.PRODUCTION.REVENUE_TIMING.v1"),
}
REQUIRED_APPS = tuple(APP_SEGMENTS)

_DDL = """
CREATE TABLE IF NOT EXISTS enterprise_work_scenarios (
    scenario_id   TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL,
    instance_id   TEXT NOT NULL,
    scope_node_id TEXT NOT NULL,
    entity_mode   TEXT NOT NULL,
    name           TEXT NOT NULL,
    purpose        TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'OPEN',
    created_by     TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    CHECK (status IN ('OPEN', 'CLOSED'))
);
CREATE INDEX IF NOT EXISTS idx_work_scenario_context
ON enterprise_work_scenarios(tenant_id, instance_id, updated_at);

CREATE TABLE IF NOT EXISTS enterprise_work_scenario_contributions (
    contribution_id       TEXT PRIMARY KEY,
    scenario_id           TEXT NOT NULL,
    app_id                TEXT NOT NULL,
    department_role       TEXT NOT NULL,
    segment_ref           TEXT NOT NULL,
    as_of                 TEXT NOT NULL,
    query_id              TEXT NOT NULL,
    path_fingerprint      TEXT NOT NULL,
    request_fingerprint   TEXT NOT NULL,
    result_fingerprint    TEXT NOT NULL,
    capability_fingerprint TEXT NOT NULL,
    model_version         TEXT NOT NULL,
    values_json           TEXT NOT NULL,
    used_snapshots_json   TEXT NOT NULL,
    relation_ids_json     TEXT NOT NULL,
    assumptions_json      TEXT NOT NULL,
    created_by            TEXT NOT NULL,
    created_at            TEXT NOT NULL,
    FOREIGN KEY (scenario_id) REFERENCES enterprise_work_scenarios(scenario_id),
    UNIQUE (scenario_id, app_id, result_fingerprint)
);
CREATE INDEX IF NOT EXISTS idx_work_contribution_scenario
ON enterprise_work_scenario_contributions(scenario_id, created_at);
"""


class WorkScenarioError(ValueError):
    """사용자 입력·상태 계약 위반(4xx)."""


class WorkScenarioStoreError(RuntimeError):
    """저장소를 읽거나 기록하지 못한 상태(503)."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class EnterpriseWorkScenarioStore:
    def __init__(self, repository=None):
        self._repo_override = repository
        self._lock = threading.RLock()

    @property
    def _repo(self):
        # 호출 시점에 얻는다. import 시점에 운영 경로를 굳히거나 파일을 만들지 않는다.
        if self._repo_override is not None:
            return self._repo_override
        from core.enterprise_context.repository import ecm_repository
        return ecm_repository

    def _connect(self) -> sqlite3.Connection:
        try:
            path = str(self._repo.db_path)
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            conn = sqlite3.connect(path, timeout=15.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout=15000")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(_DDL)
            return conn
        except (OSError, sqlite3.Error) as exc:
            raise WorkScenarioStoreError(
                f"전사 업무 시나리오 저장소를 준비하지 못했습니다: {exc}") from exc

    @staticmethod
    def _decode_contribution(row: sqlite3.Row) -> Dict[str, Any]:
        out = dict(row)
        for column, target in (
            ("values_json", "values"),
            ("used_snapshots_json", "used_snapshots"),
            ("relation_ids_json", "required_relation_ids"),
            ("assumptions_json", "assumptions_used"),
        ):
            try:
                out[target] = json.loads(out.pop(column))
            except (TypeError, ValueError) as exc:
                raise WorkScenarioStoreError(
                    f"전사 업무 시나리오 기여의 {column}을 읽지 못했습니다.") from exc
        return out

    def _decorate(self, row: sqlite3.Row, contributions: List[Dict[str, Any]]) -> Dict[str, Any]:
        out = dict(row)
        latest: Dict[str, Dict[str, Any]] = {}
        for item in contributions:
            latest[item["app_id"]] = item
        present = [app_id for app_id in REQUIRED_APPS if app_id in latest]
        missing = [app_id for app_id in REQUIRED_APPS if app_id not in latest]
        out["contributions"] = contributions
        out["latest_by_app"] = latest
        out["coverage"] = {
            "required_apps": list(REQUIRED_APPS),
            "present_apps": present,
            "missing_apps": missing,
            "ready_for_enterprise": not missing,
        }
        return out

    def create(self, *, tenant_id: str, instance_id: str, scope_node_id: str,
               entity_mode: str, name: str, purpose: str, actor: str) -> Dict[str, Any]:
        name = str(name or "").strip()
        purpose = str(purpose or "").strip()
        if not name:
            raise WorkScenarioError("전사 시나리오 이름은 필수입니다.")
        if not purpose:
            raise WorkScenarioError("전사 시나리오 목적은 필수입니다.")
        if len(name) > 120 or len(purpose) > 500:
            raise WorkScenarioError("시나리오 이름 또는 목적이 허용 길이를 넘었습니다.")
        required = {"tenant_id": tenant_id, "instance_id": instance_id,
                    "scope_node_id": scope_node_id, "entity_mode": entity_mode,
                    "actor": actor}
        if any(not str(value or "").strip() for value in required.values()):
            raise WorkScenarioError("시나리오의 조직 문맥과 작성자를 확인할 수 없습니다.")
        scenario_id = f"ews_{uuid.uuid4().hex[:16]}"
        now = _now()
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    "INSERT INTO enterprise_work_scenarios "
                    "(scenario_id,tenant_id,instance_id,scope_node_id,entity_mode,name,purpose,"
                    "status,created_by,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (scenario_id, tenant_id, instance_id, scope_node_id, entity_mode,
                     name, purpose, OPEN, actor, now, now))
                conn.commit()
        except sqlite3.Error as exc:
            raise WorkScenarioStoreError(
                f"전사 업무 시나리오를 저장하지 못했습니다: {exc}") from exc
        return self.require(scenario_id)

    def get(self, scenario_id: str) -> Optional[Dict[str, Any]]:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM enterprise_work_scenarios WHERE scenario_id=?",
                    (scenario_id,)).fetchone()
                if not row:
                    return None
                contrib_rows = conn.execute(
                    "SELECT * FROM enterprise_work_scenario_contributions "
                    "WHERE scenario_id=? ORDER BY created_at, contribution_id",
                    (scenario_id,)).fetchall()
        except sqlite3.Error as exc:
            raise WorkScenarioStoreError(
                f"전사 업무 시나리오를 읽지 못했습니다: {exc}") from exc
        return self._decorate(row, [self._decode_contribution(r) for r in contrib_rows])

    def require(self, scenario_id: str) -> Dict[str, Any]:
        row = self.get(str(scenario_id or "").strip())
        if not row:
            raise WorkScenarioError("전사 업무 시나리오를 찾을 수 없습니다.")
        return row

    def list_for(self, *, tenant_id: str, instance_id: str) -> List[Dict[str, Any]]:
        try:
            with self._connect() as conn:
                ids = [r[0] for r in conn.execute(
                    "SELECT scenario_id FROM enterprise_work_scenarios "
                    "WHERE tenant_id=? AND instance_id=? ORDER BY updated_at DESC, scenario_id",
                    (tenant_id, instance_id)).fetchall()]
        except sqlite3.Error as exc:
            raise WorkScenarioStoreError(
                f"전사 업무 시나리오 목록을 읽지 못했습니다: {exc}") from exc
        return [self.require(scenario_id) for scenario_id in ids]

    def record_contribution(self, *, scenario_id: str, app_id: str,
                            result: Dict[str, Any], as_of: str,
                            tenant_id: str, instance_id: str,
                            scope_node_id: str, entity_mode: str,
                            actor: str) -> Dict[str, Any]:
        if app_id not in APP_SEGMENTS:
            raise WorkScenarioError(
                "이 앱은 부서 계산 기여를 등록할 수 없습니다. APP-07은 세 부서 결과를 집계합니다.")
        if str(result.get("status") or "") != "COMPLETE":
            raise WorkScenarioError("완료되지 않은 계산은 전사 시나리오에 저장할 수 없습니다.")
        role, segment_ref = APP_SEGMENTS[app_id]
        outputs = result.get("segment_outputs")
        if not isinstance(outputs, dict) or not isinstance(outputs.get(segment_ref), dict):
            raise WorkScenarioError("해당 업무 앱의 계산 구간 결과를 확인할 수 없습니다.")
        required = {
            "as_of": as_of,
            "query_id": result.get("query_id"),
            "path_fingerprint": result.get("path_fingerprint"),
            "request_fingerprint": result.get("request_fingerprint"),
            "result_fingerprint": result.get("result_fingerprint"),
        }
        missing = [key for key, value in required.items() if not str(value or "").strip()]
        if missing:
            raise WorkScenarioError(f"계산 결과 결속 정보가 비어 있습니다: {', '.join(missing)}")
        used = result.get("used_snapshots")
        rels = result.get("required_relation_ids")
        cap_fps = result.get("capability_fingerprints")
        versions = result.get("segment_model_versions")
        if not isinstance(used, dict) or not used:
            raise WorkScenarioError("계산에 사용한 인증판을 확인할 수 없습니다.")
        if not isinstance(rels, list) or not rels:
            raise WorkScenarioError("계산에 사용한 승인 관계를 확인할 수 없습니다.")
        if not isinstance(cap_fps, dict) or not str(cap_fps.get(segment_ref) or ""):
            raise WorkScenarioError("계산 능력 지문을 확인할 수 없습니다.")
        if not isinstance(versions, dict) or not str(versions.get(segment_ref) or ""):
            raise WorkScenarioError("계산 모델 판을 확인할 수 없습니다.")

        now = _now()
        contribution_id = f"ewc_{uuid.uuid4().hex[:16]}"
        try:
            with self._lock, self._connect() as conn:
                # 프로세스가 둘이어도 중복 확인과 삽입 사이에 다른 쓰기가 끼지 않는다.
                # UNIQUE만 믿으면 두 프로세스가 동시에 처음 저장할 때 한쪽은 멱등 재시도가
                # 아니라 500/잠금 오류로 보인다.
                conn.execute("BEGIN IMMEDIATE")
                scenario = conn.execute(
                    "SELECT * FROM enterprise_work_scenarios WHERE scenario_id=?",
                    (scenario_id,)).fetchone()
                if not scenario:
                    raise WorkScenarioError("전사 업무 시나리오를 찾을 수 없습니다.")
                if scenario["status"] != OPEN:
                    raise WorkScenarioError("종료된 전사 시나리오에는 결과를 추가할 수 없습니다.")
                expected = (scenario["tenant_id"], scenario["instance_id"],
                            scenario["scope_node_id"], scenario["entity_mode"])
                actual = (tenant_id, instance_id, scope_node_id, entity_mode)
                if expected != actual:
                    raise WorkScenarioError("계산 결과의 조직 문맥이 전사 시나리오와 다릅니다.")
                duplicate = conn.execute(
                    "SELECT * FROM enterprise_work_scenario_contributions "
                    "WHERE scenario_id=? AND app_id=? AND result_fingerprint=?",
                    (scenario_id, app_id, required["result_fingerprint"])).fetchone()
                if duplicate:
                    out = self._decode_contribution(duplicate)
                    out["idempotent"] = True
                    return out
                conn.execute(
                    "INSERT INTO enterprise_work_scenario_contributions "
                    "(contribution_id,scenario_id,app_id,department_role,segment_ref,as_of,"
                    "query_id,path_fingerprint,request_fingerprint,result_fingerprint,"
                    "capability_fingerprint,model_version,values_json,used_snapshots_json,"
                    "relation_ids_json,assumptions_json,created_by,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (contribution_id, scenario_id, app_id, role, segment_ref, as_of,
                     required["query_id"], required["path_fingerprint"],
                     required["request_fingerprint"], required["result_fingerprint"],
                     str(cap_fps[segment_ref]), str(versions[segment_ref]),
                     _json(outputs[segment_ref]), _json(used), _json(sorted(rels)),
                     _json(result.get("assumptions_used") or {}), actor, now))
                conn.execute(
                    "UPDATE enterprise_work_scenarios SET updated_at=? WHERE scenario_id=?",
                    (now, scenario_id))
                conn.commit()
                row = conn.execute(
                    "SELECT * FROM enterprise_work_scenario_contributions WHERE contribution_id=?",
                    (contribution_id,)).fetchone()
        except WorkScenarioError:
            raise
        except sqlite3.Error as exc:
            raise WorkScenarioStoreError(
                f"부서 계산 결과를 전사 시나리오에 저장하지 못했습니다: {exc}") from exc
        out = self._decode_contribution(row)
        out["idempotent"] = False
        return out


enterprise_work_scenarios = EnterpriseWorkScenarioStore()
