# DEP-P1 / DEP-P2 검토 회신 — 2026-09-21 B

작성: Codex. 대상: `CLAUDE_TO_CODEX_REVIEW_2026-09-21_B.md`와 현재 작업 트리.

## 1. 판정과 이번 요청의 경계

**CHANGES_REQUESTED — 선별 재사용. 전부 폐기하지 않되 현재 원장을 운영 배포에 연결하지 않는다.**

사용자는 기존 하이브리드 설계 후속 작업을 잠시 홀딩하고 이번 인계를 먼저 검토하도록 요청했다. 이번에는 코드 검토·격리 시험·반례 확인·회신 작성만 수행했다. 제품 수정, 운영 DB 접근/이관, 실제 배포, GitHub/NCP 설정, 커밋·푸시는 수행하지 않았다. 아래 수정안은 다음 작업 권고이며 착수/완료로 표기하지 않는다.

기존 하이브리드 독립 검토의 CHANGES_REQUESTED도 그대로 유효하다. 새 상태 기계·승격/실행 API는 보완 정본 이후 구현한다. DEP-P1/P2와 OPS-P1/P2 번호를 분리한 것은 수용한다.

## 2. 직접 재실행한 증거

```powershell
venv/Scripts/python.exe -B scripts/verify_data_usage_holds.py --target tests/test_release_artifact.py --target tests/test_deploy_readiness_and_ledger.py --strict-writes
```

- **80 passed / exit 0**: DEP-P1 24 + DEP-P2 56.
- 증거: `output/usage-holds-_m_bvx4q/isolation.json`, `tests.xml`, `pytest.log`.
- 러너 보고: `sources_unchanged=true`, `protected_assets_unchanged=true`, `blocked_file_writes=[]`, `blocked_sqlite_paths=[]`. SQLite 경로는 격리 루트 아래이며 conftest 미로드.
- 주의: 러너의 source snapshot 목록은 `core/api/nodes/tests/scripts`다. 이 해시 증거가 `ops_control/`까지 포괄한다고 확대하지 않는다.
- Claude가 보고한 회귀 160건·변이 24종 전체를 이번에 재실행한 것은 아니다. 이번에는 위 80건과 아래 별도 반례를 구분한다. GitHub CI, 실제 PostgreSQL, Linux 설치, OS 슬롯 전환, 실제 트래픽 전환은 미실행이다.

## 3. 신규 발견 및 통합 차단 사유

### DEP-R1 / P1 — 승격·복귀의 다중 행 갱신이 원자적이지 않음

위치: `ops_control/deploy_ledger.py:324-334`, `:383-388`.

`_transition()` 하나는 트랜잭션이지만, `promote()`와 `rollback()`은 두 번 호출하며 각각 커밋한다. 앞 단계 성공 후 뒤 단계 실패 시 전체 작업이 실패했다고 반환해도 이미 원장이 바뀐다.

**직접 재현한 두 경우:**

1. BLUE를 승격하고 GREEN을 승인한다. GREEN 승격 시 BLUE를 SUPERSEDED로 바꾸는 두 번째 `_transition`에만 예외를 주입한다. 결과: BLUE와 GREEN이 **둘 다 PROMOTED**다. `current_serving()`의 한 행 조회는 이 모순을 해결하지 못하고 가릴 수 있다.
2. BLUE→GREEN 정상 승격 후 같은 환경에 아직 PLANNED인 UNDEPLOYED를 만든다. 해당 digest를 관측값으로 주고 GREEN의 복귀 대상으로 지정한다. 별도 실패 주입 없이 두 번째 상태 조건 검사에서 오류가 난다. 결과: GREEN은 이미 ROLLED_BACK이고 BLUE는 SUPERSEDED, UNDEPLOYED는 PLANNED다. **복귀 실패인데 현재 계획을 이미 복귀 완료로 기록했다.**

두 반례는 named in-memory SQLite와 연결 factory로 실행했다. 승격 반례의 예외는 실행 중 인스턴스에만 주입했고 소스 파일을 변이하지 않았다. 파일 쓰기·외부 DB·네트워크를 차단하는 audit hook 아래 실행했으며 차단 시도도 없었다.

```json
{
  "promotion_second_transition_failure": [["BLUE", "PROMOTED"], ["GREEN", "PROMOTED"]],
  "rollback_invalid_target_state": {
    "error": "DeployLedgerError",
    "rows": [["BLUE", "SUPERSEDED"], ["GREEN", "ROLLED_BACK"], ["UNDEPLOYED", "PLANNED"]]
  },
  "file_writes": 0,
  "database_mode": "named in-memory only",
  "blocked_attempts": []
}
```

