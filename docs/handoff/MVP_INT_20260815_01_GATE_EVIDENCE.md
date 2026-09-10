# MVP-INT-20260815-01 통합 Gate 증적

> 작성자: Codex
> 작성 시각: 2026-08-15 KST
> 기록 이유: Claude Code I-4 3단계 완료 신호 후 G2 병렬 커밋을 통합 전용 worktree에 적용하고, 깨끗한 checkout에서 재현 가능한지 검증한 결과를 팀에 인계한다.
> 판정: **HOLD — G2 집중 회귀는 통과했으나 전체 테스트가 Git에 없는 운영 시드와 실제 작업 디렉터리에 의존한다.**

## 1. 기준선과 적용 커밋

```yaml
integration_id: MVP-INT-20260815-01
base_commit: 6823f876a
base_description: I-4 3단계 계약 원문·물질화 지문 봉인
integration_branch: codex/integration-three-week-mvp
integration_worktree: C:\WorkSpace\gemini_agent_team_verG\workspace\integration-three-week-mvp
applied_commits:
  - 330026960  # 37ca74c0c cherry-pick, G2 관계 거버넌스 런타임
  - dd923fcf8  # 110e9bb4d cherry-pick, G2 모델 계약·REST 팩토리
origin_touched: false
main_dev_modified_by_integration: false
```

## 2. Gate 결과

| Gate | 결과 | 증적 |
|---|---|---|
| Gate 0 깨끗한 기준선 | 조건부 PASS | clean worktree 생성, `import main`, I-4 집중 회귀, `tsc -b + vite build` 통과 |
| Gate 1 U1 집중 회귀 | PASS | G2 runtime + G1-B/I-4 계약 테스트 통과 |
| Gate 1 U2 집중 회귀 | PASS | G2 model/REST + G1-B/I-4 계약 테스트 통과 |
| Gate 1 전체 pytest | **FAIL/HOLD** | 291 failures. 아래 기준선 대조상 G2가 아니라 비밀 환경 의존성 |
| Gate 2 계약 정합 | NOT_RUN | 전체 Gate 해결 전 진행 금지 |
| Gate 3 보안·오류 계약 | NOT_RUN | Resolver 미구현 |
| Gate 4 실서버 카나리 | NOT_RUN | 제품 mount 전 |
| Gate 5 브라우저 E2E | NOT_RUN | 제품 UI 연결 전 |
| Gate 6 수직 폐루프 | NOT_RUN | G4·시연 UI 전 |

## 3. 통과한 항목

### 3.1 I-4 3단계 깨끗한 checkout

- `6823f876a`에서 별도 worktree 생성
- venv Python 3.14.3으로 `import main` 성공
- I-4 3단계 관련 집중 회귀 전부 통과
- 프론트 `npm run build` 통과
- U1·U2 적용 전 작업트리 clean

### 3.2 G2 U1

- 충돌 없이 신규 2개 파일 적용
- `core/ontology_runtime.py`
- `tests/test_ontology_runtime.py`
- G2·PDP·I-4 집중 회귀 전부 통과

### 3.3 G2 U2

- 충돌 없이 모델 계약·REST 팩토리 적용
- `api/routes/ontology_control.py`
- `tests/test_ontology_control.py`
- 모델 설치·지문·승인·숨김·503 계약과 I-4 공유 계약 집중 회귀 전부 통과
- `main.py` mount는 하지 않음

## 4. 전체 테스트 실패

전체 pytest 결과:

```text
FAILED_COUNT=291

181  tests/test_track_g_route_sealing.py
 41  tests/test_agent_governance_api.py
 33  tests/test_planning_control_gate.py
  8  tests/test_agent_registry_permissions.py
  7  tests/test_scope_write_canonical.py
  5  tests/test_scope_boundary_normalization.py
  4  tests/test_route_authority_table.py
  3  tests/test_agent_asset_runtime_switch.py
  3  tests/test_project_deletion_policy.py
  2  tests/test_enforcement_switch.py
  2  tests/test_p4_recommendations.py
  1  tests/test_org_trust_header.py
  1  tests/test_sse_ticket.py
```

대표 증상:

- 익명 요청이 401이 아니라 200
- 일반 사용자·viewer가 관리자 capability를 가짐
- 조직 밖 자산이 404가 아니라 200
- 숨김 envelope가 사라짐
- 범위 제한 목록이 전사 목록처럼 동작

## 5. G2 회귀가 아님을 확인한 대조

G2 미적용 `6823f876a` 전용 worktree에서도 `tests/test_agent_governance_api.py`가 동일한 형태로 실패했다.

반면 메인 작업폴더에서 같은 커밋·같은 테스트 파일은 통과했다.

| 환경 | scope policy | 사용자 | 부서 | agent governance | track G sealing |
|---|---:|---:|---:|---|---|
| 메인 작업폴더 | `True` | 22 | 12 | PASS | PASS |
| 깨끗한 checkout | `None` | 0 | 0 | FAIL | FAIL |
| 통합 worktree에 메인 DB 사본 3개 복제 | `True` | 22 | 12 | PASS | 1건 제외 PASS |

복제한 것은 다음 세 파일의 **사본**이며 원본은 수정하지 않았다.

- `data/master/master.db`
- `data/enterprise_context.db`
- `data/scope_policy.json`

결론:

> “3,488 passed”는 코드만으로 재현되는 증거가 아니라 Git에 없는 메인 데이터 상태를 포함한 결과다.

## 6. 테스트 하니스 결함

