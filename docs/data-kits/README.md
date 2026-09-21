# AI Factory Studio Data Kit 문서 인덱스

## 현재 정본 문서 목록

### 1. 첫 번째 가상기업: AFS 데모소재그룹 (비철금속·동제련)
- [`SAMPLE_COMPANY_STARTER_KIT_MASTER_SPEC_2026-08-11.md`](SAMPLE_COMPANY_STARTER_KIT_MASTER_SPEC_2026-08-11.md)  
  샘플 회사 방식의 제품 목적, 가상기업 구조, 35개 데이터 패키지, 데이터 계약·분류·생성·시나리오·앱·보고서·완료 기준.
- [`SAMPLE_COMPANY_DATA_REGISTRATION_EXECUTION_PLAN_2026-08-11.md`](SAMPLE_COMPANY_DATA_REGISTRATION_EXECUTION_PLAN_2026-08-11.md)  
  35개 데이터셋별 필드·생성량·품질·대사·등록 대상·소비 기능·Wave·Sprint·테스트·즉시 착수 백로그.

### 2. 두 번째 가상기업: AFS 배터리케미컬 (양극재·전구체)
- [`SAMPLE_COMPANY_BATTERY_CHEMICAL_STARTER_KIT_SPEC_2026-08-11.md`](SAMPLE_COMPANY_BATTERY_CHEMICAL_STARTER_KIT_SPEC_2026-08-11.md)  
  이차전지 양극재·전구체 화학 제조 도메인의 가상기업 구조, 수율·에너지 인과 방정식, 35개 패키지 정본 규격.
- [`SAMPLE_COMPANY_BATTERY_CHEMICAL_EXECUTION_PLAN_2026-08-11.md`](SAMPLE_COMPANY_BATTERY_CHEMICAL_EXECUTION_PLAN_2026-08-11.md)  
  AFS 배터리케미컬 35개 데이터 패키지별 사양, Quick/Full 생성량, 대사(Reconciliation) 4대 기준 및 생성계획.

### 3. 확산 적용 사전 검토 (2026-09-16~17)

⚠️ **사전 검토다.** 「향후 기능 완성 후 타 산업군·타사로 확산할 때 무엇을 준비해야
하는가」를 대상화한 것이고, 운영 중인 시연·점검 작업과 분리해 진행했다.
브랜치 `claude/diffusion-readiness-20260916`.

| 문서 | 무엇을 답하나 |
|---|---|
| [`DIFFUSION_READINESS_ANALYSIS_2026-09-16.md`](DIFFUSION_READINESS_ANALYSIS_2026-09-16.md) | **어느 범위까지 적용 가능한가.** 업태별 데이터셋 커버리지 · 제공 경계(우리/현업) · 네 층 |
| [`TAXONOMY_TO_KIT_COVERAGE_2026-09-16.md`](TAXONOMY_TO_KIT_COVERAGE_2026-09-16.md) | **분류에서 키트로 넘어가는 연결고리.** 키트의 단위 · 선정 기준 · 생성 방법 |
| [`KIT_DIFFUSION_IN_PLATFORM_2026-09-17.md`](KIT_DIFFUSION_IN_PLATFORM_2026-09-17.md) | **플랫폼 안에서 키트를 어떻게 늘리나.** 등록 경로 둘 · 끊긴 곳 · 사업 단위로 내기 |
| [`KIT_SHELF_SPEC_2026-09-17.md`](KIT_SHELF_SPEC_2026-09-17.md) | **키트 선반 상세 설계.** 설계 결정 8 · 자료구조 · 영향 · 시험 · 순서 |
| [`FIELD_LAYER_DESIGN_2026-09-16.md`](FIELD_LAYER_DESIGN_2026-09-16.md) | 필드를 **어느 층에** 붙이나 (A 업태 · B 업종 · 업무 형태) |
| [`KIT_PLATFORM_BRIDGE_DESIGN_2026-09-16.md`](KIT_PLATFORM_BRIDGE_DESIGN_2026-09-16.md) | 키트가 준 것이 **플랫폼 동인 체계로** 가는 길 |
| [`KIT_PLATFORM_BRIDGE_SPEC_2026-09-16.md`](KIT_PLATFORM_BRIDGE_SPEC_2026-09-16.md) | 그 구현 명세 — 대응표 · 함수 · 시험 |
| [`WIRE_CABLE_SPECIALIZATION_DRAFT_2026-09-16.md`](WIRE_CABLE_SPECIALIZATION_DRAFT_2026-09-16.md) | 전선·케이블 3 단 특성화 초안 (⏸ 보류) |
| [`LSMNM_BATTERY_NEWBIZ_REVIEW_2026-09-16.md`](LSMNM_BATTERY_NEWBIZ_REVIEW_2026-09-16.md) | 실적이 없는 **신규 사업부**에 키트를 어떻게 주나 |
| [`../handoff/PLATFORM_REVIEW_ABSOLUTE_DRIVERS_2026-09-16.md`](../handoff/PLATFORM_REVIEW_ABSOLUTE_DRIVERS_2026-09-16.md) | 플랫폼 검토 건 — 동인이 **절대량**을 담지 못한다 |
| [`../handoff/DIFFUSION_SESSION_HANDOFF_2026-09-17.md`](../handoff/DIFFUSION_SESSION_HANDOFF_2026-09-17.md) | **인수인계** — 어디까지 왔고 다음에 무엇을 하나 · **조심할 것** |

