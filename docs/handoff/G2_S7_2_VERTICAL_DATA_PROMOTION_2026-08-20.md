# §7 2단계 — 계약형 시연 데이터 **다섯 종** 합성 인증 승격 (완료 보고)

작성: Claude Code (백엔드) · 2026-08-20
**범위: 승격만. Dataset Resolver·범위 색인·온톨로지 관계 설치는 하지 않았다.**

---

## 0. 한눈에

```
□→■ 전체 샘플 회사 생성기는 기존 기능 유지      ■  35종 그대로, 축소하지 않음
□→■ 다섯 계약키만 온톨로지 MVP 대상으로 선택     ■  PRC-02·LOG-02·INV-01·MFG-01·SLS-01
□→■ 다섯 데이터셋의 행 단위 열쇠·범위 검증        ■  8종 검사 · 각각 빨강 재현
□→■ PRC-02 ↔ LOG-02 주문행 관계 검증            ■  120건 전부 정확히 1:1
□→■ 합성 데이터 인증판 5개 생성                  ■  DEMO_CERTIFIED
□→■ 실제 실적 승격 금지 표시                     ■  깃발이 아니라 **상태 기계**
□→■ 동일 seed 재생성 지문 일치                   ■  CSV·내용 지문 (§2.4)
□→✗ 전체 키트 빌드 멱등                          ✗  **미충족** — P1-KIT-GEN-01 (§3)
□→■ 기존 pilot 화면·시험 무회귀                  ■  파일 미변경 · 회귀 통과
□→■ 운영 데이터 불변                            ■  불변식 전후 동일
□→■ Dataset Resolver·관계 설치는 하지 않음        ■  손대지 않음
```

---

## 1. 새 상태를 만들지 않았다 — 제품에 이미 있었다

Supervisor 지시는 「`SYNTHETIC_CERTIFIED` 가 없으면 새 상태를 임의로 만들지 말고
기존 계약으로 표현하라」였다. 확인해 보니 **기존 계약이 이미 더 정확하다.**

```
RAW → PROFILED → STANDARDIZED → RECONCILED → DEMO_CERTIFIED | QUARANTINED | REVOKED
```

★ 인증 상태의 이름 자체가 `CERTIFIED` 가 아니라 **`DEMO_CERTIFIED`** 다. 실제 Data
Owner 없이 실적 인증을 주장하지 않으려고 그렇게 지어져 있었다.

### 1.1 ⚠️ 「실적 승격 금지」는 깃발이 아니다

`promotable=false` 같은 깃발은 **누군가 `True` 로 바꾸면 끝난다.** 여기서는 그럴
필요가 없었다:

| 사실 | 확인 |
|---|---|
| 평범한 `CERTIFIED` 라는 상태가 **존재하지 않는다** | `"CERTIFIED" not in SNAPSHOT_STATES` |
| `DEMO_CERTIFIED` 에서 갈 수 있는 곳은 `REVOKED` **뿐** | `SNAPSHOT_TRANSITIONS` |
| 뒤로도 못 간다(정정은 새 Snapshot) | `can_snapshot_transition` 4방향 전부 `False` |

두 시험이 이 사실 자체를 못박는다. 계보 파일에도 `promotable_to_real: false` 와 함께
**왜 그런지**(`promotion_guard`)를 문장으로 남겼다.

---

## 2. 실측 결과

### 2.1 원천 (quick 프로필)

| 계약키 | 행 | 열쇠 | 원천 sha256 |
|---|---:|---|---|
| `PRC-02` | 200 | `po_line_id` | `af3b3d5025c9709b…` |
| `LOG-02` | 120 | `shipment_id` | `38664e02ea6dff9e…` |
| `INV-01` | 540 | `snapshot_id` | `40d320f2ba323e7c…` |
| `MFG-01` | 500 | `plan_line_id` | `56d3ab0045ffba1c…` |
| `SLS-01` | 300 | `sales_line_id` | `a9b3b4b356bba847…` |

키트 지문 `6eb97470b102a9041322273e8aabc8c195c52689ce4b3c3c49f3f6a61cf16a21`

### 2.2 관계 무결성

```
● 기본키 중복 0 · 필수 열쇠 빈 값 0 · 범위 없는 행 0 · tenant 혼입 0
● LOG-02.po_line_id → PRC-02.po_line_id 가 주문**행** 단위로 정확히 1:1 (120/120)
● 주문일보다 이른 출항 0건
```

### 2.3 인증판

| 계약키 | Snapshot ID | 상태 | 행 | 성격 |
|---|---|---|---:|---|
| `PRC-02` | `ds_26066e4c4b424d` | `DEMO_CERTIFIED` | 200 | `DEMO/SYNTHETIC` |
| `LOG-02` | `ds_8b9590f1b1b94f` | `DEMO_CERTIFIED` | 120 | `DEMO/SYNTHETIC` |
| `INV-01` | `ds_c00c24ce995c42` | `DEMO_CERTIFIED` | 540 | `DEMO/SYNTHETIC` |
| `MFG-01` | `ds_6536fa0d567446` | `DEMO_CERTIFIED` | 500 | `DEMO/SYNTHETIC` |
| `SLS-01` | `ds_e33c2f1d639f45` | `DEMO_CERTIFIED` | 300 | `DEMO/SYNTHETIC` |

