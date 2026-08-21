# A — **경로 단위 계산 계약** rev.2 (설계 · 구현 없음)

작성: Claude Code (백엔드) · 2026-08-21
**상태: rev.2 · 조건부 승인 반영.** 코드 변경 없음. 계산은 여전히 하나도 실행되지 않는다.
전제: [§5-0 계산 의미 계약 2판](G2_S5_0_CALCULATION_SEMANTICS_CONTRACT_2026-08-21.md)

> ⚠️⚠️ **rev.1 의 §3.2 는 틀렸다.** 입력만 해시해 놓고 이름을 `result_fingerprint` 라고
> 붙였다. 그러면 **출력이 달라져도 같은 지문**이 나오고, 「이 숫자는 무엇으로 만들었나」에
> 답한다고 믿으면서 실제로는 「이 질문은 무엇이었나」에만 답한다. rev.2 에서 두 지문으로
> 가른다.

---

## 0. 이 문서가 정하는 것

「경로 하나에 대해 **한 번에** 계산한다」가 무슨 뜻인지 — 무엇을 넣고, 무엇이 나오고,
막혔을 때 무엇을 돌려주는지. 산식은 정하지 않는다(5b).

---

## 1. 왜 간선별이 아닌가

**① 네 번 반올림한다.** 구간이 자기 결과를 내고 다음 구간이 받으면, `producible_qty`
를 자른 값으로 `revenue_shift_days` 를 내게 되고 하루 경계에서 답이 갈린다.

**② 중간값이 서로 다른 판에서 올 수 있다.** 구간마다 `as_of` 를 따로 해석하면
`INV-01` 은 6월 판, `MFG-01` 은 3월 판을 볼 수 있다. **각 구간은 옳고 합쳐진 답이
틀린다.**

**③ 그래서 같은 질문에 두 번 답할 때 값이 흔들린다.**

★ 경로 하나가 계산의 단위다. 계산 참조 4종은 각자 실행되는 것이 아니라 경로 안의
**구간 이름**이 된다.

---

## 2. 결정 1 — 부분 결과 (확정)

```
관계·승인   구간별로 만들어질 수 있다        ← 막지 않는다
계산        전체 경로를 BLOCKED 로 처리한다   ← 부분 수치 없음
브리핑·결정 패키지   부분 수치를 싣지 않는다
내부 진단 화면      준비되지 않은 구간과 사유를 보여 준다
```

**「경로는 만들되 계산은 거부」가 정본이다.**

⚠️⚠️ 「앞의 두 구간은 계산됐으니 그것만 보여 주자」가 위험하다. 화면에 숫자가 뜨면
사람은 그것을 **답**으로 읽는다. 「재고 부족 230톤」만 보이고 매출 영향이 비어 있으면,
읽는 사람은 「매출 영향은 없구나」로 받아들인다 — 실제로는 **계산하지 못한 것**이다.

### 2.1 ⚠️ 차단 사유도 누설이다

숨겨진 관계나 권한 밖 경로의 **구간 수·이름을 노출하지 않는다.**

「구간 3개 중 2개가 막혔습니다」는 **구간이 3개 있다는 사실**을 알려 준다. 권한이 없는
사람에게 그것은 이미 정보다.

★ 그래서 사유는 두 층이다:

| 대상 | 무엇을 말하나 |
|---|---|
| 경영 브리핑·결정 패키지 | 「이 경로는 아직 계산할 수 없습니다」 — 구간 정보 없음 |
| 내부 진단(권한 있는 사람) | 구간 이름과 §5a 의 차단 사유 그대로 |

---

## 3. 결정 2 — 지문을 **둘로** 가른다 (확정)

### 3.1 두 지문

```
request_fingerprint = sha256({
  query_id, path_fingerprint,
  tenant_id, entity_mode, scope_node_id,      ← 정체성 세 값
  as_of(UTC 정규화),
  baseline_id, baseline_fingerprint,
  sealed_snapshots(정렬),
  relation_approvals(정렬),
  assumptions(정렬·반올림),
  path_model_version,
  segment_capability_fingerprints(정렬)        ← **쓴 것만**
})

result_fingerprint = sha256({
  request_fingerprint,
  normalized_metrics,
  normalized_segment_outputs,
  used_snapshots
})
```

### 3.2 왜 이렇게 가르나

