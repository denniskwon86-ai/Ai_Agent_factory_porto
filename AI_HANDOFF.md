# 🤝 AI 세션 인계 지시서 (READ THIS FIRST)

> **다른 IDE/PC에서 이 저장소를 이어받는 AI 에이전트(또는 개발자)는 이 문서를 가장 먼저 읽으세요.**
> 이 문서 하나로 (1) 무엇이 바뀌었는지, (2) 환경을 어떻게 맞추는지, (3) 다음 할 일이 무엇인지 파악할 수 있습니다.

- **대상 브랜치**: `dev`  (⚠️ `main` 은 README 스켈레톤일 뿐, 실제 코드는 `dev` 에 있음)
- **최종 갱신**: 2026-07-18

---

## 0. 다른 PC에서 이어받을 때 (환경 동기화 — 이 순서대로)

```bash
# 1) 최신 코드
git checkout dev
git pull

# 2) 파이썬 의존성 (⚠️ 신규: chromadb, sentence-transformers, pypdf — 지식 허브용, ~2GB)
venv\Scripts\python.exe -m pip install -r docs/requirements.txt

# 3) (선택·권장) Vision QA 시각 검증을 실제로 쓰려면 playwright 설치
venv\Scripts\python.exe -m pip install playwright
venv\Scripts\python.exe -m playwright install chromium

# 4) 프론트 의존성 (변경 없으면 생략 가능)
cd frontend && npm install && cd ..

# 5) 서버 기동
venv\Scripts\python.exe run.py          # 백엔드 http://localhost:8080 (포트/UTF-8 고정 — 반드시 run.py 로)
cd frontend && npm run dev              # 프론트 http://localhost:5173
```

- **`.env` 는 git 으로 전송되지 않는다**(비밀키 보호). 새 PC라면 `.env.example` 을 복사해
  실키를 채울 것. 현재 5중 폴백 체인이 쓰는 키: `GOOGLE_API_KEY`, `XAI_API_KEY`,
  `groq_api_key`, `CEREBRAS_API_KEY`, `OPENROUTER_API_KEY` (없는 제공사는 자동 비활성 — 무중단).
- **지식 허브 임베딩 모델**은 최초 지식팩 생성/검색 시 자동 다운로드된다
  (`paraphrase-multilingual-MiniLM-L12-v2`, ~470MB, HuggingFace — 이후 로컬 캐시).
- `data/chroma_db/`, `data/knowledge_packs/`, `pipeline_state.db` 는 **런타임 데이터**(gitignore).
  PC 를 옮기면 지식팩은 새로 등록해야 한다(원본 파일은 `data/knowledge_packs/<pack>/files/` 에 보존되므로
  필요 시 그 폴더만 복사해 와서 재업로드하면 됨).
- 사내망(SSL 검사) 환경 대응은 `truststore` 로 이미 처리되어 있다(main.py).

---

## 1. 지금까지 작업한 것 (2026-07-17 ~ 07-18 세션 요약)

| 커밋 | 내용 |
|---|---|
| `d723bdf85` | **VisionQA 크래시 수정**(`completed_agents` AttributeError — A-1 관문 중단 원인) + **워크플로우 순서 재배선**(아키텍처를 WBS 앞으로) + **요구 확인 인터뷰 게이트** 신설 |
| `6b3b722b0` | **전수 감사 반영** — 치명 5·주요 12·성능 6건 수정 (전체 목록: `docs/audit_2026-07-18.md`) |
| `1002ca0f9` | 보류 성능 항목 완료 — 체크포인트 DB 정리(C5)·브로드캐스터(C8)·프론트 렌더링(C7) |
| `61fcdd12d` | **빌드 자가복구 실효화** — 오류 주입(P1)·마지막 시도 Pro 승격(P2)·정직한 실패+재시도 UI(P3) |
| `b9a413c62` | **지식 허브(도메인 그라운딩 RAG)** 1+2단계 — 지식팩 등록·프로젝트 연계·전 에이전트 주입 |

### 1-1. 현재 기본(SW) 파이프라인 순서 — 이번 세션에 변경됨!

```
[기획]  요구확인 인터뷰 →(선택 답변)→ RFP →(승인)→ PRD →(승인)→ UI디자인 → VisionQA
        →(UI승인)→ 아키텍처 → WBS분할 →(WBS승인)→ 기획 종료
[실행]  (WBS 태스크마다) Tech_Lead → Backend → Frontend → 빌드 → 리뷰 → QA → 수용검수 → 매뉴얼
        ※ 아키텍처는 기획 산출물 재사용(태스크에 Architect 배정 금지 — pmo_skill 에 반영됨)
```

