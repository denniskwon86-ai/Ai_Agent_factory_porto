# AI Factory Studio 기술·제품 용어 재정의 대상 전체 목록

> 작성일: 2026-08-11  
> 목적: 제품 문서·UI·API·코드에서 사용하는 기술 요소의 명칭을 하나의 언어 체계로 재정의하기 위한 1차 Inventory  
> 범위: Product Bible, 독자 제품 전략, 최종 로드맵, LLM 구현 명세, UI 추적 문서, Starter Kit 규격, 현재 `core/`, `api/routes/`, `nodes/`, `frontend/src/`  

> **생성 산출물(최종 갱신 2026-08-13)**
> - Excel 전환 사전: `docs/architecture/AI_FACTORY_STUDIO_TECHNOLOGY_TERMINOLOGY_DICTIONARY_2026-08-12.xlsx`  
> - 시스템 임시 화면: 전역 메뉴 → 데이터 기반 → **기술·제품 용어집**  
> - 단일 데이터 원천: `data/terminology/technology_terminology_glossary.json`  
> - 재생성: `venv\Scripts\python.exe scripts\build_technology_terminology_dictionary.py`  

## 1. 이 문서의 판정 기호

| 기호 | 의미 |
|---|---|
| `PRODUCT` | 고객·사용자·경영진에게 노출할 제품 언어 후보 |
| `DOMAIN` | 제조·경영·데이터 업무 의미를 나타내는 도메인 언어 |
| `TECH` | API·코드·운영자 문서에서만 사용할 구현 언어 |
| `MIXED` | 제품 언어와 구현 언어가 섞여 재정의가 필요한 상태 |
| `PLANNED` | 기획은 있으나 제품 구현·노출 수준이 확정되지 않음 |
| `LEGACY` | 과거 문서·시안에서 사용했으며 폐기 또는 별칭 처리가 필요 |

---

## 2. 제품 정체성·최상위 구조

| ID | 현재 사용 용어 | 현재 성격 | 재정의 쟁점 |
|---|---|---|---|
| PROD-01 | AI Factory Studio | PRODUCT | 최종 제품명과 내부 프로젝트명을 분리할지 |
| PROD-02 | 경영 시스템 | PRODUCT | 업무 자동화 도구와 구분되는 최상위 정의 필요 |
| PROD-03 | 제조 경영 디지털트윈 | PRODUCT | Digital Twin·Management Twin과 통합 필요 |
| PROD-04 | Manufacturing Management Twin | MIXED | 대외 영문 제품 범주명 여부 |
| PROD-05 | Living Enterprise Canvas | LEGACY | UI 컨셉명인지 제품 기능명인지 불명확 |
| PROD-06 | Enterprise Canvas | MIXED | Enterprise Page·Cockpit과 충돌 |
| PROD-07 | Enterprise Cockpit | PRODUCT | 경영진 화면인지 전체 첫 화면인지 구분 필요 |
| PROD-08 | Private AI Cockpit | LEGACY | 초기 런처 명칭, 존치 여부 결정 |
| PROD-09 | Operational App Factory | PRODUCT | SW 생성기·App Factory와 통합 필요 |
| PROD-10 | Host-Governed Operational App Factory | MIXED | 전략 용어로는 정확하나 UI 용어로는 과도하게 기술적 |
| PROD-11 | SW 생성기 | PRODUCT | 생성 대상이 단순 SW인지 업무 앱인지 결정 |
| PROD-12 | App Factory | MIXED | 코드·전략·화면에서 범위가 다름 |
| PROD-13 | 앱인앱 / App-in-App | PRODUCT | 실행 구조인지 사용자 제품명인지 구분 필요 |
| PROD-14 | 생성 앱 / Generated App | PRODUCT | 운영 앱·업무 앱·하위 앱과 혼용 |
| PROD-15 | 운영 앱 / Operational App | PRODUCT | 생성 산출물의 정식 명칭 후보 |
| PROD-16 | Program | MIXED | 장기 업무 프로그램과 소프트웨어 프로그램 혼동 |
| PROD-17 | Project | PRODUCT | SW 생성 프로젝트와 경영 개선 과제 구분 필요 |
| PROD-18 | Mega Project | PRODUCT | 다중 프로젝트 묶음의 제품상 의미 재검토 |
| PROD-19 | Workspace | MIXED | 부서 작업영역·프로젝트 파일공간·권한 경계로 중복 사용 |
| PROD-20 | Vault | LEGACY | 독립 프로젝트 보관함·라이브러리와 혼용 |

## 3. 회사·조직·문맥·권한 범위

| ID | 현재 사용 용어 | 현재 성격 | 재정의 쟁점 |
|---|---|---|---|
| ORG-01 | Enterprise Group | DOMAIN | 지주사·기업집단과의 정확한 대응 |
| ORG-02 | Legal Entity | DOMAIN | 사업회사·법인과의 대응 |
| ORG-03 | Business Division | DOMAIN | 사업부·사업단위와의 대응 |
| ORG-04 | Plant / Site | DOMAIN | 공장과 사업장을 같은 계층으로 볼지 |
| ORG-05 | Department | DOMAIN | 조직부서와 기능조직 구분 |
| ORG-06 | Organization Node / Org Node | TECH | UI에서는 회사·사업부·공장 등 실제 유형으로 표현 |
| ORG-07 | Enterprise Context | MIXED | 회사 데이터·조직 범위·브랜드·업종 특성까지 포함 |
| ORG-08 | Company Context | MIXED | Enterprise Context와 경계 불명확 |
| ORG-09 | Active Context | TECH | 사용자가 현재 선택한 작업 문맥의 제품 용어 필요 |
| ORG-10 | Context Switcher | PRODUCT | 회사·사업부·공장 선택기의 정식 명칭 필요 |
| ORG-11 | Tenant | TECH | 고객사·기업집단과 반드시 분리해야 함 |
| ORG-12 | Scope | MIXED | 조직범위·데이터범위·권한범위가 한 단어에 섞임 |
| ORG-13 | Enterprise Scope | MIXED | scope_node_id·enterprise_scope_id 통합 필요 |
| ORG-14 | Scope Assignment | TECH | 사용자·자산·데이터 바인딩의 종류 분리 필요 |
| ORG-15 | Scope Contract | TECH | 데이터 계약과 권한 계약의 관계 정리 |
| ORG-16 | Scope Policy | TECH | 정책 결정점·권한 정책과 통합 필요 |
| ORG-17 | Scope Guard | TECH | UI 노출 금지, 구현 통제명으로 고정 가능 |
| ORG-18 | Organization Activation | TECH | 조직 생성·활성·운영개시 상태 구분 |
| ORG-19 | Rollup | DOMAIN | 조직 집계·연결재무·경영 집계와 구분 |
| ORG-20 | Virtual Company | PRODUCT | 가상회사·시나리오 회사·경쟁사 참조 모델 구분 |
| ORG-21 | Real Company | DOMAIN | 실제 운영회사라는 의미와 Actual 데이터 보유 여부 분리 |
| ORG-22 | Competitor Reference | DOMAIN | 경쟁사를 회사 계층에 넣을지 참조 객체로 둘지 |
| ORG-23 | Company Profile | DOMAIN | 업종·업태·브랜드·프로세스 Profile 분리 필요 |
| ORG-24 | Company Brand Profile | DOMAIN | CI·컬러·로고 설정의 정식 명칭 |
| ORG-25 | Clone / Company Clone | PRODUCT | 복사와 가상 파생회사 생성의 차이 |

