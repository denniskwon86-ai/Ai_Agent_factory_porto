"""B2 전용 인스턴스 결속. 기존 registry/instance DDL과 레거시 행을 변경하지 않는다."""
from core.data_preparation import models
from core.enterprise_context.process_configuration import uid
from core.enterprise_context.process_schema import ProcessError, canonical, fingerprint


DDL = """
CREATE TABLE IF NOT EXISTS kit_process_instances (
 operation_id TEXT PRIMARY KEY, instance_id TEXT NOT NULL UNIQUE,
 context_root_id TEXT NOT NULL, artifact_digest TEXT NOT NULL,
 identity_json TEXT NOT NULL, identity_digest TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS kit_process_link_immutable
BEFORE UPDATE ON kit_process_instances
BEGIN SELECT RAISE(ABORT, 'immutable process kit link'); END;
CREATE TRIGGER IF NOT EXISTS kit_process_link_no_delete
BEFORE DELETE ON kit_process_instances
BEGIN SELECT RAISE(ABORT, 'immutable process kit link'); END;
CREATE TRIGGER IF NOT EXISTS kit_process_link_no_replace
BEFORE INSERT ON kit_process_instances WHEN EXISTS (
 SELECT 1 FROM kit_process_instances WHERE operation_id=NEW.operation_id OR instance_id=NEW.instance_id)
BEGIN SELECT RAISE(ABORT, 'immutable process kit link'); END;
CREATE TABLE IF NOT EXISTS kit_process_instance_upgrades (
 operation_id TEXT PRIMARY KEY, instance_id TEXT NOT NULL, sequence INTEGER NOT NULL,
 from_artifact_digest TEXT NOT NULL, to_artifact_digest TEXT NOT NULL,
 identity_json TEXT NOT NULL, identity_digest TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(instance_id, sequence), UNIQUE(instance_id, to_artifact_digest)
);
CREATE TRIGGER IF NOT EXISTS kit_process_upgrade_immutable
BEFORE UPDATE ON kit_process_instance_upgrades
BEGIN SELECT RAISE(ABORT, 'immutable process kit upgrade'); END;
CREATE TRIGGER IF NOT EXISTS kit_process_upgrade_no_delete
BEFORE DELETE ON kit_process_instance_upgrades
BEGIN SELECT RAISE(ABORT, 'immutable process kit upgrade'); END;
CREATE TRIGGER IF NOT EXISTS kit_process_upgrade_no_replace
BEFORE INSERT ON kit_process_instance_upgrades WHEN EXISTS (
 SELECT 1 FROM kit_process_instance_upgrades WHERE operation_id=NEW.operation_id
 OR (instance_id=NEW.instance_id AND (sequence=NEW.sequence OR to_artifact_digest=NEW.to_artifact_digest)))
BEGIN SELECT RAISE(ABORT, 'immutable process kit upgrade'); END;
"""
#: 고정 정체성의 열쇠. 원 링크와 업그레이드 기록이 같은 모양을 쓴다.
_IDENTITY = ("kit_id", "version", "kit_fingerprint", "tenant_id", "scope_node_id", "entity_mode")
#: 판본이 바뀌어도 같아야 하는 것 — 같은 적용본이다.
_STABLE = ("kit_id", "tenant_id", "scope_node_id", "entity_mode")


def prepare(store):
    with store.transaction() as conn:
        conn.executescript(DDL)


