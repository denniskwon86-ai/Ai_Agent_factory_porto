# B5 일반 HOTL 저장 초안 사용완료 결속 — 구현·집중 검증 인계

## 추가: `check-process-installation` 회귀 해소 — 2026-09-14 KST

Claude Code / 권고10 / G3. 전체21/40=52.5% **유지**(검사 복구이며 제품 기능 변화 없음).

> **정정:** 아래 두 절이 이 실패를 「이 워크트리의 CRLF 체크아웃 때문」이라고 적었다.
> **그 진단은 틀렸다.** 문제의 정규식은 `\s*` 를 쓰므로 CRLF 에서도 매칭된다. 줄바꿈과
> 무관하며 아래 두 절의 해당 문장은 이 절이 대체한다.

### 실제 원인 — 같은 커밋 안에서 소스와 검사가 어긋났다

`58713ed1d`(Codex, 9/13)가 `check-process-installation.mjs` 1,696줄을 신규 추가하면서
같은 커밋에서 `KitOperationsPanel.tsx` 의 조회 의존성을 바꿨다.

    -  }, [revision]);
    +  }, [revision, identity]);

검사는 `/\},\s*\[revision\]\)/` **정확 일치**를 요구해 `identity` 가 붙자 닫혔다.
104PASS 뒤 `AssertionError` 로 중단했다.

★ **소스 쪽이 옳다.** 사용자·회사 전환 시 목록을 다시 읽어야 하고, 같은 effect 안에서
`identity !== studioIdentityKey()` 로 늦은 응답을 버린다. 의존성에서 빼면 문맥 전환 후
옛 목록이 남는다.

### 조치

같은 파일의 `EnterprisePage` 검사와 **같은 방식**으로 맞췄다 — 의존성 배열을 뽑아
이름이 들어 있는지만 본다. 정확 일치를 요구하지 않는다.

    const instanceDeps = text.match(/listInstances\(\)[\s\S]*?\},\s*\[([^\]]*)\]\)/)?.[1] || '';
    assert.match(instanceDeps, /\brevision\b/);

검사 의도(닫은 뒤 재조회가 배선돼 있다)는 그대로다. 의존성 추가는 이 검사가 막으려는
것이 아니다. 제품 소스는 고치지 않았다.

### 검증

`node scripts/check-process-installation.mjs` → **105 PASS / exit 0**(종전 104PASS 뒤 중단).

⚠️ 다른 팀원(Codex)이 만든 검사를 고쳤다. 소스가 옳고 검사가 좁았다는 판단이며,
동일 파일 내 기존 방식에 맞춘 것이다. 이견이 있으면 이 절을 근거로 되돌릴 수 있다.
Codex 인계 §4 검증 근거 표에 이 검사가 없고 마지막 통과 기록이 B4 17:14 시점인 것으로
보아, 문제의 커밋 뒤 이 명령을 다시 돌리지 않은 것으로 보인다.

---

## 추가: 구 release·replan 접수 기록 마감 — 2026-09-14 KST

Claude Code / 권고4·7·10 / G2→G3. 전체21/40=52.5%, 로컬18/28≈64.3% **유지**. 23:03 Codex
인계가 잔여로 남긴 「legacy release/replan의 내구 영수증 없는 UNKNOWN」을 닫았다. 아래 절보다
이 절이 최신이다. B5전체/B6/B7 완료는 아니다.

### 구현 계약

- 실행 명령에 `RELEASE`·`REPLAN`을 더했다. 종전 두 경로는 원키 없는 직접 POST 였고, 응답이
  유실되면 저장·재분할 여부를 확인할 방법이 없었다. **REPLAN 은 되돌릴 수 없다** — 기존 WBS 가
  사라지는데 다시 눌러 또 지웠다. 같은 문제를 같은 상태 기계로 닫는다. 새 저장소를 만들지 않았다.
- 둘 다 `EXECUTIONS`다. 결과 확인이 필요한 명령이 남은 프로젝트에서는 새 실행이 `PROJECT_BUSY`로
  막힌다. UNKNOWN 을 다른 키로 우회해 재실행할 수 없다.
