"""프로젝트 계약 합산기 — 태스크마다 쓴 초안을 **계약 하나**로 모은다.

[I-4 4c-1] `HostContractCompiler` 는 `task_id` 를 받는 **태스크 단위** 컴파일러다.
그런데 게이트와 상태(`ProjectState` 5.2.0)는 **프로젝트당 계약 하나**를 전제한다.
그대로 이으면 이렇게 된다:

```text
APP 태스크 A 계약 작성
→ APP 태스크 B 계약 작성
→ B 계약이 프로젝트 계약을 대체
→ A 데이터셋 계약 «소실»
```

그리고 A 의 앱은 계약에 없는 데이터셋을 쓰는 앱이 된다. 그 상태는 오류를 내지
않는다 — B 를 만든 사람은 A 를 모르기 때문이다.

## 합치지 않는 것

★★★ **충돌은 자동으로 병합하지 않는다.** 같은 `dataset_key` 를 두 태스크가 서로
  다르게 선언했다면 그것은 두 사람이 같은 이름으로 다른 것을 뜻한 것이고, 합집합을
  만들면 **아무도 의도하지 않은 세 번째 것**이 된다. 권한(`allowed_actions`)에서는
  합집합이 곧 «둘 중 넓은 쪽으로 조용히 넓히기» 다. → `BLOCKED`.

## 삭제된 태스크

WBS 에서 사라진 태스크의 데이터셋은 **새 합산에서 즉시 제외**한다. 지문이 바뀌므로
재승인을 지난다.
⚠️ 물리 데이터셋·레코드·이전 릴리스 바인딩은 **건드리지 않는다.** 계약에서 빠지는
  것과 데이터를 지우는 것은 다른 일이고, 후자는 별도의 명시적 retire 절차에서만
  일어난다 — 계약을 고쳤다고 업무 데이터가 사라지면 아무도 계약을 못 고친다.

⚠️⚠️ 「같은 데이터셋인가」의 판정은 `app_runtime_contract.semantic_material` 을
  **그대로 빌려 쓴다.** 여기서 다시 구현하면 [I-4 2.2a] 처럼 두 정의가 갈리고,
  갈린 날 「지문은 같은데 합산은 충돌」 같은 설명 불가능한 상태가 나온다.
  덕분에 `label`·`purpose` 처럼 지문에 안 들어가는 문구는 충돌도 아니다 — 문구가
  다르다고 막으면 사람이 문구를 맞추느라 의미를 안 보게 된다.
"""
import re
from typing import Any, Dict, List, NamedTuple, Tuple

from core import app_runtime_contract as arc
from core import wbs_artifact_kind as ak

#: 충돌 종류.
CONFLICT_DATASET = "DATASET"
CONFLICT_APP_CLASS = "APP_CLASS"
CONFLICT_INTENT = "INTENT"


class AggregateResult(NamedTuple):
    """합산 결과.

    `blocked` 가 참이면 **계약을 만들지 않는다** — 초안만 돌려주고 컴파일은 하지
    않는다. 반쪽 계약을 만들어 두면 그것이 승인 대상이 되기 때문이다."""
    draft: Dict[str, Any]
    errors: List[str]
    conflicts: List[Dict[str, Any]]
    included_task_ids: List[str]
    excluded_task_ids: List[str]
    missing_task_ids: List[str]

    @property
    def blocked(self) -> bool:
        return bool(self.errors or self.conflicts)


def _dataset_identity(ds: Any) -> str:
    """이 데이터셋의 **정체**. 이름이 아니라 `dataset_key` 다."""
    d = ds if isinstance(ds, dict) else {}
    return str(d.get("dataset_key", "") or d.get("name", "")).strip()


def _dataset_semantics(ds: Any) -> Dict[str, Any]:
    """지문이 보는 것과 **같은 눈**으로 데이터셋을 본다(정의를 빌려 쓴다)."""
    material = arc.semantic_material({"datasets": [ds if isinstance(ds, dict) else {}],
                                      "app_class": "", "capability_intents": []})
    return material["datasets"][0]


def _intent_identity(intent: Any) -> Tuple[str, str]:
    i = intent if isinstance(intent, dict) else {}
    return (str(i.get("requirement_ref", "")).strip(),
            str(i.get("capability", "")).strip())


def _intent_semantics(intent: Any) -> Dict[str, str]:
    i = intent if isinstance(intent, dict) else {}
    #: `reason` 은 설명 문구다 — 지문에도 안 들어간다. 여기서도 충돌 근거가 아니다.
    return {"status": str(i.get("status", "")).strip(),
            "user_decision": str(i.get("user_decision", "")).strip()}


_FR_RE = re.compile(r"\bFR-\d{2,3}\b")


def _task_requirements(task: Any) -> set:
    """태스크가 **자기 것이라고 말한 요구들**. 제목·목표·범위에서 FR-ID 를 뽑는다.

    ⚠️ `out_of_scope` 는 보지 않는다 — 거기 적힌 것은 「이 태스크가 안 하는 일」이다.
      섞으면 하지 않기로 한 것까지 계약에 요구하게 된다."""
    t = task if isinstance(task, dict) else {}
    parts = [str(t.get("title", "")), str(t.get("goal", ""))]
    scope = t.get("scope")
    if isinstance(scope, list):
        parts += [str(x) for x in scope]
    return set(_FR_RE.findall(" ".join(parts)))