최종 구현 수용 조건: 환경 단위 동시성 통제 하에서 현재 포인터·새 계획 결과·감사 기록을 일관되게 갱신한다. DB 트랜잭션이 외부 트래픽 전환까지 원자적으로 만드는 것은 아니므로, 외부 전환과 DB 기록 사이 장애는 관측·재대조 경로로 처리한다. 중간 실패, 동시 승격, 재시도, 잘못된 복귀 대상 시험을 추가한다.

**구 원장의 과거 계획 되살리기 자체는 이미 정본과 충돌한다. 그 상태 기계를 먼저 고쳐 완성한 뒤 다시 버리는 이중 작업은 하지 않는다.** 현재 반례를 후속 설계/시험의 필수 사례로 보존하고, 실제 API 연결은 새 계약을 충족한 구현에만 한다.

### DEP-R2 / P2 — 준비도에 실제 fail-open 반례 두 개

위치: `core/serving_readiness.py:88-100`, `:206-219`.

직접 실행 결과:

```text
Report(checks=[Check("probe", "TIMEOUT")]).verdict → READY
check_shared_storage([]).verdict                  → READY
```

- 알려진 FAIL/UNKNOWN만 검사하고 나머지를 READY로 반환한다. 허용되지 않은 판정은 통과하면 안 된다.
- CLI의 `--shared-dir` 기본값은 빈 목록이다. 공유 경로를 지정하지 않아도 해당 검사가 READY가 된다.

권고: 개별 판정 값 검증 + 집계에서 모든 필수 검사가 명시적으로 READY일 때만 READY. 공유 저장소가 필요한 설치에서 빈 경로는 UNKNOWN/FAIL로 차단한다. 정말 공유 저장소가 불필요한 역할이 있다면 승인된 설치 계약으로 명시하며, 단순 누락을 불필요로 간주하지 않는다. 정상 READY 양성 대조도 유지한다.

### DEP-R3 / 운영 연결 전 P1 — 현재 준비도는 실제 serving 증거가 아님

위치: `core/serving_readiness.py:206`, `:245`, `:279`, `scripts/serving_readiness_probe.py:40-68`.

- `.afs-shared`는 단순 파일 존재 검사다. 서로 다른 로컬 디렉터리에 빈 파일을 두어도 공유 저장소로 간주한다. 실제 마운트/저장소 동일성을 증명하지 않는다.
- 역할은 CLI의 `--started` 문자열, digest/config는 탐침 프로세스의 환경변수로 받는다. 실행 중인 업무 프로세스가 직접 제공한 신원/생존 관측이 아니다. 직접 predicate 실행에서도 같은 선언값만 주면 READY가 된다.
- 기본 DB 경로는 로컬 SQLite `auth.db`·`enterprise_context.db`다. 현재 설정한 실제 backend/DSN의 PostgreSQL 준비도를 검사하는 구현이 아니다.
- 기존 합성 시험은 로컬 DB·표식·전달한 역할 문자열만으로 READY를 만든다. 이는 판정 함수 연결 시험이지 실제 서버 기동 증거가 아니다.

따라서 인계 §4의 “실제 증거 쪽”은 **“읽기 전용 준비도 판정 초안; 실제 관측 공급자 미연결”**로 정정해야 한다. 실제 앱을 내린 상태에서 운영 탐침 전체를 검증한 것은 아니므로 그러한 실측으로도 과장하지 않는다.

통합 시에는 노드/환경/릴리스 신원과 관측 시각이 결속된 실제 응답, 역할별 생존/필수 의존성, 설정된 DB backend, 공유 저장소 결속을 확인한다. stale/unknown/mismatch는 승격 불가다. 이 조건 없이 현재 READY를 단독 승격 근거로 사용하면 안 된다.

### DEP-R4 / P2 — 폴더 이동만으로 관리 저장소가 분리되지 않음

위치: `ops_control/deploy_ledger.py:44`, `:112-116`, `:131`.

`core.paths.data_path`를 import하고, 경로를 생략하면 업무 `data/deploy_ledger.db`를 사용하며 생성자에서 DDL을 실행한다. `ops_control/`로 옮기고 업무 산출물에서 제외한 것은 맞지만 **의존성과 기본 저장 위치는 아직 분리되지 않았다.** 기본 생성자는 이번 검토에서 실행하지 않았다.

