# §7-0 대표 질문 종단 시뮬레이션 — **종이 위 통과 시험**

**상태: 검토용 · 코드 변경 없음 · 계약 `DESIGN_ONLY` 유지**
작성: Claude Code (백엔드) · 2026-08-20
전제 문서: [G2 승인 패키지 초안 2판](G2_ONTOLOGY_CONTRACT_APPROVAL_PACKAGE_DRAFT_2026-08-20.md)

> **결론 먼저** — 대표 질문은 닫히지 않는다. 다만 **막힌 이유가 첫 판과 다르다.**
>
> ⚠️⚠️ **[2026-08-20 정정]** 첫 판은 「`INV-01`·`SLS-01` 데이터 모델이 없다」고 적었다.
> **틀렸다.** `scripts/generate_sample_company_starter_kit.py` 에 다섯 계약키가 모두
> 있고 **행 단위 열쇠까지 갖췄다.** 내가 본 것은 낡은 `pilot_demo_seed.py` 였고,
> **한 시드만 보고 저장소 전체에 없다고 단정**한 것이다.
>
> 진짜 막힌 곳은 셋이다 — ① §7-0 이 **낡은 시연 어휘**를 쓰고 있고, ② `CALC.*` 를
> 실행으로 잇는 레지스트리가 없으며, ③ Resolver 가 **자기가 왜 불렸는지 모른다**(§4).
> ③이 가장 깊다.

---

## 0. 대표 질문 (확정)

> `PO-LINE-001` 의 선적 `SHP-001` 이 기준일 대비 **15일** 늦어지면, 어느 재고·생산계획·
> 판매계획이 영향을 받고 매출 인식 시점과 현금흐름은 어떻게 달라지며 어떤 결정을
> 요청해야 하는가?

```
PO-LINE-001
  ─ FULFILLED_BY_SHIPMENT → SHP-001
  ─ AFFECTS → (INV-01 대상 재고)
  ─ AFFECTS → (production-plan-line)
  ─ AFFECTS → (sales-line)
  ─ G4 계산 → 매출·현금 영향
  ─ G5 → 결정 안건
```

---

## 1. ⚠️⚠️ 시작 전에 드러난 차단점 — 실측

### 1.1 ⚠️ 정정 — 데이터 모델은 **이미 있다**

첫 판의 이 절은 `pilot_demo_seed.py` 만 보고 썼다. 계약형 생성기를 확인한 결과:

| 계약키 | 생성기의 열쇠 | 연결 필드 |
|---|---|---|
| `PRC-02` 구매주문 라인 | `po_line_id` (`{po_id}-10`) | — |
| `LOG-02` 선적 | `shipment_id` | **`po_line_id` 있음** |
| `INV-01` 재고 스냅샷 | `snapshot_id` (`STK-{일자}-{자재}-{창고}`) | 자재·창고·일자 |
| `MFG-01` 생산계획 라인 | `plan_line_id` (`MPS-…`) | `site_id` |
| `SLS-01` 판매 라인 | `sales_line_id` (`SO-…-10`) | 고객·일자 |

★ `FULFILLED_BY_SHIPMENT` 의 근거 `LOG-02.po_line_id` 가 **실제로 있다.** 행에
`scope_node_id` 도 붙어 있어 범위 색인이 쓸 재료도 갖춰져 있다.

**그러므로 할 일은 데이터를 새로 만드는 것이 아니라, 이 키트를 정본 시연 데이터로
승격하고 낡은 파일럿 어휘를 교체하는 것이다.**

### 1.1.1 (참고) 낡은 시드가 쓰던 어휘

`scripts/pilot_demo_seed.py` 가 만드는 데이터셋은 여덟이다:

```
supplier_master · purchase_orders · shipments · material_arrivals
production_plans · products · financials · external_indicators
```

계약의 `dataset` 계약키(`PRC-02`·`LOG-02`·`INV-01`·`MFG-01`·`SLS-01`)는 **하나도 없다.**
계약키 코드 자체는 `scripts/generate_sample_company_starter_kit.py` 에 정의돼 있지만
**시연 시드는 그 어휘를 쓰지 않는다.**

| 계약 요구 | **낡은** 파일럿 시드 | 판정 |
|---|---|---|
| `PRC-02` purchase-order-line | `purchase_orders` | 낟알이 다름(주문 vs 주문행) |
| `LOG-02` shipment | `shipments` | `po_line_id` 없음 |
| `INV-01` inventory-snapshot | 없음 | — |
| `MFG-01` production-plan-line | `production_plans` | 대응 가능 |
| `SLS-01` sales-line | 없음 | — |

