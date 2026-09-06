# AI 데이터 수집·정비 오케스트레이터 v0.1 — 인수인계

브랜치 `claude/data-acquisition-orchestrator-20260905`
기점 `1bdada5a1` (Codex 의 기준선 통합 위) · **push 하지 않았다**

---

## 1. 무엇을 만들었나

자연어 데이터 요청을 받아 **찾기 → 평가 → 수집 → 정리 → 연결 → 검증**까지 수행하는
오케스트레이터. 첫 공식 Provider 는 OpenDART 이고, LS MnM 10개년 연결 재무제표를 종단
카나리로 썼다.

```
사용자 자연어 요청
      ↓
AI 수집 계획·매핑 제안          ← LLM 은 여기까지만
      ↓
결정론적 정책·권한 검사          ← ★ 관문
      ↓
격리 수집 및 Dry-run           ← 적재본에 한 줄도 쓰지 않는다
      ↓
품질·대사·중복 검사
      ↓
사용자 검토 후 적용             ← 사람 관문
      ↓
격리 DB 적재 · 계보
```

## 2. 코드 경계

```
core/external_intelligence/            (기존 .py 를 패키지로 — import 경로 불변)
  __init__.py            원천 등록부·지표·관측값·등급 정책        (기존 652줄)
  acquisition_models.py  ★ 닫힌 어휘 — 상태 11 · 전이표 · 자료성격 4
  raw_store.py           ★ 원문 보관소 — 내용주소·체크섬·비밀 차단
  acquisition_store.py   ★ 작업 저장소 — 두 층 통제 · 계약 제안 · 격리 적재
  request_interpreter.py ★ 자연어 관문 — LLM 제안을 결정론적으로 판정
  mapping.py             ★ 라우팅·매핑 검증·새 계약 제안
  orchestrator.py        ★ discover / dry_run / apply
  provenance.py          ★ 「이 숫자는 어디서 왔나」
  providers/
    base.py              8 메서드 계약 · SSRF 전송층
    __init__.py          등록부 · 우선순위(기존 표를 읽는다)
    opendart.py          첫 Provider  — 공시 재무제표 → PUB-01
    ecos.py              둘째 Provider — 환율·금리·물가 → EXT-01

api/routes/acquisition_control.py      14 라우트 · /api/v1/external/acquisition/*
frontend/src/components/AcquisitionPanel.tsx
frontend/src/lib/externalIntelligenceApi.ts   (기존 파일에 덧붙임)
```

## 3. 재사용한 것 — 새로 만들지 않았다

| 기존 | 쓴 자리 |
|---|---|
| `external_research.validate_public_target` | SSRF·사설망·리디렉션 검사 전부 |
| `external_intelligence.PURPOSE_MIN_GRADE` | 용도별 최소 신뢰등급 |
| `external_intelligence._SOURCE_PRIORITY` | 원천 우선순위(지시 3) |
| `external_intelligence.QUALITY_STATUS` | `SUPERSEDED` 등 품질 상태 |
| `data_preparation.models.QUARANTINE_KINDS` | 격리 사유 두 종 |
| `decision_ledger` 주체 `external_connection` | 선언만 돼 있고 쓰이지 않던 것 |
| `route_authority` 표 | 권한 배정 |
| `system_ids` | 내부 ID 자동 발급 |

⚠️ **한 자리 어긋난 것**: 지시 3 은 「계약 Provider」를 「공공기관 RSS」보다 앞에 두는데
기존 `_SOURCE_PRIORITY` 는 `RSS=3 · PROVIDER_API=4` 다. 지금 원천이 전부 `API`/`CSV` 라
결과가 바뀌지 않아 기존 표를 그대로 뒀다. **바꿀 곳은 기존 표 하나다.**

## 4. 지시 14 의 완료 구분 — 어디까지 했나

```
오케스트레이터 구현   ✔
Provider 구현        ✔  OpenDART · ECOS 2개
fixture 검증         ✔  390건 · 네트워크 0회
실제 API 실측        ✘  AFS_OPENDART_API_KEY 가 없다
실제 데이터 수집      ✘
격리 DB 적재         ✔  data_acquisition_rows · 전부 UNCERTIFIED
운영 적용            ✘  Snapshot 인증 · 업무키트 결속 · 준비도 재평가
자동갱신 활성화       ✘  일정은 걸 수 있으나 스케줄러 배선은 안 함
```

★★★ `apply()` 가 「운영 적용까지 했다」고 **말하지 않는다.** `ApplyReport.pending_stages`
가 안 한 단계와 이유를 담고, 시험이 「한 단계가 완료와 미완 양쪽에 있지 않은지」를 센다.

