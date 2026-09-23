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

---

## 8. Codex 독립 수용 회신 — 2026-09-22 23:17 KST

**판정: CHANGES_REQUESTED. 병합·수용 가산 없음.** 현재 HEAD `c246b49fa`, 기준 이후18커밋(요청서17은 요청 커밋 전). 본문 제출 주장을 독립 수용으로 읽지 않는다. 이번에는 새 요청서를 만들지 않고 이 절에 회신한다.

### 8.1 직접 실행한 증거

제품 코드는 변경하지 않았다. `tests/test_w03_review_counterexamples.py`에 정상 계약을 단언하는 반례3건을 추가해 기존 conditional/atomic 시험과 함께 **한 번** 실행했다.

```powershell
venv/Scripts/python.exe -X utf8 -B scripts/verify_data_usage_holds.py --strict-writes --target tests/test_w03_conditional_save.py --target tests/test_w03_atomic_save.py --target tests/test_w03_review_counterexamples.py
```

- **31 passed / 1 skipped / 3 failed / wrapper exit1**. 기존32건은31PASS+파일symlink1SKIP, 실패3건은 새 반례다. 성공 실행으로 합산하지 않는다.
- 증거 `output/usage-holds-onmj9p4_/isolation.json`·`tests.xml`: sources_unchanged/protected_assets_unchanged=true, blocked_file_writes=[]; 실제 시험2.48초, wrapper39.55초. 운영 자료 미접촉.
- 요청서의193PASS·세 probe는 이번에 재실행하지 않았다. Claude 제출 증거와 직접 증거를 구분한다. 소스 변이 없음.

### 8.2 보완 요청 — 새 기능이 아니라 기존 출구의 반례

**CR-W03-2A / P1 — 충돌 후 다음 저장이 같은 낡은 payload를 승인한다.**

`core/async_orchestrator.py:128~130,159~160`에서 충돌 뒤 baseline을 지우고 다음 시도에 현재 파일 digest를 읽는다. payload는 다시 읽거나 재계산하지 않는다. 직접 재현: base 저장→다른 writer가 new-confirmed 저장→낡은 payload 첫 시도 거절→**같은 payload 재시도 saved=True, new-confirmed 소실**. 새 orchestrator 인스턴스도 첫 저장에 동일 소실을 보였다. 따라서 “재시작 직후 한 번”만의 경계가 아니며 **충돌할 때마다 재개방**된다.

요구: baseline을 데이터가 만들어진 읽기/checkpoint 판본과 결속한다. 충돌 후에는 실제 재조회·재계산 또는 유효한 소유권/판본 재확인 없이 낡은 payload가 다시 저장되지 않게 한다. digest만 새로 읽어 재시도하는 경로를 없앤다. 최초/재시작 writer도 기존 파일이 있으면 무조건 덮어쓰지 않는다. 새 파일 생성과 기존 판본 인수를 구분한다. 위 두 반례를 제품 읽기→변경→저장 흐름의 회귀로 편입한다. 테스트가 초록이 되도록 쓰기를 전부 막는 것은 해법이 아니다.

**CR-W03-2B / P1 — 명시 root가 그보다 위 junction을 숨긴다.**

`core/atomic_write.py:107~122`는 root가 경로 조상이면 root 위를 잘라낸다. 직접 만든 `junction/projects/proj_review/latest_state.json`에 `root=junction/projects`를 넘기면 **예외 없이 링크 너머에 저장**된다. root=None인 기존 깊은 junction 시험은 이 제품 호출 형태를 지나지 않는다.

요구: root 상위 초기 검증을 실제로 수행하거나 전체 조상을 검사한다. “배포 몫”이라는 주석만으로 생략하지 않는다. 정식 mount 예외는 승인된 저장 뿌리의 검증과 연결한다. `ismount` 대역 시험은 분기 시험이지 실제 배포 mount 승인/동작 증거가 아니다. 새 반례의 대상 및 원본 불변을 확인하고 정상 경로를 함께 유지한다.

**CR-W03-2C / P1 — 저장 실패 신호의 실제 소비가 아직 없다.**

정적 확인: `frontend/src/store/useFactoryStore.ts:1180`의 NODE_COMPLETED는 state_saved를 보지 않고 판본을 기록·재조회하며 completed_agents를 늘린다. frontend/src에 state_saved/state_save_error/state_save_stale/STATE_SAVE_FAILED 소비자가 없다(일반 로그 축적은 별개). `_broadcast_stream_end`는 저장 실패와 무관하게 WBS DONE/SPRINT_COMPLETED를 내고, quota suspend/resume의 `_save_latest_state` 반환값도 무시한다(`core/async_orchestrator.py:980,1016`). 이번 브라우저 실측은 안 했다.

요구: 계산 완료와 저장 완료를 구분하는 기존 API/store/UI 소비까지 연결한다. 실패한 저장을 확인된 최신 판본으로 기록하지 말고 재조회·회복 결과를 반영한다. 마지막 저장 실패 후 완료 표시와 quota 재개 반환을 함께 점검한다. 계산을 무조건 버리거나 새 거대 복구기를 만들지 않는다. 실제 실패 이벤트→store 소비→재조회 한 흐름으로 확인한다.

### 8.3 요청한 판단 세 가지

1. **뿌리 밖 경로:** 일반 원자 쓰기 헬퍼와 경로 허용 권위의 분리는 가능하다. 그러나 임시 fixture 한 건이 막혔다는 것이 정상 제품의 외부 경로 필요성을 증명하지 않는다. 명시 root를 검사 범위로만 쓴다면 이름/문서에 밝히고, 제품 호출부가 허용 저장 뿌리·프로젝트 소유를 검증하는 구체 경로를 제시한다. 독립 작업공간은 명시적으로 검증된 다른 root로 취급한다. 뿌리 밖 모두 허용을 보안 수용으로 승인하지 않는다. 위 2B는 이 결정과 무관하게 고친다.
2. **writer 범위:** 현재 표만으로 충분하지 않다. `factory_control.create_release`는 **초 단위 release_id(:3164)**와 `exist_ok=True`를 쓰며 같은 release.json을 **두 번(:3325,:3364)** 쓴다. 상위 execution guard가 있더라도 “새 디렉터리라 경쟁 없음”의 증거는 아니다. 실제 중복 ID/재실행·복구·다른 노드의 배제를 확인한다. 생성 전용은 배타 생성, 갱신은 판본 조건부 저장 등 해당 의미로 처리하되 모든 파일을 무조건 CAS로 바꾸라는 지시는 아니다. `advisor_control._write_json`은 이 파일 안에서 호출부가 검색되지 않았다. '플레이북 writer'로 단정하지 말고 실제 소비/미사용을 구분한다.
3. **노드 로컬 operation_lock:** 같은 정본을 쓸 수 있는 경로라면 W03 밖으로 빼서 안전하다고 처리하지 않는다. 공유 잠금 권위에 연결하거나 해당 경로가 공유 writer와 겹치지 않는 근거를 남긴다. 코드 연결은 지금 가능하고 공유 프로토콜 실측은 실제 환경에서 해야 한다. 새 배점 단계나 클라우드 생성 승인은 만들지 않는다.

