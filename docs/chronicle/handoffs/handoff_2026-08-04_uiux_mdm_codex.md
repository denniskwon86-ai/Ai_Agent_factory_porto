# 인수인계 — 2026-08-04 · Codex UI/UX 지식 허브 감사 마감 및 MDM 2/10 이관

- 작성자: Codex
- 기록 시각: 2026-08-04 11:24 KST
- 기준 브랜치: `dev`
- 기준 HEAD: `823771c15`
- 커밋·푸시: **미수행**
- 팀 보드 대응 항목: `.agents/TEAM_BOARD.md` `[UIUX-IMPL-35]`
- 선행 인수인계: `docs/chronicle/handoffs/handoff_2026-08-04_uiux_migration.md`

> **후속 정정 · 2026-08-04 11:56 KST:** 제품 기본 외형은 다크가 아니라
> **라이트 업무 표면 + LS Navy 구조 헤더/레일**이다. `UIUX-CORRECTION-36`에서
> `afs-product-shell`을 신설해 런처와 제품 진입점에 복구했다. 이 문서를 이어받을 때
> `index.css`의 레거시 다크 `@theme`를 제품 기본값으로 해석하지 말고,
> `frontend/src/design/product-shell.css`와 `master-concept/ADOPTION_DECISION.md`의 시각 기준선을 따른다.

---

## 1. 이번 인수인계의 결론

선행 인수인계가 지정한 **지식 허브 감사 보완**과 **이관 2/10 MDM 기준정보 화면**의 코드 작업을
완료했다. MDM 실데이터를 확인하는 과정에서 단순 UI 문제가 아닌 **서버 권한 누수**를 발견했다.

발견 당시 동작:

- 익명 사용자로 `GET /api/v1/master/types` 호출 → 기준정보 유형 21개 반환
- 익명 사용자로 `GET /api/v1/master/records` 호출 → 실제 기준정보 반환
- 프롬프트 주입 경로는 조직 바인딩을 지켰지만 목록·상세·수정 API는 바인딩과 권한을 확인하지 않음

따라서 화면에서만 숨기는 임시조치로 끝내지 않고 다음 계약까지 구현했다.

1. 목록을 열 수 없는 사용자는 `data=[]`와 `blocked_reason`을 받는다.
2. 일반 사용자는 ECM 가시 조직 범위에 명시적으로 바인딩된 기준정보만 본다.
3. 타 조직 상세 조회는 존재를 노출하지 않도록 404로 응답한다.
4. 404 거부 시 내부 감사로그에는 실제 마스터 코드와 요청자를 남긴다.
5. 기준정보 쓰기·범위 관리·품질 점검은 데이터 표준 관리자만 수행한다.
6. 주입 미리보기와 범위별 허용 코드 조회는 클라이언트가 보낸 조직 범위를 그대로 신뢰하지 않는다.

현재 상태는 **코드 구현 완료, 프론트 빌드 및 Python 구문 검증 완료, 백엔드 전체 회귀 테스트 대기**다.

---

## 2. 변경 파일과 역할

### 2.1 프론트엔드

#### `frontend/src/components/MasterDataPanel.tsx`

기존 화면을 전면 이관했다.

- `HubDialog` + `HubShell` + `JarvisRail` 공통 셸 적용
- `DataState`로 로딩·정상 0건·조회 실패·접근 불가 구분
- 기준정보 유형 선택과 레코드 목록/상세를 한 작업면에 배치
- 유형이 21개 이상일 때 긴 카드 목록 대신 셀렉터로 선택
- 등록·개정, 별칭 추가·제거, 소프트 폐기, CSV 일괄등록 유지
- 개정 이력 및 출처 표시
- 복합 속성을 `[object Object]`가 아닌 서식화된 JSON으로 표시
- 에이전트가 실제로 받는 기준정보 블록 미리보기 제공
- 일반 사용자의 미리보기에는 ECM 조직 범위 입력을 받으며 서버가 권한을 재검증
- raw `fetch`, `alert`, `confirm`, 자체 `fixed` 모달 제거
- 가시 텍스트 12px 미만 제거

