# Codex 검토 인계 — 2026-09-20 (2차) · 권한 P1 · A · B · C 전부 처리

작성: Claude Code · 2026-09-20 KST. **푸시 없음.** 기준 HEAD `c9623f286`.
**전체 21/40=52.5% · 로컬 18/28=64.3% 를 마지막 인정치로 유지합니다.** 칸 판정은 제 몫이 아닙니다.
지시: `CODEX_D01_REVIEW_NEXT_2026-09-20.md` §2·§3-A·§3-B·§3-C — **네 건 모두 마쳤습니다.**

---

## 0. 읽는 순서

| 순서 | 문서 | 성격 |
|---|---|---|
| 1 | `CLAUDE_RELEASE_READ_VISIBILITY_2026-09-20.md` | P1 권한 보완 |
| 2 | `CLAUDE_A_REACTIVATE_RESTORE_2026-09-20.md` | A 최소안 **구현** |
| 3 | `CLAUDE_REACTIVATE_AND_LABEL_2026-09-20.md` | A 조사 · B 라벨(확인창 포함 검증 완료) |
| 4 | `CLAUDE_C_DOCUMENT_LEAVE_CAUSE_2026-09-20.md` | C 원인 확인 |

---

## 1. 네 건 결과

| 지시 | 결과 |
|---|---|
| **§2 권한 P1** | `get_release` 에 목록과 **같은** 가시성 판정(fail-closed) · 상태 확인 실패 시 실행 payload 차단 · 예외 원문 비노출. 비가시 릴리스가 **없는 릴리스와 같은 404** 로 바뀜(API·화면 양쪽 실측) |
| **§3-A 재개 상태** | 조사 후 **최소안 구현**. `reactivate` 가 이력의 「중단 직전」 상태로 되돌린다 — `candidate` 는 `candidate` 로. 모르면 **거절**. `data_fingerprint` 도 함께 복원(종전에는 지워졌다) |
| **§3-B 라벨** | 선택 목록·**확인창** 모두 `이름 · 게시 시각 · release_id`. 둘 다 브라우저 실측 |
| **§3-C 문서 이탈** | **원인 확인 완료** — 제품 보호는 등록·발화·`preventDefault()` 까지 정상이고, 이동한 것은 **자동화가 확인창을 처리**했기 때문 |

## 2. 새로 찾아 고친 것 (지시 밖에서 나온 것)

두 건 다 **조사 중에 드러난 같은 유형**이라 마저 처리했습니다. 과했다면 되돌리겠습니다.

1. **`reactivate` 가 `data_fingerprint` 를 지우고 있었다.** `set_status` 는 준 값으로
   덮어쓰는데 재개는 빈 값을 넘겼다 → 「어느 업무 데이터 위에서 내린 결정인가」가 사라진다.
   A 최소안에 포함해 고쳤다.
2. **구 통제실 내려받기는 성공하면 아무 말도 하지 않았다.** 실제 클릭으로 확인했다 —
   `export` 200 인데 alert 0건. 브라우저가 조용히 받으면 「눌렀는데 아무 일도 없다」다.
   새 Studio 는 「시작했습니다」라고 말한다. 같은 파일에서 이미 고친 여덟 자리와 **같은
   유형**이라 한 줄 더했다(시험 + 변이 포함).

## 3. 검증 요약 (전부 제 실행값 · Codex 독립 실행값 아님)

```
서버(격리 러너, strict-writes) — 관련 시험만
  release_item_visibility 8 · release_list_visibility 2 · release_catalog_cleanup 14
  program_lifecycle 22 · program_usable_existence 4 · reactivate_restores_prior_state 7
  route_authority_table 10                                    합계 67 passed
  sources_unchanged: true · protected_assets_unchanged: true

프런트  197 PASS / 0 FAIL · check-studio-contracts 157 / 0 · tsc -b · build 통과

극성   권한 2 · 재개 3 · 내려받기 안내 1 = 6종, 각각 단독으로 물림 · 원복 해시 일치
       (가시성 가드 제거 → 6 failed / 2 passed · 재개를 종전 동작으로 → 5 failed)
```

### 브라우저 실측 (격리 · 로그인 · 실제 포인터 클릭)

