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
"""


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


def binding_for_instance(store, instance):
    import json
    with store.transaction() as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='kit_process_instances'").fetchone():
            return None
        link = conn.execute("SELECT * FROM kit_process_instances WHERE instance_id=?", (instance["instance_id"],)).fetchone()
    if not link:
        return None
    expected = json.loads(link["identity_json"])
    if fingerprint(expected) != link["identity_digest"] or any(instance.get(k) != v for k, v in expected.items()):
        raise ProcessError("PROCESS_INSTANCE_CONFLICT", "인스턴스 문맥의 고정 지문이 다릅니다.", 503)
    return dict(link)


def profile_for_instance(store, instance):
    """새 팩은 mutable registry를 baseline으로 읽지 않는다. 기존 판본은 기존 경로 그대로."""
    link = binding_for_instance(store, instance)
    if link:
        from core.data_preparation.process_pack_artifacts import get_bundle
        bundle = get_bundle(store, link["artifact_digest"])
        if (instance["kit_id"] != bundle["kit_id"] or instance["version"] != bundle["version"] or
                instance["kit_fingerprint"] != bundle["artifact_digest"]):
            raise ProcessError("PROCESS_ARTIFACT_UNAVAILABLE", "인스턴스의 원본 지문이 다릅니다.", 503)
        return bundle["profile"]
    registered = store.get_kit_version(instance["kit_id"], instance["version"])
    if not registered:
        raise ProcessError("PROCESS_ARTIFACT_UNAVAILABLE", "등록된 키트 원본이 없습니다.", 503)
    return registered["profile"]
