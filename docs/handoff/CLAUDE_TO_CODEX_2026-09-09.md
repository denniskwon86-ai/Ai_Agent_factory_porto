# Claude → Codex 인계 (2026-09-09)

- 대상 작업: 2026-09-08 하루치 (수집기 마무리 · 검증 계획 재작성 · F-0/F-7/F-6/F-4)
- 앞 인계: `ACQUISITION_LANE_SPLIT_2026-09-08.md` (레인 분리 — 그것은 그대로 유효하다)
- 브랜치: `claude/data-acquisition-orchestrator-20260905` @ `3562356d9`

---

## 0. ⚠️ 급한 것 — **내가 당신 파일을 커밋했다**

`git add tests/` 로 디렉터리째 담다가 **작업 중이던 시험 11건**이 내 커밋
`c1b54546f` 에 들어갔다. 미안하다.

### 되돌린 것 (신규 6건)

    tests/test_kit_production_revision.py
    tests/test_kit_quantity_audit.py
    tests/test_kit_stock_revision.py
    tests/test_kit_warehouse_revision.py
    tests/test_release_catalog_cleanup.py
    tests/test_release_rollback_api.py

이들은 **import 하는 모듈이 아직 미커밋**이라(`core/data_preparation/kit_production_revision.py`
등) 새로 clone 하면 수집 단계에서 깨진다. `git rm --cached` 로 **추적만 뗐다**(`3562356d9`).
★ **파일은 디스크에 그대로 있다** — 당신의 작업 상태는 바뀌지 않았다.

### 되돌리지 «않은» 것 (이미 추적 중이던 5건의 수정분)

    tests/test_kit_sample_audit.py          tests/test_kit_sample_revision.py
    tests/test_kit_business_view_ui.py      tests/test_management_home_ui_contract.py
    tests/test_release_readiness.py

되돌리면 **당신의 다음 커밋과 충돌한다.** 그래서 남겨 뒀다.
★ 확인했다: 이 5건은 **210건 전부 통과**한다 — 트리가 깨지지는 않았다. 다만 «당신이
  커밋할 준비가 되기 전에» 올라갔다. 필요하면 그대로 이어서 커밋하면 된다.

⚠️ 재발 방지: 앞으로 `git add <디렉터리>` 를 쓰지 않는다. 파일을 명시하고, 커밋 전에
  `git diff --cached --name-only` 로 목록을 눈으로 본다. **하루에 두 번** 저질렀다.

---

## 1. 검증 계획을 «다시 그렸다» — 기존 것에 덧붙이지 않았다

    docs/test_plan/05_northstar_verification_plan_2026-09-08.md   ← 새 상위 계획
    docs/test_plan/F0_BREAKS.md                                   ← 자동 생성 (탐침 산출)
    docs/test_plan/00_master_plan.md · 01_scenario_catalog.md      ← 「위에 상위 계획 있음」 표시

기존 계획(7월)은 제품이 «생성 팩토리»이던 시절의 것이었고, 그 뒤 core 신규 128파일 ·
라우트 15개가 들어왔는데 카탈로그에는 ECM·업무키트·준비도·수집이 **0회** 언급이었다.

★ 거기에 트랙을 덧붙이려다 멈췄다 — Product Bible **§9.1 이 「기능 나열형 플랫폼」을
  함정으로 명시**하기 때문이다. 기능 목록을 시험 목록으로 바꾸는 것은 같은 함정이다.

### 능력 지도 — 539 라우트를 북극성 8단계에 귀속시킨 결과

    1 의도·상담         17   ← 입구
    2 데이터·기준 정의  123
    3 안전한 연계        74
    4 생성               87
    5 운영·승인·공유     76
    6 전사 축적          37
    7 비교              112
    8 경영 의사결정      10   ← 출구

    양 끝 27  vs  가운데 509

시각판: https://claude.ai/code/artifact/07b5732e-a14b-4c13-ab07-6abac8c41cfd

**단위가 「기능」이 아니라 「이음매」다.** 기능은 각자 통과해도 이음매에서 끊긴다.

---

## 2. F-0 실행 결과 — 끊긴 곳 목록

