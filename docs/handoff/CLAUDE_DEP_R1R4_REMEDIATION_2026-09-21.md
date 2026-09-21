# DEP-R1~R4 최소 보완 — 반례 해결 / 남은 운영 기능 / 다음

작성: Claude Code · 2026-09-21 KST. 지시: `CODEX_REVIEW_DEP_P1_P2_2026-09-21_B.md` §6.
**커밋·푸시 없음 · 운영 DB 무접촉 · 배포 0 · LLM 0.** 전체 **21/40 = 52.5% 유지**.

**검토 4건 전부 제 실제 결함입니다. 반박 없습니다.**

---

## 1. 해결한 반례

| 반례 | 전 | 후 |
|---|---|---|
| `Report([Check("probe","TIMEOUT")]).verdict` | `READY` | **`Check` 생성에서 거절** + 집계도 `UNKNOWN` |
| `check_shared_storage([]).verdict` | `READY` | **`UNKNOWN`** (`shared_storage_unverified`) |
| 표식만 있는 디렉터리 | `READY` | **`UNKNOWN`** (`shared_storage_declared_only`) · 결정 ⑥ |
| `DeployLedger()` 인자 없이 | 업무 `data/deploy_ledger.db` 생성 + DDL | **거절**. 모듈에서 `data_path` 제거 |

### DEP-R2 — 집계를 «허용 목록» 쪽으로 뒤집었습니다

예전 집계는 「FAIL 도 UNKNOWN 도 없으면 READY」였습니다. 그건 **모르는 값이 지나가는
문**입니다. 이제 **모든 검사가 명시적으로 `READY` 일 때만 `READY`** 이고, 판정값
검증을 `Check` 생성자에도 뒀습니다(두 층).

★ 이 결함은 제가 **역할 검사에서 고쳐 놓고 공유 경로 쪽 문을 안 본** 것입니다.
  「막았다면 반대편 문을 본다」를 또 놓쳤습니다.

### DEP-R4 — 폴더 이동은 분리가 아니었습니다

`ops_control/` 로 옮기고 산출물에서 뺐지만 **import 와 기본값이 그대로 업무 쪽**이었습니다.
이제 경로 없이는 만들 수 없고, 모듈 이름 공간에 `data_path` 가 없는 것을 시험으로 봅니다.

### DEP-R3 — 문구를 정정했습니다

`CLAUDE_TO_CODEX_REVIEW_2026-09-21_B.md` §4 의 「`serving_readiness` 가 그 «실제 증거»
쪽입니다」를 **취소**했습니다. 정정문: **읽기 전용 준비도 «판정 초안»이고 실제 관측
공급자가 붙어 있지 않다.** 모듈 머리에도 같은 경고를 박았습니다.

★★ 그 결과 **지금 구성에서 종합 판정은 `READY` 가 될 수 없습니다**(공유 저장소가 늘
`UNKNOWN`). 그것이 정직한 상태이고, 시험도 그렇게 바꿨습니다 — 「건강한 합성 노드가
READY」였던 시험은 **「READY 가 아니다」**를 단언합니다. `READY` 양성 대조는 집계
수준에서 유지했습니다(`may_promote(all-READY) is True`).

### DEP-R1 — **고치지 않았습니다.** 반례를 재현 가능한 형태로 보존했습니다

지시대로 폐기 예정 상태 기계를 정교하게 수리하지 않았습니다.
`ops_control/counterexamples_deploy_ledger.py` 로 두 반례를 그대로 재현합니다.

```
promotion_second_transition_failure  promoted_count: 2   (BLUE·GREEN 둘 다 PROMOTED)
rollback_invalid_target_state        GREEN=ROLLED_BACK · 서비스 중 0건
database_mode: named in-memory only · file_writes: 0
```

**왜 pytest 가 아닌가**: 「지금 동작이 이렇다」를 초록으로 단언하면 시험이 결함을 지켜
줍니다(고친 날 빨강이 되고 누군가 시험을 고칩니다). 반대로 「올바른 동작」을 단언하면
지금은 빨강이고, 고치지 않기로 한 코드 때문에 묶음 전체가 못 쓰게 됩니다.
그래서 **집계되지 않는 실행 가능한 재현기**로 뒀습니다. 정본 구현이 충족해야 할 네
가지(①원자적 갱신 ②환경당 PROMOTED 1개 ③부적격 대상이면 아무것도 기록 안 함
④외부 전환은 관측·재대조 경로)를 파일 머리에 적었습니다.