#### `frontend/src/lib/masterDataApi.ts` — 신규

- 기준정보 유형·레코드·이력·CSV·주입 미리보기 타입 정의
- MDM API 호출을 한곳으로 통합
- 목록 응답의 `blocked_reason`과 `hidden_count` 보존
- JSON 요청은 공용 `closedLoopFetch`, FormData만 전용 요청 사용

#### `frontend/src/components/KnowledgeHubPanel.tsx`

- 지식팩 목록의 `blocked_reason`을 접근 불가 상태로 표시
- 접근 불가를 정상 0건으로 오인하지 않음
- 권한 범위 밖의 숨김 건수 안내
- 접근 불가 상태에서는 `새 지식팩` 입력 패널을 표시하지 않음
- `사람 확인` 표현을 `사용자 확인`으로 통일

#### `frontend/src/lib/closedLoopFetch.ts`

- 기존 `data`만 반환하는 호출은 유지
- `blocked_reason`, `hidden_count`까지 필요한 화면을 위한 `closedLoopEnvelopeFetch` 추가
- 403·409 오류 제목 추가

#### `frontend/src/lib/knowledgeApi.ts`

- 지식팩 목록을 봉투 보존형 호출로 변경

#### `frontend/src/design/afs.css`

- MDM JSON/주입 블록의 줄바꿈·가로 오버플로 방지
- 검색 입력의 지우기 버튼을 수용하도록 그리드 수정
- 폼·상태·사용자 정보 최소 글자 크기 상향

#### `frontend/src/design/HubShell.tsx`

- 레일 배지에 의미 있는 `countLabel`을 선택적으로 부여
- 모든 숫자를 잘못 `N건 대기`로 읽던 기본 aria-label을 중립적인 `N건`으로 변경

#### `frontend/src/App.tsx`, `frontend/src/components/GlobalNav.tsx`

- 1280px 상단 내비게이션이 우측 Network 상태를 밀어내지 않도록 간격·패딩 축소
- Network 텍스트는 큰 화면에서만 표시하고 상태 점은 유지

### 2.2 백엔드

#### `api/routes/master_control.py`

추가한 서버 권한 계약:

- `visibility_block_reason()`으로 목록 자체를 열 수 있는지 먼저 판정
- `viewer_visible_scopes()`와 `master_data.bindings_for_scope()`로 열람 가능 코드 계산
- `/types`, `/records`는 허용 코드 기준으로 필터링하고 `hidden_count` 반환
- 익명·미등록·폐지·부서 미배정 사용자는 `data=[] + blocked_reason`
- `/records/{master_code}`의 타 조직 자원은 404 + `audit.denied_scope()`
- 유형 생성/수정/삭제, 레코드 생성/폐기, 별칭 변경, CSV 등록은 `assert_can_manage_standard`
- 중복 후보, 범위 커버리지, 범위 바인딩 전체 목록, 문서 품질도 관리자 전용
- `/scope-bindings/allowed`는 일반 사용자의 요청 범위를 서버 계산 범위와 교차 검증
- `/grounding/preview`도 같은 범위 검증 적용
- 일반 사용자가 범위를 지정하지 않고 전량 미리보기 하는 것을 422로 차단

DB 스키마와 기준정보 본문은 변경하지 않았다.

### 2.3 테스트

#### `tests/test_listing_visibility_gate.py`

추가한 회귀 계약:

- 익명 MDM 목록은 비노출이며 차단 이유가 존재
- A 조직 사용자는 A에 바인딩된 레코드와 해당 유형만 열람
- 타 조직 레코드 상세는 404이고 감사 이벤트 생성
- 일반/미등록 사용자의 기준정보 쓰기 차단
- 범위 커버리지·전체 바인딩·문서 품질 관리 API 차단

