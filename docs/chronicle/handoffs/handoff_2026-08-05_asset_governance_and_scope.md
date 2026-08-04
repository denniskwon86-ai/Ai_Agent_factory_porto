# 인수인계 — 자산 거버넌스 P1 완주 · 경영계획 통제 · 조직 범위 정본 이행 착수

- **작성**: Claude Code / 2026-08-05 KST
- **브랜치**: `dev` (원격 `origin/dev` 보다 앞서 있었고 이 기록과 함께 푸시)
- **직전 인수인계**: [`handoff_2026-08-04_uiux_migration_3to9.md`](handoff_2026-08-04_uiux_migration_3to9.md)
  — 그 문서의 §4.1(먼저 막을 것)을 실행했고 **§4.2 화면 이관은 미착수**다.

---

## 0. 30초 요약 — 이것만 알면 이어받을 수 있다

1. **D-017 §9 P1 이 5/5 로 끝났다.** 에이전트·워크플로우·스킬이 조직별 버전 자산으로 관리되고,
   기존 `/agents`·`/templates` 가 그것을 **응답 형태를 바꾸지 않고** 함께 보여준다.
2. **경영계획 API 가 익명에게 열려 있었다.** 무방비 라우트 14개를 봉합했다. 인수인계 기록은
   «0건이라 실제 유출 없음» 이라고 적었지만 **하루 만에 데이터가 들어와 실제 유출 상태**였다.
3. **조직 범위 정본이 `node_id` 로 확정됐다**(D-018, 사용자 결정). 10단계 이행 중 **1·9 완료**.
4. **내가 두 번 사고를 냈다** — 통제 확인 목적으로 쓰기 API 를 불러 운영 DB 에 데이터를 만들었다.
   복구했고 규칙을 갱신했다. **§5 를 반드시 읽을 것.**
5. **화면 이관 3~9/10 은 `dev` 에 없다** — 다른 브랜치에 있다(§7). 이것을 모르면 «화면이 왜
   예전 모습인가» 로 시간을 버린다.

---

## 1. 진척 현황

### D-017 §9 — 에이전트 거버넌스 (근거: `docs/design_agent_governance_scope_permissions_2026-08-04.md` §9)

```
전체   ██████████░░░░░░░░░░  11/23  (48%)

P0 즉시 보안 봉합    ████████████████████  6/6   완료
P1 범위형 자산 저장소 ████████████████████  5/5   완료 ★ 이번 세션
P2 생성기 UI 통합    ░░░░░░░░░░░░░░░░░░░░  0/4   ⚠️ 화면 작업 — Codex 영역과 겹침
P3 런타임 강제       ░░░░░░░░░░░░░░░░░░░░  0/4
P4 품질·비용·운영    ░░░░░░░░░░░░░░░░░░░░  0/4
```

### D-018 — 조직 범위 정본 이행 (10단계, 사용자 확정)

```
█████░░░░░░░░░░░░░░░  2/10

 1 ECM·Master DB 경로 절대화        ████ 완료 ★ 이번 세션
 2 resolve_scope_ref 계약 통합       ░░░░  ← 다음
 3 API 입력 3형태 허용(과도기)       ░░░░
 4 API 경계에서 node_id 정규화        ░░░░
 5 기존 코드값 백필                  ░░░░
 6 신규 쓰기 node_id 강제             ░░░░
 7 코드 별칭·변경이력·유일성 제약     ░░░░
 8 미해석·복수후보 Fail-closed        ░░░░  (부분 — 기존 동작 유지)
 9 readable_scope_nodes 우회 유지     ████ 완료(제거 금지)
10 백업·시드에서 node_id 보존         ░░░░
```

### 인수인계 §4 지시

```
§4.1 Planning 통제  ████████████████████  완료 ★ (예상 밖 결함 1건 포함)
§4.2 화면 이관 8개  ░░░░░░░░░░░░░░░░░░░░  0/8   미착수
```

### 검증 기준선

| 시점 | 통과 | 비고 |
|---|---:|---|
| 세션 시작(`21950422b`) | 1,846 | 이전 세션 |
| P1-2 후 | 1,870 | +25 |
| P1-4 후 | 1,918 | +48 |
| P1-5 후 | 1,937 | +19 |
| Planning 통제 후 | **1,970** | +33 · 1 skipped · 실패 0 · exit 0 |

---

## 2. 이번 세션 커밋 (오래된 것 → 최신)

