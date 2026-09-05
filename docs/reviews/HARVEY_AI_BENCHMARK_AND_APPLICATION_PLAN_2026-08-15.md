# Harvey AI 심층 벤치마크와 AI Factory Studio 적용계획

> 문서 상태: 제품·설계 교차검토안 1.0  
> 작성일: 2026-08-15  
> 조사 기준: Harvey 공식 제품·도움말·보안·연구 공개자료  
> 적용 원칙: Harvey의 기능을 복제하지 않고, 전문 도메인 AI를 엔터프라이즈 제품으로 완성하는 운영 원리를 제조 경영 시스템에 맞게 재설계한다.  
> 구현 경계: 이 문서는 설계·우선순위 제안이다. 현재 진행 중인 G1-B/I-4 구현의 코드·DB·API를 변경하지 않는다.

---

## 1. 결론

Harvey는 법률 문서 업무를 중심으로 한 전문 AI이고, AI Factory Studio는 제조 기업의 실제 운영 데이터와 경영 의사결정을 다루는 시스템이다. 따라서 직접적인 기능 경쟁 상대는 아니다. 그러나 다음 질문에는 Harvey가 매우 좋은 기준점이다.

> 전문 지식, 조직 권한, 반복 업무, AI 모델, 산출물 검증과 도입 확산을 어떻게 하나의 엔터프라이즈 제품 경험으로 묶는가?

Harvey에서 참고할 핵심은 여섯 가지다.

1. **하나의 Assistant에서 탐색·분석·작성·검증을 연결한다.**
2. **업무별 자료 공간과 승인된 조직 지식을 구분한다.**
3. **개인의 업무 방법을 Workflow/Playbook으로 만들고 조직 표준으로 발행한다.**
4. **답변과 추출 결과를 원문 근거까지 되짚을 수 있게 한다.**
5. **모델 성능을 실제 장기 업무 과제로 평가한다.**
6. **기능 사용량이 아니라 도입·활용·ROI를 운영한다.**

AI Factory Studio는 여기에 다음 네 가지를 더해야 한다.

- 현업이 직접 만드는 **Host-governed App-in-App**
- MDM·카탈로그·Crosswalk·업무 사건을 연결하는 **제조 경영 온톨로지**
- LLM이 아닌 승인 수식이 숫자를 만드는 **결정론적 계산 그래프**
- 시뮬레이션에서 결정·실행·효과 측정까지 닫는 **경영 폐루프**

따라서 Harvey를 참고한 최종 목표는 `Harvey for Manufacturing`이 아니다.

> **현업 업무 생성, 기업 지식, 운영 데이터, 제조 경영 온톨로지와 결정론적 계산을 결합하여 실제 경영 결정을 실행하고 학습하는 Manufacturing Management Twin을 완성한다.**

---

## 2. 조사 범위와 공식 근거

