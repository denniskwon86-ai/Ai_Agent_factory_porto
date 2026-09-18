# 설계안 — 남은 진입 대상의 확인 경로 (`kit_app` · `mega` · `draft`)

작성: Claude Code · 2026-09-15 KST · 권고10 / G3
전체 **21/40=52.5%**, 로컬 **18/28≈64.3% 유지** — 이 문서는 **설계안이며 구현이 아니다.**

> ⚠️ **결정을 대신하지 않는다.** Codex 가 `project` 용으로 세운 진입 확인 계약이 정본이고,
> 이 문서는 그것을 남은 세 대상에 어떻게 넓힐지 **선택지와 근거**를 정리한 것이다.
> 채택·수정·기각은 Codex 판단이다. 합의 전에는 구현하지 않는다.

관련 문서 — [B6 진입 및 READ](handoff/L2_STUDIO_B6_PROJECT_ENTRY_2026-09-15.md) ·
[브라우저 기준선 실측](handoff/L2_STUDIO_BROWSER_BASELINE_2026-09-15.md) §12 ·
[시작 안내](handoff/CLAUDE_CODE_START_HERE_2026-09-15.md) §4

## 1. 왜 이 문서가 필요한가

`studioLocation.ts` 는 **6종 대상**을 문법으로 판정한다. 그중 실제로 연결된 것은 셋이다.

| 대상 | 연결 | 서버 진입 확인 |
|---|---|---|
| `project` | ✅ | `GET /api/v1/factory/{project_id}/entry-metadata` |
| `new` | ✅ | **불필요** — 만들기라 조회 대상이 없다 |
| `release` | ✅ | 없음 — 기존 `library/item` 조회 + 실패 상태로 대응 |
| `kit_app` | ❌ | **없음** |
| `mega` | ❌ | **없음** |
| `draft` | ❌ | **없음** |

★ B6 인계가 못박았다 — 「성공 응답의 소유 조직과 현재 조회 조직은 상위/하위 관계일 수
있다. **조직 ID 단순 일치로 권한 판정을 대체하지 않는다.** 프런트는 서버가 검증한 문맥만
확인한다.」 서버 확인 없이 URL 을 붙이면 프런트가 그 판정을 흉내 내게 된다.

## 2. `project` 가 세운 계약 — 이것이 기준이다

`api/routes/factory_control.py` 의 `entry-metadata` 와 그것이 쓰는
`studio_input_draft_control._authorized` 를 읽어 정리했다.

### 2.1 판정 순서

1. `_safe_id` — 형식 위반은 **400**
2. 미로그인은 **401**
3. `org_directory.resolve_scope(fresh=True)` — 실패는 **503**. ★ 캐시를 쓰지 않는다
4. 자원 존재·읽기 권한 — 403 을 **404 로 바꾼다**
5. 고정 문맥 판독(`for_principal`) — v2 승인 문맥 확인
6. 소유 문맥 대 조회 문맥 가시성(`context_visible`) — 불가시는 **404**, 판독 실패는 **503**
7. 반환 **직전** 재확인(`recheck`) — 메타 변경·문맥 변화·권한 회수를 다시 본다

### 2.2 응답 계약

```
{ "status": "success", "data": {
    "<id 필드>": "...", "<표시 이름>": "...", "runtime_document_version": "1.0"|"2.0",
    "ownership":       { tenant_id, enterprise_scope_id, entity_mode },
    "viewing_context": { tenant_id, scope_node_id,       entity_mode } } }
```

### 2.3 지켜야 할 불변식

- **401·403·404 를 같은 문구로 답한다.** 나누면 존재 여부가 응답으로 샌다.
- **원문을 메아리치지 않는다.** 손상된 이름·경로·내부 사유를 화면 오류에 옮기지 않는다.
- **상태·초안 원문·체크포인트를 주지 않는다.** 진입 확인은 「볼 수 있는가」만 답한다.
- **조회가 자원을 만들지 않는다.** 디렉터리·DB·행 생성 금지.
- **조회 가능 ≠ 실행·게시 승인.** 그 판정은 각 단계가 다시 한다.
- 409·5xx 는 **503 `*_ENTRY_UNAVAILABLE`** 로 접는다.

## 3. 대상별 조사 결과

### 3.1 `mega` — 새 API 가 필요 없을 수 있다

`mega` 는 **project 의 한 종류**다. 실측 근거:

- 서버 경로가 `POST /api/v1/factory/projects/{project_id}/mega/plan` — **project_id 기반**이다.
- 프런트도 `currentProject?.is_mega_project === true` 로 판정한다(`App.tsx:547`).
- `studioLocation` 의 `mega` 대상은 `megaProjectId` + 선택적 `childProjectId` 인데,
  둘 다 프로젝트 ID 다.

**선택지 A — 기존 `entry-metadata` 를 재사용한다.**
`megaProjectId` 를 그대로 `entry-metadata` 에 묻고, 응답에 `is_mega_project` 를 **더한다.**
`childProjectId` 가 있으면 한 번 더 물어 **둘 다 확인되고 부모-자식 관계가 서버에서
확인될 때만** 연다.

- 장점: 판정 규칙이 한 곳에 남는다. 새 엔드포인트가 없다.
- 확인 필요: 부모-자식 관계를 **서버가** 답해 줄 수 있는가. 프런트가 두 응답을 보고
  관계를 추론하면 안 된다 — 그것이 §1 이 금지한 흉내다.

