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
| Gate 4 · 정상 인증 | **충족** | 로그인 세션으로 **200**, 소유·조회 문맥 반환 |
| Gate 4 · 권한 부족 | **충족** | 미인증 **401** |
| Gate 4 · 다른 조직 | **충족** | §5.1 |
| Gate 4 · Resolver 장애 | **충족** | §5.2 |
| Gate 4 · 운영 DB 지문 불변 | **충족** | 원본 트리 무변경 |
| Gate 5 · 실제 로그인 세션 | **충족** | |
| Gate 5 · 문맥 선택·경영 질문·계산·접근성 | **미확인** | |

★ `create_router(runtime)` 에 Resolver 주입 항목은 원본 계획의 **G2 관계 런타임 맥락**이며
L2 Studio 진입 경로에 직접 대응하는 대상이 없다. 여기서는 판정하지 않는다.

### 5.1 다른 조직 — 실서버 HTTP 로 닫았다

없는 프로젝트는 **모든 문맥에서 404** 라 「숨긴 것」과 「원래 없는 것」이 구분되지 않는다.
그래서 **카나리 대상**을 만들어 확인하고 즉시 제거했다(`gate4-canary-resolver`,
legacy 1.0 meta 만 둔 디렉터리. LLM·생성 API 미사용).

| 요청 | 결과 |
|---|---|
| 정상 문맥 | **200** — `ownership`·`viewing_context` 반환 |
| `X-Enterprise-Scope: plant-afs-battery-02`(다른 조직) | **404** · `data` 없음 |
| `X-Enterprise-Tenant: tenant-other-xyz` | **200** — 단, 아래 ★ |
| `X-Entity-Mode: SYNTHETIC` | **200** — 단, 아래 ★ |

★ **테넌트·실체모드 헤더는 결함이 아니다.** 응답의 `viewing_context` 를 실측하니
헤더 값이 아니라 **실제 소유 문맥**(`tenant-afs-demo-materials` / `REAL`)이 돌아온다.
서버가 클라이언트 헤더를 그대로 믿지 않는다. 프런트도 `readProjectEntry` 에서 선택 문맥과
`view` 를 대조해 다르면 409 로 막는 이중 방어다. 처음에 200 만 보고 결함으로 의심했으나
**전체 응답을 확인해 판정을 정정했다.**

### 5.2 Resolver 장애 — 실서버 HTTP 로 닫았다

카나리의 `project_meta.json` 을 손상시켜 확인했다.

| 손상 형태 | 결과 |
|---|---|
| 최상위가 배열 `[]` | **404** · `data` 없음 |
| `project_name` 이 객체 | **503** · `reason_code: PROJECT_ENTRY_UNAVAILABLE` · `data` 없음 · **손상 원문 메아리 없음** |

⚠️ **먼저 시도한 방법은 실패했고 그 과정에서 별도 사실을 알아냈다.** `advisor.db` 를 치우고
재기동해 유실 503 을 보려 했으나, **서버가 기동하면서 `advisor.db` 를 다시 만든다**
(표 4개·86,016바이트). B6 인계가 「시작 singleton 초기화는 제거 대상이 아니다」라고 적어 둔
것의 실증이다. 따라서 **「DB 유실」 장애는 실서버 기동 경로에서 재현되지 않는다** —
격리 시험의 `monkeypatch` 로만 만들 수 있다.

되돌린 뒤 원본과 **바이트 단위로 일치**함을 확인했고(백업 대조), 임시물은 전부 제거했다.

### 5.3 이 절차에서 건드린 것과 되돌린 것

| 조작 | 되돌림 |
|---|---|
| 8090 백엔드 중지·재기동 2회 | 재기동 후 200 확인 |
| `advisor.db` 일시 이동 | 원본 복구, 백업과 해시 일치 확인 후 백업 삭제 |
| 카나리 프로젝트 생성·메타 손상 | 디렉터리 삭제, `projects/` 비어 있음 확인 |

5183 프런트와 다른 세션의 8080·5173 은 **건드리지 않았다**. 복원 데이터는 41,159행에서
41,162행이 됐다 — 증가분 3건은 로그인 세션과 SSE 티켓이다.

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

