"""[ECM E4] 외부환경 인텔리전스 → 보드 `FORECAST` 계열 — **등급 미달은 값이 아니라 결손이다.**

## 이 모듈이 잇는 두 곳

- `core/external_intelligence.py` — 외부 지표를 등급(gold/silver/bronze)·vintage·품질상태와 함께
  보관하고, **용도별 최소 등급**을 지킨다(§12.2). 등급이 안 되면 `allowed=False, value=None` 이다.
- `core/enterprise_context/executive_board.py` — 상태별 계열을 세운다. `FORECAST` 자리는
  있었지만 **아무것도 이어져 있지 않았다**(E4 의 남은 조각).

## 이을 때 지켜야 하는 것

★ `resolve_value()` 가 값을 거부하면 **그 지표를 계열에서 빼고 `blocked` 로 올린다.** 거부된 값을
  0 이나 이전 값으로 대신 채우지 않는다.
⚠️ 여기가 이 연결의 유일한 위험 지점이다. 외부 지표는 "없으면 아쉬운" 값이 아니라 **경영 보고에
  올라가는 값**이고, 등급 미달 값을 슬쩍 채우면 §12.1 이 금지한 "검증 없이 기사·시장 전망값으로
  기준 계획을 바꾸는" 상황이 된다. 그리고 표에서는 그 차이가 보이지 않는다.

★ 보드의 `FORECAST` 계열은 기본 용도를 `scenario`(최소 silver)로 쓴다 — 전망은 시나리오
  등급이면 충분하다. 다만 **경영 보고용 보드**라면 호출자가 `purpose="official_report"`(gold)를
  지정할 수 있게 열어 둔다. 용도를 여기서 고정하면 화면마다 다른 기준이 생긴다.

★ 각 값에 등급·관측시점·vintage·원천을 붙여 올린다. 그것이 없으면 보드에서 전망값과 실적이
  같은 숫자로 보인다(§12.2 가 "구분해 표기해야 한다"고 한 이유).

LLM 0콜.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

#: 보드 `FORECAST` 계열의 기본 용도. 전망은 시나리오 등급(silver)이면 성립한다.
#: 경영 보고용으로 쓸 때는 호출자가 `official_report`(gold)를 지정한다.
DEFAULT_PURPOSE = "scenario"


class OutlookError(ValueError):
    """구성 불가 — 4xx 로 전달한다."""


class OutlookSeries:
    def __init__(self, intelligence=None):
        self._ei_override = intelligence

    @property
    def _ei(self):
        if self._ei_override is not None:
            return self._ei_override
        from core.external_intelligence import external_intelligence
        return external_intelligence

    def build(self, indicator_codes: List[str], purpose: str = DEFAULT_PURPOSE,
              as_of: str = "", vintage: str = "") -> Dict[str, Any]:
        """지표 목록으로 `FORECAST` 계열을 만든다.

        돌려주는 것:
          · `values` — 보드 `series["FORECAST"]` 에 그대로 넣을 `{지표: 값}`
          · `meta` — 보드 `meta["FORECAST"]` 에 넣을 계열 근거(용도·등급 요건)
          · `evidence` — 지표별 등급·관측시점·vintage·원천
          · `blocked` — **등급 미달·관측 없음으로 빠진 지표와 그 이유·다음 행동**
        ⚠️ `values` 에는 허용된 값만 들어간다. 빠진 것을 0 으로 채우지 않는다 — 채우면 그 숫자가
          경영 보고에 올라가고, 표에서는 채운 것인지 실제 값인지 구분되지 않는다."""
        if not indicator_codes:
            raise OutlookError("지표 코드가 비어 있습니다.")
        try:
            from core.external_intelligence import PURPOSE_MIN_GRADE
        except Exception:                                            # pragma: no cover
            PURPOSE_MIN_GRADE = {}
        if PURPOSE_MIN_GRADE and purpose not in PURPOSE_MIN_GRADE:
            raise OutlookError(
                f"purpose 는 {list(PURPOSE_MIN_GRADE)} 중 하나여야 합니다: {purpose} — "
                f"용도를 정하지 않으면 어떤 등급이 필요한지 정해지지 않습니다(§12.2).")

        values: Dict[str, Any] = {}
        evidence: Dict[str, Dict[str, Any]] = {}
        blocked: List[Dict[str, Any]] = []
        for code in indicator_codes:
            try:
                r = self._ei.resolve_value(code, purpose=purpose, as_of=as_of, vintage=vintage)
            except Exception as e:
                # 해석 실패는 값 없음으로 처리하고 **이유를 남긴다** — 조용히 빠지면
                # "지표가 없다"와 "조회가 깨졌다"가 같아진다.
                blocked.append({"indicator_code": code, "reason": f"조회 실패: {e}",
                                "next_action": "지표 등록·원천 승인 상태를 확인하십시오."})
                continue
            if not r.get("allowed"):
                blocked.append({
                    "indicator_code": code,
                    "reason": r.get("reason", "사용할 수 없는 값입니다."),
                    "required_grade": r.get("required_grade", ""),
                    "available_grade": r.get("available_grade", ""),
                    "next_action": r.get("next_action", ""),
                })
                continue
            values[code] = r.get("value")
            evidence[code] = {
                "grade": r.get("grade", ""), "observed_at": r.get("observed_at", ""),
                "vintage": r.get("vintage", ""), "source_id": r.get("source_id", ""),
                "quality_status": r.get("quality_status", ""), "unit": r.get("unit", ""),
            }

        meta = {
            "purpose": purpose,
            "required_grade": (PURPOSE_MIN_GRADE or {}).get(purpose, ""),
            "as_of": as_of, "vintage": vintage,
            "source": "external_intelligence",
            # 전망은 공식 수치가 아니다 — 보드가 `official` 로 구분해 그릴 수 있어야 한다.
            "official": False,
            "evidence": evidence,
        }
        notes: List[str] = []
        if blocked:
            notes.append(
                f"⚠️ 지표 {len(blocked)}건이 계열에서 제외됐습니다(등급 미달 또는 관측 없음) — "
                f"**0 으로 채우지 않았습니다.** 빈 자리는 값이 없다는 뜻입니다.")
        if values:
            notes.append(
                f"전망값은 실적이 아닙니다 — 표시할 때 실제값·전망·계획 가정·시나리오를 구분해 "
                f"표기하십시오(§12.2). 용도 '{purpose}' 최소 등급 "
                f"'{meta['required_grade'] or '-'}' 를 통과한 값만 담겨 있습니다.")
        if not values:
            notes.append(
                "사용할 수 있는 전망값이 하나도 없습니다 — 전망 계열을 보드에 세우지 마십시오. "
                "빈 계열을 세우면 '전망이 0' 으로 읽힙니다.")
        return {"values": values, "meta": meta, "blocked": blocked,
                "usable": len(values), "excluded": len(blocked), "notes": notes}

    def attach_to_board(self, board_input: Dict[str, Any], indicator_codes: List[str],
                        purpose: str = DEFAULT_PURPOSE, as_of: str = "",
                        vintage: str = "") -> Dict[str, Any]:
        """보드 입력(`series`/`meta`)에 `FORECAST` 계열을 얹는다.

        ★ **사용할 수 있는 값이 하나도 없으면 계열을 세우지 않는다.** 빈 계열은 "전망이 0" 으로
          읽힌다 — 결손을 0 으로 채우지 않는 것과 같은 이유다."""
        out = self.build(indicator_codes, purpose=purpose, as_of=as_of, vintage=vintage)
        series = dict(board_input.get("series") or {})
        meta = dict(board_input.get("meta") or {})
        if out["values"]:
            series["FORECAST"] = out["values"]
            meta["FORECAST"] = out["meta"]
        merged = dict(board_input)
        merged["series"] = series
        merged["meta"] = meta
        merged["outlook"] = {"blocked": out["blocked"], "usable": out["usable"],
                            "excluded": out["excluded"], "notes": out["notes"]}
        return merged


outlook_series = OutlookSeries()