**선택지 B — `mega/plan` 조회에 진입 확인 의미를 부여한다.**
이미 있는 경로라 새 API 가 없지만, 그 응답이 계획 원문을 담으므로 §2.3 의 「상태·원문을
주지 않는다」와 어긋난다. **권하지 않는다.**

### 3.2 `kit_app` — 판정 로직이 이미 있다

`core/kit_app_contract.py:496` 의 `_visible_v2_instance` 가 §2.1 과 **같은 구조**로 판정한다.

- 인스턴스 조회 → 선택 문맥의 `tenant_id`·`entity_mode` 일치 확인
- `binding_for_instance` 로 `context_root_id` 일치 확인
- `ProcessBoundary` 구성 → `ProcessConfigurationService._authorize`
- 불가시는 `missing()` — 은닉 계약을 이미 지킨다

즉 **인스턴스 수준 확인은 재사용할 수 있다.** 남는 것은 두 가지다.

1. **`app_id` 단위 확인** — `kit_app_contracts` 에 그 앱이 있고 현재 문맥에서 보이는가.
   `list_for_instance(store, instance_id)` 가 이미 목록을 준다.
2. **선택적 `releaseId`** — `studioLocation` 의 `kit_app` 은 release 를 함께 받을 수 있다.
   릴리스 결속까지 서버가 확인해야 하는지 결정이 필요하다.

**제안**: `GET /api/v1/data-preparation/instances/{instance_id}/apps/{app_id}/entry-metadata`
— 기존 `instances/{id}/apps` 경로 아래에 두어 소유를 명확히 한다.

### 3.3 `draft` — 문맥을 **호출자가 넘긴다**

`api/routes/studio_draft_control.py:81` 의 `GET /drafts/{draft_id}` 는
**`context_root_id` 를 필수 쿼리로 받는다**(`scope_node_id`·`revision` 은 선택).

```
GET /drafts/{draft_id}?context_root_id=...&scope_node_id=...&revision=N
```

⚠️ 이것이 다른 둘과 결정적으로 다르다. `project`·`kit_app` 은 서버가 **선택 문맥 헤더**로
판정하는데, `draft` 는 **경계를 인자로 받는다.** 그래서 URL 진입에 그대로 쓰면:

- 프런트가 `context_root_id` 를 **어디선가 만들어 넣어야** 하고,
- 그 값이 사용자의 현재 선택과 다르면 **다른 문맥의 초안을 여는 길**이 열린다.

`studioLocation` 의 `draft` 대상은 `draftKind`·`draftId`·`revision` 만 가진다 —
경계를 담지 않는다. **의도적이다**(문법 모듈 머리말: 「권한·문맥 키와 미지원 대상 별칭은
Studio URL 에서 거절한다」).

**선택지 A — 진입 확인 전용 엔드포인트를 따로 둔다.**
`GET /api/v1/studio/drafts/{draft_id}/entry-metadata` — 경계를 **인자로 받지 않고**
서버가 선택 문맥 헤더로 판정한다. 기존 `GET /drafts/{draft_id}` 는 그대로 둔다.

- 장점: URL 에 경계가 실리지 않는다. 다른 둘과 판정 방식이 같아진다.
- 비용: 새 엔드포인트 + 기존 `StudioDraftService.get` 의 경계 판정을 헤더 기반으로 한 번 더 감싼다.

**선택지 B — 프런트가 현재 선택 문맥을 인자로 채운다.**
새 API 가 없지만, **현재 선택과 초안 소유가 다를 때 조용히 빈 결과가 될 위험**이 있다.
그리고 URL 로 들어온 초안이 어느 문맥 것인지 프런트가 추측하게 된다. **권하지 않는다.**

## 4. 공통화 — 하나로 묶을 것인가

세 대상에 각각 엔드포인트를 두면 §2.3 의 불변식이 **네 곳**(project 포함)에 복제된다.
B6 인계가 이미 경고했다 — 「후속 공통화 시 **이중 규칙의 드리프트를 방지**해야 한다.」

**선택지 A — 대상별 엔드포인트 + 공통 헬퍼.**
각 라우트는 자원 조회만 하고, 공통 헬퍼가 §2.1 의 3·6·7 단계(fresh scope·가시성·재확인)와
§2.3 의 응답 형태를 맡는다.

- 장점: 자원별 조회 로직이 각자 자리에 남는다. 경로가 소유를 드러낸다.
- 비용: 헬퍼 추출 시 **기존 `entry-metadata` 를 건드린다** — 회귀 위험. 46건 시험이 방어한다.

**선택지 B — 단일 엔드포인트.**
`GET /api/v1/studio/entry?target=kit_app&instance=...&app=...`

- 장점: 불변식이 한 곳.
- 단점: 대상별 권한 소유가 흐려진다. `factory`·`data-preparation`·`studio` 세 라우터의
  권한 가드(`_route_authority_guard`)가 다른데 하나로 묶으면 그 경계가 사라진다.
  **권하지 않는다.**

**내 권고: 선택지 A.** 다만 **헬퍼 추출을 먼저 하고**(회귀 시험으로 잠근 뒤) 대상별
엔드포인트를 얹는 순서를 제안한다. 반대로 하면 복제본이 셋 생긴 뒤 합치게 된다.

## 5. 순서와 규모 제안

