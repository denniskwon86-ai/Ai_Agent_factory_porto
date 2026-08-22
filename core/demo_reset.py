"""★★★ [M0-5] 시연 **초기화** — 「이번 시연에서 만든 실행 결과」만 되돌린다.

## 무엇을 되돌리고 무엇을 남기는가 — 사용자가 고정한 범위

| | 무엇 | 왜 |
|---|---|---|
| **지운다** | 시나리오 입력값·가정(초안) · 계산 실행 결과 · 초안 안건 · 미발간 브리핑 초안 · Preview 임시 상태 | 이번 리허설이 만든 것이다 |
| **남기고 경계만 긋는다** | 이미 발간된 브리핑 · 결정된 안건과 승인 이력 · 실패·취소 기록 | **지우면 그 판을 근거로 만든 계보가 끊긴다** |
| **절대 유지** | Decision Ledger 전부 · 인증판과 원천 · 소유권 결속 · 온톨로지·관계 승인 · 계산 능력 승인 · 계약·스키마·코드 지문 · 사용자·조직·권한 | 정본과 통제다 |

⚠️⚠️ **원장은 어떤 안에서도 사건을 지우지 않는다.** 추가 전용이다 — 초기화 자체가
  세 사건으로 남는다(`REQUESTED`/`COMPLETED`/`FAILED`).

## 「비활성·보관」을 무엇으로 구현했는가

발간된 브리핑의 상태를 `WITHDRAWN` 으로 바꾸지 **않는다.** 그것은 대외 상태 변경이고,
초기화가 할 일이 아니다 — 회수는 사람이 사유를 달아 하는 별개의 결정이다.

★ 대신 **경계**를 남긴다. 초기화 시각을 기록하고, 시연 화면은 그 경계 이후 것만 보여
  준다. 아무것도 바뀌지 않았고, 아무것도 사라지지 않았으며, 다음 리허설은 깨끗하다.

## ⚠️⚠️ 「DEMO/SYNTHETIC 환경」을 무엇으로 판정하는가

**등록부의 키트 모드**(`kit_registry_versions.mode`)다. 호출자가 보내는 값이 아니다 —
보내게 두면 「데모라고 적어 보낸 요청」이 운영 자료를 지운다.

⚠️ `entity_mode` 를 데모 표지로 쓰지 않는다. 이 저장소의 시연 인스턴스는 `REAL` 문맥에서
  돈다(합성 회사를 실제 조직 문맥으로 세운다) — `entity_mode` 로 가르면 시연이 막히거나,
  더 나쁘게는 운영 `REAL` 인스턴스가 데모로 오인된다.

## 재확인

`execute()` 는 **`plan()` 이 낸 지문**을 요구한다. 계획을 보지 않고는 지울 수 없다 —
그리고 그 사이에 자료가 바뀌면 지문이 달라져 거부된다.

LLM 호출: 0건.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.data_preparation import models as m

RESET_REQUESTED = "DEMO_RESET_REQUESTED"
RESET_COMPLETED = "DEMO_RESET_COMPLETED"
RESET_FAILED = "DEMO_RESET_FAILED"
RESET_SUBJECT = "demo_reset"

#: 지우지 **않는** 안건 상태 — 결정·조치·측정이 끝났거나 취소된 것.
#: ⚠️ 지우면 그 결정을 근거로 한 실행 기록이 부모를 잃는다.
KEEP_DECISION_STATUSES = ("DECIDED", "ACTIONED", "EFFECT_MEASURED", "CANCELLED")
#: 지우지 **않는** 발간 상태 — 이미 남에게 나갔다. 회수해도 본 사람이 있다.
KEEP_PUBLICATION_STATUSES = ("PUBLISHED", "CORRECTED", "WITHDRAWN")


class DemoResetError(Exception):
    """초기화를 할 수 없다. ⚠️ 「일부만 지우고 성공」으로 답하지 않는다."""


class DemoResetRefused(DemoResetError):
    """**환경이 아니다.** 운영 자료를 대상으로 삼았다 — 라우트가 403 으로 바꾼다."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fp(payload: Any) -> str:
    return hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()


# ── 관문: 여기가 아니면 아무것도 지우지 않는다 ────────────────────────────

