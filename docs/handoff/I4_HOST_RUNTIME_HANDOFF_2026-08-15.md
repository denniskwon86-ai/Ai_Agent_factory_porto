# [I-4] Host Runtime 생성기 연동 — 인수인계

**작성 2026-08-15 · 상태: 설계 rev.3 승인 · **1단계·2단계+2.1 보정 완료** · 3~8단계 미착수**

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
[7] I-4 ── 설계 rev.3 ✅  ·  1단계 ✅  ·  2단계+2.1 보정 ✅  ·  3~8단계 미착수
```

**다음에 할 일: 설계서 §20 의 3단계** — 계약 지문을 **증명에 봉인**한다(§16).
순서를 바꾸지 않는다: 6 없이 7 을 하면 승격할 후보가 없다.

⚠️ **각 단계는 그 단계까지의 회귀를 갖고 커밋한다.** 여덟 단계를 모아서 한 번에 올리면
어느 단계가 깨졌는지 아무도 못 찾는다.

### 1단계 (2026-08-15)

| 파일 | 무엇 |
|---|---|
| `core/app_runtime_contract.py` | 계약 정본 — 결정표 · JSON Schema · 조건부 규칙 · 의미 지문 |
| `core/host_contract_compiler.py` | 초안 → 계약(비-LLM · **던지지 않는다**) |
| `state_models.py` | `PROJECT_STATE_SCHEMA_VERSION = "5.2.0"` · 지연 마이그레이션 · 계약 필드 6 |
| `tests/test_app_runtime_contract.py` (69) | 결정표 · 지문 · 승인 초기화 · 매니페스트 대조 |
| `tests/test_project_state_schema_5_2.py` (18) | 회귀 일곱 + 소스 검사 둘 |

**변이 27/27.** 실측: 실제 `latest_state.json` **58개 전부** `5.2.0` 승격(읽기 전용, 실패 0).

⚠️ `arc.validate()` 는 **저장된 계약에도** 같은 규칙을 건다. 컴파일 경로에만 검사를 두면
파일로 들어온 계약이 아무것도 통과하지 못한 채 통과한다(변이 검사에서 잡힌 실제 구멍).

### 2단계 (2026-08-15)

| 파일 | 무엇 |
|---|---|
| `core/app_data_store.py` | `app_dataset_versions` · `app_release_dataset_bindings` · `app_id`/`dataset_key` 열 · **재실행 가능한 백필** |
| `core/app_data.py` | `bind_release` · `allowed_actions` · `adopt_dataset` · `contract_coverage` · `find_dataset` 가 결속을 지난다 |
| `api/routes/app_data_runtime.py` | `_assert_contract_action` — **6개 경로 전부**에 2차 판정 |
| `core/app_policy.py` | `DENY_DATASET_ACTION` (전역 권한 없음과 **다른 사유**) |
| `tests/test_app_dataset_binding.py` (58) | 승계 · 2차 판정 · 결속 판 · revision 불변 · 유일성 · 원자성 |

**변이 22/22.** 전체 스위트 **3,352 passed · 1 skipped**.

### 2.1 보정 (2026-08-15 · 교차검토 93 조건부 승인)

2단계는 «어느 판을 쓰는가» 를 **DB 에 적기만 하고 런타임에 쓰지 않았다.** 네 가지를 닫았다.

| # | 무엇이 틀렸나 | 무엇을 했나 |
|---|---|---|
| 1 | `version_id` 를 저장만 하고, 검증은 데이터셋 마스터의 단일 `schema_json` 으로 했다 — v1·v2 가 서로 다른 판을 가리켜도 **둘 다 마지막 스키마 하나**로 검증됐다 | `find_dataset`·`_require_active` 가 **결속된 판**을 돌려준다 · 런타임 쓰기가 `release_id` 를 넘긴다 · 콘솔 `update_schema()` 는 **계약 결속된 데이터셋을 거부**한다 |
| 2 | 같은 `(dataset_id, revision)` 에 다른 스키마가 오면 **덮어썼다** — 승인된 revision 의 의미가 나중에 바뀐다 | `schema_fingerprint` 열 추가 · 같은 내용은 멱등, **다른 내용은 충돌 거부**. 바꾸려면 새 revision |
| 3 | 유일성 제약이 옛 `(release_id, name)` 뿐이었다 · 중복 시 `adopt_dataset` 이 **첫 행을 임의 선택**했다 | 부분 UNIQUE 둘(`(tenant,app_id,dataset_key) WHERE app_id<>''` · `(release_id,runtime_name)`) · 결속에 `runtime_name` 봉인 · **모호하면 거부** · 인덱스를 못 걸면 `integrity_problems()` 로 드러냄 |
| 4 | 생성과 결속이 **별도 커밋**이라 고아 데이터셋·경쟁이 가능했다 | `AppDataStore.transaction()`(`BEGIN IMMEDIATE`) — 생성·판·결속·허용행동이 **한 트랜잭션** |

**변이 20/20** (1회차 5건 생존 · 전부 시험이 약한 것이었다).
전체 스위트 **3,378 passed · 1 skipped**.

**실측**: 운영 백업(`app_data.db.bak_test_pollution_20260813_114845` — 옛 13열 스키마 ·
결속표 없음)의 **사본**에 마이그레이션을 두 번(2단계·2.1) 돌려 확인했다:
데이터셋 보존 · 이름 조회 OK · `dataset_key`·`runtime_name` 백필 · `contract_bound=0` ·
유일성 문제 0 · 레거시 보고 `recoverable=1` · 물질화 지문 산출 · **원본 파일 지문 불변**.
⚠️ 원본에는 돌리지 않았다(운영 DB 쓰기 금지).

#### ⚠️ 레거시는 아직 승계되지 않는다 — 숫자로 드러낸다

「앱을 개정해도 데이터가 유지된다」는 **신규 계약 데이터셋에만** 참이다. 마이그레이션은
`dataset_key=name` 만 채우고 `app_id` 는 **비워 둔다**. `legacy_identity_report()` 가
다섯으로 나눈다: `recoverable` · `ambiguous` · `unbindable` · `succeeded` · `quarantined`.

⚠️⚠️ **이름이 같다는 이유로 자동 연결하지 않는다.** 서로 다른 앱이 `orders` 를 쓰는 것은
흔하고, 잘못 이으면 **남의 앱 레코드가 이 앱에 보인다.** 보고만 하고 고치지 않는다 —
4단계 물질화에서 사람이 판단한다.

#### 3단계는 지문을 **둘로** 봉인한다 (설계 §16-1)

| 지문 | 사실 | 상태 |
|---|---|---|
| `runtime_contract_fingerprint` | 승인된 계약 원문 | 계산 있음(1단계) |
| `materialization_fingerprint` | **실제 DB 결속 상태** | 계산 있음(2.1) · **봉인·`410` 강제는 3단계** |

⚠️ 원문 지문만 봉인하면 **「계약서는 승인됐지만 결속이 다른 상태」**를 못 잡는다.
어느 쪽이 달라져도 일반 만료가 아니라 **`410` + 프레임 폐기**다 — 만료로 다루면 브리지가
새 증명을 받아 **옛 코드를 계속 돌린다.**


#### ★★★ 2단계에서 반드시 알아야 할 세 값

`allowed_actions(release, dataset)` 가 돌려주는 값은 **셋이고 셋 다 다른 뜻**이다:

| 값 | 뜻 | 런타임 |
|---|---|---|
| `None` | 계약이 말한 적 없다(레거시 결속) | 2차 판정 **없음** |
| `()` | 계약이 «아무 행동도 허용 안 함» 이라 말했다 | **전부 막힘** |
| `("read",…)` | 그 목록만 | 목록 밖은 403 |

⚠️ `None` 과 `()` 를 뭉개면 **계약이 잠근 데이터셋이 열리거나, 계약 이전 앱이 통째로
멈춘다.** 둘 다 조용하다. 변이 검사가 이 둘을 각각 잡는다.

#### ⚠️ 지금 `contract_bound=1` 을 만드는 제품 경로가 없다

메커니즘과 강제는 있고, **계약을 물질화하는 쪽이 아직 없다**(4단계에서 붙는다).
그래서 현재 운영 적용률은 0 이다 — `app_data_service.contract_coverage()` 로 언제든
셀 수 있게 해 뒀다. ★ 세지 못하면 「계약을 도입했다」와 「계약이 적용되고 있다」를
구분할 수 없고, **적용률 0% 인 채로 초록인 상태**가 가장 위험하다.

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

### 2-2. 권한이 «데이터셋별» 이 아니었다  ✅ 2단계에서 닫음

`core/app_proof.manifest_actions()` 가 매니페스트 capability 를 `read/write/delete/manage`
**전역 합집합**으로 평탄화한다. 즉

```
orders.read + secrets.update  →  전역 read + write  →  orders 에도 write 가 열린다
```

이제 `_assert_contract_action` 이 **1차 판정 뒤**에 데이터셋별 `allowed_actions` 로 자른다.
⚠️ 1차(증명·릴리스·조직·세션)를 **데이터셋 뒤로 옮기지 않는다** — 그 순서에서 만료·타인
증명으로 **데이터셋 이름을 열거**할 수 있었다(교차검토 86 에서 실제로 열렸다).
★ 매니페스트의 전역 합집합은 **그대로 둔다** — 1차는 여전히 그것을 본다. 2차가 좁힐 뿐이다.

### 2-3. 새 릴리스가 나오면 현업 데이터가 안 보였다  ✅ 2단계에서 닫음

```sql
-- core/app_data_store.py:42
CREATE TABLE IF NOT EXISTS app_datasets ( dataset_id TEXT PRIMARY KEY,
    release_id TEXT NOT NULL, name TEXT NOT NULL, ... )
