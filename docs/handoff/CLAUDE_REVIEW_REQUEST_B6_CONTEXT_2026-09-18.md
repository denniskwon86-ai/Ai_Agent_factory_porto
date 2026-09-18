# Codex 검토 요청 — FIX4 안전 점검 · B6-CONTEXT-SSE-01 (결정 ②까지)

작성: Claude Code · 2026-09-18 KST. **커밋·푸시 없음.** 기준 HEAD `2380143ea`.
지시: `docs/handoff/CODEX_FIX3_REVIEW_AND_B6_NEXT_2026-09-18.md` (A·B 안전 점검 + B6 첫 묶음),
그리고 사용자 결정 **②**(전환 시 열린 대상을 명시적으로 확인시킨다).
전체 21/40=52.5% · 로컬 18/28=64.3% **유지 — 가산 요청 없음**(근거 §6).

> §5 가 **먼저 봐 달라는 곳**이다. 그중 §5-① 은 내 **오보 정정**이다.

---

## 1. 지시 항목별 대조

| 지시 | 한 일 | 증거 |
|---|---|---|
| **A.** 배너 두 선택 이후의 연속 이동을 한 건 재현. 번호 없으면 이전 번호를 쓰지 않는다. 관리 구간이 다른 항목 간 정수 차이로 방향 추정 금지 | 되돌리기가 **이 칸** 에 눈금을 맞춘다(없으면 없는 채로). 번호에 **구간**(`__studioEpoch`)을 함께 찍고 **같은 구간일 때만** 차이를 쓴다 | 재현 1건 + 경계 3종, 변이 3건 |
| **B.** 다음 검증이 쓰는 기동·인증·조직/정책·프로젝트·라이브러리·로그 경로만 조사. **경로 구성요소** 기준 | 런처와 같은 조건으로 맞춘 뒤 제품 모듈에 직접 질의. 모듈 7 + 저장 9 전부 격리 뿌리 안 | `isolation_paths_report` (§3) |
| **B.** 운영 쓰기 경로에 연결되면 시작하지 않는다 | 격리 밖 0건 → 시작함. 임시 launch 항목은 **기록만** 하고 손대지 않았다 | 같은 보고 |
| **C.** 열린 project 하나로 A→B 전환·재확인·SSE | 전환·SSE·B 문맥 재진입은 **실측**. 「전환 «중» 열린 대상」은 **도달 불가**(§5-②) | §4 |
| **②** 전환 시 열린 대상을 명시적으로 확인시킨다 | `revalidateOpenProject` → **`revalidateOpenEntry`**, 여섯 대상 전부를 **단 하나의 진입 경로**로 되돌린다 | 시험 2건 + 변이 3건 |

---

## 2. 핵심 diff 지도 (이번 라운드는 **프런트만**)

| 파일 | 무엇 |
|---|---|
| `frontend/src/App.tsx` popstate·URL | `__studioEpoch`(관리 구간) 도입 · 같은 구간일 때만 delta 사용 · 번호를 잃으면 새 구간 |
| 〃 배너 「되돌리기」 | 현재 칸의 **실제 state** 로 눈금을 맞춘다(없으면 `null`, 지어내지 않는다) |
| 〃 `revalidateOpenEntry` | 여섯 대상 재확인. 대상의 정본은 URL. `applyStudioEntryRef` 로 기존 경로 재사용 |
| `frontend/scripts/check-project-entry.mjs` | FIX4 연속 전이 1건 + 경계 3종, B6 재확인 2건 (합계 59) |
| `frontend/scripts/check-studio-contracts.mjs` | STATIC 이름 단언을 새 이름으로(뜻은 그대로, §5-④) |

**서버 제품 코드 변경 없음.** 이번 라운드에 바꾼 것은 위 3개 파일뿐이다.
App.tsx 는 9/16 정리한 LF 유지(CR 잔여 0), 내용 diff 600줄.

---

## 3. 재현 명령과 실측

```bash
cd frontend && npx tsc -b && for f in scripts/check-*.mjs; do node "$f"; done && npm run build
```

```
프런트 181 PASS / 0 FAIL
  project 59 · draft-entry 17 · draft-open 29 · kit-app 14 · location 25 · release 37
check-studio-contracts 157 / 0 · tsc -b · build 성공
변이 극성  FIX4 3건 + B6 3건 = 6건 전부 «그 시험만» 죽임 · 원복 해시 일치
```

### 격리 경로 확인 (지시 B)

```
cwd C:\sentwt · sys.path[0] C:\sentwt
모듈 7: core.paths · core.org_directory · core.auth · core.scope_policy
        core.library_paths · api.deps · main            → 전부 C:\sentwt\...
저장 9: data 뿌리 · projects · master.db(조직) · auth.db(인증) · scope_policy.json(정책)
        enterprise_context.db(ECM) · library(게시물) · access_audit.jsonl · interaction_log.jsonl
                                                        → 전부 C:\sentwt\...
격리 밖 0 · 운영 트리 0
대조군: C:\sentwt2\data 를 «밖» 으로 세는지 — 정상(문자열 startswith 였다면 안으로 셌다)
```

⚠️ 서버 pytest 는 이번 라운드에 **안 돌렸다**(프런트만 바꿨다). 이전 값을 합산하지 않는다.

---

## 4. 브라우저 실측 (같은 문서 / 실제 조작)