## 4-1. 두 번째 Provider(ECOS)를 붙여 보고 안 것

★★★ **첫 Provider 로 세운 계약이 진짜 계약이었는지는 두 번째를 붙여 봐야 안다.**
붙여 보니 네 군데가 어긋났고, 전부 「한 곳에서 정해야 할 것을 두 곳에서 정한」 유형이었다.

    ① 주기 D 인데 기간을 YYYYMM 으로 만들었다        실제 호출이면 원천이 거부한다
    ② 커서가 전진 못 하면 같은 구간을 되풀이했다      중복만 쌓인다
    ③ 계보 질의가 DART 필드명을 박아 놨다            ECOS 는 기간·단위가 **조용히 빈 값**
    ④ 업무 키 규칙이 호출부에 흩어질 뻔했다           같은 행이 다른 키 → 중복 인덱스 무력화

⚠️ 특히 ③ — **한 계약에서만 맞는 코드는 두 번째 계약에서 오류를 내지 않는다. 빈 값을 낼 뿐이다.**

### ECOS 가 다른 점 셋 (그래서 명시적 변환기가 따로 있다)

  · **인증키가 URL 경로에 있다** — S1 의 값 기반 삭제가 실제로 필요했던 첫 원천.
  · **오류가 HTTP 200 으로 온다** — `RESULT.CODE` 를 본다. `INFO-200` 만 「자료 없음」.
  · **세부항목 코드를 물어본다** — 상수로 박으면 원천이 바꾼 날 다른 계열을 받는다.

### 새 통제: 계약이 «말하는 성격» 과 행의 성격이 같아야 한다

`assert_origin_fits()` 를 적용 직전에 둔다. 이 검사가 **계약의 `classification` 을 읽는
첫 코드**다(기존 코드는 아무도 읽지 않았다).

⚠️ 키트의 `EXT-01` 이 `SYNTHETIC` 인 것은 「환율이 원래 가짜」가 아니라 **이 키트 전체가
  시연용**이기 때문이다(`entity_mode: VIRTUAL · not_for_management_decision: true`).
  코드에 `KIT_MODES = ('DEMO/SYNTHETIC','REAL')` 이 있고, 실제 회사용 키트는 같은 열 모양에
  `REAL` 이 붙는다.

  → 그래서 **시연 키트 파일은 고치지 않는다.** 수집한 실제 데이터는 격리 저장소에 들어가고
    `ext01_public_proposal()` 로 **자기 선언**을 따로 갖는다. 두 저장소는 원래 다른 곳이다.

★ 나중에 **실제 회사용 키트(REAL 모드)** 를 만들 때 정할 것: 그 키트의 `EXT-01` 환율을
  ① ECOS 매매기준율로 채울지 ② 회사 시스템의 실제 체결 환율로 채울지 ③ 둘을 구분해 둘지.
  회계·재무 담당의 판단이고, **그 키트를 만들 때** 물으면 된다.

## 5. 만들면서 실제로 뚫린 것 넷

**① 퍼센트 인코딩된 비밀키가 디스크에 적혔다.**
값 기반 삭제는 원문(`abc/def`)을 찾지 못하고, 이름 기반은 목록 밖 인자명을 몰라 지나쳤다.
→ 삭제를 세 표기로 넓히고 차단기가 **디코드한 형태로도** 보게 고쳤다.

**② 요청한 회사와 다른 회사의 응답이 그대로 적재됐다.**
연결/별도와 연도는 검사하면서 **회사만 빠져 있었다.** fixture 를 흘려 보고 출력의
`corp_code` 가 요청과 다른 것을 알아챘다.

**③ 시험이 결함을 단언하고 있었다.**
OpenDART 가 `status=010`(키 오류)을 `AUTH` 로 판정해 예외에 실었는데 오케스트레이터가
**예외 타입만 보고** `POLICY` 로 덮어썼다. 그리고 나는 그 동작에 맞춰 시험을 썼다 —
초록인 채 결함이 굳을 뻔했다. 판정을 `failure_kind_of()` 한 곳으로 모았다.

**④ 공통 봉투를 매핑의 책임으로 셌다.**
Provider 는 테넌트를 모르는 것이 설계인데 검증기가 그것을 미매핑으로 세어 **어떤 매핑도
통과하지 못했다.** 그런 검사는 사람이 곧 끈다.

## 6. 통제 — 그리고 그 통제가 실제로 도는지 확인한 방법