```
비가시 릴리스 직접 링크 → 거절 · 내용 0      가시 릴리스 → 정상 열림
릴리스 선택 목록·확인창 → 이름 · 시각 · id   확인창 「취소」 → 상태 불변
구 통제실 내려받기 실클릭 → export 200 · 「✅ 내려받기를 시작했습니다 — ….zip」
재개 경로(제품 HTTP) → candidate → disable → reactivate → **candidate**
```

## 4. 여전히 미검증 — **사람 또는 승인이 필요합니다**

| 항목 | 왜 |
|---|---|
| 문서 이탈 시 **브라우저 확인창 실물**(취소/계속) | 자동화가 그 창을 띄우지 못함. **사람이 한 번 눌러 보면 닫힙니다** |
| 구 통제실 **「검토용 버전 저장」 실클릭** | 네이티브 `confirm()` 을 자동화로 지날 수 없음(가로채면 실사용자 확인이 아님) |
| `alert` **네이티브 대화상자 렌더** | 문구 확인을 위해 `window.alert` 을 수집기로 바꿨음 — 호출·문구는 확인, 상자 렌더는 미관찰 |
| D01 **반복 업무** 수용 | 실제 사용자·자료 필요 |
| D07 / 유료 제작 1회 | 승인 대기. 「제 토큰 대체」는 실제 생산자 관통을 증명하지 못합니다 |

## 5. 판단을 구하는 것

1. **A 후속 문구.** 후보로 되돌아가면 사용자는 「사용 재개」를 눌렀는데 운영에서 안 도는
   결과를 본다. 버튼 이름·완료 문구를 함께 정해야 한다.
2. **승격됐던 판**을 내렸다 켜는 경우 — `workspace_promotion` 은 별도 테이블이다.
3. **§2 의 「소유자 없는 릴리스」 처리 방침** — 지금은 차단만 하고 보존한다.
4. 위 §2 의 두 추가 수정이 범위를 벗어났는지.

## 6. 나무 상태

```
로컬 커밋 4건 (푸시 없음)
미커밋 (제 것)
  M api/routes/factory_control.py            ← P1 권한
  M core/program_lifecycle.py                ← A 최소안
  M frontend/src/components/ControlPanel.tsx ← 앞 라운드 8자리 + 성공 안내 + 주석 정정
  M frontend/src/components/WorkspacePanel.tsx · frontend/src/App.tsx   ← B 라벨
  M frontend/src/factory/StudioExecutionRequests.tsx (훅 수출 1줄)
  M frontend/scripts/check-project-entry.mjs (74건)
  ?? tests/test_release_item_visibility.py · tests/test_program_reactivate_restores_prior_state.py
  M .agents/TEAM_BOARD.md · docs/handoff/*
일부러 제외
  data/interaction_log.jsonl   운영 사용자 대화 로그
  tests/b6_sse_probe.py        격리 하네스(원복 대상)
⚠️ 제 것이 «아닌» 새 파일이 트리에 있습니다 — `docs/roadmap/NCP_OPERATIONAL_TRIAL_CICD_2026-09-20.md`.
   건드리지 않았고 커밋 대상에서 제외합니다.
```

## 7. 환경 / 원복 대상 (갱신)

- **워크트리 동기화**: 격리 서버는 `C:/sentwt` 사본을 실행합니다(프런트는 주트리).
  이번에 동기화한 파일 — `C:/sentwt/api/routes/factory_control.py`,
  `C:/sentwt/core/program_lifecycle.py` (+ 무해한 프런트 사본 2).
- 격리 fixture 추가: `latest_state.json` 에 **`project_name`**(구 통제실 진척 100% 분기를
  태우기 위해). 기존 `artifacts`·`frontend_code_summary`·`supervisor_*`·`user_manual_summary` 유지.
- 격리 DB: 합성 릴리스 `…150827` 은 `active`(원복 완료로 쓰지 않음), `…150809` 는
  `candidate`(재개 시험으로 disable→reactivate 왕복함).
- 격리 서버에 보낸 쓰기: 릴리스 저장 2 · disable 2 · reactivate 2 · 거절 POST 3(409×3).
  전부 합성 대상. **「전사 승격」·「공유」는 누르지 않았습니다.**
- LLM 0 · 운영 데이터·키·사용자 로그 무접촉 · skip/xfail 없음 · 단언 약화 없음.
