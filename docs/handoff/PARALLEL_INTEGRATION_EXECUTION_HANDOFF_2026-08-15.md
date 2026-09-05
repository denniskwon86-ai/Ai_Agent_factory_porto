# 병렬개발 통합 실행 인계

> 작성자: Codex
> 지시자: Supervisor
> 작성일: 2026-08-15
> 필수 수신자: Claude Code, Codex, Gemini Antigravity 및 이후 통합 담당자
> 작성 이유: 병렬 구현을 안전하게 하나로 합치는 절차가 구두 합의에 머물지 않도록, 착수 조건·실행 순서·증적·금지사항을 작업 인계로 고정한다.

## 0. 최신 실행 판정 — MVP-INT-20260815-01

최신 통합 증적:

`docs/handoff/MVP_INT_20260815_01_GATE_EVIDENCE.md`

현재 판정은 **HOLD**다.

- I-4 3단계 `6823f876a` 기준선 재현 완료
- G2 U1·U2 선별 적용과 집중 회귀 완료
- 깨끗한 checkout 전체 테스트 291건 실패
- 같은 코드가 메인 작업폴더에서는 통과하고 clean checkout에서는 실패함
- 원인: Git에 없는 운영 Master·ECM·scope policy 시드 의존 및 테스트의 실제 worktree 쓰기

Claude Code는 4단계보다 먼저 증적 §8의 P0-A~C 테스트 하니스 보정을 수행한다. 보정 전에는
U3 이후 통합, `main.py` mount, `dev` 승격을 진행하지 않는다.

## 1. 필독 정본

병렬 통합 작업 전 다음 문서를 전문으로 읽는다.

`C:\WorkSpace\gemini_agent_team_verG\workspace\codex-three-week-mvp\docs\roadmap\PARALLEL_DEVELOPMENT_INTEGRATION_EXECUTION_PLAN_2026-08-15.md`

통합 후 프로젝트 내부 정본 위치:

`docs/roadmap/PARALLEL_DEVELOPMENT_INTEGRATION_EXECUTION_PLAN_2026-08-15.md`

요약만 읽고 작업하지 않는다. 특히 다음 절은 생략할 수 없다.

- §3 실측 기준선
- §4 U0~U8 통합 단위와 강제 순서
- §5 통합 전용 worktree
- §6 충돌 등급 C0~C5
- §7 Gate 0~6
- §8 중단 조건
- §9 롤백
- §12 통합 증적 양식
- §15 즉시 다음 행동

## 2. Claude Code에게 인계하는 즉시 행동

현재 Claude Code의 우선 작업은 I-4 3단계를 완결된 기준선으로 만드는 것이다.

### 2.1 I-4 3단계 완료 조건

1. 계약 원문 지문과 물질화 지문을 각각 증명에 봉인한다.
2. 어느 하나라도 바뀌면 기존 증명이 차단되고 프레임 폐기 계약이 유지되는지 확인한다.
3. 관련 생산자→소비자 배선을 실제 라우트까지 시험한다.
4. 변이 검사·집중 회귀·전체 회귀·프론트 타입 검사를 기록한다.
5. 본인 변경만 원자 커밋한다.
6. `git status --short`가 깨끗한지 확인한다.
7. 다음 항목을 인수인계에 남긴다.
   - 완료 커밋 ID
   - 변경 파일
   - 테스트 결과
   - 설계 대비 변경
   - 남은 위험
   - 통합 착수 가능 여부

### 2.2 Claude Code가 지금 하지 않을 것

- Codex 병렬 브랜치 전체 merge
- `9aebe87ee` 또는 `d59dd679f` 같은 동기화 merge commit cherry-pick
- `main.py`, 전역 API, `frontend/src/App.tsx`의 선행 연결
- G2 구현을 같은 이름의 새 모듈로 다시 작성
- 운영 DB를 사용한 마이그레이션·카나리
- 사용자 별도 지시 없는 origin 작업

## 3. 통합 담당자의 실행 순서

Claude Code의 완료 인계와 깨끗한 `dev`가 확보된 뒤에만 다음을 수행한다.

```text
U0  Claude I-4 3단계 기준선 확정
 └─ Gate 0
     └─ U1 37ca74c0c 적용
         └─ 집중 회귀
             └─ U2 110e9bb4d 적용
                 └─ 집중 회귀
                     └─ U3 G2↔G1-B 계약 어댑터
                         └─ U4 Object Scope·Approval Resolver
                             └─ Gate 2·3
                                 └─ U5 main.py API mount
                                     └─ Gate 4 실서버 카나리
                                         └─ U6 UI·내비게이션
                                             └─ Gate 5 브라우저 E2E
                                                 └─ U7 첫 수직 폐루프
                                                     └─ Gate 6 시연 승인
```

### 3.1 적용 대상

| 순서 | 커밋 | 내용 |
|---:|---|---|
| 1 | `37ca74c0c` | G2 관계 거버넌스 런타임 |
| 2 | `110e9bb4d` | G2 승인 모델 계약·REST 팩토리 |
| 3 | `a22388741` | 코드 Gate 통과 후 병렬 트랙 인수인계 |
| 4 | `6c9f685ed` | 본 통합 수행계획서 |

