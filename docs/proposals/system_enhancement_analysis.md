# 🌐 Antigravity AI Factory 고도화 분석 보고서

> **설계 보강(2026-07-28):** 온톨로지·출처·샌드박스·이벤트 연합은 모든 기업을 한 덩어리로 취급해서는 안 된다. Enterprise Context Master가 조직 범위, 실제/가상/경쟁사 상태, 프로필과 권한의 공통 기준이 된다. 상세 설계: [`../design_enterprise_context_master.md`](../design_enterprise_context_master.md).
**작성자:** Palantir AI Program Expert Persona
**목적:** 현재 Multi-Agent 소프트웨어 팩토리 시스템의 아키텍처 한계를 분석하고, 엔터프라이즈급(Enterprise-grade) 강건성, 데이터 온톨로지(Ontology), 그리고 휴먼-머신 공생(Human-Machine Symbiosis) 관점에서의 고도화 방안 제언.

---

## 1. 지식 온톨로지(Ontology) 도입 및 데이터 출처(Provenance) 관리
현재 `state_models.py`의 `ProjectState`는 단일 거대 JSON(Fat Object) 형태로 파이프라인의 모든 상태를 짊어지고 있습니다. 이는 확장이 어렵고, 에이전트 간 맥락 단절을 유발합니다.

*   **현재의 한계:** 요구사항(RFP)과 최종 산출물(Code) 사이의 '시맨틱 연결고리(Semantic Edge)'가 부재합니다. 코드가 변경되었을 때 어떤 기획적 요구에 의한 것인지 추적하기 어렵습니다.
*   **고도화 방안 (Ontology Layer):** 
    *   단순 JSON 상태를 넘어 **지식 그래프(Knowledge Graph)** 기반의 온톨로지로 전환해야 합니다. 
    *   `[Feature A] -> requires -> [API Endpoint B] -> implemented_by -> [Code Block C]` 형태로 데이터를 구조화하면, 특정 API 설계가 변경될 때 연관된 프론트엔드 UI 요소를 담당하는 에이전트만 선별적으로 재가동할 수 있습니다.
*   **출처 추적(Data Provenance):** 모든 산출물 변경 사항에 대해 "어떤 에이전트가, 어떤 LLM 모델(Pro/Flash)을 사용하여, 어떤 프롬프트를 기반으로 작성했는지"를 블록체인 원장처럼 불변 로그로 남기는 체계를 구축해야 합니다.

## 2. 미세 조정 가능한 휴먼-머신 공생 체계 (Granular HOTL)
현재의 HOTL(Human-On-The-Loop) 체계는 파이프라인을 멈추고 단순히 텍스트 피드백을 주거나 전체를 승인(Auto-approve)하는 'All-or-Nothing' 방식입니다.

*   **현재의 한계:** 사용자는 에이전트가 만든 산출물의 일부만 마음에 들지 않아도 전체를 반려(Rework)해야 하며, 이는 불필요한 LLM API 호출(비용/할당량 낭비)로 이어집니다.
*   **고도화 방안 (Human-in-the-loop Symbiosis):**
    *   **부분 승인(Partial Approval) 및 시맨틱 Diff:** 사용자가 산출물을 리뷰할 때, Git Diff처럼 변경된 코드나 WBS 태스크 단위로 시각적 대조를 제공하고, 특정 부분만 승인(Lock)하거나 반려할 수 있어야 합니다.
    *   **Visual MLOps:** UI 목업이나 프론트엔드 코드의 경우, 렌더링된 화면(iframe) 위에서 사용자가 직접 영역을 드래그하거나 주석(Annotation)을 달면, 이를 멀티모달(VisionQA) 입력으로 변환해 디자이너 에이전트에게 즉각 피드백하는 시스템이 필요합니다.

## 3. 격리된 샌드박스 자율 치유 (Autonomous Self-Healing in Sandbox)
현재 `agent_graph.py`의 `CodeBuilder`와 `Reviewer`는 빌드 실패 시 에이전트에게 코드를 돌려보내지만(Circuit Breaker), 에이전트가 코드를 테스트할 안전하고 자동화된 실행 환경이 부족합니다.

*   **현재의 한계:** 코드를 실제 환경에 배포하거나 의존성을 설치하지 않고 정적 분석이나 LLM의 추론에만 의존하여 품질을 보증하려 합니다.
*   **고도화 방안 (Ephemeral Sandbox):**
    *   에이전트가 코드를 작성하면 즉시 **Docker WebAssembly(Wasm) 또는 MicroVM** 기반의 샌드박스에서 컴파일 및 단위 테스트(Unit Test)를 실행해야 합니다.
    *   에이전트는 샌드박스에서 발생한 런타임 에러(Stack trace)를 텍스트로 피드백 받아 스스로 코드를 수정(Self-healing)한 뒤에만 리뷰어(Reviewer) 노드로 산출물을 넘겨야 합니다.

## 4. 메타 오케스트레이션과 이벤트 주도형 연합 (Event-Driven Federation)
현재 메가 프로젝트(`is_mega_project`) 개념이 상태 모델에 정의되어 있으나, 서브 프로젝트 간의 의존성을 조율하는 메커니즘은 단순 사전(`shared_ledger`) 형태입니다.

*   **현재의 한계:** 프로젝트 A(백엔드 API)와 프로젝트 B(웹 프론트엔드)가 병렬로 진행될 때, A의 설계가 바뀌면 B가 즉각적으로 대응하기 어렵습니다.
*   **고도화 방안 (Event Bus / Pub-Sub Federation):**
    *   분산 메시지 큐(예: Kafka, Redis PubSub)를 도입하여 에이전트 간 **이벤트 주도형 비동기 통신**을 구현합니다.
    *   예컨대 백엔드 에이전트가 API 스키마(OpenAPI spec)를 변경하면 "Schema_Updated" 이벤트를 발행하고, 프론트엔드 에이전트가 이를 구독(Subscribe)하여 클라이언트 코드를 백그라운드에서 자율적으로 재생성하는 메타-그래프(Meta-Graph) 아키텍처로 진화시켜야 합니다.

---
**💡 요약 및 결론:**
시스템의 안정성과 확장성을 위해 코드 수정을 서두르기보다, **1) 단일 상태 객체(ProjectState)를 지식 온톨로지로 분리**하고, **2) 샌드박스 기반의 실행 환경을 구축**하며, **3) 부분 승인이 가능한 정밀한 HOTL UI**를 설계하는 기획적 리팩토링이 선행되어야 합니다.
