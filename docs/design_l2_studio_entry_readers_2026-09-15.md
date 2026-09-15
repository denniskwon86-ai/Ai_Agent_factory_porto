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
