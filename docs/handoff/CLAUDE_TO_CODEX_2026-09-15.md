# Claude Code → Codex 인계 (2026-09-15)

- 대상: 2026-09-15 하루치. 브랜치 `codex/l2-unified-studio-20260912`
- 기준: 당신의 `b13b73687` 위에 커밋 **17개**. **푸시 완료**(HEAD `802c4c815`)
- 앞 인계: [시작 안내](CLAUDE_CODE_START_HERE_2026-09-15.md) 를 입구로 삼아 §6 순서대로 진행했다
- 상세: [실서버·브라우저 기준선](L2_STUDIO_BROWSER_BASELINE_2026-09-15.md) ·
  [진입 대상 설계안](../design_l2_studio_entry_readers_2026-09-15.md)

> **코드를 바로 손대려면 §10(코드 지도) → §14(착수 순서)** 를 먼저 읽는다.
> **결정만 내리려면 §5** 로 간다. **같은 함정을 피하려면 §13.**

## 0. 처음 1분에 확인할 결론

- 전체 **21/40 = 52.5%**, 로컬 **18/28 ≈ 64.3% 유지.** 관문을 전진시키지 않았다.
- **당신이 막혔던 브라우저가 이 환경에서는 열렸다.** 복원 데이터로 경영 홈·계산·문맥
  전환을 실제로 확인했다(§3).
- **진입 대상 6종 중 4종을 연결했다** — `project`·`new`·`release`·`kit_app`.
  `mega`·`draft` 는 **당신 결정을 기다린다**(§5).
- **Gate 4 는 여섯 항목 전부 닫았다. Gate 5 는 「12px 미만 79건」 하나로 미충족**이다(§3).
- ⚠️ **당신 판단이 필요한 것이 다섯 가지 남아 있다**(§5). 합의 전에는 구현하지 않았다.
- ⚠️ **내가 네 번 틀렸고 전부 기록했다**(§6). 그중 하나는 사용자가 짚어 주어 알았다.

## 1. 커밋 17개 — 주요 15건

| SHA | 내용 | 주로 건드린 파일 |
|---|---|---|
| `bfd82f9a1` | 인계 검증·DB 복원·**연결 전 기준선 실측** | 기준선 문서 |
| `8d9de0435` | `project` 직접 링크를 서버 확인 뒤에만 열도록 연결 | `App.tsx` |
| `868565e15` | Gate 5 항목별 판정 | 기준선 문서 |
| `2be8ceced` | 회사·사용자 전환 시 열린 Studio 재확인 | `App.tsx` |
| `a490c3cd5` | 전환 재확인 기록 | `PROGRESS.md` |
| `cd490d8ba` | `new`·`release` 연결 + **`viewRelease` 가 삼키던 실패 수정** | `App.tsx` · `useFactoryStore.ts` |
| `15443b9e8` | 남은 세 대상 진입 확인 **설계안** | `design_…_2026-09-15.md` |
| `e68547a99` | 「자산이 없다」 서술 실측 정정 | 설계안 |
| `e9b7575ad` | `kit_app` 연결 전 기준선 | 기준선 문서 |
| `be0fad048` | `contract/v2` 404 원인 확정 | 기준선 문서 |
| `2a0544469` | `kit_app` 진입 확인 구현·연결 | `data_preparation_control.py` · `studioKitAppEntry.ts` · `StudioKitAppEntryGate.tsx` · `App.tsx` |
| `0c6189ab3` | 기록 | `PROGRESS.md` |
| `d777f38e4` | `kit_app` 서버 시험 17건 + **한글 ID 통과 결함 수정** | `test_b6_kit_app_entry.py` · `data_preparation_control.py` |
| `dd6348f57` | 기록 | `PROGRESS.md` |
| `bb8abc329` | **프런트 계약·배선 검사** — kit-app-entry 14 신설 + STATIC 배선 4 | `check-kit-app-entry.mjs` · `check-studio-contracts.mjs` |

나머지 둘은 인계·진척 기록이다. `main.py` **diff 0**.

**파일 단위 총계** — 13파일 **+2,122 / −16**.

