# Claude Code 인수인계 — I-4 4c 진행과 결정 원장 복구 (2026-08-17)

> 이 문서 하나로 재개할 수 있게 쓴다. **다음 사람이 물을 질문**을 먼저 적고, 그 답을
> 근거와 함께 남긴다.

---

## 0. 한 문장

I-4 4단계의 판정부(4a·4b)와 4c-0·4c-1 을 완료했고, **4c-2 도중 시험이 운영 결정
원장을 오염시킨 사고**가 드러나 4c-2 를 HOLD 한 채 원장 복구 절차(P0-L1~L5)로
전환했다. 지금 L1·L2 까지 끝났고 **L3(포렌식 보관) 직전에서 멈춰 있다.**

---

## 1. 지금 어디에 있나

```
I-4 4단계
├ 4a WBS artifact_kind        ██████████  완료
├ 4b ContractReviewGate 판정   ██████████  완료
├ 4c-0 프로필 3상태·손상 차단   ██████████  완료  9ec020b9a
├ 4c-1 프로젝트 계약 합산기     ██████████  완료  d252338ac
├ 4c-2 검토 요청 이벤트         ██░░░░░░░░  HOLD — 코드는 «작업트리에 미커밋»
├ 4c-3 전용 승인·반려 API       ░░░░░░░░░░
├ 4c-4 일반 HOTL 우회 차단      ░░░░░░░░░░
├ 4c-5 비소급 회귀              ░░░░░░░░░░
├ 4c-6 그래프 연결              ░░░░░░░░░░
└ 4c-7 릴리스 최종 차단         ░░░░░░░░░░

결정 원장 복구
├ P0-L1 격리                   ██████████  완료  99d951b9a
├ P0-L2 불변 회귀               ██████████  완료  (같은 커밋)
├ P0-L3 포렌식 보관             ░░░░░░░░░░  ← **여기서 멈춰 있다**
├ P0-L4 신규 활성 원장          ░░░░░░░░░░
└ P0-L5 전체 재검증             ░░░░░░░░░░
```

**다음 행동은 P0-L3 이다.** Supervisor 가 「보정·커밋 후 재확인해 동일하면 승인」
이라고 했고 그 조건은 충족됐다(§4). 실행 지시만 받으면 된다.

---

## 2. 사고 — 시험이 운영 결정 원장에 썼다

### 2.1 무엇이 일어났나

`tests/conftest.py` 에 **결정 원장 격리 항목이 아예 없었다.** 그래서 원장에 쓰는 모든
시험이 운영 `data/decision_ledger.db` 에 직접 썼다.

| 시점 | 행 수 | 비고 |
|---|---:|---|
| 사고 인지 전 기준선 | 11,591 | Supervisor 감사: 시험 계정 패턴 **99.64%** |
| 4c-2 시험 작성 중(1차) | 11,627 | 확정 가능한 이번 사고분 최소 36건 |
| 격리 «검증» 변이 검사(2차) | **11,633** | 아래 2.3 |

현재 센티널: `rows 11,633` · `max_seq 11,633` ·
tail `5c72c7e814f6d44905c97792ac718ffe3309190ee1dc75468133ded96ac1f408`
· `-wal`·`-shm` **없음**

### 2.2 왜 아무도 몰랐나

- `data/decision_ledger.db` 는 **Git 미추적**이다 → status 오염 검사에 안 잡힌다.
- 내가 감시하던 지문 4종(`master.db`·`enterprise_context.db`·`scope_policy.json`·
  `planning.db`)에 **없었다.**

> ⚠️ **감시하지 않는 것은 격리되지 않는다.** 격리 목록과 감시 목록이 서로를 보증하지
> 않으면, 목록에서 빠진 항목은 「없는 것」이 아니라 「보이지 않는 것」이 된다.

### 2.3 2차 사고 — 확인하려다 6건을 더 썼다

격리가 실제로 동작하는지 **메인 작업트리에서 변이 검사**를 돌렸다. 격리를 되돌리는
변이는 **정의상 운영 파일에 쓴다.** seq 11628–11633 이 그렇게 들어갔다.

> ⚠️⚠️ **메인 작업 트리에서 격리 제거 변이 검사는 영구 금지.** 반드시 `data/` 가
> 따로인 폐기 가능한 worktree 에서만 수행한다. 같은 실수를 두 번 했다 — 처음은
> 격리를 확인하지 않고 돌린 것, 두 번째는 **격리를 확인하려고** 돌린 것.

### 2.4 근본 원인 세 가지 (모두 P0-L1 에서 닫음)

