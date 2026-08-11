# 생성 앱 데이터 평면 설계 (트랙 I)

> 작성일: 2026-08-08 · 작성자: Claude Code · 결정자: Supervisor(2026-08-08 «(B) 먼저, (A)는 사례 쌓고 재판정»)
> 선행 문서: `docs/design_backbone_system_platform.md` §2-3·§4-③·§9-2 · `core/app_manifest.py`(CL-0 계약)
> 관련 진척: `PROGRESS.md` 트랙 I

---

## 1. 이 문서가 나온 질문

> **«저장도 되지 않는 프로그램을 관통 테스트하는 게 무슨 의미가 있는가»** (Supervisor, 2026-08-08)

정당한 지적이고, 이 문서는 그 답이다. 관통 테스트를 미루고 **저장부터 만든다.**

### 1-1. 무엇이 없었나 (실측)

| 항목 | 실태 | 근거 |
|---|---|---|
| 프론트 실행 | iframe `srcdoc` 안에서 렌더 | `frontend/src/components/PreviewPanel.tsx:651` |
| **백엔드 실행** | **되지 않는다** — import 부팅 여부만 보고 버린다 | `tools/backend_smoke_run.py` |
| **앱의 데이터 저장소** | **없다** | 샌드박스 토큰은 명시적으로 «읽기 전용·가상 문맥 전용» (`api/routes/sandbox_control.py:1`) |
| 라이브러리 게시 | 산출물 **요약과 코드 텍스트** 스냅샷 | `api/routes/factory_control.py:1402` |

⚠️ 그래서 지금 만들 수 있는 앱의 실체는 **«브라우저 탭 안에서 도는, 저장이 안 되는 프론트엔드»** 다.
`docs/business_value_assessment.md` §6-A 가 대표 예시로 든 **구매 요청 관리·설비 점검 체크리스트·
원료 입고 대장 셋 다 저장이 필요하다** — 즉 팔겠다고 적어 둔 것을 하나도 만들 수 없었다.

---

## 2. 왜 (B) 인가 — 이것은 새 방향이 아니라 **이미 한 약속의 이행**이다

★★★ 이 절이 이 문서에서 가장 중요하다.

`core/app_manifest.py`(CL-0)는 생성 앱의 계약을 **이미 고정값으로 못 박아 두었다**:

```
auth_mode             = PLATFORM_INHERITED    인증은 호스트에서 상속
enterprise_scope_mode = HOST_CONTEXT          회사 문맥도 호스트가 준다
audit_mode            = PLATFORM_LEDGER       감사는 플랫폼 원장에 남는다
forbidden_features    = local_login · local_user_store · jwt_issuer
```

그리고 `standalone_auth=True` 와 `host_auth_required=False` 를 **경고가 아니라 거부**한다
(`core/app_manifest.py:113-131`). 이유도 파일에 적혀 있다 — 앱이 자기 인증을 가지면
«회사 권한 체계 밖에서 사용자를 인증»하게 되고 조직 범위·등급·감사가 전부 우회된다.

| 선택지 | CL-0 계약과의 관계 |
|---|---|
| **(A) 앱 런타임(G1)** — 생성된 백엔드를 실제로 기동 | 앱이 **자기 백엔드를 갖는** 길이다. 매니페스트가 금지한 방향과 같은 쪽을 향한다 |
| **(B) 플랫폼 데이터 평면** — 앱은 프론트, 데이터는 플랫폼 | **계약이 처음부터 전제한 구조**다 |

★ 즉 없는 것은 «방향»이 아니라 **그 계약을 이행할 데이터 평면 하나**였다. 지금 매니페스트는
**지킬 수단이 없는 약속**으로 남아 있다. 이 문서는 그 수단을 만든다.

⚠️ (A)를 닫지 않는다. `docs/design_backbone_system_platform.md` §9-2 가 G1 을 «사실상 미니
PaaS» 로 재평가했고 `AI_HANDOFF.md:251` 의 «인프라 과투자» 기각과 충돌한다고 적었다. (B)로
실물 앱이 쌓인 뒤 «서버가 꼭 필요하다» 는 **사례를 근거로** 재판정한다.

---

## 3. 무엇을 만드는가 (범위)

| # | 항목 | 산출 |
|---|---|---|
| I-1 | 저장소 코어 | `core/app_data_store.py` — 데이터셋·레코드·스키마 |
| I-2 | 데이터 API | `api/routes/app_data_control.py` — 권한·범위·감사 강제 |
| I-3 | iframe 브리지 | 앱은 자격증명을 보지 않는다(§7) |
| I-4 | 생성기 연동 | 백엔드 생성 대신 이 API 를 쓰도록 |
| I-5 | 카탈로그 등재 | 게시 시 데이터셋 스키마를 `data_catalog` 에 |
| I-6 | 검증 UI | 사람이 눈으로 데이터를 확인 |
| I-7 | 회귀 테스트 | 권한 우회·범위 이탈·감사 누락 |

### 범위 밖 (지금 하지 않는 것 — 숨기지 않고 적는다)