def assert_demo_target(store: Any, instance: Dict[str, Any]) -> str:
    """이 인스턴스가 **시연 키트**인지 등록부에서 확인한다. 아니면 거부.

    ★★★ 판정 근거는 `kit_registry_versions.mode` — 서버가 등록할 때 정한 값이다.
    ⚠️ 못 읽으면 **거부**한다. 「모르니까 데모겠지」는 운영 자료를 지우는 문이다."""
    from core.data_preparation import kit_registry

    kit_id = str(instance.get("kit_id", "") or "")
    version = str(instance.get("version", "") or "")
    try:
        row = kit_registry.resolve(store, kit_id, version)
    except Exception as exc:  # noqa: BLE001
        raise DemoResetRefused(
            f"키트 등록부를 읽지 못해 초기화하지 않습니다({kit_id}@{version}): {exc} — "
            f"시연 환경인지 확인할 수 없으면 지우지 않습니다.")
    if not row:
        raise DemoResetRefused(
            f"등록되지 않은 키트입니다({kit_id}@{version}) — 시연 환경인지 확인할 수 "
            f"없으면 지우지 않습니다.")
    mode = str(row.get("mode", "") or "")
    if mode != m.KIT_MODE_DEMO:
        raise DemoResetRefused(
            f"시연 환경이 아닙니다(키트 모드 {mode or '(없음)'}) — 초기화는 "
            f"`{m.KIT_MODE_DEMO}` 키트에서만 할 수 있습니다.")
    return mode


# ── 계획: 무엇을 지우고 무엇을 남기는가 ──────────────────────────────────

def _scenario_rows(tenant_id: str, scope_node_id: str) -> Dict[str, List[str]]:
    """시나리오 입력·결과. ⚠️ **얼린 것과 승인된 것은 빼고** 센다."""
    import sqlite3

    from core.enterprise_context.scenario_inputs import scenario_inputs

    out: Dict[str, List[str]] = {"assumption_sets": [], "baseline_snapshots": [],
                                 "scenario_results": []}
    path = scenario_inputs._repo.db_path            # noqa: SLF001 — 저장소 경로 정본
    if not os.path.exists(path):
        return out
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        for table, id_col in (("assumption_sets", "assumption_set_id"),
                              ("baseline_snapshots", "snapshot_id")):
            try:
                rows = conn.execute(
                    f"SELECT {id_col} AS id FROM {table} WHERE tenant_id=? AND "
                    f"scope_node_id=? AND frozen=0 AND approved_at=''",
                    (tenant_id, scope_node_id)).fetchall()
            except sqlite3.OperationalError:
                #: 표가 아직 없다 — 「0건」이 맞다(장애가 아니다).
                continue
            out[table] = [str(r["id"]) for r in rows]
        #: ★★★ `scenario_results` 에는 **범위 열이 없다.** 테넌트로만 지우면 같은 회사의
        #:   **다른 공장 결과까지** 지운다.
        #: ⚠️ 그래서 **범위가 확정된 부모**(이 범위의 가정·기준값)로 좁힌다. 부모가 없는
        #:   결과는 어느 범위의 것인지 알 수 없으므로 **건드리지 않는다** — 모르는 것을
        #:   지우는 것보다 남기는 편이 낫다.
        parents = set(out["assumption_sets"]) | set(out["baseline_snapshots"])
        if parents:
            try:
                marks = ",".join("?" * len(parents))
                rows = conn.execute(
                    f"SELECT result_id FROM scenario_results WHERE tenant_id=? AND "
                    f"(assumption_set_id IN ({marks}) OR snapshot_id IN ({marks}))",
                    (tenant_id, *sorted(parents), *sorted(parents))).fetchall()
                out["scenario_results"] = [str(r["result_id"]) for r in rows]
            except sqlite3.OperationalError:
                pass
    finally:
        conn.close()
    return out