| 신규 7 | 줄 |
|---|---|
| `frontend/src/factory/studioKitAppEntry.ts` | 124 |
| `frontend/src/factory/StudioKitAppEntryGate.tsx` | 31 |
| `frontend/scripts/check-kit-app-entry.mjs` | 187 |
| `tests/test_b6_kit_app_entry.py` | 150 |
| `docs/design_l2_studio_entry_readers_2026-09-15.md` | 426 |
| `docs/handoff/L2_STUDIO_BROWSER_BASELINE_2026-09-15.md` | 549 |
| `docs/handoff/CLAUDE_TO_CODEX_2026-09-15.md` | 이 문서 |

| 수정 6 | 증감 |
|---|---|
| `frontend/src/App.tsx` | +223 |
| `api/routes/data_preparation_control.py` | +67 |
| `frontend/scripts/check-studio-contracts.mjs` | +52 |
| `frontend/src/store/useFactoryStore.ts` | +35 |
| `PROGRESS.md` · `.agents/TEAM_BOARD.md` | +38 씩 |

## 2. 환경 — 실행 데이터를 살렸다

스냅샷 ZIP 을 정석 경로 `C:\WorkSpace\gemini_agent_team_verG` 에 복원했다
(**164파일 · `absolute_root_matches: true` · 15DB · 41,159행 · RAW 144**).

복원 위치는 선택 여지가 없었다 — `restore_snapshot():237` 이 `source_root` 와 경로 일치를
강제하고, `core/paths.py` 가 데이터 경로를 코드 위치로 고정하며 환경변수 덮어쓰기를 막는다.

★ **venv 를 새로 만들지 않았다.** 기존 venv 파이썬으로 복원 checkout 의 `run.py` 를
실행하면 그쪽 데이터를 본다(약 20분 절약).

| 구성 | 값 |
|---|---|
| 백엔드 | `127.0.0.1:8090` — 복원 checkout |
| 프런트 | `localhost:5183` — 이 워크트리 dev 서버 |
| 로그인 | 사용자가 직접(`hikwon@lsmnm.com`). **비밀번호 입력은 내 금지 행위** |

⚠️ 5183 은 IPv6 로 열린다. `localhost:5183` 으로 접속한다.
⚠️ 당신 환경의 8080·5173 은 **건드리지 않았다.**
⚠️ **두 서버는 지금 꺼져 있다** — 인계 시점에 사용자가 직접 종료했다. 화면을 다시 보려면
§9.1 기동 절차부터 밟는다. **데이터는 남아 있다**(복원 checkout 은 그대로다).

## 3. Gate 판정 — 하나 남았다

**Gate 4 실서버 카나리 — 여섯 항목 전부 충족.** 다른 조직 404 은닉과 Resolver 장애
503·원문 비노출까지 카나리 대상을 만들어 닫고 즉시 제거했다.

**Gate 5 브라우저 E2E — 「12px 미만 79건」 하나로 미충족.**

| 항목 | 판정 |
|---|---|
| 로그인 세션·문맥 전환·온톨로지 경로·계산 결과·상태 구분·가로 넘침·키보드 | **충족** |
| 경영 질문 | **부분** — 전송은 되고 응답이 502(LLM 키 부재. 스냅샷이 `.env` 제외) |
| **12px 미만** | **미충족 — 79건** (전부 라벨·배지, 30자 초과 본문 0건) |

★ **「NO SILENT ZERO」가 말뿐이 아니었다.** 계산을 실행하니 `BLOCKED` 와 차단 사유·다음
조치를 보여 준다. 0 을 만들지 않는다.

★ 자비스 502 는 **올바른 동작**이다. `jarvis_control.py:174` 주석대로 종전에는 키가 없어
답을 못 만든 상황이 HTTP 200 success 로 나갔고 지금은 끊는다.

## 4. 무엇을 연결했나

### 4.1 연결 전 기준선 — 대조군을 먼저 남겼다

| 대상 | 연결 전 |
|---|---|
| `project` | **잘못 열림** — 없는 id 인데 작업공간이 렌더링되고 404 4종이 「서버 연결 끊김」으로 보임. SSE 구독까지 맺음 |
| `kit_app` | **조용히 안 열림** — 오류도 안내도 없이 목록면 |

### 4.2 연결 후

| 대상 | 방식 | 확인 |
|---|---|---|
| `project` | 진입 확인 게이트 | 거절 문구+재확인 / 정상은 **서버가 준 이름**으로 열림 |
| `new` | **게이트 없음** — 조회 대상이 없다 | 만들기 흐름 열림, 새로고침 재등장 없음 |
| `release` | 기존 조회 + **실패 상태 신설** | 거절 문구+나갈 길 |
| `kit_app` | **진입 확인 API 신설**(목록 수준) | 정상은 경로 계산 패널, 없는 앱은 거절 |