## 9. 연결 구현과 개선 증명 — 2026-09-15

`frontend/src/App.tsx` **한 파일**만 바꿨다. 세 지점이다.

| 지점 | 변경 |
|---|---|
| URL 해석 | 직접 `URLSearchParams` 읽던 것을 `parseStudioLocation` 으로 옮김 |
| 진입 | `setCurrentProject()` 즉시 호출 → **Gate 확인 후로** |
| 이탈 | 닫기 3곳에서 게이트도 함께 닫음(확인 화면 재등장 방지) |

★ **목록에서 눌러 여는 경로는 건드리지 않았다** — 서버가 준 목록에서 고른 것이라 진입
확인을 한 번 더 할 이유가 없다.

★ 확인 화면에는 **나갈 길**(경영 홈·앱 제작)을 App 이 함께 둔다. `StudioProjectEntryGate`
자체에는 재조회 버튼만 있어 거절되면 갇힌다.

### 실측 대조 — §4 와 같은 조작

| 상황 | 연결 전 | 연결 후 |
|---|---|---|
| 없는 project id | **Studio 전체 렌더** · wbs/state/hotl/feed **404 × 10** · SSE 구독 | **「현재 회사·권한에서 프로젝트를 찾을 수 없습니다」+ 재확인 버튼** · `entry-metadata` 만 호출 |
| 유효한 직접 링크 | (프로젝트 없어 확인 불가) | **Studio 열림** · 제목이 **서버가 준 이름** · 상태 「대기(가동 안 함)」 |
| 목록에서 클릭 | 열림 | **열림 — 회귀 없음** (URL 도 `space=build&project=…` 로 갱신) |
| 생성·실행 POST | 없음 | **없음 — 유지** |

★ 연결 전에는 실패가 「서버 연결 끊김 — 재연결 시도 중」으로 보였다. 지금은 원인을
그대로 말한다. 유효한 프로젝트에서는 「대기(가동 안 함)」로 **다른 상태와 구분**된다.

정상 경로 확인에는 임시 대상(`b6-entry-canary`, meta 만 둔 디렉터리)을 쓰고 **즉시 제거**했다.
`projects/` 가 비어 있음을 확인했다.

### 검사

| 대상 | 결과 |
|---|---|
| tsc | 오류 0 |
| 제품 build | PASS(기존 청크 경고만) |
| B5 계약 | **153 PASS / 0 FAIL** |
| project-entry | **26 PASS / 0 FAIL** |
| studio-location | **25 PASS / 0 FAIL** |
| 설치 계약 | **105 PASS** |

### ⚠️ 확정하지 못한 것 하나

첫 관찰에서 `entry-metadata` 가 **503 을 한 번** 반환했고 곧이은 재요청은 404 였다.
연속 5회 호출은 **전부 404** 이고 그 뒤 재현되지 않았다. 네트워크 추적 도구가 새로고침
시점의 첫 요청을 잡지 못해 **재현 조건을 확정하지 못했다.**

서버는 `409` 와 `5xx` 를 모두 `503 PROJECT_ENTRY_UNAVAILABLE` 로 바꾸므로 문맥 캐시 경쟁일
가능성이 있으나 **확인하지 않았으므로 원인이라고 적지 않는다.** 화면 동작에는 영향이 없다
— 거절 표시와 재조회 버튼이 나오고, 재조회하면 정상 판정된다.

### 범위 밖으로 남긴 것

- **회사 전환 시 이미 열린 Studio 를 닫는 것.** 현재 App 은 회사가 바뀌면 SSE 만 다시 맺고
  `currentProjectId` 를 비우지 않는다(연결 전부터 그랬다). Gate 는 확인 단계에서만 감싸므로
  확인이 끝난 뒤의 전환은 잡지 못한다. **다음 묶음 대상**이다.
- new/draft/kit_app/release/mega 대상 연결, 히스토리·SSE 통합.
- B6 전체 완료로 가산하지 않는다. 전체 21/40=52.5% 유지.

