# 인계서 — W03.2 마무리 (CR §12 세 건) / 2026-09-23

작성: Claude Code (이 PC 세션) · 대상: **다른 PC·다른 계정의 Claude Code 세션**
브랜치: **`claude/w03-atomic-save-20260922`** · 마지막 푸시 `c246b49fa`

> ⚠️ 이 문서는 «무엇을 했는가» 보다 **«무엇을 믿어도 되고 무엇이 아직 틀렸는가»** 를 적는다.
> 지금 저장소는 **시험 2건이 실패하는 상태**로 커밋돼 있다 — 숨기지 않고 그대로 넘긴다.

---

## 0. 30초 요약

```
지금 상태   반례 25 PASS / 2 FAIL  (+ 프런트 하네스 1 FAIL)
남은 것     CR §12 의 P1 세 건.  «조건을 덧붙이지 말고 한 흐름으로 연결» 하는 일
다음 분량   정상 시작 · 정상 재개 · 낡은 재개  세 갈래를 먼저 함께 닫기 (60~90분)
전체 잔여   3~5시간 잠정
진척        1855/5300 = 35.0% (이번 보완으로 가산 없음)
```

**가장 먼저 읽을 것**: `docs/handoff/CLAUDE_REVIEW_REQUEST_W03_R01_2026-09-22.md` **§12**
(line 504~). 이 인계서는 그 지시를 실행 가능한 형태로 풀어 놓은 것이다.

---

## 1. 지금 무엇이 실패하고 있나 — 실행해서 확인할 것

```powershell
venv/Scripts/python.exe -X utf8 -B scripts/verify_data_usage_holds.py --strict-writes `
  --target tests/test_w03_review_counterexamples.py --target tests/test_w03_conditional_save.py
```

이 PC 실측: **25 passed / 2 failed / exit 1**

```
FAILED tests/test_w03_review_counterexamples.py::
  test_start_and_resume_bind_the_actual_input_revision[normal-start-through-entry]
  test_start_and_resume_bind_the_actual_input_revision[resume-older-checkpoint]
```

프런트 하네스(Codex 가 1건 추가):

```powershell
node frontend/scripts/check-studio-contracts.mjs
```

Codex 실측: 기존 157 PASS / 추가 1 FAIL.

⚠️ **이 실패들은 고쳐야 할 결함이지, 시험이 잘못된 것이 아니다.** 시험을 고쳐 초록으로
만들지 말 것.

---

## 2. 남은 세 건 — 원인은 전부 «내가 조건을 하나씩 덧댄 것»

### P1-① 정상 시작도 저장 거절

`start_sprint` 가 `terminal_status`·`terminal_reason` 을 **먼저 초기화**한 뒤,
`_run_sprint_loop` 이 **그 바뀐 payload 전체**를 파일과 비교한다. 그래서 파일을 정확히
읽어 보낸 정상 요청도 「입력이 파일과 다르다」로 판정돼 `claimed=false` 가 되고, 계산이
끝난 뒤 저장이 거절된다.

- 관련: `core/async_orchestrator.py` — `start_sprint`(초기화) · `_run_sprint_loop`(비교)
- ⚠️ **비교 제외 필드를 계속 늘리는 방식으로 풀지 말 것**(지시 명시). 기준 토큰과
  실행용 payload 를 **분리**해야 한다.

### P1-② 낡은 checkpoint 재개가 최신 정본을 덮음

`_resume_stream` 이 `started_from` 없이 인수한다. 내가 달아 둔 주석
「checkpoint 에서 이어받으므로 경쟁 판본에서 파생된 것이 아니다」는 **근거가 아니라
주장**이었다. 옛 checkpoint 가 남은 상태에서 다른 writer 가 정본만 갱신한 반례에서,
재개 결과가 최신 정본을 덮고 `state_saved=true` 가 됐다.

- ⚠️ **재개에서 인수를 전부 금지하면 정상 재개가 다시 깨진다**(앞 라운드에서 실제로
  그랬다). 「checkpoint 가 어느 정본에 연결되는가」를 실행 **전에** 판단해야 한다.

### P1-③ 옛 정본 GET 성공을 저장 회복으로 취급

`fetchLatestState` 가 `status=success` 면 무조건 `lastStateSaveError=null` 로 만든다.
**저장이 실패해도 예전 정본 GET 은 성공한다.** 게다가 `NODE_COMPLETED`/`SPRINT_COMPLETED`
가 자동 재조회를 하므로 경고가 곧 사라진다.

★ 이것은 내가 바로 앞 라운드에서 「걸기만 하고 안 내리면 소음이 된다」며 넣은 해제다.
**읽기 성공과 실패한 쓰기의 회복은 별개**라는 것을 놓쳤다.

- 관련: `frontend/src/store/useFactoryStore.ts` `fetchLatestState`
- 해제 근거는 **기대한 저장 판본의 확인** 또는 **명시적 회복/포기 결정**이어야 한다.
  단순 GET 200·시간 경과로 해제하지 않는다.

### 추가 정적 잔여 (같은 규칙에 포함)

- `core/studio_bootstrap.py` 초기 기록: `_, state_digest = read_json_with_digest(...)` 로
  **내용을 버리고** 쓴다. READY 갱신의 읽기-수정-쓰기와 모양이 다르다.
- `core/kit_app_builder.py` 진입 시점 CAS 는 **함수 내부 경쟁 범위를 줄인 것**이며,
  이미 만들어져 전달된 계약의 **교체 권위를 증명한 것이 아니다**(내가 명시한 한계 유지).
  별도 제품 권한 정책은 만들지 않는다.

---

## 3. 요구된 설계 — 조건을 덧대지 말고 **하나의 흐름**

```
변경 전 읽기 / 검증된 checkpoint
   → 내용에 결속된 «기준 토큰»
   → 실행용 변경(payload 가공은 여기서)
   → 같은 실행의 조건부 저장
   → 저장된 판본 확인
   → 실패 안내 해제
