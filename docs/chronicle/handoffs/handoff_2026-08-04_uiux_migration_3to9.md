# 인수인계 — 2026-08-04 · UI/UX 이관 3~9/10 및 «경로 단위» 권한 통제

- 작성자: Claude Code
- 기록 시각: 2026-08-04 (KST, 세션 종료 시점)
- 기준 브랜치: `claude/nice-hawking-f8b4bf` (워크트리 `.claude/worktrees/nice-hawking-f8b4bf`)
- 기준 HEAD: `7c60dcf80`
- 커밋: **완료(8건)** · 푸시: **미수행**
- 팀 보드 대응 항목: `.agents/TEAM_BOARD.md` `[UIUX-MIG-27]` ~ `[UIUX-MIG-31]`
- 선행 인수인계: `docs/chronicle/handoffs/handoff_2026-08-04_uiux_mdm_codex.md`

---

## 1. 이번 세션의 결론 — 한 문장

**이관은 «화면을 라이트로 바꾸는 일»이 아니었다.** 화면 7개를 옮기는 동안 **읽기·쓰기 라우트에
자격 검사가 없는 구멍이 여섯 번 연속** 나왔고, 매번 화면 작업보다 통제 복구에 시간이 더 들었다.
그래서 다음 사람은 **화면을 열기 전에 그 화면이 쓰는 라우트부터 훑어야 한다.**

### 1.1 발견한 구멍 (전부 실측 확인 후 수정·커밋 완료)

| 이관 | 열려 있던 것 | 무게 |
|---|---|---|
| 3/10 업무표준 | `POST /standards`, `POST /standards/seed?force=true` | 익명이 **에이전트 판정 기준**을 개정·재시드 |
| 4/10 조직·권한 | `GET /org/users`, `/tree`, `/departments` | 익명이 **전 직원 21명의 이름·이메일·부서·관리자 여부** |
| 5/10 거버넌스 | `/contracts/evaluate`, `/external/readiness` 등 7경로 | 익명이 **취약점 지도**(위반 계약·격차 영향) |
| 6/10 에이전트 통제소 | `PUT /factory/agents`, `POST /agents/reset`, `POST /skills/proposals/{id}/approve`, `ai-recommend/*` | 익명이 **HOTL 중단점 삭제·스킬 문서 개정·LLM 예산 소모** |
| 7/10 프로젝트 | `POST /{id}/hotl/resume` 등 8경로 | 익명이 **HOTL 중단점을 그냥 통과** |
| 9/10 브리핑 | `GET /briefing` | **요약 화면이 5/10 통제를 우회** |

### 1.2 이 목록에서 배울 것 두 가지

**① 통제는 한 경로만 막아서는 안 된다.**
6/10 에서 «HOTL 중단점을 지우려면 관리자 권한»을 막았는데, 7/10 에서 보니 **지울 필요 없이
`hotl/resume` 로 통과**시킬 수 있었다. 9/10 브리핑은 5/10 에서 막은 거버넌스 자료를 **다시 모아**
보여 줬다. 즉 «자료를 만지는 경로»와 «자료를 요약하는 경로»를 함께 봐야 한다.

**② 판정은 라우트가 아니라 판정 함수에 둔다.**
7/10 에서 `assert_project_readable/writable` **안**에 관문 A 를 넣었다. 그러면 그 함수를 이미
쓰는 모든 경로(스프린트·삭제·복제·릴리스·재시뮬레이션)가 함께 보호되고, 새 라우트가 생겨도
판정을 부르는 순간 같이 걸린다. 라우트마다 흩으면 다음 라우트에서 또 빠진다.

---

## 2. 커밋 이력 (오래된 것부터)

| 커밋 | 내용 |
|---|---|
| `b1ec7e1a0` | **캡처 경로 확보** — `scripts/capture_screens.py`(playwright + 설치된 Chrome) |
| `f224ae685` | 공통 셸 결함 6건(아이콘 중복·레일 잘림·고아 줄바꿈·Jarvis 빈 공간·상단 바 노출·숨김 배너) |
| `0512bd522` | 버전 상태에서 «미측정» 제거 |
| `5e8e58583` | 이관 3/10 업무표준 + 통제 |
| `49e34f295` | 이관 4/10 조직·권한 + 통제 |
| `3ff5c1eed` | 이관 5/10 거버넌스 + 통제 |
| `c592b5ef8` | 이관 6/10 에이전트 통제소 + 통제 + `reset` 백업 |
| `080cd119a` | 이관 7/10 선행 — 프로젝트 실행 경로 통제 |
| `7c60dcf80` | 이관 7~9/10 런처·스킬 개선안·브리핑 |

