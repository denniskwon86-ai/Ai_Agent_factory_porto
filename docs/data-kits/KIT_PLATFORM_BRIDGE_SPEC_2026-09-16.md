# 키트 → 플랫폼 이음매 명세 — 구현하는 사람이 보는 것

- 기준일: 2026-09-16
- 설계: [이음매 설계](KIT_PLATFORM_BRIDGE_DESIGN_2026-09-16.md) — **왜 이렇게 하는가**는 그쪽에
- 이 문서: **무엇을 어떻게 짜는가.** 대응표 · 함수 · 시험 목록
- 상태: 설계 7 장의 결정 ⑤⑥이 이 문서에서 초안으로 채워졌다. **확정은 사람이 한다.**

---

## 1. 동인 대응표 — ★ 이것이 「산업 최대한 반영」의 실체다

설계 6.3 에서 드러났다 — `input_metric` 을 그대로 넣으면 `AR_AP_TIMING` 이 되고,
플랫폼이 동인을 두는 이유(**가정이 업무 언어가 된다**)가 깨진다. 그래서 사람이 한 번
적는다. 12 개뿐이다.

`unit` 과 `external_code` 는 **키트의 `EXT-01~03` 에서 실측한 값**이다(추정이 아니다).

| 키트 | `name` (업무 언어) | `unit` | `category` | `external_code` |
|---|---|---|---|---|
| `DRV-FX` | 환율 (USD/KRW) | `KRW/USD` | `fx` | `USD_KRW` |
| `DRV-COMMODITY` | 원자재 기준가격 | `USD/TON` | `price` | `COPPER` |
| `DRV-FREIGHT` | 해상 운임 | `USD/TON` | `cost` | `SEA_FREIGHT` |
| `DRV-POWER` | 산업용 전력 단가 | `KRW/KWH` | `energy` | `INDUSTRIAL_POWER` |
| `DRV-DEMAND` | 수요 변화율 | `%` | `volume` | `MFG_DEMAND_INDEX` ⚠️ |
| `DRV-SUPPLY` | 공급 감소율 | `%` | `volume` | — |
| `DRV-YIELD` | 생산 수율 | `%` | `volume` | — |
| `DRV-DOWNTIME` | 설비 정지 시간 | `HOUR` | `volume` | — |
| `DRV-DELAY` | 도착 지연 일수 | `DAY` | **`schedule`** | — |
| `DRV-CASH` | 대금 회수·지급 시점 | `DAY` | **`schedule`** | — |
| `DRV-CAPEX` | 설비투자액 | `KRW` | `cost` | — |
| ~~`DRV-GM`~~ | — | — | — | **제외 (1.1)** |

⚠️ `DRV-DEMAND` 의 외부 지표는 단위가 `INDEX` 인데 동인은 `%` 다. 「지수가 변하는
비율」이라 연결 자체는 맞지만 **단위가 같지 않다** — 표시용 연결이라 문제되지
않으나(`external_code` 는 자동 주입이 아니다), 자동 주입을 붙일 때 다시 봐야 한다.

⚠️ `category` 의 `schedule` 은 **새 범주**다. 플랫폼 주석은
`volume | price | cost | fx | labor | energy` 인데 「일수」가 어디에도 없다.
컬럼이 자유 텍스트(`category TEXT DEFAULT ''`)라 넣을 수는 있지만, **새 범주를 우리가
정하는 것이 맞는지는 플랫폼 쪽과 맞춰야 한다**(설계 7 장 ③).

### 1.1 ★ `DRV-GM` 은 동인이 아니다 — 넣지 않는다

    DRV-GM   input=REVENUE_AND_COST   output=GROSS_MARGIN   formula=REVENUE-COGS

**이것은 계산식이다.** 「매출과 원가가 1% 변하면 매출총이익이 몇 % 변하는가」는 물음이
성립하지 않는다 — 매출이 오르면 GM 이 오르고 원가가 오르면 내린다. 하나의 탄력도로
답할 수 없다.