```

1. **시작**은 `terminal` 초기화 등 정상 가공 **전에** 기준을 고정한다. 이후 바뀐 payload
   의 전체 동일성으로 원래 읽기를 판정하지 않는다. 기준은 저장까지 **실행 단위로 전달**한다.
2. **재개·쿼터 재개**는 checkpoint 가 어느 정본에 연결되는지 검증한다. 다른 writer 의 새
   정본과 어긋나면 최신 digest 로 승인하지 말고 기존 회복/재조회 경로로 구분한다.
   **정본과 일치하는 checkpoint 의 정상 재개는 유지**한다. 저장 함수의 키와 호출자의
   실행 키를 통일한다.
3. **bootstrap** 초기 생성/복구는 앞선 읽기와 **검증한 소유·단계**의 기준을 쓴다. 읽은
   내용을 버린 채 쓰기 직전 새 기준을 받아들이지 않는다. READY 경로·기존 실패 주입
   회귀는 유지한다.
4. **store/UI** 는 미저장 결과의 **식별 정보를 유지**한다. 옛 정본을 «표시하는 것» 과
   미저장 결과가 «복구된 것» 을 구분한다. 확인된 회복·프로젝트 전환·명시 결정 때만
   표시를 정리한다. `저장 실패 → 옛 GET → 경고 유지 → 정상 저장 확인 → 해제` 의 양쪽을
   **같은 실제 store 흐름**에서 확인한다.

---

## 4. ⚠️⚠️ 착수 전에 반드시 풀어야 할 «설계 충돌» 하나

**같은 파일 안의 두 시험이 재개에 대해 서로 다른 것을 요구하는 것처럼 보인다.**
내가 확인한 사실만 적는다 — 판단은 다음 세션이 하되, **모르고 밟지 않도록** 남긴다.

| 시험 | 파일 상태 | 엔진 `aget_state` | 기대 |
|---|---|---|---|
| `test_product_loop_preserves_revision_contract[restart-resume]` (기존, **통과 중**) | `{"value":"base"}` | 항상 `{"value":"resume-result"}` | **저장 성공** |
| `test_start_and_resume_bind_the_actual_input_revision[resume-older-checkpoint]` (신규, **실패 중**) | `{...,"value":"new-confirmed"}` | 스트림 전 `{...,"value":"base",...}` | **저장 거절** |

두 경우 모두 **스트림 직전 `aget_state()` 값이 파일과 다르다.** 그래서
「스트림 전 checkpoint == 파일이면 인수, 아니면 거절」이라는 단순 규칙을 넣으면
**신규는 통과하지만 기존이 깨진다.**

차이를 가르는 단서(내가 관찰한 것):
- 기존 시험의 대역 엔진은 **checkpoint 개념이 없다** — `aget_state` 가 언제나 «결과» 를
  돌려준다(스트림 전후 구분이 없음).
- 신규 시험의 대역 엔진은 `self.values = dict(checkpoint)` 로 **스트림 전 상태를 들고
  있다가** 스트림에서 갱신한다.

→ **가능한 해석**: 「스트림 전 상태를 물어볼 수 있는 엔진」에서만 정합성을 판단하고,
그렇지 않으면 다른 근거(예: 파일 자체를 기준으로 한 조건부 저장)로 간다. 다만 이것은
**내 해석이지 지시가 아니다.** 규칙을 정하기 전에 두 시험의 의도를 Codex 에게 확인하거나,
둘 다 만족하는 규칙을 찾은 근거를 문서에 남길 것.

⚠️ 기존 시험을 「낡았다」며 고쳐 초록으로 만들지 말 것. 두 시험 다 Codex 가 쓴 반례다.

---

## 5. 지금까지 해 둔 것 — **믿어도 되는 것**

이번 브랜치에서 이미 닫혀 회귀로 지켜지고 있는 것들(다시 만들지 말 것):

| 항목 | 상태 |
|---|---|
| lost update 조건부 저장(`atomic_write.*_if_unchanged`) | 있음. 비교·교체가 같은 상호배제 구간 |
| 잠금 권위를 **정본 옆**에 | 있음(`_target_lock`). `data/` 노드 로컬 잠금과 구분 |
| 링크 검사 **전체 조상** + 정식 mount 면제 | 있음. `root` 는 담김 확인에만 |
| `mkdir` 을 링크 경계 안으로(`ensure_directory`) | 있음 |
| 실행 단위 기준 키(`_skey(pid, task_id)`) | 있음 |
| 같은 바이트에서 내용+지문(`read_json_with_digest`) | 있음 |
| writer 의미 분리(생성=배타, 갱신=조건부) | 있음. 표는 §7 |
| 프로젝트별 저장 실패 기록 | 있음(`state_save_failures`) |
| `NODE_COMPLETED`·`SPRINT_COMPLETED`·`QUOTA_EXHAUSTED` 의 `state_saved` | 있음 |
| 기존 `ControlPanel` 상태 줄에 실패 안내 | 있음(새 화면 아님) |
| 잠금 파일 규약(`LOCK_SUFFIX`) + 배포 제외 | 있음 |

---

## 6. 환경·명령

```powershell
# 집중 (반례 + 조건부 저장)
venv/Scripts/python.exe -X utf8 -B scripts/verify_data_usage_holds.py --strict-writes `
  --target tests/test_w03_review_counterexamples.py --target tests/test_w03_conditional_save.py

# 영향 흐름까지
… --target tests/test_w03_atomic_save.py --target tests/test_b3_studio_bootstrap.py `
  --target tests/test_w03_release_consistency.py --target tests/test_w03_shared_release_read.py `
  --target tests/test_r01_provider_path.py

# 넓은 회귀 (10분 내외) — 마지막에 한 번만
… + tests/test_b3_kit_contract_v2.py tests/test_program_lifecycle.py `
    tests/test_release_readiness.py tests/test_app_delivery_real_release.py `
    tests/test_kit_app_api.py tests/test_release_artifact.py

# 프런트
cd frontend && npx tsc -b --force
node frontend/scripts/check-studio-contracts.mjs

# probe (격리 러너 밖 — 러너가 subprocess 를 막는다. 끄지 말 것)
venv/Scripts/python.exe -X utf8 -B scripts/w03_atomic_write_probe.py lost-update --writers 3 --rounds 40
venv/Scripts/python.exe -X utf8 -B scripts/w03_atomic_write_probe.py compare
venv/Scripts/python.exe -X utf8 -B scripts/w03_shared_read_probe.py compare
```

