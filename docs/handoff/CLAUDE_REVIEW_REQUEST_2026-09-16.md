# Codex 검토 요청 — SINGLE-ENTRY-01-FIX2 · ROUTE-AUTHORITY-01

작성: Claude Code · 2026-09-16 KST. **커밋·푸시 없음.** 기준 HEAD `2380143ea`.
전체 21/40=52.5% · 로컬 18/28=64.3% **유지**(가산 요청 없음).

> 이 문서는 「봐 달라」는 요청이며 판정을 미리 주장하지 않는다. 아래 §5 는 **내가 스스로
> 의심하는 곳**이고, 검토를 거기서 시작해 주면 가장 빠르다.

---

## 1. 검토 대상 두 묶음

| 묶음 | 지시서 | 상태 |
|---|---|---|
| **SINGLE-ENTRY-01-FIX2** | `CODEX_SINGLE_ENTRY_FIX2_2026-09-16.md` 1·2·3·4 | 코드·검사·**브라우저**까지 |
| **ROUTE-AUTHORITY-01** | 같은 문서 §수행 순서 4 | 4 ERROR 해소, 격리 러너 9 PASS |

상세 경과는 `docs/handoff/CLAUDE_CODE_EXECUTION_STATUS.md` 맨 앞 두 절에 있다.

---

## 2. 핵심 diff 지도 — 어디를 보면 되는가

### FIX2 (프런트만. **서버 변경 없음**)

| 파일 | 무엇 |
|---|---|
| `frontend/src/App.tsx` | ① `historyIndex`/`__studioIndex` 로 **방향·칸 수**를 구해 `go(-delta)`/`go(delta)` · `pendingApproval` 로 빠른 클릭 순서 제어 |
| 〃 | ② URL 동기화 effect 에서 **복원 표시를 조기 return 보다 위에서 소비** |
| 〃 | ③ `applyStudioEntry` 배타 정리 · `openRelease`/`leaveRelease` 한 계약 · `openTarget` 에 `new` · 업무앱 닫기/열기 양쪽 기록 |
| 〃 | ★ `buildStart` 초기값을 `initialEntry.current.isNew` 로 (브라우저가 잡은 결함, §5-③) |
| `frontend/src/factory/studioLeaveGuard.ts` | ④ `confirmLeave` 가 `LeaveOutcome` 을 돌려주고 **예외에서 `proceed()` 를 부르지 않는다** |
| `frontend/src/components/BuildStartDialog.tsx` | `safe` 를 `requestLeave` 의 기존 제한과 일치 · `onConfirmError` |
| `frontend/scripts/check-project-entry.mjs` | +7 시험(방향·연속 전이·openTarget·닫기·보호·첫 렌더) |
| `frontend/scripts/check-release-entry.mjs` | +1 시험(열기/닫기가 조회와 주소 의도를 함께 움직이는가) |

### ROUTE-AUTHORITY-01 (**제품 코드 무변경**, 시험 2파일)

| 파일 | 무엇 |
|---|---|
| `tests/test_route_authority_table.py` | `client` fixture 를 `enforced_org` + **실제 세션 토큰**으로. `@pytest.mark.real_auth`. 대조군 사전 단언 3줄. `SAFE_PROBES` 에 관찰 주석 |
| `tests/usage_hold_test_plugin.py` | `real_auth` **표식 등록만** (+11줄) |

---

## 3. 재현 명령 — 그대로 복사해 돌릴 수 있다

```bash
# 서버(격리 러너로만 — 운영 뿌리에서 직접 pytest 하지 않는다)
venv/Scripts/python.exe scripts/verify_data_usage_holds.py --strict-writes \
  --target tests/test_route_authority_table.py

# 프런트
cd frontend && npx tsc -b
for f in scripts/check-*.mjs; do node "$f"; done
npm run build
```

### 실측(2026-09-16, 내가 돌린 값)

```
프런트 177 PASS / 0 FAIL
  project 55 · draft-entry 17 · draft-open 29 · kit-app 14 · location 25 · release 37
check-studio-contracts 157 / 0 · tsc -b 통과 · build 성공
격리 러너 tests/test_route_authority_table.py  9 passed / exit 0
  protected_assets_unchanged true · blocked_file_writes [] · blocked_sqlite_paths []
  sources_unchanged true · repository_conftest_loaded false
conftest 세계 확인: 격리 워크트리 /c/sentwt 에서 pytest  9 passed
```

⚠️ **서버 전체 pytest 는 이번에 안 돌렸다.** 이전 162 PASS 는 이전 실측이며 합산하지 않는다.

### 변이 극성

```
FIX2            10건 전부 «그 통제를 단언한 시험만» 죽음
ROUTE-AUTHORITY  6건 중 5건 정확, 1건 미탐지 → 원인 규명(§5-①)
원복은 둘 다 해시 일치로 확인
```

---

## 4. 브라우저 — 같은 문서 왕복만 주장한다

기존 격리 환경(`/c/sentwt` · 8086 · 5181) 재사용. 문서 재적재와 구분하려고 페이지에 표식
(`window.__fix2mark`)을 박고 모든 측정에서 함께 읽었다.

```
＋새 앱 → target=new, 번호 0→1, 칸 +1
입력 후 뒤로 → 확인창 · 번호 1 복귀 · 입력·URL·칸 그대로
앞으로 취소 ★ → 번호 1 복귀 (옛 go(1) 이면 «더 앞으로» 갔다)
앞으로 승인 → 번호 2
초안→닫기→뒤로(초안)→닫기→뒤로 → 초안 주소·화면 복귀 (②의 정면)
릴리스 실패 → 안내가 뜨고 URL 은 그대로
```