| 통제 | 어떻게 확인했나 |
|---|---|
| DB `CHECK` 제약 | 응용층을 **건너뛰고** SQL 로 `status='ALMOST_DONE'` 직접 삽입 → IntegrityError |
| 조건부 UPDATE | 낡은 스냅샷을 쥐여 **응용층을 통과시킨 뒤** 두 번째 승인이 지는지 |
| 권한표 | 표에서 한 줄을 **실제로 빼 보고** 시험이 잡는지 (자체 판정 없는 라우트로) |
| SSRF 차단 | 평문·목록 밖·비표준포트·사용자정보·fragment·빈목록 6종 + **DNS 가 사설망을 가리키는 경우** |
| 비밀 차단기 | 삭제기를 monkeypatch 로 **무력화한 뒤** 파일이 안 만들어지는지 |
| LLM 권한 탈취 | 제안에 `unrestricted:true`·넓은 범위·낮은 등급을 넣어 보고 셋 다 버려지는지 |
| 원문 미유출 | `samples`·`rows` 에 실제 값이 든 계약을 넘기고 프롬프트에 그 값이 없는지 |

## 7. 남은 일

| | |
|---|---|
| **A** | `PUB-01` 을 인증 키트에 편입 → Snapshot 인증 · 업무키트 결속 · 준비도 재평가 |
| **B** | 실제 `AFS_OPENDART_API_KEY` 로 1회 실측 (한도 주의 — 10개년 × 4분기 한 번에 받지 말 것) |
| **C** | KOSIS·공공데이터포털·World Bank Provider 추가 (`base.Provider` 8메서드 구현). ECOS 완료 |
| **D** | 운영 스케줄러가 `GET /due` 를 읽어 하나씩 부르도록 배선 (프로세스 내 타이머 금지) |
| **E** | 화면 렌더 확인 — 로그인 뒤라 이번에 눈으로 보지 못했다 |
| **F** | `sim_marketing` 도메인 내용 업무 검토 (이전 묶음에서 이월) |

⚠️ **C 를 할 때**: `normalize()` 의 기본 구현을 만들지 말 것. 기반 클래스가 일부러 주지
않는다 — 주면 새 Provider 가 물려받아 「대충 돌아가는」 상태가 되고, 그 파서는 OpenDART
응답도 KOSIS 응답도 통과시키되 뜻은 다르게 읽는다(지시 4).

## 8. 검증 기록

```
전체 스위트 T3   6,098 passed · 2 skipped · 실패 0        798초 (13:18) · 1회만 실행
                 ⚠️ ECOS(신규 76건) **이전** 시점의 결과다 — ECOS 추가 뒤 T3 는 다시 돌려야 한다
수집 회귀        390건 통과 (90초) · 네트워크 0회 · LLM 0회   ← ECOS 포함
tsc -b           0건
프로덕션 빌드     성공 · 패널 문구·경로 상수가 번들에 실림 확인
제품 경로 실측    없는 경로 404 · 수집 라우트 4개 401
```

**정산이 맞는다.** 기준선 5,793 + 신규 305 = 6,098, 그리고 수집 건수 6,100 = 통과 6,098 +
건너뜀 2. ⚠️ 이 대조를 하는 이유: 끝까지 자르는 편집이 시험을 조용히 지워도 「전부 통과」는
그대로 나온다 — 이 저장소에서 회귀 21건이 사라진 채 초록이었던 적이 있다.

⚠️ **화면이 그려지는 것은 보지 못했다.** 앱이 로그인 뒤에 있고 대리 로그인을 하지 않았다.
「배선됐다」까지만 주장한다 — §7-E 가 남은 일이다.

⚠️ **이 T3 는 브랜치 `claude/data-acquisition-orchestrator-20260905` 의 것이다.** 기점
`1bdada5a1`(Codex 기준선) 위에서 돌렸고, 다른 브랜치의 미커밋 작업은 포함하지 않는다.

⚠️⚠️ **T3 를 다시 돌려야 한다.** 위 결과는 커밋 `d246958be` 시점이고, 그 뒤 ECOS 묶음
  (`938e4304c` · 신규 76건)이 들어왔다. 수집 회귀 390건과 영향 회귀는 통과했지만
  **전체 스위트로는 확인하지 않았다** — 다음 세션의 첫 일이다.

## 9. 금지 범위 (이번에도 지켰다)

- push 하지 않았다
- 임의 URL 수집 없음 — 등록된 `allowed_hosts` 밖으로 한 번도 나가지 않는다
- LLM 이 만든 코드를 운영 프로세스에서 실행하지 않았다
- 운영 DB 직접 SQL 쓰기 없음 — 격리 `data_acquisition_rows` 만 쓴다
- 공개자료를 내부 `REAL` 로 표기하지 않았다 (관문이 거부한다)
- 비밀키를 커밋하지 않았다 — `.env.example` 에 **이름만** 추가