def _coverage_errors(tasks_in_scope: Any, intents: Any) -> list:
    """★★★ [2026-08-27 실측] **만들 수 없는 요구가 말없이 사라지면 안 된다.**

    ## ⚠️⚠️ 무엇이 있었나

    `CRM002` 의 RFP 에 `FR-008`(사용자 권한 제어)이 **Must** 로 있었고 WBS 에 그 태스크도
    생겼다. 그런데 계약에는 —

        FR-009 (파일 첨부)  → `unsupported_requirements` 에 기록
                              (「데이터 평면에 바이너리가 없다」· user_decision=WAIT)
        FR-008 (권한 제어)  → **능력에도 없고 미지원 목록에도 없다**

    아무도 「이 요구는 만들 수 없습니다」라고 말하지 않았다. 요구가 **증발**했다.
    만들 수 없는 것을 말없이 지우는 것은, 만들었다고 말하는 것 다음으로 나쁘다 —
    사용자는 그것이 만들어지는 줄 알고 인수한다.

    ★ 그래서 **집합 비교**로 막는다. 정규식 판정이 아니라 「태스크가 자기 것이라 말한
      FR」과 「계약이 다룬 FR」의 차집합이므로 오탐이 없다.
    ⚠️ 능력으로 다루든 미지원으로 적든 **둘 다 «다뤘다»** 다. 강제하는 것은 「만들라」가
      아니라 **「말하라」** 이다 — 못 만들면 못 만든다고 적으면 통과한다.
    """
    covered = {str((i or {}).get("requirement_ref", "")).strip()
               for i in (intents or []) if isinstance(i, dict)}
    out = []
    for t in (tasks_in_scope or []):
        tid = str((t or {}).get("task_id", "")).strip()
        missing_fr = sorted(_task_requirements(t) - covered)
        if missing_fr:
            out.append(
                f"{tid}: 계약이 {', '.join(missing_fr)} 를 다루지 않습니다 — 만들 수 "
                f"있으면 `capability_intents` 에 능력으로, **만들 수 없으면 그 사실을** "
                f"적으십시오(못 만드는 능력 이름 + `user_decision`). 말없이 빠지면 "
                f"사용자는 그 요구가 만들어지는 줄 알고 인수합니다.")
    return out


