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
  refresh_runner.py      ★ 정기 갱신 한 바퀴 + 자동적용 관문 6개
  readiness_bridge.py    ★ 「준비되지 않음」에서 끝내지 않는다 — 수집 제안
  providers/
    base.py              8 메서드 계약 · SSRF 전송층
    __init__.py          등록부 · 우선순위(기존 표를 읽는다)
    opendart.py          첫째 — 공시 재무제표   → PUB-01
    ecos.py              둘째 — 환율·금리·물가  → EXT-01
    kosis.py             셋째 — 생산·재고 지수  → EXT-03
    datagokr.py          넷째 — 공공데이터포털  → EXT-03  (기반 + 서비스별 Provider)

api/routes/acquisition_control.py      15 라우트 · /api/v1/external/acquisition/*
api/routes/data_preparation_control.py 준비도 응답에 수집 제안을 얹는다(6줄 추가)
scripts/run_acquisition_refresh.py     운영 스케줄러 진입점
frontend/src/components/AcquisitionPanel.tsx
frontend/src/components/DataReadinessBoard.tsx           (제안 구역)
frontend/src/lib/externalIntelligenceApi.ts · dataPrepApi.ts  (기존 파일에 덧붙임)
```

⚠️ **Provider 를 만들면 다섯 곳에 넣어야 한다** — 등록부(import) · 업무키 규칙표 ·
  API 계약 제안 규칙 · 스케줄러 스크립트 · 준비도 제안 라우트. 빠뜨리면 등록부에 없어
  화면에 안 나오고, 요청 관문이 「등록되지 않은 원천」으로 거부한다.

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
Provider 구현        ✔  OpenDART · ECOS · KOSIS · 공공데이터포털(KPX SMP) 4개
fixture 검증         ✔  677건 · 네트워크 0회
실제 API 실측        ✘  AFS_OPENDART_API_KEY 가 없다
실제 데이터 수집      ✘
격리 DB 적재         ✔  data_acquisition_rows · 전부 UNCERTIFIED
운영 적용            ✘  Snapshot 인증 · 업무키트 결속 · 준비도 재평가
자동갱신 활성화       ✔  운영 스케줄러 진입점 + 자동적용 관문 6개
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

## 4-2. 정기 갱신 — 자동 적용을 어떻게 안전하게 하나

정기 갱신이 **매번 사람 승인**을 요구하면 일별 환율은 실무에서 못 쓴다. 그렇다고 **무조건
적용**하면 사람 관문이 무의미해진다. 그래서 「처음 승인한 것과 같은 모양일 때만」 적용한다.

    ① 자동 적용이 켜져 있는가        기본 꺼짐 · 켜는 것 자체가 원장에 남는 결정
    ② 원천·계약이 처음 그대로인가
    ③ 계약이 여전히 승인 상태인가
    ④ 계약 성격과 원천 성격이 맞는가   적용 직전과 **같은 판정자**를 쓴다
    ⑤ 품질 검사를 통과했는가
    ⑥ 원천의 필드 구성이 그대로인가

⚠️⚠️ **⑥ 을 처음에 장식으로 만들었다.** 정규화된 행을 계약과 대조했는데, 명시적 변환기가
  새 열을 애초에 버리므로 **원천이 바뀌어도 아무 차이가 없었다.** 원천에 `NEW_COLUMN` 을
  넣은 시험이 그대로 통과해 잡혔다.
  → `NormalizedBatch.source_fields` 에 **원문이 준 필드 이름들**을 담고, 적용 때 그것을
    체크포인트에 적어 다음 갱신이 비교한다. 열이 **사라지는 것**도 변경으로 본다.

실행은 `scripts/run_acquisition_refresh.py` 를 **운영 스케줄러가** 부른다. 프로세스 안에
타이머를 두면 웹 서버가 4개 뜰 때 같은 수집이 4번 돈다. 겹쳐 돌면 파일 잠금으로 건너뛴다.

## 4-3. A(키트 편입)를 멈춘 이유 — **실물 데이터에 인증 경로가 없다**

### ⚠️ 앞 판의 이 절은 틀렸다 (2026-09-08 정정)

처음에 나는 이렇게 적었다: 「`DATA_KINDS` 가 둘뿐인데 공개 자료는 어느 쪽도 아니고,
`calc_execution_approval` 이 그 값으로 **경영 계산 승인을 가른다**. 넓히려면 113곳을
건드려야 하니 거버넌스 결정이 먼저다.」

**세 군데가 틀렸다.**

    ✘ `calc_execution_approval` 은 `data_kind` 로 막지 않는다.
      승인 **지문의 구성요소이자 기록 표시**다 — 코드에 그렇게 적혀 있다
      (`calculation_control.py:402` 「조회 키가 아니라 기록 표시다」).
    ✘ `DATA_KINDS` 를 넓힐 필요가 없다. 그 값의 뜻은 「시연이냐 실물이냐」이고,
      ECOS 관측값은 **실물**이니 `REAL` 이 맞다. 「우리 내부 실적이냐」는
      `data_origin`(PUBLIC_DISCLOSED)이 이미 답한다 — **축이 원래 둘이었다.**
    ✘ 그러므로 이것은 「공개 통계를 써도 되는가」라는 거버넌스 질문이 아니었다.

`data_kind` 가 실제로 막는 곳은 한 군데다 — `baseline_build.py:113`,
**한 기준선에 성격이 다른 판을 섞지 못한다.** 그것은 옳은 제약이고 그대로 두면 된다.

### 진짜 이유 — 이쪽이 훨씬 크다

    SNAPSHOT_STATES  RAW → PROFILED → STANDARDIZED → RECONCILED → DEMO_CERTIFIED
                                                                   ↑ 유일한 종착
    latest_certified  DEMO_CERTIFIED 만 인정한다
    READY             인증판을 요구한다
    certify_demo      data_kind != DEMO 이면 **거부한다**

★★★ **실물 데이터는 오늘 어떤 경로로도 `READY` 가 될 수 없다.** 공개 통계만이 아니라
  회사의 진짜 매출 데이터도 똑같이 막힌다.

그리고 이것은 **의도된 경계**다. `snapshot_service.certify_demo` 가 직접 적어 뒀다:

> 시연 인증. **`CERTIFIED ACTUAL` 이 아니다.**
> 실제 Data Owner 가 없는 상태에서 실적 인증을 주장하면, 그 숫자를 본 사람은 검증된
> 값이라고 믿는다. 그래서 상태 이름 자체가 `DEMO_CERTIFIED` 다.

### 외생 지표에는 그 Data Owner 가 **이미 있다**

「실제 Data Owner 승인」이 없다는 것은 **내부 데이터**의 이야기다. 우리 매출에는 「이것이
우리 숫자다」라고 말할 사람이 필요하다. 그러나 **환율의 소유자는 한국은행**이고, 그에
해당하는 승인 흐름은 이 저장소에 이미 있다.

    approve_source()      「이 출처의 값을 회사 계획에 쓴다」 + **승인자 필수**
    PURPOSE_MIN_GRADE     용도별 최소 등급 — 미달이면 **값을 아예 주지 않는다**
                          (경고가 아니다 — `resolve_value` 가 `value=None` 을 준다)

★ 그리고 그 차단기는 **실제로 배선돼 있다** — `outlook_series.py:78` ·
  `planning_drivers.py:270` · `external_control.py:465` 세 곳이 부른다.
  (「검사기는 있는데 부르는 곳이 0곳」이 아니다.)

### 그래서 남은 일의 모양이 바뀐다

「거버넌스 결정을 받는다」가 아니라 **「두 승인 개념을 잇는다」** 다:

    ① 외생 지표 계약(EXT-01/02/03)의 인증 권한을 **원천 승인 + 등급 정책**으로 삼는다
       → `DEMO_CERTIFIED` 옆에 `SOURCE_CERTIFIED`(가칭) 종착을 두거나,
         `latest_certified` 가 그 경로를 함께 인정하게 한다
    ② 내부 실적 계약(FIN·MFG·SLS·PRC)은 **손대지 않는다** — 실제 Data Owner 승인 흐름이
       생길 때까지 `DEMO_CERTIFIED` 만 있는 것이 맞다
    ③ 기준선 혼합 금지는 그대로 둔다 — 시연 생산실적과 실제 환율이 한 손익에 섞이면
       그 결과의 성격을 말할 수 없다

⚠️ ①은 **스냅샷 상태 목록을 건드린다**(`data_preparation` 소유). 이 브랜치에서 단독으로
  하지 않고, 담당 레인과 합의한 뒤에 한다.

★ 설계가 비워 둔 자리도 그대로다: `models.PROVIDER_CONNECTOR_QUERY` 가 선언돼 있고
  `source_binding.validate_config` 가 「계약과 화면 자리만 있고 아직 지원하지 않습니다」
  라고 명시한다.

### 그럼에도 사람에게 물어야 할 것 (하나로 줄었다)

    ★ 실제 회사용 키트(REAL 모드)의 EXT-01 환율을 ECOS 매매기준율로 채울지,
      회사 시스템의 실제 체결환율로 채울지, 둘을 구분해 둘지 (§4-1)
      — 회계·재무 담당의 판단이고, **그 키트를 만들 때** 물으면 된다.

## 4-4. 그 대신 한 것 — 지시의 앞 절반

> 「업무키트가 요구하는 데이터가 부족할 때 **부족한 자료를 찾고 수집 계획을 제안**한다」

`core/external_intelligence/readiness_bridge.py` — 준비도 결과에 **제안만** 얹는다.

    NOT_CONFIGURED · SOURCE_CONFIGURED  → 채울 수 있는 원천과 그 한계를 제시
    이미 수집돼 있으면                    → 건수 + **남은 단계를 이름으로**
    채울 원천이 없으면                    → 「등록되지 않았습니다」(빈 목록만 주지 않는다)
    QUALITY_FAILED · RECONCILIATION_FAILED → **제안하지 않는다**(원인을 덮는다)

★★★ 준비도 상태를 바꾸지 않는다. `PUB-01` 은 40행이 수집돼 있어도 여전히
  `NOT_CONFIGURED` 다 — 받아 온 것과 인증되어 결속된 것은 다르고, **그 차이가 이 시스템의
  전부다.**

## 4-5. 세 번째 Provider(KOSIS) — 셋이 「자료 없음」을 서로 다르게 말한다

    DART   {"status": "013"}                 코드
    ECOS   {"RESULT": {"CODE": "INFO-200"}}   코드(단, HTTP 200 으로)
    KOSIS  []                                 ★ **빈 배열 — 코드가 아니라 «모양»**

★★★ 코드 표만 보는 판정기는 KOSIS 의 「자료 없음」을 놓치고 **0건을 적재 성공으로 읽는다.**
  `load_rows` 가 모양을 명시적으로 가른다. 시험이 **DART·ECOS 응답을 이 파서에 넣어
  통과하지 않는지** 센다.

### 분류축 — 앞의 둘에 없던 축

한 통계표에 「제조업 생산지수」와 「광업 생산지수」가 같이 있다. 축을 무시하면 **서로 다른
계열이 한 지표로 뭉친다.** 축이 다른 행은 사유와 함께 버리고, 검증에 「분류축 단일」을 두고,
**업무 키에 축을 넣는다**(빼면 두 계열이 같은 키가 되어 하나가 다른 하나를 덮어쓴다).
축 코드는 상수로 박지 않고 첫 응답에서 확인한다 — 통계청이 분류를 개편한다.

### ⚠️ EXT-03 에 `vintage_date` 가 없었다

키트의 `EXT-03` 은 형제 계약(`EXT-01`·`EXT-02`)과 달리 그 열이 **빠져 있다.** 시연 자료
에서는 티가 안 나지만 공표 통계는 정정 공표가 있어서, 그 열 없이는 「그 계획이 당시 어떤
값을 썼는가」를 재현할 수 없다(§12.5). `ext03_public_proposal()` 이 더한다.

★ **둘째는 코드의 어긋남을, 셋째는 계약의 결손을 드러냈다.**

### ⚠️⚠️ 「항상 실패하는 검사」를 만들었다

KOSIS 오류 코드 표를 실측으로 확인하지 못해 그 사실을 알리려고 검증 항목을 `ok=False` 로
뒀더니 — **정상 자료가 매번 격리되고 자동 적용이 영원히 막혔다.**

★ 항상 걸리는 검사는 아무도 안 보게 되거나 영구 차단기가 된다. 둘 다 나쁘다. 코드표
  미확인은 **품질 문제가 아니라 주의사항**이고, 실제 위험(모르는 코드를 성공으로 읽는 것)은
  파서가 이미 막는다 — 표에 없는 코드는 `TRANSPORT` 로 떨어진다.

⚠️ `ERROR_TABLE_VERIFIED = False` 를 **코드·원천 카드·검증 보고서 세 곳**에 남겼다.
  실제 키로 한 번 돌린 뒤 표를 갱신할 것.

## 4-6. 네 번째 원천(공공데이터포털) — 포털 하나가 «여러 원천»이다

앞의 셋은 「기관 하나 = Provider 하나」였다. 공공데이터포털은 아니다. 포털은 창구일 뿐,
그 뒤에 전력거래소·기상청·관세청이 서로 다른 서비스로 앉아 있다.

★★★ **신뢰등급은 Provider 당 하나다.** `ProviderDescriptor.default_trust_grade` 는 필드가
  하나뿐인데, 설계서 §4.2 는 **KPX 를 Silver** 로 두고 ECOS·KOSIS 는 Gold 로 둔다. 포털
  전체를 Provider 하나로 만들면 이 구분이 사라져, 기상청 관측이 KPX 와 같은 등급으로
  읽힌다. 그래서 이렇게 갈랐다:

    DataGoKrService   기반 — 봉투 해석·인증·오류 방언.  ★ **등록부에 넣지 않는다**
    KpxSmpProvider    서비스 — 전력거래소 SMP · silver · EXT-03

  다음 서비스(기상청·관세청)는 `DataGoKrService` 를 상속해 엔드포인트·필드표·등급만
  적으면 된다.
  ⚠️ 기반 클래스를 등록부에 올리지 말 것. 올리면 「어느 서비스인지 모르는 원천」이 화면에
    뜨고, 등급이 정해지지 않은 값이 계약으로 들어간다.

### ⚠️ 선언만 해 두고 아무도 안 읽던 필드 — 페이징

`FetchResult.has_more` · `next_cursor` 는 `base.py` 에 **첫날부터 있었지만 읽는 곳이
0곳이었다.** 앞의 세 원천이 한 번에 다 주는 응답이었기 때문이다. 넷째가 처음으로 나눠
줬고, 그제서야 이 필드가 장식이었음이 드러났다.

`_collect()` 는 Provider 가 아니라 **오케스트레이터**에 뒀다 — 쪽을 어떻게 이어 붙이든
원문 보관·거부 집계 규칙은 모든 Provider 에 같아야 하기 때문이다.

    쪽마다 원문을 «따로» 보관한다      3쪽이면 체크섬 3개. 합쳐 보관하면 재현이 깨진다
    정규화 결과만 합친다               행은 이어 붙이되 원문은 쪽 단위로 남는다
    MAX_COLLECT_PAGES = 50            서버가 has_more 를 계속 참으로 줘도 멈춘다
    fetch(page=n) 을 모르는 Provider   TypeError 를 잡아 1쪽만 받는다 (앞의 셋이 그렇다)

### ⚠️ 거부 사유에 쪽 번호를 넣었다가 어휘를 오염시켰다

거부 행의 `reason` 앞에 `"1쪽: "` 을 붙였더니 사유를 비교하던 시험들이 깨졌다. `reason`
은 **닫힌 어휘**이고 화면·통계가 그것으로 묶는다. 쪽 번호는 사람이 읽는 `detail` 로 옮겼다.

### 네 번째 「자료 없음」 방언 — 그리고 오류가 봉투 «둘»로 온다

    DART   status=013             코드
    ECOS   RESULT.CODE=INFO-200   코드 (단, HTTP 200 으로)
    KOSIS  []                     모양
    포털   resultCode=03          코드 — 단, **봉투가 둘이다**

★ 인증·한도 실패는 `OpenAPI_ServiceResponse.cmmMsgHeader` 로 오고, 그 밖은
  `response.header.resultCode` 로 온다. 봉투 하나만 보는 판정기는 키 오류를 「알 수 없는
  응답」으로 읽는다. `read_envelope()` 가 둘을 다 본다.

★ **1건이면 `item` 이 배열이 아니라 객체다** (XML→JSON 변환의 흔적). 한 건짜리 응답을
  0건으로 읽는 결함이라 fixture 를 따로 뒀다(`single_item.json`).

### ⚠️ 자격 실패가 너무 늦게 나왔다

`discover()` 는 순수 함수라 키를 보지 않았다. 그래서 키가 없어도 「후보」가 나오고
dry-run 에 가서야 인증 오류가 났다 — 사람이 세 화면 뒤에서 처음 안다. `discover()` 에
`self.credential()` 을 넣어 **첫 화면에서** 말하게 했다.

### fixture 로 종단까지 확인한 것

    3쪽 · 25행 · 원문 3개(체크섬 3개 각각 검증)
    3쪽에 있던 값을 계보 질의로 되찾음 — 그 값의 trust_grade == "silver" (앞의 둘은 gold)
    보관된 메타데이터·URL 에 서비스키 문자열 없음 (퍼센트 인코딩된 형태까지 확인)

### 실측으로 확인하지 못한 것

`SERVICE_VERIFIED = False` — 서비스키 없이 만들었다. 엔드포인트 경로와 필드명은 포털
문서 기준이고 **실응답과 대조하지 않았다.** §7-B 에서 키를 받으면 이 상수를 지운다.

## 4-7. 다섯째(World Bank)는 «착수 전 조사까지만» 했다 — 그런데 그 조사가 다섯 개를 찾았다

⚠️ **코드는 한 줄도 없다.** 사람이 중지를 지시해 파서를 쓰기 전에 멈췄다. 아래는 **버리면
안 되는 조사 결과**다 — 다음 사람이 이것을 다시 파헤치지 않도록 남긴다.

### ① 다섯째는 앞의 넷과 «범주»가 다르다 — 처음으로 API 가 아니다

설계서 §4.2 의 등록 내용:

    SRC_WB_PINK_SHEET | 월별 국제 원자재 가격 | Gold 또는 Silver | 공식 XLS 다운로드

앞의 넷(DART·ECOS·KOSIS·공공데이터포털)은 전부 JSON API 였다. 이것은 **공식 파일**이고,
지시 3 의 우선순위(공식 API > **공식 파일** > 계약 Provider > RSS·공시 > 웹)에서 아무도
밟지 않은 두 번째 층이다. 그래서 이 Provider 가 처음으로 하게 될 것 셋:

    ① 자격증명이 «필요 없다» (requires_credential=False) — 비밀 없는 경로가 처음이다
    ② 응답이 «바이너리»다 (xlsx = zip)
    ③ 응답에 «요청한 구간이 없다» — 파일은 늘 1960년부터 전부 온다

③ 때문에 구간 선택이 URL 이 아니라 `dataset_ref` 에 실려야 한다(KOSIS 의 관례).

### ②★★★ 기존 우선순위 표가 지시 3 과 «어긋난다»

    기존   _SOURCE_PRIORITY = {API:1, CSV:2, RSS:3, PROVIDER_API:4, REPORT:5, WEB:6}
    지시3  공식API > 공식파일 > 계약Provider > RSS·공시 > 웹

지시 3 은 **계약 Provider 를 RSS 위**에 두는데, 표는 **아래**에 둔다(RSS:3 < PROVIDER_API:4).
둘 중 하나가 틀렸다.

⚠️ **내가 고치지 않았다.** 이 표는 `core/external_intelligence/__init__.py:48` 에 있고
  원천 등록 시점에 DB 열로 저장된다(같은 파일 229행) — 즉 다른 레인의 것이고, 상수를
  바꿔도 **이미 등록된 행은 안 바뀐다.** 순서를 바꾸려면 마이그레이션이 함께 가야 한다.
  → external_intelligence 레인과 합의할 것.

★ 다행히 이번 원천은 「공식 파일」이라 **양쪽에서 똑같이 2위**다. 그래서 이 어긋남이
  다섯째 Provider 를 막지는 않는다.

### ③ 닫힌 목록에 「공식 파일」을 가리킬 말이 없다

    SOURCE_TYPES = ("API", "CSV", "RSS", "WEB", "REPORT", "PROVIDER_API")

실제 형식은 **xlsx** 인데 목록에 없다. `CSV` 를 써야 하는데, 그러면 사람이 보는 원천
카드에 「CSV」라고 뜨면서 실제로는 xlsx 를 받는다 — 작은 거짓말이다.

★ 그래도 `CSV` 가 맞는 선택이다. 코드가 이 값을 쓰는 곳은 `_SOURCE_PRIORITY` 조회 하나뿐이고
  거기서 `CSV`=2 가 정확히 「공식 파일」 자리다. 어휘를 늘리는 것(`FILE` 추가)은 이 닫힌
  목록을 공유하는 레인의 결정이라 여기서 하지 않는다 — ②와 같은 곳에 얹어 물을 것.

### ④ 등급 `silver` 는 «설계서에서 유도된다» — 취향이 아니다

설계서 §4.2 는 등급을 「Gold 또는 Silver」로 **정하지 않고** 뒀다. 그런데 같은 줄에
용도 제약을 적었다: 「실구매 단가를 대체하지 않는다. 국제 기준 가격·**시나리오 동인**으로
쓴다.」 그리고 기존 정책이 정확히 그 경계다:

    PURPOSE_MIN_GRADE = {baseline_plan: gold, official_report: gold,   ← 막힌다
                         scenario: silver, review: silver,             ← 열린다
                         detection: bronze}

즉 **설계서가 쓴 문장이 `silver` 로 이미 표현돼 있다.** gold 로 두면 그 문장이 코드에서
사라진다. → `default_trust_grade="silver"`.

### ⑤ 원문 보관소가 xlsx 를 `.bin` 으로 저장한다

`raw_store._EXT_BY_TYPE` 에 json·xml·csv·txt·html 만 있고 xlsx 가 없어 `.bin` 으로
떨어진다. 내용주소·체크섬·재현에는 **문제가 없다** — 사람이 보관된 원문을 열어 보려 할 때
확장자가 없어 불편할 뿐이다. 한 줄 추가하면 된다:

    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx"

### 배관은 이미 된다 (확인함)

    https_get      response.read() 로 bytes 를 그대로 준다 — 바이너리 가능
    MAX_RESPONSE_BYTES = 32MB   Pink Sheet(약 1MB) 는 여유
    raw_store.put  "wb" 로 쓴다 — 바이너리 가능
    openpyxl 3.1.5 venv 에 있다

### ⚠️⚠️ 다음 사람에게 — 이 원천의 진짜 위험

**레이아웃을 실제 파일로 확인할 수 없다.** 네트워크를 쓰지 않았고 실제 워크북이 없다.
Pink Sheet 는 머리 구역이 여러 행(제목·품목명·단위·코드)이고 결측이 `..` 다.

★★★ 그래서 파서를 쓸 때 **행·열 번호를 박지 말 것.** 전부 내용으로 찾아야 한다:

    자료 시작 행   A열이 `1960M01` 모양인 «첫 행»
    품목 열       머리 구역에서 품목 이름이 적힌 칸 → 그 열
    단위          그 열의, 품목 이름 아래·자료 시작 위의 `(...)` 칸

★★★ 그리고 **품목 이름을 못 찾으면 «다른 열을 읽지 말고 실패»할 것.** 넘겨짚으면 구리
  자리에서 알루미늄 가격을 읽고도 아무도 모른다 — 이 저장소에서 「엉뚱한 회사의 DART
  응답을 조용히 적재」한 사고가 실제로 있었다(§5).
  이름 비교는 «정확히 같거나 뒤에 쉼표»만 — 부분 일치를 허용하면 `Lead` 가
  `Leaded gasoline` 을 잡는다.

★ 업무 키에 **가격기준(가격판/지수판)이 들어가야 한다.** 워크북에 `Monthly Prices` 와
  `Monthly Indices` 가 함께 있어서, 축을 빼면 `$/mt` 와 `2010=100` 이 같은 키가 된다 —
  KOSIS 분류축과 같은 교훈이다.

⚠️ 문서 URL 에 **회전하는 해시**가 들어 있어 박아 두면 언젠가 404 가 된다. 환경변수
  덮어쓰기를 두되 `allowed_hosts` 로 호스트는 고정할 것(그러면 임의 URL 이 되지 않는다).

⚠️ 과거 값이 **소급 정정**된다. 같은 업무 키로 다시 오면 중복으로 거부된다 — EXT-01 과
  같은 성질이고, 반영은 사람이 판단한다.

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
| **0** | **T3 재실행** — 아래 §8 의 6,282 는 `432055636` 이전이다 |
| **A** | `PUB-01` 편입 → 준비도 재평가. ⚠️ **실물 인증 경로가 없다** — §4-3 (거버넌스가 아니라 배선 문제) |
| **B** | 실제 `AFS_OPENDART_API_KEY` 로 1회 실측 (한도 주의 — 10개년 × 4분기 한 번에 받지 말 것) |
| **C** | World Bank Provider 추가 — **착수 전 조사만 끝났다(§4-7). 코드 0줄.** 설계 결정 5개는 §4-7 에 확정해 뒀다 |
| **G** | ⚠️ 기존 `_SOURCE_PRIORITY` 가 지시 3 과 순서가 어긋난다 · 닫힌 목록에 「공식 파일」이 없다 — external_intelligence 레인과 합의 (§4-7 ②③) |
| ~~D~~ | ~~스케줄러 배선~~ — 완료(`scripts/run_acquisition_refresh.py`) |
| **E** | 화면 렌더 확인 — 로그인 뒤라 이번에 눈으로 보지 못했다 |
| **F** | `sim_marketing` 도메인 내용 업무 검토 (이전 묶음에서 이월) |

⚠️ **C 를 할 때**: `normalize()` 의 기본 구현을 만들지 말 것. 기반 클래스가 일부러 주지
않는다 — 주면 새 Provider 가 물려받아 「대충 돌아가는」 상태가 되고, 그 파서는 OpenDART
응답도 KOSIS 응답도 통과시키되 뜻은 다르게 읽는다(지시 4).

## 8. 검증 기록

```
전체 스위트 T3   6,282 passed · 2 skipped · 실패 0         992초 (16:31) · 커밋 7a782aa3e
                 ⚠️ **최신이 아니다** — 그 뒤 커밋 2개가 들어왔다(아래 이력)
수집·준비도 회귀  677건 통과 (67초) · 네트워크 0회 · LLM 0회   ← 최신 `432055636` 에서
tsc -b           0건
프로덕션 빌드     성공 · 패널 문구·경로 상수가 번들에 실림 확인
제품 경로 실측    없는 경로 404 · 수집 라우트 4개 401
```

### 「수집·준비도 회귀 677건」의 선택 집합 — 그대로 다시 돌릴 수 있게

⚠️ 중괄호 확장을 쓰지 않았다 — 팀 기본 셸이 PowerShell 이고 거기서는 확장되지 않는다.
   아래는 bash·PowerShell 어디에 붙여넣어도 같게 돈다(한 줄).

    venv/Scripts/python.exe -m pytest -p no:randomly tests/test_acquisition_api.py tests/test_acquisition_mapping.py tests/test_acquisition_models.py tests/test_acquisition_orchestrator.py tests/test_acquisition_store.py tests/test_external_raw_store.py tests/test_request_interpreter.py tests/test_provider_contract.py tests/test_provider_datagokr.py tests/test_provider_dispatch.py tests/test_provider_ecos.py tests/test_provider_kosis.py tests/test_provider_opendart.py tests/test_refresh_runner.py tests/test_readiness_bridge.py tests/test_data_readiness.py tests/test_source_binding.py tests/test_dataset_snapshot.py tests/test_release_readiness.py tests/test_decision_source_binding.py

⚠️ 앞선 커밋들의 「594건」·「579건」과 이 677건은 **선택이 다르다** — 서로 빼서 증감을
계산하지 말 것. 위 목록이 지금부터의 기준이다.
⚠️ pytest 를 동시에 두 개 돌리지 말 것. 이 저장소에서 경합으로 3시간짜리 실행이 나왔고
멈춘 줄 알았다(실제로는 단독 실행 시 67초).

**정산이 맞는다.**

    수집 6,284 = 통과 6,282 + 건너뜀 2
    직전 6,176 + 스케줄러 30 + 수집제안 27 + KOSIS 51 = 6,284

⚠️ 이 대조를 하는 이유: 끝까지 자르는 편집이 시험을 조용히 지워도 「전부 통과」는 그대로
나온다 — 이 저장소에서 회귀 21건이 사라진 채 초록이었던 적이 있다.

### 이 브랜치의 T3 이력

    6,098   4862927b3 이전   기준선 5,793 + 수집 오케스트레이터 305
    6,174   4862927b3        + ECOS 76
    6,282   7a782aa3e        + 스케줄러 30 · 수집제안 27 · KOSIS 51
    (미실시) 744c62373       + Codex 업무키트 시작안내·초기데이터 대사
    (미실시) 432055636       + 공공데이터포털 36     ← **T3 가 아직 안 본 구간**

⚠️ **화면이 그려지는 것은 보지 못했다.** 앱이 로그인 뒤에 있고 대리 로그인을 하지 않았다.
「배선됐다」까지만 주장한다 — §7-E 가 남은 일이다.

⚠️ **이 T3 는 브랜치 `claude/data-acquisition-orchestrator-20260905` 의 것이다.** 기점
`1bdada5a1`(Codex 기준선) 위에서 돌렸고, 다른 브랜치의 미커밋 작업은 포함하지 않는다.

⚠️ **이 T3 는 더 이상 최신이 아니다.** 돌릴 당시에는 최신이었고 그 뒤 코드를 건드리지
  않았지만, 이후 커밋 2개(`744c62373` · `432055636`)가 들어왔다 — §7-0 이 남은 일이다.
  그 구간은 **집중 회귀 677건**으로만 확인했다.

★ **앞선 T3 들의 교훈은 그대로 둔다.**
  앞선 두 번은 T3 가 도는 동안 작업을 이어가 결과가 「직전 시점의 것」이 됐다 — 이번에는
  T3 가 끝날 때까지 코드를 손대지 않았다.
  ⚠️ 다음 커밋이 들어오면 이 줄을 다시 갱신할 것. 「거의 최신」인 검증 기록을 최신처럼
    두면 그 줄만 읽는 사람이 속는다.

## 9. 금지 범위 (이번에도 지켰다)

- ~~push 하지 않았다~~ → **2026-09-08 사람이 명시적으로 푸시를 지시해 푸시했다.**
  ⚠️ 지시 14 의 「push 하지 않는다」는 **사람이 직접 뒤집었다** — 내 판단이 아니다.
  브랜치 `claude/data-acquisition-orchestrator-20260905` 로만 갔고 `main` 은 건드리지 않았다.
- 임의 URL 수집 없음 — 등록된 `allowed_hosts` 밖으로 한 번도 나가지 않는다
- LLM 이 만든 코드를 운영 프로세스에서 실행하지 않았다
- 운영 DB 직접 SQL 쓰기 없음 — 격리 `data_acquisition_rows` 만 쓴다
- 공개자료를 내부 `REAL` 로 표기하지 않았다 (관문이 거부한다)
- 비밀키를 커밋하지 않았다 — `.env.example` 에 **이름만** 추가