## 4. 데이터 기반·MDM·카탈로그

| ID | 현재 사용 용어 | 현재 성격 | 재정의 쟁점 |
|---|---|---|---|
| DATA-01 | MDM | DOMAIN | 기준정보 관리 전체인지 마스터 레코드 관리만인지 |
| DATA-02 | Master Data / 마스터 데이터 | DOMAIN | 기준정보와 같은지 상위 개념인지 |
| DATA-03 | 기준정보 | DOMAIN | Master Data의 사용자용 한글 정식어 후보 |
| DATA-04 | Reference Data | DOMAIN | 기준정보·코드정보·외부 공식자료와 충돌 |
| DATA-05 | Reference Registry | MIXED | 승인 문서·외부지표·기준자료 등록부로 범위가 넓음 |
| DATA-06 | Source Registry | DOMAIN | 외부 데이터 원천 등록부로 한정 필요 |
| DATA-07 | Data Catalog | PRODUCT | MDM·Knowledge Hub·Reference Registry와 명확히 분리 |
| DATA-08 | Dataset | DOMAIN | 물리 파일·논리 테이블·데이터 제품 단위 혼용 |
| DATA-09 | Data Package | DOMAIN | Starter Kit 납품 단위와 Dataset의 관계 |
| DATA-10 | Data Product | PRODUCT | 향후 전사 공유 단위인지 기술 단위인지 |
| DATA-11 | Data Contract | DOMAIN | Schema·품질·권한·계보 계약의 포함 범위 |
| DATA-12 | Schema | TECH | 논리 스키마·물리 DB 스키마·JSON Schema 구분 |
| DATA-13 | Data Dictionary | DOMAIN | 필드 정의서와 Business Glossary의 차이 |
| DATA-14 | Business Glossary | PRODUCT | 업무용어사전·동의어사전과 통합 여부 |
| DATA-15 | Synonym / Alias | DOMAIN | 동의어·유사어·약어·코드 별칭 분리 |
| DATA-16 | Crosswalk | MIXED | 시스템 코드 매핑·조직 매핑·Schema 매핑 혼용 |
| DATA-17 | Mapping | DOMAIN | Crosswalk의 한글 사용자 용어 필요 |
| DATA-18 | Work Standard | PRODUCT | 업무표준·업무절차·SOP·규칙의 경계 |
| DATA-19 | Data Lineage | PRODUCT | 사용자는 데이터 계보, 기술자는 lineage_id 사용 |
| DATA-20 | Data Quality | PRODUCT | 규칙·검사 결과·점수·상태를 분리해야 함 |
| DATA-21 | Data Readiness | PRODUCT | 데이터 준비도·업무 준비도·앱 생성 준비도 구분 |
| DATA-22 | RAW | DOMAIN | 수집 원본과 미검증 입력의 정식 상태명 |
| DATA-23 | VALIDATED | DOMAIN | 형식 검증·업무 검증·대사 검증 범위 명확화 |
| DATA-24 | CERTIFIED | DOMAIN | 실제 의사결정 사용 가능의 승인 주체 필요 |
| DATA-25 | CERTIFIED_FOR_DEMO | DOMAIN | 합성 데이터 전용 인증 상태로 고정 |
| DATA-26 | QUARANTINE | DOMAIN | 격리·보류·반려의 차이 |
| DATA-27 | REJECTED | DOMAIN | 레코드 반려와 데이터셋 등록 실패 구분 |
| DATA-28 | ACTUAL | DOMAIN | 실제값 출처인지 업무적 실적 의미인지 혼동 주의 |
| DATA-29 | PLAN | DOMAIN | 확정계획·작업계획·목표 구분 |
| DATA-30 | FORECAST | DOMAIN | 전망·예측·추정과 통합 필요 |
| DATA-31 | SCENARIO | DOMAIN | What-if 입력과 계산 결과 객체 구분 |
| DATA-32 | SYNTHETIC | DOMAIN | 가상값·합성값·샘플값과 통합 필요 |
| DATA-33 | data_class | TECH | 출처 분류·업무 종류를 분리한 현재 규칙 유지 여부 |
| DATA-34 | business_data_kind | TECH | ACTUAL/PLAN/FORECAST/SCENARIO/REFERENCE 의미 |
| DATA-35 | data_origin | TECH | SOURCE/SYNTHETIC/DERIVED 등 계보 출발점 |
| DATA-36 | quality_status | TECH | 행 상태와 데이터셋 품질 판정 분리 필요 |
| DATA-37 | certification_status | TECH | 품질 상태와 승인 상태 분리 |
| DATA-38 | Snapshot | DOMAIN | 데이터 Snapshot·계산 Snapshot·화면 상태 혼용 |
| DATA-39 | Baseline | DOMAIN | 인증 기준선·시나리오 기준선·Git 기준선 혼용 |
| DATA-40 | Reconciliation / 대사 | DOMAIN | 물량·금액·원천·회계 대사의 공통 구조 필요 |
| DATA-41 | Starter Kit | PRODUCT | 샘플회사+계약+데이터+앱+보고서 패키지 정식 명칭 |
| DATA-42 | Quick Profile | PRODUCT | 체험용 데이터 프로필의 사용자 명칭 |
| DATA-43 | Full Profile | PRODUCT | 운영 유사 데이터 프로필의 사용자 명칭 |
| DATA-44 | Minimum Viable Actual | DOMAIN | 구현용 합성 데이터와 실제값 부트스트랩을 구분 |