---

## 3. 지금 상태

### 3.1 검증 수치

- pytest **1821 passed / 실패 0** (세션 시작 시 1777 → 신규 44건)
- `tsc --noEmit` 통과
- 화면 캡처 **84개 전 항목 통과**(42화면 × 1280×720·1440×900)

### 3.2 이관 완료 화면 (셸 위)

지식 허브 · 기준정보 마스터 · 협업(의사결정·발간 포함) · 업무표준 · 조직·권한 · 거버넌스 ·
에이전트 통제소 · 스킬 개선안 · 전사 브리핑 · **런처(App.tsx)**

### 3.3 미이관 화면 8개 — 사용자 결정: **전부 이관**

| 화면 | 줄수 | 특이사항 |
|---|---|---|
| AdvisorPanel | 694 | 가장 큼 |
| PreviewPanel | 658 | `alert` 1곳 |
| PlanningPanel | 374 | **무방비 라우트 13개**(아래 4.1) |
| WorkspacePanel | 373 | |
| CrosswalkPanel | 313 | `alert/confirm/prompt` **10곳** · 자체 `API_BASE_URL` 1곳 |
| ShadowModePanel | 305 | |
| ProgramAdminPanel | 239 | |
| TelemetryPanel | 227 | |

---

## 4. 다음 사람이 바로 할 일

### 4.1 ★★★ 먼저 막을 것 — Planning 경영 계획 (권고)

`api/routes/planning_control.py` 에 **`Principal` 없는 라우트 13개**가 있다. 실측:

```
익명 GET /api/v1/planning/submissions        → 200 (0건)
익명 GET /api/v1/planning/accounts           → 200 (0건)
익명 GET /api/v1/planning/scenarios          → 200 (0건)
익명 GET /api/v1/planning/drivers            → 200 (0건)
익명 POST /planning/scenarios/{id}/assumptions  ← 계획 가정을 바꾼다
익명 POST /planning/accounts · /planning/drivers ← 계정과목·동인 등록
```

⚠️ **지금은 0건이라 실제 유출이 없지만 통제가 없다는 사실은 그대로다.** 경영 계획(매출·원가
전망)이 들어오면 그때부터 새어 나간다. 데이터가 비어 있는 지금 막는 편이 안전하다.

권장 방침(3~7/10 과 같은 형태):
- 목록·조회 — `visibility_block_reason` 으로 익명·미등록·폐지 차단(0건 + 이유)
- `submissions`·`submissions/current` — **경영 계획 본문**이다. 거버넌스 수준(`governance_block_reason`)
  또는 별도 «계획 열람» 자격을 정할 필요가 있다. **이건 사용자 결정이 필요하다** — 계획을
  누가 볼 수 있는지는 제품 정책이다.
- 쓰기(`accounts`·`drivers`·`assumptions`) — `assert_can_manage_standard` 이 적절해 보이나
  계획 수립 권한을 별도로 둘지 확인이 필요하다.

### 4.2 화면 이관 순서 (작은 것부터 — 위험이 낮고 성과가 빨리 쌓인다)

`Telemetry(227) → ProgramAdmin(239) → Shadow(305) → Crosswalk(313) → Workspace(373) →
Planning(374) → Preview(658) → Advisor(694)`

각 화면마다 **이 순서로** 한다:
1. 그 화면이 쓰는 라우트의 자격 검사 확인 → 없으면 먼저 막고 테스트로 잠근다
2. 백엔드를 고쳤으면 **8080 재시작**(§5.1)
3. 화면을 셸(`HubDialog` + `HubShell`)로 옮긴다
4. `scripts/capture_screens.py` 에 캡처 대상 추가 → 게이트 통과
5. **캡처 이미지를 직접 열어 눈으로 본다**(§5.2 — 자동 통과 후에도 결함이 나온다)
6. `.agents/TEAM_BOARD.md` 에 주체·이유·근거 기록

### 4.3 이관 완료 조건 (사용자 확정, 2026-08-04)

1. 사용자 용어만 노출 — 내부 슬러그·상태 코드는 `frontend/src/design/terms.ts` 사전을 거친다.
   ⚠️ 사전에 없는 값은 `console.error` 를 내고 **캡처 게이트가 잡는다**(실제로 3건 잡았다).
   단 `STD-QA`·`build_success` 처럼 **실제 식별자는 번역하지 않는다** — 사용자도 그 문자열로 찾는다.