- **생성된 백엔드 코드의 실행** — 산출물로 남기되 돌리지 않는다. 이것이 (B)의 대가다.
- **여러 앱이 같은 테이블에 쓰는 공용 저장소**(§4-③) — 그것은 G3(표준 사전)가 하드 선행이다.
  여기서는 **앱마다 자기 데이터셋**을 갖는다. 표준 편입은 I-5 카탈로그 등재로 잇는다.
- **워크플로 엔진**(④) · **작업 지시 인박스**(②) — 별개 트랙.
- 무거운 서버 로직(배치·스케줄·외부 연동) — 사례가 쌓이면 (A) 재판정 근거가 된다.

---

## 4. 데이터 모델

저장소는 `data/app_data.db` 하나. 기존 관례를 따른다 — `data_path()` 로 절대경로,
`CREATE TABLE IF NOT EXISTS`, **import 시점에 스키마를 만들지 않는다**
(`core/collaboration_store.py:120-124` 의 이유: 테스트가 경로를 바꿔치기할 틈이 필요하다).

```
app_datasets
  dataset_id      TEXT PK
  release_id      TEXT NOT NULL     -- 어느 앱의 것인가
  name            TEXT NOT NULL     -- 앱 안에서 부르는 이름 (예: "purchase_request")
  schema_json     TEXT NOT NULL     -- 필드 선언 (§4-1)
  owner_dept_id   TEXT              -- 게시 당시 소유 부서 (릴리스에서 고정)
  scope_node_id   TEXT              -- 조직 범위
  app_class       TEXT              -- personal | departmental | enterprise (매니페스트에서)
  tenant_id       TEXT NOT NULL DEFAULT 'tenant_default'
  created_by / created_at / updated_at
  UNIQUE(release_id, name)

app_records
  record_id       TEXT PK
  dataset_id      TEXT NOT NULL → app_datasets
  payload_json    TEXT NOT NULL
  created_by      TEXT NOT NULL     -- 식별 없는 쓰기는 존재할 수 없다(트랙 H 규칙)
  created_at / updated_at
  updated_by      TEXT
  deleted_at      TEXT DEFAULT ''   -- ★ 논리 삭제
  deleted_by      TEXT DEFAULT ''
```

### 4-1. 왜 `payload_json` 인가 (스키마를 컬럼으로 펴지 않는 이유)

앱마다 필드가 다르고 **생성 시점에 결정된다.** 컬럼으로 펴려면 `ALTER TABLE` 을 런타임에
실행해야 하고, 그러면 LLM 이 쓴 선언이 곧 DDL 이 된다 — 통제할 수 없다.

대신 `schema_json` 으로 **필드 선언을 검증**한다. 선언에 없는 키는 저장 시 거부한다.
⚠️ 「선언에 없으면 그냥 넣는다」로 두면 스키마가 의미를 잃고, I-5 카탈로그 등재가 거짓이 된다.

### 4-2. ★ 삭제는 논리 삭제다

물리 삭제를 허용하면 **감사 원장이 가리키는 대상이 사라진다.** 원장에 «삭제했다» 가 남았는데
무엇을 삭제했는지 확인할 수 없으면 그 기록은 감사 증적이 아니다.

---

## 5. 권한·범위 판정 — 새로 만들지 않는다

★ 이 트랙의 존재 이유가 여기에 있다. **이미 있는 판정을 그대로 태운다.**

| 관심사 | 재사용 대상 |
|---|---|
| 주체 식별 | `api/deps.py:99 current_principal` |
| 범위 | `Principal.scope` — `readable_dept_ids` · `unrestricted` |
| 프로젝트/릴리스 쓰기 자격 | `api/deps.py:531 assert_project_writable` 계열 |
| 감사 | `core/decision_ledger.py:200 append` |

### 5-1. 판정 규칙

```
읽기: 데이터셋의 owner_dept_id 가 내 readable_dept_ids 안에 있는가
      (unrestricted 는 통과 — 조직 미도입·플랫폼 관리자 하위호환 계약)
쓰기: 읽기 조건 + 그 릴리스를 내 앱으로 수락했거나(app_delivery) 소유 부서 구성원인가
```

⚠️ **`app_class` 로 판정을 갈라야 한다.** `personal` 앱의 데이터는 만든 사람만 본다 —
부서 범위로 열면 개인 편의 도구가 부서 공유물이 된다(설계서 §2-4 모순 2와 같은 갈래).

### 5-2. ★★ 식별 없는 쓰기는 거부한다 (트랙 H 규칙 계승)

`p.user_id` 가 비어 있으면 **쓰기는 401** 이다. 트랙 H가 「식별만으로 열리는 쓰기」 65건을
봉합했는데, 여기서 «식별조차 없는 쓰기»를 새로 만들면 그 작업을 무효로 만든다.

⚠️ 해석 실패는 **거부**다(fail-closed). 「범위를 못 읽었으니 통과」로 두면 조회 장애가 곧
전면 개방이 된다(`sandbox_control.py:70` 와 같은 판정).

---

## 6. 감사

모든 **쓰기**(생성·수정·삭제)를 `decision_ledger` 에 남긴다.

