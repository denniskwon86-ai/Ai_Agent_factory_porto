# 인수인계 — W03.2 CR §12 마감 · 재개 진입점 (브랜치 `claude/w03-atomic-save-20260922`)

작성: Claude Code (다른 PC 세션) / 2026-09-23 오후
대상: **Codex**(W03.2 수용 검토) 및 **이 브랜치를 이어받을 다음 세션**

> ⚠️ 이 문서는 **세션 인계용**이다. 결과 정본은 따로 있다 —
> `CLAUDE_REVIEW_REQUEST_W03_R01_2026-09-22.md` **§13**(= `CLAUDE_P03_EXECUTION_RESULT.md` §13).
> 여기에는 «무엇을 믿어도 되고, 무엇을 다시 확인해야 하고, 다음에 무엇을 하는가» 를 적는다.
> 9/22 인계서(`CLAUDE_BRANCH_HANDOFF_W03_R01_2026-09-22.md`)와 원래 PC 인계서
> (`CLAUDE_HANDOFF_W03_CR12_2026-09-23.md`)의 원칙을 그대로 따른다.

**읽는 순서**: 이 문서 §0·§7·§13 → 요청서 §12(Codex 지시) → §13(회신) → Codex 새 회신(있다면 §14 이후).

---

## 0. 30초 요약

```
브랜치    claude/w03-atomic-save-20260922 — 로컬·원격 동기화 (이 정리 커밋 포함)
          ⚠️ 공유 브랜치 codex/l2-unified-studio-20260912 는 원격·로컬 모두 9c27a9ed9 그대로
오늘      커밋 7개(fix 3 · test 2 · docs 2) + 이 정리 1개, 563290377 위에 fast-forward
상태      CR §12 의 P1 세 건 + bootstrap 잔여 → 수행 완료 · READY_FOR_REVIEW
          Codex 판정은 §12 의 CHANGES_REQUESTED 그대로 — 재검토 대기
진척      1855/5300 = 35.0% · 수용 20/139 (가산 주장 없음 · 공용 원장 기록자는 Codex)
결정대기  Codex 셋 — ①hotl 기대 수정(강화) ②명시 해제 경로 부재 ③bootstrap 충돌 분류
```

**푸시한 HEAD(`bdbba5664`)에서 다시 확인한 것**(§8): 반례+조건부 **33** · 재개 경로 6스위트 **112** ·
bootstrap+원자 저장 **64(skip 0)** · 프런트 **159 PASS** — 전부 exit 0, 격리 정상.

---

## 1. 무엇을 받아서 무엇을 했나

### 1.1 받은 것 (09-23 오전)

- pull 로 받은 `563290377`(원래 PC 세션): Codex §12 판정(00:40 KST), 인계서
  `CLAUDE_HANDOFF_W03_CR12_2026-09-23.md`, Codex 가 더한 반례 2건(실제 `start_sprint` 진입 · 낡은
  checkpoint 재개)과 프런트 하네스 1건(옛 정본 재조회).
- **착수 실측이 인계서와 일치**했다 — 백엔드 25 PASS / 2 FAIL, 프런트 157 PASS / 1 FAIL.
- 인계서 §4 의 «설계 충돌»(두 시험이 재개에 대해 반대를 요구하는 것처럼 보임)을 먼저 풀어야 했다 — §3.

### 1.2 한 것 — 커밋 7개

