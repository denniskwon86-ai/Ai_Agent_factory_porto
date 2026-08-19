# Claude Code 단독 실행 — Wave F 재개 인수인계

> 작성자: Claude Code / 2026-08-18 23:10 KST (F-0 완료 반영 2026-08-19 01:40 KST)
> 대상: **다른 Claude Code 세션(다른 계정 포함)** 이 이 저장소를 이어받아 Wave F-1 부터 계속한다.
> 상위 정본: [`CLAUDE_SOLO_I4_BDR_MVP_EXECUTION_HANDOFF_2026-08-16.md`](CLAUDE_SOLO_I4_BDR_MVP_EXECUTION_HANDOFF_2026-08-16.md)
> — **이 문서는 그것을 대체하지 않는다.** 상위 정본이 «무엇을 만드는가» 이고, 이 문서는
> «지금 어디까지 왔고, 다음에 손대면 어디가 부서지는가» 다.

---

## 0. 30초 요약

```text
Wave A~E 완료 · Wave F-0(계약 물질화) 완료.  다음은 F-1 (I-4 6 Preview DB).
전체 회귀 4,055건 통과 · 실패 0.

⚠️ F-1 을 시작하기 전에 반드시 읽을 것:
   §4.1(F-0 이 무엇이었는지 — 원래 기술이 틀렸다) · §4.1b(잘못된 이유로 통과하던 시험)
   §4.2(아직 «없는» 것) · §6(이 세션이 실제로 다친 자리)
```

---

## 1. 재개 절차 — 순서를 지킨다

1. **작업 디렉터리**: `C:\WorkSpace\gemini_agent_team_verG` · 브랜치 `dev`
2. **파이썬**: `venv/Scripts/python.exe` (Python 3.14). 시스템 파이썬을 쓰지 않는다.
3. `.agents/AGENTS.md` 를 읽는다 — 역할 SSOT. 내 담당은 **백엔드 설계·구현·검증**이다.
4. `.agents/TEAM_BOARD.md` 의 **최상단 항목**을 읽는다.
   `[BDR-WAVE-F0-20260819-01]` 이 마지막 기록이다.
   ⚠️ 이 파일은 **커밋돼 있지 않다** — 남의 미커밋 작업이 얹혀 있다(§7.1).
5. 상위 정본의 §10(Wave F)·§14(커밋 규율)를 읽는다.
6. 전체 회귀를 한 번 돌려 기준선을 확인한다(§5).

---

## 2. 지금까지 무엇이 만들어졌나

### 커밋 (오래된 것 → 최신)

| 커밋 | 무엇 |
|---|---|
| `c60ed175e` | I-4 4c-2 — 검토 요청을 원장에 한 건만 열고, 결정을 그 요청에 잇는다 |
| `6eb35e4c8` | I-4 4c-3·4c-4 — 계약 승인 전용 문, 일반 재개로는 못 지나감 |
| `5837fd326` | I-4 4c-5·4c-6 — 계약 노드 배선, 레거시는 그 노드에 닿지 않음 |
| `42652f3eb` | I-4 4c-7 — 분류를 믿지 않고 «실행되는가» 를 본다 |
| `9c1e76db7` | I-4 5단계 — Typed SDK Adapter + 정적 검사 |
| `345acdb77` | BDR-2 — Kit Instance · Source Binding (ACTIVE 유일성은 DB 부분 유일 인덱스) |
| `a73860799` | BDR-3 — L0 파일 Snapshot MVP |
| `ca162d167` | **BDR-5·6** — 결정론적 준비도 · Provider Dispatch |
| `0e32906db` | 이 인계 문서 |
| `(F-0)` | **Wave F-0** — 계약 물질화(§4.1). 승인이 실제로 데이터셋을 만든다 |

### Wave E 가 만든 것 (`ca162d167`)

```text
core/data_preparation/readiness.py      결정론적 준비도 판정 엔진 (저장소를 모른다)
core/host_runtime_provider.py           Provider Dispatch
tests/test_data_readiness.py            41건
tests/test_provider_dispatch.py         44건
```