## 10. Gate 5 — 실제 브라우저로 확인한 것과 남은 것

복원 데이터 + 사용자 로그인 세션 + 실제 Chrome 으로 원본 계획 Gate 5 의 항목을 하나씩 밟았다.

| 항목 | 판정 | 근거 |
|---|---|---|
| 실제 로그인 세션 | **충족** | 사용자가 직접 로그인. `auth_session` 1행 |
| 회사·사업부·공장 문맥 선택 | **충족** | §10.1 |
| 경영 질문 입력 | **부분** | 입력·전송은 동작. 응답은 LLM 키 부재로 502 — §10.4 |
| 온톨로지 경로와 근거 표시 | **충족** | §10.2 |
| 계산 요청과 결과 표시 | **충족** | §10.3 |
| 조회 실패·계산 전·승인 대기 구분 | **충족** | 셋이 서로 다른 문구·상태로 표시된다 |
| 가로 넘침·잘림 | **충족** | 1280×720·1440×900 둘 다 `scrollWidth == clientWidth` |
| **12px 미만** | **미충족** | **79건** — §10.5 |
| 키보드 접근 | **충족** | 포커스 가능 62개, 음수 `tabindex` 0 |
| 1280×720 · 1440×900 이미지 | **충족** | 두 해상도 모두 캡처 확인 |

### 10.1 문맥 전환

「회사 문맥 전환」 → 권한 있는 조직만 트리로 표시(본사 아래 회계·제련공장·재무·물류·마케팅·
구매·생산(배터리소재/동제련)·품질·영업본부). 「조직 코드를 직접 입력하지 않습니다」 안내가
설계대로 붙어 있다.

**제련공장을 선택하니 상단이 `LS MnM · 제련공장 (시연 자료) · REAL` 로 바뀌고 업무 흐름의
단계 구성도 달라졌다**(전사: 원료도입→수주·영업…, 제련공장: 수주·판매→원료조달…).
문맥이 표시만이 아니라 데이터에 적용된다.

### 10.2 온톨로지 경로

시작점 `생산 계획행 2 · 2026-10-14 계획 · 37.3 TON` 으로 「경로 찾기」 →
**찾은 경로 1개**: `생산 계획행 2 → 판매 주문행 2 · 2026-10-31 납기 · 13.1 TON`(구간 1개).
자비스 패널에 「참고 중인 근거 · 기준시점 · 보이는 경로 1개」가 함께 표시된다.

### 10.3 계산 결과 — 「NO SILENT ZERO」가 실제로 작동한다

「이 경로로 계산」 → **BLOCKED**.

> 아직 계산할 수 없습니다 / 계산에 필요한 업무 데이터의 연결 조건이 충족되지 않았습니다.
> 다음 조치: 데이터 준비 상태에서 필수 열과 업무 연결 상태를 점검하십시오.

★ **0 을 만들지 않고 차단 사유와 다음 조치를 보여 준다.** 화면이 내건 「막힌 계산은 숫자가
아닙니다」가 말뿐이 아님을 실측으로 확인했다. 계산 상태가 `BLOCKED` 로 명시된다.

### 10.4 경영 질문 — 전송은 되고 응답은 막힌다

추천 질문 「이 경로가 막힌 이유는 무엇입니까?」를 보내니 대화에 내 질문이 남고,
`POST /api/v1/jarvis/ask` 가 **502** 로 돌아왔다. 화면은
「비서 응답을 받지 못했습니다 … 서버는 살아 있습니다. 실패하면 다시 시도해 보십시오」를
표시하고 상태를 「일시 중단」으로 바꾼다.

**원인은 LLM 키 부재다** — 복원 환경에 `.env` 가 없고(스냅샷이 의도적으로 제외) 프로세스
환경에도 LLM 키가 없다. 확인했다.

★ 이 502 는 **올바른 동작**이다. `jarvis_control.py:174` 주석이 그 이력을 적어 두었다 —
종전에는 엔진이 예외를 삼켜 「LLM 키가 없어 답을 못 만든 상황이 그대로 HTTP 200 success 로
나갔다」. 지금은 502 로 끊는다. 실패를 그럴듯한 답으로 대체하지 않는다.