def _collab_rows(tenant_id: str, scope_node_id: str) -> Dict[str, Dict[str, List[str]]]:
    """안건·발간물. **초안만 지우고 나머지는 센다.**"""
    import sqlite3

    from core.collaboration_store import collaboration_store

    out = {"decision_cases": {"delete": [], "retain": []},
           "publications": {"delete": [], "retain": []}}
    path = collaboration_store.db_path
    if not os.path.exists(path):
        return out
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        for table, id_col, keep in (("decision_cases", "decision_id",
                                     KEEP_DECISION_STATUSES),
                                    ("publications", "publication_id",
                                     KEEP_PUBLICATION_STATUSES)):
            try:
                rows = conn.execute(
                    f"SELECT {id_col} AS id, status FROM {table} WHERE tenant_id=? "
                    f"AND scope_id=?", (tenant_id, scope_node_id)).fetchall()
            except sqlite3.OperationalError:
                continue
            for r in rows:
                bucket = "retain" if str(r["status"]) in keep else "delete"
                out[table][bucket].append(str(r["id"]))
    finally:
        conn.close()
    return out


def _preview_state() -> Dict[str, Any]:
    """Preview 임시 상태. ★ 설계상 **별도 DB 파일**이라 파일 하나로 끝난다."""
    from core.app_preview import AUDIENCE_PREVIEW, db_path

    path = db_path(AUDIENCE_PREVIEW)
    return {"path": path, "exists": os.path.exists(path),
            "bytes": os.path.getsize(path) if os.path.exists(path) else 0}


def plan(store: Any, *, instance: Dict[str, Any]) -> Dict[str, Any]:
    """**무엇을 지우고 무엇을 남기는가.** 부작용이 없다.

    ★ 이 계획의 지문이 `execute()` 의 재확인 값이 된다."""
    mode = assert_demo_target(store, instance)
    tenant = str(instance["tenant_id"])
    scope = str(instance["scope_node_id"])

    scenario = _scenario_rows(tenant, scope)
    collab = _collab_rows(tenant, scope)
    preview = _preview_state()

    delete = [
        {"kind": "시나리오 가정(초안)", "table": "assumption_sets",
         "ids": sorted(scenario["assumption_sets"])},
        {"kind": "시나리오 기준값(초안)", "table": "baseline_snapshots",
         "ids": sorted(scenario["baseline_snapshots"])},
        {"kind": "계산 실행 결과", "table": "scenario_results",
         "ids": sorted(scenario["scenario_results"])},
        {"kind": "초안 안건", "table": "decision_cases",
         "ids": sorted(collab["decision_cases"]["delete"])},
        {"kind": "미발간 브리핑", "table": "publications",
         "ids": sorted(collab["publications"]["delete"])},
    ]
    for item in delete:
        item["count"] = len(item["ids"])

    retain = [
        {"kind": "결정된 안건·승인 이력", "table": "decision_cases",
         "count": len(collab["decision_cases"]["retain"]),
         "reason": "지우면 그 결정을 근거로 한 실행 기록이 부모를 잃는다"},
        {"kind": "발간된 브리핑", "table": "publications",
         "count": len(collab["publications"]["retain"]),
         "reason": "이미 남에게 나갔다 — 회수는 사유를 단 별개의 결정이다"},
    ]
    #: ★★★ **절대 유지**를 세어서 보여 준다. 「안 건드린다」는 말보다 숫자가 낫다.
    preserve = _preserve_counts(store, instance)

    target = {"instance_id": str(instance["instance_id"]),
              "kit_id": str(instance.get("kit_id", "")),
              "kit_version": str(instance.get("version", "")),
              "kit_mode": mode, "tenant_id": tenant, "scope_node_id": scope,
              "entity_mode": str(instance["entity_mode"])}
    #: ★★★ 지문은 **지울 것과 대상**만 덮는다. 사람이 확인하는 것이 그것이기 때문이다.
    #:
    #: ⚠️⚠️ 처음에는 `preserve`(유지 대상 건수)까지 넣었다. 그런데 거기에 원장 건수가
    #:   들어 있어서, 계획과 실행 사이에 **아무 관계 없는 원장 쓰기 하나만 있어도**
    #:   확인이 무효가 됐다. 재확인은 「내가 본 삭제 목록이 그대로인가」를 물어야지
    #:   「그 사이에 시스템에 아무 일도 없었는가」를 물으면 안 된다 — 뒤엣것은 절대
    #:   만족되지 않고, 그러면 사람은 지문을 복사해 넣는 법을 배운다.
    #: ★ `retain` 은 넣는다 — 보관 대상이 늘었다는 것은 **지울 것도 달라졌다**는 뜻이다.
    confirmable = {"target": target, "delete": delete, "retain": retain}
    return {**confirmable, "preserve": preserve,
            "preview": {"path_exists": preview["exists"], "bytes": preview["bytes"]},
            "plan_fingerprint": _fp(confirmable), "planned_at": _now()}


