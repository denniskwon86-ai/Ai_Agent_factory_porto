# Codex 검토 요청 — FIX3 경계 보완 · 실화면 수용

작성: Claude Code · 2026-09-18 KST. **커밋·푸시 없음.** 기준 HEAD `2380143ea`.
지시: `docs/handoff/CODEX_FIX2_REVIEW_2026-09-18.md` §4(경계) · §5(실화면·증거·정본 대조).
전체 21/40=52.5% · 로컬 18/28=64.3% **유지 — 가산 요청 없음**(근거는 §6).

> §5 는 **내가 스스로 의심하는 곳**이다. 검토를 거기서 시작해 주면 가장 빠르다.

---

## 1. 지시 항목별 대조

| 지시(§4) | 한 일 | 증거 |
|---|---|---|
| 1. 미관리 목적지에서 편집기를 무조건 내리는 경로를 좁은 시험으로 재현. 동일 번호/0 delta 도 한 건 | 재현 후 뒤집음. 시험 ⑨~⑬ 5종 | `check-project-entry.mjs` 56 PASS |
| 2. 위치를 모르면 방향/칸 수를 추측하지 않는다. 파괴적 apply 금지·입력 보존·명시적 이동 선택·불일치를 숨기지 않는다 | `go()` 를 부르지 않고 화면·입력을 건드리지 않는다. 어긋난 주소를 **배너**로 남기고 선택 둘을 준다 | 시험 ⑨⑪⑫⑬ + 변이 5건 |
| 3. 동일/무효 번호에서 `go(0)`·잘못된 delta 금지. 앱 관리 구간의 유효한 번호일 때만 역이동 | `Number.isSafeInteger` · `delta !== 0` · `|delta| < history.length` 셋을 모두 만족할 때만 붙잡는다 | 대역이 `go(0)` 을 `RELOAD` 로 기록하도록 고쳐 경계가 보이게 함 |
| 4. 번호 있는 앞/뒤 취소·승인 보존. 전체 변이/서버 회귀 반복 금지 | 기존 ①~⑧ 그대로 통과. 서버는 권한표 1파일만 재실행 | 아래 §3 |

| 지시(§5) | 한 일 |
|---|---|
| 기존 격리 환경 재사용·**현재 실행 상태부터** 확인 | 프로세스는 내려가 있었다 → 재기동. 서버 파일 지문 4개 중 1개가 뒤처져 재복사 |
| kit_app 닫기→새로고침/목록 | 확인(§4) |
| 합성 릴리스 성공 경로 | 확인(§4). **운영 데이터 반입 없음** |
| 두 칸 이동은 실행 시험 유지, 브라우저는 가능하면 보충 | 브라우저로도 확인(취소·승인) |
| 권한표 실행 증거 경로·미검증 목록을 상태 파일에 | `output/usage-holds-wjf6gvsn/` 기록 |
| 정본 완료 칸 대조 | §6 |

---

## 2. 핵심 diff 지도

| 파일 | 무엇 |
|---|---|
| `frontend/src/App.tsx` popstate | `trusted` 판정(정수·비0·히스토리 길이) · 믿을 수 없으면 `setStrandedEntry` 후 **중단** |
| 〃 `overlays` | 어긋난 주소 배너 + 선택 둘(둘 다 칸을 안 늘린다) |
| 〃 `goHome` / 「경로 계산」 메뉴 | **화면과 대상을 함께 놓는다**(실화면이 잡은 결함, §5-②) |
| `frontend/scripts/check-project-entry.mjs` | 경계 5종 + 짝 1종 추가, 대역 히스토리에 `RELOAD`·`length` 추가 |
| `tests/test_route_authority_table.py` | **선언 계약** 시험 1건 추가(§5-③) |
| `tests/usage_hold_test_plugin.py` | `real_auth` 표식 등록만(+11줄) |

App.tsx 전체 diff는 **526줄 변경**(9/16 정리한 LF 유지, CR 잔여 0).

---

## 3. 재현 명령과 실측

```bash
venv/Scripts/python.exe scripts/verify_data_usage_holds.py --strict-writes \
  --target tests/test_route_authority_table.py
cd frontend && npx tsc -b && for f in scripts/check-*.mjs; do node "$f"; done && npm run build
```

```
프런트 178 PASS / 0 FAIL
  project 56 · draft-entry 17 · draft-open 29 · kit-app 14 · location 25 · release 37
check-studio-contracts 157 / 0 · tsc -b · build 성공
격리 러너 10 passed / exit 0
  증거: output/usage-holds-wjf6gvsn/{isolation.json, pytest.log, tests.xml, data/}
  protected_assets_unchanged true · sources_unchanged true · blocked_file_writes []
  blocked_sqlite_paths [] · repository_conftest_loaded false · sqlite_paths 전부 run_root/data
변이 극성 8건(경계 5 · 짝 3) 전부 «그 시험만» 죽임 · 원복 해시 일치
```

⚠️ 서버 전체 pytest 는 **안 돌렸다**(지시 §4-4). 이전 162 를 합산하지 않는다.

---

## 4. 브라우저 — 같은 문서 왕복만 주장한다

사람이 로그인했고, 이후 측정은 전부 페이지 표식(`window.__pN`)이 살아 있는 동안이다.

```
릴리스(합성)  진입 주소 보존 → 닫기 시 주소에서 빠짐(칸 +1) → 뒤로 복원
업무앱        진입 → 닫기(주소에서 빠짐) → 닫은 뒤 새로고침 = 목록 → 뒤로 복원
두 칸 이동    취소 → 번호 3 원위치·입력 그대로·칸 그대로 / 승인 → 번호 1 (3−2)
```

---

## 5. ★ 내가 스스로 의심하는 곳

