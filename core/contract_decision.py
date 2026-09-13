"""★★★ 컴파일러가 **사람에게 넘긴 결정**을 사람이 실제로 내릴 수 있게 한다. (2026-08-26)

## ⚠️⚠️ 무엇이 있었나 — 「사람이 정해야 합니다」인데 정할 방법이 없었다

계약 컴파일러는 스스로 못 정하는 두 가지를 **사람에게 넘긴다.** 실측에서 둘 다 나왔고,
둘 다 **막다른 길**이었다.

    ① 지원되지 않는 능력의 처리
       「사용자 결정이 필요한 요구가 …(지원 대기) 있습니다」
       → `pending_decisions` 를 **만드는 곳만 있고 읽는 곳이 0곳**이었다(전수 확인).

    ② 같은 데이터셋을 두 태스크가 다르게 선언
       「데이터셋 «x» 를 «A» 와 «B» 가 다르게 선언했습니다 — … 사람이 정해야 합니다
        (자동 병합하지 않습니다)」
       → 고를 화면도 API 도 없었다.

★ 합산기의 거절은 **옳다.** 자동 병합은 조용한 권한 확대다. 잘못된 것은 「정해야 한다」고
  말해 놓고 정할 자리를 안 준 것이다. 통제가 아니라 교착이다.

## 결정은 **초안**에 착지한다

컴파일러의 입력은 `contracts/drafts/<task_id>.json` 이다. 그러므로 결정도 거기에 남아야
다음 컴파일이 그것을 본다. 별도 «결정 표» 를 만들어 컴파일러가 안 보면, 그것이 바로
「만들어 두고 부르는 곳이 없다」의 아홉 번째 반복이다.

⚠️ 결정 자체는 **원장에도** 남는다. 초안 파일은 롤백·재생성으로 바뀔 수 있고, 「누가 언제
  무슨 근거로 이 능력을 줄이기로 했나」는 덮어쓸 수 없는 곳에 있어야 한다.
"""
from __future__ import annotations

import json
import os
import copy
import hashlib
import re
import stat
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Tuple

from core import app_runtime_contract as arc
from core import project_contract_aggregator as aggregator

#: 원장 주체 유형. ★ 「무엇을 결정했는가」를 여기서 못박는다 — 행위자 하나의 아무 결정으로
#:   다른 대상이 통과되지 않게 하는 것이 이 저장소의 규칙이다(`decision_ledger` 머리말).
SUBJECT_CAPABILITY = "app_contract_capability"
SUBJECT_DATASET = "app_contract_dataset"


class DecisionError(ValueError):
    """결정을 적용할 수 없다. **사유가 사람이 읽을 말이어야 한다** — 이 예외는 그대로
    화면에 나간다."""


# ══════════════════════════════════════════════════════════════════════════
# 무엇이 사람을 기다리는가
# ══════════════════════════════════════════════════════════════════════════

def pending_items(tasks: Any, drafts: Dict[str, Any]) -> Dict[str, Any]:
    """지금 사람이 정해야 하는 것들. **컴파일러와 같은 판정기를 쓴다.**

    ⚠️ 여기서 판정을 다시 계산하면 화면이 보여 주는 것과 컴파일러가 막는 것이 갈린다 —
      이 저장소가 이미 두 번 겪은 결함이다(게이트↔컴파일러 범위 불일치).
    """
    agg = aggregator.aggregate(tasks, drafts)

    caps: List[Dict[str, Any]] = []
    seen: set = set()
    for tid, raw in sorted((drafts or {}).items()):
        if tid not in agg.included_task_ids or not isinstance(raw, dict):
            continue
        for it in (raw.get("capability_intents") or []):
            if not isinstance(it, dict):
                continue
            cap = str(it.get("capability", "")).strip()
            status, reason = arc.decide(cap)
            if arc.is_buildable(status) or str(it.get("user_decision", "")).strip():
                continue
            key = (tid, cap)
            if key in seen:
                continue
            seen.add(key)
            caps.append({
                "task_id": tid,
                "intent_id": str(it.get("intent_id", "")),
                "capability": cap,
                "requirement_ref": str(it.get("requirement_ref", "")),
                "status": status,
                "status_label": arc.STATUS_LABEL.get(status, status),
                "reason": reason,
                #: ★ 고를 수 있는 것을 **함께** 준다. 목록 없이 「정하라」고 하면 사람은
                #:   무엇을 적어야 하는지 모르고, 그 화면은 다시 막다른 길이 된다.
                "choices": list(arc.allowed_decisions(status)),
            })

    conflicts = [c for c in agg.conflicts
                 if c.get("kind") == aggregator.CONFLICT_DATASET]
    for c in conflicts:
        #: ⚠️ 「무엇이 다른가」를 반드시 함께 준다. 이름만 주면 사람은 두 초안을 손으로
        #:   열어 비교해야 하고, 그러면 아무도 안 고른다.
        c.setdefault("differences", [])
        c["choices"] = list(c.get("tasks") or [])

    return {
        "capability_decisions": caps,
        "dataset_conflicts": conflicts,
        #: 나머지 오류는 사람이 «고르는» 것이 아니라 에이전트가 고쳐야 하는 것이다.
        #: 섞어 보여 주면 사람이 못 고치는 것을 붙들고 있게 된다.
        "other_errors": list(agg.errors),
        "pending": bool(caps or conflicts),
    }


