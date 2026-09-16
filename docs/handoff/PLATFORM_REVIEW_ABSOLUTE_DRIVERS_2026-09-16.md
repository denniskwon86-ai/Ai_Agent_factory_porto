# 플랫폼 검토 건 — 동인 체계가 **절대량**을 담지 못한다

- 올린 날: 2026-09-16
- 올린 곳: `claude/diffusion-readiness-20260916` (업무키트 확산 사전 검토 세션)
- 대상: 계획 동인(M4) · `core/planning_drivers.py` · `core/planning_engine.py`
- **이 문서는 요청이 아니라 관찰이다.** 해결 방향은 플랫폼 쪽이 정한다.

---

## 0. 한 줄

**가정(`plan_assumptions`)은 `pct`·`delta`·`set` 을 다 받는데, 동인을 거치면 `pct`
밖에 못 쓴다.** 그래서 「설비 48 시간 정지」·「신규 공장 투자 1,800 억」 같은 시나리오는
동인으로 표현할 수 없고, 계정에 직접 넣으면 **동인을 1 급으로 둔 이유가 사라진다.**

---

## 1. 어떻게 발견했나

업무키트(`KIT-MFG-NONFERROUS-PROCUREMENT 1.1.0`)의 시나리오를 플랫폼 계획 체계로
옮기는 이음매를 설계하다가, **10 개 중 4 개가 옮겨지지 않는 것**을 실측했다.

| 단위 | 건 | 시나리오 |
|---|---|---|
| `%` | 6 | 환율 10% 상승 · 원료가 15% 상승 · 운임 30% 상승 … |
| `PERCENT_POINT` | 1 | 생산수율 2%p 하락 |
| `DAY` | 1 | **선적·통관 14 일 지연** |
| `HOUR` | 1 | **주요 설비 48 시간 정지** |
| `KRW` | 1 | **신규 공장 투자 1,800 억** |

넘어가지 않는 것들이 하필 **경영 판단에 가장 가까운 것들**이다 — 설비 사고, 투자
결정, 납기 지연.

---

## 2. 정확히 어디가 막히나

### 2.1 플랫폼은 절대량을 받는다 (처음에 잘못 짚었다)

    plan_assumptions.operator  →  pct | delta | set

```python
# core/planning_engine.py
if op == "pct":    t["amount"] = base * (1.0 + val / 100.0)
elif op == "delta": t["amount"] = base + val
elif op == "set":   t["amount"] = val
```

`POST /planning/scenarios/{id}/assumptions` 도 셋을 다 받는다. **모델의 한계가
아니다.**

### 2.2 막히는 곳은 **동인 → 가정 전개** 하나다

```python
# core/planning_drivers.py :: expand_driver_assumption()
out.append({
    "target_kind": "account",
    "target_code": im["account_code"],
    "operator": "pct",                                  # ← 고정
    "value": pct_change * float(im["elasticity"]),
})
```

`driver_impacts.elasticity` 가 **「동인이 1% 변할 때 계정이 몇 % 변하는가」**로
정의돼 있다. 구조상 비율이고, **「1 시간 정지 = 생산량 n 톤 감소」를 담을 자리가 없다.**

---

## 3. 왜 그냥 계정 가정으로 넣으면 안 되나

기술적으로는 된다. 「설비 48 시간 정지」를 `target_code=4000(매출)` ·
`operator=delta` · `value=-3,000,000,000` 으로 넣으면 계산은 돈다.

**그런데 그것이 정확히 M4 가 피하려던 것이다.**

> 실제 경영계획은 "매출 계정을 10% 올린다"로 세우지 않는다. **"판매량이 10% 늘면"**
> 으로 세우고, 그것이 매출·원가·물류비에 각각 다른 비율로 파급된다. **계정에 직접
> 넣으면 그 파급 관계가 사람 머릿속에만 남고, 다음 사람은 왜 그 숫자인지 알 수 없다.**
> — `core/planning_drivers.py` 머리말

「48 시간 정지 → 매출 −30 억」을 계정에 직접 넣으면 **왜 30 억인지가 사라진다.**
가동률·생산능력·판가가 그 뒤에 있는데, 그 연결이 기록되지 않는다.

즉 **절대량 시나리오만 동인 체계 밖으로 나가고, 근거 강제(`rationale`·`source`)와
승인·판본 배포에서도 빠진다.** 하필 금액이 가장 큰 것들이 그렇게 된다.

---

## 4. 우리가 정하지 않은 것

해결은 플랫폼 소관이라 방향을 고르지 않았다. 다만 **문제의 성격**은 이렇게 보인다.

동인이 계정에 미치는 영향을 지금은 **탄력도 하나**로 적는데, 실제로는 두 종류가 있다.

| | 예 | 지금 |
|---|---|---|
| **비율 파급** | 환율 1% ↑ → 재료비 0.6% ↑ | ✅ `elasticity` |
| **절대 파급** | 설비 1 시간 정지 → 생산량 n 톤 ↓ | ✗ 담을 자리 없음 |

절대 파급을 담으려면 `driver_impacts` 에 **계수의 종류**가 필요해 보인다 — 다만
그것이 맞는 설계인지, `delta` 가정을 동인에 묶는 다른 방법이 있는지는 **플랫폼
쪽에서 볼 일**이다.

⚠️ 한 가지만 덧붙이면, 어느 방향이든 **`rationale`·`source` 강제와 승인 절차는
그대로 적용돼야** 한다. 절대 계수야말로 근거 없이 쓰이기 쉽다 — 「48 시간 정지하면
30 억」은 그럴듯해 보이지만 어디서 온 숫자인지 묻지 않으면 아무도 모른다.

---

## 5. 재현

임시 DB 로 실제 돌린 결과다.

```python
s.upsert_account("4000", "매출", "REVENUE", 1)
dr.register_driver("DRV-DOWNTIME", "설비 정지 시간", "HOUR", "volume")
dr.add_impact("DRV-DOWNTIME", "4000", -0.5, rationale="가정", source="검증용")

out, _ = dr.expand_driver_assumption("DRV-DOWNTIME", 48)   # 48 «시간» 을 넣는다
# → {'operator': 'pct', 'value': -24.0, 'target_code': '4000'}
```

**48 「시간」이 48 「%」로 읽혀 매출이 24% 움직인다.** 오류도 경고도 없다 — 단위가
없는 채로 숫자만 건너가기 때문이다.

계수 부호를 뒤집으면 방향만 바뀔 뿐 같은 문제다. 애초에 **「시간」과 「%」를 가리는
자리가 없다** — `expand_driver_assumption(code, pct_change)` 의 인자에 단위가 없고,
`plan_drivers.unit`(`HOUR`)은 전개할 때 보지 않는다.

(시나리오 단위 실측은 `starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.1.0/samples/quick/SIM-02.csv`
의 `change_unit` 분포를 세면 나온다.)

---

## 6. 관련 문서

- [키트 → 플랫폼 이음매 설계](../data-kits/KIT_PLATFORM_BRIDGE_DESIGN_2026-09-16.md)
- [이음매 명세](../data-kits/KIT_PLATFORM_BRIDGE_SPEC_2026-09-16.md) 2.1 — 단위 실측
- [확산 적용 준비도 분석](../data-kits/DIFFUSION_READINESS_ANALYSIS_2026-09-16.md) 2.6 — 이음매가 없다는 발견
