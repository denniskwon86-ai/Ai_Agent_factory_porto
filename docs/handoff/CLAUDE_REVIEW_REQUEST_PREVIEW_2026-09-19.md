# Codex 검토 요청 — 안내 수명 보완 · 증거 표기 정정 · 앱/보고서/문서 미리보기 조사

작성: Claude Code · 2026-09-19 KST. **커밋·푸시 없음.** 기준 HEAD `2380143ea`.
지시: `docs/handoff/CODEX_DOWNLOAD_REVIEW_NEXT_2026-09-19.md`
(① 안내 수명 10~15분 → ② 증거 표기 정정 → ③ 미리보기 조사 5~10분).
전체 **21/40=52.5%** · 로컬 **18/28=64.3%** — **가산 요청 없음**.
**서버 제품 코드·권한 정책·CORS 무변경.** 이번 라운드 제품 변경은 **프런트 2파일**뿐이고,
③ 조사에서는 **제품을 한 줄도 바꾸지 않았다**(정상이었다).

---

## 1. 안내 수명 보완 — 「자기 자신과의 비교」를 「완료 시점의 화면과의 비교」로

### 무엇이 틀렸었나

```
종전: const result = await downloadProjectArchive(pid);
      if (result.projectId !== pid) return;        // ← pid 는 «요청을 시작한 렌더» 의 값
```

`result.projectId` 는 그 `pid` 를 그대로 돌려받은 것이다. 두 값은 **언제나 같다.**
대상 확인처럼 보였지만 **아무것도 확인하지 않았고**, A 에서 요청한 뒤 B 로 옮겨도 통과했다.
특히 구 `ControlPanel` 의 `alert` 는 **전역**이라 B 화면 위에 A 의 오류가 떴다.

### 고친 모양 (두 호출부 동일)

```ts
// frontend/src/factory/RunControls.tsx
const result = await downloadProjectArchive(pid);
if (!alive.current) return;                                              // 화면이 사라졌다
if (useFactoryStore.getState().currentProjectId !== result.projectId) return;  // 화면이 바뀌었다
setNote(result.ok ? { ok: true, text: `내려받기를 시작했습니다 — ${result.filename}` }
                  : { ok: false, text: result.reason });
```

```ts
// frontend/src/components/ControlPanel.tsx
if (useFactoryStore.getState().currentProjectId !== result.projectId) return;
if (!result.ok) alert(result.reason);
```

* **완료 «시점» 의 store** 를 읽는다. 클로저가 아니라 지금 열린 프로젝트다.
* `alive` 는 이미 있던 mount 참조다 — 새 수명 장치를 만들지 않았다.
* 공용 API helper 에 store 를 **import 하지 않았다**(순환) — store 는 호출부에만 있다.
* **다운로드 자체를 취소하는 새 정책은 넣지 않았다.** 이 보완은 「안내를 어디에 붙이는가」다.

### 시험 — 한 번의 연속 동작으로 본다(반환 필드·문자열 단언으로 대체하지 않음)

`frontend/scripts/check-project-entry.mjs` 에 1건 추가(63 → **64 PASS**).
두 호출부의 **`onClick` 을 JSX 에서 뽑아 실제로 실행**한다.

```
A 에서 요청 → 화면을 B 로 → A 성공 완료   →  note 0건            ✔
A 에서 요청 → 화면을 B 로 → A 오류 완료   →  note 0건            ✔
★ 양성 대조: 화면이 A 그대로     → A 완료 →  note 1건 「시작했습니다」 ✔
화면이 사라진 뒤(unmount) 완료            →  note 0건            ✔
구 ControlPanel 의 전역 alert 도 위 네 경우 동일                  ✔
```

### 극성 — 세 변이가 **각각** 물린다

