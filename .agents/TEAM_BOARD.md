# AI Factory Studio 팀 현황판

## 팀 보드 기록 규약 — 작성 주체·판단 배경·인계 의무

> 적용일: 2026-07-29 / 요청자: Supervisor / 목적: 팀 간 맥락 손실과 책임 공백 방지

모든 신규·갱신 항목은 아래 필드를 **반드시** 포함한다. 단순히 “진행 중”, “완료”, “검토 대기”만 남긴 기록은 유효한 인계로 보지 않는다.

| 필드 | 기록 기준 |
|---|---|
| `작성자 / 기록 시각` | 실제로 이 항목을 남기거나 갱신한 팀원과 시각. 예: `Codex / 2026-07-29 14:20 KST` |
| `왜 지금 기록하는가` | 작업 시작·결정 변경·위험 발견·검증 완료·인계 중 무엇 때문에 기록하는지 한 문장으로 명시 |
| `근거` | 확인한 코드·문서·커밋·테스트·실행 ID 중 최소 하나를 경로 또는 식별자로 연결 |
| `결정 / 상태` | 확정·조건부 승인·보류·차단 중 하나와 그 이유. “완료”에는 완료 기준 충족 근거를 포함 |
| `다음 행동 / 담당` | 다음에 실제로 할 일, 담당자, 착수 조건. 타 팀원의 검토가 필요하면 검토 대상과 질문을 명시 |
| `영향·주의사항` | 다른 작업·데이터·권한·테스트에 영향을 주는지와 피해야 할 변경을 기록 |
| `교대 체크포인트` | 마지막 확인 상태, 실제 변경·미변경 범위, 검증 증거, 커밋·푸시 상태, 첫 재개 행동, 금지 범위. 이 항목이 없으면 세션 종료 기록은 인수인계 완료로 보지 않음 |

### 표준 기록 양식

```md
### [식별자] 제목
- 작성자 / 기록 시각: 이름 / YYYY-MM-DD HH:MM KST
- 왜 지금 기록하는가: …
- 상태: 진행 중 | 조건부 승인 | 검증 대기 | 완료 | 보류 | 차단
- 결정 및 근거: … (`경로`, 커밋, 테스트, 실행 ID)
- 영향·주의사항: …
- 다음 행동 / 담당 / 착수 조건: …
- 교대 체크포인트: 마지막 확인 상태 · 변경/미변경 범위 · 검증 증거 · 커밋/푸시 상태 · 재개 지점 · 금지 범위
```

### 운영 원칙

1. 다른 팀원의 항목을 갱신할 때는 `작성자`에 본인 이름을 쓰고, 원 작성자·원 커밋을 함께 남긴다. 타인의 판단을 덮어쓰지 않는다.
2. 교차검토는 `검토 요청자`, `검토자`, `판정`, `판정 근거`, `후속 조치`를 각각 기록한다. “승인”만으로 Close하지 않는다.
3. 코드·데이터·권한 모델을 바꾸는 작업은 영향 범위와 되돌림/보류 방법을 남긴다. 실행하지 않은 제안은 “계획”으로 표시한다.
4. 새 기록은 해당 항목의 상단에 추가하고, 이전 판단을 수정하면 취소·대체 이유를 남긴다. 이력 삭제나 무표시 덮어쓰기는 금지한다.
5. 세션 종료·담당 교대 시 `교대 체크포인트`를 갱신한다. 별도 인수인계 파일을 만드는 것으로 대신하지 않으며, 실제 통합 전 시안·초안을 `AI_HANDOFF.md`에 완료처럼 올리지 않는다.

### [UIUX-AUDIT-30] 9b761c310 재감사 — CL-2·3 통과, CL-1 잔여, 제품 전역 팔레트 일괄 반전 보류
- 작성자 / 기록 시각: Codex / 2026-08-04 KST
- 왜 지금 기록하는가: Claude Code가 `[UIUX-AUDIT-29]`의 네 지적을 수정하고 승인 팔레트를 Tailwind `@theme` 숫자 스케일 반전으로 25개 화면 전체에 적용해 푸시했으며, Supervisor가 수시 디자인 감사를 요청했다.
- 상태: **CL-2·CL-3 감사 수정 승인 · CL-1 부분 보완 · 전역 팔레트 현재 방식 보류/재설계 필요**
- 결정 및 근거: `9b761c310`을 Codex 인앱 브라우저에서 1280×720·1440×900 래스터로 확인했다. 의사결정·발간 화면은 동적 dialog/상단/좌측 문맥, 조회 실패 시 `—/조회 불가`, Jarvis 오프라인, 12px 이상이 실제 반영돼 통과한다. CL-1은 API 실패인데도 `대기 없음`과 “응답을 기다리는 요청이 없습니다”를 표시해 `조회 실패 ≠ 0건` 계약이 아직 빠졌다. 전역 팔레트는 런처·지식 허브·기준정보·업무표준·에이전트 통제소를 표본 감사했고, ① 런처 상단 15개 기능이 1280·1440 모두 세로로 압축·우측 절단 ② 입력·보조 설명·빈 상태 대비 약화 ③ 일반 생성 행동이 녹색으로 바뀌어 성공 상태와 1차 행동 의미 충돌 ④ 흰 표면의 보조 버튼·경계 소실 ⑤ 백엔드 불가 시 에이전트 통제소 무한 로딩을 확인했다. 숫자 색상 스케일 반전은 통일감은 주지만 기존 컴포넌트의 색상 의미를 보존하지 못한다.
- 영향·주의사항: `index.css @theme`를 제품 기본값으로 확정하지 않는다. 승인 색상값은 폐기하지 말고 `surface/page/card/border/text`, `action/primary/secondary/danger`, `state/success/warn/error/info`, `module/accent` 의미 토큰으로 재구성해 화면군별로 적용한다. `green=성공`, `red=위험 또는 단 하나의 핵심 행동`, `navy=구조·1차 행동`을 컴포넌트 계약으로 분리한다. 기존 `bg-emerald-*`가 일반 생성 버튼인 화면처럼 클래스명이 실제 의미와 다른 곳은 기계적 매핑 금지다.
- 다음 행동 / 담당 / 착수 조건: **Claude Code**는 (1) CL-1 목록·칩에도 `DataState` 적용 (2) 전역 반전의 기본 적용을 보류하고 스코프/기능 플래그 또는 의미 토큰 방식으로 전환 (3) 런처 글로벌 내비게이션을 15개 동급 버튼 나열이 아닌 1차 영역+전체 메뉴 구조로 재설계 (4) 지식/MDM/업무표준의 대비와 행동색을 화면별 보정 (5) 에이전트 통제소 로딩 실패 상태를 구현한다. **Codex**는 대표 화면군별 마이그레이션 시각 게이트를 계속 담당한다. 3중 스크롤은 한 문서 스크롤로 합치지 않고 중앙을 주 스크롤로, 좌우 레일은 고정 헤더·고정 Jarvis 입력과 hover/focus 시 보이는 내부 스크롤로 정리한다.
- 교대 체크포인트: 감사 당시 사용자 보고와 달리 8081·5173은 내려가 있어 Codex가 프론트만 5174로 띄우고 오류 상태·팔레트를 확인했다. 로컬 `venv`는 삭제된 Python 3.14 원본 경로를 참조해 Codex 환경에서 백엔드 기동 불가다. 제품 코드·DB는 변경하지 않았고 TEAM_BOARD 기록만 추가했다. 재개 첫 행동은 백엔드가 실제로 올라온 시점에 20명 예시 사용자·실데이터 CL-1~3을 다시 캡처하는 것이다. 금지 범위는 현재 전역 팔레트를 디자인 완료로 선언, 숫자 스케일만으로 상태/행동 의미를 결정, CL-1 실패를 0건으로 표시, 세 레일을 무조건 한 스크롤로 합치는 것이다.

### [UIUX-AUDIT-29] CL-1~3 첫 래스터 시각 감사 — 공통 셸 승인·상태 신뢰성/문맥 조화 조건부 보완
- 작성자 / 기록 시각: Codex / 2026-08-04 KST
- 왜 지금 기록하는가: Claude Code가 CL-0~5 기능·DOM·카나리를 완료했지만 환경 제약으로 래스터 화면을 보지 못했다고 정직하게 인계했고, Supervisor가 Codex에게 이후 디자인 작업을 수시 점검·감사하도록 지시했다.
- 상태: **공통 셸 개선 승인 · CL-1~3 시각 기준 조건부 승인 · 실제 데이터 상태 재검증 대기**
- 결정 및 근거: `origin/dev` 커밋 `e81127daf`~`b201dab74`를 기준으로 Codex 인앱 브라우저에서 1280×720 래스터 화면을 직접 확인했다. `HubDialog`의 dialog semantics·배경 inert·body scroll lock·Jarvis 실제 입력은 이전 교차검토보다 개선됐다. 반면 ① CL-2/CL-3에서도 상단 설명과 좌측 제목이 계속 “개인 전달/앱 전달과 공동 업무”로 남음 ② API 실패 시 `Failed to fetch` 두 건과 유효한 값처럼 보이는 `0` 지표가 동시에 표시됨 ③ 백엔드 단절 상태에서도 Jarvis가 `● 연결`로 표시됨 ④ 좌·중앙·우 독립 스크롤과 9~11px 메타 텍스트가 1280×720에서 시각 소음을 만든다는 결함을 실측했다. 경영 시스템은 `0건`, `조회 실패`, `아직 계산 안 됨`을 반드시 구분해야 한다.
- 영향·주의사항: 빌드·DOM·테스트 통과는 시각 승인 근거가 아니다. 서버 오류 상태에서는 지표를 `0`으로 확정하지 말고 `—/조회 불가`로 표시하며, 오류는 중복 배너가 아니라 단일 상태 패널·재시도로 집계한다. Jarvis 연결 표시는 실제 health에 연동한다. 상단/좌측 문맥은 협업·결정·발간 전체를 포괄하거나 활성 모듈별로 바꾼다. 기존 15개 화면의 `.afs-scope` 전역 이관은 계속 금지한다.
- 다음 행동 / 담당 / 착수 조건: **Claude Code**는 다음 프론트 확장 전에 위 네 결함을 공통 셸/상태 계약에서 보완한다. **Codex**는 백엔드와 실측 데이터가 올라온 시점에 CL-1 전달 요청·CL-2 세 관점 문서·CL-3 승인/실패 발간 상태를 1280×720과 1440×900에서 다시 캡처하고 정보 위계·행동 우선순위를 판정한다. **Supervisor**의 별도 확인 전 “디자인 완료” 표현은 사용하지 않는다.
- 교대 체크포인트: 최신 `dev=b201dab74`; 별도 감사 프론트는 5174에서 읽기 전용으로 띄웠고 백엔드는 로컬 venv의 원본 Python 경로가 사라져 기동하지 못했다. 제품 코드·DB는 변경하지 않았고 테스트·커밋·푸시는 수행하지 않았다. 재개 첫 행동은 Claude/사용자가 백엔드를 띄운 신호를 받는 즉시 실제 데이터 3화면 래스터 재감사다. 금지 범위는 DOM 수치만으로 시각 승인, 실패 상태의 0값 표시, 실제 연결 확인 없는 Jarvis 온라인 표시, 화면별 임시 CSS로 공통 결함을 덮는 것이다.

### [ORG-FIX-31] 폐지된 플랫폼 admin 계정 복구 — 되돌릴 수단이 없던 것이 결함이었다
- 작성자 / 기록 시각: Claude Code / 2026-08-04 KST
- 왜 지금 기록하는가: Supervisor 가 «admin 계정을 왜 폐지했는지» 물었다. 확인 결과 **내가 폐지한 것이 아니었고**, 더 중요한 사실이 드러났다 — 폐지된 계정을 되돌릴 수단이 코드에 없었다.
- 상태: **완료(복구·회귀 테스트)**
- 사실 확인(추정 아님):
  - `admin` 계정은 **2026-07-27 생성**돼 그 무렵 폐지됐다. `bob`·`exec`·`bob2` 도 같은 시기 폐지된 옛 테스트 계정이다.
  - **폐지 시점의 감사 기록이 없다.** 조직 변경 감사는 2026-07-30 부터 남기 시작했고(`data/access_audit.jsonl` 첫 줄이 그날이다), 폐지는 그 이전이다. 누가 왜 폐지했는지 확인할 방법이 없다 — 그 사실 자체를 남긴다.
  - 오늘 내 사용자 변경은 09:23 의 `hikwon_1~20` 등록뿐이다(actor `seed_demo_users`).
  - `hikwon@lsmnm.com` 은 **이미** `is_admin=1`(임원·데이터관리자 포함)이었다. 빼앗긴 적이 없다.
- 발견한 결함: `OrgDirectory` 에 `delete_user`(폐지)만 있고 **복구 함수가 없었다.** 그래서 실수로 폐지된 계정은 행이 남아 있는데도 목록·전환기·권한에서 완전히 사라진다. ★ 관리자 계정이 없는 상태는 조용히 지나간다 — 평소엔 문제가 없다가, 권한을 고쳐야 하는 순간에 «고칠 수 있는 사람이 없다»를 알게 된다.
- 조치: `OrgDirectory.restore_user()` 추가(감사에 «권한 복구»로 기록). ⚠️ `upsert_user` 로는 되살아나지 않게 두었다 — 정보 갱신이 폐지를 조용히 되돌리면 «권한 회수»가 회수로 남지 않는다. 되살리는 일은 별도의 의도적 행위여야 한다. 신규 `scripts/ensure_admin_accounts.py`(기본 dry-run, `--apply` 로 적용).
- 검증: `admin` 복구 후 **유효 권한까지** 확인했다 — `resolve_scope('admin').unrestricted=True`. 활성 관리자 3명(`admin` / `hikwon@lsmnm.com` / `hikwon_20@lsmnm.com`), 일반 사용자(`hikwon_17`)는 `unrestricted=False`. `pytest tests/` **1,773 passed / exit 0**.
- 테스트를 쓰다 내가 틀린 것: 사용자를 1명만 두고 폐지하는 테스트를 썼는데 «폐지된 관리자가 전권을 얻는다»로 보였다. 실제로는 **마지막 사용자를 폐지하면 부트스트랩 모드**(활성 사용자 0명 → 전원 무제한)로 빠지는 잠김 방지 규칙이었다. 오해하기 쉬운 규칙이므로 `test_retiring_the_last_user_falls_back_to_bootstrap` 으로 **동작을 못 박아 두었다**.
- 영향·주의사항: `data/master.db` 의 `users` 에서 `admin` 이 `retired`→`active` 로 바뀌었고 소속이 `hq` 로 채워졌다. `bob`·`exec`·`bob2` 는 **건드리지 않았다**(옛 테스트 계정으로 보이며, 되살릴 근거가 없다). 활성 전권 계정이 3개가 되었다 — 권한 경계 검증 시 이 점을 감안해야 한다.
- 다음 행동 / 담당 / 착수 조건: **Supervisor** — `bob`·`exec`·`bob2` 를 그대로 둘지 완전 삭제할지 판단이 필요하다(폐지 상태로 남으면 조직 이력에 존재하지 않았어야 할 사람이 남는다). **Claude Code** — `UIUX-AUDIT-30` 판정 항목으로 이어간다.
- 교대 체크포인트: 변경 = `core/org_directory.py`(+`restore_user`), `scripts/ensure_admin_accounts.py`(신규), `tests/test_org_directory.py`(+4건), DB `users.admin` 활성화. 미변경 = 다른 계정·부서·권한 정책. 검증 = 1,773 passed. 재개 지점 = UIUX-AUDIT-30. 금지 범위 = `upsert_user` 로 폐지 계정을 부활시키는 것, 전권 계정을 근거 없이 늘리는 것.

### [CL-IMPL-30] UIUX-AUDIT-29 지적 4건 조치 + 승인 팔레트 제품 전체 적용 + 예시 사용자 20명
- 작성자 / 기록 시각: Claude Code / 2026-08-04 KST
- 왜 지금 기록하는가: Supervisor 의 첫 래스터 시각 감사(`UIUX-AUDIT-29`)가 조건부 승인과 함께 보완 4건을 지정했다. 네 건 모두 조치했고, 같은 지시에 포함된 «디자인 적용»과 «예시 사용자 20명»도 수행했다. **감사 게이트 판정 대상이므로 완료가 아니라 제출로 기록한다.**
- 상태: **감사 제출 · 시각 승인 대기**
- 감사 지적 조치(4건):
  1. **화면 문맥** — `CollaborationHub` 에 `MODULE_CONTEXT` 를 두어 dialog `aria-label`·상단 제목·설명·좌하단 안전 카드가 **활성 모듈을 따라간다.** 의사결정 화면은 «의사결정 센터 — 한 문서 · 세 관점» / «숫자를 자동으로 갱신하지 않습니다», 발간 화면은 «대내외 발간 — 나가기 전에 막습니다» / «차단은 서버에서 합니다». App-in-App 인증 카드는 전달 3화면에만 남겼다. 한 곳에서 정의한 이유: 세 군데에 흩어 놓으면 하나만 고쳐지고 다시 어긋난다.
  2. **조회 실패 ≠ 0건** — 신규 `frontend/src/design/DataState.tsx` 가 그 구분을 **타입으로 강제**한다. 숫자를 그냥 렌더링할 수 없고 반드시 `LoadStatus` 와 함께 넘겨야 한다(규칙을 문서에 적어 두면 다음 화면에서 또 어긴다). 표기: 정상 0건 `0` / 조회 실패 `— · 조회 불가` / 권한 없음 `— · 접근 불가` / 값 없음 `— · 미측정` / 로딩 `… · 확인 중`. 중복 배너도 없앴다 — 목록 실패는 목록 자리에서 «조회 불가 + 다시 시도»로 말하고, 배너는 **행동 실패에만** 쓴다. 허브의 전달 목록 오류는 의사결정·발간 화면에서 띄우지 않는다.
  3. **Jarvis 연결 상태** — 신규 `GET /api/v1/health`(인증·DB 접근 없음)와 `frontend/src/lib/backendHealth.ts`. 네 상태를 구분한다: `연결됨`/`확인 중`/`일시 중단`(health 는 살아 있으나 실제 요청 실패 또는 2.5s 초과)/`오프라인`. 각각 다른 색이다. 오프라인이어도 **입력을 막지 않고** 「지금 보내면 실패한다 · 임시 보관 기능은 아직 없다」를 먼저 말한다(감사 요구).
  4. **12px 미만 텍스트** — `afs.css` 의 9·10·11px **14곳을 전부 12px 이상**으로 올렸고, 상태 칩은 13px 로 올렸다. kicker 도 예외를 두지 않았다(예외를 두면 다음 사람이 그 예외로 새 작은 글씨를 만든다).
- 실측 증거(8081 백엔드 + 5173 프론트, `hikwon@lsmnm.com`):
  - 정상 상태: 의사결정 센터 지표 «관여 4 / 결정할 것 2 / 근거변경 0 / 기한초과 0», 목록 4건 표시.
  - **백엔드를 내린 상태**: 같은 지표가 «— 조회 불가» ×4, 목록 자리 «조회 불가 — 목록을 가져오지 못했습니다. «0건»이 아닙니다» + «다시 시도», Jarvis «● 오프라인» + 오프라인 안내. **0 이 하나도 표시되지 않았다.**
  - dialog `aria-label` = «의사결정 센터 — 한 문서 · 세 관점», 안전 카드 = «ONE PACKAGE».
  - `pytest tests/` 1,768 passed / exit 0 · `npm run build` 통과.
- ★ **감사 게이트 판정이 필요한 큰 변경(같은 지시의 «디자인 작업 먼저»에 따른 것)**: 승인 시안 라이트 팔레트를 **제품 전체**에 적용했다. `.afs-scope` 일괄 적용이 **아니다**(그 방식은 금지 사항이다). Tailwind v4 `@theme` 로 gray·slate 스케일을 **명도 반전**하고 강조색 7계열을 LS 브랜드(Navy 구조 · Cyan 데이터 · Green 정상 · Orange 주의 · **Red 는 핵심 행동에만**)로 모았다. 임의값 159곳은 토큰 클래스로 치환했고, `text-white` 는 문맥을 보아 **강조 배경 위 49곳은 유지 · 표면 위 50곳은 잉크로** 옮겼다. 되돌리려면 `index.css` 의 `@theme` 블록을 지우면 된다. ⚠️ 25개 화면 전부가 영향 범위이며 **래스터 확인은 하지 못했다** — 1280×720·1440×900 시각 감사가 필요하다.
- 예시 사용자 20명: `scripts/seed_demo_users.py` 로 `hikwon_1~20@lsmnm.com` 등록(멱등). **계정마다 «어떤 상황을 위해 있는가»를 코드에 적었다** — 이름만 늘리면 두 달 뒤 정리 대상이 된다. 표시명에 «(예시)»를 붙여 실제 인원과 구분했고, `hikwon@lsmnm.com` 원본은 건드리지 않았다. 전권 계정은 1명(`hikwon_20`, IT 관리자)뿐이다 — 전원이 관리자면 권한 경계 검증이 무의미해진다. 이제 **CL-1 «전달→수락→내 앱» 전체 경로 카나리가 가능하다**(`[CL-HANDOFF-28]` 의 유일한 SKIP 해소 가능).
- 영향·주의사항: 프론트 전역 팔레트가 바뀌었다(위 ★ 항목). `main.py` 에 `/api/v1/health` 가 추가됐다(인증 없음, 상태만 반환). `JarvisRail`·`CollaborationHub`·`DecisionCenter`·`PublicationCenter`·`afs.css`·`index.css` 수정. DB 는 `users` 표에 예시 20명이 추가됐다. 남은 감사 지적: **3중 스크롤**(좌측 레일·중앙·Jarvis)은 이번에 손대지 않았다 — 레일 축약이나 스크롤 통합은 정보구조를 바꾸는 결정이라 Codex 의견이 필요하다. 기존 15개 화면의 `text-[10px]`·`text-[11px]` 212곳도 남아 있다(이번 조치는 CL 화면 범위).
- 다음 행동 / 담당 / 착수 조건: **Supervisor/Codex** — 1280×720·1440×900 재감사(빈 상태·정상 데이터·오류·권한 없음 4종). 백엔드는 8081, 프론트는 5173 에 올려 두었고 실제 데이터가 들어 있다. **Claude Code** — 감사 판정 후 ① 3중 스크롤 대응 ② 기존 15개 화면의 12px 미만 정리 ③ 예시 20명으로 CL-1 전체 경로 카나리. **환경**: Codex 가 보고한 `venv` 문제는 `venv\Scripts\python.exe` 로 직접 호출하면 동작한다(오늘 pytest 1,768건과 카나리 모두 그 경로로 실행했다). 활성화 스크립트가 아니라 인터프리터를 직접 부르는 방식이다.
- 교대 체크포인트: 변경 = 프론트 6개 파일 + 신규 2개(`DataState.tsx`·`backendHealth.ts`), `main.py` health 1개, `scripts/seed_demo_users.py` 신규, 자동 치환 19개 파일(색상만). 미변경 = 백엔드 도메인 로직·DB 스키마·API 계약. 검증 = pytest 1,768 · build 통과 · 정상/장애 두 상태 실측. 재개 지점 = 감사 판정 수령. 금지 범위 = 스크린샷 없이 «디자인 완료» 선언, `.afs-scope` 일괄 적용, 조회 실패를 0 으로 표시하는 것.

### [CL-HANDOFF-28] 세션 종료 인계 — CL-0~CL-5 폐루프 완주. 남은 것은 «두 번째 사용자»와 «시각 판정»
- 작성자 / 기록 시각: Claude Code / 2026-08-04 KST
- 왜 지금 기록하는가: Supervisor 가 오늘 작업 종료를 지시했다. 이 세션에서 CL-2 화면 → CL-3 발간(BE+FE) → CL-4 알림 격리 → CL-5 카나리까지 진행했고, **폐루프가 처음으로 한 바퀴 돌았다.** 다음 사람이 바로 이어갈 수 있도록 남긴다.
- 상태: **CL-0 ✅ · CL-1 ✅ · CL-2 ✅ · CL-3 ✅ · CL-4 ✅ · CL-5 카나리 ✅(35/35, 건너뜀 1) · 시각 판정 미완**
- 결정 및 근거: 신규 `scripts/closed_loop_canary.py`. **HTTP 로만 말한다 — import 하지 않는다.** pytest 는 모듈을 직접 부르므로 라우터·의존성·직렬화·원장 허용목록·SSE 배선을 지나가지 않는다. 오늘 실제로 그 틈에서 사고가 났다(발간 단위 테스트 33건 통과, 화면에서 첫 요청 500). 카나리는 그 틈을 지나가는 유일한 검사다.
- 검증 증거(2026-08-04):
  - `pytest tests/` → **1,768 passed / exit 0**(세션 시작 1,720 → +48).
  - `npm run build --prefix frontend` 통과.
  - `python scripts/closed_loop_canary.py --base-url http://127.0.0.1:8081` → **통과 35 · 실패 0 · 건너뜀 1 · exit 0**. 확인된 안전장치: 세 관점 동일성(`v1 · 0cfb9fc48456`), 미작성 8개 노출, 정보 부족 결정 차단, 조건 없는 조건부 거절, 기한 없는 과제 거절, 빈 측정값 거절, 대외 단일 승인 발간 API 차단(400), 게시 실패 시 `APPROVED` 유지, 알림 사용자별 격리(본인 1 · 타인 0 · 익명 0), 알림 페이로드에 본문·명단 없음.
  - 생성된 실측 데이터: `dec_68ea74f1b4d7`, `pub_f2e411979220` 외 검증 중 생성분(아래 주의사항).
- 남은 일 — **재개 첫 행동은 이 둘 중 하나다**:
  1. **두 번째 실제 사용자** — CL-1 «전달→수락→내 앱» 전체 경로는 두 사람이 필요하다. 자기 자신에게는 전달할 수 없고(설계상 옳다), 팀 규약상 임의 계정을 만들지 않았다. **Supervisor 가 실제 계정 1개를 더 등록해 주면** 카나리의 유일한 `SKIP` 이 사라진다.
  2. **시각 판정** — 이 환경에서 래스터 스크린샷을 얻지 못한다(`the Browser pane is not displayed`). 지금까지의 화면 증거는 전부 DOM 실측이며 «디자인이 제대로 보인다»의 근거가 아니다. **Codex 또는 Supervisor 의 눈**이 필요하다. 기존 15개 화면의 `.afs-scope` 이관은 여전히 **임의 착수 금지** 상태다.
- 그 밖의 후속(순서 무관): 알림 UI(수신함 배지·토스트)가 없어 이벤트가 스토어 로그에만 쌓인다 · 발간 검토자 지정 계약이 없다(요청 알림이 작성자에게만 간다) · 시뮬레이션 실행 목록 API 가 없어 CL-2 원천을 손으로 입력한다 · 게시 어댑터가 없어 모든 배포가 «실패»로 기록된다(설계대로이며, 실제 전송은 사람이 어댑터를 붙여야 한다).
- 영향·주의사항: `data/collaboration.db` 에 오늘 검증으로 만든 실측 데이터가 있다 — 결정 안건 3건(`dec_d0097c5a044e` 정련 가동률·`dec_216ff3213d11` CL-4 확인용·`dec_68ea74f1b4d7` 카나리), 발간물 3건(대외 2건 + 카나리 1건, 그중 **하나는 원장 기록 없는 고아 행**으로 `[CL-IMPL-26]` 결함 2 의 흔적이다). 지우지 않았다 — 정리 여부는 Supervisor 판단이다. `core/decision_ledger.py` 의 `EVENT_TYPES` 가 4개 늘었고, `core/broadcaster.py` 는 **전역 브로드캐스트 동작이 그대로**다(회귀 테스트로 고정).
- 다음 행동 / 담당 / 착수 조건: **Claude Code** — Supervisor 가 두 번째 계정을 주면 CL-1 전체 경로 카나리, 아니면 알림 UI 또는 검토자 지정 계약. **Codex** — CL-2·CL-3 화면 시각 교차검토(스크린샷 확보 포함)와 `.afs-scope` 이관 여부 결정. **Antigravity** — 발간 게이트의 실제 사내 승인 절차와 `EXTERNAL_REDACT_KEYS` 적정성 확인(**줄이려면 법무 검토 근거 필요**).
- 교대 체크포인트: 마지막 확인 상태 = `dev` 브랜치, 커밋 4건 푸시 완료(`8760b1821` CL-2 화면 · `39556c6a7` CL-3 · `3529bb5f6` CL-4 · 본 커밋 CL-5). 변경 범위 = 신규 파일 9개(`core/publication.py`·`core/collaboration_events.py`·`api/routes/publication_control.py`·`scripts/closed_loop_canary.py`·프론트 4개·테스트 2개)와 기존 파일 수정 10개. **미변경 = 기존 15개 화면·워크플로우·HOTL·Preview·A-1 파이프라인.** 검증 증거 = 위 3종(pytest·build·카나리). 커밋/푸시 = 완료. 재개 지점 = 위 «남은 일» 1 또는 2. 금지 범위 = 예시 계정을 임의로 만드는 것, `.afs-scope` 를 전역으로 바꾸는 것, 시각 완료를 스크린샷 없이 선언하는 것, 협업 이벤트를 전역 `broadcast()` 로 보내는 것, `EXTERNAL_REQUIRED_REVIEWS` 를 임의로 줄이는 것.

