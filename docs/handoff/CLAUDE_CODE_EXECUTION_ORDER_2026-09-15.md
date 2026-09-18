# Claude Code 실행 지시 — MEGA-ENTRY-01

작성: Codex · 2026-09-15 22:41 KST.
사용자 결정: 같은 PC·같은 소스에서 Claude Code가 실제 작업, Codex가 지시·진척·완료 검토 담당.
이 문서는 실행 지시서다. 실제 수신/시작은 상태 파일의 ACK/RUNNING으로 구분한다.

## 1. 소유권과 기준선

- 작업 루트: C:/WorkSpace/gemini_agent_team_verG
- 브랜치: codex/l2-unified-studio-20260912
- 기록 당시 HEAD: 2380143ea9552bbfbe1cf59678f54a5fb53666b5
- 같은 폴더의 미커밋 수정이 최신 기준이다. pull/reset/checkout/clean/DB restore로 정리하지 않는다.
- 제품 코드와 검사 수정은 Claude Code 단독. Codex는 구현·전체 검사 반복을 중단한다.
- 기존 수정 파일: api/routes/data_preparation_control.py, tests/test_b6_kit_app_entry.py,
  frontend/src/store/useFactoryStore.ts, frontend/src/App.tsx,
  frontend/scripts/check-release-entry.mjs 및 PROGRESS/TEAM_BOARD/인계 문서.
  이것들은 앞선 승인 작업이다. 바뀌기 전 SHA를 기준으로 회귀시키거나 버리지 않는다.
- data/interaction_log.jsonl은 사용자 기존 변경이다. 수정/커밋 대상에서 제외한다.
- 작업 시작 시 git status를 읽고 인계와 다른 추가 변경이 있으면 소유자/중복 작업을 먼저 확인한다.
  진행 중인 다른 Claude가 있다면 이 지시를 같은 세션에 이어 주며 새 실행자를 중복 생성하지 않는다.

## 2. 읽을 자료와 확정 사항

저장소 .agents/AGENTS.md의 상위 정본/착수 규칙을 준수한다.
현재 권고10/G3, 첫 수직 폐루프의 진입 문맥을 완결하는 사용자 승인 작업이다.
최신 세부 자료는 다음 순서다.

1. docs/handoff/L2_STUDIO_RELEASE_REPAIR_2026-09-15.md
2. docs/handoff/L2_STUDIO_KIT_ENTRY_REPAIR_2026-09-15.md
3. docs/handoff/CODEX_SYNC_REVIEW_2026-09-15.md §6의 mega/draft 권고
4. docs/design_l2_studio_entry_readers_2026-09-15.md 및 관련 실제 소스

R1~R3는 수정 완료다. 같은 결함을 처음부터 재조사하거나 전면 리팩터링하지 않는다.
현재 전체21/40=52.5%, 로컬18/28≈64.3%. 과거 관리평가 기준으로 분모를 바꾸지 않는다.
직접 연결된 대상은 project/new/release/kit_app이며 mega/draft는 미연결이다.

## 3. 이번 실행 범위

목표: mega 직접 진입에서 서버가 부모·선택 하위 프로젝트의 관계 및 조회 가능성을 확인하고,
확인된 대상만 기존 Studio에 연결한다. 이번에는 mega에 집중하며 draft/UI 전면개편으로 확장하지 않는다.

1. 기존 project entry metadata/PDP/메가 소속의 권위 저장소와 실제 호출자를 확인한다.
2. 부모 단독과 부모+선택 자식의 요청/응답·오류 계약을 짧게 적고, 기존 정책을 재사용한다.
   기존 metadata 호환 확장 또는 작은 전용 조회를 비교하되 대형 공통화는 선행하지 않는다.
3. 서버가 부모의 실제 메가 여부, 부모와 자식 관계, 각 대상의 현재 조회 가능성을 판정한다.
   프런트가 ID 형태나 별도 두 응답으로 관계를 추측하지 않는다.
4. 프런트 reader/Gate/기존 진입점에 연결한다. 확인 전에 프로젝트 선택·실행을 시작하지 않는다.
5. 정상/없는 부모/없는 자식/관계 불일치/다른 조직/권한 부족/문맥 변경/늦은 응답을 검사한다.
   조회만으로 자원 생성·실행·승인이 일어나지 않아야 한다.
6. 검사 결과, 실제 연결된 사용자 흐름, 잔여와 다음 ETA를 상태 파일에 남긴다.

기존 권한을 넓히거나 새 승인 정책을 임의로 정하지 않는다.
소속의 권위 근거가 없거나 제품 선택이 필요한 경우에는 대안을 2개 이하로 정리해 BLOCKED 보고한다.
정상 구현·검사마다 사용자 승인을 다시 요청하지 않는다.

## 4. 검증 효율과 안전

- 먼저 변경 직접 관련 검사를 실행한다. 새 부정 검사→수정→같은 검사로 결과를 확인한다.
- 기존 회귀 전체를 단계마다 반복하지 않는다. 합류 시 변경 영향 범위만 한 번 검증한다.
- 서버는 scripts/verify_data_usage_holds.py --strict-writes --target tests/test_....py로 격리 실행한다.
  운영DB에서 직접 pytest/서버 기동/마이그레이션하지 않는다. 검사 중 소스를 변경하지 않는다.
- 프런트 실제 flow/store 검사와 타입/build를 쓴다. 소스 문자열 검사를 실제 동작 증거로 보고하지 않는다.
- 이전 서버162PASS, 프런트363PASS/build는 이전 실측이다. 실행하지 않은 검사를 새 결과에 합산하지 않는다.
- 서버 권한 변경은 Codex의 핵심 diff 검토 대상으로 표시한다.
- 실제 브라우저를 수행하지 않았다면 NOT_RUN. 실제 로그인/데이터가 없다는 이유로 합성 정상검사를 생략하지 않는다.
- 데이터 ZIP/키/RAW/운영DB/사용자로그를 건드리지 않는다. 원격 Git 작업과 커밋은 별도 지시 전 하지 않는다.

## 5. 보고 방식

보고 파일: docs/handoff/CLAUDE_CODE_EXECUTION_STATUS.md

- 수신 즉시 ACK/RUNNING, 시작 시각, 수정 예정 파일과 완료 기준을 기록한다.
- 20~30분 또는 의미 있는 단계 완료 때 갱신한다. 시간이 긴 경우 무엇이 끝나고 무엇을 하는지 명시한다.
- 보고는 요약300~600자 + 변경 파일·검사 증거 경로 정도로 제한한다. 긴 로그 전문은 output에 둔다.
- 완료 상태는 READY_FOR_REVIEW. 변경 파일/추가 변경 요약/실행 명령/실측 결과/미검증을 반드시 포함한다.
- 구현 완료와 제품 전체 완료를 구분한다. 전체 진척 가산 후보가 있으면 해당 정본 완료 조건과 증거를 제시한다.
- BLOCKED에는 원인, 이미 시도한 것, 필요한 결정만 적는다. 같은 검사를 무한 반복하지 않는다.
- Codex가 읽기 전용으로 핵심 diff와 증거를 보고 보완 지시 또는 다음 작업을 내린다.
  공유 파일은 자동 메시지 채널이 아니므로, 현재 대화에서 수신·완료를 알리는 것도 함께 수행한다.

예상: mega30~50분. 첫20~30분에 중간 산출물 보고. 다음 후보는 draft 진입이며 별도 범위 지시로 넘긴다.
