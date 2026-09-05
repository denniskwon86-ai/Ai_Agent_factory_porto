# LAXS 통합 기준선 인수인계 — 2026-09-05

## 1. 인계 목적과 기준점

여러 세션에서 누적된 미커밋 구현을 재현 가능한 통합 기준선으로 정리한다. «파일이 존재한다»와
«제품 경로로 검증됐다»를 구분하고, 다음 담당자가 다시 조사하지 않도록 범위·검증·미완료·제외 항목을 기록한다.

- 원 작업 브랜치: `integration/g2-vertical-loop-20260821`
- 분리 브랜치: `codex/baseline-consolidation-20260905`
- 분리 기준 HEAD: `258f6ab4f`
- 기준 원격 HEAD: `8d8cb124f`
- 시작 상태: 로컬 +1커밋, 추적 변경 98개 경로와 다수 미추적 소스·문서
- 원격 확인: `git fetch origin --prune` 뒤 신규 원격 커밋 없음
- 결정: 누적분이 크고 여러 기능이 섞여 있어 기존 통합 브랜치에 직접 푸시하지 않는다.

## 2. 포함 기능

### 2.1 부서 시뮬레이션 → 전사 시나리오 → 재무 영향

- `enterprise_work_scenario.py`: 구매·생산·판매 결과를 동일 기준선·시점·인증판으로 조합한다.
- `enterprise_financial_model.py`: 봉인된 결과와 MDM-07·EXT-01·PRC-02·SLS-01·FIN-01·FIN-02로
  매출·재료/가공 마진·현금회수 기간 이동을 결정론적으로 계산한다.
- 미지원 통화, 중복 기준행, 미봉인 데이터는 추정하지 않고 중단한다.
- `enterprise_scenario_decision.py`: 완료된 조합과 재무 결과를 재계산하지 않고 Decision Package/evidence로 투영한다.
- APP-06은 판매·납기·매출 영향, APP-07은 전사 시나리오·실적 통합을 선언한다.

### 2.2 프로젝트 데이터·템플릿 결속

- `project_data_context.py`가 프로젝트의 데이터 인스턴스와 인증판을 프로젝트 문맥에 결속한다.
- 생성·재개·실행 시 템플릿 내용 지문과 데이터 문맥을 유지한다.
- 제조 원가분석·mfg_sim 템플릿의 실제 데이터 근거 요구사항을 강화한다.
- 비용 수집, 직접원가 분석, 간접비 배부, 절감안, CFO 보고 스킬 자산을 추가한다.

### 2.3 온톨로지 namespace와 사람용 표시

- namespace별 준비 상태를 폐쇄형으로 표현한다.
- 내부 객체 ID 대신 인증판 원문에서 확인한 사람용 설명과 표시 지문을 만든다.
- 원본 불일치·행 중복·계약 불일치는 임시 이름으로 접지 않고 fail-closed 처리한다.
- Dataset Resolver의 시점·범위·판 결속을 유지하고 저장소 장애와 미존재를 구분한다.
- 경영 의미지도와 경로 계산 화면은 준비되지 않은 namespace를 «0건»으로 오인시키지 않는다.

### 2.4 업무키트와 합성 시연 데이터

- 비철 제조·구매 업무키트를 APP-06/07 포함 7개 업무 앱 구성으로 확장한다.
- MDM-07 회계 계정·원가센터 계약, quick/full 합성 자료와 Excel 양식을 갱신한다.
- 동일 테스트/시연 기준선을 재사용하도록 시드 경로를 보정한다.
- `seed_comprehensive_test_data.py`, `seed_demo_showcase.py`는 화면 검증용 합성자료 생성기이며
  운영 실적으로 승격하지 않는다.

### 2.5 제품 UI와 실행 동선

- 생성된 시뮬레이터·보고서·앱을 무한 나열하지 않고 `GeneratedProjectCatalog`의
  검색·상태 필터·목록/상세·사용실적 화면으로 관리한다.
- 데이터 준비, 준비도, 업무키트, 경영 의미지도, 경로 계산, 시나리오, 협업·의사결정 화면을
  같은 제품 셸과 상태 표현으로 연결한다.
- 프로젝트 작성 재진입, 템플릿 기반 에이전트 셋, 실행 흐름, 산출물 화면의 데이터 결속을 보강한다.
- LAXS 흰 배경/남색 배경/마크 브랜드 자산을 포함한다.

### 2.6 재무 보고서 열람·인쇄·PDF

- `ExecutiveReportView.tsx`가 Markdown을 제목·섹션·표·목록·핵심요약·글자 크기 조절이 가능한 보고서로 렌더링한다.
- 인쇄·PDF는 보고서만 독립 iframe으로 복제해 고정 Canvas의 첫 페이지만 인쇄되는 결함을 피한다.
- 주요 섹션은 새 페이지에서 시작하고 소제목·본문·표의 부자연스러운 페이지 절단을 줄인다.
- 사용자가 다중 페이지 인쇄와 문단 절단 보정 결과를 육안 확인했다.

### 2.7 에이전트 그래프·라우트·감사

- Reviewer가 반환할 수 있는 Supervisor 경로를 그래프 선언과 일치시킨다.
- 결정론 게이트의 재작업 상신 판단을 공통 사다리로 모아 반복 결함을 감지한다.
- 라우트 권한, 텔레메트리, 에이전트 레지스트리·자산 어댑터 변경과 회귀를 포함한다.

## 3. 문서·거버넌스

