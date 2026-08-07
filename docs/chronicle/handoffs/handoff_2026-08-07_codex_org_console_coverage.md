# 이관 — 거버넌스 콘솔에 «왜 0인가» 를 띄운다 (Codex 담당 · 2026-08-07)

> 백엔드는 준비를 끝냈습니다. **화면이 없어서 아직 아무도 못 봅니다.**
> 작성: Claude Code(백엔드) → 수신: Codex(UI/UX·프론트)

## ★ 한 문장

`GET /api/v1/telemetry/orgs` 는 「부서별 비용의 대부분이 «미상» 이고 그중 얼마가 **영영
되살릴 수 없는지**」를 응답에 담아 주는데, **`frontend/src` 에 이 엔드포인트를 부르는 코드가
0건**이라 그 사실이 화면에 존재하지 않습니다.

## 왜 이것이 사소하지 않은가

이 화면은 정의상 «무엇이 안 되어 있는가» 를 모아 보여 줍니다. 그래서 **0 은 「문제 없음」으로
읽힙니다.** 지금 상태로 부서별 비용 막대만 띄우면 사람은 그것을 전체라고 읽습니다 —
실측(2026-08-07) 기준 `llm_call_log.jsonl` **1,133건의 부서 귀속률은 0%** 입니다.
막대가 서면 그 막대는 전부 거짓입니다.

## 실측 (2026-08-07 · 재확인)

| 확인 | 결과 |
|---|---|
| `frontend/src` 에서 `telemetry/orgs` 호출 | **0건** |
| `frontend/src` 에서 `telemetry/agents` 호출 | **0건** |
| 지금 붙어 있는 텔레메트리 화면 | `TelemetryPanel.tsx` — `/telemetry/projects`·`/telemetry/summary` 둘뿐 |
| `governanceApi.ts` 의 coverage 소비 | 마스터·카탈로그·크로스워크 3종만. **조직 운영 현황은 없음** |

## 서버가 이미 주고 있는 것

`GET /api/v1/telemetry/orgs` → `data.usage`

```jsonc
{
  "orgs": [
    { "org": "quality", "calls": 12, "failed": 1, "failure_rate": 0.0833,
      "cost_usd": 0.42, "unpriced_calls": 2,
      "scope_node_ids": ["node_41402723bc90"] }   // [D-019] 롤업축(0~N개)
  ],
  "coverage": {
    "records": 1133,
    "without_org": 1133,
    "without_org_pre_field": 972,   // 소급 불가 — 필드가 없던 시기
    "without_org_missing": 161,     // 고칠 대상 — 필드는 있는데 안 실렸다
    "attribution_rate": 0.0,
    "note": "전체 1133건 중 …"       // 사람이 읽을 한 문장
  }
}
```

같은 응답의 나머지 칸(`pending_approvals`·`policy_denials` 등)은 **`Metric`** 입니다 —
`{value, known, error, detail}`. `value: null` 은 **0 이 아니라 «읽지 못했다»** 입니다.

## 화면이 지켜야 할 것 (수용 기준)

1. **`known: false` 인 칸에 숫자를 쓰지 않는다.** «확인 못 함» 과 `error` 를 쓴다.
   0 으로 표시하면 「승인 대기 없음」·「위반 없음」으로 읽히고, 아무도 다시 묻지 않습니다.
2. **`coverage.note` 를 접어 두지 않는다.** 부서별 표·차트와 **같은 화면, 같은 시야**에 둡니다.
   툴팁이나 «자세히» 뒤로 넣으면 없는 것과 같습니다.
3. **`without_org_pre_field` 와 `without_org_missing` 을 나눠 보인다.** 앞은 어떤 배선을 고쳐도
   되살아나지 않고, 뒤는 고칠 대상입니다. 합쳐 보이면 「기록만 고치면 되는 문제」로 읽힙니다.
4. **`attribution_rate` 가 낮을 때 부서별 차트를 «전체» 처럼 그리지 않는다.** 분모를 함께 쓰거나,
   차트 자체를 「표본 N건」으로 라벨링합니다.
5. **`unpriced_calls` 를 0원으로 더하지 않는다.** 단가를 모르는 호출이며, 0 으로 두면
   「공짜였다」는 거짓이 됩니다(서버는 이미 비용에서 빼고 건수만 셉니다).
6. **`scope_node_ids` 가 2개 이상인 행**은 조직개편으로 기록 시점이 갈린 부서입니다.
   하나만 골라 표시하면 나머지 기간의 비용이 말없이 다른 조직으로 옮겨갑니다.

## 만들지 말아야 할 것

- ⚠️ **`scope_node_ids` 로 부서를 합치는 기본 뷰.** 실측상 활성 부서 12개 중 **9개가
  `node_41402723bc90`(LS_MnM) 하나**에 매핑돼 있어, 노드로 묶으면 「(미상) 한 줄」이
  「LS MnM 한 줄」로 바뀔 뿐 **부서별 비용은 여전히 사라집니다.** 세는 축은 `org`(부서)이고
  노드는 **선택적 롤업**입니다(D-019).
- ⚠️ **비어 있는 값을 «0» 이나 «—» 로만 채우기.** 왜 비었는지가 이 화면의 내용입니다.
- ⚠️ **Mock 데이터로 화면을 완성 처리하기.** 지금 이 지표의 진짜 값은 「거의 전부 미상」이고,
  그 모습 그대로 보이는 것이 이 화면의 목적입니다.

## 권한 — 아무에게나 열리지 않습니다

`assert_governance_readable(p)` 를 통과해야 합니다. 「어디가 비어 있는지」는 그 자체로
보호 대상이라는 판단입니다. 403 일 때 화면은 **빈 대시보드가 아니라 «권한 없음»** 을 보여야
합니다 — 빈 대시보드는 「문제 없음」으로 읽힙니다.

## 참고 경로

| 무엇 | 어디 |
|---|---|
| 라우트 | `api/routes/telemetry_control.py` `telemetry_by_org` |
| 집계·`Metric`·note 문구 | `core/org_operations.py` |
| 결정 | `.agents/DECISIONS.md` [D-019] |
| 원인 규명 | `docs/chronicle/handoffs/handoff_2026-08-07_p42_dept_attribution.md` |
| 기존 텔레메트리 화면 | `frontend/src/components/TelemetryPanel.tsx` |
| 기존 coverage 소비 패턴 | `frontend/src/lib/governanceApi.ts` |

## 백엔드 쪽 남은 일 (Codex 대기 사항 아님)

- 신규 프로젝트는 이제 `start_sprint` 에서 소유권이 실립니다. **기존 미태깅 프로젝트 53개는
  그대로 둡니다** — 만든 사람을 모르는 프로젝트에 부서를 추정해 넣으면 그것이 곧 「틀린 부서로
  귀속된 비용 통계」이고, 틀린 숫자는 «미상» 보다 나쁩니다(D-019).
- 그러므로 **화면에서 «미상» 은 당분간 사라지지 않습니다.** 줄어드는 것은 앞으로 쌓이는 분뿐이며,
  그 사실 자체가 위 3번 항목이 화면에 있어야 하는 이유입니다.
