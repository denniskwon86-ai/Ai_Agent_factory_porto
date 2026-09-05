# G2 첫 수직 온톨로지 계약 — 승인 패키지 **초안** (2판)

**상태: 검토용 초안 · 제출 HOLD · 설치 금지 · `DESIGN_ONLY` 유지**
작성: Claude Code (백엔드) · 2026-08-20
대상 계약: `docs/architecture/g2_first_vertical_ontology_contract_v1.json`
계약 판: `1.0.0-design` · 지문 `1d7b5e7d400867fb…`

> **2판에서 무엇이 바뀌었나** — 1판은 최소 경로를 12관계로 잡았다. Supervisor 가 계약을
> 직접 파싱해 대조한 결과 **그 12관계는 하나의 연결 경로를 만들지 못했고**, 제외해도
> 된다고 적은 MDM 은 사실 그 12관계에 끼어 있었다. 2판은 계약 제약 25건을 다시 파싱해
> **실제로 닫히는 4관계**로 재정의한다. 1판의 §2·§3·§7 은 폐기한다.

---

## 0. 이 문서가 요청하는 것과 요청하지 않는 것

**요청하지 않는다** — 지금 계약을 `APPROVED` 로 올리는 것.
**요청한다** — §7 의 실행 순서와 §4 의 색인 계약을 확정하는 것.

⚠️ 계약 상태를 바꾸는 것은 사람의 결정이다. Claude Code 가 바꾸지 않는다.

---

## 1. 계약 개요

| | |
|---|---|
| 계약 id | `G2-FIRST-VERTICAL-ONTOLOGY` |
| 판 | `1.0.0-design` |
| 객체 유형 | 28종 (ecm 1 · mdm 9 · dataset 14 · external 1 · g4 1 · decision 2) |
| 관계 유형 | 25종 |
| 제약 | 25건 |
| 질의 의도 | `DEFINE` `RELATE` `TRACE` `IMPACT` `AS_OF` `COMPARE_SCOPE` `READINESS` `WHAT_IF` `EVIDENCE` |

---

## 2. ⚠️ 1판의 「최소 12관계」는 틀렸다

### 2.1 무엇이 틀렸나 (계약 파싱 결과)

**① 끊긴 사슬을 최소 경로라고 불렀다.**
`DELIVERED_TO` 의 주어는 `dataset:shipment` 가 아니라 **`dataset:transport-event`** 다.
그 앞을 잇는 `DELIVERED_BY`(shipment → transport-event)를 1판은 «제외» 로 적었다.
**닿을 수 없는 노드를 필수 관계 목록에 넣어 둔 것이다.**

**② MDM 을 제외할 수 있다고 했는데, 1판의 12관계 중 6개가 MDM 끝점을 쓴다.**

```
ORDERS_MATERIAL     → mdm:material      STOCKS_MATERIAL   → mdm:material
DELIVERED_TO        → mdm:location      POSTED_TO_ACCOUNT → mdm:account
CONSUMES_MATERIAL·PRODUCES_MATERIAL → mdm:*  (주어도 mdm:bom-line 이다)
```

**③ `DRIVES` 를 넣으면서 `external` 을 뺐다.** 계약상 `DRIVES` 는
`external:external-observation → g4:driver` 다. `g4` 만 배선해서는 성립하지 않는다.

**④ `decision` 은 이 계약에서 쓰이지 않는다.** 객체 유형에는 2종이 있지만
**제약 25건 중 `decision:*` 을 쓰는 것이 하나도 없다.** 1판은 그것을 설치 선행 조건에
넣었다 — 있지도 않은 요구를 스스로 만든 셈이다.

> ⚠️ 네 가지 모두 «계약을 읽지 않고 로드맵의 그림을 옮겨 적어서» 생긴 오류다.
> 2판의 모든 관계는 `constraints` 배열에서 직접 뽑았다.

### 2.2 실제로 닫히는 최소 경로 — **4관계, `dataset` 만**

```
purchase-order-line → shipment → inventory-snapshot → production-plan-line → sales-line
```