| | 답하는 질문 |
|---|---|
| `request_fingerprint` | **이 질문은 무엇이었나** — 같은 질문인지 대조 |
| `result_fingerprint` | **이 숫자는 무엇으로 만들었나** — 같은 답인지 대조 |

⚠️ rev.1 은 앞엣것만 만들고 뒤엣것의 이름을 붙였다. 그러면 산식이 바뀌어 **값이
달라져도 지문이 같아서**, 재현 검증이 통과한다.

### 3.3 `scope_node_id` 가 빠지면 안 되는 이유

같은 tenant 안의 **다른 조직 계산을 구분할 수 없다.** §4.1a 에서 확인했듯 정본 다섯
종은 이미 두 조직 노드(`battery-02`·`smelting-01`)에 걸쳐 있다.

### 3.4 `relation_approvals` 가 들어가는 이유

**철회 후 재승인은 다른 실행 근거다.** 승인 이벤트가 바뀌었는데 지문이 같으면, 옛
근거로 낸 숫자가 새 승인 아래서도 유효해 보인다.

### 3.5 ⚠️ 전체 Registry 지문을 쓰지 않는다

**실제로 사용한 계산 참조의 지문만** 넣는다.

⚠️ 전체를 넣으면 **범위 밖인 `CALC.FINANCE.COST_MARGIN_CASH.v1` 의 산식을 고치는
순간 MVP 결과가 전부 무효**가 된다. 관계없는 변경이 남의 증명을 깨뜨리면, 사람은
지문 검증을 믿지 않게 되고 결국 끄게 된다.

### 3.6 `used_snapshots` 는 결과 지문에만 든다

★ 먼저 **`used_snapshots == sealed_snapshots` 를 강제**한다. 다르면 그것은 지문 문제가
아니라 **무결성 장애**다(봉인한 판이 아닌 것을 읽었다는 뜻).

그 검사를 통과한 뒤 결과 지문에 싣는다 — 「무엇을 읽고 만든 숫자인가」의 일부다.

### 3.7 ⚠️⚠️ `BLOCKED` 에는 결과 지문을 만들지 않는다

수치가 없는데 결과 지문을 만들면, 그 지문이 **「계산된 결과」의 증거처럼** 쓰인다.

```
BLOCKED  →  request_fingerprint + 차단 상태만
COMPLETE →  request_fingerprint + result_fingerprint
```

---

## 4. 결정 3 — `model_version` 은 **두 층** (확정)

```
path_model_version          경로 전체의 실행 순서 · 반올림 · 집계 · 기준선 비교 규칙
segment_model_versions = {
    "CALC.LOGISTICS.ARRIVAL_DELAY.v1": "…",
    "CALC.INVENTORY.MATERIAL_SHORTAGE.v1": "…",
}
```

⚠️ 문자열을 **이어 붙이지 않는다.** `"1.0.0|1.0.0|2.0.0"` 같은 값은 어느 구간이 올라간
것인지 알 수 없고, 구간이 하나 늘면 옛 값과 비교할 수도 없다. **정렬된 객체로 봉인**한다.

★ 두 층인 이유: 구간 산식이 그대로여도 **집계·반올림 규칙이 바뀌면 답이 달라진다.**
그것은 구간의 판이 아니라 경로의 판이다.

---

## 5. 입력·출력 계약

```
PathCalculationRequest
├─ query_id · path_fingerprint            온톨로지 런타임이 낸 경로 정체성
├─ tenant_id · entity_mode · scope_node_id
├─ as_of                                  UTC — **경로 전체가 이것 하나를 쓴다**
├─ baseline_id · baseline_fingerprint
├─ sealed_snapshots     {계약키: snapshot_id}  관계 승인 때 봉인된 판
├─ relation_approvals   {relation_id: ledger_event_id}
├─ assumptions          가정 (⚠️ `reserved_quantity=0` 같은 **가정도 여기 든다**)
├─ path_model_version
└─ segment_capability_fingerprints  쓸 참조의 지문만

PathCalculationResult
├─ status                COMPLETE | BLOCKED
├─ request_fingerprint   언제나 있다
├─ result_fingerprint    COMPLETE 일 때만
├─ metrics               §5-0 §2 어휘 (BLOCKED 면 비어 있다)
├─ segment_outputs       구간별 지표 (〃)
├─ segment_model_versions
├─ used_snapshots        = sealed_snapshots 여야 한다
└─ blocked               {대외 사유, 내부 사유[]}   §2.1 의 두 층
```

---

## 6. 실행 관문