| | 이음매 | 상태 | Codex 관련 |
|---|---|---|---|
| `OK` | F-1 의도 → 데이터 정의 | 청사진 3 → 데이터 요구 42 | — |
| `OK` | F-2 데이터 정의 → 연계 | 결속 35 · 수집 작업 80 | — |
| `MISSING` | **F-3 연계 → 생성** | 수집→생성 라우트 0개 | ⚠️ **합의 필요**(§5) |
| `UNUSED` | **F-4 생성 → 운영·승인** | 경로는 «돈다». 안 썼을 뿐 | ★ **화면이 붙을 자리**(§3) |
| `OK` | F-5 운영 → 축적 | 원장 148 · 발간물 78 | — |
| `MISSING` | **F-6 축적 → 비교** | 승격 경로는 지었다. 탄력도가 남음 | ★ **화면이 붙을 자리**(§4) |
| `OK` | F-7 비교 → 의사결정 | 실제 계정 안건 7 · 실행 지시 2 | — |
| `EMPTY` | ※ 운영 DB 시험 잔여물 | 안건 249 · 수집작업 80 | ⚠️ **화면이 이걸 보여준다**(§6) |

⚠️ **F-7 은 처음에 「막혔다」고 잘못 판정했다.** 안건 256건 중 249건이 `.invalid` 합성
계정의 시험 잔여물이었고, 실제 계정 기준으로는 결정 4 → 실행 지시 2 → 효과 측정 2 로
**완주한다.** 원시 카운트로 판정하면 안 된다.

---

## 3. ★ F-4 — 전달 시험 38건이 «가짜 lookup» 이었다

`test_app_delivery.py` 38건은 전달 논리를 잘 덮지만 **전부 `release_lookup` 을 주입한다** —
「릴리스가 있다고 치면」 그 뒤를 본다. 즉 **실제 `library/` 와 만나는 이음매는 오늘까지
아무도 밟지 않았다.** 전달이 0건인 채로 시험은 계속 초록이었다.

주입 없이 실물로 관통시켰다(`tests/test_app_delivery_real_release.py` 10건, 전부 통과):

    실제 릴리스 읽기 → 전달 생성 → 받는 사람 수신함 → 수락 → 응답 시각 기록
    제3자에게 안 보인다 · 보낸 사람이 대신 수락 못 한다 · 목적 없으면 거부

### 화면이 알아야 할 것

| | 무엇 | 근거 |
|---|---|---|
| U9 | 전달 화면 3단계의 «권한 Manifest» | `GET /api/v1/app-deliveries/preflight?release_id=` ⚠️ `release_id` **필수** |
| U10 | 받은 앱 / 보낸 앱 | `/inbox` · `/outbox` — 각각 **본인 것만** 돌려준다 |
| U11 | 수락·거절·회수 | 당사자가 아니면 **404**(403 이 아니다 — 존재가 새면 안 된다) |

★ **목적(`purpose`)은 필수다.** 목적 없는 앱을 받은 사람은 수락 여부를 판단할 근거가 없다 —
  화면이 «선택 입력»으로 만들면 안 된다.
★ 만료는 1~N일이다. 만료 없는 대기 요청은 목록을 채우고 결국 아무도 읽지 않는다.

---

## 4. ★ F-6 — 승격 라우트를 신설했다

Q2「환율·원자재가 바뀌면 어느 계정에 영향?」이 막힌 기계적 원인은 **두 저장소가 만나지
않는 것**이었다:

    수집 오케스트레이터  →  data_acquisition_rows   (격리 적재본)
    계획이 읽는 것       →  external_observations
                             ↑ 둘을 잇는 코드가 «없었다»

    신설  POST /api/v1/external/acquisition/jobs/{job_id}/promote   (ADMIN_DATA_ACCESS)
    신설  core/external_intelligence/observation_promotion.py

### 화면이 알아야 할 것

| | 무엇 | 비고 |
|---|---|---|
| U12 | 「관측값으로 올리기」 버튼 | ⚠️ **적용(apply)과 다른 단계다.** 적용은 격리 적재, 승격은 계획이 읽는 자리로 |
| U13 | 응답의 `next_actions[]` 를 그대로 보여줄 것 | 「원천이 아직 승인되지 않았습니다」 같은 «다음 할 일»이 들어 있다 |
| U14 | `rejected[]` 의 사유별 묶음 | 닫힌 어휘다 — 화면이 문구를 새로 만들지 말 것 |

★★★ **승인 전에는 «전부 거부»가 정상이다.** 화면이 그것을 「오류」로 그리면 안 된다 —
  §12.4「승인된 원천만 등록하고 수집한다」가 작동하는 모습이다.
★ `register_missing` 은 **어휘를 만든다.** 기본이 `false` 이고, 화면이 함부로 켜면 같은
  뜻의 지표가 둘 생겨 그때부터 집계가 조각난다.

⚠️ **Q2 가 실제로 열리려면 «탄력도»가 필요하다** — 환율 1% 가 어느 계정을 몇 % 움직이는가.
  그것은 도메인 결정이고 **지어내면 안 된다**(§9.4 가 경고한 함정이다). 코드는 여기까지다.

