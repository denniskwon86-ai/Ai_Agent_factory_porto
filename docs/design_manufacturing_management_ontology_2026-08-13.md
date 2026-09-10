# 제조 경영 온톨로지 런타임 — 착수 전 영향도·재사용·마이그레이션 설계

> 상태: **설계 보고(구현 착수 전)** · 코드·DB·API 변경 **0**
> 기준일: 2026-08-13 · 작성 Claude Code
> 상위 인계: `.agents/TEAM_BOARD.md` `[G2-ONTOLOGY-72]` · 로드맵 `§G2-C`(C01~C07)
> **착수 조건(Codex 순서 보정 2026-08-13): G1-B P0(B01~B05) 완료·커밋 전에는 코드·DB·API 착수 금지.**
> 이 문서는 그 금지 아래에서 허용된 **읽기 전용 설계 보고**다.
>
> 용어: 기술명 `제조 경영 온톨로지` · 제품 설명 `경영 의미 모델` · 화면명 `기업 경영 의미지도`.
>
> **상세 설계 기준선**: `docs/architecture/G2_MANUFACTURING_MANAGEMENT_ONTOLOGY_DETAILED_DESIGN_2026-08-13.md`
> **기계 판독 계약**: `docs/architecture/g2_first_vertical_ontology_contract_v1.json`
>
> **개정 2026-08-13 (rev.2) — Codex 교차검토 §12「조건부 승인」의 보정 5건을 본문에 반영했다.**
> 초판의 판단 중 **세 가지가 틀렸고** 그 자리에 정정 사유를 남긴다(지우지 않는다):
> ① `entity_types.relations` 를 온톨로지 SSOT 로 본 것 → **허용 관계 후보일 뿐**(§4.1)
> ② `master_records.supersedes`+`aliases` 로 유형 통합을 표현하려 한 것 → **레코드용 계보의 오용**(§7.1)
> ③ 응답에 `blocked.count`·사유를 실은 것 → **권한 밖 자원의 존재 누설**(§6.2)
> ★ ③ 은 내가 **바로 전날 프로젝트 목록에서는 옳게 처리한 것**이다(권한 축에서 막힌 것은
>   세지 않는다). 같은 규칙을 다른 자원에 옮겨 적으면서 놓쳤다 — 규칙을 «아는 것» 과
>   «새 자리에 적용하는 것» 은 다르다.

---

## 0. 이 문서가 답하는 것

인계가 요구한 8가지에 **실측으로** 답한다. 추정한 숫자는 쓰지 않는다.

| # | 질문 | 절 |
|---|---|---|
| 1 | 기존 자산별 SSOT·재사용·확장·폐기 판정 | §2 |
| 2 | 관계 저장 스키마와 승인·버전·유효기간 모델 | §4 |
| 3 | 테넌트·조직·REAL/VIRTUAL/SANDBOX 격리 | §5 |
| 4 | 근거·계보·기준시점이 포함된 질의 API | §6 |
| 5 | 기존 데이터 마이그레이션 및 중복 방지 | §7 |
| 6 | Graph RAG 후보 탐색과 공식 관계 승인 경계 | §8 |
| 7 | G4 로 넘길 `calculation_ref` 계약 | §9 |
| 8 | 별도 그래프 DB 도입 판단 기준 | §10 |

---

## 1. 실측 기준선 (2026-08-13, 읽기만)

### 1.1 저장소별 표와 행수

| DB | 온톨로지에 관련된 표(행수) |
|---|---|
| `master/master.db` | `entity_types(21)` · `master_records(80, active 64)` · `master_scope_bindings(45)` · `business_terms(35)` · `term_synonyms(0)` · `aliases(135)` · `data_assets(2)` · `data_asset_fields(1)` · `data_contracts(1)` · `data_quality_profiles(1)` · **`lineage_edges(4)`** · `key_crosswalk(0)` · `external_systems(0)` · `external_schemas(0)` · `crosswalk_proposals(0)` |
| `enterprise_context.db` | `organization_nodes(29)` · **`organization_edges(27)`** · `enterprise_entities(18)` · `enterprise_profiles(5)` |
| `planning.db` | `plan_accounts(10)` · `plan_facts(20)` · `scenarios(4)` · `plan_drivers(0)` · `driver_impacts(0)` |
| `external_intelligence.db` | `external_indicators(6)` · `external_sources(0)` · `external_observations(0)` |
| `connectors.db` | `connectors(0)` · `query_contracts(0)` |
| `decision_ledger.db` | `decision_ledger_events(4,050)` — **불변 이력** |

### 1.2 세 가지 발견 — 이것이 설계를 정한다

**① 관계를 담는 표가 이미 둘 있다.** `lineage_edges`(기술 계보)와 `organization_edges`(조직 관계).
셋째를 만들 때 **무엇을 흡수하고 무엇을 남기는지** 먼저 정해야 한다(§3).

**② `entity_types.relations` 가 21/21 전부 `[]` 다 — 다만 이것은 «온톨로지의 자리» 가 아니다.**

> ⚠️ **[rev.2 정정]** 초판은 이 컬럼을 「온톨로지 스키마의 SSOT」라고 적었다. **틀렸다.**
> 이 필드는 M1 정의상 **허용 관계 «후보»** 이고 방향성·역관계·버전·승인·유효기간을 담지
> 못한다. 그 위에 온톨로지를 세우면 승인 개념이 없는 자리에 공식 관계가 쌓인다.
> → 정본은 §4.1 의 4층 분리이고, 이 컬럼은 **부트스트랩 입력 또는 읽기용 축약본**이다.
> ⚠️ 21개 JSON 을 손으로 채운 뒤 다시 이관하는 작업은 **하지 않는다**(§12.3).

그럼에도 「전부 비어 있다」는 사실 자체는 유효한 기준선이다 — **업무 의미 관계가 이 저장소에
한 건도 선언된 적이 없다**는 뜻이고, 그래서 대표 수직 질문에 지금은 어떤 경로도 나오지 않는다.

