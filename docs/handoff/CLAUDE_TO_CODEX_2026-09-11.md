# Claude → Codex 인계 (2026-09-11)

- 대상 작업: 2026-09-11 오후 (브랜치 머지 · 디스크 정리 · 시연 환경 구축)
- 브랜치: `integration/g2-vertical-loop-20260821` @ `0ca2a58ad` (당신의 커밋)
- **정본은 당신 쪽이다.** 이 문서는 내가 한 일 중 그 정본에 영향을 주는 것만 모았다.

## ⚠️ 전제 — 우리는 같은 작업 트리를 쓰고 있다

`git worktree list` 가 하나다. `C:\AI Workspace\Ai_Agent_factory_porto-dev` 에서
두 세션이 동시에 작업했다. 나는 당신이 1.1.0 을 만들고 있는 것을 16:31 에 알았고,
그 시점부터 파일 수정을 멈췄다. 아래 2번이 그때까지 벌어진 일이다.

---

## 0. 급한 것 — **판정 엔진 캐시 원문을 지웠다**

사용자의 디스크 정리 지시로 `docs/business-taxonomy/engine/.cache/` 에서
**`*.xml` 347 개 + `*.zip` 626 개 (합 973 개 · 2.81GB)** 를 삭제했다.
`taxonomy.db` 가 갱신된 14:51 **이전**이다.

### 남긴 것 (11 개 · 31MB)

    corpcode.json  corpname.json  dashboard-data.json  financials.json
    instances.json  listed.json  ownership.json  reports.json
    segments.json  unlisted.json  coverage-map.html

### 당신의 P4 커밋(`e4763cb7c`)이 정의한 세 층과 대조

| 층 | 위치 | 지금 상태 |
|---|---|---|
| 정본 | `taxonomy.db` | 42.2MB · 14:51 — **무영향** |
| 보존 | `samples/sources/` | 8 개 · 6.3MB — **무영향** |
| 보존 | `samples/snapshots/` | `2026-09-11`, `2026-09-11-2` — **무영향** |
| 캐시 | `engine/.cache/*.json` | **전부 보존** |

★ 지운 XML·ZIP 은 그 표 어디에도 없다. DART 원문이고
`docs/business-taxonomy/engine/fetch_dart.py` 로 다시 받을 수 있다.
인증키는 `docs/business-taxonomy/engine/.env` 에 있다(지우지 않았다).

⚠️ 다만 **347 개를 다시 받으려면 시간이 든다**(API 일 호출 한도). 원문을 읽는
파이프라인 단계를 다시 돌릴 계획이 있으면 그 전에 재수집이 필요하다.
JSON 만 쓰는 단계라면 그대로 돌아간다.

---

## 1. 1.0.0 을 잠시 되돌렸다가 원복했다 — 16:2x ~ 16:31

사용자가 「봉인 위반 정리」를 지시해서, 당신의 `0ca2a58ad` 가 **이미 같은 일을
해 놓은 것을 모르고** 내가 작업 트리에서 되돌렸다.

    git checkout backup/pre-merge-20260911 -- starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0
    rm app_blueprints/APP-06.json app_blueprints/APP-07.json

그 뒤 사용자 지시로 원복했다.

    git checkout HEAD -- starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.0.0

★ **현재 1.0.0 은 `0ca2a58ad` 와 완전히 일치한다**(`git status` 가 깨끗하다).
당신의 작업 상태는 바뀌지 않았다.

⚠️ 그러나 **그 사이 약 10 분간 1.0.0 이 당신 커밋과 다른 상태였다.** 그때
생성기를 돌리거나 지문을 읽었다면 결과를 한 번 확인해 달라. 특히 내가 되돌린
상태에서는 `app_blueprints/` 가 5 개였다.

내가 **건드리지 않은 것** — 당신 작업물은 전부 그대로다:

    starter_kits/KIT-MFG-NONFERROUS-PROCUREMENT/1.1.0/   (140 개 파일)
    scripts/kit_defs/__init__.py · v1_0_0.py · v1_1_0.py
    scripts/generate_sample_company_starter_kit.py  (KIT_VERSION = "1.1.0")
    scripts/generate_sample_company_excel_templates.py
    scripts/validate_sample_company_starter_kit.py
    tests/test_kit_defs.py · tests/test_starter_package_catalog.py

---

## 2. 머지를 수행했다 — 이미 정본에 들어갔다

`39ed6e6af` — `origin/claude/data-acquisition-orchestrator-20260905` 를
이 브랜치로 합쳤다. 448 파일 · 51,145 줄 추가. 당신이 그 위에 두 커밋을 쌓았으니
이미 아는 내용일 것이다. 기록만 남긴다.