---

## 5. F-3 — 합의가 필요하다

    수집 적재본(`data_acquisition_rows`)  ↔  생성물 데이터 평면(`app_datasets`)
    잇는 라우트가 «한 개도 없다»

**이을지 «말지»부터 정해야 한다.** 이으면 생성 앱이 외부 수집 데이터를 직접 읽게 되고,
그러면 앱 데이터 평면의 격리 전제가 바뀐다. 내 판단으로 정할 사안이 아니다.

---

## 6. ⚠️ 운영 DB 의 시험 잔여물 — 화면이 이걸 보여준다

사용자가 **그대로 두기로** 결정했다. 그러면 화면이 다음을 알아야 한다:

    decision_cases         256건 중 **249건**이 `owner@afs.invalid`·`runner@afs.invalid`
    publications            78건 중 **73건**이 `owner@afs.invalid`
    data_acquisition_jobs   80건 전부 `t_member_a@test.invalid` (전부 DRAFT)

★ `/decisions/queue` 는 「본인이 참여자인 것만」 주므로 **실제 사용자에게는 안 보인다.**
  그러나 **집계·통계·관리자 화면은 본다.** 건수를 그대로 표시하면 사람이 속는다 —
  내 첫 판정이 정확히 그렇게 속았다.

⚠️ 화면에서 건수를 셀 때 **`.invalid` 도메인을 거를 것.** 이 저장소는 합성 행위자에
  그 도메인을 쓴다(원장 규약).

---

## 7. 내가 고친 «공유 파일» — 알아야 할 변경

| 파일 | 무엇 | 왜 |
|---|---|---|
| `tests/conftest.py` | 격리 블록 추가 — `acquisition_store`·`raw_store` | ★★★ **시험이 운영 DB 에 쓰고 있었다.** 싱글턴이 운영 `data/external_intelligence.db` 를 직접 열어 09-06~08 사이 수집 작업 80건이 쌓였다. 고쳤고, 「실행 전 80 → 시험 통과 → 실행 후 80」으로 **증명했다** |
| `tests/test_route_authority_table.py` | `GUARDED_MODULES` 에 `api.routes.research_control` 추가 | 안 넣으면 권한표 항목이 «유령»으로 잡힌다(실제로 걸렸다) |
| `tests/test_ecos_canary.py` | 낡은 단언 수정 | `assert chosen == ()` 이 「모든 원천이 키를 요구한다」를 전제했는데 World Bank 는 키가 없다 |

---

## 8. 앞 인계의 요청 두 개 — **여전히 미해결**

**①** `.agents/TEAM_BOARD.md` 의 `WORKTREE-CLEANUP-20260908` 이 「푸시 = 없음」인데
   `aecdf1d85`·`b2e1b5f17` 은 원격에 있다. `git log origin/<브랜치>` 에서 조상 여부로
   확인된다. **보드만 읽는 사람이 속는다.**

**②** `docs/handoff/EXTERNAL_ACQUISITION_UI_REFRESH_PLAN_2026-09-08.md` 가 **아직 미추적**이다.
   내 레인 지적을 담은 근거 문서인데 커밋이 안 돼 있다. 남의 초안을 내가 대신 커밋하지
   않았다 — 커밋해 주기 바란다.

---

## 9. 사용자 결정 기록 (내가 임의로 정하지 않은 것들)

    웹검색·RSS 자동 수집       하지 않는다 — 「나오던 게 안 나오면 사용자는 우리 버그로 읽는다」
    연구자료 원천              AI 가 «추천»만 하고 받아오는 것은 사람이 한다(카탈로그 27곳)
    업로드 등록 경로(KNW-01)   이번 범위 밖 — 추천만 한다. **화면이 「등록하기」를 만들면 안 된다**
    시험 잔여물                그대로 둔다(§6)
    F-3                        합의 후 결정

---

## 10. 지금 상태

    브랜치   claude/data-acquisition-orchestrator-20260905 @ 3562356d9 (원격과 동일)
    Provider  5종 — OpenDART · ECOS · KOSIS · 공공데이터포털 · World Bank
    추천기    연구자료 원천 27곳 (수집하지 않는다)
    승격      data_acquisition_rows → external_observations (신설)
    수집 6,737건 · 전체 시험 트리 정상
    T3       6,445(09-08) — ⚠️ 그 뒤 커밋 여러 개는 T3 가 보지 않았다

⚠️ **통합 초록으로 보고하지 않는다.**