**③ ★★★ 같은 개념이 두 `type_id` 로 갈려 있고, 한쪽은 범위 바인딩이 하나도 없다.**

| 밑줄형(A) | 하이픈형(B) | 이름 | `master_scope_bindings` |
|---|---|---|---|
| `quality_spec` (2) | `quality-spec` (2) | 동일 「품질 규격」 | **B 만 2건** |
| `finance_param` (6) | `finance-param` (10) | 동일 「재무·시장 파라미터」 | **B 만 10건** |
| `emission_factor` (1) | `emission-factor` (2) | 유사 | **B 만 2건** |
| `sensor_spec` (1) | `sensor-spec` (1) | 유사 | **B 만 1건** |

즉 **밑줄형 10건은 조직 범위 바인딩이 없다.** D-014(미지정 = 비노출) 아래에서 그 10건은
아무에게도 보이지 않는다. 온톨로지를 `type_id` 위에 세우면 **같은 개념이 두 노드로 갈리고,
그중 하나는 영원히 비어 있는 노드**가 된다. §7 의 선행 과제 1번이다.

---

## 2. 자산별 SSOT · 재사용 판정 (요구 1)

원칙: **폐기하지 않는다. 복제하지 않는다. SSOT 를 옮기지 않는다.**
온톨로지는 새 진실을 만드는 곳이 아니라 **이미 있는 진실들 사이의 승인된 관계**를 담는다.

| 자산 | SSOT | 판정 | 근거 |
|---|---|---|---|
| `organization_nodes` · `organization_edges` | **조직 계층·관계** | **재사용 · 흡수 금지** | 권한 상속이 `OPERATING_PARENT` 만 따른다(D-003)는 규칙과 `scope_guard`·`project_visibility` 가 여기에 묶여 있다. 온톨로지가 조직 관계를 복제하면 **권한 판정이 두 곳**이 되고, 그것이 이 저장소에서 반복된 결함 유형이다 |
| `enterprise_entities` | 실제/가상/경쟁사 실체 | 재사용 | `entity_mode` 의 원천 |
| `entity_types` | **개체 유형** | **재사용 · `relations` 는 SSOT 아님** | 유형 정의는 여기가 정본이다. 그러나 `relations` 는 **허용 관계 후보**일 뿐이며 정본은 §4.1 의 4층이다(rev.2 정정). ⚠️ 중복 4쌍 통합이 선행(§7) |
| `master_records` | **업무 개체**(품목·설비·BOM·KPI·표준필드…) | 재사용 | 온톨로지 노드의 주 공급원(active 64) |
| `master_scope_bindings` | 개체의 조직 범위 | 재사용 | 노드의 범위 판정 입력 |
| `business_terms` · `term_synonyms` · `aliases` | **용어·동의어** | 재사용 | 자연어 질문 → 개체 해석의 입력(G2-C05). `term_synonyms` 0건은 §8 후보 제안의 대상 |
| `data_assets` · `data_asset_fields` · `data_contracts` | 데이터 자산·계약 | 재사용 | 근거(`evidence_refs`)의 실체 |
| `data_quality_profiles` | 품질 측정 | 재사용 | G2-C07 입력 |
| `key_crosswalk` · `external_systems` · `external_schemas` · `crosswalk_proposals` | 외부키 매핑 | 재사용 | ⚠️ **전부 0건** — 지금은 근거를 공급하지 못한다. 「크로스워크로 이었다」를 완료로 세지 말 것 |
| `lineage_edges` + `DataLineage.impact_of` | **기술 계보** | **탐색기는 재사용 · 표는 분리**(§3) | 아래 판정 |
| `plan_accounts` · `plan_facts` · `scenarios` | 경영계획 값 | **참조만** | 수치는 G4 담당(§9) |
| `external_indicators` | 외부지표 | 재사용 | 동인 관계의 한쪽 끝 |
| `decision_ledger_events` (4,050) | **불변 이력** | **읽기만 · 수정 절대 금지** | `event_hash` 체인. 백필 제외 목록에 이미 있다 |
| `mcp_cache` | TTL 캐시 | 무관 | Snapshot 저장소가 아니다 |

**폐기 대상: 없다.** 다만 §7 의 중복 유형 4쌍은 «폐기» 가 아니라 **통합**이다.

---

## 3. 최대 쟁점 — `lineage_edges` 를 확장할 것인가

형태만 보면 확장이 옳아 보인다. `from_type/from_id/to_type/to_id/relation_type` 은 이미
G2-C02 가 요구하는 subject/object 일반형이고, **BFS 탐색기(`impact_of`, 깊이 제한·순환 방지)와
`GET /lineage/impact` API 가 이미 있다.**

그런데 실측하면 확장할 수 없다. **판정: 표는 나누고, 탐색기는 재사용한다.**

| # | 확장하면 깨지는 것 | 근거 |
|---|---|---|
| 1 | **버전·유효기간을 담을 수 없다** | `lineage_edges` 는 `(from,to,relation)` 유일 제약에 `ON CONFLICT DO UPDATE` 로 **덮어쓴다**. 같은 관계의 v1·v2 가 공존해야 하는 G2-C03 과 정면으로 충돌한다 |
| 2 | **기존 4건이 「승인됨」으로 바뀐다** | `add_edge` 는 `status='active'` 를 즉시 준다 — 승인 개념이 없다. 승인 필드를 얹으면 기존 행이 **무승인 상태로 승인 대접**을 받는다(인계 금지 범위 「무승인 관계 확정」) |
| 3 | **질문이 다르다** | 지금 내용 4건은 전부 기술 계보다(`release→project derives_from`, `asset→release feeds`). 업무 의미 관계는 0건. 섞으면 「원료 지연이 어느 공장 손익에 영향을 주나」의 답에 **릴리스 포크가 섞인다** |
| 4 | 범위 3키가 없다 | `tenant_id`·`scope_node_id`·`entity_mode` 부재 → 격리를 얹을 자리가 없다 |

