# AI Factory Studio — 시스템 완주 & 비즈니스 연대기 (System Chronicle v2.0)

> **상태**: 지속적 갱신 원장 (Living Document)  
> **버전**: v2.0 (어휘 세련화, C-Level 경영 시뮬레이터 사상 통합, 핵심 경쟁력 재강조 버전)  
> **최초 작성일**: 2026-07-29  
> **주요 용도**: 내부 성과 및 비즈니스 모델(BM) 보고, 그룹 계열사 확장 및 대외 사업화(PR/IR) 소개 백서  
> **공동 기록자**: 사용자(Supervisor), Gemini Antigravity, Claude Code, Codex  

---

## Executive Summary (경영진 요약)

본 연대기는 **'AI Factory Studio'**가 단순한 소스코드 생성 도구를 넘어, **"현업 실무자의 바텀업(Bottom-Up) 운영 데이터 축적과 최고경영진(C-Level)의 탑다운(Top-Down) 경영 시뮬레이터를 융합한 자율 소프트웨어 제조 팩토리"**로 탄생하고 완성되어 온 전 과정을 기록한 공식 사서(史書)입니다.

프로젝트 초창기 엔진의 아키텍처적 핵심 병목(모델 라우팅 붕괴, 하네스 거짓 반려 등)을 쇄신하고, 관문 시나리오(A-1 단위변환기) 100% 완격 통과를 거쳐, 지주사-법인-공장을 잇는 **Enterprise Context Master(ECM)** 아키텍처, **실제급 제조 합성 데이터 생성 스크립트**, 그리고 **4인 원팀(One-Team) 협업 체계**를 정립하기까지의 전 과정을 6개 장으로 구성하여 관리합니다.

---

## Chapter 1. 비전과 시스템 사상 (Genesis & Vision)

### 1.1 왜 엔터프라이즈 AI SW 팩토리인가? (현업 실무 → C-Level 경영 시뮬레이터)
* **기존 시장의 한계**: 기존 AI 앱 빌더(Lovable, Bolt.new 등)는 일회성 샌드박스 코딩에 머물러 있고, 기존 BI/AI 대시보드(Palantir AIP 등)는 현장의 정밀한 바텀업(Bottom-Up) 데이터 없이 Top-Down 껍데기 대시보드만 구축하려다 실패했습니다.
* **우리의 융합 비전**: 
  1. **현업 사용자 (Bottom-Up)**: 통제실(Control Room)에서 일상 업무에 필요한 맞춤형 Full-Stack SW를 자연어로 자율 제조하여 현장 운영 데이터를 신뢰성 있게 축적합니다.
  2. **C-Level 경영진 (Top-Down)**: 현업에서 쌓인 실시간 신뢰 데이터 위에서 전사 실적과 성과지표(KPI)를 정확히 계산하고, 다양한 What-if 재무/제조 예측을 수행하는 **최고 경영 시뮬레이터(Management Simulator)**로 완성됩니다.

### 1.2 비즈니스 모델(BM) 핵심 지향점
1. **토큰당 비용이 아닌 '승인된 결과물 1건당 가치' 최적화**
2. **LLM 환각(Hallucination) 제로화**: "LLM은 기획·설계·추론만 담당하며, 숫자 계산/권한/시뮬레이션은 결정론적 계산 엔진이 담당"한다는 비협상 원칙 확립.
3. **Shadow Mode 및 데이터 계약**: 실제 운영계 DB 오염 없이 안전하게 가상 시나리오를 테스트하고 전사 RAG 지식으로 재활용.

---

## Chapter 2. 초기 아키텍처 병목과 핵심 난제 극복 (Architectural Bottlenecks & Fixes)

### 2.1 팩토리 엔진의 초기 아키텍처 병목
플랫폼 개발 초창기, 이론적으로 완벽해 보이던 에이전트 그래프는 실제 가동 시 수많은 숨은 병목과 환경적 한계로 인해 시련을 겪었습니다.

