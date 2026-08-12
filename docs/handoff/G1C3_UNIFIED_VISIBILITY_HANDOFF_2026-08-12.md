# [G1-C3] 통합 가시성 판정기 — 인수인계

**작성 2026-08-12 · 상태: 판정기 완성 · 배선 미착수**

이 문서 하나만 읽고 이어받을 수 있게 적는다. 무엇을 왜 했고, **무엇이 아직 안 됐고**,
어디서부터 손대야 하는지.

---

## 1. 왜 이 작업이 필요한가

교차검증(Supervisor, 2026-08-12)에서 확인된 것:

> 프로젝트 목록은 **사용자·부서 권한만** 검사한다. `GET /projects` 는 선택 회사 문맥을 받지
> 않고, `assert_project_readable/writable` 도 테넌트·REAL/VIRTUAL·선택 조직을 보지 않는다.
> 반면 **SSE 는 그 문맥을 검사한다.**

그래서 지금 이런 상태가 가능하다.

```
목록에는 보이는데 SSE 이벤트는 안 온다
다른 회사 문맥의 프로젝트를 URL·API 로 직접 조회·변경할 수 있다
REAL 화면에 VIRTUAL/SANDBOX 프로젝트가 노출될 수 있다
```

그리고 더 나쁜 것 — **빈 값이 모든 문맥 검사를 통과**하고 있었다.

| 조건 | 종전 동작 | D-014 원칙 |
|---|---|---|
| 자원 `tenant_id` 가 빔 | 통과 | 비노출 |
| 자원 `entity_mode` 가 빔 | 통과 | 비노출 |
| 자원 `enterprise_scope_id` 가 빔 | `scope_covers()` 가 `True` | 비노출 |
| ECM 계층 판독 중 예외 | `True` | 비노출 + 점검 대상 |

즉 **「범위 미지정 = 전사 공용」** 이었고, 그것이 D-014 가 명시적으로 금지한 상태다.

---

## 2. 이번에 **끝낸 것** — 판정기와 그 테스트

`core/project_visibility.py` 에 두 축을 나누고 AND 로 묶는 정본 판정기를 넣었다.

```python
authorization_visible(scope, user_id, ownership)      # 축 ① 권한
context_visible(ctx, ownership) -> (bool, reason)     # 축 ② 지금 고른 문맥
project_visible(scope, user_id, ctx, ownership) -> (bool, reason)   # ① AND ②
```

### 왜 나누는가

둘을 한 함수에 섞으면 **어느 쪽 때문에 안 보이는지 말할 수 없다.** 화면은 «0건» 만 보여 주고,
사용자는 자료가 없는 것인지 권한이 없는 것인지 문맥이 어긋난 것인지 알 수 없다.
**사유를 함께 돌려주는 것이 이 설계의 요점이다.**

### 사유 값

| 값 | 뜻 | 화면이 해야 할 말 |
|---|---|---|
| `OK` | 보인다 | — |
| `UNAUTHORIZED` | 권한 축에서 막힘 | 404 · 접근 불가 |
| `TENANT_MISMATCH` | 다른 테넌트 | 다른 회사 문맥의 자료입니다 |
| `MODE_MISMATCH` | REAL/VIRTUAL/SANDBOX 불일치 | 실행 문맥이 다릅니다 |
| `SCOPE_OUTSIDE` | 고른 조직 밖 | 선택한 조직 범위 밖입니다 |
| `RESOURCE_UNBOUND` | 자원에 문맥이 없음 | **문맥 점검 필요**(0건 아님) |
| `CONTEXT_MISSING` | 요청에 문맥이 없음 | **문맥 점검 필요** |
| `LOOKUP_FAILED` | ECM 계층 조회 실패 | **조회 불가 · 문맥 점검 필요** |

### 규칙 (전부 fail-closed)

- 문맥의 테넌트·실행모드가 없으면 → `CONTEXT_MISSING`
- 자원의 테넌트·실행모드·범위 중 **하나라도** 비면 → `RESOURCE_UNBOUND`
- 고른 범위가 비면 **좁히지 않는다** — 같은 테넌트·같은 모드 안에서 권한이 닿는 전체
- 고른 범위가 있으면 자원이 **그 노드이거나 운영 계층상 하위**(`OPERATING_PARENT` 만 따름)
- ECM 조회 실패·순환·끊어진 참조 → `LOOKUP_FAILED`(비노출, 점검 대상)
- `visibility="company"` 는 전 세계 공개가 아니라 **같은 테넌트·같은 모드 안에서만** 공개
- **무제한 권한자도 문맥은 지킨다** — 「전권」과 「지금 보는 범위」는 다른 축이다

### 테스트