| 묶음 | 내용 | 예상 |
|---|---|---|
| 1 | `mega` — `entry-metadata` 에 `is_mega_project` 추가 + 부모-자식 확인 방식 결정 | 20~30분 |
| 2 | 진입 확인 공통 헬퍼 추출 + 기존 46건 회귀 | 30~40분 |
| 3 | `kit_app` 진입 확인 API + 프런트 reader + 검사 | 60~90분 |
| 4 | `draft` 진입 확인 API(선택지 A) + 프런트 reader + 검사 | 60~90분 |
| 5 | 세 대상 App 연결 + 브라우저 실측 | 40~60분 |

★ 1 을 먼저 두는 이유: **새 API 없이 끝날 수 있는 유일한 대상**이고, 그 과정에서 공통
헬퍼의 모양이 드러난다.

★★ **3(`kit_app`)은 실측으로 검증할 수 있다.** 복원 데이터에 인스턴스
`ki_6b06ffb50a994a` 와 승인된 앱 7개(APP-01 원료 도입계획·추적 … APP-07 전사 시나리오·실적
통합)가 있고 전부 `readiness_state: AVAILABLE` 이다. 거절 경로뿐 아니라 **정상 경로까지
화면으로 확인할 수 있는 유일한 남은 대상**이다(§7 참조). 그 점에서 4(`draft`)보다 먼저
두는 것이 낫다 — draft 는 자산이 없어 거절 경로만 볼 수 있다.

## 6. Codex 가 결정해야 할 것

1. **`mega` 의 부모-자식 관계를 서버가 답하는가.** 프런트가 두 응답으로 추론하면 안 된다.
2. **`kit_app` 의 선택적 `releaseId` 를 진입 확인 범위에 넣는가.**
3. **`draft` 를 선택지 A(새 엔드포인트)로 갈 것인가.** 기존 경계 인자 방식을 유지하면
   URL 진입은 포기하는 편이 낫다고 본다.
4. **공통 헬퍼 추출 시점** — 지금(선택지 A 권고) 또는 세 대상을 만든 뒤.
5. **담당 분담.** 서버 API 는 `factory_control`·`data_preparation_control`·`studio_draft_control`
   세 라우터를 건드린다. B5/B6 계약과 맞물리므로 Codex 가 직접 할지, 내가 하되 계약을
   문서로 먼저 확정할지.

## 7. 이 문서의 한계

- **구현하지 않았다.** 위 경로·함수명은 2026-09-15 시점 소스를 읽어 적은 것이고,
  제안한 엔드포인트는 아직 없다.
- `release` 는 §1 표대로 이미 연결했으나 **진입 확인 API 없이** 기존 조회 + 실패 상태로
  대응한 것이다. 다른 셋과 같은 수준으로 맞추려면 별도 논의가 필요하다.
- ⚠️ **정정(2026-09-15).** 이 문서의 첫 판에 「실제 릴리스·키트 앱·초안 자산이 복원
  데이터에 없다」고 적었다. **틀렸다.** `library/` 디렉터리가 빈 것만 보고 셋을 싸잡아
  일반화했고, DB 를 확인하지 않았다. 실측은 다음과 같다.

| 자산 | 복원 데이터 실측 | 조회 |
|---|---|---|
| **키트 인스턴스** | `ki_6b06ffb50a994a`(KIT-MFG-NONFERROUS-PROCUREMENT 1.0.0, 제련공장) **1건** | — |
| **키트 앱 계약** | APP-01~APP-07 **7건 전부 `APPROVED`** | `GET /instances/{id}/apps` **200** |
| **릴리스 결속** | `app_release_dataset_bindings` **69행**, ID 8종(`CRM003_…`·`TEST001_…`) | `library/list` **200 빈 배열**, 단건 **404** |
| 초안(advisor) | `consultations`·`solution_blueprints` **0행** | — |

따라서 정확히는 이렇다.

- **`kit_app` 은 자산이 있다.** 인스턴스와 승인된 앱 7개가 실재하고 API 가 200 을 준다.
  **정상 경로를 화면으로 확인할 수 있다** — 이 문서의 설계를 실측으로 검증할 근거가 있다.
- **`release` 는 DB 기록은 있으나 산출물 파일이 없다.** 릴리스 결속 69행과 ID 8종이 남아
  있지만 `library/` 가 비어 조회가 404 다. 스냅샷이 `library` 를 제외했고, 저장소 이력에도
  한 번도 커밋된 적이 없으며(`git log --all --diff-filter=A -- library/*` 0건) 원본 트리에도
  없다. **산출물 자체가 이 PC 에 존재하지 않는다.**
- **`draft` 는 실제로 없다.** advisor 표가 0행이다(스냅샷 제외 대상).

- 제안한 엔드포인트는 아직 없다. 위 경로·함수명은 2026-09-15 시점 소스를 읽어 적은 것이다.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## 8. `kit_app` 연결 전 기준선 — 실측 (2026-09-15)

복원 데이터에 자산이 있으므로(§7) 연결 전 현재 동작을 먼저 기록해 둔다. 나중 개선의
대조군이다.

### 8.1 URL 진입 — 조용히 목록면으로 떨어진다

`?space=build&target=kit_app&instance=ki_6b06ffb50a994a&app=APP-03` 으로 들어가면:

- URL 이 `?space=build` 로 정리되고(§12.3 의 진입 키 제거가 작동)
- **앱 제작 목록면이 뜬다.** 오류도 안내도 없다.

★ `project` 의 연결 전 상태(**잘못 열림** — 없는 프로젝트인데 작업공간이 렌더링되고 404 가
「서버 연결 끊김」으로 보임)와 **다른 종류의 문제**다. `kit_app` 은 **조용히 안 열림**이다.
링크를 받은 사용자는 왜 목록이 떴는지 알 수 없다.