## 5. 지식·근거·검색

| ID | 현재 사용 용어 | 현재 성격 | 재정의 쟁점 |
|---|---|---|---|
| KNOW-01 | Knowledge Hub | PRODUCT | 검색 화면·지식 저장소·RAG 원천의 범위 |
| KNOW-02 | Knowledge Base | TECH | Chroma 저장소와 제품 지식허브를 분리 |
| KNOW-03 | Knowledge Pack | PRODUCT | 문서 묶음·도메인 키트·Agent Pack과 충돌 |
| KNOW-04 | Reference Document | DOMAIN | 참고자료·근거자료·표준문서 구분 |
| KNOW-05 | Evidence | DOMAIN | 데이터 근거·문서 근거·검증 증거 구분 |
| KNOW-06 | Citation | DOMAIN | 출처 링크·문서 위치·계보 ID와 관계 |
| KNOW-07 | Grounding | TECH | 사용자에게는 근거 연결로 표현 필요 |
| KNOW-08 | RAG | TECH | 구현 방식이며 제품 기능명으로 사용하지 않음 |
| KNOW-09 | Graph RAG | PLANNED | 의미 그래프·관계 검색·영향 경로와 분리 설계 필요 |
| KNOW-10 | Semantic Search | PRODUCT | 자연어 검색·벡터 검색·그래프 검색 통합 UX |
| KNOW-11 | Context Engine | TECH | Prompt Context와 Enterprise Context 충돌 주의 |
| KNOW-12 | JIT Context | TECH | 필요한 파일·서명만 주입하는 구현 최적화 용어 |
| KNOW-13 | Context Report | TECH | 모델 주입 내역 설명 보고서인지 사용자 보고서인지 |
| KNOW-14 | Persona Learner | TECH | 회사 특성 학습·사용자 개인화와 구분 |
| KNOW-15 | Manufacturing Management Ontology / 제조 경영 온톨로지 | PLANNED | 경영 의미 모델의 기술 정식명; MDM·카탈로그·Graph RAG·계산 그래프와 책임 경계 고정 |
| KNOW-16 | 경영 의미 모델 | PRODUCT | 사용자·사업 설명용 표현과 기술 정식명 `제조 경영 온톨로지`의 병기 규칙 |

## 6. AI 에이전트·모델·워크플로우 구성

| ID | 현재 사용 용어 | 현재 성격 | 재정의 쟁점 |
|---|---|---|---|
| AI-01 | Agent | PRODUCT | 역할 에이전트·실행 노드·전역 비서 구분 |
| AI-02 | Agent Registry | MIXED | 에이전트 정의 저장소와 UI 마스터의 관계 |
| AI-03 | Agent Asset | PRODUCT | 에이전트·스킬·도구·모델 구성을 하나의 자산으로 보는 단위 |
| AI-04 | Agent Pack | PRODUCT | 산업·회사·업무별 추천 에이전트 묶음 |
| AI-05 | Agent Pack Binding | TECH | 회사 문맥과 Pack 연결 규칙 |
| AI-06 | Agent Master | PRODUCT | 생성·수정 화면인지 시스템 등록부인지 |
| AI-07 | Agent Governance | PRODUCT | 승인·버전·권한·성과관리 범위 |
| AI-08 | Role | DOMAIN | 사람 역할과 에이전트 역할 충돌 |
| AI-09 | Skill | PRODUCT | Prompt 문서·도구 능력·업무역량 혼용 |
| AI-10 | Skill Evolution | PRODUCT | 자가학습 표현보다 승인형 규칙 개선으로 정의 필요 |
| AI-11 | Skill Proposal | PRODUCT | 개선 제안·승인·반려 상태 정의 |
| AI-12 | Pipeline | TECH | Workflow·Graph와 관계 |
| AI-13 | Workflow | PRODUCT | 업무 흐름과 에이전트 실행 그래프 구분 |
| AI-14 | Workflow Template | PRODUCT | 산업·업무 템플릿과 Agent Pack 관계 |
| AI-15 | Graph | TECH | LangGraph 실행 그래프·Graph RAG·Traceability Graph 충돌 |
| AI-16 | Node | TECH | 사용자에게 에이전트 단계로 노출할지 |
| AI-17 | Universal Node | TECH | 비SW 템플릿 범용 실행기 |
| AI-18 | Debate | TECH | 초안–비판–수정 내부 품질 기법 |
| AI-19 | Critic | TECH | 사용자 노출 에이전트인지 내부 평가 역할인지 |
| AI-20 | Judge | TECH | 점수 판정기·승인권자와 혼동 방지 |
| AI-21 | LLM Gateway | TECH | Provider·Tier·Fallback의 단일 진입점 |
| AI-22 | Provider | TECH | 모델 공급자와 모델 자체 분리 |
| AI-23 | Model Tier | TECH | Pro·Flash 등 품질·비용 등급의 제품 명칭 필요 없음 |
| AI-24 | Model Routing | TECH | 작업 난이도·비용·품질 기반 선택 정책 |
| AI-25 | Fallback | TECH | 장애 대체와 품질 하향을 구분 |
| AI-26 | Cooldown | TECH | 공급자 실패 후 제외 상태 |
| AI-27 | Token Budget | TECH | 컨텍스트·출력·목표 예산 구분 |
| AI-28 | LLM Telemetry | TECH | 모델 호출·비용·지연·품질 측정 |
| AI-29 | Golden Benchmark | TECH | 모델·파이프라인 품질 회귀 기준 |
| AI-30 | Cost/Quality Optimizer | PRODUCT | 제품 해자로서 정식 명칭 필요 |

## 7. SW 생성·오케스트레이션·산출물

