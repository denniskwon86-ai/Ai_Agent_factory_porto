# M2 착수 관문 설계 — 명시적 범위 계약과 접근 감사

> 상태: **설계 확정본(구현 착수 전)** · 기준일 2026-07-29 · 작성 Claude Code
> 상위 근거: 2026-07-29 사용자(Supervisor) 판정 — 3대 부채 「조건부 승인 / 증적 확인 전 Close 금지」
> 선행 조건: A-1 재카나리로 QUALITY-TEL-01 Close · `bc3b8bbe9` 보류 유지
> 관문 테스트: `tests/test_m2_entry_gates.py` (현재 7 xfail = 닫힌 문 7개)

---

## 0. 이 문서가 결정하는 것

M2(권한·안전 연계) 착수 조건인 관문 두 개를 **구현 가능한 계약**으로 확정한다.

| 관문 | 통과 조건 |
|---|---|
| **A. 미바인딩 비노출** | 범위가 명시되지 않은 데이터는 **어느 조직에서도 보이지 않는다.** 전사 공용은 빈 값의 해석이 아니라 `scope_type=ENTERPRISE_SHARED` + 승인 이력이 있는 명시적 상태다. |
| **B. 404 은폐 + 감사로그** | 타 조직 자원의 거부는 존재하지 않음과 구분되지 않고(외부), 그 순간 서버 감사로그에 `ACCESS_DENIED_SCOPE_MISMATCH` 와 대상 식별자가 남는다(내부). |

⚠️ **이 문서는 M2 코드를 바꾸지 않는다.** 사용자 지시(「M2 DB·API·권한 코드 변경 금지」)에 따라
설계와 관문만 고정하고, 구현은 재카나리 통과 후 착수한다.

---

## 1. 지금 무엇이 문제인가 (실측)

### 1.1 "미바인딩 = 통과" 규칙은 정확히 두 곳에 있다

```
core/master_data.py :: select_for_injection._in_scope()
    if code not in _bound: return True          # 아직 바인딩되지 않은 기준정보 = 전사 공통

core/enterprise_context/scoping.py :: is_visible()
    if not owner: return True                   # 전사 공용(점진 도입)
```

**두 곳 다 막지 않으면 한쪽으로 샌다.** 앞의 것은 *프롬프트 주입 경로*, 뒤의 것은 *목록·조회
가시성*이다. 2026-07-29 사고는 앞의 경로에서 났다 — 재시드가 바인딩을 건너뛰자 26건이 미바인딩으로
남아 **LS전선 프롬프트에 MnM 기준정보가 들어갔다.**

### 1.2 감사로그 인프라가 없다

`core/enterprise_context/__init__.py` 에 `(예정) audit.py` 라고만 적혀 있다. 즉 거부를 404 로
바꾸는 순간, **아무 기록도 남지 않는 조용한 차단**이 된다. 은폐는 외부용이고 내부에는 남아야 한다.

### 1.3 MCP 가 클라이언트가 보낸 범위를 그대로 믿는다

```
POST /api/v1/mcp/resolve  { "scope_node_id": "BATTERY", ... }   ← 요청 본문의 값을 그대로 신뢰
```

즉 아무나 남의 조직 범위를 적어 보내면 그 범위로 조회된다. **클라이언트가 보낸 범위는 '요청'이지
'권한'이 아니다.** 서버가 인증 주체로부터 범위를 계산하고, 요청 범위는 그 안에서만 교차 검증해야 한다.

---

## 2. 범위 계약 (관문 A)

### 2.1 필수 필드 7종

기존 ECM-lite 3키(`tenant_id`·`enterprise_scope_id`·`entity_mode`)로는 부족하다.
"누가 책임지는가", "어떤 공유 상태인가", "누가 언제 승인했는가"에 답할 수 없기 때문이다.

| 필드 | 의미 | 비고 |
|---|---|---|
| `owner_organization_id` | **데이터 책임 조직** | `enterprise_scope_id` 와 분리한다 — 소유와 적용 범위는 다르다 |
| `scope_type` | 공유 상태(아래 §2.2) | **이 값이 가시성의 1차 판정 축** |
| `scope_assignments` | 접근 가능한 조직 목록 또는 계층 규칙 | 조직 공유(`ORG_SHARED`)에서만 의미를 가진다 |
| `classification` | `PUBLIC` / `INTERNAL` / `CONFIDENTIAL` | 등급이 낮은 사용자에게는 목록에서도 감춘다 |
| `effective_from` / `effective_to` | 기준·연계 유효기간 | 만료된 계약이 조용히 계속 쓰이는 것을 막는다 |
| `approval_status` / `approved_by` | 공용 전환 승인 이력 | `ENTERPRISE_SHARED` 는 이 두 값 없이 성립하지 않는다 |

