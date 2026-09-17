# 키트 선반 — 상세 기획설계

- 기준일: 2026-09-17
- 무엇: [`KIT_DIFFUSION_IN_PLATFORM`](KIT_DIFFUSION_IN_PLATFORM_2026-09-17.md) 8.6 의
  「지금 할 셋」을 구현 수준으로 내린다
- ⚠️ **아직 구현하지 않았다.** 이 문서는 명세다
- 이 문서의 「실측」은 전부 코드에서 직접 확인한 것이다

---

## 0. 범위

| | 한다 | 안 한다 |
|---|---|---|
| 1 | 사업 정의에 **키트 정체성** | 플랫폼 안 생성기 |
| 2 | 제련·전지소재를 **각각 봉인**해 선반에 | 배급 시스템 |
| 3 | 키트 경로를 **설정으로** | `--profile-only` (D5) |
| 4 | 선반 **카탈로그** | 등록 경로 잇기(다음 단계) |

---

## 1. 설계 결정 — 여덟

### D1. `kit_id` 는 **사업 정의에 명시한다** (유도하지 않는다)

    smelting_nonferrous  →  KIT-MFG-SMELTING-NONFERROUS
    battery_materials    →  KIT-MFG-BATTERY-MATERIALS

⚠️ 유도하려면 A 축(업태)이 필요한데 `sector` 는 **B 축만 담는다**
  (`"B:금속>비철금속>제련·정련"`). A 축을 또 넣고 규칙을 세워도 **조합일 때는 규칙이
  없어 어차피 명시해야 한다.** 명시가 단순하고 정직하다.

### D2. 새 키트의 첫 판본은 **1.0.0 이 아니라 1.2.0**

`--version` 은 **생성 로직 판본**이고 `scripts/kit_defs/v{판본}.py` 가 그 로직을 담는다.
키트마다 판본을 따로 매기면 로직 판본과 어긋나 `kit_defs` 매핑이 깨진다.

| 안 | 뜻 | 판단 |
|---|---|---|
| 키트별 판본 (1.0.0 부터) | 키트마다 이력이 독립 | ✗ `kit_defs` 를 키트 × 판본 2 차원으로 바꿔야 한다 |
| **로직 판본을 따른다** | **「이 키트는 1.2.0 로직으로 만들어졌다」** | ✅ 구조가 그대로다. 첫 판본이 1.2.0 인 것이 오히려 정직하다 |

### D3. `industry_codes` 를 manifest 에서 **뺀다** — 자리에 `sector` 를 넣는다

    industry_codes: ["C24"]                  ← 제거
    sector: ["B:금속>비철금속>제련·정련"]      ← 추가

⚠️ 같은 황산니켈 제조라도 **켐코는 `C2820`, LS MnM 사업부는 `C24`** 다
  (`LSMNM_BATTERY_NEWBIZ_REVIEW` 1 장). **법인 구조가 정하는 값**이지 키트 속성이
  아니다. 분류와 잇는 열은 우리 좌표 `sector` 이고 `business_defs` 가 이미 갖고 있다.

★ **실측: 키트 쪽에서 `industry_codes` 를 읽는 코드가 없다.**
  `core/advisor_playbook.py` 의 같은 이름은 **플레이북의 업종 적용 범위**로 다른
  개념이다. 검증기도 `kit_id`·`version`·`data_class` 만 본다. **제거해도 깨지는 곳이 없다.**

⚠️ 기존 1.0.0~1.2.0 은 봉인돼 있다 — **그대로 둔다.** 새로 내는 것부터 다르다.

### D4. ★ manifest 에 `kit_name` 을 **새로 넣는다**

**실측: `company_name` 이 카탈로그의 키트 이름으로 쓰이고 있다.**

    core/data_preparation/kit_registry.py:126   "name": manifest.get("company_name") or kit_id
    core/demo_vertical_slice.py:431             name = profile.get("company_name") or KIT_ID

즉 목록에 **「AFS 데모소재그룹」**이 뜬다. 회사 이름이지 키트 이름이 아니다.

| | |
|---|---|
| `kit_name` (새로) | **「비철 제련·정련 업무키트」** — 사람이 고르는 이름 |
| `company_name` (유지) | 「AFS 메탈 주식회사」 — 샘플 회사. 사업이 하나면 그 법인, 여럿이면 그룹 |

읽는 쪽은 `kit_name or company_name or kit_id` 로 떨어뜨린다 — **기존 판본이 그대로 돈다.**

### D5. `--profile-only` 를 **만들지 않는다**

정의(432 KB)만 뽑고 싶지만 **검증 420 건이 `samples/` 를 본다.** 정의만 만들면 검증할
수 없고, 검증 없이 봉인하면 「검증 PASS 뒤에 얼린다」는 규칙을 스스로 깬다.

★ **만들 때는 전부 만들고, 배급할 때 고른다.** 선별은 배급의 일이지 생성의 일이 아니다.

### D6. 새 키트 둘을 **저장소에 넣는다** (지금은)

| | 지금 | 넣으면 |
|---|---|---|
| 작업트리 `starter_kits/` | 119 MB | **약 223 MB** |