브랜치 전체를 merge하지 않는다. 위 기능 커밋을 순서대로 선별 적용한다.

### 3.2 공통 진입점

다음 파일은 병렬 작업자가 각자 수정하지 않고 통합 담당자 한 명이 마지막에 연결한다.

- `main.py`
- 전역 API router 등록부
- `frontend/src/App.tsx`
- 전역 내비게이션·라우트

Object Scope Resolver와 Decision Ledger Approval Resolver 없이 G2 router를 mount하지 않는다. 미구현 상태를 선택적 import로 숨기지 않는다.

## 4. 계약 통합 체크리스트

| 계약 | 확인할 내용 |
|---|---|
| ResourceScope | tenant·entity mode·scope·프로그램 상태를 G1-B 정본 판정기로 해석하는가 |
| 계약 지문 | semantic fingerprint와 materialization fingerprint를 구분해 봉인하는가 |
| Object Scope | ECM·MDM·Snapshot namespace마다 번역만 하고 자체 판정을 만들지 않는가 |
| 승인 원장 | 문자열 correlation ID가 아니라 Decision Ledger 사건을 검증하는가 |
| 데이터 역할 | DEMO_ONLY·SYNTHETIC·REFERENCE·CERTIFIED가 Actual에 섞이지 않는가 |
| 오류 의미 | 볼 수 없음 404, 문맥 미선택 409, 판정 불가 503이 유지되는가 |
| 누설 방지 | 권한 밖 객체·관계의 존재·건수·차단 사유를 응답에서 숨기는가 |

## 5. 중단 조건

다음 중 하나라도 참이면 다음 단계로 넘어가지 않는다.

1. `dev` 또는 통합 worktree가 dirty
2. I-4 3단계 커밋·테스트 증적 없음
3. 깨끗한 checkout에서 `import main` 또는 프론트 build 실패
4. 계약·물질화·모델 지문 중 하나가 미봉인
5. Resolver 누락·장애가 빈 목록이나 0건으로 표시됨
6. 권한 불일치를 테스트 기대값 완화로 통과시킴
7. 운영 DB가 카나리 대상이 됨
8. API mount와 UI 호출이 없는 상태를 통합 완료로 보고함

## 6. 검증 책임

| 담당 | 책임 |
|---|---|
| Claude Code | I-4 기준선, 백엔드 계약, API·DB·테스트, 충돌 구현 판정 |
| Codex | G2 코드 설명, 제품 영향·UI/UX, 공통 진입점·시연 화면 검토 |
| Antigravity | DB 사본·데이터 오염·Scope 누설·E2E·텔레메트리 독립 감사 |
| Supervisor | DEMO/CERTIFIED 경계, 시연 범위, 최종 승격 승인 |

자가검토와 수정은 허용한다. C2~C5 위험 항목의 교차검토는 구현 착수를 막는 대기가 아니라 다음 Gate 승격 조건이다.

## 7. 완료 보고 양식

모든 통합 완료 보고에는 다음을 포함한다.

```text
[통합 회차] MVP-INT-YYYYMMDD-NN
작성자 / 작성 시각 / 작업 이유
기준 커밋 / 적용 커밋 / 제외 커밋
충돌 파일과 계약 / 해결자 / 판정 근거
Gate 0~6: PASS·FAIL·NOT_RUN
집중 테스트 / 전체 테스트 / 프론트 / 브라우저
운영 DB 접근 여부
잔여사항 / 담당 / 착수 조건
dev 승격 판정: HOLD·APPROVED
```

진척은 반드시 시각화한다.

```text
기준선 정리           ░░░░░░░░░░  0/1
G2 원자 커밋 적용     ░░░░░░░░░░  0/2
계약·Resolver 통합    ░░░░░░░░░░  0/2
제품 API·UI 연결      ░░░░░░░░░░  0/2
첫 수직 E2E           ░░░░░░░░░░  0/1
Gate 통과             ░░░░░░░░░░  0/7
```

## 8. Claude Code 확인 기록 양식

Claude Code는 이 인계서를 읽은 뒤 다음 내용을 자기 인수인계 또는 작업 보고에 남긴다.

```yaml
reader: Claude Code
read_at: YYYY-MM-DD HH:MM KST
read_full_plan: true
current_task: I-4 stage 3
current_base_commit: commit-id
owned_dirty_files:
  - file
integration_ready: false
ready_when:
  - 원자 커밋 완료
  - 집중·전체 회귀 완료
  - dev clean
next_action: 통합 담당자에게 Gate 0 착수 신호
```

## 9. 현재 상태

```text
통합계획              ██████████  작성·지시 연결 완료
Claude 기준선         ████████░░  I-4 3단계 진행 중
실제 코드 통합        ░░░░░░░░░░  미착수
제품 연결             ░░░░░░░░░░  미착수
첫 수직 폐루프        ░░░░░░░░░░  미착수
```

현재 통합 판정은 `HOLD`다. Claude Code가 I-4 3단계를 원자 커밋하고 `dev`를 clean으로 만든 뒤 Gate 0부터 착수한다.