| 바뀐 파일 | 무엇이 바뀌었나 |
|---|---|
| `api/routes/data_preparation_control.py` | `GET /instances/{id}/readiness` |
| `api/routes/app_data_runtime.py` | 읽기 3·쓰기 3 경로에 Dispatch 배선 |
| `core/app_data_store.py` · `core/app_data.py` | `enterprise_contract_key` · `kit_instance_id` 열 |
| `core/data_preparation/kit_registry.py` | `outputs` 파서·검증 |
| `core/data_preparation/models.py` | `QUARANTINE_QUALITY` / `QUARANTINE_RECONCILIATION` 코드 |
| `docs/data-kits/afs_materials_procurement_v1.kit.json` | 산출물 3종 선언 |

---

## 3. 핵심 설계 판단 — 바꾸기 전에 이유를 읽을 것

### 3.1 준비도 상태 어휘 — 정본이 갈렸던 자리

상세설계 §10.1 과 솔로 인수인계 §9.1 의 이름이 다르다. **인수인계 9상태를 정본**으로 삼았다.

```text
NOT_CONFIGURED · SOURCE_CONFIGURED · DATA_AVAILABLE · QUALITY_FAILED
RECONCILIATION_FAILED · APPROVAL_PENDING · READY · STALE · UNAVAILABLE
```

설계서 어휘와의 대응은 `core/data_preparation/readiness.py` 머리말에 적어 뒀다.
`NOT_APPLICABLE`(불필요 승인)은 승인 흐름이 없어 MVP 밖이며, **`READY` 로 접지 않고 없는
상태로 남겼다** — 접으면 필요 없다고 판단한 데이터가 준비된 데이터로 세어진다.

⚠️ 이 어휘는 `tests/test_data_readiness.py::test_the_state_vocabulary_is_pinned_literally`
가 **문자열 그대로** 못 박고 있다. 바꾸려면 그 시험을 먼저 고치고, 왜 바꾸는지 남긴다.

### 3.2 Provider Dispatch — 앱은 출처를 모른다

```text
source_intent          → provider              → 어디서 읽는가
AFS_NATIVE             → AFS_NATIVE            → app_data.db
ENTERPRISE_READ        → FILE_SNAPSHOT         → 승인된 data_preparation Snapshot
EXTERNAL_REFERENCE     → CONNECTOR_QUERY       → NOT_YET_SUPPORTED (503)
DERIVED_READ           → DERIVED               → NOT_YET_SUPPORTED (503)
(빈 문자열)             → AFS_NATIVE            → 레거시 결속 — 폴백이 아니라 «선언된 사실»
(그 밖의 값)            → ✗ 없음                → 503 (우리 DB 로 폴백하지 않는다)
```

앱에 나가는 것은 **`as_of` 와 `stale` 둘뿐**이다. Provider 종류·결속 id·내부 경로·SQL·
자격증명은 표면 밖이다.

**쓰기는 `AFS_NATIVE` 하나뿐**이다(`WRITABLE_PROVIDERS`). 나머지는 403.

★ [F-0] `source_intent`·`enterprise_contract_key`·`kit_instance_id` 는 **계약 물질화가
  채운다**(`core/contract_materializer.py`). 시험이 결속 표를 직접 UPDATE 하던 방식은
  걷어냈다 — 그 방식으로는 「계약이 그 값을 채우지 않는다」를 영원히 못 잡는다.

### 3.3 실패는 404 가 아니라 503 이다

⚠️ Dispatch 실패에 404 를 주면 앱은 「그런 것은 없다」로 읽고 **화면에서 그 표를 지운다.**
「지금은 못 읽는다」는 503 이고, 앱이 할 일은 지우기가 아니라 다시 묻기다.
`tests/test_provider_dispatch.py::test_a_source_that_breaks_after_the_app_was_made_is_not_an_empty_table`
이 못 박는다.
⚠️ [F-0] 이름이 바뀐 이유: 이제 **원천이 없으면 앱이 아예 만들어지지 않으므로**,
  현실적인 상황은 「만든 뒤 인증이 회수된다」다.

### 3.4 범위는 «증명에 봉인된 값» 으로 대조한다