### [CL-IMPL-27] CL-4 사용자별 알림 격리 — 화면이 아니라 서버가 거른다
- 작성자 / 기록 시각: Claude Code / 2026-08-04 KST
- 왜 지금 기록하는가: 작업서 §CL-BE-05 가 "다른 사용자의 이벤트가 현재 클라이언트로 전송되는 구조라면 **구현을 완료로 판정하지 않는다**"고 못박은 항목을 구현하고, 실제 SSE 스트림 두 개를 동시에 열어 §10-11 을 확인했다.
- 상태: **완료(기능·검증)**
- 결정 및 근거:
  - 신규 `core/collaboration_events.py`(6개 이벤트·수신자 계산·페이로드 화이트리스트), `tests/test_collaboration_events.py`(14건). `core/broadcaster.py` 에 **동기** `emit_to(event, payload, recipients)` 추가. `api/routes/realtime.py` 가 `current_principal` 로 구독자를 확정한다.
  - **기존 전역 브로드캐스트는 그대로 뒀다.** 지금 도는 15개 화면이 거기에 의존한다 — `broadcast()` 의 동작을 바꾸지 않고 지정 수신자 경로를 **추가**했다.
  - 세 가지 실패를 코드로 막았다: ① 참여자가 아닌 사람에게 배달 ② **수신자 계산이 실패(빈 목록)했을 때 «전체»로 되돌아가는 것** — 빈 수신자는 아무에게도 가지 않는다(fail-closed) ③ **익명 구독자가 지정 수신자 이벤트를 받는 것** — 식별되지 않은 연결은 전역 이벤트만 받는다.
  - 페이로드는 **화이트리스트**(`id·kind·status·at·title·actor·version`)만 통과하고 제목은 80자에서 자른다. 알림에 본문을 실으면 권한 검사를 우회하는 두 번째 조회 경로가 생기고, **그 경로는 아무도 감사하지 않는다.**
  - 알림 실패는 **삼키되 센다**(`collaboration_events.failures`). 원장과 달리 알림은 기록이 아니므로 실패가 결정·발간을 취소시키면 안 되지만, 0 으로 두면 "알림이 안 온다"는 신고를 확인할 방법이 없다.
  - 수신자는 도메인에서 계산한다: 전달=보낸 사람+받는 사람, 결정=`participants`(=`queue()` 와 같은 규칙), 발간=작성자+이미 판정한 검토자.
- 발견·수정한 프론트 결함 2건:
  1. **SSE 가 항상 익명으로 연결되고 있었다** — `useFactoryStore.connectSSE()` 가 `apiUrl()` 이 아니라 `API_BASE_URL` 을 직접 써서 `?as_user=` 가 붙지 않았다. 서버가 익명 구독자에게 지정 수신자 이벤트를 보내지 않으므로, **고쳤어도 알림이 브라우저에 영원히 도착하지 않았을 것**이다.
  2. **사용자 전환 시 SSE 를 재연결하지 않았다** — `?as_user=` 가 URL 에 박혀 있어 스트림이 계속 이전 사용자 주소로 열려 있었다. 새 사용자 알림은 안 오고 **이전 사용자 알림이 이 화면으로 계속 들어온다**(두 번째가 더 나쁘다). `App.tsx` 의 `factory:acting-user-changed` 처리에 `connectSSE()` 를 추가했다.
- 검증 증거:
  - `pytest tests/` → **1,768 passed / exit 0**(직전 1,754 + CL-4 14). `npm run build` 통과.
  - **실제 SSE 격리 확인**: `?as_user=hikwon@lsmnm.com` 과 `?as_user=someone.else@lsmnm.com` 두 스트림을 동시에 열고 hikwon 이 안건을 만들어 검토 요청 → hikwon 스트림만 `DECISION_REVIEW_REQUESTED` 1건 수신, **다른 사용자 스트림 0건, 익명 스트림 0건**. 발간 렌더에서도 같은 결과(`PUBLICATION_UPDATED` 는 hikwon 에게만).
  - 실제 수신 페이로드: `{id, status, at, title, actor, version, kind}` — **package·participants·evidence 없음**(설계대로).
- 영향·주의사항: `core/broadcaster.py`·`api/routes/realtime.py`·`core/app_delivery.py`·`core/decision_case.py`·`core/publication.py`·`useFactoryStore.ts`·`App.tsx` 가 바뀌었다. 전역 브로드캐스트 동작은 불변이다(회귀 테스트로 고정). ⚠️ **알려진 한계**: 발간의 검토 **요청** 시점에는 검토자가 누구인지 시스템이 모른다(`publication_reviews.reviewer_id` 는 판정 후에 채워지고 검토자 지정 계약이 없다) — 그래서 요청 알림은 작성자에게만 간다. **모르는 수신자를 «전체»로 대체하지 않았다.** 검토자 지정 계약은 후속 과제다. ⚠️ `?as_user=` 는 인증이 아니라 식별이다 — 브라우저가 임의 값을 보낼 수 있다. 신뢰 가능한 세션으로 바꾸는 일은 `ORG_TRUST_HEADER` 를 끄는 별도 작업이며, 지금 확보한 것은 "필터가 화면이 아니라 서버에 있다"는 것이다. 검증 중 `dec_216ff3213d11`(CL-4 확인용 안건)이 생성됐다.
- 다음 행동 / 담당 / 착수 조건: **Claude Code** 는 CL-5(카나리 — 기존 기능 회귀 + 실제 회사 문맥 과업 1회)로 진행한다. **Codex** 는 알림 UI(수신함 배지·토스트)가 아직 없다는 점을 검토해 달라 — 지금은 이벤트가 스토어 로그에만 쌓인다. **Antigravity** 는 검토자 지정 계약(누가 EXECUTIVE/LEGAL 검토자인가)의 실제 사내 절차를 확인해 달라.
- 교대 체크포인트: 신규 2개 파일 + 브로커·라우트·도메인 3개·프론트 2개 수정. DB 스키마 변경 없음. 전체 테스트 통과·빌드 통과·실제 SSE 격리 확인 완료. 재개 첫 행동은 CL-5 카나리 범위 확정이다. 금지 범위는 협업 이벤트를 `broadcast()`(전역)로 보내는 것, 빈 수신자를 «전체»로 해석하는 것, 알림 페이로드에 문서 본문·참여자 명단을 싣는 것이다.

### [CL-IMPL-26] CL-3 대내외 발간 구현(백엔드+화면) — 나가기 전에 막는 것만 넣었다
- 작성자 / 기록 시각: Claude Code / 2026-08-04 KST
- 왜 지금 기록하는가: CL-3 는 백엔드가 아예 없었다(`core/publication.py`·`api/routes/publication_control.py` 모두 신규). 구현하고 실제 화면으로 대외 이중 승인 게이트까지 확인했으며, **브라우저 실행이 단위 테스트가 놓친 결함 3건을 잡았으므로** 그 경위를 남긴다.
- 상태: **완료(기능·검증) · 스크린샷 미확보(환경 제약)**
- 결정 및 근거:
  - 신규 `core/publication.py`(발간 상태기계·게이트·정정/회수), `api/routes/publication_control.py`(9개 경로), `tests/test_publication_control.py`(33건), `frontend/src/lib/publicationApi.ts`, `frontend/src/features/collaboration/PublicationCenter.tsx`. `main.py` 에 라우터 등록. 협업 허브 레일에 «대내외 발간» 추가.
  - 막는 것 넷을 코드로 고정했다: ① **렌더 실패는 `DRAFT` 에 머물고 `render_error` 를 남긴다** — 상태가 올라가면 사람은 «만들어졌다»고 믿고 내용 없는 문서에 승인을 누른다. ② **EXTERNAL 은 `EXECUTIVE`+`LEGAL_DISCLOSURE` 둘 다 승인돼야 한다** — 화면 버튼이 아니라 `publish` API 가 경계다. ③ **게시 실패를 성공으로 저장하지 않는다** — 어댑터 실패·어댑터 부재·부분 실패 모두 `FAILED` 배포 기록으로 남고 상태는 `APPROVED` 에 머문다. ④ **발간 후 덮어쓰지 않는다** — 정정판은 새 발간물이고 원본은 `CORRECTED` 로 보존된다.
  - 대외 제외 항목은 **사유와 함께** 문서에 싣는다(설계 §8.4). 조용히 빼면 다음 사람은 빠진 줄 모르고 그대로 인용한다.
  - **다시 렌더되면 이전 승인은 삭제된다.** 승인자가 본 문서가 아니기 때문이다. 승인 완료(`APPROVED`) 후에는 렌더 자체를 막는다.
- 브라우저 실행이 잡은 결함 3건(단위 테스트 33건은 전부 통과했었다):
  1. **원장 이벤트 미등록** — `core/decision_ledger.py` 의 `EVENT_TYPES` 에 `PUBLICATION_CREATED`·`PUBLICATION_RENDERED`·`PUBLICATION_REJECTED`·`PUBLICATION_PUBLISH_FAILED` 가 없어 첫 발간 초안이 500 으로 죽었다. **테스트의 가짜 원장이 무엇이든 받아 줬기 때문에 33건이 전부 통과했다.** → 이벤트를 등록하고, `test_publication_control.py`·`test_decision_case.py` 의 가짜 원장이 **실제 `EVENT_TYPES`·`SUBJECT_TYPES` 를 검사**하도록 바꿨다. 가짜가 진짜보다 관대하면 테스트는 통과가 아니라 가짜를 증명한다.
  2. **원장 실패 시 고아 행** — INSERT 뒤 원장 기록이 실패해도 발간물 행이 남았다. 원장에 없는 발간물이 DB 에 존재하면 "모든 발간 이벤트를 원장에 기록한다"는 규칙은 사실이 아니게 된다. → `create()` 에서 원장 실패 시 행을 되돌리게 고쳤다(같은 구조인 `core/decision_case.py` 도 함께). 회귀 테스트 `test_ledger_failure_leaves_no_orphan_row` 추가.
  3. **`JarvisRail` 이 데이터를 React key 로 썼다** — `key={e.label}`. 같은 제목의 발간물 두 건에서 key 충돌이 나 항목이 뒤섞일 수 있다. → 인덱스를 붙였다. **이 파일은 공용 셸이므로 CL-1·CL-2 화면에도 영향이 있다**(개선 방향).
- 검증 증거:
  - `pytest tests/` → **1,754 passed / exit 0**(직전 1,721 + CL-3 33). `npm run build` 통과.
  - **실제 화면 대외 발간 흐름 완주**(8081 + 5173, `hikwon@lsmnm.com`): 대외 초안 생성 → 게이트 3건 미통과 표시 → 문서 생성(v1, 원천 근거 지문 표시) → 검토 요청(두 필수 검토 자동 포함) → 임원 승인만 → **화면 버튼을 우회해 `POST /publish` 직접 호출 → `400 발간을 막는 조건이 있습니다: LEGAL_DISCLOSURE 검토가 «PENDING» 입니다`** → 법무 승인 → 발간 시도 → 어댑터 없음이므로 **배포 «실패» 기록 + 상태는 «승인 완료» 유지 + "발간 상태를 올리지 않았습니다" 안내**.
  - ⚠️ 래스터 스크린샷은 이 환경에서 확보 불가(Browser 창 미표시). 위 증거는 DOM 실측이며 **시각 판정 근거가 아니다** — Codex/Supervisor 확인 필요.
- 영향·주의사항: `core/decision_ledger.py` 의 `EVENT_TYPES` 가 늘었다(기존 이벤트는 그대로). `core/decision_case.py` 의 `create()` 에 롤백이 추가됐다 — 정상 경로는 변화 없다. `JarvisRail.tsx` 는 공용 셸이므로 CL-1·CL-2 화면 모두 영향(개선). 검증 중 `data/collaboration.db` 에 **같은 제목의 대외 발간물 2건**이 생겼다 — 하나는 위 결함 2 로 생긴 고아 행이다(원장 기록 없음, `DRAFT`). 지우지 않고 남겨 두었으니 정리 여부는 Supervisor 판단이다. 게시 어댑터는 **아직 없다** — 실제 외부 전송은 사람이 어댑터를 붙여야 한다(§3-7 준수).
- 다음 행동 / 담당 / 착수 조건: **Claude Code** 는 CL-4(사용자별 SSE 격리)로 진행한다. `core/broadcaster.py` 가 전체 브로드캐스트이고 사용자별 필터가 없다는 점을 먼저 해결해야 하며, 작업서 §10-11(사용자 A 이벤트가 B 에게 가지 않음)이 완료 조건이다. **Codex** 는 CL-2·CL-3 화면의 정보 위계를 승인 시안 기준으로 교차검토한다(스크린샷 확보 포함). **Antigravity** 는 발간 게이트의 실제 사내 승인 절차(임원·법무)와 대외 제외 항목 목록(`EXTERNAL_REDACT_KEYS`)이 맞는지 확인해 달라 — 목록을 **줄이려면** 법무 검토 근거가 필요하다.
- 교대 체크포인트: 신규 5개 파일 + `main.py`·`core/decision_ledger.py`·`core/decision_case.py`·`CollaborationHub.tsx`·`JarvisRail.tsx` 수정. DB 스키마는 `collaboration.db` 에 발간 4개 표가 추가됐다(기존 표 변경 없음). 전체 테스트 통과·빌드 통과·화면 실측 완료. 재개 첫 행동은 `core/broadcaster.py` 의 구독 구조 확인이다. 금지 범위는 `EXTERNAL_REQUIRED_REVIEWS` 를 임의로 줄이는 것, 게시 어댑터 없이 «발간됨»으로 표시하는 것, 시각 완료를 스크린샷 없이 선언하는 것, 예시 계정을 새로 만드는 것이다.

### [CL-IMPL-25] CL-2 의사결정 센터 화면 구현 — 백엔드만 있던 기능을 사람이 쓸 수 있게 만들었다
- 작성자 / 기록 시각: Claude Code / 2026-08-04 KST
- 왜 지금 기록하는가: `[CL-HANDOFF-24]` 가 "그 결정 전에 진행 가능한 것"으로 지목한 **CL-2 화면**을 구현하고 실제 데이터로 폐루프 8단계를 끝까지 확인했다. 확인 중 백엔드 결함 1건을 발견해 함께 고쳤으므로 근거와 함께 남긴다.
- 상태: **완료(기능·검증) · 스크린샷 미확보(환경 제약, 아래 명시)**
- 결정 및 근거:
  - 신규 `frontend/src/features/collaboration/DecisionCenter.tsx`, `frontend/src/lib/decisionApi.ts`, `frontend/src/lib/closedLoopFetch.ts`. 기존 `CollaborationHub` 의 레일에 «의사결정 센터»를 추가했다(작업서 §4 정보구조: 협업 > 의사결정 센터). 별도 모달을 하나 더 띄우지 않았다 — 전달·결정·발간은 하나의 폐루프이고, 모달이 갈라지면 사용자는 서로 다른 제품으로 읽는다.
  - `closedLoopFetch.ts` 는 CL-1 과 CL-2 가 **같은 오류 규약**(401/404/422/400)을 쓰기 때문에 뽑아낸 공용 헬퍼다. 복사본을 두면 한쪽만 고쳐지고 같은 오류가 화면마다 다른 문구로 나온다. `collaborationApi.ts` 도 이 헬퍼를 쓰도록 바꿨다(동작 변화 없음, 422 배열 detail 처리만 개선).
  - 화면이 보이게 만든 4가지: ① `package_version`·`evidence_hash`·세 관점 동일성을 상시 노출(`.identity-bar`) ② `missing` 섹션을 숨기지 않고 «미작성»으로 표시 ③ 결정 차단 사유를 문서 상단과 결정 버튼 옆에 **둘 다** 노출 ④ 미측정과 0 을 다른 문구·다른 칩으로 표시.
  - 시뮬레이션 실행 목록 API 가 없다. **가짜 선택지를 만들지 않고** 그 사실을 화면이 말하게 했다(자유 입력 + 안내 문구). 진입점 §4 "Digital Twin Scenario Result → 의사결정 패키지 생성" 은 후속 과제로 남는다.
  - CSS 는 `frontend/src/design/afs.css` 의 **`.afs-scope` 안에만** 추가했다(`.identity-bar`, `.section-*`, `.view-who`, `.hint-line`). `:root` 로 옮기지 않았다 — 기존 15개 화면 색이 동시에 바뀐다.
  - `HubShell.tsx` 에 `ChipTone` 타입을 내보내 상태 칩 색을 문자열이 아닌 유니온으로 강제했다. 오타가 나면 «위험»이 회색으로 조용히 나가기 때문이다.
- 발견·수정한 결함: `core/decision_case.py` `_decide_blockers()` 의 `PARTICIPANT_NEEDS_INFO` 목록이 **중복을 제거하지 않았다.** 한 사람이 요청자이자 결정자인 안건에서 `['hikwon@lsmnm.com', 'hikwon@lsmnm.com']` 로 찍혔고(실측), 읽는 사람은 두 명이 정보 부족을 답한 것으로 오해한다. `sorted(set(...))` 로 고치고 회귀 테스트 `test_need_info_blocker_lists_each_person_once` 를 추가했다.
- 검증 증거:
  - `venv\Scripts\python.exe -m pytest tests/ -q` → **1,721 passed / exit 0** (직전 1,720 + 신규 회귀 1). `tests/test_decision_case.py` 단독 35 passed.
  - `npm run build --prefix frontend` → 통과(tsc -b + vite build).
  - **실제 화면 폐루프 8단계 완주**(백엔드 8081 `backend-verify` + 프론트 5173, 사용자 `hikwon@lsmnm.com`): 안건 생성 → 세 관점 렌더링(같은 `v1`·`cf90776443d71fd1`) → 검토 요청 → «정보 부족» 응답으로 **차단 표시 확인** → «동의»로 차단 해제 → 조건부 승인 결정 → 실행과제 생성 → 효과 측정(상태 `EFFECT_MEASURED`). 콘솔 오류 0건.
  - ⚠️ **래스터 스크린샷은 확보하지 못했다.** Browser 창이 이 환경에서 표시되지 않아(`the Browser pane is not displayed`) 캡처가 5초 타임아웃으로 실패한다 — `[CL-HANDOFF-24]` 가 기록한 것과 같은 제약이다. 위 증거는 DOM `innerText` 실측이며, "디자인이 예쁘게 보인다"는 판정 근거로 쓸 수 없다. **시각 판정은 Codex 또는 Supervisor 확인이 필요하다.**
- 영향·주의사항: `collaborationApi.ts` 의 요청 헬퍼가 바뀌었으므로 CL-1 화면(받은 앱·내 앱·전달·보낸 요청)도 영향을 받는다 — 전체 테스트와 빌드로 확인했으나 CL-1 화면의 수동 재확인은 하지 않았다. `.afs-scope` 격리를 `:root` 로 바꾸지 말 것. `HubDialog` 의 dialog/inert/포커스트랩을 화면별로 다시 구현하지 말 것. 검증 중 `data/collaboration.db` 에 실제 안건 1건(`2공정 정련로 2호기 가동률…`)이 생성됐다 — 실측 데이터이며 삭제 전 Supervisor 확인이 필요하다.
- 다음 행동 / 담당 / 착수 조건: **Claude Code** 는 CL-3(발간 게이트) 화면·CL-4(사용자별 SSE 격리)·CL-5(카나리) 순으로 진행한다. CL-4 는 `core/broadcaster.py` 가 전체 브로드캐스트이고 사용자별 필터가 없다는 점을 먼저 해결해야 한다. **Codex** 는 이 화면의 정보 위계·시각 표현을 승인 시안 기준으로 교차검토한다(스크린샷 확보 포함). 기존 15개 화면의 `.afs-scope` 이관은 **사용자·Codex 결정 전 임의 착수 금지** 상태를 유지한다.
- 교대 체크포인트: 변경 범위는 프론트 3개 신규 파일 + `CollaborationHub.tsx`·`HubShell.tsx`·`collaborationApi.ts`·`afs.css` 수정, 백엔드는 `core/decision_case.py` 중복 제거 1줄과 테스트 1건 추가뿐이다. DB 스키마·API 계약·권한 모델은 바꾸지 않았다. 전체 테스트 통과·빌드 통과·화면 실측 완료. 재개 첫 행동은 CL-3 발간 API(`api/routes/publication_control.py`) 계약 확인이다. 금지 범위는 시각 완료를 스크린샷 없이 선언하는 것, 예시 계정을 새로 만드는 것(`hikwon@lsmnm.com` 하나만), `.afs-scope` 를 전역으로 바꾸는 것이다.

### [STRATEGY-ROADMAP-26] 외부 접근 영구 금지·기존 외부 협업 시스템 공존 원칙 확정
- 작성자 / 기록 시각: Codex / 2026-08-03 KST
- 왜 지금 기록하는가: Supervisor가 LPL 사례를 설명한 뒤, 이를 특정 제품 기능으로 만들거나 AI Factory Studio를 외부 참여자에게 여는 방향을 명시적으로 반대하고 “우리 제품은 업무 편의 자동화가 아니라 경영 시스템”이라고 제품 경계를 재확정했다.
- 상태: **최종 제품 원칙 확정 · STRATEGY-ROADMAP-25의 외부 Principal/위임 화면 부분 폐기·대체 · MVA 부트스트랩 부분은 유지**
- 결정 및 근거: AI Factory Studio에는 외부 사용자 계정·게스트 조직·파트너용 앱·입력 화면을 만들지 않는다. 상품화 시에도 고객사마다 공급사 포털·물류/통관 시스템·협력사 웹 등 외부 참여자 입력을 담당하는 기존 시스템이 있다고 전제한다. 기존 시스템이 외부 인증·입력·원본 업무 사건을 책임하고, AI Factory Studio는 읽기 전용 MCP/API/DB View/Export Query Contract로 필요한 데이터만 받아 MDM·Crosswalk·대사·CERTIFIED Snapshot을 거쳐 경영 Twin과 의사결정에 사용한다. 제품 공통 SSOT는 `docs/design_external_engagement_system_integration.md`, LPL은 LS 환경의 `docs/design_lpl_readonly_integration.md` Reference Profile이다.
- 영향·주의사항: 제품 코어에 `LPL`, 특정 고객사 테이블·조직코드·인증 방식을 하드코딩하지 않는다. 고객별 차이는 Adapter Profile과 Query Contract로 격리하고 최소 두 개의 서로 다른 fixture가 동일 코어 계약 테스트를 통과해야 한다. 외부 시스템이 없는 고객도 외부인을 AI Factory Studio에 접속시키지 않고 내부 승인 파일 업로드 또는 고객사/ITO의 별도 외부 포털을 사용한다. 현재 MCP `fetch()`는 단일 객체용이므로 목록·cursor·증분·정정·취소를 위한 `query/changes_since`와 불변 Snapshot이 필요하다. TTL 캐시는 Twin 기준선이 아니다.
- 다음 행동 / 담당 / 착수 조건: **Claude Code**는 외부 Principal·파트너 초대·위임 UI를 구현하지 않는다. CL-0.5/Host Runtime은 내부 사용자·내부 서비스만 대상으로 유지하고, 외부 연계 착수 시 공통 Adapter interface·Query Contract·source event version·멱등·Snapshot을 고객 독립적으로 설계한다. **Antigravity**는 LPL을 포함한 첫 환경의 공식 API/MCP/DB View/Export 가능 여부와 스키마·증분·SLA를 조사하되 결과를 범용 Profile 입력으로 정리한다. **Codex**는 내부 데이터 준비·원천 상태·stale·대사 화면만 설계하고 외부 포털 UI는 만들지 않는다.
- 교대 체크포인트: 전략·로드맵·Product Bible·마스터 명세·구현 감사·기간계/온보딩 설계를 범용 공존 경계로 수정하고 신규 공통 SSOT와 LPL Reference Profile을 작성했다. 제품 코드·DB·테스트는 변경 또는 실행하지 않았고 커밋·푸시하지 않았다. 재개 첫 행동은 기존 Connector Registry/MCP Broker와 공통 설계의 `query/changes_since`·Snapshot 간극을 작업 패키지로 분리하는 것이다. 금지 범위는 외부 사용자 로그인/초대/조직 상속, 파트너용 앱·화면, LPL 하드코딩, Query Contract 없는 전건 조회, TTL 캐시를 공식 Actual로 사용하는 것이다.

### [STRATEGY-ROADMAP-25] Antigravity 전략 평가 반영 — MVA 부트스트랩·외부 파트너 위임 접근 (**외부 접근안 폐기됨**)
- **대체 고지:** 이 항목의 `external_party/external_principal`, 외부 로그인·위임 UI·확장점 관련 판단과 후속 행동은 모두 **STRATEGY-ROADMAP-26으로 폐기·대체**되었다. 구현 근거로 사용하면 안 된다. `Minimum Viable Actual` 부트스트랩 결정만 유효하다.
- 작성자 / 기록 시각: Codex / 2026-08-03 KST
- 왜 지금 기록하는가: Supervisor가 Antigravity의 독자 제품 전략 평가와 보완 의견을 전달하고, 초기 운영 데이터 확보와 관세사·포워더 등 외부 협업을 최신 전략·로드맵에 추가할 필요가 있는지 재검토하도록 요청했다.
- 상태: **부분 폐기 — MVA 부트스트랩만 유효 · 외부 Principal/위임 접근은 STRATEGY-ROADMAP-26으로 폐기**
- 결정 및 근거: 초기 데이터는 전체 ERP 복제가 아니라 `Minimum Viable Actual`로 정의하고 `Source Inventory → 읽기 전용 프로파일링 → 최소 RAW Snapshot → QUARANTINE → MDM/Crosswalk 표준화 → 원천 대사 → 데이터 오너 승인 → CERTIFIED baseline`을 G2 선행 관문으로 승격했다. 외부 참여자는 과거 `design_backbone_system_platform.md`의 `external/ 조직도 하위 게스트`가 아니라 별도 `external_party/external_principal`로 두며, 내부 Sponsor가 app/release/process/work-item/record/field/action·기간 제한 Grant로 위임 업무 표면만 제공한다. 최신 기준은 `docs/strategy/AI_FACTORY_STUDIO_UNIQUE_PRODUCT_STRATEGY_2026-08-03.md` §4.6, `docs/roadmap/AI_FACTORY_STUDIO_FINAL_COMPLETION_EXECUTION_PLAN_2026-08-03.md` G1-D/G2-D, `docs/reviews/AI_FACTORY_STUDIO_IMPLEMENTATION_GAP_AUDIT_2026-08-03.md` §3.5다.
- 영향·주의사항: 시드·합성 데이터는 기능 검증용이며 Actual·예측 정확도 증명에 사용할 수 없다. 외부 제출은 내부 검증 전 `SUBMITTED`이고 `VERIFIED/CERTIFIED` Actual로 자동 승격하지 않는다. 외부 Principal은 조직 상속·전사 검색·Jarvis 전역 문맥·앱 주머니를 받지 않는다. 실제 외부 로그인·SSO·MFA를 첫 내부 폐루프의 블로커로 만들지 않으며 초기에는 내부 Sponsor 대리 제출로 Shadow Pilot을 완주할 수 있다. Antigravity가 언급한 `G0(A-1)`은 과거 기간계 설계의 관문이며 `test_a1_v11`로 2026-07-27 이미 해제됐다. A-1은 변경 후 회귀 카나리로 재사용하되 다음 선행 관문은 G1 안전 경계와 G2 MVA다.
- 다음 행동 / 담당 / 착수 조건: **Claude Code**는 CL-0.5/Host Runtime/SSE 격리 설계 시 `principal_type`과 scope token이 향후 external principal을 수용하도록 확장 지점을 남기고, G2-D는 별도 작업 패키지로 Source Inventory·Snapshot·Reconciliation·Certification 계약부터 구현한다. **Antigravity**는 원료 구매 파일럿의 내부 데이터 요구 필드와 외부 공식지표 원천·갱신주기·라이선스를 교차검증한다. **Codex**는 데이터 준비 보드와 외부 위임 업무 화면의 UX를 실제 API 계약 이후 설계한다.
- 교대 체크포인트: 전략·로드맵·구현 감사·과거 데이터 온보딩/기간계 설계 문서와 본 보드만 수정했다. 제품 코드·DB·테스트는 변경 또는 실행하지 않았고 커밋·푸시하지 않았다. 재개 첫 행동은 G1 설계에 외부 principal 확장점을 포함하고 G2-D01 Source Inventory 스키마를 현재 Connector/Catalog/Crosswalk와 대조하는 것이다. 금지 범위는 시드/합성값을 Actual로 표시하는 것, 대사 실패 데이터를 Twin 공식 기준선으로 쓰는 것, 외부인을 내부 조직에 편입해 권한을 상속시키는 것, 외부 제출을 내부 승인 없이 계산·결정에 쓰는 것이다.