def _preserve_counts(store: Any, instance: Dict[str, Any]) -> List[Dict[str, Any]]:
    """건드리지 않는 것들의 **수**. ⚠️ 못 세면 0 이 아니라 `null` 이다."""
    out: List[Dict[str, Any]] = []

    def add(kind: str, fn) -> None:
        try:
            out.append({"kind": kind, "count": int(fn())})
        except Exception as exc:  # noqa: BLE001
            #: ⚠️ 「세지 못했다」를 0 으로 적지 않는다 — 0 은 「없다」로 읽힌다.
            out.append({"kind": kind, "count": None, "error": str(exc)})

    inst = str(instance["instance_id"])
    add("인증판", lambda: sum(1 for s in store.list_snapshots(inst)
                            if str(s.get("state")) == m.DEMO_CERTIFIED))
    add("계산 능력 승인", lambda: len(_active_approvals(store, instance)))
    add("원장 사건", _ledger_count)
    return out


def _active_approvals(store: Any, instance: Dict[str, Any]) -> List[Dict[str, Any]]:
    from core import calc_execution_approval as cea

    return [r for r in cea.list_approvals(
        store, tenant_id=str(instance["tenant_id"]),
        scope_node_id=str(instance["scope_node_id"])) if r["status"] == cea.ACTIVE]


def _ledger_count() -> int:
    import sqlite3

    from core.decision_ledger import decision_ledger

    conn = sqlite3.connect(decision_ledger.db_path)
    try:
        return int(conn.execute(
            "SELECT count(*) FROM decision_ledger_events").fetchone()[0])
    finally:
        conn.close()


# ── 실행 ─────────────────────────────────────────────────────────────────

def execute(store: Any, *, instance: Dict[str, Any], actor: str, reason: str,
            confirm_fingerprint: str) -> Dict[str, Any]:
    """초기화를 **실제로** 한다. 원장에 세 사건 중 둘이 남는다.

    ⚠️⚠️ `confirm_fingerprint` 는 `plan()` 이 낸 값이어야 한다 — 계획을 보지 않고는
      지울 수 없고, 그 사이에 자료가 바뀌면 지문이 달라져 거부된다."""
    who = str(actor or "").strip()
    why = str(reason or "").strip()
    if not who:
        raise DemoResetError("초기화 행위자가 없습니다 — 「누가 지웠나」에 답할 수 "
                             "없는 삭제는 하지 않습니다.")
    if not why:
        raise DemoResetError("초기화 사유가 필요합니다.")

    current = plan(store, instance=instance)
    if str(confirm_fingerprint or "").strip() != current["plan_fingerprint"]:
        raise DemoResetError(
            "확인한 계획과 지금 상태가 다릅니다 — 대상 목록을 다시 확인한 뒤 "
            "초기화하십시오(그 사이에 자료가 바뀌었습니다).")

    from core.decision_ledger import decision_ledger

    tenant = current["target"]["tenant_id"]
    mode = current["target"]["entity_mode"]
    before = _state_fingerprint(store, instance)
    ledger_before = _ledger_count()
    requested = decision_ledger.append(
        event_type=RESET_REQUESTED, subject_type=RESET_SUBJECT,
        subject_id=current["target"]["instance_id"], actor_type="user", actor_id=who,
        decision="REQUESTED", rationale=why, tenant_id=tenant, entity_mode=mode,
        #: ★ 원장에는 `payload` 칸이 없다 — 사실을 `evidence_refs` 에 **문자열로** 싣는다.
        #: ⚠️ 사유(`rationale`)에 섞지 않는다. 사유는 사람이 쓴 문장이고, 거기에 기계값을
        #:   넣으면 나중에 문구를 다듬을 때 기록이 조용히 바뀐다.
        evidence_refs=_facts(current, before=before, ledger_before=ledger_before))

    try:
        deleted = _delete(current)
        preview_cleared = _clear_preview()
    except Exception as exc:  # noqa: BLE001
        #: ⚠️⚠️ **실패도 남긴다.** 안 남기면 「요청만 있고 결과 없음」이 되고, 다음 사람은
        #:   초기화가 됐는지 안 됐는지 모른다.
        decision_ledger.append(
            event_type=RESET_FAILED, subject_type=RESET_SUBJECT,
            subject_id=current["target"]["instance_id"], actor_type="user",
            actor_id=who, decision="FAILED", rationale=f"초기화 실패: {exc}",
            parent_event_id=str(requested["event_id"]),
            tenant_id=tenant, entity_mode=mode)
        raise DemoResetError(f"초기화에 실패했습니다: {exc}")

    after = _state_fingerprint(store, instance)
    ledger_after = _ledger_count()
    if ledger_after < ledger_before:
        #: ⚠️⚠️ 원장이 줄었다 — 있을 수 없는 일이고, 있었다면 **초기화가 지운 것**이다.
        raise DemoResetError(
            f"원장 사건이 줄었습니다({ledger_before} → {ledger_after}) — 초기화는 원장을 "
            f"건드리지 않아야 합니다. 즉시 점검이 필요합니다.")
    completed = decision_ledger.append(
        event_type=RESET_COMPLETED, subject_type=RESET_SUBJECT,
        subject_id=current["target"]["instance_id"], actor_type="user", actor_id=who,
        decision="COMPLETED", rationale=why,
        parent_event_id=str(requested["event_id"]),
        tenant_id=tenant, entity_mode=mode,
        evidence_refs=_facts(current, before=before, after=after, deleted=deleted,
                             preview_cleared=preview_cleared,
                             ledger_before=ledger_before, ledger_after=ledger_after))
    return {"reset_id": "dr_" + uuid.uuid4().hex[:20],
            "requested_event_id": str(requested["event_id"]),
            "completed_event_id": str(completed["event_id"]),
            "deleted": deleted, "preview_cleared": preview_cleared,
            "retained": current["retain"], "preserved": current["preserve"],
            "before_fingerprint": before, "after_fingerprint": after,
            "reset_at": _now()}


