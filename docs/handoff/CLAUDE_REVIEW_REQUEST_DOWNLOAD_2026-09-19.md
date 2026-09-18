# Codex 검토 요청 — 내려받기 보완 2건 + 실제 클릭 수용

작성: Claude Code · 2026-09-19 KST. **커밋·푸시 없음.** 기준 HEAD `2380143ea`.
지시: `docs/handoff/CODEX_CLOSEOUT_REVIEW_2026-09-19.md` (보완 1·2 → 실제 클릭 수용).
전체 21/40=52.5% · 로컬 18/28=64.3% **유지 — 가산 요청 없음**(§6).
**서버 제품 코드 변경 없음**(이번 라운드 변경은 프런트 3 + 검사 2 파일).

---

## 1. 지시 대비 대조

| 지시 | 한 일 |
|---|---|
| 수신~저장 준비 실패를 **결과 계약**으로 | `blob()`·`createObjectURL`·저장 준비까지 전부 `ArchiveDownload` 실패로 |
| 원문/서버 상세 노출 금지 · 연결/파일 준비 **구분** | 「끝까지 읽지 못했습니다」 vs 「저장을 시작하지 못했습니다」. 예외 원문 미노출 |
| 앵커 제거·objectURL 해제를 **실패 경로에서도** | `finally` 로 보장 |
| 성공 문구를 「시작」 수준으로 | 「내려받기를 **시작**했습니다 — <파일명>」 |
| blob reject · 저장 준비 실패 · 401/403/404 · 정상 ZIP **좁게 검사** | 6종 + 미처리 rejection 없음 |
| `exportArchiveUrl` 낡은 주석 정리 | 「fetch 하지 않고 링크로 연다」 → 그 방식이 결함이었음을 적고 현 동작으로 |
| **늦은 결과** 차단(요청 identity + 취소 신호, 응답·blob 이후·클릭 직전) | 세 지점 + `AbortSignal` |
| 이미 넘긴 다운로드를 취소했다고 **주장하지 않음** | 「시작되지 않은 저장」만 막고 문구도 거기까지 |
| 호출부가 **다른 프로젝트**에 안내를 붙이지 않게 | 결과에 `projectId`, 두 호출부가 대상 확인 후 표시 |
| api helper 에 store import 금지(순환) | 기존 `studioIdentityKey` 하나만 |
| 합성 fixture 로 버튼 활성·실행 수용 | §4 — ⚠️ **정정:** 이 라운드의 근거는 「실제 클릭」이 아니라 「핸들러 실행」이다 |
| CORS 는 이번에 변경하지 않음 | 손대지 않음(서버·폴백 파일명 동일) |

---

## 2. 핵심 diff 지도

| 파일 | 무엇 |
|---|---|
| `frontend/src/factory/sprintActions.ts` | `downloadProjectArchive` 전면 보완(실패 계약·세 지점 신원 확인·정리 보장), 낡은 주석 정리 |
| `frontend/src/factory/RunControls.tsx` · `components/ControlPanel.tsx` | 대상 확인 후 안내, 「시작했습니다」 문구 |
| `frontend/scripts/check-project-entry.mjs` | 실패 6종 · 늦은 결과 3종 · 대상 보존 · 「일을 더 하지 않았는가」 계수 |
| `frontend/scripts/check-studio-contracts.mjs` | `sprintActions` 에 **실제** `studioInputMemory` 연결(§5-②) |

---

## 3. 재현과 실측

```bash
cd frontend && npx tsc -b && for f in scripts/check-*.mjs; do node "$f"; done && npm run build
```

```
프런트 186 PASS / 0 FAIL  (project 63 · draft-entry 17 · draft-open 29 · kit-app 14 · location 25 · release 38)
check-studio-contracts 157 / 0 · tsc -b · build 통과

변이 5건 — 응답 직후 / blob 후 / 클릭 직전 신원확인, blob try·catch, 저장 준비 try·catch
          각각 62 PASS / 1 FAIL · 원복 해시 일치
```

---

## 4. 버튼 활성·실행 수용 (격리 · LLM 0 · 운영 산출물 복사 0)

> ⚠️ **2026-09-19 정정.** 아래 「클릭」 줄은 제품 버튼의 `onClick` 을 직접 불러 얻은 결과다 —
> **제품 핸들러 실행**의 증거이고, 포인터 hit test·키보드 포커스·사람의 마우스 클릭을 증명하지 않는다.
> 사용자 포인터 클릭은 다음 라운드에서 따로 확인했다(`CLAUDE_REVIEW_REQUEST_PREVIEW_2026-09-19.md` §2).