CREATE UNIQUE INDEX ... ON app_datasets(release_id, name);
```

종전에는 데이터셋이 릴리스에 직접 묶여 있고 `find_dataset()` 이 `WHERE release_id=? AND
name=?` 로 범위를 잡았다. **앱을 한 번 개정하면 그 이름의 데이터셋을 못 찾고 새로 만들었다**
→ 레코드 승계 실패. 화면에는 오류가 아니라 «데이터 0건» 이 떴다.
이제 `find_dataset()` 은 **결속(binding)을 지나** 찾고, `adopt_dataset(app_id, dataset_key,
새 release)` 가 같은 데이터셋을 이어받는다 — `app_records.dataset_id` 는 그대로다.

### 2-4. `ProjectState` 는 `extra='forbid'` 다  ✅ 1단계에서 닫음

`state_models.py:95`. 필드를 선언하지 않으면 Compiler 가 계약을 산출해도 **상태가 조용히
버린다.** 여섯 필드를 더했다(설계 §11) — 앞으로 계약에 필드가 늘면 **여기도 함께** 는다.

### 2-5. 증명은 **매니페스트 지문만** 봉인한다 — 3단계에서 닫는다

계약만 바뀌고 매니페스트의 전역 합집합이 같으면 **기존 증명이 살아남는다.**
그리고 **지문 하나로는 부족하다**: 계약 원문이 승인된 그대로여도 **DB 결속이 어긋나면**
앱은 승인받은 것과 다른 권한·다른 스키마로 돈다. 원문 지문은 그때 아무 신호도 내지 않는다.
그래서 `runtime_contract_fingerprint` 와 `materialization_fingerprint` **둘 다** 봉인한다
(설계 §16-1). 물질화 지문 계산은 2.1 에서 끝났고, 봉인·`410` 강제가 3단계다.

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

### 한 것 (전부 ✅)

1. **버전 상수화** — `state_models.py` 에 `PROJECT_STATE_SCHEMA_VERSION = "5.2.0"`,
   `schema_version` 기본값도 그것을 쓴다. ⚠️ 문자열을 반복하면 한 곳만 고치는 날이 온다.
2. **지연 마이그레이션** — `_migrate_schema_version` (`model_validator(mode="before")`)

   ```
   버전 없음 / 현재보다 낮은 버전  → schema_version = 5.2.0 (필드 기본값이 보완)
   5.2.0                          → 그대로 검증
   5.2.0 초과                     → 명확한 ValidationError
   X.Y.Z 모양이 아님              → 패턴 검증이 그 자리에서 거부
   ```

   ★ 「5.1.0 목록」이 아니라 **「현재보다 낮으면 승격」**으로 구현했다 — 목록을 쓰면
   `5.0.x` 같은 더 오래된 상태가 조용히 빠진다.
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
| `ControlPanel.tsx:304` | 상태 스키마 | ✅ `schema_version: undefined` 로 제거 |
| `ControlPanel.tsx:342` | 상태 스키마 | ✅ 같음 |
| `sprintActions.ts:65` | 상태 스키마 | ✅ 키 자체를 뺌 |
| `run_e2e_scenario.py:185` | 상태 스키마 | ✅ 보내지 않음 |
| **`main.py:45` `version="5.1.0"`** | **FastAPI 앱 버전** | ⚠️ **손대지 않았다** |

⚠️⚠️ 마지막 줄이 함정이다. 같은 문자열이라 함께 고치고 싶어지는데, 그러면 **API 버전과 상태
스키마가 한 숫자에 묶인다** — 이후 한쪽만 올릴 수 없게 된다.
`test_api_version_is_not_coupled_to_state_schema` 가 그 결합을 막는다.

★ `ControlPanel` 에서 키를 지우지 않고 `undefined` 를 쓴 이유: 그 자리는
`...(state || {})` 로 **디스크에서 읽은 옛 상태를 펼치는** 자리다. `GET /state/latest` 는
파일을 그대로 돌려주므로(모델을 지나지 않는다) 거기에 `5.1.0` 이 들어 있다. `undefined` 로
덮어야 그 값이 **되돌아가지 않는다**(`JSON.stringify` 가 키를 버린다).

### 3-2. 1단계 필수 회귀 일곱 — 전부 ✅

`tests/test_project_state_schema_5_2.py` (18 tests)

| 회귀 | 시험 |
|---|---|
| 버전 없는 상태 → `5.2.0` | `test_state_without_version_is_promoted` |
| `5.1.0` → 필드 기본값과 함께 승격 | `test_state_510_promoted_with_default_contract_fields` |
| 신규 필드 JSON 저장·재로드 | `test_contract_fields_survive_json_roundtrip` |
| 체크포인트 직렬화·역직렬화 | `test_checkpoint_roundtrip_preserves_contract_fields` |
| 옛 프런트가 보낸 `5.1.0` → 다운그레이드 없음 | `test_stale_client_payload_cannot_downgrade` |
| 미래 버전 명확 거부 | `test_future_version_is_rejected` |
| 신규 노드 강제 진입 없음 | `test_contract_fields_do_not_change_routing` · `test_no_i4_node_is_wired_yet` |

여기에 소스 검사 둘을 더했다: 프런트가 버전 문자열을 **싣지 않는지**(주석 제외하고 본다),
`main.py` 가 상태 스키마 상수를 **API 버전으로 쓰지 않는지**.

### 3-3. 혼동하면 안 되는 세 버전

| 이름 | 값 | 무엇의 계약인가 |
|---|---|---|
| `ProjectState.schema_version` | `5.2.0` | 파이프라인 상태 |
| `App Runtime Contract.schema_version` | `1.0` | 계약 문서 형식 |
| `runtime_contract_version` | `1` | 앱↔Host 런타임 계약 세대 |

---

## 4. 남은 순서 (설계서 §20)

```
1. 계약 JSON Schema · Compiler · 상태 필드          ✅ 2026-08-15
2. 데이터셋 안정 식별자 · 릴리스 바인딩 · 데이터셋별 Runtime 판정  ✅ 2026-08-15
3. Proof 의 계약 지문 결속                          ← 여기부터
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
   ⚠️ **아직 새고 있다**: 전체 스위트를 돌리면 `data/decision_ledger.db`·`data/llm_cache.db`
   mtime 이 움직인다. 개별 스위트로는 재현되지 않는다 — 어느 시험인지 미특정(§6-7).
