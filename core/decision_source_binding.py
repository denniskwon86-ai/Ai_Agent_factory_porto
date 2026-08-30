"""Decision Package 가 선택할 수 있는 시뮬레이션 실행의 서버 정본.

화면은 사람이 읽는 시나리오명·기간·기준선명을 보여 주지만, 결속은 내부 실행 ID로 한다.
생성 시에도 이 모듈이 같은 행을 다시 읽어 기준선·시나리오·조직을 파생한다. 목록과 생성이
서로 다른 판정을 가지면 목록에서는 가능해 보인 실행이 생성 단계에서 다른 실행으로 바뀐다.
"""
from __future__ import annotations

import json
from typing import Any, Iterable

from core.planning_model import PlanningStore


class DecisionSourceError(ValueError):
    """결속할 수 없는 실행."""


class DecisionSourceNotFound(DecisionSourceError):
    """없거나 요청자 범위 밖인 실행. 존재 여부를 구분하지 않는다."""


class DecisionSourceBlocked(DecisionSourceError):
    """실행은 보이지만 안건의 근거로 쓸 수 없다."""


_BASELINE_LABEL = {"PLAN": "계획", "ACTUAL": "실적", "FORECAST": "예측"}


class DecisionSourceCatalog:
    def __init__(self, store: PlanningStore | None = None):
        self._explicit_store = store

    @property
    def store(self) -> PlanningStore:
        # 테스트·런타임 격리가 교체한 전역 저장소를 호출 시점에 읽는다.
        if self._explicit_store is not None:
            return self._explicit_store
        from core.planning_model import planning_store
        return planning_store

    @staticmethod
    def _metrics(raw: Any) -> dict[str, Any]:
        try:
            value = json.loads(str(raw or "{}"))
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _visible(scope_id: str, visible_scopes: Iterable[str] | None) -> bool:
        # None 은 무제한 주체다. 빈 집합은 아무 범위도 볼 수 없는 주체다.
        return visible_scopes is None or bool(scope_id and scope_id in set(visible_scopes))

    def _rows(self, run_id: str = "") -> list[dict[str, Any]]:
        conn = self.store._connect()
        try:
            sql = (
                "SELECT r.*, s.name AS scenario_name, s.org_id, s.baseline_kind, "
                "s.owner_organization_id, s.status AS scenario_status "
                "FROM simulation_runs r LEFT JOIN scenarios s ON s.scenario_id=r.scenario_id"
            )
            args: tuple[Any, ...] = ()
            if run_id:
                sql += " WHERE r.run_id=?"
                args = (run_id,)
            sql += " ORDER BY r.completed_at DESC, r.started_at DESC"
            return [dict(row) for row in conn.execute(sql, args)]
        finally:
            conn.close()

    def _option(self, row: dict[str, Any]) -> dict[str, Any]:
        metrics = self._metrics(row.get("metrics_json"))
        scope_id = str(row.get("owner_organization_id") or row.get("org_id") or "").strip()
        period = str(metrics.get("period") or "").strip()
        baseline_kind = str(metrics.get("baseline_kind") or row.get("baseline_kind") or "").upper()
        baseline_id = str(metrics.get("baseline_id") or "").strip()
        scenario_name = str(row.get("scenario_name") or "").strip()

        reasons: list[str] = []
        if not scenario_name:
            reasons.append("연결된 시나리오를 찾을 수 없습니다")
        if str(row.get("status") or "").lower() != "completed":
            reasons.append("실행이 완료되지 않았습니다")
        if not scope_id:
            reasons.append("소유 조직이 결속되지 않았습니다")
        if not (baseline_id and period and baseline_kind):
            reasons.append("기준선 결속 정보가 없는 이전 실행입니다")
        if metrics.get("complete") is not True:
            reasons.append("계산 결과가 완전하지 않습니다")
        if metrics.get("unapplied_assumptions"):
            reasons.append("적용되지 않은 가정이 있습니다")
        if metrics.get("driver_warnings"):
            reasons.append("동인 계산 경고가 남아 있습니다")

        baseline_name = _BASELINE_LABEL.get(baseline_kind, baseline_kind or "기준선 미확인")
        label_parts = [scenario_name or "이름 미등록 시나리오"]
        if period:
            label_parts.append(period)
        label_parts.append(f"{baseline_name} 기준")
        return {
            # API 결속용. 일반 화면에서는 value 로만 쓰고 문자열을 그리지 않는다.
            "run_id": str(row.get("run_id") or ""),
            "scenario_id": str(row.get("scenario_id") or ""),
            "baseline_id": baseline_id,
            "scope_id": scope_id,
            "scenario_label": scenario_name or "이름 미등록 시나리오",
            "baseline_label": f"{period + ' · ' if period else ''}{baseline_name} 기준",
            "label": " · ".join(label_parts),
            "completed_at": str(row.get("completed_at") or ""),
            "engine_version": str(row.get("engine_version") or ""),
            "bindable": not reasons,
            "blocked_reason": " · ".join(reasons),
            "binding": {
                "run_id": str(row.get("run_id") or ""),
                "scenario_id": str(row.get("scenario_id") or ""),
                "baseline_id": baseline_id,
                "input_hash": str(row.get("input_hash") or ""),
                "engine_version": str(row.get("engine_version") or ""),
                "completed_at": str(row.get("completed_at") or ""),
                "period": period,
                "baseline_kind": baseline_kind,
                "scenario_label": scenario_name or "이름 미등록 시나리오",
                "baseline_label": f"{period + ' · ' if period else ''}{baseline_name} 기준",
            },
        }

    def list_options(self, visible_scopes: Iterable[str] | None) -> list[dict[str, Any]]:
        options = [self._option(row) for row in self._rows()]
        return [item for item in options
                if self._visible(str(item.get("scope_id") or ""), visible_scopes)]

    def resolve(self, run_id: str, visible_scopes: Iterable[str] | None) -> dict[str, Any]:
        rows = self._rows(str(run_id or "").strip())
        if not rows:
            raise DecisionSourceNotFound("실행을 찾을 수 없습니다.")
        option = self._option(rows[0])
        if not self._visible(str(option.get("scope_id") or ""), visible_scopes):
            raise DecisionSourceNotFound("실행을 찾을 수 없습니다.")
        if not option["bindable"]:
            raise DecisionSourceBlocked(str(option["blocked_reason"]))
        return option


decision_sources = DecisionSourceCatalog()