| ID | 현재 사용 용어 | 현재 성격 | 재정의 쟁점 |
|---|---|---|---|
| FLOW-01 | RFP | DOMAIN | 사용자 요구 정제 문서의 실제 산출물 명칭 검토 |
| FLOW-02 | Clarification | PRODUCT | 요구사항 사전상담·선택형 질문·HOTL과 구분 |
| FLOW-03 | PRD | DOMAIN | 기획서·제품 요구사항서와 통합 |
| FLOW-04 | Architecture | DOMAIN | 업무 아키텍처·SW 아키텍처·데이터 아키텍처 분리 |
| FLOW-05 | UI Design | DOMAIN | 화면설계·UI 시안·디자인 시스템 구분 |
| FLOW-06 | Vision QA | TECH | 화면 시각검증의 제품 언어 필요 |
| FLOW-07 | WBS | PRODUCT | 작업분해구조와 실행 Stage Map 연결 |
| FLOW-08 | Task | MIXED | WBS 작업·Sprint Task·Codex Task 혼용 |
| FLOW-09 | Stage | PRODUCT | 사용자 진행단계의 정식 단위 후보 |
| FLOW-10 | Phase | PRODUCT | 장기 제품 Phase·생성 Stage와 충돌 |
| FLOW-11 | Sprint | MIXED | Agile Sprint가 아니라 LangGraph 실행 단위로 사용 중 |
| FLOW-12 | Planning Mode | TECH | 기획 생성 모드와 경영 Planning 충돌 |
| FLOW-13 | Execution Mode | TECH | 코드 생성 실행과 현장 실행 충돌 |
| FLOW-14 | Orchestrator | TECH | Graph 실행·Task 관리·체크포인트 제어 |
| FLOW-15 | Checkpoint | TECH | 실행 재개 지점과 품질 관문 구분 |
| FLOW-16 | thread_id | TECH | 사용자 노출 금지 |
| FLOW-17 | HOTL | MIXED | Human-on-the-loop인지 Human-in-the-loop인지 재정의 필요 |
| FLOW-18 | User Review Gate | PRODUCT | 사용자 검토 요청의 정식 제품 용어 후보 |
| FLOW-19 | Approval Gate | PRODUCT | 승인·피드백·조건부 승인 상태 필요 |
| FLOW-20 | Revision | PRODUCT | 사용자 수정 요청과 내부 Rework 구분 |
| FLOW-21 | Rework | TECH | 동일 Stage 재작업 |
| FLOW-22 | Rollback | TECH | 코드·데이터·결정 철회 각각 분리 |
| FLOW-23 | Retry | TECH | 동일 호출 재시도와 전체 재작업 구분 |
| FLOW-24 | Circuit Breaker | TECH | 무한루프 차단과 실패 종료 계약 |
| FLOW-25 | Artifact / 산출물 | PRODUCT | 문서·소스·앱·보고서·이미지 상위 개념 |
| FLOW-26 | Stage Artifact | PRODUCT | 단계 산출물과 최종 결과물 구분 |
| FLOW-27 | Source Code | DOMAIN | 생성 결과 유형 중 하나 |
| FLOW-28 | Report Output | PRODUCT | 보고서형 산출물의 정식 유형 필요 |
| FLOW-29 | Preview | PRODUCT | 정적 미리보기와 운영 실행 구분 |
| FLOW-30 | Code Builder | TECH | 파일 쓰기·구문검사 역할 |
| FLOW-31 | Reviewer | MIXED | AI 코드 검토자와 사용자 검토자 구분 |
| FLOW-32 | QA | MIXED | 결정론적 테스트와 LLM 품질평가 구분 |
| FLOW-33 | Supervisor | MIXED | 파이프라인 판정자와 전역 AI 비서 충돌 |
| FLOW-34 | Manual Writer | TECH | 사용자 매뉴얼 생성 Stage |
| FLOW-35 | Self-Healing | PRODUCT | 자동 복구·사용자 요청 복구·재생성 구분 |
| FLOW-36 | Release Readiness | PRODUCT | 빌드 성공과 운영 배포 적격성 분리 |
| FLOW-37 | Release | PRODUCT | 버전 확정·배포 가능 상태 |
| FLOW-38 | Promotion | PRODUCT | Workspace→운영 자산 승격 |

## 8. 생성 앱 런타임·보안·실시간 통신

| ID | 현재 사용 용어 | 현재 성격 | 재정의 쟁점 |
|---|---|---|---|
| RUN-01 | Host Runtime | MIXED | 생성 앱을 통제하는 상위 실행환경의 정식 명칭 |
| RUN-02 | Host SDK | TECH | 생성 앱이 플랫폼 기능을 호출하는 유일한 인터페이스 |
| RUN-03 | App Data Plane | TECH | 앱별 데이터 읽기·쓰기·액션 경로 |
| RUN-04 | Capability Manifest | MIXED | App Manifest와 통합 또는 계층화 필요 |
| RUN-05 | App Manifest | PRODUCT | 앱 기능·데이터·권한·릴리스 선언서 |
| RUN-06 | Capability | DOMAIN | 기능 권한·API 권한·업무 능력 혼용 |
| RUN-07 | Short-lived Token | TECH | 앱·릴리스·사용자·범위·Capability 결합 토큰 |
| RUN-08 | Sandbox Token | TECH | Preview 격리 토큰과 운영 App Token 구분 |
| RUN-09 | Principal | TECH | 사용자·서비스·앱 주체의 공통 보안 객체 |
| RUN-10 | Session | TECH | 로그인 세션·생성 실행 세션·Preview 세션 구분 |
| RUN-11 | RBAC | TECH | 역할 기반 권한 |
| RUN-12 | ABAC | PLANNED | 속성·문맥 기반 권한 적용 범위 |
| RUN-13 | Policy Decision Point | TECH | 권한 판정·업무 정책 판정과 구분 |
| RUN-14 | Route Authority | TECH | API 접근 권한 해석기 |
| RUN-15 | Fail-closed | DOMAIN | 권한·데이터·Scope 해석 실패 시 차단 원칙 |
| RUN-16 | Data Stealth / 404 은폐 | DOMAIN | 타 범위 자원 존재 자체를 숨기는 정책 |
| RUN-17 | Sandbox | MIXED | Preview iframe·가상회사·시뮬레이션 Sandbox 충돌 |
| RUN-18 | Preview Isolation | TECH | 생성 코드의 부모 토큰·네트워크 접근 차단 |
| RUN-19 | CSP | TECH | Preview 네트워크·스크립트 제한 정책 |
| RUN-20 | iframe sandbox | TECH | 브라우저 실행 격리 |
| RUN-21 | postMessage Contract | TECH | Preview와 Host 간 메시지 허용 계약 |
| RUN-22 | Preview Session ID | TECH | 지연·위조 메시지 폐기 키 |
| RUN-23 | SSE | TECH | 실시간 이벤트 전송 방식, WebSocket과 혼용 금지 |
| RUN-24 | SSE Ticket | TECH | 30초·1회용 실시간 연결 인증권 |
| RUN-25 | EventSource | TECH | 프론트 SSE 클라이언트 구현 |
| RUN-26 | Broadcaster | TECH | 사용자·내부 Listener 이벤트 Fan-out |
| RUN-27 | Collaboration Event | DOMAIN | 앱 전달·결정·발간 이벤트의 공통 모델 |
| RUN-28 | App Delivery | PRODUCT | 앱 전달 요청·수신·승인 전체 과정 |
| RUN-29 | App Pocket | PRODUCT | 사용자가 승인한 앱 보관·실행 영역의 정식 명칭 검토 |
| RUN-30 | Generated App Runtime | PRODUCT | 승인 앱의 실제 실행 화면 |

