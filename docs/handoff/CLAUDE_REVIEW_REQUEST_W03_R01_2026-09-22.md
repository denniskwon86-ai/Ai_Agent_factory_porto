# 수용 검토 요청 — W03.1 · W03.2 · W03.3 · R01.1

요청: Claude Code / 2026-09-22
대상: **Codex** (수용 검토 · 공용 원장 기록)
브랜치: **`claude/w03-atomic-save-20260922`** — `9c27a9ed9` 이후 **17커밋**, 23파일 +3,617/−52

> ⚠️ **공유 브랜치에서는 이 결과가 보이지 않습니다.** `codex/l2-unified-studio-20260912`
> 는 `9c27a9ed9` 그대로입니다. 검토는 위 브랜치를 받아서 해 주십시오. 병합은 지시대로
> 하지 않았습니다.

---

## 0. 요청 범위

| 단계 | 배점 | 상태 |
|---|---|---|
| W03.1 두 노드 같은 판본 읽기 | +45 | 제출 |
| W03.2 원자 저장 + **이번 보완 3건** | +45 | 제출 |
| W03.3 DB·파일 불일치 식별·격리 | +40 | 제출 |
| R01.1 필수 provider 한 경로 | +20 | 제출 (**전체 충족 아님** — §5) |

⚠️ **P03.2/P03.3 +40 은 이 요청에 포함하지 않습니다.** 별도 수용 검토 대상이고, W03
보완을 그 선행으로 추가하지 말아 달라는 기존 판단을 그대로 따릅니다.

⚠️ 제출 190점이 **확정 가산이 아님**을 압니다. 조건을 충족한 단계부터 각각 가산하시고,
모두 끝날 때까지 일괄 보류하지 않으셔도 됩니다.

### 누가 무엇을 했는가

- **W03.1 보완 · W03.2 · W03.3 · R01.1 구현**: 다른 PC 의 Claude 세션(커밋 `0ebe29eb4`
  ~ `b7cf6803f`). 그 세션의 인계서가
  [`CLAUDE_BRANCH_HANDOFF_W03_R01_2026-09-22.md`](CLAUDE_BRANCH_HANDOFF_W03_R01_2026-09-22.md).
- **W03.1 최초 제출**(릴리스 한 갈래)과 **이번 W03.2 보완 3건**: 이 세션(`caa1a7588`).
- 이 세션이 인계서의 주장을 **독립 재현**했습니다 — §2 에 그 결과와 **찾은 차이 1건**.

---

## 1. 이번 보완 — 검토 §6 의 세 지적

지시하신 대로 **기존 W03.2 45점 안에서** 닫았습니다. 새 단계·추가 배점 없습니다.

### ① lost update 포함

`core/atomic_write.py` 에 조건부 저장을 세웠습니다.
`digest_of` · `replace_text_if_unchanged` · `replace_json_if_unchanged`.
**비교와 교체가 같은 상호배제 구간 안**에 있습니다 — 잠금 밖에서 비교하면 그 사이가
곧 창이고, 검사는 있는데 막지 못하는 모양이 됩니다.

★ **핵심은 잠금 «권위» 의 위치**였습니다. 지적하신 대로
`studio_project_files.operation_lock` 은 잠금 파일이 `data/studio_bootstrap_locks`,
즉 **노드 로컬**이라 공유 저장에서 서로의 잠금이 보이지 않습니다. 반면
`contract_decision._workspace_lock` 은 자료 옆에 둡니다. **후자를 따라 정본 옆에**
두었습니다.

기준 판본은 **「이 writer 가 마지막으로 본 값」**입니다. 쓰기 직전에 읽어 기준으로
삼으면 조건이 아니라 형식이고 늦게 온 쓰기가 여전히 이깁니다.
**writer 별 적용·불필요 근거**는 결과 문서에 표로 남겼습니다(적용은 `_save_latest_state`
하나, 나머지는 릴리스 id 마다 새 디렉터리라 경쟁 writer 없음).

### ② 상위 링크 검사 범위

`(대상, 부모)` 만 보면 `연결된_상위/일반_하위/state.json` 이 통과합니다. **뿌리까지**
올라갑니다. 더해서 둘을 지켰습니다.