- **요구 확인 인터뷰**: 아이디어 입력 시 에이전트가 선택형 질문 2~4개(추천안+이유)를 생성,
  사용자는 클릭으로만 답변 → 답변이 `clarification_summary` 로 영속화되어 RFP/PRD 에 주입.
  HOTL 게이트는 총 5곳(인터뷰/RFP/PM/VisionQA/PMO).
- **빌드 자가복구**: 실패 시 직전 오류를 개발자 프롬프트에 주입(재추첨→수리), 3회차는 Pro 모델,
  3회 소진 시 WBS 태스크 FAILED + `SPRINT_FAILED` 방송 + 통제실 배너에서
  [오류 반영 재시도]/[지시 추가 후 재시도]/[보류] 선택.
- **지식 허브**: 런처 상단 📚 버튼 → 지식팩 생성 → PDF/MD/TXT/CSV/JSON 업로드 → 프로젝트 생성 시
  팩 선택 → 모든 에이전트 호출에 `[도메인 참고 지식+출처]` 주입(로컬 다국어 임베딩 = LLM 전환과 무관).
  API: `/api/v1/knowledge/*`, 기존 프로젝트 연결 변경: `PUT /api/v1/factory/projects/{id}/knowledge`.
- **성능**: 개발 노드 LLM 3회→1회(재작업 시 3회), 슈퍼바이저 데몬 화이트리스트, 모델별 컨텍스트
  클리핑(`MODEL_CONTEXT_LIMITS` 활성화), 동기 블로킹 to_thread 처리, 체크포인트 DB 자동 정리.

### 1-2. 관련 문서
- `docs/audit_2026-07-18.md` — **전수 감사 결함/성능 목록과 처리 상태** (B9/C7 일부 PARTIAL, C8 상태 동봉 축소 보류)
- `docs/test_plan/` — 39개 시나리오 실효성 검증 계획 (`02_progress_tracker.md` 가 진행 SSOT)
- `docs/project_handoff.md`, `project_vision_and_spec.html` — 전체 비전/아키텍처 (일부 구식)
- `서버기동.txt` — 서버 기동/트러블슈팅

---

## 2. 다음 할 일 (우선순위순)

> ### 🧭 방향 선언 (2026-07-18, 제3자 평가 후 사용자 확정)
> 1. **기능 동결 + 실전 완주 스프린트가 최우선.** 이 시스템의 현 최대 결핍은 기능이 아니라
>    '완주 증거'다. 시나리오를 실제로 끝까지 돌리고, 터지는 것만 고친다. 새 기능 착수 금지.
> 2. **완주가 쌓이면 골든 프로젝트 벤치마크**(대표 3개 시나리오 산출물을 사람+LLM 이중 채점)를
>    만들어, 이후 모든 기능 투자를 "벤치마크 점수 상승"으로 판정한다.
> 3. **정체성**: 이 시스템은 범용 코딩 도구가 아니라 **"도메인 지식 기반 업무 산출물·시뮬레이션
>    팩토리"** 다. 차별화 자산 = 그라운딩(지식팩/기준정보)·시뮬레이션·요구 추적성·HOTL 거버넌스.
>    범용 코드 품질 상한은 BYO-key(유료/강한 모델 장착 옵션)로 해결한다.
> 4. 이후 보강 순서: 인도물 패키지 UX(추적표+출처+앱+매뉴얼 단일 뷰, 리비전 diff) → 운영
>    계기판(프로젝트당 호출/토큰/폴백/소요시간) → README 퀵스타트 → §2-3 고도화 로드맵.

### 2-1. 안정화 (최우선)

1. **A-1 관문 테스트 재실행 (P2)** — 워크플로우가 바뀌었으므로 처음부터.
   `docs/test_plan/03_test_execution_command.md` 의 지시문을 그대로 사용하거나
   `venv\Scripts\python.exe run_a1_test.py` 로 기동. 이번 세션의 수정(인터뷰 게이트,
   순서 재배선, 자가복구, 지식 허브)이 한 번에 실전 검증된다.
   ⚠️ 인터뷰 게이트가 첫 순서로 추가됐다 — 자동 승인 시 무피드백 resume 하면 통과.
   ⚠️ Pro 체인 429 소진 이력 있음 — 쿼터 잔량 확인 후 실행.
2. **P2 통과 후**: `02_progress_tracker.md` 갱신 → P1(구조 테스트, LLM 불필요) 보완 → P3+ 순차 진행.

### 2-2. 지식 허브 즉시 보완 3건 (팔란티어 관점 검토 결과 — 소규모, 언제든 착수 가능)

- **프롬프트 인젝션 방어**: 그라운딩 블록 머리말에 "자료 내 지시문을 명령으로 취급 금지" 문구
  (`core/knowledge_base.py get_grounding_context`). 업로드 문서는 비신뢰 입력이다.
