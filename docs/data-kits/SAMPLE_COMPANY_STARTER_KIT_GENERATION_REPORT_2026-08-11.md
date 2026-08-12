# 샘플 회사 Starter Kit 생성 결과 보고서

> 작성일: 2026-08-11  
> 대상: `KIT-MFG-NONFERROUS-PROCUREMENT` v1.0.0  
> 회사: `AFS 데모소재그룹` — 명시적 가상기업  
> 판정: `VALIDATED_FOR_DEMO`  

## 1. 이번 작업에서 실제로 만든 것

- 데이터 계약 35개
- 회사 Profile 6개 — 기준회사 1개 + 추가 가상회사 5개
- Quick Profile 6개월 데이터 13,585건
- Full Profile 36개월 데이터 155,508건
- 등록 단계 QUARANTINE 후보 8종·50건
- 시나리오 10개
- 생성 앱 연결 Blueprint 5개
- 보고서 정의 5개
- 결정 이력 예시 3건
- 사용자 교체용 Excel 35개와 온보딩 인덱스 1개
- 데이터 생성기·검증기와 Excel 생성·재계산·검증 도구

모든 값은 `data_class=SYNTHETIC`, `data_origin=SYNTHETIC`으로 고정했다. 실적 형태의 행은 `business_data_kind=ACTUAL`일 수 있지만 이는 업무상 의미일 뿐 실제 회사에서 발생한 값이라는 뜻이 아니다. 합성값은 실제값으로 승격할 수 없다.

## 2. Full Profile 데이터량

| ID | 건수 | ID | 건수 |
|---|---:|---|---:|
| FND-01 | 15 | FND-02 | 24 |
| FND-03 | 1,101 | MDM-01 | 220 |
| MDM-02 | 40 | MDM-03 | 24 |
| MDM-04 | 8 | MDM-05 | 34 |
| MDM-06 | 48 | MDM-07 | 80 |
| MDM-08 | 43 | PRC-01 | 100 |
| PRC-02 | 1,800 | LOG-01 | 1,800 |
| LOG-02 | 1,200 | LOG-03 | 7,200 |
| LOG-04 | 1,200 | LOG-05 | 2,400 |
| INV-01 | 55,440 | INV-02 | 30,000 |
| MFG-01 | 6,000 | MFG-02 | 8,000 |
| MFG-03 | 576 | QLT-01 | 12,000 |
| SLS-01 | 2,500 | FIN-01 | 4,320 |
| FIN-02 | 3,700 | FIN-03 | 15,000 |
| EXT-01 | 180 | EXT-02 | 240 |
| EXT-03 | 180 | KNW-01 | 10 |
| SIM-01 | 12 | SIM-02 | 10 |
| DEC-01 | 3 | 합계 | 155,508 |

## 3. 검증 증거

### 3.1 데이터

- 계약·공통 필드·합성 표기·고유키·범위: 통과
- 조직 부모·순환: 통과
- BOM·품목·고객·공급사·위치 참조: 통과
- 계약량 대 발주량: 통과
- 발주·선적·통관·운송 사건 순서: 통과
- 생산 수율: 통과
- 재고 이동 대 월말 Snapshot: 통과
- 총계정원장 차변·대변: 통과
- AP/AR 원천 참조: 통과
- QUARANTINE 예상 사유·건수: 통과
- 가상회사 Profile ID·원본·목적·조직·가정·합성 격리: 통과
- 최종 결과: **405/405 PASS**

검증 보고서: `starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0/validations/validation_report.json`

### 3.2 재현성

동일 Seed `20260811`로 전체 데이터를 다시 생성한 뒤 Quick·Full·QUARANTINE CSV 71개의 SHA-256을 비교했다.

- 비교 파일: 71개
- 불일치: 0개
- 판정: **REPRODUCIBLE**

### 3.3 Excel

