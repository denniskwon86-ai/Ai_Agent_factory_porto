# [WEB-0] SQLite 사용처 목록 — PostgreSQL 이관 기준선

> ⚠️ **손으로 고치지 말 것** — `scripts/sqlite_inventory.py --write` 가 만든다.
>
> 시연에서 SQLite 를 쓴다는 결정이 **상용 저장소 결정으로 굳지 않게** 하려고
> 지금 세어 둔다. 나중에 세면 그때는 이미 늘어 있다.

## 요약 — 파일 18개 · 표 71개 · 기동 시 열 추가 9곳

## 파일

| 파일 | 크기 | 표 | 언급하는 모듈 |
|---|---:|---:|---|
| `advisor.db` | 196,608 | 4 | `core/advisor_store.py` |
| `app_data.db` | 36,864 | 2 | `core/app_data_store.py`, `core/app_preview.py` |
| `asset_usage.db` | 20,480 | 2 | `core/asset_usage.py` |
| `auth.db` | 49,152 | 3 | `core/auth.py` |
| `collaboration.db` | 491,520 | 10 | `core/collaboration_store.py` |
| `connectors.db` | 24,576 | 2 | `core/connector_registry.py` |
| `data_preparation.db` | 155,648 | 9 | `core/data_preparation/store.py` |
| `decision_ledger.db` | 36,864 | 1 | `core/decision_ledger.py` |
| `enterprise_context.db` | 229,376 | 12 | `core/enterprise_context/repository.py`, `core/paths.py` |
| `external_intelligence.db` | 61,440 | 4 | `core/external_intelligence.py` |
| `knowledge.db` | 0 | 0 | **(코드에서 이름을 찾지 못함)** |
| `llm_cache.db` | 2,142,208 | 1 | `core/cache_manager.py` |
| `mcp_cache.db` | 12,288 | 1 | `core/mcp_broker.py` |
| `ontology.db` | 73,728 | 5 | `core/ontology_runtime.py` |
| `planning.db` | 102,400 | 8 | `core/planning_model.py` |
| `program_lifecycle.db` | 24,576 | 2 | `core/program_lifecycle.py` |
| `shadow_runs.db` | 20,480 | 1 | `core/shadow_mode.py` |
| `workspace.db` | 65,536 | 4 | `core/release_readiness.py`, `core/workspace_promotion.py` |

## 표

### `advisor.db`

`blueprint_data_requirements`, `consultation_turns`, `consultations`, `solution_blueprints`

### `app_data.db`

`app_datasets`, `app_records`

### `asset_usage.db`

`asset_usage`, `asset_usage_meta`

### `auth.db`

`auth_credential`, `auth_session`, `auth_sse_ticket`

### `collaboration.db`

`app_deliveries`, `decision_actions`, `decision_cases`, `decision_meetings`, `decision_participants`, `publication_distributions`, `publication_reviews`, `publication_versions`, `publications`, `user_app_pocket`

### `connectors.db`

`connectors`, `query_contracts`

### `data_preparation.db`

`baseline_builds`, `calc_execution_approvals`, `dataset_ownership_bindings`, `dataset_snapshots`, `kit_instances`, `kit_registry_versions`, `object_scope_index`, `readiness_evaluations`, `source_bindings`

### `decision_ledger.db`

`decision_ledger_events`

### `enterprise_context.db`

`agent_pack_bindings`, `agent_packs`, `assumption_sets`, `baseline_snapshots`, `competitor_metrics`, `enterprise_entities`, `enterprise_profiles`, `organization_edges`, `organization_node_code_aliases`, `organization_nodes`, `scenario_entities`, `scenario_results`

### `external_intelligence.db`

`external_forecasts`, `external_indicators`, `external_observations`, `external_sources`

### `knowledge.db`

_(표 없음)_

### `llm_cache.db`

`exact_cache`

### `mcp_cache.db`

`mcp_cache`

### `ontology.db`

`semantic_model_contracts`, `semantic_relation_constraints`, `semantic_relation_events`, `semantic_relation_types`, `semantic_relations`

### `planning.db`

`driver_impacts`, `plan_accounts`, `plan_drivers`, `plan_facts`, `plan_submissions`, `scenario_assumptions`, `scenarios`, `simulation_runs`

### `program_lifecycle.db`

`program_status`, `program_status_history`

### `shadow_runs.db`

`shadow_runs`

### `workspace.db`

`release_promotions`, `release_rollbacks`, `workspace_forks`, `workspace_shares`

## ⚠️ 기동 시 열을 더하는 곳 — 이관에서 손으로 옮겨야 한다

이 저장소에는 마이그레이션 도구가 없다. 코드가 기동 때 `ALTER TABLE ADD COLUMN`
으로 열을 더한다. PostgreSQL 로 갈 때 **이 자리들이 전부 이관 대상**이다.

| 위치 | 표 | 열 |
|---|---|---|
| `core/advisor_store.py:186` | `{table}` | `{name}` |
| `core/agent_assets.py:159` | `agent_assets` | `{col}` |
| `core/app_data_store.py:255` | `{table}` | `{column}` |
| `core/auth.py:162` | `{table}` | `{col}` |
| `core/data_preparation/store.py:279` | `object_scope_index` | `{col}` |
| `core/master_data.py:476` | `{table}` | `{col}` |
| `core/org_directory.py:211` | `departments` | `{col}` |
| `core/org_directory.py:218` | `users` | `{col}` |
| `core/planning_model.py:198` | `{table}` | `{col}` |

## 이관에서 특히 조심할 것

- **부분 UNIQUE 인덱스**(`… WHERE status='active'`) — PostgreSQL 에도 있지만
  문법과 계획이 다르다. 멱등을 DB 가 지키던 자리가 여기다.
- **`julianday()` 트리거** — 기간 겹침을 막는 트리거가 SQLite 함수를 쓴다.
  PostgreSQL 에는 없다(`tstzrange` + 배제 제약으로 옮겨야 한다).
- **`executescript()` 의 조기 커밋** — 감싼 트랜잭션을 끊는다. 이관 스크립트가
  같은 가정을 하면 반쪽만 적용된 스키마가 남는다.
- **파일 경계가 곧 격리** — Preview 는 별도 파일이라 «논리 분리» 사고를 피했다.
  한 DB 로 합치면 그 경계가 코드 조건문으로 내려온다(`core/app_preview.py` 머리말).
