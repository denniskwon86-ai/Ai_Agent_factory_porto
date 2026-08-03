"""[ECM E3/E4] 결과 비교 — **실제·계획·예측·가상을 한 칼럼에 섞지 않는다.**

## 이 모듈이 존재하는 이유

§7.1 흐름의 마지막이 "결과·가정·근거·버전을 비교/승인" 이고, §8.1 은 "실제값, 계획, 예측,
시나리오, 경쟁사 참조는 **물리적/논리적 저장 영역과 조회 조건에서 분리한다**"고 못 박았다.

비교는 그 분리를 깨기 가장 쉬운 자리다. 두 숫자를 나란히 놓고 차이를 계산하는 순간, 한쪽이
확정 실적이고 다른 쪽이 가정이라는 사실이 **표에서 사라진다.** 그리고 그 표는 경영 판단에
쓰인다.

⚠️ 그래서 이 모듈은 값마다 상태(`mode`)와 근거를 **끝까지 들고 다닌다.** 차이(delta)를 주더라도
  "무엇과 무엇의 차이인가"를 같은 행에서 읽을 수 있어야 한다.

## 결손을 숨기지 않는다

기준선에만 있는 항목, 결과에만 있는 항목을 **따로 세어 돌려준다**. 교집합만 비교하고 조용히
넘어가면 "빠진 항목 없이 다 비교됐다"고 오해하게 된다 — M0-a 에서 겪은 유형이다.

## 무엇을 하지 않는가

- **계산하지 않는다.** 결정론적 엔진이 낸 결과를 읽어 비교만 한다(§8.2: LLM 은 계산값을
  만들지 않는다).
- **판단하지 않는다.** "좋아졌다/나빠졌다"를 붙이지 않는다 — 지표의 방향은 도메인 지식이고,
  여기서 추측하면 틀린 방향을 자신 있게 말하게 된다.

LLM 0콜.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

#: 값의 상태 — §8.1 의 분리 대상. 비교 결과의 모든 값이 이 중 하나를 들고 다닌다.
MODE_ACTUAL = "ACTUAL"          # 확정 실적
MODE_PLAN = "PLAN"              # 계획
MODE_FORECAST = "FORECAST"      # 예측
MODE_SCENARIO = "SCENARIO"      # 가상 시나리오 계산 결과
MODE_COMPETITOR = "COMPETITOR"  # 경쟁사 참조(추정)
MODES = (MODE_ACTUAL, MODE_PLAN, MODE_FORECAST, MODE_SCENARIO, MODE_COMPETITOR)

MODE_KO = {
    MODE_ACTUAL: "확정 실적", MODE_PLAN: "계획", MODE_FORECAST: "예측",
    MODE_SCENARIO: "가상 시나리오", MODE_COMPETITOR: "경쟁사 추정",
}

#: 기준선 스냅샷의 `entity_mode` → 값 상태. 실제 문맥 스냅샷은 확정 실적으로 본다.
_SNAPSHOT_MODE = {"REAL": MODE_ACTUAL, "VIRTUAL": MODE_SCENARIO,
                  "COMPETITOR_REFERENCE": MODE_COMPETITOR}


class ComparisonError(ValueError):
    """비교 불가 — 4xx 로 전달한다."""


def _num(v: Any) -> Optional[float]:
    """숫자로 볼 수 있으면 float, 아니면 None.

    ⚠️ 문자열을 억지로 숫자로 만들지 않는다 — "약 12%" 를 12 로 읽으면 그 순간부터 근사값이
      확정값으로 계산에 들어간다."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def compare_result(result_id: str, store=None) -> Dict[str, Any]:
    """계산 결과를 그 기준선과 비교한다.

    돌려주는 것:
      · `rows` — 항목별 {기준선 값·상태, 결과 값·상태, delta, delta_pct, comparable}
      · `baseline_only` / `result_only` — **결손을 따로 센다**(교집합만 보여주면 오해한다)
      · `context` — §8.1 실행 문맥 키 전부(시나리오·기준선·가정·모델버전)
      · `assumptions` — 이 결과가 선 가정과 **근거**
    ★ `comparable=False` 인 행은 delta 를 주지 않는다 — 숫자가 아닌 값의 차이를 지어내지 않는다."""
    st = store
    if st is None:
        from core.enterprise_context.scenario_inputs import scenario_inputs
        st = scenario_inputs

    res = st.get_result(result_id)
    if not res:
        raise ComparisonError(f"계산 결과를 찾을 수 없습니다: {result_id}")
    snap = st.get_snapshot(res["snapshot_id"])
    if not snap:
        raise ComparisonError(
            f"기준선 스냅샷이 없습니다: {res['snapshot_id']} — 기준선 없이는 비교할 수 없습니다.")
    asm = st.get_assumption_set(res["assumption_set_id"])

    base_mode = _SNAPSHOT_MODE.get(snap.get("entity_mode", "REAL"), MODE_ACTUAL)
    bvals: Dict[str, Any] = snap.get("values") or {}
    rvals: Dict[str, Any] = res.get("values") or {}

    rows: List[Dict[str, Any]] = []
    for k in sorted(set(bvals) & set(rvals)):
        bn, rn = _num(bvals[k]), _num(rvals[k])
        row = {
            "key": k,
            "baseline": {"value": bvals[k], "mode": base_mode, "mode_ko": MODE_KO[base_mode],
                         "as_of": snap.get("as_of", ""), "source": snap.get("source", "")},
            # 결과는 항상 가상 시나리오 계산값이다 — 실제와 같은 칼럼에 놓더라도 상태는 남는다.
            "result": {"value": rvals[k], "mode": MODE_SCENARIO,
                       "mode_ko": MODE_KO[MODE_SCENARIO],
                       "model": res.get("calculation_model_version", "")},
            "comparable": bn is not None and rn is not None,
        }
        if row["comparable"]:
            row["delta"] = rn - bn
            # 0 으로 나누지 않는다. 기준선이 0 이면 비율은 의미가 없으므로 주지 않는다.
            row["delta_pct"] = ((rn - bn) / bn * 100.0) if bn else None
        else:
            row["note"] = ("숫자가 아니어서 차이를 계산하지 않았습니다 — 값의 의미를 "
                           "사람이 봐야 합니다.")
        rows.append(row)

    baseline_only = sorted(set(bvals) - set(rvals))
    result_only = sorted(set(rvals) - set(bvals))

    out = {
        "result_id": result_id,
        # §8.1 — 산출 결과는 입력과 같은 키를 갖는다. 그 키를 그대로 되돌려준다.
        "context": {
            "scenario_id": res["scenario_id"], "baseline_snapshot_id": res["snapshot_id"],
            "assumption_set_id": res["assumption_set_id"],
            "calculation_model_version": res["calculation_model_version"],
            "computed_at": res["computed_at"], "computed_by": res.get("computed_by", ""),
        },
        "baseline": {"snapshot_id": snap["snapshot_id"], "name": snap["name"],
                     "as_of": snap["as_of"], "source": snap["source"],
                     "mode": base_mode, "mode_ko": MODE_KO[base_mode],
                     "status": snap["status"], "checksum_ok": snap.get("checksum_ok", True)},
        "assumptions": {
            "assumption_set_id": (asm or {}).get("assumption_set_id", ""),
            "name": (asm or {}).get("name", ""),
            "status": (asm or {}).get("status", ""),
            "values": (asm or {}).get("values", {}),
            # 근거를 함께 낸다 — 가정만 보여주면 "왜 그 값인가"가 화면에서 사라진다.
            "evidence": (asm or {}).get("evidence", {}),
        },
        "rows": rows,
        "baseline_only": baseline_only,
        "result_only": result_only,
        "summary": {
            "compared": len(rows),
            "numeric": sum(1 for r in rows if r["comparable"]),
            "baseline_only": len(baseline_only),
            "result_only": len(result_only),
        },
    }
    out["notes"] = _notes(out, snap)
    return out