★ URL 진입 키 9종을 동기화 때 걷어 낸다. 남겨 두면 새로고침이 이미 처리한 진입을 다시
실행한다. legacy `project` 만 다시 쓴다.

★ **회사·사용자 전환 시 열린 Studio 를 새 문맥으로 다시 확인한다.** 닫고 끝내지 않는다 —
상위/하위 조직 이동처럼 여전히 보이는 경우를 닫아 버리지 않기 위해서다.

### 4.3 고친 기존 결함 둘

- **`viewRelease` 가 실패를 삼켰다.** `res.ok` 가 아니면 아무 일도 하지 않아 직접 링크로
  들어오면 화면이 멎는다. 진행·실패를 상태로 남기고 401·403·404 를 같은 문구로 답한다.
- **`str.isalnum()` 이 한글을 통과시켰다.** 내가 만든 `app_id` 형식 검사가 한글·한자 ID 를
  뚫렸다. 정규식 명시 집합으로 교체했다(§6.3).

## 5. ⚠️ 당신이 결정해야 할 다섯 가지

설계안 §6 에 근거와 함께 적었다. **합의 전에는 구현하지 않았다.**
각 항목에 「결정되면 어디부터 손대는가」를 붙였다.

### 5.1 `mega` 의 부모-자식 관계를 서버가 답하는가

`mega` 는 project 의 한 종류라 새 API 없이 `entry-metadata` 확장으로 될 수 있다.
다만 **프런트가 두 응답을 받아 관계를 추론하면 안 된다** — 부모와 자식을 각각 조회해
「둘 다 보이니 부모-자식이겠지」로 잇는 순간, 권한이 갈린 조직에서 없는 관계를 만든다.

- **확장으로 간다면**: `api/routes/factory_control.py:2582` 의 `entry-metadata` 에
  부모·자식 필드를 더하고, `studioProjectEntry.ts` 의 응답 검증에 필드를 추가한다.
  프런트 호출은 **한 번**으로 유지한다.
- **새 API 로 간다면**: `kit_app` 과 같은 골격으로 `studioMegaEntry.ts` 를 만든다(§11).

### 5.2 `kit_app` 의 선택적 `releaseId` 를 진입 확인 범위에 넣는가

지금은 `studioLocation.ts` 가 **문법으로만 받고 쓰지 않는다.** 진입 확인은 인스턴스+앱만
본다. 넣기로 하면 서버가 「이 앱의 이 릴리스인가」까지 답해야 하고, 목록 수준 판정과
어긋나는지 먼저 정해야 한다 — 목록은 릴리스를 구분해 보여 주지 않는다.

### 5.3 `draft` 를 새 엔드포인트로 갈 것인가

⚠️ **기존 `GET /drafts/{draft_id}` 가 경계를 쿼리 인자로 받는다.** URL 진입에 그대로 쓰면
프런트가 경계를 만들어 넣게 되고, 현재 선택과 어긋나면 **다른 문맥의 초안을 여는 길**이
열린다. 조용히 열리는 종류의 구멍이라 시험이 없으면 안 잡힌다.

- 권고: **경계를 인자로 받지 않는 진입 전용 엔드포인트**를 새로 만든다. 서버가 현재
  주체의 문맥으로만 판정한다.
- ⚠️ 실측: 초안 자산은 **0행**이다(§6.1). 구현해도 **실측 검증이 안 된다** — 시험용 초안을
  만들어 넣는 절차를 먼저 정해야 한다.

### 5.4 공통 헬퍼 추출 시점

지금 네 대상의 불변식이 복제돼 있다. **헬퍼를 먼저 뽑고 대상을 얹는 순서를 권고**했다 —
반대로 하면 복제본이 셋 생긴 뒤 합치게 된다. 복제 실태는 **§11 에 실측으로 정리**했다.

### 5.5 담당 분담

서버 API 가 세 라우터를 건드리고 B5/B6 계약과 맞물린다. 프런트만 먼저 가면 서버 응답
모양이 바뀔 때 계약 시험을 두 번 고치게 된다.

★ 6·7번(진입 확인의 `unrestricted` 처리, v2 연결 없는 인스턴스 통과 여부)은 **사용자가
「목록 수준」으로 결정**해 그대로 구현했다. 재론이 필요하면 설계안 §6-6·§6-7 을 본다.

