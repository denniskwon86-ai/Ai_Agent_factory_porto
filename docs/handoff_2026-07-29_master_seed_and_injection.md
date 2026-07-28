# 인계 — 기준정보 시드·조직 범위 바인딩·주입 경로 정상화 (2026-07-29, Claude Code)

> 담당: Claude Code(기능 설계·구현·검증) · 커밋 `34a3e8a37`
> 검증: pytest **709 통과** · 실제 FastAPI 경로 200 확인 · 실제 DB 격리 실측
> 선행 커밋: `4cfb4b45a`(P0 비용 관측) · `1fe965902`(R-001 1차)

---

## 0. 한 줄 요약

문서로만 존재했던 M1~M4 기준정보를 **실제 저장소에 적재하고 조직 범위에 묶었다**(감사
`ENTERPRISE-01` Action 1 종결). 그 과정에서 **기준정보 주입 경로의 결함 3건**을 실측으로
발견해 함께 고쳤다. 세 건 모두 테스트는 통과하고 있었고 실측하지 않으면 드러나지 않았다.

---

## 1. 한 것 — 기준정보 시드 (`core/master_data_seed.py` 신규)

`docs/master_data/*.json` 4개 문서를 `master_records` 로 적재하고 ECM 조직 범위에 바인딩한다.

| 문서 | 내용 | 바인딩 범위 | 상속 |
|---|---|---|---|
| `battery_material_m1.json` | 배터리소재 자재·설비·품질·BOM·재무 | `MNM_BATTERY` | 하위 공장 |
| `copper_smelting_m2.json` | 동제련 정광·부산물·제련마진 | `MNM_COPPER` | 하위 |
| `global_standard_m3.json` | ISO22400 KPI·ISA95/SAP·ERP 산식·CBAM | `LS_MNM`(법인) | 전 사업부 |
| `digital_twin_simulation_m4.json` | DES 확률분포·3D 레이아웃·동기화 충실도 | `LS_MNM` | 전 사업부 |