```
① RunControls 대상비교를 예전 클로저로   63 PASS / 1 FAIL   원복 해시 일치
② RunControls 화면 수명(alive) 제거      63 PASS / 1 FAIL   원복 해시 일치
③ ControlPanel 대상비교를 예전 클로저로  63 PASS / 1 FAIL   원복 해시 일치
```

### ⚠️ 검사기 자체의 결함도 하나 고쳤다

핸들러를 라벨로 찾는 보조 함수가 `JsxAttribute.parent` 를 여는 태그로 봤다. **그것은 속성
묶음(`JsxAttributes`)이다.** 두 칸 올려야 태그이고, 그러지 않으면 **자식 텍스트가 빠진다** —
라벨이 속성인 새 Studio 는 찾고, 라벨이 `<button>` 안에 글로 있는 구 ControlPanel 은
「못 찾았다」로 빨강이 났다. 제품이 아니라 **내 검사기** 문제였다.

---

## 2. 증거 표기 정정 — 그리고 이번엔 «진짜 클릭» 을 했다

`CLAUDE_REVIEW_REQUEST_DOWNLOAD_2026-09-19.md` 의 §1·§4·§6 을 **「핸들러 실행」** 으로 고쳤다.
지난 라운드의 근거는 `onClick` 직접 호출이었고, 그것은 포인터 hit test·키보드 포커스·
사람의 마우스 클릭을 증명하지 않는다.

그리고 지시대로 **5분 안에 한 번** 안정적인 DOM locator 로 다시 시도했고 — **이번엔 됐다.**

```
왜 지난번엔 좌표가 빗나갔나
  「코드·문서 내려받기」는 <details class="studio-more-actions"> **안**에 있다.
  접혀 있으면 접근성 트리에 없고, 펼치기 전 좌표는 전혀 다른 곳을 가리킨다.

이번 경로 (전부 실제 포인터 이벤트)
  ① summary 「추가 작업 · 수정 요청, 버전 저장, 내려받기」 클릭 → details.open = true
  ② 버튼 「코드·문서 내려받기」 클릭 (disabled:false, rect 240–442 × 417–468)
  ③ document.activeElement === 그 버튼        ← 클릭이 실제로 그 요소에 닿았다
  ④ GET /api/v1/factory/prj_…/export → 200 OK  ← 네트워크 기록
  ⑤ .run-note ok · role=status · 「내려받기를 시작했습니다 — prj_….zip」
```

| 층 | 판정 |
|---|---|
| 제품 버튼에 **실제 포인터 클릭**이 닿았다 | **확인** (activeElement + 네트워크 200) |
| 서버 ZIP 내용·권한 거절(403) | **확인**(지난 라운드, 같은 세션 응답을 풀어서) |
| 뷰어 디스크에 **파일이 저장**되었다 | **미검증** — 브라우저 패널이 뷰어 저장을 막는다 |
| 어느 화면을 눌렀나 | **새 Studio**(`RunControls`). 구 `ControlPanel` 버튼은 **미클릭**(활성 조건 미충족) |

---

## 3. 앱/보고서/문서 미리보기 조사 — **끊긴 곳이 없다. 제품을 바꾸지 않았다**

### 소비 경로 (코드)

```
AdaptivePhaseCanvas
 ├ 구현 단계(EXECUTION·BUILD·IMPLEMENTATION·CODE)
 │    → GeneratedAppRuntime → **기존 PreviewPanel 그대로** (rawCode = state.frontend_code_summary)
 │      · 그 패널의 문서 탭 13개(요구정의·기획서·…·수용검수·사용자 매뉴얼)도 함께 들어온다
 ├ 산출물 단계 10종 → StageArtifactCanvas
 │    → 문서: **PreviewPanel 의 ManualRenderer 재사용**(렌더러를 새로 만들지 않았다)
 │    → 보고서: 같은 렌더러 + 판정칩 / 단계 id 가 REPORT·CFO 면 ExecutiveReportView
 └ 낯선 단계라도 그 단계 산출물이 있으면 StageArtifactCanvas 로 넘어간다(`hasCustomArtifact`)
```