8. **1단계에서 새로 겪은 것 — 변이 검사가 「검사가 한쪽 경로에만 있다」를 잡아냈다.**
   사용자 결정 규칙이 컴파일러에만 있고 `validate()` 에는 시험이 없어, 규칙을 통째로
   지워도 초록이었다. 계약은 **파일로도 들어온다**(릴리스 스냅샷·손편집) — 검사는 두 경로
   모두에서 시험해야 한다.

---

## 6. 아직 안 된 것 · 부채

| # | 항목 | 메모 |
|---|---|---|
| 1 | **I-4 3~8단계** | 1·2(+2.1)단계는 끝났다. 다음은 Proof 의 **두 지문** 봉인(§16-1) |
| 2 | `app_pdp_enforce` 관리자 **카드** | API 는 있고 화면이 없다. 현재값·출처·영향·사유·이력 함께 표시 |
| 3 | 서버 쪽 **멱등키 저장** | 지금은 한 세대 안의 중복만 막는다 |
| 4 | 레코드 **판(version) 컬럼** | 없어서 계약이 `version` 을 **거부**한다 |
| 5 | `_release_scope` 의 미러 의존 | 전환이 끝났으므로 파일을 단일 원천으로 삼을 수 있다 — 다만 드리프트를 먼저 0 으로 |
| 6 | G2 온톨로지 구현 | I-4 가 만드는 계약의 `ontology_entity_type` 이 그 입력이다 |
| 7 | **시험이 `data/*.db` 에 쓴다** | 전체 스위트 후 `decision_ledger.db`·`llm_cache.db` mtime 변동. 개별 스위트로는 재현 안 됨 — 범인 미특정. 2026-08-13 오염과 같은 부류 |
| 8 | 계약 원문의 **저장 위치 배선** | `<workspace>/contracts/app_runtime_contract.json` 읽기·쓰기는 4단계에서 붙인다(1단계 컴파일러는 순수 함수) |
| 9 | **계약 물질화 경로 없음** | `contract_bound=1` 을 만드는 제품 코드가 아직 없다 → 운영 적용률 0. 4단계에서 붙는다 |
| 10 | 관리 API 가 계약 밖 데이터셋을 만든다 | §4 의 `409` 는 6~7단계 몫. 지금은 `contract_coverage(declared=…)` 의 `undeclared` 로 **보이기만** 한다 |
| 11 | 레거시 `app_id` 복원 | `legacy_identity_report()` 가 다섯으로 나눠 보고만 한다 — **자동 연결 금지**, 4단계에서 사람이 판단 |

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
| `tests/test_app_runtime_contract.py` (69) | **[1단계]** 결정표 · 지문 · 승인 초기화 · 매니페스트 대조 |
| `tests/test_project_state_schema_5_2.py` (18) | **[1단계]** 5.2.0 마이그레이션 · 소스 검사 |
| `tests/test_app_dataset_binding.py` (58) | **[2단계+2.1]** 승계 · 2차 판정 · 결속 판 · revision 불변 · 유일성 · 원자성 |
| `scripts/canary_host_runtime{,_seed}.py` | 격리 카나리(드라이버가 스스로 판정) |

**변이 검사 누적 157/157**(G1-B 88 + 1단계 27 + 2단계 22 + 2.1 보정 20).
전체 스위트 **3,378 passed · 1 skipped**(2026-08-15) · `tsc -b` 초록.

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