**G2-C02 최소 12필드 대비 현황: 4/12 충족**(`subject`·`object`·`relation_type`·`evidence_ref`).
없는 것 — `version` · `effective_from/to` · `tenant_id` · `scope_node_id` · `entity_mode` ·
`approval_status` · `source_lineage`.

### 재사용하는 것

- **`impact_of` 의 탐색 골격** — BFS · `max_depth` · 순환 방지 · 결과에 `depth` 병기.
  여기에 **필터 훅**(승인·기간·범위)을 주입할 수 있게 일반화한다. 새 탐색기를 쓰지 않는다.
- **`derive_edges` 의 규약** — 「추론으로 만드는 선은 없다. 명시된 링크에서만 만든다」와
  `origin='derived'` 표시. §8 의 후보 경계가 이미 이 형태로 존재한다.
- **`NODE_TYPES`·`RELATION_TYPES` 화이트리스트** — 자유 문자열 금지 관례를 그대로 승계.

---

## 4. 관계 저장 스키마와 승인·버전·유효기간 (요구 2)

### 4.1 ★★★ [rev.2] 정본은 **네 층으로 분리**한다 — 한 표에 담지 않는다

초판은 `semantic_relations` **한 표**에 유형·제약·인스턴스·이력을 섞으려 했다. 그러면
「어떤 관계가 성립할 수 있는가」(유형·제약)와 「지금 무엇이 이어져 있는가」(인스턴스)가 같은
자리에 있게 되고, 유형을 고치는 순간 인스턴스의 승인 이력이 흔들린다.

| 층 | 표 | 담는 것 |
|---|---|---|
| ① 관계 **유형** | `semantic_relation_types` | 유형 id · 사용자 표시명 · **방향성** · **역관계** · 대칭/전이 여부 · 버전 · 승인 상태 · 유효기간 |
| ② 허용 **조합** | `semantic_relation_constraints` | 허용 subject/object 유형 쌍 · 범위 요구조건 · **근거 요구조건**(어떤 근거가 있어야 이을 수 있는가) |
| ③ 관계 **인스턴스** | `semantic_relations` | 실제 관계 + 승인 후보(§4.2) |
| ④ 변경 **이력** | `semantic_relation_events` | append-only. **승인 의사결정은 `decision_ledger` 와 correlation id 로 연결**한다 |

⚠️ **감사 원장을 둘로 만들지 않는다.** ④는 «관계가 어떻게 바뀌었나» 의 기술 이력이고,
«누가 왜 승인했나» 는 `decision_ledger`(4,050건, 불변·해시 체인)가 정본이다. 둘을 각자
진실원본처럼 두면 나중에 어느 쪽이 맞는지 아무도 답할 수 없다.

★ `entity_types.relations` 는 위 ①②에서 **생성한 읽기용 축약본**으로만 유지하거나 단계적으로
폐기한다. 그것을 먼저 손으로 채우는 일은 하지 않는다.

### 4.2 ★ 필드 이름을 새로 만들지 않는다

`business_terms`·`data_assets`·`data_contracts` 는 **이미 같은 범위 계약 필드 집합**을 쓴다
(D-013 + M2 관문 §2.1):

```
tenant_id · enterprise_scope_id · entity_mode · scope_type · owner_organization_id
scope_assignments · classification · effective_from · effective_to
approval_status · approved_by
```

인계가 적은 최소 필드(`scope_node_id`·`approval_status`…)와 **뜻이 같고 이름만 다른 것**이
있다. 새 이름을 만들면 같은 개념이 저장소마다 다른 낱말이 되어, 그것 자체가 온톨로지가
없애려는 문제다. → **기존 낱말을 그대로 쓰고**, 인계 표의 `scope_node_id` 는
`enterprise_scope_id` 로 읽는다(D-018 상 값은 노드 id 정본).

### 4.3 인스턴스 표 구성(안)

```
semantic_relations                     -- 관계 인스턴스(승인된 것 + 후보)
  relation_id      TEXT PK
  subject_type / subject_id            -- 유형은 semantic_relation_types 화이트리스트
  object_type  / object_id
  relation_type                        -- 〃
  version          INTEGER              -- 같은 (subject,object,relation) 의 세대
  supersedes_version INTEGER
  effective_from / effective_to
  tenant_id / enterprise_scope_id / entity_mode
  scope_type / owner_organization_id / scope_assignments / classification
  approval_status  -- §4.4 의 6종
  approved_by / approved_at
  origin           -- user | derived | suggested            (§8)
  confidence       REAL                 -- ⚠️ §4.5 — 후보에만 의미가 있다
  evidence_refs    TEXT(JSON 배열)      -- 복수. 단수 `evidence_ref` 를 쓰지 않는다
  source_lineage   TEXT(JSON)           -- 어느 표·어느 행에서 유도됐는가
  calculation_ref  TEXT                 -- §9. 없으면 빈 값(«수치는 여기서 만들지 않는다»)
  ledger_correlation_id TEXT            -- 승인 의사결정을 decision_ledger 로 잇는 열쇠
  created_by / created_at / updated_at
```

### 4.4 [rev.2] 승인 상태는 **6종**이고 `EXPIRED` 는 저장하지 않는다

```
DRAFT → IN_REVIEW → APPROVED → (SUPERSEDED | RETIRED)
                  ↘ REJECTED
```

- ⚠️ 초판의 4종(`DRAFT|REVIEW|APPROVED|RETIRED`)으로는 **「반려됨」과 「새 버전에 밀려남」을
  구분할 수 없다.** 둘은 사람이 해야 할 다음 행동이 다르다 — 반려는 고쳐서 다시 내는 것이고,
  밀려남은 아무것도 안 해도 되는 것이다.
- **`EXPIRED` 는 상태가 아니라 계산이다.** `effective_to` 로 판정한다. 상태로 저장하면 시간이
  지날 때마다 누군가 배치로 갱신해야 하고, 그 배치가 멈추면 만료된 관계가 유효한 얼굴로 남는다.