정식 OPS 구현은 별도 관리 DB 설정·명시적인 마이그레이션을 사용하고 업무 DB로 fallback하지 않는다. SQLite용 연결 factory/Row 처리를 그대로 PostgreSQL 어댑터라고 부르지 않는다. 프로토타입을 남기는 동안에도 향후 실수로 배선되지 않도록 명시적 경로 없이는 생성 불가 등의 방어와 시험을 후속 최소 보완으로 권고한다.

## 4. 이미 알려진 충돌에 대한 판정

- **과거 계획 SUPERSEDED→PROMOTED 복원은 수용하지 않는다.** 복귀는 이전 artifact를 목표로 하는 새 계획이고 과거 실행 이력은 바꾸지 않는다. 환경의 현재 serving 포인터와 역사적 계획 결과를 구분한다.
- 임의 approver 문자열을 받는 현재 `approve()`는 GitHub의 신원·권한·최종 승인 증거를 대체하지 않는다. 지금 제품 API에 배선되지 않았으므로 실제 권한 우회가 발생했다고 주장하지 않는다.
- 현재 코드의 `production` 환경과 7개 상태를 V1 정본에 무조건 이식하지 않는다. 15개 이름으로 바꾸는 것만으로 lease·승인·실행/대조 수명·복구 계약이 생기지 않는다.
- 파일 색인은 재사용한다. full release manifest, 출처 승인, Linux 빌드/설치, 배포 적격성은 별도 증거다. `eligible=true` 금지에 동의한다.
- 확인한 정적 호출 범위에서 원장 제품 배선은 발견하지 못했다. 이는 **현재 미연결 상태의 확인**이지, 미래의 호출을 막는 강제 통제나 모든 동적 호출의 부재 증명은 아니다.

## 5. 결정 요청 8건 회신

| 번호 | 검토 결론 / 다음 구현 기준 |
|---|---|
| ① 원장 재사용 | **선별 재사용.** 파일을 지우지 말고 미연결 프로토타입으로 보존한다. 환경 잠금·승인 결속·실패 시 기존 서비스 보존 등의 시험 의도는 살린다. 기존 클래스/상태/저장 모델 그대로 OPS-P2 완료품으로 채택하지 않는다. 보완 정본 이후 실제 domain/persistence를 구현하고 겹치는 프로토타입을 정리한다. |
| ② readiness 위치 | 업무 노드가 자신의 의존성을 읽는 health/readiness는 `core/`에 남아도 된다. 관리툴이 업무 모듈을 직접 import하지 않고 문서화된 응답 계약으로 소비한다. 순수 판정 함수와 노드의 관측 수집자를 구분한다. |
| ③ HTTP 경계 | “인증 때문에 LB 불가 / 무인증이면 내부 노출”의 양자택일은 아니다. **LB용 최소 상태 응답과 관리용 상세 진단을 분리**한다. 전자는 사설 네트워크·LB 접근원 제한과 최소 본문, 후자는 agent 인증/mTLS와 권한을 적용한다. 실제 NCP LB 종류·포트·라우팅 확인 전 새 HTTP 엔드포인트를 임의 공개하지 않는다. 지금 CLI는 진단 초안으로 유지한다. |
| ④ starter_kits 출처 | 경로만으로 합성/공유 승인을 인정하지 않는다. 소유자·출처·민감도·배포 가능 범위를 파일 hash 목록과 결속한다. 미분류 CSV/XLSX는 외부 배포 적격성에서 차단한다. 원본 삭제나 내용 공개는 하지 않는다. 합성이 아닌 자료도 권한과 승인에 따라 배포 가능하므로 ‘실자료면 무조건 삭제’로 단순화하지 않는다. |
| ⑤ scripts 제외 | 업무 runtime 산출물은 기본 제외 + 검토한 탐침의 명시 허용을 유지한다. migration/bootstrap 도구가 필요하면 별도 권한의 배포 작업용 묶음으로 명시한다. 모든 scripts 또는 파종 도구 8종을 runtime에 일괄 허용하지 않는다. |
| ⑥ .afs-shared | 설치 선언용 보조 표식은 가능하지만 **빈 파일을 놓아 READY를 만드는 안은 승인하지 않는다.** 실제 backend/mount 결속과 양 노드 동일 저장소 확인이 필요하다. 필요한 읽기 검증 자료는 승인된 설치/격리 절차에서 준비하고 readiness 자체는 무변경을 유지한다. |
| ⑦ update.sh | 기존 in-place pull/install/restart 경로를 무중단 트라이얼 배포 경로에 연결하지 않는다. 불변 산출물을 candidate에 설치·검증·전환하는 새 경로가 파일 선별/manifest 검증을 소비해야 한다. 구 스크립트는 임의 삭제하지 말고 legacy 용도로 구분한다. |
| ⑧ 기존 미결 4건 | 아래처럼 규칙·구현 조사·외부 입력을 나누어 처리한다. 네 건 모두를 하나의 사용자 선택 대기로 묶지 않는다. |

