# 격리 화면 검증 환경 — 세우는 법·쓰는 법·내리는 법

작성: Claude Code · 2026-09-16. 근거: `CODEX_SINGLE_ENTRY_DECISION_2026-09-16.md`
「격리 기동 절차는 개인 메모리에만 두지 말고 저장소 문서의 정확한 경로를 보고한다」.

⚠️ 이 문서에는 **운영 데이터도 비밀키도 적지 않는다.** 경로·명령·포트·합성 데이터 만드는
법만 적는다.

---

## 0. 왜 이 문서가 필요한가 — 막다른 길 세 개를 먼저 적는다

처음 이 길을 찾는 데 40분 넘게 썼다. 다음 사람이 같은 데서 막히지 않게 **안 되는 것부터** 적는다.

| 시도 | 결과 |
|---|---|
| `scripts/run_local_demo.py` (별도 `demo_data/` 서버) | **폐지됐다.** 실행하면 「별도 demo_data 서버는 폐지됐습니다」를 찍고 종료(exit 2) |
| 환경변수로 데이터 뿌리 바꾸기 | **없다.** `core/paths.py` 가 「환경 변수로 덮을 수 있게 두지 않는다」고 **의도적으로** 막는다 |
| 운영 `data/` 로 서버 기동 | **금지.** 기동만으로 저장소가 스키마를 만든다(쓰기) |

★ 그래서 남는 방법은 하나다 — **워크트리로 `PROJECT_ROOT` 자체를 옮긴다.**
`core/paths.py` 의 `PROJECT_ROOT` 는 그 파일 위치에서 계산되므로, 워크트리의 `core/` 를
쓰면 `DATA_DIR` 도 워크트리의 `data/` 가 된다.

### ⚠️⚠️ 함정 ③ (2026-09-18 실측): **`PROJECT_ROOT` 를 안 따르는 저장소가 있다**

| 저장소 | 뿌리 기준 |
|---|---|
| `data/*.db` 등 | `core/paths.PROJECT_ROOT` — 워크트리를 따라온다 ✔ |
| **게시물 보관소 `library/`** | `core/library_paths._LIBRARY_DIR = "library"` — **프로세스 작업 디렉토리** 기준 ✘ |

런처는 워크트리의 `run.py` 를 **주 트리를 작업 디렉토리로** 실행한다. 그래서 격리 서버가
**게시물만은 운영 `library/` 를 읽고 있었다.** 합성 릴리스를 워크트리에 심었더니 404 가
나서 드러났다(읽기만 했고 쓴 적은 없다 — 운영 `library/` 최신 항목 날짜 불변으로 확인).

★ **작업 디렉토리를 옮기는 껍데기로 띄운다.** 제품 코드는 고치지 않는다.

```python
# <격리경로>/run_isolated.py  — 워크트리에만 두고 커밋하지 않는다
import os, runpy, sys
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE); sys.path.insert(0, HERE)
from core import library_paths, paths
print("[isolated] cwd =", os.getcwd(), "| DATA_DIR =", paths.DATA_DIR,
      "| library =", os.path.abspath(library_paths.library_dir()), flush=True)
assert os.path.abspath(library_paths.library_dir()).lower().startswith(HERE.lower())
runpy.run_path(os.path.join(HERE, "run.py"), run_name="__main__")
```

launch 항목의 `runtimeArgs` 를 `run.py` 대신 **`run_isolated.py`** 로 바꾸고, 기동 로그의
저 세 줄을 **읽어서** 확인한다 — 고지문이 아니라 측정이다.

⚠️ 다른 상대경로 저장소가 더 있는지는 `grep -rn '= "library"\|= "projects"' core/` 로
확인한다(2026-09-18 기준 `library` 하나였다).


### ⚠️⚠️ 함정 ④ (2026-09-19): **기동이 조직 노드를 다시 쓴다**