## 6. ⚠️ 내가 틀린 것 넷 — 그대로 남긴다

### 6.1 「자산이 없다」를 확인 없이 단정했다 — 사용자가 짚어 알았다

설계안 첫 판에 「릴리스·키트 앱·초안 자산이 복원 데이터에 없다」고 적었다. **`library/`
디렉터리가 빈 것만 보고 셋을 싸잡아 일반화**했고 DB 를 확인하지 않았다.

실측하니 **키트 인스턴스 1 + 승인된 앱 7개(전부 `AVAILABLE`)** 가 있었고, 릴리스도
**결속 69행·ID 8종**이 남아 있었다(산출물 파일만 없다). 초안만 실제로 0행이었다.

★ 이 정정으로 `kit_app` 을 **실측 검증할 수 있게** 됐고, 오늘 그것으로 구현·시험을 마쳤다.
사용자가 짚지 않았으면 「검증 불가」로 남겨 뒀을 것이다.

### 6.2 관찰 도구의 한계를 「동작 안 함」으로 읽었다 — 두 번

- **회사 전환 재확인**: 화면 스냅샷·네트워크 추적·WebSocket 카운트 세 방법이 모두 실패처럼
  보였다. 임시 탐침을 넣고서야 **1.2초 안에 왕복을 마치는 정상 동작**임을 확정했다.
  추적은 새로고침 시 리셋되고 `connectSSE` 는 기존 연결이면 새 소켓을 만들지 않는다.
- **`new`·`kit_app` 연결**: 화면 텍스트 **앞부분만** 보고 「안 열렸다」고 판단할 뻔했다.
  오버레이가 뒤에 있었다.

★ **부분 관찰로 결론 내지 않는다.** 도구가 못 보는 것을 「없다」로 적으면 다음 사람이
멀쩡한 기능을 다시 만든다.

### 6.3 내가 만든 코드에서 같은 원칙을 두 번 어겼다

- **은닉 문구를 둘로 만들었다.** `kit_app` 진입 확인 첫 구현에서 「업무 앱 없음」과
  「인스턴스 없음」이 다른 문구가 됐다 — 인스턴스 존재가 샌다. 설계안에 「같은 문구로
  답하라」고 적어 놓고 어긴 자리다.
- **느슨한 시험을 썼다.** 형식 위반을 `in (400, 404, 405)` 로 받아 **형식 검사를 지워도
  통과**했다. 줄 단위 검증에서 발견해 400 을 강제하도록 조였고, **조이자마자 한글 ID 가
  통과하는 제품 결함이 드러났다** — `str.isalnum()` 이 유니코드를 참으로 본다.

★ 둘 다 **줄 단위 검증**이 잡았다. 통과만 보고 넘어갔으면 남았다.

### 6.4 검사를 처음 쓸 때도 둘 틀렸다 — 검사 자체가 가짜 통과를 낼 뻔했다

- **금지 범위를 너무 넓게 잡았다.** `URLSearchParams(...).get(` 을 통째로 금지했더니
  App 자기 소유인 `space` 키까지 걸렸다. 진입 대상 키 9종만 금지하도록 좁혔다.
- **타입 선언을 구현으로 착각했다.** `store.indexOf('viewRelease:')` 가 타입 선언을 먼저
  잡아서, **구현이 비어 있어도 통과**할 수 있었다. `'viewRelease: async'` 로 좁혔다.

★ 검사는 「있는지」가 아니라 **「없으면 실패하는지」로 확인**해야 한다. 지워 보기 전에는
통과가 무슨 뜻인지 모른다.

## 7. 검증 — 최종 실행 기준

| 대상 | 결과 |
|---|---|
| 서버 (strict-writes, 7파일) | **148 PASS / 0 FAIL** · 229.32초 |
| 격리 증거 | `sources_unchanged`·`protected_assets_unchanged` **true** · 차단 쓰기 0 · conftest 미적재 |
| 프런트 B5 계약 `check-studio-contracts.mjs` | **157 PASS** (153 + STATIC 배선 4) |
| `check-kit-app-entry.mjs` (신규) | **14 PASS** |
| `check-project-entry.mjs` | **26 PASS** |
| `check-studio-location.mjs` | **25 PASS** |
| `check-process-installation.mjs` | **105 PASS** |
| tsc · 제품 build | 오류 0 · PASS |

