# AI Factory Studio UI/UX 시안 관리

## 현재 제품 기준선

- 시작 페이지: `index.html`
- 공통 콘텐츠 기준: `CONTENT_BASELINE.md`
- 전체 선택·통합 가이드: `V1_V10_SELECTION_GUIDE.md`
- North Star 경영 홈: `master-concept/`
- 기능별 제품 샘플: `m6-product-samples/`
- Software Factory 비교안과 투명 오케스트레이션: `sw-factory-concepts/`
- 앱 전달·의사결정·발간 폐쇄루프: `closed-loop-product-samples/`

## 탐색 이력

- `revision-v2/`: 비판 반영 전체 수정 세트
- `revision-v2-1/`: 타이포그래피·공간 모델 보완
- `revision-v2-2/`: LS CI 컬러 비교 세트
- `revision-v3/`: 제3자 비교 실험; 최종 제품 기준에서 제외
- `v1/`~`v10/`: 초기 기능별 디자인 탐색 이력
- `REVISION_SET_COMPARISON.md`: 세트 비교와 판단 이력

초기 탐색 파일은 구현 SSOT가 아니다. 실제 이식 기준은 `docs/uiux/`의 화면기능정의서·UI설계서·추적 매트릭스와 각 승인 프로토타입 README를 함께 사용한다.

## 로컬 실행

```powershell
node uiux-prototypes/preview-server.mjs
```

브라우저: `http://127.0.0.1:8090/`