def create_or_get(store, *, operation_id, bundle, boundary, actor, label=""):
    """동일 operation은 같은 인스턴스. 별도 DP 트랜잭션이며 ECM 원자성을 주장하지 않는다."""
    from core.data_preparation.process_pack_artifacts import pin_bundle, get_bundle
    pin_bundle(store, bundle)
    fixed = get_bundle(store, bundle["artifact_digest"])
    models.assert_context(boundary.tenant_id, boundary.scope_node_id or boundary.context_root_id, boundary.entity_mode)
    prepare(store)
    from core.data_preparation.store import _now
    expected = dict(kit_id=fixed["kit_id"], version=fixed["version"], kit_fingerprint=fixed["artifact_digest"],
                    tenant_id=boundary.tenant_id, scope_node_id=boundary.scope_node_id or boundary.context_root_id,
                    entity_mode=boundary.entity_mode)
    with store.transaction() as conn:
        conn.execute("BEGIN IMMEDIATE")
        link = conn.execute("SELECT * FROM kit_process_instances WHERE operation_id=?", (operation_id,)).fetchone()
        if link:
            prior = conn.execute("SELECT * FROM kit_instances WHERE instance_id=?", (link["instance_id"],)).fetchone()
            if (not prior or any(prior[k] != v for k, v in expected.items()) or prior["status"] != "active" or
                    link["context_root_id"] != boundary.context_root_id or
                    link["artifact_digest"] != fixed["artifact_digest"] or link["identity_digest"] != fingerprint(expected)):
                raise ProcessError("PROCESS_INSTANCE_CONFLICT", "설치 인스턴스의 고정 문맥 또는 상태가 다릅니다.")
            return {**dict(prior), "artifact_digest": link["artifact_digest"], "context_root_id": link["context_root_id"]}
        # 동일 이름의 레거시 계약과 섞지 않는다. 새 버전은 전용 불변 artifact 색인에서만 해석한다.
        if conn.execute("SELECT 1 FROM kit_registry_versions WHERE kit_id=? AND version=?",
                        (fixed["kit_id"], fixed["version"])).fetchone():
            raise ProcessError("IMMUTABLE_VERSION_CONFLICT", "레거시 레지스트리에 같은 버전이 있습니다. 새 버전을 사용하십시오.")
        now = _now()
        row = dict(**expected, instance_id=uid("ki"), label=label, status="active",
                   created_by=actor, created_at=now, updated_at=now)
        conn.execute(f"INSERT INTO kit_instances ({','.join(row)}) VALUES ({','.join('?' for _ in row)})", tuple(row.values()))
        conn.execute("INSERT INTO kit_process_instances VALUES(?,?,?,?,?,?)", (operation_id, row["instance_id"],
                     boundary.context_root_id, fixed["artifact_digest"], canonical(expected), fingerprint(expected)))
        return {**row, "artifact_digest": fixed["artifact_digest"], "context_root_id": boundary.context_root_id}


def _link(conn, instance):
    import json
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='kit_process_instances'").fetchone():
        return None
    link = conn.execute("SELECT * FROM kit_process_instances WHERE instance_id=?", (instance["instance_id"],)).fetchone()
    if not link:
        return None
    expected = json.loads(link["identity_json"])
    if fingerprint(expected) != link["identity_digest"] or any(instance.get(k) != v for k, v in expected.items()):
        raise ProcessError("PROCESS_INSTANCE_CONFLICT", "인스턴스 문맥의 고정 지문이 다릅니다.", 503)
    return dict(link)


def binding_for_instance(store, instance):
    with store.transaction() as conn:
        return _link(conn, instance)


# ── [2026-09-25] 고정 이력 — 같은 적용본(인스턴스 ID)의 판본 업그레이드 ─────────────
#
# ★ 원 링크(`kit_process_instances`)와 인스턴스 행은 **그대로 둔다** — 설치 때 고정한 정체성이고
#   과거 승인판·릴리스·인증이 그것을 가리킨다. 업그레이드는 `kit_process_instance_upgrades` 에
#   **새 행을 더할 뿐**이다(갱신·삭제·교체 트리거로 막는다). 그래서 «이 인스턴스가 판본 D 에
#   고정된 적이 있는가» 는 이력 안에 D 가 있는가로 묻고, 새로 시작하는 일은 마지막 고정을 쓴다.
# ⚠️ 이력 한 줄이라도 사슬이 끊기면(순번·이전 지문·정체성) 전체를 손상으로 본다 — 앞부분만
#   믿고 쓰지 않는다.

