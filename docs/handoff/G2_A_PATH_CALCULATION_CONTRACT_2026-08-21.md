# A — **경로 단위 계산 계약** (설계 · 구현 없음)

작성: Claude Code (백엔드) · 2026-08-21
**상태: 설계 초안 · 교차검토 대기.** 코드 변경 없음. 계산은 여전히 하나도 실행되지 않는다.
전제: [§5-0 계산 의미 계약 2판](G2_S5_0_CALCULATION_SEMANTICS_CONTRACT_2026-08-21.md)(승인 대기)

---

## 0. 이 문서가 정하는 것

「경로 하나에 대해 **한 번에** 계산한다」가 무슨 뜻인지 — 무엇을 넣고, 무엇이 나오고,
막혔을 때 무엇을 돌려주는지.

⚠️ 산식은 정하지 않는다. 그것은 5b 이고, §5-0 이 승인돼야 착수한다.

---

## 1. 왜 간선별이 아닌가

간선마다 계산기를 하나씩 두면 이런 일이 생긴다.

**① 네 번 반올림한다.** 각 구간이 자기 결과를 내고 다음 구간이 그것을 받는다.
`producible_qty` 를 소수 여섯 자리에서 자르고, 그 값으로 `revenue_shift_days` 를 내면
하루 경계에서 답이 갈린다.

**② 중간값이 서로 다른 판에서 올 수 있다.** 구간마다 따로 `as_of` 를 해석하면
`INV-01` 은 6월 판, `MFG-01` 은 3월 판을 볼 수 있다. 각 구간은 옳고 **합쳐진 답이
틀린다.**

**③ 같은 질문에 두 번 답할 때 값이 흔들린다.** ①②가 겹치면 재실행 지문이 달라지고,
그러면 「이 숫자는 무엇으로 만들었나」에 답할 수 없다.

★ 그래서 **경로 하나가 계산의 단위**다. 계산 참조 4종은 각자 실행되는 것이 아니라
그 경로 안의 **구간 이름**이 된다.

---

## 2. 입력 계약

```
PathCalculationRequest
├─ path                    관계 id 목록 + 끝점 ObjectRef 들 (온톨로지 런타임이 낸 것)
├─ query_id                그 경로가 나온 질의 (oq_…)
├─ path_fingerprint        경로 자체의 지문
├─ as_of                   UTC 정규화된 한 시점 — **경로 전체가 이것 하나를 쓴다**
├─ tenant_id · entity_mode 객체 정체성 (§4.1a)
├─ sealed_snapshots        {계약키: snapshot_id}  관계 승인 때 봉인된 판
├─ relation_approvals      {relation_id: ledger_event_id}
├─ assumptions             가정 (예: 선적 지연 일수)
└─ capability_fingerprint  실행 시점의 Registry 지문
```

### 2.1 ⚠️ `as_of` 는 **하나**다

경로 전체가 같은 시점을 쓴다. 구간별로 다른 시점을 허용하면 §1-② 가 그대로 일어난다.

### 2.2 ⚠️⚠️ 봉인된 판이 없으면 계산하지 않는다

관계를 승인할 때 봉인한 `snapshot_id` 가 있어야 한다. 없으면 **거부**한다 —
「지금 최신 판으로 하죠」는 그때 승인한 그 자료가 아니다.

★ 이 검사는 이미 있다: Resolver 가 `required_snapshot_id` 와 다르면 무결성 장애를 낸다.
경로 계산은 그 장치를 **쓰는 쪽**이지 새로 만들지 않는다.

---

## 3. 출력 계약

```
PathCalculationResult
├─ status              COMPLETE | BLOCKED
├─ segments[]          구간마다: calculation_ref · 상태 · 지표들 · 쓴 판
├─ metrics             경로 전체의 지표 (§5-0 §2 어휘)
├─ result_fingerprint  결정론적 지문
├─ model_version       산식 판
├─ used_snapshots      실제로 읽은 판 전부
├─ capability_fingerprint  계산 능력 계약의 지문
└─ blocked_segments[]  막힌 구간과 **사유**
```

### 3.1 ⚠️⚠️ 부분 결과를 내지 않는다

구간 하나라도 막히면 **경로 전체가 `BLOCKED`** 이고, 지표는 비어 있다.

「앞의 두 구간은 계산됐으니 그것만 보여 주자」가 위험하다. 화면에 숫자가 뜨면 사람은
그것을 **답**으로 읽는다. 「재고 부족 230톤」만 보이고 매출 영향이 비어 있으면,
읽는 사람은 「매출 영향은 없구나」로 받아들인다 — 실제로는 **계산하지 못한 것**이다.

★ 대신 `blocked_segments` 가 **어느 구간이 왜 막혔는지**를 이름으로 말한다.
G5 의 `missing_steps` 가 이미 그 자리를 갖고 있다(설계 §12: 계약키가 아니라 사람이
읽는 이름으로).