### 4.5 [rev.2] `confidence` 는 **후보에만** 의미가 있다

승인된 공식 관계에 확률값을 붙여 보여주면 사용자는 **사람이 확정한 사실을 추정치로 읽는다.**
→ 승인 후에는 참고 메타데이터로만 보존하고 **응답의 사용자 표시 영역에 싣지 않는다.**
(경쟁사 근거에서 「신뢰도는 숫자가 아닌 단계」로 판단한 것과 같은 이유다.)

### 4.6 규칙

1. **승인된 것만 기본 질의에 나온다.** `APPROVED` 가 아니거나 기간 밖이면 기본 Fail-closed.
   「후보도 보고 싶다」는 **명시 파라미터**로만(§8).
2. **덮어쓰지 않는다.** 개정은 새 `version`, 이전 버전은 `SUPERSEDED` + `effective_to`.
   `lineage_edges` 의 `ON CONFLICT DO UPDATE` 를 승계하지 않는 이유가 이것이다.
3. **[rev.2] 유일성은 모든 상태에 걸지 않는다.** `DRAFT`·`REJECTED` 후보는 **공존해야 한다**
   — 같은 관계를 두 사람이 각자 제안할 수 있고, 하나를 막으면 제안 자체가 사라진다.
   → **`APPROVED` 이면서 같은 기준시점에 유효한 것만 하나**가 되도록 부분 유일 제약
   (`WHERE approval_status='APPROVED'`) 또는 트랜잭션 검사를 둔다.
   ⚠️ 초판의 「(subject,object,relation,tenant,mode) 활성 1개」는 후보를 죽인다.
4. **as-of 조회가 1급이다.** `as_of` 를 주면 그 시점에 유효했던 버전만 본다. 주지 않으면
   **현재**다(과거를 기본값으로 두면 사용자는 옛 답을 최신으로 읽는다).
5. **폐기는 삭제가 아니다.** `RETIRED` + `effective_to`. 이미 그 관계로 만든 답변의 근거가
   사라지면 재현이 깨진다.
6. **자기 참조·순환** — 자기 참조는 거부(기존 `add_edge` 규칙 승계), 순환은 거부하지 않고
   **탐색 깊이로 끊는다**(조직 그래프가 이미 그 방식이다).

---

## 5. 테넌트·조직·REAL/VIRTUAL/SANDBOX 격리 (요구 3)

### ★★★ [rev.2] 새 판정기를 만들지 않되, `project_visibility` 를 **직접 부르지도 않는다**

> ⚠️ **초판 정정.** 초판은 「`project_visibility` 를 그대로 부른다」고 적었다. 두 가지가 틀렸다.
>
> ① 그 모듈은 **프로젝트 메타·소유자·부서 가시성에 특화**돼 있다. 관계 객체는 소유자도
>    `project_meta.json` 도 없다 — 억지로 맞추려면 가짜 소유권을 만들어야 한다.
> ② **일부 보조 함수는 의도적으로 fail-open 이다.** `scope_covers` 는 조상 판정에 실패하면
>    「좁히지 않는다」로 통과시킨다(화면을 비우지 않기 위한 판단이고, 그 자리에서는 옳다).
>    그것을 온톨로지 **보안 경계**로 쓰면 G2 의 Fail-closed 계약과 정면으로 충돌한다.

**그래서 층을 하나 둔다.**

```
G1-B 정책 결정점 (PDP)          ← 규칙은 여기 한 곳
        ▲
   ResourceScope 계약           ← 자원 종류에 무관한 범용 어댑터
    ┌───┴────┐
 프로젝트    온톨로지 노드·간선   ← 각자 자기 자료를 계약 형태로 «번역» 만 한다
```

| 축 | 재사용하는 **원칙·primitive** | 재사용하지 **않는** 것 |
|---|---|---|
| 「지금 무엇을 보기로 했는가」 | `resolve_viewing_context`(문맥 확정) | `context_visible` 의 프로젝트 메타 전제 |
| 조직 계층 상하 | ECM 계층 조회(OPERATING_PARENT 만, D-003) | `scope_covers`(**fail-open**) |
| 요청 범위 검증 | `scope_guard.resolve_effective_scope` | — |
| 거부 응답 | 단건 **404 은폐** · 목록/경로는 **보이는 것만** · 401 · 422 (§3.3 경계표) | — |
| 감사 | `ACCESS_DENIED_SCOPE_MISMATCH` — 요청값과 서버 계산값을 **둘 다** | — |

⚠️ **정책 규칙은 한 곳(PDP)에 유지한다.** 어댑터는 «이 자원의 tenant·scope·mode·소유·등급은
무엇인가» 를 답할 뿐, **판정하지 않는다.** 어댑터가 판정을 시작하는 순간 판정이 다시 둘이 된다.
⚠️ 이 층은 **G1-B04(데이터 읽기·쓰기·업무 액션별 정책 결정점)** 위에 선다 — 그래서 G1-B P0
완료가 온톨로지 구현의 하드 선행이다.

**관계는 «양 끝» 이 있다.** 그래서 판정 단위가 노드가 아니라 **경로**다.

> 규칙: 경로 위의 **모든 노드와 모든 간선**이 보여야 그 경로를 반환한다. 하나라도 막히면
> 경로 자체를 내지 않고, **몇 개가 가려졌는지만** 알린다(G1-C3 목록이 쓴 방식과 동일).
> ⚠️ 중간 노드를 «건너뛰고» 이어 붙이면 **볼 수 없는 자원의 존재가 경로 모양으로 새어나간다.**

`SANDBOX`·`VIRTUAL` 은 실행 문맥 축에서 이미 갈린다 — 온톨로지가 따로 거르지 않는다.

---

## 6. 근거·계보·기준시점을 포함한 질의 API (요구 4)