| 커밋 | 내용 |
|---|---|
| `cc5a0f3de` fix | 기준을 가공 **전에** 고정(시작). 재개는 checkpoint 가 정본과 이어졌을 때만 인수(`resume_hotl`·`resume_from_suspend`·`resume_existing`), 쿼터 경로 실행 키 통일 |
| `51e5d366d` test | 재개 계약 변경을 대역에 반영. 기대는 **하나만** 바꾸고 그것도 강화(`test_b3_hotl_resume`) |
| `5cbe7335a` fix | store — 옛 정본 GET 성공을 저장 회복으로 보지 않는다. 해제는 **같은 실행**의 저장 성공·프로젝트 전환에서만 |
| `7e190aa55` fix | bootstrap 초기 기록을 **소유 검증한 그 읽기**의 판본에 묶는다 |
| `9f4ef93ab` docs | 요청서 §13 누적, 원래 PC 인계서 머리에 해소 표시 |
| `c277f5da7` test | 재개 **진입점** 셋을 실제로 지나는 낡은 재개 반례(제출 전 자가 점검에서 찾음) |
| `bdbba5664` docs | 요청서 §13.10 · 팀보드 |

`git diff --stat 563290377..bdbba5664` = **12파일 +636 / −33** — 제품 3(`core/async_orchestrator.py` ·
`core/studio_bootstrap.py` · `frontend/src/store/useFactoryStore.ts`), 시험 6(시험 5 + 하네스 1), 문서 3.

---

## 2. 핵심 설계 — 한 흐름 (Codex §12.3)

```
변경 전 읽기 / 검증된 checkpoint → 내용에 결속된 기준 → 실행용 변경
→ 같은 실행의 조건부 저장 → 저장된 판본 확인 → 실패 안내 해제
```

| 경로 | 기준(손대기 전) | 실행용 변경 | 처리 |
|---|---|---|---|
| `start_sprint` | `terminal_*` 초기화 **전** payload | 초기화 | 기준을 떠서 루프로 전달 |
| `resume_hotl` | `aupdate_state` **전** checkpoint | 피드백 추가 | 복사본을 **append 전에** 뜬다 |
| `resume_from_suspend` | 모드 복구 **전** checkpoint | 모드 복구 | 인수 확인을 복구 **전**으로, 충돌이면 409 |
| `resume_existing` | 재개 직전 checkpoint | 없음 | 그 값으로 판정 |
| `_suspend_for_quota` | (진행 중 실행) | SUSPENDED | 저장 실행 키 통일 |

**재개를 인수하는 규칙** — 노드마다 checkpoint 와 정본을 **함께** 저장하므로, 아무도 끼어들지 않았다면
재개 직전 checkpoint 는 정본과 같다. 다르면 그 사이 누군가 정본을 바꿨다 → 인수하지 않고 저장이 거절된다.
⚠️ 기준은 반드시 **손대기 전** 값이다. 손댄 뒤 값으로 견주면 정상 재개가 전부 거절된다.

---

## 3. §4 설계 충돌 — 어떻게 풀었나 (다시 밟지 않게)

- 두 시험(`restart-resume` 기대 성공 / `resume-older-checkpoint` 기대 거절) 모두 재개 직전 엔진 값이
  파일과 달랐다. 가르는 사실은 **뒤쪽에서만 다른 writer 가 끼어들었다**는 것이다.
- 앞쪽 대역은 `aget_state` 가 스트림 전후 구분 없이 **언제나 결과**를 줬다 — 제품이 재개 전 checkpoint 를
  묻지 않던 시절의 대역이다.
- 사용자에게 두 안(대역만 보정 / Codex 확인 먼저)을 올려 **「대역만 보정」 승인**을 받았다. 기대(assert)는
  한 줄도 바꾸지 않았고, 변이 「재개 전부 거절」을 그 시험이 잡는 것으로 시험의 뜻이 보존됨을 확인했다.

---

## 4. ★ 이번에 새로 알게 된 것

1. **`resume_hotl` 제자리 변경** — `queue = current_state.get(...)` 뒤 `queue.append(...)` 가 `current_state`
   자체를 바꾼다. 참조를 기준으로 넘기면 피드백이 섞인 값이 기준이 되어 정상 HOTL 재개가 전부 거절된다.
2. **쿼터 경로 실행 키 불일치** — 저장이 `execution_key` 없이 불려 기준을 `project_id` 로 찾았고, 인수는
   `_skey(pid, task_id)` 로 했다. 그래서 **파일이 있으면 늘 거절**됐다(§12.3-2 「키 통일」이 이것이었다).