신설이 필요한 어휘:
- `SUBJECT_TYPES` 에 `"app_dataset"` 추가 — 릴리스나 프로젝트로 뭉개면 «이 앱의 데이터에
  무슨 일이 있었나» 를 «이 릴리스가 어떻게 됐나» 와 구분할 수 없다(CL-1~3 의 판단과 같다).
- `EVENT_TYPES` 에 `APP_DATASET_CREATED` · `APP_DATA_WRITTEN` · `APP_DATA_DELETED`.

⚠️ **레코드 1건마다 원장 1건은 쓰지 않는다.** 업무 앱은 레코드를 대량으로 만든다 —
2,457건짜리 원장에 하루 수천 건이 들어오면 **결정 이력이 데이터 로그에 파묻힌다.**
→ 데이터셋 **생성·스키마 변경·삭제**는 원장에, **레코드 단위 변경**은 `app_records` 자체의
`created_by`/`updated_by`/`deleted_by` 로 남긴다. 이 구분을 I-7 테스트로 고정한다.

---

## 7. ★★★ iframe 브리지 — 여기가 가장 위험하다

현재 프리뷰 iframe 은 `sandbox="allow-scripts allow-same-origin"` 이다
(`PreviewPanel.tsx:651`). `AS_IS_화면기능정의서_리버스엔지니어링_2026-07-28.md:254` 가 이미
**«완전한 격리 보안 경계가 아니다»** 라고 경고해 두었다.

⚠️⚠️ 여기에 데이터 API 를 순진하게 붙이면 — **LLM 이 쓴 앱 코드가 부모 창의 자격증명에
접근**할 수 있다. 그러면 트랙 B·G·H 로 3주간 봉합한 것이 **앱 하나로 뚫린다.**

### 규칙

```
iframe 안의 앱  ──postMessage(요청)──▶  부모(PreviewPanel)
                                          │ 자기 Principal 로 fetch
                                          ▼
                                       /api/v1/appdata/...
iframe 안의 앱  ◀──postMessage(결과)──  부모
```

1. **앱은 `fetch` 를 직접 호출하지 않는다.** 주입되는 것은 `window.afs.data.*` 뿐이고,
   그 구현은 `postMessage` 로 부모에게 요청을 보내는 얇은 껍데기다.
2. **앱은 토큰·헤더·사용자 식별자를 본 적이 없다.** 부모가 자기 것으로 호출한다.
3. **부모는 출처를 검증한다** — 이미 있는 신뢰 소스 검증(`PreviewPanel.tsx:531-534`)을 그대로
   쓴다. 우리 iframe/팝업이 보낸 메시지만 처리한다.
4. **부모가 `release_id` 를 붙인다.** 앱이 자기 `release_id` 를 말하게 하면 **남의 앱 데이터를
   요청할 수 있다.** 앱은 데이터셋 «이름» 만 말하고, 어느 릴리스인지는 부모가 안다.

★ 4번이 핵심이다. 이것 하나로 «앱이 남의 데이터를 읽는» 경로가 원천 차단된다.

---

## 8. 생성기 연동 (I-4)

생성 프롬프트가 지금은 FastAPI 백엔드를 만들게 한다. 이것을 바꾼다:

- 데이터가 필요한 앱은 **`window.afs.data` 를 쓰는 프론트 코드**를 만든다.
- 필요한 데이터셋을 **매니페스트에 선언**한다(이미 `required_data_scopes` 자리가 있다).
- 백엔드 코드 생성은 **유지하되 «설계 산출물»로 표시**한다 — 실행되지 않는다는 것을 화면에
  명시한다.

⚠️ **여기서 «조용한 거짓말» 이 나기 쉽다.** 백엔드 코드가 산출물에 그대로 있는데 실행되지
않으면, 그것을 본 사람은 «백엔드가 있다» 고 읽는다. 트랙 F 에서 7개 화면이 같은 유형으로
걸렸다. → 산출물 화면에 **«이 코드는 실행되지 않습니다»** 를 표시한다.

---

## 9. 미해결 · 결정 필요

| # | 사안 | 선택지 |
|---|---|---|
| 1 | `personal` 앱 데이터의 소유 | ⓐ 만든 사람만 ⓑ 만든 사람 + 부서장 |
| 2 | 릴리스가 폐기되면 데이터는 | ⓐ 유지(감사) ⓑ 함께 폐기 — **권장 ⓐ** |
| 3 | 레코드 수 상한 | 설계서 §11-5 «목표 규모 확정» 이 여전히 미결이다 |

---

## 10. 이 설계가 틀릴 수 있는 지점

- **`payload_json` 방식은 조회 성능이 나쁘다.** 레코드가 수만 건을 넘고 필드 검색이 필요해지면
  인덱스를 만들 수 없다. → 규모(§9-3)가 정해지면 재검토. 지금은 «저장이 아예 안 되는» 상태를
  벗어나는 것이 우선이다.
- **(A)가 결국 필요할 수 있다.** 이 설계는 그것을 부정하지 않고 **판단을 사례 이후로 미룬다.**