### 2.2 `scope_type` 열거값 — **이것이 관문 A의 핵심**

| 값 | 가시성 | 승인 필요 |
|---|---|---|
| `ORG_PRIVATE` | 소유 조직 + 그 하위(운영 상속) | 불필요 |
| `ORG_SHARED` | 소유 조직 + `scope_assignments` 에 명시된 조직 | 소유 조직 승인 |
| `ENTERPRISE_SHARED` | 전 조직 | **필수**(`approval_status=APPROVED` + `approved_by`) |
| `SANDBOX` | 해당 가상 문맥 세션 안에서만 | capability token(§4.3) |
| `LEGACY_UNSCOPED` | **한시 예외** — 통과시키되 반드시 센다 | 만료일 지정 필수 |

> ★ **기본값은 `ORG_PRIVATE` 이고, 소유 조직이 비어 있으면 아무에게도 보이지 않는다.**
> 종전의 "빈 값 = 전사 공용"과 정반대다. 빈 값은 이제 **설정 누락**이지 공유 의사가 아니다.

### 2.3 레거시 이행 — 하루아침에 안 보이게 하지 않는다

기존 데이터를 즉시 비노출로 바꾸면 도입이 멈춘다. 그러나 **통과시키는 것과 통과한 줄 모르는 것은
다르다.**

1. 마이그레이션 시 기존 미바인딩 레코드를 `scope_type=LEGACY_UNSCOPED` 로 **명시적으로 표시**한다
   (빈 값으로 두면 신규 누락과 구분되지 않는다).
2. `LEGACY_UNSCOPED` 는 만료일(`effective_to`)을 갖는다. 만료 후에는 비노출이다.
3. 거버넌스 콘솔과 `coverage()` 가 **한시 예외 건수를 별도 칸으로** 보여준다
   (`legacy_grandfathered`) — 미지정과 같은 칸에 두면 "정리됐다"로 오독된다.
4. **신규 데이터에는 `LEGACY_UNSCOPED` 를 쓸 수 없다.** 생성 API 가 거부한다.

### 2.4 적용 대상

| 테이블 | 현재 | 필요 작업 |
|---|---|---|
| `master_records` + `master_scope_bindings` | 바인딩 1:N (R-001) | 바인딩에 `scope_type`·승인 이력 추가. 미바인딩 = 비노출 |
| `data_assets` · `business_terms` · `data_contracts` | ECM-lite 3키 (D-013) | 4필드 추가 |
| `external_systems` | ECM-lite 3키 (**D-016, 보류 중**) | 보류 해제 시 4필드로 보정 |
| `advisor_*`(상담·Blueprint) | ECM-lite 3키 | 동일 |

---

## 3. 접근 감사 (관문 B)

### 3.1 왜 별도 모듈인가

거부 판정은 여러 곳에서 난다(주입 경로·목록·개별 조회·MCP). **기록 형식이 곳마다 다르면
운영자는 침해 시도를 추적할 수 없다.** 판정 로직을 `scoping.py` 한 곳에 모은 것과 같은 이유로
기록도 한 곳에 모은다 → `core/enterprise_context/audit.py`.

### 3.2 이벤트 계약

```python
audit.record(
    event="ACCESS_DENIED_SCOPE_MISMATCH",   # 열거값(자유 문자열 금지)
    actor="hikwon@lsmnm.com",               # 인증 주체 — 익명이면 "" 가 아니라 "anonymous"
    actor_scopes=["MNM_BATTERY"],           # 서버가 계산한 주체의 범위(요청값 아님)
    resource_type="external_system",        # master_record | data_asset | external_system | mcp_resource
    resource_id="mes-smelting",             # ★ 실제 대상 식별자 — 이것이 없으면 추적이 불가능
    requested_scope="SMELTING",             # 클라이언트가 요청한 범위(신뢰하지 않되 기록은 한다)
    outcome="denied",
    reason="scope_mismatch",
)
```