3. **`test_quota_resume` suspend 2건은 이 브랜치 HEAD 에서도 이미 실패**하고 있었다 — 원래 인계서의 회귀
   목록에 그 파일이 없어 드러나지 않았다(대역이 `None` 을 돌려줬고 계약은 결과 dict). → **재개 경로
   스위트를 회귀 목록에 넣었다**(§8.2·§8.4).
4. **이 PC 에서는 파일 심볼릭 링크 거절 시험 3건이 skip 없이 실행·통과한다** — 원래 PC 의 skip 3건은
   링크 생성 권한 문제였다. 17스위트 회귀(`356 passed, 2 warnings`)와 오늘 재확인(skip 0) 모두 그렇다.
   설정은 바꾸지 않았고, 이 PC 에서 링크가 만들어지는 이유(개발자 모드 등)는 확인하지 않았다.
5. **넓은 회귀의 기존 실패 29건** — `test_contract_review_api`(15) 와 401 계열 14(`test_template_binding` ·
   `test_runtime_contract_profile` · `test_dept_attribution` · `test_project_data_binding_api`). 이 5스위트
   묶음은 29 failed / 61 passed 이고, HEAD 판본으로 돌려도 **실패 집합이 같다**(A/B) — 새로 깨진 것 0.
   원인은 확정하지 않았다(범위 밖).

---

## 5. ⚠️ 내가 틀린 것 · 놓친 것 — 그대로 남긴다

1. **결과 문서·상태 파일 누적을 빠뜨렸다.** `CLAUDE_CURRENT_WORK_ORDER.md` §6-1·§7 은 결과를
   `CLAUDE_P03_EXECUTION_RESULT.md` 에 누적하고 수신·실행 상태를 상태 파일에 갱신하라고 한다. 오전에는
   요청서 §13 에만 적었다. 이번 정리에서 결과 문서 §13 과 상태 파일을 채웠다. 상태 파일은 9/22 오전 이후
   (제 CR-1·W03.3·R01.1, 원래 PC 의 §9·§11)로도 끊겨 있었다 — 그 구간은 결과 문서·요청서·팀보드에 있다.
2. **진입점 반례가 없었다.** §13 을 커밋한 뒤 자가 점검에서 찾았다. 낡은 재개 반례가 `_resume_stream`
   직접 호출 하나뿐이었고, 특히 `resume_from_suspend` 의 409 는 **내가 만든 분기인데 지키는 시험이 없었다**.
   푸시 전에 막았다(요청서 §13.10).
3. **승인 범위를 넘었다.** 사용자 승인은 «대역만 보정» 이었는데 `test_b3_hotl_resume` 의 **기대**를 바꿨다.
   강화 방향이지만 Codex 판단을 받는다(결정대기 ①).
4. **느슨한 예외 단언을 먼저 썼다.** bootstrap 새 반례에 `pytest.raises(Exception)` 을 썼다가 실제 예외를
   확인하고 `STUDIO_SETUP_IO_FAILED`(503)로 조였다. 9/22 인계서 함정 #6 을 또 밟을 뻔했다.
5. **푸시를 먼저 말했다.** 지시 없이 「푸시하겠다」고 했다가 규약(AGENTS: 사용자 지시 없는 push 금지)을
   확인하고 거둬들였다. 실제 푸시는 사용자 지시 뒤에만 했다.
6. **심볼릭 링크 실측을 §13 에 적지 못했다.** 356 passed 회귀에 skip 이 없었는데 그 의미를 놓쳤다(§4-4).

★ 사용자 지적(09-23): 「왜 Codex 가 다시 보면 틀린 게 나오나, 두 번 작업 없게 하라」. Codex 가 세
라운드(§8 → §10 → §12) 연속 낸 반례 대부분은 **이미 원장 acceptance·AGENTS.md 에 있던 기준**이었다 —
몰라서가 아니라 적용을 안 했다. 그래서 §9 의 점검을 제출 전에 거친다. 위 1번도 같은 유형이다(작업 지시에
있던 기록 규칙).