| 커밋 | 무엇 |
|---|---|
| `c4056a272` | **P1-2** 파일 자산 SYSTEM·LEGACY 어댑터 |
| `dcd275592` | **P1-4** 조직별 목록·복사·승인·폐기 API |
| `1eb238d08` | **P1-5** 기존 `/agents`·`/templates` 어댑터 전환 |
| `e61236956` | **경영계획 API 통제** — 무방비 14개 + 범위 판정 수정 |
| `59d141ee0` | (Codex) D-018 정본 결정 기록 |
| `4d83c6d87` | **D-018 후속 1** 데이터 경로 절대화 + 경영계획 DB 격리 |

상세 배경은 각 커밋 메시지와 `.agents/TEAM_BOARD.md` 의
`[SEC-P1-45]`·`[SEC-P1-46]`·`[SEC-P1-48]`·`[SEC-PLAN-50]`·`[SEC-SCOPE-51]` 에 있다.

---

## 3. 지금 무엇이 동작하는가 — 새 구조 지도

### 3.1 자산은 두 곳에 있고 어댑터가 합친다

```
파일 자산(54개)                       DB 자산(조직별·버전형)
  agents_registry.json  15 에이전트      agent_assets
  templates/*.json       8 워크플로우     agent_asset_versions
  skills/*.md           31 스킬          └ 버전을 쌓는다(덮어쓰지 않는다)
        │                                        │
        └────────► core/agent_asset_adapter ◄────┘
                          │
        ┌─────────────────┼──────────────────────┐
   list_all()      resolve_workflow()      asset_visible()
   (목록 병합)      (런타임 단일 입구)       (가시성 단일 판정)
        │                 │                      │
   ┌────┴────┐      agent_graph            두 API 가 공유
   신 API    구 API   get_runtime_app()
```

- **신 API**: `/api/v1/agent-governance/…` (P1-4) — 11개 엔드포인트
- **구 API**: `/api/v1/factory/agents`·`/templates` (P1-5) — **응답 키를 하나도 없애지 않았다.**
  `source`·`status`·`owner_scope_id`·`needs_migration` 만 **추가**했다(기존 화면은 무시).

### 3.2 판정은 몇 개의 함수에만 있다 (라우트에 흩지 않았다)

| 판정 | 함수 | 파일 |
|---|---|---|
| 자산 가시성 | `asset_visible()` | `core/agent_asset_adapter.py` |
| 자산 읽기·쓰기·승인·생성 | `_assert_may_read/_write/_publish/_create` | `api/routes/agent_governance.py` |
| 조직 범위 승인 자격 | `can_manage_scope()` · `can_publish_enterprise()` | `core/admin_capability.py` |
| 계획 식별·범위·숨김·행검증 | `_assert_identified` · `_only_visible_orgs` · `_hidden` · `_assert_rows_in_scope` | `api/routes/planning_control.py` |
| 주체 조직 범위 | `_actor_scopes()` | `core/scope_guard.py` |
| 뷰어 가시 범위 | `viewer_visible_scopes()` | `api/deps.py` |

⚠️ **`_actor_scopes` 와 `viewer_visible_scopes` 는 같은 값을 돌려줘야 한다.**
`tests/test_planning_control_gate.py::test_scope_sources_agree` 가 그것을 잠근다. 갈라지면
「목록에는 있는데 상세는 404」 같은 어긋남이 생긴다.

---

## 4. ★★★ 다음 사람이 바로 할 일 (우선순위)

### 4.1 D-018 후속 2~4 — 해석 계약 통합 → 경계 정규화 (권고 1순위)

사용자가 확정한 순서의 다음 조각이다. 구체적으로:

1. **`resolve_scope_ref(ref, tenant_id, entity_mode)` 로 시그니처 통일.**
   지금은 `resolve_scope_ref(ref)` 하나뿐이고 tenant·mode 문맥이 없다. 가상회사 변형 코드
   (`V8039_MNM_BATTERY` 등)가 실제로 있으므로 **같은 코드가 모드별로 다른 노드일 수 있다.**
   현재 코드는 전역에서 코드를 찾는다 — D-018 이행규칙 ④가 금지하는 형태다.
2. **API 경계에서 즉시 `node_id` 로 정규화.** 지금은 라우트가 받은 값을 그대로 저장한다.
3. 응답에 `scope_node_id` + 표시용 `scope_code`·`scope_name` 함께(D-018 이행규칙 ③).

착수 전 읽을 것: `.agents/DECISIONS.md` `[D-018]` 전문 · `[SEC-SCOPE-51]`.

⚠️ **금지**: `find_node_by_code(... LIMIT 1)` 로 후보를 임의 선택하는 것. 미해석·복수 후보는
fail-closed 다. 그리고 **`readable_scope_nodes` 우선 우회를 제거하지 말 것** — 백필 완료 전까지
그것이 유일하게 동작하는 경로다.

