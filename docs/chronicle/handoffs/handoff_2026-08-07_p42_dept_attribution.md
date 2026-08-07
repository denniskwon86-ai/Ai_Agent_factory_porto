# 인계 — P4-2 부서 귀속률 0% 원인 규명 (2026-08-07)

> **조사 전용 세션. 코드·데이터 변경 0건.** 읽기 전용 조회만 했습니다.
> 워크트리(`.claude/worktrees/vibrant-moore-a92165`)에는 초기 커밋(README)뿐이라
> 실제 조사는 메인 작업 디렉터리에서 수행했습니다.

## ★ 한 문장

`ProjectState.owner_dept_id` 는 **선언만 되어 있고 값을 심는 경로가 주경로에 없으며**,
배선을 고쳐도 지금은 안 채워집니다 — **진실원본 `project_meta.json` 55개 중 53개가 비어 있습니다.**

---

## 1. 실측 (재현 가능)

| 대상 | 결과 |
|---|---|
| `data/llm_call_log.jsonl` | 1,133건 / `owner_dept_id` 비어 있음 **1,133건 (귀속률 0%)** |
| ↳ 2026-07-25~07-27 | **972건** — `owner_dept_id` **키 자체가 없음**(필드 도입 전) · `project_id` 도 없음 |
| ↳ 2026-07-29~08-07 | **161건** — 키는 있고 값이 `""` · `project_id` 는 있음 |
| `projects/*/project_meta.json` | 55개 중 값 있음 **2개**(`MEGA_02_quality`=quality, `MEGA_02_sales`=sales) |
| `projects/*/latest_state.json` | 55개 **전부** `owner_dept_id=""` |
| `ownership` 미러 (project 행) | 50행 중 디스크 실재 **5행** · 그 5행은 meta 와 **불일치 0건** |
| `departments` (master.db) | 12개 부서 · `scope_node_id` 채워진 부서 11개 |
| `users.primary_dept_id` | 채워져 있음 (`hikwon@lsmnm.com`=hq, `hikwon_1`=production_battery …) |

### 소급 귀속 불가 — 근거

161건의 `project_id` 는 `test_a1_unitconv_canary1/2/3`·`workspace`·`snap_probe` 인데
그 프로젝트들의 `meta.owner_dept_id` 가 전부 `""` 라 **조인으로 되찾을 수 있는 레코드 0건**.
972건은 `project_id` 조차 없어 프로젝트에도 못 붙습니다.

→ `core/org_operations.py:100` 의 `coverage.note` 는 **유지**가 맞습니다.
   다만 지금 문구는 두 종류를 구분하지 않습니다. 「필드 도입 전 972건 / 기록 누락 161건」으로
   나누면 더 정확합니다.

---

## 2. 코드 실태

### 읽는 곳 3 · 채우는 곳 0(주경로)

**선언**: `state_models.py:102` — 저장소 전체에서 `state_models.py` 내 출현은 이 1건뿐.

| 읽는 곳 | 용도 | 성격 |
|---|---|---|
| `core/llm_gateway.py:333` | 비용 텔레메트리 | 계측 |
| `core/quality_telemetry.py:127` (+`StateRef` 146) | 품질 텔레메트리 | 계측 |
| `core/knowledge_base.py:764` | **RAG 과거사례 부서 필터** | ★ 기능 |

**채우는 곳**: 비테스트 코드에서 `state` / `project_state_payload` 에 이 키를 대입하는 곳 **0건**.
모든 쓰기는 `project_meta.json`(진실원본) · `ownership` 미러 · `advisor_store` · `data_catalog` 로 갑니다.

**유일한 간접 경로**: `api/routes/advisor_control.py:486` — Blueprint→프로젝트 부트스트랩이
`latest_state.json` 에 `owner_dept_id` 를 직접 씁니다 → `_restore_accumulated_from_disk` 가 복원.
그러나 이 경로로 만들어진 프로젝트가 디스크에 **0건**이라 실제로 동작한 적이 없습니다.

### 순환 구조

```
state 가 비어 있다  →  latest_state.json 이 빈다  →  복원이 아무것도 못 채운다  →  state 가 비어 있다
```

`_ACCUMULATED_FIELDS`(`api/routes/factory_control.py:135`)에 `owner_dept_id` 가 있는 것은
**유실 방지**용이지 **최초 주입**이 아닙니다 — 주석의 "스프린트 사이에 유실되면 안 된다"는
이미 채워진 값을 전제합니다.

### `start_sprint` 주입 4필드에 소유권이 빠져 있다

`api/routes/factory_control.py:968` `start_sprint` 가 권위 원본에서 주입하는 것:

| 라인 | 필드 |
|---|---|
| 977 | `template_id` |
| 979 | `knowledge_pack_ids` |
| 981 | `master_domains` |
| 983 | `mcp_live_grounding` |
| — | **`owner_dept_id` 없음** |