**신설 검사 14건의 내역** — `check-kit-app-entry.mjs`

| 묶음 | 건 | 무엇을 잡는가 |
|---|---|---|
| API 계약 | 7 | 단건 GET·`no-store`·허용 필드만 / **소유≠조회 정상**(목록 수준) / 통신 전 형식 차단 / 대상 불일치·필드 손상 거절 / 실패 상태의 본문 비전파 / 문맥 변경 시 응답 폐기 / 선택 문맥과 다른 조회 문맥 거절 |
| FLOW | 4 | 로딩 중 이전 데이터 숨김 / 회사 전환 즉시 무효화 / 늦은 응답이 최신을 못 덮음 / 해제 뒤 조회·이벤트 없음 |
| SSR | 2 | 확인 전 자식 미생성·GET 없음 / **조회 가능과 실행 승인을 구분해 말함** |
| 해시 보존 | 1 | 소스·검사 파일을 검사가 건드리지 않음 |

**STATIC 배선 4건의 위치** — `check-studio-contracts.mjs`

| 줄 | 이름 |
|---|---|
| 373 | B6 STATIC 진입 확인 네 대상이 App 에 배선돼 있다 |
| 388 | B6 STATIC 회사·사용자 전환이 열린 Studio 를 다시 확인시킨다 |
| 399 | B6 STATIC URL 진입 키를 App 이 걷어 낸다 |
| 407 | B6 STATIC 조회 실패를 삼키지 않는다 |

**줄 단위 검증 기록** — 차단하는 줄을 지우면 대응 시험만 실패한다.

| 지운 것 | 실패 |
|---|---|
| `kit_app` 은닉 문구 통일 | 1건 |
| `kit_app` 앱 존재 확인 | 6건 |
| `kit_app` 형식 검사 | 5건 |
| 사용자 전환 재확인 배선 | 1건 |
| `kit_app` 게이트 배선 | 1건 |

**실제 브라우저로 확인한 것**: 경영 홈 렌더링, 문맥 전환, 온톨로지 경로, 계산 BLOCKED,
네 대상의 정상·거절 경로, 1280×720·1440×900 두 해상도.

**NOT_RUN**: 현업 수용, 실제 LLM 응답(키 부재), `release` 정상 경로(산출물 없음),
`draft` 전 범위(자산 0행).

## 8. 남은 일

| 항목 | 상태 | 착수 |
|---|---|---|
| `mega`·`draft` 연결 | **당신 결정 대기**(§5.1·§5.3) | 결정 후 |
| 공통 헬퍼 추출 | 미결 — 복제 실태는 §11 | 결정 후 |
| **오류 코드 도달 가능성 조사** | 어제 대응표가 남긴 물음. 선언만 있고 도달 경로가 없는 코드가 섞였을 수 있다 | **지금 가능** |
| **T25·T29·T39·T40 서버 시험** | 명세만 있고 시험 없음(§12.3) | **지금 가능** |
| 12px 미만 79건 | Gate 5 미충족. 디자인 시안 확정 단계 항목으로 본다 | 시안 확정 후 |
| 로그인·로그아웃 이벤트 경로 | 범위 밖. 인증 게이트가 전체를 되돌리는 별도 경로다 | — |
| `release` 진입 확인 API | 없음. 기존 조회 + 실패 상태로 대응했다. 다른 셋과 같은 수준으로 맞추려면 별도 논의 | 논의 후 |
| `entry-metadata` 첫 호출 503 1회 | **원인 미확정.** 재현되지 않았다. 다시 보이면 기록을 남긴다 | 재현 시 |

## 9. 재현 명령

### 9.1 서버 기동 (현재 꺼져 있다)

백엔드 — 복원 checkout 의 데이터를 본다. venv 는 이 워크트리 것을 쓴다.

```powershell
venv/Scripts/python.exe C:\WorkSpace\gemini_agent_team_verG\run.py
```

프런트 — 이 워크트리에서. `localhost:5183` (IPv6).

```powershell
npm.cmd --prefix frontend run dev -- --port 5183
```

로그인은 **사용자가 직접** 한다(`hikwon@lsmnm.com`).

### 9.2 서버 시험

```powershell
venv/Scripts/python.exe -B scripts/verify_data_usage_holds.py --strict-writes --target tests/test_b6_kit_app_entry.py --target tests/test_b6_project_entry.py --target tests/test_b6_revision_reads.py --target tests/test_b2_installation.py --target tests/test_b2_installation_api.py --target tests/test_b3_execution_context.py --target tests/test_b5_hotl_submission_api.py
```