### 8.2 서버 거절 경로

| 호출 | 결과 |
|---|---|
| `/instances/{정상}/apps` | **200** — 앱 7개, 전부 `AVAILABLE` |
| `/instances/{없는 id}/apps` | **404** 「키트 인스턴스를 찾을 수 없습니다」 |
| `/instances/{형식 위반}/apps` | **404** — 같은 문구(은닉 유지) |
| `/instances/{정상}/apps` + `X-Enterprise-Scope: 다른 조직` | ⚠️ **200** |
| `/instances/{정상}/apps` + `X-Enterprise-Tenant: 다른 테넌트` | ⚠️ **200** |
| `/apps/{app}/contract/v2` — 문맥 미선택(권한 범위 전체) | **422** `PROCESS_CONTEXT_REQUIRED` |
| `/apps/{app}/contract/v2` — 제련공장 문맥 | **404** `PROCESS_INSTANCE_NOT_FOUND` |

### 8.3 ⚠️ 같은 라우터 안에서 문맥 판정이 셋으로 갈린다

이것이 이 조사의 핵심이며 **진입 확인 API 설계에 직접 영향을 준다.**

| 판정자 | 규칙 |
|---|---|
| `_instance_or_404`(`data_preparation_control.py:129`) | **`p.scope.unrestricted` 면 문맥 비교를 건너뛴다** |
| `_kit_review_context`(`:258`) | 명시 문맥을 **필수**로 요구 — 없으면 **422** |
| project 의 `entry-metadata` | 소유 대 조회 문맥을 `context_visible` 로 비교 — **unrestricted 여도 다르면 404** |

★ 화면은 「선택한 문맥은 모든 제품 화면과 조회에 함께 적용됩니다」라고 약속한다.
`_instance_or_404` 의 unrestricted 분기는 그 약속과 어긋나 보인다. **다만 전사 조회 권한의
의도된 설계일 수 있어 결함으로 단정하지 않는다** — Codex 판단이 필요하다.

### 8.3.1 `contract/v2` 404 의 원인 — 확정했다

소유 조직 문맥에서도 404 이므로 문맥 문제가 아니었다. 조건을 하나씩 평가해 확정했다.

```
store.get_instance('ki_6b06ffb50a994a')  →  정상
  tenant-afs-demo-materials / REAL / plant-afs-smelting-01 / active
binding_for_instance(store, inst)        →  None   ← 여기서 막힌다
```

`process_kit_instances.binding_for_instance:68` 이 **표 자체가 없으면 `None` 을 돌려준다.**

```python
if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table'
                     AND name='kit_process_instances'").fetchone():
    return None
```

그리고 `_visible_v2_instance` 가 `if not link: raise missing()` → **404**.

**복원 데이터의 `data_preparation.db` 에 `kit_process_instances` 표가 없다.**
`kit_process_artifacts` 도 없다. 둘 다 **B2 프로세스 설치가 만드는 표**다
(`test_b2_installation.py` 가 설치 후 `kit_instances` 와 `kit_process_instances` 가 1:1 로
생기는 것을 확인한다). 시험 seed 도 이 둘을 dp 필수 표로 둔다(`b3_kit_seed.py:22`).

복원 데이터의 표 구성(17개):
`kit_instances`(1) · `kit_app_contracts`(7) · `kit_registry_versions`(2) ·
`source_bindings`(35) · `dataset_snapshots`(38) · `dataset_ownership_bindings`(35) ·
`object_scope_index`(37,748) · `baseline_builds`(1) · `calc_execution_approvals`(3) ·
인증 계열 7표(전부 0행).

★ **결함이 아니라 데이터 상태다.** 이 키트 인스턴스는 **B1/B2 프로세스 구성과 연결되지
않은 채** 만들어졌다. 그래서 v2 계약 경로가 「새 업무 팩 적용본을 찾을 수 없습니다」로
**의도대로 차단**한다. 차단이 옳게 동작하는 것을 확인한 셈이다.

⚠️ **다만 이것이 진입 확인 설계에 직접 영향을 준다** — §8.4 참조.

### 8.4 그래서 진입 확인은 무엇을 물어야 하나

- **앱 목록(`/apps`)만으로 「이 인스턴스에 이 앱이 있고 볼 수 있다」는 답이 나온다.**
  계약 상세(`contract/v2`)는 그보다 엄격하며 진입 확인의 범위를 넘는다(§2.3 「상태·원문을
  주지 않는다」).
- 따라서 제안한 `instances/{id}/apps/{app_id}/entry-metadata` 는 **목록 수준 가시성 +
  app_id 존재**만 답하고, 계약·준비도·릴리스 결속은 각 단계가 다시 확인하는 편이 계약에 맞다.

★★ **§8.3.1 이 이 선택을 강하게 뒷받침한다.** 진입 확인을 v2 계약 경로 위에 얹으면
`kit_process_instances` 가 없는 이 데이터에서는 **모든 키트 앱 링크가 404** 가 된다.
사용자는 화면 목록에서 앱 7개를 보면서 링크로는 못 여는 상태가 된다 — 같은 자원에
**두 답**이 나오는 것이고, 그것이 이 저장소가 반복해서 막아 온 결함 유형이다.

⚠️ 반대로 목록 수준만 보면 **v2 연결이 없는 인스턴스의 앱도 열린다.** 그것이 맞는지는
제품 판단이다 — 「조회 가능 ≠ 실행·게시 승인」(§2.3) 원칙대로라면 **열되 각 단계가 다시
막는 것**이 일관되나, Codex 확인이 필요하다(§6-7).