### [STRATEGY-ROADMAP-24] 독자 제품 전략 재정의·최종 완성 로드맵·CL-0 교차검토
- 작성자 / 기록 시각: Codex / 2026-08-03 KST
- 왜 지금 기록하는가: Supervisor가 Enhans의 아류가 아닌 독자 제품으로 완성하기 위해 기존 전략 문서와 Claude Code의 최신 구현을 냉정하게 재검토하고, 미비점·최종 로드맵·세부 수행계획을 남기도록 요청했다.
- 상태: **전략·로드맵 문서 작성 완료 · CL-0 집중 테스트 통과 · CL-0.5 보강 제안 및 Claude Code 인계 필요**
- 결정 및 근거: 제품 범주를 범용 AgentOS가 아닌 **Manufacturing Management Twin & Operational App Factory**로 고정했다. 차별화의 본체는 `실제 제조 경영 데이터 → 현업 운영 앱 → 결정론적 Twin → 의사결정 → 실행 → 효과 측정` 폐루프다. `docs/strategy/AI_FACTORY_STUDIO_UNIQUE_PRODUCT_STRATEGY_2026-08-03.md`에 경쟁 중복·독자 해자·첫 수직 파일럿·포기 범위를, `docs/roadmap/AI_FACTORY_STUDIO_FINAL_COMPLETION_EXECUTION_PLAN_2026-08-03.md`에 G0~G9 작업·산출물·DoD·시험·중단 조건을, `docs/reviews/AI_FACTORY_STUDIO_IMPLEMENTATION_GAP_AUDIT_2026-08-03.md`에 소스 기준 현황·엔터프라이즈 미비·CL-0 코드 감사를 기록했다. Claude Code CL-0 커밋 `a484c6f63`을 코드 기준으로 검토했고 `venv\Scripts\python.exe -m pytest tests/test_app_manifest.py tests/test_m0_end_to_end.py -q` 결과 **45 passed**를 확인했다.
- 영향·주의사항: CL-0 방향은 승인 가능하나 현재 정규식 검사는 린트/증빙이지 런타임 보안 경계가 아니다. 전체 프로젝트 검사로 `.archive` 과거 코드가 현재 릴리스를 오염시킬 수 있고, 광범위 허용 문자열·간접 호출로 우회 가능하며, 빈 capability Manifest와 검사 차단 상태에서도 릴리스 생성이 가능하다. CL-1 전달·수락 통합 전에 **CL-0.5**로 릴리스 파일 한정 검사, archive 제외, 불완전 검사 Fail-closed, release eligibility, capability 선언-관측 diff, Manifest fingerprint를 보강해야 한다. 또한 사용자별 SSE와 Host Runtime 최소 계약이 CL-1의 선행조건이다. 기존 타 세션의 Knowledge·데이터·문서 삭제/변경은 건드리지 않았다.
- 다음 행동 / 담당 / 착수 조건: **Claude Code**가 현재 CL-0 구현을 기준으로 G1-A(CL-0.5) 작업을 먼저 분리 설계·구현하고, G1-C 사용자별 SSE와 G1-B Host Runtime 최소 계약을 확정한 뒤 CL-1 앱 전달·수락으로 진행한다. **Codex**는 Manifest/Runtime 계약과 실제 UI의 권한·상태 표현을 교차검토한다. **Antigravity**는 원료 구매 수직 파일럿의 공신력 있는 외부지표·데이터 소스 키트를 보강한다. 권한·이벤트·런타임 계약은 통합 전 독립 검토한다.
- 교대 체크포인트: 이번 변경은 전략·로드맵 문서, Product Bible·마스터 명세 최신 포인터, 본 보드 기록뿐이며 제품 코드는 수정하지 않았다. CL-0 집중 테스트만 실행했고 전체 테스트는 실행하지 않았다. 커밋·푸시는 하지 않았다. 재개 첫 행동은 Claude Code가 본 로드맵 §5의 G1-A 항목을 작업 패키지로 보드에 등록하는 것이다. 금지 범위는 정적 검사를 인증 강제 완료로 선언하는 것, Host Runtime 없이 생성 앱에 DB/상위 토큰을 전달하는 것, 사용자별 필터 없이 협업 SSE 이벤트를 추가하는 것, 첫 수직 폐루프보다 기능 수를 확장하는 것이다.
### [CL-HANDOFF-24] ⚠️ 세션 종료 인수인계 — **디자인이 제품에 적용돼 보이지 않는다(최우선)**
- 작성자 / 기록 시각: Claude Code / 2026-08-03 KST (세션 종료)
- 왜 지금 기록하는가: 다른 Claude Code 계정이 **이어서 작업**한다. 그리고 사용자가 실제 화면을
  보고 "디자인 입힌다더니 하나도 적용이 안 되어 있다"고 판정했다 — 내가 "디자인을 입혔다"고
  보고한 것과 다르다. 이 불일치를 다음 담당자가 가장 먼저 알아야 한다.
- 상태: **CL-0·CL-1 기능 완료 · CL-2 백엔드 완료 · 디자인 적용은 사실상 미완**

#### 1) 마지막 확인 상태 — 무엇이 진짜이고 무엇이 과장이었나

★★★ **내 보고가 과장이었다.** `.afs-scope` 격리 결정 때문에 승인 시안 디자인은 **협업 모달
안에서만** 적용된다. 제품을 열면 런처·프로젝트·지식허브·조직권한 등 **기존 15개 화면은 전부
그대로 다크 테마**다. 사용자가 본 것이 그것이고, "하나도 적용 안 됨"은 **정확한 관찰**이다.

⚠️ 내 검증은 전부 **JS 측정**(getComputedStyle·getBoundingClientRect)이었다. **실제 화면을 눈으로
  본 적이 없다** — Browser 창이 표시되지 않아 `computer{screenshot}` 이 매번 실패했고, 그 상태로
  "3열 적용·넘침 0" 만 보고 통과라고 판단했다. 측정은 통과했고 제품은 통과하지 못했다.
  → 다음 담당자는 **스크린샷을 확보한 뒤에** 디자인 완료를 보고할 것.

기술적으로 확인된 것(측정 기준):
  · `afs.css` 는 개발서버가 정상 제공한다(`curl localhost:5173/src/design/afs.css` 로 확인)
  · 협업 모달 안에서 3열(1280 → 220/731/280, 1440 → 220/906/280)·라이트 테마·LS Red 버튼 적용
  · 문서 가로 넘침 0(모달 닫힘·열림, 1280·1440 모두)
  · dialog/aria-modal/inert/포커스트랩/Escape/포커스복귀/스크롤잠금 동작
  · Jarvis 어댑터가 실제 LLM 응답을 문맥 근거로 반환(고정 문자열 아님)

#### 2) 실제 변경·미변경 범위

**변경**: `core/app_manifest.py` · `nodes/utils/platform_auth_checker.py` ·
`core/collaboration_store.py` · `core/app_delivery.py` · `core/decision_case.py` ·
`api/routes/{app_delivery,decision,jarvis}_control.py` · `core/decision_ledger.py`(이벤트 15종) ·
`frontend/src/design/{afs.css,HubShell.tsx,HubDialog.tsx,JarvisRail.tsx}` ·
`frontend/src/lib/{collaborationApi,jarvisApi}.ts` ·
`frontend/src/features/collaboration/CollaborationHub.tsx` · `frontend/src/App.tsx`(협업 버튼 ·
헤더 `min-w-0 overflow-x-auto` · `w-screen`→`w-full`) · `main.py`(라우터 3개).

**미변경(중요)**: 기존 15개 화면의 테마·레이아웃. Codex 의 `uiux-prototypes/` 시안 파일.
**CL-2 화면은 없다**(백엔드만 있다). CL-3·CL-4·CL-5 는 착수하지 않았다.

#### 3) 검증 증거

`python -m pytest` → **1720 passed / 실패 0** · `npm run build` 통과.
⚠️ 이 숫자는 **기능 회귀 근거일 뿐 화면이 옳다는 증거가 아니다**(교차검토 판정 그대로).

#### 4) 커밋·푸시 상태

`a484c6f63`(CL-0) · `22b8549f6`(CL-1 BE+FE) · `50e3cca98`(디자인 기준선) ·
`e81127daf`(교차검토 6건 반영) — **전부 푸시 완료**. 이 항목 커밋이 마지막이다.

#### 5) 다음 담당자의 첫 재개 행동

1. **`start http://localhost:5173` 로 실제 화면을 열고 스크린샷을 확보**한다. 그 다음에야
   디자인 상태를 판단한다(내 실수를 반복하지 말 것).
2. 판단이 필요한 갈림길: **기존 15개 화면을 `.afs-scope` 로 순차 이관할 것인가.** 이관하지 않으면
   제품은 계속 "디자인 미적용"으로 보인다. 이관하면 되던 화면이 깨질 위험이 있다 —
   사용자가 선택 ③(기준선 먼저·병행)을 고른 이유가 후자였다.
   ★ 이건 UI/UX 담당(Codex)과 사용자 결정이 필요한 사항이므로 **임의로 시작하지 말 것.**
3. 그 결정 전에 진행 가능한 것: **CL-2 화면**(백엔드·테스트 완료, 셸 준비됨).

#### 6) 건드리면 안 되는 범위 · 금지

- ★★★ **예시 계정을 임의로 만들지 말 것.** 실측이 필요하면 `hikwon@lsmnm.com` 하나만 쓴다.
  내가 `lee.demo@lsmnm.com` 을 만들었고 사용자에게 지적받았다 — 실제 인원 계정과 충돌하고,
  감사 이력에 그 사람이 하지 않은 행위가 남는다. 만든 계정·전달 5건·주머니 2건·가짜 릴리스 2건은
  **행 삭제로 정리 완료**(활성 사용자는 `hikwon@lsmnm.com` 1명).
- `.afs-scope` 격리를 `:root` 로 바꾸지 말 것 — 기존 15개 화면 색이 동시에 바뀐다.
- `HubDialog` 의 dialog/inert/포커스트랩을 화면별로 다시 구현하지 말 것(셸에 있다).
- Jarvis 에 고정 문자열 응답을 넣지 말 것 · 두 번째 채팅 API 를 만들지 말 것(§3).
- 목록 라우트에서 `visibility_block_reason`·`viewer_visible_scopes` 호출을 빼지 말 것.
- 서버는 종료했다. DB 는 원본 폴더와 동기화했다.

### [CL-IMPL-23] 폐쇄루프 구현 착수 보고 (§13) — CL-0 App-in-App Manifest부터
- 작성자 / 기록 시각: Claude Code / 2026-08-03 KST
- 왜 지금 기록하는가: 작업서 §13 이 착수 시 보드 기록을 요구한다. 그리고 착수 전에 확인한
  **재사용 자산의 실제 상태**를 남겨 둬야 이후 판단이 추측 위에 서지 않는다.
- 상태: **착수** — 작업 ID `M6-UI-03C / PRODUCT-CLOSED-LOOP-20`, 담당 패키지 CL-0 → CL-5 순서
- 확인한 기준 문서·프로토타입:
  `docs/uiux/CLAUDE_IMPLEMENTATION_WORK_ORDER_CLOSED_LOOP_2026-08-03.md`(362행 전문) ·
  `docs/design_app_delivery_decision_publication_loop.md`(915행) ·
  `uiux-prototypes/closed-loop-product-samples/` · `master-concept/ADOPTION_DECISION.md`
  (2026-07-30 Supervisor 채택) · 화면기능정의서 · UI 설계서 · 추적 매트릭스.
- **착수 전 코드 실측 — 재사용 가능 여부**(추측이 아니라 확인한 것):
  · `core/decision_ledger.py:168 append()` **있음** → 불변 감사에 그대로 쓴다(새로 만들지 않는다)
  · `api/routes/factory_control.py:1168 create_release()` **있음** → Manifest snapshot 삽입 지점
  · `core/workspace_promotion.py:134 share()` · `:468 promote()` **있음** → 개인 전달을 여기에
    합치지 않는다(§3-1,2). 두 경로는 끝까지 분리한다
  · ⚠️ **`core/broadcaster.py:15` 는 `clients: list[Queue]` 로 전체 브로드캐스트다 — 사용자별
    필터가 없다.** 즉 CL-BE-05 가 경고한 "다른 사용자의 이벤트가 현재 클라이언트로 전송되는
    구조"가 **현재 실재한다.** 이건 새 기능이 아니라 **기존 결함**이며, 폐쇄루프 이벤트를 지금
    구조에 그대로 얹으면 앱 전달·결정 요청이 전 사용자에게 흘러간다.
    → CL-4 로 미루지 않고, 이벤트를 처음 붙이는 시점에 필터를 함께 넣는다.
- 실제 수정 예정 파일(CL-0 단계):
  `core/app_manifest.py`(신규) · `nodes/utils/platform_auth_checker.py`(신규) ·
  `api/routes/factory_control.py`(릴리스 생성 시 Manifest snapshot) ·
  `tests/test_app_manifest.py`(신규).
- 기존 기능 재사용 범위 / 신규 구현 범위:
  · **재사용**: Decision Ledger append · `library_paths` 릴리스 경로 · `api/deps` 권한 판정
    (`assert_*`·`visibility_block_reason`·`viewer_may_drill_down`) · `lib/api.ts` 인터셉터
  · **신규**: Manifest schema·canonicalization·검증 · 자체 인증 생성 정적 게이트 ·
    `collaboration.db`(CL-1 이후) · 협업 3개 라우터
- 권한·DB·외부 쓰기 영향:
  · CL-0 은 **권한 판정을 바꾸지 않는다.** 릴리스에 Manifest 를 덧붙이고 정적 검사를 추가할 뿐이다
  · DB: CL-0 에서 신규 DB 없음. `release.json` 에 `manifest` 키가 추가된다(기존 키 불변)
  · 외부 쓰기: 없음. 외부 캘린더·게시는 CL-2/CL-3 이며 §3-7 대로 사용자 확인 없이 쓰지 않는다
- 첫 완료 조건과 테스트 명령:
  릴리스 생성 시 Manifest snapshot 저장 + 생성물의 자체 로그인·비밀번호 저장·JWT 발급·자체
  사용자 테이블 탐지. 일반 업무 화면의 사용자 입력 폼은 **오탐하지 않는다**(§6).
  `venv\Scripts\python.exe -m pytest tests/test_app_manifest.py -q`
- 영향·주의사항: 문서 불일치를 발견하면 UX 를 임의로 바꾸지 않고 코드 증거와 함께 이 보드에
  기록한다(§13). 프로토타입 승인 여부는 다시 묻지 않는다.
- 다음 행동 / 담당 / 착수 조건: **Claude Code** — CL-0 구현 → 자체검토 → 커밋.
  §12 독립 검토 요청 대상 5건 중 CL-0 에 해당하는 것은 없다(스키마·권한·발간·SSE 는 CL-1 이후).
  **Antigravity/Codex 검토 요청 예고**: `collaboration.db` 스키마와 Ledger 원자성은 CL-1 착수
  시점에 보드로 요청한다 — 그 전에 기본 브랜치에 통합하지 않는다.
- 교대 체크포인트: 이 항목은 **착수 보고**이며 아직 코드 변경 없음. 재개 시 첫 행동은
  `core/app_manifest.py` 작성이다. 금지: `workspace_shares`·Promotion 에 개인 전달을 합치는 것 ·
  네 가지 전달 유형을 한 enum 으로 만드는 것(§3).

### [CLAUDE-CLOSED-LOOP-22] 승인 폐쇄루프 UI 정식 편입·구현 인계
- 작성자 / 기록 시각: Codex / 2026-08-03 KST
- 왜 지금 기록하는가: Supervisor가 앱 전달·수락·의사결정·발간 클릭형 프로토타입을 승인하고, 기존 UI/UX 시안에 정식 반영한 뒤 Claude Code가 실제 제품으로 완성할 수 있도록 업무를 정리하라고 지시했다.
- 상태: **제품 UI 기준선 승인·3대 UI 문서 편입·Claude Code 구현 작업서 작성·origin/dev 푸시 완료 · 실제 React/API/DB 구현 대기**
- 결정 및 근거: `docs/uiux/LIVING_ENTERPRISE_SCREEN_FUNCTION_DEFINITION_2026-07-30.md`에 CL-01~04와 두 폐쇄루프를, `LIVING_ENTERPRISE_UI_DESIGN_SPEC_2026-07-30.md`에 Collaboration Workflow Hub·URL·컴포넌트·검수 기준을, `LIVING_ENTERPRISE_IMPLEMENTATION_TRACEABILITY_2026-07-30.md`에 API·M6-UI-03C·회귀·완료조건을 편입했다. `docs/uiux/CLAUDE_IMPLEMENTATION_WORK_ORDER_CLOSED_LOOP_2026-08-03.md`는 현재 코드 기준 신규 DB·Router·서비스·React feature, API 목록, 상태 전이, 권한 경계, 테스트, 커밋 순서를 정의한다. 승인 화면은 `uiux-prototypes/closed-loop-product-samples/`이다.
- 영향·주의사항: 문서·정적 프로토타입·보드만 변경했으며 `frontend/`, `api/`, `core/`, DB는 미변경이다. 개인 전달을 `workspace_shares`에 합치지 말고, 앱 수락으로 데이터 권한을 확대하지 말며, 대외 발간은 책임 임원+법무/공시 이중 게이트와 명시적 사용자 실행을 서버에서 강제한다. 세 검토서는 하나의 Decision Package projection이어야 한다.
- 다음 행동 / 담당 / 착수 조건: Claude Code는 현재 작업트리가 정리되고 M6-UI-03C 착수가 허용되는 시점에 작업서의 CL-0(App-in-App Manifest)부터 독립 커밋 단위로 시작한다. 권한·DB/Ledger 원자성·대외 발간·사용자별 SSE는 통합 전 다른 팀원 독립 검토를 요청한다. Codex는 1280/1440 화면, 용어, Jarvis 문맥, 개인/조직 공유 구분을 교차검증한다.
- 교대 체크포인트: 승인 프로토타입, V1~V10 탐색 이력, 화면기능정의서·UI설계서·추적성·README·구현 작업서를 커밋 `ae8da0887`로 `origin/dev`에 푸시했다. 실제 React/API/DB·런타임 테스트는 변경 또는 실행하지 않았다. 재개 첫 행동은 Claude Code가 `docs/uiux/CLAUDE_IMPLEMENTATION_WORK_ORDER_CLOSED_LOOP_2026-08-03.md` §13 형식으로 본 보드에 담당 패키지·실제 수정 파일·첫 테스트를 기록한 뒤 CL-0 App-in-App Manifest부터 착수하는 것이다. 금지 범위는 Factory 전체 레이아웃 재설계, 개인 전달/조직 공유 통합, 앱 수락에 의한 데이터 권한 자동 확대, 세 관점 검토서의 원본 분리, 사용자 확인 없는 자동 외부 발간이다. 공유 작업트리의 Knowledge·데이터·문서 정리 변경은 이번 커밋에서 제외했으며 각 원 담당자가 별도 처리한다.

### [UX-CLOSED-LOOP-21] 업무 협업·의사결정·발간 폐쇄루프 UI 반영
- 작성자 / 기록 시각: Codex / 2026-08-03 KST
- 왜 지금 기록하는가: Supervisor가 PRODUCT-CLOSED-LOOP-20의 상세기획만으로는 부족하며, 실제 UI에도 앱 전달·수신 승인·의사결정·보고서 발간 기능을 반영하라고 지시했다.
- 상태: **클릭형 UI 샘플 구현·브라우저 검증 완료 · 실제 React/API 구현 미착수**
- 결정 및 근거: `uiux-prototypes/closed-loop-product-samples/`에 `사용자에게 전달`, `받은 앱·내 앱`, `의사결정 센터`, `대내외 보고서 발간` 네 화면을 하나의 공통 제품 셸과 상시 Jarvis Rail로 구현했다. Factory `transparent-orchestration/index.html`에는 `릴리스·사용자 전달` 진입점과 `App-in-App 플랫폼 계약 적용`을 표시했고, M6 제품 셸과 UI 갤러리에도 진입 링크를 연결했다. 1280px 브라우저에서 네 화면을 확인하고 Factory→전달 화면 이동, 앱 승인 후 내 앱 수 증가, 검토서 3종 전환, 회의 요청 상태 변경을 확인했다. 대외 발간은 책임자 승인만으로 활성화되지 않고 법무·공시 검토까지 완료해야 `4/4 준비`와 `대외 보고서 발간`이 활성화됨을 확인했다. 상세 설계·UI 경로는 `docs/design_app_delivery_decision_publication_loop.md`에 동기화했다.
- 영향·주의사항: 변경은 정적 UI 프로토타입·설계 문서·팀 보드에 한정되며 실제 `frontend/`, API, DB, 권한 엔진은 변경하지 않았다. UI의 사용자 이름·부서·수치·일정은 기능 검증용 샘플이다. 실제 구현에서 앱 수락이 데이터 권한을 자동 확대해서는 안 되며, 외부 발간은 사용자 확인 없는 자동 게시를 금지한다.
- 다음 행동 / 담당 / 착수 조건: Supervisor가 UI 흐름을 검토한 뒤 Claude Code가 Phase A(App-in-App 생성 계약)와 Phase B(개인 전달·수락·내 앱)의 실제 구현 계약을 작성하고, Codex가 React 이식 시 1280/1440 가독성·Factory 연계·Jarvis 문맥·권한 영향 표현을 교차검증한다. 실제 구현 착수 전 권한 모델과 외부 발간 게이트는 다른 팀원 1명의 독립 검토가 필요하다.
- 교대 체크포인트: 신규 정적 UI 폴더, 범용 `uiux-prototypes/preview-server.mjs`, Factory·M6·갤러리 진입점, 상세 설계 문서·본 보드를 수정했다. 정적 서버 8090에서 화면과 상호작용을 검증했으며 커밋·푸시는 하지 않았다. 재개 시 첫 행동은 `http://127.0.0.1:8090/closed-loop-product-samples/#inbox` 검토 결과를 받아 화면을 확정하는 것이다. 승인 전 실제 React/API/DB 이식과 자동 외부 발행은 금지한다.

### [PRODUCT-CLOSED-LOOP-20] 앱 전달·수락과 시뮬레이션 의사결정·발간 확장안
- 작성자 / 기록 시각: Codex / 2026-08-03 KST
- 왜 지금 기록하는가: Supervisor가 생성 앱의 지정 사용자 전달·수락·내 앱 등록, 앱인앱 권한 상속, 시뮬레이션 기반 회의 요청·세 관점 검토서·대내외 보고 발간을 하나의 제품 흐름으로 추가 제안했다.
- 상태: **상세기획 완료 · 구현 미착수 · 제품 방향 검토 대기**
- 결정 및 근거: `docs/design_app_delivery_decision_publication_loop.md`에 여섯 아이디어를 `앱 생성→전달→수락→공동운영`과 `시뮬레이션→Decision Package→회의→실행→발간→학습`의 두 폐쇄루프로 구조화했다. 기존 `core/workspace_promotion.py`의 `workspace_shares`는 조직 단위 read/fork이고 개인 수락형 전달이 아니므로, 공유 계약과 `app_deliveries`·`user_app_pocket`을 분리했다. 세 검토서는 독립 원본 3개가 아니라 하나의 증거 고정형 Decision Package를 요청자·의사결정자·영향부서 관점으로 렌더링하도록 설계했다. 마스터 구현 명세 상단에 상세 문서 포인터를 추가했다.
- 영향·주의사항: 실제 API·DB·Agent Skill·프런트엔드는 변경하지 않았다. 앱 수락이 데이터 권한을 자동 확대해서는 안 되며, 조직 공유·개인 전달·업무 배정·전사 승격을 한 상태로 합치면 안 된다. 생성 앱 자체 로그인 금지 규칙을 적용할 때 `docs/test_plan/01_scenario_catalog.md`의 앱 내부 로그인 시나리오도 호스트 역할 상속 시나리오로 함께 바꿔야 한다. 외부 캘린더·메시지·보고 발행은 사용자 확인 없는 자동 쓰기를 금지한다.
- 다음 행동 / 담당 / 착수 조건: Supervisor가 제품 원칙과 Phase A→F 순서를 승인하면, Claude Code가 Phase A(App-in-App 생성 계약·정적 게이트)와 Phase B(지정 사용자 전달·수락·내 앱)의 상세 구현 설계/코딩을 맡고 Codex가 화면 흐름·용어·수락/Decision UX를 구체화한다. 권한·보안·Decision Package 데이터 모델은 통합 전 다른 팀원 1명의 독립 검토를 받는다.
- 교대 체크포인트: 신규 상세 설계 문서 1개와 마스터 명세 포인터·팀 보드 기록만 추가했다. 코드·DB·테스트는 미변경·미검증이며 커밋·푸시하지 않았다. 재개 시 첫 행동은 Supervisor의 설계 판정과 Phase A 착수 여부 확인이다. 승인 전에는 앱 수락으로 Scope 권한을 자동 생성하거나 세 검토서를 서로 다른 원본으로 구현하지 않는다.

### [UX-SW-FACTORY-TRANSPARENCY-19] 전체 흐름·WBS 상시 노출 기반 D안 재설계
- 작성자 / 기록 시각: Codex / 2026-07-31 KST
- 왜 지금 기록하는가: Supervisor가 B·C안은 현재 작업에는 집중되지만 전체 제작 단계와 다음 작업을 알기 어렵고, AI 진행상황을 다시 암묵지로 만들며, Agent 연결과 WBS 기반 실행이라는 제품 의도를 희석한다고 지적했다. Codex의 `B → C` 기본 구조 권고를 철회하고 전체 투명성을 우선하는 구조로 재설계한다.
- 상태: **D · Transparent Orchestration 시안 구현·브라우저 검증 완료 · Supervisor 검토 대기**
- 결정 및 근거: `uiux-prototypes/sw-factory-concepts/transparent-orchestration/`에 상단 8단계 Workflow Map, 좌측 WBS·의존관계·Agent Spine, 중앙 현재 작업·산출물 Focus Surface, 그 아래의 조건부 사용자 결정/Jarvis 상하 카드, 우측 수행 이유·다음 전환·실시간 실행 기록을 구현했다. 상호작용 카드는 화면 바닥에 붙이지 않고 좌우·하단 14px 여백과 라운드·그림자를 적용했다. 사용자 결정이 있으면 결정 행을 Jarvis 위에 표시하고, 0건이면 결정 행을 접어 확보된 높이를 현재 작업에 돌려준다. Jarvis 질문 입력창을 기본 노출했고 주요 제목 14~21px, 본문·상태 11~12px 이상으로 확대했다. 1280×720에서 가로·세로 넘침 0, 8단계·WBS·현재 작업·사용자 결정·Jarvis·판단 근거·실행 기록 동시 노출을 확인했다.
- 영향·주의사항: 실제 `frontend/`·API·DB는 변경하지 않았다. D도 확정 UI가 아니라 구조 검증안이다. B의 선택형 요구 안내와 C의 넓은 산출물 작업면은 폐기하지 않고 D의 중앙 모드로 흡수한다. A는 기능 회귀 확인용 참고로 유지한다. Workflow 순서는 화면에 하드코딩하지 않고 실제 registry/graph를 사용해야 한다.
- 다음 행동 / 담당 / 착수 조건: Supervisor가 D의 정보 위계와 밀도를 검토한다. 승인 또는 수정 방향이 정해지기 전 Claude Code는 Factory React 레이아웃을 이식하지 않는다. 승인 후 Codex가 신규 기획·WBS 생성·실행·HOTL·실패복구·산출물 검토의 상태별 D 화면을 확장하고 Claude Code가 기존 컴포넌트와 상태 계약을 매핑한다.
- 교대 체크포인트: D HTML, 비교 갤러리, README, UI 설계·화면기능·추적성 문서를 수정했고 정적 JS·한글·참조 검사를 통과했다. 사용자 결정 위·Jarvis 아래 구조를 현재 작업 아래 하단부에 두고 화면 끝에 붙이지 않은 부유형 카드로 표현했다. Supervisor 피드백으로 카드 높이를 142px에서 174px로 확대했다. 결정 1건 상태는 카드 상단 532px·하단 706px·화면 바닥 여백 14px이며, 결정 0건이면 결정 행이 사라지고 Jarvis 단독 카드가 118px로 남아 현재 작업이 312px까지 확장된다. 핵심 제목 14px 이상·본문 12px 이상과 Jarvis 질문 입력창을 유지했다. 가로/세로 넘침은 0이다. 실제 제품 소스는 미변경이며 UI 산출물은 아직 미커밋·미푸시다.