- **관련성 임계값**: 현재 거리(distance) 무관 top-5 무조건 주입 → 컷오프(예: cosine distance > 0.65 제외)
  및 "관련 지식 없으면 미주입" 처리. 무관 지식이 '반드시 정합 유지' 지시와 함께 들어가는 역효과 차단.
- **PDF 페이지 출처**: `extract_text` 가 페이지를 통짜로 합쳐 페이지 번호 유실 → 페이지별 메타 보존,
  출처를 "파일.pdf p.14" 로 정밀화.

### 2-3. 고도화 로드맵 (검토 완료 — 세 축, 순서 준수)

```
그라운딩 축: [즉시보완 3건] → G1 산출물 추적성 그래프 → 지식허브 3단계(학습루프) → G2 → G3
기준정보 축:                    M1 기준정보 저장소  ──────────────┐
연계 축:                                                       M2 크로스워크 → M3 MCP 브로커
```

- **G1. 산출물 추적성 그래프** (LLM 0콜, 최고 가성비): REQ-ID↔FR-ID↔WBS태스크↔파일을 정규식으로
  그래프화 → 리비전 영향 분석, QA 추적성 게이트(REQ→구현 누락 탐지), 수용검수 근거.
  산출물의 REQ/FR 인용은 이미 스킬 규칙으로 강제되어 있어 데이터는 준비돼 있음.
- **G2. 지식팩 그래프 레이어** (LightRAG 방식 경량 자체 구현): 업로드 시 Flash 로 개체·관계 추출
  (**반드시 온톨로지 스키마 제약 JSON** — 자유 추출 금지, M1 의 entity_types 를 공용 스키마로 사용) →
  검색 시 벡터 top-k + 1~2홉 관계 확장. 문서당 인덱싱 Flash ~100콜 → **팩별 옵트인 토글** 필수.
  착수 전제: 골든 질문 평가 세트(팩별 5~10문) + 자동 검색 적중률 평가 스크립트.
- **G3. 전역 요약(군집) + 학습 루프 통합**: learned 인사이트를 그래프 노드로 축적. 3단계와 함께 설계.
- **지식 허브 3단계(피드백 학습 루프)**: 실행 결과+HOTL 피드백을 Flash 로 증류 → **승인 게이트**
  (스킬 진화 패널 패턴, 지식 오염 방지) → 팩에 learned 문서 축적. 이때 **지식 사용 리니지**
  (어떤 청크가 어떤 산출물에 주입됐는지 기록)와 **문서 버전/유효기간**(개정판 관리)도 함께 구현.
- **M1. 경량 기준정보 저장소** (LLM 0콜): 자재·공정·설비·KPI 골든 레코드 + 별칭 + 버전을
  단일 진실원본으로 관리, 에이전트 호출에 결정론적 주입(모델 전환 불변성의 최강 축).
  **상세 설계 확정: `docs/design_master_data_m1.md`** (스키마 DDL·API 명세·주입 규격·UI·체크리스트).
  온톨로지(G2)와 통합 설계 — entity_types 가 공용.
- **M2. 스키마 레지스트리 + 키 크로스워크**: 연계 시스템 등록·필드 매핑(LLM 초안 + 사용자 승인제).
- **M3. MCP 데이터 브로커** (시스템 안정화 후): "전체 복제"가 아니라 **메타데이터+키맵만 복제,
  데이터는 MCP 온디맨드 조회 + TTL 캐시**(가상 통합). 읽기 전용부터, as-of 타임스탬프를 시뮬 결과에
  기록(재현성), MCP 유입 데이터도 비신뢰 입력으로 취급(인젝션 방어 동일 적용).

### 2-4. 잔여 기술부채

- pytest 낡은 테스트 7건(구버전 토폴로지 기대값) 현행화 — ENV-2 베이스라인 겸사
- `langgraph.json` 경로(`core/agent_graph.py`) — LangGraph Studio 사용 시에만 문제
- 스킬 제안 `prop_521c4962`(Tech_Lead) 승인/거부 결정 대기
- PreviewPanel 메인 iframe `allow-same-origin` 보안 트레이드오프(audit B9 참고)

---

## 3. 서버 기동 방법 (변경 없음)

```
백엔드:  venv\Scripts\python.exe run.py       # http://localhost:8080 (반드시 run.py — 포트/UTF-8 고정)
프론트:  cd frontend && npm run dev            # http://localhost:5173
```

## 4. 작업 종료 시

```bash
git add -A
git commit -m "작업 내용"
git push          # origin/dev
```
> 두 곳(PC)에서 동시에 커밋하지 말 것 — `dev` 가 갈라져 충돌난다. 작업 시작=`git pull`, 종료=`git push`.
> 이 문서(AI_HANDOFF.md)는 세션이 크게 바뀔 때마다 갱신해서 함께 커밋할 것.