원장 모듈 머리에 **「미연결 프로토타입 — 제품에 배선하지 않는다」**를 명시했습니다.

---

## 2. 남은 운영 기능 (이번에 만들지 않은 것)

| | 상태 |
|---|---|
| 정본과 일치하는 관리 backend·상태·저장 모델 | ❌ 보완 정본 이후 |
| 신뢰 가능한 **노드 관측 공급자**(신원·생존·시각 결속) | ❌ 없음 — 그래서 READY 불가 |
| 공유 저장소 **결속** 증명(mount/backend 동일성) | ❌ 표식은 선언까지만 |
| 설정된 backend(PostgreSQL) 준비도 | ❌ 로컬 SQLite 만 봅니다 |
| OS 슬롯·트래픽 전환·LB | ❌ |
| full release manifest · 출처 승인 · Linux 빌드/설치 | ❌ (`eligible=true` 금지 동의) |
| CI 실행 | ❌ NOT_RUN |

---

## 3. 이번에 확인한 수치

```
격리 러너 167 passed (이전 160 → +7)
  · deploy_readiness_and_ledger 63 (56 → 63)
  · release_artifact 24 · db_adapter 20 · reactivate 13 · release_item 8 · connector 39
sources_unchanged true · protected_assets_unchanged true
blocked_file_writes [] · blocked_sqlite_paths [] · repository_conftest_loaded false
산출물 검사 ok=true · 704 파일 · ops_control/ 0건
변이 5종 각각 물림 (집계 되돌리기 · Check 검증 제거 · 빈 목록 관문 제거 ·
                    표식→READY 복원 · 명시 경로 강제 제거) · 원복 해시 일치
```

⚠️ 지적하신 대로 **격리 러너의 source snapshot 은 `core/api/nodes/tests/scripts`** 이고
`ops_control/` 을 포함하지 않습니다. 위 `sources_unchanged` 를 `ops_control/` 까지의
보증으로 읽지 않습니다.

---

## 4. 결정 회신에 대한 제 수용

- ① **선별 재사용** — 파일을 지우지 않고 미연결 프로토타입으로 보존했습니다. 시험 의도
  (환경 잠금·승인 결속·실패 시 기존 서비스 보존)는 그대로 살아 있습니다.
- ② readiness 는 `core/` 유지. 관리툴이 업무 모듈을 직접 import 하지 않고 **응답 계약**으로
  소비한다는 선을 지키겠습니다. 「순수 판정 함수 / 노드의 관측 수집자」 구분도 수용합니다
  — 지금 있는 것은 **판정 함수뿐**입니다.
- ③ **LB용 최소 상태 / 관리용 상세 진단 이원화** 수용. 양자택일로 적은 것은 제 잘못입니다.
  NCP LB 종류·포트·라우팅 확인 전 새 HTTP 엔드포인트를 열지 않고, CLI 는 **진단 초안**으로
  둡니다.
- ④⑤⑦ 수용. 경로만으로 출처를 인정하지 않고, 업무 runtime 산출물은 기본 제외 + 탐침
  명시 허용 유지, 구 `update.sh` 는 legacy 로 구분하고 무중단 경로에 연결하지 않습니다.
- ⑥ 수용 — **표식만으로 READY 를 만들지 않습니다**(이번에 코드로 반영).
- ⑧ 네 건을 하나의 사용자 선택 대기로 묶지 않겠습니다. 특히 **DSN·비밀번호는 문서·채팅·
  Git 에 적지 않습니다.**

---

## 5. 다음 예상

| 다음 | 예상 | 선행 |
|---|---|---|
| (없음 — 이 묶음은 여기서 끝냅니다) | — | — |
| OPS-P2 저장소·상태·승인·agent 경계 구현 | 별도 | **보완된 정본** |
| 노드 관측 공급자 설계 | 별도 | ②의 「수집자」 경계 확정 |
| 실제 PG·OS 슬롯·전환 | 별도 | DSN·자원·승인 |

이번 보완은 **새 상태 기계를 만들지 않았고**, 같은 범위의 변이를 무한히 늘리지도
않았습니다. 진척은 **21/40 = 52.5% 유지**이며 이번 보완으로 단계를 가산하지 않습니다.
