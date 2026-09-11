# 제품 전체 진척 재산정 — 2026-09-11

- 작성: Codex / 기준 시각 **2026-09-11T16:16:44+09:00** / 코드 `3ddf4be4ac4e78f6723d3c83ebd941287a70802c`.
- 사용자 지시: 과거 관리평가를 반복하지 말고 지금 전체 진척을 실제로 재산정할 것.
- 작업 위치: 권고 착수 4~6 및 11~14를 포함한 전체 영역 감사. G0~G9의 구현/연결/수용 증거를 대조했으며, 새 기능이나 관문 완료를 선언하는 작업은 아니다. 전략 §11의 첫 폐루프 병목을 식별하는 작업이고 사용자도 명시적으로 지시했다.
- 정본은 [PROGRESS.md](C:/WorkSpace/gemini_agent_team_verG/PROGRESS.md)다. 이 문서는 근거이며 별도 진척 정본이 아니다.

## 결론

**현재 전체 단계 진척 50%(20/40), 로컬 우선 범위 61%(17/28)**.

완료 20 · 진행/부분 8 · 검증 미완료 6 · 미착수/대기 6. 전 영역의 실사용 검증을 마친 것은 아니다. 기능 수, 작업 시간, 제품 안정성 확률, 상용 출시 준비율을 50%라고 주장하지 않는다.

## 기준과 산식

기존 10영역×설계/구현/연결 검증/실사용 검증의 **40칸 분모를 유지**하되 모든 영역을 최신 근거로 다시 판정했다. 오래된 점수를 자동 승계하지 않았고, 새 구현 수나 테스트 수를 분자에 더하지 않았다. 4단계는 순차 누적이며 완료 셀만 1점, 그 외는 0점이다. 부분점 0.5점은 쓰지 않는다.

- 설계: 영역의 책임·범위·출구 기준이 상위 문서에 명시됨.
- 구현: 핵심 제품 경로가 구현되고 검증 근거가 있음. 보조 모듈만 있으면 부분.
- 연결 검증: 표에 명시한 **대표 제품 경로**의 생산자→소비자·권한·상태 연결 근거가 있음. 현재 핵심 소비자 계약이 깨진 경우 재개방. 대표 경로 통과를 모든 업무·모든 원천·전사 연결 완료로 확대하지 않는다.
- 실사용 검증: 영역의 사용자·반복 업무·오류·권한·실데이터 수용 조건까지 검증됨.
- 진행/부분은 부분 구현 또는 미완 연결이 있다는 뜻이지 모든 영역을 지금 동시에 실행 중이라는 뜻은 아니다. 미착수/대기는 해당 **후속 수용 단계**가 로드맵상 대기이고 착수 증거를 확인하지 못한 상태다. 코드가 전혀 없다는 뜻이 아니다.

| 영역 | 설계 | 구현 | 연결 검증 | 실사용 검증 | 점수 |
|---|---|---|---|---|---:|
| 기본 기능·UI | 완료 | 완료 | 완료 | 검증 미완료 | **3/4** |
| 업무키트 | 완료 | 완료 | 진행·부분 | 검증 미완료 | **2/4** |
| 현업 데이터 입력·등록 | 완료 | 완료 | 진행·부분 | 검증 미완료 | **2/4** |
| 초기 데이터 준비 | 완료 | 완료 | 진행·부분 | 검증 미완료 | **2/4** |
| 외부 공개자료 수집·갱신 | 완료 | 완료 | 완료 | 진행·부분 | **3/4** |
| 부서·전사 시뮬레이션 | 완료 | 완료 | 완료 | 검증 미완료 | **3/4** |
| AI·의사결정·보고·실행 | 완료 | 완료 | 진행·부분 | 검증 미완료 | **2/4** |
| PostgreSQL·서버 | 완료 | 진행·부분 | 미착수·대기 | 미착수·대기 | **1/4** |
| 파일럿·효과 측정 | 완료 | 진행·부분 | 미착수·대기 | 미착수·대기 | **1/4** |
| 그룹 확산 | 완료 | 진행·부분 | 미착수·대기 | 미착수·대기 | **1/4** |