# ══════════════════════════════════════════════════════════════════════════
# 결정을 초안에 남긴다
# ══════════════════════════════════════════════════════════════════════════

def apply_capability_decision(draft: Dict[str, Any], *, capability: str,
                              decision: str) -> Tuple[Dict[str, Any], str]:
    """능력 하나의 `user_decision` 을 정한다. `(바뀐 초안, 사람이 읽을 요약)`.

    ⚠️⚠️ **상태가 허용하는 결정만 받는다.** `arc.allowed_decisions` 밖의 값을 넣으면
      컴파일러가 그 자리에서 버리고(`user_decision = ""`), 결정은 원장에만 남아
      「분명히 정했는데 또 물어본다」가 된다 — 사람은 시스템을 믿지 않게 된다.
    ★ 금지(`PROHIBITED`) 능력에 `REQUEST_HOST_FEATURE` 를 넣는 경로가 여기서 막힌다.
    """
    cap = (capability or "").strip()
    dec = (decision or "").strip().upper()
    if not cap:
        raise DecisionError("어떤 능력에 대한 결정인지 지정해야 합니다.")

    status, _reason = arc.decide(cap)
    if arc.is_buildable(status):
        raise DecisionError(
            f"«{cap}» 은 이미 지원되는 능력입니다 — 고를 것이 없습니다.")
    allowed = arc.allowed_decisions(status)
    if dec not in allowed:
        raise DecisionError(
            f"«{cap}»({arc.STATUS_LABEL.get(status, status)}) 에서 고를 수 있는 것은 "
            f"{list(allowed)} 입니다 — «{dec}» 는 받을 수 없습니다.")

    # Keep the CAS snapshot immutable while constructing a proposed decision.
    intents = copy.deepcopy(draft.get("capability_intents") or [])
    hit = False
    for it in intents:
        if isinstance(it, dict) and str(it.get("capability", "")).strip() == cap:
            it["user_decision"] = dec
            hit = True
    if not hit:
        raise DecisionError(f"이 초안에 «{cap}» 요구가 없습니다 — 대상을 다시 확인하십시오.")

    out = dict(draft)
    out["capability_intents"] = intents
    return out, f"«{cap}» → {dec}"


def apply_dataset_resolution(drafts: Dict[str, Any], *, dataset_key: str,
                             winner_task_id: str) -> Tuple[Dict[str, Dict[str, Any]], str]:
    """충돌한 데이터셋 선언을 **한쪽으로 통일**한다. `(바뀐 초안들, 요약)`.

    ★ 이긴 태스크의 선언을 **통째로 복사**한다. 칸을 골라 합치지 않는다 — 그것이 곧
      「자동 병합」이고, 합산기가 거절한 바로 그 행위다. 사람이 고른 것은 「어느 선언이
      맞는가」이지 「어떻게 섞을까」가 아니다.
    ⚠️ 진 쪽 초안의 **다른 데이터셋은 건드리지 않는다.** 충돌한 것 하나만 맞춘다.
    """
    key = (dataset_key or "").strip()
    win = (winner_task_id or "").strip()
    if not key or not win:
        raise DecisionError("어느 데이터셋을 어느 태스크 기준으로 맞출지 지정해야 합니다.")

    src = (drafts or {}).get(win)
    if not isinstance(src, dict):
        raise DecisionError(f"«{win}» 의 계약 초안을 찾지 못했습니다.")

    winning = None
    for ds in (src.get("datasets") or []):
        if isinstance(ds, dict) and aggregator._dataset_identity(ds) == key:
            winning = ds
            break
    if winning is None:
        raise DecisionError(f"«{win}» 초안에 데이터셋 «{key}» 가 없습니다.")

    changed: Dict[str, Dict[str, Any]] = {}
    for tid, raw in (drafts or {}).items():
        if tid == win or not isinstance(raw, dict):
            continue
        datasets = list(raw.get("datasets") or [])
        touched = False
        for i, ds in enumerate(datasets):
            if isinstance(ds, dict) and aggregator._dataset_identity(ds) == key:
                if ds != winning:
                    datasets[i] = json.loads(json.dumps(winning, ensure_ascii=False))
                    touched = True
        if touched:
            out = dict(raw)
            out["datasets"] = datasets
            changed[tid] = out

    if not changed:
        raise DecisionError(
            f"데이터셋 «{key}» 에서 «{win}» 과 다르게 선언한 태스크가 없습니다 — "
            f"이미 정리되었거나 대상을 잘못 지정했습니다.")
    return changed, f"데이터셋 «{key}» 를 «{win}» 기준으로 통일({', '.join(sorted(changed))})"


