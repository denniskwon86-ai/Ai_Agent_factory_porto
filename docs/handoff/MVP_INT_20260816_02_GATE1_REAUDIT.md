# MVP-INT-20260816-02 Gate 1 재감사 결과

- 기록자: Codex
- 기록일: 2026-08-16
- 목적: I-4 3단계 이후 테스트 하니스 보정과 G2 U1·U2 병렬 통합의 재현 가능성 판정
- 원격 저장소 작업: 없음 (`origin` 미사용)

## 1. 입력 기준선

| 구분 | 커밋 |
|---|---|
| I-4 3단계 | `6823f876a` |
| 하니스 격리·합성 조직 | `240672043` |
| 테스트 전제 명시 | `5f5ff54a3` |
| G2 U1 관계 런타임 통합본 | `6e78f79bf` |
| G2 U2 승인 모델·REST 통합본 | `27e188dc3` |
| Codex 하니스 최종 보정 | `fa2830ff8` |

검증 브랜치: `codex/integration-gate1-audit`

## 2. 재감사에서 추가로 닫은 결함

### 2.1 격리 실패가 경고 후 계속 진행됨

`tests/conftest.py`의 런타임 격리 단계가 실패하면 `print` 또는 `pass` 후 테스트를 계속했다.
이 상태에서는 테스트가 운영 DB·실제 프로젝트·템플릿으로 후퇴하면서도 초록이 될 수 있다.

조치:

- 모든 런타임 격리 예외를 `pytest.fail(...)`로 전환
- 품질 로그, LLM 로그, 감사, 승격, Shadow Run, 생명주기, 자산 관측, ECM, 범위 정책,
  기준정보·조직, 경영계획, App Data, 작업 디렉터리, 정책 Shadow를 모두 fail-closed 처리
- 새 격리 항목이 추가돼도 `pass`·`print`로 회귀하지 못하게 AST 계약 테스트 추가

### 2.2 품질 텔레메트리 API 테스트가 조직 0건에 암묵적으로 의존

`test_quality_outcomes.py` API fixture를 `seeded_org` 문맥으로 전환하고, 인증 사용자를
`test.invalid` 합성 계정으로 교체했다. 일반 권한 시험에서 부트스트랩 무제한 상태를 제거했다.

## 3. 독립 검증 결과

새 clean worktree에서 I-4·하니스 보정·G2 U1·U2를 결합했다.

| 검증 | 결과 |
|---|---|
| Cherry-pick 충돌 | 0건 |
| 집중 회귀 | 680/680 통과 |
| 보정 후 전체 수집 | 3,513건 |
| 보정 후 전체 실행 | **3,512 passed / 1 skipped / 0 failed** |
| 테스트 후 tracked/untracked 오염 | 0건 |
| 관련 ignored 런타임 산출물 | 0건 |
| `git diff --check` | 통과 |

운영 데이터 지문도 실행 전 보고값과 일치했다.

| 파일 | SHA-256 앞 16자리 |
|---|---|
| `data/master/master.db` | `8c10257250e00c00` |
| `data/enterprise_context.db` | `ee021fc8e9b410dd` |
| `data/scope_policy.json` | `c27f8ffbb2dfbce0` |
| `data/planning.db` | `15247253eb61d5be` |

## 4. 판정

| 단계 | 판정 | 의미 |
|---|---|---|
| 테스트 하니스 P0 | **PASS** | 코드와 추적 자산만으로 재현 가능, 격리 실패는 즉시 중단 |
| Gate 1 — G2 U1 집중 회귀 | **PASS** | 관계 런타임 원자 단위 통합 가능 |
| U2 집중 회귀 | **PASS** | 모델·REST 자체 회귀 통과 |
| Gate 2 — 계약 정합 | **HOLD** | ResourceScope·승인·지문·오류 계약 교차검토 필요 |
| I-4 4단계 | **재개 가능** | 단, `fa2830ff8`을 dev에 먼저 선별 적용 |
| G2 U3·U4 | **HOLD** | Gate 2 통과 전 Resolver·어댑터 구현 금지 |

## 5. 클로드 코드 실행 지시

`dev`에는 G2 통합 브랜치를 합치지 말고 하니스 보정 하나만 선별 적용한다.

```bash
git cherry-pick fa2830ff8
```

그 뒤 I-4 4단계를 진행할 수 있다. `origin` push 여부는 사용자 지시를 별도로 따른다.

## 6. 다음 잔여 작업

```text
하니스 보정 dev 반영      █████████░  cherry-pick 대기
Gate 1                    ██████████  PASS
Gate 2 계약 정합          ░░░░░░░░░░  다음
G2 U3·U4                  ░░░░░░░░░░  HOLD
I-4 4단계                 ░░░░░░░░░░  하니스 반영 후 재개
Gate 3 보안·오류 계약     ░░░░░░░░░░  대기
Gate 4~6 카나리·UI·시연   ░░░░░░░░░░  대기
```