전체: **3+2+2+2+3+3+2+1+1+1=20; 20/40=50%**. 로컬: **3+2+2+2+3+3+2=17; 17/28=60.714…%, 반올림 61%**.

## 왜 이전과 달라졌는가

이전 18/40에서 **초기 데이터 준비 +1 · 외부 공개자료 +1 · 시뮬레이션 +1 · 의사결정 연결 재개방 −1 = 20/40**이다. 45%→50%는 순증 5%p다. 이전 로컬 16/28은 원표 합산 오류였고, 정확한 이전값 15/28에서 현재 17/28로 바뀐다.

### D01. 기본 기능·UI — 3/4 → 3/4 (G1/G3/G7)

목록·권한·공통 조회 및 페이지 이동의 연결 증적과 현행 코드가 있다. 최신 전체 브라우저 수용 검증은 미완료다.

근거: [KitAppPanel.tsx](C:/WorkSpace/gemini_agent_team_verG/frontend/src/components/KitAppPanel.tsx), [RELEASE_CATALOG_CLEANUP_2026-09-08.md](C:/WorkSpace/gemini_agent_team_verG/docs/handoff/RELEASE_CATALOG_CLEANUP_2026-09-08.md).

다음 출구: 일반 사용자 진입·페이지 이동·오류·롤백 화면 수용 검증.

### D02. 업무키트 — 2/4 → 2/4 (G2/G3)

7앱 구현과 2앱 사전 점검은 있으나 목표 부서 자료의 인증·권한·앱 연결이 닫히지 않았다. 8종 RAW 확보를 앱 완료로 세지 않는다.

근거: [KitAppPanel.tsx](C:/WorkSpace/gemini_agent_team_verG/frontend/src/components/KitAppPanel.tsx), [K1_C5_EXISTING_DEPARTMENT_ALIGNMENT_2026-09-10.md](C:/WorkSpace/gemini_agent_team_verG/docs/handoff/K1_C5_EXISTING_DEPARTMENT_ALIGNMENT_2026-09-10.md).

다음 출구: 선행 5종 정렬 후 대상 앱 데이터·권한 연결 및 7앱 수용 검사.

### D03. 현업 데이터 입력·등록 — 2/4 → 2/4 (G2-D/G3)

업로드·원천 결속·검사 API와 UI가 존재한다. 회사 실적 인증 정책 계층은 새로 구현됐지만 OWNER_CERTIFIED 종점과 정책 화면은 아직 없다.

근거: [data_preparation_control.py](C:/WorkSpace/gemini_agent_team_verG/api/routes/data_preparation_control.py), [DataPrepPanel.tsx](C:/WorkSpace/gemini_agent_team_verG/frontend/src/components/DataPrepPanel.tsx), [actual_certification_policy.py](C:/WorkSpace/gemini_agent_team_verG/core/actual_certification_policy.py), [admin_control.py](C:/WorkSpace/gemini_agent_team_verG/api/routes/admin_control.py), [PROPOSAL_ACTUAL_CERTIFICATION_2026-09-11.md](C:/WorkSpace/gemini_agent_team_verG/docs/handoff/PROPOSAL_ACTUAL_CERTIFICATION_2026-09-11.md).

다음 출구: 기존 소유권 계층을 재사용한 실적 인증 종점·귀속 기간·정책 화면 및 일반 사용자 입력 검증.

### D04. 초기 데이터 준비 — 1/4 → 2/4 (G2-D)

현행 제품 저장소를 사용해 6종·13,900행을 격리 RAW에 적재하고 전수 대사했으므로 설계만이 아닌 구현 완료로 재판정한다. 선행 5종·가격 보류 강제·소유권/인증이 남아 연결 완료는 아니다.