★ 기존/신규가 **같은 스냅샷**(`GET /state/latest`)을 읽는다. 별도 미리보기 API·엔진 없음.

### 실측 — 격리 환경 · **합성** 산출물 · LLM 0 · 운영 산출물 복사 0

전부 위 §2 와 같은 **실제 포인터 클릭**으로 이동했다.

| 유형 | 단계 | 화면 | 판정 |
|---|---|---|---|
| **앱** | 09 구현 | 샌드박스 iframe 안에서 합성 React 앱이 **실행됨** — `B6-PREVIEW-APP-001` · 「눌린 횟수: 0」 · 「🔒 안전 미리보기 · 실데이터 연결 제한」 | 정상 |
| **보고서** | 13 총괄 감독 | `DELIVERABLE 수용 검수 보고` · 판정칩 **「통과」**(낱말+색) · 본문·「보조 검토」 | 정상 |
| **문서** | 14 매뉴얼 작성 | `B6-PREVIEW-DOC-001` · 「사용 방법 1. 2.」 목록 렌더 | 정상 |
| **문서(구 경로)** | 구현 단계 PreviewPanel 탭 📘 | 같은 본문이 그대로 | 정상 — **두 경로 일치** |
| 빈 결과 ① 아직 | 03 사업 기획 | 「기획서(PRD)이(가) **아직** 없습니다 … 진행되면 채워집니다」 | 정상 |
| 빈 결과 ② 영영 | 05 화면 검증 | 「서버가 텍스트 요약을 남기지 않습니다. **기다려도 이 자리에는 생기지 않습니다**」 | 정상 |
| 지난 단계 표시 | 03·13·14 | 「지난 단계를 보고 있습니다 — 실행 중인 단계는 **구현**입니다」 | 정상 |
| 거절(403) | — | 코드상 `단계 지도를 그릴 근거가 없습니다` + `loadReason`(tone=forbidden). **실화면 미실행** | 미검증 |
| 문맥 전환 | — | 문맥·SSE 묶음에서 마감. **다시 열지 않았다** | 범위 밖 |

**결론: 「화면은 있는데 호출이 없음」 은 없다. 구현할 한 건이 없어 제품을 바꾸지 않았다.**

### ⚠️ 이번 조사에서 내가 두 번 잘못 쟀다 — 둘 다 제품 결함이 아니었다

**(가) fixture 가 에이전트 id 를 지어냈다.** 종전 파종은 `artifacts["Frontend_Dev"]` 였는데
정본(`core/agent_registry.py`)의 id 는 **`Frontend`** 다. 그래서 화면이 「14단계 중 **0단계**
완료」로 나왔고, 나는 그것을 「서버가 준 산출물을 화면이 안 읽는다」로 읽을 뻔했다.
정본 id 로 고치자 즉시 「**1단계 완료 · 현재 구현**」이 되었다. 필드 이름도 내가 짓지 않고
`STAGE_DOC_FIELDS` 를 보고 맞췄다.

**(나) 내가 바꾼 뷰포트가 클릭을 망가뜨렸다.** 화면을 크게 찍으려고 뷰포트를 강제로 바꿨더니
그 뒤의 클릭이 **전부 아무 데도 닿지 않았다.** 단계를 눌러도 작업면이 안 바뀌길래 결함으로
적을 뻔했다 — 같은 상태에서 「작업 목록」 버튼도 안 눌린 것을 보고 **계측기를 의심**했고,
뷰포트를 되돌리자 같은 클릭이 한 번에 됐다. 위 표는 전부 **되돌린 뒤**의 기록이다.

### 곁가지 관찰 (결함 아님 · 조치 안 함)

