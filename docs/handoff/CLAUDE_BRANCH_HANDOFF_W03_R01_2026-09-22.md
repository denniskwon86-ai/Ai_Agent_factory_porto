# 인수인계 — 브랜치 `claude/w03-atomic-save-20260922` (W03.1~3 · R01.1)

작성: Claude Code (다른 PC 세션) / 2026-09-22
대상: **Codex**(수용 검토) 및 **이 브랜치를 이어받을 다음 세션**

> ⚠️ 이 문서는 «무엇을 했는가» 보다 **«무엇을 믿어도 되고 무엇을 다시 확인해야 하는가»**
> 를 적는다. 앞 인계서(`CLAUDE_SESSION_HANDOFF_2026-09-22.md`)의 원칙을 그대로 따른다.

---

## 0. 30초 요약

```
브랜치   claude/w03-atomic-save-20260922   (기준 9c27a9ed9, 커밋 14개)
⚠️ 공유 브랜치 codex/l2-unified-studio-20260912 는 원격·로컬 모두 9c27a9ed9 그대로다

제출      W03.1 +45 · W03.2 +45 · W03.3 +40 · R01.1 +20   → 전부 Codex 수용 대기
진척      1855/5300 = 35.0% 유지 (착수·시험 건수로 가산하지 않았다)
제품      2 신규 + 8 수정 · 시험 46건 · probe 2 (1 신규 · 1 확장)
결정대기  ①「잘못된 판본」이 lost update 를 포함하는가(점수 직결) ②CR-1 방향 재확인
```

**세 가지 발견이 이 브랜치의 실질이다** — §3. 나머지는 그 발견을 잠근 것이다.

---

## 1. ⚠️ 먼저 — 브랜치가 따로다

사용자가 「pull 당겨온 작업트리 말고 별도 브랜치에 커밋한 거 맞지?」라고 물어 확인해 보니
**아니었다.** 나는 pull 해온 `codex/l2-unified-studio-20260912` 에 직접 커밋하고 있었다.
푸시 전이라 원격은 무사했고, `git switch -c` + `git branch -f` 로 옮겼다(`reset --hard`
쓰지 않음). 지금 상태:

| | 위치 |
|---|---|
| 이 작업 커밋 14개 | `claude/w03-atomic-save-20260922` (원격 동기화됨) |
| `codex/l2-unified-studio-20260912` | **`9c27a9ed9`** — 로컬·원격 모두 무변경 |

★ 그래서 **공유 브랜치에서는 아래 문서들이 보이지 않는다.** 수용 검토는 이 브랜치를
받아서 해야 한다.

---

## 2. 무엇을 했나 — 단계별

### 2.1 W03.2 원자 저장 (+45)

★ **원자 쓰기 구현이 이미 저장소에 있었다**(`core/studio_project_files.py:30`). B3 승격
저장만 쓰고 있었고, **정본을 쓰는 나머지 7곳이 전부 `open(...,"w")` 직접 쓰기**였다.
만든 쪽은 있고 쓰는 쪽이 안 붙은 **배선 누락**이다.

구현을 `core/atomic_write.py` 한 곳에 두고 7곳을 전환했다.
⚠️ 인계서 §4 의 시작 지점 표를 정정한다 — 쓰는 곳은 3곳이 아니라 **7곳**이고,
`factory_control.py:749` 는 **읽는 곳**이다(`_restore_accumulated_from_disk`).

지킨 것 둘:
- **직렬화 정책을 모듈이 강제하지 않는다.** `sort_keys` 를 공통으로 걸면 내용이 같은데
  키 순서가 바뀌어 **digest 가 달라지고**, W03.1 이 판본 동일성을 digest 로 보므로 그
  증거와 충돌한다. 같은 이유로 텍스트 모드를 유지했다(바이너리로 바꾸면 줄바꿈 변환이
  사라져 digest 가 달라진다).
- **대상이 링크면…** → 처음엔 따라갔다가 **CR-1 로 뒤집었다**(§2.3).

