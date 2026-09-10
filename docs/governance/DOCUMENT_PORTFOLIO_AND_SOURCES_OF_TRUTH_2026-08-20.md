# AI Factory Studio 문서 포트폴리오와 정본 체계

작성일: 2026-08-20  
목적: 외부 제안서, 내부 의사결정 자료, 프로젝트 관리 문서, 구현 증거가 서로 다른 숫자와
완성도를 말하지 않도록 문서의 역할·정본·파생 관계를 확정한다.

---

## 1. 결론

공식 사업제안서 하나로는 부족하다. 최소 문서 체계는 다음 다섯 층이어야 한다.

```text
제품 정본
  ↓
내부 경영·사업 의사결정
  ↓
프로젝트 통합관리
  ↓
구현·검증 증거
  ↓
외부 제안·소개·파일럿 계약
```

외부 문서는 내부 정본과 증거에서 파생한다. 외부 문서에서 새로운 기능·ROI·일정을 먼저
만들지 않는다.

---

## 2. 필수 문서 세트

### A. 제품 정본

| 문서 | 독자 | 역할 | 현재 정본·조치 |
|---|---|---|---|
| Product Bible | 전 팀 | 제품 정의, 사용자, 문제, 원칙, 용어, 비대상 | `docs/AI_FACTORY_STUDIO_PRODUCT_BIBLE.md` 유지·현행화 |
| 제품 전략 | 제품 책임자·경영진 | 차별점, 진입시장, 업무키트, 확장 논리 | `docs/strategy/AI_FACTORY_STUDIO_UNIQUE_PRODUCT_STRATEGY_2026-08-03.md` 현행화 |
| 최종 제품 로드맵 | 전 팀 | G1~G8 관문과 전체 제품 범위 | `docs/roadmap/AI_FACTORY_STUDIO_FINAL_COMPLETION_EXECUTION_PLAN_2026-08-03.md` 정본 유지, 상태 갱신 |
| 용어·메시지 정본 | 전 팀·문서 작성자 | 사용자 용어와 기술 용어의 이중 표기 | 기존 용어사전·시스템 용어집을 정본으로 연결 |

### B. 내부 경영·사업 의사결정

| 문서 | 독자 | 역할 | 현재 정본·조치 |
|---|---|---|---|
| 내부 사업승인안 | Sponsor·CEO·CFO·CIO | 왜 지금 투자하는가, 무엇을 승인할 것인가 | `business-model/internal-venture/01_executive_decision_request.html`을 내부 승인 정본 후보로 선정 |
| 내부 Business Case | Sponsor·CFO | 비용 구조, 편익 가설, 기준선, ROI 측정식 | 기존 심층 보고서의 과장 가능 수치를 걷어내고 별도 정본화 필요 |
| 운영모델·책임체계 | Sponsor·제품책임자·IT·Data Owner | 제품 오너십, 데이터 승인, 보안, 운영 인력, 예산 | **신규 필요** |
| 사업화 선택안 | Sponsor·사업개발 | 내부 확산, 외부 제품화, 경력 전환의 조건부 선택 | `commercialization_real_options_strategy.md`와 100일 로드맵을 연결 |

### C. 프로젝트 통합관리

| 문서 | 독자 | 역할 | 현재 정본·조치 |
|---|---|---|---|
| Program Charter | Sponsor·팀 | 목표, 범위, 성공 기준, 권한, 제약 | Product Bible과 3주 계획에서 추출해 **신규 1장 정본 필요** |
| Integrated Master Plan | 전 팀 | 전체 일정, 의존성, Critical Path, Gate | 최종 로드맵 + 3주 MVP 계획을 연결해 현행화 필요 |
| Integrated WBS | 구현팀 | 작업·담당·선행·완료조건 | `docs/wbs/system_implementation_wbs.html` + `.agents/TEAM_BOARD.md`; 역할을 분리해 유지 |
| RAID Log | Sponsor·PM·Tech Lead | Risk, Assumption, Issue, Decision | 사고·잔여사항이 흩어져 있어 **신규 정본 필요** |
| Release/Demo Readiness | PM·QA·시연자 | 시연 범위, 데이터, 계정, 스크립트, 복구, Go/No-Go | Gate Evidence 문서를 통합해 **신규 정본 필요** |
| 변경·형상관리 계획 | 전 팀 | 브랜치, 커밋, 통합, origin 보존, 롤백 | 병렬통합 계획을 현재 단독 개발 체계에 맞게 축약·현행화 |

### D. 구현·검증 증거

| 문서 | 독자 | 역할 | 현재 정본·조치 |
|---|---|---|---|
| 요구사항·Gate 추적표 | PM·QA·감사 | 요구→코드→시험→증거→잔여사항 | WBS·Gate Evidence를 연결한 색인 **신규 필요** |
| Architecture Decision Record | Tech Lead·감사 | 중요한 설계 선택과 기각안 | 상세 설계·인계서에서 핵심 결정을 ADR로 승격 필요 |
| Test & Evidence Register | QA·감사 | 회귀 수, 변이, 카나리, 불변식, 깨끗한 checkout | 기존 `docs/test_plan`과 handoff 증거를 통합 색인 |
| Data Provenance & Certification | Data Owner·감사 | 원천·Snapshot·대사·합성/실제·승인 | BDR·데이터 키트·온톨로지 승인 자료를 연결 |
| Incident & Recovery Register | 운영·감사 | 시험 오염, 원장 복구, 재발 방지 | 원장 사고 문서 등 기존 자료를 색인하고 종료 상태 표시 |

### E. 외부·현업 파생 문서