### 9.3 프런트 검사 — `frontend` 에서

```bash
node scripts/check-studio-contracts.mjs
```

```bash
node scripts/check-kit-app-entry.mjs
```

```bash
node scripts/check-project-entry.mjs
```

```bash
node scripts/check-studio-location.mjs
```

```bash
node scripts/check-process-installation.mjs
```

이어서 `npx.cmd tsc --noEmit` · `npm.cmd run build`.

실행 데이터 화면은 [기준선 문서](L2_STUDIO_BROWSER_BASELINE_2026-09-15.md) §8 참조.

## 10. 코드 지도 — 직접 링크 한 번에 무엇이 도는가

### 10.1 흐름

```
URL ?target=kit_app&instance=…&app=…
  └─ studioLocation.ts        문법만 판정 → MATCH / LIST / NOT_STUDIO / INVALID_TARGET
       └─ App.tsx:87 readStudioEntry()      MATCH 를 네 갈래로 나눔
            └─ App.tsx:184-185 게이트 상태   entryGateId · kitAppGate
                 └─ StudioKitAppEntryGate    확인 전에는 자식을 만들지 않음
                      └─ studioKitAppEntry   readKitAppEntry → GET entry-metadata
                           └─ 서버 판정      data_preparation_control.py:1135
```

★ **순수 문법 파서와 서버 확인이 분리돼 있다.** `studioLocation.ts` 는 네트워크를 모른다.
「열어도 되는가」는 전적으로 서버가 답한다. 이 분리를 깨지 않는다.

### 10.2 파일 위치

| 층 | 파일 | 줄 |
|---|---|---|
| 문법 파서 | `frontend/src/factory/studioLocation.ts` | 227 |
| project reader | `frontend/src/factory/studioProjectEntry.ts` | 113 |
| project 게이트 | `frontend/src/factory/StudioProjectEntryGate.tsx` | 31 |
| kit_app reader | `frontend/src/factory/studioKitAppEntry.ts` | 124 |
| kit_app 게이트 | `frontend/src/factory/StudioKitAppEntryGate.tsx` | 31 |
| release 조회·실패 상태 | `frontend/src/store/useFactoryStore.ts` 의 `viewRelease` | — |
| 서버 project | `api/routes/factory_control.py:2582` | — |
| 서버 kit_app | `api/routes/data_preparation_control.py:1135` | — |

### 10.3 `App.tsx` 안의 진입 관련 자리

| 줄 | 무엇 |
|---|---|
| 87 | `readStudioEntry()` — MATCH 를 `project`/`isNew`/`release`/`kitApp` 로 |
| 156 | `initialEntry` — 최초 1회만 읽는다 |
| 177 | `routeRestored` — 복원 전에는 URL 동기화를 하지 않는다 |
| 184 · 185 | `entryGateId` · `kitAppGate` 게이트 상태 |
| 197 | `revalidateOpenProject()` — 전환 시 **닫지 않고 다시 확인** |
| 206–222 | URL 동기화. **진입 키 9종을 여기서 걷어 낸다** |
| 329 · 340 | 세션·회사 전환 이벤트에 `revalidateOpenProject` 연결 |
| 1244–1266 | `kitAppGate` 렌더 |
| 1276–1305 | `entryGateId` 렌더 |

⚠️ **1244 의 `!showPathCalc` 조건**에 주의한다. 경로 계산 패널이 열려 있으면 게이트를
그리지 않는다. `mega` 를 얹을 때 이런 상호배타 조건이 또 필요한지 먼저 본다.

## 11. 네 대상에 복제된 불변식 — §5.4 판단 자료

`studioProjectEntry.ts`(113줄) 와 `studioKitAppEntry.ts`(124줄) 는 **export 심볼 구조가
완전히 같다.**

| project | kit_app |
|---|---|
| `type ProjectEntry` | `type KitAppEntry` |
| `class ProjectEntryError` | `class KitAppEntryError` |
| `readProjectEntry(projectId, signal?)` | `readKitAppEntry(instanceId, appId, signal?)` |
| `type ProjectEntryState` | `type KitAppEntryState` |
| `createProjectEntryFlow(projectId)` | `createKitAppEntryFlow(instanceId, appId)` |