### 3.2 결정론적 지문

```
result_fingerprint = sha256({
    path_fingerprint, as_of(UTC), tenant_id, entity_mode,
    sealed_snapshots(정렬), assumptions(정렬·반올림),
    model_version, capability_fingerprint
})
```

⚠️ `capability_fingerprint` 가 들어가는 것이 중요하다 — 산식 계약이 바뀌면 **옛 결과가
스스로 무효**임을 드러낸다. §5a 에서 `mvp_scope`·`ledger_event_id` 까지 지문에 넣은
이유가 여기서 쓰인다.

⚠️ `used_snapshots` 는 지문에 **넣지 않는다.** 봉인된 판이 이미 입력에 있고, 실제로
읽은 판이 그와 다르면 그것은 지문이 아니라 **무결성 장애**로 다뤄야 한다.

---

## 4. 실행 관문

계산을 시작하기 전에 순서대로 본다. 하나라도 걸리면 **그 자리에서 멈춘다.**

| # | 관문 | 실패하면 |
|---|---|---|
| 1 | 경로의 모든 관계가 승인돼 있는가 | `BLOCKED` · 관계 이름 |
| 2 | 승인이 지금도 유효한가(**철회 재확인**) | `BLOCKED` · 철회 사유 |
| 3 | 구간별 `calculation_ref` 가 실행 가능한가 | `BLOCKED` · §5a 의 사유 그대로 |
| 4 | 봉인된 판이 전부 있는가 | `BLOCKED` |
| 5 | 끝점이 `as_of` 시점에 결속돼 있는가 | 무결성 장애(503) |
| 6 | 필수 계약키의 인증판이 전부 있는가 | `BLOCKED` · 없는 계약키 |

★ 2번은 §5a 의 `assert_executable(ref, ledger_verifier)` 가 이미 요구한다.
★ 5번은 Resolver 가 이미 한다(`RELATION_ENDPOINT` 목적).

⚠️ **지금은 3번에서 전부 멈춘다.** 넷 다 `NOT_IMPLEMENTED`·`OUT_OF_SCOPE` 이기 때문이다.
그것이 지금의 사실이고, 이 계약은 그 사실을 **정직하게 표현하는 모양**을 정한 것이다.

---

## 5. G5 로 넘기는 모양 (B 의 입력)

`decision_package.build()` 는 이미 다음을 싣는다:

```
result_fingerprint · baseline_fingerprint · baseline_id · snapshot_ids · as_of
assumptions · impact_path · missing_evidence · missing_steps
```

**남은 것은 둘뿐이다.**

| 필요한 것 | 지금 | 할 일 |
|---|---|---|
| 경로 정체성 | 없음 | `query_id`·`path_fingerprint` 를 `evidence` 에 더한다 |
| 경로 모양 | 고정 `ontology_path` 모양 | 런타임 `{nodes, edges}` → `{path, missing_*}` 어댑터 |

⚠️ `build()` 는 **기준선이 다른 두 결과의 비교를 거부**한다. 경로 계산도 같은 규칙을
따라야 한다 — 봉인 판이 다른 두 결과를 비교하지 않는다.

★ B 는 **계산 없이도 할 수 있다.** 경로와 정체성만 흘려보내면 되고, 5b 가 열리면
지표가 그 자리에 채워진다.

---

## 6. 아직 정하지 않은 것

1. **가정의 어휘** — `calc_graph` 는 `lead_time_days` 를 쓴다. 경로 계약도 그 이름을
   쓸 것인가, 「선적 지연」을 관계에 붙일 것인가
2. **구간 결과의 낟알** — 자재별로 낼 것인가, 경로 하나에 하나만 낼 것인가
   (§5-0 은 `shortage_qty` 를 **자재별**로 정의했다)
3. **`model_version` 의 주인** — 경로 계약의 판인가, 구간별 계산의 판을 합친 것인가
4. **부분 결과 금지의 예외** — 「구간 3까지만 승인된 경로」를 아예 만들 수 없게 할지,
   만들되 계산을 거부할지

★ 1·2 는 5b 착수 전에, 3·4 는 B 착수 전에 정해야 한다.

---

## 7. 상태

```
A  경로 단위 계산 계약   █████████░  설계 초안 · 교차검토 대기
B  경로 → G5 어댑터      ░░░░░░░░░░  A 검토 후 · **계산 없이 진행 가능**
5b 계산 모델            ░░░░░░░░░░  §5-0 승인 후 · HOLD
```

**판단 요청**: §3.1(부분 결과 금지)과 §3.2(지문 구성)를 확정해 주십시오. §6 의 3·4 를
정해 주시면 B 를 바로 시작할 수 있습니다.