⚠️ 임계(키트 5 개 · 설치 3 곳)에 닿으면 밖으로 옮긴다. **D7 을 함께 하므로 그때 설정
  한 줄이면 된다.** 지금 밖에 두면 git 이 지키지 못하고 시험이 보지 못한다.

### D7. 키트 경로를 **환경변수로** — 기본값은 지금 그대로

    AFS_KITS_DIR           기본: <PROJECT_ROOT>/docs/data-kits
    AFS_STARTER_KITS_DIR   기본: <PROJECT_ROOT>/starter_kits

관례는 `deploy/install.sh` 를 따른다 (`${AFS_*:-기본값}`).

### D8. 조합 키트 `KIT-MFG-NONFERROUS-PROCUREMENT` 를 **유지한다**

1.0.0~1.2.0 이 봉인돼 있고 `demo_vertical_slice` 가 1.0.0 을 쓴다. 건드리지 않는다.

---

## 2. 자료구조 — `BusinessDef` 확장

`scripts/business_defs/__init__.py`

```python
class BusinessDef:
    # ── 키트 정체성 (이 사업 하나로 키트를 낼 때)
    #: 키트 식별자. **유도하지 않고 명시한다** (D1)
    kit_id: str = ""
    #: 사람이 고르는 이름 — 카탈로그에 뜬다 (D4)
    kit_name: str = ""
    #: manifest 의 `primary_use_case`. **그 사업의 손익이 무엇으로 정해지는가**
    use_case: str = ""
```

두 사업에 더할 값:

| | `kit_id` | `kit_name` | `use_case` |
|---|---|---|---|
| 제련 | `KIT-MFG-SMELTING-NONFERROUS` | 비철 제련·정련 업무키트 | 정광 구매에서 제련수수료·회수율·부산물까지 |
| 전지소재 | `KIT-MFG-BATTERY-MATERIALS` | 전지소재(황산니켈) 업무키트 | 원료 확보에서 배터리급 품질·고객 인증까지 |

⚠️ 제련의 「제련수수료·회수율·부산물」은 지어낸 것이 아니라 초안 문서에서 확인한
  것이다 (`NONFERROUS_SMELTING_SPECIALIZATION_DRAFT`).

### 새 헬퍼

```python
def kit_identity(defs, kit_id="", kit_name="") -> tuple[str, str, str]:
    """(kit_id, kit_name, use_case). **사업이 여럿이면 명시해야 한다.**"""
```

| 경우 | 동작 |
|---|---|
| 사업 1 개 | 그 사업의 셋. `kit_id` 가 비었으면 **거부** — 오타로 이름 없는 키트가 나온다 |
| 여럿 + **기본 조합** | 기존 `KIT-MFG-NONFERROUS-PROCUREMENT` (하위호환 · D8) |
| 여럿 + 다른 조합 | **`--kit-id` 없으면 거부** — 자동으로 붙일 옳은 이름이 없다 |

---

## 3. 생성기 변경

`scripts/generate_sample_company_starter_kit.py`

| 곳 | 지금 | 바꾼 뒤 |
|---|---|---|
| L38 `KIT_ID` | 모듈 상수 | `use_businesses()` 가 정한다 |
| `use_businesses(codes)` | 사업만 | `use_businesses(codes, kit_id="", kit_name="")` |
| L1406~1410 manifest | `kit_id`·`company_name`·`industry_codes`·`primary_use_case` 하드코딩 | 사업에서 온다 |
| `--business` 옆 | — | `--kit-id` · `--kit-name` |

manifest 변경(신규 판본부터):

```python
"kit_id": KIT_ID,
"kit_name": KIT_NAME,                        # 새로 (D4)
"company_name": _company_name(),             # 사업 1 개면 법인, 여럿이면 그룹
"sector": [b.sector for b in BUSINESSES],    # 새로 (D3)
"primary_use_case": _use_case(),
# "industry_codes": [...]                    ← 제거 (D3)
```

⚠️ **`KIT_ROOT` 는 `KIT_ID` 가 정해진 뒤에 계산돼야 한다.** 지금은 모듈 최상단에서
  상수로 잡는다(L67). 호출 순서에 의존하게 되므로 **`build()` 안에서 사업 → 판본
  순으로 다시 잡는다.**

---

## 4. 경로 설정화

`core/data_preparation/kit_registry.py`

```python
def kits_dir() -> str:
    """Profile 디렉터리. **환경변수가 우선한다** — 키트를 코드 배포에서 떼어내기 위해.

    ⚠️ `/opt/afs/app` 은 `update.sh` 가 `git pull` 로 갈아 끼우고 `/opt/afs/data` 는
      남는다. 키트가 app 쪽에 있으면 **코드 릴리스에 묶인다.**
    """
    import os
    from core.paths import PROJECT_ROOT
    return os.environ.get("AFS_KITS_DIR") or os.path.join(PROJECT_ROOT, KITS_DIRNAME)


def starter_packages_dir() -> str:
    """Starter Kit 디렉터리. 같은 이유로 환경변수를 받는다."""
```