그리고 플랫폼은 **이미 이것을 계산한다.** `plan_accounts` 의 `category`(REVENUE/COGS)와
`sign`(+1/−1)이 있으므로 손익은 엔진이 낸다. 동인으로 넣으면 **같은 것을 두 번 세는**
셈이고, 현업은 의미 없는 계수를 등록하라는 요구를 받는다.

★ 이것이 키트 `SIM-01` 의 성격을 드러낸다 — **「동인」과 「계산식」이 한 표에 섞여
있다.** `input_metric` 이 동인이고 `output_metric`+`formula` 는 그 동인이 들어가는
계산인데, `DRV-GM` 만은 `input_metric` 자리에 동인이 아닌 것이 왔다.

---

## 2. 단위 환산 — ★ 100 배 사고를 막는 자리

설계 6.2 에서 잰 것: 키트는 `0.1`(비율), 플랫폼은 `10`(퍼센트 수). 그대로 넘기면
**오류 없이 100 배 작게** 계산된다.

```python
def to_pct_change(change_value: str, change_unit: str) -> float:
    """키트 시나리오의 변화량을 플랫폼의 `pct_change` 로 옮긴다.

    ⚠️ 키트는 **비율**로 적고(`0.1` = 10%), 플랫폼은 **퍼센트 수**를 받는다(`10`).
      그대로 넘기면 오류 없이 100 배 작게 계산되고, 「환율이 10% 올랐는데 원가가
      0.06%」를 이상하다고 느끼지 못하면 그대로 경영 보고서로 간다.
    """
    v = float(change_value)
    u = (change_unit or "").strip().upper()
    if u in ("%", "PCT", "PERCENT"):
        return v * 100.0
    if u == "PERCENT_POINT":
        #: %p 는 % 가 아니다 — 수율 92%→90% 는 −2%p 이고 −2.17% 다.
        #: 기준값은 **회사 데이터**라 여기서 만들 수 없다.
        raise NeedsBaseline(
            f"%p 시나리오는 기준값이 있어야 옮길 수 있습니다: {change_value}{change_unit}. "
            f"현업이 현재 값을 넣은 뒤 to_pct_change_from_baseline() 을 쓰십시오.")
    raise UnsupportedScenarioUnit(
        f"퍼센트가 아닌 시나리오는 옮길 수 없습니다: {change_value} {change_unit}. "
        f"플랫폼의 expand_driver_assumption() 은 비율 변화만 받습니다.")


def to_pct_change_from_baseline(change_value, change_unit, baseline: float) -> float:
    """%p 를 기준값으로 비율 변화로 바꾼다. **기준값은 현업이 준다.**"""
    if (change_unit or "").strip().upper() != "PERCENT_POINT":
        return to_pct_change(change_value, change_unit)
    if not baseline:
        raise NeedsBaseline("기준값이 0 이거나 없습니다 — %p 를 비율로 바꿀 수 없습니다.")
    return float(change_value) / baseline * 100.0
```

### 2.1 ★★★ 실측 — 10 개 중 **4 개가 옮겨지지 않는다**

세어 봤다. 「구현할 때 보자」로 미룰 일이 아니었다.

| 단위 | 건 | 옮길 수 있나 |
|---|---|---|
| `%` | **6** | ✅ ×100 |
| `PERCENT_POINT` | 1 | △ **기준값이 있어야 한다** (아래) |
| `DAY` | 1 | ✗ `SCN-04` 선적·통관 14 일 지연 |
| `HOUR` | 1 | ✗ `SCN-07` 주요 설비 48 시간 정지 |
| `KRW` | 1 | ✗ `SCN-10` 신규 공장 투자 1,800 억 |

**키트가 주는 시나리오의 40% 가 플랫폼으로 넘어가지 않는다.** 그리고 넘어가지 않는
것들이 하필 **경영 판단에 가장 가까운 것들**이다 — 설비 정지, 투자 결정, 납기 지연.

#### 왜 넘어가지 않나 — ⚠️ 처음에 잘못 짚었다

처음에 「플랫폼의 시나리오 모델이 절대량을 받지 못한다」고 적었는데 **틀렸다.**
확인해 보니 플랫폼은 세 연산자를 다 받는다.