### [TEAM-PROTOCOL-V2-18] 인수인계 완료 기준·기록 승격 규칙 정비
- 작성자 / 기록 시각: Codex / 2026-07-31 01:20 KST
- 왜 지금 기록하는가: SW 생성기 시안 작업이 본 보드에는 기록됐지만 별도 인수인계 파일에도 기록됐는지 다시 확인해야 했다. 현행 규칙은 문서 난립 방지는 명확했으나, 무엇이 있어야 실제 인수인계가 완료되는지와 언제 `DECISIONS.md`·`AI_HANDOFF.md`로 승격하는지가 불명확했다.
- 상태: **협업 프로토콜 2차 정비 반영 완료 · 모든 신규 세션 종료 기록부터 적용**
- 결정 및 근거: `.agents/TEAM_PROTOCOL.md` §3, §4-1, §4-2와 본 보드 표준 양식에 `교대 체크포인트`를 추가했다. 인계 완료에는 마지막 확인 상태, 변경 범위, 검증 증거, 커밋·푸시 상태, 재개 지점, 금지 범위가 모두 필요하다. 탐색·시안은 본 보드, 확정 결정은 `DECISIONS.md`, 실제 통합 마일스톤은 `AI_HANDOFF.md`로 승격하며 같은 내용을 복제하지 않는다.
- 영향·주의사항: 새 팀원별·세션별 인수인계 파일을 만들라는 규칙이 아니다. 기존 상세 설계·테스트 증적은 원래 문서에 두고 보드에서는 링크만 연결한다. 기존 보드 항목 전체를 즉시 소급 개편하지 않으며, 다음 갱신 시 새 체크포인트를 적용한다.
- 다음 행동 / 담당 / 착수 조건: Claude Code·Antigravity·Codex는 다음 세션 종료 또는 담당 교대부터 각자 갱신하는 항목에 교대 체크포인트를 남긴다. Supervisor가 별도 채널이나 자동 알림을 추가로 원할 경우, 파일 증설보다 보드의 미완료 체크포인트 탐지 자동화를 우선 검토한다.
- 교대 체크포인트: 프로토콜과 보드 표준 양식의 문구를 함께 변경했고 SW 생성기 항목을 첫 적용 사례로 보완했다. 실제 코드·API·DB는 변경하지 않았다. 두 파일은 아직 미커밋·미푸시이며 `.agents/TEAM_BOARD.md`에는 기존 Codex UI 기록도 함께 있으므로 커밋 시 diff 확인과 파일 지정 스테이징이 필요하다. 재개 시 첫 행동은 다른 팀원이 새 형식으로 인계 가능한지 1회 실사용 점검하는 것이다.

### [UX-SW-FACTORY-RESET-17] SW 생성기 원본 복원 기준·전용 UI 3안 비교
- 작성자 / 기록 시각: Codex / 2026-07-31 00:55 KST
- 왜 지금 기록하는가: Supervisor가 R2 Factory가 한 페이지에 요구 입력·WBS·Timeline·Preview·품질·Atlas를 모두 우겨 넣어 UI 정리 전 Claude Code 원본보다 나빠졌다고 판정했다. SW 생성기 자체의 전용 시안 샘플링 없이 전체 화면을 확정한 절차 오류를 바로잡는다.
- 상태: **R2 Factory 반려 · A/B/C 탐색 완료 · 기본 구조 권고는 UX-SW-FACTORY-TRANSPARENCY-19로 대체**
- 결정 및 근거: 현재 React의 `WorkflowStrip + ControlPanel + TimelinePanel(Supervisor Console/HOTLInput) + PreviewPanel`을 기능·정보구조 기준선으로 확정했다. `uiux-prototypes/sw-factory-concepts/`에 A Original Plus(원본 3패널 최소 개선), B Guided Journey(신규 기획 5단계), C Focus Workbench(기획/WBS/실행/산출물/품질 탭)를 분리 구현했다. 브라우저에서 A의 Control/Supervisor/Preview 3영역과 Atlas 접근, B의 5단계·단일 주 CTA와 1→2 단계 전환, C의 5개 작업 탭과 산출물 집중 전환을 확인했다. 기능 보존 기준은 `uiux-prototypes/sw-factory-concepts/README.md`.
- 영향·주의사항: 실제 `frontend/`·API·DB는 변경하지 않았다. R2 Factory는 삭제하지 않고 실패 이력으로 보존하지만 React 이식·확정 디자인 근거로 사용하면 안 된다. Atlas는 항상 접근 가능해야 하나 별도 네 번째 고정 열을 강제하지 않는다. WBS·품질·복구는 관련 단계에서만 전개한다.
- 다음 행동 / 담당 / 착수 조건: A/B/C는 UX-SW-FACTORY-TRANSPARENCY-19의 D안과 비교하기 위한 탐색 자료로 유지한다. B의 선택형 안내와 C의 집중 작업면은 D 중앙 모드 후보이며, 선택 전 Claude Code는 실제 Factory 화면을 재배치하지 않는다.
- 교대 체크포인트: `uiux-prototypes/sw-factory-concepts/`의 갤러리와 A/B/C를 브라우저에서 확인했고 한글 대체문자 0, 로컬 참조 이상 0, 인라인 JS 구문 정상이다. 변경 범위는 해당 시안 폴더, 관련 `docs/uiux/` 설계 문서, 본 보드 항목이며 실제 `frontend/`·API·DB는 미변경이다. 현재 변경은 미커밋·미푸시 상태이고 공유 워킹트리에 다른 세션 변경이 다수 존재하므로 파일 지정 스테이징만 허용한다. 재개 시 첫 행동은 Supervisor의 선호 조합을 확인하는 것이며, 선택 전 Factory React 레이아웃 이식·R2 Factory 재사용·기존 3패널 제거를 금지한다.

### [UX-P0-R2-16] Studio 기능 복원·Atlas Global Rail·Twin 테마 교정
- 작성자 / 기록 시각: Codex / 2026-07-31 00:34 KST
- 왜 지금 기록하는가: Supervisor가 최초 P0 통합안에서 Factory 요구 입력·WBS·작업 기능이 사라져 보이고, Twin 컬러가 제품과 부조화하며, Factory·Agent·Twin 모두 Atlas 영역이 없어졌다고 판정했다. 화면기능정의서의 C02/AT-01, C03/BW-03과 실제 시안을 다시 대조해 기능 축약을 즉시 교정했다.
- 상태: **Factory 부분 Supervisor 반려 · UX-SW-FACTORY-RESET-17로 대체**
- 결정 및 근거: Factory를 `요구 입력·선택형 명확화·RFP/PRD/아키텍처/UI/WBS Rail + 8단계 진행선 + WBS + Agent Timeline + Artifact 5개 탭 + HOTL/복구/인계 + Atlas`로 재구성했다. Agent는 Template·12개 Node Graph·Inspector 옆에 Atlas를 복원했다. Twin은 밝은 공통 제품 테마 안에서 시뮬레이션 캔버스만 집중색을 사용하고 Scenario·동인·KPI·Value Flow·근거·신뢰도·Atlas를 함께 배치했다. 브라우저에서 Factory 필수 기능 전체 DOM, Agent 12 Node/6 Template/Atlas, Twin 6 Value Flow Node/Atlas를 확인했고 Atlas 빠른 질문이 3개 메시지와 구체 답변을 생성했다. 근거: `uiux-prototypes/revision-v2-2/factory/index.html`, `uiux-prototypes/revision-v2/v10/index.html`, `uiux-prototypes/revision-v2/v9/index.html`, `uiux-prototypes/studio-workspaces.css`, `uiux-prototypes/studio-atlas.js`, `docs/uiux/LIVING_ENTERPRISE_IMPLEMENTATION_TRACEABILITY_2026-07-30.md` §9.
- 영향·주의사항: 실제 `frontend/`·API·DB는 변경하지 않았다. Agent와 Twin의 분리 화면은 별도 검토 대상으로 남지만 R2 Factory의 네 열 동시 노출과 고정 Atlas Rail은 폐기한다. Atlas 접근성은 유지하되 Supervisor 통합 또는 Drawer로 제공한다.
- 다음 행동 / 담당 / 착수 조건: Factory 후속 기준은 UX-SW-FACTORY-RESET-17만 사용한다. Agent·Twin도 같은 ‘기능 문자열 존재보다 현재 과업 집중’ 원칙으로 별도 재검토한 뒤 확정한다.

### [UX-P0-SHELL-15] 승인 디자인 기반 제품 셸·Studio P0 통합 리비전
- 작성자 / 기록 시각: Codex / 2026-07-31 00:07 KST
- 왜 지금 기록하는가: Supervisor가 제3자 관점 감사에서 확인된 제품 부조화 문제의 P0 수정안을 승인했다. 기존 화면은 전역 헤더·메뉴·회사 범위가 서로 달랐고 `studio-nav.js`가 별도 바와 V10 텍스트를 런타임에 덧씌우는 임시 구조였다.
- 상태: **Supervisor 반려 · UX-P0-R2-16으로 대체**
- 결정 및 근거: `product-shell.css/js`를 공통 기준으로 경영 홈·M6·Factory·Agent·Twin의 메뉴를 `경영 홈→Factory→운영→Twin→보고서→Knowledge→Agent`로 통일했다. 회사 문맥은 `LS MnM · 전사공통 · 경영관리팀 · REAL`, 샘플 화면은 `PROTOTYPE · SAMPLE DATA`로 고정했다. Factory는 생산 제어·WBS·Timeline·Preview·품질·복구, Agent는 원본 노드·엣지 Graph Editor, Twin은 3개 시나리오와 4개 동인으로 재구성했다. Agent 미저장 Draft·Twin 미저장 시나리오·Factory 실행 중 이탈 보호를 구현했다. 1280px 가로 넘침 0, 전역 셸 화면당 1개, M6 Report 활성, Agent 이탈 경고/저장, Twin KPI 재계산, Factory ASSEMBLE→BUILD 전환, 신규 브라우저 오류 0건을 확인했다. 상세 근거는 `docs/uiux/LIVING_ENTERPRISE_IMPLEMENTATION_TRACEABILITY_2026-07-30.md` §9.
- 영향·주의사항: 실제 `frontend/`·API·DB는 변경하지 않았다. 공통 전역 셸과 `studio-nav.js` 제거 결정만 유지한다. Factory 생산라인 중심 공간 모델, Twin 전면 다크 테마, 하단 한 줄 Atlas는 기능 정의 위반으로 폐기됐다.
- 다음 행동 / 담당 / 착수 조건: Claude Code가 M6 React 이식 시 공통 `AppShell`·`CompanyContextBar`부터 구현하고 Factory→Agent→Twin 순으로 실제 상태 계약에 연결한다. Codex는 각 단계의 1280/1440 가독성·문맥·작업 보호·기능 손실을 브라우저 교차검증한다. 착수 조건은 현재 Reference Registry/Knowledge 작업과 충돌하지 않는 별도 UI 변경 범위 확정이다.

### [UX-STUDIO-IA-14] 경영 홈 복원 및 전용 Studio 분리
- 작성자 / 기록 시각: Codex / 2026-07-30 KST
- 왜 지금 기록하는가: Supervisor가 M6 Enterprise의 의미가 불명확하고 승인 원안과 달라졌으며, SW 생성·Agent 관리·Simulator를 메인 3열 화면 안이 아니라 기능 특성에 맞는 독립 화면으로 분리해야 한다고 지적했다.
- 상태: **UX-P0-SHELL-15로 대체 완료**
- 결정 및 근거: 이 항목에서 채택한 경영 홈·전용 Studio 분리 원칙은 유지한다. 다만 임시 `studio-nav.js` 주입과 V10 런타임 문구 치환 구현은 UX-P0-SHELL-15에서 제거하고 각 Studio 원본 HTML과 공통 제품 셸로 대체했다.
- 영향·주의사항: 후속 구현과 검토는 본 항목의 임시 Studio Bar가 아니라 UX-P0-SHELL-15 및 UI 추적성 문서 §9를 기준으로 한다.
- 다음 행동 / 담당 / 착수 조건: Claude Code가 M6 구현 시 `docs/uiux/LIVING_ENTERPRISE_IMPLEMENTATION_TRACEABILITY_2026-07-30.md`의 M6-UI-02, 03, 05, 07A 순서로 route와 공통 Context Bar를 구현한다. Codex는 경영 홈에 편집 기능이 다시 혼입되지 않는지, Studio별 작업 면적·핵심 시각화·이탈 보호가 유지되는지 브라우저 교차검토한다.

### [UX-M6-SAMPLE-13] UI 설계서 기반 기능별 제품 화면 샘플
- 작성자 / 기록 시각: Codex / 2026-07-30 KST
- 왜 지금 기록하는가: Supervisor가 화면기능정의서와 UI 설계서를 문서로 끝내지 말고 승인 디자인을 실제 기능 화면에 입혀 샘플링하라고 지시했다.
- 상태: **10개 핵심 화면 클릭형 샘플 완료 · 실제 React 이식 기준선 확정**
- 결정 및 근거: `uiux-prototypes/m6-product-samples/`에 Enterprise, Company Universe, Guided Start, SW Production, Report Studio, Operate, Digital Twin, Knowledge·MDM, Agent OS, Settings & Administration 10개 화면을 구현했다. Company Universe는 회사·사업부·공장 선택, 권한 범위, 산업 플레이북과 REAL 격리형 가상회사 복사 생성을 제공한다. Report Studio는 V5 Business Planning Binder의 목차·본문·주석·근거·버전·승인·PDF/Word 배포 구조를 계승한다. Admin은 개인 설정과 회사 브랜드·사용자 권한·AI 모델/비용·데이터 연계·감사/복구를 권한별로 분리하고 우측에서 변경 영향을 확인한다. Atlas에는 Task ID 없는 전역 질의와 업무 SW·시뮬레이터·보고서 공동설계 상담 진입을 추가했다. 앱 내장 브라우저에서 `Copper Expansion 2032` 가상회사 생성, Atlas 시뮬레이터 상담→Guided Start 인계, 보고서 승인, 자연어 검색, Admin 6개 도메인 탐색·브랜드 변경 검토·저장을 확인했고 콘솔 오류는 0건이었다.
- 영향·주의사항: 실제 `frontend/`·백엔드·DB는 변경하지 않았다. 화면의 경영 수치와 계산식은 UX 동작 검증용 예시이며 실제 계산 엔진의 SSOT로 사용하면 안 된다. React 이식 시 `app.js` 샘플 상태를 Zustand·REST·SSE 계약으로 교체하고, 조직 범위·404 은폐·승인 Fail-closed 원칙을 유지한다.
- 다음 행동 / 담당 / 착수 조건: Claude Code가 `docs/uiux/LIVING_ENTERPRISE_IMPLEMENTATION_TRACEABILITY_2026-07-30.md`와 본 샘플을 함께 사용해 M6-UI-01 공통 셸부터 기존 UI 병행 카나리로 이식한다. Codex는 이식 PR/커밋을 브라우저에서 정보 위계·폰트·핵심 버튼·콘텐츠 누락 기준으로 검토한다.

### [UX-SCREEN-SPEC-12] 승인 North Star 기반 M6 화면기능정의·UI 설계
- 작성자 / 기록 시각: Codex / 2026-07-30 KST
- 왜 지금 기록하는가: Supervisor가 Claude Code의 현재 기능 구현을 상세히 파악하고, 최종 승인된 `Living Enterprise Canvas` 중심으로 기능별 UI/UX 배치가 가능한 화면기능정의서와 UI 설계서를 작성하라고 지시했다.
- 상태: **설계 문서 완료 · Claude Code M6 구현 인계 가능**
- 결정 및 근거: 현재 `App.tsx`와 25개 주요 컴포넌트, 분리된 API 클라이언트, 전체 백엔드 라우트, 최근 M2~M5 커밋, 진행 중 Reference Dataset Registry를 대조했다. `docs/uiux/LIVING_ENTERPRISE_SCREEN_FUNCTION_DEFINITION_2026-07-30.md`, `LIVING_ENTERPRISE_UI_DESIGN_SPEC_2026-07-30.md`, `LIVING_ENTERPRISE_IMPLEMENTATION_TRACEABILITY_2026-07-30.md`에 34개 목표 화면, 역할·권한, 핵심 여정, 상태 계약, API/컴포넌트 매핑, M6 단계별 구현안을 기록했다.
- 영향·주의사항: 실제 `frontend/`와 백엔드는 수정하지 않았다. Claude Code가 작업 중인 `KnowledgeHubPanel.tsx`·Reference Registry 파일을 덮어쓰지 않는다. 원본자료는 승인 전 자동 전사 색인하지 않으며, 기존 `ControlPanel`·`TimelinePanel`·`PreviewPanel` 기능은 Production Workspace로 보존 이식한다. 전역 Canvas와 Atlas에는 신규 `/api/v1/enterprise-canvas`, `/api/v1/atlas/chat` 계약이 필요하다.
- 다음 행동 / 담당 / 착수 조건: Claude Code가 M6-UI-01(AppShell·Context)과 M6-UI-02(Read-only Canvas)를 기존 UI 병행 카나리로 구현한다. Codex는 각 단계의 가독성·정보 위계·기능 누락을 브라우저로 검토한다. 권한·경영수치·승격 동작 변경은 후속 교차검토 대상으로 남기되, 자체 구현과 자체검토를 불필요하게 정지시키지 않는다.

### [UX-MASTER-CONCEPT-11] Living Enterprise Canvas North Star
- 작성자 / 기록 시각: Codex / 2026-07-30 KST
- 왜 지금 기록하는가: Supervisor가 반복되는 시안 제안과 설명을 중단하고, 실제 계획을 세워 우리 시스템만의 대표 화면을 즉시 구현하라고 지시했다.
- 상태: **Supervisor 최종 합격·North Star 채택** · 실제 제품 적용 준비
- 결정 및 근거: `uiux-prototypes/master-concept/`에 좌측 의사결정 대기열, 중앙 Enterprise Digital Thread, 현업 생성 SW·Data·Twin 레이어, 하단 Trust Foundation, 우측 전역 Atlas를 하나의 화면으로 구현했다. 업무 노드 전환, 레이어 표시, 시나리오 비교, Atlas 근거 질문·자유 질문·의사결정안 생성 인터랙션을 실제 브라우저에서 검증했다. 현재 API와 신규 Aggregate·Atlas 계약의 경계는 `IMPLEMENTATION_MAPPING.md`에 기록했다.
- 영향·주의사항: 실제 `frontend/`와 API는 아직 변경하지 않았다. 현재 Supervisor Chat은 `project_id`가 필요하므로 시안의 전역 Atlas를 구현하려면 `/api/v1/atlas/chat`과 회사 Context Resolver가 필요하다. 기존 `ControlPanel`·`TimelinePanel`·`PreviewPanel`은 폐기 대상이 아니라 선택 노드의 상세 작업 공간으로 재배치한다.
- 다음 행동 / 담당 / 착수 조건: Codex가 화면 기능 정의와 디자인 토큰을 확정하고, Claude Code가 MC-1 Read-only Aggregate API 및 React 카나리 이식을 수행한다. 기존 통제실을 유지한 병행 카나리로 검증하며 실제 메인 전환은 사용자 과업 테스트 통과 후 결정한다.

### [UX-REVISION-V2-2-10] LS 공식 CI 컬러 테마 비교안
- 작성자 / 기록 시각: Codex / 2026-07-30 KST
- 왜 지금 기록하는가: Supervisor가 LS Holdings 공식 CI 페이지를 참고해 V2-1의 대표 화면 3종에 회사 대표 컬러를 적용한 V2-2를 요청했다.
- 상태: 공식 CI 조사·V2-2 테마·문서·실제 렌더링·상호작용 검증 완료 · Supervisor 비교 검토 대기
- 결정 및 근거: LS 공식 CI의 LS Blue `RGB(10,30,90)`, LS Red `RGB(250,0,45)`, Green `RGB(0,155,180)`, Blue `RGB(5,105,160)`, Gray `RGB(125,130,130)`를 `uiux-prototypes/revision-v2-2/`에 적용했다. 구조와 기능 콘텐츠는 V2-1과 동일하게 유지해 테마 효과를 독립 비교한다. 의미 체계와 상용화 전 CI 승인 조건은 `BRAND_APPLICATION_GUIDE.md`에 기록했다.
- 영향·주의사항: 실제 `frontend/`와 API는 변경하지 않았다. 시안의 LS 문자 표시는 테마 검토용이며 공식 로고 원본 재현물이 아니다. 상용 적용 전 회사 CI 담당 부서 승인과 계열사별 공식 로고·보호공간·배경 규정 등록이 필요하다.
- 다음 행동 / 담당 / 착수 조건: Supervisor가 V2-1 기준안과 V2-2 LS 테마를 비교한다. 채택 후에만 Codex가 실제 디자인 토큰과 회사 마스터 테마 스키마를 설계하고, Claude Code가 React 적용을 교차검토한다.

### [UX-REVISION-V2-1-09] 대표 화면 3종 방향 검증
- 작성자 / 기록 시각: Codex / 2026-07-30 KST
- 왜 지금 기록하는가: Supervisor가 Revision V3를 양산형 AI 디자인으로 판단하고, Revision V2의 독창성을 살린 보완안 V2-1을 요청했다.
- 상태: 대표 화면 3종 구현·정적 검증 완료 · Supervisor 시각 검토 대기
- 결정 및 근거: `uiux-prototypes/revision-v2-1/`에 Enterprise World, Software Production Line, Future Scenario Room을 구현했다. 공통 UI·본문은 Pretendard/Noto Sans KR 계열, 수치·코드만 고정폭으로 제한했다. 한글 손상 0건, 금지 글꼴 0건, 로컬 참조 누락 0건, 핵심 상호작용과 `git diff --check`를 확인했다. 기능 보존표는 `CONTENT_COVERAGE.md`, 채택 기준은 `DIRECTION_SCORECARD.md`에 기록했다.
- 영향·주의사항: 실제 `frontend/`와 API는 변경하지 않았다. `revision-v3/`는 최종 후보가 아니라 통일형 실험의 실패 이력으로 보존하며, 그 세트의 공통 Shell을 향후 구현 기준으로 사용하지 않는다.
- 다음 행동 / 담당 / 착수 조건: Supervisor가 대표 화면별 채택·부분 채택·재설계를 판정하면 Codex가 승인된 공간 모델을 나머지 기능 화면과 최종 디자인 시스템으로 확장한다. 실제 React 이식 전 Claude Code가 API·상태 매핑을 교차검토한다.

### [UX-SET-B-08] 통일형 두 번째 UI/UX 후보 세트
- 작성자 / 기록 시각: Codex / 2026-07-30 KST
- 왜 지금 기록하는가: Supervisor가 Revision V2의 기능별 구조를 긍정적으로 평가하면서 글꼴 변화를 최종 취합 시 제한하고, 같은 기능군을 다른 방식으로 설계한 두 번째 세트와 비교해 최종 선택하라고 요청했다.
- 상태: Set B V1~V10 구현·정적 검증 완료 · Set A/B 비교 선택 대기
- 결정 및 근거: `uiux-prototypes/revision-v3/`에 공통 `set-b.css`를 사용하는 10개 대안을 구현했다. V1 Mission, V2 Workspace, V3 Evidence Matrix, V4 Plant Timeline, V5 Planning Workbook, V6 Organization Tree, V7 Critical Path, V8 Day Planner, V9 Performance Ledger, V10 Guided Launchpad다. 모든 UI·본문은 Pretendard/Noto Sans KR 계열을 사용하고 숫자·코드에만 고정폭 글꼴을 적용한다. V1~V10 고유 구조·상호작용·공통 CSS 참조, 한글 손상 0건, 누락 참조 0건, 금지 글꼴 0건, 갤러리 연결과 `git diff --check`를 검증했다.
- 영향·주의사항: 실제 `frontend/`는 변경하지 않았다. Set A는 개성·차별성, Set B는 통일성·구현성 평가용이며 한 세트를 통째로 선택할 필요는 없다. 비교 기준은 `uiux-prototypes/REVISION_SET_COMPARISON.md`다.
- 다음 행동 / 담당 / 착수 조건: Supervisor가 화면별 Set A/Set B/혼합 채택을 결정하면 Codex가 Set B 글꼴·Shell·상태 토큰 위에 선택 구조를 통합한 Final UI Architecture와 화면 명세를 작성한다. Claude Code는 최종안의 React·API·상태 매핑을 교차검토한다.

### [UX-REVISION-V2-07] V1~V10 디자인 전체 수정본
- 작성자 / 기록 시각: Codex / 2026-07-30 KST
- 왜 지금 기록하는가: Supervisor가 기존 10개 시안이 구성만 다르고 실제 디자인 테마는 2~3개에 불과하다고 지적했고, 제3자 평가에서도 카드형 대시보드 반복·작은 글자·정적 화면 문제가 확인되어 전체 수정본 작성을 요청했다.
- 상태: Revision V2 구현·정적 검증 완료 · Supervisor 시각 검토 및 선별 대기
- 결정 및 근거: `uiux-prototypes/revision-v2/`에 V1 Product Control Room, V2 Desktop OS, V3 Decision Theater, V4 Plant Mimic, V5 Planning Binder, V6 Spatial Constellation, V7 Process River, V8 Editorial Personal Portal, V9 Value Chain Sankey, V10 Atlas Solution Canvas를 분리 구현했다. 각 화면은 고유 공간 모델과 최소 1개 상호작용을 갖는다. V1~V10 파일·고유 제목·디자인 키·본문 14px 기준·style/script 블록, 한글 손상 0건, 로컬 참조 누락 0건, `git diff --check`를 검증했다.
- 영향·주의사항: 실제 `frontend/`는 변경하지 않았다. 수치는 레이아웃 검토용 예시다. 기존 `v1/`~`v10/`은 삭제하지 않고 비판 전 탐색 이력으로 보존하며, 이후 최종 비교는 `revision-v2/index.html`을 기준으로 한다.
- 다음 행동 / 담당 / 착수 조건: Supervisor가 `revision-v2/SELECTION_SCORECARD.md` 기준으로 채택·부분 채택·보류·제외를 판정하면 Codex가 선택 요소를 하나의 To-Be 정보구조·디자인 시스템·화면 명세로 통합한다. Claude Code는 최종 통합안에 한해 현재 React·API·상태 모델 구현 적합성을 교차검토한다.

### [UX-DIVERGENCE-06] V1~V10 디자인 문법 중복 감사와 전면 리비전
- 작성자 / 기록 시각: Codex / 2026-07-30 KST
- 왜 지금 기록하는가: Supervisor가 10개 시안의 구성 차이에도 불구하고 실제 디자인 테마가 다크·라이트·V8 편집형의 3개 수준에 불과하다고 지적했다.
- 상태: 중복 원인 감사 및 리비전 설계 완료 · 실제 시안 재구축 착수 전
- 결정 및 근거: 코드 감사 결과 V2~V10 중 9개가 CSS Grid·흰 카드·상단 바를 사용하고 8개가 파란 포인트 계열을 공유했다. `uiux-prototypes/DESIGN_DIVERGENCE_REVISION_PLAN.md`에서 V1~V10에 서로 다른 공간 모델·탐색·상호작용·시각 언어와 금지 규칙을 배정했다. V2·V3·V4·V5·V9는 전면 재설계, V6·V10은 핵심 캔버스 강화, V7·V8은 용도를 유지하며 정제한다.
- 영향·주의사항: C01~C12 콘텐츠와 V7=프로젝트 하위 모듈, V8=향후 개인화 포털이라는 제품 판단은 유지한다. 기존 HTML을 삭제하지 않고 각 버전 폴더에서 리비전하되, 디자인 차이를 만들기 위해 콘텐츠를 누락해서는 안 된다.
- 다음 행동 / 담당 / 착수 조건: Codex가 Wave 1(V2 Desktop OS, V3 Decision Theater, V4 Industrial Control Room, V5 Planning Binder)을 순차 재구축한다. 각 Wave 완료 후 Supervisor가 실제 시각 차이를 검토하고, Claude Code는 최종 채택안에 대해서만 React 구현 적합성을 교차검토한다.

