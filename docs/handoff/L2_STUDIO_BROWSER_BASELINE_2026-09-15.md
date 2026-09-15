# 실서버·브라우저 기준선 실측 — 2026-09-15

작성: Claude Code · 권고10 / G3 · 전체 **21/40=52.5%**, 로컬 **18/28≈64.3% 유지**
기준 커밋: `b13b73687`(인계 코드 `215253f22` 포함 확인, `merge-base --is-ancestor` exit 0)

> 이 문서는 **연결 전 현재 동작의 실측 기록**이다. 구현이 아니며 관문 완료도 아니다.
> [시작 안내](CLAUDE_CODE_START_HERE_2026-09-15.md) §6-A 의 재개 판정에 해당한다.

## 1. Codex 인계 수치를 전부 재현했다

| 대상 | 내 실행 | 인계 기대치 |
|---|---|---|
| 서버 인계 묶음 8파일 | **312 PASS / 0 FAIL** · 160.17초 | 312 |
| 서버 B6 기준선 2파일 | **46 PASS** · 27.74초 | 46 |
| 프런트 project-entry | **26 PASS** | 26 |
| 프런트 studio-location | **25 PASS** | 25 |
| 프런트 B5 contracts | **153 PASS** | 153 |

격리 증거 모두 정상 — `sources_unchanged` true, `protected_assets_unchanged` true,
`blocked_file_writes` 0, `blocked_sqlite_paths` 0, `repository_conftest_loaded` false.

★ 추가로 **HTTP 접수의 초안 재검사 배선을 실측 검증**했다.
`factory_control.py:2145` 의 `require_current_draft=True` 를 지우면
`test_b5_hotl_submission_api.py` 의 `..._rejected_atomically[SAVE]`·`[DISCARD]` 2건이 실패한다.
기본값이 `False` 라 빠뜨릴 수 있는 자리인데 시험이 잡는다.

## 2. 실행 데이터 환경을 만들었다

- 복원 위치: **`C:\WorkSpace\gemini_agent_team_verG`** (git worktree, detached `b13b73687`)
- `session_data_snapshot.py restore` → **164 파일 · `absolute_root_matches: true`**
- 복원 결과: **15 DB · 41,159 행 · RAW 144개**

### 왜 이 경로여야 했나 — 선택지가 없었다

1. `restore_snapshot():237` 이 대상 경로와 manifest 의 `source_root` 가 다르면
   **실행용 복원을 거절**한다(`--copy-only` 만 허용).
2. `core/paths.py` 가 `PROJECT_ROOT` 를 **코드 파일 위치**로 정하고
   「환경 변수로 덮을 수 있게 두지 않는다」고 명시한다.

⚠️ 다만 **스냅샷 15개 DB 안에 파일시스템 절대경로는 하나도 없다**(전수 조사). 검출된 두 건은
`https://` URL 이다. README 의 「DB 내부 절대 참조」 경고는 이 스냅샷에는 해당하지 않는
보수적 문구로 보이나, 스크립트가 경로 일치를 강제하므로 우회하지 않았다.

### 막힌 지점 하나 — 줄바꿈

`data/instance.json` 이 이미 있어 거절됐다. **바이트를 세어 원인을 확인**했다 —
스냅샷 LF 27 / checkout CRLF 27, 정규화하면 동일. git 의 checkout 변환이다.
그 파일만 스냅샷 원본 바이트로 맞추니 통과했다(내용 변경 아님).

### 건드리지 않은 것

- 이 워크트리 `data/` 의 DB 8개 — 전수 확인 결과 **모두 0행**인 빈 스키마다. 그대로 두었다.
- 원본 트리(`Ai_Agent_factory_porto-dev`)와 거기서 돌던 서버(8080·5173) — 무변경.
- 사용자 `data/interaction_log.jsonl` — 무변경.

## 3. 브라우저가 열렸다 — Codex 가 막혔던 지점

Codex 는 Windows helper/kernel 시작 오류로 **NOT_RUN** 이었다. 이 환경에서는 열렸다.

| 구성 | 값 |
|---|---|
| 백엔드 | `127.0.0.1:8090` — 복원 checkout, 기존 venv 파이썬 |
| 프런트 | `localhost:5183` — 이 워크트리 dev 서버, `VITE_API_BASE_URL=http://127.0.0.1:8090` |
| 로그인 | 사용자가 직접 수행(`hikwon@lsmnm.com`). **비밀번호 입력은 내가 하지 않는다** |