tenant `tenant-afs-demo-materials` · 범위 `plant-afs-smelting-01` · `entity_mode=VIRTUAL`
· 인증 행위자 `demo.data.owner@afs.invalid` · 생성기 seed `20260811`

⚠️⚠️ **가상회사 인증 원장에 실존 인물을 적지 않는다.** 실측용 단일 계정 규칙은 «사람이
쓰는 화면» 을 위한 것이고, 인증 원장은 **행위의 기록**이다 — 실존 이름이 남으면 나중에
그 사람이 「이 숫자를 인증했다」고 읽히게 된다. `.invalid` 는 예약 도메인이라 실재하지
않는다(RFC 2606). 시험이 이 사실을 못박는다.

⚠️ Snapshot ID 는 실행마다 달라진다(새 판은 새 기록이다). 같아야 하는 것은 **내용
지문**이고, 다섯 모두 원천 sha256 과 일치한다.

### 2.4 재실행 멱등 — **셋을 구분해야 한다**

```
35종 CSV 데이터    ● 동일 seed 에서 바이트 멱등
승격 내용 지문      ● 멱등
전체 키트 빌드      ✗ **비멱등**
                     · manifest 의 검증 상태를 되돌린다
                     · 다른 생성기의 Excel 산출물을 삭제한다
```

★ CSV 는 같은 seed 에서 **바이트 단위로 동일**하다 — 재생성 뒤 git 이 `samples/` 아래
변경을 0건으로 보고했다. 승격을 새 폴더에 다시 돌려도 내용 지문 다섯이 모두 같았다.

⚠️⚠️ **그러나 「전체 키트가 바이트 단위로 동일」은 틀린 말이다.** 첫 판에서 그렇게 적었는데,
같은 문서 §3 의 manifest 변경·Excel 삭제와 **양립하지 않는다.** 데이터가 멱등한 것과
빌드가 멱등한 것은 다른 말이고, 그 둘을 붙여 쓰면 「재생성해도 안전하다」로 읽힌다 —
안전하지 않다.

---

## 3. ⚠️⚠️ 재생성이 추적 파일을 건드렸다 — 원인과 복구

멱등성을 확인하려고 생성기를 돌렸더니 **되돌릴 것이 생겼다.**

```
M  starter_kits/…/manifest.json   status: VALIDATED_FOR_DEMO → GENERATED_UNDER_VALIDATION
                                  file_index 에서 232줄 소실
D  추적 파일 38개 삭제 — 그중 templates/excel/ 의 xlsx **36개 전부**
```

※ 숫자 근거: `git ls-files …/templates/excel/` = **36**(복구 뒤 디스크도 36).
관측된 삭제 총계는 **38**이었고, 나머지 2건은 복구 전에 목록을 남기지 않아 지금은
특정할 수 없다. ⚠️ 확인한 것과 확인하지 못한 것을 한 숫자로 뭉치지 않는다.

**원인**: `generate_sample_company_starter_kit.py` 의 `build(clean=True)` 가 기본값으로
`shutil.rmtree(KIT_ROOT)` 를 하고, 그 아래에는 **다른 스크립트가 만든 산출물**이 함께
있다(`generate_sample_company_excel_templates.py` 의 xlsx 36종). 생성기는 자기가 만들지
않은 것까지 지운 뒤 자기 것만 다시 만든다.

⚠️ `manifest.json` 의 `status` 는 더 중요하다 — 커밋된 값은 `VALIDATED_FOR_DEMO`
(사람이 검증을 마쳤다는 뜻)인데, 재생성이 `GENERATED_UNDER_VALIDATION` 으로 **되돌렸다.**
「검증했다」는 사실이 명령 한 번에 사라진다.

**복구**: `git checkout -- starter_kits` — 변경 0건, xlsx 36개 복귀, `status` 복원 확인.
CSV 는 애초에 한 바이트도 바뀌지 않았으므로 잃은 것은 없다.

★ **이 단계에서 생성기를 다시 돌릴 필요는 없다.** 산출물이 이미 저장소에 있고
결정론적이다. 승격 스크립트는 **읽기만** 한다.

### 3.1 잔여 결함 — `P1-KIT-GEN-01`

```
P1-KIT-GEN-01
· build(clean=True) 가 **소유하지 않은 산출물까지 삭제**한다
· **검증 완료 상태를 생성 중 상태로 되돌린다**(VALIDATED_FOR_DEMO → GENERATED_UNDER_VALIDATION)
· 수정 전까지 **저장소의 정본 키트에 생성기 재실행 금지**
```

2단계를 막지는 않는다 — 산출물이 이미 저장소에 있고 CSV 는 결정론적이므로 승격은
**읽기만** 하면 된다. 이번 단계 범위 밖이라 고치지 않았다.

---

## 4. 만든 것