`_dispatch()` 는 `proof.tenant_id` / `scope_node_id` / `entity_mode` 를 넘긴다.
⚠️ **결속 표의 값으로 비교하면 자기 자신과 비교하는 것이라 언제나 통과한다.**
이 세션에서 실제로 그 결함이 있었다(§6.1).

---

## 4. 지금 «없는» 것 — Wave F 선행 과제

### 4.1 ~~계약 컴파일러가 `enterprise_contract_key` 를 채우지 않는다~~ → **완료(F-0)**

> ⚠️ **이 절의 원래 기술은 틀렸다.** 「두 열을 안 넘긴다」로 적었는데, 실제로는
> **승인된 계약을 데이터셋으로 만드는 단계 자체가 운영 코드에 없었다.**
> 그 사실은 다음으로 확인됐다 — `create_dataset`/`bind_release`/`adopt_dataset` 에
> `allowed_actions` 를 넘기는 곳이 **시험뿐**이었고, 운영 `app_data.db` 에는
> `app_release_dataset_bindings` 표가 **존재조차 하지 않았다**(계약 경로를 지난
> 릴리스가 한 건도 없다는 뜻). 승인 뒤 하는 일은 타입 어댑터 파일 쓰기 하나였다.
>
> **그 상태는 오류를 내지 않았다.** 봉인은 「그때와 같은가」에 답할 뿐 「무언가
> 생겼는가」에는 답하지 않는다. 60/60 프로젝트가 LEGACY_OFF 였던 이유가 이것이다.

**F-0 에서 만든 것**

| 무엇 | 어디 |
|---|---|
| 계약 물질화기 | `core/contract_materializer.py` (신규) |
| 게시 경로 배선 | `api/routes/factory_control.py::_materialize_contract_for_release` |
| 결속 표까지 두 열 전달 | `core/app_data.py` — `create_dataset`/`bind_release`/`adopt_dataset`/`_bind_in_tx` |
| `ENTERPRISE_READ` 지원 개방 | `core/app_runtime_contract.SOURCE_INTENT_DECISION` |
| 계약키 필수 검증 | `core/host_contract_compiler._compile_datasets` |
| 시험 | `tests/test_contract_materializer.py` (35건) |

**설계 판단 셋 — 바꾸기 전에 읽을 것**

★★★ ① **전부 아니면 아무것도.** `plan()` 이 먼저 전부 해석하고 그 뒤에야 쓴다.
  다섯 중 셋만 만들어지면 앱은 둘을 「없는 것」으로 보고 화면에서 지운다.

★★★ ② **Kit Instance 를 못 박는다.** 물질화 시점에 (tenant, scope, entity_mode,
  계약키) 로 해석해 `kit_instance_id` 를 적는다. 매 요청 해석하면 앱이 보는 원천이
  조용히 바뀐다. 못 박은 값은 Dispatch 가 **매 요청 범위 대조**한다(§3.4) — 못 박기와
  대조는 **둘 다** 있어야 한다. 못 박기만 하면 낡고, 대조만 하면 흔들린다.

★★★ ③ **애매하면 만들지 않는다.** 후보 0개는 「그 데이터를 줄 원천이 이 조직에
  없다」, 2개 이상은 「어느 것인지 우리가 정할 일이 아니다」. 「첫 번째를 고른다」는
  임의이고 **조용하다.**

**부수 효과 — 알고 있어야 할 것**

⚠️ **원천이 준비되지 않으면 앱이 아예 만들어지지 않는다.** 게시 시점에 활성 원천이
  없으면 물질화가 실패하고 `contract_materialization.state = "FAILED"` 로 릴리스에
  기록된다(게시 자체는 막지 않는다 — 산출물은 이미 있고, 못 꺼내게 하는 것이 더 큰
  손해다). 이것은 의도된 동작이다: 만들어진 뒤 런타임에서 막히면 사용자는 앱이
  고장 났다고 생각한다.

### 4.1b ⚠️⚠️ F-0 에서 드러난 «잘못된 이유로 통과하던 시험»