`_read_project_ownership` 는 이 경로에서 호출되지 않습니다(목록 필터·릴리스 등록에서만 쓰임:
1438 · 1496 · 1551). `create_project`(539–546) → `provision_project` → `_write_project_meta`
→ `_sync_project_ownership` 는 전부 **파일과 미러**만 건드리고 state 근처에 가지 않습니다.

---

## 3. 정본 — **한 값만 고르면 두 경우 다 틀린다** (⚠️ 결정 대기)

`departments` 실측:

```
hq, accounting, finance, logistics, marketing,
procurement, production, quality, sales   →  node_41402723bc90 (LS_MNM)   ← 9개가 한 노드
production_battery                        →  node_36c1c7c797e0 (MNM_BATTERY)
production_copper                         →  node_a56a75e63b10 (MNM_COPPER)
t_admin                                   →  (매핑 없음)
```

- **`node_id` 만 싣는 경우**: 9개 부서가 `LS MnM` 한 줄로 뭉칩니다.
  「(미상) 한 줄」이 「LS MnM 한 줄」로 바뀔 뿐 **부서별 비용 통계는 여전히 없습니다.**
  D-018 이 적은 "여러 부서가 하나의 LS_MNM 범위에 매핑된다"가 여기서는 손실로 나타납니다.
- **`dept_id` 만 싣는 경우**: D-018 의 경고 그대로 — 조직개편·개명으로 과거 비용 해석이 끊깁니다.
- **⚠️ 의미를 `node_id` 로 바꾸는 것은 텔레메트리 변경이 아닙니다.**
  `core/knowledge_base.py:764` 가 이 필드를 `org_directory.get_department()` 의 키로 써서
  `path` 조상 체인을 만들고 Chroma `$in` 필터에 넣습니다. `node_id` 를 넣으면
  `get_department` → `None` → 체인 `[node_id]` → 매칭 0건 →
  **과거사례 주입이 오류 없이 조용히 0건**이 됩니다. `_ownership_visible` 의
  `p.scope.readable_dept_ids` 도 같은 계약입니다.

### 권고안 (D-019 로 올릴 것 — 단독 확정하지 않았음)

두 축을 **함께** 싣습니다. D-018 의 예외가 아니라 적용입니다.

| 로그 필드 | 값 | 근거 |
|---|---|---|
| `owner_dept_id` | `departments.dept_id` (기존 계약 그대로) | 권한 주체 축. RAG·권한 필터와 같은 키여야 두 로그가 붙는다 |
| `owner_scope_node_id` (신규) | **기록 시점의** `departments.scope_node_id` | D-018 정본. 부서가 사라지거나 개명돼도 해석 가능 |

화면은 `dept_id` 로 세고 `node_id` 로 롤업합니다.
⚠️ `node_id` 는 **기록 시점 스냅샷**임을 명시해야 합니다 — `update_department` 가
`scope_node_id` 를 새 버전으로 개정하므로, 나중 조회로 재계산하면 과거 비용이 소급해서 움직입니다.

---

## 4. 다음 행동 (정본 확정 후)

| # | 할 일 | 선행 조건 |
|---|---|---|
| 1 | `start_sprint` 977행 옆에 `template_id` 와 **같은 패턴**으로 소유권 주입 (1줄) | D-019 확정 |
| 2 | 미태깅 53개 프로젝트 백필 **여부 결정** | ⚠️ 만든 사람을 모르는 프로젝트에 부서를 추정해 넣으면 그것이 곧 「틀린 부서로 귀속된 비용 통계」입니다. **미태깅으로 남기고 note 로 드러내는 편을 권합니다.** |
| 3 | `project_id` 없는 호출(상담사·지식허브)용 **별도 축** — 호출자 principal 의 `primary_dept_id` | 사용자 표는 이미 채워져 있음 |

### ⚠️ 화면 담당(Codex)에게 넘길 것

`frontend/src` 전체에서 `telemetry/orgs` 를 호출하는 코드가 **0건**입니다.
`coverage.note` 는 API 응답에만 있고 **아직 화면에 뜨지 않습니다.**
"소급 불가라는 사실이 화면에 남아야 한다"는 요구가 지금은 충족되지 않은 상태입니다.

---

## 금지 범위 (이어받는 세션이 하면 안 되는 것)

- `owner_dept_id` 에 `node_id` 를 넣는 것 — RAG 과거사례가 **조용히** 0건이 됩니다.
- 값을 급히 채우는 것 — 정본(D-019) 확정 전.
- 53개 미태깅 프로젝트에 부서를 추정해서 백필하는 것.
- `coverage.note` 를 제거하거나 귀속률을 0 이 아닌 값으로 보이게 만드는 것.
- 운영 DB(`data/master/master.db`, `data/enterprise_context.db`)에 쓰기 탐침.

## 교대 체크포인트

- **변경 = 없음.** 이 문서만 추가.
- **검증 = 읽기 전용 조회만.** 테스트 미실행(코드 변경이 없음).
- **재개 지점 = D-019(정본) 결정 → `start_sprint` 주입 배선.**