한 프로젝트에 구 통제실과 새 Studio 가 **동시에 mount** 되어 `PreviewPanel` 이 둘이고
iframe 도 2개다(각각 벤더 약 4MB 인라인). 설계 §10 이 의도한 병행 카나리 구간이라
동작 결함은 아니지만, **C3 정리 때 함께 치울 목록**으로 남긴다.

---

## 4. 검사·빌드

```bash
cd frontend && npx tsc -b && for f in scripts/check-*.mjs; do node "$f"; done && npm run build
```

```
프런트 187 PASS / 0 FAIL  (project 64 · draft-entry 17 · draft-open 29 · kit-app 14 · location 25 · release 38)
check-studio-contracts 157 / 0 · kit-getting-started 15+11 · process-installation · tsc -b · build 통과
```

---

## 5. §10.1 남은 기능 — 이름과 개수 (숫자만 반복하지 않는다)

정본 `docs/design_l2_unified_studio_execution_2026-09-12.md` §10.1 의 보존 대상은 **17개**다.

| 구분 | 개수 | 기능 |
|---|---|---|
| **실화면 증거로 닫을 수 있음** | **2** | 코드·문서 내려받기 / 앱·보고서·문서 미리보기 |
| **새 Studio 에 입구가 없음(확인됨)** | **1** | 기존 공유·승격 진입 — `ReleaseCanvas` 가 「종전 통제실에서 하십시오」라고 스스로 적어 둠 |
| **서버 지표 부재로 «미측정» 표기** | **1** | 비용 — `vm.project.cost === null` → 「누적 비용 미측정」(0 으로 채우지 않음). 연결 상태는 표시됨 |
| **코드 연결은 있으나 실화면 증거 미기록** | **13** | 프로젝트 생성/열기 · 요구 명확화 · 기획 시작 · 설계/계약 결정 · HOTL 승인/반려 · 실행 관찰 · 일시정지/중단/재개 · 한도 대기 · 실패 복구/횟수 제한 · 작업 재분할 · 수정 요구 · 근거·시험 결과 · 검토용 버전 저장 |

★ 13건을 「했다」로 세지 않는다 — 버튼과 호출은 있으나 성공/실패·권한·상태 갱신을 **같은
기준의 실측으로 기록하지 않았다.** 다음 후보를 고른다면 이 13건 중에서 고르는 것이 맞다.
**가산 없음 — 전체 21/40=52.5% 유지.**

---

## 6. 먼저 봐 달라는 것

1. **§1 의 수명 판정 기준**이 맞는지. 「현재 열린 프로젝트 + 화면 생존」 둘로 충분한가,
   아니면 요청마다 **일련번호**를 붙여 「그 요청의 답인가」까지 봐야 하는가.
   (같은 A 를 빠르게 두 번 누르면 첫 결과가 둘째 화면의 안내로 보일 수 있다.)
2. **§3 의 종료 범위** — 미리보기를 「정상, 변경 없음」으로 닫아도 되는지. 거절(403) 실화면은
   좁은 권한 계정 재로그인이 필요해 **이번엔 하지 않았다.**
3. **§5 의 13건** 중 다음 한 건을 지정해 주시면 그 한 건만 같은 깊이로 진행한다.

---

## 7. 건드리지 않은 것 / 환경

- 서버 제품 코드·권한 정책·상태코드·CORS **무변경**. skip·xfail 없음. 단언 약화 없음.
- 커밋·푸시·pull 없음. 유료 LLM·외부 전송 0. 운영 데이터·키·사용자 로그 무접촉.
- 격리 환경 가동 중. **원복 대상**: `launch.json` 의 `sent-isolated`, 워크트리의
  `run_isolated.py`·`tests/b6_sse_probe.py`, 합성 fixture(릴리스 1·프로젝트 1·부서 1·계정 3·
  산출물 3 + `latest_state.json` 의 `artifacts`·`frontend_code_summary`·
  `supervisor_report_summary`·`supervisor_verdict`·`user_manual_summary`),
  `data/instance.json` 의 배터리 노드 `dept_id`.