⚠️ 이 표는 **낡은 시드의 한계**를 적은 것이지 저장소의 한계가 아니다.

⚠️ `material_arrivals` 는 입고 **움직임**(INV-02 성격)이지 재고 **스냅샷**이 아니다.
`financials.ending_inventory` 는 기간 합계이지 자재별 재고가 아니다. 둘 중 어느 것도
`INV-01` 을 대신할 수 없다 — **대신하게 만들면 그 순간 조용한 거짓말이 된다.**

⚠️ `products` 는 품목 마스터이지 판매 **계획선**이 아니다. 단가가 있다고 `SLS-01` 로
쓰면 「매출 인식 시점」 질문에 **시점이 없는 데이터로 답하는 것**이 된다.

> ⚠️ 첫 판은 여기서 「`SLS-01` 도 없다」고 한 걸음 더 나아갔다. **한 시드에 없는 것을
> 저장소에 없는 것으로 넓힌 것**이고, 그 확대가 틀렸다. 없는 것을 찾을 때는
> **어디를 봤는지**를 먼저 적어야 한다.

### 1.2 낟알 — 낡은 시드에는 `po_line_id` 가 없고, 정본 키트에는 있다

낡은 `shipments` 는 `po_no`(주문 단위)를 갖는다. 「지금은 1:1이니 괜찮다」로 넘기면
**다품목 주문이 들어오는 순간 조용히 잘못 연결된다.**

★ 계약형 생성기의 `LOG-02` 는 `po_line_id` 를 그대로 갖는다 — **끼워 맞출 필요가 없다.**
정본 데이터원을 바꾸면 이 문제는 사라진다.

### 1.3 계산 참조 3종은 **이름만 있다**

```
CALC.LOGISTICS.ARRIVAL_DELAY.v1
CALC.INVENTORY.MATERIAL_SHORTAGE.v1
CALC.PRODUCTION.REVENUE_TIMING.v1
```

전 저장소 검색 결과 이 세 문자열은 **계약 JSON 과 시험 파일에만** 있다. 제품의 실행
경로에는 없다.

제품의 실제 G4 진입점은 **다른 어휘**다:

| | 계약이 쓰는 이름 | 제품이 실제로 쓰는 것 |
|---|---|---|
| 계산 | `CALC.<도메인>.<이름>.v1` | `calc_graph.simulate(baseline, base_values, assumptions)` |
| 동인 | (없음) | `planning_drivers` 의 `driver_code` (`DRV-SUPPLY` 등) |
| 지문 | (없음) | `_fingerprint(baseline_fp, assumptions)` + `CALC_VERSION` |

즉 **`CALC.*` 를 키로 무언가를 부르는 레지스트리가 존재하지 않는다.**
→ 세 계산 모두 **`NOT_IMPLEMENTED`** 로 적는다. 「참조가 있다」와 「계산이 실행된다」는
다른 말이고, 이 문서는 그 둘을 섞지 않는다.

---

## 2. 홉별 통과 시험

범례 — ● 통과 · △ 가정 필요 · ✗ 차단

### 홉 1 · `PO-LINE-001` ─`FULFILLED_BY_SHIPMENT`→ `SHP-001`

| 축 | 답 | |
|---|---|:---:|
| 객체 | 주어 `dataset:purchase-order-line:PO-LINE-001` / 목적어 `dataset:shipment:SHP-001` | ● |
| 원천 | `PRC-02` → 시연 `purchase_orders` / `LOG-02` → 시연 `shipments` | △ |
| 범위 | `tenant_demo` · `REAL` · 시연 조직 노드 | ● |
| 시간 | Snapshot 인증 시점 = 시드 실행 시각 · 관계 유효기간 = 승인 시각부터 · `as_of` = 질의값 | ● |
| 관계 | `FULFILLED_BY_SHIPMENT` · 승인 원장 ID 필요 · 근거 `LOG-02.po_line_id` | △ |
| 계산 | 없음(정성 관계) | ● |
| 결과 | 경로 노드 2개 · `path_fingerprint` 산출됨 | ● |
| 결정 | — | |
| 성격 | `DEMO/SYNTHETIC` | ● |
| 실패 상태 | 색인 없으면 **503**(승인 관계의 끝점이므로) | ● |