### 4.2 매핑되지 않은 부서 (작지만 실제 사용자가 막힌다)

실측: `procurement` 부서는 어느 ECM 노드에도 매핑되지 않았다(`organization_nodes.dept_id` 가
16건 중 **3건만** 채워져 있다 — `hq`·`production_copper`·`production_battery`).
그래서 `resolve_scope_ref("procurement")` → `''` 이고, 그 부서 소속인 `hikwon_7@lsmnm.com` 은
부서 경로로 범위를 얻지 못한다(지금은 `readable_scope_nodes` 우회로 동작한다).

→ **데이터 문제인지 설계 문제인지 확인이 필요하다.** 부서 전체를 노드에 매핑할 것인가, 아니면
`readable_scope_nodes` 를 정식 경로로 승격할 것인가. 후자라면 `_actor_scopes` 의 «폴백» 주석을
고쳐야 한다.

### 4.3 P3-1 — 독립·Mega 프로젝트가 같은 Resolver 사용

P1-5 가 `resolve_workflow()` 를 만들어 두었으므로 지금 붙일 수 있다. 실행 입구는
`agent_graph.get_runtime_app()` **한 곳**이다(실측 확인).

### 4.4 화면 이관 8개 (직전 인수인계 §4.2)

`Telemetry(227) → ProgramAdmin(239) → Shadow(305) → Crosswalk(313) → Workspace(373) →
Planning(374) → Preview(658) → Advisor(694)`
⚠️ **먼저 §7(브랜치 분기)을 해결해야 한다** — 셸·디자인 토큰이 다른 브랜치에 있다.

### 4.5 P2 (생성기 UI) — 착수 전 분담 확인 필요

화면 작업이라 **Codex 담당과 겹친다.** 서버 계약은 이미 다 서 있다(`GET /capabilities` 의
`asset_actions`·`can_publish_enterprise` 가 버튼 상태의 근거다).

---

## 5. ⚠️⚠️ 내 사고 2건과 갱신한 규칙 — 반드시 읽을 것

### 무슨 일이 있었나

통제가 실제로 막히는지 확인하려고 **쓰기 엔드포인트를 운영 DB 를 향해 호출**했다. 두 번 모두
「무효 payload 를 보낸다」고 의도했으나 값이 유효해 **실제 데이터가 생겼다.**

| 회차 | 호출 | 생긴 것 |
|---|---|---|
| 1 | 익명 `POST /planning/accounts`·`/drivers` | 계정과목 `PROBE_X` · 동인 `PROBE_D` |
| 2 | `unrestricted` 계정으로 `POST /facts`·`/scenarios`·`/submissions` | fact · 시나리오 · 제출물 각 1건 |

백업 후 해당 행만 삭제해 복구했고, **첫 실측값과 일치**함을 확인했다
(accounts 10 · facts 20 · scenarios 4 · assumptions 3 · submissions 1 · drivers 0, 탐침 흔적 0).

### 갱신한 규칙 (종전 규칙은 불충분했다)

- **종전**: «파괴적 엔드포인트는 익명으로, 존재하지 않는 id / 무효 payload 로만 탐침» → **두 번 틀렸다.**
- **지금**: **운영 DB 를 향한 쓰기 호출은 하지 않는다.** payload 가 무효할 «예정» 이어도 하지 않는다.
  통제 확인은 **격리 DB(tmp) 또는 정식 테스트**로만 한다.
- 정식 테스트에서도 쓰기 경로는 **존재하지 않는 id·빈 payload** 만 쓴다(`test_planning_control_gate.py`
  에 그 이유를 주석으로 남겼다).

### 그리고 격리를 늘렸다

`data/planning.db` 가 테스트 격리 목록에 **없었다.** 경로를 절대경로로 고정하면 cwd 와 무관하게
항상 운영 파일을 쓰므로 위험이 확정된다 — 그래서 `tests/conftest.py` 에 격리를 추가했다.

⚠️ **아직 격리되지 않은 저장소 7개**: `advisor` · `collaboration` · `connectors` ·
`decision_ledger` · `external_intelligence` · `benchmark` · `chroma`/`knowledge_packs` ·
`mcp_cache`. 각각 어느 테스트가 쓰는지 확인이 필요하다(별개 작업).

---

## 6. ★ 정정 — 내가 틀린 진단을 커밋에 남겼다

**틀린 진단**(`e61236956` 커밋 메시지와 `[SEC-PLAN-50]` 기록):
> `resolve_scope_ref` 가 `LS_MNM`·`MNM_BATTERY`·`production` 등 **모든 참조에 빈 문자열**을 반환한다.