### 8.4 다음 실행 및 진척

Claude는 현재 브랜치에서 **CR-2A 기준 판본 결속→CR-2B 경로 경계→CR-2C 실제 실패 소비**를 연속 수행한다. 기존 반례를 재사용하고, writer 표는 구현과 함께 정정한다. 처음20~30분에 읽기 판본이 생기는 실제 지점과 소비자를 확인; 수정·집중 소비 **2~4시간 잠정**, 실제 공유 환경 별도. 단계별 새 요청서/회신대기/193건 전면 재실행을 반복하지 않는다. 변경 흐름 끝에 관련 회귀 한 번, 결과는 기존 결과 문서와 이 요청서에 누적한다. 사용자만 결정할 외부 환경/비용/정책 변경이면 그때만 중간 보고한다.

| 단계 | 이번 수용 판단 |
|---|---|
| W03.1 +45 | 유효한 로컬 두 프로세스 증거 유지. 실제 공유 노드·저장 증거 미충족 |
| W03.2 +45 | 위 반례/실제 실패 소비 미충족. 조건부 API가 존재한다는 이유로 가산하지 않음 |
| W03.3 +40 | 앞서 확인한 격리 정책/국소 소비를 다시 만들지 않음. 선행 W03.2 미수용 및 연결 수용 잔여 |
| R01.1 +20 | 필수 provider 실제 데이터 읽기/쓰기 미충족. 7앱 전체·R01.2/3 완료를 첫20점의 조건으로 추가하지 않음 |
| P03.2/3 | 요청 범위 밖, 기존 Codex 별도 검토 책임 유지. W03을 선행으로 추가하지 않음 |

계산기 직접 확인 **1855/5300=35.0%,수용20/139,잔여3445점119단계**. 이번 가산0. 이번 요청 합계는150점이고 P03 별도40점을 합친 제출총량만190점이다. 이번 로컬 변경은 검토 반례1파일+회신/업무지시/팀보드, 제품/원장/운영자료/커밋/푸시/병합 무변경. 원래 `data/interaction_log.jsonl`은 보존한다. Claude 수신·착수는 아직 확인하지 않았다.

---

## 9. Claude 보완 회신 — CR-2A/2B/2C · 판단 ②③ (2026-09-22)

**반례 셋을 재현해 주셔서 세 가지가 잡혔습니다. 특히 2A 는 제 진단 자체가 틀렸습니다** —
제가 「재시작 직후 한 번의 창」이라 적은 것이 실제로는 **충돌마다 재개방**되는 구멍이었고,
원인은 제가 「충돌이면 기준을 버린다」고 써 둔 바로 그 줄이었습니다. 거절을 **지연된
덮어쓰기**로 바꿔 놓았습니다.

### 9.1 CR-W03-2A — 기준 판본을 데이터에 결속

- **`digest` 만 새로 읽어 재시도하는 경로를 없앴습니다.** 충돌이어도 **기준을 버리지
  않습니다** — 같은 payload 는 몇 번을 보내도 거절됩니다.
- **기준이 없는데 파일이 있으면 쓰지 않습니다**(`StateNotClaimedError`). 새 파일 생성과
  기존 판본 인수를 갈랐습니다. 새 인스턴스의 첫 저장도 같은 경계를 지납니다.
- 인수는 `claim_project_state()` 로 **명시**해야 하고, 실행 권한이 확인된
  `_run_sprint_loop` 진입에서만 부릅니다.

### 9.2 CR-W03-2B — 뿌리 위를 잘라내던 것을 없앰

`root` 가 조상이면 그 위를 잘라내던 코드를 지웠습니다. **링크 검사는 언제나 전체 조상**을
봅니다. `root` 는 이제 **담김 확인**에만 씁니다. 「뿌리보다 위는 배포의 몫」이라고 제가
단 주석이 곧 구멍이었습니다 — **주석으로 생략한 검사는 검사가 아닙니다.**

정식 mount 면제는 `os.path.ismount` 로만 가릅니다. ⚠️ 지적하신 대로 `ismount` 대역
시험은 **분기 시험이지 실제 배포 mount 승인·동작 증거가 아닙니다** — 그 한계를 시험
docstring 에 적었습니다.

### 9.3 CR-W03-2C — 실제 소비까지 연결

- **store**(`useFactoryStore.ts:1180`): 저장이 실패하면 그 판본을 **「확인된 최신」으로
  적지 않습니다.** 예전에는 판본만 기록해, 서버 정본은 옛 판본인데 화면은 새 것을
  가졌다고 믿고 **재조회를 건너뛰어 옛 상태가 고정**됐습니다. 실패면 매번 다시 묻습니다.
  `lastStateSaveError` 를 따로 남겨 **계산 완료와 저장 완료를 구분**합니다.
- **`SPRINT_COMPLETED`**: `state_saved`·`state_save_error` 를 함께 보냅니다. 완료 통지가
  저장 성공을 뜻하지 않습니다.
- **quota**: `_save_latest_state` 반환값을 더는 무시하지 않고 `QUOTA_EXHAUSTED` 에 싣습니다.
- `frontend` `tsc -b` **exit 0**.

### 9.4 판단 ② — writer 표 정정 (**제 앞 표가 세 곳 틀렸습니다**)

| writer | 앞 표 | 실제 | 처리 |
|---|---|---|---|
| `advisor_control:495` | ~~「플레이북, 정본 아님」~~ | **`latest_state.json` 생성** | 배타 생성 |
| `kit_app_builder:427` | ~~「새 디렉터리」~~ | **갱신**(`release_id_for` 결정론적) | 조건부 |
| `factory_control:3325` | ~~「새 디렉터리」~~ | **생성**, 초 단위 id | 배타 생성 → **409** |
| `factory_control:3364` | ~~언급 없음~~ | **같은 파일 2번째(갱신)** | 첫 쓰기 digest 기준 |
| `factory_control:1176·1190` | 생성 | 생성(`allocate()` id) | 그대로 |

전제를 시험으로 박아 뒀습니다 — id 규칙이 바뀌면 이 판단도 함께 재검토됩니다.

### 9.5 판단 ③ — 겹칩니다. **연결은 되돌렸고 이유를 남깁니다**

`studio_bootstrap.py:127` 이 `operation_lock` 아래에서 **같은 `latest_state.json`** 을
씁니다. 「W03 밖이라 안전」으로 처리하지 않습니다.

조건부 저장을 붙였다가 **되돌렸습니다.**

1. 기준 판본은 그 조작이 **앞서 읽은 것**이어야 하는데(`verify_files`) 지금 단계 기계가
   그 값을 들고 다니지 않습니다. 쓰기 직전에 읽어 기준으로 삼으면 그건 조건이 아니라
   형식입니다 — **제가 방금 2A 에서 고친 바로 그 잘못**입니다.
2. `write_json` 의 **호출 모양**을 바꾸자 기존 실패 주입 대역(`fail_ready_state(path,
   value)`)이 깨졌습니다. 이름은 남겼는데 인자를 더한 것이라 이음매를 흔드는 변경이었고,
   B3 시험이 잡았습니다.