- `PROJECT_SCOPED = {RELEASE, REPLAN}`, `PROJECT_TASK = "PROJECT"`. 프로젝트 단위 명령은
  task 별 입력을 받지 않고 task_id 도 고정값만 받는다(422). 임의 task 를 기록에 남기면
  「어느 작업에 적용됐나」가 실제 적용 범위와 달라진다.
- 서버는 기존 `factory.create_release`·`factory.replan_wbs` handler 를 그대로 부른다. 서버 동작과
  기존 경로는 바뀌지 않았다. 두 명령은 `mark_effect_started()`를 먼저 표시한다 — 되돌릴 수 없는
  쓰기가 응답 유실로 REJECTED 오판되지 않게 한다.
- 프런트 `saveProjectRelease`·`replanWbs`를 `postExecution`으로 옮겼다. 응답 모양이 다른 두
  명령의 접수증 검증을 분기로 더했다. RELEASE 는 서버가 만든 `release_id`, REPLAN 은 서버가 새로
  정한 `task_id`를 주며 **둘 다 요청 task_id('PROJECT')와 다르다**. 이 분기가 없으면 정상 응답이
  무결성 실패로 닫힌다(아래 실패 기록 참조).

### 검증 증거와 범위

- 최종 서버 `output/usage-holds-*/isolation.json`: **310 수집/실행/PASS, 177.52초**.
  B5 execution_command_store(신규6)·execution_commands_api·execution_resume·healing_task·
  hotl_submissions·input_drafts·revision_requests, B3 execution_guard·hotl_api, 권한표 2개.
- 최종 프런트: **137PASS/0FAIL**(직전 133 + 신규4). `tsc -b` 오류 0, 제품 build PASS 2.01초.
- ⚠️ 실패 기록: 첫 계약 실행에서 **135PASS/2FAIL**. `studioExecutionApi.ts`의 `operations`
  허용 목록에 두 명령을 더하지 않아 정상 접수증이 `invalid()`로 닫혔다. 원인을 찾아 목록을
  넓힌 뒤 137 재통과. 첫 실패를 최종 PASS 로 치환하지 않는다.
- `check-process-installation.mjs`는 아래 절과 같은 사유(CRLF)로 104PASS 뒤 중단한다. 이번
  변경 파일이 아니다.
- 실제 브라우저·현업 수용 NOT_RUN. 실제 릴리스 저장/WBS 재분할의 운영 실행은 하지 않았다 —
  합성 접수증 대역과 서버 저장소 계약까지만 검증했다.

### B5 출구 판정 갱신

아래 절의 표에서 **오류 복구** 칸에 「구 release/replan 원키 없는 UNKNOWN」이 포함돼 있었다.
이번에 닫혔다. 남은 미완료는 **명확화 초안 소비(설계 필요)·세부 접근성·실제 브라우저** 셋이다.

---

## 마감: 일반 HOTL 제출 기록·초안 소비 — 2026-09-14 KST

Claude Code / 권고4·7·10 / G2→G3. 전체21/40=52.5%, 로컬18/28≈64.3% **유지**. 이번 묶음
구현·집중검증 완료이며 B5전체/B6/B7 완료는 아니다. 원 지시는 23:03 Codex 인계 §8.1이고
그 문서의 담당·형식을 따랐다. 진척 칸에 이번 인계·시험을 더하지 않는다.

### 구현 계약

- POST `/api/v1/factory/{pid}/hotl/resume`에 `client_request_id` UUID와
  `input_draft:{draft_id,revision,digest}`를 **선택**으로 더했다. 둘 다 없으면 기존 재개와
  완전히 같고 기록도 남기지 않는다. **한쪽만 오면 422**다 — 조용히 무시하면 화면은 닫힌 줄
  알고 서버는 열어 둔 채로 갈린다. 기존 `task_id·feedback·expected_request_id·
  expected_questions_digest`는 그대로이며 구 호출을 깨뜨리지 않는다.
- GET `/api/v1/factory/{pid}/hotl/submissions/{client_request_id}`는 현재 사용자·문맥의
  고정 제출 기록을 조회한다. 응답 유실 뒤 재전송 대신 이 경로만 쓴다.