#### 이 검토에서 실제로 바뀐 것

| | |
|---|---|
| ✅ **사업 정의 분리** (`a86a45295`) | `scripts/business_defs/` — **키트는 회사가 아니라 사업의 조합이다.** 제련·전지소재를 갈라 단독으로 뽑을 수 있다 |
| ✅ **봉인 결함 수리** (`a7a45b6cf`) | 1.1.0 이 확정 판본인데 **지킬 대장이 없었다** — 값을 바꿔도 검증 406 건이 통과했다. 봉인하고, 표식만 있고 대장이 없으면 실패하게 했다 |
| ✅ **1.2.0 — 산업의 의미** (`4d6f177ad`·`2e9d17124`·`793aabb18`) | 등급 · 부산물(만들고 판다) · 판매 단위 · 전체 공정 · 기초재고. 그리고 **사업 경계가 새던 곳 다섯**(재고 스냅샷 · 실사 조정 · BOM 원료 · 더미 배정 · `owner_of`)과 **재고 음수 1,082 행** |
| ✅ **깨져 있던 시험 셋** (`b86de04e1`) | 넓게 돌리자 나왔다 — **분리 때 둘, 이번에 내가 하나.** 좁은 범위만 돌려서 몰랐다 |
| ✅ **선반 카탈로그** (`scripts/kit_shelf.py`) | **무엇을 줄 수 있고 어디가 비었나** — 씨앗(사업 정의)과 선반(실제 산출물)을 대조한다. 손으로 쓴 표는 낡는다 |
| ✅ 분류 집계 도구 | `docs/business-taxonomy/engine/diffusion_report.py` — 업태별 규모·커버리지 |

#### ⏳ 남은 것

**구현 안 된 설계**

| | 무엇 | 어디에 |
|---|---|---|
| 1 | 필드 계층 (`FieldExtension`) — **스키마에 열을 더하는** 층 | `FIELD_LAYER_DESIGN` |
| 2 | 키트 → 플랫폼 이음매 | `KIT_PLATFORM_BRIDGE_SPEC` |
| 3 | `ORDER:PROJECT` 축 (수주형) | `FIELD_LAYER_DESIGN` 3.2 |

**설계가 없는 것**

| | 무엇 | 왜 |
|---|---|---|
| 4 | 사업 **단계**(램프업·인증) | 36 개월 수율이 평평해 신규 사업을 그리지 못한다. 사업이 아니라 **단계**의 문제라 회사 프로파일이 맡는다 |
| 5 | **`KIT-MFG-BATTERY-CHEMICAL-PROCUREMENT` 의 자리** | 같은 35 종을 **JSON 으로** 담은 별개 키트가 있다(`5939597ca`). 생성기·봉인·`lineage` 와 연결돼 있지 않아 **유지되는 것인지 버려진 것인지 알 수 없다.** 전지소재는 비철 키트 안에도 있어 중복이다 |
| 6 | **원장에 매출이 없다** | `FIN-03` 전표가 전부 `AP-PO-*`(매입)다. 판매·부산물이 손익으로 이어지지 않는다 — 1.1.0 부터 그랬고, 부산물만의 문제가 아니라 **재무가 거래와 연결돼 있지 않다.** 고치면 `FIN-01~03` 전체가 움직인다 |

**일부러 고치지 않은 것**