`run.py` 의 `_apply_installation_settings()` 가 `data/instance.json` 으로 `organization_nodes`
를 **매 기동 다시 쓴다.** 그래서 DB 에 직접 심은 fixture 결속은 **재기동으로 사라진다**
(실측: 배터리 노드의 `dept_id` 가 빈 값으로 돌아갔고, 그때부터 문맥 선택이 403 이었다).

★ 조직 결속은 **양쪽 모두** 적는다 — `seed_ecm` 이 그렇게 하는 이유다.

```
① 부서 → 노드 : org_directory.create_department(..., scope_node_id="<node>")
② 노드 → 부서 : ecm_repository.upsert_node(OrganizationNode(..., dept_id="<dept>"))
③ 기동 보존   : <격리경로>/data/instance.json 의 organization.scope_nodes[].dept_id
```

⚠️ ③ 을 빼면 ①②가 기동 한 번에 지워진다. **운영 `instance.json` 은 건드리지 않는다.**

### ⚠️ 함정 ⑤ (2026-09-19): **SSE 티켓의 범위는 «본문» 이다**

`POST /api/v1/auth/sse-ticket` 은 요청 **헤더의 범위를 일부러 무시**하고 본문의
`scope_node_id` 만 본다(「요청자가 scope 를 지정하지 않는다」는 계약을 지키려는 설계).
헤더로 보내면 티켓이 «전체» 로 발급되어, 좁은 범위에서 **안 와야 할 이벤트가 온다.**
그것을 제품 결함으로 읽으면 없는 결함을 쫓게 된다(실제로 한 번 그랬다).

```js
// 관찰 연결을 여는 단 하나의 방법 — 범위는 반드시 본문
const r = await fetch(BASE + '/api/v1/auth/sse-ticket', { method:'POST',
  headers:{ 'Content-Type':'application/json', 'X-Session-Token': token },
  body: JSON.stringify({ scope_node_id: scope }) });
```

⚠️ 음성(안 온다) 시험은 **반드시 같은 도구의 양성 대조**와 짝지어 적는다. 「아무것도 안 왔다」
는 계측기가 죽어도 똑같이 나온다.

### ⚠️ 함정 ⑥ (2026-09-19): **화면 관측은 «고유 문구» 로 판정한다**

`body.innerText.slice(0, 600)` 이나 「첫 `[role=dialog]`」로 열림을 판정하면 틀린다 — 실제로
두 번 틀렸다(대화상자 본문이 600자 뒤에 있었고, `HubDialog` 의 머리말을 전환 창으로 오인).

```
전환 창   본문 고유 문구 「회사·조직 선택」
문맥 칩   button.afs-context · aria-label「회사 문맥 전환」 · elementFromPoint 로 가림 확인
거절 화면 「현재 회사·권한에서 프로젝트를 찾을 수 없습니다.」
```

---

## 1. 세우기

### 1-1. 격리 워크트리

```bash
git worktree add /c/<격리경로> HEAD
```

`data/` 에 추적 파일 몇 개는 딸려 오지만 **DB 는 없다**(gitignore). 그래서 격리된다.

⚠️ 미커밋 변경은 워크트리에 **없다.** 검증에 필요한 **서버 쪽** 변경 파일만 복사한다.
프런트는 주 트리에서 띄우므로 복사하지 않는다.

```bash
cp api/routes/<바꾼 파일>.py  /c/<격리경로>/api/routes/
cp core/<바꾼 파일>.py        /c/<격리경로>/core/
cp .env                       /c/<격리경로>/.env      # 있을 때만
```

### 1-2. `.claude/launch.json` 항목 두 개

```json
{ "name": "<이름>-isolated",
  "runtimeExecutable": "venv/Scripts/python.exe",
  "runtimeArgs": ["C:/<격리경로>/run.py", "--port", "8086"],
  "port": 8086, "url": "http://127.0.0.1:8086" }
```

★ **주 트리의 venv 로 «워크트리의» `run.py` 를 실행한다.** 파이썬이 `sys.path[0]` 을
스크립트 위치로 잡으므로 `core`·`api` 가 워크트리에서 온다.
⚠️ 경로는 **슬래시**로 쓴다. JSON 안의 `"\\r"` 같은 이스케이프가 경로를 깨뜨린 적이 있다.

