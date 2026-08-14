# [I-4] 생성기 ↔ Host Runtime 연동 — 상세 설계 **rev.3**

**작성 2026-08-15 · rev.3 2026-08-15 · 상태: 구현 승인(순서 §20) · 코드 변경 0건**

선행: `docs/design_app_data_plane_2026-08-08.md` ·
`docs/handoff/G1B_P0_APP_RUNTIME_HANDOFF_2026-08-14.md` · `[G1-B-CANARY-REVIEW-89]` 완료 판정.
개정 근거: 교차검토 `[G1-B-I4-DESIGN-REVIEW-90]`(rev.2) · `[G1-B-I4-DESIGN-REVIEW-91]`(rev.3).

> ★ rev.3 으로 **구현이 승인됐다**(교차검토 91). 착수 순서는 §20 이고, 각 단계는 그 단계까지의
> 회귀를 갖고 커밋한다. 이 문서 자체는 여전히 코드 변경 0건이다.

---

## 0. rev.1 의 전제가 틀렸다 — 실측으로 확인한 것

rev.1 은 「`Tech_Lead.hotl_after=True` 하나면 계약이 코드보다 먼저 온다」고 적었다.
**그것은 사실이 아니다.**

```python
# core/agent_graph.py:100  _route_to_first_assigned()
if include_design:
    if include_architect and _has_role(agents, "Architect", ...): return "Architect"
    if _has_role(agents, "Tech_Lead", ...):                       return "Tech_Lead"
if _has_role(agents, "Backend", ...):  return "Backend"      # ← 여기로 바로 간다
```

실행 태스크의 `required_agents` 에 Tech_Lead 가 없으면 **설계 단계를 건너뛰고 코드 생성으로
진입한다.** 즉 rev.1 안대로 하면 **일부 앱은 계약 없이 만들어진다** — 그리고 그런 앱일수록
「간단해 보여서」 배정이 생략된 앱이다.

★★★ 그래서 결론이 바뀐다:

> **Tech Lead 가 계약을 «초안» 하고, 시스템이 계약을 «결정론적으로 컴파일·강제» 하며,
> 검증된 후보만 활성 릴리스로 «승격» 한다.**

세 동사가 각각 다른 주체다. 하나로 뭉치면 그 지점이 우회로가 된다.

### 함께 확인한 두 가지 (rev.2 가 고치는 것)

| 실측 | 무엇이 문제인가 |
|---|---|
| `core/app_proof.py:manifest_actions()` 가 capability 를 **전역 합집합**으로 평탄화 | `orders.read` + `secrets.update` 선언이 **`orders` 에도 write** 를 연다 |
| `state_models.py:95` `ProjectState(extra='forbid')`, 계약 필드 없음 | Tech Lead 가 계약을 산출해도 **상태를 통과하지 못한다** |

---

## 1. 능력 상태 다섯 — 「지원 대기」와 「허용되지 않음」은 다른 말이다

⚠️⚠️ 자체 로그인·직접 API 호출을 「지원 대기」로 적으면 사용자는 **언젠가 열린다고 읽는다.**
그리고 그때까지 우회로를 찾는다. 그 둘은 영원히 열리지 않는다.

| 상태 | 사용자 표시 | 뜻 |
|---|---|---|
| `SUPPORTED` | 지원됨 | 지금 만들 수 있다 |
| `CONDITIONAL` | 조건부 지원 | 범위 안에서만(§1-2) |
| `HOST_SERVICE_REQUIRED` | Host 기능 필요 | 앱이 아니라 **플랫폼이** 해야 한다 |
| `NOT_YET_SUPPORTED` | 지원 대기 | 계획에 있고 아직 없다 |
| `PROHIBITED` | 플랫폼 정책상 허용되지 않음 | **열 계획이 없다** |

### 1-1. 결정표 (닫힌 목록 — 코드 상수)

| 요구 능력 | 상태 | 근거 |
|---|---|---|
| 앱 데이터 조회·등록·수정·삭제 | `SUPPORTED` | `window.afs.data` |
| 자체 로그인·권한·세션 | **`PROHIBITED`** | 회사 권한 체계 밖에서 인증하게 된다 |
| 직접 App Data API 호출 | **`PROHIBITED`** | 증명 경계를 우회한다 |
| 브라우저 토큰·자격증명 저장 | **`PROHIBITED`** | B02 |
| 앱 전용 DB·권한 테이블 | **`PROHIBITED`** | 판정이 두 곳이 된다 |
| 집계·복합 질의 | `CONDITIONAL` | §1-2 의 경계 안에서 |
| 파일 업로드 | `NOT_YET_SUPPORTED` | 데이터 평면에 바이너리 없음 |
| 백그라운드 작업 | `NOT_YET_SUPPORTED` | 앱은 프레임 수명 안에서만 산다 |
| 외부 API·MCP 호출 | `HOST_SERVICE_REQUIRED` | CSP `connect-src 'none'` · Host 중개 |
| 업무 액션(승인·발주·통보) | `HOST_SERVICE_REQUIRED` | 원장·승인 흐름을 지나야 한다 |
| 경영 시뮬레이션 계산 | `HOST_SERVICE_REQUIRED` | **G4 계산 그래프** — `afs.data` 아님 |
| 그 밖의 서버 로직 | `HOST_SERVICE_REQUIRED` | 임의 FastAPI 생성 금지 |
| **표에 없는 것** | **`NOT_YET_SUPPORTED`** | ⚠️ 아래 |