def _facts(planned: Dict[str, Any], *, before: str, after: str = "",
           deleted: Optional[Dict[str, int]] = None,
           preview_cleared: Optional[bool] = None,
           ledger_before: Optional[int] = None,
           ledger_after: Optional[int] = None) -> List[str]:
    """원장에 실을 **사실들.** 대상 환경·삭제/보관 건수·전후 지문.

    ★ 문자열 목록으로 둔다 — 나중에 사람이 원장을 훑을 때 그대로 읽힌다.
    ⚠️ 「보관 0건」과 「보관을 세지 못함」을 가른다 — 세지 못한 것은 `?` 로 적는다."""
    t = planned["target"]
    out = [f"target.instance_id={t['instance_id']}",
           f"target.kit={t['kit_id']}@{t['kit_version']}",
           f"target.kit_mode={t['kit_mode']}",
           f"target.tenant_id={t['tenant_id']}",
           f"target.scope_node_id={t['scope_node_id']}",
           f"target.entity_mode={t['entity_mode']}",
           f"fingerprint.before={before}",
           f"plan={planned['plan_fingerprint']}"]
    if after:
        out.append(f"fingerprint.after={after}")
    for item in planned["delete"]:
        n = deleted.get(item["table"]) if deleted is not None else item["count"]
        out.append(f"deleted.{item['table']}={n}")
    for item in planned["retain"]:
        out.append(f"retained.{item['table']}={item['count']}")
    for item in planned["preserve"]:
        n = item["count"]
        out.append(f"preserved.{item['kind']}={'?' if n is None else n}")
    if preview_cleared is not None:
        out.append(f"deleted.preview={'yes' if preview_cleared else 'none'}")
    #: ★ 원장은 **줄지 않았음**을 건수로 보인다(지문으로 보면 전후가 당연히 다르다).
    if ledger_before is not None:
        out.append(f"ledger.before={ledger_before}")
    if ledger_after is not None:
        out.append(f"ledger.after={ledger_after}")
    return out