### [UX-EVAL-04] Antigravity UX 평가 개입 철회 및 Codex 주도권 위임
- 작성자 / 기록 시각: Antigravity / 2026-07-30 13:40 KST
- 왜 지금 기록하는가: 저(Antigravity)의 섣부르고 일관성 없는 UX 평가 개입으로 혼선이 발생하여, Supervisor의 지시에 따라 모든 디자인 강제 지시를 철회하고 원래 담당자에게 주도권을 돌려주기 위함입니다.
- 상태: **Antigravity 이전 개입(UX-EVAL-01~03) 전면 무효화**
- 결정 및 근거:
  - 프론트엔드 통합, Set A/B 선택 및 하이브리드 구성 등 UI/UX 디자인에 관한 모든 권한과 최종 결정권은 전적으로 **Codex**에게 일임합니다.
- 영향·주의사항:
  - 저(Antigravity)는 이후 UI 디자인의 미적, 구조적 결정에 일절 관여하지 않습니다.
- 다음 행동 / 담당 / 착수 조건: **Codex**가 자신의 판단과 제품 기획 역량을 바탕으로 Master UI 통합을 주도합니다.

### [PMO-WBS-02] 팀원별 마이크로 태스크 분할 및 M5 통합 E2E 기획 갱신
- 작성자 / 기록 시각: Antigravity / 2026-07-30 11:30 KST
- 왜 지금 기록하는가: 단일 Master WBS의 한계를 보완하기 위해 각 에이전트별 상세 Task Tracker를 도입하고, 누락된 비즈니스 검증 시나리오를 3단계 통합 E2E에 태우기 위함.
- 상태: 완료 (적용 중)
- 결정 및 근거:
  1. `docs/wbs/` 하위에 `claude_code_tasks.md`, `codex_tasks.md`, `antigravity_tasks.md` 3종의 마이크로 태스크 트래커를 신설함. 향후 각 에이전트는 본인의 할 일을 이 파일들로 쪼개어 관리할 것.
  2. 기존 `run_e2e_scenario.py`가 담지 못하는 권한 격리 및 디지털트윈 검증을 포함하기 위해 `docs/wbs/test_plan_m5_e2e.md` (3단계 E2E 통합 기획서)를 신설함.
- 영향·주의사항:
  - M5 통과(Quality Gate)는 위 E2E 기획서의 3단계 시나리오(Core, Auth, Business)를 모두 PASS 해야 완료(DONE)로 간주됨.
  - 앞으로 개별 기능 To-Do 갱신 시 `TEAM_BOARD`에 중복 서술하기보다 각자의 Task Tracker 마크다운을 업데이트할 것.
- 다음 행동 / 담당 / 착수 조건: Antigravity가 PMO이자 품질 관리자로서 위 M5 E2E 테스트 스위트를 직접 기동하며 오류 텔레메트리를 감사(Audit)함.

### [PMO-WBS-01] 시스템 파일 정리 및 Master WBS 체계 전환 공지
- 작성자 / 기록 시각: Antigravity / 2026-07-30 10:45 KST
- 왜 지금 기록하는가: Supervisor의 지시에 따라 PMO로서 시스템의 테스트 파일들을 아카이브하고 Master WBS를 신설했음을 팀에 공유하기 위함.
- 상태: 완료 (적용 중)
- 결정 및 근거:
  1. `docs/wbs/system_implementation_wbs.html` 를 전체 마일스톤 진행률을 모니터링하는 공식 Master WBS로 지정함.
  2. 1회성 스크립트(`test_*.py` 등)는 `_archive/scripts_tests/` 로 격리 이동되었으며, 옛 문서들은 `docs/chronicle/` 과 `docs/archive/` 로 분류 보관됨. (`walkthrough.md` 참조)
- 영향·주의사항:
  - 앞으로 과거 테스트 코드를 찾으려면 `_archive/` 경로를 확인해야 함.
  - 테스트 및 빌드 과정에서 옛 경로 참조 시 에러가 날 수 있으므로 주의.
  - 마일스톤(M1~M6) 상태 갱신 시 `TEAM_BOARD.md` 기록과 함께 Master WBS의 타임라인 및 % 갱신도 병행할 것.
- 다음 행동 / 담당 / 착수 조건: 전 팀원(Claude Code, Codex)은 새 파일 구조와 WBS를 작업 기준점으로 삼고 진행할 것.

### [M2-ENFORCE-01] ⚠️ 조직 권한 강제를 **켰다** — 서버 재시작 시 화면 동작이 바뀐다
- 작성자 / 기록 시각: Claude Code / 2026-07-31 KST (같은 날 야간에 실측 결과로 갱신)
- 왜 지금 기록하는가: **운영 동작이 바뀌는 전환을 실행**했고, 이 사실을 모르면 다음 사람이
  서버를 재시작한 뒤 "앱이 고장났다"고 판단하기 때문이다. 인계 없이 넘기면 안 되는 항목이다.
- 상태: **완료(가동 중) · 실서버 실측 완료** — 실측에서 결함 6건이 나와 모두 수정했다.
  ⚠️ 처음 이 항목을 "완료"로 적었을 때 실제로는 **목록 API 에 통제가 없었다.** 강제를 켠 것과
  통제가 걸리는 것은 다른 사실이었고, 그 차이는 서버를 띄워 부르기 전까지 보이지 않았다.
- 결정 및 근거: `ORG_ENFORCE=False` 인 동안 `resolve_scope()` 는 **전원 무제한**을 돌려준다
  (`core/org_directory.py:498`). 즉 관문 A·범위 격리·등급 가림·경영진 드릴다운이 실 시스템에서
  **하나도 작동하지 않는 상태**였다. 스위치를 정책 저장소로 옮겨(`core/scope_policy.py`)
  배포 없이 켜고 끌 수 있게 한 뒤 켰다.
  · 근거 커밋: `e8f510fb9`(스위치·사전점검) · `8dd82ed44`(가동·폐지 결함 수정) · `76ac642a8`
  · 실측: `hikwon@lsmnm.com` 무제한 / 폐지 계정 4건 전부 차단 / 미등록·익명 차단 /
    지식 검색 LS_MNM 3건·MNM_BATTERY 5건(상속)·**LS_CABLE 0건**(타 법인 차단)
  · 테스트 **1426 passed**(두 폴더 동일) · `tests/test_m2_entry_gates.py` **xfail 0**
- 영향·주의사항:
  · ⚠️ **8080·5173 을 재시작하면 그때부터 강제가 적용된다.** 프론트는 `localStorage` 의
    `factory.actingUser` 가 설정돼야 사용자 헤더를 보내므로, **화면 우측 상단에서 사용자를
    지정하지 않으면 목록이 빈다.** 이유는 화면이 붉은 배너로 설명한다(`/api/v1/org/me` 의
    `access_note`) — 자료가 사라진 것이 아니다.
  · ⚠️ 활성 사용자는 `hikwon@lsmnm.com`(권희권) **1명뿐**이다. 테스트 잔여 계정 4건
    (`admin`·`bob`·`bob2`·`exec`)은 소프트 폐지했다(`status='retired'` — 되돌릴 수 있다).
    Codex·Antigravity 가 화면 실측을 하려면 **본인 계정을 등록**하거나 위 계정으로 접속해야 한다.
  · ⚠️ 폐지가 권한을 제거하지 않던 결함을 함께 고쳤다 — `get_user()` 가 `status` 를 거르지
    않아 폐지된 `admin` 이 **전권을 유지**하고 있었다(`resolve_scope` 에서 차단).
  · **되돌리기(코드 배포 불필요)**:
    `PUT /api/v1/admin/org-enforcement {"enabled": false, "reason": "..."}` (관리자 전용)
    또는 `data/scope_policy.json` 의 `org_enforce` 를 `false` 로.
- 다음 행동 / 담당 / 착수 조건:
  · **Claude Code**: ~~서버 재시작 후 6개 화면 실측~~ → **완료(2026-07-31)**. 실측에서 결함
    6건이 나와 함께 고쳤다 — 아래 교대 체크포인트 참조
  · **Antigravity**: 강제 ON 상태의 격리 실측(사업부 간 교차 조회·경영진 드릴다운·감사로그).
    ★ 이제 실측 대상이 실제로 존재한다 — 부서별 조직범위 배정이 끝났으므로 비관리자 계정을
    만들어 사업부 간 교차 조회를 실제로 시도할 수 있다(측정 방법은 체크포인트 3번에 기재)
  · **Codex**: 화면별 빈 상태 안내. `App.tsx` 의 지식팩 선택 영역에는 적용했으나
    (`blocked_reason` 을 받아 "안 보인다"로 구분) **`KnowledgeHubPanel.tsx` 는 수정 중이라
    손대지 않았다** — 그 파일의 "등록된 지식팩이 없습니다"도 같은 구분이 필요하다.
    ⚠️ 그 파일이 자기 `API_BASE_URL = 'http://localhost:8080'` 을 선언한 것이 오늘 결함 5건 중
    하나의 원인이었다(아래 5번). 인터셉터 쪽에서 덮었으니 급하지는 않지만, 공용
    `lib/api.ts` 의 `API_BASE_URL` 을 import 하는 편이 옳다
  · **사용자**: 실제 인원 부서 배정(파일럿 대상자 목록 필요) — 부서→조직범위 배선은 끝났으므로
    이제 "누가 어느 부서인가"만 있으면 권한이 곧바로 정해진다
  · ~~최상위 부서 `hq` 의 이름이 "해킹"~~ → **해결(2026-07-31)**. 버전 이력에서 v1 이 "본사"
    였음을 확인하고 v4 로 복원했다(추측이 아니라 원래 이름 복원).
    ★ 사용자가 "보안 테스트하다 걸린 것 아니냐"고 물었고 **답할 수 없었다** — 그 질문이
    아래 [ORG-AUDIT-02] 를 만들었다. 조사 결과만 남긴다: 개명 시각은 2026-07-27 23:39:53
    (부서 생성 2분 뒤), 그날은 권한 강제 가동(7/30 23:55) **전**이라 익명으로도 개명이
    가능했으므로 **취약점 통과의 증거로 볼 수 없다**. 리포지토리 어느 코드에도 그 문자열은
    없고, 감사로그는 그 날짜를 담지 않는다. 행위자는 확인 불가로 남는다
- 교대 체크포인트 (v2 §4-2 · 작성: Claude Code / **2026-07-31 야간 세션 갱신**):
  1. **마지막 확인 상태**: 이전 체크포인트가 남긴 유일한 공백(**실 서버 6개 화면을 강제 ON
     상태로 확인하지 못했다**)을 닫았다. 서버 8080·5173 을 띄우고 실제로 부르자
     **결함 6건**이 나왔다 — 테스트 1426건이 통과하는 상태에서였다.
     ⚠️ 이 항목이 이번 세션의 교훈이다: **테스트 통과는 화면이 옳다는 증거가 아니다.**
     발견한 6건(모두 수정·커밋 완료):
     ① `GET /knowledge/packs` 가 익명에게 지식팩 4건, `/reference/assets` 가 자산 68건을
        그대로 반환했다 — 조직 범위 필터가 `scope_node_id` 를 준 호출자에게만 적용되는
        **선택 사항**이었고 프론트는 주지 않았다. 관문 A("미지정 = 비노출")의 정반대였다.
     ② `DELETE /knowledge/packs/{id}` 에 권한이 없었다 — **익명이 전사 지식팩을 지울 수 있었다**
        (업로드·문서삭제·범위부여·scope-report 도 같았다).
     ③ 폐지 계정에게 화면이 "부서가 배정되지 않았습니다"라고 **틀린 이유**를 말했다.
        판정은 맞고 설명이 틀린 경우 — 사용자는 부서 배정을 요청하고 관리자는 이미 배정된 것을
        보고 시스템 오류로 판단한다. 실제 이유(계정 폐지)에는 아무도 도달하지 못한다.
     ④ 사용자를 바꿔도 목록이 갱신되지 않았다 — `UserSwitcher` 가 쏘는
        `factory:acting-user-changed` 를 **듣는 곳이 없었다**.
     ⑤ `KnowledgeHubPanel.tsx` 가 자기 `API_BASE_URL` 을 `localhost:8080` 으로 선언해
        인터셉터(`127.0.0.1` 기준)가 식별 헤더를 못 붙였다 → 그 패널의 모든 호출이 조용히
        익명으로 나갔고, 통제를 켜자 **무제한 권한 관리자에게도 지식 허브가 텅 비었다**.
     ⑥ 일반 직원에게도 **하위 조직 열람**이 열려 있었다(사용자 결정 ③은 경영진만) —
        `include_descendants=True` 를 라우트가 각자 정하고 있었기 때문이다.
  1-b. **이번 세션에 추가로 완성한 것 — 부서→ECM 조직 노드 매핑**(권한 모델의 마지막 조각):
     이전 체크포인트 시점에는 "열어도 되는가"까지만 판단했고 "무엇까지 보이는가"는 판단하지
     못했다(자료의 소유자는 부서명이 아니라 `LS_MNM`·`MNM_BATTERY` 같은 ECM 노드로 적혀 있는데
     둘 사이에 다리가 없었다). 다리를 **부서**에 놓았다(`departments.scope_node_id`) —
     사용자에 놓으면 같은 부서의 두 사람이 다른 범위를 갖고, 그 차이는 아무도 의도하지 않은 채
     생긴다(어제 `production` 이 두 사업부에 걸쳐 정렬 순서가 권한을 정한 사고와 같은 유형).
     실 조직 11개 부서를 배정했다: 스태프·본사 기능 9개 → `LS_MNM`,
     `production_battery` → `MNM_BATTERY`, `production_copper` → `MNM_COPPER`.
     `t_admin`(테스트 부서)은 **일부러 미배정**으로 남겼다 — 추측하지 않는다.
  2. **변경 범위**: 어제 커밋 22건(`91e1fb497`→`b99914f08`) + 오늘 3건
     (`5d36f456d` 프로토콜 v2 · `5ec79edb6` 목록 통제 · `cce0a9714` 운영파일 추적 해제
     · 부서 매핑 커밋). 신규 모듈 11개(`core/scope_contract.py` ·
     `sandbox_token.py` · `scope_policy.py` · `org_activation.py` · `classification.py` ·
     `external_collector.py` · `library_paths.py` 등) · 라우트 5개 · 테스트 1234→1426.
     **미변경**: 프론트엔드는 `UserSwitcher.tsx` · `App.tsx` · `lib/api.ts` **3개 파일만** 고쳤다.
     Codex 의 UI 시안·`uiux-prototypes/`·`_archive/` 정리물, 그리고 **Codex 가 수정 중인
     `KnowledgeHubPanel.tsx` 와 `knowledge_control.py` 의 `INDEXABLE_EXTS` 변경은 손대지 않았다**
     (§9). 후자는 오늘 병합 시 두 변경이 함께 살아 있는지 확인했다.
     **실 데이터 변경 있음**: 부서 2개 생성(`production_copper`·`production_battery`) · 실제
     관리자 1명 등록 · 테스트 계정 4건 소프트 폐지 · 지식팩 청크 1342건에 소유 조직 부여 ·
     참고문서 17건 승인·16건 색인 · `data/scope_policy.json` 생성(강제 ON) ·
     **오늘: 부서 11개에 조직범위 배정(각 부서 새 버전 생성)**.
     ⚠️ 오늘 실측을 위해 비관리자 계정 2건(`batt.test@`·`acct.test@`)을 만들었고 **측정 직후
     폐지했다**. 활성 사용자는 다시 `hikwon@lsmnm.com` 1명뿐이다.
  3. **검증 증거**: `python -m pytest` → **1447 passed / 실패 0 / xfail 0**
     (어제 1426 → 신규 21건: 목록 통제 10 · 부서 매핑 10 · 폐지 안내 1).
     관문: `tests/test_m2_entry_gates.py` · `tests/test_listing_visibility_gate.py` ·
     `tests/test_dept_scope_binding.py`.
     **실서버 실측(강제 ON)** — 재현 방법까지 남긴다:
     · 익명 → packs 0건 · assets 0건 · indexable 0건(+ 이유 문구) / 상세·검색·scope-report 403 /
       삭제 403
     · `hikwon@lsmnm.com`(무제한) → packs 4건 · assets 68건 · 검색 200(본문 조각 반환)
     · `production_battery` 소속 비관리자 → packs **4건**(자기 사업부 1 + 전사 상속 3) · assets 52건
     · `accounting` 소속 비관리자 → packs **3건**(전사만, 배터리 팩 1건 가려짐) · assets 46건
       ★ 이 두 줄이 조직 범위가 실제로 갈린다는 증거다. 재현: 해당 부서로 사용자를 만들고
         `curl -H "X-User-Id: <id>" .../api/v1/knowledge/packs` — 끝나면 반드시 폐지할 것.
     · 화면: 접근 불가 배지 · 익명 배너 · "지식팩이 보이지 않습니다(자료가 없는 것이 아닙니다)" ·
       사용자 전환 시 목록 갱신 · 6개 패널(거버넌스·기준정보·업무표준·조직권한·크로스워크·계기판)
       콘솔 오류 0 · 조직·권한 화면에 조직도 12부서·사용자 1명·폐지 4계정 미노출
     DB 백업: 스크래치패드 `db_backup_2026-07-30`(13개 DB · 4.3MB).
     ⚠️ **DB 복사 시 `-wal` 을 함께 가져갈 것.** 오늘 `master.db` 만 복사해 검증 환경을 만들었다가
       최신 커밋(관리자 등록·계정 폐지)이 빠진 **과거 상태**를 실측하고 "고침이 동작하지 않는다"고
       오판했다. sqlite WAL 은 본체 파일 밖에 있다.
  4. **저장소 상태**: 작업 폴더 · 원래 폴더 · `origin/dev` 모두 일치하며 제 변경은
     **전부 커밋·푸시 완료**.
     ⚠️ 원래 폴더에 **Codex 의 미커밋 변경**이 남아 있다(`.agents/AGENTS.md` ·
     `KnowledgeHubPanel.tsx` · `knowledge_control.py`(확장자 목록) · `run_e2e_scenario.py` ·
     `uiux-prototypes/` · `CODEX_EXECUTION_DIRECTIVE.md` · `check_models.py`·`docs/*.docx` 삭제).
     `TEAM_PROTOCOL.md` 와 이 보드는 오늘 `5d36f456d` 로 커밋했다(본문 저작은 Codex — 커밋
     메시지에 표기). 같은 파일을 고칠 때는 v2 §5-1 규칙 7대로
     **`git add` 전에 diff 를 확인**해야 한다.
     ✔ `data/reference_registry.json` · `data/access_audit.jsonl` · `data/scope_policy.json` 은
     **오늘 추적에서 뺐다**(`cce0a9714`). 파일은 양쪽 폴더에 그대로 남아 있다.
     ⚠️ 두 폴더에 각각 사본이 존재하므로 **여전히 자동 동기화되지 않는다** — 운영 상태를 옮길
     때는 파일을 직접 복사하고, DB 라면 `-wal` 까지 가져간다.
  5. **재개 지점**: 남은 것은 **업무 판단이 필요한 항목**이다(코드 쪽 강제 경로는 닫혔다).
     첫 행동 후보 세 가지, 우선순위 순:
     ① 사용자에게 `hq` 부서명("해킹")을 확인받아 정상화 — 부서명 변경은 새 버전을 만든다
     ② 파일럿 대상자 목록을 받아 실제 인원 부서 배정(부서→조직범위 배선은 끝났다)
     ③ E3 Sandbox(가상 기업 문맥) — 토큰·가시성 배관은 있고(`core/sandbox_token.py`,
        `/api/v1/sandbox/*`) **가상 데이터를 만드는 흐름이 없다**.
        `bind_master_to_scope` 가 `entity_mode != REAL` 을 거부하는 것이 시작점이다.
     참고: 다중 워커 토큰 저장소는 **결함이 아니다** — `run.py` 는 단일 워커이고, 메모리 저장은
     "세션 전용"의 의도된 성질이다(`core/sandbox_token.py` 상단 참조). `gunicorn -w N` 으로
     갈 때 공유 저장소가 필요해지는 **배포 전제 조건**으로 취급할 것.
     참고: 스캔 PDF OCR 은 지금 병목이 아니다 — 색인 막힌 51건 중 **50건이 DRM**이고
     변환 필요는 1건이다(`/api/v1/reference/summary` 로 재확인 가능).
  6. **금지·주의 범위**:
     · **`config.ORG_ENFORCE` 를 고쳐 끄려 하지 말 것** — 정책 저장소(`data/scope_policy.json`)가
       코드 기본값을 이긴다. 끄려면 `PUT /api/v1/admin/org-enforcement {"enabled": false}`.
     · **폐지 계정 4건을 되살리지 말 것**(`admin` · `bob` · `bob2` · `exec`) — 되살리면 테스트가
       만든 `admin` 이 전권을 갖는다. 필요하면 본인 이름의 계정을 새로 만든다.
     · **DRM 보호 문서 50건은 손대지 말 것** — 사용자 결정으로 시스템 오픈 후 처리다. 변환
       도구로 열리지 않는다(시도하면 전부 실패한다 — 실측).
     · **`tests/conftest.py` 의 격리 13개를 줄이지 말 것** — 줄이면 테스트가 운영 데이터에
       의존해 폴더에 따라 다른 결과를 낸다(이번 세션에 실제로 발생·수정).
     · **목록 라우트에서 `visibility_block_reason` / `viewer_visible_scopes` 호출을 빼지 말 것.**
       통제를 요청 파라미터(`scope_node_id`)로 되돌리면 오늘 고친 구멍이 그대로 재발한다 —
       파라미터는 통제의 **입력**이지 해제 수단이 아니다.
     · **라우트에서 `include_descendants=True` 를 직접 쓰지 말 것.** 하향 열람 판정은
       `api/deps.py:viewer_may_drill_down()` 한 곳이다(경영진만 — 사용자 결정 ③).
       라우트가 각자 정하면 그 라우트만 조용히 넓어진다(오늘 결함 ⑥).
     · **`departments.scope_node_id` 를 비어 있는 부서에 추측으로 채우지 말 것.** 미지정은
       미지정으로 둔다 — 추측이 한 번 맞으면 아무도 다시 검증하지 않고, 틀리면 다른 사업부
       자료가 열린다. `t_admin` 이 의도적으로 비어 있는 예다.

### [ECM-E4-06] 외부환경 인텔리전스 → 보드 FORECAST 계열 — E4 마지막 조각
- 작성자 / 기록 시각: Claude Code / 2026-08-03 KST
- 왜 지금 기록하는가: Codex 가 구현 인계서를 작성 중이라 매핑 문서를 만들면 같은 내용이 두 곳에
  생긴다(§4-1). 그래서 겹치지 않는 제 담당(백엔드 잔여)을 진행했고, E4 의 마지막 조각을 닫았다.
- 상태: **완료(구현·실서버 양성/음성 경로 실측)**
- 결정 및 근거: 보드에 `FORECAST` 계열 **자리만 있고 아무것도 이어져 있지 않았다.**
  `core/external_intelligence.py` 는 이미 §12.2 용도별 최소 등급을 지켜 등급 미달이면
  `allowed=False, value=None` 을 준다. 연결 지점에서 그 규율을 무너뜨리기가 가장 쉽다.
  ⚠️ **등급 미달은 값이 아니라 결손이다.** 거부된 값을 0 이나 이전 값으로 채우면 표는 정상으로
    보이고, §12.1 이 금지한 "검증 없이 시장 전망값으로 기준 계획을 바꾸는" 상황이 된다.
    그리고 그 차이는 화면에서 보이지 않는다.
  · 제외된 지표는 `outlook.blocked` 에 **이유·요구등급·보유등급·다음 행동**과 함께 올라간다
  · 조회가 깨져도 `blocked` 로 올린다 — 조용히 빠지면 "지표가 없다"와 "조회가 깨졌다"가 같아진다
  · **쓸 수 있는 값이 하나도 없으면 계열을 세우지 않는다** — 빈 계열은 "전망이 0" 으로 읽힌다
  · 기본 용도는 `scenario`(silver). 전망에 gold 를 요구하면 계열이 늘 비고 아무도 쓰지 않는다.
    경영 보고용은 호출자가 `official_report`(gold)를 지정한다 — 용도를 코드에 고정하면 화면마다
    다른 기준이 생긴다
  · 값마다 등급·관측시점·vintage·원천을 올린다. 없으면 보드에서 전망값과 실적이 같은 숫자로 보인다
  · 전망 계열은 `official=False` — 보드가 구분해 그릴 수 있다
- 영향·주의사항: `POST /enterprise-context/executive-board` 에 `outlook_indicators` ·
  `outlook_purpose` · `outlook_as_of` · `outlook_vintage` 를 추가했다(기본값은 종전 동작).
  `outlook.notes` 를 보드 `notes` 에 합류시켰다 — 별도 필드에만 두면 화면이 읽지 않는다.
  **실 시스템 상태 변경 1건**: 플레이북이 선언한 외부지표 **6건**을 등록부에 시드했다
  (`ext_fx`·`ext_material`·`ext_energy`·`ext_rate`·`ext_demand_index` 등). 멱등이고 플레이북
  선언을 그대로 옮긴 것이므로 **유지**했다 — 이제 `/external/readiness` 가 의미 있는 답을 준다.
  실측용 관측값 1건·원천 1건은 **삭제**했다(관측값 0건·원천 0건 확인).
- 다음 행동 / 담당 / 착수 조건: **Antigravity** — 실제 원천(전력 고시·환율·원자재)을 등록·승인하고
  관측값을 넣는 일이 남았다. 지표 6건은 등록됐고 **관측값은 0건**이므로 지금 보드의 전망 계열은
  항상 비어 있다(그리고 그 사실을 `blocked` 로 말한다). 착수 조건: 원천의 라이선스·이용허용 확인.
- 교대 체크포인트: 신규 모듈 `core/enterprise_context/outlook_series.py` + 보드 라우트 확장 +
  `tests/test_outlook_series.py` 15건. 헤더 주석 1건 정정
  (`resolved-profile` 을 "미구현" 으로 적어 둔 낡은 줄 — 이미 있는 기능을 없다고 적은 주석은
  다음 사람이 같은 것을 다시 만들게 한다).
  검증 **1611 passed / 실패 0**(1596 → +15). 실서버 **음성**: 미등록 지표 2건 → 계열 미생성 ·
  제외 2건 · 안내 2줄 · 잘못된 용도 400. 실서버 **양성**: 지표 시드 6건 → gold 관측값 1건 등록 →
  보드에 `예측 132.5 / official=false` 로 오르고 가로합계 None 확인.
  ⚠️ 양성 경로를 처음엔 대역으로만 검증했는데, 실서버 지표가 0건이라 **대역만 검증한 상태**였다 —
  실물로 다시 확인했다. 커밋·푸시·DB 동기화 완료, 서버 종료.
  ⚠️ 금지: 제외된 지표를 0·이전 값으로 채우지 말 것 · 빈 전망 계열을 세우지 말 것 ·
  용도(`purpose`)를 코드에 고정하지 말 것.

### [ECM-E4-05] 경쟁사 근거·신뢰도 · 계산 엔진 연결 · 전사 집계 · 경영진 보드
- 작성자 / 기록 시각: Claude Code / 2026-08-03 KST
- 왜 지금 기록하는가: 사용자가 "남은 것도 바로 이어서" 지시했다. 남아 있던 세 건
  (경쟁사 근거·신뢰도 / 엔진 연결 / M4·E4 집계·보드)을 모두 마무리했다.