- `core/studio_hotl_submissions.py`는 주입된 AdvisorStore의 전용 표
  `studio_hotl_submissions`다. PROCESSING 선기록→실제 재개→ACCEPTED/REJECTED/UNKNOWN 종결
  CAS, command/receipt/record 3중 지문 검증, 동일 key/동일 body 멱등, 다른 body 409.
  **같은 사용자·문맥의 같은 저장 초안 판은 요청 키를 바꿔도 재제출 409**다. 타인의 본문·판본은
  이 판정으로 노출하지 않는다. 지문 규칙은 `studio_input_drafts`의 것을 그대로 쓴다 — 두 벌을
  두면 같은 본문이 서로 다른 지문을 갖는다.
- 접수 전 서버가 방금 읽은 차수와 화면이 보낸 `expected_request_id·expected_questions_digest`가
  다르면 접수 자체를 409로 거절한다. 옛 질문의 답변이 새 차수에 붙지 않는다.
- 종결 판정은 실행 명령과 같은 규칙이다. ProcessError 4xx는 쓰기 전 거절이므로 REJECTED,
  5xx와 예상 못한 예외는 UNKNOWN, `success=False`는 REJECTED다. **기록 종결 실패가 실제 재개
  결과를 덮어쓰지 않는다** — 그 경우 PROCESSING으로 남고 원키 조회가 사실을 보여 준다.
- `studio_input_draft_control`의 `consume_supported`에 GENERAL_HOTL을 더했다. 소비는
  `verify_consumption`이 접수 확정(ACCEPTED)·소유자·문맥·원target·본문(`content.text.strip()`)·
  저장 판본을 모두 대조한 뒤의 명시적 CAS다. **PROCESSING/UNKNOWN으로는 닫지 않는다**(503).
- 프런트 `studioDecisionApi.resume`은 결속 제출이면 응답의 `submission`을 요청 본문과 대조하고,
  없으면 malformed로 닫는다. `readSubmission`은 원키 GET 전용이다. `studioDecisionFlow.resume`은
  세 번째 인자로 초안 참조를 받고 접수 확인된 제출만 `eventId`에 남긴다. `recheckSubmission`은
  재전송 없이 상태만 다시 읽는다. `StudioDecisionPanel`은 저장 초안과 현재 입력의 본문이 같을
  때만 결속하고, 처리 기록에서 GENERAL_HOTL 초안을 소비 대상으로 렌더한다.

### 검증 증거와 범위

- 최종 서버 `output/usage-holds-r069shfs/isolation.json`: **229 수집/실행/PASS, 161.20초**,
  wrapper 168.363초/0. B5 hotl_submissions(신규10)·input_drafts·revision_requests·
  execution_commands_api, B3 hotl_api·hotl_context·hotl_resume·execution_guard, 권한표 2개.
  `protected_assets_unchanged`·`sources_unchanged` 모두 true, 차단된 쓰기 0.
  실제 FastAPI/저장소/격리 SQLite 대역이며 실제 LLM·Host·운영 데이터 실행이 아니다.
- 최종 프런트 `output/studio-contracts-d3318220-3411-493d-ac86-1b3afff66f6c/report.json`:
  **127PASS/0FAIL**. 기존 127을 유지했다(신규 계약 시험은 더하지 않았다 — 아래 잔여 참조).
  `tsc -b` 오류 0, 제품 build PASS 1.99초.
- ⚠️ `node scripts/check-process-installation.mjs`는 **104PASS 뒤 중단**한다. 원인은 이
  워크트리의 CRLF 체크아웃이며 스크립트가 `src/components/*.tsx` 원문을 LF 전제 정규식으로
  대조하기 때문이다. 대상은 `KitOperationsPanel`·`ProcessInstallationPanel`로 **이번 변경
  파일이 아니다**. 이번 작업이 만든 실패로 세지 않으며 고치지도 않았다.
- 기준선: 착수 전 같은 러너로 157PASS를 먼저 확인했다. 첫 통과를 최종 결과로 치환하지 않았다.
- 실제 브라우저 클릭·포커스·현업 수용 **NOT_RUN**. 실제 LLM/Host 운영 실행, 운영 회사 실승인,
  분산 원자성 미실행. 단일 서버 프로세스의 SQLite 종결 CAS까지만 보장한다.
- `main.py`/`frontend/src/App.tsx` diff 0. 운영 DB·RAW·실역할·실승인·기존 dirty 보존.

