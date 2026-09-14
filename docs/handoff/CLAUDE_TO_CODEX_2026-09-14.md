# Claude Code → Codex 인계 (2026-09-14)

- 대상: 2026-09-14 하루치. 브랜치 `codex/l2-unified-studio-20260912`
- 기준: 당신의 `d0f811826` 위에 커밋 4개. **미푸시**
- 앞 인계: `L2_STUDIO_CROSS_SESSION_HANDOFF_2026-09-13.md` §8.1 이 지정한 다음 구현을 했다
- 상세 계약·검증은 `docs/handoff/L2_STUDIO_B5_GENERAL_HOTL_CONSUMPTION_2026-09-14.md`
  (절 4개, 최신이 위)

## 0. 진척 — 21/40 = 52.5% 유지

**제품 관문을 전진시키지 않았다.** 오늘 한 것은 전부 B5 내부 출구와 검사 복구다.
로컬 18/28 ≈ 64.3% 도 그대로다. 이번 인계·시험을 완료 칸에 더하지 않는다.

**B5 저장 출구는 모두 닫혔다.** B5 전체는 아직이다 — 실제 브라우저·현업 수용이 남는다.

## 1. 커밋 4개

| SHA | 내용 |
|---|---|
| `0ba6674a8` | 일반 HOTL 초안 사용완료 결속 · 구 release/replan 접수 기록 |
| `ba7f9f06b` | `check-process-installation` 회귀 해소 (당신 커밋의 소스·검사 불일치) |
| `4cd1ffc45` | 명확화 초안 소비 — 설계안 갈래 A |
| `aacfe86a6` | 원키 재조회 배선 누락 수정 · 접근성 정적 보강 |

22 + α 파일, 약 1,500줄 추가. `main.py`·`frontend/src/App.tsx` **diff 0**.

## 2. ⚠️ 당신 커밋에서 발견한 회귀 하나

`58713ed1d` 가 `check-process-installation.mjs`(신규 1,696줄)를 추가하면서 **같은 커밋에서**
`KitOperationsPanel.tsx` 의 조회 의존성을 바꿨다.

    -  }, [revision]);
    +  }, [revision, identity]);

검사는 `/\},\s*\[revision\]\)/` **정확 일치**를 요구해 104PASS 뒤 `AssertionError` 로 중단했다.

★ **소스가 옳다.** 문맥 전환 시 목록을 다시 읽어야 하고 같은 effect 가
`identity !== studioIdentityKey()` 로 늦은 응답을 버린다. **검사를 고쳤다** — 같은 파일의
`EnterprisePage` 방식(의존성 배열에 이름이 있는지)으로 맞췄다. 제품 소스는 건드리지 않았다.
지금 **105PASS/exit 0**.

당신 인계 §4 검증 표에 이 명령이 없고 마지막 통과 기록이 B4 17:14 인 것으로 보아, 그 커밋
뒤 다시 돌리지 않은 것으로 보인다. 이견이 있으면 인계 문서의 해당 절을 근거로 되돌릴 수 있다.

## 3. 무엇을 만들었나

### 3.1 일반 HOTL · 명확화 저장 초안 사용완료 결속

`verify_decision_submission` 이 「차수·입력 결속 증거가 없다」로 막고 있던 두 종류를 열었다.

- 신규 `core/studio_hotl_submissions.py` — AdvisorStore 전용 표. PROCESSING 선기록 →
  실제 재개 → ACCEPTED/REJECTED/UNKNOWN 종결 CAS, 3중 지문, 같은 초안 판 재제출 409.
- `POST /{pid}/hotl/resume` 에 `client_request_id`·`input_draft` **선택** 추가. 둘 다 없으면
  기존과 동일, 한쪽만 오면 422. **구 호출 호환 유지.**
- `GET /{pid}/hotl/submissions/{uuid}` — 응답 유실 뒤 재전송 대신 원키 확인.
- 명확화는 **접수 시점**에 서버가 `core/clarify_answers.py` 로 본문을 재현해 저장 초안과
  대조한다(설계안 갈래 A, 사용자 결정). 차수가 지나가면 질문을 다시 읽을 수 없어 소비
  시점으로 미룰 수 없다.

### 3.2 구 release·replan 접수 기록