def _upgrades(conn, instance_id):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='kit_process_instance_upgrades'").fetchone():
        return []
    return [dict(r) for r in conn.execute(
        "SELECT * FROM kit_process_instance_upgrades WHERE instance_id=? ORDER BY sequence", (instance_id,))]


def pins(conn, instance):
    """이 인스턴스의 고정 이력(오래된 것부터). B2 결속이 없으면 빈 목록."""
    import json
    link = _link(conn, instance)
    if not link:
        return []
    first = json.loads(link["identity_json"])
    history = [dict(sequence=0, operation_id=link["operation_id"], artifact_digest=link["artifact_digest"],
                    identity=first, context_root_id=link["context_root_id"])]
    for index, row in enumerate(_upgrades(conn, instance["instance_id"]), 1):
        try:
            identity = json.loads(row["identity_json"])
            broken = (row["sequence"] != index or set(identity) != set(_IDENTITY)
                      or fingerprint(identity) != row["identity_digest"]
                      or row["from_artifact_digest"] != history[-1]["artifact_digest"]
                      or identity["kit_fingerprint"] != row["to_artifact_digest"]
                      or any(identity[k] != first[k] for k in _STABLE))
        except (TypeError, ValueError, KeyError):
            broken = True
        if broken:
            raise ProcessError("PROCESS_INSTANCE_CONFLICT", "인스턴스의 고정 이력이 손상되었습니다.", 503)
        history.append(dict(sequence=index, operation_id=row["operation_id"], artifact_digest=row["to_artifact_digest"],
                            identity=identity, context_root_id=link["context_root_id"]))
    return history


def pin_for(conn, instance, artifact_digest):
    """이력 안에서 그 판본의 고정 한 건. 없으면 `None`."""
    return next((p for p in pins(conn, instance) if p["artifact_digest"] == artifact_digest), None)


def current_pin(conn, instance):
    history = pins(conn, instance)
    return history[-1] if history else None


def pin_for_store(store, instance, artifact_digest):
    with store.transaction() as conn:
        return pin_for(conn, instance, artifact_digest)


def _pinned_bundle(conn, pin):
    from core.data_preparation.process_pack_artifacts import stored_bundle
    bundle = stored_bundle(conn, pin["artifact_digest"])
    identity = pin["identity"]
    if (bundle is None or identity["kit_id"] != bundle["kit_id"] or identity["version"] != bundle["version"]
            or identity["kit_fingerprint"] != bundle["artifact_digest"]):
        raise ProcessError("PROCESS_ARTIFACT_UNAVAILABLE", "인스턴스의 원본 지문이 다릅니다.", 503)
    return bundle


def _version_key(version):
    return tuple(int(part) for part in str(version).split("."))