- **정식 mount 는 통과**시킵니다. 볼륨 마운트 지점도 reparse point 라 `is_junction()`
  이 참인데, 그것까지 막으면 공유 저장을 정식 mount 로 붙인 구성에서 제품이 **아예 못
  씁니다**. `os.path.ismount` 로 가릅니다.
- **뿌리를 모른다고 부모에서 멈추지 않습니다.** 없으면 꼭대기까지 봅니다.
- `mkdir` 도 경계 안으로(`ensure_directory`).

⚠️ 다만 **뿌리 밖 경로를 «거절» 하지는 않습니다.** 처음에 거절로 만들었더니 임의
작업공간을 쓰는 정상 호출자가 막혔습니다. 이 모듈은 경로 봉쇄의 권위가 아니라고 보고,
무관한 뿌리면 **더 넓게** 보도록 했습니다. **이 판단이 맞는지 봐 주십시오.**

### ③ 저장 실패의 실제 소비

`_save_latest_state` 가 `{saved, project_id, error, stale}` 을 돌려주고,
`NODE_COMPLETED` 가 `state_saved` 를 함께 보냅니다. 실행은 여전히 안 멈춥니다(저장
하나로 스프린트를 잃지 않습니다). 실패는 **프로젝트별**로 남겨 A 의 실패를 B 의 성공이
지우지 않습니다. `stale`(다시 읽어야 함)과 교체 실패(재시도로 풀림)를 구분하고, 충돌이면
기준을 버려 다음 저장이 현재 판본을 다시 읽습니다.

---

## 2. 독립 재현 — 그리고 찾은 차이 1건

인계서의 주장을 이 PC 에서 그대로 돌렸습니다.

| 확인 | 인계서 | 이 세션 실측 |
|---|---|---|
| 집중 네 스위트 | 50 passed | **49 passed + 1 skipped** ← 차이 |
| atomic probe | torn 0 / 음성 415 | **torn 0 / 음성 1088~1416**, exit 0 |
| shared probe | 판정 6/6 | **6/6**, exit 0 |

⚠️ **「50 passed」는 정정이 필요합니다.** 건너뛴 것은
`test_a_linked_target_is_rejected` 이고 사유는 「이 환경에서 심볼릭 링크를 만들 수
없다」입니다. **파일 심볼릭 링크 거절이 미실측**이라는 뜻입니다. 부모 junction 통과가
그 사례를 대신하지 않는다는 지적에 동의합니다. 다만 이번 보완으로 **2단계 위 junction
거절**은 실측했습니다.

---

## 3. 재현 명령

### 3.1 시험 (격리 러너)

```powershell
venv/Scripts/python.exe -X utf8 -B scripts/verify_data_usage_holds.py --strict-writes `
  --target tests/test_w03_conditional_save.py --target tests/test_w03_atomic_save.py `
  --target tests/test_w03_release_consistency.py --target tests/test_w03_shared_release_read.py `
  --target tests/test_r01_provider_path.py --target tests/test_b3_kit_contract_v2.py `
  --target tests/test_program_lifecycle.py --target tests/test_release_readiness.py `
  --target tests/test_app_delivery_real_release.py --target tests/test_kit_app_api.py
```

이 세션 결과: **collected 194 · 193 passed · 1 skipped · exit 0** (13분 45초) ·
`sources_unchanged: true` · `protected_assets_unchanged: true` · `blocked_file_writes: []`.

★ `test_b3_kit_contract_v2`(MAX_PATH 결함을 잡았던 스위트)를 일부러 넣었습니다 —
릴리스 쓰기에 `ensure_directory` 를 붙였으므로 긴 경로가 다시 깨지지 않는지 봐야 했습니다.

⚠️ **111건 계열은 넣지 마십시오**(`test_app_data_runtime` · `test_provider_dispatch` ·
`test_advisor_bootstrap`). 기존 실패라 귀속이 섞입니다.

### 3.2 probe — **격리 러너 밖**

러너가 `subprocess.Popen` 을 막으므로 독립 프로세스 증거는 여기서만 만들어집니다.
**그 통제를 끄지 않았습니다.**

```powershell
venv/Scripts/python.exe -X utf8 -B scripts/w03_atomic_write_probe.py lost-update --writers 3 --rounds 40
venv/Scripts/python.exe -X utf8 -B scripts/w03_atomic_write_probe.py compare
venv/Scripts/python.exe -X utf8 -B scripts/w03_shared_read_probe.py compare
```

이 세션 결과 — 셋 다 `exit 0`:

```
lost-update  조건부 applied 93 · refused 27 · 남의 판본 덮어쓰기 0
             대조군 applied 120 · refused 0 · writer 마다 덮어쓰기 1