프런트는 다른 세션의 `.env.local`(8080)·`.env.verify.local`(8083)을 **건드리지 않도록**
전용 모드를 쓴다.

```
frontend/.env.isolated.local     →  VITE_API_BASE_URL=http://127.0.0.1:8086
launch.json  "frontend-isolated" →  npm run dev -- --port 5181 --strictPort --mode isolated
```

⚠️ CORS 는 `main.py` 가 개발 포트 **5173~5199** 를 허용한다. 그 범위 안에서 고른다.

### 1-3. 합성 데이터 — 함정 둘이 여기 있다

```bash
cd /c/<격리경로> && <주트리>/venv/Scripts/python.exe scripts/seed_starter_data.py --check   # 먼저 확인
cd /c/<격리경로> && <주트리>/venv/Scripts/python.exe scripts/seed_starter_data.py           # 키트·판·기준선
```

⚠️⚠️ **함정 ①: 이 스크립트는 조직·사용자를 만들지 않는다.** 머리말이 「운영에는 이미 조직이
있다. 그것을 쓴다」고 못박는다. 빈 뿌리에서는 **사용자 0명**이 된다.

⚠️⚠️ **함정 ②: 폐지된 `run_local_demo._org()` 는 앱이 «안 읽는» 파일에 쓴다.**
그 함수는 `OrgDirectory(db_path=TARGET_ROOT/"org.db")` 를 만드는데, 제품은 싱글턴
`core.org_directory.org_directory`(= `<뿌리>/master/master.db`)를 읽는다. 그래서 「심었는데
0명」이 된다.

★ **제품 싱글턴으로 직접 심는다.** 부서는 `seed_starter_data` 가 만든 것을 쓴다.

```python
sys.path.insert(0, r"C:\<격리경로>")
from core import paths
assert paths.DATA_DIR.lower().startswith(r"c:\<격리경로>")      # 격리 확인
from core.org_directory import org_directory as org
DEPT = org.list_departments()[0]["dept_id"]
org.upsert_user("<id>", "<이름>", primary_dept_id=DEPT, is_admin=True, actor="isolated-verify-seed")
org.set_user_roles("<id>", {DEPT: "manager"}, actor="isolated-verify-seed")
```

⚠️ 계정은 **RFC 2606 예약 도메인(`.invalid`)** 또는 저장소의 기존 예시 계정 규약을 따른다.

### 1-4. ★ 조직 강제를 켠다

```python
import core.scope_policy as sp
sp.set_org_enforce(True, actor="isolated-verify-seed", reason="격리 검증에서 권한 경계를 보이게")
```

⚠️ 안 켜면 `resolve_scope` 가 **전원 무제한**을 돌려준다. 그 상태의 검증은 「전부 되는
것처럼」 끝나고, 권한 경계를 하나도 못 본다.

### 1-4-b. ⚠️⚠️ 순서 — **서버를 «먼저» 한 번 띄운다**

ECM 의 `organization_nodes`·`enterprise_entities` 는 **서버가 처음 뜰 때** 만들어진다.
파종 스크립트가 만들지 «않는다».

★ 그래서 순서가 이렇다. 뒤집으면 초안을 만들 때 경계(테넌트·루트·범위 노드)를 못 찾는다
(실제로 `StopIteration` 으로 멈췄다).

```
① worktree · 파일 복사 · launch 항목
② seed_starter_data.py          (키트·판·기준선·부서)
③ 사용자 + org_enforce          (제품 싱글턴으로)
④ ★ 서버를 띄운다 → ECM 노드가 생긴다
⑤ 초안 만들기                   (④의 노드로 경계를 구성한다)
⑥ 프런트를 띄운다 → 사람이 로그인
```

### 1-5. 검증용 초안(B3 blueprint) 만들기

