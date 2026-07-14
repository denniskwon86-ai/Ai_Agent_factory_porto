# Antigravity 소프트웨어 팩토리 - 프로젝트 핸드오프 및 AI 연계 문서

본 문서는 현재까지 작업된 **소프트웨어 팩토리(Multi-Agent 자동화 파이프라인) 프로젝트**의 전체 기획 내용, 기능 설계, 향후 계획 및 다른 LLM(Agent)이 즉시 컨텍스트를 파악하고 이어서 작업할 수 있도록 작성된 Handoff(인계) 문서입니다.

---

## 1. 전체 기획 내용 (Project Overview)

본 프로젝트는 요구사항 입력부터 요구정의서(RFP), 기획서(PRD), UI 디자인, 작업분해도(WBS), 아키텍처 및 기술 명세, 실제 코드(Front/Back) 구현, 리뷰, QA, 매뉴얼 작성에 이르는 전 과정을 **다중 AI 에이전트(Multi-Agent)들이 협력하여 자동 수행하는 소프트웨어 팩토리 플랫폼**입니다.

* **백엔드 (Backend):** Python, FastAPI, LangGraph 기반의 상태 머신 및 에이전트 파이프라인.
* **프론트엔드 (Frontend):** React, Vite, Tailwind CSS 기반의 통제실(Control Panel) 대시보드.
* **핵심 컨셉 (Core Concept):** 
  - 각 단계별 특화된 페르소나와 스킬을 가진 에이전트(`Master_PM`, `UIDesigner`, `Architect` 등)가 순차적/병렬적으로 역할을 수행.
  - 중요한 분기점(예: WBS 확정, UI/UX 승인, 최종 검수 등)에서 사용자(Supervisor)가 개입하여 승인/반려/수정 지시를 내리는 **HOTL (Human-On-The-Loop)** 체계 구축.

---

## 2. 현재 구현된 기능 및 기능 설계서 (Implemented Features & Specs)

### 2.1 프론트엔드 (통제실 UI/UX)
1. **메가 프로젝트 / 독립 프로젝트 지원:** 프로젝트 성격에 따라 템플릿(소프트웨어/문서/시뮬레이션 등)을 선택하여 파이프라인을 다르게 가동할 수 있습니다.
2. **실시간 파이프라인 트래킹:** `ControlPanel.tsx`에서 웹소켓을 통해 현재 가동 중인 에이전트 단계, 상태, 진행률(%), 마지막 활동 시간을 실시간으로 렌더링합니다. (세로 찌그러짐 방지 등 CSS 레이아웃 최적화 완료)
3. **에이전트 중간 산출물 렌더링 (`PreviewPanel.tsx`):**
   - **코드 렌더링:** 프론트/백엔드 코드가 JSON 형태로 산출될 경우, 마크다운 코드 블록 형태로 변환해 가독성을 높였습니다.
   - **UI 목업 렌더링:** `UIDesigner`가 작성한 HTML/Tailwind CSS 마크다운 블록을 정규식으로 추출하여 실제 웹 브라우저(`iframe`) 화면으로 렌더링합니다.
4. **HOTL 피드백 패널 (`HOTLInput.tsx`):** 슈퍼바이저가 개입해야 하는 단계(`RFP`, `PLANNING`, `UI_DESIGN`, `PMO` 등)에서 해당 산출물이 어느 탭에 있는지 명확히 안내하고, 사용자의 코멘트를 받아 백엔드로 전송합니다.

### 2.2 백엔드 (에이전트 파이프라인)
1. **상태 관리 (`state_models.py`):** `ProjectState` 객체를 통해 `ui_mockup_summary`, `prd_summary` 등 각 에이전트의 산출물 상태를 영속적으로 관리합니다.
2. **에이전트 라우팅 그래프 (`agent_graph.py`):**
   - `Master_PM` (기획) $\rightarrow$ **`UIDesigner` (UI 디자인)** $\rightarrow$ `Master_PMO` (WBS 생성) 파이프라인을 성공적으로 연결했습니다.