`test_enterprise_read_cannot_have_input_actions`(이중 입력 게이트 ①)는 **게이트가
아니라 문구 때문에** 통과하고 있었다. 컴파일러가 `ENTERPRISE_READ` 를 「아직 물질화
불가」로 먼저 막았고, 그 안내문에 마침 「입력 화면」이라는 말이 들어 있었다.
옆 시험(`test_stored_contract_with_enterprise_read_writes_is_invalid`)의 주석이
그 사실을 이미 적어 뒀지만, 아무도 그것이 **이 시험을 무력화한다**는 뜻으로 읽지 않았다.

출처를 열자 우연한 방벽이 사라졌고, 컴파일러가 `role_source_errors` 를 **부르지
않고 있다**는 사실이 드러났다. 지금은 부른다.

★ 교훈: **막는 시험이 통과할 때, 무엇이 막았는지 확인한다.** 사유 문자열이 우연히
  겹치면 게이트가 없어도 초록이다.

### 4.2 ⚠️ 증명이 Snapshot 지문을 봉인하지 않는다

증명(`core/app_capability_token.py`)이 봉인하는 것은
`manifest_fingerprint` · `contract_fingerprint` · `materialization_fingerprint` 이고,
**Snapshot 지문은 들어 있지 않다.**

**뜻**: 인증판이 교체돼도 기존 프레임이 무효화되지 않고 다음 요청부터 새 판을 읽는다.
읽기 전용이라 데이터가 깨지지는 않지만 **「그 화면이 어느 판을 보고 있었나」에 답할 수 없다.**

Wave F 의 「지문 변경 시 stale frame 무효화」에서 함께 다룬다.

### 4.3 문서화된 잔여물 (Supervisor 승인 하에 연기)

- `tests/test_quality_outcomes.py` 가 조직 0건 상태에 의존한다.
- 실제 계정 문자열이 8개 파일에 남아 있다(P1 정리).

---

## 5. 검증 절차 — 그대로 따라 할 것

### 5.1 전체 회귀

```bash
venv/Scripts/python.exe -m pytest tests/ -p no:warnings --no-header -q --junit-xml=reg.xml
```

⚠️ 이 저장소는 `-q` 요약줄을 출력하지 않는다. 건수는 junit XML 에서 읽는다.

```bash
venv/Scripts/python.exe -c "import xml.etree.ElementTree as ET; a=(lambda r:(r[0] if r.tag=='testsuites' else r).attrib)(ET.parse('reg.xml').getroot()); print(a['tests'], a['failures'], a['errors'], a['skipped'])"
```

**현재 기준선: 4,055건 · 실패 0 · 오류 0 · 건너뜀 1.** 소요 약 9분.

### 5.2 운영 불변식 — 회귀 뒤에 반드시 확인

```bash
venv/Scripts/python.exe -c "import sqlite3,os; c=sqlite3.connect('file:data/decision_ledger.db?mode=ro',uri=True); print('ledger', c.execute('SELECT COUNT(*) FROM decision_ledger_events').fetchone()[0]); print('dp.db', os.path.exists('data/data_preparation.db')); print('raw', os.path.exists('data/data_preparation'))"
```

기대값: `ledger 0` · `dp.db False` · `raw False`.
그리고 `git status --porcelain data/ projects/` 에 **새 항목이 없어야** 한다.

⚠️ 원장 표 이름은 `decision_ledger_events` 다(`decision_events` 가 아니다).

### 5.3 변이 검사 — **반드시 폐기 워크트리에서**

```bash
git worktree add --detach "$SCRATCH/mut_x" HEAD
# 바꾼 파일들을 워크트리로 복사한 뒤, 한 건씩 변이 → pytest → 원복
git worktree remove "$SCRATCH/mut_x" --force && git worktree prune
```

**메인 작업트리에서 격리 제거 변이 검사는 영구 금지다**(사용자 지시). 과거에 그렇게
해서 운영 원장을 오염시켰다.

변이 스크립트 본은 이 세션의 스크래치패드에 있었다(휘발). 형식은 단순하다 —
`(이름, 파일, 원본 문자열, 바꿀 문자열)` 목록을 돌면서 하나씩 치환하고 pytest 를
돌린 뒤 되돌린다. `src.count(old) != 1` 이면 **SKIP 이 아니라 실패로 센다**(대상이
바뀌었는데 조용히 넘어가면 그 변이는 검사되지 않은 채 «통과» 로 보인다).