기존 라우터를 **대체하지 않고** 위에 얹는다. `catalog`·`glossary`·`lineage`·`master`·
`crosswalk`·`enterprise-context` 는 그대로 둔다.

| Method | Path | 역할 |
|---|---|---|
| `GET` | `/api/v1/ontology/objects` | 개체 조회(유형·범위·as-of) |
| `GET` | `/api/v1/ontology/relations` | 관계 조회(승인·기간·범위 필터) |
| `GET` | `/api/v1/ontology/paths` | **의미 경로** — subject → object, 깊이 제한 |
| `POST` | `/api/v1/ontology/relations` | 초안 생성(DRAFT) |
| `POST` | `/api/v1/ontology/relations/{id}/submit`·`/approve`·`/retire` | 승인 흐름 |
| `GET` | `/api/v1/ontology/candidates` | 후보(§8) — 공식 의미망과 **분리된 자리** |
| `POST` | `/api/v1/ontology/ask` | 자연어 질문 → 질의 계획 → 경로(G2-C05) |

### 6.2 ★★★ [rev.2] 응답 계약 — **막힌 것의 개수·사유를 사용자에게 주지 않는다**

> ⚠️⚠️ **초판의 보안 결함.** 초판은 `blocked: {count: 3, reasons: {SCOPE_OUTSIDE: 2,
> NOT_APPROVED: 1}}` 을 실었다. 그것은 **다른 조직의 관계와 미승인 관계가 «존재한다» 는 사실을
> 알려 준다.** 「그 조직에 이 개체와 이어진 무언가가 2건 있다」는 그 자체로 남의 회사 정보다.
>
> ★ 나는 **바로 전날 프로젝트 목록에서 이것을 옳게 처리했다** — 권한 축(`UNAUTHORIZED`)에서
>   막힌 것은 세지 않고 문맥 축만 셌다. 같은 규칙을 새 자원에 옮겨 적으면서 놓쳤다.
>   규칙을 «아는 것» 과 «새 자리에 적용하는 것» 은 다르다.

**두 경우를 가른다.**

| 상황 | 사용자 응답 | 감사 로그 |
|---|---|---|
| **볼 권한은 있는데 지금 고른 문맥 때문에 빠짐** | `context_omitted` 로 **건수와 전환 방법**을 알린다 | 남긴다 |
| **권한이 없거나 승인되지 않음** | **존재·개수·사유를 전부 숨긴다.** 단건 404, 목록·경로는 보이는 것만 | **여기에만** 상세 사유를 남긴다 |

```json
{
  "path": [{"type":"master","id":"RM-MHP-001","relation_to_next":"feeds","relation_version":2}],
  "as_of": "2026-08-13T00:00:00",
  "evidence_refs": ["data_asset_fields.master_code=RM-MHP-001", "business_terms:term_x"],
  "source_lineage": {"derived_from": "master_scope_bindings", "run_id": "..."},
  "scope_decision": {"tenant_id":"...","entity_mode":"REAL","scope_node_id":"...","result":"OK"},
  "context_omitted": {"count": 2, "how_to_include": "조직 범위를 상위로 바꾸면 보입니다"},
  "calculation_ref": ""
}
```

- `context_omitted` 만 남는다. **`SCOPE_OUTSIDE`·`NOT_APPROVED` 건수는 응답에 없다.**
- ⚠️ 그렇다고 「0건」으로 뭉개지도 않는다 — 볼 수 있는데 문맥 때문에 빠진 것은 **말해 줘야**
  사용자가 범위를 바꿔 볼 수 있다. 숨겨야 하는 것은 «볼 수 없는 것의 존재» 뿐이다.
- ⚠️ 경로 위의 **모든 노드·간선이 보여야** 그 경로를 낸다(§5). 중간을 건너뛰어 이으면
  볼 수 없는 자원의 존재가 **경로 모양으로** 새어나간다.

---

## 7. 마이그레이션과 중복 방지 (요구 5)

### 7.1 선행 과제 1 — `entity_types` 중복 4쌍 통합 (**사용자 결정 완료**)

**결정(Supervisor / 2026-08-13): 하이픈형을 정본으로 한다** — `quality-spec` · `finance-param` ·
`emission-factor` · `sensor-spec`. 근거는 현행 시드·테스트·운영 바인딩이 하이픈형을 쓴다는 것이다.

> ⚠️ **[rev.2 정정]** 초판은 통합을 `master_records.supersedes` + `aliases` 로 하겠다고 적었다.
> **오용이다.** `supersedes` 는 **레코드 버전 계보**이고 `aliases` 는 **`master_code` 별칭**이다.
> 둘 다 «유형(`type_id`) 별칭» 을 표현하지 못한다. 거기에 유형을 끼워 넣으면 레코드 계보를
> 읽는 기존 코드가 유형 통합 이력을 레코드 개정으로 오독한다.

**필요한 것: 명시적 유형 별칭 계약**

```
entity_type_aliases
  alias_type_id      TEXT   -- 예: finance_param
  canonical_type_id  TEXT   -- 예: finance-param
  reason             TEXT
  effective_at       TEXT
  PRIMARY KEY (alias_type_id)
```

**이행 4단계(구현 직전 보고 대상 ①)**

1. 밑줄형 레코드의 `type_id` 를 하이픈형으로 이관한다. **삭제하지 않고 백업·대사**한다.
2. 조직 `master_domains`, 과거 로더, 시드, 문서의 **밑줄형 참조를 전수 조사**한다.
3. 외부 입력의 밑줄형은 정본으로 **정규화해 받되**, 응답·신규 저장에는 **하이픈형만** 쓴다.
4. 이관 전후 **레코드 수 · 범위 바인딩 수 · 주입 결과**가 보존되는지 검증한다.

⚠️ 4번이 핵심이다. 밑줄형 10건은 지금 **바인딩이 없어 아무에게도 안 보이므로**, 이관하면
   보이는 건수가 **늘어난다.** 그것이 의도인지(=원래 보였어야 하는지) 확인 없이 넘기면
   「없던 자료가 갑자기 나타난」 상태가 된다.