### 8.5 §6 에 더할 결정 사항

6. **진입 확인이 `unrestricted` 를 어떻게 다룰 것인가.** `_instance_or_404` 처럼 문맥
   비교를 건너뛸 것인가, project 처럼 소유 대 조회를 항상 비교할 것인가. **둘이 다르면
   같은 사용자가 대상에 따라 다른 답을 받는다.**
7. **v2 연결이 없는 키트 인스턴스의 앱을 진입 확인이 통과시킬 것인가.** 복원 데이터가
   정확히 그 상태다(§8.3.1). 통과시키면 화면 목록과 링크가 같은 답을 주지만 v2 계약이 없는
   대상을 열게 되고, 막으면 목록에 보이는 앱을 링크로는 못 여는 상태가 된다.

## 9. `kit_app` 구현 — 6·7번 결정 반영 (2026-09-15)

사용자가 **§6-6·§6-7 을 「목록 수준」으로 결정**해 그대로 구현했다. 나머지 결정(1~5)은
그대로 열려 있고, 공통 헬퍼(§6-4)도 **추출하지 않았다.**

### 9.1 서버 — `GET /instances/{instance_id}/apps/{app_id}/entry-metadata`

`api/routes/data_preparation_control.py`. 판정 순서:

1. `app_id` 형식 위반 → **400**
2. `_instance_or_404` — **기존 은닉 규칙 재사용**(6번 결정: `unrestricted` 면 문맥 비교를
   건너뛴다). 404 를 **아래와 같은 문구로 접는다**
3. 목록과 **같은 분기** — v2 연결이 있으면 그 경로, 없으면 legacy `PROJECT_RUN` 요구
   (7번 결정: v2 연결이 없어도 통과한다)
4. 프로필의 앱 정의에서 `app_id` 존재 확인 → 없으면 **404**
5. **반환 직전 재확인** — 조회 중 권한·문맥 변화

⚠️ **준비도를 계산하지 않는다.** `kit_registry.outputs(profile)` 의 앱 정의만 본다.
링크를 열 때마다 준비도 계산 비용을 내지 않기 위해서다. 준비도·계약·릴리스 결속은
§2.3 대로 주지 않는다.

**구현 중에 결함 하나를 만들고 잡았다.** 처음에는 `_instance_or_404` 의 기존 문구를 그대로
통과시켜 「업무 앱을 찾을 수 없습니다」와 「키트 인스턴스를 찾을 수 없습니다」가 **다른
문구**가 됐다 — 인스턴스 존재 여부가 샌다. 한 문구로 접었다. §2.3 을 적어 놓고 스스로
어긴 자리였다.

### 9.2 프런트

- `frontend/src/factory/studioKitAppEntry.ts` — reader + flow
- `frontend/src/factory/StudioKitAppEntryGate.tsx` — 확인 중·거절·재조회 표시
- `App.tsx` — 게이트 분기. 확인되면 **기존 「키트 운영 → 시뮬레이션」과 같은 자리**로 넘긴다
  (`setPathCalcInitialInstanceId/AppId` + `setShowPathCalc(true)`)

⚠️ **project reader 와 다른 점 하나**: 소유와 조회 문맥이 **같은지 보지 않는다.** 목록 수준
판정이라 전사 조회 권한에서는 둘이 다를 수 있다(6번 결정). project reader 는 둘이 다르면
잘못된 응답으로 본다. 코드 주석에 그 이유를 적었다.

⚠️ **공통화하지 않았다.** flow 부분이 `studioProjectEntry.ts` 와 구조가 같다. §6-4 가
미결이므로 **합칠 때 옮기기 쉽도록 같은 모양을 유지**했다.

### 9.3 실측

| 경로 | 결과 |
|---|---|
| `?target=kit_app&instance=ki_6b06ffb50a994a&app=APP-03` | **경로 계산 패널 열림** |
| 같은 URL, `app=APP-99` | **「현재 회사·권한에서 업무 앱을 찾을 수 없습니다」 + 재확인 버튼** |
| API 정상 | **200** · `app_label: "재고·생산 영향 분석"` |
| API 없는 앱 / 없는 인스턴스 | **404 — 같은 문구** |
| API 형식 위반 | **400** |
| API 다른 조직 헤더 | **200**(6번 결정대로) |

★ §8.1 의 연결 전 기준선(**조용히 목록면으로 떨어짐**)과 대조된다. 이제 열리거나, 왜 못
여는지 말한다.

⚠️ **첫 관찰에서 「안 됐다」고 판단할 뻔했다.** 화면 텍스트 앞부분만 보고 목록면이라고
읽었는데, 경로 계산 패널이 **오버레이로 뒤에** 있었다. `new` 연결 때와 같은 착오다.
**부분 관찰로 결론 내지 않는다.**

### 9.4 검사

tsc 0 · build PASS · B5 계약 **153** · project-entry **26** · studio-location **25** ·
서버 **83 PASS**(`test_b6_project_entry`·`test_b6_revision_reads`·`test_b2_installation`,
소스·보호 자산 지문 불변).

### 9.5 서버 시험 — `tests/test_b6_kit_app_entry.py` **17건**

실제 B2 설치로 인스턴스를 만들고 `data-preparation` 라우터만 mount 한 HTTP 회귀다.

