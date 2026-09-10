# 키트로 앱 생성 — **여정의 빈 칸을 열었다**

작성: Claude Code (백엔드) · 2026-08-23
**상태: 구현·회귀·화면 실측 모두 완료. T3 4,927건 초록 · 운영 데이터 무변경 확인.**

> **한 줄로** — 준비도 보드는 「지금 만들 수 있는 것: 가능」을 그렸는데 **누를 것이
> 없었다.** 통제는 전부 서 있었고 부르는 경로가 없었다.

---

## 1. 무엇이 없었나

12분 여정의 「키트로 앱 생성」 칸은 **한 번도 열린 적이 없다.** 세 가지가 동시에 빠져
있었다:

```
① 청사진 → 런타임 계약 번역기          없음
② 계약을 보관하고 승인하는 곳          없음   ← 가장 큰 구멍
③ 화면에서 부르는 경로                 없음
```

★ 소유권 승인(4.1c-D)에서 이미 지적받은 **「통제는 있는데 부르는 경로가 없다」** 와
같은 결함이다. 같은 모양으로 지었다.

---

## 2. 만든 것

| 파일 | 무엇 |
|---|---|
| `core/kit_app_builder.py` | 청사진 → **정본 스키마를 통과하는** 계약 · 인증판에서 필드 |
| `core/kit_app_contract.py` | 초안 · 승인 · 조회 (원장 사건 + 직무 분리) |
| `core/data_preparation/store.py` | `kit_app_contracts` 표 + **자기승인 금지 트리거 2개** |
| `api/routes/data_preparation_control.py` | 목록 · 초안 · 승인 · 물질화 4경로 |
| `frontend/src/components/KitAppPanel.tsx` | 「계약 초안 만들기 → 승인 → 앱 만들기」 |
| `frontend/src/lib/dataPrepApi.ts` | 위 4경로의 클라이언트 |
| `scripts/run_local_demo.py` | 앱용 28종 심기 + **보충(top-up)** |

흐름:

```
청사진(키트 등록부)
  → contract_from_blueprint()      초안 · status=DRAFT · approval=PENDING
  → kit_app_contract.draft()       저장(개정 관리 · 멱등)
  → kit_app_contract.approve()     **다른 사람** · 원장 사건 · status=APPROVED
  → kit_app_builder.build()        contract_materializer 로 물질화
```

---

## 3. 실측

```
격리 뿌리에서 종단
  35종 인증  →  준비도 READY 35/35  →  APP-01~05 AVAILABLE
  APP-01(10) · APP-02(6) · APP-03(6) · APP-04(6) · APP-05(6)   물질화 5/5

회귀
  test_kit_app_builder.py    26건
  test_kit_app_contract.py   11건
  test_kit_app_api.py        12건
  T2(영향 모듈 14파일)      441건 초록 · 60초

프런트
  npx tsc -b --force  →  통과
  대조군: 일부러 틀린 타입을 넣으니 잡았다(검사가 실제로 이 파일을 본다)

T3(전체)
  4,927 passed · 1 skipped · 654초
  불변식 비교  →  「운영 데이터 영역이 회귀 전과 같습니다」
```

### 3.1 ★★★ 화면 실측 — **제품에서 한 바퀴 돌렸다**

시연 서버(8084, `demo_data/` 뿌리) + 프런트(5179, `--mode verify`).

```
① hikwon(관리자)  준비도 보드   필요 35 중 준비 35 · 막힘 0
                              APP-01~05 전부 「가능」 · 그 아래 새 패널
② hikwon          APP-01 초안   → 「승인 대기 · 개정 1 ·
                                  hikwon 님이 만들었습니다 — 다른 사람이 승인해야」
③ hikwon          자기 승인 시도 → ● 막힘
                    「계약을 만든 사람은 승인할 수 없습니다 —
                     요청자가 승인자 자리에 앉으면 승인은 절차의 이름만 남습니다.」
④ runner(실행자)  승인 시도     → ● 막힘
                    「권한이 없습니다: ['admin.data_access']」
⑤ runner          APP-02 초안   → 「승인 대기 · runner 님이 만들었습니다」
⑥ hikwon          APP-02 승인   → 「승인됨 · hikwon 님이 승인했습니다」 + 「앱 만들기」
⑦ hikwon          앱 만들기     → 200 · release kitapp_ki_…_APP-02 · 데이터셋 6개
                    화면: 「● 만들어졌습니다 — 데이터셋 6개」 · 버튼 「다시 만들기」
```