| | |
|---|---|
| `plan_assumptions.operator` | `pct` \| `delta` \| `set` |
| 엔진 | `pct`→`base×(1+v/100)` · `delta`→`base+v` · `set`→`v` |
| API | `POST /scenarios/{id}/assumptions` 가 셋 다 받는다 |

**막히는 곳은 동인 경로 하나다.**

```python
# expand_driver_assumption()
out.append({..., "operator": "pct",                    # ← 고정
           "value": pct_change * float(im["elasticity"])})
```

`driver_impacts.elasticity` 가 「1% 변하면 n% 변한다」라 **구조적으로 비율**이다.
「1 시간 정지 = 생산량 n 톤 감소」를 담을 자리가 없다.

→ 그래서 「설비 48 시간 정지」는 **계정 가정으로 직접** 넣을 수는 있다. 다만 그러면
동인을 1 급으로 둔 이유가 사라진다 — 「왜 그 숫자인가」가 사람 머릿속에만 남는다.
**이것은 플랫폼 모델의 검토 건**이고 이음매가 정할 일이 아니다 →
[절대량 동인 검토](../handoff/PLATFORM_REVIEW_ABSOLUTE_DRIVERS_2026-09-16.md)

#### `PERCENT_POINT` 는 특히 조심해야 한다

    SCN-06  생산수율 2%p 하락   DRV-YIELD  -0.02  PERCENT_POINT

**%p 와 % 는 다르다.** 수율이 92% → 90% 로 가는 것이지 92% 의 2% 가 아니다.
비율로 옮기면 **−2.17%** 이고, 그 환산에는 **현재 수율(92%)** 이 있어야 한다.

★ 그 기준값은 **회사 데이터**다(분석 2.0 의 「현업」 칸). 즉 이 시나리오는 현업이
자기 수율을 넣은 뒤에만 옮길 수 있다.

⚠️ `%` 로 잘못 보고 ×100 하면 **−2%** 가 되어 그럴듯하게 틀린다(정답 −2.17%).
차이가 작아 **눈으로 못 잡는다** — 그래서 시험으로 잠근다.

### 2.2 옮길 수 없는 것은 **거부한다**

**조용히 버리지 않고 예외로 멈춘다.** 옮길 수 없는 것을 옮긴 척하면 그 시나리오는
「실행됐는데 아무 일도 안 일어난」 것이 된다.

---

## 3. 함수 — `scripts/seed_starter_data.py` 에 붙인다

### 3.1 계정

```python
_PNL_TO_CATEGORY = {"REVENUE": "REVENUE", "COGS": "COGS", "OPEX": "SGA"}

def seed_plan_accounts(rows: list[dict], store) -> dict:
    """`MDM-07` → `plan_accounts`. 손익 계정만 옮긴다.

    반환: {"loaded": int, "skipped": [(code, name, pnl_line)], "failed": [...]}
    """
```

- `sign` 은 `account_type` 에서 — `REVENUE`→`+1`, 그 외→`−1`
- `BALANCE_SHEET` 4 건(현금·매출채권·재고자산·매입채무)은 **건너뛰고 반환값에 담는다**
- 실측: 30 건 중 **26 건 적재 · 4 건 건너뜀 · 실패 0**

### 3.2 동인

```python
def seed_plan_drivers(rows: list[dict], store) -> dict:
    """`SIM-01` → `plan_drivers`. **파급 계수는 만들지 않는다.**

    반환: {"loaded": [...], "skipped_existing": [...], "excluded": [...]}
    """
```

- 대응표(1 장)에 없는 `driver_id` 는 **`excluded`** 로 — `DRV-GM` 이 여기 걸린다
- 이미 있는 `driver_code` 는 **`skipped_existing`** 으로, 건드리지 않는다(설계 5.1)
- `note` 에 키트가 아는 것을 담는다

```python
note = (f"{output_metric} 에 파급된다. 계산식 {formula_definition}"
        + (f" (지연 {lag}개월)" if lag and lag != "0" else ""))
```