⚠️⚠️ **모르는 intent 를 자동 허용하지 않는다.** 표에 없으면 `NOT_YET_SUPPORTED` 로 떨어지고
사용자 선택을 받는다 — 「모르니까 되겠지」가 곧 통제 없는 기능이다.

### 1-2. `CONDITIONAL` 의 경계를 숫자로

지금 데이터 평면이 **실제로** 할 수 있는 것:

    한 데이터셋 · 페이지 단위(limit ≤ 100) · 정렬 고정(생성 역순) · 필터 없음

· 지원: **상한 안에서 화면이 계산하는** 집계(합계·평균·그룹 표시)
· 대기: 조인 · 데이터셋 간 집계 · 전체 스캔 통계 · 정렬/필터 지정 ·
  `total` 이 상한을 넘는 전수 집계

⚠️ 「일단 다 받아서 계산한다」를 허용하지 않는다 — 데이터가 늘어난 날 **조용히 틀린 합계**를
보여준다. 그때 화면은 아무 오류도 내지 않는다.

---

## 2. 누가 무엇을 정하는가 — LLM 은 요구를 읽되 지원 여부를 정하지 않는다

| 주체 | 하는 일 | 하지 않는 일 |
|---|---|---|
| **LLM**(Tech Lead) | 자연어 요구 → `capability_intents` 구조화, 데이터셋·필드 **초안** | 지원 여부 판정 · 지문 계산 · 어댑터 생성 |
| **Compiler**(비-LLM) | 결정표로 상태 판정 · 계약 검증·정규화 · 의미 지문 · typed 어댑터 생성 | 없는 요구를 지어내기 |
| **사용자** | 축소 / 대기 / Host 기능 확장 중 **선택** | — |

★ 판정을 LLM 에서 떼어 내는 이유: 같은 요구에 대해 어제와 오늘의 답이 달라지면 그 차이는
**릴리스가 나온 뒤에야** 드러난다. 결정표는 두 번 물어도 같은 답을 준다.

---

## 3. 파이프라인 — Tech Lead 필수화 + 결정론적 컴파일러

```text
RFP / PMO
  └─ 요구 능력 «의도» 만 구조화 (capability_intents)          [기존 LLM 노드]
        │
I-4 대상 실행 태스크
  └─ Tech_Lead 를 **필수 역할로 정규화**                      [배정 규칙 변경]
        └─ Manifest · Dataset 초안                            [기존 LLM 노드]
        │
HostContractCompiler                                          [신규 · 비-LLM]
  ├─ 결정표로 지원 상태 판정
  ├─ 계약 검증·정규화 (JSON Schema)
  ├─ 의미 지문(semantic_fingerprint) 생성
  └─ Typed SDK Adapter 생성 (src/generated/afs-contract.ts)
        │
ContractReviewGate                                            [신규 · 비-LLM]
  ├─ 최초 계약 또는 **지문 변경** → 사용자 검토
  └─ 지문 불변 → 자동 통과
        │
Backend / Frontend → CodeBuilder → 정적 검사 → …
```

### 왜 새 LLM 에이전트를 만들지 않는가

에이전트가 늘면 토큰·시간·실패 지점이 함께 는다. 그리고 **판정은 LLM 이 할 일이 아니다**(§2).
두 신규 노드는 전부 **비-LLM 시스템 노드**다(`CodeBuilder` 와 같은 부류: `llm: False`).

### Tech Lead 필수화의 범위

⚠️⚠️ rev.2 는 여기서 「앱 데이터를 다루는 태스크만」이라고 적었다. **그것은 순환 논리였다** —
  데이터 사용을 놓친 태스크가 곧 계약을 우회하는 태스크가 된다. **§15 로 대체됐다.**

### 기존 프로젝트에 끼워 넣지 않는다

`host_runtime_contract_v1` 이 활성화된 **신규 워크플로우부터** 적용한다.
⚠️ 진행 중 프로젝트에 노드를 삽입하면 `completed_agents` 순서 전제와 체크포인터 상태가
어긋난다 — 그 결함은 재개할 때에야 드러나고, 그때는 원인을 찾기 어렵다.

---

## 4. 계약의 네 계층 — 「어디가 정본인가」를 하나로 답하지 않는다

⚠️ rev.1 은 `release.json` 과 `app_datasets` 중 **하나를 고르려** 했다. 그 질문 자체가
틀렸다 — 둘은 책임이 다르다.

| 계층 | 위치 | 책임 | 바뀌면 |
|---|---|---|---|
| **설계 정본** | `<workspace>/contracts/app_runtime_contract.json` | 승인 전후의 계약 원문 | 지문이 바뀐다 → 재승인 |
| **승인 증거** | `decision_ledger` | **누가 어떤 지문을 승인했는가** | 추가만 된다(불변) |
| **릴리스 봉인** | `release.json` | 그 릴리스가 쓴 계약 스냅샷 | 릴리스마다 고정 |
| **런타임 투영** | `app_datasets` 표 | 승인된 계약의 **물질화** | 계약을 따라간다 |

★★★ `app_datasets` 는 **정본이 아니라 투영본**이다. 그래서:

· I-4 릴리스에서는 관리자도 **계약 밖 데이터셋을 만들 수 없다** → `409`
· 바꾸려면 **계약 개정 → 재승인 → 재물질화** 순서를 지나야 한다
· 레거시 릴리스만 **명시적 예외 모드**로 구분한다(`requires_host_runtime: false`)

⚠️ 「관리자니까 예외」를 두지 않는다. 예외가 있으면 계약은 설명서가 되고, 설명서는 곧 낡는다.

---