| 주어 | 관계 | 목적어 | 근거 | 계산(G4) |
|---|---|---|---|---|
| `purchase-order-line` | `FULFILLED_BY_SHIPMENT` | `shipment` | `LOG-02.po_line_id` | — |
| `shipment` | `AFFECTS` | `inventory-snapshot` | approved delay model | `CALC.LOGISTICS.ARRIVAL_DELAY.v1` |
| `inventory-snapshot` | `AFFECTS` | `production-plan-line` | approved BOM/inventory/plan | `CALC.INVENTORY.MATERIAL_SHORTAGE.v1` |
| `production-plan-line` | `AFFECTS` | `sales-line` | approved production-sales allocation | `CALC.PRODUCTION.REVENUE_TIMING.v1` |

**끝점이 전부 `dataset`** 이다. 그래서 **Dataset Resolver 하나로 이 경로가 닫힌다.**

★ 셋이 `calculation_ref` 를 달고 있다는 것이 중요하다 — **역할 경계가 계약에 이미
적혀 있다.** 온톨로지는 「어디로 이어지는가」를 답하고, 숫자는 G4 가 낸다.

### 2.3 이번 설치에 넣지 않는 것과 그 이유

| 대상 | 왜 지금 아닌가 |
|---|---|
| MDM 관계 9건 | 물량·계정 차원을 더한다. 첫 폐루프에는 **경로**만 필요하다 |
| `DRIVES`(external → g4) | 환율·운임 영향은 확장이다. Resolver 두 개가 더 필요해진다 |
| `cost-record → ledger-line` | 위 사슬과 **떨어져 있다**. 재무 연결은 G4 계산 결과로 잇는다 |
| `SETTLED_BY`·`FULFILLS_SALES` 등 | 경로를 넓히기만 하고 시연 질문에 답하지 않는다 |
| `decision:*` | **계약이 쓰지 않는다.** G5 는 관계가 아니라 계산 결과를 받는다 |
| `OWNED_BY`·`LOCATED_AT`·`AUTHORIZED_BY` | 제약 25건 **어디에도 안 나온다**(계약 자체의 미사용 관계) |

---

## 3. Resolver 준비 상태

### 3.1 ⚠️⚠️ 배선한 하나가 이 계약에서는 안 쓰인다

| namespace | 제약에서 쓰이나 | Resolver | 최소 경로에 필요 |
|---|:---:|:---:|:---:|
| `dataset` | ● (20건) | ✗ | **● 필요** |
| `mdm` | ● (9건) | ✗ | ✗ |
| `external` | ● (1건) | ✗ | ✗ |
| `g4` | ● (1건) | ✗ | ✗ |
| `ecm` | **✗ (0건)** | ● 배선됨 | ✗ |
| `decision` | **✗ (0건)** | ✗ | ✗ |

★ `ecm` Resolver 는 제대로 동작하지만 **이 계약의 제약 어디에도 `ecm:` 끝점이 없다.**
`OWNED_BY`·`LOCATED_AT` 가 미사용 관계이기 때문이다. 즉 **지금까지 배선한 하나는 이
계약의 관계 탐색에서 한 번도 불리지 않는다.**

⚠️ 1판은 이것을 「28종 중 1종 완료」로 적었다. 분모가 틀렸을 뿐 아니라 **분자도 이
계약에는 기여하지 않는다.** 실제 상태는 **최소 경로 기준 0/1** 이다.

※ `ecm` 배선이 헛일이라는 뜻은 아니다. 조직 범위 판정과 승인 결속 경로는 그대로 쓰이고,
Resolver 계약의 모양(fail-closed · 503 · 승인 대조)을 먼저 확정한 값이 있다.

### 3.2 미배선은 `None` 이 아니라 503 이다

`None` 이면 화면이 「영향 경로 없음」을 그리고 사람은 그것을 **사실**로 읽는다.
실제로는 우리가 아직 안 만든 것이다. 그래서 미배선 namespace 는 예외를 던진다.

---

## 4. Dataset 범위 색인 계약 (확정안)

### 4.1 왜 필요한가

계약의 `dataset` 객체 id 는 **업무 레코드 ID**(`SHP-001`, `PO-LINE-001`)이지
Snapshot ID(`ds_…`)가 아니다. 그런데 범위(`tenant_id`·`entity_mode`·`scope_node_id`)는
Snapshot 이 들고 있다. 그 사이를 잇는 것이 없다.