3. **UI 디자이너 노드 (`ui_designer.py` & `ui_designer_skill.md`):**
   - 프롬프트에 의해 단일 HTML+Tailwind 코드를 도출하며, 모던 웹(Glassmorphism, Micro-animations) 스타일 지침을 따르도록 설계되었습니다.

---

## 3. 향후 수행 계획 (Future Execution Plan)

1. **에이전트 자율성 및 도구 연계 확장:** 에이전트들이 코드를 작성할 때 샌드박스 환경에서 직접 빌드/테스트를 해보고 오류를 자가 치유(Self-Healing)하는 루프 강화.
2. **에러 핸들링 및 타임아웃 처리:** 외부 LLM API 지연으로 인한 데드락 방지를 위해 단계별 타임아웃 로직 고도화.
3. **Mega Project 릴레이션 체계:** 메가 프로젝트 하위에 속한 다수의 서브 독립 프로젝트들이 서로 데이터를 공유하고 의존성을 관리할 수 있는 메타-그래프 체계 도입.
4. **산출물 다운로드/Export 기능:** 완성된 프론트엔드/백엔드 코드를 zip 파일로 패키징하거나 GitHub Repository로 즉시 푸시하는 파이프라인 연동.

---

## 4. [AI HANDOFF] 다른 LLM 모델/IDE를 위한 컨텍스트 주입 지침

> **System Prompt / Handoff Context for New AI Agents:**
> 아래 내용을 복사하여 새로운 대화창이나 다른 LLM 도구의 시스템 프롬프트(혹은 초기 지시문)에 붙여넣으면, 동일한 컨텍스트 내에서 개발을 즉시 이어나갈 수 있습니다.

```markdown
# AI Context Handoff: Antigravity Multi-Agent Factory

당신은 Python(FastAPI/LangGraph) 백엔드와 React(Vite/Tailwind) 프론트엔드로 구성된 "소프트웨어 자동화 팩토리" 프로젝트의 AI 코딩 어시스턴트입니다.

## 1. 아키텍처 및 상태
- **디렉토리 구조:**
  - `/frontend`: 프론트엔드 웹 앱 (`src/components/` 핵심: ControlPanel, PreviewPanel, HOTLInput)
  - `/core`: LangGraph 파이프라인 코어 (`agent_graph.py`, `agent_registry.py`, `state_models.py`)
  - `/nodes`: 각 에이전트별 실행 로직 (`ui_designer.py`, `planning.py` 등)
  - `/skills`: 에이전트별 페르소나 및 지침 (Markdown 파일 형식)
- **통신 방식:** 프론트엔드와 백엔드는 REST API 및 WebSocket을 통해 에이전트의 실시간 상태(`ProjectState`)를 주고받습니다.

## 2. 규칙 및 제약사항
- UI 수정 시 Tailwind CSS 유틸리티 클래스를 최우선으로 사용하세요. (`App.css`나 `index.css`에 직접 작성은 피할 것)
- 파이프라인 그래프(`agent_graph.py`) 수정 시, 노드의 입출력은 반드시 `ProjectState`를 기준으로 하며, 노드 추가 시 `agent_registry.py`와 `state_models.py`를 함께 수정해야 합니다.
- 파일 탐색 및 코드 수정은 제공된 시스템 도구(Tool)를 사용하되, bash 명령어 내에서 `cat` 이나 `grep` 등을 남용하지 말고 전용 `view_file`, `grep_search`, `replace_file_content` 툴을 사용하세요.

## 3. 직전 작업 내역 (당신이 이어나갈 맥락)
- 최근 `UIDesigner` 에이전트가 새롭게 도입되어 `Master_PM` 직후 HTML/Tailwind 기반의 목업을 생성하고 통제실 iframe에 렌더링하는 기능이 구현되었습니다.
- HOTL(Human-On-The-Loop) 입력 인터페이스와 파이프라인 상태 UI 반응성(CSS Flex 랩핑 등)이 수정되었습니다.

위 내용을 바탕으로 사용자의 다음 요구사항(Next Request)을 분석하고, 필요한 디렉토리 및 파일을 탐색하여 개발을 이어나가십시오.
```