⚠️ 시연 조직에는 승인자가 `hikwon` 하나뿐이다. 그래서 **hikwon 이 만든 계약은
  시연에서 승인할 수 없다** — 초안은 `runner@afs.invalid` 가 만들어야 고리가 닫힌다.
  통제가 옳게 도는 것이지 결함은 아니지만, 시연 대본에 적어야 한다.

---

## 4. ⚠️ 도중에 잡힌 **내 결함** 넷

### 4.1 계약이 계약이 아니었다

내가 만든 것은 `{app_id, name, revision, status, datasets}` 5칸이었다. 정본 스키마는
**필수 13칸에 `additionalProperties: false`** 다.

**그런데 물질화까지 통과했다** — `contract_materializer` 는 `status` 만 보고
`arc.validate()` 를 부르지 않는다. 정본을 안 보고 내 말로 쓰면 **끝까지 아무도 막지
않는다.**

★ 이제 `contract_from_blueprint()` 가 스스로 `arc.validate()` 를 부른다.

부수적으로 드러난 것들:

```
name          PRC-01 을 그대로 넣었다 → 이름 문법(^[a-z][a-z0-9_]{0,63}$) 위반
              → prc_01 로 접고 계약키는 enterprise_contract_key 에 남긴다
data_role     "reference" 라고 지어냈다 → 닫힌 목록에 없다 → ENTERPRISE_ACTUAL
manifest      네 칸을 손으로 적었다 → version 누락·두 표현 불일치
              → app_manifest.build() 에 위임(상수를 베끼는 것도 지어내기다)
fields        비워 뒀다 → 인증판 schema_json 에서 읽는다
              · 예약 칸(record_id 등) 제외 — 앱이 감사 표시를 위조할 수 있다
              · datetime → date 변환표. 모르는 형은 **막는다**(string 으로 안 뭉갠다)
```

### 4.2 원장 어휘를 새로 만들려 했다

`KIT_APP_CONTRACT_APPROVED` / `kit_app_contract` 를 추가하려다 **닫힌 목록에 막혔다.**
확인해 보니 `APP_CONTRACT_APPROVED` / `app_contract` 가 **같은 질문으로 이미 있었다**
(I-4 4단계 — 「이 계약이 언제 어떤 지문으로 승인됐나」).

★ 닫힌 목록이 실수를 잡아 줬다. 열려 있었으면 조용히 갈렸을 것이고, 승인 건수를 세는
순간 둘로 조각났을 것이다.

⚠️ 겸사겸사 **그 세 유형에 주체 고정이 빠져 있던 것**을 채웠다. 머리말은 「subject_id 는
계약 지문이다」라고 적어 두었는데 코드가 강제하지 않았다 — 주석이 코드를 대신 주장하던
자리다. 이제 `_ONTOLOGY_SUBJECT` 에 `app_contract` 로 못박혀 있다.

### 4.3 ★★★ 내 격리가 **원장 격리 감시자를 뒤집었다**

`tests/conftest.py` 가 `paths.DATA_DIR` 을 tmp 로 돌리자,
`tests/ledger_isolation.live_ledger_path()` 가 그대로 따라갔다. 결과:

```
tmp 경로            → 「운영 원장 자체다」라며 거부
진짜 data/…ledger.db → 「격리 경로다」라며 통과
```

**감시자가 완전히 뒤집혔는데 이름은 그대로였다.** 시험 4건이 잡았다.

★ 운영 뿌리는 **사실**이지 변수가 아니다 — `PROJECT_ROOT/data` 로 고정했다.
캐너리 시험(`test_end_to_end_canary`)에서 같은 날 같은 방식으로 고친 것과 동일한 결함이다.

⚠️ **통제는 자기가 막을 것에 기대면 안 된다.**

### 4.4 슬라이스 편집이 함수를 지웠다

`contract_from_blueprint` 부터 `release_id_for` 까지를 잘라 갈아 끼웠는데, 그 사이에
있던 `fields_from_certified` 가 함께 사라졌다. 시험 10건이 즉시 빨개져 잡혔다.
★ 편집 뒤 **정의 집합을 확인**한다.

---

## 5. 통제 배치