| 영역 | 확인한 Harvey 공식 자료 | 확인한 핵심 |
|---|---|---|
| 통합 비서 | [Assistant](https://www.harvey.ai/platform/assistant) | 신뢰 원천 검색, 다단계 분석, 문서·표·프레젠테이션 생성, 인용 포함 결과 |
| 지식 운영 | [Knowledge](https://www.harvey.ai/platform/knowledge) | 조직 지식과 외부 전문 데이터 연결 |
| 대량 자료 공간 | [Vault](https://www.harvey.ai/platform/vault) | 대규모 문서 집합, Review Table, Knowledge Base, 권한 |
| 업무 자동화 | [Workflow Agents](https://www.harvey.ai/platform/workflow-agents) | 자연어로 맞춤 Agent를 만들고 조직 전문성과 템플릿으로 그라운딩 |
| 표준 업무 발행 | [Playbook Builder Permissions](https://help.harvey.ai/articles/beta-feature-new-playbook-builder-permissions) | Creator/Manager 역할, 공식 발행, 사용량·공유 범위 관리 |
| 검증 UX | [Review Table Cell Improvements](https://eu.help.harvey.ai/release-notes/review-cells-improvements) | 셀 단위 설명과 문장 단위 인용, 검증·수정 |
| 모델 운영 | [How to Choose an AI Model](https://help.harvey.ai/articles/multi-model) | 기본 자동 라우팅, 선택 기능은 관리자 통제 |
| 모델 구조 | [What AI Models Does Harvey Use?](https://help.harvey.ai/articles/what-ai-models-does-harvey-use) | 작업 분해·모델 위임·최종 종합의 다중 모델 구조 |
| 평가 | [Legal Agent Benchmark](https://www.harvey.ai/blog/introducing-harveys-legal-agent-benchmark) | 실제 장기 업무, 닫힌 자료 환경, 검토 가능한 결과물, 전문가 루브릭 |
| 보안 | [Security](https://www.harvey.ai/security) | SSO, 감사, 보존, 데이터 지역, 윤리 장벽, 고객 데이터 비학습 |
| AI 거버넌스 | [ISO 42001 및 AI Governance](https://www.harvey.ai/blog/governance-iso-42001) | 출처 계보·품질 게이트·사람 검토·제품 위험평가·감사 가능성 |
| 관리자 통제 | [Admin Settings](https://help.harvey.ai/articles/accessing-admin-settings) | 역할·모델·지식 원천·통합·공유·출력양식·분석 관리 |
| 도입 분석 | [Governance Controls](https://www.harvey.ai/blog/harveys-governance-controls) | 활성 사용자, 상위 Workflow, 제품 영역별 사용량, 협업 감사 |
| 도입 프로그램 | [Transformation Office](https://www.harvey.ai/blog/introducing-harveys-transformation-office) | 기술뿐 아니라 역량·소통·조직·거버넌스를 함께 운영 |
| 단계적 배포 | [Release Overview](https://help.harvey.ai/articles/release-overview) | 기능별 활성화 방식, 관리자 조치, 지역, Early Access, 단계적 배포 |

조사는 공개된 기능과 정책을 확인한 것이며, 비공개 내부 아키텍처나 실제 계약 조건을 추정하지 않는다.

---

## 3. Harvey의 제품 구조에서 배워야 할 것

### 3.1 Assistant는 채팅창이 아니라 작업 조정면이다

Harvey Assistant는 질의응답, 다단계 분석, 신뢰 자료 검색, 파일 생성과 내보내기를 한 표면에서 연결한다. 중요한 점은 기능이 많다는 것이 아니라 **사용자가 자료 위치와 실행 도구를 일일이 옮기지 않아도 하나의 업무 문맥이 유지된다는 것**이다.

#### 우리 시스템의 대응

자비스는 이미 화면 객체 문맥을 받고 시스템 전역 상태에 답할 수 있는 기반이 있다. 그러나 현재 핵심 응답은 주로 자연어 본문이고, 답변의 사실 종류와 근거를 강제하는 통합 계약이 없다.

자비스의 목표 응답은 다음 다섯 층으로 고정해야 한다.

1. **현재 확인된 사실**
2. **근거와 기준시점**
3. **온톨로지 영향 경로 또는 계산 계보**
4. **사용자가 선택할 수 있는 대안**
5. **권한 범위에서 실행 가능한 다음 행동**

자비스가 해야 하는 일은 `답변 생성`이 아니라 `근거를 가진 판단 준비`다.

### 3.2 Vault·Knowledge Base·Knowledge Sources의 분리는 제품 이해도를 높인다

Harvey는 다음을 구분한다.

- 특정 사건·업무 묶음의 자료 공간
- 조직이 승인한 지식 기반
- 외부 전문 데이터 원천
- 자료에서 구조화해 재사용하는 Review Table

우리 시스템도 기술적으로는 지식팩, 카탈로그, MDM, 외부지표, 문서 원본, 프로젝트 산출물을 갖고 있으나 사용자는 이들의 **용도와 신뢰 차이**를 한눈에 이해하기 어렵다.

#### 우리 시스템의 4층 지식 운영모델

| 제품 용어 | 목적 | 포함 데이터 | 권한·상태 |
|---|---|---|---|
| **업무 사례 공간** | 특정 프로젝트·시뮬레이션·의사결정에 필요한 문맥 | 파일, 대화, 산출물, Snapshot, 계산 결과, 결정 패키지 | 참여자·조직 범위 상속 |
| **전사 지식 기반** | 반복 사용이 승인된 조직 지식 | 표준, 선례, 템플릿, 계산 기준, 검증된 업무 설명 | 검토·승인·유효기간 필수 |
| **외부 신뢰 원천** | 공공·상용·공식 외부 정보 | 환율, 가격, 운임, 전기료, 정책·산업 자료 | 출처·발표일·빈티지·라이선스 필수 |
| **검토 데이터셋** | 문서·원천에서 추출한 구조화 결과 | 표 형태 추출값, 검증 상태, 셀별 근거 | 원천 권한 상속, 검증 전 경영 계산 금지 |

`업무 사례 공간`은 프로젝트 디렉터리의 새 이름이 아니다. **같은 경영 질문에 쓰인 자료·데이터·계산·결정·실행을 하나의 문맥 키로 묶는 제품 객체**다.

### 3.3 Review Table의 핵심은 표가 아니라 셀 단위 검증이다

Harvey의 Review Table에서 참고할 것은 대량 문서를 표로 만든다는 외형이 아니다. 각 결과를 원문과 연결하고, 사용자가 확인·수정·표시하며, 그 검증 결과를 다음 업무의 지식 원천으로 재사용한다는 점이다.

#### 우리 시스템 적용

우리 `검토 데이터셋`의 각 셀 또는 레코드는 최소 다음을 가져야 한다.

```json
{
  "value": "2026-09-15",
  "truth_class": "SOURCE",
  "source_ref": "shipment_notice_2026_0815.pdf#page=3",
  "source_version": "sha256:...",
  "extraction_method": "deterministic|llm|human",
  "confidence": "HIGH|MEDIUM|LOW",
  "verification_status": "UNVERIFIED|VERIFIED|CORRECTED|REJECTED",
  "verified_by": "user_id",
  "verified_at": "ISO-8601",
  "scope_node_id": "MNM_COPPER"
}
```

검증되지 않은 추출값은 검색과 검토에는 사용할 수 있지만, `Actual`·`Certified` 기준선이나 경영 계산에는 들어가지 못한다.

### 3.4 Workflow Agent와 Playbook은 개인 자동화와 조직 표준을 분리한다

Harvey는 Workflow를 만드는 권한과 조직에 공식 발행하는 권한을 분리하고, 발행 여부·소유자·실행 횟수·공유 범위를 관리한다.

우리 시스템에는 다음 자산이 이미 존재한다.

- 상담 Playbook과 Blueprint
- 에이전트·워크플로우 자산 거버넌스
- 개인·조직·전사 승격
- 스킬 개선 후보와 승인
- 생성 앱 Manifest와 Release

하지만 이 자산들의 생명주기가 서로 다른 모듈에 분산돼 있다. 하나의 `업무 템플릿 자산 계약`으로 정렬해야 한다.

#### 권고 상태 전이

```text
PERSONAL_DRAFT
  → TESTABLE
  → DEPARTMENT_PUBLISHED
  → ENTERPRISE_CANDIDATE
  → ENTERPRISE_APPROVED
  → DEPRECATED
  → RETIRED
```

| 전이 | 필수 조건 |
|---|---|
| DRAFT → TESTABLE | 입력·출력 계약, 허용 도구, 지식 원천, 비용 한도 |
| TESTABLE → DEPARTMENT_PUBLISHED | 골든 사례 통과, 소유 부서 검토, 권한 범위 |
| DEPARTMENT → ENTERPRISE_CANDIDATE | 복수 사용자 재현, 데이터 범용성, 보안 검사 |
| CANDIDATE → ENTERPRISE_APPROVED | 독립 검토, 전사 소유자, 버전·폐기 계획 |
| APPROVED → DEPRECATED | 대체 버전 지정, 신규 실행 금지 시점 |
| DEPRECATED → RETIRED | 보존·감사·기존 산출물 재현 정책 확인 |

자가검토를 금지하지 않는다. 개인·부서 실험은 스스로 검토하고 계속 개선할 수 있다. 다만 **조직 또는 전사 정본으로 발행하는 순간에만 독립 검토를 강제**한다.

### 3.5 다중 모델은 모델 목록보다 평가·권한·라우팅이 중요하다

Harvey는 기본적으로 작업을 나누고 모델을 선택한 뒤 결과를 종합한다. 사용자의 모델 선택은 선택 기능이며 관리자가 접근 권한을 통제한다.

우리 시스템은 이미 공급자 폴백, 모델 티어, 비용 추정, 품질 텔레메트리를 갖는다. 오히려 다음 면에서는 Harvey보다 더 투명하게 만들 수 있다.

- 관리자에게 실제 사용 모델·비용·지연·폴백 사유 공개
- 업무 유형별 모델 정책과 예산 공개
- 모델 변경 전후 골든 벤치마크 비교
- 고위험 업무는 비용보다 최소 품질 기준 우선
- 일반 사용자에게는 모델 이름보다 `빠른 처리 / 표준 / 정밀 분석` 정책으로 표현

Harvey의 Auto 모드처럼 사용 편의는 유지하되, 관리자에게까지 실제 라우팅을 숨기지는 않는다. **비용·품질 최적화가 우리 제품 해자이기 때문이다.**

### 3.6 실제 업무 기반 벤치마크가 제품 신뢰를 만든다

Harvey LAB은 짧은 질의응답이 아니라 `업무 지시 + 닫힌 자료 환경 + 검토 가능한 결과물 + 전문가 루브릭`으로 장기 업무 수행을 평가한다.

우리 `golden_benchmark`는 좋은 기반이지만 현재 중심은 생성 파이프라인과 산출물 품질이다. 이를 대체하지 말고 **제조 경영 장기 업무 평가층**을 추가해야 한다.

#### Manufacturing Management Task Benchmark v1

| 구성 | 계약 |
|---|---|
| Instruction | 현업 책임자가 주는 실제 업무 요청 형식 |
| Environment | 회사·조직 문맥, 승인 문서, Snapshot, 외부지표, 제한된 도구 |
| Expected Work Product | 앱, 검토표, 시뮬레이션, 의사결정 검토서, 보고서 중 하나 이상 |
| Deterministic Checks | 계산값, 필수 필드, 범위, 출처, 상태 전이 |
| Expert Rubric | 업무 완결성, 설명 가능성, 위험 누락, 실행 가능성 |
| Operational Metrics | 비용, 지연, 재시도, 사람 수정량, 근거 조회시간 |

초기에는 1,200개 과제를 흉내 내지 않는다. 첫 수직 폐루프를 닫는 12개 과제로 시작한다.

1. 원료 구매 계획 등록
2. 계약 가격·환율 적용
3. 선적·통관·운송 사건 대사
4. 도입 지연 탐지
5. 재고 가용량 영향 계산
6. 생산계획 영향 경로 설명
7. 납기·매출 영향 계산
8. 운전자본·현금흐름 계산
9. 세 가지 대안 시나리오 비교
10. 의사결정 3관점 검토서 생성
11. 승인 이후 실행과제 생성
12. 실제 결과 대사와 학습 후보 생성

평가는 다음 두 점수를 분리한다.

- **All-pass**: 필수 안전·정확성 조건을 하나라도 어기면 실패
- **Quality score**: 표현, 통찰, 편의성, 사용자 평가

안전 실패를 평균 품질점수로 상쇄하지 않는다.

### 3.7 도입은 기능 교육이 아니라 조직 변화 프로그램이다

Harvey는 도입을 기술만의 문제가 아니라 Skills, Communications, Structures, Governance를 포함하는 변화 프로그램으로 본다.

우리도 `시스템 설치 → 사용자 교육 → 사용 권고`로 끝내면 안 된다. 다음 운영체계가 필요하다.

| 역할 | 책임 |
|---|---|
| Executive Sponsor | 첫 경영 질문과 성공 기준 확정, 부서 간 충돌 해결 |
| Domain Owner | 데이터·업무 규칙·계산 기준 승인 |
| Product Steward | 템플릿·앱·지식 자산 생명주기 관리 |
| Data Steward | 품질·대사·용어·계보 관리 |
| AI Governance Owner | 모델·평가·비용·위험·감사 관리 |
| Adoption Lead | 사용자 온보딩, 활용도, 개선 피드백, 확산 |

제품 안에는 이 역할의 업무를 지원하는 `도입·성과 센터`가 필요하다.

---

## 4. 그대로 따라 하면 안 되는 것

### 4.1 외부 Shared Space

Harvey는 로펌과 고객이 같은 공간에서 협업하도록 외부 공유를 지원한다. 우리 제품은 경영 시스템이므로 외부 참여자에게 열지 않는다는 원칙을 유지한다.

- 외부 거래처·관세사·운송사는 고객사의 기존 시스템을 사용한다.
- AI Factory Studio는 MCP/API/DB View/파일 계약으로 승인된 데이터만 받는다.
- 외부 공유 기능 대신 **외부 원천 계약·수신 상태·대사·차단 사유**를 관리한다.

### 4.2 문서 중심 제품 구조

우리의 중심은 문서가 아니라 운영 사실·업무 사건·계산·결정이다. 문서와 지식은 근거지만, 경영 숫자의 진실 원천은 승인된 Snapshot과 계산 그래프다.

### 4.3 모델 추론을 계산 근거로 표시

사용자에게 모델의 내부 사고과정을 노출하거나 이를 계산 근거처럼 취급하지 않는다. 대신 다음을 보여 준다.

- 사용한 원천과 버전
- 온톨로지 관계 경로
- 적용한 계산식과 버전
- 가정값과 승인 상태
- 사용자 수정·승인 이력

### 4.4 범용 AI 기능 경쟁

문서 요약, 범용 검색, 챗봇, Workflow Builder만으로는 차별화되지 않는다. 모든 참고 기능은 첫 제조 경영 폐루프를 더 신뢰성 있게 완주하게 할 때만 우선한다.

---

## 5. 우리 시스템의 현재 상태 대조

### 5.1 이미 있는 강한 기반 — 새로 만들지 않는다

| Harvey 참고 영역 | AI Factory Studio 현재 자산 | 판단 |
|---|---|---|
| Knowledge Base | `core/knowledge_base.py`, 지식팩·조직 범위·검색 | 재사용 |
| Knowledge Catalog | `core/data_catalog.py`, 카탈로그·품질·계보 | 재사용 |
| Workflow/Playbook | `advisor_playbook`, Blueprint, agent governance | 통합 계약 필요 |
| 공식 발행·승격 | agent/skill/app 자산 승인·승격 기반 | 상태 정렬 필요 |
| Benchmark | `core/golden_benchmark.py`, benchmark API | 제조 경영 과제층 확장 |
| Usage/Cost | telemetry API, 비용·공급자·에이전트 집계 | 도입·ROI 지표 확장 |
| Quality outcomes | `quality_telemetry.py` | 사용자 수정·효과와 연결 |
| Evidence | decision ledger, evidence hash, scenario evidence | 자비스·보고서 공통 계약 필요 |
| Multi-model | LLM gateway·폴백·티어·쿨다운 | 관리자 정책·회귀 게이트 강화 |
| Scope/Governance | ECM·조직 권한·fail-closed·감사 | 자산별 정책 일관성 검증 |
| Assistant | Supervisor/Jarvis 엔진·화면 문맥 | 근거 응답·안전한 실행 확장 |

### 5.2 부분 구현 — 연결이 필요하다

1. **지식팩과 업무 사례가 분리돼 있다.** 검색 자료가 어느 결정·시뮬레이션에 쓰였는지 제품 객체로 묶이지 않는다.
2. **근거 구조가 모듈별로 다르다.** `evidence_refs`, `source`, `confidence`, `verified`가 존재하지만 공통 응답 봉투가 없다.
3. **Playbook·Workflow·Agent·Skill·App의 승격 상태가 정렬되지 않았다.** 사용자는 무엇이 개인 실험이고 전사 표준인지 한 화면에서 판단하기 어렵다.
4. **골든 벤치마크가 실제 경영업무 완결성을 충분히 평가하지 않는다.** 모델이 바뀌어도 같은 경영 결론·근거가 나오는지 별도 검증이 필요하다.
5. **텔레메트리가 기술 비용과 품질에 치우쳐 있다.** 사용자 시간 절감·의사결정 속도·수정량·실제 효과가 연결되지 않는다.
6. **자비스가 근거를 설명할 수는 있어도 계약으로 강제되지 않는다.** 답변별 사실 종류와 근거 누락을 서버에서 차단하지 않는다.

### 5.3 아직 부족한 제품 기능

- 업무 사례 공간과 문맥 Manifest
- 공통 `Grounded Output Envelope`
- 검토 데이터셋과 셀·필드 단위 검증
- 조직 표준 Workflow/Playbook 관리 콘솔
- 제조 경영 장기 업무 벤치마크
- 도입·성과·ROI 센터
- 기능별 Early Access·활성화·롤백 정책
- 지식 원천별 허용·보존·만료·재검토 관리

---

## 6. 공통 답변·산출물 신뢰 계약

### 6.1 `Grounded Output Envelope v1`

자비스 답변, 지식 검색, 보고서, 시뮬레이션 설명, 검토 데이터셋이 같은 계약을 사용한다.

```json
{
  "answer": "도입 지연은 제1공장 생산계획과 9월 현금흐름에 영향을 줍니다.",
  "claims": [
    {
      "claim_id": "clm-001",
      "text": "선적 일정이 15일 지연되었습니다.",
      "truth_class": "SOURCE",
      "evidence_refs": ["shipment_event:SHP-001:v3"],
      "as_of": "2026-08-15T09:00:00+09:00",
      "scope_node_id": "MNM_COPPER"
    },
    {
      "claim_id": "clm-002",
      "text": "9월 현금 유출이 기준선 대비 증가합니다.",
      "truth_class": "CALCULATED",
      "calculation_run_id": "calc-run-123",
      "formula_version": "cashflow-v2.1",
      "input_snapshot_ids": ["baseline-2026M08", "scenario-delay15"]
    }
  ],
  "context_omitted": false,
  "allowed_actions": ["open_evidence", "compare_scenario", "request_decision"],
  "model_trace_ref": "trace-admin-only-123"
}
```

### 6.2 사실 종류

| 코드 | 의미 | 경영 숫자 사용 |
|---|---|---|
| `SOURCE` | 원천에서 직접 확인한 사실 | 데이터 상태에 따라 가능 |
| `CALCULATED` | 승인된 계산 그래프 결과 | 가능 |
| `INFERRED` | 온톨로지·규칙·AI가 도출한 관계·해석 | 직접 숫자 확정 금지 |
| `PROPOSED` | AI 또는 사용자가 제안한 대안 | 승인 전 실행 금지 |
| `UNVERIFIED` | 근거나 검증이 부족한 내용 | 계산·결정 근거 사용 금지 |

### 6.3 UI 원칙

- 본문을 배지로 도배하지 않는다.
- 주장이나 수치 선택 시 `근거 패널`을 연다.
- 수치에는 `계산식 보기`, 사실에는 `원문 보기`, 추론에는 `영향 경로 보기`를 제공한다.
- 권한으로 가려진 근거는 존재·개수·사유를 노출하지 않고 `현재 권한에서 일부 문맥이 제외되었습니다`만 표시한다.
- 관리자에게만 모델·비용·라우팅 상세를 제공한다.

---

## 7. 적용 작업 패키지

### H0. 정본 계약과 용어 정렬 — 설계 선행

| ID | 작업 | 산출물 | 완료 기준 |
|---|---|---|---|
| H0-01 | 지식 4층 모델 확정 | 객체·상태·권한 표 | 기존 지식팩·카탈로그와 중복 없음 |
| H0-02 | Grounded Output Envelope | JSON Schema·오류 계약 | 자비스·보고서·검색 3종 예제 검증 |
| H0-03 | 업무 템플릿 자산 계약 | 상태 전이·역할·버전 | Agent/Skill/App/Playbook 대응표 승인 |
| H0-04 | 제조 경영 Benchmark 계약 | Task·Environment·Rubric Schema | 기존 golden benchmark 확장 경계 확정 |
| H0-05 | 도입·성과 지표 사전 | 이벤트·분모·소유자 | 비용과 효과를 같은 기간·범위로 집계 가능 |

### H1. 자비스 Evidence-first 응답 — G6 정렬

| ID | 작업 | 구현 포인트 | 검증 |
|---|---|---|---|
| H1-01 | 답변 봉투 적용 | Jarvis API에 claims·evidence 추가 | 근거 없는 수치가 `UNVERIFIED` |
| H1-02 | Evidence Resolver | 카탈로그·Snapshot·결정원장·계산 결과 통합 조회 | 원천 삭제·권한 회수 즉시 반영 |
| H1-03 | 근거 패널 | 원문·계산식·영향 경로 탭 | 1280/1440 가독성·키보드 접근 |
| H1-04 | 실행 가능 행동 제한 | `allowed_actions`를 서버 권한으로 생성 | 익명·읽기전용에게 쓰기 제안 0건 |
| H1-05 | 답변 회귀셋 | 같은 질문의 모델별 비교 | 필수 주장·근거 all-pass |

### H2. 지식 운영모델 — G2/G7 정렬

| ID | 작업 | 구현 포인트 | 검증 |
|---|---|---|---|
| H2-01 | 업무 사례 공간 | decision/scenario/project 문맥 Manifest | 모든 근거가 같은 회사·범위·mode |
| H2-02 | 전사 지식 기반 | 승인 자료·표준·템플릿 전용 컬렉션 | DRAFT 자료 검색 결과 혼입 0건 |
| H2-03 | 외부 신뢰 원천 | source registry·license·vintage·review_due | 만료·철회 원천 자동 제외 |
| H2-04 | 검토 데이터셋 | 구조화 추출·셀 근거·검증 상태 | 미검증 셀의 CERTIFIED 승격 차단 |
| H2-05 | 권한 상속 | 원천→추출표→산출물 권한 계승 | 이동·복제 시 권한 확대 0건 |
| H2-06 | 지식 관리 화면 | 사례/전사/외부/검토 데이터셋 구분 | 사용자가 10초 내 차이 설명 가능 |

### H3. Workflow·Playbook 승격 — G3/I-4 정렬

| ID | 작업 | 구현 포인트 | 검증 |
|---|---|---|---|
| H3-01 | 공통 자산 메타데이터 | owner·scope·version·status·sources·cost budget | 분산 자산 조회 일관성 |
| H3-02 | Builder/Publisher 분리 | 생성과 공식 발행 권한 분리 | 생성 권한만으로 전사 발행 불가 |
| H3-03 | Test Workspace | Synthetic/Preview 전용 실행 | Actual DB 쓰기 0건 |
| H3-04 | 공식 템플릿 Library | 개인·부서·전사 탭, 승인·버전 표시 | 사용자가 공식본을 명확히 식별 |
| H3-05 | 활용·품질 메타데이터 | run count·success·correction·cost·owner | 실행 수만 높은 저품질 자산 승격 금지 |
| H3-06 | 폐기·대체 | superseded_by·new_run_blocked_at | 기존 결과 재현 가능, 신규 실행 차단 |

I-4의 Runtime Contract Compiler가 먼저 완성되어야 H3의 앱·Workflow 계약을 런타임에서 강제할 수 있다. H3는 I-4를 우회하거나 별도 권한 체계를 만들지 않는다.

### H4. Manufacturing Management Task Benchmark — G8 선행

| ID | 작업 | 구현 포인트 | 검증 |
|---|---|---|---|
| H4-01 | 12개 Task Pack | 샘플 회사 데이터 키트 재사용 | 모든 과제 재현 가능 |
| H4-02 | 결정론적 검사 | 수치·필드·권한·근거·상태 | 안전 실패 all-pass 강제 |
| H4-03 | 전문가 루브릭 | 구매·물류·생산·재무 관점 | 평가자 간 불일치 기록 |
| H4-04 | 모델·라우팅 회귀 | 모델/정책/프롬프트 버전별 비교 | 품질·비용·지연 동시 비교 |
| H4-05 | 사람 수정량 | 최초 결과→승인 결과 diff | 수정시간·수정범주 계측 |
| H4-06 | Golden 승격 | 사람 승인·근거·버전 고정 | 무승인 Golden 생성 불가 |

### H5. 도입·성과 센터 — G7/G8 정렬

| ID | 작업 | 지표 | 완료 기준 |
|---|---|---|---|
| H5-01 | 활성·활용 | WAU/MAU, 부서, 기능, Workflow | 테스트 계정·샌드박스 제외 |
| H5-02 | 업무 효과 | 처리시간, 대기시간, 재작업, 보고서 작성시간 | 도입 전 기준선과 비교 |
| H5-03 | 경영 효과 | 재고·운전자본·납기·품질손실·예측오차 | 계산 근거와 실제 대사 연결 |
| H5-04 | AI 경제성 | 호출비용, 사람 수정시간, 성공 결과당 비용 | 미산정 비용을 0으로 표시하지 않음 |
| H5-05 | 자산 건강도 | 재사용, 실패, 소유자 부재, stale | 폐기·개정 후보 자동 제시 |
| H5-06 | 확산 운영 | 온보딩 단계·교육·피드백·챔피언 | 부서별 도입 병목 가시화 |

### H6. 엔터프라이즈 릴리스·관리자 통제 — G7 정렬

| ID | 작업 | 구현 포인트 | 완료 기준 |
|---|---|---|---|
| H6-01 | Feature Availability | OFF/EA/OPT_IN/GA/RETIRED | 기능별 관리자·지역·의존성 표시 |
| H6-02 | 단계적 배포 | 조직·역할·사용자별 활성화 | 즉시 롤백·감사 가능 |
| H6-03 | 모델 접근 정책 | 역할별 모델·정밀도·비용 한도 | 사용자 우회 선택 불가 |
| H6-04 | 지식 원천 토글 | 원천별 허용·보존·만료·재검토 | 비승인 원천 문맥 주입 0건 |
| H6-05 | 출력양식 관리 | 공식 보고서·문서 템플릿 | 외부 발간 승인과 연결 |
| H6-06 | 관리자 변경 감사 | 누가·언제·무엇을·왜 | 정책 직접 파일 편집 우회 차단 |

---

## 8. 구현 순서와 현재 작업 정렬

현재 Claude Code의 주 작업은 G1-B Host Runtime과 I-4 생성기 연동이다. 이 선행 통제를 흔들지 않는다.

```text
현재
├─ G1-B/I-4 Runtime Contract Compiler 완료
└─ H0 문서 계약 설계 병행

그다음
├─ H3 Workflow·Playbook 공통 자산 계약
├─ H1 자비스 Grounded Output Envelope 최소판
└─ H4 Benchmark Schema와 12개 Task 설계

G2 데이터·온톨로지 최소판 이후
├─ H2 업무 사례 공간·검토 데이터셋
├─ H1 Evidence Resolver·영향 경로 UI
└─ H4 실제 수직 폐루프 벤치마크 실행

G7/G8
├─ H5 도입·성과 센터
└─ H6 단계적 배포·관리자 통제
```

### 8.1 P0/P1/P2

| 우선순위 | 작업 | 이유 |
|---|---|---|
| P0 | H0-02 Grounded Output Envelope | 근거·수치·추정 경계의 정본 |
| P0 | H4-01~04 제조 경영 Benchmark 최소판 | 모델 변경과 품질 주장 검증 |
| P0 | H3-01~03 템플릿 자산 계약·권한·격리 | 현업 생성 기능을 조직 자산으로 안전하게 승격 |
| P1 | H1 Evidence-first 자비스 | 전역 비서 신뢰성과 실행 가능성 |
| P1 | H2 지식 4층 UI·검토 데이터셋 | 지식 운영을 사용자가 이해하고 검증 |
| P1 | H5 기술비용+업무효과 계측 | 파일럿 ROI 증명 |
| P2 | H6 단계적 배포 고도화 | 복수 조직 확산 전 필요 |

---

## 9. 문서별 업데이트 필요사항

### 9.1 `AI_FACTORY_STUDIO_PRODUCT_BIBLE.md` — 필수

추가할 원칙:

- 자비스와 모든 경영 산출물은 `SOURCE/CALCULATED/INFERRED/PROPOSED/UNVERIFIED`를 구분한다.
- 업무 사례 공간, 전사 지식 기반, 외부 신뢰 원천, 검토 데이터셋을 구분한다.
- 개인 업무 방법은 검증을 거쳐 부서·전사 표준으로 승격한다.
- 제품 성공은 기능 수가 아니라 실제 업무 결과·사람 수정량·ROI로 측정한다.

수정할 기존 내용:

- §8.1의 첫 파일럿이 아직 `경영계획–실적–외부환경`으로 남아 있다. 최신 전략과 로드맵의 `원료 구매·도입 계획 → 생산·현금·손익` 폐루프로 명시적으로 대체 표시해야 한다.

### 9.2 `strategy/AI_FACTORY_STUDIO_UNIQUE_PRODUCT_STRATEGY_2026-08-03.md` — 필수

추가할 내용:

- 전문 도메인 AI 제품화 기준점으로 Harvey를 별도 절에 기록
- 독자 해자를 가능하게 하는 운영 기반으로 `Grounded Output Contract`, `Template Promotion`, `Domain Benchmark`, `Adoption Analytics` 추가
- 모델 라우팅은 사용자 편의상 자동화하되 관리자에게 비용·품질·라우팅 근거를 공개한다는 차별점 명시

### 9.3 `roadmap/AI_FACTORY_STUDIO_FINAL_COMPLETION_EXECUTION_PLAN_2026-08-03.md` — 필수

기존 G단계를 늘리지 않고 다음에 배치한다.

- G2: H2 지식 4층·검토 데이터셋
- G3: H3 업무 템플릿 생명주기
- G6: H1 자비스 신뢰 응답 계약
- G7: H6 관리자 통제·단계적 배포
- G8: H4 제조 경영 Benchmark·H5 ROI

§16 검증 체계에는 `장기 업무 Task/Environment/Work Product/Expert Rubric`를 추가한다.

### 9.4 `LLM_MASTER_IMPLEMENTATION_SPEC_2026-07-28.md` — 필수

추가할 계약:

- Grounded Output Envelope JSON Schema
- 모델 내부 사고과정이 아니라 근거·계보·계산식만 노출
- 모델·프롬프트·지식·계산 버전 추적
- 모델 변경 시 제조 경영 벤치마크 회귀
- 사용자 모델 선택과 관리자 모델 정책의 우선순위

### 9.5 `uiux/LIVING_ENTERPRISE_IMPLEMENTATION_TRACEABILITY_2026-07-30.md` — 필수

추가 화면·컴포넌트:

- 업무 사례 공간
- 검토 데이터셋과 셀 근거 Drawer
- 공식 업무 템플릿 Library
- 자비스 근거·계산·영향 경로 패널
- 도입·성과 센터
- Feature Availability·모델·지식 원천 관리자 설정

### 9.6 `data-kits/*` — 필수

샘플 회사 데이터 키트를 벤치마크 환경으로 재사용한다.

- 각 데이터셋에 기대 업무 질문과 정답 범위
- 12개 Task Pack
- 결정론적 기대값
- 오류·결측·정정·취소 대조군
- 사람 검토 루브릭
- 기준 실행비용과 소요시간

### 9.7 용어사전 — 권고

Harvey 용어를 그대로 제품 용어로 가져오지 않는다.

| 외부 참고어 | 우리 권장어 |
|---|---|
| Vault | 업무 사례 공간 또는 업무 자료함 |
| Knowledge Base | 전사 지식 기반 |
| Knowledge Source | 신뢰 원천 |
| Review Table | 검토 데이터셋 |
| Workflow Agent | 업무 에이전트 또는 실행 템플릿 |
| Playbook | 업무 표준 플레이북 |
| Assistant | 자비스·AI 경영 보좌관 |

`Vault`는 기존 Secret Vault와 혼동되므로 사용자 용어로 사용하지 않는다.

### 9.8 제품소개서·브로셔 — 후속

외부 자료에는 Harvey 이름을 넣지 않고 다음 제품 경험을 보여 준다.

1. 현업 업무 앱 생성
2. 앱 데이터의 중앙 환류
3. 승인 지식과 외부 원천 연결
4. 온톨로지 영향 경로
5. 결정론적 계산
6. 자비스의 근거 있는 답변
7. 의사결정·실행·효과 측정

---

## 10. 적용 후 목표 사용자 경험

### 10.1 신규 사용자의 첫날

1. 회사·조직 문맥을 선택한다.
2. 자비스에게 하고 싶은 업무를 말한다.
3. 자비스가 권장 데이터·지식·업무 템플릿과 준비 상태를 제시한다.
4. 사용자는 공식 템플릿을 실행하거나 개인 초안을 만든다.
5. 부족한 데이터가 있으면 가능한 범위와 다음 준비 행동을 안내받는다.

### 10.2 현업 담당자의 반복 업무

1. 업무 사례 공간에 관련 원천과 Snapshot이 자동 연결된다.
2. 검토 데이터셋에서 추출값과 원문 근거를 확인한다.
3. Workflow가 앱·시뮬레이션·보고서를 생성한다.
4. 자비스가 확정 사실, 계산 결과, 추정과 제안을 구분한다.
5. 검증된 업무 방법은 부서 템플릿 후보가 된다.

### 10.3 경영자의 질문

> “환율이 10% 오르고 선적이 15일 늦어지면 9월 현금과 연간 손익은 어떻게 되는가?”

화면은 다음 순서로 답한다.

- 현재 확인된 운영 사실
- 영향을 받는 원료·공장·생산계획·매출·현금 경로
- 승인 계산식으로 산출한 기준선 대비 변화
- 대응안별 결과·위험·필요 결정
- 원천·기준시점·계산 버전
- 회의 요청 또는 시나리오 비교 실행

### 10.4 관리자와 제품 운영자

- 어떤 부서가 어떤 기능과 템플릿을 실제로 사용하는지 본다.
- 모델·원천·기능을 역할별로 활성화한다.
- 품질·비용·사용자 수정량·업무 효과를 함께 본다.
- 낮은 품질 또는 소유자 없는 자산을 개정·폐기한다.
- Early Access 기능을 제한 조직에서 먼저 검증하고 확대한다.

---

## 11. 검증 기준

### 11.1 신뢰

- 경영 숫자 100%가 `SOURCE` 또는 `CALCULATED`로 분류된다.
- `CALCULATED` 숫자 100%가 계산 run·식·입력 Snapshot으로 재현된다.
- `INFERRED/PROPOSED/UNVERIFIED`가 Actual로 승격되는 경로가 없다.
- 권한 밖 근거의 존재·개수·사유가 노출되지 않는다.

### 11.2 업무 템플릿

- 공식 템플릿은 소유자·버전·범위·시험·비용 한도를 가진다.
- 개인 생성 권한만으로 전사 표준을 발행할 수 없다.
- 공식본과 개인 복제본을 사용자가 구분할 수 있다.
- 대체·폐기 이후에도 과거 산출물을 해당 버전으로 재현할 수 있다.

### 11.3 벤치마크

- 12개 과제의 안전 필수조건 all-pass
- 모델·프롬프트·라우팅 변경 전후 자동 비교
- 사람 수정량과 검토시간 기록
- 비용 미산정 호출을 0원으로 합산하지 않음

### 11.4 도입 효과

- 도입 전 기준선과 도입 후 수치를 같은 기간·업무 범위로 비교
- 샌드박스·예시 계정·Synthetic 데이터 제외
- 기술 사용량과 업무 효과를 별도 표시
- 효과를 제품 기여로 단정하지 않고 다른 변화 요인을 기록

---

## 12. 위험과 방지책

| 위험 | 발생 형태 | 방지책 |
|---|---|---|
| Harvey 모방 제품으로 보임 | Vault·Workflow·Assistant 외형 복제 | 제조 경영 폐루프 기준으로 재명명·재설계 |
| 지식 구조 중복 | 기존 지식팩 옆에 새 저장소 생성 | 기존 자산을 4층 운영모델에 매핑 |
| 과도한 승인 | 모든 개인 개선에 독립 검토 강제 | 조직·전사 발행 시점에만 강제 |
| 근거 UI 과밀 | 모든 문장에 배지 표시 | 선택형 근거 패널·요약 배지 |
| 모델 추론 노출 | 내부 사고과정을 근거로 오인 | 출처·계보·식·가정만 제공 |
| 벤치마크 과대 구축 | 대규모 과제 생성에 개발 지연 | 첫 폐루프 12개로 시작 |
| 사용량을 ROI로 오인 | 실행 횟수가 높으면 성공으로 판단 | 시간·수정량·오차·경영효과와 분리 |
| 외부 사용자 개방 | Shared Space를 그대로 모방 | 기존 외부 시스템+MCP 경계 유지 |

---

## 13. 최종 권고

Harvey에서 가장 먼저 배울 것은 UI나 법률 기능이 아니다. **검증 가능한 전문지식을 반복 가능한 조직 업무로 만들고, 그 사용과 효과를 관리하는 제품 운영체계**다.

AI Factory Studio의 다음 제품화 작업은 아래 순서가 가장 효과적이다.

1. `Grounded Output Envelope`를 정본으로 확정한다.
2. I-4 이후 Workflow·Playbook·Agent·App의 공통 승격 계약을 연결한다.
3. 샘플 회사 데이터 키트로 제조 경영 장기 업무 12개를 만든다.
4. 자비스의 답변을 근거·계산·추정·제안으로 분리한다.
5. 지식 허브를 업무 사례·전사 지식·외부 원천·검토 데이터셋으로 재구성한다.
6. 기술 텔레메트리를 도입·업무효과·ROI까지 확장한다.
7. 복수 조직 확산 전에 기능·모델·지식 원천의 단계적 배포 통제를 완성한다.

이 작업이 완료되면 우리 제품의 차별화는 다음 한 문장으로 설명할 수 있다.

> **Harvey가 법률 전문지식을 신뢰 가능한 AI 업무로 제품화했다면, AI Factory Studio는 기업의 실제 운영 데이터와 제조 경영 지식을 온톨로지·계산·현업 앱·의사결정 폐루프로 제품화한다.**

