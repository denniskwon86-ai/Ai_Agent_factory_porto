# M6 Product UI Samples

승인된 `master-concept`의 **Living Enterprise Canvas**를 경영 의사결정 홈으로 사용하고, 깊은 편집이 필요한 기능은 독립 Studio로 분리한 클릭형 제품 샘플이다. 개념 발표용 시안이 아니라 `docs/uiux/`의 화면기능정의서와 UI 설계서를 실제 구현 화면에 연결하기 위한 기준선이다.

## 화면 구조

- `경영 홈`: 현재 회사의 의사결정·위험·업무·데이터·SW·Twin 연결을 보여준다.
- `전용 Studio`: Software Factory, Agent Studio, Digital Twin은 전체화면 작업공간으로 이동한다.
- `공통 제품 셸`: 모든 화면이 동일한 경영 홈·Factory·운영·Twin·보고서·Knowledge·Agent 순서와 회사 문맥을 사용한다.
- `공통 문맥`: 화면을 이동해도 `LS MnM · 전사공통 · 경영관리팀 · REAL` 문맥을 유지하고, Studio 내부 작업 범위는 별도 Context Bar로 표시한다.
- `Atlas`: 경영 홈에서는 고정 의사결정 비서, Studio에서는 접이식 브리핑·영향 설명자로 동작한다.

## 포함 화면

| 화면 | 주소 | 검증 목적 |
|---|---|---|
| 경영 홈 | `/master-concept/` | 회사 문맥, Digital Thread, 의사결정 대기열, Atlas 전역 비서 |
| Company Universe | `#context` | 회사·사업부·공장 선택, 권한, 산업 플레이북, 가상회사 생성 |
| Guided Start | `#advisor` | 상담형 업무 정의, 선택형 요구 확인, 데이터 준비도 |
| Software Factory | `/revision-v2-2/factory/` | 입력 명세, 생산라인, WBS·Agent, Timeline·Preview, 품질·비용·복구·릴리스 |
| Report Studio | `#report` | 문서 목차, 보고서 본문, 근거·주석·버전·승인·배포 |
| Operate | `#operate` | 부서 SW 운영, 전사 승격, 오너·보안·품질 게이트 |
| Digital Twin | `/revision-v2/v9/` | 3개 시나리오, 가치사슬 Sankey, 복수 동인, 손익·현금·운영 영향·근거 비교 |
| Knowledge | `#knowledge` | 원본자료, 지식팩, MDM, 카탈로그, 연계, 외부지표 |
| Agent Studio | `/revision-v2/v10/` | 실제 노드·엣지 Agent Graph, Registry, Template, Skill, 모델·HOTL·품질·비용 정책 |
| Settings & Admin | `#admin` | 개인 설정, 회사 브랜드, 사용자·권한, AI 비용, 연계, 감사·운영 |

## 실행

저장소 루트에서 다음 명령을 실행한다.

```powershell
python -m http.server 8090 --directory uiux-prototypes
```

브라우저 주소:

```text
http://127.0.0.1:8090/m6-product-samples/
```

## 샘플 상호작용

- 상단 회사 문맥 전환: 실제 조직·사업부·공장·가상회사 선택 및 기업 테마 전환
- Company Universe: 회사 계층 선택, 운영 문맥 적용, 기존 회사 기준 가상회사 Sandbox 생성
- Enterprise: 업무 노드 선택, DATA/SW/TWIN 레이어 표시 전환, 의사결정 초안
- Guided Start: 추천 선택지 변경과 다음 질문 진행
- Report Studio: 장별 목차 이동, 근거·검토의견 확인, 버전 비교, PDF·Word 내보내기, 승인
- Digital Twin: 환율·원료가격·전력단가·고용인원 변경에 따른 KPI·그래프 재계산
- Knowledge: 자연어 의미 검색, Graph 관계 경로, 출처·범위·승인 상태 확인, 기반 영역 탭과 운영자료 선택
- Agent OS: Workflow Template·HOTL 토글 선택
- Settings & Admin: 설정 영역 전환, 개인/전사 적용 범위 확인, 회사 색상 실시간 Preview, 변경 검토·저장
- Atlas: Task ID 없이 회사 전체 질문, 업무 SW·시뮬레이터·보고서 생성 상담 및 Guided Start 연결
- 통합 검색: 상단 검색 또는 `Ctrl+K`

## 구현 연결 원칙

1. `index.html`의 정보 구조와 주요 의사결정 위치를 우선 유지한다.
2. `styles.css`의 제품 토큰과 컴포넌트 규칙을 React 공통 셸로 이관한다.
3. `app.js`는 샘플 데이터 기반 동작이며 실제 구현에서는 Zustand selector와 REST/SSE 상태로 교체한다.
4. 권한이 없는 회사·조직·데이터는 목록에서 숨기고 직접 접근도 404로 은폐한다.
5. 계산 불가·근거 부족·승인 대기는 숫자 0이나 정상 상태로 대체하지 않는다.
6. 개인 설정은 즉시 저장할 수 있지만 회사·권한·모델·연계·운영 정책은 영향 분석과 승인 후 적용한다.
7. 경영 홈에 제작·편집 도구를 삽입하지 않는다. 경영 홈은 요약과 결정, Studio는 깊은 작업을 담당한다.
8. 전용 Studio 전환은 모달이나 전체화면 Overlay가 아니라 독립 URL로 구현하고, 뒤로가기·새로고침·딥링크를 보장한다.
9. 프로토타입 수치는 `PROTOTYPE · SAMPLE DATA`로 명시하며 실제 운영 상태인 것처럼 표시하지 않는다.
10. 편집 중이거나 실행 중인 Studio에서 다른 모듈로 이동할 때 저장·일시정지 여부를 확인한다.

## P0 통합 리비전 결과

- 공통 자산: `../product-shell.css`, `../product-shell.js`
- 제거: 화면 위에 별도 바를 주입하고 Agent 본문을 실행 시 변경하던 `studio-nav.js`
- 경영 홈: 연결 업무축 7개와 시각 노드 수를 일치시키고 진행 제품 2건을 실제로 표시했다. 근거 추적 버튼과 Studio 이동을 연결했다.
- Factory: 제품 Context Bar, 생산 제어, WBS·Agent·Timeline·Preview·품질·복구·릴리스 진입을 하나의 워크스페이스로 정리했다.
- Agent: 상담 화면의 텍스트 치환 방식 대신 노드·엣지 Graph Editor와 선택 Agent Inspector를 원본 HTML로 구현했다.
- Twin: 단일 Slider 예시를 기준안·대응안·복합충격안 3개와 환율·원료·전력·고용 동인으로 확장했다.
- 보호 UX: Agent 미저장 Draft, Twin 미저장 시나리오, Factory 실행 중 상태에서 전역 이동 시 경고한다.