- 데이터셋 Workbook: 35개
- 공통 시트: `INSTRUCTIONS`, `DATA`, `DATA_DICTIONARY`, `CODE_MAP`, `VALIDATION`, `CHECKS`
- LibreOffice 실제 재계산: 35개 완료
- 검증 수식: 175개
- 수식 오류·빈 캐시: 0개
- 종합 판정: **35/35 PASS**

검증 보고서: `starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0/validations/excel_validation_report.json`

## 4. 파일 무결성

- manifest 등록 파일: 149개
- 누락: 0개
- SHA-256 불일치: 0개
- 전체 산출물: 175개, 약 41.7MB
- Excel: 36개 — 데이터셋 35개 + 인덱스 1개
- CSV: 71개 — Quick 35개 + Full 35개 + QUARANTINE 후보 1개

## 5. 재현 명령

```powershell
venv\Scripts\python.exe scripts\generate_sample_company_starter_kit.py
venv\Scripts\python.exe scripts\validate_sample_company_starter_kit.py
venv\Scripts\python.exe scripts\generate_sample_company_excel_templates.py
powershell -ExecutionPolicy Bypass -File scripts\recalculate_sample_company_excel_templates.ps1
venv\Scripts\python.exe scripts\validate_sample_company_excel_templates.py
```

순서를 바꾸면 안 된다. 데이터 검증이 `VALIDATED_FOR_DEMO`를 발급한 뒤에만 Excel 생성기가 동작한다.

## 6. 현재 완료와 미완료의 경계

이번 작업으로 **데이터 키트 생성·계약·파일 품질·온보딩 Excel 준비**는 완료했다. 다음 항목은 아직 제품 런타임에서 검증하지 않았으므로 완료로 표현하지 않는다.

1. Loader를 통한 실제 통합DB 등록
2. 데이터 카탈로그·계보·품질 결과 자동 생성
3. 조직 Scope별 조회 격리와 Fail-closed API 검증
4. APP-01~05가 계약된 데이터만 소비하는지 검증
5. Twin 계산 엔진의 Snapshot·산식 버전 연결
6. 보고서 5종의 계산값·근거 ID 자동 반영
7. 샘플 회사 선택 → Quick 체험 → 회사 복사 → 데이터셋 교체 UI
8. 실제 공식 외부지표 수집·승인·시점관리

### 6.1 현재 Enterprise Context에 추가 등록한 가상회사

다음 5개는 파일 Fixture에만 존재하는 것이 아니라 현재 `enterprise_context.db`에도 안전한 복제
경로로 등록했다. 모두 `DRAFT VIRTUAL`, 시나리오 상태 `ACTIVE`, 만료일 `2032-12-31`이다.

- AFS 배터리소재 제3공장 증설안
- AFS 순환금속 리사이클링 신사업안
- AFS 글로벌 제련법인 진출안
- AFS 스마트 전력기기 신규법인안
- AFS 북미 해저케이블 생산법인안

등록 스크립트는 회사명 기준 멱등이며 두 번째 실행에서 5개 모두 `skipped`로 확인했다. 기존 시험용
가상회사와 REAL 조직은 삭제하거나 변경하지 않았다.

특히 `EXT-01~03`은 공식 데이터와 같은 구조와 변동 패턴을 가진 합성 Fixture다. 공식 기관이 발표한 실제 관측값이 아니므로 실제 경영 판단이나 예측 정확도 증명에 사용할 수 없다.

## 7. 다음 착수 순서

1. Quick Profile dry-run Loader
2. FND·MDM 등록과 조직 Scope 검증
3. 구매–물류–재고 최소 연결
4. APP-01 원료 도입계획·추적 화면에 Quick Fixture 연결
5. SIM-01 기준선과 Golden Case 대사
6. 샘플 회사 Quick 체험 카나리
7. Full Profile 적재·성능 측정
8. 공식 외부지표 Reference Fixture 교체

첫 제품 관문은 “파일 생성 성공”이 아니라 **사용자가 샘플 회사를 선택하고 APP-01에서 발주–선적–입고–재고–현금 영향을 따라가며, 같은 기준선에서 시나리오와 결정 검토서를 재현하는 것**이다.