**필수 원칙 4가지**

1. **은폐는 외부용이다.** 응답은 404 로 뭉개도 감사로그에는 실제 대상 식별자를 남긴다.
2. **요청값과 계산값을 둘 다 남긴다.** 무엇을 요구했고(요청) 무엇이 허용됐는지(계산)를 나란히
   두어야 "권한 상승 시도"가 보인다.
3. **감사 기록 실패가 요청을 죽이지 않는다.** 단, 기록 실패 자체를 카운트한다(조용한 유실 금지).
4. **감사로그는 append-only.** `llm_call_log` · `quality_outcomes` 와 같은 규약
   (`data/access_audit.jsonl`).

### 3.3 404 은폐의 적용 경계 — **여기가 가장 위험한 부분**

| 상황 | 응답 | 이유 |
|---|---|---|
| 타 조직의 개별 자원 조회 | **404** | 존재를 알려주면 안 된다 |
| 목록 조회 | **200 + 필터링된 목록** | 목록은 원래 "내 것만" 준다. 404 는 부적절 |
| 인증 정보 없음 | **401** | 사용자가 로그인해야 한다는 것을 알아야 한다 |
| 토큰 만료 | **401** | 갱신하면 된다는 것을 알아야 한다 |
| 요청 형식 오류 | **422 / 400** | 클라이언트 버그를 숨기면 아무도 못 고친다 |
| 쓰기 권한만 없음(읽기는 가능) | **403** | 자원의 존재를 이미 아는 상태라 은폐 의미가 없다 |

> ⚠️ **전부 404 로 만들면 운영 진단이 불가능해진다.** 은폐 대상은 "볼 수 없는 자원의 존재"
> 하나뿐이다. 회귀 잠금: `test_gate_b_auth_failures_are_not_disguised_as_404`.

---

## 4. 서버측 범위 계산 (관문 B-4)

### 4.1 신뢰 경계

```
[클라이언트]  scope_node_id="SMELTING"   ← 요청(신뢰하지 않음)
      │
[서버] Principal(인증 주체)
      → org_directory.resolve_scope(user_id)      # 부서 권한(기존 자산)
      → scoping.resolve_scope_ref(dept → node)    # D-005 이중 형태 해석(기존 자산)
      → visible = scoping.visible_scopes(node)    # 운영 상속(기존 자산)
      → 교차 검증: requested ∈ visible ?
           yes → requested 로 조회
           no  → 404 + ACCESS_DENIED_SCOPE_MISMATCH
```

**재사용 가능한 자산이 이미 다 있다.** 새로 만들 것은 "교차 검증" 한 줄과 감사 기록뿐이다.
요청 범위를 아예 안 받는 방법도 있으나, 상위 조직 사용자가 하위 조직 문맥으로 조회하는 정당한
사용(경영진 드릴다운)을 막으므로 **"요청은 받되 검증한다"** 가 옳다.

### 4.2 적용 지점

| 경로 | 현재 | 변경 |
|---|---|---|
| `POST /api/v1/mcp/resolve`·`resolve-batch`·`invalidate` | 요청 본문 신뢰 | `Depends(current_principal)` + 교차 검증 |
| `GET /api/v1/mcp/systems/{id}/health` | 쿼리 신뢰 | 동일 |
| `/api/v1/crosswalk/*` | 쿼리 신뢰 | 동일 |
| `ContextEngine` 주입 경로 | `state.enterprise_scope_id` | **변경 없음** — 파이프라인은 서버 내부이고 상태는 서버가 만든다 |

### 4.3 VIRTUAL Sandbox — "권한 승급"이 아니다

E3(가상 기업 Sandbox)에서 `entity_mode` 완전 일치 규칙이 걸림돌이 되지만, **실제 조직 권한을
올리는 방식은 금지**한다. 대신:

- 세션 전용 **capability token**: 짧은 만료(기본 30분) · **읽기 전용** · 가상 조직 범위로만 유효
- 토큰은 REAL 데이터에 대한 어떤 권한도 부여하지 않는다(가상 문맥 복제본에만 유효)
- 발급·사용·만료를 감사로그에 남긴다(`SANDBOX_TOKEN_ISSUED` / `_USED` / `_EXPIRED`)

---

## 5. 실행 계획