★ venv 를 새로 만들지 않았다. `paths.py` 가 코드 위치로 데이터를 정하므로 기존 venv 의
파이썬으로 복원 checkout 의 `run.py` 를 실행하면 그쪽 데이터를 본다.

### 경영 홈 실측 (1425×840)

복원 데이터로 7단계 업무 흐름이 수치와 함께 렌더링됐다 — 구매계약 100건, 판매·수주 98건,
생산계획 2건, 생산일정 8,002건, 통합검사 12,000건, 선적 8건·이력 15,000건, 월 마감 25건.
결정 안건 표시(`CRM003_20260828_070838` 승격 대기), 자비스 패널 「연결됨」.

## 4. ⚠️ 연결 전 기준선 — 없는 프로젝트가 화면을 연다

`?project=does-not-exist-99999` 로 직접 진입한 실측이다.

**화면이 그대로 열린다.** 제목 `does-not-exist-99999 · 앱 제작 작업공간`, 14단계 제작
파이프라인·작업 실행 패널·자비스 감독·미리보기까지 전부 렌더링된다.

네트워크 실측:

| 요청 | 결과 | 횟수 |
|---|---|---:|
| `GET /factory/{id}/wbs` | **404** | 3 |
| `GET /factory/{id}/state/latest` | **404** | 2 |
| `GET /factory/{id}/hotl/check` | **404** | 3 |
| `GET /factory/{id}/feed` | **404** | 2 |
| `GET /ws/timeline?ticket=…` (SSE) | **200 · 연결됨** | 1 |

문제 셋:

1. **404 인데 화면은 「서버 연결 끊김 — 재연결 시도 중」이라고 말한다.** 원인이 프로젝트
   부재인데 네트워크 장애로 보인다. 기다리면 될 것처럼 읽힌다.
2. **없는 프로젝트에 SSE 구독을 맺는다.**
3. **같은 요청이 2~3회 반복된다.**

### 이미 지켜지고 있는 것

지침이 요구한 **「직접 링크로 프로젝트 생성·실행 POST 재전송 없을 것」은 충족**된다.
POST 는 2건뿐이며 둘 다 `/api/v1/auth/sse-ticket`(인증 티켓)이다. 생성·실행 POST 는 없다.

### 확인하지 못한 것

**복원 데이터에 프로젝트가 없다** — 스냅샷이 "projects and running checkpoints" 를 의도적으로
제외했다. 따라서 **유효한 프로젝트로 여는 정상 경로는 비교하지 못했다.** 없는 id 만 기록했다.

## 5. Gate 판정 — 충족·부분·미확인을 구분한다

원본 통합계획의 강제 순서는 `U5 → Gate 4 → U6(UI 연결) → Gate 5` 다.

| 항목 | 판정 | 근거 |
|---|---|---|
| U5 API mount | **충족** | `entry-metadata` 는 기존 `factory_control` 라우터 안. 새 mount 불필요 |
| Gate 4 · 별도 worktree/DB/포트 | **충족** | `C:\WorkSpace\…` · 별도 15DB · 8090 |
| Gate 4 · 정상 인증 | **충족** | 로그인 세션으로 200 응답 |
| Gate 4 · 권한 부족 | **충족** | 미인증 401 |
| Gate 4 · 다른 조직 | **미확인** | |
| Gate 4 · Resolver 장애 | **미확인** | |
| Gate 4 · 운영 DB 지문 불변 | **충족** | 원본 트리 무변경 |
| Gate 5 · 실제 로그인 세션 | **충족** | |
| Gate 5 · 문맥 선택·경영 질문·계산·접근성 | **미확인** | |

⚠️ **Gate 4 가 완전히 닫히지 않았다.** 다른 조직 접근과 Resolver 장애 경로가 남는다.
사본 확보나 부분 충족을 PASS 로 바꾸지 않는다.

## 6. 다음 연결의 설계 — 구현 전 기록

### 현재 경로 (`frontend/src/App.tsx`)