| 지키는 것 | 어디서 |
|---|---|
| 승인 없이 물질화 금지 | `kit_app_builder.build()` + `contract_materializer` (2겹) |
| **만든 사람 ≠ 승인자** | `kit_app_contract.approve()` + **DB 트리거 2개** (2겹) |
| 승인 권한 | `ownership_binding.require_approval_authority()` — **규칙을 복제하지 않는다** |
| 승인 근거 필수 | `approve()` |
| 원장 없는 승인 금지 | 원장 실패 시 상태를 올리지 않음 |
| 한 앱에 승인 하나 | 부분 유일 색인 `uq_kac_approved` |
| 승인된 계약 덮어쓰기 금지 | `ON CONFLICT … WHERE status <> 'APPROVED'` |
| 막힌 산출물 생성 금지 | `build()` + 화면이 버튼을 안 그림 |
| 라우트 권한 | `ROUTE_CAPS` — 초안·물질화는 `project.run`, **승인은 `admin.data_access`** |

⚠️ **DB 트리거는 응용의 정규화를 믿지 않는다** — 공백·대소문자를 직접 처리한다.
층마다 다른 가정에 서야 층이다.

---

## 6. 남은 것

1. **시연 대본**에 「초안은 실행자, 승인은 관리자」를 적어야 한다(위 3.1 주의).
2. **운영 평면 물질화**는 여기서 하지 않는다. 승격(`factory_control._promotion_materializer`)
   의 일이다 — 여기서 하면 승격 절차를 건너뛴다.
3. `app_class` 를 사람이 고르게 두었다. 키트 manifest 가 말해 주는 편이 낫지만,
   **지금은 말하지 않으므로 지어내지 않았다.**
4. 필드 `classification` 은 전부 `INTERNAL` 선언이다 — **평가가 아니라 「아직 평가하지
   않았다」**다. 데이터 카탈로그가 붙여야 한다.
5. 필드 `required` 는 전부 `False` 다 — 인증판이 「필수인가」를 말하지 않는다.
   `True` 로 두면 값이 빈 행이 거부되고, 그것은 **원천에 있는 사실을 우리가 지우는 일**이다.

---

## 7. 부수적으로 고친 것

- `scripts/run_local_demo.py` — cp949 콘솔에서 **기동이 죽었다**(`▸` 인코딩).
  그런데 그 시점에 이미 「시연 뿌리」까지 찍혀 있어 로그만 보면 정상으로 보였다.
  ★ `sys.stdout.reconfigure(encoding="utf-8")` 로 고정.
- `scripts/run_local_demo.py` — 이미 심어진 뿌리에 **보충(top-up)** 을 넣었다.
  종전에는 `--reset` 으로 온톨로지·기준선까지 다 날려야 채울 수 있었다.
  실측: 기존 시연 뿌리에 28종 보충 성공.
- `core/kit_app_builder.py` — 예약 칸 알림을 `print` → `logging` (회귀 출력에 열 줄씩
  쌓여 진짜 실패를 가렸다).
- `main.py` — CORS 개발 허용 포트를 **대역(5173~5199)** 으로 바꿨다.
  ⚠️⚠️ 하나씩 더하다가 **네 번째로 같은 벽**에 부딪혔다(08-04 5174 · 08-06 5175 ·
  08-08 5177 · 08-23 5179). 네 번 다 증상이 「서버에 연결하지 못했습니다」였고, 네 번 다
  자기 변경을 의심하며 시간을 썼다. ★ 열리는 것은 `localhost`·`127.0.0.1` 뿐이고
  운영은 `CORS_ALLOWED_ORIGINS` 로 명시 지정하므로 영향이 없다.
- **[화면 결함]** 「앱 만들기」가 200 을 받아도 화면에 아무 표시가 없었다. 원인 둘:
  ① 성공 알림이 행의 지역 상태라 목록 재조회가 **행을 다시 그리며 지웠다**
  ② 목록 응답에 「만들어졌는가」가 없었다
  ★ ①은 알림을 패널로 올려 고치고, ②는 `release_id`·`built_datasets` 를 실었다.
  ⚠️ `built_datasets` 는 응답의 「만들었다」가 아니라 **결속을 직접 세서** 낸다.
  못 읽으면 `null` 이다 — `0`(안 만들어졌다)과 다른 사실이다.