- 충돌은 `.gitignore` 하나였고 **양쪽 추가분을 모두 남겼다.** 판정 엔진 캐시
  제외 규칙(우리 쪽)과 런타임·백업 108MB 제외 규칙(상대 쪽)은 서로 다른 것을 가린다.
- 되돌림용 태그: `backup/pre-merge-20260911` → `18cbe7435`

---

## 3. 런타임 DB 에 시연 데이터를 심었다

**이 설치본은 비어 있었다** — 부서 0 · 사용자 0 · 키트 인스턴스 0. 조직 노드 3 건만
`data/instance.json` 이 부팅 때 심는 상태였다. 사용자 확인 결과 다른 환경에서
인계받은 데이터는 없었다.

### 심은 결과

| 항목 | 수량 |
|---|---|
| 부서 | 13 |
| 사용자 | 24 |
| 키트 인스턴스 | 1 (`ki_5254b3f896894a` · 1.0.0) |
| 원천 결속 · 인증판 · 소유권 결속 | 35 · 35 · 35 |
| 색인 줄 | 37,668 |
| 계산 기준선 | 1 |
| 온톨로지 관계 | 3 (승인) |

### 순서 (이 순서여야 한다 — 4-(3) 참조)

1. `core.org_seed.seed_departments()` — hq 포함 12 개
2. `run_local_demo._ensure_demo_users(org_directory)` — `demo.admin@afs.invalid`, `runner@afs.invalid`
3. `scripts/ensure_admin_accounts.py --apply` — 플랫폼 `admin`
4. `scripts/seed_starter_data.py`
5. `scripts/seed_demo_users.py` — 예시 20 명

### 내가 추가로 만든 것

- 계정 `hikwon@lsmnm.com` (표시명 **권혁일** · hq · 전권·AI·데이터) — 5 번 스크립트의
  기준 계정이다. 사용자가 이름을 지정했다.
- 부서 `t_admin` (**IT관리** · 상위 hq · 범위 없음) — `seed_demo_users.py:87` 이
  참조하는데 `core/org_seed.py` 에 정의가 없어 20 번(전민아·격리 대조군)이
  건너뛰어졌다. ⚠️ **`org_seed` 에 넣을지는 당신이 판단해 달라** — 나는 런타임에만 만들었다.

### 백업

    data/data_preparation.db.bak_reset_20260911_143745   (16.2MB · 초기화 전)

⚠️ 첫 파종이 4-(3) 결함으로 반쯤 실패해서, 인스턴스 관련 9 개 표를 비우고
다시 심었다. `kit_registry_versions` 는 남겼다.

---

## 4. 발견한 결함 3 건 — **취합 대상**

### (1) FastAPI 버전이 명세보다 앞서서 라우터 검사가 오판한다

| | 설치됨 | `requirements.txt` |
|---|---|---|
| fastapi | 0.139.0 | 0.136.3 |
| starlette | 1.3.1 | 1.1.0 |

0.139 는 `app.routes` 에 **`_IncludedRouter` 래퍼**를 담는다 — 개별 `APIRoute` 가
펼쳐지지 않는다. 그래서 `{r.path for r in app.routes}` 로 판정하는 검사가
**모든 라우터를 미등록으로 읽는다.** `AttributeError: '_IncludedRouter' object has
no attribute 'path'` 도 같은 뿌리다.

★ **실제 서비스는 정상이다.** `GET /openapi.json` 에 **464 경로 · 45 접두**가
등록돼 있고 `/api/v1/external/acquisition/catalog` 등이 200 을 준다.

★ **머지와 무관하다.** `backup/pre-merge-20260911` 로 워크트리를 만들어 대조했고
머지 전에도 같은 11 건이 실패했다.

    test_router_registration            4건
    test_access_audit                   1건
    test_ownership_api                  1건
    test_planning_driver_release        1건
    test_planning_scenario_release      1건
    test_host_runtime_wire              1건
    test_ontology_namespace_capabilities 1건
    test_research_recommender           1건

고르는 길은 둘이다 — 명세대로 0.136.3 으로 내리거나, 검사를 새 구조에 맞춘다.
**내려서 맞추는 쪽이 안전해 보인다**(명세가 정본이고, 검사 8 곳을 고치는 것보다 좁다).

### (2) `rematerialize_index()` 가 소유권을 색인에 주입하지 않는다

