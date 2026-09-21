# A. 「사용 재개」 최소안 구현 — 중단 직전 상태로 되돌린다

작성: Claude Code · 2026-09-20 KST. 지시: `CODEX_D01_REVIEW_NEXT_2026-09-20.md` §3-A
(조사 → 최소안 제시 → 사용자 지시로 구현).
**커밋·푸시 없음 · LLM 0 · 운영 무접촉 · 권한표·역할·API 계약 무변경.**
전체 **21/40=52.5%** 마지막 인정치 유지.

## 무엇이 문제였나

```
candidate ──disable──▶ disabled ──reactivate──▶ active
(Preview 청중)                                  (운영 청중)
```

`reactivate` 가 `set_status(ACTIVE)` 하나였다. 그래서 **승인·승격 없이 끄고 켜는 것만으로**
아직 승인되지 않은 후보 판이 운영 청중이 됐다 — `core/app_preview.audience_for_state` 가
candidate→Preview, active→운영으로 갈라 놓은 의미가 이 문으로 사라졌다.
같은 자리에서 **`data_fingerprint` 도 지워졌다**(`set_status` 는 준 값으로 덮어쓴다).

## 고친 것 — `core/program_lifecycle.py` 한 파일

```python
reactivate(release_id, actor, reason=""):
    현재가 DISABLED 가 아니면  → 종전 동작 유지(ACTIVE)   ← 이 한 경로만 고친다
    DISABLED 이면:
        이력에서 «마지막 to_status=DISABLED» 의 from_status 를 읽는다
        값이 STATUSES 밖이거나 DISABLED 면  → **거절**(추정하지 않는다)
        아니면 그 상태로 되돌리고, 마지막 비어 있지 않은 data_fingerprint 도 함께 싣는다
        사유에 「중단 직전 상태로 되돌림(<상태>)」을 남긴다
```

* 재료는 **이미 있던 것**만 쓴다 — `program_status_history.from_status` · `data_fingerprint`.
  새 열·새 테이블·새 권한 없음.
* 감사 이력은 지우지 않고 **한 줄 더** 쌓는다.
* `set_status` 의 일반 전이 정책은 **건드리지 않았다**(지시대로).
* API 라우트(`program_control.reactivate`)는 **무변경** — 호출부가 그대로다.

### ⚠️ 남는 한계 (숨기지 않는다)

이력을 읽고 `set_status` 로 쓰는 사이는 **한 트랜잭션이 아니다.** 이력은 append-only 라
읽은 값이 뒤바뀌지는 않고, 그 사이 남이 상태를 바꿨다면 그것도 이력에 남는다. 완전한
원자성은 `set_status` 구조 변경이 필요해 「최소안」 범위를 넘는다고 보고 하지 않았다.

## 시험 — 신규 7건 (격리 러너)

```
① candidate → disable → reactivate → **candidate**   (운영 청중으로 열리지 않는다)
   ★ 상태값만 보지 않고 audience_for_state 로 «의미가 갈리는지» 까지 확인
② ★ 양성 대조: active  출신은 active 로 돌아온다(과잉 차단 아님)
③ deprecated 출신은 **경고를 유지한** 채 돌아온다
④ 이력이 없으면 **거절**하고 상태를 바꾸지 않는다(「모르면 활성」 금지)
⑤ data_fingerprint 가 지워지지 않는다
⑥ 중단이 아닌 판(deprecated 경고 해제)은 **종전 동작 그대로**
⑦ 감사 이력이 candidate→disabled→candidate 로 쌓이고 사유에 복원 대상이 남는다

7 passed · sources_unchanged: true · protected_assets_unchanged: true
기존 회귀: test_program_lifecycle 22 passed · test_program_usable_existence 4 passed
```

### 극성 — 세 변이가 각각 물린다

```
① 무조건 ACTIVE 로(종전 동작 복원)   5 failed / 2 passed   원복✔
② 이력을 모르면 활성으로 추정        1 failed / 6 passed   원복✔
③ 지문을 빈 값으로 덮음              1 failed / 6 passed   원복✔
```

## 제품 경로 실측 (격리 · 로그인 상태 · 실제 HTTP 라우트)

```
GET  /api/v1/programs/{id}           → candidate
POST /api/v1/programs/{id}/disable   → 200
POST /api/v1/programs/{id}/reactivate→ 200
GET  /api/v1/programs/{id}           → **candidate**   ← 종전이면 active 였다
                                       reason: 「… 재개 — 중단 직전 상태로 되돌림(candidate)」
```

★ 이번 실측은 **제품 HTTP 라우트**를 통한 것이다. 화면 클릭(릴리스 관리 → 사용 재개)은
앞 라운드에서 별도로 확인했고, 두 증거를 섞지 않는다.

## ⚠️ 워크트리 동기화 (앞서 걸린 함정)

격리 서버는 워크트리 `C:/sentwt` 사본을 실행한다. 이번에도 `core/program_lifecycle.py` 를
동기화한 **뒤에야** 실측값이 바뀌었다. **원복 대상**에 추가: `C:/sentwt/core/program_lifecycle.py`.
(프런트는 주트리에서 뜬다 — `sent-frontend` 가 주트리 `frontend/` 를 쓴다. 서버만 워크트리다.)

## 지시대로 하지 않은 것

- 서버 전이 정책 일괄 변경 없음. 승격 경로·`workspace_promotion` 무변경.
- 실제 운영 실행·승격 하지 않음.
- 이미 `active` 가 된 격리 fixture(`…150827`)는 **원복 완료로 쓰지 않는다** — 그 판의
  마지막 중단 직전 상태가 `active` 라 자가 복원되지 않는다. 원복 목록에 남긴다.

## 함께 정해야 할 것 (내가 정하지 않는다)

1. **화면 문구.** 후보로 되돌아가면 사용자는 「사용 재개」를 눌렀는데 운영에서 안 도는
   결과를 본다. 버튼 이름과 완료 문구가 그 사실을 말해야 한다.
2. **승격됐던 판**을 내렸다 켜는 경우. `workspace_promotion` 은 별도 테이블이라 이 이력만으로
   승격 상태를 되살릴지는 다른 결정이다.
