# G2 첫 수직 폐루프 — **인수인계**

작성: Claude Code (백엔드) · 2026-08-21
대상: 이 작업을 이어받는 사람(다른 계정·다른 세션)
**읽는 순서: §0 → §1 → §5(미결) → §6(다음 할 일).** 나머지는 필요할 때 찾아 읽는다.

---

## 0. 30초 요약

**목표** — 「이 도입 지연이 어디에 영향을 주는가」에 **근거를 되짚을 수 있게** 답하는
수직 경로 하나를 세운다.

**지금 어디까지 왔나** — 경로는 **닫혔다.** 정본 데이터·실제 Resolver·실제 색인·실제
승인으로 5노드 4간선이 이어지고, 근거 없는 칸이 0 이며 재실행 지문이 같다.
**숫자는 아직 없다** — 계산 4종이 전부 막혀 있고, 막혀 있다는 사실이 화면에 그렇게 보인다.

```
PO-000001-10 ─FULFILLED_BY_SHIPMENT→ SHP-000001
             ─AFFECTS→ STK-20260228-BP-GOLD-LOC-P1-RAW
             ─AFFECTS→ MPS-0000001
             ─AFFECTS→ SO-000001-10
```

**가장 중요한 규칙 하나** — 이 저장소에서 반복해 잡아 온 고장은 **「조용한 거짓말」**이다.
계산이 안 된 것이 「영향 없음」으로, 못 읽은 것이 「없음」으로, 승인 안 된 것이 「통과」로
보이는 것. 새 코드는 **모르면 막고, 왜 막혔는지 이름으로 말한다.**

---

## 1. 상태판

```
4   Dataset Resolver          ██████████  기능 완료 + 권한 타입 분리(4.1b-0)
5-0 계산 의미 계약            █████████░  2판 · **승인 대기**
5a  Capability Registry       ██████████  넷 등록 · 전부 실행 불가
A   경로 단위 계산 계약        ██████████  rev.2 (지문 둘로 분리)
B1  경로 → G5 근거 어댑터      █████████░  P0 4건 보정 · 발간 종단 회귀까지
B2  계산 결과 → G5            ░░░░░░░░░░  5b 이후
5b  계산 모델                 ░░░░░░░░░░  0/3 · **HOLD**(§5-0 승인 선행)
조직 격리 실증                ███░░░░░░░  FND-01 미적재 · 실제 권한 미검증
API·화면 종단                 ░░░░░░░░░░  조직 격리 뒤
8   계약 승인·설치            ░░░░░░░░░░  **HOLD** (`DESIGN_ONLY` 유지)
```

**출구 조건**(§7-0): 종이 2.5/6 → 실측 **4.5/6**. 남은 것은 조직 문맥(2)과 과거 판
선택 증명(3).

---

## 2. 코드 지도

| 파일 | 무엇 | 언제 읽나 |
|---|---|---|
| `core/ontology_resolve.py` | `ResolveContext`·`ObjectResolution` — **왜 불렸는지**를 아는 조회 계약 | Resolver 를 손댈 때 |
| `core/ontology_resolvers.py` | namespace 별 해석기. **`dataset` 만 배선됨** | 새 namespace 를 열 때 |
| `core/data_preparation/scope_index.py` | 인증판 ↔ **업무 객체** 색인. `as_of` 로 판 선택 | 판·시점 문제 |
| `core/data_preparation/snapshot_service.py` | 인증. **색인과 한 트랜잭션** | 인증 흐름 |
| `core/calc_capability.py` | `CALC.*` 넷의 계약. **전부 실행 불가** | 5b 착수 |
| `core/ontology_path_adapter.py` | 런타임 경로 → G5 근거 | B2·화면 연결 |
| `core/decision_package.py` | G5 안건. 경로 정체성 적재·**숫자 차단** | 안건 흐름 |
| `scripts/promote_ontology_vertical_v1.py` | 다섯 계약키 합성 인증 승격 | 시연 데이터 |

### 2.1 문서

| 문서 | 무엇 |
|---|---|
| `G2_ONTOLOGY_CONTRACT_APPROVAL_PACKAGE_DRAFT_2026-08-20.md` | 계약 승인 패키지 2판 (**설치 HOLD**) |
| `G2_S7_0_END_TO_END_SIMULATION_2026-08-20.md` | 종이 시뮬레이션 + 내가 틀린 기록 |
| `G2_S7_2_VERTICAL_DATA_PROMOTION_2026-08-20.md` | 승격 증거 + `P1-KIT-GEN-01` |
| `G2_S5_0_CALCULATION_SEMANTICS_CONTRACT_2026-08-21.md` | 지표 일곱·부호 방향 (**승인 대기**) |
| `G2_A_PATH_CALCULATION_CONTRACT_2026-08-21.md` | 경로 단위 계산 계약 rev.2 |
| `G2_S7_0_RERUN_2026-08-21.md` | 실측 재실행 결과 |