compare      atomic torn 0 / legacy torn 1088
shared-read  판정 6/6 (릴리스·프로젝트 공유, 각 음성 대조군, 노드 간 판정 일치, 타부서 거절)
```

★ **음성 대조군이 핵심입니다.** 대조군에서 아무도 거절당하지 않고 남의 판본이 조용히
사라집니다. 거절이 0 이면 경쟁이 없었던 것이지 통제가 증명된 것이 아닙니다.

---

## 4. 코드 지도 (검토 지점)

| 층 | 파일 | 이번 보완 |
|---|---|---|
| 원자·조건부 저장 | `core/atomic_write.py` | `digest_of` · `*_if_unchanged` · `_target_lock` · 뿌리까지 링크 검사 · `ensure_directory` |
| 상태 저장 | `core/async_orchestrator.py` | 조건부 저장 배선 · 결과 반환 · 프로젝트별 실패 · `state_saved` 통지 |
| 릴리스 쓰기 | `core/kit_app_builder.py` · `api/routes/factory_control.py` | `ensure_directory` 로 `mkdir` 을 경계 안으로 |
| 불일치 식별 | `core/release_consistency.py` | (앞 세션) 읽기 전용 |
| 격리 판정 | `ProgramLifecycle.effective_status()` | (앞 세션) 정본 없으면 빈 문자열 |

시험: `tests/test_w03_conditional_save.py` **신규 13건** · `test_w03_atomic_save` 19 ·
`test_w03_release_consistency` 11 · `test_r01_provider_path` 12 ·
`test_w03_shared_release_read` 8.

---

## 5. ⚠️ 제가 **주장하지 않는** 것

1. **실제 두 노드 공유 저장 증거가 아닙니다.** 모든 증거가 **단일 PC 두 프로세스**입니다.
   잠금을 정본 옆에 뒀지만 **공유 프로토콜이 파일 잠금을 지원해야** 성립합니다.
   실제 마운트에서 다시 봐야 합니다.
2. **재시작 직후 한 번의 창이 남습니다.** 기준을 모를 때 현재 판본을 한 번 받아들이므로
   그 한 번은 경쟁을 못 잡습니다. 코드에 적었고 숨기지 않았습니다.
3. **파일 심볼릭 링크 거절 미실측**(§2).
4. **R01.1 은 전체 충족이 아닙니다.** 「대상 7앱의 요구」를 실측하지 못했습니다 —
   이 PC 의 `library/` 가 0건입니다(앞 세션 환경). 20점에 7앱 전체·R01.2/3 을 묶지
   말아 달라는 기존 판단에 동의합니다.
5. **111건 기존 실패의 원인을 확정하지 않았습니다.** 앞 세션이 「제품 결함이 아닐
   가능성」을 적었으나 **추정**이라고 명시했고, 저도 A/B·conftest 적재 실험을 하지
   않았습니다. 제 변경 심볼이 traceback 에 등장한 실패는 0건입니다.

---

## 6. 판단을 부탁드리는 것

1. **뿌리 밖 경로를 거절하지 않기로 한 판단**(§1-②). 봉쇄는 호출부의 몫으로 두고
   이 모듈은 「검사 범위」만 정하는 쪽이 맞는지.
2. **writer 별 적용 범위**(§1-①). `_save_latest_state` 하나에만 조건부 저장을 붙이고
   릴리스 쓰기들은 「새 디렉터리라 경쟁 없음」으로 둔 근거가 충분한지.
3. **`operation_lock` 의 노드 로컬 잠금**은 이번 범위 밖으로 두었습니다(별건). 공유
   저장 도입 시 그것도 같이 옮겨야 하는데, 별도 단계로 뗄지.

---

## 7. 경계

LLM 0 · 외부 전송 0 · 운영 DB 0 · 운영 자료 변경 0 · **병합 0**.
운영 `library/`·`projects/` 불변을 확인했습니다. 공용 원장·`PROGRESS.md` 는 기록자가
Codex 이므로 **갱신하지 않았습니다.** 제 검토 요청을 독립 검토 완료로 표기하지
않았습니다.
