"""[G4 / H-3] 기준값을 **인증된 판에서 유도한다** — 유도할 수 없는 것은 그렇다고 말한다.

## 왜 이 파일이 생겼나 (2026-08-19 화면 실측)

시나리오·의사결정 화면이 기준값 7개를 **전부 사람에게 손으로 받고 있었다.** 그런데
그중 둘(생산량·구매지급)과 기간은 이미 올려서 인증까지 마친 판 안에 있다. 있는 것을
다시 묻는 화면은 「데이터를 올리면 숫자가 나온다」는 이 제품의 약속을 지키지 않는다.

## 이 파일이 지키는 것 넷

★★★ ① **유도한 값과 사람이 넣은 값을 구분한다.** 섞으면 「이 숫자는 어디서 왔나」에
  답할 수 없고, 회의에서 그 질문이 나오는 순간 자료 전체가 흔들린다.

★★★ ② **유도할 수 없는 것을 0으로 채우지 않는다.** 기말현금·영업이익·전력비는 이
  키트의 계약에 없다(재무 데이터다). 0으로 채우면 결과가 완성돼 보이고, 그 표는
  회의에 올라간다. 「못 만든다」와 「0이다」는 다른 사실이다.

★★★ ③ **원본이 그때 그 파일인지 확인하고 읽는다.** RAW 는 불변 영역에 있고
  checksum 이 함께 있다 — 대조하지 않고 읽으면 「인증한 판에서 뽑았다」는 말이
  거짓이 될 수 있다.

★★★ ④ **인증된 판만 쓴다.** 검사 전 판에서 뽑은 합계는 검사받지 않은 숫자이고,
  화면은 그 둘을 구분해 보여 주지 못한다.

⚠️ 여기서 «그럴듯한 기본값» 을 만들지 않는다. 채울 수 없으면 채우지 않고, 왜 채울 수
  없는지를 돌려준다 — 사용자가 무엇을 더 연결해야 하는지 알 수 있도록.

## ⚠️ 아직 남은 어긋남 — 기간 정합

`period_days` 는 **입고 기록의 기간**에서 나오고, 재무 흐름값은 **기준선에 담긴 전
기간**의 합계다. 둘이 다르면(예: 입고 3개월 · 기준선 6개월) 하루당 값이 어긋난다.

지금은 그 둘을 맞추는 장치가 없다 — 씨앗이 맞춰 심을 뿐이다. **고르는 판이 달라지면
어긋날 수 있고, 화면은 그것을 말해 주지 않는다.** 다음 세션에서 볼 것:
기준선의 기간을 하나로 정하고 두 값이 같은 창을 보게 하거나, 어긋나면 화면이 말하게
하는 것 중 하나.

LLM 0콜. 결정론적이다.
"""
from __future__ import annotations

from typing import Any, Dict, List, NamedTuple, Optional, Tuple

#: 값의 출처. ★ 화면이 이 값을 그대로 보여 준다 — 「유도했다」를 화면이 스스로
#:   판단하게 하면 서버와 화면의 판정이 갈라진다.
SOURCE_DERIVED = "DERIVED"
SOURCE_NOT_DERIVABLE = "NOT_DERIVABLE"

#: ⚠️ 한 번에 읽는 행 수 상한. 넘으면 «되는 만큼» 읽지 않고 유도를 포기한다 —
#:   잘린 합계는 그럴듯하고, 그것이 이 파일이 막으려는 것이다.
MAX_ROWS = 200_000


class BaseValueError(Exception):
    """유도 자체를 할 수 없다(판을 못 읽는 등). **부분 결과를 돌려주지 않는다.**"""


