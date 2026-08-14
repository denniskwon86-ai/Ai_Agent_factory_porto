# [I-4] Host Runtime 생성기 연동 — 인수인계

**작성 2026-08-15 · 상태: 설계 승인 완료 · 1단계 착수 승인 · 코드 미착수**

이 문서 하나만 읽고 이어받을 수 있게 적는다. 무엇이 끝났고, **무엇이 아직 안 됐고**,
어디서부터 손대야 하는지.

선행 문서:
`docs/design_i4_generator_host_runtime_2026-08-15.md` (**정본 설계 rev.3**) ·
`docs/handoff/G1B_P0_APP_RUNTIME_HANDOFF_2026-08-14.md` (런타임 보안) ·
`docs/design_app_data_plane_2026-08-08.md` (데이터 평면).

---

## 0. 재개하는 사람은 여기부터

```
G1-B P0 ✅  I-3 브리지 ✅  3.5 앱 증명 ✅  [4] 카나리 ✅  [5] 게이트 ✅  [6] 전환 ✅
[7] I-4 ── 설계 rev.3 승인 ✅  ·  구현 1단계 착수 승인 ✅  ·  코드 0줄
```

**다음에 할 일: 설계서 §20 의 1단계.** 그 안에 `ProjectState` 5.1.0 → **5.2.0** 승격이
포함된다(§20-0). 순서를 바꾸지 않는다 — 2 없이 3 을 하면 지문이 가리킬 대상이 불안정하고,
6 없이 7 을 하면 승격할 후보가 없다.

⚠️ **각 단계는 그 단계까지의 회귀를 갖고 커밋한다.** 여덟 단계를 모아서 한 번에 올리면
어느 단계가 깨졌는지 아무도 못 찾는다.

---

## 1. 지금 서 있는 자리 — [6] 까지 무엇이 끝났나

| 항목 | 상태 | 핵심 |
|---|---|---|
| B01-A/B 계약 | ✅ | 표면·호출 계약을 코드에 못박음 |
| B02 자격증명 금지 | ✅ | iframe 에 토큰이 가지 않음(소스 검사 + 실행 검증) |
| B03 앱 증명 | ✅ | 해시 저장·세션 결속·전수 대조 |
| B04 정책 결정점 | ✅ | 판정이 한 곳 |
| B05 관측·게이트 | ✅ | 지속형 + 동적 5 / 구조 5 두 축 |
| I-3 브리지 | ✅ | 기본 꺼짐 · 전용 경로만 · 응답 투영 |
| 3.5 앱 증명 종단 | ✅ | 발급 API · 폴백 없음 · 매니페스트 결속 |
| [4] 격리 카나리 | ✅ | `canary_5` 26/26 · `safe_to_switch=True` |
| [5] 전환 게이트 | ✅ | 코드 지문 `3b12d82d7f965600` 에 결속 |
| **[6] 원자적 전환** | ✅ | 관리 API 가 PDP 로 강제 · 롤백은 정책 파일 한 줄 |

### 전환의 현재 상태 (운영에 영향 있음)

· `scope_policy.app_pdp_enforce()` **기본값 True** — 관리 API 를 신규 PDP 가 강제한다
· 되돌리기: 관리자 API `PUT /api/v1/admin/app-pdp-enforcement` (`enabled=false` + **사유 필수**)
· ⚠️ 되돌리면 통제가 **넓어진다**(앱 증명·매니페스트·문맥 축이 관리 API 에서 빠진다)
· 어느 쪽이 강제하든 **두 판정을 모두 관측**한다 — 관측을 끄면 되돌릴 근거가 사라진다

---

## 2. I-4 설계에서 반드시 알고 있어야 할 다섯

설계서를 다 읽기 전에 이 다섯만은 먼저 알아야 한다. **전부 실측으로 확인된 것**이고,
모르면 rev.1 이 그랬듯 틀린 전제 위에 구현하게 된다.

### 2-1. ★★★ Tech Lead 는 건너뛸 수 있다

```python
# core/agent_graph.py:100  _route_to_first_assigned()
if include_design:
    if include_architect and _has_role(agents, "Architect", ...): return "Architect"
    if _has_role(agents, "Tech_Lead", ...):                       return "Tech_Lead"
if _has_role(agents, "Backend", ...): return "Backend"   # ← 배정 없으면 여기로 떨어진다
```

태스크의 `required_agents` 에 Tech_Lead 가 없으면 **설계 단계를 건너뛰고 코드 생성으로
진입한다.** 그래서 `hotl_after=True` 하나로는 계약을 강제할 수 없고, **결정론적 Compiler
노드와 필수화**가 함께 있어야 한다(설계 §3, §15).