⚠️ **부분 파일만 막는다.** lost update 는 다른 문제이며 풀지 않았다 — §6-①.

### 2.2 W03.1 보완 (+45)

첫 제출(다른 PC 세션)은 **릴리스 한 갈래**였고 출구는 「두 노드가 같은 **프로젝트/릴리스**
판본을 읽고 **접근권한을 확인**」이다. 빠진 둘을 채웠다.

- **프로젝트 갈래** — 격리 지점은 `core.paths.PROJECTS_DIR` 하나(`workspace_path()` 가
  호출 시점에 읽는다).
- **접근권한** — `ownership_visible` 로 주체 3종. 소유부서 보임 / **타부서 거절** /
  unrestricted 보임.
- ★ **권한 판정도 자식 프로세스 안에서** 한다. 부모가 대신 계산하면 「그 노드가 그렇게
  판정한다」가 아니라 「내가 계산했다」가 된다. 그래서 **두 노드 판정 일치**까지 증거에
  넣었다 — 판본이 같아도 판정이 갈리면 한쪽에서만 열리는 자원이 된다.

새 도구를 만들지 않고 기존 `w03_shared_read_probe.py` 를 넓혔다.

### 2.3 CR-1 링크 정책 정정 + 저장 실패 관측

자기 검토(§7)에서 잡은 차단 결함이다.

**CR-1**: `atomic_write` 가 링크를 **따라가게** 만들었는데 근거가 틀렸다. 이 저장소는
읽는 쪽에서 링크를 **아홉 곳에서 거절**한다(`async_orchestrator:295` ·
`factory_control:2448·2631·2662` · `studio_project_files:53·56` · `studio_pause_state:37` ·
`studio_revision_requests:81·87` · `studio_contract_reconcile:219·292` ·
`studio_input_draft_control:106`). 따라가면 **`latest_state.json` 이 링크일 때 쓰기는
성공하고 읽기는 503** — W03 이 없애려던 「한쪽에서만 열리는 자원」을 오히려 만든다.
**차단으로 뒤집었다**(대상 + 부모, `factory_control:2631` 과 같은 수준).

**저장 실패 관측**: `_save_latest_state` 의 `except: print` 삼킴은 **유지**했다 — 예외를
올리면 상태 저장 하나 때문에 스프린트 실행 전체를 잃고 그쪽이 더 나쁘다. 대신
`orchestrator.last_state_save_error` 에 남기고(성공하면 지움) 기존 `factory_broadcaster` 로
`STATE_SAVE_FAILED` 를 알린다. **알림이 깨져도 기록은 남는다.**

### 2.4 W03.3 DB·파일 일관성 (+40)

릴리스의 사실이 **두 곳에 나뉘어** 있고 **대조하는 곳이 없다**.

```
library/<id>/release.json     정본 — 무엇인가 · 누구 것인가(소유문맥)
data/program_lifecycle.db     사용여부 — 켜져 있는가 · 왜 껐는가
```

| 조합 | 판정 |
|---|---|
| 파일 O + 행 X | **불일치 아님** — `get_status` 가 미기록을 `active`·`recorded=False` 로 답하도록 **설계**돼 있다. 세면 구 릴리스가 매번 경보 |
| **파일 X + 행 O** | ⚠️ **불일치** — 같은 질문에 두 답 |

`core/release_consistency.py`(읽기 전용)가 식별하고, **사용자 결정 ②「행 보존 + 격리
표시」**를 `ProgramLifecycle.effective_status()` 로 구현했다 — 정본이 없으면 **빈 문자열**.
행은 지우지 않으므로 **재게시하면 껐던 결정이 그대로 살아난다**(①이었다면 꺼 둔 프로그램이
`active` 로 돌아온다).

⚠️ **새 상태 어휘를 만들지 않았다.** 빈 문자열을 쓴다 — 받는 자리들이 이미 「모르면 접지
않는다」이기 때문이다(`audience_for_state("")` → 청중 없음 → 평면도 안 고름).

