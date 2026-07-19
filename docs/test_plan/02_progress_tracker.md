# 테스트 진행 트래커 (SSOT — 시나리오 완료 시마다 즉시 갱신)

> 재개 방법: 새 세션에서 **"docs/test_plan/02_progress_tracker.md 읽고 테스트 이어서 진행해줘"**
> 상태: `PENDING`(대기) / `IN_PROGRESS`(진행 중) / `PASS` / `COND`(조건부) / `FAIL` / `DEFERRED`(쿼터 등으로 연기) / `SKIP`

## 전체 현황

| Phase | 상태 | 완료/전체 | 비고 |
|---|---|---|---|
| P0 사전 점검 | IN_PROGRESS | 2/3 | 실 API 키 확보 및 백엔드 가동 완료 |
| P1 구조 테스트 | PENDING | 0/8 | LLM 불필요 — 키 없이도 진행 가능 |
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
| ENV-2 | PENDING | — | | |
| ENV-3 | PASS | — | 2026-07-16 | 백엔드(8080)/프론트(5173) 정상 동작 |
| S-1 | PENDING | — | | |
| S-2 | PENDING | — | | |
| S-3 | PENDING | — | | |
| S-4 | PENDING | — | | |
| S-5 | PENDING | — | | |
| S-6 | PENDING | — | | |
| S-7 | PENDING | — | | |
| S-8 | PENDING | — | | |
| A-1 | IN_PROGRESS | — | 2026-07-16 | 🚧 관문 시나리오 실행 중 |
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

## 발견된 결함 로그

| # | 발견 시나리오 | 심각도 | 내용 | 상태 |
|---|---|---|---|---|
| 1 | A-1 | Critical | VisionQA가 `ProjectState`에 없는 `completed_agents` 필드 접근 → `AttributeError`로 파이프라인 중단 (nodes/vision_qa.py, 커밋 b5b8407에서 유입) | **FIXED** (2026-07-17, 통과 시 `reviewer_decision` 미초기화로 인한 UIDesigner 무한왕복 잠재결함도 함께 수정) |
| 2 | A-1 | Major | 워크플로우 순서 결함: 아키텍처가 WBS 분할 *이후* 실행 태스크 안에서 수립되어 WBS가 설계 없이 작성됨 (스킬제안 prop_521c4962가 자가 진단한 정합성 오류의 근원) | **FIXED** (2026-07-17, B안: RFP→PRD→UI→VisionQA→**Architect**→WBS 로 재배선. agent_graph/planning/execution/registry/pmo_skill/프론트 2종 수정, 라우터 테스트 37건 통과) |
| 3 | A-1 | Minor | `playwright` 미설치로 VisionQA 스크린샷 캡처가 항상 생략됨(시각 검증 실효성 없음) | OPEN — `pip install playwright && playwright install chromium` 필요 |
| 4 | ENV-2 | Minor | pytest 기존 실패 7건(구버전 토폴로지 기준의 낡은 기대값: interrupt 2개 가정 등) — 이번 변경과 무관하게 HEAD에서도 동일 실패 확인 | **FIXED** (2026-07-19 어서션 현행화 + 형제 리포 pyc 캐시 오염 제거 → **전 스위트 155건 통과 = ENV-2 베이스라인**) |
| 5 | A-1 4차 | Major | `hotl/check` 가 PLANNING_* 태스크의 HOTL 대기를 미감지(SSE 유실 시 기획 게이트 복구 불가) | **FIXED** (latest_state 의 현재 태스크로도 확인) |
| 6 | A-1 4차·AABB | Critical | WBS 분할 결과가 빈 태스크로 저장되고 게이트 통과 → 기획이 '완료된 척' 정지 (non-greedy JSON 절단 + 빈 결과 무방어) | **FIXED** (파싱 견고화+1회 재시도+빈 WBS 저장 금지) + **복구 수단 신설**(`wbs/replan` API·UI 버튼) |
| 7 | A-1 2차 | Major | `run.py` reload=True 가 .py 저장 시 서버 재시작 → 실행 중 스프린트 스트림 사망 | **FIXED** (운영 모드 기본 reload OFF, `--dev` 옵트인) |
| 8 | 환경 | Major | 프로바이더 패키지 설치가 langchain-core 를 0.3 으로 다운그레이드시켜 gemini/groq 임포트 파손. langchain-cerebras 는 core 1.x 미지원 | **FIXED** (core 1.x 정렬, Cerebras 는 OpenAI 호환 API 로 전환 — 5중 폴백 전부 활성) |

## 세션 인수인계 메모

- 2026-07-16: 새 LLM 라우팅 체인(OpenRouter, xAI 등) 적용 완료 후 ENV-1 정상 동작 확인됨. 
- 2026-07-16: A-1(test_a1_unitconv) 테스트 데이터를 생성하여 초기 스프린트 백엔드에서 가동 중.
- 2026-07-17: A-1이 RFP(1.0)→PRD(0.963)→UI_DESIGN(1.0) 통과 후 VisionQA에서 결함 #1로 크래시. 결함 #1·#2 수정 완료(미커밋). **워크플로우가 바뀌었으므로 A-1은 처음부터 재실행 필요**(sprint_init 재가동 시 자동 아카이브됨). Pro 체인 전 제공사 429 소진 이력 있음 → 쿼터 잔량 확인 후 재실행 권장.
- 2026-07-18: **신규 기능 — 요구 확인 인터뷰 게이트** 추가(미커밋). PLANNING 진입 시 `Requirement_Interviewer`가 선택형 질문 2~4개 생성 → HOTL 게이트(질문 카드 UI, 추천안 기본 선택) → 답변이 RFP/PRD에 주입. 기본 파이프라인이 **CLARIFICATION → RFP → PRD → UI → VisionQA → ARCHITECTURE → WBS** 로 변경됨. HOTL 게이트 5곳(인터뷰/RFP/PM/VisionQA/PMO). ⚠️ 테스트 시나리오의 HOTL 자동 승인 절차에 인터뷰 게이트 1회 추가 반영 필요(무피드백 resume 시 추천안 없이 아이디어만으로 RFP 진행되므로, 자동화 시엔 그냥 resume 하면 됨).