### 2-2. ★★★ 지금 권한은 «데이터셋별» 이 아니다

`core/app_proof.manifest_actions()` 가 매니페스트 capability 를 `read/write/delete/manage`
**전역 합집합**으로 평탄화한다. 즉

```
orders.read + secrets.update  →  전역 read + write  →  orders 에도 write 가 열린다
```

I-4 는 데이터셋별 `allowed_actions` 를 **2단계 판정**으로 강제한다(설계 §6).
⚠️ 1차(증명·릴리스·조직·세션)를 **데이터셋 뒤로 옮기지 않는다** — 그 순서에서 만료·타인
증명으로 **데이터셋 이름을 열거**할 수 있었다(교차검토 86 에서 실제로 열렸다).

### 2-3. ★★★ 새 릴리스가 나오면 현업 데이터가 안 보인다

```sql
-- core/app_data_store.py:42
CREATE TABLE IF NOT EXISTS app_datasets ( dataset_id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL, name TEXT NOT NULL, ... )
CREATE UNIQUE INDEX ... ON app_datasets(release_id, name);
```

데이터셋이 릴리스에 직접 묶여 있고 `find_dataset()`(`core/app_data.py:255`)이
`WHERE release_id=? AND name=?` 로 범위를 잡는다. **앱을 한 번 개정하면 그 이름의 데이터셋을 못 찾고 새로 만든다** → 레코드 승계 실패.
설계 §18 이 `app_datasets` / `app_dataset_versions` / `app_release_dataset_bindings` 로
쪼개고 `app_records` 는 **안정적인 dataset_id** 에 남긴다.

### 2-4. `ProjectState` 는 `extra='forbid'` 다

`state_models.py:95`. 필드를 선언하지 않으면 Compiler 가 계약을 산출해도 **상태가 조용히
버린다.** 1단계에서 여섯 필드를 더한다(설계 §11).

### 2-5. 증명은 **매니페스트 지문만** 봉인한다

계약만 바뀌고 매니페스트의 전역 합집합이 같으면 **기존 증명이 살아남는다.**
`contract_id`·`contract_revision`·`contract_fingerprint` 를 더해야 한다(설계 §16, 3단계).

---

## 3. 1단계 상세 — `ProjectState` 5.2.0 과 계약 필드

### 왜 버전을 올리는가

⚠️ 필드 추가는 기존 상태를 깨지 않으니 major 는 아니다. 그러나 **저장·재개되는 계약이
확장**되므로 `5.1.0` 을 유지하면 다음 둘을 구분할 수 없다:

    「구버전이라 계약 필드가 없는 상태」   vs   「신버전인데 데이터셋 0개인 정상 계약 상태」

그 둘은 전혀 다른 사실이고, I-4 는 후자를 **정상 계약**으로 다룬다(설계 §15).

### 실측 (2026-08-15, 내가 직접 셈)

```
projects/**/latest_state.json  58개
  버전 없음  42
  5.1.0      16
```

**두 경우 모두** 회귀로 잠근다.

### 해야 할 일

1. **버전 상수화** — `state_models.py` 에 `PROJECT_STATE_SCHEMA_VERSION = "5.2.0"` 를 두고
   `schema_version` 기본값도 그것을 쓴다. ⚠️ 문자열을 반복하면 한 곳만 고치는 날이 온다.
2. **지연 마이그레이션** — `model_validator(mode="before")` 에서

   ```
   버전 없음 / 5.1.0  → 계약 필드 기본값 보완 → schema_version = 5.2.0
   5.2.0             → 그대로 검증
   5.2.0 초과        → 명확한 ValidationError (조용히 읽지 않는다)
   ```

   ⚠️⚠️ **미래 버전을 추측해 읽지 않는다.** 모르는 계약을 읽으면 그 추측이 곧 데이터 손상이다.
3. **새 필드 여섯** (기본값 안전하게)

   ```
   capability_intents = []          app_runtime_contract_status = ""
   app_runtime_contract_fingerprint = ""   app_runtime_contract_summary = ""
   unsupported_requirements = []    approved_contract_fingerprint = ""
   ```

   ★ **계약 원문은 workspace 파일이 정본**이고 상태에는 요약·상태·지문만 둔다 —
   원문을 상태에 넣으면 체크포인터가 매 단계 복사하고, 커지는 상태는 재개를 느리게 만든다.
4. **기존 파일을 일괄 재작성하지 않는다.** 읽을 때 승격하고, 저장이 일어날 때 기록한다.
5. **프런트가 스키마 버전을 정하지 않게 한다** — 아래 §3-1.