---

## 3. 반드시 지켜야 하는 규칙

**① 운영 DB 에 쓰지 않는다.** 통제 확인은 격리 DB·정식 시험으로만. 승격 스크립트는
`--data-dir data` 와 그 하위를 exit 2 로 거부한다.

**② 변이 검사는 폐기 가능한 worktree 에서만.** 주 작업트리 금지.

**③ `git add -A` 금지.** 명시 경로만. 다른 멤버의 미커밋 작업을 쓸어 담지 않는다.

**④ `origin` 에 푸시하지 않는다.** 사용자 지시가 있을 때만.

**⑤ 검증 3단(T1/T2/T3).**

```
T1  바꾼 파일           ~10초   편집할 때마다
T2  영향 모듈 묶음     46~230초  「됐습니다」 보고 전
T3  전체 + 불변식        ~11분   커밋 직전 **한 번**
```

⚠️ **T3 를 시작했으면 코드를 고치지 않는다.** 고칠 게 남았으면 T3 를 시작하지 않는다.
이 규칙을 두 번 어겨 회귀를 두 번 버렸다.

```bash
venv/Scripts/python.exe -m pytest -q -x --ff -p no:warnings
```

**⑥ 합성 인증 행위자는 `.invalid` 계정.** 가상회사 원장에 실존 인물을 적지 않는다.

**⑦ 「무엇이 있는가」가 아니라 「무엇이 도는가」를 본다.** 단위 초록 뒤 실측.

---

## 4. 이 세션에서 배운 것 (되풀이하지 말 것)

**① 도구를 만든 것과 도구를 쓰는 것은 다르다.** `_utc()` 를 만들고 정렬이 그걸 쓰는지
안 봤다 → 변이가 살아남았다. 시험은 **쓰는 쪽**을 봐야 한다.

**② 시험이 자기 자신과 비교하면 아무것도 못 잡는다.** `unit in UNITS` 는 `UNITS` 가
같은 상수에서 파생되므로 늘 참이었다. **글자 그대로** 못박아야 한다.

**③ 낱말만 보면 우연히 통과한다.** 「원장」이라는 낱말이 다른 사유에도 들어 있어서
가드 제거 변이가 살아남았다. 사유는 **구체적으로** 대조한다.

**④ 예외가 났다는 것만 보면 안 된다.** 어떤 **상태로 남았는지**까지 봐야 한다
(RECONCILED vs REVOKED).

**⑤ 한 곳만 보고 저장소 전체를 단정하지 않는다.** `pilot_demo_seed.py` 만 보고
「INV-01 이 없다」고 보고했다. 계약형 생성기에는 다 있었다.

**⑥ 대표값을 전체의 성질로 넓히지 않는다.** 인증판 하나의 `scope_node_id` 를 보고
「자료 전체가 한 범위」라고 했다. 실제로는 두 조직 노드였다.

**⑦ 패치 스크립트가 `assert` 로 멈추면 앞의 편집도 전부 잃는다.** 결과를 확인하지 않고
「배선 완료」로 넘어갔다.

**⑧ 주석은 통제가 아니다.** 「권한 있는 사람에게만」이라고 적어 놓고 검사가 없었다.

---

## 5. ⚠️ 미결 — 확인이 필요한 결정

### 미결 1 (P0급) — 숫자 차단의 범위를 좁혔다

Supervisor 지시는 「`complete=False` **또는** `calculation_blocked=True` 면 거부」였다.
그대로 넣었더니 **기존 통제 둘이 깨졌다**:

```
tests/test_baseline_and_calc.py::test_the_briefing_does_not_hide_missing_evidence
tests/test_baseline_and_calc.py::test_the_briefing_names_missing_steps_for_people
```

이 둘은 「근거가 빠진 단계를 브리핑에 **드러낸다**」를 지키는 시험이다. 미완결을
어디서나 막으면 그 통제가 **도달 불가능**해진다.

**그래서 이렇게 좁혔다**(`core/decision_package.py`):

```
calculation_blocked   → 언제나 막는다
complete=False        → 런타임 경로일 때만 막는다 (query_id 가 있는 경우)
```

