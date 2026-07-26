# 테스트 진행 트래커 (SSOT — 시나리오 완료 시마다 즉시 갱신)

> 재개 방법: 새 세션에서 **"docs/test_plan/02_progress_tracker.md 읽고 테스트 이어서 진행해줘"**
> 상태: `PENDING`(대기) / `IN_PROGRESS`(진행 중) / `PASS` / `COND`(조건부) / `FAIL` / `DEFERRED`(쿼터 등으로 연기) / `SKIP`

## 전체 현황

| Phase | 상태 | 완료/전체 | 비고 |
|---|---|---|---|
| P0 사전 점검 | PASS | 3/3 | 전 시나리오 완료 |
| P1 구조 테스트 | PASS | 8/8 | LLM 불필요 — 자동화 테스트(pytest)로 검증 완료 |
| P2 파일럿(관문) | IN_PROGRESS | 0/1 | A-1 관문 테스트 가동 중 |
| P3 SW 다양화 | PENDING | 0/5 | |
| P4 view_type 변형 | PENDING | 0/3 | |
| P5 HOTL 리비전 | PENDING | 0/2 | |
| P6 마케팅+분석 | PENDING | 0/4 | |
| P7 제조 4종 | PENDING | 0/4 | |
| P8 시뮬레이터 | PENDING | 0/2 | |
| P9 메가 프로젝트 | PENDING | 0/2 | |
| P10 시스템 기능 | PENDING | 0/6 | |
| P11 종합 리포트 | PENDING | 0/1 | |

## 시나리오별 상세

| ID | 상태 | 점수(/30) | 실행일 | 특이사항 |
|---|---|---|---|---|
| ENV-1 | PASS | — | 2026-07-16 | LLM Gateway 다중 폴백 정상 구동 확인 |
| ENV-2 | PASS | — | 2026-07-21 | 180건 모두 통과 완료 |
| ENV-3 | PASS | — | 2026-07-16 | 백엔드(8080)/프론트(5173) 정상 동작 |
| S-1 | PASS | — | 2026-07-21 | pytest 스위트로 검증 완료 |
| S-2 | PASS | — | 2026-07-21 | pytest 스위트로 검증 완료 |
| S-3 | PASS | — | 2026-07-21 | pytest 스위트로 검증 완료 |
| S-4 | PASS | — | 2026-07-21 | pytest 스위트로 검증 완료 |
| S-5 | PASS | — | 2026-07-21 | pytest 스위트로 검증 완료 |
| S-6 | PASS | — | 2026-07-21 | pytest 스위트로 검증 완료 |
| S-7 | PASS | — | 2026-07-21 | pytest 스위트로 검증 완료 |
| S-8 | PASS | — | 2026-07-21 | pytest 스위트로 검증 완료 |
| A-1 | COND | — | 2026-07-26 | 기획 파이프라인(CLARIFICATION~PMO) 100% 만점 통과 및 WBS 5건 분할 완수. 1차 과업(E2E-01) 수행 중 외부 LLM API 서버의 504 타임아웃 지속으로 인한 코드 수신 실패로 중단 — 504 방어(Tier/Circuit Breaker) 가동 실측. 외부 API 안정화 후 재도전 예정 |
| A-2 | PENDING | — | | |
| A-3 | PENDING | — | | |
| A-4 | PENDING | — | | |
| A-5 | PENDING | — | | |
| A-6 | PENDING | — | | |
| A-7 | PENDING | — | | |
| A-8 | PENDING | — | | |
| A-9 | PENDING | — | | |
| A-10 | PENDING | — | | |
| A-11 | PENDING | — | | |
| B-1 | PENDING | — | | |
| B-2 | PENDING | — | | |
| C-1 | PENDING | — | | |
| C-2 | PENDING | — | | |
| D-1 | PENDING | — | | |
| D-2 | PENDING | — | | |
| D-3 | PENDING | — | | |
| D-4 | PENDING | — | | |
| E-1 | PENDING | — | | |
| E-2 | PENDING | — | | |
| F-1 | PENDING | — | | |
| F-2 | PENDING | — | | |
| G-1 | PENDING | — | | |
| G-2 | PENDING | — | | |
| G-3 | PENDING | — | | |
| G-4 | PENDING | — | | |
| G-5 | PENDING | — | | |
| G-6 | PENDING | — | | |