⚠️ 되돌림 계획을 함께 낸다 — 백필 스크립트의 계약(dry-run · 백업 · 멱등 · 모호하면 건너뜀)을 따른다.

### 7.2 선행 과제 2 — 첫 수직 폐루프 유형부터 정의 (**전수 금지**)

**결정(Supervisor / 2026-08-13): 21개 전수를 채우지 않는다.**

- 대상은 **원료 구매·도입계획 → 생산 → 매출·현금흐름·손익**에 필요한 유형만:
  원료 · 공급자 · 구매/도입계획 · 선적/통관/운송 이벤트 · 사업장/공장 · 공정/BOM ·
  생산계획 · 제품 · 품질규격 · 외부지표 · 재무 파라미터 · 계획계정 · KPI.
- ⚠️ **트랜잭션·이벤트는 `master_records` 로 복제하지 않는다.** 원천 Snapshot·계약의
  **식별자를 온톨로지 객체로 참조**한다. 복제하면 기준정보가 거래 원장이 되고 SSOT 가 무너진다.
- ★ 나머지 유형은 빈 배열이 아니라 **`UNMODELED` 로 명시**한다.
  `[]` 는 「관계가 없다」와 「아직 모델링하지 않았다」를 **구별하지 못하고**, 그 구별이 없으면
  완료 판정이 거짓이 된다(이 저장소의 «0과 미측정을 섞지 않는다» 규칙과 같다).
- ⚠️ `UNMODELED` 인 유형은 **완료 판정에 쓰지 않는다.**

### 마이그레이션 방침

| 대상 | 방침 |
|---|---|
| `lineage_edges` 4건 | **옮기지 않는다.** 기술 계보로 그 자리에 남는다(§3) |
| `organization_edges` 27건 | **옮기지 않는다.** 조직 그래프의 SSOT |
| `data_asset_fields.master_code` 등 명시 링크 | `derive_edges` 와 같은 방식으로 **후보**(`origin='derived'`)로만 생성. 자동 승인 금지 |
| `decision_ledger_events` | 읽기만 |

### 중복 방지

1. `(subject, object, relation_type, tenant_id, entity_mode)` 에 **활성 버전 1개** 유일 제약.
2. 후보(`suggested`)는 정본과 **같은 표·다른 상태**로 둔다. 별도 표로 빼면 승격 시 이관이
   필요하고, 이관은 유실 지점이 된다.
3. 온톨로지는 **개체를 복제하지 않는다** — `subject_id` 는 원천 키(`master_code`·`node_id`·
   `term_id`·`asset_id`)를 그대로 가리킨다. 사본을 만들면 SSOT 가 둘이 된다.

---

## 8. Graph RAG 후보와 공식 관계의 경계 (요구 6)

`origin` 3값으로 가른다 — **이 규약은 `derive_edges` 에 이미 있다.**

| `origin` | 뜻 | 기본 질의 노출 |
|---|---|---|
| `user` | 사람이 선언 | 승인되면 노출 |
| `derived` | **명시된 링크**에서 결정론적으로 유도(LLM 0콜) | 승인되면 노출 |
| `suggested` | LLM·Graph RAG 가 제안 | **절대 기본 노출 없음** |

- 후보는 `approval_status=DRAFT` + `origin='suggested'` + `confidence` + `evidence_refs` 를
  반드시 갖는다. 근거 없는 제안은 **저장하지 않는다**(빈 근거를 저장하면 그것이 곧 사실이 된다).
- 승인은 사람이 한다. **자기 승인 금지**는 `scope_assignments` 가 이미 쓰는 규칙을 승계.
- ⚠️ LLM 은 «점수» 를 매기지 않는다 — 같은 입력에 다른 값이 나오면 임계값 보정이 불가능하다
  (유사도 게이트 8-2 에서 같은 판단을 이미 했다).
- ⚠️ `term_synonyms` 0건 · `key_crosswalk` 0건 — **초기에는 후보가 거의 나오지 않는 것이
  정상**이다. 그것을 「기능이 안 된다」로 읽지 않도록 화면에 «관측 기반이 아직 없다» 를 적는다
  (P4-4 자산 위생이 같은 함정을 겪었다).

---

## 9. G4 로 넘기는 `calculation_ref` 계약 (요구 7)

**온톨로지는 수치를 만들지 않는다.** 「무엇이 무엇과 왜 연결되는가」까지가 경계다.

```
온톨로지:  원료 도입 지연 → (affects) → 제1공장 생산계획 → (affects) → 매출·현금흐름
            각 간선에 calculation_ref 가 있으면 그 이름만 돌려준다
G4:        calculation_ref 를 받아 승인된 계산 그래프로 수치를 만든다
```

- `calculation_ref` 는 **승인된 계산 정의의 식별자**다. 값도 산식도 아니다.
- 비어 있으면 «영향은 있으나 계산 정의가 아직 없다» 이고, 그 상태를 **그대로 표시**한다 —
  0 이나 추정치로 채우지 않는다(§16 비협상 조건 「모르는 것을 0 으로 두지 않는다」).
- 온톨로지 응답에 숫자가 들어가는 유일한 경우는 `confidence` 뿐이며, 그것은 **관계의 확신도**
  이지 업무 수치가 아니다.
- G4 는 `calculation_ref` + `as_of` + 승인 버전으로 **재현 가능**해야 한다. 온톨로지는 그 세
  값을 정확히 전달하는 것까지 책임진다.

---

## 10. 별도 그래프 DB 도입 판단 기준 (요구 8)

**현 시점 판정: 도입하지 않는다.** 근거는 규모다.

| 항목 | 현재 실측 |
|---|---|
| 노드 후보 | `master_records(active) 64` + `organization_nodes 29` + `business_terms 35` + `data_assets 2` ≈ **130** |
| 간선 | `lineage_edges 4` + `organization_edges 27` = **31** |
| 탐색 깊이 | 조직 계층 최대 8(`ORG_MAX_DEPTH`), 계보 기본 깊이 제한 있음 |

