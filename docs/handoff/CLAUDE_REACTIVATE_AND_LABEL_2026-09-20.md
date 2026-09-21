# A 재개 상태 의미 (조사) · B 릴리스 라벨 (구현)

작성: Claude Code · 2026-09-20 KST. 지시: `CODEX_D01_REVIEW_NEXT_2026-09-20.md` §3-A·§3-B.
**커밋·푸시 없음 · LLM 0 · 운영 무접촉.** 전체 **21/40=52.5%** 마지막 인정치 유지.

---

# A. 「사용 재개」의 상태 의미 — 조사

> **후속:** 이 조사의 최소안은 사용자 지시로 **구현했다** —
> `docs/handoff/CLAUDE_A_REACTIVATE_RESTORE_2026-09-20.md`. 아래는 그 전의 조사 기록이다.

## 읽은 것

| 위치 | 사실 |
|---|---|
| `core/program_lifecycle.py` `reactivate` | `set_status(release_id, ACTIVE, …)` — **무조건 ACTIVE** |
| 같은 파일 `set_status` | 값·행위자·사유·존재·대체본을 검사한다. **전이 정책은 없다** — 어느 상태에서 어느 상태로든 간다 |
| 같은 파일 `USABLE` | `(ACTIVE, DEPRECATED)` — **`CANDIDATE` 는 여기 없다**(주석: 「후보 판은 운영에서 쓸 수 있는 것이 아니다」) |
| `core/app_preview.py` `audience_for_state` | `candidate → PREVIEW`, `active·deprecated → OPERATIONAL`. 「둘 다 되는 상태는 없다」 |
| `program_status_history` | `from_status` 열이 **이미 있다** — 직전 상태를 복원할 재료가 저장돼 있다 |

## 그래서 무엇이 문제인가

```
candidate  ──disable──▶  disabled  ──reactivate──▶  active
(Preview 청중)                                      (운영 청중)
```

**승인·승격 절차 없이 「끄고 켜기」만으로 Preview 전용 후보가 운영 청중이 된다.**
`audience_for_state` 가 그 둘을 갈라 놓은 의미가 이 경로로 사라진다.

⚠️ **실증한 것과 아닌 것을 나눈다.** 격리에서 상태값이 `candidate → disabled → active` 로
바뀐 것은 실측했다. 그러나 **그 판이 실제로 운영 데이터를 만졌다거나 권한을 우회했다는
것은 실증하지 않았다** — 운영 실행·승격은 하지 않았다.

## 최소안 (제시만 · 구현하지 않음)

`reactivate` 가 **이력에서 「사용 중단 직전」 상태를 읽어 그 값으로 되돌린다.**

1. `program_status_history` 에서 그 릴리스의 **마지막 `to_status == DISABLED` 이벤트**의
   `from_status` 를 복원 대상으로 삼는다. 재료는 이미 저장돼 있어 새 열이 필요 없다.
2. `candidate` 출신은 `candidate` 로, `deprecated` 출신은 `deprecated` 로(경고 유지).
3. **이력이 없거나 값이 `STATUSES` 밖이면 추정하지 않고 거절한다** — 「무엇으로 되돌릴지
   확인할 수 없습니다」. 모르면 `ACTIVE` 로 떨어뜨리지 않는다(지금 동작이 그것이다).
4. 원자성은 기존 `set_status` 트랜잭션 안에서 읽고 쓴다. `data_fingerprint` 는 기존 인자를
   그대로 쓰고 새로 만들지 않는다. 감사 이력은 지우지 않고 **한 줄 더** 쌓는다.
5. API·권한표·역할 무변경.

### 함께 정해야 하는 것 (내가 정하지 않는다)

- 화면 문구. 후보로 되돌아가면 사용자는 「사용 재개」를 눌렀는데 **운영에서 안 도는** 결과를
  본다. 버튼 이름과 완료 문구가 그 사실을 말해야 한다.
- 「승격됐던 판」을 내렸다가 켜는 경우. `workspace_promotion` 은 별도 테이블이라 이 이력만으로
  승격 상태를 되살릴지 말지는 다른 결정이다.

**보고 표기(지시대로):** 사용 중단·이력 보존 **확인** / 사용 재개 호출 **확인** /
**이전 상태 복원 미완료.** 이미 `active` 가 된 격리 fixture 를 원복 완료로 쓰지 않는다.

---

# B. 릴리스 라벨 — 생성 시각 + release_id (구현)

## 수정 파일

| 파일 | 무엇 |
|---|---|
| `frontend/src/components/WorkspacePanel.tsx` | `releaseLabel` 을 `이름 · 게시 시각 · release_id` 로. 선택 목록도 **같은 formatter** 사용. 옵션 타입에 `createdAt` 추가 |
| `frontend/src/App.tsx` | `releaseOptions` 에 `createdAt: r.created_at || ''` 를 실어 줌 |

* 시각은 **같을 수 있으므로** 시각만으로 구별하지 않는다 — id 를 항상 붙인다.
* 시각이 없으면 **「시각 미기록」**. 없는 값을 만들어 채우지 않는다.
* 선택값(`release_id`)·제목·저장 데이터는 **바꾸지 않았다**. 전체 앱 라벨 개편 없음.

## 실측

```
브라우저(격리, 로그인 상태)에서 선택 목록을 읽음 —
  「prj_ddb23f3f22075a4815fd · 2026-09-19 15:08:27 · prj_…_20260919_150827」
  「prj_ddb23f3f22075a4815fd · 2026-09-19 15:08:09 · prj_…_20260919_150809」
→ 같은 이름의 두 판이 이제 구별된다(종전에는 둘 다 「prj_ddb23f3f22075a4815fd」).

프런트 197 PASS / 0 FAIL · contracts 157 · tsc -b · build 통과
```

## 확인창도 검증 완료 (2026-09-20 후속)

`form_input` 으로 선택한 뒤 **실제 포인터 클릭**으로 「게이트 점검」 → 「운영에서 내리기」 →
확인창을 열어 **그 영역만** 짚어 읽었다(선택 목록 텍스트와 섞이지 않게).

```
확인창 본문:
  「prj_ddb23f3f22075a4815fd · 2026-09-19 15:08:27 ·
    prj_ddb23f3f22075a4815fd_20260919_150827 가 운영에서 내려갑니다. …」
  → 시각·ID 둘 다 포함 ✔
「취소」 클릭 → 확인창 닫힘 · 서버 상태 그대로(active) ✔  (부수 효과 0)
```

★ 앞 기록의 NOT_VERIFIED 는 **닫혔다.** 당시 실패는 네이티브 `<select>` 키보드 조작이
재현되지 않은 것이었고, `form_input` + 실제 클릭 조합으로 통과했다.

---

## 남은 것 / 다음

```
C 문서 이탈 보호 미발동 «원인 확인»        **완료**(별도 문서)
A 최소안                                   **구현 완료**(별도 문서)
B 확인창 렌더 문자열                        **검증 완료**(위 «후속» 절)
```