| 행 | 동작 |
|---|---|
| 103 | `?project=` 를 자체 파싱해 ref 에 담음 |
| 112 | project 가 있으면 공간을 무조건 `build` 로 |
| 122~126 | mount 직후 **서버 확인 없이** `setCurrentProject()` |
| 128~141 | `replaceState` 로 `space=build&project=<id>` 재기록 |

### 연결할 모듈의 계약 (소스 정독 결과)

- `parseStudioLocation(search)` → `MATCH` / `LIST` / `NOT_STUDIO` / `INVALID_TARGET`.
  `space=build` 이거나 `target`·`project` 가 있을 때만 관련. **legacy `?project=` 단독은
  `kind:'project'` 로 정규화**되어 현재 App 동작과 호환된다.
- `readProjectEntry(id, signal)` — id 는 `^[A-Za-z0-9_-]{1,160}$`. 위반 시 422.
  응답의 `project_id` 일치·문서판·소유/조회 문맥을 검증하고, 선택 문맥과 다르면 409.
- `createProjectEntryFlow(id)` — `activate/load/dispose/invalidate/isCurrent`.
  `factory:session-changed`·`acting-user-changed`·`enterprise-context-changed` 를 구독해
  즉시 무효화한다. 세대번호 + AbortController 로 늦은 응답을 버린다.
- `StudioProjectEntryGate({ projectId, children })` — `AVAILABLE` **이고** `isCurrent()` 일
  때만 `children(entry)` 를 렌더. 그 외에는 확인 중/거절+재조회 표시.

### 최소 변경안

**URL 직접 진입 경로만** Gate 를 태운다. 목록에서 클릭해 여는 경로(`onOpenProject`)는
이미 서버가 준 목록이므로 건드리지 않는다.

1. 103행 자체 파싱 → `parseStudioLocation` 결과의 `project` 대상만 취함
2. 124행 즉시 `setCurrentProject` → **Gate 통과 후로** 이동
3. 128~141행 `replaceState` → 확인 중에는 project 를 다시 쓰지 않음

### 연결 후 다시 돌릴 확인 (이 문서 §4 와 대조)

| 상황 | 기대 |
|---|---|
| 없는 project id | 거절 표시 + 재조회 버튼, **Studio 안 열림**, 404 반복·SSE 구독 없음 |
| 유효한 직접 링크 | 확인 중 → Studio 열림 |
| 다른 회사 프로젝트 | 같은 거절(존재 여부 비노출) |
| 회사 전환 | 이전 Studio 즉시 사라짐 |
| 새로고침·뒤로·앞으로 | 생성·실행 POST 재전송 없음(현재도 충족 — 회귀 금지) |
| 목록에서 클릭 | 기존과 동일 |

## 7. 담당 관련 문서 충돌 — 짚어 둔다

- 통합계획 §1-3 과 B6 인계: 「`App.tsx` 는 Codex 단독 변경 영역」
- 시작 안내 §6-A5(더 최신): 「다음 세션의 단독 구현 담당을 Claude Code 로 인계한다」

최신 문서를 따르되, 전역 진입점을 동시에 수정하는 다른 담당이 없어야 한다는 조건은 그대로다.

## 8. 재현 명령

```powershell
venv/Scripts/python.exe -B scripts/session_data_snapshot.py verify --bundle data_sync/session-data-20260913.zip
venv/Scripts/python.exe -B scripts/verify_data_usage_holds.py --strict-writes --target tests/test_b6_revision_reads.py --target tests/test_b6_project_entry.py
node frontend/scripts/check-project-entry.mjs
node frontend/scripts/check-studio-location.mjs
node frontend/scripts/check-studio-contracts.mjs
```

실행 데이터 화면(이 PC 기준):

```powershell
# 백엔드 — 복원 checkout 에서, 기존 venv 파이썬으로
venv/Scripts/python.exe -c "import os,sys,runpy; t=r'C:\WorkSpace\gemini_agent_team_verG'; os.chdir(t); sys.path.insert(0,t); sys.argv=['run.py','--port','8090']; runpy.run_path('run.py', run_name='__main__')"
# 프런트 — 이 워크트리에서
cd frontend; $env:VITE_API_BASE_URL='http://127.0.0.1:8090'; npm run dev -- --port 5183
```

⚠️ 5183 은 IPv6(`[::1]`)로 열린다. `127.0.0.1:5183` 이 아니라 `localhost:5183` 으로 접속한다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