`scripts/run_local_demo.py:272`. 색인을 다시 세우기는 하는데
**`owner_binding_id` 가 빈 채로 남는다.** `scope_index.plan(snapshot)` 은 스냅샷
행만 받고 `dataset_ownership_bindings` 를 조회하지 않기 때문이다(실측: 결속이 있는
`LOG-02` 의 색인 줄 `owner_binding_id` 가 `''`).

그래서 「결속 없이 인증 → 나중에 결속」 상태가 되면
`OntologyIntegrityError: 이 색인은 소유권 결속이 없던 때에 만들어졌는데 지금은
결속이 있습니다` 에서 **영구히 막힌다.** 재물질화를 3 번 돌려도 풀리지 않았다.

⚠️ 함수 머리말은 「인증 때와 **같은 경로**(`plan` → `write_conn`)를 쓴다」고 적어
두었지만, 인증 경로에 있는 **소유권 주입 단계가 여기에는 없다.**

우회는 초기화 후 재파종뿐이었다(3번 참조). 결속→인증 순서로 돌면 한 번에 통과한다.

### (3) `seed_starter_data.py` 가 빈 설치본을 전제하지 않는다

`SKIP_ORG = True` 로 조직 생성을 건너뛰면서도 소유권 승인자로는
`demo.admin@afs.invalid` 를 계속 쓴다(`run_local_demo.py:208` `USER_ADMIN`).
그 계정을 만드는 `_ensure_demo_users()` 는 `SKIP_ORG` 분기에서 호출되지 않는다.

결과: 조직이 없는 설치본에서 **소유권 결속 0 건**(`OwnershipError` 35 건) → 인증판은
생기고 → 온톨로지가 (2) 로 죽는다. 즉 **복구 불가능한 반쪽 상태**가 된다.

주석의 「이미 부서 13 개·사용자 25 명이 있다」가 암묵적 전제다. 새 설치본에서는
성립하지 않는다.

---

## 5. 환경을 바꿨다 — **재부팅이 남아 있다**

사용자 지시로 디스크를 정리했다. C: 여유 **14.3GB → 22.4GB**.

| 대상 | 확보 |
|---|---|
| 판정 엔진 원문 캐시 (0번) | 2.81GB |
| 도구 캐시 (pip·npm·huggingface·playwright) | 1.74GB |
| 임시 폴더 (Diagnostics·pytest·Outlook) | 1.01GB |
| Downloads 설치 파일 10 개 | 0.95GB |
| Claude 구버전 앱 2 개 | 0.79GB |
| 브라우저 캐시 | 0.76GB |

⚠️ **playwright 브라우저를 지웠다**(0.67GB). `nodes/vision_qa.py`,
`scripts/audit_local_ui.py`, `docs/video/*/capture_*.py` 가 쓴다 —
필요하면 `playwright install`.

### 재부팅하면 13GB 더 회수된다

크래시 덤프를 **전체 → 자동 메모리 덤프**로, 페이지 파일을 **17GB 고정 → 초기 4GB·
최대 8GB**로 바꿨다. 전체 덤프 설정이 페이지 파일을 물리 메모리(16GB) 이상으로
강제하고 있었고, 실제 최대 사용량은 80MB 였다. 되돌리려면 레지스트리
`HKLM\SYSTEM\CurrentControlSet\Control\CrashControl\CrashDumpEnabled` 를 `1` 로.

### frontend 의존성 94 개를 설치했다

`@tailwindcss/browser/dist/index.global.js` 가 없어 `npm run dev` 가
`predev` 단계에서 죽었다. `npm install` 로 해결했다.
★ `package.json` · `package-lock.json` 은 **바뀌지 않았다**(누락 설치였다).

---

## 6. 지금 돌고 있는 것

- 백엔드 `8080` — `.venv/Scripts/python.exe run.py`
- 프런트엔드 `5173` — `frontend` 에서 `npm run dev`

시연 확인용으로 사용자가 로그인까지 마쳤다. 끄려면 각 프로세스를 종료하면 된다.

---

## 7. 남은 판단 — 당신 몫

1. **1.1.0 판본** — 당신이 만들고 있다. 나는 손대지 않았다.
2. **`t_admin`(IT관리) 부서를 `org_seed` 에 넣을지** — 3번 참조.
3. **FastAPI 버전** — 4-(1). 내려서 맞출지, 검사를 고칠지.
4. **`rematerialize_index()` 수정** — 4-(2). 이것이 고쳐지지 않으면 다음에도 같은
   반쪽 상태에서 초기화밖에 답이 없다.
5. **`seed_starter_data.py` 의 조직 전제** — 4-(3). 빈 설치본에서 부트스트랩하는
   경로가 필요하다.
6. **판정 엔진 원문 재수집 시점** — 0번.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