`tests/test_unified_visibility_judge.py` — 21건 통과.
문맥 표 11건 · 계층 상하/형제 · ECM 실패 · AND 결합 · 사유 4종이 서로 겹치지 않는지 ·
무제한 권한자도 테넌트를 넘지 못하는지.

⚠️ **변이 검사는 하지 못했다.** 착수했다가 중단됐고, 그 과정에서 `context_visible` 의
테넌트 검사 한 줄이 **실제로 삭제됐다가 복구**됐다(전체 테스트 0 실패로 확인). 이어받는
세션은 아래 「변이 검사」를 반드시 먼저 돌려라.

---

## 3. **아직 안 된 것** — 여기서부터 이어받는다

### 3.1 라우트·SSE 배선 (핵심)

판정기는 있는데 **아무도 부르지 않는다.** 지금 목록·상세·수정은 여전히 `_ownership_visible`
(권한 축만)을 쓴다. 다음을 전부 `project_visible` 로 갈아야 한다.

| 경로 | 현재 | 파일·위치 |
|---|---|---|
| 프로젝트 목록 | `_ownership_visible` | `api/routes/factory_control.py:202`, `:479` |
| 상세·상태·WBS·피드 | 권한만 | `factory_control` 의 각 라우트 |
| 수정·삭제·스프린트 실행 | 권한만 | 같음 |
| 릴리스·내보내기 | 권한만 | `factory_control` 릴리스 라우트 |
| SSE 배달 | `ownership_visible` + 별도 문맥 비교 | `core/broadcaster.py` `_may_receive` |

⚠️⚠️ **문맥 범위는 부서 코드로 들어온다.** `api/deps.current_enterprise_context` 는
`primary_dept_id` 를 fallback 으로 쓰는데(예: `procurement`), 자원은 노드 id
(`node_a50a1553d4d3`)를 갖는다. **정규화 없이 비교하면 전부 `SCOPE_OUTSIDE` 가 된다.**

정본 정규화 지점이 이미 있다 — 새로 만들지 마라:

```
api/deps.assert_scope_allowed(p, requested, resource_type=..., tenant_id=..., entity_mode=...)
core/scope_guard.resolve_effective_scope(p, requested, tenant_id, entity_mode) -> EffectiveScope
```

`EffectiveScope.scope_node_id` 가 정규화된 값이고, **그 사용자가 고를 수 있는 범위인지도
함께 검증**한다(`denied` 면 404 + 감사). 요청 헤더 `X-Enterprise-Scope` 를 그대로 믿으면 안
된다는 지시가 바로 이것이다.

### 3.2 예상되는 파장 — 반드시 먼저 측정하라

지금 데이터에서 fail-closed 를 켜면 **거의 모든 것이 사라진다.** 착수 전에 아래를 세어라.

```bash
venv/Scripts/python.exe - <<'PY'
import os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from core.project_visibility import read_project_ownership, context_visible
ctx = {"tenant_id": "tenant_default", "entity_mode": "REAL", "scope_node_id": ""}
from collections import Counter
c = Counter()
for n in sorted(os.listdir('projects')):
    if not os.path.isdir(os.path.join('projects', n)): continue
    ok, why = context_visible(ctx, read_project_ownership(os.path.join('projects', n)))
    c[why] += 1
print(c)
PY
```

알려진 상태(2026-08-12):

- 61개 중 **59개가 SANDBOX/VIRTUAL** (G1-C1.1 마이그레이션 결과) → REAL 문맥에서 `MODE_MISMATCH`
- `demo-todo-app` 은 `enterprise_scope_id="hq"` — **노드 id 가 아니라 코드**다. 정규화 필요.
- `smart-life-app` 만 `node_41402723bc90` 로 정상 바인딩돼 있다.

즉 **REAL 문맥 사용자에게 보이는 프로젝트가 1~2개로 줄어든다.** 그것이 옳은 결과이지만,
그대로 내보내면 「목록이 비었다 = 고장」으로 읽힌다. 그래서 3.3 이 함께 가야 한다.

### 3.3 화면 오류 계약 (같이 해야 함)

| 상황 | 응답 |
|---|---|
| 정상적으로 대상 없음 | `0건` |
| 권한 없음 | `404` · 접근 불가 |
| 문맥 판독 실패(`RESOURCE_UNBOUND`·`CONTEXT_MISSING`·`LOOKUP_FAILED`) | **「조회 불가 · 문맥 점검 필요」** + 그 개수 |
| 격리 자료(SANDBOX) | 일반 목록에서 숨기고 **감사 화면에서만** |

목록 응답에 `context_blocked_count` 와 사유별 집계를 실어야 화면이 이 말을 할 수 있다.

