# 🤝 AI 세션 인계 지시서 (READ THIS FIRST)

> **다른 IDE/PC에서 이 저장소를 이어받는 AI 에이전트는 이 문서를 가장 먼저 읽으세요.**
> 이 문서 하나로 (1) 방금 무엇이 바뀌었는지, (2) 무엇을 먼저 해야 하는지, (3) 다음 할 일이
> 무엇인지 파악할 수 있습니다.

- **대상 브랜치**: `dev`  (⚠️ `main` 은 README 스켈레톤일 뿐, 실제 코드는 `dev` 에 있음)
- **최신 커밋**: `cb36e4741` — "스킬진화 API·ZIP Export·Cerebras 3중 폴백 + 실효성 테스트 계획"
- **최종 갱신**: 2026-07-15

---

## 0. pull 직후 반드시 실행 (환경 동기화)

```bash
git checkout dev
git pull                                            # 최신 코드
.venv\Scripts\python.exe -m pip install -r docs/requirements.txt   # ⚠️ 신규 의존성(langchain-cerebras)
```

- **`.env` 는 git 으로 전송되지 않는다**(비밀키 보호, .gitignore). 이 PC에 이미 `.env`(실키 포함)가
  있으면 그대로 사용. Cerebras 를 쓰려면 `.env` 에 `CEREBRAS_API_KEY` 추가(선택).
- 프론트 의존성은 이번에 변경 없음 → `npm install` 불필요.
- ⚠️ 비밀키는 반드시 **`.env`(점 있음)** 에만 둘 것. 점 없는 `env` 는 과거 실키가 담겨 유출 위험이
  있었고 현재 `.gitignore` 로 차단돼 있다(추적 안 됨).

---

## 1. 이번 세션에서 바뀐 것 (What changed)

| 영역 | 변경 | 파일 |
|---|---|---|
| **스킬 진화 API** | 승인/거부/목록 엔드포인트 신설(프론트가 호출하던 404 해결) | `api/routes/skill_control.py`, `main.py` |
| 〃 | 폴백 스킬 매핑 버그 수정(`developer_be/fe`→`Backend/Frontend`) | `core/skill_evolution.py` |
| **ZIP Export** | `GET /api/v1/factory/{project_id}/export` (node_modules 등 제외 스트리밍) + 통제실 다운로드 버튼 | `api/routes/factory_control.py`, `frontend/src/components/ControlPanel.tsx` |
| **LLM 3중 폴백** | `Gemini → Groq → Cerebras`(무료 티어). 키/패키지 없으면 자동 비활성(무중단) | `config.py`, `core/llm_gateway.py` |
| **레지스트리 정합성** | `_normalize` 가 템플릿 `id` 스탬프(WorkflowStrip 중복 key 경고 해소), `list_templates` 가 `output_formats.json` 제외 | `core/agent_registry.py`, `frontend/src/components/WorkflowStrip.tsx` |
| **스킬 제안 승인** | 사용자가 승인한 4건 반영(pending→approved, 해당 skills/*.md 에 규칙 추가됨) | `data/skill_proposals/approved/`, `skills/pm_skill.md`·`sim_pm.md`·`tech_lead_skill.md` |
| **보안** | 점 없는 `env` 변형 gitignore 규칙 추가 | `.gitignore` |
| **테스트 계획** | 실효성 검증 문서 4종 신설 | `docs/test_plan/` |

### 검증 완료(UI 확인됨)
- 스킬 진화 패널: 목록 표시 / 승인 / 거부 전 구간 정상
- ZIP Export: 통제실 버튼 → `200 OK`, zip 내용물·제외규칙 확인
- 템플릿 드롭다운에서 `output_formats` 사라짐, WorkflowStrip 중복 key 경고 해소

### 주의: 아직 검증 안 된 것
- **`langgraph.json`** 은 현재 `./agent_graph.py:app` 로 되어 있음(실제 파일은 `core/agent_graph.py`).
  LangGraph Studio 로 직접 여는 경우에만 문제되며, FastAPI 런타임에는 영향 없음. (수정할지는 사용자 결정)

---

## 2. 다음 할 일 (Next: 실효성 검증 테스트)

이 저장소의 핵심 미완 작업은 **"플랫폼이 실제로 쓸 만한가"를 검증하는 전수 테스트**다.
계획과 진행 상태가 아래 문서에 이미 준비돼 있다:

- `docs/test_plan/00_master_plan.md` — 마스터플랜(11 Phase, 30점 루브릭, 리스크)
- `docs/test_plan/01_scenario_catalog.md` — **39개 시나리오의 실제 입력 데이터**(그대로 투입 가능)
- `docs/test_plan/02_progress_tracker.md` — **진행 현황판(SSOT)** — 매 시나리오 완료 시 갱신
- `docs/test_plan/03_test_execution_command.md` — 실행 지시문(복사·붙여넣기용)

### 테스트를 이어가려면
1. `docs/test_plan/02_progress_tracker.md` 를 읽어 현재 어디까지 됐는지 파악.
2. `IN_PROGRESS` 또는 첫 `PENDING` Phase 부터 진행.
3. 시나리오 1건 끝날 때마다 tracker 를 **즉시 갱신**(끊겨도 이어갈 수 있도록).
4. **P2(파일럿)가 관문** — 실패 시 P3+ 중단하고 원인부터 수정.

> ⚠️ **P2 이후(실제 파이프라인 실행)에는 유효한 LLM 키가 필수**다. `.env` 의
> `GOOGLE_API_KEY`/`groq_api_key`(선택 `CEREBRAS_API_KEY`)가 실제 값인지 먼저 확인할 것.

---

## 3. 서버 기동 방법

```
백엔드:  .venv\Scripts\python.exe run.py      # http://localhost:8080 (포트/UTF-8 고정)
프론트:  cd frontend && npm run dev            # http://localhost:5173
```
- 반드시 `run.py` 로 백엔드 기동(포트 8080 + UTF-8 강제). 직접 `uvicorn` 실행 시 과거 포트/인코딩
  장애 이력 있음(자세한 건 `서버기동.txt`).

---

## 4. 더 넓은 컨텍스트

- `docs/project_handoff.md` — 프로젝트 전체 비전·아키텍처·기능 설계
- `project_vision_and_spec.html` — 제품 비전 문서
- `서버기동.txt` — 서버 기동/트러블슈팅 매뉴얼

---

## 5. 작업 종료 시

```bash
git add -A
git commit -m "작업 내용"
git push          # origin/dev 로 자동 push (로컬 dev 가 origin/dev 추적 중)
```
> 두 곳(PC)에서 동시에 커밋하지 말 것 — `dev` 가 갈라져 충돌난다. 작업 시작=`git pull`, 종료=`git push`.