⚠️ **정정**: 앞서 「위험한 호출자 다섯」이라 적었으나 **셋**이었다. `calculation_control:683`
과 `data_preparation_control:1475` 는 **이미 정본을 확인**하고 있었고, 그 둘은 그대로 뒀다 —
calculation 쪽은 정본 없음을 「아직 생성되지 않았습니다」(409)로 **구분해 답하고** 그 구분이
쓸모 있다. 공통 함수로 뭉뚱그리면 그 말이 사라진다.

### 2.5 R01.1 provider 실제 경로 (+20)

**이미 구현돼 있었다.** `provider_for_intent` 는 모르면 빈 문자열, `resolve` 는 미지원을
`NOT_YET_SUPPORTED` 로 거절(빈 목록 아님), 쓰기는 Native 하나. 기존
`test_provider_dispatch` 가 단위 27건을 덮는다.

빠진 것은 **실제 경로**(`app_data_runtime._dispatch`)가 단위로 검증된 적이 없다는 것이다.
HTTP 로만 간접 확인됐고 그 HTTP 시험이 이 환경에서 **10건 깨져 있다**(§3.3).
`_plane` 하나만 대신하면 단위 호출이 되어 12건으로 덮었다. **제품 코드 변경 0.**

---

## 3. ★ 발견 셋 — 이 브랜치에서 가장 값있는 것

### 3.1 MAX_PATH — 회귀가 내 결함을 잡았다

`test_b3_kit_contract_v2` 가 `FileNotFoundError` 로 깨졌다. 경로 **278자**:

```
…/kitapp_ki_604d5af5542747dfaa9671e49097c7f8_APP-03/release.json.<uuid32>.tmp
                                                    ^^^^^^^^^^^^  +37자
```

**원본 `release.json` 은 써지는데 임시 파일만 못 만드는** 상태였다. Windows 한계(260) 초과.
**원자 저장을 넣었더니 원래 되던 게 안 된 것**이라 결함이다.

고침 — 임시 이름을 **정본보다 길지 않게**: `.<hex6>.tmp`(11자) vs `release.json`(12자).
원본을 쓸 수 있는 경로면 임시도 쓸 수 있다는 것이 불변식이다.

★★ **이 결함은 W03.2 회귀 묶음(8스위트)에서는 안 잡혔다 — 경로가 짧아서다.**
W03.3 을 하며 묶음을 넓혔더니 나왔다. **회귀 범위가 곧 증거의 범위다.**

### 3.2 「이 출처가 지금 되는가」가 두 곳에 있다

```
core/app_runtime_contract.py  SOURCE_INTENT_DECISION   ← 앱을 «만들 때» 보는 표
core/host_runtime_provider.py SERVING_PROVIDERS        ← 앱이 «돌 때» 보는 표
```

**지금은 일치한다.** 그러나 한쪽만 열면 **앱은 만들어지는데 실행이 거절**되고, 어느 쪽도
미리 오류를 내지 않는다. 이 저장소가 여러 번 겪은 「판정이 두 곳에 있다」 유형이다.
`test_the_two_support_tables_say_the_same_thing` 이 갈림을 잡는다(변이로 확인).

### 3.3 111건 기존 실패 — 제품 결함이 아닐 가능성

이 PC 에서도 재현된다(`test_app_data_runtime` **28 failed**, 원래 PC 보고와 같은 수).
증상을 모아 보면:

```
test_app_data_runtime    26건  같은 이름의 데이터셋이 이미 있습니다: orders
test_provider_dispatch   10건  «arrivals» 를 제공하는 원천이 2개입니다 — 사람이 정해야 합니다
test_advisor_bootstrap   19건  fixture 'seeded_org' not found
```

**셋 다 제품이 «올바르게 거절»하거나 픽스처가 없어서 나는 실패로 보인다.** 공통점은
격리 러너가 **저장소 conftest 를 읽지 않는다**는 것이다(`repository_conftest_loaded: false`).