| 문서 | 독자 | 역할 | 현재 정본·조치 |
|---|---|---|---|
| 제품 브로셔 | 첫 접점 | 문제·핵심 가치·차별점 요약 | `docs/product-brochure/` 마지막에 개정 |
| 제품 및 기능소개서 | 고객 실무·경영진 | 제품 구조, 화면, 기능, 통제, 상태 | `docs/product-feature-guide-v2/`를 v3로 개정 |
| 공식 사업제안서 | 외부 고객·파트너 | 고객 문제, 파일럿, 범위, 비용, 책임, 효과 측정 | `docs/business-model/enterprise-business-proposal.html` 개정 |
| 파일럿 실행계획/SOW | 고객·수행조직 | 90일 산출물, 역할, 입력 데이터, 인수 기준, 제외 범위 | **신규 필요** |
| Security & Data FAQ | 고객 CIO·보안·법무 | 데이터 위치, LLM, 권한, 암호화, 감사, 삭제, 책임 | **신규 필요** |
| 업무키트 시작 가이드 | 현업 사용자·Data Owner | 맨땅이 아닌 등록·사용·승격 예시 | 기존 샘플 회사 키트 문서를 사용자용으로 압축 필요 |
| Demo Script | 시연자 | 회사 선택부터 브리핑·보고서까지 재현 | 3주 MVP 시연 흐름에서 **신규 정본 필요** |
| Case Study | 외부 고객 | 실제 효과와 교훈 | 실제 파일럿 전에는 만들지 않음 |

---

## 3. 정본과 파생 관계

```text
Product Bible ───────────────┐
제품 전략 ───────────────────┤
최종 제품 로드맵 ────────────┤
용어사전 ────────────────────┤
                             ↓
                   내부 사업승인안·Business Case
                             ↓
                 Program Charter·Master Plan·WBS
                             ↓
                  Gate Evidence·ADR·Data Provenance
                             ↓
      기능소개서 → 사업제안서 → 파일럿 SOW → 브로셔·Demo Script
```

외부 문서의 수치·화면·기능 상태는 증거층으로 되돌아갈 수 있어야 한다.

---

## 4. 기존 중복 문서 정리 원칙

`business-model/internal-venture/`에는 유사한 임원 보고서가 여러 판 존재한다. 지금 삭제하지
않고 다음 기준으로 정리한다.

1. `01_executive_decision_request.html` — 내부 승인 요청 정본 후보
2. `01_executive_decision_presentation_executive.html` — 임원 발표 파생본 후보
3. `01_executive_decision_presentation_detailed.html` — 읽기 자료 파생본 후보
4. cinematic/final/masterpiece 등은 내용 대조 후 `archive/` 후보

정본을 확정하기 전에는 서로 다른 수치와 약속을 가진 문서를 외부로 배포하지 않는다.

---

## 5. 지금 우선 만들어야 할 내부 문서

### 5.1 프로젝트 통합 현황판

한 문서에서 다음을 보여야 한다.

- G1~G8 전체 진척
- 3주 시연 MVP의 Critical Path
- 현재 작업·다음 작업·차단 사항
- 담당자와 커밋
- Gate별 완료 증거
- 운영 오염·보안·데이터 위험
- 시연 가능 범위와 미구현 범위

### 5.2 RAID Log

최소 열:

```text
ID · 종류(R/A/I/D) · 내용 · 영향 · 가능성 · 대응 · 책임자 · 기한 · 상태 · 근거
```

현재 즉시 등록할 항목에는 AIP 문서 50건, 키트 생성기 비멱등, Dataset Resolver 미완,
`CALC.*` 어댑터 미완, 실제 ROI 미측정, 오래된 제품 화면이 포함된다.

### 5.3 내부 Business Case

확정 수익을 쓰는 문서가 아니라 다음을 계산하는 문서다.

- 기준선: 보고·분석·시스템 개발·데이터 준비에 드는 현재 시간과 비용
- 투자: 개발, 연결, 운영, LLM, 보안, 데이터 오너 업무
- 편익: 리드타임, 중복 입력, 수작업, 재고·운전자본·품질손실의 변화
- 시나리오: 보수·기준·상향
- 중단 기준과 회수기간

### 5.4 파일럿 Charter/SOW

외부 사업제안서가 “왜”를 설명한다면 SOW는 “누가 무엇을 언제까지 어떤 입력으로 만들고
무엇을 통과하면 끝나는가”를 계약 수준으로 정의한다.

---

## 6. 개정 우선순위

```text
1 문서 포트폴리오·증거 통제              완료
2 프로젝트 통합 현황판 + RAID Log         최우선
3 제품 및 기능소개서 v3                  핵심 종단 안정 후
4 내부 사업승인안 + Business Case         기능 상태와 병행
5 공식 사업제안서 + 파일럿 SOW            내부 정본 확정 후
6 Security & Data FAQ                    외부 제안 전
7 100일 사업 실행 마스터플랜              Gate 재산정 후
8 브로셔·Demo Script                     마지막 압축·시연 단계
```

---

## 7. 문서 관리 규율

- 모든 정본은 문서 소유자, 버전, 기준일, 상태, 근거 커밋을 가진다.
- 파생 문서는 어느 정본에서 만들어졌는지 머리말에 적는다.
- 완료되지 않은 기능은 상태 배지 없이 서술하지 않는다.
- 실제 수치와 합성 예시는 시각적으로 구분한다.
- 문서의 기능 상태는 구현 Gate가 바뀔 때만 갱신한다.
- 배포본 PDF는 HTML/원본과 내용 지문·페이지 렌더를 대조한다.
- 이전 판은 삭제보다 archive를 우선하되, 배포 가능한 정본은 하나만 둔다.

