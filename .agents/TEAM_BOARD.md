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
- 상태: **R2 Factory 반려 · 원본 React 3패널을 기준선으로 복원 · 전용 비교 시안 A/B/C 구현 및 브라우저 검증 완료 · Supervisor 선택 대기**
- 결정 및 근거: 현재 React의 `WorkflowStrip + ControlPanel + TimelinePanel(Supervisor Console/HOTLInput) + PreviewPanel`을 기능·정보구조 기준선으로 확정했다. `uiux-prototypes/sw-factory-concepts/`에 A Original Plus(원본 3패널 최소 개선), B Guided Journey(신규 기획 5단계), C Focus Workbench(기획/WBS/실행/산출물/품질 탭)를 분리 구현했다. 브라우저에서 A의 Control/Supervisor/Preview 3영역과 Atlas 접근, B의 5단계·단일 주 CTA와 1→2 단계 전환, C의 5개 작업 탭과 산출물 집중 전환을 확인했다. 기능 보존 기준은 `uiux-prototypes/sw-factory-concepts/README.md`.
- 영향·주의사항: 실제 `frontend/`·API·DB는 변경하지 않았다. R2 Factory는 삭제하지 않고 실패 이력으로 보존하지만 React 이식·확정 디자인 근거로 사용하면 안 된다. Atlas는 항상 접근 가능해야 하나 별도 네 번째 고정 열을 강제하지 않는다. WBS·품질·복구는 관련 단계에서만 전개한다.
- 다음 행동 / 담당 / 착수 조건: Supervisor가 A/B/C의 선호 요소를 검토한다. 현재 Codex 권고는 `B 신규 기획 → A 실행 통제실 → C 산출물 집중 모드` 조합이다. 선택 전 Claude Code는 실제 Factory 화면을 재배치하지 않는다. 승인 후 Codex가 선택 조합의 상태별 화면 명세를 확정하고 Claude Code가 기존 컴포넌트를 보존한 채 단계적으로 이식한다.
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