## 5. Dataset Contract — 버전형 JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "afs://contracts/app_runtime_contract/1.0",
  "title": "App Runtime Contract",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "contract_id", "revision", "project_id",
               "runtime_contract_version", "status", "app_class",
               "capability_intents", "manifest", "datasets",
               "unsupported_requirements", "semantic_fingerprint", "approval"],
  "properties": {
    "schema_version": {"const": "1.0"},
    "contract_id": {"type": "string", "pattern": "^contract_[a-z0-9]{12}$"},
    "revision": {"type": "integer", "minimum": 1},
    "project_id": {"type": "string"},
    "task_id": {"type": "string"},
    "runtime_contract_version": {"type": "integer", "enum": [1]},
    "status": {"enum": ["DRAFT", "COMPILED", "APPROVED", "SUPERSEDED"]},
    "app_class": {"enum": ["personal", "departmental", "enterprise"]},

    "capability_intents": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["intent_id", "requirement_ref", "capability", "status"],
        "properties": {
          "intent_id": {"type": "string"},
          "requirement_ref": {"type": "string"},
          "capability": {"type": "string"},
          "status": {"enum": ["SUPPORTED", "CONDITIONAL", "HOST_SERVICE_REQUIRED",
                              "NOT_YET_SUPPORTED", "PROHIBITED"]},
          "reason": {"type": "string"},
          "user_decision": {"enum": ["", "REDUCE", "WAIT", "REQUEST_HOST_FEATURE"]}
        }
      }
    },

    "manifest": {"type": "object"},

    "datasets": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["name", "label", "purpose", "allowed_actions", "fields"],
        "properties": {
          "name": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,63}$"},
          "label": {"type": "string"},
          "purpose": {"type": "string", "minLength": 1},
          "allowed_actions": {
            "type": "array", "minItems": 1, "uniqueItems": true,
            "items": {"enum": ["read", "create", "update", "delete"]}
          },
          "ontology_entity_type": {"type": "string"},
          "knowledge_eligibility": {
            "enum": ["OPERATIONAL_UNVERIFIED", "OPERATIONAL_VERIFIED",
                     "REFERENCE_CANDIDATE", "NOT_ELIGIBLE"]
          },
          "fields": {
            "type": "array", "minItems": 1,
            "items": {
              "type": "object",
              "additionalProperties": false,
              "required": ["name", "type", "required", "classification"],
              "properties": {
                "name": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,63}$"},
                "type": {"enum": ["string", "text", "number", "boolean", "date"]},
                "required": {"type": "boolean"},
                "label": {"type": "string"},
                "business_term_id": {"type": "string"},
                "semantic_role": {
                  "enum": ["", "identifier", "event_time", "quantity", "amount",
                           "status", "party", "location", "note"]
                },
                "unit": {"type": "string"},
                "classification": {"enum": ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]},
                "master_reference": {"type": "string"}
              }
            }
          }
        }
      }
    },

    "unsupported_requirements": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["requirement_ref", "status", "user_decision"],
        "properties": {
          "requirement_ref": {"type": "string"},
          "status": {"enum": ["HOST_SERVICE_REQUIRED", "NOT_YET_SUPPORTED", "PROHIBITED"]},
          "reason": {"type": "string"},
          "user_decision": {"enum": ["REDUCE", "WAIT", "REQUEST_HOST_FEATURE"]}
        }
      }
    },

    "semantic_fingerprint": {"type": "string", "pattern": "^[0-9a-f]{16}$"},

    "approval": {
      "type": "object",
      "additionalProperties": false,
      "required": ["status"],
      "properties": {
        "status": {"enum": ["PENDING", "APPROVED", "REJECTED"]},
        "approved_by": {"type": "string"},
        "approved_at": {"type": "string"},
        "decision_ledger_id": {"type": "string"}
      }
    }
  }
}
```

### 왜 `business_term_id`·`unit`·`classification` 이 **필수 수준**인가

⚠️ 이 셋이 없으면 현업 앱의 데이터가 중앙에 쌓여도 **G2 온톨로지와 전사 시뮬레이션에서 쓸 수
없다.** 「도착일」이라는 컬럼이 무슨 사건의 시각인지, 「수량」이 톤인지 개인지, 그 값을
누구에게 보여도 되는지를 나중에 사람이 추측하게 된다 — 그리고 추측한 숫자로 경영 판단을 한다.

★ 다만 `business_term_id`·`master_reference` 는 **비어 있을 수 있다**(용어가 아직 없을 수
있다). 대신 `classification` 은 **필수**다 — 등급 없는 데이터는 공유 판단을 할 수 없다.

### 의미 지문(`semantic_fingerprint`)에 들어가는 것

```
app_class · 각 데이터셋의 (name, allowed_actions, ontology_entity_type)
         · 각 필드의 (name, type, required, unit, classification, semantic_role)
         · capability_intents 의 (capability, status, user_decision)
```

⚠️ **들어가지 않는 것**: `label`·`purpose`·`reason` 같은 설명 문구. 문구를 다듬었다고
재승인을 요구하면 사람이 게이트를 습관으로 통과시킨다.

---

## 6. 데이터셋별 `allowed_actions` — 런타임에서 강제한다

### 지금 무엇이 틀렸나 (실측)

`core/app_proof.manifest_actions()` 는 매니페스트의 모든 capability 를
`read/write/delete/manage` 의 **전역 합집합**으로 평탄화한다. 따라서

```
orders.read
secrets.update
```

를 선언하면 증명에는 **전역 `read + write`** 가 들어가고, 판정은 `orders` 에 대한 write 를
막을 근거가 없다. **데이터셋별 권한이 아니었다.**

### 두 단계 판정

```
1차 — 데이터셋을 알기 전:  증명 · 릴리스 · 앱 · 조직 · 세션 · 문맥 · 전역 capability
       (현행 `_judge`. 열거 오라클을 막으려고 데이터셋보다 먼저 끝난다)