⑧ 세부:

1. **열 추가 규칙:** 신규 운영 경로는 기동 중 자동 DDL 대신 버전 관리된 명시 migration을 기본으로 한다. 무중단이면 old/new 앱이 함께 읽을 수 있는 expand→전환→contract 순서다. 테이블별 현재 DDL/데이터 검증 없이 열을 실제 추가하지 않는다.
2. **julianday 트리거:** SQLite 전용 표현을 PostgreSQL에 그대로 전달하지 않는다. 시간 단위·NULL·timezone·갱신 조건을 동등성 시험으로 고정하고 방언별 migration을 구현한다. 구체 SQL은 해당 트리거 대조 및 격리 PG 시험 후 확정한다.
3. **일반 status 승격 근거:** 범용 상태 변경이나 CLI 결과만으로 승인/적격/serving 증거를 대체하지 않는다. 기존 권한 계약을 유지하고, 실제 해당 소비자 및 전이의 근거를 제시한 뒤 변경한다. 이번 원장 검토가 다른 업무 status 변경 권한을 부여하지 않는다.
4. **PostgreSQL DSN:** 실제 접속 대상과 계정은 외부 선행조건이다. 격리 시험 DB를 먼저 지정하고 비밀 저장소/로컬 비공개 환경으로 주입한다. DSN·비밀번호를 인계서나 채팅·Git에 적지 않는다. 미제공 상태에서 운영 DB로 자동 fallback하거나 신규 유료 자원을 만들지 않는다.

NCP 네트워크 경계 참고: 공식 [Load Balancer 접근 문제 해결](https://guide.ncloud-docs.com/docs/en/loadbalancer-troubleshoot-access)은 LB 서브넷과 서비스 포트를 기준으로 ACG/NACL 허용을 확인하도록 안내한다. 위 HTTP 이원화는 이를 활용한 설계 권고이며, 현재 클라우드에 해당 설정이 완료됐다는 증거는 아니다.

## 6. 다음 묶음 권고 — 재작성 낭비를 줄이는 순서

**이번 턴에는 미착수. 기존 설계 후속 작업 홀딩도 유지.**

1. **30~45분:** DEP-R2 두 반례를 정규 시험으로 추가하고 fail-closed 보완. 준비도를 ‘실제 serving 증거’로 부른 문구/인계 수용표 정정. 관리 원장의 업무 DB 기본 fallback 방어와 소규모 시험을 포함하되 새 상태 기계를 만들지 않는다.
2. **15~25분:** DEP-R1의 실패/잘못된 대상 시나리오를 재현 가능한 검토 회귀 사례로 남긴다. 확정되지 않은 구 rollback을 정교하게 수리하는 데 시간을 쓰지 않는다. 프로토타입 미연결 및 업무 산출물 제외를 재확인한다.
3. **설계 작업 재개 후:** 독립 검토 지적을 보완한 정본 기준으로 OPS-P2의 저장소·상태·승인·agent 경계를 구현한다. 실제 PG·OS 슬롯·관측 공급자는 각각 실행 증거가 생길 때만 완료 처리한다. 이 작업은 위 45~70분에 포함하지 않는다.

완료 보고는 ‘시험 수’보다 **해결한 반례 / 남은 운영 기능 / 다음 예상 시간**을 앞에 둔다. 같은 범위의 변이를 무한 추가하거나 폐기 예정 원장 구현을 먼저 완성하지 않는다.

## 7. 진척과 전달 상태

- 전체 인정치 **21/40 = 52.5% 유지**. 이번 검토로 단계 가산하지 않는다.
- 현재 유용한 산출물: 파일 선별/색인과 거절 시험, 읽기 전용 SQLite 진단 초안, 원장의 정책 시나리오.
- 미완료: 정본과 일치하는 관리 backend/DB, 신뢰 가능한 노드 관측, OS 슬롯·트래픽 전환, 출처 승인/완전 manifest, 실제 PG 수용.
- 이번 공유물은 검토 회신이다. Claude가 읽었거나 수정에 착수했다고 아직 확인하지 않았다.