def aggregate(tasks: Any, drafts: Any) -> AggregateResult:
    """WBS 와 태스크별 초안에서 **프로젝트 초안 하나**를 만든다. 던지지 않는다.

    · `tasks` — WBS 태스크 목록(정규화 전이어도 된다. 여기서 정규화해 판정한다)
    · `drafts` — `{task_id: 초안}`. 계약 대상이 아닌 태스크의 초안은 **무시한다**.

    ⚠️ 계약 대상인데 초안이 없으면 «데이터셋 0개» 로 넘어가지 않는다. 그것은
      「데이터를 안 쓰는 앱」과 「아직 안 쓴 계약」을 같게 만든다 — 앞은 유효한
      계약이고 뒤는 미완성이다."""
    required = ak.contract_required_task_ids(tasks)
    normalized = ak.normalize_tasks(tasks)
    all_ids = [str(t.get("task_id", "")) for t in normalized]
    excluded = [tid for tid in all_ids if tid not in required]

    draft_map = drafts if isinstance(drafts, dict) else {}
    errors: List[str] = []
    conflicts: List[Dict[str, Any]] = []
    missing: List[str] = []
    included: List[str] = []

    #: 정체 → (처음 선언한 태스크, 원본, 의미)
    datasets: Dict[str, Tuple[str, Dict[str, Any], Dict[str, Any]]] = {}
    intents: Dict[Tuple[str, str], Tuple[str, Dict[str, Any], Dict[str, str]]] = {}
    app_class_by_task: Dict[str, str] = {}

    #: ★ 태스크를 **정렬해** 돈다. 그래야 「먼저 선언한 쪽」이 입력 순서가 아니라
    #:   내용으로 정해지고, WBS 순서를 바꿔도 결과가 같다.
    for tid in sorted(required):
        raw = draft_map.get(tid)
        if not isinstance(raw, dict) or not raw:
            missing.append(tid)
            continue
        included.append(tid)

        app_class = str(raw.get("app_class", "")).strip()
        if app_class:
            app_class_by_task[tid] = app_class

        for ds in (raw.get("datasets") or []):
            key = _dataset_identity(ds)
            if not key:
                errors.append(f"{tid}: 이름도 `dataset_key` 도 없는 데이터셋이 있습니다 — "
                              f"정체를 모르는 것은 합산할 수 없습니다.")
                continue
            sem = _dataset_semantics(ds)
            if key not in datasets:
                datasets[key] = (tid, ds if isinstance(ds, dict) else {}, sem)
                continue
            first_tid, _, first_sem = datasets[key]
            if first_sem != sem:
                #: ⚠️ 합치지 않는다. 사람이 어느 쪽이 맞는지 정해야 한다.
                conflicts.append({
                    "kind": CONFLICT_DATASET, "dataset_key": key,
                    "tasks": [first_tid, tid],
                    "detail": (f"데이터셋 «{key}» 를 «{first_tid}» 와 «{tid}» 가 다르게 "
                               f"선언했습니다 — 스키마·행동·역할·출처·중복입력 중 "
                               f"무엇이 맞는지는 사람이 정해야 합니다(자동 병합하지 "
                               f"않습니다)."),
                    "differences": sorted(k for k in set(first_sem) | set(sem)
                                          if first_sem.get(k) != sem.get(k)),
                })

        for it in (raw.get("capability_intents") or []):
            ident = _intent_identity(it)
            if ident == ("", ""):
                continue
            sem = _intent_semantics(it)
            if ident not in intents:
                intents[ident] = (tid, it if isinstance(it, dict) else {}, sem)
                continue
            first_tid, _, first_sem = intents[ident]
            if first_sem != sem:
                conflicts.append({
                    "kind": CONFLICT_INTENT,
                    "requirement_ref": ident[0], "capability": ident[1],
                    "tasks": [first_tid, tid],
                    "detail": (f"요구 «{ident[0]}/{ident[1]}» 의 판정·결정이 «{first_tid}» "
                               f"와 «{tid}» 에서 다릅니다."),
                })

    if missing:
        errors.append(
            "계약 대상 태스크인데 계약 초안이 없습니다: " + ", ".join(missing)
            + " — 「데이터를 안 쓰는 앱(데이터셋 0개)」과 「아직 계약을 안 쓴 태스크」는 "
              "다릅니다. Tech Lead 가 초안을 만들어야 합니다.")

    #: ★★★ [2026-08-27] **요구가 말없이 사라지지 않게 한다.**
    #: ⚠️ 초안이 아예 없는 태스크는 위 `missing` 이 이미 말했으므로 여기서 또 말하지
    #:   않는다 — 같은 사실을 두 번 말하면 사람은 두 가지 문제로 읽는다.
    _in = set(included)
    _scoped = [t for t in normalized if str((t or {}).get("task_id", "")) in _in]
    #: `intents` 는 `{(ref, cap): (tid, 원문, 의미)}` 다 — 원문만 넘긴다.
    errors.extend(_coverage_errors(_scoped, [v[1] for v in intents.values()]))

    classes = sorted(set(app_class_by_task.values()))
    if len(classes) > 1:
        conflicts.append({
            "kind": CONFLICT_APP_CLASS, "app_classes": classes,
            "tasks": sorted(app_class_by_task),
            "detail": (f"태스크마다 `app_class` 가 다릅니다({classes}) — 프로젝트 계약은 "
                       f"하나이므로 분류도 하나여야 합니다. 넓은 쪽으로 자동 승격하지 "
                       f"않습니다(그것은 조용한 권한 확대입니다)."),
        })

    draft: Dict[str, Any] = {
        "app_class": classes[0] if len(classes) == 1 else "",
        #: ★ 정렬해 담는다. 지문은 어차피 정렬하지만, **계약 본문 자체도** 결정론적
        #:   이어야 사람이 두 릴리스를 눈으로 비교할 수 있다.
        "datasets": [datasets[k][1] for k in sorted(datasets)],
        "capability_intents": [intents[k][1] for k in sorted(intents)],
    }
    return AggregateResult(draft=draft, errors=errors, conflicts=conflicts,
                           included_task_ids=included, excluded_task_ids=sorted(excluded),
                           missing_task_ids=missing)


def compile_project_contract(tasks: Any, drafts: Any, *, project_id: str,
                             previous: Any = None):
    """합산 → 컴파일. 합산이 막히면 **컴파일하지 않는다.**

    ⚠️ 막힌 채로 컴파일하면 「일부 태스크만 담긴 계약」이 `COMPILED` 상태로 나오고,
      그것은 승인 가능한 대상이 된다. 사람은 그 계약이 전부라고 믿는다.

    반환은 `host_contract_compiler.CompileResult` 와 같은 모양이되, 합산 단계에서
    막히면 `errors` 에 사유가 담긴 `DRAFT` 계약을 돌려준다."""
    from core import host_contract_compiler as hcc

    agg = aggregate(tasks, drafts)
    if agg.blocked:
        reasons = list(agg.errors) + [c["detail"] for c in agg.conflicts]
        empty = hcc.compile_contract({}, project_id=project_id, task_id="")
        return hcc.CompileResult(contract=empty.contract, errors=reasons,
                                 pending_decisions=[], fingerprint_changed=False), agg

    #: `task_id=""` — 이 계약의 주인은 태스크가 아니라 **프로젝트**다.
    return hcc.compile_contract(agg.draft, project_id=project_id, task_id="",
                                previous=previous if isinstance(previous, dict) else None), agg