### 10.5 ⚠️ 12px 미만 79건 — Gate 5 미충족

| 크기 | 건수 |
|---|---:|
| 11.5px | 2 |
| 11px | 25 |
| 10.5px | 49 |
| 10px | 2 |
| 9px | 1 |

**30자를 넘는 본문 성격의 텍스트는 0건**이다 — 전부 라벨·배지·짧은 상태 표시
(`OPERATING CONTEXT`, `REAL`, `결정`, `막힘` 등). 그래도 Gate 5 가 명시한 검사 항목이므로
**미충족으로 적는다.** AGENTS 가 「지금 UI 의 목적은 디자인 완성도가 아니다」라고 둔 범위와
겹치므로, 디자인 시안 확정 단계에서 함께 처리할 항목으로 본다.

### 10.6 이 절차에서 건드린 것

브라우저 창 크기를 1280×720 → 1440×900 으로 바꿨고 **되돌리지 않았다**(사용자 창이며 표준
크기다). 문맥 선택은 「제련공장 (시연 자료)」로 바꾼 상태로 두었다. 둘 다 화면에서 되돌릴
수 있다. 계산 실행은 읽기·판정이며 데이터를 쓰지 않았다.

## 11. 회사·사용자 전환 시 Studio 재확인 — 2026-09-15

§9 에서 범위 밖으로 남겼던 항목을 이어서 구현했다. `App.tsx` 한 파일이다.

### 무엇이 문제였나

전환 이벤트 두 개(`factory:enterprise-context-changed`·`factory:acting-user-changed`)를
받아 **SSE 만 다시 맺고 `currentProjectId` 는 그대로 두었다.** 바뀐 문맥에서 볼 수 없는
프로젝트가 화면에 남고, 그 위의 숫자가 어느 회사 것인지 알 수 없게 된다. 연결 전부터
그랬던 동작이다.

### 어떻게 고쳤나

`revalidateOpenProject()` 를 두 핸들러에 붙였다. **닫기만 하지 않고 같은 프로젝트를 새
문맥으로 다시 확인한다.**

1. 열려 있으면 `setCurrentProject(null)` — Studio 즉시 내림
2. `setEntryGateId(open)` — 진입 게이트로 되돌림
3. 서버가 판정 — 여전히 볼 수 있으면 다시 열리고, 없으면 거절 화면

★ 상위/하위 조직으로 옮긴 경우처럼 **여전히 보이는 경우를 닫아 버리지 않는다.** 조직 ID 를
화면에서 비교해 흉내 내지 않고 서버 판정을 따른다.

### 실측 — 탐침으로 확정했다

화면 스냅샷으로는 변화가 안 보였다. 확인 왕복이 1초 안에 끝나 「확인 중」 프레임을 잡지
못한 것이다. **임시 탐침을 코드에 넣어 상태 전이를 직접 확인하고 즉시 제거했다.**

| 시점 | `currentProjectId` |
|---|---|
| 전환 직전 | `b6-switch-canary` |
| `setCurrentProject(null)` 직후 | **null** — Studio 닫힘 |
| 1.2초 후 | `b6-switch-canary` — 재확인 성공해 다시 열림 |

⚠️ **처음에는 「동작하지 않는다」고 판단했다.** 스냅샷·네트워크 추적·WebSocket 카운트로
세 번 관찰했는데 모두 결론을 내기에 부족했다(네트워크 추적은 새로고침 시 리셋되고,
`connectSSE` 는 이미 연결돼 있으면 새 소켓을 만들지 않는다). 탐침을 넣고서야 확정했다.
**관찰 도구가 부족할 때 「안 된다」로 넘기지 않는다.**

거절 경로는 별도로 확인했다 — 문맥을 「제련공장」으로 둔 상태에서 본사 소유 프로젝트
직접 링크를 열면 거절 화면이 뜬다(§10.1 의 문맥 전환과 같은 판정).

### 검사

tsc 0 · build PASS · B5 계약 **153** · project-entry **26** · studio-location **25**.

### 남은 것