⚠️ **추정이다.** A/B 도 conftest 적재 실험도 하지 않았다. 다만 「제품이 깨져 있다」와
「검증 인프라가 이 스위트를 못 돌린다」는 **대응이 완전히 다르므로** 적어 둔다.
내 변경 심볼이 traceback 에 등장한 실패는 **0건**이다.

---

## 4. ⚠️ 내가 틀린 것 — 그대로 남긴다

1. **브랜치를 안 나눴다.** 공유 브랜치에 직접 커밋했고 사용자가 짚어 알았다(§1).
2. **CR-1 — 링크 정책 근거가 틀렸다.** 자기 검토에서 잡았다(§2.3).
3. **MAX_PATH 결함을 만들었다.** 회귀가 잡았다(§3.1).
4. **계측을 섞었다.** 부분 파일(파싱 실패)과 Windows 공유 위반(열기 실패)을 한 칸에 세어
   **원자 모드가 실패한 것처럼 보였다.** 나눠 세니 부분 파일은 0. 계측 잘못을 제품 결함으로
   보고할 뻔했다.
5. **회귀 묶음을 잘못 골랐다.** `test_advisor_bootstrap` 을 넣어 19 errors 를 봤는데 그
   스위트는 conftest 의존이라 **러너 대상이 아니었다.**
6. **인계서 지뢰 #3 을 그대로 밟았다.** 살아 있는 `PROJECTS_DIR` 를 `PROJECT_ROOT/projects`
   와 견주었다가 실패 — 러너가 그 상수도 갈아끼운다. 앞 세션이 릴리스 쪽에서 겪고 적어 둔
   것을 프로젝트 쪽에서 반복했다.
7. **느슨한 시험을 두 번 썼다.** W03.3 에서 한 번, R01.1 에서 또 —
   `status_code >= 400` 만 보면 「미지원이라 거절」과 「키가 없어 거절」이 구분되지 않고
   **변이에서도 초록**이었다. 9/15 에 배운 것을 또 밟았다.
8. **「다섯 호출자」로 과장했다.** 실제로는 셋이었다(§2.4).

---

## 5. 환경 — 이 PC 의 제약

| 항목 | 이 PC | 원래 PC |
|---|---|---|
| Python | **3.12.10** | 3.14.3 |
| Docker / PG | **없음**(설치 안 됨) | 있음 |
| `library/` · `projects/` | **0건 · 0건** | 29 · 73 |
| C 드라이브 여유 | **12.0 GB** | — |

- **PG 는 W03·R01 에 필요 없었다.** 지시 원문에 DB·PG 언급이 없다.
- **`library/` 0건 때문에 R01.1 의 「대상 7앱 요구 실측」을 못 했다**(§6-③).
- Python 3.12 에서 W03·R01 관련은 전부 통과했으나 **전체 회귀는 돌리지 않았다.**
  다른 영역까지 3.12 에서 동등하다고 주장하지 않는다.
- Docker 설치 시 5~8 GB 가 필요한데 여유가 12 GB 다. 설치 전에 정리하는 편이 안전하다.

---

## 6. ⚠️ 결정·판단이 필요한 것

### ① 「잘못된 판본」이 lost update 를 포함하는가 — **점수에 직결**

W03.2 acceptance 는 「부분 파일**이나 잘못된 판본**을 읽지 않도록」이다. 지시 §4-2 의
「다른 문제」는 **「한 번에 달성했다고 쓰지 말라」**이지 「하나만 해도 된다」가 아니다.
포함한다면 W03.2 는 잔여를 안은 **부분 수용**이고, 아니라면 완결이다.

관련해서 **「정상 반환한 성공 버전의 소실을 허용하지 않는다」가 `_save_latest_state` 에서
여전히 깨질 수 있다** — Windows 교체 거절(실측 41/180)이 예외로 오는데 그 함수가 삼킨다.
이번에 관측은 붙였지만 소실 자체는 막지 않았다.