---

## 3. 검증 결과

### 통과

```text
npm run build
→ TypeScript 검사 통과
→ Vite production build 통과
```

```text
LibreOffice Python 3.12 -m py_compile
  api/routes/master_control.py
  tests/test_listing_visibility_gate.py
→ 구문 검사 통과
```

```text
git diff --check -- <이번 작업 대상 파일>
→ 통과
```

1280×720 확인 내용:

- 지식 허브: 접근 불가와 0건 구분
- MDM: 실데이터 유형 21개, BOM 레코드 2건 표시
- 긴 유형 목록을 셀렉터로 바꾼 뒤 작업면 과도한 세로 밀림 완화
- 중앙 작업면 가로 오버플로 0
- 12px 미만 가시 글자 0
- 실제 레코드 상세·이력·복합 JSON 표시 확인
- 주입 미리보기에서 매칭 코드와 grounding block 표시 확인

### 실행하지 못한 검증

전체 pytest와 실서버 권한 카나리는 실행하지 못했다.

원인:

- `venv/pyvenv.cfg`가 삭제된 `C:\Users\denni\AppData\Local\Python\pythoncore-3.14-64`를 참조
- `venv\Scripts\python.exe`가 프로세스를 만들지 못함
- LibreOffice Python 3.12에 venv site-packages를 연결하면 Python 3.14용 `pydantic_core` 바이너리를 불러오지 못함
- 확인 시점에 8081 백엔드는 실행 중이 아니었음

이 사유를 테스트 성공으로 간주하지 말 것.

---

## 4. 다음 세션의 첫 행동

### 4.1 정상 Python 환경 확보 후 우선 회귀 테스트

```powershell
python -m pytest `
  tests/test_listing_visibility_gate.py `
  tests/test_master_api_routes.py `
  tests/test_master_scope_binding.py `
  tests/test_m2_entry_gates.py -q
```

가상환경이 복구됐다면:

```powershell
venv\Scripts\python.exe -m pytest `
  tests/test_listing_visibility_gate.py `
  tests/test_master_api_routes.py `
  tests/test_master_scope_binding.py `
  tests/test_m2_entry_gates.py -q
```

### 4.2 테스트 실패 시 우선 확인 순서

1. `test_listing_visibility_gate.py`
   - `AccessScope.readable_scope_nodes`가 테스트의 `ORG-A`를 실제로 전달하는지
   - route-level `viewer_visible_scopes` monkeypatch가 적용되는지
2. `test_master_api_routes.py`
   - 조직 강제 OFF 환경에서 `unrestricted=True` 하위호환이 유지되는지
   - `/records/duplicates`가 관리자 권한으로 정상 응답하는지
3. `test_master_scope_binding.py`, `test_m2_entry_gates.py`
   - 미바인딩 비주입 원칙이 유지되는지
   - 새 목록 필터가 프롬프트 주입 로직을 변경하지 않았는지

테스트를 통과시키기 위해 다음 원칙을 약화하지 말 것:

- 미바인딩 = 전사 공용 금지
- 타 조직 상세 = 404 Data Stealth
- 거부 = 내부 감사로그 기록
- 관리자/조직 미도입 환경의 `unrestricted` 하위호환

### 4.3 실서버 읽기 전용 확인

백엔드를 8081로 실행하고 관리자·일반 사용자·익명 세 상태를 확인한다.

```powershell
# 관리자: 전체 또는 관리자 정책 범위가 보여야 함
Invoke-RestMethod http://127.0.0.1:8081/api/v1/master/types `
  -Headers @{ 'X-Factory-User'='hikwon@lsmnm.com' }