> **[2026-07-29 12:55 갱신 · Claude Code]** 「M2 코드 변경 금지」가 사용자 지시로 해제되어
> 착수 가능해졌다. 4차 카나리(Antigravity 주관)와 **병행 가능**하다 — 아래 1~3단계는 카나리
> 결과에 의존하지 않고, 4~5단계만 데이터·실측이 걸린다.

### 5.1 단계별 순서와 의존성

| # | 작업 | 여는 관문 | 선행 | 되돌림 | 규모 |
|---|---|---|---|---|---|
| 1 | `core/enterprise_context/audit.py` 신설 + 거부 지점 배선 | B-2 | 없음 | 쉬움(부가 기록) | 소 |
| 2 | MCP·크로스워크에 `current_principal` + 서버측 범위 교차 검증 | B-4 | 1 | 쉬움(인자 추가) | 중 |
| 3 | 거부 응답 409 → 404 (§3.3 경계표 준수) | B-1 | 1·2 | 쉬움 | 소 |
| 4 | `scope_type` 등 4필드 마이그레이션 + `LEGACY_UNSCOPED` 표시 | A-3·A-4 | 3 | **어려움 — 데이터 변경** | 대 |
| 5 | `is_visible`/`_in_scope` 기본값을 **비노출**로 전환 | A-1·A-2 | 4 | 중간(플래그 단계 전환) | 중 |
| 6 | `bc3b8bbe9`(보류분)를 새 계약으로 보정해 해제 | — | 4·5 | — | 소 |

**순서의 근거**: 감사로그(1)를 **먼저** 만든다. 거부를 404로 바꾼 뒤에 감사를 붙이면 그 사이
모든 차단이 기록 없이 지나간다. 마이그레이션(4)은 되돌리기 가장 어려우므로 검증 수단(1~3)이
전부 선 후에 한다.

### 5.2 각 단계의 완료 판정

| # | 완료 판정 |
|---|---|
| 1 | `test_gate_b_denial_is_written_to_the_audit_log` 가 xpass · 감사 레코드에 요청값과 서버 계산값이 **둘 다** 있음 |
| 2 | `test_gate_b_mcp_does_not_trust_client_supplied_scope` 가 xpass · 상위 조직 드릴다운은 계속 동작 |
| 3 | `test_gate_b_other_org_resource_returns_404` 가 xpass · **회귀 잠금 유지**(인증 401·형식 422·목록 200) |
| 4 | 기존 레코드가 `LEGACY_UNSCOPED` 로 **명시 표시** · 거버넌스 콘솔에 한시 예외 건수 별도 표시 |
| 5 | 관문 A 4건 xpass · `SCOPE_FAIL_CLOSED=false` 로 즉시 되돌릴 수 있음 |
| 6 | `tests/test_crosswalk_mcp_scoping.py` 18건 유지 + 새 계약 테스트 통과 |

### 5.3 위험과 대비

- **4번 전에 반드시 DB 백업.** 데이터 변경이 유일하게 되돌리기 어려운 단계다.
- **5번은 환경변수 플래그(`SCOPE_FAIL_CLOSED`)로 감싼다.** 한 번에 전환하면 무엇이 안 보이게
  됐는지 아무도 모른다. 켜기 전에 `coverage()` 로 "꺼면 몇 건이 사라지는지"를 먼저 센다.
- **관문을 통과시키려다 회귀 잠금 2건을 깨지 않는다** — 범위 미지정 호출의 전량 조회(ECM 미도입
  환경)와 인증 실패의 401. `tests/test_m2_entry_gates.py` 가 둘 다 지킨다.
- **4차 카나리와 동시 진행 시 8080 을 건드리지 않는다**(§3-1 단일 포트).

---

## 6. 열린 질문 (사용자 결정 필요)

1. **`LEGACY_UNSCOPED` 만료일을 언제로 둘 것인가.** 짧으면 현업이 막히고, 길면 예외가 상태가 된다.
2. **`classification` 등급별 정책** — `CONFIDENTIAL` 은 목록에서도 감출 것인가, 제목만 보일 것인가.
3. **경영진 드릴다운의 범위** — 상위 조직 사용자가 하위 조직 문맥으로 조회할 때 `CONFIDENTIAL`
   까지 볼 수 있는가.
4. **감사로그 보존 기간과 열람 권한** — 감사로그 자체가 민감정보다(누가 무엇을 시도했는지).