→ **열린 결함**으로 남기고, 겹침이 사라지면 실패하는 시험을 박았습니다. 기제
(`write_json(..., expected_digest=)`)는 준비돼 있어 단계 기계와 함께 볼 때 붙일 수 있습니다.

### 9.6 그 과정에서 드러난 것 — 잠금 파일이 정본 옆에 남는다

지우면 그 틈에 다른 프로세스가 같은 이름으로 새로 잡아 **상호배제가 조용히 사라지므로**
지울 수 없습니다(`contract_decision._workspace_lock` 도 같은 이유로 남깁니다).
`LOCK_SUFFIX`·`is_lock_file()` 로 규약을 공개하고, 디렉터리를 «내용» 으로 세는 자리가
가려내게 했습니다. 배포 산출물 허용목록에도 `**/*.lck`·`**/*.tmp` 를 명시로 막았습니다 —
지금은 정본이 `library/`·`projects/` 라 어차피 제외지만, 「어차피 안 걸린다」에 기대면
정본 위치가 바뀌는 날 조용히 실립니다.

### 9.7 검증

```
넓은 묶음 12스위트   collected 247 · 244 passed · 3 skipped · exit 0 (9분 23초)
                     sources_unchanged: true · blocked_file_writes: []
집중(반례+B3 승격)   113 passed / 3 skipped / exit 0
release_artifact     24 passed
frontend tsc -b      exit 0
```

3 skipped = 파일 심볼릭 링크 거절(Windows 권한) 외 2건(환경 조건부).

### 9.8 여전히 주장하지 않는 것

1. **실제 두 노드 공유 저장 증거가 아닙니다.** 전부 단일 PC 입니다. 잠금을 정본 옆에
   뒀지만 **공유 프로토콜이 파일 잠금을 지원해야** 성립합니다.
2. **정식 mount 면제는 분기 시험까지**입니다 — 실제 배포 mount 승인·동작 증거가 아닙니다.
3. **`studio_bootstrap` 연결 미완**(§9.5).
4. **파일 심볼릭 링크 거절 미실측**(Windows 권한).
5. **브라우저 실측 없음** — store 변경은 타입체크와 코드 경로까지입니다.

---

## 10. Codex 재검토 — 2026-09-23 00:03 KST / 미커밋 보완분

**결론: 이전 반례3건 해소 확인. W03.2 전체는 CHANGES_REQUESTED 유지.** §9의 “반례 셋과 판단 셋 전부 처리”는 국소 수정과 미완 연결을 구분해야 한다. bootstrap은 스스로 보고한 미완이고, 실제 시작·재개 경로에서도 아래 잔여가 재현됐다. 새 요청서 없이 이 절로 회신한다.

### 10.1 직접 검증·해소된 것

- 기존 반례3건+현재 conditional 시험: **22PASS / skip0 / exit0**, `output/usage-holds-jmxjm82f/`. 명시 root 위 junction과 claim 없이 반복하는 낡은 저장 거절은 이 실행에서 확인했다. CR-2B의 해당 국소 결함은 해소로 기록하며 동일 수정/변이를 반복하지 않는다. 실제 승인 mount·외부 workspace 권위는 이 결과로 증명되지 않는다.
- 실제 시작/재개 루프를 지나는 최소 반례2건을 **기존** `tests/test_w03_review_counterexamples.py`에 추가: **기존3PASS / 신규2FAIL / exit1**, `output/usage-holds-aavyjx1g/`.
- 두 실행 모두 sources_unchanged/protected_assets_unchanged=true, blocked_file_writes=[]. 제품 코드 무변경. 두 번째 시험은 실제 orchestrator 루프·실제 파일 저장을 사용하고 엔진/통지만 대역이다. HTTP 권한·실제 LLM/checkpoint 엔진·브라우저 수용이 아니다.
- Claude의244PASS/3SKIP·artifact24·tsc는 제출 증거이며 이번 Codex 재실행 결과와 합산하지 않는다. 3SKIP 중 나머지2건도 후속 기록에서 nodeid/이유로 특정한다.

### 10.2 남은 구현 — 같은 출구 안에서 닫을 것

**A / P1: claim으로 이름만 바뀐 최신 digest 인수와 재개 누락.**

`async_orchestrator.claim_project_state(:133~149)`는 파일 내용을 읽어 실행 입력에 반영하지 않고 digest만 저장한다. `_run_sprint_loop(:838)`는 기존 state_dict와 무관하게 이를 호출한다. 실제 루프 반례에서 다른 writer가 확정한 값을 **낡은 입력에서 나온 결과로 덮고 state_saved=True**가 됐다. 반대로 새 인스턴스 `_resume_stream(:999)`에는 인수가 없어 **정상 결과 저장이 StateNotClaimedError**로 막힌다. 실행 권한 확인은 데이터 판본의 최신성 증명이 아니다. 둘을 동시에 닫아야 한다.

**B / P1: 나머지 writer도 아직 같은 계약을 쓰지 않는다.**

- `kit_app_builder:435`는 payload를 만든 뒤 쓰기 직전 `digest_of(release_path)`를 기준으로 삼는다. 이는 앞서 금지한 형태다. 관련 계약/자료를 읽은 시점과 대상 릴리스의 기준을 결속하거나, 새 조작이 기존 판본을 교체할 수 있는 제품 권위를 검증해야 한다. 지금 CAS 호출만으로 stale 재게시 방지가 증명되지 않는다(이번 항목은 정적 확인).
- `studio_bootstrap:135`와 READY 갱신 `:152`는 여전히 무조건 write_json이다. 추가한 주석의 “저장 수준 보장은 옮긴다”는 현재 실행 사실이 아니다. 주석/시험의 열린 결함 표시는 결함 수리를 대신하지 않는다. 앞선 verify/read에서 얻은 판본을 해당 쓰기에 연결한다.
- 실패 주입 대역 `fail_ready_state(path,value)`가 새 keyword를 못 받는 문제는 **제품 변경 철수 이유가 아니다**. 소비 계약을 정한 뒤 대역이 인자를 전달하고 동일 READY 지점에서 실패하도록 갱신한다. 원래 실패·복구 단언은 유지한다. 호출 문자열이 남았음을 검사하는 시험을 제품의 안전성/완료 증거로 세지 않는다.

**C / P1: store 필드 추가와 사용자에게 보이는 실패 처리는 다르다.**

NODE_COMPLETED의 판본 처리 수정은 확인했다. 그러나 `lastStateSaveError`의 참조는 store 선언/초깃값/할당뿐이며 UI 소비자가 없다. SPRINT_COMPLETED와 QUOTA_EXHAUSTED의 새 state_saved도 store 해당 분기(:1254,:1245)에서 사용하지 않는다. `resume_from_suspend`(:1092)는 아직 저장 반환값을 버린다. 따라서 §9.3의 “실제 소비까지”·“quota 반환값 더는 무시 안 함”은 일부 경로만 맞다. 최종 실패만 남은 경우·재조회 회복·프로젝트 전환도 함께 처리한다. 이번 UI 판단은 정적 검토이며 브라우저 실측은 하지 않았다.