2차 — 자기 릴리스의 데이터셋을 이름으로 해석한 뒤:
       그 데이터셋의 계약상 `allowed_actions` 에 이번 행동이 있는가
```

★ 순서를 바꾸지 않는다. 1차를 데이터셋 뒤로 옮기면 **만료·타인 증명으로 이름을 열거**할 수
있게 된다([교차검토 86] 에서 실제로 열렸던 구멍이다).

⚠️ 2차 거부는 **그 앱 자신의 사실**이므로 `FORBIDDEN` 으로 알린다 — 숨기면 개발자가
계약을 고칠 방법을 모른다. 반면 **계약에 없는 이름**은 `NOT_FOUND` 다(존재를 알리지 않는다).

### 필수 회귀

· `orders.read` 만 선언한 앱이 `orders.update` **불가**
· `secrets.update` 선언이 **`orders.update` 를 열지 않는다**(전역 합집합 회귀 방지)
· 계약에 없는 데이터셋 이름 → **404**
· 동적으로 조립한 데이터셋 이름으로 계약을 **우회할 수 없다**
· 계약 개정으로 `allowed_actions` 가 줄면 **기존 증명이 즉시 막힌다**(지문 결속과 같은 축)

---

## 7. 생명주기 — Preview 와 Release 의 순서를 확정한다

rev.1 은 §2 에서 `Preview → Release`, §6 에서 `Release → Preview` 라고 적었다. **모순이다.**
그리고 현행 Host Runtime 증명은 `release_id` 를 요구하므로 **릴리스 없이 실제 Runtime
Preview 를 돌릴 수 없다.**

```
DRAFT → CONTRACT_APPROVED → RELEASE_CANDIDATE → PREVIEW_APPROVED → ACTIVE
                                   ↓ (정적 검사 실패)
                              QUARANTINED
```

### 상태 전이표

| 현재 | 사건 | 다음 | 가드(성립해야 넘어간다) |
|---|---|---|---|
| `DRAFT` | 컴파일 성공 | `DRAFT` | JSON Schema 통과 · 지문 생성 |
| `DRAFT` | 사용자 승인 | `CONTRACT_APPROVED` | 지원 대기 항목마다 `user_decision` 존재 · 원장 기록 |
| `CONTRACT_APPROVED` | 코드 생성·빌드 | `RELEASE_CANDIDATE` | 계약 지문 불변 |
| `RELEASE_CANDIDATE` | 정적 검사 **실패** | `QUARANTINED` | — |
| `RELEASE_CANDIDATE` | 정적 검사 통과 | `RELEASE_CANDIDATE` | 금지 신호 0건 · 미선언 데이터셋 0건 |
| `RELEASE_CANDIDATE` | Preview 종단 통과 | `PREVIEW_APPROVED` | 여섯 작업 성공 · 부정 시나리오 차단 |
| `PREVIEW_APPROVED` | 승격 | `ACTIVE` | **코드 해시·계약 지문이 후보와 동일** |
| `QUARANTINED` | 재생성 | `DRAFT` | — |
| `ACTIVE` | 계약 개정 | `DRAFT`(새 revision) | 옛 릴리스는 그대로 남는다 |

### `RELEASE_CANDIDATE` 는 활성 릴리스가 아니다

· 활성 라이브러리에 **노출되지 않는다** · 전달·앱 주머니 등록 **불가**
· **Preview 전용 격리 데이터**와 **Preview 전용 증명**만 쓴다
  (증명에 `purpose="preview"` 를 박고, 그 증명은 후보 릴리스에만 유효하다)

⚠️⚠️ **승격은 «같은 것» 임을 확인하고 한다.** 후보와 활성의 코드 해시나 계약 지문이 다르면
거부한다 — 「Preview 에서 본 것」과 「현업이 쓰는 것」이 다르면 그 검증은 아무 뜻이 없다.

---

## 8. 게이트는 하나 — 지문이 바뀔 때만 연다

| 자리 | 무엇을 |
|---|---|
| 기존 RFP 게이트 | 지원 상태 **예비 안내**(이 요구 중 넷은 지금 못 한다) |
| 기존 PMO 게이트 | WBS 에서 **지원 대기 작업 확인** |
| **신규 Contract Review Gate** | **최종 계약 승인** |

여는 조건 — 아래 중 하나라도 참일 때만:

· 최초 계약 · capability 변경 · 데이터셋/필드/`allowed_actions` 변경
· 조직 범위·데이터 등급 변경 · 지원 대기 항목의 처리 방향 변경

⚠️ **단순 코드 재작업으로 지문이 같으면 다시 열지 않는다.** 매번 멈추면 사람은 내용을 읽지
않고 통과 버튼을 누르게 되고, 그 순간 게이트는 장식이 된다.

---

## 9. 정적 검사 — 게시와 산출물 보존을 분리한다

rev.1 의 「게시는 되지만 증명이 안 나간다」는 **기각한다.** 현업은 게시된 앱을 **쓸 수 있는
제품**으로 읽는다. 게시 뒤 데이터가 안 붙으면 그것은 보안 통제가 아니라 **고장 난 제품**이고,
그 평판은 Host Runtime 전체에 붙는다.

```
코드 생성 완료 → RELEASE_CANDIDATE
  ├─ 검사 실패 → QUARANTINED (산출물·근거 보존, 활성 노출 없음)
  └─ 검사 통과 → Preview 승인 → ACTIVE 로 원자적 승격