⚠️ 첫 구현은 레코드 ID 를 그대로 `get_snapshot()` 에 넣었다 — 영영 찾지 못하는데
결과가 `None` 이라 「범위 밖」과 구분되지 않았고, 그것을 «배선 완료» 로 보고했다.

### 4.2 확정안 (Supervisor 권고)

| 항목 | 결정 |
|---|---|
| 생성 주체 | **CERTIFIED Snapshot 승인 시 자동 생성** |
| 저장 위치 | **`data_preparation` 측 색인** — 온톨로지 DB 에 업무 본문을 복제하지 않는다 |
| 판 교체 | 새 Snapshot 에 **새 색인 판**을 만들고 **옛 판은 보존** |
| 필수 결속 | `object_id` + `snapshot_id` + row evidence + `tenant_id`/`entity_mode`/`scope_node_id` |
| 관계 승인 | 양 끝점과 `evidence_refs` 가 **승인된 판에 결속**됐는지 확인 |

★ 「옛 판 보존」이 `as_of` 질의의 전제다. 옛 판을 지우면 과거 시점 질의가 **오늘의
답**을 내게 되고, 그것은 조용한 거짓말이다.

### 4.3 남은 구현 판단 3건

1. 색인의 열쇠를 `(namespace, object_type, object_id, snapshot_id)` 로 둘 것인가,
   `(namespace, object_type, object_id)` 에 판 이력을 따로 둘 것인가
2. 한 레코드 ID 가 **여러 인증판**에 있을 때 Resolver 가 어느 판을 고르는가
   (질의의 `as_of` 로 고르는 것이 자연스럽지만, 명시해야 한다)
3. 색인에 없는 `object_id` 는 `None`(안 보임)인가 **예외**(자료 불일치)인가
   ★ §3.2 의 원칙대로면 **예외**가 맞다 — 「색인에 없다」는 「범위 밖」이 아니다

### 4.4 MVP 데이터와의 관계

현재 시연 키트는 9종 계약키(59행)를 덮는다. 최소 경로가 요구하는 것은
`PRC-02`·`LOG-02`·`INV-01`·`MFG-01`·`SLS-01` 다섯이다. **`INV-01`(재고 Snapshot)이
없다** — 지금은 재무 기준선의 기말재고로 대신하고 있다. 색인 설계와 함께 채워야 한다.

---

## 5. 승인에 필요한 형식 요소

| 항목 | 값 | 정한 사람 |
|---|---|---|
| 승인자(`actor_id`) | (미정) | Supervisor |
| 원장 이벤트 | `ONTOLOGY_MODEL_APPROVED` · `subject_type=ontology_model_contract` · `subject_id=`**계약 지문** | 자동 |
| 유효 시작(`effective_from`) | (미정) | Supervisor |
| 계약 판 | `1.0.0` | Supervisor |

### 5.1 ⚠️⚠️ 판을 올리면 지문이 바뀐다 — 승인 순서의 함정

지문은 파일 해시가 아니라 **컴파일된 내용**(`contract_id`·`contract_version`·관계·제약)의
해시이고, `contract_version` 도 재료에 들어간다:

| 판 | 지문 |
|---|---|
| `1.0.0-design` (지금) | `1d7b5e7d400867fb980e6a96218ba419…` |
| `1.0.0` (설치판) | `0e5f3ef772156ee589c8014e3fc7ed84…` |

★ **판을 먼저 올리고 그 지문으로 승인**해야 한다. 지금 지문으로 승인한 뒤 `-design` 을
떼면 설치가 거부된다 — 옳은 거부지만 원인을 찾는 데 시간이 든다.

※ 위 두 값은 `_compile_model_contract()` 를 실제로 돌려 얻었다. 컴파일 통과는 근거 없는
제약 · 중복 제약 · 미등록 관계 참조 · 계산식 없는 정량 관계가 **없다**는 뜻이다.

---

## 6. 롤백·폐지 조건

### 6.1 승인 철회 · 관계 폐지

`ONTOLOGY_APPROVAL_REVOKED` 를 원 승인에 `parent_event_id` 로 잇는다. 원장은 부모와
같은 `subject_type`·`subject_id` 인지 확인하며, 다른 대상을 적은 철회는 **기록 자체가
거부된다.** 개별 관계는 `retire()` 로 폐지하되 삭제되지 않고 **유효기간이 닫힌다** —
과거 `as_of` 질의는 그때의 답을 그대로 낸다.