---

## 6. 이 세션이 실제로 다친 자리 — 같은 실수를 반복하지 말 것

### 6.1 「조용한 거짓말」이 또 나왔다 (Wave E)

Dispatch 가 **조직 범위를 대조하지 않고 있었다.** 그런데 내가 처음 쓴 시험이 그것을
**통과시켰다** — 타 범위에 판을 만들지 않아서 「범위가 달라 막힘」과 「판이 없어 막힘」이
똑같이 503 이었다.

교훈 두 가지:

- **대조군이 진짜 대조군인지 먼저 증명한다.** 「막혔다」를 확인하는 시험은, 통제를
  지웠을 때 **반드시 통과해야** 의미가 있다.
- **여러 필드를 한꺼번에 어긋내지 않는다.** 셋을 동시에 틀리게 하면 판정이 그중 하나만
  봐도 통과한다. 실제로 `tenant_id` 만 결속 표에서 가져오는 변이가 살아남았다.
  → `test_each_scope_field_is_compared_against_the_proof` 가 셋을 하나씩 본다.

### 6.1b 「막는 시험」이 문구 때문에 통과하고 있었다 (Wave F-0)

§4.1b 참조. 이중 입력 게이트 시험이 **게이트가 아니라 안내 문구의 우연한 단어 겹침**
으로 통과했다. 옆 시험의 주석이 그 사실을 이미 적어 뒀는데도 아무도 「이 시험이
무력화됐다」로 읽지 않았다.

★ **막는 시험이 통과할 때, 무엇이 막았는지 확인한다.**

### 6.1c 손으로 적은 계약이 스키마를 네 번 어겼다 (Wave F-0)

시험 픽스처의 계약을 손으로 적었더니 `runtime_contract_version` 누락 → `purpose`
빈 값 → `approval` 필드명 오류 → `decision_ledger_id` 누락 순으로 게이트가 막았다.
**계약은 손으로 적지 말고 `compile_contract` 로 만든다** — 시험만 아는 계약 모양이
생기는 것도 「시험만 아는 배선」과 같은 병이다.

★ 반대로 읽으면: **계약 게이트가 실제로 일하고 있다**는 증거이기도 하다.

### 6.2 변이 검사가 놓친 네 건과 그 처리 (Wave E)

| 놓친 변이 | 무엇이 안 잡혔나 | 처리 |
|---|---|---|
| 인증판을 목록 마지막으로 고른다 | 인증판이 **둘 이상**인 경우를 시험한 적이 없었다 | 새 판을 목록 앞에 둔 시험 |
| 원천 저장소 장애를 빈 목록으로 | 앱 응답이 둘 다 503 이라 구별 불가 | **감사 기록**을 검사 |
| Dispatch 사유를 앱에 그대로 | 성공 응답만 봤고 **오류 응답**은 안 봤다 | 오류 본문 누출 검사 |
| `sort_keys=False` | 호출부가 이미 정렬된 키로 payload 를 만들어 **구조상 관측 불가** | 가짜 시험을 짓지 않고 사유를 코드 주석에 기록 |

★ 마지막 줄이 중요하다. **관측 불가한 변이에 억지 시험을 붙이지 않는다.** 왜 안 잡히는지와
왜 코드를 남기는지를 적는 편이 정직하고, 다음 사람이 그 자리를 다시 의심할 수 있다.

### 6.3 셸을 거친 소스 편집이 파일을 부순 적이 세 번 있다

- `\b` 가 백스페이스(`\x08`)로 바뀌어 정규식 3개가 조용히 매칭되지 않았다.
- `\x00` 이 **리터럴 NUL** 로 박혀 모듈 전체가 못 읽히게 됐다.
- 비 ASCII `bytes` 리터럴이 SyntaxError 를 냈다.

→ **인용부호·이스케이프가 섞인 본문은 heredoc 대신 파이썬 스크립트 파일로 쓴다.**

### 6.4 JSON 을 재직렬화해 diff 를 133행으로 부풀린 적이 있다