두 경로만 원키 없는 직접 POST 였다. **REPLAN 은 되돌릴 수 없는데**(기존 WBS 삭제) 응답이
유실되면 다시 눌러 또 지웠다. 실행 명령에 `RELEASE`·`REPLAN` 을 더했다. 둘 다 EXECUTIONS 이고
`PROJECT_SCOPED`·고정 `task_id="PROJECT"` 다. 기존 handler 를 그대로 부르므로 서버 동작·경로는
바뀌지 않았다.

## 4. ⚠️ 남는 위험 — 표시 문구가 두 곳이다

갈래 A 의 대가다. 명확화 조합 규칙이 `frontend/src/factory/clarifyAnswers.ts` 와
`core/clarify_answers.py` 양쪽에 있다. 한쪽만 고치면 **정상 제출이 대조 실패로 닫힌다.**

- 착수 전 두 구현의 출력이 **바이트 단위로 같음을 실측**했다(프런트 함수를 실제 실행해
  서버 `GOLDEN_TEXT` 와 대조).
- 같은 고정 예제를 `tests/test_b5_clarify_answers.py` 와 `check-studio-contracts.mjs` 양쪽에
  두어 잠갔다.
- ★ **한계: 예제를 한쪽만 고치면 잡지 못한다.** 형식을 바꿀 때는 양쪽 예제를 함께 고쳐야
  하고, 그 사실을 두 파일 머리말에 적어 두었다. 설계안 §4 에 미리 명시한 한계 그대로다.

## 5. 내가 틀린 것 두 가지 — 그대로 남긴다

### 5.1 검증 없이 원인을 단정했다

`check-process-installation` 실패를 「워크트리 CRLF 체크아웃」이라고 **확인하지 않고 단정**해
인계·PROGRESS·TEAM_BOARD 세 곳과 커밋 메시지에 적었다. 그 정규식은 `\s*` 를 쓰므로 CRLF 와
무관하다 — 한 번 돌려 봤으면 1분 만에 알았다.

★ 당신이 그 기록을 믿었다면 없는 문제를 찾거나 진짜 회귀를 놓쳤을 것이다. 세 문서를 모두
정정했고(`ba7f9f06b`), 「원인을 말하려면 재현·제거로 확인한다」를 규칙으로 남겼다.

### 5.2 배선 누락을 스스로 만들었다

`recheckSubmission` 을 만들고 화면에 붙이지 않았다. 계약 시험은 flow 를 직접 불러 초록인데
**사용자는 쓸 수 없었다.** 응답 유실 시 접수를 확인할 유일한 경로였다. `aacfe86a6` 에서
버튼을 붙이고 STATIC 검사로 잠갔다.

★ 버튼이 쓰는 값은 `eventId` 가 아니라 `body.client_request_id` 다 — `eventId` 는 접수 확인
시에만 채워지는데 이 버튼이 필요한 때는 UNKNOWN 이다. 처음 `eventId` 로 썼다가 바꿨다.

## 6. 검증 — 마지막 실행 기준

| 대상 | 결과 |
|---|---|
| 서버 (strict-writes 러너) | **392 수집/실행/PASS, 178.30초** |
| 프런트 계약 | **139 PASS / 0 FAIL** |
| 설치 계약 | **105 PASS** |
| tsc · 제품 build | 오류 0 · PASS |
| 보호 자산·소스 지문 | `protected_assets_unchanged`·`sources_unchanged` **true** |

착수 전 기준선 157PASS 를 먼저 확인했다. **실패 기록을 보존한다** — 계약 첫 실행
135PASS/2FAIL(`operations` 허용 목록 누락), 서버 중간 2FAIL(기존 시험 두 건이 옛 동작을 기대).
첫 실패를 최종 PASS 로 치환하지 않았다.

**실제 브라우저·현업 수용 NOT_RUN.** 실제 LLM/Host 실행, 운영 데이터 검증도 하지 않았다.

## 7. 기존 시험 3건을 갱신했다 — 보장은 유지

1. `test_b5_hotl_submissions` 「명확화 거절」 → 「명확화 수락 + 계약·능력·데이터셋 거절」.
2. `test_b5_input_drafts.test_api_clarification_submission_claim_cannot_consume` — 종류 미지원
   409 를 기대했으나 지금은 형식 오류 422 와 **기록 없음 404** 를 검사한다. ★ 보장(임의
   주장으로 닫히지 않는다 · DRAFT 유지)은 그대로이며 존재하지 않는 제출 ID 검사를 더해 강해졌다.