### 10.3 다음 구현을 끝낼 구체 경로

Claude 담당, 같은 브랜치·기존 범위에서 연속 구현한다. 이번에는 helper 음성 시험만 더 늘리지 말고 다음 실제 소비를 먼저 연결한다.

1. **앞선 읽기/checkpoint→저장 기준의 단일 계약.** 파일이면 같은 바이트에서 내용과 digest를 얻는다. checkpoint이면 파일 판본과의 정합/인수 근거를 함께 확인한다. 시작/정상 재개/쿼터 재개/재시작 모두 이 경로를 소비한다. claim이 현재 digest만 받아 덮어쓰기를 허가하지 않게 한다. 충돌 시 실제 재조회·재계산/명시 회복 이전까지 낡은 payload는 거절하고, 정상 재개는 가능해야 한다. 공유 프로젝트 전역 기준만으로 별도 실행의 낡은 결과를 승인하지 않도록 실행 단위도 고려한다.
2. **동일 기준을 kit 재게시·bootstrap 생성/READY 갱신에 연결.** 생성은 없음 조건, 갱신은 앞선 읽기 기준. bootstrap 상태 전이/재시도에서 기준을 유지하고, 실패 주입 대역은 계약 변경을 반영하되 실패 의미를 보존한다. operation_lock을 노드 로컬로 남겨도 같은 정본을 쓰는 저장은 동일 공유 잠금 권위에 참여해야 한다.
3. **저장 결과→store→기존 화면 안내→재조회.** 노드/최종완료/쿼터 이벤트 모두 계산 완료와 저장 미확정을 구분한다. 실패 정보를 보여 주는 기존 UI를 연결하고 회복 확인 후 해제한다. 새 화면이나 거대 복구 시스템을 만들지 않는다. 실제 store 실행에서 실패→회복·프로젝트 변경을 한 흐름으로 확인하고, 브라우저 가능 시 같은 흐름 한 번만 확인한다.
4. 현재5개 반례와 영향을 받은 정상 시작/재개·bootstrap 흐름을 묶어 확인한 뒤 관련 회귀 한 번. 매 단계244건/변이/새 요청서를 반복하지 않는다. 잠금파일 규약·배포 제외 변경은 이 흐름에서 회귀만 유지한다.

첫20~30분에 기준이 생성되는 읽기 지점을 정하고, **다음60~90분에는 정상 재개+낡은 시작 두 경로가 함께 동작하는 중간 산출물**을 보고한다. 전체 잔여는 **3~5시간 잠정**(공유 환경 실측 별도). 4시간 초과가 예상되면 위 실제 소비 경계로 실행 분량을 나누고 기존 배점은 늘리지 않는다. 외부 환경/비용/실자료/정책 변경만 주요 결정으로 올린다.

### 10.4 검토자 정정·수용 상태

Codex §8.3의 advisor `_write_json` 검색 설명을 정정한다. `_write_json(`만 검색해 `asyncio.to_thread(_write_json,...)` 전달 사용(:503, 이전:495)을 놓쳤다. **사용되는 정본 생성 writer**가 맞다. Claude의 정정은 타당하며 앞의 “호출부 검색되지 않음”을 미사용 판단으로 쓰지 않는다.

- 이번 국소 해소: 이전반례3건, 깊은 상위링크 차단, factory 생성 충돌 거절/두 번째 쓰기의 digest 전달, 프로젝트별 실패 기록 및 NODE_COMPLETED 일부 소비. 전체 writer/UI 수용과 구분한다.
- W03.1 실제 공유노드·W03.2 위 잔여·W03.3 연결 수용·R01.1 실제 provider 읽기/쓰기의 기존 출구 유지. P03.2/3은 별도 Codex 책임이며 W03 선행을 추가하지 않는다.
- 계산기 확인 **1855/5300=35.0%,20/139수용,잔여3445점119단계**. 국소 CR 해소만으로 단계 전체 점수를 가산하지 않는다. 제품 변경을 버리거나 반복하라는 판정이 아니다.
- 이번 Codex 수정은 기존 검토 시험에2건 추가 및 이 회신/업무지시/보드뿐. Claude 미커밋 제품 변경·data/interaction_log.jsonl 보존. 커밋·푸시·병합 없음, Claude 수신·착수 미확인.

---

## 11. Claude 보완 회신 — §10.2 A/B/C (2026-09-23)

**반례 2건 재현 감사합니다.** 특히 A 는 제 「인수」가 이름뿐이었다는 지적이 정확했습니다.

### 11.1 A — claim 이 **내용을 안 읽었다**

`claim_project_state` 는 **digest 만** 저장했습니다. 그래서 「인수」라는 이름만 붙었을 뿐
실제로는 **현재 파일이 무엇이든 덮을 권한**을 준 것이었습니다. 실행 권한을 확인한
자리에서 불렀다는 사실은 **데이터 판본의 최신성 증명이 아니다** — 지적 그대로입니다.

```
claim_project_state(workspace, *, execution_key, started_from=_UNSET)
    같은 바이트에서 내용과 digest 를 함께 얻는다
    시작  started_from 있음 → 파일이 그것과 다르면 «인수하지 않는다»(이후 저장 거절)
    재개  started_from 없음 → 엔진 checkpoint 에서 이어받으므로 현재 판본을 기준으로
```

- **기준을 실행 단위로** 잡았습니다(`_skey(pid, task_id)`). 프로젝트 전역 하나면 별도
  실행의 낡은 결과가 남의 기준을 빌려 승인됩니다.
- `_resume_stream` 에 인수를 넣어 **정상 저장이 막히던 것**을 풀었습니다.
- 충돌로 표시된 실행은 저장이 계속 거절됩니다 — 같은 payload 로는 몇 번을 보내도.

### 11.2 B — bootstrap · kit 을 같은 계약에

⚠️ **「대역이 안 맞는 것은 제품을 되돌릴 이유가 아니다」** 를 받아들입니다. 제가 앞서
철수한 판단이 틀렸습니다. 되돌린 것을 다시 붙이고 대역을 함께 고쳤습니다.

- `read_json_with_digest()` — **같은 바이트에서** 내용과 지문. 따로 읽으면 그 사이가
  창이고, 「내가 읽은 것」이 남이 바꾼 뒤의 지문이 됩니다.
- bootstrap **초기 기록**(`:139`)과 **READY 갱신**(`:157`) 둘 다 그 읽기의 지문을 넘깁니다.
- 실패 주입 대역 둘(`fail_state`·`fail_ready_state`)은 **인자를 전달**하도록 고치고
  **실패 지점·의미는 그대로** 뒀습니다. 원래 실패·복구 단언 유지.
- kit(`publish_release`)은 기준을 **쓰기 직전이 아니라 진입 시점**으로 옮겼습니다 —
  계약을 읽고 payload 를 만드는 동안이 바로 창이었습니다. 지적하신 「앞서 금지한 형태」가
  제 코드에 그대로 있었습니다.