### 3.4 필수 검증 매트릭스 (아직 없음)

지시된 것 중 **판정기 단위로만 덮인 것**과 **API·SSE 종단이 필요한 것**을 나눠 적는다.

| 항목 | 판정기 단위 | API·SSE 종단 |
|---|---|---|
| 동일 사용자·다른 테넌트 | ✅ | ⬜ |
| REAL ↔ VIRTUAL ↔ SANDBOX | ✅ | ⬜ |
| 상위→하위 조회 | ✅ | ⬜ |
| 하위→상위·형제 차단 | ✅ | ⬜ |
| `private`/`dept`/`company` | 부분(`company` 경계만) | ⬜ |
| 소유자·일반·관리자 | 부분 | ⬜ |
| **목록·상세·수정·SSE 결과 일치** | — | ⬜ **가장 중요** |
| 문맥 헤더 위조 | — | ⬜ |
| 빈 범위·끊어진 노드·판독 실패 | ✅ | ⬜ |
| 회사 전환 직후 SSE 종료·재연결 | — | ⬜ |

### 3.5 변이 검사 (반드시)

테넌트·모드·범위 검사를 **하나씩** 지우고 테스트가 깨지는지 확인하라.
⚠️ **`git checkout` 으로 되돌리지 마라** — 그 파일의 미커밋 작업이 전부 사라진다.
이 세션에서 실제로 그렇게 잃었다. 역치환(원래 문자열로 되돌리는 replace)만 쓴다.

---

## 4. 이 세션에서 함께 끝낸 다른 작업 (참고)

| 커밋 | 내용 |
|---|---|
| `d67d88c48` | 정적검사 `ok=None`·누락·예외에도 앱이 전달되던 것 차단(`is not True`), `.archive` 검사 제외 |
| `3641a02e9` | SSE 티켓에 tenant·scope·mode·session 봉인 · `context_version` · 로그아웃 시 스트림 차단 · 문맥 fail-closed |
| `091796602` | 협업 알림 테넌트 격리를 **routing_context** 로 재구현(payload 는 `_clean` 이 지우므로 판정 근거가 못 된다) |
| `d0086ebe9` | 과거 시험 릴리스 3건·승격 3건·활성 공유 1건 격리(`quarantined`·`SYNTHETIC_TEST`) |

### 반복해서 틀린 지점 — 같은 실수를 하지 마라

1. **테스트가 실제 배선을 타지 않으면 그 초록은 거짓이다.** `emit_to` 테넌트 격리를 완료로
   보고했는데, 테스트가 `CollaborationEvents` 를 건너뛰어 실서비스에서는 작동하지 않았다.
2. **변이 검사에서 반쪽만 잡힌 적이 있다.** 세션 검사를 지웠는데 0건 실패였다 — 로그아웃
   테스트가 `emit_to` 경로만 타고 `broadcast` 경로는 안 탔다. 두 경로는 다른 함수를 지난다.
3. **재실행 멱등을 두 번 놓쳤다.** 이미 격리한 것을 다시 세어 「N건 남음」으로 보고했다.
4. **「완료」를 성급하게 선언했다.** 부분 통제를 전체 통제로 보고한 것이 이 세션에서만 두 번.

---

## 5. 이후 순서 (확정)

```
⑤ 통합 가시성 판정기 배선   ← 지금 여기(판정기만 완성)
  ↓
⑥ 시험 데이터의 경영 결과·CERTIFIED 진입 차단
     최소 범위: 경영 브리핑·KPI · 실적 집계 · CERTIFIED 기준선 ·
                계산/시뮬레이션 Actual 입력 · 지식 승격 · 대내외 보고서
     (지금까지 닫은 것: 자산 사용 집계 · 릴리스/승격/공유)
  ↓
G1-B Host Runtime SDK + 단기 Capability Token
```

**G1-B 를 먼저 하면 안 되는 이유** — Capability Token 에
`app_id / release_id / user / tenant / scope / entity_mode / capability` 가 들어간다.
가시성 계약이 통일되지 않은 상태에서 토큰을 만들면 **잘못된 권한 규칙이 토큰 계약에 굳고**,
이후 Host Runtime 전체를 다시 고쳐야 한다.

---

## 6. 작업 위생

⚠️ 지금 작업 트리에 **다른 팀원의 용어집·UI·데이터 키트 변경**이 함께 있다.
`git add -A` 를 쓰지 마라. 파일을 하나씩 골라 스테이징한다.
`main.py`·`config.py` 처럼 여러 세션이 건드리는 파일은 `git diff --cached` 로 **훅 단위**까지
확인한다 — 이 저장소는 파일 단위 스테이징 때문에 HEAD 가 깨진 적이 있다.