# 익명: data=[]와 blocked_reason이어야 함
Invoke-RestMethod http://127.0.0.1:8081/api/v1/master/types
```

일반 사용자 확인 시 기대값:

- 자기 ECM 범위에 바인딩된 기준정보만 반환
- `hidden_count`가 실제 숨김 건수와 일치
- 타 조직 마스터 코드 상세는 404
- `data/access_audit.jsonl`에 `ACCESS_DENIED_SCOPE_MISMATCH`와 실제 코드 기록
- POST/DELETE는 403

데이터를 생성·수정·폐기하는 API는 이 검증에서 호출하지 않는다.

### 4.4 화면 감사

정상 서버와 실제 사용자 상태에서 다음을 1280×720과 1440×900으로 확인한다.

1. 관리자: 유형·레코드·등록·CSV·주입 미리보기
2. 일반 사용자: 바인딩된 유형·레코드만 노출, 숨김 건수 안내
3. 익명: 접근 불가, 0건 지표 금지, 등록 패널 비노출
4. 지식 허브: 접근 불가 상태에서 새 지식팩 폼 비노출
5. 상단 내비게이션: Network 상태 점까지 화면 안에 존재
6. 가로 오버플로 0, 12px 미만 가시 글자 0

이 검증 전에는 **UI/UX 이관 2/10 최종 승인**이라고 표현하지 않는다.

---

## 5. 현재 작업 트리와 커밋 주의

이번 작업 관련 미커밋 파일:

```text
M  .agents/TEAM_BOARD.md
M  api/routes/master_control.py
M  frontend/src/App.tsx
M  frontend/src/components/GlobalNav.tsx
M  frontend/src/components/KnowledgeHubPanel.tsx
M  frontend/src/components/MasterDataPanel.tsx
M  frontend/src/design/HubShell.tsx
M  frontend/src/design/afs.css
M  frontend/src/lib/closedLoopFetch.ts
M  frontend/src/lib/knowledgeApi.ts
M  tests/test_listing_visibility_gate.py
?? frontend/src/lib/masterDataApi.ts
?? docs/chronicle/handoffs/handoff_2026-08-04_uiux_mdm_codex.md
```

공유 작업 트리에는 위 목록 외에도 다른 세션이 만든 문서·데이터·삭제·수정이 다수 존재한다.

절대 하지 말 것:

- `git reset --hard`
- `git checkout -- .`
- 관련 없는 삭제 파일 복구 또는 정리
- 전체 작업 트리를 한 번에 stage/commit
- 다른 세션의 `api/routes/knowledge_control.py`, 문서 이동, 데이터 변경을 이번 커밋에 혼합

커밋이 필요하면 **이번 인수인계에 명시한 파일만 선별 stage**하고, 먼저 `git diff --cached`로
경계를 확인한다.

---

## 6. 남은 제품 작업 순서

현재 UI/UX 이관 순서:

1. 지식 허브 — 코드 보완 완료, 권한별 래스터 재감사 필요
2. MDM 기준정보 — 코드 이관 완료, 백엔드 회귀·권한별 래스터 재감사 필요
3. 업무표준 — **다음 이관 대상**, 1·2 게이트 확인 후 착수
4. Crosswalk
5. 데이터 거버넌스
6. 조직·권한
7. 에이전트 통제소
8. 스킬 진화·출력양식
9. SW Factory·WBS·Timeline·Preview·HOTL
10. 경영계획·Digital Twin·전사 브리핑·텔레메트리

업무표준으로 바로 넘어가지 말고, 이번 MDM 서버 권한 테스트를 먼저 통과시킨다. 이번에 발견한
결함은 화면 문제가 아니라 **실제 엔터프라이즈 데이터 격리 결함**이므로 우선순위가 더 높다.

---

## 7. 한 문장 재개 지시

> `handoff_2026-08-04_uiux_mdm_codex.md`를 기준으로 먼저 MDM 권한 회귀 테스트 4개 파일을 정상
> Python 환경에서 실행하고, 관리자/일반/익명 읽기 전용 실서버 검증과 1280·1440 화면 감사를
> 마친 뒤에만 UI/UX 이관 3/10 업무표준으로 진행한다.