- TEAM_BOARD의 2026-08-18 이전 이력을 `.agents/archive`와 `docs/archive`에 보존한다.
- 온톨로지 설계·계약·승인 패키지 초안, 격리·키트 앱·통합 게이트 인수인계,
  구현 갭·웹 배포·시스템 생성 ID 이관 계획을 저장소에 보존한다.
- 개인 포트폴리오와 과거 브로셔/기능설명서 HTML은 현행 공식 정본이 아니라 이력·참고 산출물이다.
- 거절된 스킬 제안 18건은 pending 삭제와 rejected 추가를 함께 커밋한다.

## 4. 커밋하지 않는 환경 상태

| 경로 | 제외 이유 |
|---|---|
| `data/interaction_log.jsonl` | 실행 상호작용 로그이며 세션 정보가 섞일 수 있음 |
| `data/raw/` | 인증판 생성 원시 적재본 약 81MB, 재생성 가능 |
| `data/archive/`, `data_backup_*/`, `data/*.bak_*` | 마이그레이션·복구 전 DB 사본 |
| `.codex-tmp/` | 서버 로그·감사 임시본·화면 캡처 |
| `data/model_routing_policy.json` | 환경별 LLM 라우팅 상태 |

제외 계약은 `.gitignore`에 추가한다. 이미 추적 중인 `data/interaction_log.jsonl`은 삭제·원복하지 않고
미커밋 상태로 남긴다.

## 5. 검증 기록

| 검증 | 결과 |
|---|---|
| Python 신규/영향 회귀 | PASS · 종료코드 0 |
| 프런트 TypeScript + production build | PASS · 3,495 modules |
| 전체 pytest T3 | PASS · 5,793 passed · 2 skipped · 실패 0 |
| 스테이징 비밀정보·DB/로그 감사 | 실행 예정 |
| 원격 ahead/behind 및 push 후 SHA 대조 | 실행 예정 |

## 6. 완료로 주장하지 않는 것

- OpenDART·ECOS·KOSIS·관세청 외부 데이터 수집 오케스트레이터는 아직 구현하지 않았다.
- 공개 재무자료는 내부 상세 매입·고객·BOM 실적이 아니다. 합성 상세는 `SYNTHETIC_DERIVED`로
  표시하고 공개 총계와 대사해야 한다.
- 임의 URL 크롤링, LLM 생성 SQL 실행, 생성 커넥터 즉시 운영 등록, 운영 DB 직접 적재는 금지한다.
- Naver Cloud 배포, TLS/도메인, PostgreSQL 전환, 최대 10명 파일럿, 정량 ROI 실측은 후속 단계다.
- 보고서 출력은 확인했지만 외부 수집부터 업무키트·전사 시나리오·안건 발간까지의 최신 전체
  단일 브라우저 여정은 다시 수행해야 한다.

## 7. 다음 재개 순서

1. 이번 기준선의 전체 T3와 원격 SHA를 확인한다.
2. 자연어 요청 기반 통제된 데이터 수집·정리 오케스트레이터를 별도 묶음으로 구현한다.
3. 첫 공급자는 OpenDART로 제한해 2016~2025 LS MnM 연결 재무제표를 preview → staging →
   품질검사 → 불변 스냅숏까지 통과시킨다.
4. ECOS 환율·금리, KOSIS, 관세청 무역자료, World Bank 원자재 가격을 승인 공급자 계약으로 확장한다.
   사용권한 없는 LME 직접 수집은 금지한다.
5. 공개 총계와 대사되는 SYNTHETIC_DERIVED 상세자료로 구매·재고/생산·판매·재무 업무키트를 강화한다.
6. 로컬 브라우저에서 데이터 요청 → 계획 검토 → 수집 → 인증판 → 업무키트 → 부서 시뮬레이션 →
   전사 조합 → AI 경영비서 설명 → 의사결정 안건·실행계획의 전 여정을 검증한다.

## 8. 다음 담당자가 먼저 확인할 파일

- `docs/handoff/LAXS_INTEGRATION_BASELINE_HANDOFF_2026-09-05.md`
- `docs/handoff/LAXS_UI_APP_FACTORY_HANDOFF_2026-08-26.md`
- `docs/roadmap/FULL_MENU_UI_ONTOLOGY_EXTERNAL_AGENT_EXECUTION_PLAN_2026-08-27.md`
- `core/external_collector.py`, `core/external_intelligence.py`
- `core/enterprise_work_scenario.py`, `core/enterprise_financial_model.py`
- `core/project_data_context.py`
- `frontend/src/components/GeneratedProjectCatalog.tsx`
- `frontend/src/factory/ExecutiveReportView.tsx`

## 9. 교대 체크포인트

- 마지막 확인: 누적분을 소스/문서/환경 상태로 분류했고 원격 신규 변경이 없음을 확인했다.
- 변경 범위: §2~§3의 소스·테스트·문서·브랜드·업무키트 자산.
- 제외 범위: §4의 로그·원시자료·DB 사본·환경 정책. 파일은 삭제하지 않았다.
- 검증 증거: §5 최종 결과와 커밋 SHA로 갱신한다.
- 커밋/푸시: 작성 시점 미실행. 별도 기준선 브랜치로만 푸시한다.
- 첫 재개 행동: OpenDART 1개 공급자의 read-only preview 계약.
- 금지 범위: 운영 DB 직접 적재, 비밀키 커밋, 미승인 임의 URL 수집, 공개자료를 내부 ACTUAL로 표기,
  `origin/dev` 또는 기존 통합 브랜치 강제 갱신.