`json.dump` 로 키트 문서를 다시 쓰면 서식이 통째로 바뀐다. **텍스트 삽입**으로 필요한
부분만 넣어라(11행이면 될 일이었다).

### 6.5 픽스처 기본값이 시험을 무력화한 적이 여러 번 있다

`def _resolve(binding=None)` 에서 「명시한 `None`」과 「기본값」을 구분하지 못해,
«결속 없음» 시험이 조용히 «결속 있음» 을 검사했다. → `_UNSET = object()` 센티널.

---

## 7. 작업트리·커밋 규율 — 반드시 지킬 것

### 7.1 커밋하지 않은 남의 작업이 있다

`git status` 에 다음이 **이 세션 시작 시점부터 이미** 있었다. **내 커밋에 넣지 않았다.**

```text
 M .agents/AGENTS.md
 M .agents/TEAM_BOARD.md                       ← 2,408행 삭제(히스토리 아카이브 분리)
 M docs/data-kits/README.md
 M docs/design_manufacturing_management_ontology_2026-08-13.md
?? .agents/archive/  ?? docs/archive/          ← 위 삭제분의 보관처(추적되지 않음)
?? docs/product-brochure/  ?? docs/product-feature-guide*/  ?? output/  ?? tmp/
?? data/app_data.db.bak_test_pollution_20260813_114845  ?? data/archive/
```

⚠️ **`.agents/TEAM_BOARD.md` 를 단독으로 커밋하면 히스토리 2,408행이 사라진다** —
그 내용은 아직 **추적되지 않는** `.agents/archive/` · `docs/archive/` 에만 있다.
아카이브 작업을 한 팀원이 **아카이브 파일과 함께** 커밋해야 한다.

이 세션의 Wave E TEAM_BOARD 기록(`[BDR-WAVE-E-20260818-01]`)은 **작업 트리에만** 있고
커밋되지 않았다. 다음 세션이 그 항목을 못 보면 이 문서가 대신한다.

### 7.1.1 ⚠️ origin 에 없는 문서들 — 새로 clone 하면 보이지 않는다

`docs/handoff/` 아래 다음 문서들이 **추적되지 않은 상태**로 로컬에만 있다.

```text
DECISION_LEDGER_FORENSIC_MANIFEST_20260817.md      원장 오염 사고 포렌식 매니페스트
PARALLEL_INTEGRATION_EXECUTION_HANDOFF_2026-08-15.md
MVP_INT_20260815_01_GATE_EVIDENCE.md
MVP_INT_20260816_02_GATE1_REAUDIT.md
```

첫 번째는 Gemini Antigravity 와 공동 작성분이고 나머지는 통합 작업분이라 **내가 커밋
범위에 넣지 않았다.** 같은 머신에서 이어받으면 그대로 보이지만, **새로 clone 한 세션은
이 문서들을 볼 수 없다** — 필요하면 원 작성 주체에게 커밋을 요청한다.

이 문서(`CLAUDE_SOLO_WAVE_F_RESUME_HANDOFF_2026-08-18.md`)는 커밋·push 돼 있으므로
어느 세션에서도 보인다.

### 7.2 스테이징은 언제나 경로 명시

`git add -A` · `git add docs` 금지. 과거에 남의 파일을 쓸어 담은 적이 있다.
커밋 전 `git diff --cached --stat` 로 **본인 파일만** 확인한다.

### 7.3 원격

`origin` = `https://github.com/denniskwon86-ai/Ai_Agent_factory_porto.git`
**사용자의 명시 지시 없이 fetch·pull·push 하지 않는다.** 이 문서를 만든 시점에
사용자가 push 를 지시했고, 8커밋 + 이 문서를 push 했다.

---

## 8. 절대 하지 말 것 (사용자 지시 · 누적)