근거: [snapshot_service.py](C:/WorkSpace/gemini_agent_team_verG/core/data_preparation/snapshot_service.py), [store.py](C:/WorkSpace/gemini_agent_team_verG/core/data_preparation/store.py), [K1_C5_EXISTING_DEPARTMENT_ALIGNMENT_2026-09-10.md](C:/WorkSpace/gemini_agent_team_verG/docs/handoff/K1_C5_EXISTING_DEPARTMENT_ALIGNMENT_2026-09-10.md), [batch-result.json](C:/WorkSpace/gemini_agent_team_verG/output/kit-logistics-review-2026-09-10/factory-rehearsal-7h8jvgww/logistics-raw-batch-eweopj4t/batch-result.json), [verification-notes.json](C:/WorkSpace/gemini_agent_team_verG/output/kit-logistics-review-2026-09-10/factory-rehearsal-7h8jvgww/logistics-raw-batch-eweopj4t/verification-notes.json).

다음 출구: FND-01/03·MDM-04/08·EXT-02를 한 묶음으로 정렬; 기존 판/원문 보존.

### D05. 외부 공개자료 수집·갱신 — 2/4 → 3/4 (G2-D/G4)

World Bank 240행의 수집·승격·동인 연결 및 SOURCE_CERTIFIED 판의 실제 실행 기록을 현행 구현과 대조했다. 대표 공개 원천의 제품 서비스 연결은 완료이며 다원천 반복 갱신·운영 화면 사용 검증은 미완이다.

근거: [SESSION_2026-09-11_WORLDBANK_LIVE_RUN.md](C:/WorkSpace/gemini_agent_team_verG/docs/handoff/SESSION_2026-09-11_WORLDBANK_LIVE_RUN.md), [F8_REAL_WALK.md](C:/WorkSpace/gemini_agent_team_verG/docs/test_plan/F8_REAL_WALK.md), [snapshot_export.py](C:/WorkSpace/gemini_agent_team_verG/core/external_intelligence/snapshot_export.py), [models.py](C:/WorkSpace/gemini_agent_team_verG/core/data_preparation/models.py), [test_snapshot_export.py](C:/WorkSpace/gemini_agent_team_verG/tests/test_snapshot_export.py).

다음 출구: 원천·데이터 성격·인증자 표시와 반복 갱신/실패 복구 확인; 다른 Provider 실측은 별도.

### D06. 부서·전사 시뮬레이션 — 2/4 → 3/4 (G4)

공개 관측→승인 동인 판본→조직 기준선→시나리오 계산의 대표 경로가 기록되고 현행 코드와 일치한다. 이를 연결 단계로 인정하되 합성 기준선·가정의 업무 적합성과 실제 회사 실적 Replay/전사 검증까지 인정하지 않는다.

근거: [planning_drivers.py](C:/WorkSpace/gemini_agent_team_verG/core/planning_drivers.py), [planning_engine.py](C:/WorkSpace/gemini_agent_team_verG/core/planning_engine.py), [enterprise_financial_model.py](C:/WorkSpace/gemini_agent_team_verG/core/enterprise_financial_model.py), [05_northstar_verification_plan_2026-09-08.md](C:/WorkSpace/gemini_agent_team_verG/docs/test_plan/05_northstar_verification_plan_2026-09-08.md), [F8_REAL_WALK.md](C:/WorkSpace/gemini_agent_team_verG/docs/test_plan/F8_REAL_WALK.md).

다음 출구: 같은 회사·기간·업종의 인증 실적을 이용한 Replay/Backtest와 사용자 화면 검증.

### D07. AI·의사결정·보고·실행 — 3/4 → 2/4 (G3/G5/G6)

백엔드 결정·실행·효과 경로는 있으나 현재 CaseCreate의 필수 evidence_basis를 DecisionCenter와 decisionApi가 보내지 않는다. 현행 요청 모델을 분리 실행해 missing 오류를 재현했으므로 연결 단계를 재개방한다.

근거: [decision_control.py](C:/WorkSpace/gemini_agent_team_verG/api/routes/decision_control.py), [decision_case.py](C:/WorkSpace/gemini_agent_team_verG/core/decision_case.py), [decisionApi.ts](C:/WorkSpace/gemini_agent_team_verG/frontend/src/lib/decisionApi.ts), [DecisionCenter.tsx](C:/WorkSpace/gemini_agent_team_verG/frontend/src/features/collaboration/DecisionCenter.tsx), [F8_REAL_WALK.md](C:/WorkSpace/gemini_agent_team_verG/docs/test_plan/F8_REAL_WALK.md).

