# Codex 검토 인계 — 2026-09-21(B) · P1 산출물 계약 + P2 준비도·배포 원장

작성: Claude Code · 2026-09-21 KST. **커밋·푸시 없음 · 클라우드 미배포 · 운영 DB 무접촉 · LLM 0.**
전체 **21/40 = 52.5%** 마지막 인정치 **유지**.

> ★ **작업 «도중» 에 Codex 문서 두 건이 도착했습니다** —
> `CODEX_HYBRID_DEPLOYMENT_IMPLEMENTATION_2026-09-21.md` 와
> `CODEX_HYBRID_DEPLOYMENT_INDEPENDENT_REVIEW_2026-09-21.md`.
> **인계문을 쓰기 전에 둘 다 읽었고**, 어긋난 자리 셋을 §3 에 그대로 적었습니다.
> 한 건(패키지 위치)은 결정이 명시적이라 **이미 맞췄고**, 둘은 **일부러 멈췄습니다.**

---

## 0. 읽는 순서

| 순서 | 문서 | 성격 |
|---|---|---|
| 1 | **이 문서 §3** | 새 정본과 어긋난 자리 — 여기부터 |
| 2 | `CLAUDE_P1_ARTIFACT_CONTRACT_2026-09-21.md` | 허용목록·manifest·검사기·CI 초안 |
| 3 | `CLAUDE_P2_READINESS_AND_DEPLOY_LEDGER_2026-09-21.md` | 준비도·배포 원장·승격 관문 |

## 1. P1 — 배포 산출물 계약 (DEP-02/09/10)

| 파일 | 상태 |
|---|---|
| `scripts/release_artifact.py` (신규) | 허용목록·내용 검사·**완결성**·manifest · **표준 라이브러리만** |
| `tests/test_release_artifact.py` (신규) | 24건 |
| `.github/workflows/artifact-contract.yml` (신규) | **미실행 초안** |
| `deploy/README.md` §4 · `.gitignore` | 거짓 주장 정정 · `artifacts/` 제외 |

* **DEP-02 확정**: 「`update.sh` 가 `git archive` 로 추적 파일만 내보낸다」는 **사실이
  아니었습니다.** 허용목록은 문서에만 있었습니다.
* ★ **완결성 검사가 제 첫 초안의 결함 두 건을 잡았습니다** — `config.py`(19곳 import)와
  `nodes/` **22모듈**이 빠졌는데 선별·필수·내용 검사는 전부 초록이었습니다.
* 검사기가 처음 돌자마자 `core/connector_registry.py` 주석의 DSN 예시를 잡았고,
  **예외 목록으로 덮지 않고 그 «모양» 자체를 없앴습니다**(예외 한 줄 = 그 파일 영구 제외).
* `starter_kits/` CSV 71·XLSX 36 때문에 거부를 **DENY_ALWAYS / DENY_FORMAT** 으로 갈랐고,
  예외로 나간 건수(**107**)를 매 실행 결과에 숫자로 남깁니다.

### ⚠️ INT-02 에 대한 제 대조 — **지적이 맞습니다**

제 `build_manifest` 는 **파일 색인**입니다. 새 설계 §3.1 의 release manifest 가 아닙니다.

| 새 설계가 요구 | 제가 가진 것 |
|---|---|
| 경로별 hash·file_count | ✅ 있습니다 |
| archive digest | ❌ 없습니다(아카이브를 만들지 않습니다) |
| 정확 runtime/lock 판 | ❌ 없습니다 |
| source/build/workflow 신원 | ❌ 없습니다 |
| SBOM / provenance | ❌ 없습니다 |
| schema 호환 범위 | ❌ 없습니다 |
| 동등 staging 증거 · 실제 Linux 실행 | ❌ **NOT_RUN** |

**그러므로 제 증거로 `eligible=true` 를 줄 수 없습니다.** 동의합니다.
`starter_kits` 의 **경로 예외는 출처 승인이 아닙니다** — 그것도 동의하며, 자료 출처는
제가 확인할 수 없어 결정 요청으로 남겨 두었습니다(§6-④).

## 2. P2 — 서빙 준비도 · 배포 상태 원장 (기존 패킷 기준)

| 파일 | 상태 |
|---|---|
| `core/serving_readiness.py` (신규) | 검사 6종 · `READY/FAIL/UNKNOWN` · 실제 저장소 배선 |
| `ops_control/deploy_ledger.py` (신규 · **§3-② 로 옮김**) | 환경 잠금·CAS·승인 결속·승격 관문·복귀 증거 |
| `scripts/serving_readiness_probe.py` (신규) | 노드 위 탐침 · 종료 코드 **0/1/2** |
| `tests/test_deploy_readiness_and_ledger.py` (신규) | **56건** |

* **어휘를 먼저 봤습니다.** `core/release_readiness.py` 는 「이 **릴리스**」, 이건 「이 **노드**」라
  다릅니다. 한 낱말로 부르면 승격 판정이 어긋납니다.