**△ 사유**: ① 계약키 대응이 이름이 아니라 **사람의 판단**으로 이어져 있다.
② `po_line_id` 가 없어 `po_no` 를 행 식별자로 쓴다는 **명시적 가정**이 필요하다.

### 홉 2 · `SHP-001` ─`AFFECTS`→ 재고 (정본 데이터원 전환 필요)

| 축 | 답 | |
|---|---|:---:|
| 객체 | 목적어 `dataset:inventory-snapshot:STK-…` | ● |
| 원천 | `INV-01` — 계약형 생성기에 **있다**(낡은 시드에만 없었다) | ● |
| 관계 | 근거 «approved delay model» — 승인된 지연 모델이 **없다** | ✗ |
| 계산 | `CALC.LOGISTICS.ARRIVAL_DELAY.v1` → **`NOT_IMPLEMENTED`** | ✗ |
| 실패 상태 | 목적어 부재는 «비노출» 이 아니라 **자료 미비**다 | — |

⚠️ 낡은 시드의 `material_arrivals` 로 대신하고 싶은 유혹이 있었다. 그러면 경로는
「연결됨」이 되지만 **답은 재고가 아니라 입고 기록**이 된다 — 질문을 바꾸는 것이다.
★ 정본 `INV-01` 을 쓰면 그럴 이유가 없다.

### 홉 3 · 재고 ─`AFFECTS`→ `production-plan-line`

| 축 | 답 | |
|---|---|:---:|
| 객체 | 목적어 `dataset:production-plan-line:*` — 시연 `production_plans` 대응 | ● |
| 주어 | 정본 전환 뒤에는 도달 가능 | ● |
| 계산 | `CALC.INVENTORY.MATERIAL_SHORTAGE.v1` → **`NOT_IMPLEMENTED`** | ✗ |

★ 남은 차단은 계산뿐이다 — 관계도 데이터도 있다.

### 홉 4 · `production-plan-line` ─`AFFECTS`→ `sales-line` (정본 데이터원 전환 필요)

| 축 | 답 | |
|---|---|:---:|
| 객체 | 목적어 `dataset:sales-line:SO-…-10` | ● |
| 원천 | `SLS-01` — 계약형 생성기에 **있다** | ● |
| 계산 | `CALC.PRODUCTION.REVENUE_TIMING.v1` → **`NOT_IMPLEMENTED`** | ✗ |

### 홉 5 · G4 계산 — 매출·현금 영향

제품에는 **작동하는 계산 경로가 이미 있다.** 다만 계약이 부르는 이름과 다르다.

| 축 | 답 | |
|---|---|:---:|
| 진입점 | `calc_graph.simulate(baseline, base_values, assumptions)` | ● |
| 입력 | 기준선 ID + 가정(동인 확장 포함) | ● |
| 결과 지문 | `sha256({baseline, calc: CALC_VERSION, assumptions})` — **결정론적** | ● |
| 계약 연결 | `CALC.*` → `simulate` 를 잇는 레지스트리 **없음** | ✗ |

★ 즉 홉 5 는 **계산이 없어서가 아니라 계약과 제품이 서로를 부르지 못해서** 막혀 있다.
이것은 §1.3 의 다른 얼굴이고, 다른 종류의 일이다 — 계산기를 새로 만드는 것이 아니라
**이름을 잇는 계약**을 정하는 일이다.

### 홉 6 · G5 결정 안건

⚠️ **첫 판에서 이 칸을 잘못 적었다.** 「계산 결과 ID 를 받는 자리가 없다」고 썼는데,
`decision_package.build()` 를 열어 보니 **이미 싣고 있다.** 코드를 보지 않고 적었다.

| 축 | 답 | |
|---|---|:---:|
| 안건 생성 | 책임자·기한이 없으면 **만들지 않는다**(빈 안건 방지) | ● |
| 계산 결과 ID | `evidence.result_fingerprint` — **있다** | ● |
| 기준선 결속 | `baseline_fingerprint`·`baseline_id`·`snapshot_ids`·`as_of` — **있다** | ● |
| 기준선 대조 | 기준선이 다른 두 결과는 **비교를 거부**한다 | ● |
| 영향 경로 자리 | `evidence.impact_path` — **자리는 있다** | ● |
| 경로 출처 | 그 자리는 **고정 `core/ontology_path.py`** 의 모양에 배선돼 있다 | ✗ |
| 경로 ID | 런타임의 `query_id`(`oq_…`)·`path_fingerprint` 는 **안 실린다** | ✗ |
| 성격 표시 | 브리핑 첫 줄 `[시연용 합성 데이터]` | ● |