```

★ 「검사 실패로 산출물이 사라진다」는 걱정은 **후보를 보존**하면 풀린다. 보존을 위해
**활성 게시를 허용할 이유는 없다.**

### 검사 신호 — 기존 여섯에 다섯을 더한다

현행 `nodes/utils/platform_auth_checker.py` 가 이미 잡는 것(실측):
`local_login_form` · `local_login_route` · `password_storage` · `jwt_issuer` ·
`local_user_store`(block) · `auth_library`(warn)

| 추가 신호 | 잡는 것 | 심각도 |
|---|---|---|
| `token_in_browser_store` | 브라우저 저장소에 **토큰·자격증명** | block |
| `direct_appdata_call` | `/api/v1/appdata` 직접 호출 | block |
| `generic_host_fetch` | 호스트를 향한 범용 `fetch`/XHR/WebSocket | block |
| `app_local_db` | 앱 전용 DB·권한 테이블 | block |
| `undeclared_dataset` | **어댑터를 거치지 않은** `window.afs.data.*` 직접 호출 | block |

⚠️ **검사기의 어려운 부분은 「무엇을 잡을까」가 아니라 「무엇을 놓아줄까」다**(그 파일 머리말이
이미 못박았다). 오탐이 늘면 검사기는 꺼지고, 꺼진 검사기는 없는 것과 같다.
예: 앱이 **자기 화면 상태**를 `localStorage` 에 두는 것은 정상이다(브리지가 가짜 저장소로
갈아끼운다) — 잡을 것은 **토큰·자격증명**이다.

---

## 10. Typed SDK Adapter — LLM 이 데이터셋 문자열을 쓰지 않게

Compiler 가 **결정론적으로** 생성한다:

```ts
// src/generated/afs-contract.ts   ⚠️ 자동 생성 — 손으로 고치지 않는다
export const materialArrivals = {
  list:   (page?: { limit?: number; cursor?: string }) =>
            window.afs.data.list('material_arrivals', page),
  get:    (recordId: string) => window.afs.data.get('material_arrivals', recordId),
  create: (payload: MaterialArrival) =>
            window.afs.data.create('material_arrivals', payload),
  // ⚠️ 계약의 allowed_actions 에 'delete' 가 없으므로 remove 는 **생성되지 않는다**
};
```

LLM 은 이 어댑터만 `import` 한다. 직접 `window.afs.data.*` 를 부르면 §9 의
`undeclared_dataset` 이 잡는다.

★★★ 이렇게 하면 **미선언 데이터셋 · 동적 이름 · 오탈자 · 허용되지 않은 update/delete** 를
정규식 추정이 아니라 **구조적으로** 막는다. 없는 함수는 타입 검사에서 먼저 걸린다.
그리고 LLM 이 쓸 코드가 줄어 토큰과 실패 확률이 함께 준다.

⚠️ 어댑터는 **두 번째 그물**이다. 서버의 2차 판정(§6)이 첫 번째다 — 어댑터만 믿으면
브라우저에서 고쳐 부르는 순간 통제가 없다.

---

## 11. `ProjectState` 에 계약 필드를 더한다

`state_models.py:95` 는 `extra='forbid'` 다. 필드를 선언하지 않으면 Tech Lead 가 계약을
산출해도 **상태가 그것을 버린다**(그리고 조용히 버린다).

```python
capability_intents: List[Dict[str, Any]] = Field(default_factory=list)
app_runtime_contract_status: str = Field(default="")        # DRAFT|COMPILED|APPROVED
app_runtime_contract_fingerprint: str = Field(default="")
app_runtime_contract_summary: str = Field(default="")       # 사람이 읽는 요약
unsupported_requirements: List[Dict[str, Any]] = Field(default_factory=list)
approved_contract_fingerprint: str = Field(default="")      # 게이트가 비교하는 값
```

★ **계약 원문은 workspace 파일이 정본**이고 상태에는 **요약·상태·지문만** 둔다.
⚠️ 원문을 상태에 넣으면 체크포인터가 매 단계 그것을 복사하고, 커지는 상태는 재개를 느리게
만든다(그리고 언젠가 잘린다).

---

## 12. 온톨로지·업무용어 매핑 — 왜 지금 넣는가

I-4 로 만든 앱의 데이터가 중앙에 쌓이는 것이 G2 의 입력이다. 그런데 매핑을 **나중에** 붙이면
그때는 이미 수십 개 앱이 각자 다른 이름으로 같은 것을 부르고 있다.

· `ontology_entity_type` — 이 데이터셋이 온톨로지의 어느 객체 유형인가(비어 있을 수 있다)
· `business_term_id` — 이 필드가 어느 표준 용어인가(마스터 데이터의 용어집)
· `semantic_role` — 사건 시각인가 수량인가 상태인가(닫힌 목록)
· `unit` — 톤인가 개인가(수량·금액에는 사실상 필수)
· `classification` — 등급(**필수**)
· `master_reference` — 코드 값이 어느 기준정보를 참조하는가

⚠️ 강제 수준을 낮게 잡는다: **`classification` 만 필수**, 나머지는 비어도 계약이 성립한다.
전부 필수로 하면 Tech Lead 가 값을 **지어낸다** — 그러면 없느니만 못하다.

---

## 13. 완료 관문

```
자연어 요구 입력
 → capability_intents 구조화(LLM)
 → 결정표 판정(Compiler) · 지원 대기 항목마다 사용자 선택
 → Manifest · Dataset Contract 컴파일 · 지문 생성
 → Contract Review Gate 승인(원장 기록)
 → typed 어댑터 생성 → 앱 코드 생성
 → 정적 검사: 자체 인증 0 · 직접 API 호출 0 · 미선언 데이터셋 0
 → RELEASE_CANDIDATE
 → Preview 에서 window.afs 준비 · 여섯 작업 성공
 → 다른 앱 · 다른 조직 · 다른 세션 차단
 → 로그아웃 · Manifest 변경 · 프로그램 중단 **즉시** 반영
 → 코드 해시·계약 지문 동일 확인 → ACTIVE 승격