2. 권한별로 **실제 가능한 행동만** Jarvis 가 안내 — `frontend/src/lib/actingScope.ts`
3. 조회 실패·자료 없음·미지정을 각각 구분 — `Loaded<T>` + `Metric notes`
4. 1280×720 · 1440×900 시각 회귀
5. 자동 측정 통과 후 **실제 캡처 육안 검토**
6. TEAM_BOARD 기록

---

## 5. 함정 — 내가 실제로 빠진 것들

### 5.1 백엔드를 고치고 재시작하지 않아 **옛 코드로 검증했다** (3회)

`preview_start`/`preview_stop`(name: `backend`)으로 재시작한다. 재시작 전 실측은 무의미하다.
증상: 「막았는데 화면에 그대로 보인다」 → 서버가 옛 코드였다.

### 5.2 자동 게이트가 통과했는데 육안으로 결함이 나왔다 (매 화면)

세션 첫날 「측정 통과 → 이미지 보니 결함 6건」을 겪고 게이트 항목을 늘렸지만, 그 뒤에도
**화면마다 2~4건씩** 육안으로만 잡혔다. 예:
- 목록 아바타가 빈 원(제목을 **NBSP** 로 들여썼다 — 눈에도 안 보이고 `trim()` 으로도 안 잡힌다)
- 동작하지 않는 빈 검색창(4/10·5/10 에서 반복)
- 남색 상단 바에 어두운 글자 → **제목이 사라짐**
- 익명에게 Jarvis 가 «할 수 있는 일»을 말함(누르면 403)
- **권한 잔상** — 익명으로 바꿨는데 이전 사용자의 목록이 배너와 함께 남음

→ **게이트 통과는 «검증 완료»가 아니다.** 반드시 `Read` 로 PNG 를 열어 본다.

### 5.3 ★★★ 파괴적 엔드포인트를 «차단 확인» 목적으로 불러 **데이터를 지웠다**

`POST /api/v1/factory/agents/reset` 을 그대로 호출했고, 그 엔드포인트는 `agents_registry.json`
을 **삭제**한다. 파일이 사라졌고 git 에 커밋된 적 없는 런타임 산출물이라 복원되지 않았다.
(reset 직전 GET 이 기본값과 같았으므로 실제 손실은 없었을 가능성이 높지만 **확정할 수 없다.**)

또 `POST /ai-recommend/skill` 을 유효 payload 로 불러 `skills/a_skill.md` 쓰레기 파일이 생겼다
(커밋에 섞여 들어갔다가 제거).

**규칙**: 파괴적·생성형 경로는
- 익명으로만, 그리고
- **존재하지 않는 id** 나 **유효하지 않은 payload** 로만 찔러 본다.
- 권한자 경로는 저장 함수를 monkeypatch 로 대역화한 **테스트**로 확인한다.

재발 방지는 코드에도 넣었다: `reset_registry()` 가 직전 상태를 `agents_registry.prev.json` 으로
남기고 **백업 실패 시 삭제하지 않는다**. `POST /api/v1/factory/agents/restore` 로 한 번 되돌린다.

### 5.4 payload 를 비우면 **422 가 먼저 나서 «막혔다»고 잘못 읽는다**

FastAPI 는 body 검증을 먼저 한다. 자격 검사를 확인하려면 **모델이 요구하는 형태**로 payload 를
줘야 한다. 그러지 않으면 통제가 없는데도 422 를 보고 «차단됨»으로 오판한다.

### 5.5 모달이 열려 있으면 `#root[inert]` 로 상단 바를 **클릭할 수 없다**

캡처 스크립트에서 사용자 전환이 30초 타임아웃 났다. `switch_user` 가 먼저 `close_dialogs` 를
부른다. 셀렉트는 통과했지만 버튼은 막힌다는 점이 함정이었다.

### 5.6 통제를 켜면 **로그인 경로가 막힐 수 있다**

4/10 에서 사용자 명부에 자격 검사를 넣자 `UserSwitcher` 가 «목록 0건» 조건으로 스스로 사라져
**아무도 진입할 수 없게** 됐다. 계정 직접 입력 경로를 만들어 복구했다.
→ 통제를 넣은 뒤 **익명 상태에서 화면을 열어 보라.**

### 5.7 401·403 을 «서버 이상»으로 세면 안 된다

통제를 켜자 Jarvis 머리가 «일시 중단»으로 바뀌고 "요청이 실패하고 있습니다" 가 떴다. 사실이
아니고, 그렇게 두면 진짜 장애 때 그 표시를 아무도 믿지 않는다. `backendHealth.reportRequestFailure`
가 상태 코드를 받아 401/403 을 건강으로 처리한다(호출부 15곳에 전달했다).

---