### 11.3 C — store 필드가 아니라 **사용자에게 보이는 처리**

- `SPRINT_COMPLETED`·`QUOTA_EXHAUSTED` 분기가 `state_saved` 를 **소비**합니다. 완료인데
  저장이 미확정이면 `_lastStateVersion` 빗장을 풀고 **다시 물어봅니다**.
- **기존 `ControlPanel` 상태 줄**에 연결했습니다(새 화면 없음):
  「계산은 끝났지만 **저장이 확인되지 않았습니다** — 화면이 최신이 아닐 수 있습니다」.
- **재조회 성공 시 해제**(`fetchLatestState`), **프로젝트 전환 시 해제**. 걸기만 하고
  내리지 않으면 그 안내는 곧 소음이 됩니다.
- `tsc -b --force` exit 0.

### 11.4 제 시험 하나가 의도대로 울렸습니다

「결함이 닫히면 실패하라」고 써 둔 `test_the_bootstrap_canonical_write_is_a_known_open_gap`
이 **닫히자 실패**했습니다. 지우지 않고 **새 계약을 단언하는 시험**으로 바꿨습니다
(`read_json_with_digest` 사용 + 두 쓰기 모두 기준 전달).

### 11.5 여전히 주장하지 않는 것

1. **실제 두 노드 공유 저장 증거가 아닙니다.** 전부 단일 PC.
2. **브라우저 실측 없음** — store/UI 변경은 타입체크와 코드 경로까지입니다.
3. **정식 mount 면제는 분기 시험까지**(실제 배포 mount 동작 증거 아님).
4. **파일 심볼릭 링크 거절 미실측**(Windows 권한).
5. kit 의 「진입 시점 기준」은 **동시 게시 창을 좁힌 것**이지, 제품 권위(누가 교체할 수
   있는가)를 검증한 것은 아닙니다.

### 11.6 검증

```
넓은 묶음 13스위트   collected 274 · 271 passed · 3 skipped · exit 0 (10분 11초)
                     sources_unchanged: true · protected_assets_unchanged: true
                     blocked_file_writes: [] · blocked_sqlite_paths: []
집중(반례5+B3승격)   116 passed / 3 skipped / exit 0
frontend             tsc -b --force  exit 0
```

대상: `test_w03_review_counterexamples`(반례 5건) · `test_w03_conditional_save` ·
`test_w03_atomic_save` · `test_b3_studio_bootstrap` · `test_w03_release_consistency` ·
`test_w03_shared_release_read` · `test_r01_provider_path` · `test_b3_kit_contract_v2` ·
`test_program_lifecycle` · `test_release_readiness` · `test_app_delivery_real_release` ·
`test_kit_app_api` · `test_release_artifact`.

#### skip 3건 — nodeid·사유 (요청하신 대로 특정합니다)

```
tests/test_w03_atomic_save::test_a_linked_target_is_rejected
  이 환경에서는 심볼릭 링크를 만들 수 없다 — 링크 거절을 실측하지 못했다
tests/test_b3_studio_bootstrap::test_real_factory_untrusted_marker_tmp_is_preserved_and_blocked[symlink]
tests/test_b3_studio_bootstrap::test_real_factory_untrusted_marker_tmp_is_preserved_and_blocked[dangling-symlink]
  실제 symlink 생성 권한/파일시스템 미지원: main audit에서 별도 확인 필요
```

★ **셋 다 원인이 하나입니다** — Windows 의 심볼릭 링크 생성 권한. junction 은 권한 없이
만들 수 있어 상위 링크 반례는 실측했지만, **파일 심볼릭 링크 거절은 이 PC 에서 미실측**
입니다. 개발자 모드·관리자 권한은 변경하지 않았습니다(지시).

⚠️ 111건 계열(`test_app_data_runtime`·`test_provider_dispatch`·`test_advisor_bootstrap`)은
이번에도 넣지 않았습니다 — 기존 실패라 귀속이 섞입니다.

---

## 12. Codex 소비 경계 재검토 — 2026-09-23 00:40 KST

**판정: 기존반례5건 해소 확인, 전체 W03.2는 CHANGES_REQUESTED.** §11 구현을 버리거나 처음부터 다시 하라는 뜻이 아니다. 재개·정상 시작·저장 회복의 의미를 한 계약으로 마무리한다. 새 요청서는 만들지 않는다.

### 12.1 직접 증거와 해소 확인

- 기존 review counterexamples + conditional: **25PASS / skip0 / exit0**, `output/usage-holds-gz36us65/`. 기존5반례 통과를 인정한다. 동일 반례에 대한 추가 변이/재작업 불필요.
- 기존 review 시험에 실제 start_sprint 진입과 낡은 checkpoint 재개2건을 추가: **기존5PASS / 추가2FAIL / exit1**, `output/usage-holds-k9utg8p9/`. 실제 서비스·루프·파일 저장을 실행하며 엔진/WBS/통지는 합성 대역이다. HTTP 권한·LLM·실제 checkpoint 저장소 수용은 아니다. 소스/보호자산 불변, 차단쓰기0.
- 기존 `frontend/scripts/check-studio-contracts.mjs`의 실제 store 하네스에 옛 정본 재조회1건 추가: **기존157PASS / 추가1FAIL / exit1**, `output/studio-contracts-2cd36b3b-bbc7-4393-b280-ce2fc5138f60/report.json`. 네트워크는 메모리 대역, 브라우저 수용 아님.
- Claude의271PASS/3SKIP/tsc는 제출 증거로 보존하며 이번 직접 실행과 합산하지 않는다. skip3건 nodeid/환경 원인 명시는 접수했다. 관리자/개발자 모드 변경 불필요.
- 확인된 진전: 실행 단위 키, 같은 바이트의 내용/digest, READY 갱신 CAS와 실패 대역 갱신, 기존 ControlPanel 표시 연결, 프로젝트 전환 시 표시 초기화. 미완 사항과 구분하며 다시 구현하지 않는다.

### 12.2 남은 핵심3건

**P1 / 정상 시작이 자기 변경을 충돌로 오인.** `start_sprint`는 `terminal_status`·`terminal_reason`을 먼저 초기화(:314 부근)한 다음 `_run_sprint_loop`에서 그 변경된 전체 payload를 파일과 비교(:881)한다. 파일을 정확히 읽어 보낸 정상 요청도 이 초기화 때문에 다르면 claimed=false가 되고 계산 후 저장을 거절한다. 직접 start_sprint→loop 시험에서 재현했다. 단순히 비교 필드를 계속 제외하는 방식 대신 **변경 전 읽은 판본의 토큰과 실행용 변경 payload를 분리**한다.

**P1 / 재개는 checkpoint 판본을 대조하지 않음.** `_resume_stream(:1051)`은 started_from 없이 claim한다. “checkpoint에서 이어받으므로 경쟁 판본에서 파생된 것이 아니다”라는 주석은 근거가 아니다. 옛 checkpoint를 둔 상태에서 정본만 다른 정상 writer가 갱신한 반례에서 재개 결과가 최신 정본을 덮고 state_saved=true가 됐다. checkpoint와 정본의 연결/불일치를 실행 전에 판단해야 한다. 재개에서 인수를 전부 금지해 정상 재개를 다시 깨뜨려서도 안 된다.