**양쪽에 같은 모양으로 들어 있는 불변식 9가지** — 헬퍼로 뽑는다면 이것들이다.

1. ID 문법 검사 `^[A-Za-z0-9_-]{1,160}$` — **통신 전에** 끊는다
2. 호출 전후 문맥 동일성 확인 (`studioIdentityKey()` 비교, `current()`)
3. `cache: 'no-store'` 단건 GET
4. 실패 상태의 **본문 비전파** — 401 은 로그인 안내, 400·403·404 는 **같은 은닉 문구**
5. 응답 봉투 검증 (`status === 'success'`, 대상 id 일치, 필드 타입·길이)
6. 선택 문맥과 응답의 조회 문맥 대조 → `CONTEXT_CHANGED`
7. 확장 필드 **비복사** — 준비도·계약·릴리스를 진입 확인이 나르지 않는다
8. flow 의 generation·AbortController 로 **늦은 응답 폐기**
9. 세 이벤트(`session-changed`·`acting-user-changed`·`enterprise-context-changed`) 구독과
   `dispose()` 시 해제

**의도적으로 다른 곳은 단 한 줄이다.**

```
studioProjectEntry.ts:51
  || owner.tenant_id !== view.tenant_id || owner.entity_mode !== view.entity_mode) throw malformed();
```

project 는 **소유와 조회 문맥이 다르면 잘못된 응답**으로 본다. `kit_app` 에는 이 줄이
**없다** — 목록 수준 판정이라 전사 조회 권한에서 둘이 갈릴 수 있기 때문이다(설계안 §6-6).

★ 헬퍼를 뽑는다면 **이 한 줄을 옵션으로 받는 형태**가 된다. 나머지 9가지는 그대로 공유
가능하다. 두 파일을 일부러 같은 모양으로 유지한 이유가 이것이다 — 옮기기 쉽게.

⚠️ **헬퍼를 뽑을 때 시험을 같이 합치지 말 것.** `check-project-entry.mjs`(26) 와
`check-kit-app-entry.mjs`(14) 는 **각 대상의 계약**을 보는 것이지 헬퍼 구현을 보는 것이
아니다. 헬퍼가 생겨도 두 검사는 **고치지 않고 그대로 통과**해야 한다 — 그게 헬퍼가 맞게
뽑혔다는 증거다. 검사를 같이 고쳐야 통과한다면 뽑기가 틀린 것이다.

## 12. 계약 세부 — 다음 대상을 같은 모양으로 만들 때 쓴다

### 12.1 오류 코드

| project | kit_app | 상태 | 뜻 |
|---|---|---|---|
| `ENTRY_INVALID_TARGET` | `KIT_APP_ENTRY_INVALID_TARGET` | 422 | 문법 위반. **통신 전** |
| `ENTRY_CONTEXT_CHANGED` | `KIT_APP_ENTRY_CONTEXT_CHANGED` | 409 | 회사·사용자가 바뀜 |
| `ENTRY_RESPONSE_INVALID` | `KIT_APP_ENTRY_RESPONSE_INVALID` | 503 | 응답 봉투 손상 |
| `ENTRY_CONNECTION_FAILED` | `KIT_APP_ENTRY_CONNECTION_FAILED` | 503 | 연결 실패 |
| `ENTRY_UNAVAILABLE` | `KIT_APP_ENTRY_UNAVAILABLE` | 503 | 기본값 |
| `ENTRY_HTTP_{status}` | `KIT_APP_ENTRY_HTTP_{status}` | 동적 | 서버가 준 상태 그대로 |

⚠️ **접두사가 다르다.** project 는 `ENTRY_`, kit_app 은 `KIT_APP_ENTRY_`. 헬퍼로 합칠 때
어느 쪽으로 통일할지 정해야 하고, 바꾸는 쪽의 시험을 같이 고쳐야 한다.

### 12.2 화면 문구 — 은닉 규칙

| 상태 | 문구 |
|---|---|
| 401 | `로그인이 필요합니다.` |
| 400 · 403 · 404 | `현재 회사·권한에서 업무 앱을 찾을 수 없습니다.` — **셋이 같아야 한다** |
| 409 | `확인 중 문맥이 바뀌었습니다. 다시 확인하세요.` |
| 그 외 | `업무 앱을 확인하지 못했습니다. 잠시 후 다시 확인하세요.` |