def _notes(out: Dict[str, Any], snap: Dict[str, Any]) -> List[str]:
    """사람이 반드시 읽어야 하는 경고. **빈 목록이면 정상이다** — 항상 뜨는 경고는 아무도 읽지 않는다."""
    n: List[str] = []
    base = out["baseline"]
    if base["mode"] != MODE_SCENARIO:
        n.append(f"기준선은 **{base['mode_ko']}**({base['as_of']} 기준)이고 결과는 "
                 f"**가상 시나리오 계산값**입니다 — 같은 종류의 값이 아닙니다.")
    if base["status"] != "APPROVED":
        n.append(f"⚠️ 기준선이 승인되지 않았습니다(status={base['status']}).")
    if not base.get("checksum_ok", True):
        n.append("⚠️ 기준선 내용이 등록 시점과 다릅니다 — 이 비교는 재현할 수 없습니다.")
    if out["assumptions"]["status"] and out["assumptions"]["status"] != "APPROVED":
        n.append(f"⚠️ 가정 세트가 승인되지 않았습니다(status={out['assumptions']['status']}).")
    if out["summary"]["baseline_only"]:
        n.append(f"기준선에만 있는 항목 {out['summary']['baseline_only']}건은 결과에 없습니다 "
                 f"— 계산에서 빠졌는지 확인하십시오.")
    if out["summary"]["result_only"]:
        n.append(f"결과에만 있는 항목 {out['summary']['result_only']}건은 기준선에 없습니다 "
                 f"— 비교 기준이 없으므로 증감을 말할 수 없습니다.")
    if out["summary"]["compared"] and not out["summary"]["numeric"]:
        n.append("비교된 항목 중 숫자가 하나도 없습니다 — 차이를 계산하지 않았습니다.")
    return n