SQLite 관계 표 + BFS 로 충분한 규모다. **측정 없이 그래프 DB 를 들이면 운영 대상이 하나 늘고
백업·마이그레이션·격리 규칙을 전부 다시 만들어야 한다**(감사 §3.3 이 이미 「저장소 분산」을
위험으로 지적했다).

### 재판정 기준 — 아래 중 **둘 이상**이 관측되면 그때 검토한다

1. 간선 **10만 건** 초과, 또는 한 조직 범위의 활성 간선이 1만 건 초과
2. 대표 질문의 경로 탐색 p95 가 **1.5초** 초과(권한·승인 필터 포함, 서버 실측)
3. 실제 질의의 평균 깊이가 **5홉** 초과 — 얕은 질의는 조인으로 충분하다
4. 한 번의 답변에 필요한 경로 수가 **1,000개** 초과
5. 재귀 CTE 로도 표현 못 하는 질의 유형(가중 최단경로·중심성 등)이 **업무 요구**로 확정

⚠️ 기준을 넘어도 **먼저 인덱스·캐시·질의 계획을 본다.** 이 저장소의 성능 부채는 대부분
저장소 종류가 아니라 «전량 파일 스캔·전건 메모리 로드» 였다(감사 G-c).

---

## 11. 착수 조건과 이 문서의 한계

### 착수 조건(Codex 보정)

**G1-B P0(B01~B05) 완료·커밋 전에는 코드·DB·API 착수 금지.** 현재 생성 앱 데이터 평면
**2.5/7**, I-3 iframe 브리지·I-4 생성기 연동 미완.

그 순서가 옳은 이유를 이 설계로 다시 확인했다 — §5 가 통째로 **G1 의 판정기·토큰 계약 위에
서 있다.** 그것이 굳기 전에 온톨로지 질의 API 를 만들면 잘못된 권한 규칙이 계약에 박히고,
그때는 온톨로지·Host Runtime 양쪽을 다시 고쳐야 한다.

### 구현 직전에 다시 보고할 세 가지 (rev.2 확정 · G1-B P0 완료 후)

이 문서는 **설계 기준선**이고, 아래 셋은 **구현 착수 직전**에 별도로 보고한다.

| # | 산출물 | 왜 지금이 아니라 그때인가 |
|---|---|---|
| ① | **유형 통합 영향 및 롤백 계획**(§7.1 4단계 + 되돌림) | 전수 조사 대상(로더·시드·문서)이 G1-B 작업 중에도 바뀐다 — 그때의 실측이어야 유효하다 |
| ② | **첫 수직 폐루프 객체·관계·허용 조합표**(§7.2) | Codex 의 `기업 경영 의미지도` UX 교차검토 결과가 관계 유형의 이름·방향성을 바꾼다 |
| ③ | **G1-B 정책 결정점 ↔ `ResourceScope` 호출 흐름**(§5) | PDP 의 실제 계약이 확정돼야 어댑터 형태를 정할 수 있다. 지금 그리면 추측이 된다 |

### 이 문서가 하지 않은 것 (정직하게)

- **성능 실측을 하지 않았다.** §10 의 기준은 «언제 재판정할지» 이지 «지금 느리다/빠르다» 가 아니다.
- **자연어 질의 계획(G2-C05)의 설계는 개요뿐이다.** 질문 유형 목록이 확정되기 전에는
  질의 계획기의 형태를 정할 수 없다 — Codex 의 `기업 경영 의미지도` UX 교차검토가 선행이다.
- ~~중복 유형 4쌍의 정본을 고르지 않았다.~~ → **결정 완료**(하이픈형, §7.1). 다만 **이행과
  롤백 계획은 아직**이다(위 ①).
- 대표 수직 질문(「원료 도입 지연이 …」)을 **끝까지 시뮬레이션하지 않았다.** 관계가 0건이라
  지금은 어느 경로도 나오지 않는다 — 그 사실 자체가 §7 선행 과제의 근거다.
- **`ResourceScope` 계약의 필드를 확정하지 않았다.** G1-B04 PDP 가 없는 상태에서 정하면
  그 위에 얹을 때 다시 고쳐야 한다(위 ③).

### 교차검토 요청

- **Codex** — §6 API 이름과 화면 용어(`기업 경영 의미지도`), §5 «경로 단위 격리» 가 UX 로
  성립하는지(가려진 경로를 어떻게 말할 것인가).
- **Antigravity** — §8 후보 근거 품질 기준, §10 재판정 임계값이 업계 기준에 맞는지.
- **Supervisor** — §7 중복 유형 4쌍의 정본 선택, `entity_types.relations` 를 채울 범위.

---

## 12. Codex 교차검토 및 사용자 결정 대행안 (2026-08-13 10:30 KST)

> 검토자: Codex / 상태: **조건부 승인** / 구현 금지는 유지한다.
> 아래 보정사항을 본 설계에 반영한 뒤 G2 설계 기준선으로 채택한다.

### 12.1 결정 1 — 중복 유형 4쌍은 하이픈형을 정본으로 통합한다

다음 네 유형은 운영 바인딩·현행 시드·테스트·주입 우선순위가 사용하는 하이픈형을 정본으로 한다.

| 폐기하지 않고 별칭으로 보존할 ID | 정본 ID |
|---|---|
| `quality_spec` | `quality-spec` |
| `finance_param` | `finance-param` |
| `emission_factor` | `emission-factor` |
| `sensor_spec` | `sensor-spec` |

단, §7의 `master_records.supersedes + aliases`만으로는 유형 통합 이력을 표현할 수 없다.
`master_records.supersedes`는 레코드 버전 계보이고 `aliases`는 `master_code` 별칭이므로,
`type_id` 별칭으로 오용하면 안 된다. 구현 시 `entity_type_aliases(alias_type_id,
canonical_type_id, reason, effective_at)` 또는 동등한 명시적 매핑을 두고 다음을 함께 이행한다.