| 시험 | 무엇을 잠그나 |
|---|---|
| `..._same_set_as_the_visible_list` | **목록에 보이는 앱은 전부 진입 확인을 통과한다** — 두 답이 갈리지 않는다(6·7번 결정의 핵심) |
| `..._no_readiness_or_contract_leak` | 응답 형태 고정 + `readiness_state`·`contract_status`·`release_id` 등 **7개 필드 비노출** |
| `..._unknown_app_is_404...` | 없는 앱 3종 → 404, `data` 없음 |
| `..._same_wording_as_missing_app` | **없는 인스턴스와 없는 앱이 같은 문구** — 인스턴스 존재 비노출 |
| `..._rejected_with_400` | 라우팅을 통과하는 형식 위반 5종 → **400** |
| `..._never_reaches_the_handler` | 슬래시·빈 값 3종 → 라우팅에서 갈림 |
| `..._creates_nothing` | 없는 대상을 물어도 **세 DB 전체가 그대로** |
| `..._ownership_reports_the_instance` | 소유는 인스턴스의 것 — 호출자 문맥을 되돌려 주지 않음 |
| `..._unauthenticated_caller_is_rejected` | 미인증 차단 |

**줄 단위로 검증했다.** 차단하는 줄을 지우면 대응 시험이 실패한다.

| 제거한 것 | 실패 |
|---|---|
| 은닉 문구 통일 | 1건 — 정확히 그 시험만 |
| 앱 존재 확인 | 6건 |
| `app_id` 형식 검사 | 5건 |

### 9.6 ⚠️ 시험이 내 결함을 둘 잡았다

**하나는 느슨한 시험이었다.** 형식 위반 시험을 처음에 `status_code in (400, 404, 405)` 로
썼다. 그러면 **형식 검사를 통째로 지워도 404 로 통과**한다 — 가짜 통과다. 줄 단위 검증에서
「제거해도 실패 0건」이 나와 알았고, 라우팅을 통과하는 위반은 **400 을 강제**하도록 조였다.

**하나는 제품 결함이었다.** 조인 시험이 곧바로 실패했다 — 한글 `앱` 이 400 이 아니었다.
원인은 `str.isalnum()` 이 **유니코드 문자를 참으로 본다**는 것이다. 한글·한자 ID 가 형식
검사를 통과하고 있었다. `re.fullmatch(r"[A-Za-z0-9_-]{1,160}")` 로 바꿨다 — 프런트 reader 와
같은 집합이다.

★ 느슨한 시험을 조이지 않았다면 이 결함은 그대로 남았다.


---

## 10. `mega` 진입 계약 — 변경 전 확정 (2026-09-15, MEGA-ENTRY-01)

지시서 §3-2 에 따라 **코드를 고치기 전에** 적는다. 새 엔드포인트를 만들지 않고
§3.1 선택지 A(기존 `entry-metadata` 호환 확장)를 따른다.

### 10.1 권위 저장소 — 실측

메가 소속의 정본은 **프로젝트 작업공간의 `latest_state.json`** 이다.

```
부모(mega)  is_mega_project: true   parent_project_id: ""   sub_projects_map: {domain: child_id}
자식        is_mega_project: false  parent_project_id: <mega_id>
```

쓰는 곳은 `factory_control.create_mega_project`(1168~1189), 읽는 곳은 목록
엔드포인트(863~879)와 `mega/plan`(1264). 프런트는 `currentProject.is_mega_project`
(`App.tsx:565`)와 `sub_projects_map`(`MegaBoardroomPanel`)을 본다.

⚠️⚠️ **관계의 출처가 둘이다.** 부모의 `sub_projects_map` 과 자식의 `parent_project_id`
가 서로 다른 파일에 있고 **어긋날 수 있다.** 한쪽만 보면 조용히 뚫린다 —
자식이 자기 것이 아닌 메가를 가리키거나, 부모가 자기 것이 아닌 자식을 열거한다.
**둘 다 일치할 때만 관계로 인정한다.**

★ `entry-metadata` 는 지금 `project_meta.json` 만 읽는다. 소속은 **다른 파일**이므로
  읽는 파일이 하나 는다 — `recheck` 도 그 파일을 같이 봐야 한다(§2.1-7).

### 10.2 요청

```
GET /api/v1/factory/{project_id}/entry-metadata               부모 단독
GET /api/v1/factory/{project_id}/entry-metadata?child=<ID>    부모 + 선택 자식
```

★ **하나의 확인 응답**이다(Codex 검토 권고 1). 프런트가 두 번 물어 관계를 추론하지 않는다.

### 10.3 응답 — 기존 계약에 두 칸만 더한다

```
{ "status": "success", "data": {
    ...기존 그대로(project_id · project_name · runtime_document_version ·
                   ownership · viewing_context)...,
    "is_mega_project": true|false,        ← 항상 있다
    "child": null | {                     ← ?child= 를 준 경우에만 객체
        "project_id", "project_name", "runtime_document_version",
        "ownership", "viewing_context" } } }
```

기존 소비자는 모르는 칸을 복사하지 않으므로(`studioProjectEntry.ts` 가 화이트리스트로
읽는다) **호환 확장**이다.

### 10.4 오류 계약 — 기존 정책을 그대로 쓴다

