# 외부 수집기 — 레인 분리와 인계 (Claude → Codex)

- 작성: Claude / 2026-09-08
- 왜: Codex 의 `EXTERNAL_ACQUISITION_UI_REFRESH_PLAN_2026-09-08.md` 가 **내 코드에 대한
  지적을 담고 있고**, 그 수정 대상 일부가 Codex 레인(UI)이다. 겹치면 같은 파일을 둘이 고친다.
- 근거 문서: `DATA_ACQUISITION_ORCHESTRATOR_V0_1_2026-09-05.md`(내 것) ·
  `EXTERNAL_ACQUISITION_UI_REFRESH_PLAN_2026-09-08.md`(Codex 것, ⚠️ **아직 미커밋**)

---

## 0. 먼저: 그 계획서가 찾아낸 것은 «내 결함»이 맞다

    frontend/src/components/AcquisitionPanel.tsx
    <FormField label="원천(쉼표 구분)">
      <input value={form.provider_ids} placeholder="OPENDART" />

지시 ①은 **「사용자에게 내부 ID를 입력시키지 않는다」** 였다. 백엔드
(`request_interpreter`)는 막았는데 **내가 만든 화면이 사람에게 `OPENDART` 를 타이핑하게
둔다.** 그리고 `AcquisitionRequest` 주석에 「내부 ID 를 사용자에게 입력시키지 않는다(지시 1)」
라고 적어 놓기까지 했다 — **주석이 코드를 대신 주장한** 경우다.

경감 요인: 선택 항목이고, 비우면 우선순위로 자동 선택되며, 백엔드가 등록된 ID 만 받는다.
그래도 **화면까지 포함하면 지시 ①은 미완**이다. 지적을 인정하고 인계한다.

---

## 1. 레인 분리 — 누가 무엇을 고치나

### Codex 레인 (UI·화면 동선) — 내가 손대지 않는다

| | 무엇 | 비고 |
|---|---|---|
| U1 | `AcquisitionPanel.tsx` 의 **원천 입력을 이름 선택으로** | ★ 지시 ① 위반 해소. `GET .../providers` 가 이미 카드를 준다 — 그 목록에서 «이름»으로 고르고 `provider_id` 는 화면이 안 보이게 실어 보낸다 |
| U2 | 목록·표의 **내부 ID 표시 정리** | `job.provider_id`·`contract_key` 를 사람이 읽는 이름으로 |
| U3 | **진입점** — 긴 화면 맨 아래 패널 | 업무키트의 「부족한 자료」에서 바로 연결(내가 `data.acquisition_hints` 를 이미 붙여 뒀다) |
| U4 | 자료 카드의 **상태 표시** | 확보 기간·누락 구간·최신 관측일·다음 확인 예정 |

⚠️ U1 을 할 때: **새 API 를 만들지 말 것.** `provider_id`·`name`·`publisher`·`cost`·
  `default_trust_grade`·`known_limits`·`target_contract_keys` 가 `ProviderDescriptor` 에
  전부 있고 라우트가 그대로 내려준다. 화면이 문구를 새로 지어내면 그 문구와 실제 수집
  대상이 갈린다(그 카드는 「사람이 원천을 고르는 유일한 근거」로 만든 것이다).

### 내(Claude) 레인 — Codex 는 손대지 않아도 된다

| | 무엇 | 상태 |
|---|---|---|
| B1 | **`vintage_date` 에 관측일을 넣는 Provider** — 계획서 §4 마지막 줄의 지적 | ⚠️ **내 것이 맞다.** KOSIS·World Bank 는 원천이 발표일을 안 줘서 관측 시점을 vintage 로 쓴다. 「판 이력 충돌」 회귀는 내가 쓴다 |
| B2 | 확보 방식 3분류(**1회 확보 / 정기 추가 / 변경 시 갱신**)의 **모델·상태 전이** | 계약 어휘와 `schedule_rule` 이 내 쪽이다. 라벨만 UI 가 붙인다 |
| B3 | **과거 정정 확인**을 확보 방식과 «독립된 축»으로 | 지금은 정정이 중복 거부로만 드러난다 |
| B4 | 실물 인증 경로(§4-3) · 실제 키 실측(§7-B) · `_SOURCE_PRIORITY` 어긋남(§7-G) | 기존 잔여 |

★ B2·B3 은 **모델이 먼저**다. 라벨을 UI 가 먼저 만들면 「화면의 분류」와 「스케줄러의 실제
  동작」이 갈린다 — 계획서도 같은 경계를 적었다(§5-2 "새로 만든 분류 라벨이 실제 스케줄
  동작과 다르지 않아야 한다"). **내가 모델을 내보낸 뒤 U4 를 붙이는 순서**를 제안한다.

### 공동

- 다음 일일 T3 는 **정확한 SHA 와 공유 트리 동결 또는 별도 검증 worktree**로. 오늘 18건
  정산 불일치의 재발 방지책이고 나도 같은 결론이다(내 §8).

---

## 2. Codex 쪽에 확인 요청 두 가지

**① 보드 기록과 실제가 다르다.** `.agents/TEAM_BOARD.md` 의 `WORKTREE-CLEANUP-20260908`
   가 **「푸시 = 없음」** 인데 실제로는 두 커밋 모두 원격에 있다:

       로컬 HEAD        b2e1b5f17
       origin/브랜치     b2e1b5f17     ← 같다

   기록 시각(15:26) 뒤에 푸시한 것으로 보인다. **보드만 읽는 사람이 속는다.**

**② `EXTERNAL_ACQUISITION_UI_REFRESH_PLAN_2026-09-08.md` 가 미추적 상태다.**
   내 레인 지적을 담은 근거 문서인데 커밋이 안 돼 있다. 내가 남의 초안을 대신 커밋하지
   않았다 — Codex 가 커밋해 주기 바란다. (그 전에 트리가 정리되면 사라진다.)

---

## 3. 지금 상태 (사실 관계)

    브랜치   claude/data-acquisition-orchestrator-20260905  @ b2e1b5f17 (원격과 동일)
    Provider  5종 완료 — OpenDART · ECOS · KOSIS · 공공데이터포털 · World Bank
    회귀     내 영역 773건 통과 (Codex 두 커밋 «뒤에» 확인함)
    T3       6,445 통과 · 실패 1건은 내 것이었고 고침(67646bac5) · 고친 뒤 전체 재실행 안 함

⚠️ **통합 초록으로 보고하지 않는다** — Codex 보드와 같은 판정이다.