★ 즉 G5 는 **거의 다 준비돼 있다.** 남은 것은 두 가지뿐이다:

```
① 모양이 다르다 — build() 는 {"path", "missing_evidence", "missing_steps"} 를 읽고,
   런타임은 {"nodes", "edges", "path_fingerprint"} 를 낸다
② 질의 정체성이 안 실린다 — query_id 와 path_fingerprint 를 담을 열쇠가 없다
```

⚠️ ②가 없으면 「이 안건은 어느 질의의 어느 경로에서 나왔는가」에 답할 수 없다.
  결과 지문은 **계산**을 재현하지만 **경로**를 재현하지 않는다.

---

## 3. 출구 조건 판정

| # | 출구 조건 | 판정 |
|---|---|:---:|
| 1 | 4관계가 중간 노드 생략 없이 연결됨 | △ 정본 데이터원 전환이 선행 |
| 2 | 모든 끝점이 같은 허용 문맥에서 해석됨 | — 도달 못 함 |
| 3 | `as_of` 가 바뀌면 올바른 옛 Snapshot 을 선택함 | ✗ **Resolver 가 `as_of` 를 못 받는다**(§4) |
| 4 | 계산 참조가 실행되거나 `NOT_IMPLEMENTED` 로 명시됨 | ● 명시함(3종 모두) |
| 5 | G5 안건이 경로 ID·계산 결과 ID 를 참조함 | △ 계산 ● · 경로 ✗ |
| 6 | 같은 입력 재실행 시 같은 결과 지문 | ● 두 지문 모두 결정론적 |

**6개 중 2개 통과 · 1개 절반.** 그림은 그릴 수 있지만 **경로는 닫히지 않는다.**

---

## 4. ⚠️⚠️ 시뮬레이션이 드러낸 Resolver 계약의 구멍

현재 계약은 이렇다:

```python
object_scope_resolver(ref: ObjectRef) -> ResourceScope | None
#   ObjectRef = (namespace, object_type, object_id)   ← 이것뿐이다
```

호출부(`_object_visible`)의 처리는:

```
scope 가 None      → 안 보임(False)
예외가 나면        → OntologyIntegrityError (503)
```

여기서 **§4.3-3 의 세 갈래를 만들 수 없다.**

| 상황 | 있어야 할 답 | 지금 낼 수 있나 |
|---|---|:---:|
| 사용자가 아무 id 나 넣음 | `None` / 404 | ● |
| **승인된 관계의 끝점**인데 색인에 없음 | **503** | ✗ 구별 못 함 |
| 인증 Snapshot 에 있어야 하는데 색인에 없음 | **503** | ✗ 구별 못 함 |

Resolver 는 자기가 «임의 조회» 때문에 불렸는지 «승인된 관계를 그리는 중» 에 불렸는지
**알 방법이 없다.** 같은 `ObjectRef` 가 오기 때문이다.

같은 이유로 출구 조건 3도 불가능하다 — `as_of` 가 전달되지 않으니 **판을 고를 수 없다.**

### 필요한 확장 (설계 제안, 미구현)

```python
object_scope_resolver(ref: ObjectRef, ctx: ResolveContext) -> ResourceScope | None

ResolveContext = (purpose, as_of, evidence_ref)
    purpose:      "browse" | "relation_endpoint" | "evidence"
    as_of:        판 선택에 쓴다 — 「그냥 최신」 금지
    evidence_ref: 관계 승인 시 봉인된 snapshot_id
```

⚠️ 이것은 **깨는 변경**이다. 지금 배선된 `ecm` Resolver 도 서명이 바뀐다.
★ 다만 §3.1 에서 확인했듯 `ecm` 은 이 계약의 제약에 안 쓰이므로, **Dataset Resolver 를
만들기 전에 바꾸는 것이 가장 싸다.** 나중에 바꾸면 이미 배선된 것들을 함께 고쳐야 한다.

---

## 5. §4.3 세 판단 — 시뮬레이션이 확인해 준 것

Supervisor 잠정 권고를 시뮬레이션에 넣어 본 결과, **셋 다 그대로 맞다.**