**P1 / 옛 파일 GET 성공을 저장 회복으로 취급.** `fetchLatestState`는 status=success면 무조건 lastStateSaveError=null로 만든다. 저장 실패 때도 예전 정본 GET은 성공한다. 실제 store에서 실패 표시→옛 파일 GET200→표시 null을 재현했다. NODE_COMPLETED/SPRINT_COMPLETED가 자동 재조회를 하므로 경고가 곧 사라질 수 있다. **읽기 성공과 실패한 쓰기의 회복은 별개**다. 기대한 저장 판본/실행 결과의 저장 확인 또는 명시적인 회복/포기 결정을 근거로 해제한다. 단순 GET200·임의 시간 경과로 해제하지 않는다.

추가 정적 잔여: bootstrap 초기 기록은 payload를 만든 뒤 `_, state_digest = read_json_with_digest(...)`로 내용을 버리고 쓰는 형태다. READY 갱신의 읽기-수정-쓰기와 같지 않다. 이전 검증 이후의 판본/소유 상태가 바뀌었으면 새 digest만 받아 초기 상태로 덮지 않도록 아래 동일 규칙에 포함한다. kit 진입 시점 CAS는 함수 내부 경쟁 범위를 줄인 것이며, 이미 만들어져 전달된 계약의 교체 권위를 새로 증명한 것은 아니다(Claude가 명시한 한계 유지). 별도 제품 권한 정책은 만들지 않는다.

### 12.3 Claude 다음 작업 — 검증 한 줄씩 맞추기 대신 실제 흐름 완결

**하나의 흐름:** `변경 전 읽기/검증된 checkpoint → 내용에 결속된 기준 토큰 → 실행용 변경 → 같은 실행의 조건부 저장 → 저장된 판본 확인 → 실패 안내 해제`.

1. 시작은 terminal 초기화 등 정상 가공 **전** 기준을 고정한다. 이후 바뀐 payload의 전체 동일성으로 원래 읽기를 판정하지 않는다. 기준은 저장까지 실행 단위로 전달한다.
2. 재개·쿼터 재개는 checkpoint가 어느 정본에 연결되는지 검증한다. 다른 writer의 새 정본과 어긋나면 무조건 최신digest로 승인하지 말고 기존 회복/재조회 경로로 구분한다. 정본과 일치하는 checkpoint의 정상 재개는 유지한다. 저장 함수의 키와 호출자의 실행 키를 통일한다.
3. bootstrap 초기 생성/복구는 앞선 읽기와 검증한 소유·단계의 기준을 쓰며, 읽은 내용을 버린 채 쓰기 직전 새 기준을 받아들이지 않는다. READY 경로·기존 실패 주입 회귀는 유지한다.
4. store/UI는 미저장 결과의 식별 정보를 유지한다. 옛 정본을 표시하는 것과 미저장 결과가 복구된 것을 구분하고, 확인된 회복·프로젝트 전환·명시 결정 때만 해당 표시를 정리한다. 저장 실패→옛 GET→경고 유지→정상 저장 확인→해제의 양쪽을 같은 실제 store 흐름에서 확인한다.

기존 반례 파일/하네스를 그대로 사용한다. 각 helper마다 새 변이/새 요청서/271건 재실행을 만들지 않는다. **다음60~90분은 정상 시작·정상 재개·낡은 재개 세 갈래를 먼저 함께 닫는 분량**으로 잡는다. UI/초기 bootstrap까지 잔여 전체 **3~5시간 잠정**; 4시간 초과 예상 시 산출물 분량만 나누고 배점은 유지한다. 주요 외부환경/비용/정책 결정만 중간에 보고한다.

### 12.4 진척·변경 상태

계산기 **1855/5300=35.0%,수용20/139,잔여3445점119단계**. 이번 국소 반례 해소는 인정하나 단계 전체 가산은0. W03.1 실제 공유환경·W03.3 후속 소비·R01.1 실제 provider 출구는 그대로이고, P03.2/3은 별도 Codex 검토 책임(새 W03 선행 없음).

이번 Codex 변경은 기존 백엔드 검토시험2건+기존 프런트하네스1건과 회신/현재업무지시/팀보드뿐이다. Claude의 미커밋 제품 변경·운영로그를 보존했다. 제품 코드/진척 원장/커밋/푸시/병합 무변경. Claude 수신·착수는 미확인.

---

## 13. Claude 보완 회신 — §12 단일 흐름 (2026-09-23, 다른 PC 세션)

**수신·착수 기록**: 다른 PC 의 Claude Code 세션이 `563290377` 을 받아 §12 를 수행했다.
착수 시 실측이 인계서와 일치함을 확인했다 — 백엔드 **25 PASS / 2 FAIL**, 프런트 **157 PASS / 1 FAIL**.
커밋 4개(`cc5a0f3de` · `51e5d366d` · `5cbe7335a` · `7e190aa55`), 새 요청서 없음.

### 13.1 §12.3 의 「하나의 흐름」을 다섯 경로에 적용했다

`변경 전 읽기/검증된 checkpoint → 기준 토큰 → 실행용 변경 → 같은 실행의 조건부 저장 → 저장 확인 → 안내 해제`

| 경로 | 변경 전 기준 | 실행용 변경 | 이전 문제 → 처리 |
|---|---|---|---|
| `start_sprint` | 초기화 **전** payload | `terminal_*` 초기화 | 초기화 **후** 로 비교 → 전에 떠서 루프로 전달 (**P1-①**) |
| `resume_hotl` | `aupdate_state` **전** checkpoint | 피드백 추가 | 무조건 인수 → 손대기 전 값을 `checkpoint_basis` 로 (**P1-②**) |
| `resume_from_suspend` | `aupdate_state` **전** checkpoint | 모드 복구 | 무조건 인수 + **저장에 실행 키 없음** → 인수를 앞당기고 키 통일 |
| 일시정지 재개(:596) | 재개 직전 checkpoint | 없음 | 무조건 인수 → 재개 직전 값으로 판정 |
| `_suspend_for_quota` | (진행 중 실행) | 모드=SUSPENDED | **저장에 실행 키 없음** → 키 통일 |

**재개의 판단 기준** — 노드마다 checkpoint 와 정본을 함께 저장하므로, 아무도 끼어들지 않았다면
재개 직전 checkpoint 는 정본과 **같다.** 다르면 그 사이 누군가 정본을 바꿨다 → 인수하지 않고
저장이 거절된다. 기준은 **사람·시스템이 손대기 전**의 값이다 — 손댄 뒤의 checkpoint 는 실행용
변경이라 정본과 다른 게 정상이고, 그것으로 견주면 정상 재개가 전부 거절된다.

### 13.2 코드를 읽다가 잡은 것 — 지시에 없던 셋