## 9. 경영계획·시뮬레이션·디지털트윈

| ID | 현재 사용 용어 | 현재 성격 | 재정의 쟁점 |
|---|---|---|---|
| TWIN-01 | Digital Twin | PRODUCT | 설비 Twin과 경영 Twin을 반드시 구분 |
| TWIN-02 | Management Twin | PRODUCT | 경영 디지털트윈의 정식 축약명 후보 |
| TWIN-03 | Simulator | PRODUCT | 계산 엔진·시나리오 UI·생성 앱 유형 혼용 |
| TWIN-04 | Simulation | PRODUCT | 실행 1회·기능 모듈·제품 영역을 분리 |
| TWIN-05 | Planning Engine | DOMAIN | 경영계획 계산과 SW Planning Mode 충돌 |
| TWIN-06 | Planning Model | DOMAIN | 계획 버전·산식·조직 구조의 묶음 |
| TWIN-07 | Planning Driver | DOMAIN | 외부지표·내부 KPI·사용자 레버 관계 |
| TWIN-08 | Assumption | DOMAIN | 기준 가정·시나리오 가정·보정값 구분 |
| TWIN-09 | Driver | DOMAIN | 원인 변수·계산 입력·외부지표 혼용 |
| TWIN-10 | Lever | PRODUCT | 사용자가 조정하는 통제 가능 Driver |
| TWIN-11 | External Indicator | DOMAIN | 외부환경 정보와 수치 지표 구분 |
| TWIN-12 | External Intelligence | PRODUCT | 수집·검증·영향 매핑까지 포함하는 기능 |
| TWIN-13 | Benchmark | DOMAIN | 외부 기준가격·모델 품질기준·비교기업 기준 혼용 |
| TWIN-14 | Calculation Contract | DOMAIN | 입력·산식·단위·버전·출력·오류 규칙 |
| TWIN-15 | Calculation Graph | DOMAIN | 결정론적 인과 계산망, Agent Graph와 분리 |
| TWIN-16 | Calc Bridge | TECH | Enterprise Context 값을 계산 엔진 입력으로 변환 |
| TWIN-17 | Deterministic Engine | PRODUCT | LLM과 분리된 숫자 계산 책임자 |
| TWIN-18 | Scenario Definition | DOMAIN | 변경 가정·적용범위·기간·작성자 |
| TWIN-19 | Scenario Overlay | DOMAIN | Baseline에 덧씌우는 변경값 집합 |
| TWIN-20 | Simulation Run | DOMAIN | Snapshot·산식버전·결과가 고정된 실행 1회 |
| TWIN-21 | Outlook Series | DOMAIN | 미래 전망 시계열의 정식 명칭 |
| TWIN-22 | Risk Analyzer | PRODUCT | 위험 탐지·민감도·대안 추천 범위 |
| TWIN-23 | Backtest | DOMAIN | 과거 시점 재현과 예측 정확도 측정 |
| TWIN-24 | Replay | DOMAIN | 과거 데이터 재실행과 Backtest 구분 |
| TWIN-25 | Shadow Mode | PRODUCT | 운영 반영 없이 병행 계산·검증하는 상태 |
| TWIN-26 | Shadow Run | DOMAIN | Shadow Mode에서 수행한 실행 1회 |
| TWIN-27 | Golden Case | DOMAIN | 예상 결과가 고정된 대표 시나리오 |
| TWIN-28 | Golden Decision Case | DOMAIN | 의사결정 전후까지 포함한 검증 사례 |
| TWIN-29 | Sensitivity Analysis | DOMAIN | 단일·다중 변수 민감도 구분 |
| TWIN-30 | Scenario Comparison | PRODUCT | 기준안·대안·최악·최선 비교 화면 |

## 10. 의사결정·협업·실행·발간