### 3-1. 하드코딩 위치 — 다섯 곳이고, **한 곳은 성격이 다르다**

| 위치 | 무엇인가 | 조치 |
|---|---|---|
| `frontend/src/components/ControlPanel.tsx:304` | 상태 스키마 | 요청에서 **제거** |
| `frontend/src/components/ControlPanel.tsx:342` | 상태 스키마 | 요청에서 **제거** |
| `frontend/src/factory/sprintActions.ts:65` | 상태 스키마 | 요청에서 **제거** |
| `run_e2e_scenario.py:185` | 상태 스키마 | 서버 값 사용 |
| **`main.py:45` `version="5.1.0"`** | **FastAPI 앱 버전** | ⚠️ **건드리지 않는다** |

⚠️⚠️ 마지막 줄이 함정이다. 같은 문자열이라 함께 고치고 싶어지는데, 그러면 **API 버전과 상태
스키마가 한 숫자에 묶인다** — 이후 한쪽만 올릴 수 없게 된다.

★ 서버가 버전을 부여하게 하는 이유: 오래 열린 브라우저가 `5.1.0` 을 다시 보내 상태를
**다운그레이드**하는 경로를 없앤다. `sprint/start` 에서도 서버 값이 클라이언트 값을 이긴다.

### 3-2. 1단계 필수 회귀 일곱

· 버전 없는 기존 상태 → `5.2.0` 으로 로드
· `5.1.0` 상태 → 신규 필드 기본값과 함께 `5.2.0` 으로 승격
· 신규 계약 필드의 JSON 저장·재로드
· 체크포인트 직렬화·역직렬화 후 필드 보존
· 오래된 프런트가 `5.1.0` 을 보내도 **서버 상태가 다운그레이드되지 않음**
· `6.0.0` 같은 미래 버전은 **명확하게 거부**
· 기존 진행 프로젝트가 **신규 I-4 노드에 강제 진입하지 않음**

### 3-3. 혼동하면 안 되는 세 버전

| 이름 | 값 | 무엇의 계약인가 |
|---|---|---|
| `ProjectState.schema_version` | `5.2.0` | 파이프라인 상태 |
| `App Runtime Contract.schema_version` | `1.0` | 계약 문서 형식 |
| `runtime_contract_version` | `1` | 앱↔Host 런타임 계약 세대 |

---

## 4. 남은 순서 (설계서 §20)

```
1. 계약 JSON Schema · Compiler · 상태 필드          ← 여기부터 (승인됨)
2. 데이터셋 안정 식별자 · 릴리스 바인딩 · 데이터셋별 Runtime 판정
3. Proof 의 계약 지문 결속
4. Tech Lead / WBS(artifact_kind) / Contract Review Gate 연결
5. Typed SDK Adapter 와 정적 검사
6. Release Candidate · Preview DB · Preview Proof
7. ACTIVE 원자적 승격
8. 신규 생성 앱 종단 카나리
```

---

## 5. 작업 규율 — 이 저장소에서 반복해 다친 것들

이번 트랙에서 실제로 겪은 것만 적는다. 전부 **초록인데 틀린** 유형이다.

1. **하니스가 제품과 다른 세계를 만든다.** `plugin_test_auth._override` 의 `Principal` 에
   `session_id`·`requested_scope_node_id` 가 빠져 있어 **세션·범위 통제가 테스트에서 한 번도
   참인 적이 없었다.** principal 에 필드가 늘면 그쪽도 함께 늘려야 한다.
2. **대조군이 없으면 「전부 거부」도 초록이다.** 막히는 것만 보는 검사는 통제를 증명하지 않는다.
   실제로 카나리에서 「지운 뒤 0건」을 격리 증거로 쓴 적이 있다 — 무엇을 해도 0 이었다.
3. **채움값이 검사 대상과 겹치면 시험이 스스로 무력화된다.** 게이트 하니스가 `DENY_SCOPE` 를
   채움값으로 써서 「다른 조직」 시나리오를 공짜로 덮었다.
4. **주석이 검사를 통과시킨다.** 「다시 시도할 방법을」이라는 **주석** 때문에 단추를 지워도
   초록이었다. 소스 검사는 주석을 빼고 본다.
5. **시험 스텁이 제품 서명을 안 따르면 거짓 빨강이 난다.** `audit.record` 의 첫 인자는
   위치인자인데 `**kw` 만 받는 스텁을 써서 TypeError 가 호출부 `except` 에 삼켜졌다.