```

⚠️ **하나의 종단 실행으로 본다.** 단계별로 따로 초록을 모으면 「각 조각은 되는데 이어 붙이면
안 되는」 상태를 놓친다 — 이 저장소가 반복해 겪은 유형이다.

---

## 14. 확정된 결정 셋 (교차검토 91)

### 14-1. Preview 데이터는 **물리적으로 분리된 DB** 다 — `data/app_preview.db`

네임스페이스 분리를 기각하고 **별도 파일**로 간다.

⚠️⚠️ 같은 DB 에 두면 **조회 실수 한 번**으로 Preview 데이터가 경영 집계에 섞인다. 그리고 그
섞임은 조용하다 — 숫자가 조금 커질 뿐 아무 오류도 나지 않는다. 보존·폐기 정책도 다르고,
후보를 지울 때 「그 후보의 데이터만」 지우는 것이 파일 분리면 자명해진다.

**고정 규칙**

· `candidate_id` 기준 격리 · **`SYNTHETIC_TEST` 데이터만** 허용 · 운영 데이터 복제 금지
· 후보 폐기 또는 기간 만료 시 **자동 삭제**
· 지식 허브·온톨로지·경영 집계·백업 대상에서 **제외**
· Preview 증명은 운영 Runtime API 에서 **쓸 수 없다**(§17)
· ACTIVE 승격 시 Preview 데이터를 운영 DB 로 **복사하지 않는다**

★ Preview 데이터는 **검증용**이다. 운영 초기 데이터는 별도의 승인된 적재 과정으로 만든다 —
「테스트로 넣은 것이 그대로 실적이 되는」 경로를 만들지 않는다.

### 14-2. 계약에 **마이그레이션 선언**을 포함한다 (v1 은 범위를 좁힌다)

⚠️ 모든 마이그레이션을 v1 에서 지원하려 하면 범위가 터진다. **자동 허용을 좁게 열고 나머지는
막는다** — 막힌 것은 사람이 판단하면 되지만, 잘못 자동화한 변환은 되돌릴 수 없다.

| v1 자동 허용 | 재승인 |
|---|---|
| 선택 필드 추가 | 필요 |
| 표시명·설명 변경 | 불필요(지문에 안 들어간다) |
| 허용 작업 축소·확대 | **필수** |
| 분류·용어·온톨로지 매핑 보강 | 조건부(등급이 낮아지면 필수) |

**자동 적용하지 않는다 → `MIGRATION_REQUIRED` 로 분류하고 ACTIVE 승격을 차단한다**

· 필드 기술명 변경 · 타입 변경 · **필수 필드 추가** · 필드 삭제 · 데이터셋 삭제
· 단위 변경 · 그 밖에 **기존 값을 변환해야 하는** 모든 변경

★ 「필수 필드 추가」가 자동 허용에 없는 이유: 기존 레코드에는 그 값이 **없다.** 자동으로
넣으면 그 값은 **지어낸 값**이고, 그것이 나중에 집계에 들어간다.

### 14-3. Host Service 개방 순서

우리는 업무 자동화 도구가 아니라 **경영 시스템**이다. 그래서 「읽어서 계산하고 결정한 뒤,
마지막에 쓴다」 순서로 연다.

1. **Legacy/MCP Read Gateway** — ERP·MES·WMS·LPL·외부지표 **읽기 전용**.
   계약·Crosswalk·조직 범위·계보 적용.
2. **Host Calculation Service** — G4 결정론적 계산 그래프(시뮬레이션·손익·현금·재고).
   ⚠️ LLM 은 **설명만** 한다 — 수치는 승인된 계산기가 낸다.
3. **Host Decision Action** — 회의 요청·검토서 생성·실행과제 등록. 승인·결정 원장 연결.
4. **External Write/Command Gateway** — ERP 발주·메일 발송·외부 상태 변경.
   **가장 마지막.** 사용자 승인·멱등성·보상 처리·감사 필수.

**사용자에게 보이는 문구 — 날짜를 약속하지 않는다**

    Legacy/MCP 조회       — 우선 개발
    경영 계산             — G4 연계 예정
    회의·결정 액션        — 계산 결과 연계 후
    외부 시스템 쓰기      — 안전성 관문 통과 후

⚠️ 날짜를 적으면 그 날짜가 지날 때 신뢰를 잃고, 사용자는 우회로를 찾는다.

---

## 15. I-4 적용 대상 — **모든 App-in-App 릴리스**

rev.2 는 「데이터 CRUD 를 포함한다고 판정된 태스크」만 계약을 요구했다. **그것은 순환
논리다** — 데이터 사용을 놓친 태스크가 곧 계약을 우회하는 태스크가 된다. 그리고 놓치는 쪽은
언제나 「간단해 보이는」 앱이다.

★ **사용자가 실행할 수 있는 App-in-App SW 릴리스를 만드는 모든 태스크**가 대상이다.
데이터가 없는 앱도 **「데이터셋 0개인 계약」**을 갖는다 — 0개라는 선언 자체가 통제다
(나중에 하나가 생기면 지문이 바뀌고 게이트가 열린다).

**WBS 에 `artifact_kind` 를 닫힌 목록으로 추가한다**

| 값 | 계약 |
|---|---|
| `APP` | **필수** |
| `SIMULATOR` | **필수** |
| `REPORT` | 불필요 |
| `DOCUMENT` | 불필요 |
| `LIBRARY` | 불필요 |

⚠️ **판독할 수 없으면 계약 대상으로 처리한다.** 「모르면 면제」는 곧 우회로다 —
이 저장소가 fail-closed 를 쓰는 모든 자리와 같은 규칙이다.

---

## 16. 계약 지문을 **증명에 봉인**한다

rev.2 는 「`allowed_actions` 가 줄면 기존 증명이 즉시 막힌다」고 적었다. **지금 구조로는
그렇지 않다.** 증명은 **매니페스트 지문만** 봉인하므로, Dataset Contract 만 바뀌고
매니페스트의 전역 행동 합집합이 그대로면 **기존 증명이 살아남는다.**

증명에 세 필드를 더한다:

```
contract_id · contract_revision · contract_fingerprint
```

· **발급 시 봉인**하고 · **요청마다** 현재 릴리스의 계약 지문과 대조한다
· 불일치는 **매니페스트 변경과 동일하게** 다룬다 — `410`, 재발급 금지, **프레임 폐기**
  (「낡은 앱이 새 증명으로 살아남지 않는다」와 같은 규칙)

★ 두 지문을 **따로** 두는 이유: 매니페스트는 「이 앱이 무엇을 할 수 있다고 선언했나」이고
계약은 「어느 데이터셋에 무엇을 할 수 있나」다. 하나로 합치면 둘 중 하나가 바뀔 때 다른
하나까지 무효가 되어, 필요 없는 재승인이 늘고 사람이 게이트를 습관으로 통과시킨다.

---

## 17. Preview 증명과 운영 증명을 **완전히 분리**한다

토큰에 `purpose="preview"` 를 넣는 것만으로는 부족하다 — 그것은 **표시**이지 경계가 아니다.

| | Preview | 운영 |
|---|---|---|
| 발급 API | `POST /runtime/preview/proof` | `POST /runtime/proof` |
| 대상 릴리스 | `RELEASE_CANDIDATE` **만** | `ACTIVE` **만** |
| 접근 DB | `app_preview.db` **만** | `app_data.db` **만** |
| 데이터 성격 | `SYNTHETIC_TEST` | 업무 데이터 |

· Candidate 는 운영 `app_data.db` 에 **닿을 수 없다**
· ACTIVE 증명은 `candidate_id` 를 **받지 못한다**
· ⚠️ **두 토큰의 audience 교차 사용 회귀**를 반드시 둔다 — 「preview 토큰으로 운영 API」와
  「운영 토큰으로 preview API」 **양방향** 모두.

★ 발급 API 를 나누는 이유: 한 API 에 분기를 두면 그 분기가 언젠가 「둘 다 되게」 완화된다.
경로가 다르면 완화하려면 **경로를 합쳐야** 하고, 그것은 리뷰에서 보인다.

---

## 18. 데이터셋 식별자 — 릴리스와 데이터셋을 분리한다

**지금 무엇이 문제인가 (실측)**

```sql
CREATE TABLE app_datasets ( dataset_id TEXT PRIMARY KEY,
                            release_id TEXT NOT NULL, name TEXT NOT NULL, ... )