**사실**: 실제 DB 에서는 **정상 동작한다.**
`LS_MNM → node_41402723bc90`, `MNM_BATTERY → node_36c1c7c797e0`,
`production_battery → node_36c1c7c797e0`.

**진짜 원인**: pytest 안에서 `ecm_repository.db_path` 가
`…/pytest-of-denni/pytest-553/test_env0/enterprise_context.db`(노드 **0건**)를 가리켰다.
즉 «정본 불일치» 로 보인 것은 **상대경로가 다른 파일을 열고 있었던 것**이다.
실서버에서 실제로 해석되지 않는 것은 **매핑되지 않은 부서**(`procurement`) 하나다.

**교훈**: 「같은 함수가 환경에 따라 다른 값을 준다」를 만나면 **먼저 그 함수가 어느 파일을 보고
있는지** 찍어야 한다. 나는 값이 틀렸다고 보고 정본 설계를 의심했고, 한 단계 엉뚱한 곳을 향했다.
`_actor_scopes` 수정 자체는 유효하다(매핑 누락을 우회한다) — 근거만 달라졌다.

---

## 7. ⚠️ 브랜치 분기 — 이것을 모르면 시간을 버린다

```
                    cbe3a7ec4 (분기점)
                   ╱                ╲
   claude/nice-hawking-f8b4bf        dev  ← 지금 여기
   (커밋 7개, 원격 미병합)            (자산 거버넌스 P0~P1 + 경영계획 + 경로)
   화면 이관 3~9/10 + 런처
   HubShell · afs.css · RailIcon
   terms.ts · actingScope.ts
   scripts/capture_screens.py
```

- **`dev` 에는 화면 이관 결과물이 없다.** 「이관 완료」라고 기록된 화면 10개와 런처, 공용 셸
  (`HubShell`·`afs.css`), 용어 사전(`terms.ts`), 헤드리스 캡처 스크립트가 **모두 그 브랜치에만** 있다.
- **겹치는 파일 5개**에서 양쪽이 같은 권한 구멍을 **각각 독립적으로** 막았다:
  `api/deps.py` · `api/routes/factory_control.py` · `knowledge_control.py` · `org_control.py` ·
  `.agents/TEAM_BOARD.md` → **병합 시 충돌 예상.**
- 병합 시 참고: `hidden_envelope`·`_EXACT_COUNT_RULES` 는 이번 세션에 **브랜치와 동일한 형태로**
  dev 에 도입했다(충돌이 아니라 같은 내용이 되도록 의도). `plan` 규칙만 dev 쪽에 더 있다.
- **화면 이관(§4.4)을 하려면 병합이 선행**돼야 한다 — 공용 셸이 없으면 이관할 대상이 없다.

---

## 8. ★ 함정 — 이번 세션에 실제로 빠진 순서대로

1. **`list_assets` 가 돌려주는 행에는 `body`·`versions`·`runnable` 이 없다**(그 셋은 `get()` 이
   붙인다). 모르고 `r.get("runnable")` 로 판정해 **모든 조직 워크플로우가 목록에서 사라졌다.**
   `agent_count` 도 항상 0 이었다. **같은 원인으로 P1-4 목록도 이미 틀려 있었다**(`version_count`
   항상 0). → 「키가 있을 것」을 전제로 `.get()` 을 쓰면 `0`·`None`·`False` 가 조용한 거짓이 된다.
2. **테스트 계정을 실측 없이 고르면 엉뚱한 이유로 통과한다.** `hikwon_1@lsmnm.com` 은 **AI 거버넌스
   관리자 10명 중 하나**다 — 「일반 부서원」 자리에 쓰면 전사 공개까지 통과한다.
   실측해 고른 계정: `hikwon_7`(manager·`LS_MNM` 만) · `hikwon_2`(member·`MNM_BATTERY`) ·
   `hikwon_17`(viewer) · `hikwon_4`(AI 관리자·3범위) · `hikwon@lsmnm.com`(`unrestricted`).
3. **통제를 조이다가 기능을 껐다.** `_scope()` 를 태우자 **자기 조직 요청도 404** 가 됐다.
   「막혔으니 안전」으로 읽으면 아무도 못 쓰는 제품이 된다 —
   `test_own_scope_still_works` 가 그 상태를 잡는다. **이 테스트가 이 세션에서 가장 중요하다.**
4. **`/import/rows` 는 검증 실패에도 200 + `ok:false`** 를 준다(맞는 설계다). `status_code` 만
   보면 「범위 통과」와 「검증 실패」를 구분하지 못한다.
