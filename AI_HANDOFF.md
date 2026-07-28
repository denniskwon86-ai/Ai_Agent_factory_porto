# 🤝 AI 세션 인계 지시서 (READ THIS FIRST)

> **다른 IDE/PC에서 이 저장소를 이어받는 AI 에이전트(또는 개발자)는 이 문서를 가장 먼저 읽으세요.**
> 이 문서 하나로 (1) 무엇이 바뀌었는지, (2) 환경을 어떻게 맞추는지, (3) 다음 할 일이 무엇인지 파악할 수 있습니다.

- **대상 브랜치**: `dev`  (⚠️ `main` 은 README 스켈레톤일 뿐, 실제 코드는 `dev` 에 있음)
- **최종 갱신**: 2026-07-27

## 📖 제품의 장기 기준 문서

구현·설계·우선순위를 판단하기 전에 다음 두 문서를 함께 읽습니다.

- **[docs/AI_FACTORY_STUDIO_PRODUCT_BIBLE.md](docs/AI_FACTORY_STUDIO_PRODUCT_BIBLE.md)**: 제품의 존재 이유, 시장 가설, 핵심 사상, 비협상 원칙, 팀 협업 헌장
- **[docs/LLM_MASTER_IMPLEMENTATION_SPEC_2026-07-28.md](docs/LLM_MASTER_IMPLEMENTATION_SPEC_2026-07-28.md)**: To-Be 기능 명세, 데이터 모델, API 초안, 단계별 수행계획

두 문서는 목표 설계를 담고 있습니다. 현재 구현 여부는 As-Is 설계서와 최신 handoff를 우선 확인하고, 목표 기능을 이미 구현된 것으로 취급하지 마세요.

> **팀 역할 규약**: [`.agents/AGENTS.md`](.agents/AGENTS.md) — 사용자·Claude Code·Codex·Antigravity 4인 팀의 역할 헌장과 겹치는 구간의 합의가 여기 있습니다. 작업 착수 전에 "이 작업이 내 영역인가"를 먼저 확인하세요.
> **Enterprise Context 선행 규칙**: [`docs/design_enterprise_context_master.md`](docs/design_enterprise_context_master.md) — 이후 구현되는 모든 기능은 `tenant → 기업집단 → 법인 → 사업부 → 사업장/공장` 문맥과 실제/가상/경쟁사 상태를 명시적으로 가져야 합니다.

---

## 🧭 2026-07-29 — 기준정보 시드·주입 경로 정상화 (최신 세션)

> ### 👉 **[docs/handoff_2026-07-29_master_seed_and_injection.md](docs/handoff_2026-07-29_master_seed_and_injection.md)**
>
> M1~M4 기준정보를 실제 저장소에 적재하고 조직 범위에 묶었다(감사 `ENTERPRISE-01` Action 1 종결).
> 그 과정에서 **주입 경로의 결함 3건**을 실측으로 발견해 함께 고쳤다 — 세 건 모두
> **테스트는 통과하고 있었다.**
>
> 1. **주입 상한 12건이 산식을 잘라내고 있었다** — 배터리소재는 적용 가능 30건 중 12건만
>    주입되고 잘린 18건에 표준원가 산식·MPS·라우팅·배출계수·시뮬 확률분포가 전부 포함됐다.
>    → **전수 주입으로 전환**(D-010). 상한 12건은 2026-07-22 에 근거 없이 임의로 고른 값이었다.
> 2. **별칭 히트 경로가 죽어 있었다** — 문서 정식명 `"… (MHP)"` 를 그대로 별칭에 써서 단어경계
>    매칭이 44건 전부 실패했다. → `derive_aliases()`(D-011).
> 3. **재시드가 격리를 조용히 무너뜨렸다** — 미바인딩 레코드가 전사 공통으로 통과해 모든 조직에
>    노출됐다(실측 26 < 45). → 44/44 복구.
>
> **잔여 작업과 전체 진척(약 60% 잔여)은 그 문서 §4 에 정리돼 있습니다.**
> pytest 709 통과 · 커밋 `34a3e8a37`.

---

## 📮 Codex 앞 인계 — 프론트엔드 변경 통지 (2026-07-28, Claude Code)

역할 규약상 UI/UX·프론트엔드는 Codex 담당인데, 백엔드 API 계약 변경 때문에 **사전 통지 없이 프론트를 직접 수정한 건이 1건** 있습니다. 되돌릴 필요는 없다고 판단했지만 검토·재설계 대상으로 남깁니다.

