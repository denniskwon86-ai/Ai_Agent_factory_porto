"""[ECM E4] 경영진 비교 보드 — **실제·계획·예측·가상·경쟁사를 한 화면에, 섞지 않고.**

설계서 §11 E4: "경영진 보드에서 실제·계획·예측·가상 결과를 **근거·가정과 함께** 비교한다."

## 이 보드가 하는 일과 하지 않는 일

**한다**: 상태별 계열을 따로 세워, 각 값에 상태·기준일·근거·`official` 여부를 붙여 돌려준다.
합계가 필요하면 `rollup` 이 만든 결과를 그대로 싣는다(집계 규칙을 여기서 다시 구현하지 않는다).

**하지 않는다**:
- **상태를 가로질러 더하지 않는다.** 확정 실적 + 가상 계산값의 합계는 존재하지 않는 숫자다.
- **우열을 판정하지 않는다.** "계획 대비 미달" 같은 판단은 지표의 방향(높을수록 좋은가)을
  알아야 하고, 그건 도메인 지식이다 — 추측하면 틀린 방향을 자신 있게 말하게 된다.
- **경쟁사와의 차이를 계산하지 않는다**(§7.3-5). 추정치와의 차이는 대부분 추정 오차다.

## 왜 이렇게까지 하는가

경영 보고 화면은 이 저장소에서 **가장 늦게 틀린 것이 발견되는 자리**다. 프롬프트 유출이 화면
유출보다 늦게 발견된 것과 같은 이유로, 잘못된 합계는 의사결정이 끝난 뒤에야 드러난다.
그래서 값마다 상태를 끝까지 들고 다니고, 판단은 사람에게 남긴다.

## 권한

하위 조직 값을 보는 것은 **경영진 권한**이다(사용자 결정 2026-07-30 ③). 이 모듈은 권한을
판정하지 않고 `api/deps.viewer_may_drill_down()` 의 결과를 받는다 — 판정 지점을 늘리지 않는다.

LLM 0콜.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.enterprise_context.comparison import (MODE_ACTUAL, MODE_COMPETITOR, MODE_FORECAST,
                                                MODE_KO, MODE_PLAN, MODE_SCENARIO)

#: 보드에 세울 수 있는 계열. 순서가 화면 순서다(확정 → 계획 → 예측 → 가상 → 경쟁사).
SERIES_ORDER = (MODE_ACTUAL, MODE_PLAN, MODE_FORECAST, MODE_SCENARIO, MODE_COMPETITOR)


class BoardError(ValueError):
    """구성 불가 — 4xx 로 전달한다."""


def build_board(node_id: str, series: Dict[str, Dict[str, Any]],
                meta: Optional[Dict[str, Dict[str, Any]]] = None,
                rollups: Optional[Dict[str, Dict[str, Any]]] = None,
                drill_down: bool = False,
                competitor_rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """상태별 계열을 한 표로 세운다.

    · `series` — `{모드: {지표: 값}}`. 모드는 `SERIES_ORDER` 중 하나여야 한다.
    · `meta` — `{모드: {as_of, source, status, official, ...}}`. 각 계열의 근거.
    · `rollups` — `{모드: rollup() 결과}`. 합계·이중계상·커버리지를 그대로 싣는다.
    · `drill_down` — 하위 조직 값을 볼 수 있는 주체인가(경영진). False 면 합계만 남기고
      기여 내역(`contributions`)을 **뺀다**.
    · `competitor_rows` — `competitor_reference.compare_with_internal()` 의 rows.

    ⚠️ 이 함수는 계산하지 않는다. 값을 만들지도, 합치지도 않는다 — 세우기만 한다."""
    if not (node_id or "").strip():
        raise BoardError("node_id 는 필수입니다.")
    unknown = [m for m in series if m not in SERIES_ORDER]
    if unknown:
        raise BoardError(
            f"알 수 없는 값 상태입니다: {unknown} — 가능: {list(SERIES_ORDER)}. 상태가 없는 값을 "
            f"보드에 세우면 그 숫자가 실제인지 가정인지 구분할 수 없게 됩니다(비협상 3).")

    meta = meta or {}
    rollups = rollups or {}
    modes = [m for m in SERIES_ORDER if m in series]
    keys = sorted({k for m in modes for k in (series[m] or {})})

    rows: List[Dict[str, Any]] = []
    for k in keys:
        cells = {}
        for m in modes:
            if k not in (series[m] or {}):
                continue
            mm = meta.get(m) or {}
            cells[m] = {
                "value": series[m][k], "mode": m, "mode_ko": MODE_KO[m],
                "as_of": mm.get("as_of", ""), "source": mm.get("source", ""),
                "status": mm.get("status", ""),
                # 확정 실적만 공식 수치다. 나머지는 계획·가정·추정이다.
                "official": bool(mm.get("official", m == MODE_ACTUAL)),
            }
        rows.append({"key": k, "cells": cells,
                     # 상태를 가로지르는 합계·차이는 만들지 않는다. 그 이유를 행에 남긴다.
                     "cross_mode_total": None,
                     "cross_mode_note": ("상태가 다른 값은 합치지 않습니다 — 확정 실적과 가상 "
                                         "계산값의 합계는 존재하지 않는 숫자입니다(§8.1)."),
                     })

    board: Dict[str, Any] = {
        "node_id": node_id,
        "series": [{"mode": m, "mode_ko": MODE_KO[m], "meta": meta.get(m) or {}} for m in modes],
        "rows": rows,
        "rollups": {},
        "competitor": competitor_rows or [],
        "drill_down": bool(drill_down),
        "notes": [],
    }

    for m, r in rollups.items():
        if m not in SERIES_ORDER:
            raise BoardError(f"알 수 없는 집계 상태입니다: {m}")
        entry = dict(r)
        if not drill_down:
            # 하위 조직별 기여는 경영진만 본다(사용자 결정 ③). 합계·커버리지는 남긴다 —
            # 커버리지를 빼면 부분 합계를 전체로 오해한다.
            entry.pop("contributions", None)
            entry["contributions_hidden"] = True
        board["rollups"][m] = entry
        for n in (r.get("notes") or []):
            board["notes"].append(f"[{MODE_KO.get(m, m)}] {n}")

    if MODE_ACTUAL in modes and MODE_SCENARIO in modes:
        board["notes"].append(
            "확정 실적과 가상 시나리오가 같은 표에 있습니다 — 색·범례로 구분해 표시하고, "
            "두 값을 합치거나 차이를 실적처럼 읽지 마십시오.")
    if competitor_rows:
        board["notes"].append(
            "경쟁사 값은 **참조**이며 회계·경영의 공식 수치가 아닙니다(§7.3-5).")
    if not drill_down and board["rollups"]:
        board["notes"].append(
            "하위 조직별 기여 내역은 표시하지 않았습니다(경영진 권한) — 합계와 커버리지만 "
            "보입니다.")
    return board