| # | 관문 | 실패하면 | 이미 있는 장치 |
|---|---|---|---|
| 1 | 경로의 모든 관계가 승인돼 있는가 | `BLOCKED` | 원장 |
| 2 | 승인이 **지금도** 유효한가(철회 재확인) | `BLOCKED` | §5a `ledger_verifier` |
| 3 | 구간별 참조가 실행 가능한가 | `BLOCKED` | §5a `assert_executable` |
| 4 | 봉인된 판이 전부 있는가 | `BLOCKED` | — |
| 5 | 끝점이 `as_of` 시점에 결속돼 있는가 | 무결성 장애(503) | Resolver `RELATION_ENDPOINT` |
| 6 | 읽은 판 == 봉인된 판인가 | 무결성 장애(503) | §3.6 |
| 7 | 필수 계약키의 인증판이 전부 있는가 | `BLOCKED` | 범위 색인 |

⚠️ **지금은 3번에서 전부 멈춘다.** 넷 다 `NOT_IMPLEMENTED`·`OUT_OF_SCOPE` 이기 때문이고,
이 계약은 그 사실을 **정직하게 표현하는 모양**을 정한 것이다.

---

## 7. 5b 전에 확정할 의미 규칙 (승인 반영)

### 7.1 `reserved_quantity`

데모에서는 **0 으로 가정하되 `assumptions` 와 지문에 반드시 넣는다.**

⚠️ 가정을 지문 밖에 두면 「예약 0 으로 계산한 결과」와 「예약 데이터로 계산한 결과」가
**같은 지문**을 갖는다.
⚠️⚠️ 운영 모델에서는 예약·할당 데이터 없이 0 으로 간주하면 **안 된다.**

### 7.2 `material_requirement` — BOM 이 정본

```
자재별 필요량 = plan_quantity × BOM quantity_per_output ÷ standard_yield
```

같은 자재의 BOM 행은 **자재별로 먼저 합산**한다(FG-CATHODE 는 같은 자재로 두 줄이다).

`MFG-01.material_requirement` 는 **대사 대상 파생값**으로 둔다.

⚠️⚠️ 저장값과 재계산값이 다르면(실측: 66.4 vs 67.35) **하나를 임의로 고르지 않고
readiness 실패**로 처리한다. 임의로 고르면 어느 쪽이 정본인지 아무도 모르게 되고,
그 선택은 코드 한 줄에 숨는다.

### 7.3 `revenue_shift_days`

```
revenue_shift_days  = 시나리오 예상 인식일 − 기준선 예상 인식일
delivery_delay_days = actual_ship_date − due_date      ← 별도 실적 KPI
```

---

## 8. B1 착수 범위 (승인)

**계산 없이 진행한다.** 경로와 정체성만 흘려보내고, 5b 가 열리면 지표가 그 자리에 채워진다.

| 할 것 | 안 할 것 |
|---|---|
| 런타임 `{nodes, edges}` → G5 `impact_path` 변환 | 수치 계산 |
| `query_id`·`path_fingerprint` 전달 | 고정 `ontology_path` 와 **혼합·fallback** |
| 승인·가시성이 확인된 경로만 전달 | 기존 `calc_graph` 결과와 섞기 |
| 계산 없으면 `BLOCKED`·`missing_steps` 로 전달 | 부분 수치 |

### 8.1 필수 회귀

1. 숨겨진 중간 노드가 있으면 **경로 전체 비노출**
2. 권한 밖 구간 수·이름 **비누설**
3. `query_id`·`path_fingerprint` 가 G5·원장·발간까지 **유지**
4. 경로 지문 불일치 시 **패키지 생성 거부**
5. 계산 미구현이 **0 또는 「영향 없음」으로 접히지 않음**
6. 기존 고정 경로 **fallback 부활 차단**

---

## 9. 상태

```
A   경로 단위 계산 계약   ██████████  rev.2 · 조건부 승인 반영
B1  경로 → G5 근거 어댑터 ░░░░░░░░░░  다음
5b  계산 모델            ░░░░░░░░░░  0/3 · HOLD
```

⚠️ §5 의 입출력 구조는 **B1 에서 전부 쓰이지 않는다.** B1 은 `query_id`·
`path_fingerprint`·`blocked` 세 자리만 채우고, 나머지는 5b 가 열릴 때 채운다 —
지금 빈 껍데기를 만들어 두면 「있는데 안 채워진 것」과 「없는 것」이 섞인다.