| ID | 현재 사용 용어 | 현재 성격 | 재정의 쟁점 |
|---|---|---|---|
| DEC-01 | Decision Case | PRODUCT | 의사결정 안건의 상위 업무 객체 |
| DEC-02 | Decision Package | PRODUCT | 검토서·근거·영향·대안을 묶은 제출물 |
| DEC-03 | Decision Ledger | PRODUCT | 의사결정 이력 원장과 일반 감사로그 구분 |
| DEC-04 | Decision Center | PRODUCT | 사용자가 판단할 안건 화면 |
| DEC-05 | Decision Request | PRODUCT | 회의 요청·승인 요청·검토 요청 구분 |
| DEC-06 | Three Perspectives | PRODUCT | 요청자·결정자·영향부서 검토서 구조 |
| DEC-07 | Requester View | DOMAIN | 의사결정 요청 측 관점 |
| DEC-08 | Decision Maker View | DOMAIN | 승인·판단 측 관점 |
| DEC-09 | Affected Department View | DOMAIN | 영향받는 조직 관점 |
| DEC-10 | Meeting Request | PRODUCT | 회의 생성·참석자·기한·안건 연결 |
| DEC-11 | Approval | DOMAIN | 승인·조건부 승인·반려·보류 상태 필요 |
| DEC-12 | Execution Task | PRODUCT | 결정 후 현장 적용 과제 |
| DEC-13 | Effect Measurement | PRODUCT | 결정 전 기준선 대비 실제 효과 측정 |
| DEC-14 | Closed Loop | PRODUCT | 데이터→분석→결정→실행→효과→학습 |
| DEC-15 | Decision-to-Execution-to-Learning | PRODUCT | 대외 전략 메시지와 제품 내 용어 분리 |
| DEC-16 | Publication | PRODUCT | 보고서 발간·배포·공개 범위 |
| DEC-17 | Publication Center | PRODUCT | 대내외 보고서 검토·승인·발간 화면 |
| DEC-18 | Internal Report | DOMAIN | 사내 경영 보고서 |
| DEC-19 | External Report | DOMAIN | 대외 발간물, 비공개 경영 데이터 차단 필요 |
| DEC-20 | Executive Briefing | PRODUCT | 경영진 요약과 일반 보고서 구분 |
| DEC-21 | Enterprise Briefing | PRODUCT | 전사 현황 브리핑과 Executive Briefing 통합 여부 |
| DEC-22 | Boardroom | LEGACY | Mega Boardroom·Executive Board와 관계 |
| DEC-23 | App Push | PRODUCT | 앱 전달과 모바일 Push 알림 혼동 방지 |
| DEC-24 | Received App | PRODUCT | 수신 앱함·검토 대기 앱 |
| DEC-25 | Accept / Reject / Reassign / Recall | PRODUCT | 앱 전달 수명주기 상태의 한글 표준화 |

## 11. 전역 AI 비서·감독 기능

| ID | 현재 사용 용어 | 현재 성격 | 재정의 쟁점 |
|---|---|---|---|
| ASST-01 | Jarvis | PRODUCT | 현재 UI·API에서 사용 중인 전역 비서 이름 |
| ASST-02 | Atlas | LEGACY | 과거 후보명, 문서·시안 잔존 여부 정리 |
| ASST-03 | Supervisor | MIXED | 전역 비서·파이프라인 검토 노드·백그라운드 데몬 충돌 |
| ASST-04 | Global Supervisor | PRODUCT | Jarvis와 동일 개념인지 상위 통제 역할인지 |
| ASST-05 | Supervisor Daemon | TECH | NODE_COMPLETED 감시형 내부 LLM 평가기 |
| ASST-06 | Jarvis Dock / Rail | PRODUCT | 화면 우측 고정 대화영역의 정식 UI 용어 |
| ASST-07 | Advisor | PRODUCT | 최초 상담역과 전역 비서의 관계 |
| ASST-08 | Business/Data Design Advisor | PRODUCT | 업무·데이터 준비 상담 특화 역할 |
| ASST-09 | Solution Blueprint | PRODUCT | 상담 결과로 생성되는 실행 설계서 |
| ASST-10 | Enterprise Briefing Agent | PLANNED | 브리핑 생성 역할과 Jarvis 통합 여부 |
| ASST-11 | Recommendation | PRODUCT | 설명·추천·자동실행 제안 수준 분리 |
| ASST-12 | Intervention | PRODUCT | 자동 중단·사용자 확인·권고만 제공 구분 |
| ASST-13 | Global Question | PRODUCT | Task ID 없이 전체 상태에 질의하는 기능 |
| ASST-14 | Selected Object Context | TECH | 현재 화면·회사·프로젝트 문맥을 비서에 전달 |

## 12. 외부 연계·MCP·수집

| ID | 현재 사용 용어 | 현재 성격 | 재정의 쟁점 |
|---|---|---|---|
| INT-01 | Connector | PRODUCT | ERP·MES·파일·API·DB 연결 어댑터의 상위 개념 |
| INT-02 | Connector Registry | TECH | 연결 정의·자격·버전 등록부 |
| INT-03 | Connector Execution | TECH | 실제 호출·재시도·대사 실행 |
| INT-04 | MCP | TECH | 연결 프로토콜이지 사용자 기능명이 아님 |
| INT-05 | MCP Broker | TECH | 외부 MCP 서버 접근 통제·감사 경계 |
| INT-06 | External System | DOMAIN | 기간계·업무시스템·외부 협업시스템 구분 |
| INT-07 | Legacy System | DOMAIN | 교체 대상이 아니라 공존·연계 대상으로 정의 |
| INT-08 | External Engagement System | DOMAIN | 거래처·통관사·운송사 입력 시스템의 일반 유형 |
| INT-09 | External Engagement Integration Boundary | MIXED | 경영 시스템 외부참여자 비개방 원칙의 기술 경계 |
| INT-10 | LPL | DOMAIN | 특정 회사 사례이며 제품 일반 용어로 승격 금지 |
| INT-11 | Data Ingestion | TECH | 수집·복제·변환·등록 단계 분리 |
| INT-12 | Collector | TECH | 외부지표 수집기와 업무데이터 Connector 구분 |
| INT-13 | External Collector | TECH | 공식 외부정보 수집 모듈 |
| INT-14 | Source Adapter | TECH | 원천별 형식 변환기 |
| INT-15 | Replication | TECH | 데이터 레이어 복제와 실시간 동기화 구분 |
| INT-16 | Sync | TECH | 주기·증분·양방향 여부 명시 필요 |
| INT-17 | Import | PRODUCT | 파일 등록·계획 Import·데이터 적재 혼용 |
| INT-18 | Export | PRODUCT | 프로젝트 ZIP·데이터 추출·보고서 발간 구분 |
| INT-19 | Web Crawling | PLANNED | 공식 API·파일 수집보다 후순위 원칙 반영 |
| INT-20 | Late-arriving Data | DOMAIN | 마감 후 도착 데이터의 반영·재계산 규칙 |

## 13. 품질·감사·운영·테스트