| 상황 | 응답 |
|---|---|
| id 형식 위반(부모·자식 공통) | **400** |
| 미로그인 | **401** |
| 없는 부모 / 안 보이는 부모 / 삭제된 부모 | **404** 같은 문구 |
| `?child=` 인데 **부모가 메가가 아님** | **404** 같은 문구 |
| 없는 자식 / 안 보이는 자식 / 삭제된 자식 | **404** 같은 문구 |
| **관계 불일치**(둘 중 하나라도 어긋남) | **404** 같은 문구 |
| 다른 조직·권한 부족 | **404** 같은 문구 |
| 확인 중 문맥·메타·소속 변경 | **503** `PROJECT_ENTRY_UNAVAILABLE` |
| 권한 판독 실패·409·5xx | **503** `PROJECT_ENTRY_UNAVAILABLE` |

⚠️ **어느 단계에서 막혔는지 말하지 않는다.** 「부모는 있는데 자식이 없다」를 구분해
  주면 존재 여부가 응답으로 샌다(§2.3 첫 줄).

### 10.5 ★ 소속을 못 읽을 때 — 방향이 중요하다

`latest_state.json` 이 **없거나·손상·심볼릭 링크**면 소속 판독기는 `None` 을 돌려주고
`is_mega_project` 는 **false** 가 된다.

> ⚠️ **실측으로 한 칸 고친다(2026-09-15).** 「손상이면 200 + false」를 예상했는데,
> 실제로는 **기존 인증 경로가 먼저 503** 을 낸다 — `studio_project_context` 가 같은
> 파일을 읽기 때문이고 **내 변경 이전부터 그렇다**. 더 닫힌 쪽이라 그대로 둔다.
> 아래 두 줄이 지키려던 것은 **「파일이 아예 없는」 레거시 프로젝트**이고, 그건
> 그대로 200 + false 로 들어간다(`test_a_project_without_any_state_file_still_enters`). 두 가지를 동시에 만족하기 때문이다.

- **기존 `project` 진입을 깨지 않는다.** 레거시 프로젝트엔 그 파일이 아예 없다.
  여기서 503 을 내면 지금 되던 진입이 죽는다.
- **메가 진입에는 fail-closed 다.** false 면 메가로 열리지 않는다.

그리고 `?child=` 가 온 경우에는 **부모·자식 양쪽 소속을 다 읽어야** 하고, 하나라도
못 읽으면 **404** 다. 관계를 주장하는 요청은 관계를 증명해야 한다.

### 10.6 지키는 불변식 (§2.3 그대로)

- 조회가 **자원을 만들지 않는다** — 작업공간·상태 파일·행 생성 금지.
- **상태·계획 원문·체크포인트를 주지 않는다** — `sub_projects_map` 전체도 주지 않는다.
  「이 자식이 이 부모의 것인가」에만 답한다.
- **조회 가능 ≠ 실행·게시 승인.** 확인 전에 프로젝트 선택·실행을 시작하지 않는다.
- 권한을 넓히지 않는다 — 판정은 전부 기존 `_authorized`·`resolve_scope(fresh=True)` 다.

---

## 11. 【FIX1 · 2026-09-15】 판정 순서와 **실제 보장 범위**

Codex 핵심 검토(`docs/handoff/CODEX_MEGA_ENTRY_REVIEW_2026-09-15.md`) 반영분.

### 11.1 순서 — 숨겨야 할 대상은 «읽기 전에» 닫는다

503 을 404 로 **접지 않는다.** 대신 순서를 고쳤다.

```
① 부모 확인(_authorized · 문맥 · 메타)
② 부모 소속 판독 → is_mega_project
③ ★ 부모 «사실만으로» 끝나는 거절      ← 여기서 닫으면 자식을 «아예 안 읽는다»
      · 부모가 메가가 아니다
      · 부모 목록에 그 자식이 없다
      · 자기 자신을 자식으로 요청했다
④ 자식 확인(_authorized · 메타 · 소속)
⑤ 자식이 부모를 가리키는가
```

⚠️ ③을 ④ 뒤에 두면, 관계 밖 자식의 **판독이 실패할 때 503 이 나간다.** 그러면
「없는 자식」과 「관계 밖이지만 존재하는 자식」이 구분된다 — 존재가 응답으로 새는 것이다.

### 11.2 ★ 보장 범위 — 「판독 장애 = 503」이 **아니다**

실측으로 확정했다. 어느 파일이 깨졌느냐에 따라 다르다.

| 깨진 것 | 결과 | 누가 정하나 |
|---|---|---|
| `project_meta.json`(소속) | **404** | 기존 PDP 계층이 «없는 것» 으로 은폐 |
| `latest_state.json`(상태) | **503** | `studio_project_context` 판독 실패 |
| 상태 파일이 **아예 없음** | **200**, `is_mega_project=false` | 레거시 프로젝트 보존 |

★ `membership()` 의 `None` 은 **이 표와 충돌하지 않는다.** 그 함수는 어떤 경우에도
  예외를 던지지 않고 「소속을 모른다」만 돌려준다 — 위의 404·503 은 **더 앞 계층**이
  내는 것이고, `membership()` 이 부르기 전에 이미 요청이 끝나 있다.
  `membership()` 이 실제로 결과를 정하는 경우는 **상태 파일이 없는 레거시**뿐이다.

⚠️ 즉 §10.5 의 「없거나·손상·심볼릭 링크면 false」는 **`membership()` 함수의 계약**이지
  **엔드포인트의 계약이 아니다.** 손상은 그 함수에 닿기 전에 막힌다.

### 11.3 프런트 — 메가 요청은 «명시 true» 일 때만 진행한다

```
App(요청 종류 보존) → Gate(requireMega) → flow → reader
```

