# V6 Enterprise Constellation

흔한 사이드바·카드 대시보드에서 벗어나 회사 자체를 화면 중앙의 “업무 코어”로 표현한 공간형 시안이다.

- 중앙: 회사 CI, 현재 조직과 권한 컨텍스트
- 주변: SW 생성기, 디지털 트윈, 운영, 지식·MDM, 연결·MCP, 에이전트, Atlas, 릴리스
- 연결선: 데이터·근거·실행 관계
- 하단 리본: 지금 사용자가 결정할 최우선 업무
- 우측: Atlas 전역 대화와 회사 운영 신호

디자인은 참신하지만 기능 콘텐츠는 `../CONTENT_BASELINE.md`의 C01~C12를 모두 유지한다.

```powershell
python -m http.server 8092 --directory uiux-prototypes/v6
```