| ID | 현재 사용 용어 | 현재 성격 | 재정의 쟁점 |
|---|---|---|---|
| OPS-01 | Governance | PRODUCT | 데이터·에이전트·앱·권한 거버넌스 분리 |
| OPS-02 | Governance Console | PRODUCT | 통합 관리화면인지 특정 기능인지 |
| OPS-03 | Admin Console | PRODUCT | 설정·사용자·권한·운영관리 범위 |
| OPS-04 | Program Admin | PRODUCT | Program 관리와 시스템 관리 구분 |
| OPS-05 | Audit | DOMAIN | 보안 감사·데이터 감사·변경 감사 구분 |
| OPS-06 | Audit Log | DOMAIN | 이벤트 로그·Decision Ledger·Lineage와 분리 |
| OPS-07 | Telemetry | TECH | LLM·품질·운영·사용행태 텔레메트리 분리 |
| OPS-08 | Quality Telemetry | PRODUCT | 산출물 품질 결과와 모델 품질 결과 구분 |
| OPS-09 | System Log | TECH | 사용자 이벤트·감사로그와 분리 |
| OPS-10 | Config Snapshot | TECH | 설정 버전 재현과 데이터 Snapshot 구분 |
| OPS-11 | Cache | TECH | LLM 응답·Context·Registry 캐시 분리 |
| OPS-12 | Persistence | TECH | LangGraph checkpoint·업무 DB·파일 Snapshot 구분 |
| OPS-13 | SQLite Checkpointer | TECH | 개발 기본 저장소 |
| OPS-14 | Postgres Checkpointer | TECH | 운영 후보 저장소, 업무 통합DB와 분리 |
| OPS-15 | Release Gate | PRODUCT | 앱 릴리스 적격성 관문 |
| OPS-16 | Syntax Check | TECH | 구문 유효성 검사 |
| OPS-17 | Regression Check | TECH | 기능·심볼 감소 검출 |
| OPS-18 | Render Check | TECH | 프론트 렌더링 검사 |
| OPS-19 | Interactivity Check | TECH | 입력·버튼 동작 정적 검사 |
| OPS-20 | Backend Smoke Test | TECH | 생성 백엔드 기동·Route 검사 |
| OPS-21 | Platform Auth Scan | TECH | 생성 앱 자체 로그인·인증 코드 차단 |
| OPS-22 | Test Runner | TECH | pytest·bandit·compileall·npm build 실행기 |
| OPS-23 | Quality Score | MIXED | LLM 점수·결정론 검사·사용자 평가 분리 |
| OPS-24 | PASS / REWORK / ROLLBACK | TECH | Stage 판정과 데이터 품질 상태 혼동 방지 |
| OPS-25 | Traceability | PRODUCT | 요구→설계→코드→테스트→결정 추적 |
| OPS-26 | Traceability Graph | PRODUCT | Graph RAG·Calculation Graph와 분리 |
| OPS-27 | Readiness | PRODUCT | 데이터·릴리스·조직·파일럿 준비도 각각 명명 |
| OPS-28 | Lifecycle | DOMAIN | Project·Program·App·Data Contract 수명주기 분리 |
| OPS-29 | Archive | PRODUCT | 삭제 전 보존·과거 실행·산출물 보관 구분 |
| OPS-30 | Delete / Deletion | PRODUCT | 프로젝트·회사·데이터의 참조 정리 정책 필요 |
| OPS-31 | Resume Guard | TECH | 중단 실행의 안전 재개 검사 |
| OPS-32 | Run Context | TECH | 실행 문맥과 Enterprise Context 분리 |

## 14. 주요 화면·내비게이션 명칭

| ID | 현재 사용 용어 | 현재 성격 | 재정의 쟁점 |
|---|---|---|---|
| UI-01 | Enterprise | PRODUCT | 첫 화면의 목적을 경영 현황·업무 진입 중 무엇으로 둘지 |
| UI-02 | Build SW | PRODUCT | SW 생성기 정식 메뉴명과 통합 |
| UI-03 | Operate | PRODUCT | 생성 앱 실행·업무운영·프로그램 관리 범위 |
| UI-04 | Simulate | PRODUCT | Twin·Scenario·Planning 메뉴 구조 |
| UI-05 | Knowledge | PRODUCT | Knowledge Hub 정식 메뉴명 |
| UI-06 | Data | PRODUCT | MDM·Catalog·Contract·Lineage 진입점 |
| UI-07 | Agents | PRODUCT | Agent Master·Governance·Skill 진입점 |
| UI-08 | Collaboration | PRODUCT | 앱 전달·의사결정·발간 통합영역 |
| UI-09 | Administration | PRODUCT | 관리자 전용 영역의 정식 메뉴명 |
| UI-10 | Master Data | PRODUCT | 기준정보 관리 화면 |
| UI-11 | Crosswalk | MIXED | 사용자용 한글 메뉴명 필요 |
| UI-12 | Work Standard | PRODUCT | 업무표준 화면 |
| UI-13 | Shadow Mode | PRODUCT | 운영 검증 화면 |
| UI-14 | Telemetry | MIXED | 운영자 화면인지 일반 사용자 화면인지 |
| UI-15 | Quality Outcomes | PRODUCT | 산출물 품질 결과 화면 |
| UI-16 | Workflow Strip | LEGACY | 단계 지도·Production Stage Map과 통합 필요 |
| UI-17 | WBS Spine | PRODUCT | 생성 진행의 세로 작업 구조 UI |
| UI-18 | Production Stage Map | PRODUCT | SW 생성단계 지도, 제조 생산과 명칭 충돌 가능 |
| UI-19 | Adaptive Phase Canvas | PRODUCT | 현재 작업 산출물 영역의 정식 명칭 검토 |
| UI-20 | Timeline | PRODUCT | 실행 로그·이벤트·감사 타임라인 구분 |
| UI-21 | Preview Panel | PRODUCT | 소스·앱·보고서 결과 미리보기 유형화 필요 |
| UI-22 | Context Inspector | PRODUCT | 현재 회사·데이터·근거·산출물 문맥 보기 |
| UI-23 | Decision Drawer | PRODUCT | 전역 의사결정 대기 UI와 Decision Center 관계 |
| UI-24 | User Review Request | PRODUCT | 기존 사람 검토 요청을 대체하는 정식 용어 후보 |
| UI-25 | Jarvis Rail | PRODUCT | 전역 비서 영역의 위치 독립적 명칭 필요 |

---

## 15. 가장 먼저 결정해야 할 P0 용어 충돌