**설계 원칙 3가지** (사용자 지시 반영 — *"데이터 수치가 맞냐, 정확도가 얼마냐는 구현 단계에서
확인할 수 없다. 실사용 전 또는 사용 과정에서 보정되어야 한다"*):

1. **계수를 코드에 박지 않는다.** 전부 문서에서 읽는다. 변형하면 나중에 문서를 고쳐도 반영되지
   않고 무엇이 원본인지 알 수 없다. `source="master_document_seed"` 로 사용자 입력과 구분한다.
2. **값을 자동 보정하지 않는다.** 대신 `inspect_data_quality()` 가 **보정 목록**을 만든다.
   근거 없는 숫자를 시스템이 만들어내면 안 된다(명세서 §16).
3. **시드는 초기 공급이지 진실원본이 아니다.** 재실행이 현업 개정값을 덮지 않는다(멱등).

### 적재 실측 (44건)

```
material 11 · finance-param 10 · equipment 6 · sim-param 5 · bom 2 · quality-spec 2
logistics-param 2 · work-center 2 · emission-factor 2 · kpi 1 · sensor-spec 1
바인딩 44건 (LS_MNM 17 / MNM_COPPER 14 / MNM_BATTERY 13)
```

### 격리 실측

| 조회 조직 | 결과 |
|---|---|
| 배터리소재 / 제1공장 | 배터리 자재·설비 + 전사표준 (동제련 0건) |
| 동제련 | 정광·금 부산물 + 전사표준 (배터리 0건) |
| 전사공통(LS MnM) | M3/M4 표준만 |
| **LS전선(다른 법인)** | **0건** |

### 품질 점검 결과 — 5건(high 4)

| 종류 | 대상 | 내용 |
|---|---|---|
| `cost_exceeds_price` | `FG-NiSO4-001` | 재료비 $93,000 vs 판가 $22,000 — 구조적 적자. `RM-H2SO4-001`($75,000)이 지배 |
| `cpk_unreachable` | M1 Co / M1 Fe / M2 Pb | 공차·표준편차·목표 Cpk 가 서로 모순(0.83·0.67·1.46 vs 목표 1.33·1.33·1.67). 필요한 σ 를 함께 산출 |
| `uom_price_scale_suspect` | `RM-H2SO4-001` | 황산 단가가 UOM 기준 500배 과대 의심 |

> ⚠️ **오탐 방지**: 금(`BP-GOLD-001`) 온스당 $2,300 은 정상이다. 문서 자체의 LBMA 시세
> (`lbma_gold_price_usd_oss: 2350`)와 **교차검증**해 배제했다. 외부 시장가를 끌어와 판정하면
> 근거 없는 숫자가 되므로, 판정 기준은 **문서 안의 값끼리의 비교뿐**이다.

### API 5개 (`api/routes/master_control.py`)

```
POST /api/v1/master/documents/seed          문서 → 저장소 적재 + 바인딩 (force 옵션)
GET  /api/v1/master/documents/quality       보정 목록 조회
POST /api/v1/master/scope-bindings          원본 1 : 적용범위 N 바인딩
GET  /api/v1/master/scope-bindings          바인딩 목록
GET  /api/v1/master/scope-bindings/allowed  이 조직에 적용 가능한 코드 + 주입 상한 상태
POST /api/v1/master/grounding/preview       (확장) scope_node_id 지원 + stats 반환
```

---

## 2. 발견한 결함 3건 — **테스트는 통과하고 있었다**

### 결함 1 — 주입 상한 12건이 산식을 잘라내고 있었다 (D-010, 설계서 §F4 해소)

사용자 질문("조직별로 12건씩 나온 건 누가 왜 정한거야")에서 시작해 `git log -S` 로 추적했다.

- **출처**: 커밋 `169612ccc`(2026-07-22) — Claude Code 가 토큰 폭주를 막는 가드레일로 **임의로
  고른 값**. 실측·토큰 예산 계산 근거 없음. `docs/design_master_data_m1.md` §4 에 기재.
- **이미 결함으로 지목돼 있었다**: `design_org_permission_enterprise.md` §F4 가 *"전 부서
  기준정보에 절대 부족하고 `break`(continue 아님)라 긴 레코드 하나가 뒤를 전부 잘라낸다"* 며
  파라미터화 + 예산 자동 스케일을 처방했는데 **미구현**이었다(`max_items`·`skip_oversize` 0건).

**실측 피해** (시드 44건 적재 후):

| 조직 | 적용 가능 | 실제 주입 | 문자수 |
|---|---|---|---|
| 배터리소재 | 30건 | **12건** | 2,225자 |
| 동제련 | 31건 | **12건** | 2,196자 |
| 전사 | 17건 | **12건** | 2,538자 |

- 잘린 18건에 `M3-ERP-COST-MANAGEMENT`(표준원가 산식)·`M3-ERP-PRODUCTION-PLANNING-MPS`·
  `M3-ROUTING`·`M3-EMIS-01`·`M4-DES-*`(시뮬 확률분포)가 **전부** 포함
  → **"LLM 이 산식을 지어내지 못하게 확정 주입한다"는 M1 의 존재 이유가 무력화**되고 있었다.
- 3,000자 예산은 **한 번도 도달하지 않았다**(2,196~2,538자). 두 상한이 서로 맞지 않아
  문자 예산의 약 25%를 버렸다.
- tie-break 가 `master_code` 알파벳순이라 `RM-MHP-001`·`RM-H2SO4-001`·`WIP-*` 는 **철자 때문에**
  항상 탈락했다 → **무엇이 버려지는지가 중요도가 아니라 이름으로 결정**됐다.

**조치**(사용자 지시: *"실제 적용가능한 문서가 있는데 왜 임의로 잘라서 적용해? 넣을 수 있는건
모두 다 전수 다 적용해"*):

1. **기본 상한 없음(전수 주입)** — `_INJECT_MAX_ITEMS = _INJECT_MAX_CHARS = None`.
   전량은 배터리소재 ≈6,000자 / 전 문서 44건 ≈8,700자로 컨텍스트 부담이 없다.
2. `select_for_injection(..., max_items=-1, max_chars=-1, with_stats=False)` —
   `-1`=모듈 기본, `None`=무조건 전수, 양수=명시 상한. 환경변수
   `MASTER_INJECT_MAX_ITEMS`/`MASTER_INJECT_MAX_CHARS` 로 운영 비상 상한.
3. **`break` → `continue`** — 긴 레코드 하나가 뒤를 전부 잘라내지 않는다.
4. **`is_core` 를 관문에서 정렬 신호로 강등** — 종전에는 관문이어서 비핵심 레코드가 도메인이
   맞아도 영원히 주입되지 않았다. 우선순위 3계층: 별칭 히트 → 전사 표준·산식 → 도메인 핵심.
5. **절단 가시화** — 상한이 실제로 걸리면 주입 블록에
   `[주의] … N건 중 M건만 표시 … 추정하지 말 것` 을 적고 `/scope-bindings/allowed` 가
   `injection_capped` 를 반환. **조용히 잘리는 것이 가장 위험하다.**

**수정 후 실측**: 적용 가능 30건 → 주입 30건, `dropped: 0`.

### 결함 2 — 별칭 히트 경로가 죽어 있었다 (D-011)

`_alias_hit` 은 단어경계(`\b`)로 **문자열 전체**를 찾는데, 시드가 문서 정식명
`"Mixed Hydroxide Precipitate (MHP)"` 를 그대로 별칭에 넣었다. 실제 프롬프트에 이 괄호 표기가
나올 일이 없으므로 **시드 44건 전부에서 별칭 매칭이 영원히 실패**했다. 그래서 선정이
`is_core` + 알파벳순으로만 이뤄져 결함 1의 편향이 그대로 노출됐다.

→ `derive_aliases()` 가 괄호 앞 본문·괄호 안 토큰·문서상 식별자로 분해한다.
`"Sulfuric Acid (H2SO4, 98%)"` → `Sulfuric Acid` · `H2SO4` (`98%` 는 오탐 유발로 탈락).
**새 문자열은 창작하지 않고 문서에 이미 적힌 부분만 쓴다.**

### 결함 3 — 재시드가 격리를 조용히 무너뜨렸다

R-001 의 점진 도입 규칙은 **"바인딩 없는 코드는 전사 공통으로 통과"** 다(하위호환).
그런데 시드가 기존 레코드를 건너뛸 때 **바인딩 확인까지 건너뛰어**, ECM 조직 없이 먼저 적재된
레코드가 미바인딩으로 남고 → 통과 규칙을 타고 **모든 조직에 노출**됐다.

실제 DB 에서 **바인딩 26건 < 레코드 45건**으로 재현. 쓰기만 건너뛰고 바인딩은 항상 확인하도록
수정 → **44/44**, LS전선 노출 0건.

> ★ 이것이 `TEAM_BOARD` 의 `MDM-SCOPE-01` 검토 요청 ①("점진 도입 규칙이 유출 창구가 되지
> 않는지")에 대한 답이다: **됐다.** 규칙 자체는 유지하되 **미바인딩 레코드 수를 상시 관측**해야
> 한다. 관측 지표 추가는 미구현(§4 잔여 항목).

### 세 결함의 공통점

전부 **생산자→소비자 배선 누락** 유형이다(이 프로젝트에서 반복되는 결함 계열, `TEAM_PROTOCOL`
§8-2). 만들기는 했는데 **소비자가 쓸 수 있는 형태인지 확인하지 않았다.**
그리고 세 건 다 **단위 테스트로는 드러나지 않았다** — 실제 데이터를 넣고 실제 주입 결과를
눈으로 봐야 나왔다. 교훈: **기능 완성의 판정 기준에 "실제 데이터로 최종 산출물 확인"을 포함해야
한다.**

---

## 3. 잠금 테스트 (누가 되돌리면 깨진다)

`tests/test_master_document_seed.py` 30건. 특히:

| 테스트 | 무엇을 막는가 |
|---|---|
| `test_all_applicable_records_are_injected` | 적용 가능 전량 주입, `dropped == 0` |
| `test_formulas_survive_injection` | 산식(ERP·MPS·라우팅·KPI)이 잘리지 않음 |
| `test_default_has_no_cap` | 상한 부활 시 근거 문서화를 강제 |
| `test_explicit_cap_drops_do_not_kill_the_rest` | `break` 회귀 방지 |
| `test_truncation_is_visible_in_the_block` | 조용한 절단 방지 |
| `test_aliases_are_matchable` | 별칭 히트 경로 사망 재발 방지 |
| `test_reseed_binds_preexisting_records` | 재시드 격리 붕괴 재발 방지 |
| `test_cross_division_isolation` / `test_other_legal_entity_gets_nothing` | 부서·법인 유출 |
| `test_values_are_stored_verbatim` | 값 변형 금지 |
| `test_seed_does_not_overwrite_user_revision` | 현업 개정 보호 |
| `test_quality_inspection_does_not_mutate_documents` | 자동 보정 금지 |
| `test_precious_metal_is_not_false_flagged` | 품질 점검 오탐 |

`tests/test_master_data.py::test_alias_detection_word_boundary` 는 `is_core` 관문에 기대어
오탐 부재를 측정하고 있었으므로 도메인 불일치 방식으로 측정 방법을 바꿨다(성질 자체는 동일).

---

## 4. 남은 일

### 4-1. 다음 착수 전 정리 (작지만 프로토콜상 선행)

| 항목 | 내용 |
|---|---|
| 교차검토 부채 3건 | `ECM-E1-REVIEW` · `ECM-E2-01` · `MDM-SCOPE-01`(C등급). §3-1 상 큰 통합 전 해소 필요. D-010/D-011 도 함께 검토 대상 |
| 시드 기준 정리 | 외부 세션의 `scripts/generate_realistic_mfg_data.py` + `data/ls_mnm_realistic_enterprise_seed.json` + `docs/master_data/REALISTIC_DATA_GENERATION_SPEC.md` 가 `core/master_data_seed.py` 와 **영역이 겹친다**. 어느 쪽을 기준으로 삼을지 결정 필요 |
| 문서 번호 오류 | `LLM_MASTER_IMPLEMENTATION_SPEC_2026-07-28.md` §13 하위번호가 `12.1~12.3`, §17 이 `16.1~16.3` |

### 4-2. M1 완결까지 (실질 9개 작업)

| # | 작업 | 근거 |
|---|---|---|
| 1 | **R-001 잔여** — `master_version` 고정, `effective_from/to` 기간 평가 | 지금은 항상 현행 버전이 주입돼 "그때 그 값으로 재현"이 안 된다 |
| 2 | **미바인딩 레코드 관측** — 결함 3의 근본 대응 | 위 §2 결함 3 |
| 3 | **ECM E2 잔여** — 카탈로그/크로스워크/MCP 범위 키, `scope_assignments` | 설계서 §11 E2 |
| 4 | 데이터 카탈로그 — 자산·필드·소유자·민감도·갱신주기 | 명세서 §14 M1 |
| 5 | 용어사전 — 동의어·계산 정의·MDM 연결 | 명세서 §14 M1 |
| 6 | 품질/계보 — 프로파일링, 원천→앱→보고서 영향 관계 | 명세서 §14 M1 |
| 7 | 데이터 계약 — 스키마·품질·접근·버전 | 명세서 §14 M1 |
| 8 | 외부 인텔리전스 기반 — 원천 등록부, 외부지표 6종 | 명세서 §12·§15-7. **합성 불가 4건**(금리·산업수요지수·임금상승률·현금흐름)의 유일한 해결 경로 |
| 9 | 프론트 — 전역 컨텍스트 스위처, 바인딩 관리 화면, 품질 보정 목록 | 기능 확인 수준(디자인 개편 전) |

부가: **§10.3 `quality_outcomes` 텔레메트리**(게이트별 pass/fail·재시도·근본원인 분류·인간 수용)
— P0 잔여분이며 §8.3 실패 원인 분류와 함께 처리.

### 4-3. 전체 진척 (명세서 §14 기준)

| 단계 | 작업묶음 | 상태 |
|---|---|---|
| P0 생성공장 안정화 | 5 | ✅ 완료 |
| M0 상담·Blueprint | 4 | ✅ 완료(a~e) |
| **M1 데이터기반·거버넌스** | 6 | MDM 확장 ✅ / **5 남음** |
| M2 권한·안전연계 | 4 | 부분(IAM·RBAC 대부분) |
| M3 증빙형 부서앱 | 4 | 미착수 |
| M4 경영계획 디지털트윈 | 6 | 미착수 |
| M5 전사 자비스 | 1 | 미착수 |

**약 60% 잔여.** M4 디지털트윈(계산엔진·시나리오·Backtest)은 단독으로 M1 전체와 맞먹는다.

> ⚠️ **달력 기준 예측은 하지 않는다.** 이번 세션만 봐도 계획에 없던 결함 수정이 계획 작업만큼의
> 시간을 썼고, 이것이 줄어들 근거가 아직 없다. 신뢰할 수 있는 지표는 실적뿐이다 —
> **이번 세션: 작업단위 9개, 테스트 360 → 709건.**

### 4-4. 데이터 합성 가능성 (참고 — 이번 세션 조사 결과)

플레이북 요구 21건 중 **14건 합성 가능 · 3건 부분 · 4건 불가**.
불가 4건(금리·산업수요지수·임금상승률·현금흐름)은 문서에 원천이 없어 §4-2의 8번(외부 인텔리전스
원천 등록부)이 유일한 경로다. 값을 지어내면 안 된다(명세서 §16).

---

## 5. 관련 문서·커밋

- 결정 기록: `.agents/DECISIONS.md` **D-010**(주입 상한 폐기) · **D-011**(별칭 파생)
- 설계 갱신: `docs/design_master_data_m1.md` §4(전수 주입으로 개정) ·
  `docs/design_org_permission_enterprise.md` §F4(해소 기록 + 실측 수치)
- 현황판: `.agents/TEAM_BOARD.md` `MDM-SCOPE-01` 에 검토 요청 ① 자체 답 기재
- 커밋: `34a3e8a37`
