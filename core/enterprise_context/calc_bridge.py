"""[ECM E3 ↔ M4] 계산 엔진 연결 — **ECM 가정 세트가 엔진 가정의 원본이 된다.**

## 왜 다리가 필요한가

두 세계가 나란히 있었다:

- **ECM**(`scenario_inputs.py`): 가정 세트에 근거·승인·동결이 붙는다. §8.1 의 실행 문맥 키를 갖는다.
- **엔진**(`core/planning_*`): 자체 `scenarios` · `scenario_assumptions` 표로 결정론적 계산을 한다.

연결이 없으면 결과를 **사람이 손으로 옮겨** `POST /results` 에 넣어야 한다. 그러면 두 곳의
가정이 조용히 달라진다 — 엔진에서는 +12%로 계산하고 ECM 기록에는 +10%로 남는 상황이 생기고,
그때 비교표의 근거는 거짓이 된다.

⚠️ 이 유형이 이 저장소에서 반복된 실패다: 같은 사실이 두 곳에 선언되면 반드시 갈라진다
  (라이브러리 경로 · `owner_org_id`/`scope_code` · 부서/코드/노드). 그래서 **원본을 하나로 둔다**:
  ECM 가정 세트가 원본이고, 엔진 가정은 그것에서 파생된다.

## 키 규약 — 모호한 것은 거부한다

ECM 가정 세트의 키는 엔진 가정으로 번역돼야 한다. 규약:

    "account:<계정코드>:<pct|delta|set>"   예) "account:4000:pct"
    "driver:<동인코드>:<pct|delta|set>"    예) "driver:ENERGY_PRICE:pct"

★ **규약에 맞지 않는 키는 조용히 무시하지 않고 거부한다.** 무시하면 그 가정만 계산에서 빠지고,
  결과는 정상처럼 보인다 — 사람은 12개 가정을 넣었다고 믿는데 실제로는 9개만 반영된 상태다.
  이 저장소가 "필터를 부르지 않으면 통제가 없다"에서 배운 것과 같은 교훈이다.

## 무엇을 하지 않는가

- **계산하지 않는다.** `planning_engine.run_scenario()` 가 계산한다.
- **엔진 결과를 고치지 않는다.** 받은 값을 그대로 `scenario_results` 에 남긴다.
- 값을 지어내지 않는다 — 기준선이 비면 엔진이 거부하고, 그 오류를 그대로 전달한다.

LLM 0콜.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

#: 가정 키 규약. 대상 종류 · 코드 · 연산자.
_KEY_RE = re.compile(r"^(account|driver):([A-Za-z0-9_.\-]{1,40}):(pct|delta|set)$")
_OPERATORS = ("pct", "delta", "set")


class CalcBridgeError(ValueError):
    """번역·실행 불가 — 4xx 로 전달한다."""


def parse_assumption_key(key: str) -> Tuple[str, str, str]:
    """`"account:4000:pct"` → `("account", "4000", "pct")`. 규약 위반은 거부한다."""
    m = _KEY_RE.match((key or "").strip())
    if not m:
        raise CalcBridgeError(
            f"가정 키가 규약에 맞지 않습니다: '{key}'. 형식은 "
            f"'account:<계정코드>:<pct|delta|set>' 또는 'driver:<동인코드>:<pct|delta|set>' 입니다 "
            f"— 규약 밖의 키를 조용히 무시하면 그 가정만 계산에서 빠지고 결과는 정상처럼 보입니다.")
    return m.group(1), m.group(2), m.group(3)


def translate_assumptions(values: Dict[str, Any],
                          evidence: Dict[str, str]) -> List[Dict[str, Any]]:
    """ECM 가정 세트 → 엔진 가정 행. **근거를 함께 옮긴다.**

    엔진도 `rationale` 을 필수로 요구한다(근거 없는 가정은 재현이 아니라 창작이다). ECM 쪽
    근거를 그대로 실어 보내므로 두 곳의 근거가 갈라지지 않는다."""
    if not values:
        raise CalcBridgeError("가정값이 비어 있습니다.")
    out: List[Dict[str, Any]] = []
    for k in sorted(values):
        kind, code, op = parse_assumption_key(k)
        v = values[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise CalcBridgeError(
                f"가정값은 숫자여야 합니다: '{k}' = {v!r} — 문자열을 숫자로 해석하면 근사값이 "
                f"확정 계산의 입력이 됩니다.")
        rationale = (evidence or {}).get(k, "").strip()
        if not rationale:
            # ECM 쪽에서 이미 막지만, 다리에서도 확인한다 — 다리를 직접 부르는 경로가 생길 수 있다.
            raise CalcBridgeError(f"가정 '{k}' 의 근거가 없습니다 — 엔진도 근거를 요구합니다.")
        out.append({"target_kind": kind, "target_code": code, "operator": op,
                    "value": float(v), "rationale": rationale, "unit": ""})
    return out


class CalcBridge:
    def __init__(self, store=None, engine=None, planning_store=None):
        self._store_override = store
        self._engine_override = engine
        self._ps_override = planning_store

    @property
    def _store(self):
        if self._store_override is not None:
            return self._store_override
        from core.enterprise_context.scenario_inputs import scenario_inputs
        return scenario_inputs

    @property
    def _engine(self):
        if self._engine_override is not None:
            return self._engine_override
        from core import planning_engine
        return planning_engine

    @property
    def _ps(self):
        if self._ps_override is not None:
            return self._ps_override
        from core.planning_model import planning_store
        return planning_store

    # ── 실행 ──────────────────────────────────────────────────────────────
    def run_and_record(self, ecm_scenario_id: str, assumption_set_id: str, snapshot_id: str,
                       org_id: str, period: str, baseline_kind: str = "PLAN",
                       actor: str = "", tenant_id: str = "tenant_default",
                       persist_engine_facts: bool = False) -> Dict[str, Any]:
        """ECM 가정 세트로 엔진을 돌리고 결과를 `scenario_results` 에 남긴다.

        순서가 중요하다:
          ① ECM 가정 세트를 읽는다(승인·근거는 ECM 이 이미 보증한다)
          ② 규약대로 엔진 가정으로 **번역**한다(규약 위반은 여기서 거부 — 부분 반영 방지)
          ③ 엔진 시나리오를 만들고 가정을 넣는다
          ④ 엔진을 돌린다(계산은 엔진이 한다)
          ⑤ 결과를 ECM 결과로 등록한다 → 이 시점에 가정·기준선이 **동결**된다

        ⚠️ ②가 ③보다 먼저인 이유: 번역을 하다 실패하면 **엔진 시나리오가 반쯤 만들어진 채로
          남는다.** 먼저 전부 번역해 보고, 통과한 뒤에 쓰기를 시작한다."""
        asm = self._store.get_assumption_set(assumption_set_id)
        if not asm:
            raise CalcBridgeError(f"가정 세트를 찾을 수 없습니다: {assumption_set_id}")
        if asm["status"] != "APPROVED":
            raise CalcBridgeError(
                f"승인되지 않은 가정 세트로는 계산할 수 없습니다(현재 {asm['status']}).")
        rows = translate_assumptions(asm["values"], asm["evidence"])   # ← 전부 번역 후에만 진행

        engine_scenario_id = f"ecm_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn = self._ps._connect()
        try:
            conn.execute(
                "INSERT INTO scenarios (scenario_id, name, org_id, baseline_kind, "
                "baseline_period, status, owner, created_at, tenant_id, entity_mode) "
                "VALUES (?,?,?,?,?,'draft',?,?,?,?)",
                (engine_scenario_id, f"[ECM] {asm['name']}", org_id, baseline_kind, period,
                 actor or "", now, tenant_id, "VIRTUAL"))
            for r in rows:
                conn.execute(
                    "INSERT INTO scenario_assumptions(assumption_id,scenario_id,target_kind,"
                    "target_code,operator,value,unit,rationale,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (uuid.uuid4().hex[:16], engine_scenario_id, r["target_kind"],
                     r["target_code"], r["operator"], r["value"], r["unit"],
                     r["rationale"], now))
            conn.commit()
        finally:
            conn.close()

        run = self._engine.run_scenario(engine_scenario_id, org_id, period,
                                        baseline_kind=baseline_kind,
                                        persist=persist_engine_facts)

        values = self._result_values(run)
        if not values:
            raise CalcBridgeError(
                "엔진이 비교 가능한 결과를 내지 않았습니다 — 빈 결과를 기록하면 '계산했다'는 "
                "기록만 남고 근거가 없습니다.")

        from core.planning_model import ENGINE_VERSION
        model_version = f"planning_engine_v{ENGINE_VERSION}"
        recorded = self._store.record_result(
            ecm_scenario_id, snapshot_id, assumption_set_id, model_version, values,
            actor=actor, tenant_id=tenant_id)
        recorded["engine"] = {
            "engine_scenario_id": engine_scenario_id,
            "run_id": run.get("run_id", ""),
            # 엔진의 입력 지문 — 같은 기준선·가정이었는지 나중에 검증할 수 있다.
            "input_hash": run.get("input_hash", ""),
            "engine_version": run.get("engine_version", ""),
            "baseline_kind": baseline_kind, "org_id": org_id, "period": period,
            "translated_assumptions": len(rows),
            # 엔진이 쓰는 이름 그대로 옮긴다 — 이름을 바꾸면 엔진 문서와 대조할 수 없다.
            "unapplied_assumptions": run.get("unapplied_assumptions") or [],
            "driver_warnings": run.get("driver_warnings") or [],
        }
        # 반영되지 않은 가정·동인 경고를 **소리 내어** 알린다.
        # ⚠️ 조용히 넘기면 "가정을 12개 넣었고 결과가 나왔다"로 읽힌다 — 실제로는 9개만 반영된
        #   결과일 수 있고, 그 상태에서 나온 숫자가 경영 판단에 쓰인다.
        problems = []
        if recorded["engine"]["unapplied_assumptions"]:
            problems.append(f"반영되지 않은 가정 "
                            f"{len(recorded['engine']['unapplied_assumptions'])}건")
        if recorded["engine"]["driver_warnings"]:
            problems.append(f"동인 경고 {len(recorded['engine']['driver_warnings'])}건")
        if problems:
            recorded["warning"] = (
                f"⚠️ {' · '.join(problems)} — 기준선에 없는 계정·동인이거나 파급 계수가 "
                f"미승인일 수 있습니다. 결과를 그대로 신뢰하지 마십시오.")
        return recorded

    @staticmethod
    def _result_values(run: Dict[str, Any]) -> Dict[str, Any]:
        """엔진 결과에서 **비교 가능한 숫자만** 뽑는다.

        ★ 엔진 결과에는 실행 메타(run_id·시각 등)도 섞여 있다. 그것까지 결과 값으로 넣으면
          비교표에 "run_id 가 달라졌다"는 행이 생긴다 — 의미 없는 차이가 표를 채운다."""
        after = run.get("result") or {}
        out: Dict[str, Any] = {}
        for k, v in (after.items() if isinstance(after, dict) else []):
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                out[k] = v
        return out


calc_bridge = CalcBridge()