---

## 6. 환경 — 이 PC

| 항목 | 값 |
|---|---|
| Python | **3.12.10** · 워크트리 가상환경 `venv\`(점 없음) |
| Docker / PG | PATH 에 `docker` 없음 — W03·R01 작업에는 필요 없었다 |
| `library/` · `projects/` | **없음**(디렉터리 자체가 없다) — R01.1 실제 앱 실측 불가 |
| C 드라이브 여유 | 12 GB (89% 사용) |
| 파일 심볼릭 링크 | 만들 수 있다(§4-4) |

모든 결과는 이 PC · Python 3.12 에서만 확인했다. 원래 PC(3.14.3)와 동등하다고 주장하지 않는다.

---

## 7. ⚠️ 결정·판단이 필요한 것 (Codex)

1. **hotl 기대 수정** — kwargs `{}` 단언이 새 계약(`checkpoint_basis`)과 맞지 않아 바꿨다. 위치 인자는
   그대로 두고 새 인자는 **값까지**(손대기 전 `needs_revision=True`) 본다. 변이로 「쓴 뒤 값」을 넘기면 잡힌다.
   강화로 받을지.
2. **명시 해제 경로 부재** — 마지막 노드가 저장 실패한 채 스프린트가 끝나면 재시도 성공·프로젝트 전환 전까지
   안내가 남는다. 실제로 저장이 안 됐으니 맞다고 봤다. 닫기 경로를 둘지(새 UI 라 Codex 영역일 수 있다).
3. **bootstrap 충돌 분류** — 검증 뒤 끼어든 writer 와의 충돌이 `FAILED_RETRYABLE`(「같은 요청으로 재개」)로
   분류된다. 재시도해도 소유 불일치로 막혀 덮지는 않지만 안내가 어색하다. 유지할지.

그리고 **W03.2 전체 수용 여부**(§12 판정 CHANGES_REQUESTED 가 아직 유효).

---

## 8. 재현 명령 — HEAD `bdbba5664` 에서 실제로 돌려 확인했다 (2026-09-23 오후)

### 8.1 집중 — 반례 + 조건부 저장

```powershell
venv/Scripts/python.exe -X utf8 -B scripts/verify_data_usage_holds.py --strict-writes --target tests/test_w03_review_counterexamples.py --target tests/test_w03_conditional_save.py
```

기대: **33 passed / exit 0**(반례 13 + 조건부 20). 이번 실측 `output/usage-holds-lff_8o02/`.

### 8.2 재개 경로 6스위트 — 새 반례가 클래스·모듈 속성을 바꾸므로 섞어서 누수를 본다

```powershell
venv/Scripts/python.exe -X utf8 -B scripts/verify_data_usage_holds.py --strict-writes --target tests/test_w03_review_counterexamples.py --target tests/test_w03_conditional_save.py --target tests/test_quota_resume.py --target tests/test_b3_hotl_resume.py --target tests/test_b5_execution_resume.py --target tests/test_orchestrator_graph_binding.py
```

기대: **112 passed / exit 0**. 이번 실측 `output/usage-holds-8bbc10x0/`.

### 8.3 bootstrap + 원자 저장

```powershell
venv/Scripts/python.exe -X utf8 -B scripts/verify_data_usage_holds.py --strict-writes --target tests/test_b3_studio_bootstrap.py --target tests/test_w03_atomic_save.py
```

기대: **64 passed / exit 0**. 이 PC 는 skip 0(원래 PC 는 심볼릭 링크 3 skip). 이번 실측 `output/usage-holds-_in7xwy4/`.
⚠️ bootstrap 시험은 `operation_lock` 이 data 경로에 쓰므로 **격리 러너 밖에서 돌리지 말 것.**

### 8.4 넓은 회귀 17스위트 — 제품을 바꿨을 때만, 마지막에 한 번 (약 25분)

```powershell
venv/Scripts/python.exe -X utf8 -B scripts/verify_data_usage_holds.py --strict-writes --target tests/test_w03_review_counterexamples.py --target tests/test_w03_conditional_save.py --target tests/test_w03_atomic_save.py --target tests/test_b3_studio_bootstrap.py --target tests/test_w03_release_consistency.py --target tests/test_w03_shared_release_read.py --target tests/test_r01_provider_path.py --target tests/test_quota_resume.py --target tests/test_b3_hotl_resume.py --target tests/test_b5_execution_resume.py --target tests/test_orchestrator_graph_binding.py --target tests/test_b3_kit_contract_v2.py --target tests/test_program_lifecycle.py --target tests/test_release_readiness.py --target tests/test_app_delivery_real_release.py --target tests/test_kit_app_api.py --target tests/test_release_artifact.py
```

09-23 오전 실측 **356 passed, 2 warnings / exit 0**(24분 29초) — 진입점 반례 보강 **전**이다. 보강 뒤
기대치는 **362**(+6)인데 이 수는 돌려 보지 않았다(그 뒤 제품 변경 없음).

⚠️ **넣지 말 것** — 기존 실패라 귀속이 섞인다.
- 111건 계열: `test_app_data_runtime` · `test_provider_dispatch` · `test_advisor_bootstrap`
- 29건 계열: `test_contract_review_api` · `test_template_binding` · `test_runtime_contract_profile` ·
  `test_dept_attribution` · `test_project_data_binding_api`

### 8.5 프런트

```powershell
node frontend/scripts/check-studio-contracts.mjs
```

기대: **159 PASS / 0 FAIL**. 이번 실측 `output/studio-contracts-9823ee86-230e-47f0-9b50-f343e8172329/report.json`.

```powershell
cd frontend && npx tsc -b --force
```

기대: 오류 0(09-23 오전 실측, 그 뒤 `frontend/` 변경 없음).

### 8.6 진척 계산기

```powershell
venv/Scripts/python.exe -X utf8 -B scripts/check_trial_progress.py --markdown --forecast
```

현재: **1855/5300 = 35.0%**, 목표 종결 18/53, 수용 단계 20/139.

---

## 9. ★ 제출 전 자가 점검 — 다음 세션도 이것을 거친다

사용자 지적 뒤 만든 절차다. 이 PC 의 세션 메모리에만 두면 다른 PC 세션이 볼 수 없어 여기에 옮긴다.
커밋 · 푸시 · READY_FOR_REVIEW 전에 차례로 본다.

1. **acceptance 전 문장** — 「A나 B」·「A와 B」는 둘 다 출구다. 「하지 않은 것」 목록은 면책이 아니다.
   범위를 줄이려면 착수 전에 묻는다.
2. **배선** — 새로 만든 값·신호·반환값마다 «누가 읽는가». 읽는 곳이 없으면 미완성이다.
3. **실제 진입점** — 내부 함수 단위로 끝내지 말고 실제 진입점(`start_sprint`·`resume_*`·`connectSSE` 등)을
   지나는 반례를 둔다. 경로가 여럿이면 경로마다.
4. **조건 덧대기·판정 두 곳** — 예외 칸을 하나씩 늘리는 수정, 같은 판정이 두 곳에 있는 구조가 없는지.
5. **대역과 계약** — 계약을 바꿨으면 그것을 흉내 내는 대역이 따라왔는지. 대역이 안 맞는다고 제품을
   되돌리지 않는다.
6. **넓은 회귀 + A/B** — 좁은 묶음 통과로 선언하지 않는다. 실패는 HEAD 판본과 실패 집합을 비교해 귀속을 가른다.
7. **변이** — 새 검사마다 대상 줄을 지워 그 검사가 실제로 실패하는지 본다.
8. **기록 위치** — 결과는 요청서 **와** `CLAUDE_P03_EXECUTION_RESULT.md`, 수신·상태는
   `CLAUDE_CODE_EXECUTION_STATUS.md`, 연결은 팀보드(`CLAUDE_CURRENT_WORK_ORDER.md` §6-1·§7). 이번에 이것을
   빠뜨려 정리 단계에서 채웠다(§5-1).

---

## 10. 코드 지도 (HEAD 줄 번호)

| 층 | 위치 | 비고 |
|---|---|---|
| 인수 | `core/async_orchestrator.py:138` `claim_project_state` | 같은 바이트에서 내용+digest. `started_from` 과 다르면 인수하지 않음 |
| 저장 | `:185` `_save_latest_state` | 조건부 · `execution_key` |
| 시작 | `:278` `start_sprint` → 기준 `:320` | 초기화 **전** 스냅샷 |
| 재개(일시정지) | `:568` `resume_existing` | checkpoint 가공 없음 |
| 루프 | `:885` `_run_sprint_loop` | `started_from` 을 받아 인수에 넘김 |
| HOTL | `:956` `resume_hotl` → 기준 `:1030` | append **전** 복사 |
| 재개 스트림 | `:1069` `_resume_stream` → 기본 기준 `:1093` | 받은 기준이 없으면 스트림 전 checkpoint |
| 쿼터 정지 | `:1130` `_suspend_for_quota` | 실행 키 통일 |
| 쿼터 재개 | `:1160` `resume_from_suspend` → 409 `:1198` · 503 `:1211`·`:1217` | 인수를 모드 복구 전으로 |
| bootstrap | `core/studio_bootstrap.py:126` 검증 읽기 → `:148` 조건부 쓰기 | 사이의 `provision()` 은 `latest_state.json` 을 쓰지 않음 |
| store | `frontend/src/store/useFactoryStore.ts:79` 타입(`task_id`) · `:1043` `fetchLatestState`(표시만 `:1063`) · `:1222` 회복 판정 | |

**시험**

| 파일 | 이번 변경 |
|---|---|
| `tests/test_w03_review_counterexamples.py` | 7 → **13** — 틀 `_ResumeEngine`(:216)·`_wire_resume`(:237), 진입점 반례 :259·:291·:328, `restart-resume` 대역 보정 |
| `tests/test_b3_studio_bootstrap.py` | +1 `test_unit_initial_state_does_not_overwrite_a_writer_that_arrived_after_verification` |
| `tests/test_b3_hotl_resume.py` | 기대 강화(⚠️ 결정대기 ①) |
| `tests/test_quota_resume.py` | `_save_latest_state` 대역이 결과 dict 를 돌려준다 |
| `tests/test_b5_execution_resume.py` | 한 시험 안에서만 동결 상태를 실제대로(fixture 공유 시험 무접촉) |
| `frontend/scripts/check-studio-contracts.mjs` | 양쪽 흐름 시험 +1 — 실제 `connectSSE` → `onmessage` |

---

## 11. ⚠️ 함정 — 이번에 실제로 밟았거나 밟을 뻔한 것

9/22 인계서 §10 의 여덟 가지(러너의 `subprocess` 차단, `_LIBRARY_DIR`·`PROJECTS_DIR` 갈아끼움,
`importlib.reload` 금지, 검사 중 소스 수정 금지 등)는 그대로 유효하다. 아래는 추가분이다.

1. **기준은 손대기 전 값이다.** `aupdate_state` 뒤 checkpoint 로 견주면 정상 재개가 전부 거절된다.
2. **제자리 변경.** 기준을 참조로 넘기지 말고 `jsonable_encoder` 로 **변경 전에** 복사한다.
3. **대역의 `aget_state` 는 스트림 전후를 구분해야 한다.** 언제나 결과를 주는 대역으로는 재개 판단을
   시험할 수 없다.
4. **하네스 정리는 `onerror` 로 하지 않는다** — 5초 재연결 타이머를 건다(`check-studio-contracts.mjs:2754`).
5. **bootstrap 시험은 격리 러너 안에서만** — `operation_lock` 이 data 경로에 쓴다.
6. **A/B 는 판본을 바꿔 끼운 뒤 반드시 원복 해시를 확인한다.** 러너가 도는 중에는 바꾸지 않는다.
7. **회귀 목록이 곧 증거 범위다.** 원래 인계서 목록에 재개 경로 스위트가 없어 기존 실패 2건이 숨어 있었다.
8. **공유 스태시 금지 · `git add .` 금지 · 이 브랜치에만 커밋.** push 는 사용자 지시가 있을 때만.

---

## 12. 주장하지 않는 것

1. 실제 두 노드 공유 저장 증거가 아니다 — 전부 단일 PC 두 프로세스다.
2. 브라우저 실측 없음 — store 는 하네스(메모리 네트워크)까지다.
3. 실제 LangGraph checkpoint 저장소 수용이 아니다 — 엔진은 합성 대역이다. 「노드마다 checkpoint 와 정본을
   함께 저장한다」는 전제는 코드 경로(`_run_sprint_loop`·`_resume_stream`)에서 확인한 것이다.
4. kit 진입 시점 기준은 창을 좁힌 것이지 교체 권위를 증명한 것이 아니다(§12 지시대로 변경하지 않음).
5. 111건 · 29건 기존 실패의 원인은 확정하지 않았다.

---

## 13. 다음 착수 지점

| 순서 | 무엇 | 담당 | 착수 조건 |
|---|---|---|---|
| 1 | W03.2 재검토 + 결정대기 셋(§7) | **Codex** | 지금 가능 — 이 브랜치 HEAD |
| 2 | 회신이 CR 이면 같은 요청서 **§14** 로 회신 + 결과 문서 누적 + 상태 파일 갱신 | Claude | Codex 회신 뒤. 새 요청서 만들지 않음 |
| 3 | W03.3 연결 수용 잔여 | Claude | 선행 W03.2 수용 뒤 |
| 4 | W03.1 실제 공유 환경(두 노드 · 공유 저장) | Claude + 환경 담당 | 공유 저장 환경 확보(환경·비용 결정은 사용자) |
| 5 | R01.1 필수 provider 실제 데이터 읽기/쓰기 | Claude | 실제 앱 자산이 있는 환경(이 PC 는 `library/` 없음) |
| 6 | 111건 · 29건 원인 확정 | 미정 | 범위 밖 선언 상태 — 대응이 달라지는 건이라 기록만 둔다 |

★ 계산기의 「선행·승인 충족 단계」 목록(W03.1 · R01.1 · P03.2 · F05.1 등)은 **업무 배정이 아니다.** 담당 ·
현행 지시 · 승인 범위를 함께 본다. F05.1 은 비용 승인자가 필요하고, P03.2/3 은 Codex 별도 검토 책임이다.

---

## 14. 담당 · 경계 · 관문

- 공용 원장 · `PROGRESS.md` 의 기록자는 **Codex** 다. 가산은 Codex 수용 뒤다.
- 운영 `data/` · `library/` · `projects/` 무접촉. 서버 검증은 격리 러너(`--strict-writes`)로만.
- `data/interaction_log.jsonl` 은 사용자 소유 — 삭제 · 커밋 금지.
- 병합하지 않는다. 공유 브랜치 `codex/l2-unified-studio-20260912` 는 `9c27a9ed9` 다.
- **관문**: 운영 트라이얼 GAP 계획의 목표 묶음 **W «서버를 바꿔도 작업·이벤트·파일이 유지된다»(0/4)** 의
  W03 이다. 이번 작업은 W03.2 출구(동시 쓰기·장애 시 부분/옛 파일·다른 문맥 노출 방지)의 반례를 닫은
  것이고, 수용 전이라 묶음 진척은 **0/4 그대로**다. W03 은 P05 · W04 · C06 의 선행이다.