| 금지 | 왜 |
|---|---|
| 메인 작업트리에서 격리 제거 변이 검사 | 과거에 운영 원장을 두 번 오염시켰다 |
| 운영 DB에 쓰기 탐침 | 「무효 payload 일 예정」이라는 판단이 세 번 틀렸다 |
| `git add -A` / 디렉터리 통째 staging | 남의 미커밋 작업을 쓸어 담는다 |
| 지시 없는 `origin` fetch·pull·push | — |
| 조직 0건 상태 사용(`is_bootstrap()` 검증 외) | 권한 시험이 거짓 초록이 된다 |
| 승인 없이 LLM 경로 실행 | 비용·비결정성 |
| 실제/데모 계정을 새로 만드는 것 | 예시 계정은 `hikwon@lsmnm.com` **하나만** |
| 실패하는 기준선을 커밋해 다음 단계로 넘기는 것 | — |
| `except: pass` 또는 경고 후 운영 경로 폴백 | — |

---

## 9. Wave F — 다음에 할 일

상위 정본 §10 을 정본으로 삼되, 순서는 다음과 같다.

### ~~F-0 (선행) 계약 컴파일러 → Dispatch 배선~~ → **완료**

§4.1 참조. 승인된 계약이 실제로 데이터셋을 만든다. 변이 23/23 포착, 전체 회귀 4,055건.

⚠️ 남은 조각 하나: 물질화는 **게시 시점**에 돈다. Preview(F-1)·ACTIVE 승격(F-2)이
  각자 언제 물질화를 다시 돌릴지는 그 단계에서 정한다 — 지금은 게시 하나뿐이다.

### F-1 = I-4 6 — Release Candidate · Preview DB · Preview Proof

- Preview DB **물리 분리**
- Candidate 만 Preview proof 발급
- `SYNTHETIC_TEST` 만 사용
- Preview/운영 proof audience 교차 사용 **양방향** 차단
- 파일 Snapshot 은 시연용 복제/참조 정책을 명시하고 운영 기준선으로 승격하지 않음

### F-2 = I-4 7 — ACTIVE 원자 승격

- 계약·정적검사·Review·물질화·**Snapshot Readiness** 를 한 번 더 검증
- ACTIVE 승격과 바인딩 전환의 **원자성**
- 실패 시 이전 ACTIVE 보존
- 실행 가능한 App-in-App 의 계약 누락 차단
- **§4.2 (Snapshot 지문 봉인) 을 여기서 함께 처리한다**

### F-3 = I-4 8 — 종단 카나리

```text
업무키트 선택 → 계약 합산·승인 → 데이터셋 물질화
→ 파일 Snapshot read + Native memo write → Preview → ACTIVE → 새 세션 실행
```

**구조적으로 분리된 DB 와 fresh worktree 를 쓴다. 운영 DB 에 카나리 쓰기 금지.**

### Gate F

- 생성→Preview→ACTIVE→실행 완주
- 읽기·쓰기 허용/거부 **양쪽 표본**
- 계약·물질화·binding·snapshot 변경 시 stale 차단
- 운영 DB 지문 불변
- 전체 회귀·프론트 빌드·브라우저 카나리 통과

⚠️ 프런트 타입체크는 **`tsc -b`** 로 한다. `-p tsconfig.json` 은 0개 파일을 검사하고
조용히 통과한다(실제로 두 번 속았다).

### 이후

Wave G(BDR-7 Baseline · G2 최소 연결 · G4 최소 계산 · 의사결정),
Wave H(최소 화면 7종 · Demo Reset · 시연 안정화).

---

## 10. 진척

```text
Wave A~D (I-4 4c · 5 · BDR-2 · BDR-3)   ██████████  완료
Wave E   (BDR-5 준비도 · BDR-6 Dispatch) ██████████  완료 · Gate E 5/5
Wave F-0 (계약 물질화)                    ██████████  완료 · 변이 23/23
Wave F   (I-4 6 · 7 · 8)                 ░░░░░░░░░░  미착수 ← 여기부터
Wave G   (BDR-7 · G2 · G4 · 의사결정)     ░░░░░░░░░░  미착수
Wave H   (최소 화면 · 시연 안정화)         ░░░░░░░░░░  미착수
```

**분모의 정의**: 위 다섯 Wave 는 상위 정본 §8~§12 의 Wave 구분이다. 「조각의 합」이지
「사용자가 관통해 할 수 있는 일」이 아니다 — 관통 동선(§F-3 카나리)은 **아직 0회** 다.