def _delete(planned: Dict[str, Any]) -> Dict[str, int]:
    """계획한 **그 id 들만** 지운다.

    ⚠️ 조건을 다시 쓰지 않는다 — 다시 쓰면 계획과 실행이 갈라지고, 사람이 확인한
      목록과 실제로 지워지는 것이 달라진다."""
    import sqlite3

    from core.collaboration_store import collaboration_store
    from core.enterprise_context.scenario_inputs import scenario_inputs

    where = {"assumption_sets": ("assumption_set_id",
                                 scenario_inputs._repo.db_path),   # noqa: SLF001
             "baseline_snapshots": ("snapshot_id",
                                    scenario_inputs._repo.db_path),  # noqa: SLF001
             "scenario_results": ("result_id",
                                  scenario_inputs._repo.db_path),  # noqa: SLF001
             "decision_cases": ("decision_id", collaboration_store.db_path),
             "publications": ("publication_id", collaboration_store.db_path)}
    done: Dict[str, int] = {}
    for item in planned["delete"]:
        table = item["table"]
        ids = list(item["ids"])
        done[table] = 0
        if not ids:
            continue
        id_col, path = where[table]
        conn = sqlite3.connect(path)
        try:
            marks = ",".join("?" * len(ids))
            cur = conn.execute(f"DELETE FROM {table} WHERE {id_col} IN ({marks})",
                               tuple(ids))
            conn.commit()
            done[table] = int(cur.rowcount or 0)
        finally:
            conn.close()
    return done


def _clear_preview() -> bool:
    """Preview 임시 DB 를 지운다. ★ 별도 파일이라 **파일 하나**로 끝난다.

    ⚠️⚠️ 파일만 지우면 **다음 미리보기가 죽는다.** `AppDataStore.ensure_schema()` 가
      「이 경로는 이미 준비됐다」를 기억하므로(`_ready`), 파일이 사라져도 스키마를 다시
      만들지 않는다. 그래서 서비스 싱글턴도 함께 버린다 — 다음 호출이 새로 만든다.
    ★ 이것이 「지우기」와 「되돌리기」의 차이다. 되돌린다는 것은 **다시 쓸 수 있는
      상태**로 만든다는 뜻이지, 파일이 없어졌다는 뜻이 아니다."""
    import core.app_preview as ap

    path = ap.db_path(ap.AUDIENCE_PREVIEW)
    existed = os.path.exists(path)
    if existed:
        os.remove(path)
    #: 있든 없든 캐시는 버린다 — 파일이 없던 경우에도 옛 싱글턴이 남아 있을 수 있다.
    try:
        ap._preview_service = None                  # noqa: SLF001 — 캐시 무효화
    except Exception:  # noqa: BLE001
        pass
    return existed


def _ownership_fingerprints(store: Any, instance: Dict[str, Any]) -> List[str]:
    """이 문맥의 소유권 결속. ⚠️ 못 읽으면 **던진다** — 「없다」로 접지 않는다."""
    with store.transaction() as conn:
        rows = conn.execute(
            "SELECT binding_id, owner_dept_id, status FROM dataset_ownership_bindings "
            "WHERE tenant_id=? AND scope_node_id=? ORDER BY binding_id",
            (str(instance["tenant_id"]), str(instance["scope_node_id"]))).fetchall()
    return [f"{r[0]}:{r[1]}:{r[2]}" for r in rows]


def _state_fingerprint(store: Any, instance: Dict[str, Any]) -> str:
    """초기화 **전후 지문.** 무엇이 유지됐는지 대조할 수 있어야 한다.

    ★ 재료는 **유지되어야 하는 것들**이다 — 인증판·소유권 결속·계산 승인.
      지워지는 것은 넣지 않는다(넣으면 전후가 당연히 달라 대조가 무의미하다).

    ⚠️⚠️ **원장 건수를 넣지 않는다.** 처음에 넣었더니 전후가 절대 같을 수 없었다 —
      초기화 자체가 원장에 사건을 남기기 때문이다. 원장에 대해 지켜야 할 성질은
      「같다」가 아니라 **「줄지 않았다」**이고, 그것은 지문이 아니라 건수로 본다."""
    inst = str(instance["instance_id"])
    snaps = sorted(str(s.get("snapshot_id")) for s in store.list_snapshots(inst)
                   if str(s.get("state")) == m.DEMO_CERTIFIED)
    approvals = sorted(str(r["binding_fingerprint"])
                       for r in _active_approvals(store, instance))
    return _fp({"certified_snapshots": snaps, "calc_approvals": approvals,
                "ownership_bindings": _ownership_fingerprints(store, instance)})