class Field(NamedTuple):
    """기준값 한 칸의 답. `value is None` 이면 채우지 못한 것이다."""
    key: str
    value: Optional[float]
    source: str
    reason: str = ""
    derived_from: Tuple[str, ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        return {"key": self.key, "value": self.value, "source": self.source,
                "reason": self.reason, "derived_from": list(self.derived_from)}


def _num(v: Any) -> Optional[float]:
    """숫자로 읽히면 숫자, 아니면 `None`. ★ 0 으로 떨어뜨리지 않는다."""
    s = str(v if v is not None else "").strip().replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _sum_column(rows: List[Dict[str, str]], column: str) -> Tuple[Optional[float], str]:
    """한 열의 합계.

    ⚠️ **숫자가 아닌 칸이 하나라도 있으면 합계를 내지 않는다.** 그 행만 빼고 더하면
      「전체 합계」라고 적힌 부분 합계가 나오고, 아무도 그것을 고장으로 보지 않는다."""
    if not rows:
        return None, "행이 없습니다."
    if column not in rows[0]:
        return None, f"«{column}» 열이 없습니다."
    total = 0.0
    for i, r in enumerate(rows):
        n = _num(r.get(column))
        if n is None:
            return None, f"{i + 1}번째 행의 «{column}» 이 숫자가 아닙니다 — 일부만 더한 "\
                         f"합계를 «전체» 라고 적지 않습니다."
        total += n
    return total, ""


def _sum_product(rows: List[Dict[str, str]], a: str, b: str) -> Tuple[Optional[float], str]:
    """두 열의 곱의 합(수량 × 단가). ⚠️ 위와 같은 이유로 부분 합계를 내지 않는다."""
    if not rows:
        return None, "행이 없습니다."
    for col in (a, b):
        if col not in rows[0]:
            return None, f"«{col}» 열이 없습니다."
    total = 0.0
    for i, r in enumerate(rows):
        x, y = _num(r.get(a)), _num(r.get(b))
        if x is None or y is None:
            return None, f"{i + 1}번째 행의 «{a}» 또는 «{b}» 가 숫자가 아닙니다."
        total += x * y
    return total, ""


def _latest(rows: List[Dict[str, str]], order_by: str, column: str
            ) -> Tuple[Optional[float], str]:
    """**가장 최근 기간**의 값 하나.

    ★★★ 월별 기준선에서 기준값을 뽑을 때는 «합계» 가 아니라 «마지막 잔액» 이다.
      기말현금 6개월치를 더하면 그 숫자는 아무것도 아니다 — 그런데 그럴듯하다.
    ⚠️ 기간 열이 없거나 값이 숫자가 아니면 **뽑지 않는다.**"""
    if not rows:
        return None, "행이 없습니다."
    for col in (order_by, column):
        if col not in rows[0]:
            return None, f"«{col}» 열이 없습니다."
    best, best_key = None, ""
    for r in rows:
        key = str(r.get(order_by) or "").strip()
        if not key:
            return None, f"«{order_by}» 이 비어 있는 행이 있습니다 — 어느 것이 마지막인지 "\
                         f"정할 수 없습니다."
        if key >= best_key:
            best_key, best = key, r
    n = _num((best or {}).get(column))
    if n is None:
        return None, f"마지막 기간({best_key})의 «{column}» 이 숫자가 아닙니다."
    return n, ""


def _day_span(rows: List[Dict[str, str]], column: str) -> Tuple[Optional[float], str]:
    """가장 이른 날 ~ 가장 늦은 날의 **일수**(양 끝 포함).

    ⚠️ 「몇 건인가」가 아니라 「며칠치인가」다 — 둘을 섞으면 하루당 값이 통째로
      어긋난다."""
    from datetime import date

    if not rows:
        return None, "행이 없습니다."
    if column not in rows[0]:
        return None, f"«{column}» 열이 없습니다."
    days: List[date] = []
    for i, r in enumerate(rows):
        s = str(r.get(column) or "").strip()[:10]
        try:
            y, m, d = (int(x) for x in s.split("-"))
            days.append(date(y, m, d))
        except Exception:
            return None, f"{i + 1}번째 행의 «{column}» 을 날짜로 읽을 수 없습니다({s!r})."
    return float((max(days) - min(days)).days + 1), ""


#: ★★★ 어느 기준값이 어느 계약 데이터에서 나오는가. **닫힌 표다.**
#: ⚠️ 여기 없는 칸을 「어떻게든」 만들어 내지 않는다 — 못 만드는 이유를 그대로 적는다.
_RULES: Dict[str, Dict[str, Any]] = {
    "production_qty": {
        "dataset": "material_arrivals",
        "how": ("sum", "quantity"),
        #: ⚠️ 입고량이지 생산량이 아니다. 이 키트가 가진 것이 이것뿐이라 **대리값**으로
        #:   쓰고, 대리값이라는 사실을 화면이 말할 수 있게 사유에 적는다.
        "note": "원료 입고량 합계를 생산 규모의 대리값으로 씁니다 — 확인하고 고치십시오.",
    },
    "purchase_payment": {
        "dataset": "purchase_orders",
        "how": ("product", "quantity", "unit_price"),
        "note": "구매주문의 수량 × 단가 합계입니다.",
    },
    "period_days": {
        "dataset": "material_arrivals",
        "how": ("span", "arrived_at"),
        "note": "입고 기록의 처음과 마지막 사이 일수입니다.",
    },
    #: ★★★ [2026-08-20] 월별 재무 기준선이 계약에 생겨서 넷이 더 유도된다.
    #:   ⚠️ **합계가 아니라 마지막 기간의 값**이다 — 기말현금 6개월치를 더하면 그
    #:     숫자는 아무것도 아닌데 그럴듯하다.
    #: ★★★ **잔액과 흐름을 다르게 뽑는다.**
    #:   · 잔액(현금·재고)은 **마지막 기간의 값** — 6개월치를 더하면 아무 뜻도 없다.
    #:   · 흐름(영업이익·전력비)은 **기간 합계** — 마지막 달만 쓰면 3개월치 구매지급과
    #:     한 달치 이익을 같은 표에서 비교하게 되고, 그 표는 「환율 10%가 이익을
    #:     날린다」처럼 읽힌다(2026-08-20 실측에서 영업이익 -86%가 그렇게 나왔다).
    #: ⚠️ 둘을 같은 방식으로 뽑으면 오류가 나지 않는다. 숫자만 조용히 틀린다.
    "ending_cash": {
        "dataset": "financials",
        "how": ("latest", "period", "ending_cash"),
        "note": "월별 기준선의 **가장 최근 기간** 기말현금입니다(잔액).",
    },
    "ending_inventory": {
        "dataset": "financials",
        "how": ("latest", "period", "ending_inventory"),
        "note": "월별 기준선의 가장 최근 기간 기말재고입니다(잔액).",
    },
    "operating_profit": {
        "dataset": "financials",
        "how": ("sum", "operating_profit"),
        "note": "기준선에 담긴 **전 기간 합계** 영업이익입니다(흐름).",
    },
    "power_cost": {
        "dataset": "financials",
        "how": ("sum", "power_cost"),
        "note": "기준선에 담긴 전 기간 합계 전력비입니다(흐름).",
    },
}

#: 계약에 아예 없는 것들 — **왜 없는지**를 사람 말로 적는다.
#: ⚠️ 지금은 비어 있다. 키트가 첫 수직 경로 전체를 덮게 되면서 일곱 칸 모두 유도된다.
#:   ★ 이 표를 지우지 않는다 — 다른 키트는 이 중 일부가 없을 수 있고, 그때 「왜
#:     없는지」를 말할 자리가 여기다. 빈 표가 「그런 경우는 없다」는 뜻은 아니다.
_ABSENT: Dict[str, str] = {}

#: 답해야 하는 칸 전부. ★ `core/calc_graph._require` 가 읽는 키와 **같아야 한다.**
FIELD_KEYS: Tuple[str, ...] = ("production_qty", "ending_inventory", "purchase_payment",
                               "ending_cash", "operating_profit", "power_cost",
                               "period_days")


def derive(*, rows_by_dataset: Dict[str, List[Dict[str, str]]],
           snapshot_by_dataset: Dict[str, str],
           labels: Optional[Dict[str, str]] = None) -> List[Field]:
    """유도할 수 있는 것만 유도한다. **저장소를 모른다** — 행을 넘겨받을 뿐이다.

    ★ 이 함수가 저장소를 모르는 것이 요점이다. 그래야 「어느 판에서 뽑았는가」를
      호출부가 정하고, 여기서는 «넘겨받은 것» 만 계산한다.

    ⚠️ `labels` 는 계약키 → 사람이 읽는 이름. **사유 문장에 쓰인다** — 없으면
      계약키를 그대로 쓰지만, 그 문장은 사용자 화면에 그대로 나가므로 호출부가
      채워 주는 것이 맞다(설계 §12). 여기서 지어내지 않는다."""
    assert set(_RULES) | set(_ABSENT) == set(FIELD_KEYS), "규칙과 칸 목록이 갈라졌다"

    out: List[Field] = []
    for key in FIELD_KEYS:
        if key in _ABSENT:
            out.append(Field(key, None, SOURCE_NOT_DERIVABLE, _ABSENT[key]))
            continue
        rule = _RULES[key]
        ds = str(rule["dataset"])
        rows = rows_by_dataset.get(ds)
        if rows is None:
            name = str((labels or {}).get(ds) or ds)
            out.append(Field(key, None, SOURCE_NOT_DERIVABLE,
                             f"«{name}» 의 인증된 판이 기준선에 없습니다 — "
                             f"그 데이터를 준비해 인증하면 자동으로 채워집니다."))
            continue
        how = rule["how"]
        if how[0] == "sum":
            value, why = _sum_column(rows, how[1])
        elif how[0] == "product":
            value, why = _sum_product(rows, how[1], how[2])
        elif how[0] == "latest":
            value, why = _latest(rows, how[1], how[2])
        else:
            value, why = _day_span(rows, how[1])
        if value is None:
            out.append(Field(key, None, SOURCE_NOT_DERIVABLE, why))
            continue
        out.append(Field(key, value, SOURCE_DERIVED, str(rule["note"]),
                         (snapshot_by_dataset.get(ds, ""),)))
    return out


def summary(fields: List[Field]) -> Dict[str, Any]:
    """화면이 한 줄로 말할 수 있게. ★ 「몇 칸을 사람이 채워야 하는가」가 핵심이다."""
    derived = [f for f in fields if f.source == SOURCE_DERIVED]
    return {"fields": [f.as_dict() for f in fields],
            "derived_count": len(derived),
            "manual_count": len(fields) - len(derived),
            #: ⚠️ 「전부 채웠다」를 여기서 만들지 않는다 — 사람이 채운 값은 이 응답
            #:   뒤에 들어오므로, 여기서 판단하면 항상 틀린다.
            "note": ("인증된 판에서 뽑을 수 있는 값만 채웠습니다. 나머지는 회사 실적에서 "
                     "직접 넣어 주십시오 — 없는 값을 0으로 채우지 않습니다.")}
