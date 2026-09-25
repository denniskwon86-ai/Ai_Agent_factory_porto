"""B1 업무 구성: ECM 안에서 초안·승인판·head CAS·감사 outbox를 원자 저장한다.

새 DB/역할/데이터 인스턴스/앱은 만들지 않는다. 조직 정책은 매 명령 재조회하며
다른 DB와 분산 트랜잭션이라고 주장하지 않는다. UI 연결은 B4의 일이다.
"""
from __future__ import annotations

import copy
import json
import sqlite3
import uuid
from contextlib import contextmanager

from core.enterprise_context.process_schema import (
    ProcessBoundary, ProcessDocument, ProcessError, ProcessNode, canonical, fingerprint,
    validate_document,
)

KEY_WHERE = "tenant_id=? AND context_root_id=? AND entity_mode=? AND scope_node_id=? AND configuration_kind=?"


def uid(prefix):
    return f"{prefix}_{uuid.uuid4().hex}"


def missing():
    return ProcessError("PROCESS_NOT_FOUND", "업무 구성을 찾을 수 없습니다.", 404)


class ProcessConfigurationService:
    def __init__(self, repo=None, store=None):
        if repo is None:
            from core.enterprise_context.repository import ecm_repository
            repo = ecm_repository
        self.repo = repo
        self.store = store

    @contextmanager
    def transaction(self, write=False):
        conn = None
        try:
            conn = self.repo._connect()
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield conn
            conn.commit()
        except sqlite3.Error as exc:
            if conn is not None:
                conn.rollback()
            raise ProcessError("PROCESS_STORAGE_UNAVAILABLE", "업무 구성을 저장·조회하지 못했습니다. 입력을 보존하고 재시도하십시오.", 503) from exc
        finally:
            if conn is not None:
                conn.close()

    @staticmethod
    def _chain(conn, node_id, boundary):
        """실제 ECM 연결 하나에서 활성 OPERATING_PARENT 경로를 읽는다. 오류는 빈 지도 아님."""
        chain = []
        while node_id:
            if node_id in chain:
                raise ProcessError("PROCESS_CONTEXT_UNAVAILABLE", "조직 문맥에 순환이 있습니다.", 503)
            row = conn.execute(
                "SELECT n.*,e.entity_mode,e.status AS entity_status,e.tenant_id AS entity_tenant "
                "FROM organization_nodes n JOIN enterprise_entities e ON n.entity_id=e.entity_id WHERE node_id=?",
                (node_id,)).fetchone()
            if (not row or row["status"] != "ACTIVE" or row["entity_status"] != "ACTIVE"
                    or row["tenant_id"] != boundary.tenant_id or row["entity_tenant"] != boundary.tenant_id
                    or row["entity_mode"] != boundary.entity_mode):
                raise missing()
            chain.append(node_id)
            parents = conn.execute(
                "SELECT from_node_id FROM organization_edges WHERE to_node_id=? AND tenant_id=? "
                "AND relation_type='OPERATING_PARENT' AND status='ACTIVE' "
                "AND (effective_from='' OR effective_from<=?) AND (effective_to='' OR effective_to>?)",
                (node_id, boundary.tenant_id, ProcessConfigurationService._now(),
                 ProcessConfigurationService._now())).fetchall()
            if len(parents) > 1:
                raise ProcessError("PROCESS_CONTEXT_UNAVAILABLE", "단일한 운영 조직 루트를 확인할 수 없습니다.", 503)
            node_id = parents[0][0] if parents else ""
        return chain

    @staticmethod
    def _now():
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    def _authorize(self, conn, boundary, actor, context, action="read"):
        from core import admin_capability as caps
        from core.org_directory import org_directory
        if not actor:
            raise ProcessError("PROCESS_AUTHENTICATION_REQUIRED", "로그인이 필요합니다.", 401)
        if (context.get("tenant_id") != boundary.tenant_id or context.get("entity_mode") != boundary.entity_mode
                or not context.get("scope_node_id")):
            raise missing()
        target = boundary.scope_node_id or boundary.context_root_id
        chain = self._chain(conn, target, boundary)
        selected_chain = self._chain(conn, context["scope_node_id"], boundary)
        if (chain[-1] != boundary.context_root_id or selected_chain[-1] != boundary.context_root_id
                or context["scope_node_id"] not in chain):
            raise missing()
        try:
            user = org_directory.get_user(actor)
            if not user or user.get("status") != "active":
                raise ProcessError("PROCESS_ACTOR_INELIGIBLE", "활성 등록 사용자가 필요합니다.", 403)
            scope = org_directory.resolve_scope(actor, fresh=True)
            if scope.unrestricted and not scope.is_admin:
                raise ProcessError("PROCESS_AUTHORITY_UNAVAILABLE", "업무 구성은 조직 권한 강제 상태에서만 사용할 수 있습니다.", 503)
            rights = caps.resolve(scope, user)
        except ProcessError:
            raise
        except Exception as exc:
            raise ProcessError("PROCESS_AUTHORITY_UNAVAILABLE", "현재 조직 권한을 확인하지 못했습니다.", 503) from exc
        dept = conn.execute("SELECT dept_id FROM organization_nodes WHERE node_id=?", (target,)).fetchone()[0]
        if not scope.is_admin and not ((dept and scope.can_read(dept)) or target in scope.readable_scope_nodes):
            raise missing()
        cap = {"read": caps.PROCESS_CONFIG_READ, "propose": caps.PROCESS_CONFIG_PROPOSE,
               "edit": caps.PROCESS_CONFIG_EDIT, "publish": caps.PROCESS_CONFIG_PUBLISH}[action]
        if not rights.has(cap):
            raise ProcessError("PROCESS_ACTION_FORBIDDEN", "이 업무 구성 작업의 권한이 없습니다.", 403)
        if action != "read" and not scope.is_admin:
            allowed = (scope.writable_dept_ids if action == "propose" else scope.manageable_dept_ids)
            node_allowed = scope.manageable_scope_nodes if action in ("edit", "publish") else set()
            if not ((dept and dept in allowed) or target in node_allowed):
                raise ProcessError("PROCESS_ACTION_FORBIDDEN", "현재 조직 범위의 변경 권한이 없습니다.", 403)
        return rights

    def permitted_actions(self, conn, boundary, actor, context):
        """역할의 capability 합집합이 아니라 해당 경계의 실제 B1 행동을 투영한다."""
        self._authorize(conn, boundary, actor, context, "read")
        actions = ["read"]
        for action, public_name in (("propose", "propose"), ("edit", "edit"), ("publish", "approve")):
            try:
                self._authorize(conn, boundary, actor, context, action)
            except ProcessError as exc:
                # 회수·문맥 유실·권한 조회 장애를 빈 권한이나 일부 성공으로 숨기지 않는다.
                if exc.status_code == 403 and exc.reason_code == "PROCESS_ACTION_FORBIDDEN":
                    continue
                raise
            actions.append(public_name)
        self._authorize(conn, boundary, actor, context, "read")
        return actions

    def resolve_context(self, *, actor, context, company_wide=False):
        """명시 선택 노드의 활성 운영 경로만으로 root를 확정한다. GET은 저장하지 않는다."""
        if type(company_wide) is not bool:
            raise ProcessError("PROCESS_CONTEXT_INVALID", "전사 또는 선택 조직 범위를 명시하십시오.", 422)
        if not isinstance(context, dict) or not context.get("scope_node_id"):
            raise ProcessError("PROCESS_CONTEXT_REQUIRED", "회사·조직 문맥을 명시적으로 선택하십시오.", 422)
        try:
            provisional = ProcessBoundary(tenant_id=context.get("tenant_id"),
                entity_mode=context.get("entity_mode"), context_root_id=context["scope_node_id"],
                scope_node_id=context["scope_node_id"])
        except (TypeError, ValueError) as exc:
            raise ProcessError("PROCESS_CONTEXT_INVALID", "회사·조직·모드 형식을 확인하십시오.", 422) from exc
        with self.transaction() as conn:
            chain = self._chain(conn, context["scope_node_id"], provisional)
            boundary = provisional.model_copy(update={"context_root_id": chain[-1],
                "scope_node_id": "" if company_wide else context["scope_node_id"]})
            actions = self.permitted_actions(conn, boundary, actor, context)
            target = boundary.scope_node_id or boundary.context_root_id
            target_label = conn.execute("SELECT name_ko FROM organization_nodes WHERE node_id=?", (target,)).fetchone()[0]
            root_label = conn.execute("SELECT name_ko FROM organization_nodes WHERE node_id=?", (chain[-1],)).fetchone()[0]
            return {"boundary": boundary.model_dump(), "permitted_actions": actions, "principal_user_id": actor,
                    "selected_scope_node_id": context["scope_node_id"], "company_wide": company_wide,
                    "target_label": target_label, "context_root_label": root_label}

    @staticmethod
    def _head(conn, boundary):
        row = conn.execute(f"SELECT * FROM enterprise_process_heads WHERE {KEY_WHERE}", boundary.key()).fetchone()
        if row:
            ProcessConfigurationService._check_head(conn, dict(row))
        return dict(row) if row else None

    @staticmethod
    def _check_head(conn, head):
        active = conn.execute("SELECT * FROM enterprise_profiles WHERE configuration_id=? AND status='ACTIVE'",
                              (head["configuration_id"],)).fetchall()
        if head["head_version"] == 0 and not head["active_profile_id"] and not active:
            return
        if (head["head_version"] < 1 or not head["active_profile_id"] or len(active) != 1
                or active[0]["profile_id"] != head["active_profile_id"] or not active[0]["approved_at"]
                or active[0]["version"] != head["head_version"]
                or any(active[0][k] != head[k] for k in ("tenant_id", "context_root_id", "entity_mode", "scope_node_id"))):
            raise ProcessError("PROCESS_PROFILE_UNAVAILABLE", "승인 head의 판본·문맥·포인터를 확인하지 못했습니다.", 503)
        try:
            payload = validate_document(json.loads(active[0]["payload_json"]))
            proof = conn.execute("SELECT draft_digest FROM enterprise_process_changes WHERE draft_profile_id=? AND status='APPLIED'",
                                 (head["active_profile_id"],)).fetchone()
            if not proof or payload["configuration_id"] != head["configuration_id"] or fingerprint(payload) != proof[0]:
                raise ValueError("head digest")
        except (ValueError, ProcessError) as exc:
            raise ProcessError("PROCESS_PROFILE_UNAVAILABLE", "현재 승인판의 고정 지문을 확인하지 못했습니다.", 503) from exc

    def _legacy(self, conn, boundary):
        chain = self._chain(conn, boundary.scope_node_id or boundary.context_root_id, boundary)
        placeholders = ",".join("?" for _ in chain)
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM enterprise_profiles WHERE tenant_id=? AND profile_kind='process_profile' "
            f"AND configuration_id='' AND (scope_node_id IN ({placeholders}) OR scope_node_id='') ORDER BY profile_id",
            (boundary.tenant_id, *chain))]
        return rows, fingerprint(rows)

    def _profile(self, conn, profile_id, head, *, approved=True):
        row = conn.execute("SELECT * FROM enterprise_profiles WHERE profile_id=? AND configuration_id=?",
                           (profile_id, head["configuration_id"])).fetchone()
        if not row:
            raise ProcessError("PROCESS_PROFILE_UNAVAILABLE", "고정된 업무 구성 판을 확인하지 못했습니다.", 503)
        if any(row[k] != head[k] for k in ("tenant_id", "context_root_id", "entity_mode", "scope_node_id")):
            raise ProcessError("PROCESS_PROFILE_UNAVAILABLE", "업무 구성 문맥의 무결성을 확인하지 못했습니다.", 503)
        if approved and (not row["approved_at"] or row["status"] not in ("ACTIVE", "ARCHIVED")):
            raise missing()
        try:
            payload = validate_document(json.loads(row["payload_json"]))
            if payload["configuration_id"] != head["configuration_id"]:
                raise ValueError("configuration")
        except (ValueError, ProcessError) as exc:
            raise ProcessError("PROCESS_PROFILE_UNAVAILABLE", "저장된 업무 구성의 형식·무결성을 확인하지 못했습니다.", 503) from exc
        if approved:
            proof = conn.execute("SELECT draft_digest FROM enterprise_process_changes WHERE draft_profile_id=? AND status='APPLIED'", (profile_id,)).fetchone()
            if not proof or proof[0] != fingerprint(payload):
                raise ProcessError("PROCESS_PROFILE_UNAVAILABLE", "승인판의 고정 지문이 다릅니다.", 503)
        return dict(row), payload

    def resolved(self, *, boundary, actor, context, profile_id=""):
        with self.transaction() as conn:
            rights = self._authorize(conn, boundary, actor, context)
            head = self._head(conn, boundary)
            rows, token = self._legacy(conn, boundary)
            base = {"boundary": boundary.model_dump(), "configuration_id": head["configuration_id"] if head else "",
                    "head_version": head["head_version"] if head else 0, "profile_id": "", "digest": "",
                    "state": "UNCONFIGURED", "payload": None, "sources": [],
                    "legacy_token": token, "legacy_review_required": bool(rows),
                    "capabilities": sorted(c for c in rights.capabilities if c.startswith("process_config."))}
            if profile_id and (not head or not conn.execute(
                    "SELECT 1 FROM enterprise_profiles WHERE profile_id=? AND configuration_id=? AND approved_at<>''",
                    (profile_id, head["configuration_id"])).fetchone()):
                raise missing()
            pid = profile_id or (head["active_profile_id"] if head else "")
            if not pid:
                return base
            row, payload = self._profile(conn, pid, head)
            digest = fingerprint(payload)
            return {**base, "state": "APPROVED", "profile_id": pid, "digest": digest, "payload": payload,
                    "sources": [{"profile_id": pid, "digest": digest}], "version": row["version"],
                    "legacy_review_required": False}

    def _commands(self, payload, commands, boundary):
        if not isinstance(commands, list) or not commands or len(commands) > 200:
            raise ProcessError("PROCESS_COMMAND_INVALID", "1~200개의 변경 명령이 필요합니다.", 422)
        doc = copy.deepcopy(payload)
        for command in commands:
            if not isinstance(command, dict):
                raise ProcessError("PROCESS_COMMAND_INVALID", "변경 명령 형식이 잘못되었습니다.", 422)
            kind = command.get("op")
            fields = {"ADD_NODE": {"op", "node"}, "RENAME": {"op", "process_id", "label"},
                      "SET_NOTE": {"op", "process_id", "note"},
                      "REORDER_PLACEMENTS": {"op", "parent_process_id", "placement_ids"},
                      "SET_USAGE": {"op", "process_id", "enabled"},
                      "MOVE_NODE": {"op", "process_id", "parent_process_id"},
                      "ADD_SHORTCUT": {"op", "process_id", "parent_process_id"},
                      "REMOVE_SHORTCUT": {"op", "placement_id"}}
            if not isinstance(kind, str) or kind not in fields or set(command) != fields[kind]:
                raise ProcessError("PROCESS_COMMAND_UNSUPPORTED", "지원하는 변경 명령과 필드를 확인하십시오.", 422)
            nodes = {n["process_id"]: n for n in doc["nodes"]}
            if kind == "ADD_NODE":
                allowed = {"process_id", "level", "parent_process_id", "label", "note"}
                if not isinstance(command["node"], dict) or set(command["node"]) - allowed:
                    raise ProcessError("PROCESS_COMMAND_INVALID", "노드의 관리 필드는 서버가 발급합니다.", 422)
                try:
                    node = ProcessNode.model_validate({**command["node"], "recorded_at": self._now(),
                                                      "owner_scope_node_id": boundary.scope_node_id or boundary.context_root_id}).model_dump()
                except ValueError as exc:
                    raise ProcessError("PROCESS_COMMAND_INVALID", "업무 노드 필드를 확인하십시오.", 422) from exc
                if node["process_id"] in nodes:
                    raise ProcessError("PROCESS_COMMAND_INVALID", "이미 사용 중인 업무 ID입니다.", 422)
                doc["nodes"].append(node)
                doc["placements"].append({"placement_id": uid("placement"), "process_id": node["process_id"],
                                          "parent_process_id": node["parent_process_id"], "kind": "CANONICAL",
                                          "position": len(doc["placements"]), "hidden": False})
            elif kind == "REORDER_PLACEMENTS":
                parent, ordered = command["parent_process_id"], command["placement_ids"]
                if (not isinstance(parent, str)
                        or (parent and (parent not in nodes or nodes[parent]["level"] != "L1"))
                        or not isinstance(ordered, list)
                        or any(not isinstance(pid, str) or not pid for pid in ordered)):
                    raise ProcessError("PROCESS_COMMAND_INVALID", "상위 L1 또는 최상위 빈 ID와 배치 ID 목록을 지정하십시오.", 422)
                # 숨김·미사용·바로가기를 제외하지 않는다. 순서 변경은 부모 이동이나 새 배치 생성이 아니다.
                siblings = [p for p in doc["placements"] if p["parent_process_id"] == parent]
                if len(ordered) != len(set(ordered)) or set(ordered) != {p["placement_id"] for p in siblings}:
                    raise ProcessError("PROCESS_COMMAND_INVALID", "같은 부모의 모든 배치 ID를 중복·누락 없이 지정하십시오.", 422)
                positions = {pid: index for index, pid in enumerate(ordered)}
                for placement in siblings:
                    placement["position"] = positions[placement["placement_id"]]
            elif kind == "REMOVE_SHORTCUT":
                found = next((p for p in doc["placements"] if p["placement_id"] == command["placement_id"] and p["kind"] == "SHORTCUT"), None)
                if not found:
                    raise ProcessError("PROCESS_COMMAND_INVALID", "제거할 바로가기를 확인하십시오.", 422)
                doc["placements"].remove(found)
            else:
                if not isinstance(command["process_id"], str):
                    raise ProcessError("PROCESS_COMMAND_INVALID", "업무 ID는 문자열이어야 합니다.", 422)
                node = nodes.get(command["process_id"])
                if not node:
                    raise ProcessError("PROCESS_COMMAND_INVALID", "변경할 업무 ID를 확인하십시오.", 422)
                if kind == "RENAME":
                    node["label"] = command["label"]
                elif kind == "SET_NOTE":
                    if not isinstance(command["note"], str):
                        raise ProcessError("PROCESS_COMMAND_INVALID", "설명은 문자열이어야 합니다. 빈 문자열로 설명을 비울 수 있습니다.", 422)
                    node["note"] = command["note"]
                elif kind == "SET_USAGE":
                    node["enabled"] = command["enabled"]
                elif kind == "MOVE_NODE":
                    node["parent_process_id"] = command["parent_process_id"]
                    for placement in doc["placements"]:
                        if placement["process_id"] == node["process_id"] and placement["kind"] == "CANONICAL":
                            placement["parent_process_id"] = command["parent_process_id"]
                else:
                    doc["placements"].append({"placement_id": uid("placement"), "process_id": node["process_id"],
                                              "parent_process_id": command["parent_process_id"], "kind": "SHORTCUT",
                                              "position": len(doc["placements"]), "hidden": False})
            doc["local_overrides"].append({"command": copy.deepcopy(command), "base_profile_id": doc["base_profile_id"]})
        return validate_document(doc)

    def propose(self, *, boundary, actor, context, commands, expected_head_version,
                base_profile_id, base_fingerprint, client_request_id, reason,
                configuration_id="", legacy_token=""):
        if not isinstance(client_request_id, str) or not client_request_id.strip() or not isinstance(reason, str) or not reason.strip():
            raise ProcessError("PROCESS_CHANGE_INVALID", "멱등키와 변경 이유가 필요합니다.", 422)
        request_fp = fingerprint({"commands": commands, "head": expected_head_version, "base_profile_id": base_profile_id,
                                  "base_fingerprint": base_fingerprint, "reason": reason, "legacy_token": legacy_token})
        with self.transaction(write=True) as conn:
            self._authorize(conn, boundary, actor, context, "propose")
            head = self._head(conn, boundary)
            if configuration_id and (not head or configuration_id != head["configuration_id"]):
                raise missing()
            if not head:
                cid = uid("process_config")
                conn.execute("INSERT INTO enterprise_process_heads(configuration_id,tenant_id,context_root_id,entity_mode,scope_node_id,configuration_kind) VALUES(?,?,?,?,?,?)", (cid, *boundary.key()))
                head = self._head(conn, boundary)
            prior = conn.execute("SELECT * FROM enterprise_process_changes WHERE configuration_id=? AND actor=? AND client_request_id=?",
                                 (head["configuration_id"], actor, client_request_id)).fetchone()
            if prior:
                if prior["request_fingerprint"] != request_fp:
                    raise ProcessError("PROCESS_IDEMPOTENCY_CONFLICT", "같은 요청 키에 다른 변경이 들어왔습니다.")
                return self._change_result(dict(prior))
            if type(expected_head_version) is not int or head["head_version"] != expected_head_version or head["active_profile_id"] != base_profile_id:
                raise ProcessError("PROCESS_HEAD_CONFLICT", "승인판이 변경되었습니다. 입력을 보존하고 최신 판과 비교하십시오.")
            legacy, current_legacy_token = self._legacy(conn, boundary)
            if base_profile_id:
                _, payload = self._profile(conn, base_profile_id, head)
                if fingerprint(payload) != base_fingerprint:
                    raise ProcessError("PROCESS_DIGEST_CONFLICT", "편집 기준판의 지문이 다릅니다.")
                payload["base_profile_id"], payload["base_fingerprint"] = base_profile_id, base_fingerprint
            else:
                if base_fingerprint:
                    raise ProcessError("PROCESS_DIGEST_CONFLICT", "빈 업무 구성에는 기준판 지문이 없습니다.")
                if legacy:
                    # B2 설치 미리보기에서 범위 대응을 확인한 뒤 이관한다. 추정 자동 이관 금지.
                    raise ProcessError("PROCESS_CONTEXT_REVIEW_REQUIRED", "기존 v1 업무의 회사·모드·범위 대응 검토가 필요합니다.")
                if legacy_token and legacy_token != current_legacy_token:
                    raise ProcessError("PROCESS_LEGACY_CONFLICT", "구 업무 구성이 변경되었습니다. 다시 확인하십시오.")
                payload = ProcessDocument(configuration_id=head["configuration_id"]).model_dump()
            payload = self._commands(payload, commands, boundary)
            pid, change_id, now = uid("prof"), uid("process_change"), self._now()
            self._insert_profile(conn, pid, head, payload, now)
            conn.execute("INSERT INTO enterprise_process_changes(change_id,configuration_id,base_head_version,draft_profile_id,draft_digest,patch_json,legacy_token,actor,reason,status,client_request_id,request_fingerprint,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (change_id, head["configuration_id"], head["head_version"], pid, fingerprint(payload),
                          canonical(commands), current_legacy_token, actor, reason, "DRAFT", client_request_id, request_fp, now))
            return self._change_result(dict(conn.execute("SELECT * FROM enterprise_process_changes WHERE change_id=?", (change_id,)).fetchone()))

    @staticmethod
    def _insert_profile(conn, pid, head, payload, now):
        conn.execute("INSERT INTO enterprise_profiles(profile_id,tenant_id,context_root_id,entity_mode,configuration_id,scope_node_id,industry_code,profile_kind,payload_json,inheritance_mode,status,version,approved_by,approved_at,created_at,updated_at) VALUES(?,?,?,?,?,?,'','process_profile',?,'replace','DRAFT',?,'','',?,?)",
                     (pid, head["tenant_id"], head["context_root_id"], head["entity_mode"], head["configuration_id"],
                      head["scope_node_id"], canonical(payload), head["head_version"] + 1, now, now))

    @staticmethod
    def _change_result(change):
        return {k: change[k] for k in ("change_id", "configuration_id", "base_head_version", "draft_profile_id", "draft_digest", "actor", "reason", "status")}

    def _change(self, conn, change_id, actor, context, action="read"):
        change = conn.execute("SELECT * FROM enterprise_process_changes WHERE change_id=?", (change_id,)).fetchone()
        if not change:
            raise missing()
        head = conn.execute("SELECT * FROM enterprise_process_heads WHERE configuration_id=?", (change["configuration_id"],)).fetchone()
        if not head:
            raise missing()
        head, change = dict(head), dict(change)
        boundary = ProcessBoundary(**{k: head[k] for k in ProcessBoundary.model_fields})
        self._authorize(conn, boundary, actor, context, action)
        self._check_head(conn, head)
        return change, head, boundary

    def validate(self, *, change_id, actor, context, draft_digest):
        with self.transaction() as conn:
            change, head, boundary = self._change(conn, change_id, actor, context, "propose")
            _, payload = self._profile(conn, change["draft_profile_id"], head, approved=False)
            self._check_draft(change, head, payload, draft_digest, change["base_head_version"])
            from core.enterprise_context.process_installation import pending_upgrade, validate_installation_references
            validate_installation_references(payload, boundary, repo=self.repo, store=self.store,
                                             upgrade=pending_upgrade(conn, change))
            return {**self._change_result(change), "payload": payload, "review_required": "DISTINCT_PUBLISHER",
                    "ready_to_review": True, "data_ready": False, "apps_ready": False}

    def _review_documents(self, conn, change, head, boundary):
        """검토 diff는 현재 head가 아닌 초안에 고정된 기준판/제안판이다. 손상은 503."""
        try:
            status = change["status"]
            if status not in ("DRAFT", "APPLIED", "REJECTED") or change["configuration_id"] != head["configuration_id"]:
                raise ValueError("change identity")
            row, payload = self._profile(conn, change["draft_profile_id"], head, approved=status == "APPLIED")
            if (fingerprint(payload) != change["draft_digest"] or row["version"] != change["base_head_version"] + 1
                    or change["base_head_version"] < 0
                    or (status != "APPLIED" and (row["status"] != "DRAFT" or row["approved_at"]))):
                raise ValueError("draft identity or digest")
            base = None
            if payload["base_profile_id"]:
                base_row, base = self._profile(conn, payload["base_profile_id"], head)
                if (base_row["version"] != change["base_head_version"]
                        or fingerprint(base) != payload["base_fingerprint"]):
                    raise ValueError("fixed base identity or digest")
            elif change["base_head_version"] != 0 or payload["base_fingerprint"]:
                raise ValueError("empty base identity")
            patch = json.loads(change["patch_json"])
            operations = conn.execute("SELECT * FROM enterprise_process_installations WHERE change_id=?",
                                      (change["change_id"],)).fetchall()
            operation_id = None
            if isinstance(patch, dict) and patch.get("op") == "INSTALL_PACK":
                if (len(operations) != 1 or patch != {"op": "INSTALL_PACK", "operation_id": operations[0]["operation_id"]}
                        or any(operations[0][k] != getattr(boundary, k) for k in ProcessBoundary.model_fields)):
                    raise ValueError("installation boundary or reference")
                from core.enterprise_context.process_installation import ProcessInstallationService
                operation = ProcessInstallationService(self.repo, self.store)._verified_result(dict(operations[0]), conn, boundary)
                operation_id = operation["operation_id"]
            elif operations or not isinstance(patch, list) or not patch or not all(isinstance(c, dict) for c in patch):
                raise ValueError("change commands")
            return payload, base, operation_id
        except ProcessError as exc:
            if exc.status_code == 503:
                raise
            raise ProcessError("PROCESS_CHANGE_UNAVAILABLE", "변경안의 고정 기준판·제안판을 확인하지 못했습니다.", 503) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise ProcessError("PROCESS_CHANGE_UNAVAILABLE", "변경안의 고정 기준판·제안판을 확인하지 못했습니다.", 503) from exc

    def _review_result(self, conn, change, head, boundary, actor, context, *, detail=False):
        payload, base, operation_id = self._review_documents(conn, change, head, boundary)
        blockers = []
        if change["status"] != "DRAFT":
            blockers.append("PROCESS_CHANGE_NOT_DRAFT")
        else:
            if (change["base_head_version"] != head["head_version"]
                    or payload["base_profile_id"] != head["active_profile_id"]):
                blockers.append("PROCESS_HEAD_CONFLICT")
            if head["head_version"] == 0 and self._legacy(conn, boundary)[1] != change["legacy_token"]:
                blockers.append("PROCESS_LEGACY_CONFLICT")
            from core.enterprise_context.process_installation import pending_upgrade, validate_installation_references
            try:
                validate_installation_references(payload, boundary, repo=self.repo, store=self.store,
                                                 upgrade=pending_upgrade(conn, change))
            except ProcessError as exc:
                # 가용성/저장 형식 장애는 승인 불가 안내로 축소하지 않는다.
                if exc.status_code not in (404, 409):
                    raise
                blockers.append(exc.reason_code)
            except (KeyError, TypeError, ValueError) as exc:
                raise ProcessError("PROCESS_ARTIFACT_UNAVAILABLE", "검토할 설치 참조의 저장 형식을 확인하지 못했습니다.", 503) from exc
        if actor == change["actor"]:
            blockers.append("PROCESS_DISTINCT_REVIEWER_REQUIRED")
        try:
            self._authorize(conn, boundary, actor, context, "publish")
        except ProcessError as exc:
            if exc.status_code != 403 or exc.reason_code != "PROCESS_ACTION_FORBIDDEN":
                raise
            blockers.append(exc.reason_code)
        self._authorize(conn, boundary, actor, context, "read")
        result = {**self._change_result(change), "boundary": boundary.model_dump(),
                  "current_head_version": head["head_version"], "principal_user_id": actor,
                  "permitted_actions": ["read"] if blockers else ["read", "approve"],
                  "review_blockers": list(dict.fromkeys(blockers)), "operation_id": operation_id}
        if detail:
            result.update(payload=payload, base_payload=base)
        return result

    def list_changes(self, *, boundary, actor, context, status="DRAFT", limit=20, offset=0):
        """READ 권한의 정확한 경계 목록. 작성자 필터·전체 개수·GET 저장 부작용 없음."""
        if (type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int
                or not 0 <= offset <= 2**63 - 1):
            raise ProcessError("PROCESS_PAGE_INVALID", "페이지 크기는 1~100, offset은 0 이상의 정수여야 합니다.", 422)
        if not isinstance(status, str) or status not in ("DRAFT", "APPLIED", "REJECTED"):
            raise ProcessError("PROCESS_CHANGE_STATUS_INVALID", "DRAFT, APPLIED, REJECTED 중 하나를 선택하십시오.", 422)
        with self.transaction() as conn:
            self._authorize(conn, boundary, actor, context, "read")
            head = self._head(conn, boundary)
            rows = conn.execute("SELECT * FROM enterprise_process_changes WHERE configuration_id=? AND status=? "
                                "ORDER BY created_at DESC, change_id DESC LIMIT ? OFFSET ?",
                                (head["configuration_id"], status, limit + 1, offset)).fetchall() if head else []
            items = [self._review_result(conn, dict(row), head, boundary, actor, context) for row in rows[:limit]]
            self._authorize(conn, boundary, actor, context, "read")
            return {"items": items, "next_offset": offset + limit if len(rows) > limit else None}

    def get_change(self, *, change_id, boundary, actor, context):
        with self.transaction() as conn:
            self._authorize(conn, boundary, actor, context, "read")
            head = self._head(conn, boundary)
            row = conn.execute("SELECT * FROM enterprise_process_changes WHERE change_id=? AND configuration_id=?",
                               (change_id, head["configuration_id"])).fetchone() if head else None
            if not row:
                raise missing()
            result = self._review_result(conn, dict(row), head, boundary, actor, context, detail=True)
            self._authorize(conn, boundary, actor, context, "read")
            return result

    @staticmethod
    def _check_draft(change, head, payload, digest, expected):
        if change["status"] != "DRAFT":
            raise ProcessError("PROCESS_CHANGE_NOT_DRAFT", "검토 가능한 초안이 아닙니다.")
        if (type(expected) is not int or expected != change["base_head_version"] or head["head_version"] != expected):
            raise ProcessError("PROCESS_HEAD_CONFLICT", "다른 구성이 먼저 승인되었습니다. 변경 입력은 보존되어 있습니다.")
        if digest != change["draft_digest"] or fingerprint(payload) != digest:
            raise ProcessError("PROCESS_DIGEST_CONFLICT", "검토한 초안의 지문이 다릅니다.")
        if payload["base_profile_id"] != head["active_profile_id"]:
            raise ProcessError("PROCESS_HEAD_CONFLICT", "초안의 기준 승인판과 현재 head가 다릅니다.")

    def approve(self, *, change_id, actor, context, expected_head_version, draft_digest, reason):
        """승인. 업그레이드 설치의 초안이면 승인이 **커밋된 뒤** 새 판본을 활성화한다.

        ★ [2026-09-25 Codex §19.1] 같은 승인을 다시 요청하면(아래 멱등 경로) 끊긴 활성화를 잇는다."""
        result = self._approve(change_id=change_id, actor=actor, context=context,
                               expected_head_version=expected_head_version, draft_digest=draft_digest, reason=reason)
        from core.enterprise_context.process_installation import activate_approved_upgrade
        activate_approved_upgrade(self, change_id, actor=actor)
        return result

    def _approve(self, *, change_id, actor, context, expected_head_version, draft_digest, reason):
        if not isinstance(reason, str) or not reason.strip():
            raise ProcessError("PROCESS_REVIEW_REQUIRED", "검토 이유가 필요합니다.", 422)
        with self.transaction(write=True) as conn:
            change, head, boundary = self._change(conn, change_id, actor, context, "publish")
            if actor == change["actor"]:
                raise ProcessError("PROCESS_DISTINCT_REVIEWER_REQUIRED", "작성자와 다른 적격 승인자가 검토해야 합니다.", 403)
            if change["status"] == "APPLIED":
                if (change["review_by"] != actor or change["review_reason"] != reason
                        or change["draft_digest"] != draft_digest or change["base_head_version"] != expected_head_version):
                    raise ProcessError("PROCESS_IDEMPOTENCY_CONFLICT", "이미 승인된 요청의 검토 내용이 다릅니다.")
                return json.loads(change["result_json"])
            row, payload = self._profile(conn, change["draft_profile_id"], head, approved=False)
            self._check_draft(change, head, payload, draft_digest, expected_head_version)
            if row["status"] != "DRAFT" or row["approved_at"]:
                raise ProcessError("PROCESS_PROFILE_IMMUTABLE", "초안의 승인 상태가 변경되었습니다.")
            if head["head_version"] == 0 and self._legacy(conn, boundary)[1] != change["legacy_token"]:
                raise ProcessError("PROCESS_LEGACY_CONFLICT", "편집 도중 구 업무 구성이 변경되었습니다. 다시 검토하십시오.")
            from core.enterprise_context.process_installation import pending_upgrade, validate_installation_references
            validate_installation_references(payload, boundary, repo=self.repo, store=self.store,
                                             upgrade=pending_upgrade(conn, change))
            now, event_id = self._now(), uid("process_event")
            self._authorize(conn, boundary, actor, context, "publish")
            previous = head["active_profile_id"]
            if previous:
                conn.execute("UPDATE enterprise_profiles SET status='ARCHIVED',updated_at=? WHERE profile_id=? AND configuration_id=?",
                             (now, previous, head["configuration_id"]))
            conn.execute("UPDATE enterprise_profiles SET status='ACTIVE',approved_by=?,approved_at=?,updated_at=? WHERE profile_id=?",
                         (actor, now, now, change["draft_profile_id"]))
            updated = conn.execute("UPDATE enterprise_process_heads SET active_profile_id=?,head_version=head_version+1 WHERE configuration_id=? AND head_version=? AND active_profile_id=?",
                                   (change["draft_profile_id"], head["configuration_id"], expected_head_version, previous))
            if updated.rowcount != 1:
                raise ProcessError("PROCESS_HEAD_CONFLICT", "다른 구성이 먼저 승인되었습니다.")
            result = {"change_id": change_id, "configuration_id": head["configuration_id"], "status": "APPLIED",
                      "profile_id": change["draft_profile_id"], "head_version": expected_head_version + 1,
                      "digest": draft_digest, "event_id": event_id, "audit_delivery": "PENDING"}
            conn.execute("UPDATE enterprise_process_changes SET status='APPLIED',review_by=?,review_reason=?,result_json=? WHERE change_id=?",
                         (actor, reason, canonical(result), change_id))
            event = {**result, "actor": actor, "author": change["actor"], "reason": reason, "boundary": boundary.model_dump()}
            conn.execute("INSERT INTO enterprise_process_outbox(event_id,configuration_id,change_id,event_type,payload_json,payload_digest,created_at) VALUES(?,?,?,'PROCESS_CONFIGURATION_APPROVED',?,?,?)",
                         (event_id, head["configuration_id"], change_id, canonical(event), fingerprint(event), now))
            from core.enterprise_context.process_installation import finish_installation
            finish_installation(conn, change, result, now)
            return result

    def events(self, *, boundary, actor, context):
        with self.transaction() as conn:
            self._authorize(conn, boundary, actor, context)
            head = self._head(conn, boundary)
            if not head:
                return []
            rows = conn.execute("SELECT * FROM enterprise_process_outbox WHERE configuration_id=? ORDER BY created_at,event_id", (head["configuration_id"],)).fetchall()
            out = []
            for row in rows:
                event = json.loads(row["payload_json"])
                if fingerprint(event) != row["payload_digest"]:
                    raise ProcessError("PROCESS_EVENT_UNAVAILABLE", "업무 구성 감사 지문을 확인하지 못했습니다.", 503)
                out.append({**event, "audit_delivery": row["delivery_status"]})
            return out

    def reject(self, *, change_id, actor, context, expected_head_version, draft_digest, reason):
        if not isinstance(reason, str) or not reason.strip():
            raise ProcessError("PROCESS_REVIEW_REQUIRED", "반려 이유가 필요합니다.", 422)
        with self.transaction(write=True) as conn:
            change, head, boundary = self._change(conn, change_id, actor, context, "publish")
            if change["status"] == "REJECTED":
                if (change["review_by"] != actor or change["review_reason"] != reason
                        or change["draft_digest"] != draft_digest or change["base_head_version"] != expected_head_version):
                    raise ProcessError("PROCESS_IDEMPOTENCY_CONFLICT", "이미 반려한 요청의 검토 내용이 다릅니다.")
                return json.loads(change["result_json"])
            _, payload = self._profile(conn, change["draft_profile_id"], head, approved=False)
            self._check_draft(change, head, payload, draft_digest, expected_head_version)
            now, event_id = self._now(), uid("process_event")
            result = {"change_id": change_id, "configuration_id": head["configuration_id"], "status": "REJECTED",
                      "head_version": head["head_version"], "event_id": event_id, "audit_delivery": "PENDING"}
            conn.execute("UPDATE enterprise_process_changes SET status='REJECTED',review_by=?,review_reason=?,result_json=? WHERE change_id=?",
                         (actor, reason, canonical(result), change_id))
            event = {**result, "actor": actor, "author": change["actor"], "reason": reason, "boundary": boundary.model_dump()}
            conn.execute("INSERT INTO enterprise_process_outbox(event_id,configuration_id,change_id,event_type,payload_json,payload_digest,created_at) VALUES(?,?,?,'PROCESS_CONFIGURATION_REJECTED',?,?,?)",
                         (event_id, head["configuration_id"], change_id, canonical(event), fingerprint(event), now))
            from core.enterprise_context.process_installation import finish_installation
            finish_installation(conn, change, result, now, rejected=True)
            return result