⚠️ **111건 계열은 회귀에 넣지 말 것** — `test_app_data_runtime` · `test_provider_dispatch` ·
`test_advisor_bootstrap`. HEAD 부터 실패하는 기존 결함이라 귀속이 섞인다.

---

## 7. writer 표 (현재)

| writer | 의미 | 처리 |
|---|---|---|
| `async_orchestrator._save_latest_state` | 갱신 | 조건부 + 실행 단위 기준 ⚠️ §2-①② 미완 |
| `advisor_control:_write_json`(→ :503) | **생성**(`latest_state.json`) | 배타 생성 |
| `factory_control:1176·1190` | 생성(`allocate()` id) | 그대로 |
| `factory_control` 릴리스 1번째 | **생성**(⚠️ **초 단위 id**) | 배타 생성 → 409 |
| `factory_control` 릴리스 2번째 | **갱신** | 첫 쓰기 digest 기준 |
| `kit_app_builder.publish_release` | **갱신**(`release_id_for` 결정론적) | 진입 시점 기준 ⚠️ 권위 미증명 |
| `studio_bootstrap` 초기/READY | 생성/갱신 | READY 는 읽기-수정-쓰기, 초기는 §2 잔여 |
| `studio_project_files.write_json` | 공용 | `expected_digest` 선택 인자 |