def upgrade_or_get(store, *, operation_id, instance_id, bundle, expected_from, actor):
    """같은 인스턴스를 **새 판본에 고정**한다(이력에 한 줄 추가). 같은 operation 은 멱등.

    ⚠️ 적용본을 지우거나 새로 만들지 않는다 — 인스턴스 ID·결속·판·인증 이력은 그대로다.
    ⚠️ `expected_from` 은 계획을 검토한 시점의 현재 고정이다. 그 사이 바뀌었으면 막는다(CAS).
    ⚠️ 같은 키트의 **더 높은 판본**만 받는다. 내리거나 이미 거친 판본으로 돌아가지 않는다."""
    from core.data_preparation.process_pack_artifacts import pin_bundle, get_bundle
    from core.data_preparation.store import _now
    pin_bundle(store, bundle)
    fixed = get_bundle(store, bundle["artifact_digest"])
    prepare(store)
    with store.transaction() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM kit_instances WHERE instance_id=?", (instance_id,)).fetchone()
        if not row or row["status"] != "active":
            raise ProcessError("PROCESS_INSTANCE_CONFLICT", "업그레이드할 적용본의 상태가 다릅니다.")
        instance = dict(row)
        prior = conn.execute("SELECT * FROM kit_process_instance_upgrades WHERE operation_id=?", (operation_id,)).fetchone()
        history = pins(conn, instance)
        if not history:
            raise ProcessError("PROCESS_INSTANCE_MIGRATION_REQUIRED", "B2 결속이 없는 적용본은 업그레이드할 수 없습니다.")
        if prior:
            if (prior["instance_id"] != instance_id or prior["to_artifact_digest"] != fixed["artifact_digest"]
                    or prior["from_artifact_digest"] != expected_from):
                raise ProcessError("PROCESS_INSTANCE_CONFLICT", "같은 작업으로 다른 업그레이드를 기록할 수 없습니다.")
            pin = pin_for(conn, instance, fixed["artifact_digest"])
            return {**instance, "artifact_digest": pin["artifact_digest"], "context_root_id": pin["context_root_id"],
                    "pinned_version": pin["identity"]["version"]}
        current = history[-1]
        if current["artifact_digest"] != expected_from:
            raise ProcessError("PROCESS_PACK_UPGRADE_CONFLICT", "검토한 뒤 적용본의 고정 판본이 바뀌었습니다. 계획을 다시 확인하십시오.")
        if fixed["kit_id"] != current["identity"]["kit_id"]:
            raise ProcessError("PROCESS_PACK_UPGRADE_INVALID", "다른 키트로는 업그레이드하지 않습니다.", 422)
        if (any(p["artifact_digest"] == fixed["artifact_digest"] for p in history)
                or _version_key(fixed["version"]) <= _version_key(current["identity"]["version"])):
            raise ProcessError("PROCESS_PACK_UPGRADE_INVALID", "더 높은 새 판본으로만 업그레이드합니다.", 422)
        identity = {**{k: current["identity"][k] for k in _STABLE},
                    "version": fixed["version"], "kit_fingerprint": fixed["artifact_digest"]}
        conn.execute("INSERT INTO kit_process_instance_upgrades VALUES(?,?,?,?,?,?,?,?,?)",
                     (operation_id, instance_id, len(history), expected_from, fixed["artifact_digest"],
                      canonical(identity), fingerprint(identity), actor, _now()))
        return {**instance, "artifact_digest": fixed["artifact_digest"], "context_root_id": current["context_root_id"],
                "pinned_version": fixed["version"]}


def pinned_dataset_contract(conn, instance, dataset_contract_key):
    """설치가 고정한 **데이터셋 계약** 하나. 없으면 `None` — 막는 것은 호출자(인증)다.

    ★ 레지스트리(`kit_registry_versions`)는 보지 않는다. 그쪽은 같은 판번을 내용으로 덮는
      mutable 등록부라, 거기서 읽은 계약은 «설치에 고정된 계약» 이 아니다.
    ★ [2026-09-25] 업그레이드한 적용본은 **마지막 고정**의 계약을 쓴다.
    ⚠️ 계약을 싣지 않은 판(1.1.0)에 머문 설치본은 `None` 이다 — 추측으로 다른 판을 찾지 않는다."""
    pin = current_pin(conn, instance)
    if not pin:
        return None
    bundle = _pinned_bundle(conn, pin)
    contracts = (bundle.get("dataset_contracts") or {}).get("contracts") or []
    return next((dict(c) for c in contracts if c["dataset_contract_key"] == dataset_contract_key), None)


def profile_for_instance(store, instance):
    """새 팩은 mutable registry를 baseline으로 읽지 않는다. 기존 판본은 기존 경로 그대로.

    ★ [2026-09-25] 업그레이드한 적용본은 마지막 고정 판본의 프로필이다."""
    with store.transaction() as conn:
        pin = current_pin(conn, instance)
        if pin:
            return _pinned_bundle(conn, pin)["profile"]
    registered = store.get_kit_version(instance["kit_id"], instance["version"])
    if not registered:
        raise ProcessError("PROCESS_ARTIFACT_UNAVAILABLE", "등록된 키트 원본이 없습니다.", 503)
    return registered["profile"]