### 6.2 G7-2 Lite — **Demo 설치의 필수 조건** (Supervisor 결정)

범용 마이그레이션 롤백은 3주 시연의 선행 조건으로 두지 않는다. 대신 여섯을
**설치 전에** 갖춘다.

| # | 조건 | 뜻 |
|---|---|---|
| 1 | 격리된 Demo Ontology DB | 운영 파일과 물리적으로 다른 경로 |
| 2 | 설치 전 사본·지문 보관 | 되돌릴 대상이 실재해야 한다 |
| 3 | **복원 절차를 사본에서 1회 실증** | ⚠️ 「만들었는데 도는 것을 본 적이 없다」를 막는 항목 |
| 4 | 파괴적 마이그레이션 금지 | 열 삭제·형 변경 없이 추가만 |
| 5 | 승인 철회·관계 폐지 가능 | §6.1 — 이미 있음 |
| 6 | 운영 DB 설치는 별도 승인 전 금지 | 기본값이 거부 |

★ 3번이 핵심이다. 나머지 다섯이 갖춰져도 복원을 한 번도 안 해 봤다면 그것은 계획이지
안전장치가 아니다.

⚠️ 운영·현장 설치 전에는 **정식 G7-2 가 필수**다. Lite 는 Demo 한정이다.

---

## 7. 실행 순서 (승인된 순서)

| # | 단계 | 상태 |
|---|---|:---:|
| 0 | **계약 토폴로지 정정 · 대표 질문 종단 시뮬레이션** | 진행 중 (이 문서 §2) |
| 1 | Dataset 범위 색인 상세 설계 | ✗ |
| 2 | Dataset Resolver 구현 | ✗ |
| 3 | 최소 4관계 후보 생성 · 승인 · `as_of` 질의 | ✗ |
| 4 | G4 계산 결과 연결 | ✗ |
| 5 | G5 결정 패키지 연결 | ✗ |
| 6 | 화면을 고정 `ontology_path` → 런타임으로 전환 | ✗ |
| 7 | 외부지표 · MDM 관계 확장 | ✗ |

★ 0번의 «종단 시뮬레이션» 은 코드가 아니라 **종이 위에서** 한다 — 대표 질문 하나가
4관계를 지나 G4 계산과 G5 결정까지 닿는지 먼저 확인하고, 닿지 않으면 계약을 고친다.

---

## 8. 합성 데이터 표시 규칙

· 관계의 두 끝점이 시연 판에서 왔으면 그 관계로 만든 **경로·계보에 성격 표시**가
  붙는다. `decision_package` 가 브리핑 첫 줄에 `[시연용 합성 데이터]` 를 다는 것과 같다.
· ⚠️ 실제 판과 시연 판을 **한 경로에 섞지 않는다** — `baseline_build` 가 이미 그렇게 한다.
· 관계 저장에 어떻게 넣을지는 미정: 끝점의 판 성격에서 **파생**할 것인지, 관계 자체에
  적을 것인지. ★ 파생이 낫다 — 관계에 따로 적으면 끝점과 어긋날 수 있고, 어긋나면
  어느 쪽이 사실인지 알 수 없다.

---

## 9. 요약

```
계약 자체                 ██████████  컴파일·구조 검증 통과 · 지문 확정
최소 경로 확정             ██████████  4관계 · dataset 전용 (§2.2)
Dataset 색인 설계          ███░░░░░░░  방침 확정, 상세 3건 미정 (§4.3)
Demo 설치 안전(G7-2 Lite)  ██░░░░░░░░  6항목 중 철회·폐지만 있음
Resolver (최소 경로)       ░░░░░░░░░░  0 / 1  (dataset 미배선)
실제 런타임 종단           ░░░░░░░░░░
```

**지금 설치하면**: 계약은 들어가지만 §2.2 의 4관계를 **하나도 세울 수 없다** —
`dataset` Resolver 가 없기 때문이다. 「정식 온톨로지가 설치됐다」는 기록만 남고 화면은
여전히 고정 `ontology_path` 를 보여 준다.

**다음 할 일**: §7-0(대표 질문 종단 시뮬레이션) → §4.3 의 판단 3건 → Dataset Resolver.