---

## 5. ★ 내가 스스로 의심하는 곳 — 여기부터 봐 주면 좋겠다

### ① `programs/{id}/disable` probe 는 «표» 의 증인이 아니다

표에서 그 항목을 빼도 **여전히 403** 이다. 라우트 안에 `_admin(p)` 자기 판정이 따로 있기
때문이다(이중 방어라 제품으로서는 좋다). 지우지 않고 시험 파일에 적어 두었다.
표 단독 증인을 만들려면 `_admin` 은 통과하되 `PROJECT_RELEASE` 가 없는 역할이 필요한데
현재 `_ROLE_CAPS` 에 그 조합이 없다. **응답 문구에 기대는 단언은 만들지 않았다** —
문구가 바뀌면 조용히 무의미해진다. **결정 대상.**

### ② 기존 검사 두 개의 «위치 탐색» 을 고쳤다 — 약화가 아닌지 봐 달라

- `check-release-entry.mjs`: 릴리스 화면 닫기 버튼이 `closeRelease`→`leaveRelease` 로 바뀌어
  주입 이름을 맞췄다. **대신 시험을 하나 늘렸다**(열기/닫기가 조회와 주소를 함께 움직이는가).
- `check-studio-contracts.mjs`: `app.indexOf(event)` 로 **첫 등장**만 보던 자리다. 같은
  이벤트에 구독이 둘이 되자 **있는 통제를 없다고 답했다.** 모든 등장을 훑도록 고쳤고
  단언의 뜻(두 이벤트 모두 재확인을 부른다)은 그대로다.

### ③ ★ 내가 이번에 «만든» 결함 하나 — 브라우저가 잡았다

`?target=new` 로 진입하면 히스토리 칸이 **둘** 생기고 뒤로가기가 중간의 `?space=build` 로
갔다. `new` 를 주소에 실으면서 **첫 렌더 순서를 안 봤다** — 그 사이 렌더에서 `openTarget`
이 비어 목록 주소가 밀려 들어갔다. 초기값을 옮겨 고치고, 초기값을 **실행해서 보는** 시험과
변이(⑩)를 더했다. 같은 모양이 다른 대상에도 있는지는 릴리스만 확인했다.

### ④ ⚠️ 줄끝 — `frontend/src/App.tsx` 가 **CRLF 로 뒤집혀 있었다**

발견 당시 `git diff --stat` 이 **3541줄**을 바꾼 것으로 보였다(HEAD 는 순수 LF, 작업본은
CRLF 1931 + LF 10 **혼재**). 그대로 넘기면 diff 검토가 불가능하다.
**내용은 건드리지 않고 줄끝만** 저장소 규약(`.gitattributes: * text=auto`, HEAD 도 LF)으로
되돌렸다 → 지금은 **399 insertions / 60 deletions**.
되돌린 뒤 `tsc -b`·검사 177건·build 를 다시 돌려 초록을 확인했다.
⚠️ **누가 언제 뒤집었는지는 확인하지 않았다(미확인).** 그리고 아직 뒤집힌 채인 파일이 있다:
`frontend/scripts/check-studio-contracts.mjs` · `tests/test_route_authority_table.py` ·
`.agents/TEAM_BOARD.md`(혼재). 이 셋은 diff 가 정상으로 보여 **건드리지 않았다** —
특히 TEAM_BOARD 는 다른 세션도 쓰는 파일이라 임의로 전 줄을 다시 쓰지 않았다. **결정 대상.**

---

## 6. 아직 아닌 것 (NOT_RUN / 미검증)

- **업무앱 모달(kit_app) 닫기→새로고침 · 업무앱→목록**: 화면에서 `onOpenSimulation` 자리에
  닿지 못해 **실행 가능 검사로만** 덮였다(닫기 핸들러 실행 + 배타 정리 실행, 둘 다 변이 확인).
- **두 칸 이동**: 검사에서만 확인, 브라우저에서는 누르지 못했다.
- **릴리스 성공 경로**: 격리 뿌리에 결과물 0건이라 **실패 경로만** 봤다.
- 번호를 잃은(우리가 만들지 않은) 히스토리 항목 위에서는 이동 보호가 동작하지 않는다 —
  지시대로 **인덱스를 지어내지 않은** 결과이며 명시한 안전 범위다.

## 7. 건드리지 않은 것

- **제품 서버 코드**: ROUTE-AUTHORITY-01 은 `tests/` 두 파일만 바꿨다.
  `core/route_authority.py`·`api/routes/program_control.py`·`core/org_directory.py`·
  `core/admin_capability.py` 는 **변이 후 해시까지 확인해 무변경**이다.
- skip·xfail 없음. 단언 약화 없음. 운영 conftest 일괄 로드 없음. 감사 제품 로직 변경 없음.
- 커밋·푸시·pull 없음. 운영 DB·데이터 ZIP·키·사용자 로그 무접촉. 다른 세션 워크트리 무접촉.
- 격리 환경(`/c/sentwt` · 8086 · 5181)은 **아직 떠 있다** — 재확인이 필요하면 그대로 쓰면 된다.
  내릴지는 지시 대기(`docs/handoff/ISOLATED_VERIFICATION_ENV_2026-09-16.md` §5).