| # | 원인 | 왜 치명적인가 |
|---|---|---|
| ① | `def __init__(self, db_path: str = _DB_PATH)` | 기본 인자는 **모듈 로딩 때 한 번** 평가된다. 나중에 `_DB_PATH` 를 바꿔도 굳은 옛 값이 쓰인다 |
| ② | `db_path or _DB_PATH` | **빈 문자열이 운영 원장으로** 떨어진다. 경로 계산이 빈 값을 낸 바로 그때 운영 파일이 열리고 오류는 안 난다 |
| ③ | `__init__` 이 `_init_db()` 호출 | 전역 싱글턴이 **import 되는 순간** 운영 파일을 만든다. autouse fixture 는 그보다 늦다 — 수집 단계에서 이미 늦었다 |

---

## 3. 무엇을 고쳤나 (커밋별)

### `99d951b9a` fix(harness) — 격리 세 겹

**제품 쪽**(`core/decision_ledger.py`)

```python
def __init__(self, db_path: Optional[str] = None):
    self.db_path = _DB_PATH if db_path is None else db_path   # ②
    self._prepared_for: Optional[str] = None                  # ③ 아직 안 연다

def _ready(self) -> None:          # 첫 사용 직전에만
    if self._prepared_for != self.db_path:
        self._init_db()
        self._prepared_for = self.db_path
```

`_ready()` 는 `append`·`transaction`·`get_event`·`list_events`·`subject_history`·
`verify_chain` 여섯 진입점에 배선했다.

**하니스 쪽**(`tests/conftest.py`) — 세 겹

1. **수집 전**(모듈 최상단): 세션 임시 경로로 `_DB_PATH` 와 전역 싱글턴을 함께 돌린다.
   실패하면 `raise` — 수집 자체를 멈춘다.
2. **시험마다**(autouse): `tmp_path` 로 더 좁게 다시 건다. 실패 시 `pytest.fail`.
3. **세션 전체**: 시작·종료 시 운영 원장의 논리적 상태를 대조한다.

**확인 방법**(`tests/ledger_isolation.py`)

- 파일 해시로 하지 않는다. SQLite 는 checkpoint 만으로 바이트가 달라지고, 반대로
  WAL 에만 쓰이면 본체 해시는 그대로다. → **행 수·최대 seq·tail hash**.
- ⚠️ `immutable=1` 만 쓰면 안 된다. 그 모드는 **WAL 을 아예 보지 않아** 활성 WAL 에
  최신 행이 있으면 못 본 채로 「안 변했다」고 말한다. `-wal` 이 있으면 `mode=ro`,
  없으면 `immutable=1`(아무 파일도 만들지 않는다).

### 앞선 커밋들

| 커밋 | 내용 |
|---|---|
| `d3df38d21` | 4a·4b — `artifact_kind` 닫힌 목록·Tech Lead 필수화·게이트 판정·`runtime_contract_profile` opt-in |
| `9ec020b9a` | 4c-0 — 프로필 3상태(`LEGACY_OFF`/`V1_ON`/`UNREADABLE`), 손상 시 503 차단 |
| `d252338ac` | 4c-1 — 프로젝트 단위 계약 합산기, 충돌 자동 병합 금지 |

---

## 4. P0-L3 착수 조건 — **모두 충족됐다**

2026-08-17 커밋 직후 재확인:

| 항목 | 결과 |
|---|---|
| 5173·8080~8083·8090 리스너 | 없음 |
| Python 백엔드 프로세스 | 없음 |
| `decision_ledger.db-wal` / `-shm` | 없음 |
| 센티널 | `11,633 / 11,633 / 5c72c7e8…` |

> `node_repl.exe` 4개가 떠 있으나 포트 리스너가 없고 이 저장소의 백엔드가 아니다.

### L3 실행 절차(합의된 것)

1. WAL 재확인 → 없으면 그대로, 있으면 checkpoint 후
2. SQLite Backup API 로 `data/archive/decision_ledger_polluted_20260817.db` 생성
3. 원본/사본 SHA-256 · 행 수 · tail hash · `verify_chain()` 대조
4. 포렌식 매니페스트에 사고 문서 경로와 오염 분류 쿼리 기록
5. 보관본은 읽기 전용, 제품 조회 대상에서 제외

### L4

원본을 포렌식 이름으로 **이동** → 제품 초기화 경로로 신규 빈 원장 생성.
⚠️ 행을 선별 복사하지 않는다. `CORRECTION` 을 초기 이벤트로 오용하지 않는다.

### 금지사항(그대로 유효)

- 11,633행 삭제·수정 금지 · 대량 `CORRECTION` 금지 · 추정 복원 금지
- 이름만 보고 실제/시험 행 선별 이관 금지
- 메인 트리에서 격리 제거 변이 검사 금지
- 사용자 지시 없는 `origin` 작업 금지

---

## 5. 미커밋 작업 — 4c-2 (보존 중)

**작업트리에 그대로 있다. 커밋하지 않았다.** HOLD 상태의 미완성 기능을 기준선으로
남기지 않기 위해서다.