⚠️ **두 규칙이 실제로 부딪히는 자리다.** 한쪽을 조용히 이기게 두지 않으려고 기록한다.
확인이 필요하다 — 좁힘을 유지할지, 기존 브리핑 통제를 다른 방식으로 살릴지.

### 미결 2 — 소유 부서(`owner_dept_id`)를 무엇으로 채우나

`scope_node_id`(ECM 조직 노드)와 `owner_dept_id`(`org_directory` 부서)는 **다른 것**인데
종전에는 같은 값을 넣고 있었다. 분리했고, 시연 데이터에 부서 칸이 없어 **지금은 비어
있다** → PDP 가 `RESOURCE_UNBOUND` 로 막는다(D-014).

**막히는 것이 맞다.** 다만 조직 격리를 실측하려면 부서 결속이 필요하다.

### 미결 3 — §5-0 의 의미 규칙 셋

1. `reserved_quantity` — 데모 0 가정(가정·지문에 포함), 운영은 별도 데이터 필요
2. `material_requirement` **66.4** vs BOM 계산값 **67.35** — BOM 이 정본, 저장값은 대사
   대상. 다르면 **readiness 실패**
3. `revenue_shift_days` 의 기준선 정의

### 미결 4 — `business_as_of` / `known_at` 분리

지금은 업무 유효시점과 시스템 인증시점을 **하나의 `as_of`** 로 다룬다. G4 백테스트
전에 갈라야 한다.

⚠️ 그래서 §7-0 의 「과거 `as_of` → `NO_VISIBLE_PATH`」는 **과거 판을 올바르게 선택했다는
증거가 아니다** — 과거를 거부한 것만 확인했다.

### 미결 5 — `P1-KIT-GEN-01`

`generate_sample_company_starter_kit.py` 의 `build(clean=True)` 가
① 소유하지 않은 산출물(xlsx 36개)까지 지우고 ② 검증 완료 상태를 되돌린다.
**수정 전까지 저장소의 정본 키트에 생성기를 다시 돌리지 않는다.**

---

## 6. 다음에 할 일 (순서대로)

```
1. 미결 1·2 확인받기                    ← 여기부터
2. 4.1b-1  FND-01 을 DEMO 인증판으로 승격
3. 4.1b-2  격리 Demo ECM 에 원자적 물질화
           · 운영 data/enterprise_context.db 는 구조적으로 거부
           · 같은 지문 멱등 · 같은 ID 다른 지문 충돌 거부
           · parent_id 는 OPERATING_PARENT 로만
           · entity_mode=VIRTUAL_EXPANSION 행 하나는 ECM 이 안 받는다 —
             몰래 VIRTUAL 로 바꾸지 말 것
4. 4.1b-3  실제 org_directory.resolve_scope() Principal 로 조직 격리 실측
5. §7-0 R2  상위 조직 ● / 단일 공장 교차 ✗ / 타 조직 ✗
6. API·화면 연결                        ← 조직 격리 게이트 통과 후
7. 5b 계산 모델                         ← §5-0 승인 후
```

⚠️ **6번을 먼저 하지 말 것.** 지금 상태로 화면에 붙이면 「전체 문맥에서만 도는 경로」가
되고, 그것은 조직 경계를 확인하지 않은 화면이다.

---

## 7. 재현 절차

```bash
# 1) 시연 데이터 승격 (격리 폴더)
venv/Scripts/python.exe scripts/promote_ontology_vertical_v1.py --data-dir <격리폴더>

# 2) 전체 회귀 + 불변식
venv/Scripts/python.exe scripts/check_operational_invariants.py capture --mode tests --force
venv/Scripts/python.exe -m pytest -q -x --ff -p no:warnings
venv/Scripts/python.exe scripts/check_operational_invariants.py compare --mode tests
```

⚠️ 불변식 검사는 **서버를 내린 뒤** 돌린다 — WAL 이 비어 있지 않으면 스스로 중단한다.

### 7.1 §7-0 종단 재실행

`docs/handoff/G2_S7_0_RERUN_2026-08-21.md` §1 의 순서를 따른다. 관계 유효 시작을
**인증 시각 이후**로 잡아야 한다(앞이면 끝점이 `UNBOUND` 로 막힌다 — 옳은 거부다).

---

## 8. Git 상태

```
브랜치      dev
origin 대비 22커밋 앞섬 · **푸시하지 않았다**
```

다른 멤버의 미커밋 작업이 남아 있다(문서 재편·데이터). **손대지 말 것.**

이 인수인계와 직전 보정(B1.2·4.1b-0)은 T3 통과 후 커밋된다 —
커밋되지 않았다면 `git status` 로 확인하고 §5 의 미결을 먼저 읽을 것.