### B5 출구 판정

설계 §7 B5 출구는 「결정 종류·개별 실행/일반/쿼터 재개·저장·오류/접근성·정적/브라우저 분리」다.

| 출구 | 상태 | 근거 / 남은 것 |
|---|---|---|
| 결정 종류 분리 | 완료 | 일반HOTL·Host·능력·데이터셋·키트가 각각의 대상/증거를 쓴다 |
| 개별 실행·일반·쿼터 재개 | 완료 | 23:03 실행 명령 묶음 |
| 저장 — 수정 요청 초안 소비 | 완료 | 22:04 |
| 저장 — 결정 사건 초안 소비 | 완료 | Host/능력/데이터셋, 원장 사건 대조 |
| 저장 — **일반HOTL 초안 소비** | **완료** | 이번 묶음 |
| 저장 — **명확화 초안 소비** | **미완료(설계 필요)** | 아래 별항 |
| 오류 복구 | 완료 | HEAL·원키 GET·UNKNOWN 보존 |
| 접근성 | 미완료 | 세부 접근성 별도 |
| 정적/브라우저 분리 | 부분 | 정적·SSR 유지, 실제 브라우저 NOT_RUN |

**B5 전체는 닫히지 않는다.** 명확화 소비·세부 접근성·실제 브라우저가 남는다.

### 명확화(CLARIFICATION) 초안 소비를 이번에 하지 않은 이유

화면이 `frontend/src/factory/clarifyAnswers.ts`의 `serializeClarifyAnswers`로 질문 번호·
선택 label·설명·「선택 없음」 문구·추가 의견을 **하나의 문자열로 엮어** 제출한다. 저장 초안은
`selections`와 `text`를 구조로 보관한다. 서버가 「이 초안이 이 제출을 만들었다」를 확인하려면
같은 조합 규칙을 서버에도 두어야 하는데, 그러면 **사람이 읽는 표시 문구가 화면과 서버 두 곳**이
되고 한쪽만 고쳐지는 날 조용히 어긋난다. 클라이언트가 보낸 초안 참조를 그대로 믿는 길은
`studio_input_drafts.verify_decision_submission`의 「HTTP submitted=true는 증거가 아니다」와
정면으로 어긋난다.

두 길 중 하나를 **설계로 먼저 정해야 한다**. ① 조합을 서버로 옮기고 화면은 미리보기만 한다
(제출 DTO에 `selections`를 받고 서버가 본문을 만든다 — 화면 제출 경로 변경 포함). ② 명확화는
소비 대상에서 제외한다고 못 박고 화면이 그 사실을 표시한다. 사용자 확인 결과 이번 범위는
일반 HOTL로 한정했다. 임의로 정하면 나중에 되돌리는 비용이 크다.

### 다음·보호

- 다음은 **B5 잔여(명확화 소비 설계 결정·세부 접근성)** 와 **B6 유형별 단일 진입·URL/SSE**다.
  B6 전역 파일은 이번에 수정하지 않았고, AGENTS가 요구하는 병렬개발 통합계획 원본을 확보하기
  전에는 착수하지 않는다(지정 두 경로에서 여전히 미확인).
- 신규 계약 시험을 프런트에 더하지 않았다. 127은 기존 수치 그대로이며 이번 화면 변경은 `tsc`·
  build·기존 127 회귀로만 덮었다. 결속 경로의 프런트 전용 계약 시험은 잔여다.
- 미커밋·미푸시. 작업 트리는 `.claude/worktrees/l2-studio`(브랜치 `codex/l2-unified-studio-20260912`)이고
  원본 트리 `C:/AI Workspace/Ai_Agent_factory_porto-dev`는 `integration/g2-vertical-loop-20260821`
  그대로 두었다 — 두 세션이 같은 저장소를 공유하므로 서로의 체크아웃을 바꾸지 않았다.
- 이 워크트리의 venv는 Python 3.12.10이며 `torch`·`transformers`를 **제외**하고 설치했다.
  경로 길이(Windows 260자) 때문에 torch 내부 중첩 경로에서 설치가 중단됐고, 두 패키지를 직접
  임포트하는 소스는 없다. 임베딩 계열을 쓰는 작업은 별도 준비가 필요하다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