⚠️ **`driver_impacts` 를 만드는 코드가 있으면 그것은 결함이다.** 계수는 현업이
`rationale`·`source` 와 함께 등록한다(설계 3 장).

### 3.3 시나리오

계수가 채워진 뒤에만 의미가 있으므로 **이번 범위에 넣지 않는다**(설계 4.3).
`to_pct_change()` 만 먼저 만들어 두고, 쓰는 쪽은 나중에 붙인다.

---

## 4. 시험 — 무엇을 잠그나

★ 아래는 **전부 이 세션의 검증에서 실제로 드러난 것**이다. 하나도 상상해서 쓴
것이 없다. 시험이 없으면 그대로 다시 일어난다.

| # | 잠그는 것 | 시험 |
|---|---|---|
| 1 | **단위 100 배** | `to_pct_change("0.1", "%") == 10.0` |
| 2 | **절대 단위를 조용히 넘기지 않는다** | `to_pct_change("14", "DAY")` · `("48","HOUR")` · `("1.8e11","KRW")` 가 예외 |
| 2b | **`%p` 를 `%` 로 착각하지 않는다** | `to_pct_change("-0.02","PERCENT_POINT")` 가 예외 · `..._from_baseline(-0.02, 0.92)` ≈ −2.17 (−2.0 이 아니다) |
| 3 | **계수를 만들지 않는다** | 파종 후 `impacts_of(code)` 가 전부 빈 목록 |
| 4 | **기계 이름이 안 들어간다** | 등록된 `name` 에 `_` 가 없고 대응표와 일치 |
| 5 | **이미 있는 동인을 덮지 않는다** | 두 번 심어도 `note` 가 그대로 · `skipped_existing` 에 담김 |
| 6 | **동인 아닌 것을 넣지 않는다** | `DRV-GM` 이 `excluded` 에 · `plan_drivers` 에 없음 |
| 7 | 계정 26/30 | `loaded == 26` · `skipped` 4 건이 전부 `BALANCE_SHEET` |
| 8 | **건너뛴 것이 보고된다** | 반환값의 `skipped`·`excluded` 가 비어 있지 않고 로그에 찍힘 |

### 4.1 4 번이 가장 지키기 어렵다

「기계 이름이 아니다」를 기계가 어떻게 판정하나. `_` 가 없다는 것만으로는 약하다
(`AR AP TIMING` 도 통과한다). **대응표와의 일치**로 잠그는 것이 맞고, 그러면 대응표가
사실상 명세가 된다 — 새 동인을 넣으면 시험이 먼저 깨진다. 그것이 의도다.

---

## 5. 구현 순서

1. `to_pct_change()` + 시험 1·2 — **가장 작고 가장 위험한 것부터**
2. 대응표를 데이터로 (`_DRIVER_MAP`) + 시험 4·6
3. `seed_plan_drivers()` + 시험 3·5·8
4. `seed_plan_accounts()` + 시험 7
5. `seed_starter_data.py` 에 연결 — ⚠️ 그 전에 **빈 설치본 결함**(2026-09-11 인계
   4-(3))이 고쳐졌는지 확인한다
6. 시나리오는 계수가 쌓인 뒤 (3.3)

---

## 6. 이 명세가 정하지 않은 것

| | 왜 |
|---|---|
| **시나리오 10 개 중 4 개가 안 넘어간다**(2.1) | **동인 경로**가 비율 탄력도만 다룬다(플랫폼 전체가 아니다). 별도 검토 건으로 올렸다 |
| `category` 에 `schedule` 을 써도 되나 | 플랫폼 범주를 우리가 늘리는 것이다 — 조율 필요 |
| 재무상태표 계정 4 개 | 버릴지 `WORKING_CAPITAL` 로 보낼지 (설계 7 장 ①) |
| `register_driver` 의 승인 판본 보호 | 플랫폼 쪽 결함이고 **다른 세션 영역**이다 (설계 5.1) |
| 판본 갱신 시 이행 | 1.1.0 을 심은 회사에 1.2.0 이 오면 (설계 5.2) |
| **누가 구현하나** | 설계 7 장 ③ — 이것이 먼저다 |
