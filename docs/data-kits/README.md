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