| | 무엇 | 왜 |
|---|---|---|
| 7 | 부서가 **마지막 사업**에 붙는다 | 부서 편제는 **회사의 경영방침**이지 산업 특성이 아니다 — 현업이 플랫폼에서 정할 자리다. 게다가 다른 세션이 부서를 기준으로 시연 환경을 심고 있다 |
| 8 | 완제품 상대가격이 실제와 반대 (`FG-NISO4` > `FG-CATHODE`) | 재무 데이터 전체가 딸려 움직인다 — **도메인 검토가 먼저다** |

**도메인 검토 대기** — 사람만 답할 수 있다

| | 무엇 |
|---|---|
| 9 | 제련 드라이버 5 개 (TC/RC · 회수율 · 품위 · 부산물 · 프리미엄) |
| 10 | 1.2.0 이 넣은 **등급·단가 값** (정광 품위 · 부산물 가격) — 등급 체계가 **있다**는 구조는 확실하지만 값은 회사·계약마다 다르다 |
| 11 | 램프업 수치 (18 개월 · 0.85→0.94 · 인증 12 개월) |
| 12 | 전선 드라이버 4 개 (전가율 · 가공비 · 수주잔고 · 생산능력) |

**플랫폼 쪽**

| | 무엇 |
|---|---|
| 13 | 동인이 절대량을 못 담는다 (검토 건 제출됨) |
| 14 | 진행기준(공정률) 매출 — 35 종에 프로젝트 개념이 없다 |

---

## 구현 및 실행 시작점

### 데이터 키트를 실제 회사 데이터에 결속하는 정본

- [`../architecture/BUSINESS_DATA_BINDING_RUNTIME_DETAILED_DESIGN_2026-08-15.md`](../architecture/BUSINESS_DATA_BINDING_RUNTIME_DETAILED_DESIGN_2026-08-15.md)  
  기존 시스템·승인 파일·AFS 보완 입력·외부지표·계산 결과를 하나의 키트 계약에 결속하고, 불변 Snapshot·품질·대사·인증·준비도·기준선으로 이어가는 구현 상세설계.
- [`../architecture/business_data_binding_contract_v1.schema.json`](../architecture/business_data_binding_contract_v1.schema.json)  
  Data Kit Dataset Contract와 Source Binding의 기계 판독 JSON Schema.
- [`../architecture/first_vertical_data_binding_profile_v1.example.json`](../architecture/first_vertical_data_binding_profile_v1.example.json)  
  구매주문·선적 Milestone·시나리오 입력을 각각 파일·기존 시스템·AFS Native에 결속한 첫 수직 폐루프 예시.

비협상 원칙은 **기존 권위 원천이 있으면 AFS에 같은 입력 화면을 만들지 않는 것**이다. 앱은 원천을 직접 호출하지 않고 Host Runtime 표면만 사용하며, 공식 계산은 승인된 Snapshot ID 집합을 고정한다.

```text
1. starter_kit_manifest.schema.json
2. 35개 Dataset ID·의존성 manifest
3. FND-01~03·MDM-01~08 계약
4. AFS 데모소재그룹 & AFS 배터리케미컬 조직 Profile
5. Quick Demo 기준정보
6. 구매계약→발주→선적→입고 시드 생성기
   - scripts/seed_comprehensive_test_data.py
   - scripts/seed_battery_chemical_starter_kit.py
7. 재고/원가 물량 대사기 (Material Balance Reconciliation)
8. APP-01 원료 도입계획 연결
```

---

## 상위 정본과의 관계

이 폴더는 제품 헌장·제품 전략·최종 완성 로드맵·`PROGRESS.md`의 하위 상세 설계다. 충돌 시 상위 정본을 우선한다. 로드맵 기준으로 G2-B 데이터 키트와 G2-D MVA 부트스트랩을 구체화한다.

## 비협상 원칙

- 제품 기본 가상기업은 `AFS 데모소재그룹` 및 `AFS 배터리케미컬` 2종이다.
- 합성 데이터는 어떤 경우에도 Actual로 표시하거나 승격하지 않는다.
- 샘플 회사는 즉시 체험한 뒤 회사별 실제 데이터로 데이터셋 단위 교체한다.
- 외부 참여자는 기존 협업 시스템을 사용하며 AI Factory Studio에 직접 접속하지 않는다.
- 실제값 확정 대기는 기능 구현을 막지 않지만, 데이터 오너 승인 없이는 `CERTIFIED ACTUAL`을 발급하지 않는다.