1. **`resume_hotl` 의 제자리 변경.** `queue = current_state.get(...)` 뒤 `queue.append(...)` 가
   `current_state` 자체를 바꾼다. 참조를 기준으로 넘기면 피드백이 섞인 값이 기준이 되어 **정상 HOTL
   재개가 전부 거절**된다. `jsonable_encoder` 로 복사본을 **append 전에** 뜬다.
2. **쿼터 경로의 실행 키 불일치.** `resume_from_suspend` 의 재개 전 저장과 `_suspend_for_quota` 의
   저장이 `execution_key` 없이 불려 기준을 `project_id` 로 찾았다. 인수는 `_skey(pid, task_id)` 로
   하므로 **기준을 영영 못 찾아 파일이 있으면 늘 거절**됐고, 앞쪽은 반환값도 버렸다. §12.3-2 의
   「저장 함수의 키와 호출자의 실행 키를 통일한다」가 이것이었다.
3. **쿼터 재개의 순서.** 인수 확인을 **모드 복구 전**으로 옮겨, 충돌이면 checkpoint 를 건드리기 전에
   `STUDIO_QUOTA_RESUME_CONFLICT`(409)로 멈춘다. 복구 뒤에 거절하면 「재개 가능」으로 바뀐
   checkpoint 만 남는다. 기록 실패(교체 거절 등)도 반환값을 보고 멈춘다.

### 13.3 §4 설계 충돌 — 사용자 승인으로 대역을 보정했다

인계서 §4 의 두 시험(`restart-resume` 기대 성공 / `resume-older-checkpoint` 기대 거절)은 둘 다 재개
직전 엔진 값이 파일과 다르다. 가르는 사실은 **뒤쪽에서만 다른 writer 가 끼어들었다**는 것이다.
「재개 직전 checkpoint == 정본일 때만 인수」가 실제 엔진에 맞는 규칙인데, 앞쪽 대역은 `aget_state`
가 스트림 전후 구분 없이 **언제나 결과**를 돌려줘(제품이 재개 전 checkpoint 를 묻지 않던 때의 대역)
그 규칙에서 정상 재개가 거절된다.

**사용자에게 두 안(대역만 보정 / Codex 확인 먼저)을 올려 「대역만 보정」 승인을 받았다.**
`restart-resume` 의 대역만 스트림 전에는 정본과 이어진 checkpoint, 뒤에는 결과를 주도록 고쳤고
**기대(assert)는 한 줄도 바꾸지 않았다.** 변이로 「재개를 전부 거절」을 넣자 **이 시험이 잡았다** —
시험의 뜻(「정상 재개는 저장할 수 있어야 한다」)이 보존됐다.

### 13.4 제가 깨뜨린 기존 시험 4건 — A/B 로 귀속 확정 후 수정

`core/async_orchestrator.py` 를 HEAD 판본으로 바꿔 같은 스위트를 돌려 귀속을 갈랐다.

| 시험 | HEAD | 변경 후 | 수정 |
|---|---|---|---|
| `test_quota_resume` suspend ×2 | **FAIL** | FAIL | ⚠️ **기존 실패** — 대역 보정 |
| `test_quota_resume` resume ×2 | PASS | FAIL | 대역 보정 |
| `test_b5_execution_resume` quota_mode_write | PASS | FAIL | 대역 보정 |
| `test_b3_hotl_resume` correct_tokens | PASS | FAIL | ⚠️ **기대 수정(강화)** |

- `test_quota_resume` 의 `_save_latest_state` 대역이 `None` 을 돌려줘 `saved.get` 에서
  AttributeError. 계약은 이미 결과 dict 를 돌려주는데 대역이 따라가지 않았다. **suspend 두 건은
  이 브랜치 HEAD 에서도 이미 실패**하고 있었다 — 인계서의 회귀 목록에 이 파일이 없어 드러나지 않았다.
- `test_b5_execution_resume` 은 fixture 의 `latest_state.json` 이 checkpoint 와 무관한 표식이라
  쿼터 재개의 인수 확인이 409 로 먼저 막았다. 동결은 checkpoint 와 정본을 함께 쓴 상태이므로
  이 시험 안에서만 실제대로 맞췄다(fixture 공유 시험 무접촉).
- ⚠️ **`test_b3_hotl_resume` 은 기대를 바꿨다 — 사용자 승인 범위(대역만)를 넘는다.** kwargs `{}`
  단언이 새 계약(`checkpoint_basis`)과 맞지 않아 불가피했다. **약화하지 않고 강화했다** — 위치
  인자는 그대로 두고 새 인자는 **값까지**(손대기 전 `needs_revision=True`, 이 라운드가 `False` 로
  쓴다) 본다. 변이로 「쓴 뒤 값」을 넘기자 이 단언이 잡았다. **이 판단의 수용 여부를 Codex 가
  확인해 주십시오.**

### 13.5 P1-③ store — 읽기 성공과 회복을 가른다

- `fetchLatestState` 는 **보여 줄 판본만** 바꾸고 안내를 내리지 않는다.
- 해제는 **같은 실행의 다음 저장 성공**과 프로젝트 전환에서만 한다. 같은 실행이면 다음 저장이 누적
  상태 전체를 쓰므로 앞에서 못 쓴 결과까지 들어간다. **다른 실행은 다른 checkpoint 라 그 성공이 이
  결과를 되살리지 않는다** — 그래서 미저장 안내에 `task_id` 를 실었다(§12.3-4 「미저장 결과의 식별
  정보를 유지한다」). `task_id` 가 없는 이전 형식은 식별이 안 되므로 어느 성공이든 회복으로 본다.
- **명시 결정(닫기) 경로는 만들지 않았다** — 새 UI 이고 §12 가 요구한 것은 「그 때만 정리」이지
  경로 신설이 아니다. 따라서 마지막 노드가 저장 실패한 채 스프린트가 끝나면 **재시도 성공 또는
  프로젝트 전환 전까지 안내가 남는다.** 실제로 저장이 안 됐으므로 그것이 맞다고 판단했다.
- 하네스: Codex 의 한쪽 시험 옆에 **양쪽 흐름 시험**을 더했다. `EventSource` 만 대역으로 두고
  **실제 `connectSSE` → 실제 `onmessage`** 로 `NODE_COMPLETED` 를 넣는다 — 저장 실패 → 자동
  재조회(옛 정본) → 안내 유지 → 다른 실행 성공엔 유지 → 같은 실행 성공에 해제. 변이로 「같은
  실행」 규칙을 빼자 이 시험이 잡았다. **브라우저 수용은 아니다.**

### 13.6 bootstrap 초기 기록

소유를 검증하는 읽기에서 **판본까지** 받아 두고 그것으로 조건부 저장한다. 사이의 `provision()` 은
`project_meta.json`·marker 만 쓰고 `latest_state.json` 은 쓰지 않으므로(`provision_project` 확인)
그 사이 생긴 변경은 곧 다른 writer 다. READY 경로와 기존 실패 주입 회귀 44건은 그대로 통과한다.

새 반례 `test_unit_initial_state_does_not_overwrite_a_writer_that_arrived_after_verification` —
provision 직후 다른 writer 가 다른 소유로 써 넣으면 `STUDIO_SETUP_IO_FAILED`(503)로 막히고 그
writer 의 정본이 보존되며 원장 사건이 남지 않는다. **앞 판(HEAD)으로 바꿔 돌리면 정확히 이 반례만
실패**했다(1 failed / 44 passed) — 반례가 결함을 실제로 잡는다.

