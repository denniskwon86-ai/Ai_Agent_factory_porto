# Session Log: 2026-07-24

## 1. 개요
- **목표**: 시스템 안정화, 사용자 효용성 증대 및 시뮬레이션 팩토리의 정밀도 고도화
- **작업자**: Antigravity (AI Agent) / User

## 2. 주요 의사결정 및 작업 내역

### 2.1. 외부 인프라 및 서드파티 스킬 도입 전면 철회
- **배경**: 시스템 성능 고도화를 위해 Mem0, Zep, E2B 샌드박스, Playwright 등의 최신 오픈소스 스킬 도입을 검토함.
- **결론 (Reject)**: 현재 무료 API 쿼터 제약 하에서 토큰 폭발(Token Explosion) 및 LangGraph 상태 충돌(State Collision)을 유발할 위험이 매우 큼. 억지스러운 외부 툴 도입을 전면 백지화하고 **순정 아키텍처(Context Diet, Resume 체계)**의 안정성을 극대화하기로 결정.
- **대안 전략**: 향후 API 한도가 해제될 경우, Microsoft `LLMLingua`(프롬프트 압축)와 AST/Diff 패치(Output 토큰 감축)만을 미들웨어로 제한적 도입 고려.

### 2.2. 글로벌 룰(AGENTS.md) 갱신
- **추가된 정책**: **[Execution & File Modification Policy]**
- **내용**: 에이전트는 파일 수정을 동반하는 어떠한 지시사항이든 무조건 먼저 텍스트나 기획안으로 "무엇을 어떻게 수정할 것인지" 답신하고, **사용자의 명시적 승인(Approve)**을 얻은 후에만 실행해야 함.

### 2.3. 시뮬레이션 에이전트 라인업 고도화 (디지털 트윈화)
- **배경**: 기존 시뮬레이션 템플릿(프롬프트)이 너무 일반적이라 Hallucination(허위 정보) 발생 우려 존재.
- **조치 사항**: 시뮬레이션 팩토리를 관장하는 7종 에이전트의 셋업 문구를 전면 개편.
  - **대상 파일**: `sim_sales.md`, `sim_purchase.md`, `sim_production.md`, `sim_quality.md`, `sim_logistics.md`, `sim_finance.md`, `sim_analysis.md`
  - **핵심 튜닝 포인트**:
    1. **Data Grounding**: 임의의 계산을 금지하고, M1(기준정보) 및 M3(MCP 데이터 브로커)의 수치만을 100% 반영하도록 강제.
    2. **확률론적(Stochastic) 사고**: 단순 산수가 아닌 몬테카를로 기법, 거시경제 변수, 장비 고장률(MTBF) 등을 적용한 Best/Base/Worst 시나리오 산출.
    3. **I/O 워크플로우 릴레이**: 각 에이전트가 앞뒤로 어떤 데이터를 주고받아야 하는지 명세.
    4. **산출물 동적 포맷팅**: 사용자 설정에 맞추되 핵심 정량 지표는 반드시 JSON 또는 테이블 블록으로 강제 덤프.

### 2.4. 유료 LLM API 도입 및 비용 최적화 전략 (2026.07.24 갱신)
- **최신 라인업 적용**: GPT-5.6, Claude Opus 4.8(아키텍트), Claude Fable 5, LG EXAONE(실무) 등 2026년 7월 최신 모델을 투입.
- **OpenRouter 통합**: 각각의 개발자 계정 가입 없이 `OPENROUTER_API_KEY` 단일 계정으로 글로벌 모델 통합 호출 및 과금 일원화 (EXAONE은 별도 가입 가능성 존재).
- **무료 티어(Free Tier) 혼용 최적화**: 팩토리의 `llm_gateway.py`를 통해 단순 검수/로그(전체 비중 40%) 노드는 무료 API(Gemini Free 등)로 라우팅. 
- **효과**: 최고가 모델(GPT-5.6 등)을 메인 두뇌로 쓰면서도 월간 $30(약 4만 원) 수준에서 전체 시뮬레이션 비용을 획기적으로 방어하는 '3-Tier 하이브리드' 아키텍처 확립. (상세 분석 내역은 `docs/cost_estimate_report.md` 참조)

## 3. 다음 세션(Next Session) 진행 방향
- 추가 스킬 도입이나 아키텍처 튜닝은 전면 보류.
- API 쿼터(Quota) 회복 시, 즉각적으로 터미널에서 `python run_e2e_scenario.py test_a1_unitconv --resume` 명령어를 실행하여 A-1 관문 완주 검증 진입.