서버 쪽 은닉 문구는 `현재 문맥에서 업무 앱을 찾을 수 없습니다.` 하나다
(`data_preparation_control.py` 의 `hidden`). **없는 앱과 없는 인스턴스가 같은 문구**를
쓴다 — 다르면 인스턴스 존재가 샌다(§6.3).

### 12.3 아직 시험이 없는 명세 넷

`docs/design_business_kit_l2_process_setup_2026-09-12.md` 의 대응표에서.

| 번호 | 명세 | 기대 |
|---|---|---|
| T25 | 잘못된 부모·순환·알 수 없는 schema | 검증 실패, 부분 적용 없음 |
| T29 | 1 앱→여러 L2 / 1 L2→여러 앱 | 앱·릴리스 복제 없이 참조, 권한별 필터 |
| T39 | 인스턴스 active 지만 셋업 미완료 | 새 공식 프로세스 연결/문맥 발급 차단, 기존 앱 보존 |
| T40 | 홈·생성기의 동일 범위 조회 | 같은 승인 profile_id/digest, 범위 해석 불일치 없음 |

★ T29 는 **`mega` 설계와 맞물린다**(1 L2 → 여러 앱). §5.1 결정 전에 T29 시험을 먼저
써 두면 결정의 근거가 된다.

## 13. ⚠️ 이어받는 사람이 밟을 함정

오늘 실제로 밟았거나 밟을 뻔한 것만 적는다.

1. **`git add .` · `git add -A` 금지**(지침 §9). 파일을 짚어서 넣는다.
2. **`data/interaction_log.jsonl` 은 사용자 소유다.** 지우지도 커밋하지도 않는다.
3. **시험에서 운영 경로를 `core.paths.data_path()` 로 계산하지 않는다.** conftest 가
   `DATA_DIR` 을 tmp 로 돌려 감시자 판정이 **뒤집힌다**(실측 2건). `PROJECT_ROOT/data` 로
   고정한다.
4. **`_apply()` 의 반환값에 인스턴스 참조가 없다.** `applied["kit_instance_ref"]` 는
   KeyError 다. `_read(w)["payload"]["template_sources"][0]["kit_instance_ref"]` 를 쓴다.
5. **느슨한 상태 코드 단언을 쓰지 않는다.** `in (400, 404, 405)` 로 받으면 검사를 통째로
   지워도 통과한다(§6.3). 라우팅에서 갈리는 경우만 예외로 두고 이유를 적는다.
6. **검사를 넣었으면 대상 줄을 지워 본다.** 실패하지 않으면 그 검사는 아무것도 안 지킨다.
7. **화면 텍스트 앞부분만 보고 판단하지 않는다.** 오버레이가 뒤에 있을 수 있다(§6.2).
8. **실행 중인 서버의 DB 파일을 옮기지 않는다.** 자동 모드에서 차단된다. 서버를 먼저
   내리고, 조작하고, 되돌린다.
9. **URL 진입 키를 동기화에서 빼먹지 않는다.** 남기면 새로고침이 진입을 재실행한다.
   현재 걷어 내는 키: `target`·`draft_kind`·`draft`·`revision`·`instance`·`app`·
   `release`·`mega`·`child`. legacy `project` 만 남긴다.

## 14. 착수 순서 제안

결정(§5)이 나온 뒤를 가정한 순서다. **내 권고이지 확정이 아니다.**

1. **공통 헬퍼 먼저**(§5.4). 지금은 복제본이 둘이다. `mega`·`draft` 를 먼저 얹으면 넷이
   된다. §11 의 9가지를 헬퍼로 뽑고, `check-project-entry.mjs`·`check-kit-app-entry.mjs`
   **두 검사를 고치지 않고 통과하는지**로 확인한다.
2. **T29 시험**(§12.3). `mega` 결정의 근거가 된다. 지금 쓸 수 있다.
3. **`mega`** — §5.1 이 「확장」이면 서버 한 곳 + 응답 검증 한 곳이다. 「새 API」면
   헬퍼 위에 `studioMegaEntry.ts` 를 얹는다.
4. **`draft`** — §5.3. ⚠️ **시험용 초안을 만들어 넣는 절차부터** 정한다. 자산이 0행이라
   지금은 구현해도 실측 검증이 안 된다.
5. **오류 코드 도달 가능성 조사**(§8). 헬퍼 추출과 같이 하면 한 번에 정리된다 — 접두사
   통일(§12.1)도 이때 결정한다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