| 우선순위 | 충돌 묶음 | 결정해야 할 것 |
|---:|---|---|
| 1 | `Jarvis / Atlas / Supervisor / Supervisor Daemon` | 제품 비서, 파이프라인 판정자, 백그라운드 감시자의 이름을 각각 분리 |
| 2 | `SW 생성기 / App Factory / Operational App Factory / Build SW` | 제품 기능명·메뉴명·기술 아키텍처명을 계층화 |
| 3 | `MDM / Master Data / 기준정보 / Reference Data` | 마스터·코드·참조·외부 공식자료의 경계 확정 |
| 4 | `Data Catalog / Knowledge Hub / Reference Registry / Source Registry` | 무엇을 찾고 무엇을 승인하며 무엇을 근거로 쓰는지 분리 |
| 5 | `Scope / Context / Workspace / Tenant` | 권한 경계·현재 선택 문맥·작업공간·고객 격리 단위 분리 |
| 6 | `Project / Program / Task / Sprint / Stage / Phase` | 사용자 업무 객체와 내부 실행 객체 분리 |
| 7 | `HOTL / User Review Gate / Approval Gate` | 사람 개입을 사용자 언어로 재정의하고 내부 약어는 기술 문서로 제한 |
| 8 | `Release / Delivery / Promotion / Publication / Export` | 앱·데이터·보고서의 이동 행위를 각 수명주기로 분리 |
| 9 | `Digital Twin / Management Twin / Simulator / Simulation / Planning` | 제품 영역·계산 엔진·실행 1회·화면을 분리 |
| 10 | `Baseline / Snapshot / Version / Checkpoint` | 데이터·계산·실행 재개의 기준 상태를 분리 |
| 11 | `ACTUAL / SYNTHETIC / business_data_kind / data_origin` | 합성 실적형 데이터가 실제값으로 오인되지 않도록 이름과 표시 확정 |
| 12 | `App Manifest / Capability Manifest / Data Contract / Scope Contract` | 선언서·데이터 계약·권한 계약의 포함 관계 확정 |
| 13 | `Ontology / Knowledge Graph / Graph RAG / Agent Graph / Calculation Graph / Traceability Graph` | 의미 스키마·관계 인스턴스·검색·실행·계산·추적 그래프를 목적별 고유명으로 고정 |
| 14 | `Governance / Admin / Program Admin / Agent Governance` | 관리자 화면과 정책 체계의 메뉴 구조 확정 |
| 15 | `Enterprise / Enterprise Canvas / Cockpit / Boardroom` | 첫 화면·경영진 화면·다중 프로젝트 화면을 분리 |

## 16. 다음 재정의 작업의 산출물

이 Inventory를 기반으로 다음 네 가지를 별도 작성한다.

1. **제품 용어 사전** — 사용자·경영진·영업 제안서가 사용하는 한글 중심 용어
2. **도메인 의미 사전** — 조직·데이터·계획·시뮬레이션·의사결정의 엄밀한 정의
3. **기술 명명 규칙** — API·DB·코드 클래스·이벤트·상태값의 영문 Canonical Name
4. **Legacy Alias·Migration 표** — 기존 문서·UI·코드 용어를 어떤 이름으로 언제 치환할지

재정의 원칙은 “멋있어 보이는 새 이름”이 아니라 다음 질문에 한 문장으로 답할 수 있어야 한다.

- 누가 사용하는가?
- 무엇을 포함하고 무엇을 포함하지 않는가?
- 상위·하위 개념은 무엇인가?
- UI·문서·API·DB에서 각각 어떤 이름을 쓰는가?
- 다른 용어와 어떤 점에서 다른가?

---

## 17. 현재 산출물과 운영 상태 (2026-08-12)

이 인벤토리의 349개 용어는 전환 사전 v0.3.0으로 생성되어 있습니다.

| 산출물 | 경로 | 역할 |
|---|---|---|
| 전환 정책 | `data/terminology/technology_terminology_policy.json` | 팀 권장안·상태 정의·용어별 최종 권장 표현 |
| 정본 JSON | `data/terminology/technology_terminology_glossary.json` | 시스템·자동화가 읽는 단일 용어 사전 |
| 화면용 JSON | `frontend/src/data/technologyTerminologyGlossary.json` | 용어집 페이지가 읽는 생성 산출물 |
| Excel 사전 | `docs/architecture/AI_FACTORY_STUDIO_TECHNOLOGY_TERMINOLOGY_DICTIONARY_2026-08-12.xlsx` | 사람이 검토·공유하는 6개 시트 사전(`표준약어` 포함) |
| 시스템 화면 | `frontend/src/components/TerminologyGlossaryPanel.tsx` | 검색·필터·P0 충돌·정의·사용 원칙 조회 |
| UI 전환 백로그 | `docs/architecture/TECHNOLOGY_TERMINOLOGY_UI_MIGRATION_BACKLOG_2026-08-12.md` | 실제 소스의 화면 노출 후보와 기술 식별자 후보 분리 |

현재 상태는 다음과 같습니다.

- 전체 용어: **349개**
- P0 충돌 권장안: **15개**
- `검토 필요`: **0개**
- `대체 용어 검토 중`: **0개**
- 결정 상태: **팀 권장안** — 신규 화면·문서의 기본값으로 사용
- 최종 제품 용어 승인: **제품 책임자 승인 필요**
- API·DB·코드 식별자: **별도 마이그레이션 승인 전 변경 금지**

### 표준 약어 표시 정책 — 제품 책임자 승인(2026-08-12)

- WBS·RFP·PRD처럼 업계에서 널리 통용되는 약어는 쉬운 말로 **대체하지 않고 유지**한다.
- 최초 노출에서는 `WBS(작업분해구조)`처럼 뜻을 병기하고, 같은 화면의 반복 노출에서는 약어만 쓴다.
- 버튼은 약어를 없애는 대신 `WBS 작성 시작`·`PRD 검토`·`RFP 승인`처럼 행동을 명확히 쓴다.
- 현재 시스템의 RFP는 후속 기획·설계·구현·검증의 기준이 되는 내부 요구사항 계약이므로
  `RFP(요구사항 정의서)`로 설명한다. 외부 공급자에게 제안을 요청하는 문서일 때만
  `RFP(제안요청서)`라고 표시한다.
- 약어와 실제 산출물 의미가 다르면 용어만 부드럽게 바꾸지 않고 산출물 정의를 먼저 바로잡는다.

재생성 명령:

```powershell
venv\Scripts\python.exe scripts\build_technology_terminology_dictionary.py
venv\Scripts\python.exe scripts\audit_terminology_usage.py
```