### ② CR-1 방향 재확인

링크 차단이 맞는지. 근거로 든 아홉 곳은 **전부 읽기·검증 경로**이고, **쓰기 쪽 정책이
명시된 문서는 찾지 못했다.** 공유 마운트 지원이 별도 계획에 있다면 방향이 다를 수 있다.
그 경우 **읽기·쓰기를 함께** 바꿔야 한다.

### ③ R01.1 은 전체 충족이 아니다

「대상 7앱의 요구」를 실측하지 못했다. 합성 앱의 의도는 내가 정하는 것이라 답이 되지 않는다.
**실제 앱 자산이 있는 환경에서 다시 봐야 한다.** 토큰/권한 상속(GAP 의 나머지 절반)은
R01.2·R01.3 범위로 두었다.

### ④ 낮은 우선순위

- 원자 쓰기 구현 **4→1 통합** — `config_snapshot:160` · `contract_decision:298` 이 남아 있다.
  정본 저장이 아니라 급하지 않다. 「구현을 한 곳에」는 **정본 저장 범위로** 좁혀 읽을 것.
- `test_advisor_bootstrap` 의 러너 fixture 부채.
- 111건 원인 확정(§3.3) — 범위 밖으로 선언됐으나 대응이 달라지는 건이다.

---

## 7. 자기 검토에 대하여

중간에 사용자가 「이 브랜치에 한해 Codex 를 대신해 검토·지시하라」고 지시해
`CODEX_W03_REVIEW_AND_NEXT_2026-09-22.md` 를 썼다. **독립 검토가 아니다** — 같은 세션이
만들고 같은 세션이 봤다. 그래서 **공용 원장·PROGRESS 를 갱신하지 않았고 점수도 올리지
않았다.** 다만 그 검토가 CR-1(차단 결함)을 잡았으므로 버리지 말 것.

---

## 8. 코드 지도

| 층 | 파일 | 비고 |
|---|---|---|
| 원자 저장 | `core/atomic_write.py` | **신규 135줄.** 구현은 여기 한 곳 |
| 〃 소비 | `studio_project_files` · `kit_app_builder` · `async_orchestrator` · `factory_control`(2) · `advisor_control` | 정본 쓰기 7곳 |
| 불일치 식별 | `core/release_consistency.py` | **신규 118줄. 읽기 전용** |
| 격리 판정 | `ProgramLifecycle.effective_status()` | 정본 없으면 빈 문자열 |
| 〃 소비 | `app_data_control:349` · `app_data_runtime:237` · `factory_control:2881` | 셋 |
| provider | `core/host_runtime_provider.py` | **변경 없음**(이미 되어 있었다) |

**시험·probe**

| 파일 | 건수 |
|---|---|
| `tests/test_w03_atomic_save.py` | **19** (신규) |
| `tests/test_w03_release_consistency.py` | **11** (신규) |
| `tests/test_r01_provider_path.py` | **12** (신규) |
| `tests/test_w03_shared_release_read.py` | 4 → **8** |
| `scripts/w03_atomic_write_probe.py` | **신규** — 경쟁 + 음성 대조군 |
| `scripts/w03_shared_read_probe.py` | 확장 — 프로젝트 갈래·접근권한 |

---

## 9. 재현 명령

### 9.1 probe — **격리 러너 밖**에서 돈다

러너가 `subprocess.Popen` 을 막으므로 독립 프로세스 증거는 여기서만 만들어진다.
**그 통제를 끄지 말 것.**

```powershell
venv/Scripts/python.exe -X utf8 -B scripts/w03_atomic_write_probe.py compare
```

기대: `exit 0` · atomic `torn: 0` · **음성 대조군 `torn > 0`**(경쟁 실재 증명. 대조군이
깨지지 않으면 probe 가 `exit 2` 로 「증거가 아니다」라고 알린다).