def compare_results(result_ids: List[str], store=None) -> Dict[str, Any]:
    """여러 시나리오 결과를 나란히 본다(가정별 비교 — §7.2 의 "결과 비교").

    ⚠️ **기준선이 다른 결과는 한 표에 넣지 않는다.** 서로 다른 기준선을 쓴 두 결과의 delta 를
      나란히 놓으면 그 차이는 시나리오 차이가 아니라 기준선 차이일 수 있다 — 표는 그것을
      말해주지 않으므로 여기서 거부한다."""
    if not result_ids:
        raise ComparisonError("비교할 결과가 없습니다.")
    cmps = [compare_result(r, store=store) for r in result_ids]
    snaps = {c["baseline"]["snapshot_id"] for c in cmps}
    if len(snaps) > 1:
        raise ComparisonError(
            f"기준선이 서로 다른 결과는 한 표에서 비교할 수 없습니다({sorted(snaps)}) — "
            f"그 차이가 시나리오 차이인지 기준선 차이인지 구분할 수 없습니다.")
    keys = sorted({r["key"] for c in cmps for r in c["rows"]})
    table = []
    for k in keys:
        cells = []
        for c in cmps:
            row = next((r for r in c["rows"] if r["key"] == k), None)
            cells.append({
                "result_id": c["result_id"],
                "assumption_set_id": c["context"]["assumption_set_id"],
                "value": row["result"]["value"] if row else None,
                "delta": row.get("delta") if row else None,
                "present": row is not None,
            })
        base_row = next((r for c in cmps for r in c["rows"] if r["key"] == k), None)
        table.append({"key": k,
                      "baseline": base_row["baseline"] if base_row else None,
                      "cells": cells})
    return {
        "baseline": cmps[0]["baseline"],
        "results": [{"result_id": c["result_id"],
                     "assumption_set_id": c["context"]["assumption_set_id"],
                     "assumption_name": c["assumptions"]["name"],
                     "model": c["context"]["calculation_model_version"]} for c in cmps],
        "table": table,
        "notes": sorted({n for c in cmps for n in c["notes"]}),
    }