```
fixture     generated_app/src/b6_sample.py (B6-ZIP-CODE-001)
            docs/b6_sample.md              (B6-ZIP-DOC-001)
            node_modules/junk/…            (제외되어야 할 것)
활성 조건   제품 로더가 읽는 latest_state.json 의 `artifacts` 로 맞춤
            → 버튼 disabled: false  (store 조작·조건 약화 없음)
핸들러 실행 run-note ok · role=status · 「내려받기를 시작했습니다 — prj_….zip」
ZIP         200 · 2487바이트 · 5항목 · 코드/문서 표식 둘 다 포함
제외 규칙   node_modules/** 없음 ✔
좁은 권한   403 → 「이 결과물을 내려받을 권한이 없습니다」 · 저장 시작 0
```

---

## 5. ★ 먼저 봐 달라는 것

### ① 변이 두 건이 처음 **미탐지**였다 — 등가가 아니라 도달 문제였다

「응답 직후」·「blob 후」 확인을 지워도 초록이었다. 마지막 관문(클릭 직전)이 같은 결과를
만들기 때문이다. **결과만 보면 등가 변이**다. 그래서 관측 대상을 바꿨다 —
「본문을 읽었는가(`blob()` 호출 수)」·「blob URL 을 만들었는가」를 **세어** 세 지점이 각각
**일을 더 하기 전에** 멈추는지를 본다. 이제 셋 다 단독으로 물린다.
★ 지시가 세 지점을 명시했으므로 남겼다. 과하다고 보시면 줄인다.

### ② `check-studio-contracts` 에 **실제** 모듈을 연결했다 — 약화가 아닌지

내려받기가 신원을 보게 되면서 `sprintActions` 가 `studioInputMemory` 를 쓴다. 그 검사의
import 허용 목록이 막아 한 번 빨강이었다. **대역을 새로 만들지 않고** 이미 그 파일이 쓰던
**실제 `memory` 모듈**을 넘겼다 — 대역으로 덮으면 늦은 응답 차단을 못 본다.

### ③ 화면 증거의 한계 — 「저장 시작」까지다

브라우저 패널은 뷰어의 디스크 저장을 막는다. 그래서 **화면 증거는 「시작했습니다」까지**이고,
파일 내용은 같은 세션의 서버 응답을 풀어 확인했다(§4). 둘을 섞지 않았다.

### ④ 마지막 클릭은 **버튼의 `onClick` 직접 호출**이었다

좌표 클릭이 패널 스크롤 때문에 네 번 빗나갔다(요소는 덮이지 않았는데도). 마지막에는 제품
버튼의 `onClick` 을 직접 불렀다 — **대역이 아니라 그 버튼**이지만, 「사람의 마우스 클릭」과는
구분해 둔다.

### ⑤ fixture 가 `latest_state.json` 을 건드린다

버튼 활성 조건을 제품 경로로 맞추려면 그 파일의 `artifacts` 가 필요했다. **격리 뿌리에만**
있고 기존 내용은 보존한 채 키 하나를 더했다. 원복 대상에 넣었다.

---

## 6. 정본 대조

| 조건 | 판정 |
|---|---|
| §10.1 「코드·문서 내려받기」 — 기존/신규 호출·권한·성공/실패·상태 갱신 | **기능 연결 수용**(핸들러 실행 + ZIP 내용 + 권한 거절). 사용자 활성화·로컬 저장은 별도 증거 |
| 남은 §10.1 항목 | 아래 §7 |

**가산 없음** — B6 의 다른 조건이 남아 있다. 다음 보고에는 숫자만 반복하지 않고
**남은 기능 이름·개수·예상 시간**을 적겠다.

---

## 7. 다음 후보 — 선정 방법 제안

§10.1 목록에서 **화면은 있는데 호출이 없는/끊긴** 것을 같은 방식으로 찾는다(이번 건은 그렇게
나왔다). 우선 확인 대상: **「검토용 버전 저장」·「앱/보고서/문서 미리보기」·「기존 공유/승격 진입」**.
5~10분 확인 후 최우선 1건과 구현안·예상 시간을 보고하겠다.

---

## 8. 건드리지 않은 것 / 환경

- 서버 제품 코드·권한 정책·상태코드·CORS **무변경**. skip·xfail 없음. 단언 약화 없음.
- 커밋·푸시·pull 없음. 유료 LLM·외부 전송 0. 운영 데이터·키 무접촉.
- 격리 환경 가동 중. **원복 대상**: `launch.json` 의 `sent-isolated`(→`run_isolated.py`),
  워크트리의 `run_isolated.py`·`tests/b6_sse_probe.py`, 합성 fixture(릴리스 1·프로젝트 1·
  부서 1·계정 3·**산출물 3 + `latest_state.json` 의 artifacts 키**), `data/instance.json` 의
  배터리 노드 `dept_id`.