다음 출구: 근거 종류 선택·요청 계약을 연결하고 생성→승인→실행→발간을 재검증(이번 감사에서는 수정 안 함).

### D08. PostgreSQL·서버 — 1/4 → 1/4 (G7)

배포/DB 이관 설계, SQLite 사용처 목록과 선택적 PostgreSQL 체크포인터는 있다. 업무 DB 전체 접근계층·이관·동일 입력 대사·전환/복구 완료 증거는 없다. PostgreSQL 코드가 전혀 없다는 뜻은 아니다.

근거: [WEB_DEMO_DEPLOYMENT_EXECUTION_PLAN_2026-08-21.md](C:/WorkSpace/gemini_agent_team_verG/docs/roadmap/WEB_DEMO_DEPLOYMENT_EXECUTION_PLAN_2026-08-21.md), [sqlite_inventory.py](C:/WorkSpace/gemini_agent_team_verG/scripts/sqlite_inventory.py), [agent_graph.py](C:/WorkSpace/gemini_agent_team_verG/core/agent_graph.py), [store.py](C:/WorkSpace/gemini_agent_team_verG/core/data_preparation/store.py).

다음 출구: DB-0/1 경계 정리 후 사본 이식·대사·전환/복구; 운영 전환은 별도 승인.

### D09. 파일럿·효과 측정 — 1/4 → 1/4 (G8)

Shadow 비교·승격·비용 측정 도구는 구현돼 있다. 실제 현업 코호트/업무 주기의 Replay→Shadow→Controlled Live와 ROI 수용 증거는 확인되지 않는다. 탐침 22/22나 개발비 계측을 파일럿 완료로 세지 않는다.

근거: [shadow_mode.py](C:/WorkSpace/gemini_agent_team_verG/core/shadow_mode.py), [E_FINDINGS.md](C:/WorkSpace/gemini_agent_team_verG/docs/test_plan/E_FINDINGS.md), [AI_FACTORY_STUDIO_FINAL_COMPLETION_EXECUTION_PLAN_2026-08-03.md](C:/WorkSpace/gemini_agent_team_verG/docs/roadmap/AI_FACTORY_STUDIO_FINAL_COMPLETION_EXECUTION_PLAN_2026-08-03.md).

다음 출구: 승인된 한 업무·기간·사용자 범위에서 시간/오차/수정량/효과의 기준선과 실측.

### D10. 그룹 확산 — 1/4 → 1/4 (G9)

ECM 조직·가상 복제·Roll-up 구현은 있다. 두 번째 실제 법인에 코드 포크 없이 적용하고 통화·내부거래·지분·기간·권한까지 검증한 확산 패키지 완료 증거는 없다.

근거: [clone_service.py](C:/WorkSpace/gemini_agent_team_verG/core/enterprise_context/clone_service.py), [rollup.py](C:/WorkSpace/gemini_agent_team_verG/core/enterprise_context/rollup.py), [AI_FACTORY_STUDIO_FINAL_COMPLETION_EXECUTION_PLAN_2026-08-03.md](C:/WorkSpace/gemini_agent_team_verG/docs/roadmap/AI_FACTORY_STUDIO_FINAL_COMPLETION_EXECUTION_PLAN_2026-08-03.md).

다음 출구: 첫 파일럿 이후 두 번째 법인의 설정/확장팩 복제와 연결 집계·격리 검증.

## 이번에 직접 확인한 것과 인용한 것을 분리