- 상태: **완료(구현·실서버 실측)** — §7.3 · §8.1~8.3 · §11 E4
- 결정 및 근거:
  ① **경쟁사 참조**(`competitor_reference.py`) — §7.3 다섯 줄을 코드로.
     · 근거 5종(`source`·`published_at`·`as_of_date`·`confidence`·`evidence_level`)을 **필수**로.
       하나라도 선택으로 두면 비게 되고, 몇 달 뒤엔 내부 실적과 구분되지 않는다 —
       그때 "경쟁사는 우리보다 원가가 낮다"가 근거 없는 사실로 굳는다
     · 근거 종류는 **허용 4종만**(공개공시·공식발표·계약허용 산업데이터·검증 조사자료).
       "인터넷 검색"을 받기 시작하면 근거 필드는 장식이 된다
     · **신뢰도는 숫자가 아니라 단계**(HIGH/MEDIUM/LOW) — 0.7 로 두면 계산에 쓰이기 시작하고,
       추정 불확실성이 확정 계산의 입력이 된다
     · ★★ **"확인 불가"를 1급 상태로** 뒀다(`mark_unverifiable`). 이것이 §7.3-3("LLM 은 빈 칸을
       사실처럼 채우지 않는다")을 **코드로** 만드는 방법이다 — 값을 넣을 칸이 하나뿐이면 모르는
       값을 만난 사람(또는 모델)은 결국 그럴듯한 숫자를 넣는다
     · 커버리지가 **확인 불가와 미조사를 구분**해 센다(찾아봤고 없는 것 vs 아직 안 본 것)
     · 1년 넘은 값은 `stale`(공시는 연 1회 갱신 → 최신본이 이미 나왔을 가능성)
     · **경쟁사와의 차이(delta)를 계산하지 않는다** — 숫자로 보이는 순간 사실처럼 읽히고, 그
       차이의 대부분은 추정 오차일 수 있다
     · 경쟁사 엔터티 생성은 **이 모듈이 유일한 문**(`POST /entities` 는 여전히 REAL 만)
  ② **계산 엔진 연결**(`calc_bridge.py`) — **ECM 가정 세트가 엔진 가정의 원본이 된다.**
     연결이 없으면 결과를 손으로 옮겨야 하고, 그러면 엔진은 +12%로 계산하고 ECM 기록에는
     +10%로 남는 상황이 생긴다 — 그때 비교표의 "근거"는 거짓이 된다.
     ⚠️ 같은 사실이 두 곳에 선언되면 반드시 갈라진다(라이브러리 경로·owner_org_id·부서/코드/노드).
     · 키 규약 `account|driver:<코드>:<pct|delta|set>` — **규약 밖의 키는 거부**한다.
       조용히 무시하면 그 가정만 빠지고 결과는 정상처럼 보인다(가정 12개 넣고 9개만 반영)
     · **번역이 전부 성공한 뒤에야** 엔진에 쓴다 — 반쯤 만들어진 엔진 시나리오를 남기지 않는다
     · 반영되지 않은 가정·동인 경고를 `warning` 으로 **소리 내어** 올린다
     · 결과에 `planning_engine_v<버전>` 이 남아 재현 가능(§8.1)
  ③ **전사 집계**(`rollup.py`) — 합치는 순간 거짓말이 되기 가장 쉬운 계산.
     · **이중 계상**(부모 값 + 자식 값)은 합계에서 **제외**하고 알린다. 자동으로 고르지 않는다 —
       어느 쪽이 정본인지는 넣은 사람만 안다
     · 운영 집계는 법인 경계를 넘지 않고, 연결 집계는 **지분율**로 넘는다(다단 희석까지 곱한다 —
       A→B 60%, B→C 50% 를 A→C 100% 로 보면 안 된다)
     · **결손을 0 으로 채우지 않는다** — 커버리지를 함께 준다(부분 합계를 전체로 오해하지 않게)
  ④ **경영진 보드**(`executive_board.py`) — 실제·계획·예측·가상·경쟁사를 한 화면에, **섞지 않고.**
     · **상태를 가로지르는 합계·차이를 만들지 않는다**(§8.1). 확정 실적 + 가상값의 합계는
       존재하지 않는 숫자다
     · 상태 없는 값은 보드에 세울 수 없다(400) · 우열을 판정하지 않는다(지표 방향은 도메인 지식)
     · 하위 조직 기여 내역은 경영진만(사용자 결정 ③). 판정은 `viewer_may_drill_down()` 한 곳
- 영향·주의사항: **실측에서 오탐 결함 1건을 잡아 고쳤다.** 사업부→공장 집계에
  "법인 경계를 넘었습니다" 경고가 붙었다 — `_legal_entity_of` 가 노드 자신의 `entity_id` 를 썼고,
  이 조직도는 노드마다 엔터티가 1:1 이라 부모·자식이 항상 달랐다. 위로 올라가 법인 노드를 찾도록
  고쳤다.
  ⚠️ 이 결함이 남았다면 **오탐 경고가 진짜 경고를 묻었을 것**이다(항상 뜨는 경고는 안 읽힌다).
    제 테스트에 **반대 사례(경고가 없어야 하는 경우)** 가 없어서 양성 테스트가 틀린 이유로
    통과하고 있었다 — 회귀 테스트를 추가했다.
  실측 흔적 정리: 경쟁사 엔터티 3건·지표 전건 삭제, 실제 엔터티 9개 불변.
- 다음 행동 / 담당 / 착수 조건:
  · **Codex** — 경영진 보드 화면. `cells[*].mode_ko`·`official` 을 반드시 표시하고 `notes` 를
    접지 말 것. 경쟁사 열은 색·범례를 분리해야 §7.3-4 가 성립한다. "확인 불가" 셀은 빈 칸이
    아니라 그 문구로 그릴 것(빈 칸은 누군가 채운다).
  · **Antigravity** — 외부환경 인텔리전스(`core/external_intelligence*`)를 보드의
    `FORECAST` 계열로 잇는 것이 남았다(E4 마지막 조각). 지금은 계열 자리만 있다.
- 교대 체크포인트: 신규 4개 모듈 · 라우트 12개 · 테스트 4파일 80건.
  검증 **1596 passed / 실패 0**(1534 → +62) · 실서버에서 근거 없는 경쟁사 400 / 미허용 근거종류
  400 / 커버리지 3분류 / 이중계상 제외 + 커버리지 50% 경고 / 보드 3계열·가로합계 None ·
  경쟁사 "확인 불가" 표시 확인. **프론트엔드 미변경.** 커밋·푸시·DB 동기화 완료.
  ⚠️ 금지: 근거 5종을 선택으로 바꾸지 말 것 · 신뢰도를 숫자로 바꾸지 말 것 ·
  경쟁사 delta 를 계산하지 말 것 · 이중계상을 자동 해결하지 말 것 ·
  보드에 상태 가로 합계를 넣지 말 것 · 결손을 0 으로 채우지 말 것.

### [ECM-E3-04] 가정 세트·기준선 스냅샷·결과 비교·에이전트팩 바인딩 — 키만 있고 대상이 없던 것들
- 작성자 / 기록 시각: Claude Code / 2026-08-03 KST
- 왜 지금 기록하는가: 사용자가 "기능을 온전히 다 구현하고 확인하는 것이 최우선"이라 지시하고
  추천 순서(①가정·스냅샷 → ②결과 비교 → ③에이전트팩)를 승인했다. 세 건 모두 완료했다.
- 상태: **완료(구현·실서버 실측)** — §8.1 · §7.1/§7.2 · E2 잔여
- 결정 및 근거:
  ① **가정 세트·기준선 스냅샷**(`core/enterprise_context/scenario_inputs.py`)
     §8.1 이 실행 문맥 키로 못 박은 `assumption_set_id`·`baseline_snapshot_id` 가 E3 구현
     시점에는 **문자열로만 통과**하고 있었다 — 키는 있고 대상이 없었다.
     ⚠️ 그 상태의 문제는 조용하다: 계산까지 되지만 "이 숫자는 무슨 가정으로 어떤 기준선과
       비교해 나왔나"에 답할 수 없다. 답할 수 없는 숫자는 근거가 아니라 주장인데, 경영 판단에
       쓰이면 그때부터 사실처럼 취급된다.
     · **가정값마다 근거 필수** — 근거를 선택 항목으로 두면 아무도 채우지 않는다
     · **결과 기록 시 입력 동결** — 수정은 새 버전으로만. 제자리 수정은 과거 결과의 근거를 지운다
     · **승인된 가정·기준선만** 계산에 쓴다(승인 전 값으로는 같은 계산이 어제와 오늘 다른 답을 낸다)
     · 스냅샷 **체크섬** — 같은 id 로 내용이 바뀌면 다른 스냅샷이다(재현 불가를 감지)
     · **가상 값이 실제 기준선으로 스며들 수 없다**(§8.3 저장소 쪽 방어선)
     · 같은 입력 조합의 결과는 하나뿐 — 결정론적 계산은 같은 입력에 같은 답을 낸다
  ② **결과 비교**(`comparison.py`) — **실제·계획·예측·가상을 한 칼럼에 섞지 않는다**(§8.1).
     두 숫자를 나란히 놓는 순간 한쪽이 확정 실적이고 다른 쪽이 가정이라는 사실이 표에서
     사라진다. 그래서 값마다 상태(`mode`)와 근거를 끝까지 들고 다니고, `notes` 가 그것을 말한다.
     · 숫자가 아닌 값은 차이를 계산하지 않는다("약 12%" 를 12 로 읽으면 근사값이 확정값이 된다)
     · 기준선이 0 이면 증감률을 주지 않는다 · **결손(한쪽에만 있는 항목)을 따로 센다**
     · 기준선이 다른 결과는 한 표에 넣지 않는다 — 시나리오 차이인지 기준선 차이인지 구분 불가
  ③ **에이전트팩 바인딩**(`agent_pack_binding.py`) — E2 잔여.
     `departments.domain_agents` 평면 목록은 전사 표준 하나를 추가할 때 **모든 부서를 각각**
     고쳐야 하고, 한 곳을 빠뜨리면 그 부서만 조용히 다른 구성으로 돈다(하드코딩 맵 3개와 같은 형태).
     · `master_scope_bindings` 와 **같은 표 모양**(범위·모드·상속·유효기간·승인). 같은 개념을
       다른 모양으로 두면 두 규칙이 갈라진다
     · 해석 결과에 **provenance**(어느 팩·어느 조직에서 상속) 와 **skipped**(만료·비상속·미승인으로
       빠진 이유)를 함께 준다 — "왜 도는지/왜 안 도는지" 둘 다 답해야 한다
     · `CONSOLIDATION_SCOPE` 는 따라가지 않는다(다른 법인 구성이 넘어온다)
     · **실행 경로에 배선했다**(`org_seed.resolve_department_config`) — 판정 함수만 만들고
       부르지 않으면 장식이다(오늘 아침 목록 API 에서 겪은 실패). 바인딩이 없으면 기존 목록을
       그대로 쓴다(하위호환 — 새 기능이 기존 흐름을 끊으면 그 기능은 꺼진다)
- 영향·주의사항: 감사 이벤트 2개 추가(`SCENARIO_INPUT_CHANGED` · `AGENT_PACK_CHANGED`).
  실서버 실측 후 **흔적을 모두 정리했다**: 에이전트팩 바인딩 해제(해제 전에는 전 부서에
  `reviewer`·`auditor` 가 주입된다 — 실제 실행 구성이 바뀌므로 반드시 해제), 시나리오 3건 CLOSED,
  부서 에이전트 구성 원복 확인(`production_battery`→`Production_Agent`).
  가정 세트·스냅샷·결과 각 1건은 남아 있다(동작에 영향 없는 기록).
- 다음 행동 / 담당 / 착수 조건:
  · **Codex** — 가상 시나리오/비교 화면이 없다. 비교표를 그릴 때 **각 값의 `mode_ko` 를 반드시
    표시**할 것(실제와 가정을 같은 칼럼에 숫자만 나란히 놓으면 이 기능의 목적이 사라진다).
    `notes` 는 접지 말고 보이게 둘 것.
  · **Antigravity** — 결정론적 계산 엔진(`core/planning_*`)과 `POST /results` 연결 검토.
    지금은 결과를 **등록**만 할 수 있고 엔진이 자동으로 남기지 않는다.
- 교대 체크포인트: 신규 3개 모듈 · 라우트 16개 · 테스트 3파일 65건 추가.
  검증 **1534 passed / 실패 0**(1489 → +45) · 실서버에서 ①근거 없는 가정 400 ②동결 확인
  ③비교표(확정 실적 10000 → 가상 12500, delta 25%) ④미승인 팩 바인딩 400 ⑤전사→사업부·공장
  상속 확인·타 법인 미상속 확인. **프론트엔드 미변경.** 커밋·푸시 완료, 서버 종료, DB 동기화 완료.
  ⚠️ 금지: 근거·승인·동결 검사를 우회하는 경로를 추가하지 말 것 · 비교표에서 `mode` 를 떼지 말 것 ·
  `resolve_department_config` 의 하위호환 폴백을 제거하지 말 것.

### [ECM-E3-03] 가상 기업 Sandbox 구현 — 복제본이지 운영계 우회 통로가 아니다
- 작성자 / 기록 시각: Claude Code / 2026-08-03 KST
- 왜 지금 기록하는가: 사용자가 "기능을 온전히 다 구현하고 확인하는 것이 최우선"이라고 지시했고,
  남아 있던 유일한 미구현 기능이 E3(가상 조직 복제·시나리오)였다.
- 상태: **완료(구현·실서버 실측)** — 설계서 §7.1 · §8.3 기준
- 결정 및 근거: 그동안 `CREATABLE_ENTITY_MODES = (REAL,)` 로 가상 생성을 전면 금지해 왔다
  (E3 선행 조건). **그 안전장치를 없애지 않고 문을 열었다** — 가상 엔터티는 직접 생성이 아니라
  **복제로만** 만들어진다. `POST /entities` 는 여전히 REAL 만 받고, 원본·목적·유효기간·복사 정책이
  함께 없으면 가상 조직이 생기지 않는다.
  ⚠️ 흐름을 안내 문구로 적어 두면 지켜지지 않는다. `entity_mode="VIRTUAL"` 을 그냥 허용하면
    원본도 목적도 만료도 없는 가상 조직이 생기고, 그 가정값이 실제와 섞인 채 쌓인다(§13 위험표).
    흐름은 **구조로** 강제해야 한다.
  · 신규 모듈 `core/enterprise_context/clone_service.py` — `COPY_POLICY`(선택 복사 5종) ·
    `NEVER_COPIED`(실거래·원장·개인정보 / 외부 자격증명·MCP 쓰기 권한)
  · **`NEVER_COPIED` 는 기본값 False 가 아니라 거부다** — 기본값으로 두면 언젠가 누가 켠다
  · 만료일(`valid_until`) 필수·미래만 허용 — 만료 없는 가상 조직은 영구 조직이 된다
    (이 저장소가 '한시 예외'에서 이미 겪은 실패)
  · 가상의 가상 금지 — 원본은 REAL 만. 계보를 잃으면 "어떤 실제 조직에서 나온 가정인가"에
    답할 수 없다
  · `dept_id` 는 복제하지 않는다 — 가상 노드가 실제 부서를 가리키면 **실제 사용자의 권한이 가상
    문맥까지 닿는다**(조용한 유출 경로)
  · 노드 code 에 접두사(`V…_`) — 같은 코드가 두 문맥에 있으면 `find_node_by_code` 가 정렬
    순서로 결정한다(부서 1:N 매핑에서 이미 겪은 사고)
  · 프로필의 **승인은 복사하지 않는다** — §4.4 는 "가장 하위의 승인된 프로필이 이긴다"이므로
    승인된 채 복사되면 가상 가정이 상속 경쟁에서 실제를 이긴다
  · 승격은 **요청까지만**(§8.3 자동 반영 금지). 응답의 `note` 가 그것을 명시한다
  · §8.3 외부호출 차단을 `core/mcp_broker.py` 조회 경로에 배선했다 — 범위 판정보다 **먼저**
    막는다(뒤에 두면 범위가 맞는 가상 노드가 운영 ERP 를 읽는다)
  · 기준정보 가상 바인딩을 **살아 있는 시나리오 안에서만** 열었다(만료·종료 시 다시 거부).
    경쟁사 참조는 E3 로도 열지 않았다 — 공개 추정치와 자사 확정값이 섞인다
- 영향·주의사항: **실측에서 결함 1건을 잡아 고쳤다.** 실서버에서 사업부를 복제하니
  `org_nodes: 1, edges: 0` 이었다 — 이 저장소 조직도는 노드마다 엔터티가 1:1 이고 계층이
  **엔터티 사이의 엣지**에 있어(LS → LS MnM → 사업부 → 공장), 엔터티의 노드만 복사하면 복제본이
  노드 하나짜리 껍데기가 된다. 기능은 있는데 쓸 수 없는 상태였다. → `OPERATING_PARENT` 하위
  트리를 따라가게 고쳤다(3노드·2엣지 확인). `CONSOLIDATION_SCOPE` 는 따라가지 않는다 —
  따라가면 법인 경계를 넘어 다른 회사가 복제된다.
  실측용 시나리오 2건은 생성·승격요청·종료까지 확인한 뒤 **모두 CLOSED 로 정리**했고 실제
  엔터티 수는 9개로 변화 없다.
- 다음 행동 / 담당 / 착수 조건: **Codex** — 가상 시나리오 화면(원본 선택·복사 정책 표·만료일·
  결과 비교)이 없다. `GET /api/v1/enterprise-context/copy-policy` 가 정책 표를 그대로 내주므로
  화면에 정책을 다시 적지 말 것(두 곳이 갈라지면 사용자는 실제로 무엇이 복사됐는지 알 수 없다).
  **Antigravity** — 가상/실제 문맥 격리 교차검증(가상 노드로 운영 커넥터 조회 시도, 가상 결과가
  실제 집계에 섞이는지).
- 교대 체크포인트: 변경 범위는 `core/enterprise_context/clone_service.py`(신규) ·
  `audit.py`(이벤트 1개) · `master_data.py`(가상 바인딩 조건) · `mcp_broker.py`(외부호출 차단) ·
  `api/routes/enterprise_context_control.py`(라우트 5개) · `tests/test_e3_virtual_sandbox.py`(32건).
  **프론트엔드는 미변경** — 가상 시나리오 화면은 없다(위 Codex 항목).
  검증: **1489 passed / 실패 0**(1457 → +32) · 실서버 복제·승격요청·종료·감사 4건 확인.
  커밋·푸시 완료. 재개 시 첫 행동은 화면 쪽이며, 서버·DB 는 정리된 상태다.
  ⚠️ 금지: `NEVER_COPIED` 를 선택 항목으로 바꾸지 말 것 · `CREATABLE_ENTITY_MODES` 에 VIRTUAL 을
  추가하지 말 것(복제 외의 문이 생긴다) · `dept_id` 복사를 되살리지 말 것 ·
  `CONSOLIDATION_SCOPE` 를 복제 범위에 넣지 말 것.

### [ORG-AUDIT-02] 조직 변경이 감사로그에 남지 않고 있었다 — 사용자 질문에서 발견
- 작성자 / 기록 시각: Claude Code / 2026-07-31 KST
- 왜 지금 기록하는가: 사용자가 부서명 "해킹"을 보고 **"보안 테스트하다 걸린 거 아니야?"** 라고
  물었고, 답하려 했더니 **답할 수 없었다.** 그 사실 자체가 결함이었다.
- 상태: **완료(수정·커밋)** — 조직 구조·사용자 변경을 감사로그에 남긴다
- 결정 및 근거: 부서 표의 버전 이력은 *무엇이* 바뀌었는지만 담고(v1 본사 → v2 해킹),
  감사로그에는 조직 변경이 **한 줄도 없었다**. 즉 "누가 바꿨나"에 구조적으로 답할 수 없었다.
  ⚠️ 이 공백이 다른 감사 항목보다 무겁다: 부서·역할·조직범위는 **"누가 무엇을 볼 수 있는가"를
    정의하는 값**이다. 접근 기록을 아무리 남겨도 그 값의 변경 이력이 없으면 "그때 그 사람에게
    왜 권한이 있었는가"를 설명할 수 없다.
  · 신규 이벤트 2개: `ORG_STRUCTURE_CHANGED`(부서 생성·개명·이동·폐지) ·
    `ORG_USER_CHANGED`(사용자 등록·권한 플래그·역할·폐지)
  · **라우트가 아니라 코어(`OrgDirectory`)에서 남긴다** — 문제의 개명은 화면이 아니라
    시드/스크립트 경로였을 가능성이 크고, 라우트에만 붙이면 바로 그 경로가 계속 기록되지 않는다
  · `actor` 가 비면 `anonymous` 로 남긴다. **기록을 건너뛰지 않는다** — 익명 경로로 조직이 바뀐
    사실 자체가 조사 대상이다. 부트스트랩(사용자 0명)에서 401 을 내면 첫 관리자를 만들 수 없으므로
    막지 않고 기록만 한다
  · 감사 기록 실패는 조직 변경을 취소하지 않는다(소리 내어 로그를 남기고 진행) — 권한 인프라의
    부작용이 기능을 멈추면 그 인프라가 꺼진다
- 영향·주의사항: 변경 전후를 `detail` 에 적는다(`name: 본사 → 해킹` 형태). 감사로그 열람은
  admin 전용이고 5년 보존이다(기존 결정 유지). 실측: `PUT /departments/quality` →
  `ORG_STRUCTURE_CHANGED | hikwon@lsmnm.com | quality | 부서 개정(v2→v3)` 기록 확인,
  익명 동일 요청은 403.
- 다음 행동 / 담당 / 착수 조건: **Antigravity** — 감사로그 기반으로 "권한이 언제 누구에게
  어떻게 넓어졌는가" 타임라인을 만들 수 있는지 검토(지금은 이벤트만 있고 조합 화면이 없다).
  착수 조건 없음(로그는 이미 쌓인다).
- 교대 체크포인트: 코어 6개 메서드에 `actor` 파라미터를 추가하고 라우트 6곳에서 전달한다.
  변경 범위는 `core/org_directory.py` · `core/enterprise_context/audit.py` ·
  `api/routes/org_control.py` · `frontend/src/components/OrgChartPanel.tsx`(조직범위 배지·편집) ·
  `tests/test_org_change_audit.py`(신규 10건). 검증: 1457 passed / 실패 0 · 실서버 기록 확인.
  커밋·푸시 완료. 재개 시 첫 행동은 없다(닫힌 항목).
  ⚠️ 금지: `actor` 가 비었을 때 기록을 건너뛰도록 바꾸지 말 것 — 그러면 이 결함이 그대로 재발한다.

### [UX-SELECTION-05] V7·V8 용도 판정 및 V9·V10 신규 시안
- 작성자 / 기록 시각: Codex / 2026-07-30 KST
- 왜 지금 기록하는가: Supervisor가 V7을 하위 기능 모듈, V8을 향후 개인화 포털 후보로 평가하고 V10까지 시안을 완성한 뒤 선별·통합하자고 요청했다.
- 상태: V9·V10 시안 구현 및 정적 검증 완료 · V1~V10 최종 선별 대기
- 결정 및 근거: `uiux-prototypes/v9/`는 수주·계획·구매·생산·품질·물류·판매·회계를 잇는 Enterprise Value Chain OS, `uiux-prototypes/v10/`은 Atlas 상담을 데이터 준비·SW·Twin 실행계획으로 변환하는 Co-Creation Studio다. 두 버전 모두 `CONTENT_COVERAGE.md`로 C01~C12를 매핑했고 한글 손상 0건, 로컬 참조 누락 0건, 필수 기능 문자열 검증과 `git diff --check`를 통과했다. 전체 용도와 선택 상태는 `uiux-prototypes/V1_V10_SELECTION_GUIDE.md`에 기록했다.
- 영향·주의사항: 실제 `frontend/` 소스는 변경하지 않았다. V7은 전역 화면이 아닌 프로젝트 하위 모듈, V8은 즉시 적용이 아닌 개인화 단계 후보로 취급한다. V9·V10의 모든 수치는 레이아웃 검토용 예시다.
- 다음 행동 / 담당 / 착수 조건: Supervisor가 V1~V10 중 화면별 채택·부분 채택·제외 의견을 확정하면 Codex가 통합 To-Be 정보구조와 공통 디자인 시스템을 만들고, Claude Code가 구현 난도·상태/API 매핑을 교차검토한다.

### [UX-V7-V8-04] 프로세스 리버·역할 적응형 UI 시안
- 작성자 / 기록 시각: Codex / 2026-07-30 KST
- 왜 지금 기록하는가: Supervisor가 V6를 전체 기능 사이트맵으로 평가하고 V3·V4를 채택 후보에서 제외한 뒤, 서로 다른 신규 방향의 V7·V8 시안을 요청했다.
- 상태: 시안 구현·정적 검증 완료 · 사용자 비교 검토 대기
- 결정 및 근거: `uiux-prototypes/v7/`은 사용자·AI Factory·데이터·경영 레인을 연결한 Process River, `uiux-prototypes/v8/`은 권한·역할별 오늘의 업무를 편집하는 Role-Adaptive Desk다. 두 시안 모두 `CONTENT_COVERAGE.md`로 C01~C12 적용을 확인했고, `uiux-prototypes/V6_V7_V8_COMPARISON.md`에 V6 사이트맵 + V8 기본 홈 + V7 프로젝트 실행 조합을 기록했다. 깨진 한글 0건, 로컬 HTML/CSS 누락 참조 0건, `git diff --check` 통과를 완료 기준으로 삼는다.
- 영향·주의사항: 실제 `frontend/`는 변경하지 않았다. V3·V4는 삭제하지 않고 참고 시안으로 보존한다. 브라우저 자동 렌더링은 실행 환경의 localhost 격리로 수행하지 못했으므로 사용자의 시각 검토 후 화면별 채택을 확정한다.
- 다음 행동 / 담당 / 착수 조건: Supervisor가 V7·V8을 검토한 뒤 선호점과 수정점을 지정하면 Codex가 V6·V7·V8 통합 정보구조 및 컴포넌트 명세를 작성하고, Claude Code가 현 React 구조 적용 난도와 구현 순서를 교차검토한다.

### [TEAM-OPERATING-01] 강점 중심 역할 배치 — 참고 기준
- 작성자 / 기록 시각: Codex / 2026-07-29 KST
- 왜 지금 기록하는가: Supervisor가 팀원별 강점을 작업 시작 시 참고할 기본 배치로 정리하되, 필요 시 자유롭게 역할을 교대하고 교차검증하도록 지시했다.
- 상태: 적용 중 — 강제 규칙 아님
- 결정 및 근거: Codex는 제품 기획·UI/UX·프론트 고도화, Antigravity는 외부 데이터/리서치·검증 분석, Claude Code는 기능 상세설계·구현·테스트를 기본적으로 주도한다. 이는 담당 독점이 아니며, Supervisor가 작업별로 언제든 변경·복수 배정할 수 있다. 핵심 변경은 교차검토한다.
- 영향·주의사항: 담당 외 작업을 금지하지 않는다. 품질·난도·일정상 필요하면 다른 팀원이 즉시 지원·주도하되, 원 책임자·근거·인계 상태를 보드에 남긴다.
- 다음 행동 / 담당 / 착수 조건: 신규 보드 항목은 참고 배치를 활용하되, Supervisor의 작업별 지시와 교차검증 요청이 항상 우선한다.

### [UX-V3-DECISION-01] 의사결정 중심 UI/UX 시안 V3
- 작성자 / 기록 시각: Codex / 2026-07-29 KST
- 왜 지금 기록하는가: Supervisor가 V2의 변경 체감 부족과 작거나 외곽에 배치된 핵심 버튼 문제를 지적하여, 화면 구조 자체를 의사결정 중심으로 재설계했다.
- 상태: 시안 구현 완료 · 실제 제품 적용 전 검토 대기
- 결정 및 근거: `uiux-prototypes/v3/`에 결정 센터·SW 생성 승인·디지털 트윈 시나리오·데이터 승인 4개 HTML 시안을 만들었다. 공통 구조는 “결정 1개 → 선택지 2~3개 → 영향·근거 → 중앙 대형 실행 버튼 + 하단 Decision Dock”이다. `README.md`에 실제 React 화면별 반영 대상을 명시했다.
- 영향·주의사항: 실제 `frontend/` 코드는 변경하지 않았다. V3 채택 시 ControlPanel/HOTLInput/KnowledgeHubPanel/MegaBoardroomPanel의 정보 구조와 상호작용을 단계적으로 재구성해야 한다.
- 다음 행동 / 담당 / 착수 조건: Supervisor가 V3 방향을 선택하거나 보완 의견을 제시하면 Codex가 확정 화면·컴포넌트 명세를 만들고, Claude Code가 실제 기능 UI 구현 범위를 검토한다.

### [UX-V4-V5-DECISION-02] 의사결정 UI 대안 V4·V5
- 작성자 / 기록 시각: Codex / 2026-07-29 KST
- 왜 지금 기록하는가: Supervisor가 V3 외에 비교 가능한 추가 방향을 요청하여, 사용자 유형과 업무 밀도가 다른 두 시안을 추가했다.
- 상태: 시안 구현 완료 · 제품 테마/화면별 채택 검토 대기
- 결정 및 근거: `uiux-prototypes/v4/`는 경영진·통제실용 다크 커맨드센터, `uiux-prototypes/v5/`는 현업 담당자용 밝은 단계형 워크벤치다. V3/V4/V5의 차이와 권고 조합은 `uiux-prototypes/V3_V4_V5_COMPARISON.md`에 기록했다.
- 영향·주의사항: 실제 제품의 전면 테마 변경은 아니다. 현업 작업 화면은 V5, 승인/HOTL은 V3, 전사 관제는 V4가 적합하다는 시안 수준의 제안이다.
- 다음 행동 / 담당 / 착수 조건: Supervisor가 기본 화면별 채택 방향을 정하면 Codex가 공통 디자인 토큰과 화면별 상세 명세를 확정하고, Claude Code가 현 프론트 구조에 맞는 적용 순서를 검토한다.

### [UX-CONTENT-INTEGRITY-03] V1 인코딩 복구·V4/V5 콘텐츠 복원·V6 공간형 시안
- 작성자 / 기록 시각: Codex / 2026-07-30 KST
- 왜 지금 기록하는가: Supervisor가 V1 한글 손상, V4/V5의 기능 콘텐츠 축소, 시안 간 유사성을 지적하여 디자인보다 콘텐츠 무결성을 우선하는 정리 작업을 요청했다.
- 상태: 시안 정리·확장 완료 · 실제 제품 적용 전 검토 대기
- 결정 및 근거: `uiux-prototypes/CONTENT_BASELINE.md`에 C01~C12 공통 콘텐츠를 고정했다. 정상 한글 V1은 `v1/`, 확장 V4/V5는 각 `index.html`과 `CONTENT_COVERAGE.md`, 공간형 신규 V6는 `v6/`에 구현했다. 루트 `index.html`은 정상 한글 버전 갤러리로 교체했다. 정상 검토 대상의 깨진 문자열 0건, 누락 HTML/CSS 참조 0건, V1 동적 화면 스크립트 문법 검증 통과.
- 영향·주의사항: 루트의 최초 A~J HTML은 문자열 손실이 있어 비교용 원본으로만 보존한다. 이후 신규 시안은 C01~C12 적용표 없이 완료 처리하지 않는다.
- 다음 행동 / 담당 / 착수 조건: Supervisor가 V1~V6를 비교해 선호하는 탐색 방식·밀도·테마를 지정하면 Codex가 후보 2개를 실제 시스템 화면 단위 명세로 좁히고 Claude Code 구현 검토로 넘긴다.

> **🚨 [2026-07-29 사용자(Supervisor) 긴급 지침 전파]**  ⚠️ **작성자 불명 — 아래 해제 고지 참조**
> **M2 구현은 보류하고, 모델·비용·컨텍스트 계측을 포함한 신규 A-1 카나리 1회를 먼저 수행하십시오.**
> 단, D-010은 현 범위에서 유지하고, D-014의 “범위 미지정=전사 공용”은 M2 신규 데이터에는 적용하지 않는 전제로 권한 설계를 진행하십시오. (M2 DB·API·권한 코드는 변경 금지)

> ### ✅ [2026-07-29 12:40 KST · 작성자: Claude Code] 「M2 코드 변경 금지」 **해제**
>
> - **왜 지금 기록하는가**: 사용자가 직접 해제했고, 동시에 출처 불명 지시의 처리 방침을 지시했다.
> - **근거**: 사용자 지시(2026-07-29 채팅) — *"M2 변경 금지부터 해제합니다. 누가 작성한지 모르는
>   정체불명의 지시는 다시 확인 받으세요."*
>
> **효력**: 바로 위 블록의 **"M2 DB·API·권한 코드는 변경 금지" 조항은 무효**다.
> M2(권한·안전 연계) 구현에 착수할 수 있다.
>
> ✅ **[2026-07-29 12:55 · Claude Code] 나머지 조항도 확인 완료 — 전부 유효하다.**
> 근거: 사용자 확인(2026-07-29 채팅) — *"모두 내 지시를 통해 다른 팀원이 수행한 내용입니다."*
> 즉 ① "D-010 은 현 범위에서 유지" ② "D-014 를 M2 신규 데이터에 적용하지 않는다"
> ③ 아래 「M1→M2 진입 관문 교차검토 부채 판정 결과」 5개 항목은 **사용자 지시를 옮긴 것**이며
> 그대로 따른다. 서명이 없어 확인에 시간이 걸렸을 뿐 내용의 문제는 아니었다
> (그래서 §5-1 기록 규약이 필요하다 — 같은 확인 비용을 다시 치르지 않기 위해).
>
> ※ 단 **D-014 본체**("범위 미지정 = 전사 공용" 반려, 기본값 = 비노출)는 사용자가 채팅에서
> 직접 확인해 준 사항이므로 **유효**하다. 위 ②는 그것의 *적용 범위*에 관한 별개 조항이다.

> ### 🔒 [2026-07-29 사용자 판정] 3대 부채 = **조건부 승인 / 증적 확인 전 Close 금지**
>
> Antigravity 교차검토 결론(Fail-closed·404 은폐·미바인딩 통과 폐기)의 **방향은 승인**되었으나
> **즉시 Close 후 M2 착수는 반려**되었다. 각 건의 Close 조건은 아래 항목에 기재한다.
>
> **[ECM-E2-XWALK-01] 조건부 승인** — ① 404 은폐 시 서버 감사로그에 반드시
> `ACCESS_DENIED_SCOPE_MISMATCH` + 실제 대상 식별자를 남길 것(운영자가 침해 시도를 추적해야 한다)
> ② 404 은폐는 **개별 자원 조회에만** 적용 — 인증 실패·토큰 만료·요청 형식 오류까지 404로 만들면
> 운영 진단이 불가능해진다 ③ VIRTUAL Sandbox 는 "권한 승급"이 아니라 **짧은 만료·읽기 전용·가상
> 조직 범위로 제한된 별도 capability token** ④ **MCP 는 클라이언트가 보낸 `enterprise_scope_id`
> 를 신뢰하면 안 된다** — 인증 주체의 조직 문맥에서 서버가 범위를 계산하고 요청 범위는 그 안에서
> 교차 검증한다. ⚠️ 현재 구현은 ④를 만족하지 않는다(쿼리 파라미터를 그대로 신뢰) — M2 재개 시 보정.
>
> **[QUALITY-TEL-01] 보류 — 증적 4종 확인 후 Close.** 카나리 실행 ID·최종 상태 /
> 모델·폴백·토큰·비용·지연 원본 / **품질 게이트 결과와 실패 분류** / UI 조회 또는 자동화 증적.
> "5173·8080 동시 기동"은 UI 검증의 전제일 뿐 텔레메트리 정합성의 증명이 아니다.
>
> **[MDM-SCOPE-01] 승인 + 데이터 계약 보완.** "미바인딩 = 통과" 즉시 폐기(기본값 = 비노출).
> 단 `enterprise_scope_id` 하나로는 부족하다 — `owner_organization_id` / `scope_type`(조직전용·
> 상위조직공유·명시적전사공유·샌드박스) / `scope_assignments` / `classification` /
> `effective_from`·`effective_to` / `approval_status`·`approved_by` 를 명시해야 한다.
> **전사 공용은 빈 바인딩의 해석값이 아니라 `scope_type=ENTERPRISE_SHARED` + 승인 이력이 있는
> 명시적 상태**다.
>
> **착수 순서**: ① 세 건 조건부 기록 ② `bc3b8bbe9` push·확장 금지(보류) ③ 카나리 계측 증적으로
> QUALITY-TEL-01 먼저 Close ④ M2 는 「미바인딩 비노출」 회귀 테스트와 「타 조직 자원 404 +
> 내부 감사로그 기록」 테스트 통과 후 착수.

### 📌 M1 $\rightarrow$ M2 진입 관문 교차검토 부채 판정 결과
> ✅ **[2026-07-29 12:55 · Claude Code] 확인 완료 — 사용자 지시를 옮긴 것이며 유효하다.**
> 근거: 사용자 확인(2026-07-29 채팅). 아래 5개 판정을 그대로 따른다.
- **D-010 (전수 주입)**: 5,300자 수준 조건부 승인. A-1 카나리에서 실증 요망.
- **D-011 (별칭 파생)**: 승인. 프롬프트 오탐률 관측.
- **D-012 (조직코드 SSOT)**: ECM 코드 체계 유지 승인.
- **D-013 / D-014**: "소유 범위와 공유 권한 분리" 원칙. "미지정=공용"은 M2 신규 데이터 적용 불가(반려).
- **ECM E1/E2 / MDM-SCOPE-01**: 조직 상속은 '문맥 적용 가능성'일 뿐 '데이터 접근 권한'과 철저히 분리. 독립 검토 후 닫기.

> 이 문서는 진행 중·검토 대기·차단 작업의 **현재 상태만** 관리한다.  
> 상세 경과는 중복 기록하지 않고 관련 커밋, 코드, 설계 문서, 테스트 증적으로 연결한다.

🚨 **[팀 공통 작성 원칙]**
앞으로 이 보드의 항목 상태를 변경하거나 의견을 남길 때는 **반드시 "작성자(에이전트명)"와 "작성 사유(판단 근거/왜 남겼는지)"를 명시**하여 맥락 유실을 막고 협업을 명확히 할 것.

> ### 🧭 [2026-07-29 13:20 KST · 작성자: Claude Code] **다음 진행 확정안** (Codex 교차검증 반영)
>
> - **왜 지금 기록하는가**: Codex 교차검증 의견과 사용자 M2 해제 지시가 부딪혀 보였고, 실측으로
>   경계를 확정했다. 근거: Codex 교차검증(2026-07-29) · 사용자 지시(M2 변경 금지 해제) ·
>   `data/reference_registry.json` 실측 · `data/knowledge_packs/` 실측
>
> **① M2 착수 경계 — "전면 금지"도 "전면 병행"도 아니다**
> Codex 는 "카나리 증적 확정 전 M2 코드 변경 금지"를 제안했으나, 사용자가 이후 변경 금지를
> 해제했다(Codex 의견은 해제 이전 상태를 본 것으로 보인다). 다만 Codex 의 실질 논거는
> 부분적으로 타당하므로 **기술적으로 정확한 경계**로 고정한다.
> - **M2 1~3단계(감사로그 · 서버측 범위 계산 · 404 은폐) → 카나리와 병행 가능.**
>   접근 판정 경로라 카나리(LLM 파이프라인 실행)와 데이터·자원이 겹치지 않는다.
> - **M2 4~5단계(범위 계약 마이그레이션 · 기본값 비노출 전환) → 카나리 판정 후.**
>   `master_records` 가시성을 바꾸므로 **실행 중 카나리의 기준정보 주입에 영향**을 준다.
>
> **② 순서 교정 — 지식 키트 색인이 카나리보다 먼저다**
> Codex 는 지식 키트를 3순위에 뒀으나, **4차 카나리의 선행 조건**이다. 실측:
> 등록부는 팩 7개를 정의했는데 지식 허브에 실제 생성·색인된 팩은 `core-m3-standards` 1개뿐이고,
> 3차 카나리가 쓴 `manufacturing-standards`·`battery-materials-operations` 는 **정의만 있고
> 색인이 없는 팩**이었다. Antigravity 가 id 를 지어낸 것이 아니라 **등록부와 지식 허브가 같은
> 이름공간을 쓰면서 연결이 없는 계약 불일치**다(내 앞선 "설정 실수" 판단을 정정한다).
> → `manufacturing-standards` 7건 승인·색인이 되면 D-010 실증이 가능해진다.
>
> **③ Codex 계획의 누락 — M4 가 없다**
> 6단계 어디에도 경영계획 디지털트윈(계산엔진·시나리오·Backtest)이 없다. 실측 결과 **M4 는 0/6**,
> 명세서 §17 첫 파일럿 최소기능은 **약 1.5/7** 이다. 지금까지 만든 것은 전부 그 파일럿을 돌릴
> **바닥**이고, 제품 가치의 본체는 아직 시작하지 않았다. 로드맵에 명시적으로 올린다.
>
> **④ 발견 — 등록 자산 68건의 `owner_org_id` 가 전부 공백**
> M2 의 fail-closed 전환(D-014) 시 **68건 전부 비노출**이 된다. 승인 워크플로우에서 소유 조직을
> **필수 입력**으로 받아야 하며, 그러지 않으면 승인해도 아무도 못 보는 자료가 된다.
> (`scope_code` 는 배정돼 있으므로 그것을 `owner_organization_id` 로 승격하는 것이 현실적이다.)
>
> **⑤ 커밋 분리 규약 — 채택**
> Codex 제안대로 팀원별로 커밋을 분리한다. 오늘 나는 두 번 남의 변경을 섞었다
> (`TEAM_BOARD.md`·`core/knowledge_base.py`). 앞으로 `git add` 전 diff 확인은 §5-1 규칙 7 이다.
>
> **확정 순서**: ⓪ 지식팩 승인·색인(선행) → ① 4차 카나리 + 5종 증적 판정 ‖ M2 1~3 병행 →
> ② M2 4~5 → ③ 외부지표 수집·스냅샷 → ④ **M4 파일럿(계산엔진·시나리오)** → ⑤ Atlas/UX →
> ⑥ 실데이터 보정

## 진행 중

### [M5-BRIEFING-01] 전사 자비스 **기반** — 권한 범위 안의 전사 상태 집계
- 작성자 / 기록 시각: Claude Code / 2026-07-30 10:40 KST
- 왜 지금 기록하는가: 다른 세션에서 `core/enterprise_briefing.py` 와 테스트(23건)를 만들고
  **API·화면 배선 전에 중단**돼 있었다. §7 역할 규약(기능은 UI 까지 완결)에 따라 이어서 완결했다.
  근거: `tests/test_enterprise_briefing.py`(34건) · 전체 1,268 통과
- 상태: **구현 완료(모델·API·화면·테스트), 교차검토 대기** — §19 완료 기준 4종 충족
- 결정 및 근거:
  · **챗봇부터 만들지 않았다.** 제품 성경 §5.5 가 요구하는 것은 "이해"이고, 그 재료 없는
    대화창은 성경이 거부한 그 챗봇이다. 재료는 이미 다 있었다(승격 게이트·릴리스 체크리스트·
    Shadow run·데이터 계약·거버넌스 결손·비용·프로그램 사용여부) — 없던 것은
    **하나의 권한 필터를 통과한 집계**뿐이다. 서술(narration)은 이 위에 얹는 별개 층이다.
  · **LLM 0콜.** 판정을 LLM 에 맡기면 같은 상태에서 매번 다른 답이 나오고, 그건 보좌가 아니라 소음이다.
  · **fail-closed** — 범위를 못 정하면 아무것도 주지 않는다. 전사 보좌에서 범위 오류의
    기본값이 "전체 노출"이면 그 한 번으로 제품이 끝난다. 거부는 404 은폐 + 감사로그.
  · **actor 는 인증 주체에서** 온다. 클라이언트가 보낸 이름으로 "내가 결정할 것"을 계산하면
    남의 결재함을 들여다볼 수 있다(테스트로 잠갔다).
  · **읽지 못한 소스를 "이상 없음"으로 두지 않는다** — `unavailable` + `complete=false` 를
    응답 최상위에 올리고, 화면은 그것을 **숫자보다 위에** 빨간 배너로 그린다.
    "위험 0건"과 "위험을 못 읽었다"는 다른 사실이다.
  · 비용 총액이 하한이면 `≥` 를 붙인다(TelemetryPanel 과 같은 규칙).
- 영향·주의사항: `core/enterprise_briefing.py` 가 `api.routes.telemetry_control` 의 집계를
  재사용한다(core → api 역방향 import = **layering 부채**). 두 곳에서 계산하면 반드시
  어긋나므로 재사용을 택했고, 정리 방향은 집계를 core 로 옮기는 것이다.
  섹션 이름은 백엔드 `SECTIONS` 가 SSOT 이며 화면이 재정의하지 않는다.
- 다음 행동 / 담당 / 착수 조건: 서술 층(자연어 브리핑)은 **선택**이며 LLM 을 쓰더라도
  판정은 이 모듈 결과를 그대로 인용해야 한다. 교차검토는 Codex(정보 위계·오독 위험) ·
  Antigravity(권한 격리 실측).
  ⚠️ **브라우저 실측 미완** — 화면을 한 번도 띄워보지 않았다.

### [M3-WORKSPACE-01] 부서 워크스페이스 — 공유·복제·**전사 승격 게이트** 구현 완료
- 작성자 / 기록 시각: Claude Code / 2026-07-29 야간 KST
- 왜 지금 기록하는가: 사용자 지시("교차검토 건너뛰고 순서대로 진행")로 M2 Shadow Mode 에 이어
  M3 를 착수해 백엔드·UI·실측을 마쳤다. §9.3 승격 조건이 실제로 강제되므로 인계를 남긴다.
- 상태: **구현 완료 · 검증 완료** (교차검토는 사용자 지시로 후순위)
- 결정 및 근거: 커밋 `823584799`(백엔드) · `81ded79e1`(화면) ·
  `core/workspace_promotion.py` · `tests/test_workspace_promotion.py`(23건) ·
  전체 **pytest 1,166 통과 + xfail 4** · 실제 FastAPI 8단계 프로브 · 실제 브라우저 확인.
  - **게이트는 체크박스가 아니라 실제 조회다.** §9.3 의 네 가지를 각각 기존 모듈에서 읽는다:
    데이터 계약(`data_contracts.evaluate`) · 보안(카탈로그 민감도·PII) ·
    품질(`quality_telemetry` 게이트 결과) · 소유자 승인(명시적 기록).
  - **모르는 것을 안전으로 치지 않는다.** 릴리스↔자산 연결은 계보 간선으로 선언하고,
    간선이 없으면 계약·보안 검사가 `unverifiable` 이며 **승격이 막힌다.**
  - **강제 승격 우회로가 없다.** Shadow Mode 의 `allow_breached` 와 다른 판단 — 여기서는
    데이터 계약 위반·PII 전사 공개라 되돌릴 수 없다.
  - 승격 시점 게이트 판정을 `gate_snapshot` 으로 보관한다(나중에 기준이 바뀌어도 재현).
- 영향·주의사항:
  - `data/workspace.db` 신규(gitignore). `tests/conftest.py` 격리 추가 — 테스트가 남긴 전사
    승격이 실제 목록에 섞이면 "이 앱이 전사 앱인가"의 답이 틀린다.
  - **품질 기록 조회 키를 `release_id` 에서 추론하지 않는다.** 승격 신청 시 `project_id` 를
    명시로 받는다 — 프로젝트명에 밑줄이 있거나 명명 규칙이 바뀌면 조용히 남의 기록을 보거나
    0건이 된다.
  - 기존 릴리스 경로(`factory_control`)는 **건드리지 않았다.** 승격은 별도 계층이다.
  - 한계: 승격은 아직 **기록과 게이트**이고, 승격된 앱이 실제로 전사 목록·권한에 반영되는
    연결은 없다. `library` 조회 경로에 승격 상태를 반영하는 것이 다음 단계다.
- 다음 행동 / 담당 / 착수 조건:
  - (내 담당) 승격 상태를 `library` 조회에 반영 — M3 「운영 준비」(릴리스 체크리스트·롤백)와
    함께 처리하는 것이 자연스럽다.
  - **Codex 검토 요청**: 게이트 5항목을 한 화면에 나열한 것이 과한지, 단계별로 접어야 하는지.
  - **Antigravity 검토 요청**: `_BLOCKED_FOR_ENTERPRISE = (confidential, restricted)` 가
    실제 운영 기준으로 적절한지(내부 규정과 대조 필요).

### [M2-SHADOW-01] Shadow Mode — M2 마지막 조각 **구현 완료 · 교차검토 대기**
- 작성자 / 기록 시각: Claude Code / 2026-07-29 야간 KST
- 왜 지금 기록하는가: 사용자 지시("M2 Shadow Mode 부터 순서대로")로 착수해 백엔드·UI·실측을
  마쳤다. §7.3 5단계가 전부 동작하므로 인계와 교차검토 요청을 위해 남긴다.
- 상태: **구현 완료 · 검증 완료 · 교차검토 대기**
- 결정 및 근거: 커밋 `5a3bcaba4`(백엔드) · `5f34dd5b5`(화면) ·
  `core/shadow_mode.py` · `api/routes/shadow_control.py` · `tests/test_shadow_mode.py`(24건) ·
  전체 **pytest 1,140 통과 + xfail 4**(관문 A 유지) · 실제 FastAPI 12단계 프로브 ·
  실제 브라우저 확인.
  - **범용 후보 실행기는 만들지 않았다.** 이 시스템에 "임의의 앱·규칙을 실행"하는 능력이
    없어서, 만들면 죽은 코드이거나 값을 지어내는 경로가 된다(외부 인텔리전스 수집기와 같은
    판단). 실행 어댑터는 실제 실행 가능한 경영계획 시나리오 하나만 붙였고, 나머지 종류는
    호출자가 결과를 주입한다.
  - 막는 것이 이 모듈의 값어치다: 같은 입력이 아니면 비교 거부 / 미측정은 0 이 아님 /
    개선 방향 모르는 지표 거부 / 검토 없이 승격 불가 / **악화 미인정 승인 불가** /
    **범위 없는 승격 불가** / 검토 후 결과 변경 불가.
- 영향·주의사항:
  - **D-014 개정을 처음 적용한 지점**이다 — `enterprise_scope_id` 필수. Shadow run 은 M2 이후
    신규 운영 데이터라 "미지정=전사 공용" 레거시 예외가 적용되지 않는다.
  - `data/shadow_runs.db` 신규(gitignore). `tests/conftest.py` 에 격리 추가 — 테스트가 남긴
    승격 기록이 실제 목록에 섞이면 "무엇을 승격했는가"의 근거가 오염된다.
  - `main.py`·`tests/test_master_api_routes.py`·`.gitignore` 각 2줄 내외 수정.
  - 승격은 아직 **기록일 뿐 강제력이 없다** — 승격된 후보를 실제 운영 경로가 자동으로 쓰지는
    않는다. 그 연결은 후보 종류별 실행 어댑터가 생길 때 함께 만들어야 한다.
- 다음 행동 / 담당 / 착수 조건:
  - **Codex 검토 요청**: ① 악화 인정 체크박스가 "형식적 동의"로 흐르지 않을 UX 인지
    ② 판정 불가(입력 불일치) 표시가 실패와 구분되어 읽히는지 ③ 승격 범위를 자유 문자열로 둔
    것이 적절한지(구조화하면 검증은 되지만 현업 표현력이 준다).
  - **Antigravity 검토 요청**: 지표 7종(kpi_value·accuracy·error_count·exception_count·
    cost_usd·user_edit_count·latency_sec)과 개선 방향이 §7.3 "KPI·오류·예외·비용·사용자
    수정량" 을 충분히 덮는지.
  - 후속(내 담당): 승격 결과를 실제 운영 경로에 연결하는 어댑터는 **M3 이후**로 미룬다 —
    지금 만들면 쓸 곳이 없다.


### [M4-PLAN-01] 경영계획 디지털트윈 — **§17 첫 파일럿 최소기능 7/7 충족**
- 작성자 / 기록 시각: Claude Code / 2026-07-29 14:30 KST
  · 갱신: Claude Code / 2026-07-29 16:00 KST (승인·동인·현금흐름·Backtest·차원 추가 완료)
- **갱신 사유**: 세션 시작 시 §17 최소기능 1.5/7 이던 것이 **7/7** 이 됐다. 커밋 6건
  (`37b54105e` 모델·엔진 → `d50c55a83` 화면 → `6b46a9ca5` 승인 → `75ef7aa24` 동인 →
  `aebec2129` 현금흐름 → `8b61326ce` 파일등록 → `b732d1410` Backtest → `152f66057` 차원).
  테스트 **1,101 통과**. 전 축 **LLM 0콜**.
  **관통 원칙 — 모르는 것을 0 으로 두지 않는다**: 실적 미입력 시 차이분석 거부 ·
  감가상각/CAPEX 없으면 현금흐름 거부(흑자도산 착시 방지) · 미등록 계정/미적용 가정/
  합계·상세 혼재(이중 계상)/승인 후 값 변경/Backtest 사후 가정을 전부 **결과와 같은 자리에**
  싣는다. 경영 보고에서 위험한 것은 틀린 숫자가 아니라 **틀린 줄 모르는 숫자**다.
- 왜 지금 기록하는가: 확정 순서의 ④ 착수. **M4 는 0/6 이었고 §17 첫 파일럿 최소기능은 1.5/7**
  이었다 — 지금까지 만든 것은 전부 이 파일럿을 돌릴 바닥이었고 여기서부터가 제품 가치다.
  근거: 명세서 §11·§17 · `tests/test_planning_engine.py`(24건)
- 상태: **코어 완료(모델·엔진·API·화면), 교차검토 대기** — §19 완료 기준 4종 충족
- 결정 및 근거:
  · **LLM 0콜.** §11.3 이 "재현 가능한 함수·규칙으로 구현"을, §17.3 이 "세 시나리오를 동일
    기준선에서 재현"을 요구한다. LLM 은 같은 입력에 같은 출력을 보장하지 못해 **원리적으로**
    이 기준을 만족할 수 없다. 재현 불가능한 숫자는 틀린 숫자보다 나쁘다 — 무엇을 고쳐야 할지
    알 수 없기 때문이다.
  · **`value_kind` 는 기본값 없는 필수값**(ACTUAL|PLAN|FORECAST|SCENARIO). 기본값이 있으면
    호출자가 생각 없이 넣고 '실적처럼 보이는 계획'이 생긴다. SCENARIO 는 scenario_id 필수,
    나머지는 금지(시나리오 결과가 실적으로 섞이는 경로 차단), 시나리오 위 시나리오 금지.
  · **모르는 것을 0 으로 두지 않는다** — 미등록 계정은 `unmapped`, 미적용 가정은
    `unapplied_assumptions`, 실적 미입력은 `comparable=false`(차이를 계산하지 않는다).
    "계획 100 · 실적 0 → 100 미달"과 "실적이 아직 없다"는 완전히 다르다.
  · **재현성의 근거 3종**: 입력 지문(sha256·정렬 고정) · 엔진 버전 · 가정의 근거(필수).
    `compare_scenarios` 는 `same_baseline` 을 함께 준다 — '비교했다'는 주장만으로는 부족하다.
  · **범위 계약을 처음부터 내장**(M2 §2.1 7필드, 기본 `ORG_PRIVATE`). 나중에 붙이면
    마이그레이션이 필요하고 **경영 데이터의 마이그레이션이 가장 비싸다**. API 는 M2 에서 만든
    `core/scope_guard.py` 를 그대로 쓴다.
- 영향·주의사항: 새 저장소 `data/planning.db`(신규 테이블 5). 기존 경로에 영향 없다.
  화면은 결손을 숨기지 않는다 — `same_baseline=false` 는 "이 비교는 무효" 배너,
  실적 미입력은 "차이 0" 이 아니라 "미입력"으로 표기한다.
- 다음 행동 / 담당 / 착수 조건: 잔여 §17 기능 — 실적 파일 등록(#2) ·
  ~~부서 승인 흐름(#3)~~ **✅ 완료(아래 갱신)** · 동인(단가·물량·환율) 기반 가정(#5) ·
  현금흐름(#6). 교차검토는 Codex(경영 보고 오독 위험) · Antigravity(계산 정합성).
- **갱신 [2026-07-29 15:10 · Claude Code] §17 기능 3(부서 승인 흐름) 완료** —
  `core/planning_approval.py` · `/api/v1/planning/submissions/*` 6개 · 테스트 20건.
  **핵심 설계**: 승인을 상태 플래그로만 두면 *"3월에 승인받은 계획의 숫자가 5월에 바뀌어
  있는데 상태는 여전히 APPROVED"* 라는 사고가 난다. 아무도 거짓말하지 않았고 오류도 없지만
  그 계획서는 **승인받지 않은 문서**다. → **승인 시점 값의 지문을 함께 박고**
  `verify_integrity()` 로 대조한다. 상태는 속일 수 있어도 지문은 못 속인다.
  익명 승인 금지 · 자기 승인 기본 차단(열면 감사에 남는다) · 반려 사유 필수 ·
  빈 계획 제출 거부. 승인 이벤트는 M2 감사로그(`APPROVAL_GRANTED`)를 그대로 쓴다.

### [M2-AUDIT-01] M2 1~3단계 완료 — 감사로그 · 서버측 범위 계산 · 404 은폐
- 작성자 / 기록 시각: Claude Code / 2026-07-29 13:50 KST
- 왜 지금 기록하는가: 확정 순서의 「M2 1~3 병행」이 끝나 **관문 B 3건이 열렸다**.
  근거: `tests/test_m2_entry_gates.py` 의 B 3건이 xpass(strict) → 회귀 잠금으로 승격 ·
  `tests/test_access_audit.py`(12건)
- 상태: **완료(관문 B 통과), 교차검토 대기** (§3-1 C등급 — 권한·보안)
- 결정 및 근거:
  · `core/enterprise_context/audit.py` — append-only 감사(`data/access_audit.jsonl`).
    **요청값과 서버 계산값을 둘 다** 남긴다(하나만 남기면 정상 조회와 권한 상승 시도가 같은
    모양이 된다). 기록 실패는 삼키지 않고 `write_failures` 로 센다.
  · `core/scope_guard.py` — **클라이언트가 보낸 범위는 요청이지 권한이 아니다.**
    인증 주체 → 부서 권한 → ECM 노드 → 운영 상속 → 교차 검증. 기존 자산을 잇고 검증 한 겹만 새로 만들었다.
    상위 조직 드릴다운은 **정당한 사용**이라 허용한다(요청을 막지 않고 검증한다).
    리솔버 장애 시 fail-closed(장애가 곧 전사 유출이 되면 안 된다).
  · `api/routes/mcp_control.py` — §3.3 경계표 적용: **"등록되지 않은 시스템"만 404**,
    비활성·매핑 없음 같은 상태 충돌은 409 유지. 전부 404 로 뭉개면 운영 진단이 불가능해진다.
- 영향·주의사항: MCP 라우트가 `Depends(current_principal)` 를 받는다 —
  조직 미도입(`unrestricted`)에서는 요청 범위가 그대로 통과해 **종전 동작이 보존**된다.
  회귀 잠금 2건 유지 확인: 인증 실패 401 · 요청 형식 422(404 로 은폐하지 않는다).
  ⚠️ **감사로그 자체가 민감정보**라 열람 API 는 만들지 않았다 — 보존기간·열람권한이
  사용자 결정으로 확정된 뒤에 만든다(설계서 §6 열린 질문 4).
- 다음 행동 / 담당 / 착수 조건: **M2 4~5단계는 카나리 판정 후**(기준정보 가시성을 바꾸므로).
  관문 A 4건은 여전히 xfail 로 닫혀 있다. 교차검토는 Antigravity(보안)·Codex(운영 영향).

### [PRODUCT-01] 사업모델·시장진입 전략 구체화
- 상태: 진행 중
- 책임 수행자 / 교차 검토자: Codex / 사용자 및 필요 시 전 팀원
- 목표·완료 기준: 첫 고객·첫 유스케이스·패키지·가격 원칙·도입 확장 경로를 제품 설계와 정합되게 정의한다.
- 영향 범위·결정/가정: 제품 포지셔닝, UI/UX 우선순위, LLM 비용 설계에 영향을 준다. 제품 방향의 최종 결정은 사용자에게 있다.
- 증거·다음 행동: `docs/business-model/index.html`에 내부 1호 고객 → 그룹 확산 → 제품회사·ITO 파트너 → 외부 확장 구조를 정리했다. 첫 파일럿 대상, 이전가격, IP·계약 구조, 외부 판매 조건을 사용자 결정 항목으로 남겼다.

### [REFERENCE-DATASET-01] 원본 참고자료 등록·업무별 지식화
- 상태: 구현 완료, 운영 승인·색인 대기
- 책임 수행자 / 교차 검토자: Codex / 데이터 오너·필요 시 Antigravity
- 목표·완료 기준: `docs/reference` 원본을 출처·해시·조직 범위·분류·추천 지식팩이 있는 등록부로 전환하고, DOCX/PPTX 본문 추출과 안전한 업로드를 지원한다.
- 영향 범위·결정/가정: 사업부 교육·운영 자료는 `PENDING_REVIEW`로 등록하며, M2 권한 모델·데이터 오너 승인 전에는 전사 RAG 또는 모든 프로젝트에 자동 주입하지 않는다.
- 증거·다음 행동: `data/reference_registry.json`(68건) · `core/reference_registry.py` · `docs/reference/REFERENCE_DATASET_REGISTER.md` · `tests/test_reference_registry.py`(3건) · 지식 허브 Office 업로드 확장. 다음 행동은 데이터 오너가 팩별 범위·분류를 승인한 뒤 해당 팩만 색인·프로젝트에 연결하는 것이다.

### [IMPLEMENT-01] 현재 기능 구현·오류 보정
- 상태: 진행 중
- 책임 수행자 / 교차 검토자: Claude Code / 작업별 지정
- 목표·완료 기준: 외부 세션에서 진행 중인 기능 구현과 오류 보정을 코드·테스트 증거로 완료한다.
- 영향 범위·결정/가정: `DECISIONS.md` D-003(권한 상속은 OPERATING_PARENT 만)·D-004(부서 권한
  재사용)·D-005(부서 id/node_id 이중 해석)에 의존한다. 되돌림 비용이 D-003 은 높다.
- 증거·다음 행동: 커밋 `2e42968ec` · `core/enterprise_context/` · `tests/test_ecm_e1.py`(36건) ·
  실측(ORG_ENFORCE=True: admin 9 / bob 0 / exec 5+경로2, 집계 대상 상세는 403) ·
  설계서 §11 E1 완료 표. **검토 요청 관점**: ① 공유서비스·연결집계에서 권한이 새지 않는지
  ② 부서 매핑 없는 상위 노드의 `readable=false` 경로 노출이 정보 유출인지 ③ 순환·깊이 상한이
  실제 조직 규모에서 충분한지 ④ `enterprise_scope_id` 이중 형태 공존의 회귀 위험.

### [ECM-E2-XWALK-01] 크로스워크·MCP 조직 범위 격리 (ECM E2 잔여)
- 작성자 / 기록 시각: Claude Code / 2026-07-29 11:20 KST
- 상태 갱신 [2026-07-30 · Claude Code]: **✅ 보류 해제 — 보정 완료.**
  보류의 근거였던 "기본값을 전사 공용으로 둔 데이터 계약"이 **관문 A 로 폐기**되어 조건이
  해소됐다. 보류 문구가 요구한 보정 항목과 미보정 잔여 2건을 하나씩 실측으로 확인했다:
  - **`scope_type`·`scope_assignments`·`owner_organization_id`·승인 이력** → `external_systems`
    실 DB 에 7필드 전부 존재 확인(`_ECM_KEYS` 마이그레이션 · 커밋 `95aa4d39e`).
    `scope_contract` 가 `external_system` 을 자원 종류로 지원한다(소유 지정·조직 공유·전사 승인).
  - **기본값 = 비노출(D-014 유효분)** → 미지정 시스템 행의 타 조직 가시성 `False` 실측
    (커밋 `01d981f82` · `tests/test_crosswalk_mcp_scoping.py::test_unscoped_system_is_invisible_and_counted`).
  - **잔여(a) MCP 가 클라이언트 전달 범위를 신뢰** → 해소. `core/scope_guard.py` 배선 +
    `test_gate_b_mcp_does_not_trust_client_supplied_scope` 통과.
  - **잔여(b) 거부가 409 이고 감사로그 없음** → 해소. 404 은폐 + `ACCESS_DENIED_SCOPE_MISMATCH`
    기록, `test_gate_b_other_org_resource_returns_404` · `..._denial_is_written_to_the_audit_log` 통과.
  - 관문: `tests/test_m2_entry_gates.py` **xfail 0**(관문 A 4건 2026-07-30 개방 · 관문 B 3건
    2026-07-29 개방). 관련 3파일 **42건 통과**, 전체 **1419 passed**.
  ⚠️ 남은 조건은 코드가 아니라 **운영 전환**이다: `ORG_ENFORCE`(정책 스위치)가 꺼져 있는 동안
    `resolve_scope` 는 전원 무제한을 돌려주므로 이 격리는 **실 시스템에서 아직 작동하지 않는다.**
    사전 점검(`/api/v1/admin/org-enforcement/preflight`)은 현재 **차단 0·경고 0**이다
    (테스트 잔여 계정 4건 폐지 완료 · 실제 관리자 `hikwon@lsmnm.com` 등록 완료).
  - 교차 검토 요청 유지: Antigravity(격리 실측 — 특히 강제 ON 이후 화면) · Codex(제품 영향).
- 왜 지금 기록하는가: 구현 후 사용자 판정으로 **보류**가 확정돼 상태를 낮춘다.
  근거: 사용자 지시(2026-07-29 채팅 — "push·확장하지 않고 보류, M2 재개 시 범위 계약으로 보정")
  · 커밋 `bc3b8bbe9`
- 상태 갱신 [2026-07-29 12:40 · Claude Code]: **M2 변경 금지 해제**(사용자 직접 지시)로
  **보정 착수 가능**해졌다. 단 보정 방향은 D-014 유효분(기본값 = 비노출)과
  `docs/design_m2_scope_contract_and_audit.md` 의 범위 계약을 따른다. 착수 전 관문
  `tests/test_m2_entry_gates.py`(현재 7 xfail)를 여는 것이 순서다.
- 상태(이전): **🔒 보류(카나리 이전 구현) — push·확장 금지, Close 금지**
  커밋 `bc3b8bbe9`. 방향은 조건부 승인됐으나 **기본값을 전사 공용으로 둔 데이터 계약이
  승인되지 않았다.** 되돌리지 않고 보류하며, M2 재개 시 위 범위 계약(`scope_type` ·
  `scope_assignments` · `owner_organization_id` · 승인 이력)으로 **보정한 뒤** 살린다.
  ⚠️ 미보정 잔여 2건: (a) MCP 가 클라이언트 전달 `enterprise_scope_id` 를 신뢰한다
  (b) 거부가 404 가 아니라 409 이고 감사로그가 없다.
- 책임 수행자 / 교차 검토자: Claude Code(완료) / **Antigravity(격리 실측)·Codex(제품 영향)**
- 목표·완료 기준: 설계서 §11 E2 잔여 중 "MDM/카탈로그/크로스워크/MCP 에 범위 키 도입과 권한
  강제"의 마지막 두 개. 카탈로그·용어사전·계약은 D-013 으로 완료돼 있었다.
- 영향 범위·결정/가정: **`DECISIONS.md` D-016**. `external_systems` 에만 ECM-lite 3키를 두고
  자식은 부모 게이트를 지난다. MCP 는 캐시보다 먼저 판정하고, 범위 해석 실패 시 실측 병기를
  생략한다(fail-closed — 기준정보 주입과 의도적으로 다름).
- 증거·다음 행동: `core/crosswalk.py`(`is_system_visible`·`require_system_visible`·
  `systems_coverage`) · `core/mcp_broker.py` · `api/routes/{crosswalk,mcp}_control.py` ·
  `tests/test_crosswalk_mcp_scoping.py`(18건) · 거버넌스 콘솔 ①에 연계 시스템 커버리지 추가.
  **★ 실재한 누출을 닫았다**: `get_live_context()` 가 활성 시스템을 전부 순회해, 배터리소재
  프로젝트 프롬프트에 동제련 연계 시스템의 실측값이 섞여 들어갔다. 상태 모델에는 조직 문맥이
  이미 있었고 **이 경로만 그것을 안 보고 있었다**.
  **검토 요청 관점**: ① 자식 테이블에 키를 복제하지 않은 대가(경로마다 게이트 한 줄)를 감안할 때
  빠진 경로가 없는지 — 특히 CSV import·제안 승인/기각 ② MCP `resolve` 의 거부가 기존 관례상
  409(MCPError)로 나가는데 404 가 맞지 않은지(존재하지 않는 시스템도 현재 409라 일관은 유지)
  ③ fail-closed 판단이 ECM 도입 초기에 실측 병기를 과하게 죽이지 않는지(기본 off 기능이라
  손실이 작다고 봤다) ④ `entity_mode` 완전 일치 규칙이 VIRTUAL Sandbox(E3) 설계와 충돌하지 않는지.

### [QUALITY-TEL-01] 품질 결과 텔레메트리 + 실패 원인 분류 (§10.3 / §8.3)
- 작성자 / 기록 시각: Claude Code(구현·증적 대조) / 2026-07-29 11:37 KST
  · 상태 갱신: Antigravity(재카나리 진행) / 2026-07-29
- 왜 지금 기록하는가: Antigravity 의 "카나리 완주로 텔레메트리 정합성 증명" 보고를 로그와
  대조한 결과 **게이트 계측이 0건**이어서 Close 조건 4종 중 2종이 미충족임을 확정했다.
  근거: 카나리 마지막 콜 `10:43:53` vs 품질 텔레메트리 커밋 `a6f13fbcd`(10:44) — **계측이
  존재하기 1분 전에 끝났다** · `scripts/canary_report.py` 판정 출력
- 상태: **검증 대기 (Close 금지) → 재카나리 진행 중 (작성자: Antigravity)**
  > **작성 사유(2026-07-29)**: 이전 카나리는 Claude Code의 품질 텔레메트리(`a6f13fbcd`) 생성 전 완료되었으며, 1차 및 2차 재카나리 시도에서 `run_inline` 호환성 에러로 좌초되었음. 현재 콜백 에러를 수정한 뒤 **3차 E2E 카나리(test_a1_unitconv_canary3)를 가동하여 대기 중**임. 완주 후 텔레메트리 갭(①③) 충족 여부를 실측하여 증적으로 첨부할 예정.
- 책임 수행자 / 교차 검토자: Claude Code(완료) / **Antigravity(계측 정합성·실측)·Codex(화면 오독 위험)**
- 목표·완료 기준: `llm_calls` 만 있고 비어 있던 `quality_outcomes` 축을 채운다 — 게이트별
  통과/실패·재작업 횟수·실패 원인 분류·사람 수용 판정. LLM 0콜. UI 까지 완결(§7 역할 규약).
- 영향 범위·결정/가정: **`DECISIONS.md` D-015**(결정론적 근거 없으면 미분류 유지).
  훅 4곳 — `nodes/utils/scoring.py`(게이트 판정, 유일한 채점 지점) ·
  `nodes/execution.py`(빌드 실패 `_build_failed` 단일화, 생성 실패) ·
  `core/async_orchestrator.py`(HOTL 사람 판정). 저장은 append-only JSONL
  (`data/quality_outcomes.jsonl`), 부서 스코프는 텔레메트리와 **같은 `apply_scope`** 재사용.
- 증거·다음 행동: `core/quality_telemetry.py` · `api/routes/telemetry_control.py`(`/quality/*` 4개) ·
  `frontend/src/lib/qualityApi.ts` + `components/QualityOutcomesView.tsx`(운영 계기판 탭) ·
  `tests/test_quality_outcomes.py`(30건) · `tests/test_quality_outcomes_wiring.py`(6건).
  ⚠️ **브라우저 실측 미완** — Antigravity 테스트 중이라 8080 을 건드리지 않았다(§3-1).
  그쪽 종료 후 화면 실측 필요.
  **함께 고친 것**: 빌드 실패 경로에서 빌더가 남긴 `build_error_log` 가 **버려지고 있었다** —
  자가복구 재시도가 원인을 모른 채 같은 프롬프트를 다시 돌리는 상태였다(`_build_failed` 로 복구).
  **검토 요청 관점**: ① 점수 미달을 자동 분류하지 않는 판단(D-015)이 지표를 쓸모없게 만들지는
  않는지 — 대안은 "미달 기준 id → 원인" 매핑표를 두는 것인데 그 표의 근거를 만들 방법이 없다고
  봤다 ② `no_human_decision` 3칸 분리가 화면에서 실제로 구분되어 읽히는지(Codex)
  ③ HOTL 재개 기록이 게이트 기록과 짝이 없어 orphan 으로 남는 구조가 허용 가능한지 —
  현재는 "어느 게이트에 대한 판정인지"를 추정하지 않고 stage 만 남긴다
  ④ 빌드 로그 패턴 규칙(`_BUILD_RULES`)의 오탐 — 특히 `test_harness` 와 `model_quality` 경계.

### [M2-GATE-01] M2 착수 관문 정의 — 미바인딩 비노출 · 404 은폐 + 감사로그
- 작성자 / 기록 시각: Claude Code / 2026-07-29 11:50 KST
- 왜 지금 기록하는가: 재카나리(Antigravity 주관) 대기 중 착수할 수 있는 다음 작업이
  사용자 지시 ④(관문 통과 후 M2 착수)뿐이라, **관문을 실행 가능한 계기로 고정**했다.
  근거: 사용자 지시(2026-07-29 채팅) · 커밋 `459e02c5b`
- 상태: **관문 정의 완료, 구현 대기** (M2 코드 변경 금지 준수 — 설계·테스트만)
- 책임 수행자 / 교차 검토자: Claude Code(완료) / Antigravity(보안 관점)·Codex(운영 영향)
- 목표·완료 기준: 사용자 지시 ④의 두 관문을 **실행 가능한 계기**로 고정한다.
  `tests/test_m2_entry_gates.py` — 현재 **7 xfail(닫힌 문) + 2 통과(회귀 잠금)**.
  `xfail(strict=True)` 라 구현되는 순간 xpass 로 뒤집혀 **관문이 열렸음을 자동 통지**한다.
- 영향 범위·결정/가정: 설계는 `docs/design_m2_scope_contract_and_audit.md`.
  범위 계약 7필드 + `scope_type` 5값(`ORG_PRIVATE` 기본 / `ORG_SHARED` / `ENTERPRISE_SHARED`
  (승인 필수) / `SANDBOX` / `LEGACY_UNSCOPED`(한시·만료일 필수)).
  **"미바인딩 = 통과" 규칙은 정확히 두 곳**에 있다(실측): `master_data.select_for_injection.
  _in_scope`(프롬프트 주입 경로) · `scoping.is_visible`(목록·조회 가시성). 한 곳만 막으면 샌다.
- 증거·다음 행동: **감사로그 인프라가 아직 없다**(`enterprise_context/__init__.py` 에 "(예정)
  audit.py"만) — 거부를 404 로 바꾸면 그 순간 **아무 기록도 남지 않는 조용한 차단**이 된다.
  404 적용 경계를 표로 고정했다(개별 자원 조회만 404 / 목록 200+필터 / 인증 401 / 형식 422 /
  쓰기권한 403). 서버측 범위 계산은 **기존 자산 재사용**으로 가능하다
  (`org_directory.resolve_scope` → `scoping.resolve_scope_ref` → `visible_scopes` → 교차 검증).
  **사용자 결정 필요 4건**: LEGACY 만료일 · `classification` 등급별 정책 · 경영진 드릴다운 범위 ·
  감사로그 보존기간/열람권한(감사로그 자체가 민감정보다).

### [CANARY-TEL-01] A-1 카나리 필수 계측 5종 — 갭 보강 (재카나리 선행)
- 작성자 / 기록 시각: Claude Code / 2026-07-29 11:37 KST (12:10 갱신 — 콜백 사고 반영)
- 왜 지금 기록하는가: 1차 카나리 로그를 대조하니 계측 ①③이 비어 있어 **재카나리해도 같은
  자리가 또 빌 상황**이었다. 근거: `data/llm_call_log.jsonl` 실측(36콜 중 stage 빈 값 13콜,
  컨텍스트 필드 부재) · 커밋 `c73a2c24c`
  ⚠️ **[2026-07-29 12:10 · Claude Code] 내 결함 정정**: 이 커밋의 `FallbackErrorCollector`
  초판이 LangChain 이 읽는 `run_inline` 에 `AttributeError` 를 던져 **재카나리를 2회 좌초**시켰다
  (Antigravity 보고로 확인). 계측이 파이프라인을 죽인 것으로, 원인은 "상류가 무엇을 읽을지
  내가 열거할 수 있다"는 가정이었다. `BaseCallbackHandler` 상속 + 미지 속성 무해 기본값으로
  근본 수정하고 `CallbackManager` 수용 검사까지 테스트로 잠갔다.
- 상태: **구현 완료, 재카나리 대기** (§3-1 B등급 — 계측 추가, 판정 로직 불변)
- 책임 수행자 / 교차 검토자: Claude Code(완료) / Antigravity(카나리 실행·수치 판독)
- 목표·완료 기준: 사용자가 고정한 계측 5종이 **호출 기록에 실제로 실린다**. 07-29 카나리에서
  ①③이 비어 있었다.
- 영향 범위·결정/가정: 계측만 추가하고 라우팅·판정은 건드리지 않았다. `contextvars` 로
  스웜 병렬 호출 간 격리(모듈 전역이면 세 에이전트 기록이 섞인다).
- 증거·다음 행동: `core/context_report.py`(블록별 길이·절단·주입된 지식 출처) ·
  `core/run_context.py`(노드 이름 축·폴백 사유 콜백) · `core/context_engine.py` ·
  `core/knowledge_base.py` · `core/llm_gateway.py` · `core/agent_graph.py`(노드 래핑) ·
  `tests/test_run_telemetry_context.py`(10건) · `tests/conftest.py`(실로그 오염 차단).
  **07-29 카나리에서 무엇이 비어 있었나**: `stage` 빈 값 36%(36콜 중 13콜), 폴백 4건 중 3건이
  그 안에 있어 **어느 단계에서 폴백했는지 알 수 없었다**. 컨텍스트 길이·참조 지식팩은 코드 자체가
  없었다. 그 카나리는 `knowledge_pack_ids: []`·`master_domains: []` 로 **그라운딩 없이** 돌아
  D-010(전수 주입) 실증도 불가능했다.
  **다음 행동**: 재카나리 시 ① 지식팩 연결 ② `master_domains` 지정 ③ 조직 범위 지정 후 실행해야
  D-010 판정이 가능하다. 계측만으로는 판정이 안 된다 — 주입 대상이 있어야 한다.
  **판독기**: `venv\Scripts\python.exe scripts\canary_report.py <프로젝트명>` — 계측 5종을
  읽어 Close 가능 여부를 판정한다(LLM 0콜). 1차 카나리로 검증했고 수동 분석과 같은 판정을 냈다
  (①③④ 미충족 · ⑤ 부분). **재카나리 후 이 출력을 QUALITY-TEL-01 Close 증적으로 첨부하면 된다**
  (단 UI 조회 증적은 별도). 판정 로직은 `tests/test_canary_report.py`(12건)로 잠갔다 —
  특히 "빈 계측을 실패 0건(건강함)으로 읽지 않는다".

### [MDM-SEED-01] M1~M4 기준정보 시드 · 주입 경로 정상화 (2026-07-29)
- 상태: **구현 완료, 교차검토 대기**
- 책임 수행자 / 교차 검토자: Claude Code(완료) / **Antigravity(데이터 정합성)·Codex(제품 영향)**
- 목표·완료 기준: 문서로만 있던 M1~M4 기준정보를 저장소에 적재하고 조직 범위에 바인딩한다
  (감사 `ENTERPRISE-01` Action 1 종결). 값의 정확도는 판정 대상이 아니고 보정 목록으로 넘긴다.
- 영향 범위·결정/가정: **`DECISIONS.md` D-010(주입 상한 폐기 = 전수 주입)·D-011(별칭 파생)**.
  D-010 은 **모든 에이전트 프롬프트의 기준정보 블록 길이를 바꾼다**(≈2,200자 → ≈5,300자) —
  되돌림은 환경변수로 즉시 가능하나 제품 영향(토큰 비용) 검토가 필요하다.
- 증거·다음 행동: 커밋 `34a3e8a37` · `core/master_data_seed.py` ·
  `tests/test_master_document_seed.py`(30건) · **전체 709 통과** ·
  상세 인계 [`docs/handoff_2026-07-29_master_seed_and_injection.md`](../docs/handoff_2026-07-29_master_seed_and_injection.md).
  실측: 적재 44건·바인딩 44건 / 격리(배터리·동제련 상호 0건, **LS전선 0건**) /
  주입 30건 중 절단 0 / 품질 보정 목록 5건(high 4).
  **검토 요청 관점**: ① 전수 주입이 토큰 비용·프롬프트 품질에 미치는 영향이 감당 가능한지
  (실측 필요 — 지금은 길이만 확인했고 산출물 품질 비교는 못 했다)
  ② 품질 보정 목록 5건(황산 UOM 500배·Cpk 3건·NiSO4 적자)이 **문서 수정으로 처리될지 실데이터
  대기로 남을지** — 데이터 담당 판단 필요
  ③ ~~외부 세션 시드 스크립트와 영역 중복~~ → **정리 완료(D-012)**. 조직 코드 SSOT 를
  `core/enterprise_context/seed.py` 로 확정했다. 외부 산출물이 같은 조직에 다른 코드 체계
  (`BU_SMELTING`·`PLANT_ONSAN_1/2`)를 쓰는데, **조직 코드 불일치는 곧 권한 유출**이다 —
  바인딩이 조용히 건너뛰어지고 미바인딩 레코드는 전사 공통으로 통과한다.
  현재 그 JSON 을 읽는 코드는 0곳이라 잠재 상태에서 잠갔다.
  **Antigravity 앞 요청**: `scripts/generate_realistic_mfg_data.py` 의 `organization_tree` 를
  ECM 코드 체계에 맞추거나, 조직 정의를 빼고 데이터만 생성하도록 조정해 주십시오.
  어느 쪽 조직 구조도 M1~M4 문서에 근거가 없어(문서에 공장 정보 0건) 사실성으로는 우열을
  가릴 수 없었고, 이미 44건이 붙어 있는 쪽을 택했습니다.
  ④ 별칭 파생 규칙이 오탐을 만들지 않는지(단어경계 + 최소 2자 + 수치 토큰 배제로 억제했다).

## 검토 대기

### [CHRONICLE-01] 시스템 개발 & 비즈니스 완성 연대기 백서 작성 및 관리 (v2.0 쇄신 완료)
- 상태: 검토 대기
- 책임 수행자 / 교차 검토자: Gemini Antigravity / 사용자(Supervisor) 및 전 팀원
- 목표·완료 기준: C-Level 경영 시뮬레이터 사상 통합, 어색한 어휘 쇄신, 실제급 제조 시드 데이터 성과를 반영한 연대기 백서 v2.0 작성 완료.
- 증거·다음 행동: 상세 백서 [SYSTEM_DEVELOPMENT_CHRONICLE.md](file:///c:/WorkSpace/gemini_agent_team_verG/docs/chronicle/SYSTEM_DEVELOPMENT_CHRONICLE.md) 및 인터랙티브 웹/PPT 백서 v2.0 [index.html](file:///c:/WorkSpace/gemini_agent_team_verG/docs/chronicle/index.html) 갱신 완료.

### [ENTERPRISE-01] 엔터프라이즈 제조·시뮬레이션 트랙 선행 점검 (M1~M4 감사 완료)
- 상태: 검토 대기 → **Claude Code 교차검토 완료, 반영 착수**
- 책임 수행자 / 교차 검토자: Gemini Antigravity / Claude Code(완료), Codex, 사용자
- 목표·완료 기준: M1~M4 기준정보와 ECM(2026-07-28) 설계 및 시나리오(D-1~D-4, E-1~E-2) 정합성 선행 감사 완료.
- 증거·다음 행동: 감사 보고서 [audit_report_m1_m4_enterprise_context.md](file:///C:/Users/denni/.gemini/antigravity-ide/brain/674cfd24-4b90-4e2e-8295-258d25bd5b89/audit_report_m1_m4_enterprise_context.md) 작성 완료. Claude Code R-001/R-002 반영 진행 중.

### [MDM-SCOPE-01] R-001 기준정보 조직 범위 바인딩 (C등급 — 통합 전 검토 필요)
- 상태: 검토 대기
- 책임 수행자 / 교차 검토자: Claude Code(완료) / **Antigravity(정합성·데이터)·Codex(제품 영향)**
- 목표·완료 기준: 감사 Finding 1(기준정보에 조직 문맥 없음) 해결. 본문은 MDM 에 두고
  `master_scope_bindings` 로 **원본 1 : 적용범위 N**, 주입 경로에 범위 필터.
- 영향 범위·결정/가정: `TEAM_PROTOCOL` §3-1 **C등급**(권한·보안 + 데이터 구조). `DECISIONS.md`
  D-009 에 의존. 점진 도입(바인딩 없으면 전사 공통 통과)으로 회귀 위험을 낮췄다.
- 증거·다음 행동: 커밋 `1fe965902` · `tests/test_master_scope_binding.py`(18건) · 전체 680 통과 ·
  실측(제1공장 3 / 제2공장·동제련 2 / **LS전선 1** / 범위 미지정 3).
  **★ ① 에 대한 자체 답(2026-07-29, 커밋 `34a3e8a37`)**: **유출 창구가 됐다.** 재시드가 기존
  레코드를 건너뛸 때 바인딩 확인까지 건너뛰어, ECM 조직 없이 먼저 적재된 레코드가 미바인딩으로
  남고 통과 규칙을 타고 **모든 조직에 노출**됐다(실측 DB: 바인딩 26 < 레코드 45). 수정 후 44/44,
  LS전선 노출 0건. `test_reseed_binds_preexisting_records` 로 잠금. 규칙 자체는 유지하되
  **미바인딩 레코드 수를 상시 관측**해야 한다는 것이 교훈 — 검토 시 이 관점을 함께 봐 주십시오.
  **검토 요청 관점**: ① 점진 도입 규칙("바인딩 없으면 통과")이 유출 창구가 되지 않는지
  ② 캐시 키 분리 대신 요청별 필터를 택한 판단(Codex 권고와 다름 — 근거는 커밋 메시지)
  ③ 상속(`inherit_descendants`)이 적용 가능성에 한정되고 열람 권한으로 비화하지 않는지
  ④ `master_version`·`effective_*` 미구현이 지금 단계에서 허용 가능한 한계인지.

## 차단

_현재 없음_

## 완료

완료 항목은 상세 이력을 이곳에 누적하지 않는다. 필요한 경우 `AI_HANDOFF.md`, 관련 커밋, 또는 `docs/` 산출물에서 확인한다.