```
회사 전환 A→B   실제 화면 조작
  scopeNodeId  plant-afs-smelting-01 → ""   (localStorage 실측)
  칩            「제련공장」 → 「권한 범위 전체」
SSE
  이전 연결  GET /ws/timeline?ticket=<redacted>  → net::ERR_ABORTED   ← 해제됨
  새 연결    GET /ws/timeline?ticket=<redacted2> → 200                ← 새 티켓 재연결
B 문맥 재진입
  GET /api/v1/factory/prj_.../entry-metadata → 200 (허용) · 화면 열림
```

⚠️ 티켓 값은 기록하지 않았다. 합성 프로젝트는 **제품 API + 실제 세션**으로 만들었다
(`POST /api/v1/factory/projects` → 200, `owner_dept_id=demo_smelting`). 모의 성공으로 덮지 않았다.

---

## 5. ★ 먼저 봐 달라는 것

### ① ⚠️ **오보 정정** — 「전환기가 안 열린다」는 내 측정 오류였다

앞 보고에서 「칩을 눌러도 전환기가 열리지 않았다(원인 미확인)」고 적었다. **틀렸다.**
열림 판정을 `document.body.innerText.slice(0, 600)` 으로 했는데 대화상자 본문이 그 **뒤** 에
있었다. 정확한 선택자로 다시 재니 **좌표 클릭만으로 매번 열린다.** 제품 결함이 아니다.
그 보고를 근거로 판단하셨다면 여기서 바로잡아 주기 바란다.

### ② 진짜 장애물 — **전환과 「열린 대상」이 같은 화면에 없다**

```
프로젝트 연 화면   document.querySelector('button.afs-context') → 없음
초안 편집기 화면   〃                                           → 없음
shell 화면         있음. 그런데 그리로 가는 「⌂ 경영 홈」은 열린 대상을 정리한다
```

그래서 **②를 구현했어도 실화면에서 관측할 수 없다.** 계약은 넓혔지만 사용자가 그 상황을
만들 수 없다. 이것을 닫으려면 **배치 결정**(대상 연 화면에도 전환을 둘 것인가)이 필요하다 —
내 단독 판단 대상이 아니라고 보고 **손대지 않았다.**

### ③ ②의 구현이 「새 정책·새 UI」로 보이는가

새 정책을 만들지 않았다. **대상의 정본은 URL**(FIX2 이후 불변)이라는 기존 사실 위에서,
「주소가 가리키는 것을 새 권한으로 다시 확인」하도록 **이미 있는 `applyStudioEntry` 한 곳**으로
되돌린다. 여섯 대상에 분기를 달지 않았다. 범위 초과로 보이면 되돌린다.

### ④ STATIC 검사 이름 변경

`revalidateOpenProject` → `revalidateOpenEntry` 로 바뀌어 `check-studio-contracts` 의 이름
단언을 고쳤다. **단언의 뜻은 그대로**이고, 「무엇을 다시 확인하는가」는 `check-project-entry`
가 **뽑아서 실행해** 본다(문자열 검사가 아니다). 약화가 아닌지 봐 달라.

### ⑤ 아직 못 만든 두 가지

- **거절 사례**: 이 계정의 전환 목록은 「제련공장」과 「내 권한 전체」 둘뿐이다. **좁히는**
  전환이 없어 403/404 를 만들 수 없다. 다른 범위 계정을 격리에 심을지는 **지시 대상**이다.
- **새 이벤트 소비 · 옛 문맥 이벤트 미반영**: LLM 경로를 태우지 않으면서 timeline 이벤트를
  내는 **무해한 제품 행동**을 아직 정하지 못했다. 후보를 지정해 주면 그것으로 잰다.

---

## 6. 정본 대조 — **가산 불가** (B6 「회사」·「SSE」)

| 조건 | 증거 | 판정 |
|---|---|---|
| SSE 이전 연결 해제 · 새 문맥 연결 | 실측(ABORTED + 새 티켓 200) | **충족** |
| SSE 새 이벤트 실제 소비 · 옛 문맥 이벤트 미반영 | 이벤트를 일으키지 못했다 | **미충족** |
| 회사 전환 시 열린 대상 재확인 | 코드·시험은 닫힘, **실화면 도달 불가** | **미충족** |
| 전환 후 새 권한으로 진입 재확인 | 실측(200 허용) | **충족** |
| 거절 경로 | 좁히는 범위가 없다 | **미충족** |

**가산 없음.** 「검사 개수」가 아니라 위 미충족 세 칸을 닫는 것이 다음 목표라는 지시를 그대로 받는다.

---

## 7. 건드리지 않은 것 / 환경

- 서버 제품 코드·권한 정책 변경 없음. skip·xfail 없음. 단언 약화 없음.
- 커밋·푸시·pull 없음. 운영 DB·키·사용자 로그 무접촉. 다른 세션 워크트리 무접촉.
- 격리 환경 가동 중(`/c/sentwt` · 8086 · 5181). 임시 launch 항목(`sent-isolated` →
  `run_isolated.py`)과 합성 fixture(합성 릴리스 1건, 합성 프로젝트 1건)는 **격리 뿌리에만**
  있으며 **원복 대상으로 기록만** 했다.
- 격리 주장 정정(게시물 보관소 부분 철회, 과거 무변경 증거는 제한적)은 상태 파일에 유지.