* **[병목 1] 약한 모델 백스톱 상한 폭주**: 무료 티어 쿨다운 발생 시 Pro 백스톱이 70B 모델로 붕괴되면서, 8,192 토큰 상한에 갇혀 구조화된 JSON 출력이 무한 파싱 실패를 일으키던 현상.
* **[병목 2] 판단 노드 캐시 오염 및 루프**: 승인/반려 판정 노드의 캐시 키가 작업 상태와 분리되지 않아 동일한 사유로 무한 반려 루프에 빠지던 현상.
* **[병목 3] 검증 하네스의 거짓 반려 (False Rejections)**: LLM이 정상 분리한 다중 디렉토리 코드(components/*, utils/*)를 렌더 하네스가 거짓으로 반려하거나, 백엔드 스모크 테스트가 SQLite 부모 디렉토리를 생성해주지 않아 거부하던 하네스 역설.
* **[병목 4] 가짜 성공 (Silent Failure)**: 오류가 발생했음에도 에이전트가 예외를 삼켜 조용히 기능이 죽고 "성공"으로 보고하던 결함.

### 2.2 대전환: 회귀 테스트 스위트와 모델 라우팅 혁신 (2026-07-27)
* **14건의 엔진 결함 보정 (커밋 `83d64437c`)**:
  * Pro 체인 라우팅에 `gemini-2.5-flash` 및 `gemini-2.5-pro`를 최상위로 편입하고, sticky winner 및 쿨다운 정책 재정립.
  * 하네스의 다중 디렉터리 구조 지연 모듈 해석 로직 반영 및 백엔드 스모크 `cwd` 자동 생성 보완.
  * 가짜 성공 차단을 위한 `TerminalHandler` 신설 및 `terminal_status` 도입으로 회귀 안전망 100% 확립.

---

## Chapter 3. Phase 1 & 2 — A-1 관문 시나리오(단위변환기) 완주 (2026-07-27)

### 3.1 "된다는 증거"의 최초 달성
* **프로젝트 ID**: `test_a1_unitconv` (단위 변환기 웹앱)
* **성과**: 5개 HOTL 게이트(Requirement Interviewer, RFP, PM, VisionQA, PMO)를 완벽히 통과하며, **RFP → PRD → UI → 아키텍처 → WBS → 코드 → 빌드 → 리뷰 → QA → 수용검수** 전 과정을 완주.
* **의의**: 시장성 평가서(`docs/business_value_assessment.md`)가 지적했던 "된다는 증거가 없다"는 우려를 완벽히 불식시키고, 실제 동작하는 앱을 최초로 전사 라이브러리에 **Release(게시)**하는 역사적 이정표 수립.

---

## Chapter 4. 4인 융합 팀 체제 및 소통 프로토콜 혁신 (2026-07-28)

### 4.1 4인 원팀(One-Team) 체제 정립
제품의 비즈니스 완성도를 극대화하기 위해 역할 중심의 4인 협업 체계를 수립하였습니다:
* **사용자 (Supervisor / Product Owner)**: 최종 결정권 및 비즈니스 방향 승인.
* **Gemini Antigravity**: E2E 시나리오/테스트 가동, 데이터 샘플링, 텔레메트리/실패 로그 정밀 분석, 외부 리서치 및 선행 감사 담당.
* **Claude Code**: 기능 설계, 백엔드/FastAPI/LangGraph 구현, 단위·계약 테스트 및 기능 검증용 UI 완결.
* **Codex**: 제품 사상·사업가치 설계, UI/UX 시안 확정 및 대대적 개편, 독립 교차 검토.

### 4.2 소통 파편화 극복 — `TEAM_PROTOCOL.md` & `TEAM_BOARD.md`
* **혁신**: **"역할은 경계가 아닌 우선순위이며, 중요한 결과는 다른 팀원의 독립 검토를 거친다"**는 협업 규약 제정 및 단일 현황판(`TEAM_BOARD.md`)을 통한 실시간 상태 관리 체계 확립.

---

## Chapter 5. Enterprise Context Master (ECM) & 제조·시뮬레이션 선행 감사 (2026-07-28 ~ 07-29)

### 5.1 최고 권위 아키텍처 제정 및 선행 감사 (`design_enterprise_context_master.md`)
* `Tenant → Enterprise Group → Legal Entity → Business Unit → Plant`로 이어지는 엔터프라이즈 조직 계층 모델 수립.
* **Antigravity 선행 감사**: M1~M4 기준정보 3대 갭(ECM 래퍼 주입, VIRTUAL 시뮬레이션 오버레이, 템플릿-마스터 1:1 바인딩) 도출 및 해결책 수립.

### 5.2 Claude Code & Codex: ECM E1/E2 백엔드 구현 및 648 Pytest 완승
* **ECM E1 (조직 그래프 & 권한 가시성)**: 커밋 `2e42968ec`, pytest 619건 통과.
* **ECM E2 (프로필 상속 병합 & 마스터 바인딩)**: 커밋 `f893b258a`, **총 648개 pytest 100% PASS 달성**.
* **Codex 독립 교차검토 완료**: DECISIONS.md D-002 및 R-001 보완안 반영 수용.

### 5.3 실제급 제조 합성 데이터 생성 스크립트 가동
* `battery_material_m1.json`, `copper_smelting_m2.json`, `m4.json` 내의 실제 공정 수율(94~98%), OEE, Weibull 마모 분포, Gaussian 품질 공차, LME 시세 파라미터를 결합한 **LS MnM 온산공장 실제급 시드 데이터(`data/ls_mnm_realistic_enterprise_seed.json`)** 파이프라인 가동 성공.

---

## Chapter 6. 향후 연대기 갱신 템플릿 & 확장 로드맵 (Roadmap)

### 6.1 마일스톤별 향후 확장 계획
* **Phase 3 (SW 다양화)**: TODO(A-2), 매출 대시보드(A-3), 재고 관리(A-5) 등 업무 앱 라인업 연속 실증.
* **Phase 7 & 8 (엔터프라이즈 제조 & 경영 시뮬레이터)**: 원가 분석(D-1), 품질 QC(D-4) 및 What-if 재실행(E-2) 실제 엔진 통합.
* **지주사/계열사 확장**: LS 그룹 등 실제 엔터프라이즈 테넌트 멀티 사업장 적용 및 대외 B2B SaaS/구축형 파이프라인 전개.

---

### 📝 연대기 업데이트 관리 규칙 (Change Log)
* 본 연대기 문서는 **`TEAM_BOARD.md`에서 [완료] 단계로 넘어가는 주요 마일스톤이 발생할 때마다** Antigravity 주관하에 새로운 Chapter 또는 절(Section)을 누적(Append)하여 갱신 관리합니다.