- **이번 Codex 직접 확인:** 39개 현행 소스·설계·결과 파일 경로/지문 고정; 10영역 대조; 현재 API의 `CaseCreate` 클래스만 AST로 분리하여 Pydantic 검증. 현행 화면과 같은 네 필드(question/package/evidence/due_at)의 요청은 evidence_basis=missing 오류, 명시 JUDGMENT를 추가한 대조군은 통과했다. 실제 서버 요청·승인·DB 변경은 하지 않았다.
- **이번 RAW 증거 재확인:** 직전 성공 보고서의 내용 지문 재계산, 신규 12판·13,900행 및 핵심 RAW 8종 확인. DB를 다시 열지 않았다. 43개 과거 판/7개 RAW 보존의 독립 RO 대조와 순수 함수 154/154는 직전 RAW 턴의 실행 결과다.
- **다른 팀 기록과 소스 대조:** World Bank 수집·승격 240행, SOURCE_CERTIFIED 판 `ds_716f0fbc363a4b`, 이름 있는 인증과 준비도/동인 소비 경로. 공개 실자료는 이 관측값과 판이며 시뮬레이션 기준선/가정은 실적 전체가 아니다. 새 정책 169건·인증 관련 723건 통과도 타 팀 보고이며 이번 독립 실행 수에 합산하지 않는다.
- **북극성 계획 22/22:** F-0/F-8에는 막힌 위치·이유를 확인하면 통과하는 조사 조건이 있다. F8_REAL_WALK에는 흐름 7, 막힘·설명 1(전달 0건)이 남아 있다. 이 숫자로 앱 실사용·파일럿·전사 폐루프를 완료 처리하지 않는다.
- **회귀 한계:** 9월 10일 동결 T3는 6,735 passed / 5 skipped / 3 failed @3b9ab8520이다. 환경 원인 및 대조군 기록은 있으나 전부 통과한 실행은 아니다. 최신 HEAD 전체 T3는 재실행하지 않았다. 별도의 기존 공유 원장 감시 teardown 오류도 이번에 해소하지 않았다.
- **동시 작업 반영:** 재산정 중 추가된 `7fca26530` 실적 인증 정책까지 확인했다. 정책 계층이 완료됐다는 것과 OWNER_CERTIFIED 종점이 구현됐다는 것을 구분한다. 이후 새 커밋은 새 증거로 재평가해야 한다.

## 다음 작업과 보고 운영

1. **현재 연결 결함 — Codex:** 결정 생성의 필수 근거 종류 선택·요청 계약을 연결하고 생성→검토/승인 경로를 재검증한다. 이는 이번 재산정에서 발견한 다음 수정 항목이며 이번 턴에서는 구현하지 않았다.
2. **진행 중 자료 작업 — Codex:** FND-01/03·MDM-04/08·EXT-02 5종을 한 묶음으로 목표 문맥/참조 정렬. 기존 RAW·사본·역할·승인은 보존한다.
3. **실적 인증 — 기존 백엔드 담당 / UI 담당:** 기존 Data Owner 계층과 새 정책을 재사용해 OWNER_CERTIFIED·귀속 기간·대사 증거를 연결한다. 정책 화면은 필요한 서명을 병렬 목록으로 표시하고 표시 직책을 실제 승인 권한으로 쓰지 않는다. 전사 보고용 실적의 분류 기준은 기존 인계의 결정 조건을 따른다.
4. **수용 검증:** 같은 사용자/부서 문맥에서 데이터 성격·인증자·원천 책임 표시, 입력→준비도→앱→시나리오→결정까지 확인. 이후 동결 환경의 전체 회귀를 수행한다. 기존 실패를 숫자 합산으로 지우지 않는다.
5. **후속 제품화:** 첫 사용 흐름이 안정되면 PostgreSQL/복구·통제 파일럿을 진행하고, 두 번째 실제 법인 확산은 G8 검증 이후다. 코드가 일부 있다는 이유로 이 후속 단계를 완료 처리하지 않는다.

이후 보고의 첫 줄은 **현재 전체 50%(20/40) · 로컬 61%(17/28) · 해당 묶음 실측**으로 한다. 새 종료 증거가 있으면 완료 셀을 갱신하고, 새 결함이 있으면 연결 셀을 재개방한다. 변동이 없으면 무엇이 전진했고 어떤 출구가 남아 분자가 그대로인지 함께 말한다.

운영 DB·업무 데이터·승인·원장·제품 코드·앱 상태는 변경하지 않았다. 바뀐 것은 진척 정본과 감사·인계 기록뿐이며 스테이징·커밋·푸시는 하지 않았다.
