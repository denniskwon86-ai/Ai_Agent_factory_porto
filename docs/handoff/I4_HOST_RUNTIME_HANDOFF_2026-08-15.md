# [I-4] Host Runtime 생성기 연동 — 인수인계

**작성 2026-08-15 · 상태: 설계 rev.3 승인 · **1·2(+2.1·2.1b)·2.2(+2.2a)·3단계 완료** · 4~8단계 미착수**

> **2026-08-15 Codex·Supervisor 제품 설계 보정(이행 완료):** 3단계 전에 먼저
> `docs/architecture/BUSINESS_DATA_BINDING_RUNTIME_DETAILED_DESIGN_2026-08-15.md` §6과
> `docs/handoff/BUSINESS_DATA_BINDING_RUNTIME_TEAM_HANDOFF_2026-08-15.md`의 **BDR-1을
> I-4 2.2 보강으로 구현**한다. `source_intent`·`data_role`·`duplicate_entry_policy`가 계약
> 의미에 들어간 뒤 3단계에서 원문 지문과 물질화 지문을 봉인해야 지문·승인 계약을 두 번
> 바꾸지 않는다. 기존 권위 원천이 있는 데이터를 `AFS_NATIVE` 입력으로 조용히 폴백하지 않는다.

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
[7] I-4 ── 설계 rev.3 ✅  ·  1단계 ✅  ·  2+2.1+2.1b ✅  ·  2.2(BDR-1)+2.2a ✅  ·  3~8 미착수
```

**다음에 할 일: 설계서 §20 의 4단계** — Tech Lead 필수화 · WBS `artifact_kind` ·
ContractReviewGate 를 파이프라인에 연결하고, **계약 → 물질화** 방향의 실제 경로를 만든다.

⚠️ 지금은 `contract_bound=1` 을 만드는 제품 경로가 없어 운영 적용률이 0 이다. 3단계 게이트는
그 상태를 **정확히** 다룬다(계약 없음 = 레거시로 통과, 계약만 있고 물질화 없음 = 차단).
4단계에서는 **fixture 없이** Compiler → 물질화 종단 시험이 필요하다.

순서: `2.1b ✅ → 2.2(BDR-1) ✅ → 2.2a ✅ → 3단계 ✅ → 4단계`.

⚠️ **각 단계는 그 단계까지의 회귀를 갖고 커밋한다.** 여덟 단계를 모아서 한 번에 올리면
어느 단계가 깨졌는지 아무도 못 찾는다.

### 1단계 (2026-08-15)

| 파일 | 무엇 |
|---|---|
| `core/app_runtime_contract.py` | 계약 정본 — 결정표 · JSON Schema · 조건부 규칙 · 의미 지문 |
| `core/host_contract_compiler.py` | 초안 → 계약(비-LLM · **던지지 않는다**) |
| `state_models.py` | `PROJECT_STATE_SCHEMA_VERSION = "5.2.0"` · 지연 마이그레이션 · 계약 필드 6 |
| `tests/test_app_runtime_contract.py` (92) | 결정표 · 지문 · 승인 초기화 · 매니페스트 대조 · **[2.2] 출처·역할·중복입력** |
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
| `tests/test_app_dataset_binding.py` (117) | 승계 · 2차 판정 · 결속 판 · revision 불변 · 유일성 · 원자성 · **테넌트 격리** · **fail-closed** |

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

### 2.1b 보정 (2026-08-15 · 교차검토 94 — P0 2건)

⚠️⚠️ 2.1 은 **새 구조에 새 구멍을 만들었다.** 교차검토가 임시 DB 에서 실제로 재현했고,
내가 같은 방법으로 다시 재현했다:

```text
source_tenant: TENANT_A
rel_tenant_b 가 TENANT_A 데이터셋을 결속: True
2차 판정: ('read','create','update','delete')
```

| # | 무엇이 틀렸나 | 무엇을 했나 |
|---|---|---|
| **P0-1** | DB 유일성은 `(tenant, app_id, dataset_key)` 인데 **승계 조회에 tenant 가 없었다.** `bind_release` 도 데이터셋↔릴리스의 테넌트·앱을 대조하지 않았다 | `adopt_dataset(dataset_key, release_id)` — **app·tenant 는 서버가 릴리스에서 산출**(호출자가 못 넘긴다) · `_assert_bindable` 이 모든 결속에서 정체를 대조 |
| **P0-2** | 결속·판을 못 찾으면 **조용히 마스터 스키마로 후퇴**했다. 「결속 없음」·「판 미지정」·「판 행 없음」이 한 모양이었다 | `_apply_bound_schema` 가 다섯 상태를 나눈다 · 무결성 오류는 **`503`**(`AppDataIntegrityError` 는 `AppDataError` 를 **상속하지 않는다**) |
| P1-1 | `schema_fingerprint` 열은 기본값 `''` 인데 **백필이 없었다** — 같은 판을 다시 결속하면 충돌 | `backfill_version_fingerprints()` · 마이그레이션이 자동 호출 · 폭이 다른 옛 지문도 재계산 · 판독 불가는 `UNREADABLE` 로 **격리** |
| P1-2 | v2 가 선택 필드를 저장하면 **v1 이 기존 필드조차 못 고쳤다** · 조회에 투영 없음 | 아는 필드만 검증 · **미래 필드 보존** · 구버전이 미래 필드를 **쓰면** 거부 · 응답을 결속 판으로 투영 |
| P1-3 | 유일성 인덱스 실패 후에도 계속 동작 | `_assert_ready()` 가 계약 경로를 막고 `readiness()` 가 `NOT_READY` 를 알린다 · 조회가 중복이면 **거부** |
| P1-4 | `recoverable` 은 이름 유일성에만 근거 | **`single_candidate_unverified`** 로 개명 · `bound_releases` 근거를 함께 싣는다 |

★ 함께 닫은 것: **계약 결속에는 스키마 판이 필수**다 — 없이 만들 수 있으면 그 행은 정상
경로로 생기고 나중에 무결성 오류로만 드러난다.

★ **지문 폭**: 증명에 봉인될 값은 축약하지 않는다 — `materialization_fingerprint` ·
`schema_fingerprint` 는 **전체 sha256(64자)**, 표시는 `short_fingerprint()`.
(계약 원문의 `semantic_fingerprint` 는 계약 문서 스키마가 16자로 못박고 있어 **3단계에서
함께** 넓힌다.)

**변이 26/26** (1회차 3건 생존 — 둘은 시험 구멍, 하나는 **중복 분기**라 시험 대신 **삭제**).
전체 스위트 **3,398 passed · 1 skipped**.

### 2.2 / BDR-1 (2026-08-15 · 데이터 출처·역할·중복입력 계약)

★★★ **무엇을 막는가**: 계약이 «이 데이터가 어디서 오는가» 를 말하지 않으면 생성기는
**모든 것을 입력 화면으로 만든다.** 그러면 현업은 ERP 에 이미 있는 값을 한 번 더 손으로
넣고, **두 값이 갈라진 뒤에야** 그 사실이 드러난다.

| 무엇 | 어디 |
|---|---|
| Dataset 에 `data_role`·`source_intent`·`duplicate_entry_policy` **필수** + `enterprise_contract_key`·`required_freshness` 선택 | `core/app_runtime_contract.py` |
| 출처 결정표 — **`AFS_NATIVE` 만 물질화**, 나머지는 `HOST_SERVICE_REQUIRED` | 같음 |
| Zero Duplicate Entry Gate — 계약으로 판정 가능한 ①②⑤ | `duplicate_entry_errors()` |
| 역할 × 출처 닫힌 표 | `ROLE_SOURCE_MATRIX` |
| 물질화본이 의미를 들고 있는다(결속 열 둘 + 검증) | `core/app_data.py` · `app_data_store.py` |
| 의미 다섯 필드를 **계약 지문**에, 역할·출처를 **물질화 지문**에 | `semantic_material()` · `materialization_fingerprint()` |

**닫은 다섯 (교차검토가 지정한 것)**

· `source_intent` · `data_role` · `duplicate_entry_policy` 를 계약 의미에 넣음
· **기업 Actual 의 AFS Native 폴백 차단** — `ROLE_SOURCE_MATRIX[ENTERPRISE_ACTUAL]` 에
  `AFS_NATIVE` 가 **없다**. 회사의 확정 실적을 AFS 화면에서 받겠다는 선언이 곧 이중 입력이다
· **미분류 레거시의 자동 Actual 승격 금지** — `data_role_for()` 는 레거시에 `None` 을
  돌려주고 `is_declared_enterprise_actual()` 은 **명시 선언만** 참으로 본다(2.2a 에서 개명)

⚠️⚠️ **모르는 출처를 `AFS_NATIVE` 로 떨어뜨리지 않는다.** 그 폴백 하나가 곧 이중 입력 앱을
만든다 — 변이 검사 1번이 정확히 그것이다.

★ 차단 문구는 기술 용어를 쓰지 않는다. 「`source_intent=ENTERPRISE_READ` 이므로 `create`
금지」는 현업에게 **다음에 무엇을 할지** 알려 주지 않는다.

**변이 28/28** (1회차 3건 생존).
⚠️ 그중 하나가 중요한 종류였다: **이중 입력 게이트 ①은 컴파일 경로에서 한 번도 실행되지
않는다** — Compiler 가 `ENTERPRISE_READ` 를 「아직 물질화 불가」로 **먼저** 막기 때문이다.
그 규칙은 **저장된 계약**(릴리스 스냅샷·workspace 원문)에서만 의미가 있고, 그쪽 시험이
없어서 규칙을 통째로 지워도 초록이었다. 나머지 둘은 지문 시험이 두 필드를 함께 바꿔
**하나가 지문에서 빠져도 다른 하나가 덮어 주던** 경우다.

**실측**: 운영 백업 사본에 마이그레이션 재실행 — 레거시 결속은 `data_role=''` ·
**미분류는 실적이 아니다** · `readiness=READY` · 원본 불변.

### 2.2a 보정 (2026-08-15 · 교차검토 95)

⚠️⚠️ 2.2 는 **같은 규칙을 두 곳에 적었다.** 계약 계층은 역할×출처 표 **전체**를 봤고
물질화 계층은 **두 가지만** 봤다. 그래서 아래가 계약에서는 막히고 DB 에는 들어갔다(재현):

```text
DERIVED_RESULT   + AFS_NATIVE       계약=막음 · 물질화=통과
NATIVE_SUPPLEMENT + ENTERPRISE_READ 계약=막음 · 물질화=통과
SCENARIO_INPUT   + DERIVED_READ     계약=막음 · 물질화=통과
```

★★★ 그렇게 들어간 상태는 3단계에서 **정상으로 봉인된다** — 봉인은 「그때와 같은가」에
답할 뿐 **「옳은가」에는 답하지 않는다.**

| # | 무엇 |
|---|---|
| 1 | **`core/business_data_semantics.py`** — 상수·판정이 여기 하나뿐이다. 아무것도 import 하지 않아 두 계층이 모두 부를 수 있다(계약 → wire → app_data 의존 때문에 서로는 못 부른다). 계약·물질화 양쪽이 **재수출**만 한다 |
| 2 | **24 조합 전수 회귀** + 표 자체를 **글자로 고정** |
| 3 | `is_official_actual` → **`is_declared_enterprise_actual`** |
| 4 | `required_freshness` 에서 **월·년 금지** |
| 5 | BDR 정본 문서 넷을 **별도 문서 커밋**으로 추적 |

⚠️ ③의 이유: 정본 설계상 **공식 실적**은 선언 + 승인된 Source Binding + 대사 완료 +
Data Owner 인증 + 유효한 CERTIFIED Snapshot 을 **모두** 요구하고, 뒤의 넷은 아직 없다
(BDR-2~3). 선언 하나를 「공식 실적」이라 부르면 **다음 사람은 코드를 읽지 않고 이름을 믿는다.**

⚠️ ④의 이유: `P1M` 은 28~31일, `P1Y` 는 365 또는 366일이다. 그 값으로 최신성을 비교하면
**같은 데이터가 기준일에 따라 신선하기도, 낡기도 한다** — 그리고 그 차이는 월말·윤년에만
드러난다. 한 달이 필요하면 `P30D` 처럼 세어서 적는다.

**변이 31/31.** ⚠️ 그중 하나가 중요했다: 24 조합 전수 시험은 기댓값을 **표 자신에서**
가져오므로 표를 넓히면 양쪽이 함께 넓어져 **초록**이다. 두 계층의 «일치» 는 증명해도
표의 «옳음» 은 증명하지 못한다 — 그래서 표를 글자로 고정하는 시험을 따로 뒀다.

### 3단계 (2026-08-15 · 두 지문 봉인 + 발급 전 일치 게이트)

★★★ **봉인만으로는 부족하다.** 지문은 «발급 뒤의 변경» 을 잡지만, **처음부터 계약과 DB
결속이 다른 상태**에는 아무 말도 하지 않는다 — 그 상태에서 나간 증명은 어긋남을 정상으로
못박고, 이후 모든 대조가 그 어긋남을 기준으로 삼는다.

    봉인은 「그때와 같은가」에 답할 뿐 **「그때가 옳았는가」에는 답하지 않는다.**

| 무엇 | 어디 |
|---|---|
| **발급 전 일치 게이트** — 데이터셋별로 7축 대조 | `core/app_contract_gate.py` |
| 두 지문 봉인(`contract_fingerprint` · `materialization_fingerprint`) | `app_capability_token.issue()` |
| 요청마다 재대조 → 어느 하나라도 다르면 **`410`** | `app_policy.decide()` · `_STALE_APP_REASONS` |
| 계약 지문 폭 확장(16 → **전체 sha256**) · `dataset_key` 를 계약·지문에 | `app_runtime_contract` |
| `tests/test_app_contract_gate.py` (28) | 게이트·봉인·410·재발급 회귀 |

**대조 7축**: 데이터셋 수 · `runtime_name` · `dataset_key` · 스키마 지문 ·
`allowed_actions` · `data_role`/`source_intent` · `contract_bound=1`.

**발급하지 않는 경우**: 계약 데이터셋 미물질화 · 계약에 없는 결속 · 계약 릴리스에 남은
레거시 결속 · 역할·출처·행동·스키마·키 불일치 · **미승인 계약** · 판독 불가 ·
**계약 없이 계약 결속만 있는 상태**(승인보다 물질화가 앞섰다).

★ **데이터셋 0개 앱은 정상이다** — 계약 0개 + 결속 0개면 통과한다.

#### ★★★ 세 표식은 서로 다른 사실이다

| 값 | 뜻 |
|---|---|
| `no-contract` | 계약이 **없다**(레거시 릴리스) |
| `unapproved` | 계약은 있는데 **승인되지 않았다** |
| 64자 sha256 | 승인된 계약의 지문 |

⚠️⚠️ 빈 문자열을 쓰지 않는 이유: 판정이 「양쪽 다 비었으니 같다」로 통과한다. 그러면
**계약이 나중에 생겨도** 이미 도는 앱이 그대로 살아남는다.
⚠️ `unapproved` 를 따로 둔 이유: **승인 상태는 의미 지문에 들어가지 않는다**(문구가 바뀌었다고
재승인을 요구하면 게이트가 습관이 된다). 그래서 승인을 취소해도 지문은 그대로였고, 도는
앱은 아무 일 없이 계속 데이터를 만졌다 — 회귀가 그것을 잡았다.

**변이 28/28** (1회차 5건 생존 — 전부 시험 구멍: 레거시 잔존 결속 · 안정 키 불일치 ·
계약 데이터셋의 레거시 물질화 · 판독 불가 계약 · 안정 키의 지문 포함).

전체 스위트 **3,488 passed · 1 skipped** · `tsc -b` 초록.

⚠️ **2단계까지의 «좁아진 권한 → 403» 이 3단계부터 «410» 이 된다.** 더 강한 보증이다 —
그 앱은 이미 다른 계약 위에서 도는 앱이고, 새 증명을 주면 옛 코드가 새 권한으로 계속 돈다.

★ fixture 가 계약 결속에 의미 기본값을 채워 주므로, **껍데기를 벗기고 제품 함수를 직접
부르는** 시험을 뒀다. ⚠️ 4단계에서는 fixture 없이 **Compiler → 물질화 종단** 시험이 필요하다.

전체 스위트 **3,460 passed · 1 skipped**.

**실측**: 운영 백업(`app_data.db.bak_test_pollution_20260813_114845` — 옛 13열 스키마 ·
결속표 없음)의 **사본**에 마이그레이션을 세 번(2단계·2.1·2.1b) 돌려 확인했다:
데이터셋 보존 · 이름 조회 OK · `dataset_key`·`runtime_name` 백필 · `contract_bound=0` ·
`readiness=READY` · 지문 백필 0건(대상 없음) · 레거시 보고
`single_candidate_unverified=1`(근거 `bound_releases=['rel_ok']`) · **원본 파일 지문 불변**.
⚠️ 원본에는 돌리지 않았다(운영 DB 쓰기 금지).
⚠️ 이 사본에는 **`app_dataset_versions` 행이 0건**이라 지문 백필 경로는 실측으로 확인하지
못했다 — 그 경로는 회귀 넷(`backfill`·축약본 재계산·판독 불가 격리·자동 호출)이 잠근다.

#### ⚠️ 레거시는 아직 승계되지 않는다 — 숫자로 드러낸다

「앱을 개정해도 데이터가 유지된다」는 **신규 계약 데이터셋에만** 참이다. 마이그레이션은
`dataset_key=name` 만 채우고 `app_id` 는 **비워 둔다**. `legacy_identity_report()` 가
다섯으로 나눈다: **`single_candidate_unverified`** · `ambiguous` · `unbindable` ·
`succeeded` · `quarantined`.

⚠️⚠️ 첫 갈래를 `recoverable` 이라고 부르지 않는다 — **`orders` 라는 이름이 하나뿐이라는
사실은 그 앱의 정체를 증명하지 않는다.** 복원하려면 결속된 `release_id` ·
`release.json.project_id` · tenant/entity/scope 일치 · 소유 조직 · 복수 릴리스 후보 여부를
함께 봐야 한다. 「복원 가능」이라고 부르는 순간 다음 사람이 그것을 **자동 복원해도 되는
목록**으로 읽는다.

⚠️⚠️ **이름이 같다는 이유로 자동 연결하지 않는다.** 서로 다른 앱이 `orders` 를 쓰는 것은
흔하고, 잘못 이으면 **남의 앱 레코드가 이 앱에 보인다.** 보고만 하고 고치지 않는다 —
4단계 물질화에서 사람이 판단한다.

#### 3단계는 지문을 **둘로** 봉인한다 (설계 §16-1)

| 지문 | 사실 | 상태 |
|---|---|---|
| `runtime_contract_fingerprint` | 승인된 계약 원문 | 계산 있음(1단계) |
| `materialization_fingerprint` | **실제 DB 결속 상태** | 계산 있음(2.1b · 전체 sha256) · **봉인·`410` 강제는 3단계** |

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
| `tests/test_app_dataset_binding.py` (117) | **[2단계+2.1+2.1b]** 승계 · 2차 판정 · 결속 판 · 불변 · 유일성 · 원자성 · 테넌트 격리 · fail-closed |
| `scripts/canary_host_runtime{,_seed}.py` | 격리 카나리(드라이버가 스스로 판정) |

**변이 검사 누적 242/242**(G1-B 88 + 1단계 27 + 2단계 22 + 2.1 20 + 2.1b 26 +
2.2/2.2a 31 + 3단계 28). 전체 스위트 **3,488 passed · 1 skipped**(2026-08-15) · `tsc -b` 초록.

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