`advisor_v2_*` 테이블은 **새 뿌리에 아예 없다**(운영에도 0건). 화면을 보려면 만들어야 한다.
제품 서비스로 만든다 — 그래야 진짜 digest·판본·context_key 가 붙는다.

```python
from core.enterprise_context.process_schema import ProcessBoundary
from core.studio_drafts import StudioDraftService
boundary = ProcessBoundary(tenant_id=<테넌트>, context_root_id=<루트노드>,
                           entity_mode="REAL", scope_node_id=<범위노드>)
context = {"tenant_id": ..., "entity_mode": "REAL", "scope_node_id": ..., "context_root_id": ...}
StudioDraftService().save(boundary=boundary, actor=<id>, context=context, draft_id="",
    expected_revision=0, expected_digest="", patch=[...], client_request_id="...",
    process_selection=None)
```

테넌트·노드는 격리 뿌리의 ECM 에서 읽는다:

```python
from core.enterprise_context.process_configuration import ProcessConfigurationService
with ProcessConfigurationService().transaction() as conn:
    conn.execute("SELECT node_id, node_type, dept_id FROM organization_nodes WHERE status='ACTIVE'")
```

⚠️ patch 의 `request_options.deliverable_type` 을 넣어야 초안 링크가 열린다 — 그 값이 없으면
제품이 **일부러 막는다**(종류를 추측하지 않는다).

---

## 2. 격리를 «증명» 하기 — 고지문이 아니라 측정

```bash
ls -la /c/<격리경로>/data/*.db     # 기동 직후 «새로» 생겨야 한다
ls -lt data/*.db                   # 운영 뿌리는 «날짜가 그대로» 여야 한다
```

이 두 줄을 보고하지 않은 격리 주장은 받지 않는다.

---

## 3. 로그인 — 401 이 나면 «비밀번호부터 의심하지 않는다»

`api/routes/auth_control.login` 은 이렇다.

```python
ok = bool(_known_user(uid)) and auth_store.verify(uid, req.password)
```

열거 방지를 위해 **「아이디가 없다」와 「비밀번호가 틀렸다」를 같은 문구**로 답한다.
그래서 화면만 보면 늘 비밀번호 문제처럼 보인다.

★ **판별법**: `verify()` 는 불리기만 하면 `<뿌리>/data/auth.db` 를 만든다.
시도한 뒤에도 그 파일이 **없으면 계정 부재**다(verify 까지 가지도 못했다는 뜻).

⚠️ 비밀번호는 `core/auth.py` 의 공통 초기값이며 **AI 가 입력하지 않는다.** 사람이 친다.
⚠️ 앱의 Browser 패널이 **숨겨져 있으면** 사람 눈에 로그인 창이 안 보인다. AI 는 그 패널을
열 수 없다(`show_pane` 은 diff·파일·터미널·PR·작업·계획만 연다).

---

## 4. 쓰기 — 화면 검증 순서

로그인 뒤 **회사·조직을 먼저 고른다.** 안 고르면 서버가 `PROCESS_CONTEXT_REQUIRED`(422)로
막는다(정상 동작이다).

```
?space=build&target=draft&draft_kind=blueprint&draft=<id>&revision=<N>
```

---

## 5. 내리기·되돌리기

```bash
# 서버 중지 → 워크트리 제거
git worktree remove /c/<격리경로> --force && git worktree prune
```

그리고 **임시로 더한 것을 되돌린다** — `launch.json` 의 두 항목, `frontend/.env.isolated.local`.
⚠️ 없어진 경로를 가리키는 launch 항목을 남기면 다음 사람이 그 함정에 빠진다.
⚠️ **다른 세션의 워크트리는 건드리지 않는다**(`git worktree list` 로 먼저 확인).

---

## 6. 이 환경으로 «증명할 수 없는» 것

- 운영 데이터의 실제 내용·규모에서만 드러나는 문제
- 실제 인증·SSO 경로(여기서는 공통 초기 비밀번호를 사람이 친다)
- 다중 사용자 동시성

그런 것은 여기서 초록이어도 **초록이라고 적지 않는다.**