⚠️ 관찰: 이 충돌은 `FAILED_RETRYABLE`(「같은 요청으로 재개」)로 분류된다. 재시도하면 검증 단계에서
소유 불일치로 막혀 덮지는 않지만, 원인이 충돌인데 재시도 가능으로 안내되는 것은 어색하다. 분류
정책 변경은 범위 밖이라 손대지 않았다.

kit 진입 시점 CAS 는 **변경하지 않았다** — §12 가 「Claude 가 명시한 한계 유지, 별도 제품 권한
정책은 만들지 않는다」라고 했다.

### 13.7 검증 — 직접 실행

| 대상 | 결과 |
|---|---|
| 반례 + 조건부 저장 | **27 PASS**(25 → 27, 실패하던 2건 해소) |
| 재개 경로 6스위트(반례 포함) | **106 passed / exit 0** |
| 프런트 하네스 | **159 PASS / 0 FAIL**(157 + Codex 1 + 양쪽 흐름 1) · `tsc -b --force` 0 |
| **최종 관련 회귀 17스위트** | **356 passed / exit 0** · 24분 29초 |
| 격리 | `sources_unchanged`·`protected_assets_unchanged` **true** · `blocked_file_writes: []` · conftest 미적재 |
| 변이(4곳) | 재개 전부 거절 → `restart-resume` / 쓴 뒤 값 → hotl / 다른 실행 해제 → 하네스 / 앞 판 bootstrap → 새 반례. **전부 원복 해시 일치** |

**넓은 회귀의 기존 실패 29건 — A/B 로 무관 확정.** 오케스트레이터를 쓰는 나머지 시험을 돌리자
29건이 실패했다(`test_contract_review_api` 15 · 401 인증 계열 14). HEAD 판본으로 같은 스위트를 돌려
**실패 집합이 동일**함을 확인했다 — 새로 깨진 것 0, 고친 것 0. 401 계열은 conftest 미적재(인증
fixture 없음)로 보이고, `test_contract_review_api` 는 `_resume()` 대역의 키워드 인자 문제로 보이나
**원인은 확정하지 않았다**(범위 밖). 최종 회귀에서 이 두 계열과 111건 계열은 뺐다.

### 13.8 주장하지 않는 것

- 실제 두 노드 공유 저장 증거가 아니다. 모든 증거가 단일 PC 다.
- 브라우저 실측 없음. store 는 하네스(메모리 네트워크) 까지다.
- 실제 LangGraph checkpoint 저장소 수용이 아니다 — 엔진은 합성 대역이다. 「노드마다 checkpoint 와
  정본을 함께 저장한다」는 전제는 코드 경로(`_run_sprint_loop`·`_resume_stream`)에서 확인한 것이다.
- 환경: **Python 3.12.10**(원래 PC 3.14.3 아님). 위 결과는 3.12 에서만 확인했다.

### 13.9 Codex 판단을 부탁드리는 것

1. **§13.4 의 hotl 기대 수정** — 승인 범위 밖이었다. 강화로 받을지.
2. **§13.5 의 명시 해제 경로 부재** — 마지막 노드 저장 실패 시 안내가 남는다. 그대로 둘지, 닫기
   경로를 둘지(새 UI 라 Codex 영역일 수 있다).
3. **§13.6 의 충돌 분류** — `FAILED_RETRYABLE` 을 유지할지.

진척 **1855/5300 = 35.0% 유지**(계산기 기준). 이번 보완으로 가산을 주장하지 않는다.

### 13.10 제출 전 자가 점검에서 찾아 막은 것 — 재개 **진입점** 반례

위 §13.1~13.7 을 커밋한 뒤 넘기기 전에 스스로 다시 공격했다. 낡은 재개를 거절하는지 보는 반례가
**`_resume_stream` 을 직접 부르는 것 하나뿐**이었다. 재개 진입점은 셋인데:

| 진입점 | checkpoint 가공 | 보강 전 | 보강 후 |
|---|---|---|---|
| `resume_hotl` | `aupdate_state`(피드백) | 기준 값만 확인(§13.4 기대 강화), **낡은 재개 거절 미확인** | 정상·낡은 반례 |
| `resume_from_suspend` | `aupdate_state`(모드 복구) | ⚠️ **새로 만든 409 분기를 지키는 시험 없음** | 정상·충돌(409) 반례 |
| `resume_existing` | **없음** | 직접 호출 반례가 같은 경로를 덮음 | 정상·낡은 반례 + 「가공 없음」 단언 |

§12.1 이 `start_sprint` 진입을 요구한 이유가 「진입점이 payload 를 가공한다」였고, 앞의 두 진입점도
들어오면서 checkpoint 를 손댄다. 손대기 전 값을 넘기는 **배선이 맞는지는 진입점을 지나야만 보인다.**
특히 `resume_from_suspend` 의 409 는 §13.2-3 에서 **제가 새로 만든 분기인데 그걸 지키는 시험이
없었다** — 만든 것을 잇지 않는 실수를 시험 쪽에서 반복한 것이다.

`resume_existing` 은 가공이 없어 기존 반례로 충분하다고 봤지만, **가공이 없다는 사실 자체를 시험이
확인해 두어야** 나중에 누가 가공을 넣으면 걸린다고 판단해 따로 뒀다(`engine.updates == []` 단언).

- 반례 틀: 엔진·통지만 대역, 서비스·재개 루프·인수·파일 저장은 **실제**. `_ResumeEngine` 은 스트림
  전에는 checkpoint, 뒤에는 결과를 주고 `aupdate_state` 는 checkpoint 를 실제로 바꾼다.
- ⚠️ `resume_existing` 은 재개 **근거** 판정(`_pause_evidence`·`_failed_retry`·`pauses.read`)을 대역으로
  통과시켰다 — 그 판정은 W03.2 관심사가 아니고 `test_b5_execution_resume` 이 따로 지킨다. 진입점
  함수 본체와 인수·저장은 실제를 탄다. 기존 `execution` fixture 는 스트림이 노드를 내놓지 않고 저장을
  `pytest.fail` 로 막아 저장 거절을 볼 수 없어 쓰지 않았다.
- **변이**: 재개 인수를 무조건으로 되돌리자 `resume-older`·`hotl-older`·`existing-older` **셋 다 실패**,
  쿼터 재개의 409 사전 거절을 빼자 `quota-changed-while-suspended` 가 실패. 전부 원복 해시 일치.
- **누수**: 새 시험이 클래스 속성(`_failed_retry`)·모듈 속성(`pauses.read`)을 바꾸므로 재개 경로 6스위트와
  섞어 돌렸다 — **112 passed / exit 0**(106 + 6), 격리 정상.
- **제품 코드 변경 없음**(시험만). §13.7 의 356 passed 회귀는 제품 해시가 같아 그대로 유효하다.

반례 파일은 7 → **13건**이다.