# Server-only generations/overlays: never part of runtime canonical material or
# the LLM draft schema. Current project authority and command guard are external.
_ROUND_META = "_decision_rounds.json"
_ROUND_ANCHOR = ".decision_rounds_required"
_ROUND_LOCK = ".decision_rounds.lock"
_SHA = re.compile(r"[0-9a-f]{64}")
_UUID = re.compile(r"[0-9a-f]{32}")
_TASK = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,159}")


class DecisionRoundError(DecisionError):
    def __init__(self, reason_code, message, status_code=409, *, event_id="", decision_request_id=""):
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code
        self.event_id = event_id
        self.decision_request_id = decision_request_id


def _round_error(message, code="DECISION_ROUND_INTEGRITY", status=503):
    return DecisionRoundError(code, message, status)


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _decode(raw):
    value = json.loads(raw, object_pairs_hook=_no_duplicates,
                       parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    if not isinstance(value, dict):
        raise ValueError("JSON object required")
    return value


def _safe_path(path):
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise _round_error("결정 파일의 링크 경로를 사용할 수 없습니다.")


def _workspace(workspace_root):
    if not isinstance(workspace_root, (str, os.PathLike)) or not str(workspace_root).strip():
        raise _round_error("서버 workspace가 필요합니다.", "DECISION_ROUND_INPUT", 422)
    workspace = Path(os.path.abspath(workspace_root))
    _safe_path(workspace)
    return workspace


def _read_bytes(path):
    _safe_path(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise _round_error("결정 파일이 일반 파일이 아닙니다.")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read()
    after = path.stat()
    signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
    if signature(before) != signature(opened) or signature(opened) != signature(after):
        raise _round_error("읽는 동안 결정 파일이 변경됐습니다.", "DECISION_ROUND_STALE", 409)
    return raw


def _atomic_bytes(path, raw):
    _safe_path(path)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        _safe_path(path)
        os.replace(temporary, path)
        if _read_bytes(path) != raw:
            raise _round_error("결정 파일 저장 후 확인에 실패했습니다.")
    finally:
        if temporary.exists() and not temporary.is_symlink():
            temporary.unlink()  # Only this call's exclusive temporary.


def _write_meta(path, doc):
    body = {key: value for key, value in doc.items() if key != "checksum"}
    _atomic_bytes(path, _canonical({**body, "checksum": _digest(body)}))


def _read_meta(path):
    doc = _decode(_read_bytes(path))
    checksum = doc.pop("checksum", None)
    if checksum != _digest(doc):
        raise _round_error("서버 결정 메타데이터 무결성을 확인할 수 없습니다.")
    return doc


def save_draft_source(workspace_root, task_id, draft, *, require_metadata=False):
    """Legacy stays legacy; only a trusted producer's explicit opt-in starts a
    managed workspace. Existing managed metadata is always verified. A v2 caller
    must pass require_metadata=True, never infer legacy from absent markers.

    Managed saves get a NEW UUID, including identical content. WRITING precedes
    replacement; interruption fails closed. Existing unversioned files require
    a separate whole-workspace migration, not an implicit one-file conversion.
    """
    if not isinstance(draft, dict):
        raise TypeError("계약 초안은 객체여야 합니다.")
    tid = str(task_id or "").strip()
    if not _TASK.fullmatch(tid):
        raise _round_error("유효한 task ID가 필요합니다.", "DECISION_ROUND_INPUT", 422)
    # Preserve the previous text writer's formatting/platform newlines exactly.
    raw = json.dumps(draft, ensure_ascii=False, indent=2, allow_nan=False).replace("\n", os.linesep).encode("utf-8")
    workspace = _workspace(workspace_root)
    try:
        with _workspace_lock(workspace):
            directory = workspace / "contracts" / "drafts"
            _safe_path(directory)
            directory.mkdir(parents=True, exist_ok=True)
            doc = _registry(workspace, required=False)
            if doc is None:
                if not require_metadata:
                    path = directory / (tid + ".json")
                    _atomic_bytes(path, raw)
                    return str(path)
                _, hashes = _raw_drafts(workspace)
                if hashes:
                    raise _round_error("기존 unversioned 초안은 명시적인 전체 전환이 필요합니다.",
                                       "DECISION_ROUND_MIGRATION_REQUIRED", 409)
                doc = {"schema": 1, "workspace_key": _workspace_key(workspace),
                       "versions": {}, "attempts": {}, "overlays": []}
                _write_meta(workspace / "contracts" / _ROUND_ANCHOR,
                            {"schema": 1, "workspace_key": _workspace_key(workspace)})
            doc["versions"][tid] = {"version_id": uuid.uuid4().hex,
                                     "raw_digest": hashlib.sha256(raw).hexdigest(), "state": "WRITING"}
            _write_meta(directory / _ROUND_META, doc)
            path = directory / (tid + ".json")
            _atomic_bytes(path, raw)
            doc["versions"][tid]["state"] = "READY"
            _write_meta(directory / _ROUND_META, doc)
            return str(path)
    except DecisionRoundError:
        raise
    except (OSError, ValueError, TypeError) as exc:
        raise _round_error("서버 초안 판 저장에 실패했습니다.", "DECISION_ROUND_IO") from exc


def save_draft_version(workspace_root, task_id, draft):
    """Explicit managed producer API; never an implicit legacy conversion."""
    return save_draft_source(workspace_root, task_id, draft, require_metadata=True)


def _snapshot(workspace, *, required):
    doc = _registry(workspace, required=required)
    drafts, hashes = _raw_drafts(workspace)
    wbs_path = workspace / "00_wbs_master_plan.json"
    tasks = _decode(_read_bytes(wbs_path)).get("tasks") if wbs_path.exists() else []
    if not isinstance(tasks, list):
        raise _round_error("WBS task 집합을 확인할 수 없습니다.")
    if doc is None:
        # Existing 1.0 pending must see the SAME legacy resolution projection as
        # its compiler. This branch cannot be reached for strict/v2 readers.
        from nodes.contract import _with_resolutions
        drafts = _with_resolutions(str(workspace), drafts)
        return {"doc": None, "drafts": drafts, "tasks": tasks, "ready": False}
    if set(hashes) != set(doc["versions"]):
        raise _round_error("현재 초안 파일 집합과 서버 판 기록이 다릅니다.", "DECISION_ROUND_STALE", 409)
    ready = True
    for tid, raw_hash in hashes.items():
        version = doc["versions"][tid]
        if version["state"] == "WRITING":
            raise _round_error("초안 판 저장이 끝나지 않았습니다.", "DECISION_ROUND_WRITE_INCOMPLETE")
        if version["raw_digest"] != raw_hash:
            raise _round_error("현재 초안 원문이 서버 판과 다릅니다.", "DECISION_ROUND_STALE", 409)
        ready = ready and version["state"] == "READY"
    if required and not ready:
        raise _round_error("기존 초안의 서버 판 메타데이터를 먼저 준비해야 합니다.", "DECISION_ROUND_METADATA_MISSING")
    version_set = {tid: {"version_id": value["version_id"], "raw_digest": hashes[tid]}
                   for tid, value in sorted(doc["versions"].items())}
    # Status/timestamps/progress are execution projection, NOT a new decision
    # target. Bind membership/classification/requirements used by the aggregator.
    task_material = [{"task_id": str(task.get("task_id", "")),
                      "artifact_kind": task.get(aggregator.ak.KIND_KEY),
                      "requirements": sorted(aggregator._task_requirements(task))}
                     for task in aggregator.ak.normalize_tasks(tasks)]
    task_material.sort(key=lambda item: _canonical(item))
    binding = {"workspace_key": doc["workspace_key"], "versions": version_set, "tasks_digest": _digest(task_material)}
    effective = copy.deepcopy(drafts)
    applied, overlay_ids = [], set()
    for overlay in doc["overlays"]:
        if (not isinstance(overlay, dict) or set(overlay) != {
                "request_id", "binding", "before_digest", "replacements", "event_id"}
                or not isinstance(overlay["replacements"], dict)
                or not isinstance(overlay["request_id"], str) or overlay["request_id"] in overlay_ids
                or not isinstance(overlay["event_id"], str) or not overlay["event_id"]
                or not isinstance(overlay["before_digest"], str) or not _SHA.fullmatch(overlay["before_digest"])
                or not isinstance(overlay["binding"], dict)
                or any(not isinstance(value, dict) for value in overlay["replacements"].values())):
            raise _round_error("결정 overlay가 손상됐습니다.")
        overlay_ids.add(overlay["request_id"])
        attempt = doc["attempts"].get(overlay["request_id"], {})
        if attempt.get("state") != "APPLIED" or attempt.get("event_id") != overlay["event_id"]:
            raise _round_error("결정 overlay의 원장 접수 기록이 없습니다.")
        if overlay["binding"] != binding:
            continue  # A new generation MUST NOT inherit old decisions.
        if overlay["before_digest"] != _digest(effective):
            raise _round_error("결정 overlay의 적용 순서/대상이 다릅니다.")
        if not set(overlay["replacements"]).issubset(drafts):
            raise _round_error("결정 overlay의 대상 초안이 없습니다.")
        effective.update(copy.deepcopy(overlay["replacements"]))
        applied.append(overlay["request_id"])
    if any(attempt["state"] == "APPLIED" and rid not in overlay_ids for rid, attempt in doc["attempts"].items()):
        raise _round_error("소비된 결정의 overlay가 유실됐습니다.")
    return {"doc": doc, "drafts": effective, "tasks": tasks, "ready": ready,
            "binding": binding, "projection_digest": _digest(effective), "applied": applied}


def load_drafts_for_workspace(workspace_root, *, require_metadata=False):
    """Managed compiler reader. Old unversioned _resolutions are deliberately
    not inherited: only overlays bound to the exact current generations apply.
    """
    workspace = _workspace(workspace_root)
    try:
        with _workspace_lock(workspace):
            return _snapshot(workspace, required=require_metadata)["drafts"]
    except DecisionRoundError:
        raise
    except (OSError, ValueError, TypeError) as exc:
        raise _round_error("결정 초안을 확인할 수 없습니다.") from exc


def _pending_snapshot(snapshot):
    result = pending_items(snapshot["tasks"], snapshot["drafts"])
    result["round_metadata_status"] = "READY" if snapshot["ready"] else "LEGACY_UNPREPARED"
    if not snapshot["ready"]:
        return result
    # One dataset decision covers ALL current declarations, not just the first
    # conflicting pair returned by the aggregator.
    grouped = {}
    included = set(aggregator.aggregate(snapshot["tasks"], snapshot["drafts"]).included_task_ids)
    for item in result["dataset_conflicts"]:
        key = item["dataset_key"]
        if key not in grouped:
            grouped[key] = copy.deepcopy(item)
            grouped[key]["choices"] = sorted(tid for tid, draft in snapshot["drafts"].items()
                if tid in included and any(aggregator._dataset_identity(ds) == key for ds in draft.get("datasets", [])))
            grouped[key]["tasks"] = list(grouped[key]["choices"])
    result["dataset_conflicts"] = list(grouped.values())
    # Conservative CAS binds every draft generation and WBS. Even an unrelated
    # file change needs a fresh preview rather than silently changing the set.
    for kind, group in (("CAPABILITY", "capability_decisions"), ("DATASET", "dataset_conflicts")):
        for item in result[group]:
            target = ({"task_id": item["task_id"], "capability": item["capability"]}
                      if kind == "CAPABILITY" else {"dataset_key": item["dataset_key"]})
            material = {"kind": kind, "target": target, "binding": snapshot["binding"],
                        "projection_digest": snapshot["projection_digest"], "choices": item["choices"]}
            digest = _digest(material)
            request_id = "cdr_" + digest
            attempt = snapshot["doc"]["attempts"].get(request_id)
            item.update(decision_request_id=request_id, expected_digest=digest,
                        decision_kind=kind, draft_versions=copy.deepcopy(snapshot["binding"]["versions"]),
                        round_status=attempt["state"] if attempt else "PENDING")
    return result


def pending_for_workspace(workspace_root, *, require_metadata=False):
    """Read current server WBS/draft generations. IDs are not client fields,
    timestamp guesses, content-only hashes, or random values minted on GET.
    """
    workspace = _workspace(workspace_root)
    try:
        with _workspace_lock(workspace):
            return _pending_snapshot(_snapshot(workspace, required=require_metadata))
    except DecisionRoundError:
        raise
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise _round_error("현재 결정 차수를 확인할 수 없습니다.") from exc


def resolve_for_workspace(workspace_root, *, decision_request_id, expected_digest, append_event,
                          task_id="", capability="", decision="", dataset_key="", winner_task_id="",
                          rationale="", require_metadata=False, before_write=None):
    """Exact-round CAS -> ledger -> atomic immutable-input-bound overlay ->
    readback. append_event(**payload) MUST attach current server actor/tenant/
    target scope/mode; this is not a PDP. Caller holds its project command guard.

    RESERVED is durable BEFORE ledger IO. Unknown/partial outcomes are 503 and
    block re-append; APPLIED replay is 409. This is not an automatic recovery or
    re-approval endpoint, nor a distributed transaction. require_metadata=False
    never enables strict submissions from unprepared legacy drafts.
    """
    if (not isinstance(decision_request_id, str) or not re.fullmatch(r"cdr_[0-9a-f]{64}", decision_request_id)
            or not isinstance(expected_digest, str) or not _SHA.fullmatch(expected_digest)
            or not callable(append_event) or (before_write is not None and not callable(before_write))):
        raise _round_error("서버 결정 ID와 expected_digest가 필요합니다.", "DECISION_ROUND_INPUT", 422)
    if not all(isinstance(value, str) for value in (task_id, capability, decision, dataset_key, winner_task_id, rationale)):
        raise _round_error("결정 입력은 문자열이어야 합니다.", "DECISION_ROUND_INPUT", 422)
    is_cap, is_ds = bool(capability), bool(dataset_key)
    if (is_cap == is_ds or (is_cap and winner_task_id) or (is_ds and (task_id or decision))):
        raise _round_error("능력 또는 데이터셋 결정 하나만 지정하십시오.", "DECISION_ROUND_INPUT", 422)
    workspace = _workspace(workspace_root)
    event_id = ""
    try:
        with _workspace_lock(workspace):
            snapshot = _snapshot(workspace, required=True)
            doc = snapshot["doc"]
            prior = doc["attempts"].get(decision_request_id)
            if prior:
                raise DecisionRoundError("DECISION_ROUND_CONSUMED" if prior["state"] == "APPLIED" else "DECISION_ROUND_PARTIAL",
                    "이미 소비된 결정입니다." if prior["state"] == "APPLIED" else "결정 기록 결과 확인이 필요합니다. 다시 결정하지 마십시오.",
                    409 if prior["state"] == "APPLIED" else 503,
                    event_id=prior.get("event_id", ""), decision_request_id=decision_request_id)
            pending = _pending_snapshot(snapshot)
            group = "capability_decisions" if is_cap else "dataset_conflicts"
            matching = [item for item in pending[group] if item["decision_request_id"] == decision_request_id
                        and item["expected_digest"] == expected_digest
                        and (item["task_id"] == task_id and item["capability"] == capability if is_cap
                             else item["dataset_key"] == dataset_key)]
            if not matching:
                raise _round_error("결정 차수 또는 현재 초안 판이 바뀌었습니다.", "DECISION_ROUND_STALE", 409)
            if is_cap:
                changed, summary = apply_capability_decision(snapshot["drafts"][task_id], capability=capability, decision=decision)
                replacements = {task_id: changed}
                subject_type, subject_id, choice = SUBJECT_CAPABILITY, capability, decision.strip().upper()
            else:
                if winner_task_id not in matching[0]["choices"]:
                    raise _round_error("현재 충돌의 허용 선택이 아닙니다.", "DECISION_ROUND_INPUT", 422)
                required = set(aggregator.aggregate(snapshot["tasks"], snapshot["drafts"]).included_task_ids)
                candidates = {tid: value for tid, value in snapshot["drafts"].items() if tid in required}
                replacements, summary = apply_dataset_resolution(candidates, dataset_key=dataset_key, winner_task_id=winner_task_id)
                subject_type, subject_id, choice = SUBJECT_DATASET, dataset_key, winner_task_id
            record = {"state": "RESERVED", "expected_digest": expected_digest, "event_id": "",
                      "command_digest": _digest({"task_id": task_id, "capability": capability, "decision": decision,
                                                  "dataset_key": dataset_key, "winner_task_id": winner_task_id, "rationale": rationale})}
            doc["attempts"][decision_request_id] = record
            meta_path = workspace / "contracts" / "drafts" / _ROUND_META
            if before_write is not None:
                before_write()
            current = _snapshot(workspace, required=True)
            if (current["binding"] != snapshot["binding"]
                    or current["projection_digest"] != snapshot["projection_digest"]):
                raise _round_error("결정 접수 전 초안 집합이 바뀌었습니다.", "DECISION_ROUND_STALE", 409)
            _write_meta(meta_path, doc)
            payload = {"event_type": "APP_CONTRACT_DECISION_RECORDED", "subject_type": subject_type,
                       "subject_id": subject_id, "decision": choice, "rationale": rationale.strip() or summary,
                       "project_id": workspace.name,
                       "evidence_refs": ["project:" + workspace.name] + ["task:" + tid for tid in sorted(replacements)],
                       "input_version_refs": [{"kind": "CONTRACT_DECISION_ROUND", "decision_request_id": decision_request_id,
                                                "digest": expected_digest, "draft_versions": snapshot["binding"]["versions"],
                                                "tasks_digest": snapshot["binding"]["tasks_digest"]}]}
            try:
                event = append_event(**payload)
            except Exception as exc:
                known_id = getattr(exc, "event_id", "")
                if isinstance(known_id, str) and known_id:
                    event_id = known_id
                    record.update(state="RECORDED", event_id=event_id)
                    try:
                        _write_meta(meta_path, doc)
                    except Exception:
                        pass  # The outward partial error still preserves the ID.
                raise
            if not isinstance(event, dict) or not isinstance(event.get("event_id"), str) or not event["event_id"]:
                raise _round_error("원장 접수 ID를 확인하지 못했습니다.", "DECISION_ROUND_LEDGER")
            event_id = event["event_id"]
            record.update(state="RECORDED", event_id=event_id)
            _write_meta(meta_path, doc)
            if any(event.get(key) != value for key, value in payload.items()):
                raise _round_error("원장 접수 사건이 요청한 결정과 다릅니다.", "DECISION_ROUND_LEDGER")
            if before_write is not None:
                before_write()
            current = _snapshot(workspace, required=True)
            if (current["binding"] != snapshot["binding"]
                    or current["projection_digest"] != snapshot["projection_digest"]):
                raise _round_error("원장 기록 중 초안 집합이 바뀌었습니다.", "DECISION_ROUND_STALE", 409)
            doc["overlays"].append({"request_id": decision_request_id, "binding": snapshot["binding"],
                                    "before_digest": snapshot["projection_digest"],
                                    "replacements": replacements, "event_id": event_id})
            record["state"] = "APPLIED"
            _write_meta(meta_path, doc)
            verified = _snapshot(workspace, required=True)
            if (decision_request_id not in verified["applied"]
                    or any(verified["drafts"].get(tid) != value for tid, value in replacements.items())):
                raise _round_error("결정 overlay 저장 후 반영을 확인하지 못했습니다.", "DECISION_ROUND_READBACK")
            return {"decision_request_id": decision_request_id, "expected_digest": expected_digest,
                    "event_id": event_id, "summary": summary, "draft_applied": True,
                    "applied_tasks": sorted(replacements), "note": ""}
    except DecisionRoundError as exc:
        if event_id and not exc.event_id:
            exc.event_id = event_id
        if not exc.decision_request_id:
            exc.decision_request_id = decision_request_id
        raise
    except DecisionError as exc:
        raise DecisionRoundError("DECISION_ROUND_INPUT", str(exc), 422) from exc
    except Exception as exc:
        # Callback can fail after actual append but before returning/readback.
        # The caller must attach its known event_id; never infer an event by time.
        event_id = event_id or getattr(exc, "event_id", "")
        status = getattr(exc, "status_code", None)
        if not event_id and isinstance(status, int) and 400 <= status < 500:
            raise DecisionRoundError(getattr(exc, "reason_code", "DECISION_ROUND_DENIED"),
                                     str(getattr(exc, "detail", None) or exc), status,
                                     decision_request_id=decision_request_id) from exc
        raise DecisionRoundError("DECISION_ROUND_PARTIAL", "결정 반영 결과를 확인할 수 없습니다. 다시 결정하지 마십시오.",
                                 503, event_id=event_id, decision_request_id=decision_request_id) from exc


@contextmanager
def _workspace_lock(workspace):
    directory = workspace / "contracts"
    _safe_path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / _ROUND_LOCK
    _safe_path(lock_path)
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    acquired = False
    try:
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError as exc:
            raise _round_error("다른 결정/초안 저장이 진행 중입니다.", "DECISION_ROUND_BUSY", 409) from exc
        yield
    finally:
        if acquired:
            if os.name == "nt":
                import msvcrt
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _workspace_key(workspace):
    return hashlib.sha256(os.path.normcase(str(workspace)).encode("utf-8")).hexdigest()


def has_round_metadata(workspace_root):
    """Presence is NOT validity. Main's authoritative v2 cohort must ALSO pass
    require_metadata=True: deletion of both files must not permit downgrade.
    """
    workspace = _workspace(workspace_root)
    return (os.path.lexists(workspace / "contracts" / _ROUND_ANCHOR)
            or os.path.lexists(workspace / "contracts" / "drafts" / _ROUND_META))


def draft_task_ids_for_scope(workspace_root):
    """Presence hints only: never approval/version proof. Keep an unreadable APP
    draft in scope so its strict reader can reject it rather than silently omit it.
    """
    directory = _workspace(workspace_root) / "contracts" / "drafts"
    try:
        _safe_path(directory)
        if not directory.exists():
            return set()
        ids = set()
        for path in directory.iterdir():
            if path.name.startswith("_") or not path.name.endswith(".json"):
                continue
            _safe_path(path)
            if not _TASK.fullmatch(path.stem) or not path.is_file():
                raise _round_error("현재 계약 초안 파일 집합을 확인할 수 없습니다.")
            ids.add(path.stem)
        return ids
    except DecisionRoundError:
        raise
    except OSError as exc:
        raise _round_error("현재 계약 초안 파일 집합을 확인할 수 없습니다.") from exc


def _raw_drafts(workspace):
    directory = workspace / "contracts" / "drafts"
    _safe_path(directory)
    if not directory.exists():
        return {}, {}
    drafts, hashes = {}, {}
    for path in sorted(directory.iterdir()):
        if path.name.startswith("_") or not path.name.endswith(".json"):
            continue
        if not _TASK.fullmatch(path.stem):
            raise _round_error("계약 초안 task ID가 잘못됐습니다.")
        raw = _read_bytes(path)
        drafts[path.stem] = _decode(raw)
        hashes[path.stem] = hashlib.sha256(raw).hexdigest()
    return drafts, hashes


def _registry(workspace, *, required):
    anchor = workspace / "contracts" / _ROUND_ANCHOR
    path = workspace / "contracts" / "drafts" / _ROUND_META
    if not os.path.lexists(anchor) and not os.path.lexists(path):
        if required:
            raise _round_error("서버 초안 판 메타데이터가 준비되지 않았거나 유실됐습니다.", "DECISION_ROUND_METADATA_MISSING")
        return None
    expected = {"schema": 1, "workspace_key": _workspace_key(workspace)}
    if _read_meta(anchor) != expected:
        raise _round_error("다른 workspace의 초안 판 메타데이터입니다.")
    doc = _read_meta(path)
    if (set(doc) != {"schema", "workspace_key", "versions", "attempts", "overlays"}
            or any(doc.get(key) != value for key, value in expected.items())
            or not isinstance(doc["versions"], dict) or not isinstance(doc["attempts"], dict)
            or not isinstance(doc["overlays"], list)):
        raise _round_error("서버 초안 판 메타데이터 형식이 잘못됐습니다.")
    for tid, version in doc["versions"].items():
        if (not isinstance(tid, str) or not _TASK.fullmatch(tid) or not isinstance(version, dict)
                or set(version) != {"version_id", "raw_digest", "state"}
                or not isinstance(version["raw_digest"], str) or not _SHA.fullmatch(version["raw_digest"])
                or version["state"] not in {"LEGACY", "WRITING", "READY"}
                or not isinstance(version["version_id"], str)
                or (version["state"] != "LEGACY" and not _UUID.fullmatch(version["version_id"]))
                or (version["state"] == "LEGACY" and version["version_id"] != "")):
            raise _round_error("서버 초안 판 기록이 손상됐습니다.")
    for rid, attempt in doc["attempts"].items():
        if (not re.fullmatch(r"cdr_[0-9a-f]{64}", rid) or not isinstance(attempt, dict)
                or set(attempt) != {"state", "expected_digest", "event_id", "command_digest"}
                or attempt["state"] not in {"RESERVED", "RECORDED", "APPLIED"}
                or not isinstance(attempt["event_id"], str)
                or (attempt["state"] != "RESERVED" and not attempt["event_id"])
                or any(not isinstance(attempt[key], str) or not _SHA.fullmatch(attempt[key])
                       for key in ("expected_digest", "command_digest"))):
            raise _round_error("결정 접수 기록이 손상됐습니다.")
    return doc