- `factory:session-changed`(로그인·로그아웃)는 이번 범위가 아니다. 로그아웃은 인증 게이트가
  전체를 되돌리므로 별도 경로다.
- Studio 화면 자체에는 회사 전환 UI 가 없다. 이 경로는 다른 탭·세션 변화로 이벤트가 올 때
  작동한다.

## 12. `new`·`release` 대상 연결 — 2026-09-15

### 먼저 조사한 것 — 다섯 대상은 사정이 다르다

⚠️ **서버의 진입 확인 API(`entry-metadata`)는 project 전용이다.** 나머지 넷에는 대응하는
확인 API 가 없다.

| 대상 | 서버 확인 API | 기존 진입 경로 | 이번 처리 |
|---|---|---|---|
| `new` | **불필요** — 만들기라 조회 대상이 없음 | `openBuildStart(type)` | **연결함** |
| `release` | 없음(`library/item` 은 일반 조회) | `viewRelease` — **실패를 삼킴** | **고치고 연결함** |
| `kit_app` | 없음 | 부분적 | 다음 묶음 |
| `mega` | 없음 | 프로젝트 속성으로만 존재 | 다음 묶음 |
| `draft` | 없음 | App 에 진입 경로 없음 | 다음 묶음 |

★ 남은 셋은 **서버 진입 확인 API 설계가 선행**돼야 한다. 없이 붙이면 프런트가 조직 판정을
흉내 내게 되고, 그것은 B6 인계가 명시적으로 금지한 것이다.

### 12.1 `new` — 확인할 것이 없는 곳에 확인 화면을 띄우지 않는다

`?space=build&target=new` 로 만들기 흐름을 연다. **진입 확인 게이트를 태우지 않는다** —
조회할 대상이 없기 때문이다. 실제 생성 POST 는 사용자가 폼에서 눌러야 나간다.

한 번만 연다. URL 의 진입 키는 아래 12.3 이 걷어 내므로 닫은 뒤 새로고침해도 되살아나지
않는다. **실측: 새로고침 후 대화상자 0개.**

### 12.2 `release` — 삼키던 실패를 먼저 고쳤다

⚠️ **기존 결함**: `viewRelease` 는 `res.ok` 가 아니면 **아무 일도 하지 않았다.** console 에만
남고 화면은 반응이 없다. 목록에서 눌러 여는 동안에는 드러나지 않지만 직접 링크로
들어오면 사용자는 **멎은 화면**을 본다.

`releaseLoad`/`releaseError` 를 더해 진행·실패를 상태로 남기고, App 에 거절 화면과 나갈
길을 두었다. **401·403·404 는 같은 문구**로 답한다 — 나누면 존재 여부가 응답으로 샌다.

실측: `?space=build&target=release&release=<없는 id>` →
「현재 회사·권한에서 결과물을 찾을 수 없습니다.」 + 경영 홈·앱 제작 버튼.

⚠️ **정상 경로는 확인하지 못했다.** 복원 스냅샷이 `library` 를 제외해 실제 릴리스 자산이
없다(`library/` 비어 있음). 거절 경로만 확인했다.

### 12.3 URL 진입 키를 App 이 소유한다

`target`·`draft_kind`·`draft`·`revision`·`instance`·`app`·`release`·`mega`·`child` 를 URL
동기화 때 걷어 낸다. 남겨 두면 새로고침·뒤로가기가 이미 처리한 진입을 다시 실행하거나,
반쪽짜리 쿼리가 남아 다음 해석을 흐린다. legacy `project` 만 다시 쓴다 — 기존 공유 링크가
그 형태다.

### 12.4 실측 요약

| 경로 | 결과 |
|---|---|
| `?space=build&target=new` | 만들기 흐름 열림 · URL `?space=build` 로 정리 · **새로고침 시 재등장 없음** |
| `?space=build&target=release&release=<없는 id>` | 거절 문구 + 나갈 길 · URL 정리 |
| `?project=<없는 id>` | 기존대로 거절 + 재확인 버튼 — **회귀 없음** |

tsc 0 · build PASS · B5 계약 **153** · project-entry **26** · studio-location **25**.