**[frontend/src/components/TelemetryPanel.tsx](frontend/src/components/TelemetryPanel.tsx)** (커밋 `4cfb4b45a`, P0 「비용 관측」)

- **왜 손댔나**: `GET /api/v1/telemetry/projects` 응답이 `string[]` → 객체 배열(`{project, project_id, owner_dept_id}`)로 바뀌어 기존 `<option>` 렌더링이 깨졌습니다. 부서 스코프를 도입하려면 이름만으로는 부족했습니다.
- **함께 넣은 것**: 비용 KPI 타일(미산정이 있으면 `≥` 접두로 **하한**임을 표시), 비용 산정 근거 분포(무료티어/캐시적중/유료/단가일부/**미산정**을 분리 — "무료라서 0"과 "몰라서 0"을 사람이 구분해야 함), 권한 범위·제외 건수 표기, 스테일 주석 "토큰 계측은 v2 예정" 제거(토큰은 이미 수집 중).
- **Codex 검토 요청 사항**: ① 비용 하한 표기(`≥ $4.5558`)가 경영 보고 화면에서 오해 없이 읽히는지 ② 미산정 경고의 시각적 위계가 적절한지 ③ 부서 필터 UX를 셀렉트가 아닌 다른 형태로 갈 필요가 있는지.
- **API 계약 참고**: `/summary` 응답에 `by_cost_basis`, `by_provider`, `totals.cost_complete`, `totals.unpriced_calls`, `permission{scope, excluded_unattributed, excluded_other_dept}` 가 추가되어 있습니다.

이후 백엔드 계약 변경 시에는 **먼저 통지하고 프론트 수정은 Codex 에 넘기겠습니다.**

---

## 🏁 2026-07-27 — A-1 관문 시나리오 **완주 달성 (PASS)**

> `test_a1_v11` / 14분 / 6개 태스크 전부 DONE · QA PASS · 수용검수 PASS · 게시 완료
> `release_id: test_a1_v11_20260727_170122`
>
> **이 프로젝트 최초의 완주 사례입니다.** `docs/business_value_assessment.md` 가
> *"설계는 시장의 빈 자리를 정확히 겨눴으나 된다는 증거가 하나도 없다"* 며 우선순위 1번으로
> 지목한 **"실제 업무 1건 완주 + 게시"** 가 이것입니다.
>
> ⚠️ 이 PASS 는 `best-effort PASS` 를 제거한 뒤의 결과라 **가짜 통과가 아닙니다.**
> 상세: [docs/test_plan/02_progress_tracker.md](docs/test_plan/02_progress_tracker.md) 의
> "2026-07-27 A-1 완주" 절 — 완주까지 제거한 병목 8건과 교훈이 기록돼 있습니다.
>
> **다음 과제**: 완주 재현성 확인(2회차) → P3 SW 다양화 → 그 뒤에 조직·권한 설계 착수
> (기간계 설계서의 게이트 G0 이 "A-1 완주 실측"이었고, 이제 해제되었습니다).

---

## ⚡ 진행 이력 — 배경이 필요하면 읽으세요

> ### 👉 **[docs/handoff_2026-07-27_b_fix14_and_next.md](docs/handoff_2026-07-27_b_fix14_and_next.md)** ← 최신 (결함 14건 수정 완료, 남은 과제 1건)
>
> 그 다음 아래 문서(오전 조사 — **실제로 사고가 났던 함정 6가지**가 여기 있습니다):
>
> ### 👉 **[docs/handoff_2026-07-27_a1_completion.md](docs/handoff_2026-07-27_a1_completion.md)**
>
> **A-1 관문 시나리오(단위 변환기) 완주 작업이 진행 중입니다.** 프로젝트 `test_a1_v3` 에서
> E2E-01 `DONE` / E2E-02 진행 중 / E2E-03~05 대기 상태이며, **서버와 드라이버가 실행 중일 수 있습니다.**
>
> 그 문서에는 이어받는 절차, 실행 중 프로세스·로그 경로, 그리고 **실제로 사고가 났던 함정 6가지**가
> 정리되어 있습니다. 특히 다음 세 가지는 모르고 건드리면 바로 사고가 납니다:
>
> 1. **Python 은 반드시 PowerShell + `.\venv\Scripts\python.exe` 로 실행** — Bash 샌드박스가 네이티브 `.pyd` 를 막아 pytest 가 전부 깨진 것처럼 보입니다.
> 2. **포트 8080 은 단일** — 서버를 재시작하면 다른 환경이 돌리던 스프린트가 죽습니다(실제 발생).
> 3. **`--resume` 는 재작업 예산(`supervisor_hops`)을 복구하지 못합니다** — 수정 효과를 검증하려면 새 태스크/새 프로젝트에서 확인하세요.
>
> **A-1 완주 전에는 조직·권한 설계나 기간계 설계의 구현을 시작하지 마세요** —
> `docs/business_value_assessment.md` 의 우선순위 1번이 "실제 업무 1건 완주 + 게시" 입니다.

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

# 6) ⚠️ 런타임 데이터 재주입 (PC 를 옮겼다면 필수 — 백엔드가 떠 있는 상태에서)
venv\Scripts\python.exe scripts\api_data_loader.py       # 마스터데이터 M1~M4 → 골든레코드 36개
venv\Scripts\python.exe scripts\api_knowledge_loader.py  # 지식팩 core-m3-standards (PDF 8종, ~10분)
```

### 0-1. ⚠️ PC 를 옮기면 데이터가 따라오지 않는다 (2026-07-25 실측 확인)

`data/master/`·`data/knowledge_packs/`·`data/chroma_db/` 는 전부 **gitignore 런타임 데이터**다.
새 PC에서 `git pull` 만 하면 마스터데이터 **0건**, 지식팩 **0건** 상태이며, 이 상태로 시나리오를
돌리면 **그라운딩 없이 완주**하게 되어 실측 데이터가 무의미해진다. 주입 여부는 이렇게 확인한다:

```bash
curl http://localhost:8080/api/v1/master/records    # data:[] 이면 미주입
curl http://localhost:8080/api/v1/knowledge/packs   # data:[] 이면 미주입
```

원본(JSON 4종 `docs/master_data/`, PDF `docs/reference/`)과 로더는 커밋돼 있으므로 위 6) 재실행으로
복원된다. 두 로더 모두 **LLM 0콜**(마스터데이터는 REST, 지식팩은 로컬 임베딩)이라 쿼터를 쓰지 않는다.
임베딩 모델은 HuggingFace 캐시에 없으면 최초 1회 ~470MB 자동 다운로드된다.

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

## 1. 지금까지 작업한 것

### 1-A. 2026-07-17 ~ 07-18 세션 요약

| 커밋 | 내용 |
|---|---|
| `d723bdf85` | **VisionQA 크래시 수정**(`completed_agents` AttributeError — A-1 관문 중단 원인) + **워크플로우 순서 재배선**(아키텍처를 WBS 앞으로) + **요구 확인 인터뷰 게이트** 신설 |
| `6b3b722b0` | **전수 감사 반영** — 치명 5·주요 12·성능 6건 수정 (전체 목록: `docs/audit_2026-07-18.md`) |
| `1002ca0f9` | 보류 성능 항목 완료 — 체크포인트 DB 정리(C5)·브로드캐스터(C8)·프론트 렌더링(C7) |
| `61fcdd12d` | **빌드 자가복구 실효화** — 오류 주입(P1)·마지막 시도 Pro 승격(P2)·정직한 실패+재시도 UI(P3) |
| `b9a413c62` | **지식 허브(도메인 그라운딩 RAG)** 1+2단계 — 지식팩 등록·프로젝트 연계·전 에이전트 주입 |

### 1-B. 그 이후 (2026-07-19 ~ 07-24 — 커밋 62건)

| 일자 | 내용 |
|---|---|
| 07-19 | 버그 일괄 수정(§2-2), **G1 추적성 엔진 착수**(`0467c7d42`), **쿼터 소진 서킷 브레이커 + Suspension UI**(`60d14eace`) |
| 07-20 | **G1 추적성 엔진 완성**(`4a520f846` REQ↔FR 링크·커버리지 게이트·수용검수 근거) + **G1-4 리비전 영향 분석**(`8fcea5a46`) + **FinOps 리스크 분석기**(`974b9eee2` 변경분 정적 위험도 → 리뷰 자동승인/정밀검토) — **셋 다 LLM 0콜**. 품질 게이트 fail-loud 전환 + 심판 앵커링 + **LLM 텔레메트리**(`b7dc409f9`) |
| 07-21 | **LOW_QUOTA_MODE**(`c99925186`), per-model 쿨다운·폴백 정제(`5f89ec974`), **운영 계기판(텔레메트리 뷰어)**(`ee5eb15f4`), 토큰 실측 v2 + 실행단계 컨텍스트 다이어트(`8cf42e558`), `JUDGE_FORCE_HEAVY` 되돌림 + WBS 태스크 크기 결정론 게이트(`0ad0f80e6`) |
| 07-22 | **[M1] 기준정보 저장소**(`169612ccc` 백엔드+결정론 주입, `468c31487` UI), **[M2] 스키마 레지스트리+크로스워크**(`fa802c706`), **[M3] MCP 데이터 브로커**(`b05243239` 백엔드, `6cf3b87ba` 실측 병기 토글 기본 off), **골든 벤치마크 프레임워크**(`dc1a1ca50` 3축 채점·스코어카드·회귀비교), **v1 Exact Hash Cache**(`f9e3dcfc5`), **SUSPENDED_QUOTA 중단지점 resume**(`e205eaceb`), 토론 다양성 캐시 게이트(`193a7cef8`) |
| 07-23 | 결함 #10 UI_DESIGN HOTL 무한루프 수정(`484ecb19a`), 지식허브 추가 업로드 임베딩 충돌 수정(`42cc2b8c1`), **VisionQA 차단 게이트 → 자문(advisory) 강등**(`e8f5e3837`) |
| 07-24 | **한국어 전용 전역 정책 강제**(`b8baf39ab`), **시뮬 에이전트 7종 프롬프트 디지털 트윈 수준 고도화**(`5fbbd9330`), **디지털 트윈 마스터데이터 M1~M4 구축**(`40fd76ae9` 외부 세션), 3-Tier 비용 추산 보고서(`2b8c93b01`), **마스터데이터 정규화 주입 로더 재작성**(`94d6edc19` 통짜 주입 → 항목당 개별 골든레코드, 활성 5→36개) |

> **정체성 변화**: 07-24 를 기점으로 이 시스템은 "SW 팩토리"가 아니라
> **"디지털 트윈 제조 시뮬레이션 팩토리"** 로 구체화됐다(시뮬 스킬 고도화 + M1~M4 제조 마스터데이터).

- **신규 코어 모듈**: `core/master_data.py`(M1) · `core/crosswalk.py`(M2) · `core/mcp_broker.py`(M3) ·
  `core/golden_benchmark.py` · `core/risk_analyzer.py` · `core/cache_manager.py`
- **신규 API**: `master_control` · `crosswalk_control` · `mcp_control` · `benchmark_control` ·
  `telemetry_control` · `format_control` (`api/routes/`)
- **신규 UI 패널**: `MasterDataPanel` · `CrosswalkPanel` · `TelemetryPanel` · `TraceabilityGraph` ·
  `KnowledgeHubPanel` · `FormatMasterPanel` · `MegaBoardroomPanel` (`frontend/src/components/`)
- **관련 설계 문서**: `docs/design_master_data_m1.md` · `m2.md` · `m3.md` ·
  `docs/design_debate_diversity_cache.md` · `docs/directives/2026-07-20_fail-loud_judge-anchor_telemetry.md` ·
  **`docs/design_org_permission_enterprise.md`**(조직·권한·부서게시·전사 데이터표준/검색/시뮬 — 설계 확정, **미착수**)
- **세션 로그**: `docs/session_log_2026-07-21.md` ~ `2026-07-24.md`, `docs/cost_estimate_report.md`

### 1-1. 현재 기본(SW) 파이프라인 순서 (2026-07-25 코드 대조 확인)

```
[기획]  요구확인 인터뷰 →(선택 답변)→ RFP →(승인)→ PRD →(승인)→ UI디자인 → VisionQA
        →(UI승인)→ 아키텍처 → WBS분할 →(WBS승인)→ 기획 종료
[실행]  (WBS 태스크마다) Tech_Lead → Backend → Frontend → 빌드 → 리뷰 → QA → 수용검수 → 매뉴얼
        ※ 아키텍처는 기획 산출물 재사용(태스크에 Architect 배정 금지 — pmo_skill 에 반영됨)
```

- **요구 확인 인터뷰**: 아이디어 입력 시 에이전트가 선택형 질문 2~4개(추천안+이유)를 생성,
  사용자는 클릭으로만 답변 → 답변이 `clarification_summary` 로 영속화되어 RFP/PRD 에 주입.
  HOTL 게이트는 총 5곳(인터뷰/RFP/PM/VisionQA/PMO).
- ⚠️ **VisionQA 는 2026-07-23 부로 차단 게이트가 아니라 '자문(advisory)'** (`e8f5e3837`).
  UI 를 자동 반려하지 않고 소견(`ui_review_advisory`)만 남기며, 재설계 여부는 사람이 미리보기를 보고
  판단한다(`route_from_vision_qa` 는 `needs_revision` 일 때만 UIDesigner 로 되돌림). 이전의
  UI_DESIGN↔VisionQA 왕복(각 ~5콜)이 무료 티어 일일 요청수를 소진하던 병목을 제거한 조치다.
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

> ### 🧭 방향 보정 (2026-07-24, 사용자 확정)
> **"무료 최적화는 중단하고, 유료/큰 모델로 일단 완주한다."** 미검증 시스템에 최적화를 얹는 건
> 순서 오류다 — 완주 데이터가 벤치마크·병목·품질 판단 전부의 선행조건이다. 무료 티어의 일일
> 요청수(RPD)를 '진짜' 줄이는 수단은 캐싱·중단지점 resume·로컬 추론뿐이며(07-24 리서치 결론),
> 이들은 완주 실측 이후에 취사선택한다. 상세: `docs/session_log_2026-07-24.md` §B.

### 2-1. 안정화 (최우선)

0. **런타임 데이터 재주입 확인** (§0-1) — PC 를 옮겼다면 시나리오 실행 **전에** 반드시.
   마스터데이터·지식팩이 비어 있으면 그라운딩 없이 완주하게 되어 실측이 무의미하다. LLM 0콜.
1. **완주용 유료/무제한 모델 1종 게이트웨이 장착** — EXAONE(FriendliAI·Together, 둘 다 OpenAI
   호환이라 기존 게이트웨이에 반나절) 또는 A급 1종. 무료 RPD 한계가 A-1 완주를 막는 최종 병목이다.
2. **A-1 관문 테스트 완주 (P2)** — 지금 가장 중요한 단일 행동.
   `docs/test_plan/03_test_execution_command.md` 의 지시문을 그대로 사용하거나
   `venv\Scripts\python.exe run_a1_test.py` 로 기동. 중단분이 있으면 `--resume`(중단지점 재개,
   `e205eaceb`)로 이어붙일 수 있다.
   ⚠️ 인터뷰 게이트가 첫 순서다 — 자동 승인 시 무피드백 resume 하면 통과.
   ⚠️ VisionQA 는 이제 자동 반려하지 않는다(자문) — UI 재설계는 사람이 미리보기 보고 판단.
3. **완주 후**: `02_progress_tracker.md` 의 A-1 벤치마크 표(리드타임/자가복구/토큰/HOTL 피로도)를
   실측으로 채움 → 골든 벤치마크(`core/golden_benchmark.py`)로 산출물 채점 → 그 다음에야
   최적화 도구 취사선택(`docs/session_log_2026-07-24.md` §B-1 카탈로그) → P3+ 순차 진행.
4. (미세) 마스터데이터 `is_core` 선별 조정 — 현재 설비 전체가 core + 광범위 `manufacturing` 태그라
   관련성 낮은 core 가 함께 주입되는 경향. 완주 데이터 확인 후 조정.

### 2-2. ✅ 완료(2026-07-19): 버그·미구현 일괄 수정 (부분 점검 세션)

- 지식 허브 즉시 보완 3건 완료: 인젝션 방어 문구 / 관련성 임계값(distance>0.65 컷, 없으면 미주입) /
  PDF 페이지 출처("파일.pdf p.N")
- **WBS 재분할 수단 신설**: `POST /{pid}/wbs/replan` + 통제실 "🔁 WBS 재분할" 버튼 —
  기획 산출물 재사용, Master_PMO 만 재실행 (REPLAN_* 라우팅)
- **WBS 빈 결과 결함 수정**: non-greedy 파싱 → 전체 loads+greedy, 빈 결과 1회 재시도, 빈 WBS 저장 금지
- **슈퍼바이저 자비스화**: 태스크 없이 시스템 전역 대화 + 실시간 현황 브리핑 동봉
- **run.py 운영 모드 기본**(reload OFF — reload 는 .py 저장 시 실행 중 스프린트를 죽임). 개발 시 `--dev`
- 기동 시 그래프 워밍업(재시작 후 첫 호출 수십 초 지연 제거), `langgraph.json` 경로 수정
- **hotl/check 가 PLANNING_* 태스크 미감지하던 결함 수정**(기획 게이트 SSE 유실 복구 불가였음)
- **LLM 프로바이더 정렬**: langchain-core 1.x 로 통일. ⚠️ langchain-cerebras 는 core 1.x 미지원이라
  제거 — Cerebras 는 `langchain-openai` 의 OpenAI 호환 API(base_url)로 호출. 5중 폴백 전부 활성
- **pytest 전 스위트 155건 통과**(스테일 테스트 7건 현행화 + 형제 리포에서 복사된 tests/__pycache__
  오염 제거 — pyc 캐시가 남의 리포 코드를 실행하고 있었음). ENV-2 베이스라인 확보

### 2-3. 고도화 로드맵 (세 축 — ✅ 는 2026-07-25 기준 구현 완료)

```
그라운딩 축: [즉시보완 3건]✅ → G1 산출물 추적성 그래프✅ → 지식허브 3단계(학습루프)❌ → G2❌ → G3❌
기준정보 축:                    M1 기준정보 저장소✅  ──────────────┐
연계 축:                                                       M2 크로스워크✅ → M3 MCP 브로커✅
```

> **남은 미착수: 지식 허브 3단계(피드백 학습 루프) · G2 · G3 · 조직/권한/전사 축.** 단 방향
> 선언(§2 서두)에 따라 **A-1 완주 전까지 신규 기능 착수 금지** — 완주·벤치마크 이후 재판정한다.
>
> **[신규 축, 2026-07-25 설계 확정·미착수] 조직 구성 · 권한 · 부서별 게시 · 전사 데이터 표준 ·
> 전사 검색 · 전사 시뮬레이션 · 경영진 총괄** — 전체 설계는
> **`docs/design_org_permission_enterprise.md`** (Phase 0~12, 재사용 자산·테스트·리스크 포함).
> **[신규 축, 2026-07-26 구상 확정·미착수] 기간계 업무시스템 전환** —
> **`docs/design_backbone_system_platform.md`**. ERP/MES 급, 즉 여러 주체가 동시·순차로 입력하고
> 상호 연계해 종합 계산하는 시스템을 만들 수 있는가의 문제. **결론: 지금은 불가하며 이유가 구조적이다.**
> ⚠️ 이 문서가 위 조직·권한 설계의 전제 하나를 뒤집는다 — **"한 판 DB"는 팩토리의 데이터였고,
> 생성된 앱들의 업무 데이터는 존재하지 않는다**(앱 백엔드는 스모크 검사 후 버려지고 DB가 만들어진 적 없음).
> 로드맵 ①읽기연계(MCP 어댑터 재사용) → ②작업지시 인박스 → ③공용 쓰기 저장소 → ④워크플로 엔진,
> 권한 확장은 병행. 착수 게이트 G0(A-1 완주)·G1(앱 런타임)·G3(표준 실질 작동)를 지킬 것.
>
> 요지: 인증은 경량 사용자 전환(SSO 교체 가능), 권한은 백엔드 강제, 부서는 **기준정보로 관리**
> (하드코딩 맵 3개 삭제), 데이터 표준은 **생성 시 권장 / 게시 시 정합화 / DA 정기 배치**,
> 권한 축은 `executive`⟂`admin`⟂`DA` 3분리. 데이터 카탈로그는 **M2 스키마 레지스트리 재사용
> (신규 테이블 0)**. 전사 단일 시뮬 실행 엔진은 `domain_agents` 필터 덕에 **코드 변경 0**.
>
> 완료 항목의 현재 진입점: 마스터데이터 `MasterDataPanel`+`/api/v1/master/*`, 크로스워크
> `CrosswalkPanel`+`/api/v1/crosswalk/*`, MCP 브로커 `/api/v1/mcp/*`(실측 병기 토글 **기본 off**),
> 추적성 `TraceabilityGraph`, 벤치마크 `/api/v1/benchmark/*`, 텔레메트리 `TelemetryPanel`.

- ✅ **G1. 산출물 추적성 그래프** — 완료(`4a520f846`, 리비전 영향 분석 `8fcea5a46`).
  (LLM 0콜, 최고 가성비): REQ-ID↔FR-ID↔WBS태스크↔파일을 정규식으로
  그래프화 → 리비전 영향 분석, QA 추적성 게이트(REQ→구현 누락 탐지), 수용검수 근거.
  산출물의 REQ/FR 인용은 이미 스킬 규칙으로 강제되어 있어 데이터는 준비돼 있음.
  ※ 사용자 기획서(proposals/implementation_plan_finops.md 1단계 '추적성 엔진')와 동일 목표 —
  G1 로 병합, 코드 뷰어 라인 클릭 시 근거(주입 기준정보·REQ) 표시 UI 를 범위에 포함.
- **G2. 지식팩 그래프 레이어** (LightRAG 방식 경량 자체 구현): 업로드 시 Flash 로 개체·관계 추출
  (**반드시 온톨로지 스키마 제약 JSON** — 자유 추출 금지, M1 의 entity_types 를 공용 스키마로 사용) →
  검색 시 벡터 top-k + 1~2홉 관계 확장. 문서당 인덱싱 Flash ~100콜 → **팩별 옵트인 토글** 필수.
  착수 전제: 골든 질문 평가 세트(팩별 5~10문) + 자동 검색 적중률 평가 스크립트.
- **G3. 전역 요약(군집) + 학습 루프 통합**: learned 인사이트를 그래프 노드로 축적. 3단계와 함께 설계.
- **지식 허브 3단계(피드백 학습 루프)**: 실행 결과+HOTL 피드백을 Flash 로 증류 → **승인 게이트**
  (스킬 진화 패널 패턴, 지식 오염 방지) → 팩에 learned 문서 축적. 이때 **지식 사용 리니지**
  (어떤 청크가 어떤 산출물에 주입됐는지 기록)와 **문서 버전/유효기간**(개정판 관리)도 함께 구현.
- ✅ **M1. 경량 기준정보 저장소** — 완료(`169612ccc` 백엔드+결정론 주입, `468c31487` UI).
  데이터 주입은 `scripts/api_data_loader.py`(§0-1) — 골든레코드 36개·타입 10종, 별칭 확정조회
  작동 확인(자용로→EQ-FLASH-01, OEE→ISO-KPI-01, MHP→RM-MHP-001).
  (LLM 0콜): 자재·공정·설비·KPI 골든 레코드 + 별칭 + 버전을
  단일 진실원본으로 관리, 에이전트 호출에 결정론적 주입(모델 전환 불변성의 최강 축).
  **상세 설계 확정: `docs/design_master_data_m1.md`** (스키마 DDL·API 명세·주입 규격·UI·체크리스트).
  온톨로지(G2)와 통합 설계 — entity_types 가 공용.
- ✅ **[채택] 리스크 분석기** — 완료(`974b9eee2`, `core/risk_analyzer.py`). 부분 승인·시각 Diff UI 는 미착수.
  (proposals/implementation_plan_finops.md 2단계
  + system_enhancement_analysis.md §2): 변경분 정적 분석으로 위험도 산출 — Low(스타일/텍스트)는
  자동 승인, High(스키마/API/의존성)만 인간 개입. LLM 0콜. 부분 승인·시각 Diff UI 는 후속 규모 큰 작업.
- **[조건부 채택] 테스트 엔지니어 노드(Flash TDD)** (동 문서 3단계): 단위 테스트 생성을 Flash 전담.
  단 '2회 실패 시 Pro 승격 없이 즉시 HOTL' 정책은 현행 자가복구(오류주입→3회차 Pro→HOTL)와 충돌 —
  **완주 스프린트 실측 데이터로 우열 판정 후** 설계 확정.
- **[채택·장기] 처방적 분석(몬테카를로/강화학습)** (proposals/product_strategy_vision.md 전략1):
  완성된 시뮬레이터를 AI 가 자율 탐색해 최적 파라미터를 선제 제시. 선행 조건 = 시뮬레이터 산출물의
  파라미터 API 표준화.
- **[채택] 시뮬 결과 → 기준정보(M1) 승격 루프** (동 문서 전략3): 검증된 최적값을 사용자 승인 거쳐
  M1 골든 레코드로 갱신(버전 계보 유지) — M1 구현 시 승격 경로 포함, 지식허브 3단계와 함께 폐쇄 루프.
- **[기각 기록]** Kafka/Redis 이벤트 버스(단일 프로세스에 과설계 — 기존 broadcaster 로 충분, 메가
  연합 실사용 시 재검토) / Docker·Wasm MicroVM 샌드박스(격리 서브프로세스 스모크가 이미 동작,
  현 단계 인프라 과투자).
- ✅ **M2. 스키마 레지스트리 + 키 크로스워크** — 완료(`fa802c706`, `core/crosswalk.py`+`CrosswalkPanel`).
  연계 시스템 등록·필드 매핑(LLM 초안 + 사용자 승인제).
- ✅ **M3. MCP 데이터 브로커** — 완료(`b05243239` 백엔드, `6cf3b87ba` 실측 병기 토글 **기본 off**).
  "전체 복제"가 아니라 **메타데이터+키맵만 복제,
  데이터는 MCP 온디맨드 조회 + TTL 캐시**(가상 통합). 읽기 전용부터, as-of 타임스탬프를 시뮬 결과에
  기록(재현성), MCP 유입 데이터도 비신뢰 입력으로 취급(인젝션 방어 동일 적용).

### 2-4. 잔여 기술부채

- ~~pytest 낡은 테스트 7건 현행화~~ → **해소**. 2026-07-25 기준 **전 스위트 258건 통과**(ENV-2 베이스라인)
- **⚠️ 쿨다운이 유료 제공사까지 30분간 배제한다** (2026-07-25 텔레메트리 실측, 최우선 부채) —
  `_update_cooldowns` 는 실패한 모델을 무조건 `MODEL_COOLDOWN_SEC`(기본 1800초) 쿨다운시킨다.
  전 모델이 쿨다운되면 `_compose_chain` 이 **첫 모델(무료 Gemini) 하나만으로 재프로브**하므로,
  크레딧이 남은 OpenRouter 유료 모델이 체인에서 빠진 채 무료 429 로 즉사하는 구간이 30분간 이어진다.
  `_all_cooled(pro_chain)` 이면 Pro→Flash 강등까지 겹쳐 유료 Pro 가 더 멀어진다.
  → **유료키로 완주를 노린다면 쿨다운 정책에서 유료 제공사를 제외하거나 쿨다운을 짧게 할 것.**
  (`core/llm_gateway.py:383-412`, `config.MODEL_COOLDOWN_SEC`)
- **유료 제공사(OpenRouter)가 폴백 체인의 맨 끝[4]** — 무료 4곳이 앞을 막고 있어, 무료 쿼터가
  남아 있는 동안에는 유료 경로가 아예 실행되지 않는다. 유료 경로만 검증하려면 무료 키를 잠시
  비우거나 체인 순서를 바꿔야 한다(체인 [0] 은 `ChatGoogleGenerativeAI` 로 하드와이어라 코드 수정 필요)
- **langgraph 체크포인트 역직렬화 경고** — `state_models.FileMetadata` 미등록 타입.
  현재는 동작하나 "향후 버전에서 차단" 예고 → langgraph 업그레이드 시 체크포인트 복구 불능 위험.
  `allowed_msgpack_modules` 등록 필요
- `scripts/api_data_loader.py:14` 실행 안내가 `.venv/Scripts/...` — PC 에 따라 `venv/`(점 없음)
- 저장소 비대화: `docs/reference/` 에 수십 MB 바이너리 다수(60MB PDF 포함) 커밋됨 — Git LFS 검토 여지
- `langgraph.json` 경로(`core/agent_graph.py`) — LangGraph Studio 사용 시에만 문제
- 스킬 제안 `prop_521c4962`(Tech_Lead) 승인/거부 결정 대기
- PreviewPanel 메인 iframe `allow-same-origin` 보안 트레이드오프(audit B9 참고)

---

## 3. 서버 기동 방법 (변경 없음)

```
백엔드:  venv\Scripts\python.exe run.py       # http://localhost:8080 (반드시 run.py — 포트/UTF-8 고정)
프론트:  cd frontend && npm run dev            # http://localhost:5173
```

### 3-1. 다중 환경 동시 작업 주의 (2026-07-25 실사고)

- **8080 은 단일 포트다.** 다른 PC/세션이 A-1 을 돌리는 중에 이쪽에서 백엔드를 띄우거나 내리면
  **상대의 스프린트가 그대로 끊긴다**(실제로 발생). 작업 전 상대 환경의 가동 여부를 확인할 것.
- 스프린트 실행 중에는 `.py` 를 저장해도 서버가 재시작되지 않는다(운영 모드 reload OFF가 기본).
  개발용 `--dev` 를 켠 채로 스프린트를 돌리지 말 것.
- **커밋은 한 곳에서만.** 두 PC 에서 동시에 커밋하면 `dev` 가 갈라진다(§4).
- ⚠️ **워킹 카피를 공유하는 경우**(같은 폴더를 두 세션이 보는 구성) — `git add -A` 금지.
  상대의 미커밋 실험 변경까지 함께 커밋된다. 실제로 2026-07-25 에 유료모델 실험분
  (`config.py` 의 `LOW_QUOTA_MODE=False`·OpenRouter 유료 모델, `nodes/execution.py` 의
  개발자 노드 Pro 강제)이 워킹트리에 떠 있는 상태로 관찰됐다.
  **커밋 전 `git status` 로 내가 만진 파일만 골라 `git add <파일>` 할 것.**

## 4. 작업 종료 시

```bash
git add -A
git commit -m "작업 내용"
git push          # origin/dev
```
> 두 곳(PC)에서 동시에 커밋하지 말 것 — `dev` 가 갈라져 충돌난다. 작업 시작=`git pull`, 종료=`git push`.
> 이 문서(AI_HANDOFF.md)는 세션이 크게 바뀔 때마다 갱신해서 함께 커밋할 것.