5. **SQL `LIKE '%__%'` 는 모든 문자열을 잡는다** — `_` 가 단일 문자 와일드카드다. 탐침 흔적
   검사가 35건을 오탐했다. 문자열 판정은 파이썬으로 하거나 `ESCAPE` 를 단일 문자로 준다.
6. **여러 줄 `import` 중간에 자동 삽입하면 구문 오류가 난다**(경로 일괄 치환에서 1건 발생).
   일괄 치환 후에는 반드시 `compileall` 로 확인한다.
7. **`_scope()` 는 범위를 명시하지 않으면 필터하지 않는다**(`no_scope_requested`). 즉 그 함수만
   부르고 행 필터를 안 하면 «범위를 안 보내면 전량» 이 된다.

---

## 9. 결정 대기 (Supervisor)

| # | 내용 | 왜 필요한가 |
|---|---|---|
| 1 | **매핑되지 않은 부서** 처리 — 노드 매핑을 채울지, `readable_scope_nodes` 를 정식 경로로 승격할지 | 지금은 우회로 동작한다(§4.2) |
| 2 | 경영계획 **수립 권한**을 별도로 둘지 | 지금은 «시나리오를 만들 수 있는 사람이 가정도 넣는다» 로 통일 |
| 3 | `is_ai_admin` **추가 부여** 대상 | 현재 10명. P2 화면이 이 값으로 버튼을 정한다 |
| 4 | 소유권 **미기록 프로젝트** 관대함을 언제 걷어낼지 | 식별된 사용자에게 열려 있다. 미기록 수를 상시 관측해야 하고 0 이 되면 제거 |
| 5 | dev 의 다른 라우트(`knowledge_control`·`master_control`)가 `hidden_count` 를 **모두에게** 준다 | Data Stealth 방침과 어긋난다. 일괄 정리 필요 |

---

## 10. 알려진 부채 (내가 만든 것 아님)

- **쓰기 경로는 아직 파일이다.** `POST /templates/copy`·`PUT /templates/{id}` 는 종전대로
  `templates/*.json` 에 쓴다. 새 자산을 DB 로 보내려면 화면이 신 API 를 써야 한다(P2).
- **`get_runtime_app` 은 컴파일 결과를 `tid` 로 캐시한다.** 조직 자산을 개정하면 캐시가 낡는다
  (파일 템플릿도 같은 한계 — «HOTL 중단점 변경은 서버 재시작 후 반영»). 버전 스냅샷은 P3.
- **플랫폼 관리자의 `manageable_scope_nodes` 는 빈 배열이다.** 서버는 `is_platform_admin` 으로
  전부 허용하지만, 화면이 이 배열만 보고 「관리 조직 없음」으로 그리면 관리자에게 아무 버튼도
  안 보인다. `capabilities` 응답의 `asset_actions`·`can_publish_enterprise` 를 보라.
- **스킬 `design_system` 은 이름이 슬러그로 노출된다** — 어느 에이전트도 쓰지 않는 디자인 문서라
  「그 스킬을 쓰는 에이전트의 이름」이 실제로 없다. `migration_report.slug_named` 로 관측된다.
- **파일 자산 54개가 승인 이력 없이 돌고 있다**(`migration_report.pending_total`). 조직 자산으로
  이관하면 「누가 언제 승인했는가」에 답할 수 있게 된다.
- 남은 «`Principal` 없는 라우트» 약 46개(crosswalk 9 · benchmark 6 · 기타).

---

## 11. 재개 절차

```bash
cd C:\WorkSpace\gemini_agent_team_verG
git checkout dev && git pull
./venv/Scripts/python.exe -m pytest -q          # 1,970 passed / 1 skipped 기대
```

읽을 순서: 이 문서 §4 → `.agents/DECISIONS.md` `[D-018]` → `.agents/TEAM_BOARD.md` 의
`[SEC-SCOPE-51]` → `docs/design_agent_governance_scope_permissions_2026-08-04.md` §5.3·§7.

⚠️ **서버 기동 전 확인**: 데이터 경로가 절대경로로 고정됐으므로 어느 디렉터리에서 띄워도 같은
DB 를 본다. 반대로 **워크트리에서 띄우면 워크트리의 `data/` 를 본다** — 조직도가 비어 있으면
전 사용자가 아무것도 못 보는 상태가 되고, 오류는 나지 않는다. 노드 수를 먼저 세어 볼 것:

```bash
./venv/Scripts/python.exe -c "from core.enterprise_context.repository import ecm_repository as r; print(len(r.list_nodes()))"
```

16 이 나와야 한다.