3. `check-process-installation` 의 의존성 대조(§2).

## 8. 다음 — 무엇이 막혀 있나

### B6 는 착수할 수 없다

AGENTS 가 요구하는 **병렬개발 통합계획 원본이 없다.** 지정 두 경로·저장소 전체·모든 브랜치
이력을 대조해 확인했다. 있는 것은 `docs/handoff/PARALLEL_INTEGRATION_EXECUTION_HANDOFF_2026-08-15.md`
(214줄) 뿐이고 이것을 계획 정본 대신 쓰지 않았다.

사용자 확인: **원본은 물리적으로 떨어진 디스크에 있어 오늘 전달 불가.** 그 파일이 확보되면
B6 를 열 수 있다. B7 은 설계상 B6 를 선행 조건으로 두므로 함께 막혀 있다.

### B5 잔여

- **실제 브라우저 수용** — 환경 미비로 NOT_RUN.
- 세부 접근성 중 좁은 화면·키보드 이동·포커스 순서는 브라우저가 있어야 판정된다.

### 판정 완료 — 운영 복구는 **B7 계열**이다

당신 인계가 「B5 또는 후속의 어느 출구인지 설계와 대조해 명시한다」고 지시한 항목이다.
처음에 미정으로 넘겼다가 지시를 이행하지 않은 것임을 알고 대조했다.

- B5 검증 항목 **U26** 이 요구하는 것은 「거절/응답 유실 시 상태 초기화·추가 REVISION 자동
  생성이 **없을 것**」 — 즉 **자동으로 손대지 않는 것**이 합격 기준이고 이미 지켜진다.
- 「사람이 확인하고 잔류 기록을 닫는 경로」는 운영 절차·권한 설계가 선행돼야 하고, 설계 B7
  출구(`process upgrade/restore`, 회귀·브라우저·현업 측정)에 속한다.
- ★ 따라서 **B5 출구는 이 항목 때문에 열려 있지 않다.** B5 잔여는 실제 브라우저 수용뿐이다.
  자동 재실행·한도 초기화·서버 내부 UNKNOWN 자동 종결은 구현하지 않은 상태를 유지한다.

### 설계 문서 세 곳의 낡은 「미구현」 표시를 실측 정정했다

| 위치 | 표시 시점 | 실측 |
|---|---|---|
| 실행 설계서 §8.3 API 목록 | 09-12 | **6행 모두 구현** |
| 실행 설계서 B4 연결 계약 보완 | 09-13 09:40 | **5항목 모두 구현** |
| 업무키트 L2 설계서 머리말 | 09-12 | §5·§6·§7 구현, §4 부분 |

각 정정에 근거 파일·경로를 표로 적었다. 방치하면 **이미 있는 것을 다시 만든다.**
「구현됐다 ≠ 그 절의 합격 기준을 모두 만족한다」도 함께 못박았다.

## 9. 환경 — 이 워크트리

두 세션이 같은 저장소를 공유하므로 작업 공간을 나눴다.

| 세션 | 디렉터리 | 브랜치 |
|---|---|---|
| 업무키트/분류 | `C:/AI Workspace/Ai_Agent_factory_porto-dev` | `integration/g2-vertical-loop-20260821` |
| 이 작업(L2) | `.../.claude/worktrees/l2-studio` | `codex/l2-unified-studio-20260912` |

- 원본 트리는 **건드리지 않았다.** 그쪽 분류 작업과 미커밋 변경 그대로다.
- 이 워크트리 venv 는 **Python 3.12.10**(당신 환경은 3.14)이며 **`torch`·`transformers` 제외**
  설치다. 경로 길이(Windows 260자) 때문에 torch 내부 중첩 경로에서 설치가 중단됐고, 두 패키지를
  직접 임포트하는 소스는 없다. 임베딩 계열 작업은 별도 준비가 필요하다.
- `data_sync/session-data-20260913.aesgcm` 은 **열지 못했다.** 키가 이 PC 에 없고
  (`C:/WorkSpace/gemini_agent_team_verG/...` 경로 자체가 없다) 경로도 달라 검사 사본까지만
  가능하다. 오늘 작업은 전부 합성 격리 환경에서 했다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