### ① 배너는 **새 기능 설계**로 보이는가

지시는 「명시적인 이동 선택을 제공하는 안전한 fallback을 정한다 / 불일치를 조용히 숨기지
않는다」였다. 그래서 **기존 `Banner`** 로 최소 UI 하나를 더했다. 정책(저장/유지/폐기)은
기존 확인 UI 가 그대로 갖고, 여기서 새로 만들지 않았다. **범위 초과로 보이면 되돌린다.**
대안(현재 칸 주소를 조용히 교체)은 「숨기지 않는다」에 어긋난다고 판단했다.

### ② 「⌂ 경영 홈」 결함은 **내가 FIX2 에서 만든 것의 반대편 문**이다

업무앱 화면만 닫고 `openedKitApp` 을 남겨 URL 이 계속 업무앱을 가리켰다. 같은 결함이
「경로 계산」 메뉴에도 있었다. `goHome` 머리말이 **이미** 「새 화면을 더할 때 여기도
더한다」고 경고하고 있었는데 내가 빠뜨렸다. 다른 화면 전환에도 같은 짝이 빠졌는지
`setShowPathCalc(false)` 5곳만 훑어 2곳을 고쳤다 — **다른 대상(초안·메가)까지는 훑지
않았다.** 전수로 볼지 지시해 주면 좋겠다.

### ③ 권한표 선언 계약 시험

§2 의 「필요하면 method/path→cap 매핑을 직접 단언」을 받아 넣었고, docstring 에
**선언 계약이지 런타임 단독 효력 증명이 아니다**라고 못박았다. probe 4건은 그대로 둔다.

### ④ ⚠️⚠️ **격리 주장의 범위를 정정해야 한다**

`core/library_paths._LIBRARY_DIR = "library"` 는 `PROJECT_ROOT` 가 아니라 **프로세스 작업
디렉토리** 기준이다. 런처가 주 트리에서 띄우므로 **격리 서버가 게시물 보관소만은 운영
`library/` 를 읽고 있었다.** 합성 릴리스가 404 나서 드러났다.

- **읽기만 했고 쓴 적 없다** — 운영 `library/` 최신 항목이 **9/12 그대로**임을 확인했다.
- 제품 코드를 고치지 않고 **작업 디렉토리를 옮기는 껍데기**(`run_isolated.py`, 워크트리에만
  둔 하네스)로 띄웠고, 기동 로그 세 줄을 **읽어서** 확인했다.
- 절차 문서에 **함정 ③** 으로 적었다.
- ★ 그래서 **9/16·9/18 의 「격리」 주장 중 「게시물 보관소」 부분은 정정 대상**이다.
  다른 상대경로 저장소가 더 있는지는 `grep` 으로 `library` 하나만 확인했다 — 더 넓게 볼지 지시 대상.

### ⑤ 두 칸 이동을 `history.go(-2)` 로 눌렀다

브라우저 패널에 다단계 뒤로 버튼이 없다. `go(-2)` 는 **브라우저 자체 이동 API**이며
제품 상태를 JS 로 조작한 것이 아니다. 그래도 「실제 입력」과 구분해서 읽어 주기 바란다.

### ⑥ 실화면 증거의 한계

릴리스는 **합성 1건**, 업무앱은 **진입·닫기·복원까지**다. 「운영 중 앱의 시뮬레이션 실행」은
계약 승인·빌드·승격·데이터셋 결속이 필요해 **LLM 경로를 태우지 않으려고 하지 않았다.**

---

## 6. 정본 완료 칸 대조 — **가산 불가**

정본 `docs/design_l2_unified_studio_execution_2026-09-12.md` §14(분모 40·28 고정) 및
배치표의 **B6 제품 진입 연결**. 출구 증거 「**단일 mount · URL/회사/SSE · 유형별 parity**」.

| B6 출구 조건 | 증거 | 판정 |
|---|---|---|
| 단일 mount | 훅 모의 StrictMode 재조회 0 · 9/16 브라우저 중복 GET 2건 실측 | 근접 |
| URL | 여섯 대상 진입·새로고침·뒤로/앞으로·취소/승인·두 칸·경계 실측 | **충족** |
| 회사(문맥) 전환 | `revalidateOpenProject` 배선은 **STATIC 문자열 검사만** | **미충족** |
| SSE | 범위 밖·미확인 | **미충족** |
| 유형별 parity | kit_app 은 진입까지 · release 는 **합성** | **미충족** |

**가산 없음.** 가산 후보 조건 셋: ① 회사 전환 후 열린 대상 재확인(브라우저) ② SSE 재연결
확인 ③ 합성이 아닌 산출물로 한 대상 이상 관통.

---

## 7. 건드리지 않은 것 / 환경 상태

- 제품 **서버 코드 변경 없음**(이번 라운드는 `frontend/src/App.tsx` + 검사·시험 파일).
  권한표 관련 `core/route_authority.py`·`api/routes/program_control.py` 등은 변이 후 **해시로
  무변경 확인**.
- skip·xfail 없음. 단언 약화 없음. 운영 conftest 일괄 로드 없음. 운영 뿌리에서 pytest 없음.
- 커밋·푸시·pull 없음. 운영 DB·데이터 ZIP·키·사용자 로그 무접촉. 다른 세션 워크트리 무접촉.
- 격리 환경은 **떠 있다**(`/c/sentwt` · 8086 · 5181). `.claude/launch.json` 의 `sent-isolated`
  가 `run_isolated.py` 를 가리키도록 바꿨다 — **임시 항목이며 철수 시 원복 대상**이다.
  합성 fixture(`/c/sentwt/library/rel_sent_synthetic_01/`)도 격리 뿌리에만 있다.