| 파일 | 무엇 |
|---|---|
| `scripts/promote_ontology_vertical_v1.py` | 다섯 종 검증 + 승격. **운영 폴더로는 실행 거부** |
| `tests/test_ontology_vertical_promotion.py` | 20건 — 고장 8종 재현 · 차단 · 인증 · 상태 기계 · 합성 행위자 |

### 4.1 운영 DB 쓰기 금지

`--data-dir data` 또는 그 하위를 주면 **exit 2 로 거부**한다. 시험이 두 경로 모두를
확인한다. ⚠️ 하위 폴더까지 막는 이유는 `data/demo` 같은 예외가 곧 구멍이 되기 때문이다.

승격은 격리 폴더에서만 돌렸고, 운영 불변식은 **전후 동일**이다.

### 4.2 기존 파일럿과 병행

`pilot_demo_seed.py` 를 **읽지도 부르지도 않는다.** 데이터셋 이름도 바꾸지 않았다.
새 프로필 이름은 `ontology_vertical_v1` 이고, 기존 화면의 기본 프로필은 그대로다.
시험이 양방향으로 확인한다(승격 스크립트가 낡은 시드를 부르지 않는가 · 낡은 시드가
새 프로필을 참조하지 않는가).

---

## 5. ⚠️ 시험이 내 검사의 설계 문제를 잡았다

「주문행이 둘이면 잡는다」 시험을 처음엔 **아무 주문행이나 복제**해서 만들었다.
그러면 **기본키 중복 규칙만 걸리고 낟알 규칙은 한 번도 실행되지 않는다** — 초록이었지만
지키는 것이 없었다.

★ 그래서 **선적이 실제로 가리키는** 주문행을 복제하도록 고쳤다. 이제 두 규칙이 함께
걸리고, 낟알 규칙이 실행된다는 것이 확인된다.

### 5.1 시험이 스스로 거짓 빨강을 냈던 것도 둘

· 하위 프로세스 출력의 한글·`«»`·`✗` 가 콘솔 코드페이지에서 `UnicodeEncodeError` 를
  내며 **종료코드 1** 이 됐다. 그러면 「막혔다(2)」·「검증 실패(1)」·「출력이 깨졌다(1)」
  가 구별되지 않는다. → `PYTHONIOENCODING=utf-8` 을 주고 그 이유를 주석에 적었다.
· `tmp_path` 를 그대로 `--data-dir` 로 준 시험 — conftest 의 격리 fixture 들이 거기에
  이미 저장소를 만들어 두므로, 그것을 「스크립트가 만든 것」으로 셌다. → 하위 폴더를
  따로 만들어 확인한다.

⚠️ 둘 다 **통제는 멀쩡했고 시험이 틀렸다.** 빨강을 봤을 때 제품부터 의심하면 멀쩡한
것을 고치게 된다.

---

## 6. 다음 단계에 넘기는 사실

1. **`INV-01` 의 열쇠는 `snapshot_id` 다** — `STK-{일자}-{자재}-{창고}` 꼴이고, 이름이
   Snapshot 판 ID(`ds_…`)와 헷갈리기 쉽다. 범위 색인 설계에서 **둘을 반드시 구분**해야
   한다. 온톨로지 객체 id 는 `STK-…` 이고 판은 `ds_…` 다.
2. ⚠️ **[2026-08-20 3단계에서 정정]** 「다섯 종이 전부 한 범위」라고 적었는데 **틀렸다.**
   행마다 `scope_node_id` 가 다르고, 색인을 세워 세어 보니 두 범위에 걸쳐 있다:

   ```
   plant-afs-battery-02    1,215건
   plant-afs-smelting-01     445건
   tenant 는 tenant-afs-demo-materials 하나
   ```

   ★ 내가 본 것은 **인증판 하나의 `scope_node_id`**(첫 행에서 파생)였고, 그것을
   「자료 전체의 범위」로 읽었다. 대표값 하나를 전체의 성질로 넓힌 것이다.

   ⚠️ 그래도 **정본에 타 조직 행을 섞지 않는다**는 원칙은 그대로다 — 다른 *tenant* 는
   여전히 하나뿐이므로, tenant 격리 시험에는 별도 fixture 가 필요하다.
   ★ 다만 **조직 노드 간 격리**는 정본 데이터로 그대로 시험할 수 있다.
3. `entity_mode=VIRTUAL` 이다. 실적(`REAL`)과 섞이지 않는다.

---

## 7. 진척

```
1 ResolveContext·회귀          ██████████  완료
2 정본 시연 데이터 정렬         █████████░  완료 · 빌드 멱등만 P1 로 이월
3 CERTIFIED → 범위 색인        ░░░░░░░░░░  다음
4 Dataset Resolver            ░░░░░░░░░░
5 CALC.* 어댑터               ░░░░░░░░░░
6 경로 → G5 어댑터             ░░░░░░░░░░
7 종단 재실행·부정 시나리오      ░░░░░░░░░░
8 계약 승인·설치               ░░░░░░░░░░  HOLD
```