**① 색인 구조 — 정체성과 판 이력을 분리한다**

```
정체성      (namespace, object_type, object_id)
판별 결속   (namespace, object_type, object_id, snapshot_id)
```

★ 홉 1 에서 `SHP-001` 은 여러 인증판에 걸쳐 **같은 배**다. 정체성을 판에 묶으면
`as_of` 를 바꿀 때마다 **다른 객체**가 되어 경로가 끊긴다.

**② 여러 인증판 — `as_of` 이하에서 유효한 CERTIFIED 중 선택, 동점이면 503**

⚠️ 「그냥 최신」은 과거 시점 질의에 **오늘의 답**을 준다. 동점을 임의로 고르는 것은
더 나쁘다 — 재실행 지문이 흔들려 출구 조건 6이 무너진다.

**③ 색인 미존재 — 세 갈래**

§4 에서 본 대로 **지금 계약으로는 구현 불가**다. `purpose` 가 먼저 필요하다.

---

## 6. 다음에 할 일 (권고 순서)

| # | 일 | 왜 이 순서인가 |
|---|---|---|
| 1 | **Resolver 계약에 `ResolveContext` 추가** | 배선이 하나(`ecm`)뿐이고 그마저 이 계약에 안 쓰인다 — 지금이 제일 싸다 |
| 2 | **기존 샘플 회사 키트를 정본 시연 데이터로 승격** | 만드는 일이 아니라 **바꿔 다는** 일 |
| 3 | 낡은 파일럿 어휘 교체 | `po_no` → `po_line_id` 등 |
| 4 | `CALC.*` → 제품 계산 진입점 레지스트리 | 계산기를 만드는 일이 아니라 **잇는** 일 |
| 5 | Dataset 색인 구현 | 위 넷이 정해져야 열쇠가 정해진다 |
| 6 | 런타임 경로 → `build()` 모양 어댑터 + `query_id`·`path_fingerprint` 적재 | 홉 6 의 남은 둘 |
| 7 | 시뮬레이션 재실행 | 출구 조건 6개 전부 |

⚠️ 계약을 **낡은 데이터에 맞춰 낮추는 것**이 이 문서에서 가장 위험한 지점이었다.
`material_arrivals`→재고, `products`→판매계획 치환은 경로를 「연결됨」으로 만들지만
**질문을 바꾼다.** 정본 키트가 이미 있으므로 그럴 이유가 없다.

---

## 7. 별도 잔여사항 — 시험 격리 (Gate A 전 필수)

`tests/conftest.py` 의 `ecm_org_seed` 는 운영 ECM 을 읽어 시험 DB 에 복사한다.
불변식 검사기의 «읽기 흔적 면제» 는 **운영 오염을 막을 뿐**, 깨끗한 checkout 과 운영
데이터가 다른 환경에서 **같은 시험 결과를 보장하지 않는다.**

· §7-0 종이 시뮬레이션을 막지는 않는다
· **Gate A 전에 고정 합성 조직 fixture 로 전환**해야 한다
· ⚠️ 운영 ECM 읽기 면제를 «시험 격리 완료» 로 세면 안 된다

---

## 8. 요약

```
대표 질문 확정          ██████████
홉 1 (주문→선적)         ███████░░░  가정 2건 필요
홉 2 (선적→재고)         █████░░░░░  데이터 있음 · 정본 전환 + 계산 필요
홉 3 (재고→생산계획)      █████░░░░░  데이터 있음 · 계산 필요
홉 4 (생산계획→판매)      █████░░░░░  데이터 있음 · 계산 필요
홉 5 (G4 계산)           ████░░░░░░  계산은 있고 이름이 안 이어짐
홉 6 (G5 결정)           ███████░░░  결과 ID·기준선 결속 있음 · 경로 ID 와 모양이 남음
출구 조건               ████░░░░░░  6 중 2.5
```

**한 줄로**: 관계는 계약에 다 있고, 계산도 G5 결속도 제품에 이미 있다.
없는 것은 **두 칸의 데이터**(`INV-01`·`SLS-01`), **이름을 잇는 계약**
(`CALC.*` ↔ `simulate`, 런타임 경로 ↔ `build()` 모양), 그리고 Resolver 가
「무엇을 위해 불렸는지」를 아는 방법이다. **새로 만들 것보다 이어 붙일 것이 많다.**