⚠️⚠️ 종전에는 서버가 `is_mega_project` 를 정확히 답했는데 **아무도 그 사실을 쓰지
  않았다.** 설계안에 「Gate 가 거절한다」고 적고 구현하지 않은 것이다 — 그래서 메가
  링크로 일반 프로젝트가 열렸다. **적은 것과 만든 것이 다르면 적은 쪽은 통제가 아니다.**

- 일반 `project` 요청은 `false` 도 정상이다.
- `mega` 요청은 **자식 유무와 무관하게** 명시 `true` 일 때만 진행한다(`ENTRY_NOT_MEGA`).
- 자식이 딸려 왔는데 `is_mega_project !== true` 면 **계약 위반**(서버가 옳다면 불가능).
- `requireMega`·`childId` 는 **질문의 일부**라 바뀌면 이전 flow·응답을 버린다.

---

## 12. 【DRAFT-ENTRY-01 · 2026-09-15】 초안 진입 — **경계를 받지 않고 «찾는다»**

§3.3 의 **선택지 A**(전용 진입 엔드포인트)를 택했다. Codex 검토 권고 3 과 같다.

### 12.1 왜 A 였나 — 조사로 확정했다

```
advisor_v2_drafts:  draft_id TEXT PRIMARY KEY, boundary_json, owner_actor, head_revision
```

★★★ `draft_id` 가 **PRIMARY KEY** 다. 즉 초안이 **자기 경계를 들고 있다.** §3.3 이
걱정한 「프런트가 `context_root_id` 를 어디선가 만들어 넣는」 문제가 **없어도 된다** —
서버가 id 로 찾아 소유 문맥을 읽고 선택 문맥과 대조하면 `project` 와 같은 모양이 된다.

⚠️ 기존 `GET /drafts/{id}?context_root_id=…` 는 **그대로 둔다.** 그 경로는 «이미 그
문맥에서 일하는» 화면이 쓰는 것이라 맞는 방식이다(`studioRequirementDraft.ts:223`).
문제는 **URL 로 들어온 초안**이고, 그때는 프런트가 문맥을 모른다.

### 12.2 계약

```
GET /api/v1/advisor/drafts/{draft_id}/entry-metadata?kind=<종류>&revision=<N>

{ "status":"success", "data": {
    "draft_id", "draft_kind", "revision",
    "ownership":       { tenant_id, context_root_id, entity_mode, scope_node_id },
    "viewing_context": { tenant_id, scope_node_id, entity_mode } } }
```

### 12.3 판정 순서 — 순서가 곧 규칙이다

```
① 종류·판본 형식        지원 종류인가 · 판본이 1 이상인가
② 선택 문맥 확정        explicit_context 가 헤더를 조직 정본에 대조한다
③ 소유 문맥 판독        초안이 들고 있는 경계 4키를 «찾는다». 받지 않는다
④ 권한·문맥 대조        기존 _authorize — 테넌트·모드·범위 사슬·사람 권한
⑤ 판본 존재            제품 경로(revisions.get)로 확인하고 **내용은 버린다**
```

⚠️ ④를 **다시 만들지 않았다.** 그 함수가 이미 「선택 문맥이 이 초안의 사슬 안에 있는가」
까지 본다. 서버 **권한 정책 변경 0건**이다.

### 12.4 ⚠️⚠️ `consultation` — 조용히 열지 않는다

종류 둘이 **서로 다른 저장소**에 살고, 결정적 비대칭이 있다.

| 종류 | 저장소 | 판본 |
|---|---|---|
| `blueprint` | `advisor_v2_drafts` | `advisor_v2_revisions.revision` — **있다** |
| `consultation` | `consultations` | **없다** |

그런데 `studioLocation` 은 **두 종류 모두에 `revision` 을 필수**로 받는다. 상담의 `N` 은
**확인할 대상이 없다.** 그냥 버리면 kit_app `releaseId` 와 **같은 결함**이 된다
(Codex 권고 2: 「조용히 버리는 현재 상태를 완료로 보지 않는다」).

그래서 서버가 **말한다** — `STUDIO_DRAFT_KIND_UNSUPPORTED`(422). 프런트도 이것을
「없다」와 **다른 문구**로 보여 준다. 사용자가 사라진 초안을 찾아다니지 않게.

★ **결정 요청**: ⒜ `consultation` 지원 전으로 두고 URL 문법에서 판본을 뺀다(권장) /
⒝ `revision` 을 `consultation_turns.turn_no` 에 결속한다(제품 의미를 새로 정하는 일).

### 12.5 flow 공통부를 뽑았다 (`studioEntryFlow.ts`)

`project` 와 `kit_app` 의 flow 본체가 **글자까지 같았다.** 셋째를 붙이는 순간이 뽑을
자리다(Codex 권고 4: 「mega/draft 추가 시 «확인된» flow 공통부분만 추출」).

⚠️ **오류 코드·메시지는 뽑지 않았다.** 공통인 것은 «수명» 뿐이다 — 세대·중단·신원·구독.
합치면 「무엇을 못 열었는지」가 한 문장으로 뭉개진다. 기존 43·14건이 그대로 통과해
추출이 동작을 바꾸지 않았음을 증명한다.

### 12.6 남은 연결 — **여기까지가 이번 범위다**

확인된 초안을 «여는 화면»은 아직 없다. 기존 `BuildStartDialog` 는 자기 상태에서
`requirementDraft` 를 만들지, **밖에서 받은 초안을 싣는 자리가 없다.** 없는 화면을
지어내지 않고 인계한다 — 진입 확인은 「볼 수 있는가」이고, 그 답은 나왔다.