## 6. 도구 사용법

### 6.1 화면 캡처

```bash
venv/Scripts/python.exe scripts/capture_screens.py                    # 전체(약 8분)
venv/Scripts/python.exe scripts/capture_screens.py --only 브리핑       # 하나만
```

전제: 프론트 5173 · 백엔드 8080 이 떠 있어야 한다(스크립트가 서버를 띄우지 않는다).
`Browser` 패널이 보이지 않아 `computer{screenshot}` 이 실패하는 환경에서도 동작한다 —
설치된 Chrome 을 playwright 로 헤드리스로 띄운다.

**게이트가 검사하는 항목**(재승인 기준과 1:1): 레일 아이콘 중복 · 활성 항목 가시성 · 잘린 항목 ·
고아 줄바꿈(글자 단위) · Jarvis 빈 공간·근거 잘림 · 모달 바깥 여백 · «0건» 오해 표현 ·
내부 슬러그 노출 · 12px 미만 본문 · 콘솔 오류. 하나라도 어기면 exit 1.

캡처 이미지는 `.gitignore` 로 커밋하지 않는다(낡은 이미지를 «지금 화면» 근거로 쓰게 된다).

### 6.2 셸 컴포넌트

- `design/HubDialog.tsx` — 전체화면 모달(포커스 트랩·Escape·배경 inert·스크롤 잠금)
- `design/HubShell.tsx` — 3열(레일 / 작업면 / Jarvis). `RailItem.icon` 은 **필수**이며
  `design/RailIcon.tsx` 등록부의 이름만 쓴다. 한 화면에 같은 아이콘이 두 번 오면 콘솔 오류.
- `design/DataFoundationShell.tsx` — 툴바(검색은 **선택적**)·목록·근거 띠·확인·폼·이력
- `design/DataState.tsx` — `Loaded<T>` · `Metric`(notes 로 상태 문구 지정) · `EmptyOrError`
- `design/terms.ts` — 내부 값 → 사용자 용어. 모르는 값은 콘솔 오류.
- `lib/actingScope.ts` — 현재 사용자가 **실제로 할 수 있는 일**(서버 판정을 옮기기만 한다)

### 6.3 서버

```
preview_start / preview_stop  (name: "backend" = 8080, "frontend" = 5173)
```

---

## 7. 미결 사항 — **사용자 결정이 필요하다**

1. **정본 결정**: 부서는 `LS_MNM` 계열 **scope code**, ECM 트리는 `node_*` **해시**를 쓴다.
   두 체계가 공존한다. 어느 쪽이 정본인지 정해야 조직 범위 지정 화면이 완결된다.
   (지금은 실제로 쓰이는 값을 제안 목록으로 준다.)
2. **경영 계획 열람 자격**(§4.1) — `planning/submissions` 를 누가 볼 수 있는가.
3. **소유권 미기록 프로젝트** — 식별된 사용자에게는 여전히 열려 있다(하위호환).
   **미기록 프로젝트 수를 상시 관측**해야 하고, 0 이 되면 이 관대함을 걷어낸다.
   테스트가 이 계약을 고정하므로 조용히 바뀌면 깨진다.
   (`tests/test_project_execution_gate.py::test_unowned_project_stays_permissive_for_identified_users`)

## 8. 알려진 부채 (내가 만든 것 아님 — 정리 대상)

- `frontend/src/App.tsx` 에 **모달 렌더 목록이 두 벌** 있다(프로젝트 없음 / 있음 화면).
  한쪽에만 추가하면 특정 상태에서만 안 열린다.
- `core/broadcaster.py` 에 **사용자별 필터가 없다.** 알림을 붙일 때(CL-4) 반드시 고쳐야 한다 —
  지금은 모든 사용자가 같은 스트림을 받는다.
- `AgentFlow/AgentDetailSidebar.tsx`(12개 필드·231줄)는 **다크 스타일 그대로** 재사용했다.
  다시 만들면 필드 누락 위험이 커서 의도적으로 남겼다 — 별도 단계로 옮긴다.
- 남은 «Principal 없는 라우트» **약 60개**(planning 13 · crosswalk 9 · benchmark 6 ·
  workspace 5 · lineage 4 · format 4 …). 화면 이관과 함께 훑는다.

## 9. 예상 잔여량

이번 세션에서 화면 4개 + 런처를 옮겼다. 남은 8개 + 통제 60여 경로는 **같은 분량의 2~3배**로
본다. 다만 변수는 화면 크기가 아니라 **구멍의 수**다 — 여섯 번 연속 나왔으므로 남은 경로에서도
상당수가 그럴 것이다.