### 📊 A-1 완주 스프린트 벤치마크 목표 (실측 데이터 기록용)
| 지표 (Metrics) | 측정 방법 | 목표 (Target) | 결과 (Actual) | 비고 |
|---|---|---|---|---|
| 총 리드 타임 | 기동부터 종료까지의 시간 | 20분 이내 | 약 19분 (실행 중단) | 기획 단계 ~10분 소요 |
| 자가복구 횟수 | CodeBuilder 에러 로깅 횟수 | 기록 | 3회 실측 | Pro 504 타임아웃 감지 -> Flash 직행 및 Circuit Breaker 재작업 지시 |
| 총 토큰 소모 | 콘솔 출력된 LLM Usage 합산 | 이전 대비 감소 | — | |
| HOTL 피로도 | 사용자 강제 개입 횟수 | 5회 이하 | 0회 (드라이버 자동 통과) | 인터뷰 게이트 및 기획 승인 전체 무피드백 통과 |

## 발견된 결함 로그

| # | 발견 시나리오 | 심각도 | 내용 | 상태 |
|---|---|---|---|---|
| 1 | A-1 | Critical | VisionQA가 `ProjectState`에 없는 `completed_agents` 필드 접근 → `AttributeError`로 파이프라인 중단 (nodes/vision_qa.py, 커밋 b5b8407에서 유입) | **FIXED** (2026-07-17, 통과 시 `reviewer_decision` 미초기화로 인한 UIDesigner 무한왕복 잠재결함도 함께 수정) |
| 2 | A-1 | Major | 워크플로우 순서 결함: 아키텍처가 WBS 분할 *이후* 실행 태스크 안에서 수립되어 WBS가 설계 없이 작성됨 (스킬제안 prop_521c4962가 자가 진단한 정합성 오류의 근원) | **FIXED** (2026-07-17, B안: RFP→PRD→UI→VisionQA→**Architect**→WBS 로 재배선. agent_graph/planning/execution/registry/pmo_skill/프론트 2종 수정, 라우터 테스트 37건 통과) |
| 3 | A-1 | Minor | `playwright` 미설치로 VisionQA 스크린샷 캡처가 항상 생략됨(시각 검증 실효성 없음) | **해소됨(무의미화)** (2026-07-23, #12 로 VisionQA 를 자문 강등 — 더 이상 자동 반려/차단하지 않으므로 스크린샷 유무가 파이프라인에 영향 없음. 필요 시 사람이 실제 미리보기로 확인) |
| 4 | ENV-2 | Minor | pytest 기존 실패 7건(구버전 토폴로지 기준의 낡은 기대값: interrupt 2개 가정 등) — 이번 변경과 무관하게 HEAD에서도 동일 실패 확인 | **FIXED** (2026-07-19 어서션 현행화 + 형제 리포 pyc 캐시 오염 제거 → **전 스위트 155건 통과 = ENV-2 베이스라인**) |
| 5 | A-1 4차 | Major | `hotl/check` 가 PLANNING_* 태스크의 HOTL 대기를 미감지(SSE 유실 시 기획 게이트 복구 불가) | **FIXED** (latest_state 의 현재 태스크로도 확인) |
| 6 | A-1 4차·AABB | Critical | WBS 분할 결과가 빈 태스크로 저장되고 게이트 통과 → 기획이 '완료된 척' 정지 (non-greedy JSON 절단 + 빈 결과 무방어) | **FIXED** (파싱 견고화+1회 재시도+빈 WBS 저장 금지) + **복구 수단 신설**(`wbs/replan` API·UI 버튼) |
| 7 | A-1 2차 | Major | `run.py` reload=True 가 .py 저장 시 서버 재시작 → 실행 중 스프린트 스트림 사망 | **FIXED** (운영 모드 기본 reload OFF, `--dev` 옵트인) |
| 8 | 환경 | Major | 프로바이더 패키지 설치가 langchain-core 를 0.3 으로 다운그레이드시켜 gemini/groq 임포트 파손. langchain-cerebras 는 core 1.x 미지원 | **FIXED** (core 1.x 정렬, Cerebras 는 OpenAI 호환 API 로 전환 — 5중 폴백 전부 활성) |
| 9 | A-1 (E2E-03) | Major | LLM Gateway 할당량(무료 티어) 소진으로 인해 기술명세 단계 중단 후 프론트엔드 산출물 빈 값 반환 → 파싱 실패 및 파이프라인 중단(FAILED) | **MITIGATED** (2026-07-23) — 근본 원인이 #12(UI_DESIGN↔VisionQA 왕복이 RPD 소진)임을 텔레메트리로 규명·수정. 단 무료 RPD 자체의 한계는 잔존(BYO 유료키/초경량 파이프라인이 최종 해법). 산출물 빈 값 방어는 별도 강화 필요 |
| 10| A-1 (E2E-04) | Critical | `UI_DESIGN` 단계에서 HOTL 게이트 `자동 승인(resume)`이 무한루프로 발생하며 다음 단계(ARCHITECTURE)로 넘어가지 못함 | **FIXED** (2026-07-23, VisionQA 반려 피드백을 UIDesigner가 수용하고 상태를 초기화하도록 수정하여 캐시 무한루프 차단) |
| 11| 지식 허브 | Major | 지식팩 첫 파일은 등록되나 추가 업로드 시 chromadb "embedding function conflict: new sentence_transformer vs persisted default" 로 실패 | **FIXED** (2026-07-23, `42cc2b8c1`) — `_embedding_fn` 지연 로드 경쟁(완료 플래그를 로드 前 설정)으로 컬렉션이 default 임베딩으로 생성되던 것을 락+완료후 플래그로 차단. `_pack_collection` 은 기존 컬렉션을 get_collection 으로 열어 재지정 안 함. 오류 메시지 한국어화. 실증(sf_glossary 추가 업로드 성공) |
| 12| A-1 | Critical | **완주 병목**: `route_from_vision_qa` 에 왕복 상한 부재 → VisionQA 가 REWORK_DEV 반복 시 UI_DESIGN↔UIDesigner 왕복(각 ~5콜)이 무료 티어 일일 요청수(RPD)를 소진해 ARCHITECTURE 도달 전 SUSPENDED. 텔레메트리상 UI_DESIGN 이 콜 대부분(07-22 127·07-23 29), Pro 는 1콜(병목 아님) | **FIXED** (2026-07-23, `e8f5e3837`) — VisionQA 를 차단 게이트→**자문(advisory)** 으로 강등. 자동 반려 루프 제거, 소견만 남겨 사람 HOTL 미리보기에서 검토. 왕복 0 |
| 13| A-1 | Critical | **재작업 루프가 Exact Hash Cache 로 무력화**: 빌드 실패 시 `build_error_log` 를 프롬프트에 주입해 재시도하나 **에러 문자열이 매번 같아 프롬프트 해시도 같다** → 캐시 히트 → 똑같은 코드 반환 → 똑같은 실패. 재작업 상한(8)까지 0.0초에 순환(실측 9초에 캐시히트 38건, code/document/json 시퀀스 8회) 후 `재작업 상한(8) 도달 - best-effort 수용` 으로 **미해결 결함을 안고 DONE 처리**. 즉 E2E-01 의 DONE 은 깨끗한 통과가 아니었다. `nodes/utils/debate.py:179,202` 는 같은 함정 때문에 이미 `cacheable=False` 를 쓰는데 개발자 노드에는 빠져 있었음(결함 #10 과 같은 종류의 재발) | **FIXED** (2026-07-26, `98cdc27ba`) — `_swarm_execution` 에 `cacheable` 파라미터 추가, 호출부 2곳이 `cacheable=not _is_rework` 전달. 첫 시도 캐시 절감은 유지하고 재작업만 우회 |
| 14| A-1 | Major | **제공사별 타임아웃 의미가 달라 504 오진 유발**: Gemini 는 `timeout` 을 `int(timeout*1000)` ms 로 변환해 gRPC **total deadline** 으로 넘기므로 60초가 총 시간 상한(실측 56~59초 실패). 반면 `ChatOpenAI` 의 timeout 은 httpx 로 가는데 httpx 의 `read` 는 '바이트 간 간격'이라 프록시가 커넥션을 살려두면 **미발동**(실측 294.67초 진행, 성공 콜도 95.82초). 따라서 '타임아웃 일괄 연장'은 잘못된 처방 | **FIXED** (2026-07-26, `9569e4275`) — 제공사별 분리(`LLM_TIMEOUT_GEMINI=180` / OPENAI_COMPAT·XAI·GROQ=90) + `aexecute` 체인 walk 를 `asyncio.wait_for(LLM_TOTAL_DEADLINE_SEC=420)` 로 감싸 총 시간 상한 강제 |
| 15| A-1 | Major | **구조화 출력 폭주 — 모델이 종료하지 않음**: 코드 생성이 `completion_tokens` 상한을 정확히 소진하고 절단되어 `Could not parse response content as the length limit was reached` 로 실패. **8192 에서 실패 → 16384 로 올려도 16384 에서 동일 실패**(prompt 6,160 → output 16,384 = 프롬프트의 2.7배). 상한 부족이 아니라 `with_structured_output(CodeOutput)` 으로 큰 코드 문자열을 뽑을 때 반복에 빠지는 현상으로 의심 | **회피(OPEN)** — 상한 8192 원복(올리면 실패가 느리고 비싸질 뿐). 정상 생성 시 출력 1,895~1,948 토큰이면 충분하므로 **재시도(새 표본)로 회피**하며, 그 경로를 결함 #13 수정이 복구했다. 근본 대응 후보: 자유 JSON(`output_mode="json"`)+자체 파싱 전환, 또는 `CodeOutput` 에서 ADR·기술부채·파일인덱스 분리 |
| 16| A-1 | Critical | **Flash 티어 체인 전체가 무료 모델** → OpenRouter 크레딧이 있어도 Flash 호출은 쓸 수 없었다. judge/scoring 이 Flash 를 쓰므로 채점 단계에서 반드시 막힌다. 실측(test_a1_v2): Pro 콜 3건은 전부 성공했는데 RFP 채점에서 `flash d=7 1.72s ❌` → 전 모델 쿨다운 → `_compose_chain` 이 `ordered[0]`(방금 429 로 죽은 무료 gemini)로 재프로브 → `0.15s ❌ ×3` → `SUSPENDED_QUOTA`. 2026-07-25 세션로그 §E-2 의 쿨다운 가설이 이로써 실측 확정됨 | **FIXED** (2026-07-26, `d59e8596f`) — ① `LLM_FLASH_FALLBACK_LIST` 말단을 `...:free` → 유료 `meta-llama/llama-3.3-70b-instruct` 로 교체(양 티어 모두 유료 백스톱 확보) ② `PAID_MODEL_COOLDOWN_SEC=60`(무료 1800 유지) + `_is_paid_model()` 신설 — 유료는 크레딧이 있는 한 살아 있으므로 장기 배제가 부당 ③ 전 모델 쿨다운 시 재프로브 대상을 **유료 우선**으로 변경. **검증(test_a1_v3)**: 동일 지점에서 `flash_router json d=7 8.65s ok=True meta-llama` — 무료 7개를 지나 유료가 받아냄 |

## 세션 인수인계 메모

- 2026-07-16: 새 LLM 라우팅 체인(OpenRouter, xAI 등) 적용 완료 후 ENV-1 정상 동작 확인됨. 
- 2026-07-16: A-1(test_a1_unitconv) 테스트 데이터를 생성하여 초기 스프린트 백엔드에서 가동 중.
- 2026-07-17: A-1이 RFP(1.0)→PRD(0.963)→UI_DESIGN(1.0) 통과 후 VisionQA에서 결함 #1로 크래시. 결함 #1·#2 수정 완료(미커밋). **워크플로우가 바뀌었으므로 A-1은 처음부터 재실행 필요**(sprint_init 재가동 시 자동 아카이브됨). Pro 체인 전 제공사 429 소진 이력 있음 → 쿼터 잔량 확인 후 재실행 권장.
- 2026-07-18: **신규 기능 — 요구 확인 인터뷰 게이트** 추가(미커밋). PLANNING 진입 시 `Requirement_Interviewer`가 선택형 질문 2~4개 생성 → HOTL 게이트(질문 카드 UI, 추천안 기본 선택) → 답변이 RFP/PRD에 주입. 기본 파이프라인이 **CLARIFICATION → RFP → PRD → UI → VisionQA → ARCHITECTURE → WBS** 로 변경됨. HOTL 게이트 5곳(인터뷰/RFP/PM/VisionQA/PMO). ⚠️ 테스트 시나리오의 HOTL 자동 승인 절차에 인터뷰 게이트 1회 추가 반영 필요(무피드백 resume 시 추천안 없이 아이디어만으로 RFP 진행되므로, 자동화 시엔 그냥 resume 하면 됨).
- 2026-07-22: **v1 Exact Hash Cache 도입 완료** (쿼터 방어 목적). 이를 기반으로 A-1 시나리오 재개했으나, `UI_DESIGN` 단계에서 자동 승인 무한루프 결함(Bug #10) 발생으로 18분 강제 종료됨. 다음 세션에서 Bug #10 추적 요망.
- 2026-07-23: 결함 #10(UI_DESIGN HOTL 무한루프)·#11(지식허브 임베딩 충돌)·#12(VisionQA 왕복 RPD 소진) 수정 완료. A-1 은 코드 결함이 아니라 **무료 쿼터 소진**으로 DEFERRED.
- 2026-07-26: **A-1 시나리오 전 과정 E2E 자동화 테스트 가동 실측 수행**. 기획 파이프라인 전 단계(요구 확인 인터뷰, RFP 1.0, PRD 0.875, UI_DESIGN 1.0 만점, 아키텍처 0.75, WBS PMO 5건 분할)를 무피드백 게이트로 완벽히 관통함. 실행 과업(E2E-01) 수행 중 외부 상위 LLM 제공사 API 서버의 504 타임아웃(DEADLINE_EXCEEDED) 장애가 발생하여, **Tier Breaker(Pro->Flash 직행 보호)** 및 **Circuit Breaker(자가 복구 2회차 지시)** 메커니즘이 정상 가동됨을 실증함. 그러나 외부 API 서버 지연 지속으로 산출물 수신 실패(FAILED). 파이프라인 엔진이나 코드의 결함이 아닌 외부 API 환경적 요인으로 확인되었으며, 추후 API 통신 및 쿼터 회복 시 재가동 요망.
- 2026-07-24: 디지털 트윈 마스터데이터 M1~M4 구축(외부 세션) + 정규화 주입 로더 재작성(`94d6edc19`). 활성 골든레코드 5→36개, 타입 10종. 지식팩 `core-m3-standards` 등록(약 370청크). 전 pytest 258건 통과.
- 2026-07-25: **런타임 데이터는 gitignore 라 PC 이동 시 따라오지 않는다** — 다른 PC에서 이어받으면 `data/master/`(마스터데이터)·`data/knowledge_packs/`·`data/chroma_db/`(지식팩)가 전부 비어 있다. 시나리오 실행 **전에** 반드시 재주입할 것(절차는 `AI_HANDOFF.md` §0). 그라운딩 없이 완주하면 실측 데이터가 무의미해진다.
- 2026-07-25: 이 트래커의 **문서 손상 복구** — 커밋 `c0b47a5f0`(07-22)에서 인코딩 사고로 ENV-3 비고와 S-1~S-7 행 7개가 소실되고(S-8 행이 ENV-3 행에 병합), 결함로그 #6~#9 블록이 인수인계 메모 끝에 중복 붙여넣기 되어 #9 가 최신(MITIGATED)/구버전(OPEN) 두 벌로 공존했다. `ae3d245e8` 기준으로 S-1~S-8 복원, 중복 블록 제거.
- 2026-07-25: **런타임 데이터 재주입 완료** — 마스터데이터 활성 36개·타입 10종(별칭 확정조회 3건 검증: 자용로→EQ-FLASH-01, OEE→ISO-KPI-01, MHP→RM-MHP-001), 지식팩 `core-m3-standards` 문서 11건·**청크 641개**(60MB CPPS PDF만 30MB 제한으로 제외). 검색 거리 0.36~0.52로 컷오프 0.65 이내 = 실제 주입됨.
- 2026-07-25: **⚠️ 지식팩 연결 정책** — 현재 **전 프로젝트가 `knowledge_pack_ids=[]`** 이라 지식허브가 실제로 주입되지 않는다(`get_grounding_context`는 팩 목록이 비면 즉시 빈 문자열 반환). **A-1(단위 변환기)은 의도적으로 미연결 유지** — 제조 표준 지식팩이 오히려 노이즈이고, A-1은 "파이프라인이 끝까지 도는가"의 기준선이기 때문. **그라운딩 효과 실측은 P7 제조 4종에서** 하며, 그때 `PUT /api/v1/factory/projects/{pid}/knowledge`로 `core-m3-standards`를 연결한다. 참고: A-1은 `project_meta.json` 자체가 없어 전부 기본값 폴백 상태다.
- 2026-07-25: **[설계 확정·미착수] 조직·권한·부서게시·전사 표준/검색/시뮬** — 전체 설계 `docs/design_org_permission_enterprise.md`(Phase 0~13). 완주 이후 착수 대상이며, 시나리오 테스트와는 독립.
- 2026-07-25: **전역 규칙 추가 및 라이브러리 자동 게시 체계 도입** — 문의/지시 시 무조건 답변 및 계획 보고 선행 규칙(Immediate Response & Plan First Policy)을 AGENTS.md에 반영. E2E 테스트 드라이버(`run_e2e_scenario.py`)에 전 태스크 완주 직후 결과물 라이브러리에 게시(`POST /{pid}/release`)하는 로직 추가. 이후 모든 테스트는 산출물이 사용자 UI [결과물 라이브러리]에 정상 게시되는 것까지 검증해야 최종 PASS로 판정함.