★ `discover(directory="")` 는 **이미 인자를 받는다.** 기본값만 바뀐다.

⚠️ `core/demo_vertical_slice.py:163` 도 `starter_kits` 를 직접 조립한다 — 같이 고친다.

---

## 5. 기존 판본에 미치는 영향

| | 영향 | 왜 |
|---|---|---|
| 1.0.0 · 1.1.0 · 1.2.0 파일 | **없다** | 봉인돼 있고 재생성하지 않는다 |
| 지문 대조 | **없다** | 파일이 안 바뀐다 |
| `profile_from_manifest()` | **없다** | `dataset_id`·`name`·`app_blueprints` 만 읽는다 |
| 카탈로그 이름 | **없다** | `kit_name or company_name` 으로 떨어진다 (D4) |
| `demo_vertical_slice` | **없다** | 1.0.0 을 그대로 쓴다 |
| 검증기 | **없다** | `industry_codes` 를 보지 않는다 |
| `--business` 없이 생성 | **없다** | 기본 조합이면 기존 `kit_id` |

★ **되돌리기**: 전부 새 코드 경로이고 기존 산출물을 건드리지 않는다. 문제가 생기면
  커밋만 되돌리면 된다 — 봉인된 판본은 그대로 남는다.

---

## 6. 검증과 시험

### 새 시험 — `tests/test_business_defs.py`

| | 무엇을 지키나 |
|---|---|
| `test_사업은_키트_정체성을_갖는다` | `kit_id`·`kit_name`·`use_case` 가 비지 않았다 |
| `test_키트_식별자가_겹치지_않는다` | 두 사업이 같은 `kit_id` 를 주장하지 않는다 |
| `test_조합은_키트_이름을_명시해야_한다` | 기본이 아닌 조합에 `--kit-id` 없이 만들면 **거부** |
| `test_사업_하나면_그_키트가_나온다` (slow) | `--business smelting_nonferrous` → manifest 의 `kit_id` 가 제련 것 |

### 새 시험 — `tests/test_kit_registry_paths.py`

| | |
|---|---|
| `test_환경변수가_키트_경로를_바꾼다` | `AFS_KITS_DIR` 설정 시 그곳을 본다 |
| `test_환경변수가_없으면_지금과_같다` | 기본값이 `PROJECT_ROOT/docs/data-kits` |

### 검증기

새 키트 둘에 `validate --version 1.2.0` 을 각각 돌려 **420 건 PASS** 를 확인한 뒤
봉인한다. 순서는 기존과 같다 (검증 → `freeze_starter_kit.py`).

---

## 7. 작업 순서

| | 무엇 | 되돌리기 |
|---|---|---|
| **1** | `BusinessDef` 에 셋 추가 + 두 사업에 값 | 커밋 되돌리기 |
| **2** | 생성기가 그 값을 쓰게 (3 장) | 〃 |
| **3** | 시험 4 건 (6 장) — **여기서 한 번 멈춘다** | 〃 |
| **4** | 제련 키트 생성 → 검증 420 → 봉인 | 디렉터리 삭제 |
| **5** | 전지소재 키트 생성 → 검증 420 → 봉인 | 〃 |
| **6** | 경로 설정화 (4 장) + 시험 2 건 | 커밋 되돌리기 |
| **7** | 선반 카탈로그 문서 | — |

⚠️ **3 에서 멈추는 이유**: 4·5 는 저장소에 100 MB 를 더한다. 그 전에 **정체성이 제대로
  붙는지** 시험으로 확인한다. `KIT_DIFFUSION` 7.7 에서 이름표 문제를 뒤늦게 발견한
  것을 되풀이하지 않는다.

---

## 8. 하지 않는 것

| | 왜 |
|---|---|
| 플랫폼 안 생성기 | 재현 보증이 깨진다 (`KIT_DIFFUSION` 7.2) |
| 별도 시스템에서 **요청 시 생성** | 같은 이유 (8.1 ①) |
| `POST /kits` | 키트는 우리가 주는 전문성이다 (5 장) |
| 배급 시스템 | 임계 전이다 — 키트 5 개 · 설치 3 곳 (8.4) |
| `--profile-only` | 검증이 `samples/` 를 본다 (D5) |
| 기존 판본 손질 | 봉인돼 있다. 새 판본으로 낸다 |

---

## 9. 결정이 필요한 것

| | 물음 | 기본안 |
|---|---|---|
| ① | `kit_name` 문구 — 「비철 제련·정련 업무키트」로 좋은가 | 그대로 |
| ② | `use_case` 문구 — 그 사업의 손익 동인을 한 줄로 | 2 장의 표 |
| ③ | 새 키트 둘을 **저장소에 넣을 것인가** (D6 · +100 MB) | 넣는다. 임계에서 옮긴다 |
| ④ | 전선 키트는 | **보류** — `ORDER:PROJECT` 결정이 먼저다 |

★ ③이 되돌리기 비용이 가장 큰 결정이다. 넣지 않기로 하면 4·5 를 건너뛰고 1~3·6·7 만
  한다 — **그래도 구조는 완성되고**, 키트는 필요할 때 만들어 밖에 둘 수 있다.