1. 밑줄형 레코드의 `type_id`를 하이픈형으로 이관하되 삭제하지 않고 백업·대사한다.
2. 기존 조직 `master_domains`, 과거 로더, 시드, 문서의 밑줄형 참조를 전수 조사한다.
3. 외부 입력의 밑줄형은 정본으로 정규화하되 응답·신규 저장에는 하이픈형만 사용한다.
4. 이관 전후 레코드 수·범위 바인딩 수·주입 결과가 보존되는지 검증한다.

### 12.2 결정 2 — 21개 전수를 채우지 않고 첫 수직 폐루프부터 정의한다

첫 구현은 원료 구매·도입계획에서 생산·매출·현금흐름·손익까지 연결하는 데 필요한 유형만
정의한다. 나머지 유형은 억지 관계를 채우지 않고 `UNMODELED`로 명시한다. 빈 배열 `[]`만으로는
「관계가 없음」과 「아직 모델링하지 않음」을 구별할 수 없으므로 완료 판정에 사용하지 않는다.

최소 대상은 원료·공급자·구매/도입계획·선적/통관/운송 이벤트·사업장/공장·공정/BOM·생산계획·
제품·품질규격·외부지표·재무 파라미터·계획계정·KPI다. 이 중 트랜잭션·이벤트는
`master_records`로 복제하지 않고 원천 Snapshot/계약의 식별자를 온톨로지 객체로 참조한다.

### 12.3 보정 1 — `entity_types.relations`는 최종 관계 유형 SSOT가 아니다

기존 M1 문서의 정의대로 이 필드는 **허용 관계 후보**이며, 버전·승인·방향성·역관계·기간을
담지 못한다. 따라서 부트스트랩 입력 또는 호환용 projection으로만 사용한다. G2의 정본은 다음처럼
분리한다.

- `semantic_relation_types`: 관계 유형 ID, 사용자 표시명, 방향성, 역관계, 대칭/전이 여부,
  버전, 승인 상태, 유효기간.
- `semantic_relation_constraints`: 허용 subject/object 유형 조합과 범위·근거 요구조건.
- `semantic_relations`: 승인 후보와 실제 관계 인스턴스.
- `semantic_relation_events`: 변경 이력. 승인 의사결정은 기존 `decision_ledger`와 correlation ID로
  연결하며 두 감사 원장을 서로 다른 진실원본처럼 만들지 않는다.

`entity_types.relations`는 위 정본에서 생성한 읽기용 축약본으로 유지하거나 향후 단계적으로
폐기한다. 21개 JSON을 먼저 수작업으로 채운 뒤 다시 이관하는 작업은 하지 않는다.

### 12.4 보정 2 — 권한 밖 경로의 `blocked` 개수와 사유를 사용자에게 반환하지 않는다

초안의 `blocked.count`와 `SCOPE_OUTSIDE` 사유는 다른 조직 또는 미승인 관계의 존재를 누설한다.
따라서 응답을 다음 두 경우로 분리한다.

- 사용자가 볼 권한은 있으나 현재 선택 문맥 때문에 제외됨: 문맥 제외 건수와 전환 방법을 표시할 수 있다.
- 애초에 권한이 없거나 승인되지 않은 관계: 사용자 응답에서 존재·개수·사유를 모두 숨긴다.
  단건은 404, 목록/경로 질의는 보이는 결과만 반환한다. 상세 차단 사유는 감사 로그에만 남긴다.

즉 예시 응답의 `blocked`는 `context_omitted`로 축소하고, 권한 거부·미승인 건수는 포함하지 않는다.

### 12.5 보정 3 — `project_visibility`를 관계 객체에 직접 적용하지 않는다

`project_visibility`는 프로젝트 메타·소유자·부서 가시성에 특화돼 있고, 일부 문맥 보조 함수는
조회 실패 시 화면을 비우지 않기 위해 fail-open한다. 온톨로지 경로의 보안 판정으로 직접 호출하면
G2의 Fail-closed 계약과 충돌한다.

G1에서 확정한 원칙과 하위 primitive(`resolve_viewing_context`, 조직 계층, scope guard)는
재사용하되, G1-B 정책 결정점 위에 범용 `ResourceScope` 계약을 두고 온톨로지 노드·간선을
그 계약에 어댑트한다. 정책 규칙은 한 곳에 유지하고 프로젝트 전용 데이터 구조는 재사용하지 않는다.

### 12.6 추가 보정 — 공식 관계의 confidence와 버전 유일성

- `confidence`는 `suggested` 후보에만 의미가 있다. 사람이 승인한 공식 관계를 확률값으로
  보이게 하지 않도록 승인 후에는 참고 메타데이터로만 보존하고 사용자 신뢰도처럼 표시하지 않는다.
- 유일성은 모든 상태에 일괄 적용하지 않는다. DRAFT/REJECTED 후보는 공존할 수 있고,
  `APPROVED`이면서 동일 기준시점에 유효한 관계만 하나가 되도록 부분 유일 제약 또는 트랜잭션 검사를 둔다.
- 승인 상태에는 최소 `DRAFT`, `IN_REVIEW`, `APPROVED`, `REJECTED`, `SUPERSEDED`, `RETIRED`를
  구분하고, `EXPIRED`는 유효기간으로 계산한다.

### 12.7 다음 행동

Claude Code는 **코드·DB·API를 변경하지 않고** 본 §12를 반영해 설계 문서만 개정한다. 이어서
G1-B P0(B01~B05)를 완료·커밋한 뒤, 온톨로지 구현 착수 전에 다음 세 가지를 다시 보고한다.

1. 하이픈형 통합 영향 목록과 되돌림 가능한 마이그레이션 계획.
2. 첫 수직 폐루프 대상 객체·관계 유형·허용 조합 표.
3. G1-B 범용 정책 결정점과 온톨로지 `ResourceScope` 어댑터의 호출 흐름.