```

데이터셋이 **릴리스에 직접 묶여** 있다. `find_dataset(release_id, name)` 이 릴리스로 범위를
잡으므로 **새 릴리스가 나오면 그 이름의 데이터셋을 찾지 못하고 새로 만든다** — 즉
**기존 레코드가 승계되지 않는다.** 앱을 한 번 개정하는 순간 현업 데이터가 안 보인다.

**바꿀 구조**

```
app_datasets                 app_id 에 속하는 **안정적인 논리 데이터셋**
app_dataset_versions         계약 revision 별 schema
app_release_dataset_bindings release_id · dataset_id · schema_version · allowed_actions
app_records                  **안정적인 dataset_id** 에 계속 저장
```

★ 요점은 `app_records.dataset_id` 가 **릴리스를 넘어 살아남는** 것이다. 릴리스는 「어느 판을
쓰는가」만 가리킨다(`bindings`).

**계약에 불변 식별자를 둔다**

```json
{ "dataset_key": "ds_material_arrivals",
  "name": "material_arrivals",
  "fields": [ { "field_id": "fld_arrival_date", "name": "arrival_date" } ] }
```

⚠️ v1 에서는 `dataset_key` · `field_id` · **기술 필드명**을 **ACTIVE 이후 변경 불가**로 둔다.
이름을 바꿀 수 있게 하면 그 순간 「이름이 같은 다른 것」과 「이름이 다른 같은 것」을 구분할
방법이 사라진다.

**마이그레이션 선언**

```json
{ "migration": {
    "from_revision": 1,
    "strategy": "ADDITIVE",
    "operations": [
      { "op": "ADD_OPTIONAL_FIELD",
        "dataset_key": "ds_material_arrivals",
        "field_id": "fld_customs_status" } ] } }