## 13. 오늘 만든 것을 잠갔다 — 프런트 계약·배선 검사 (2026-09-15)

⚠️ **연결을 마친 뒤 확인해 보니 오늘 만든 것 대부분이 잠기지 않은 상태였다.**

| 오늘 만든 것 | 검사 (추가 전) |
|---|---:|
| `studioKitAppEntry.ts`(124줄)·게이트 | **0건** |
| `viewRelease` 실패 처리 | **0건** |
| `revalidateOpenProject`(전환 재확인) | **0건** |
| `entryGateId`·`kitAppGate`(App 배선) | **0건** |

`project` 는 `check-project-entry.mjs` **26건**으로 잠겨 있는데 오늘 것들은 **서버 시험만**
있었다. 브라우저로 확인한 것은 오늘의 사실이지 내일의 보장이 아니다 — 누가 배선을 지우면
조용히 예전 동작(없는 프로젝트가 열리고, 회사를 바꿔도 화면이 남는)으로 돌아간다.

★ 어제 겪은 「생산자→소비자 배선 누락」의 **반대 방향**이다. 어제는 만들고 안 붙였고,
오늘은 붙이고 안 잠갔다.

### 13.1 `check-kit-app-entry.mjs` — 신규 **14건**

`check-project-entry.mjs` 와 같은 골격(모의 HTTP + 실제 flow/SSR + 소스 해시 보존).

API 계약 6건(단건 GET·no-store·허용 필드, **소유≠조회 정상**, 형식 위반 통신 전 차단,
응답 손상 7종 거절, 실패 상태가 서버 원문을 옮기지 않음, 문맥 변화 폐기) ·
flow 4건(로딩 중 기존 데이터 숨김, 전환 이벤트 즉시 무효화, 늦은 응답이 최신을 못 덮음,
해제 뒤 조회·이벤트 없음) · SSR 2건 · 해시 보존 1건.

★ **project 검사와 의도적으로 다른 한 건**: 「소유와 조회 문맥이 달라도 정상」. 목록 수준
판정이라 전사 조회 권한에서 갈릴 수 있다(§9 의 6번 결정).

### 13.2 `check-studio-contracts.mjs` — STATIC 배선 **4건** 추가 (153 → 157)

| 검사 | 잠그는 것 |
|---|---|
| 진입 확인 네 대상이 App 에 배선 | 파서 사용 · project/kit_app 게이트 · release 실패 표시 · new 는 게이트 없음 |
| 전환이 열린 Studio 를 재확인시킴 | **두 이벤트 모두**에 붙어 있는지 — 한쪽만 붙이면 그 경로로 옛 화면이 남는다 |
| URL 진입 키 9종 제거 | 남겨 두면 새로고침이 이미 처리한 진입을 다시 실행 |
| 조회 실패를 삼키지 않음 | `viewRelease` 가 loading/failed 를 남기고 401·403·404 를 한 문구로 접는지 |

**줄 단위로 검증했다** — 사용자 전환 쪽 재확인만 지워도 1건, kit_app 게이트만 지워도 1건이
실패한다. 복원하면 157 로 돌아온다.

### 13.3 ⚠️ 검사를 처음 썼을 때 둘이 틀렸다

- **`space` 를 금지 대상에 넣었다.** `URLSearchParams(...).get(` 전체를 금지했더니 App 의
  공간 선택까지 걸렸다. **`space` 는 App 소유다** — 파서가 다른 공간을 `NOT_STUDIO` 로
  넘기고, 문법 모듈 머리말이 「호출자는 자신이 소유한 무관한 query 를 별도로 보존한다」고
  적어 두었다. 금지할 것은 **진입 대상 키**를 직접 읽는 것이다.
- **타입 선언을 구현으로 잡았다.** `store.indexOf('viewRelease:')` 가 인터페이스의
  `viewRelease: (releaseId: string) => Promise<void>;` 를 먼저 찾았다. 그대로 뒀으면 구현을
  통째로 되돌려도 통과하는 **공허한 검사**가 됐다. `'viewRelease: async'` 로 좁혔다.