### P0-A — 사용자·부서 fixture가 운영 Master DB에 의존

`test_agent_governance_api.py`는 `hikwon_2/4/7/17`의 역할을 전제로 하지만 테스트 자체가 사용자를 만들지 않는다. 깨끗한 checkout에서는 사용자 0·부서 0이므로 권한 판정이 전부 달라진다.

필요 조치:

1. 테스트 전용 사용자·부서·capability를 명시적으로 시드한다.
2. 운영 `master.db`에서 복사하지 않는다.
3. 사용자별 기대 권한을 fixture 데이터와 함께 한 파일에서 선언한다.

### P0-B — 권한 강제 상태가 운영 scope_policy에 의존

메인에는 `org_enforce=true`가 있으나 깨끗한 checkout에는 정책 파일이 없다. 테스트 격리 fixture가 빈 정책 파일을 쓰는 경우 코드 기본값 `False`로 떨어져 익명도 unrestricted가 된다.

필요 조치:

1. 권한 경계 테스트는 `org_enforce=true`를 fixture에서 명시한다.
2. 비강제 모드 테스트만 별도 대조군으로 `False`를 사용한다.
3. 테스트 순서나 앞선 테스트의 누수로 강제가 켜지는 상태를 금지한다.

### P0-C — 테스트가 실제 worktree를 오염

전체 테스트와 Track G 탐침 후 다음 변경이 남았다.

```text
M  templates/output_formats.json          # 최종 newline 변경
?? agents_registry.prev.json
?? skills/_proposals/
?? templates/viewer_try.json
ignored projects/__track_g_probe__/
```

`test_probe_does_not_leak_into_real_projects_dir`는 실제로 위 탐침 디렉터리를 검출해 실패했다.

필요 조치:

1. `projects`·`library`·`skills/_proposals`·template·registry 백업 경로를 전부 `tmp_path`로 격리한다.
2. 테스트 종료 후 지우는 방식보다 생산 경로 자체를 tmp로 주입한다.
3. 테스트 완료 후 `git status --short`가 비면 통과하는 회귀를 둔다.

## 7. 통합 판정

### 유지

- 통합 브랜치의 U1·U2 커밋은 유지한다.
- G2 집중 회귀 결과는 유효하다.
- 메인 `dev`에는 merge·fast-forward하지 않는다.
- `main.py`·전역 UI는 연결하지 않는다.

### 보류

- Claude Code I-4 4단계를 메인 `dev`에서 바로 시작
- U3 G2↔G1-B 어댑터
- U4 Object Scope·Approval Resolver
- 제품 router mount
- 통합 브랜치의 `dev` 승격

4단계 병렬 진행이 꼭 필요하면 `6823f876a`에서 별도 worktree·별도 브랜치를 만들고 공통 진입 파일을 수정하지 않는다.

## 8. Claude Code 조치 요청

1. P0-A 테스트용 조직·사용자 fixture 작성
2. P0-B 권한 강제 fixture 명시
3. P0-C 실제 작업 디렉터리 쓰기 전부 tmp 격리
4. 깨끗한 worktree에서 대표 실패 파일 3개 우선 통과
   - `tests/test_agent_governance_api.py`
   - `tests/test_track_g_route_sealing.py`
   - `tests/test_planning_control_gate.py`
5. 깨끗한 worktree 전체 pytest 통과
6. 테스트 후 Git clean 확인
7. 보정 커밋과 실행 명령을 본 증적에 인계

## 9. 재개 조건

다음을 모두 충족하면 Gate 1을 다시 실행한다.

```text
[ ] Git에 없는 운영 DB 없이 테스트 가능
[ ] 권한 강제 상태를 fixture가 명시
[ ] 테스트 사용자·부서·역할을 fixture가 생성
[ ] 대표 3개 실패 파일 PASS
[ ] 전체 pytest PASS
[ ] 테스트 후 worktree clean
[ ] 원본 운영 DB 지문 불변
```

## 10. 진척

```text
I-4 3단계 기준선      ██████████  완료·재현
G2 U1 적용            ██████████  완료·집중 회귀 PASS
G2 U2 적용            ██████████  완료·집중 회귀 PASS
전체 회귀             ██░░░░░░░░  기준선 환경 의존 291 FAIL
테스트 하니스 보정    ░░░░░░░░░░  Claude Code 조치 필요
계약·Resolver 통합    ░░░░░░░░░░  HOLD
제품 API·UI 연결      ░░░░░░░░░░  HOLD
첫 수직 E2E           ░░░░░░░░░░  HOLD
Gate 통과             ███░░░░░░░  Gate 0·U1·U2 집중 회귀만
```

## 11. 잔여사항

| 우선순위 | 잔여사항 | 담당 | 착수 조건 |
|---|---|---|---|
| P0 | 조직·사용자 테스트 fixture | Claude Code | 즉시 |
| P0 | 권한 강제 fixture | Claude Code | 즉시 |
| P0 | 프로젝트·템플릿·레지스트리 테스트 쓰기 격리 | Claude Code | 즉시 |
| P0 | clean checkout 전체 회귀 | Claude Code + Codex 재검증 | 위 3개 완료 |
| P1 | 테스트 환경 계약 문서화 | Claude Code | 전체 회귀 통과 후 |
| P1 | U3~U4 계약 통합 | Claude Code·Codex | Gate 1 PASS |
| P1 | 카나리·UI·수직 E2E | Codex·Antigravity | Gate 2~4 PASS |