---

## 8. ⚠️ 이 브랜치에서 실제로 밟은 함정 (되풀이 금지)

1. **격리 러너는 `subprocess.Popen` 을 막는다.** 두 프로세스 증거는 probe 로, 러너 밖에서.
2. **러너는 `_LIBRARY_DIR`·`PROJECTS_DIR` 을 자기 실행 뿌리로 갈아끼운다**(cwd 가 아니다).
   시험에서 「살아 있는 값 == PROJECT_ROOT/…」를 단언하면 깨진다. `runpy` 로 새 이름공간에서.
3. **`importlib.reload` 금지.** 세션이 오염된다(단독 15건 통과하던 스위트가 묶음에서
   4실패·9오류가 됐다).
4. **검사가 도는 중에 소스를 만들거나 고치지 말 것.** `sources_unchanged: false` 가 찍히면
   그 실행 전체가 증거로 못 쓰인다(내가 한 번 버렸다).
5. **대역의 인자가 안 맞는다고 제품을 되돌리지 말 것.** 대역이 계약 변경을 반영하면
   된다. 실패 지점·의미는 보존하고 인자만 전달한다(내가 한 번 잘못 철수했다).
6. **「쓰기 직전에 digest 를 읽어 기준으로 삼기」는 조건이 아니라 형식이다.** 내가 남의
   코드에서 잡아 놓고 내 코드(kit)에 그대로 남겨 뒀다.
7. **주석으로 생략한 검사는 검사가 아니다.** 「뿌리보다 위는 배포의 몫」이라고 적은 그
   주석이 곧 구멍이었다.
8. **`git add .` 금지.** 공유 트리다. 파일을 짚어서 넣고, **이 브랜치에만** 커밋한다.

---

## 9. 주장하지 않는 것 (그대로 유지)

1. **실제 두 노드 공유 저장 증거가 아니다.** 모든 증거가 단일 PC 두 프로세스다.
   잠금을 정본 옆에 뒀지만 **공유 프로토콜이 파일 잠금을 지원해야** 성립한다.
2. **브라우저 실측 없음.** store/UI 변경은 타입체크와 코드 경로까지다.
3. **정식 mount 면제는 분기 시험까지** — 실제 배포 mount 승인·동작 증거가 아니다.
4. **파일 심볼릭 링크 거절 미실측**(Windows 권한). skip 3건의 원인은 전부 이것이다:
   `test_w03_atomic_save::test_a_linked_target_is_rejected` ·
   `test_b3_studio_bootstrap::test_real_factory_untrusted_marker_tmp_is_preserved_and_blocked[symlink]` ·
   `…[dangling-symlink]`. 개발자/관리자 모드는 변경하지 않는다.
5. **kit 의 진입 시점 기준은 창을 좁힌 것**이지 교체 권위를 증명한 것이 아니다.
6. **111건 기존 실패의 원인 미확정.**

---

## 10. 담당·경계

- **이 작업은 Claude 담당**이다. C02/C03/OPS-P1·P2·배포관리 콘솔은 **Codex** 다.
  착수 전 `docs/roadmap/OPERATIONAL_TRIAL_GAP_PLAN.md` 의 항목별 **담당/선행**과
  **「Gap/할 일」 칸 안의 금지문**을 확인할 것 — 이 세션에서 그걸 빠뜨려 C03 을 잘못
  집었다가 철수했다.
- 계산기의 「착수 가능」 목록은 **선행만** 푼 것이고 담당이 아니다.
- 공용 원장·`PROGRESS.md` 의 기록자는 **Codex** 다. 내가 갱신하지 않는다.
- 운영 `data/`·`library/`·실사용자 자료 무접촉. 검증은 격리 러너로만.
- 병합은 하지 않는다. 공유 브랜치 `codex/l2-unified-studio-20260912` 는 `9c27a9ed9` 다.