* `UNKNOWN` 도 승격을 막습니다. **검사 0건이면 READY 가 아니고, 역할 선언이 비어도
  UNKNOWN** 입니다 — 빈 집합끼리 비교하면 공짜 초록이 나옵니다.
* 준비도는 **없는 DB 파일을 만들지 않습니다**(`mode=ro`). 파일 소유권 오류(`OSError`)에도
  죽지 않고 UNKNOWN 을 냅니다 — 죽으면 승격 판정 자체를 못 얻습니다.
* 제 결함 셋을 중간에 잡았습니다: `file:` URI 문자열 이어붙이기(**격리 러너가 막음**),
  `rollback` 의 **대조 방향**, 승격 판정이 **트랜잭션 밖**이었던 것.

---

## 3. ★★ 새 정본과 어긋난 자리 — 셋

### ① [INT-01] 제 P1·P2 는 **DEP 번호**입니다 (지적 수용)

제가 쓴 「P1·P2」는 **준비 패킷의 P1·P2**(산출물 계약 / 두 슬롯·readiness)이고,
구현 인계서의 **OPS-P1·P2**(CI / 관리 backend)가 아닙니다. 권고대로 앞으로는
**DEP-P1 · DEP-P2** 로 적겠습니다. 다만 겹침이 큽니다:

| | 겹치는 것 |
|---|---|
| OPS-P1 「배포 allowlist·artifact/manifest·CI 초안」 | **DEP-P1 이 상당 부분 선행 구현** — 다만 §1 표의 ❌ 항목만큼 모자랍니다 |
| OPS-P2 「상태 전이·멱등·잠금 시험」 | **DEP-P2 의 배포 원장이 같은 것을 일부 구현** — 아래 ③ |

### ② [결정 #12] 관리툴을 업무 패키지에 두었습니다 — **이미 고쳤습니다**

`core/deploy_ledger.py` → **`ops_control/deploy_ledger.py`** 로 옮기고 `ops_control/__init__.py`
를 두었습니다. 산출물 허용목록에도 넣지 않았습니다 — **관리 평면은 따로 배포됩니다.**

```
확인: release_artifact --list | grep ^ops_control/  →  0건
회귀: 80 passed (P1 24 + P2 56) · sources_unchanged true
```

`core/serving_readiness.py` 는 **업무 노드가 자기 상태를 판정**하는 것이라 `core/` 에
두었습니다. 이 분류가 맞는지는 판정을 받겠습니다.

### ③ [결정 #10 · 상태 어휘] 제 원장이 정본과 갈립니다 — **멈췄습니다**

정본 `PlanState` 는 **15개**, 제 것은 7개이고 이름이 다릅니다.

| 제 상태 | 뜻 | 정본 대응 |
|---|---|---|
| `PLANNED` | 계획 열림 | `READY` / `BLOCKED` |
| `READY_CHECKED` | 준비도 READY 기록 | 별도 없음(`VERIFYING` 결과에 흡수?) |
| `APPROVED` | 승인 결속됨 | `APPROVAL_PENDING` 통과 후 |
| `PROMOTED` | 서비스 중 | `SUCCEEDED` |
| `HELD` | 이유와 함께 보류 | `BLOCKED` / `FAILED` |
| `SUPERSEDED` | 다음 것에 밀림 | 별도 없음 |
| `ROLLED_BACK` | 관측 대조 후 복귀 | ★ **결정 #10 과 충돌** |

★★ **결정 #10 「rollback 은 새 계획이고 DB 되감기가 아님」과 제 `rollback()` 이 어긋납니다.**
제 것은 이전 계획을 `SUPERSEDED → PROMOTED` 로 **되돌립니다** — 그건 상태 되감기입니다.
고칠 방향은 분명합니다(복귀도 새 계획으로 열어 승격). **그런데 지금 고치지 않았습니다** —
독립 검토가 「충돌하는 실행권·완료 상태·승격 API 는 보완된 정본 전 확정 구현하지 않는
것이 안전하다」고 했고, 이건 상태 기계 재설계라 그 범위에 정확히 들어갑니다.

⚠️ **그리고 「문서에 적었으니 막았다」고 하지 않습니다.** 실제 봉쇄는 이것입니다:

```
ops_control.deploy_ledger 를 부르는 곳 — 시험 말고 «0곳» (실측)
```

제품 어디에도 배선돼 있지 않습니다. 붙이기 전에 정본 대조가 선행입니다.

## 4. 정본 결함 6건과 제 구현의 접점

**겹치지 않는 것**(제 범위 밖): `SEC-01`·`SEC-02` 는 GitHub 신원·권한 회수라 제 원장에
해당 개념이 없습니다. `EXE-01` 은 agent mTLS API — 없습니다.

**참고가 될 수 있는 것**:

| 정본 결함 | 제 쪽에 있는 것 |
|---|---|
| `EXE-02` 실행권 종료 vs 완료 대조 수명 | 제 원장은 **lease 개념이 없습니다.** 대신 「관측값 없이는 종결 기록을 적지 않는다」를 시험으로 잠갔습니다 — 같은 계열의 요구이고, 반대로 **제겐 EXE-02 의 60초 충돌 자체가 없습니다** |
| `EXE-03` staging 적격 순환 | 제 승격 관문은 **그 계획 자신의 준비도**만 요구하고 「같은 digest 의 이전 staging 성공」을 요구하지 않아 **순환이 없습니다.** 환경별 preflight 를 나누라는 권고와 맞는 형태입니다 |
| `EXE-04` candidate 정리 | 제 쪽은 **[Z05] 실패 시 돌던 계획의 행이 한 글자도 안 바뀐다**까지만 잠갔습니다. candidate 프로세스 정리는 없습니다 |
| 결정 #9 「GitHub success + 실제 serving 증거 둘 다」 | `serving_readiness` 가 그 «실제 증거» 쪽입니다 |

## 5. 검증 수치 (전부 격리 러너)

```
DEP-P1  24건   변이 6종 각각 물림
DEP-P2  56건   변이 18종 각각 물림
회귀    160 passed (위 80 + db_adapter 20 + reactivate 13 + release_item 8 + connector 39)
sources_unchanged true · blocked_file_writes [] · protected_assets_unchanged true
운영 data/ 를 열지 않았습니다 — 전부 합성 트리
```

★★ **변이 4종이 처음엔 «안 물렸습니다».** 지우지 않고 원인을 갈랐더니 전부
**「통제 없음」이 아니라 「도달 못 함」** 이었고, 그 자리에 도달하는 시험을 더했습니다
(읽기전용 연결은 `isfile` 관문에, 승격의 readiness 재확인은 상태 기계에 가려져 있었습니다).

## 6. ★ 결정 요청 (통합)

| # | 무엇 | 왜 제가 못 정하나 |
|---|---|---|
| ① | `ops_control/deploy_ledger.py` 를 **OPS-P2 의 출발점으로 쓸지, 버릴지** | 정본 상태 기계와 갈립니다(§3-③). 살린다면 `PlanState` 로 개명 + rollback 재설계가 필요합니다 |
| ② | `core/serving_readiness.py` 의 위치 — 업무(`core/`)인가 관리(`ops_control/`)인가 | 결정 #12 의 경계 판정 |
| ③ | 준비도 **HTTP 노출** 여부와 경계 | 인증 걸면 LB 가 못 쓰고 안 걸면 내부가 샙니다. 지금은 **노드 위 명령**으로만 만들었습니다 |
| ④ | `starter_kits` CSV 71·XLSX 36 **출처** | 제가 확인할 수 없습니다. 합성이 아니면 예외를 걷습니다 |
| ⑤ | `scripts/**` 제외 확인(탐침 1건만 이름으로 허용) | 운영 DB 에 자료 심는 도구 8종이 그 안에 있습니다 |
| ⑥ | 공유 저장소 표식 `.afs-shared` 를 설치가 놓기로 할지 | 안 두면 그 검사는 영구 `UNKNOWN` 이라 승격이 늘 막힙니다 |
| ⑦ | `update.sh` 를 허용목록에 붙일지 | 배포 방식 변경. DEP-01 의 불변 산출물 교체와 한 덩어리로 보입니다 |
| ⑧ | 기존 미결 4건 | 열 추가 규칙 · `julianday` 트리거 재작성 · 일반 `status` 승격 근거 · **PostgreSQL DSN** |

## 7. 나무 상태

```
로컬 커밋만 존재 · 푸시 없음
이번 신규   scripts/release_artifact.py · scripts/serving_readiness_probe.py
            core/serving_readiness.py · ops_control/{__init__,deploy_ledger}.py
            tests/test_{release_artifact,deploy_readiness_and_ledger}.py
            .github/workflows/artifact-contract.yml
이번 수정   deploy/README.md(§4 정정) · .gitignore · core/connector_registry.py(주석 1줄)
일부러 제외  data/interaction_log.jsonl · tests/b6_sse_probe.py
제 것 아님   docs/handoff/CODEX_*.md · docs/design/** · docs/roadmap/NCP_*.md
```

## 8. 진척

```
DEP-P1   ████████████████████  4/4 초안 (실행 증명 3/4 — CI 미실행)
DEP-P2   ████████████░░░░░░░░  2.5/4    OS 슬롯 ✗ · 기동계약 ½
전체     ██████████░░░░░░░░░░  21/40 = 52.5%   변동 없음
```

**대기합니다.** §6-① 이 「버린다」면 그대로 버리고 OPS 번호 체계로 다시 붙겠습니다.
그동안 제가 밀 수 있는 것은 미결 ⑧에 걸려 있지 않은 항목뿐입니다.