6. **변이 검사를 돌릴 때 `-q` 를 더하지 말 것.** `pytest.ini` 에 이미 있어 `-qq` 가 되고
   요약이 사라진다 — 한 번 속아서 「전부 생존」으로 잘못 읽었다. **종료코드**가 1차 신호다.
7. **운영 DB 에 쓰기 탐침 금지.** 2026-08-13 에 실제로 오염시켰다
   (`AppDataStore.__init__(db_path=_DB_PATH)` 기본값이 **정의 시점에 묶여** 있어 conftest
   격리 **뒤에** 만든 인스턴스가 운영 파일을 잡았다). 백업:
   `data/app_data.db.bak_test_pollution_20260813_114845`.
   ★ 카나리는 `git worktree` 사본에서 돌린다 — 격리가 규율이 아니라 **구조**가 된다.

---

## 6. 아직 안 된 것 · 부채

| # | 항목 | 메모 |
|---|---|---|
| 1 | **I-4 구현 전체** | 설계만 승인됨. 1단계부터 |
| 2 | `app_pdp_enforce` 관리자 **카드** | API 는 있고 화면이 없다. 현재값·출처·영향·사유·이력 함께 표시 |
| 3 | 서버 쪽 **멱등키 저장** | 지금은 한 세대 안의 중복만 막는다 |
| 4 | 레코드 **판(version) 컬럼** | 없어서 계약이 `version` 을 **거부**한다 |
| 5 | `_release_scope` 의 미러 의존 | 전환이 끝났으므로 파일을 단일 원천으로 삼을 수 있다 — 다만 드리프트를 먼저 0 으로 |
| 6 | G2 온톨로지 구현 | I-4 가 만드는 계약의 `ontology_entity_type` 이 그 입력이다 |

---

## 7. 검증 자산 (이 트랙에서 만든 것)

| 파일 | 지키는 것 |
|---|---|
| `tests/test_app_policy.py` (59) | PDP 판정 전수 · 매니페스트 결속 |
| `tests/test_app_capability_token.py` (32) | 해시 저장 · 세션 결속 · 봉인 |
| `tests/test_app_policy_equivalence.py` (30) | 기존 ↔ PDP 완화 0 |
| `tests/test_app_data_plane.py` (41) | 관리 API 계약 · 은폐 경계 |
| `tests/test_app_data_policy_shadow.py` (16) | 전환·롤백·관측자 장애 |
| `tests/test_app_data_runtime.py` (46) | 런타임 표면 전수 |
| `tests/test_policy_shadow_gate.py` (47) | 전환 게이트 · 구조 지문 |
| `tests/test_host_runtime_sdk.py` / `_wire.py` / `_bridge_contract.py` / `_wire_parity.py` | 계약 · 실행 대조 |
| `tests/test_admin_policy_audit.py` (30) | 정책 API · 전환 스위치 |
| `scripts/canary_host_runtime{,_seed}.py` | 격리 카나리(드라이버가 스스로 판정) |

**변이 검사 누적 88/88.** 전체 스위트 **3,233 passed · 1 skipped**(2026-08-15).

⚠️ 카나리를 다시 돌리려면: 워크트리 생성 → 씨앗 → 서버(별도 포트, `AFS_SHADOW_RUN`) →
드라이버(`--seed-file`, `--run`, `--wait-expiry`). 드라이버가 기록·판정까지 하고
**어긋나면 종료코드 1** 이다. 만료 시나리오는 실제 TTL(15분)을 기다린다 — 워크트리의 TTL
상수를 낮추면 **구조 지문이 운영과 달라져 그 증거가 무효**가 된다.

---

## 8. 커밋 이력 (이 트랙)

```
b13f003ef docs(I-4)        설계 rev.1
e780fde4d docs(I-4 rev.2)  초안·컴파일·승격 분리
a59806eac docs(I-4 rev.3)  결정 셋 확정 + 보강 넷
0c7275511 fix(G1-B 6)      관측자 장애 · 판정 불가 · 롤백 운영 경로
913bb980d feat(G1-B 6)     원자적 전환
f97dbdc70 fix(G1-B 4)      증거 생성 절차를 지문에
59e68ca9b fix(G1-B 4)      지문 줄바꿈 정규화 · 시드 전달
7796bd056 fix(G1-B 4)      카나리 자가 판정 · 공격자 쓰기
71d75b53a fix(G1-B 4)      만료 열거 차단 · 게이트 두 축
052d4123f feat(G1-B 4)     격리 카나리
7572d0a72 fix(G1-B)        Preview 브라우저 종단 복구  ← Codex
```