```powershell
venv/Scripts/python.exe -X utf8 -B scripts/w03_shared_read_probe.py compare
```

기대: `exit 0` · 판정 **6/6 true**(릴리스·프로젝트 공유, 각 음성 대조군, 노드 간 판정 일치,
타부서 거절).

### 9.2 시험

```powershell
venv/Scripts/python.exe -X utf8 -B scripts/verify_data_usage_holds.py --strict-writes --target tests/test_w03_atomic_save.py --target tests/test_w03_release_consistency.py --target tests/test_w03_shared_release_read.py --target tests/test_r01_provider_path.py
```

기대: **50 passed / exit 0** · `sources_unchanged: true` · `protected_assets_unchanged: true`
· `blocked_file_writes: []`.

### 9.3 넓은 회귀 (오래 걸린다 — 스위트당 최대 23분)

```powershell
venv/Scripts/python.exe -X utf8 -B scripts/verify_data_usage_holds.py --strict-writes --target tests/test_b3_kit_contract_v2.py --target tests/test_b3_promotion.py --target tests/test_kit_app_builder.py --target tests/test_app_delivery.py --target tests/test_program_lifecycle.py --target tests/test_release_readiness.py
```

⚠️ **`test_app_data_runtime` · `test_provider_dispatch` · `test_advisor_bootstrap` 은 넣지
말 것** — 111건 계열로 기존 실패가 나오고 귀속이 섞인다(§3.3).

---

## 10. ⚠️ 함정 — 이 브랜치에서 실제로 밟은 것

1. **격리 러너는 `subprocess.Popen` 을 막는다.** 두 프로세스 증거는 probe 로, 러너 밖에서.
2. **러너는 `_LIBRARY_DIR` 과 `PROJECTS_DIR` 을 자기 실행 뿌리로 갈아끼운다**(cwd 가 아니다).
   시험에서 「살아 있는 값 == PROJECT_ROOT/…」를 단언하면 깨진다. `runpy` 로 새 이름공간에서만.
3. **`importlib.reload` 금지.** 세션이 오염된다. `runpy.run_path` 를 쓴다.
4. **검사가 도는 중에 소스를 고치지 말 것.** `sources_unchanged: false` 가 찍히면 그 실행
   전체가 증거로 못 쓰인다.
5. **`monkeypatch.setattr(atomic_write.os, "replace", …)` 는 전역 `os.replace` 를 바꾼다.**
   패치 뒤에 `os.replace` 를 집으면 가짜를 집는다 — 진짜는 모듈 적재 시점에 잡아 둘 것.
6. **느슨한 상태코드 단언 금지.** `status >= 400` 만 보면 이유가 달라져도 초록이다.
7. **검사를 넣었으면 대상 줄을 지워 볼 것.** 실패하지 않으면 그 검사는 아무것도 안 지킨다.
8. **`git add .` 금지.** 파일을 짚어서 넣는다. 그리고 **이 브랜치에만** 커밋한다.

---

## 11. 다음 착수 지점

| 후보 | 상태 |
|---|---|
| **R01.2** Host 신원·능력 차단 (25점) | 선행 **R01.1 미수용** |
| **F05.1** 실행 전 한도 집행 (20점) | 선행 F02.1 충족 · **비용 승인자 필요** |
| W03 잔여 (lost update) | **§6-① 결정 후** — 별도 단계로 뗄지부터 |
| R01.1 나머지 (대상 앱 실측) | **실제 앱 자산이 있는 환경 필요** |
| §6-④ 낮은 순위 셋 | 언제든 |

★ 계산기의 「선행·승인 충족」 목록은 **업무 배정이 아니다.** GAP_PLAN 의 담당과 「할 일」
칸 **안의** 금지문을 함께 볼 것 — 앞 세션이 C03 을 그렇게 잘못 집었다.

```powershell
venv/Scripts/python.exe -X utf8 -B scripts/check_trial_progress.py --markdown --forecast
```