```

`strategy` 는 `ADDITIVE` | `METADATA_ONLY` | `ACTIONS_ONLY` | `MIGRATION_REQUIRED`.
앞의 셋만 v1 이 자동 적용하고, 마지막은 **ACTIVE 승격을 막는다**(§14-2).

---

## 19. Compiler 가 강제하는 조건부 규칙

JSON Schema 만으로는 부족하다 — `manifest` 가 단순 객체라 **유효하지 않은 매니페스트도
스키마를 통과한다.** Compiler 가 다음을 **추가로** 검사한다:

1. `app_manifest.assert_valid()` 실행
2. **매니페스트 ↔ 계약 일치** — 선언된 데이터셋·행동이 서로를 벗어나지 않는가
3. `semantic_role ∈ {quantity, amount}` 이면 **`unit` 필수**
   (⚠️ 단위 없는 수량은 나중에 합산될 때 조용히 틀린다)
4. `approval.status == "APPROVED"` 이면 **승인자·승인시각·원장 ID 필수**
5. **사용자 결정의 허용 집합을 상태별로 닫는다**

| 상태 | 허용되는 `user_decision` |
|---|---|
| `PROHIBITED` | **`REDUCE` 만** |
| `NOT_YET_SUPPORTED` | `REDUCE` · `WAIT` |
| `HOST_SERVICE_REQUIRED` | `REDUCE` · `WAIT` · `REQUEST_HOST_FEATURE` |

★★★ 마지막 줄이 중요하다. 자체 로그인 같은 `PROHIBITED` 항목에 `REQUEST_HOST_FEATURE` 를
허용하면 **금지 정책이 개발 요청으로 변질된다** — 「요청해 뒀으니 언젠가 열리겠지」가 되고,
그 사이 사용자는 우회로를 쓴다.

---

## 20. 구현 순서 (확정)

### 20-0. 1단계에 포함되는 것 — `ProjectState.schema_version` 5.1.0 → **5.2.0** (교차검토 92)

⚠️ 필드 추가는 기존 상태를 깨지 않으므로 major 변경이 아니다. 그러나 **저장·재개되는 상태
계약이 확장**되므로 버전을 그대로 두면 안 된다 — `5.1.0` 을 유지하면
**「구버전이라 계약 필드가 없는 상태」와 「신버전인데 데이터셋 0개인 정상 계약 상태」를
구분할 수 없다.** 그 둘은 전혀 다른 사실이다.

**적용 원칙**

· `5.1.0` → `5.2.0`: 하위호환 **지연 마이그레이션**(읽을 때 승격)
· **버전 없음** → 구버전으로 간주해 `5.2.0` 으로 승격
· 새 필드는 안전한 기본값으로 보완 · 저장이 일어날 때 `5.2.0` 으로 기록
· ⚠️ **기존 프로젝트 파일을 일괄 재작성하지 않는다**
· ⚠️⚠️ **미래 버전을 조용히 읽지 않는다** — 명확히 거부한다(모르는 계약을 추측해 읽으면
  그 추측이 곧 데이터 손상이다)

**실측(2026-08-15)**: `latest_state.json` 58개 — 버전 없음 **42** · `5.1.0` **16**.
두 경우 **모두** 회귀로 잠근다.

**혼동하면 안 되는 세 버전**

| 이름 | 값 | 무엇의 계약인가 |
|---|---|---|
| `ProjectState.schema_version` | `5.2.0` | 파이프라인 상태 |
| `App Runtime Contract.schema_version` | `1.0` | 계약 문서 형식 |
| `runtime_contract_version` | `1` | 앱↔Host 런타임 계약 세대 |

★ 버전 문자열은 **상수 하나**(`PROJECT_STATE_SCHEMA_VERSION`)로 두고 기본값도 그것을 쓴다 —
문자열을 반복하면 한 곳만 고치는 날이 온다.

⚠️ **프런트가 스키마 버전을 정하지 않게 한다.** 오래 열린 브라우저가 `5.1.0` 을 다시 보내
상태를 **다운그레이드**하는 경로를 없앤다 — 요청에서 그 필드를 빼고 서버가 부여한다.
`sprint/start` 에서도 서버 값이 클라이언트 값을 이긴다.

⚠️ `main.py:45` 의 `version="5.1.0"` 은 **FastAPI 앱 버전**이지 상태 스키마가 아니다.
  같은 문자열이라 함께 고치고 싶어지는데, 그러면 두 계약이 한 숫자에 묶인다 — 건드리지 않는다.

```
1. 계약 JSON Schema · Compiler · 상태 필드
2. 데이터셋 안정 식별자 · 릴리스 바인딩 · 데이터셋별 Runtime 판정
3. Proof 의 계약 지문 결속
4. Tech Lead / WBS(artifact_kind) / Contract Review Gate 연결
5. Typed SDK Adapter 와 정적 검사
6. Release Candidate · Preview DB · Preview Proof
7. ACTIVE 원자적 승격
8. 신규 생성 앱 종단 카나리
```

⚠️ 순서를 바꾸지 않는다. 2 없이 3 을 하면 지문이 가리킬 대상이 불안정하고, 6 없이 7 을 하면
승격할 후보가 없다. 각 단계는 **그 단계까지의 회귀**를 갖고 커밋한다.

---

## 21. 이 설계가 하지 않는 것

· 기존 앱 일괄 변환 · 파일 업로드 · 백그라운드 작업
· 계산/업무 액션의 Host 중개(§14-3 의 2~4단계 — 후속)
· `app_pdp_enforce` 관리자 카드(후속 UI — [6] 판정에서 차단 사항 아님으로 확인)
· `MIGRATION_REQUIRED` 변경의 자동 변환(사람이 판단한다)