| 파일 | 변경 내용 |
|---|---|
| `core/decision_ledger.py` | `transaction()` + `_LedgerTransaction`(`find_events`·`child_event_types`·`append`), `append` 를 `_build_row`+`_insert` 로 분해 |
| `core/contract_review_gate.py` | `ensure_review_request`·`assert_decidable`·`_decidable_in_txn`, `record_decision` 재작성(부모 연결·트랜잭션 내 검사) |
| `state_models.py` | `PROJECT_STATE_SCHEMA_VERSION` 5.2.0 → **5.3.0**, `contract_review_request_event_id` 추가 |
| `tests/test_contract_review_gate.py` | 4c-2 생명주기 회귀(동시성·재사용·중복 결정 차단 등) |
| `tests/test_project_state_schema_5_2.py` | 5.3.0 승격 회귀 |

### 재개할 때 알아야 할 것

- `_build_row` + `_insert` 를 **`append` 와 `transaction()` 이 공유**한다. 두 벌로
  만들면 체인 해시가 갈리고, 그때 `verify_chain` 은 「누군가 장부를 고쳤다」고 말한다
  — 실제로는 우리가 두 번 구현했을 뿐인데.
- 「열린 요청」의 정의는 **원장으로만** 판정한다. 상태의
  `contract_review_request_event_id` 는 **캐시**다. 체크포인트 저장이 실패했을 때
  상태만 보면 요청이 두 건 생기고, 승인이 어느 쪽에 붙었는지 아무도 답할 수 없다.
- `assert_decidable` 의 네 검사(이벤트 종류·같은 프로젝트·같은 지문·미결정)는 하나라도
  빼면 그것이 우회로다. 특히 **지문 일치**가 「사람이 A 를 보고 B 를 승인하는」 경로를
  막는 유일한 검사다.
- 검사와 기록이 **한 트랜잭션**이어야 한다. 나누면 두 사람이 동시에 승인 버튼을
  눌렀을 때 둘 다 검사를 통과한다.

### 남은 4c-2 작업

- [ ] 4c-2 회귀를 **격리된 원장**에서 다시 실행(L5 이후)
- [ ] 변이 검사(폐기 worktree 에서)
- [ ] `ProjectState` 5.3.0 이전 체크포인트 회귀 확인

---

## 6. 이번에 배운 것 — 다음 사람에게

1. **감시 목록과 격리 목록은 서로를 보증해야 한다.** 한쪽에만 있는 항목은 보이지
   않는 항목이다. Git 미추적 파일이 특히 위험하다.
2. **동작으로 관찰되지 않는 규칙은 구조로 잠근다.** 「격리 경로 검증」·「fail-open
   금지」·「세션 감시」는 다른 버그가 있을 때만 발동해서, 지워도 아무 시험이 안
   깨진다(변이 검사 실측). AST 계약 시험이 그 자리를 메운다.
3. **격리를 확인하는 시험은 fixture 안에서 하면 늦다.** 수집 시점 격리는 별도
   프로세스에서 conftest 를 import 한 직후 상태를 봐야 관찰된다.
4. **파괴적 변이 검사는 폐기 worktree 에서만.** 격리를 되돌리는 변이는 정의상 운영에
   쓴다.
5. **변이 검사가 놓친 것이 매번 가장 유익했다.** 이번에도 6건을 놓쳤고, 그 6건이
   정확히 「새 보정마다 회귀가 없던」 자리였다.

---

## 7. 실측 기록

| 항목 | 값 |
|---|---|
| 시험 명령 | `venv/Scripts/python.exe -m pytest tests -p no:warnings -q` |
| 4c-1 시점 전체 회귀 | 3,629 passed / 1 skipped / 0 failed |
| 원장·격리 집중 회귀 | 52건 통과 |
| 변이 검사 누계 | 4a 11 · 4b 14 · P0 13 · 4c-1 11 · 원장격리 13 = **62/62** |
| 운영 DB 지문 4종 | 회귀 전후 불변 |
| 운영 원장 | `11,633 / 11,633 / 5c72c7e8…` (복구 대기) |

---

## 8. 잔여사항·담당·착수 조건

| 항목 | 담당 | 착수 조건 |
|---|---|---|
| P0-L3 포렌식 보관 | Claude Code | **Supervisor 실행 지시** (조건 충족됨) |
| P0-L4 신규 활성 원장 | Claude Code | L3 사본 검증 완료 |
| P0-L5 전체 재검증 | Claude Code | L4 완료 |
| 4c-2 재개 | Claude Code | L5 실패 0건·오염 0건 |
| 4c-3~7 | Claude Code | 4c-2 완료 |
| I-4 5~8 · BDR-2~7 | Claude Code | Gate A 통과 |
| G2 U3·U4 | 보류 | Gate 2 승인 |
