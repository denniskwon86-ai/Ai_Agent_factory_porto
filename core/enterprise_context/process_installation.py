"""B2 업무키트 설치 사가: ECM 예약 → DP 인스턴스 → ECM 초안 → 별도 승인.

실패 시 남은 인스턴스를 지우지 않으며 같은 operation_id로 재개한다.
plan에는 실제 인증/역할/앱 생성이 포함되지 않는다.
"""
import copy
import json
import sqlite3

from core.enterprise_context.process_configuration import KEY_WHERE, ProcessConfigurationService, uid, missing
from core.enterprise_context.process_schema import ProcessBoundary, ProcessDocument, ProcessError, ProcessNode, canonical, fingerprint, validate_document


def _activation_pending_error():
    return ProcessError("PROCESS_UPGRADE_ACTIVATION_PENDING",
                        "업무판은 새 판본으로 승인됐지만 적용본의 판본 활성화가 끝나지 않았습니다. "
                        "승인자가 같은 승인을 다시 요청하면 활성화를 다시 시도합니다.")


class ProcessInstallationService(ProcessConfigurationService):
    def __init__(self, repo=None, store=None):
        super().__init__(repo, store)
        if store is None:
            from core.data_preparation.store import data_preparation_store
            store = data_preparation_store
        self.store = store

    def _bundle(self, digest):
        from core.data_preparation.process_pack_artifacts import get_bundle
        return get_bundle(self.store, digest)

    def _instance_row(self, instance_id, boundary):
        row = self.store.get_instance(instance_id)
        if not row or any(row[k] != v for k, v in {
                "tenant_id": boundary.tenant_id, "entity_mode": boundary.entity_mode,
                "scope_node_id": boundary.scope_node_id or boundary.context_root_id}.items()):
            raise missing()
        return row

    def _existing_instance(self, instance_id, boundary, bundle):
        """이 번들에 **고정된 적이 있는** 기존 인스턴스.

        ★ [2026-09-25] 업그레이드한 적용본은 같은 ID 로 여러 판본에 고정된 이력을 갖는다 —
          판본 동등이 아니라 이력 소속으로 본다(과거 승인판의 원본도 그대로 검증된다)."""
        from core.data_preparation.process_kit_instances import activation_pending, pin_for_store
        row = self._instance_row(instance_id, boundary)
        if row["status"] != "active" or row["kit_id"] != bundle["kit_id"]:
            raise ProcessError("PROCESS_INSTANCE_CONFLICT", "선택한 인스턴스의 상태·판본이 설치 계획과 다릅니다.")
        pin = pin_for_store(self.store, row, bundle["artifact_digest"])
        if not pin:
            with self.store.transaction() as conn:
                if activation_pending(conn, row, bundle):
                    raise _activation_pending_error()
        if (not pin or pin["context_root_id"] != boundary.context_root_id
                or pin["identity"]["version"] != bundle["version"]):
            raise ProcessError("PROCESS_INSTANCE_MIGRATION_REQUIRED", "기존 인스턴스의 불변 원본 대응을 먼저 검토해야 합니다.")
        return row

    def _upgradable_instance(self, instance_id, boundary, from_digest, bundle):
        """업그레이드 계획의 적용본: 현재 고정이 `from_digest` 이고, 같은 키트의 더 높은 판본이다."""
        from core.data_preparation.process_kit_instances import current_pin, _version_key
        row = self._instance_row(instance_id, boundary)
        if row["status"] != "active" or row["kit_id"] != bundle["kit_id"]:
            raise ProcessError("PROCESS_INSTANCE_CONFLICT", "선택한 인스턴스의 상태·키트가 업그레이드 계획과 다릅니다.")
        with self.store.transaction() as conn:
            pin = current_pin(conn, row)
        if not pin or pin["context_root_id"] != boundary.context_root_id:
            raise ProcessError("PROCESS_INSTANCE_MIGRATION_REQUIRED", "기존 인스턴스의 불변 원본 대응을 먼저 검토해야 합니다.")
        if pin["artifact_digest"] != from_digest:
            raise ProcessError("PROCESS_PACK_UPGRADE_CONFLICT", "적용본의 현재 고정 판본이 계획과 다릅니다. 현재 상태로 다시 계획하십시오.")
        if _version_key(bundle["version"]) <= _version_key(pin["identity"]["version"]):
            raise ProcessError("PROCESS_PACK_UPGRADE_INVALID", "더 높은 새 판본으로만 업그레이드합니다.", 422)
        return row

    def legacy_preview(self, *, boundary, actor, context):
        with self.transaction() as conn:
            self._authorize(conn, boundary, actor, context, "propose")
            rows, token = self._legacy(conn, boundary)
            return {"legacy_token": token, "context": boundary.model_dump(), "sources": [
                {"profile_id": r["profile_id"], "source_digest": fingerprint(r),
                 "status": r["status"], "source_scope_node_id": r["scope_node_id"],
                 "industry_code": r["industry_code"], "payload": json.loads(r["payload_json"]),
                 "review_required": "EXPLICIT_CONTEXT_AND_KEY_MAPPING"} for r in rows]}

    @staticmethod
    def _migrate(payload, rows, decisions, boundary):
        if not rows and not decisions:
            return
        if (not isinstance(decisions, list) or len(decisions) != len(rows) or
                len({d.get("profile_id") for d in decisions}) != len(rows)):
            raise ProcessError("PROCESS_CONTEXT_REVIEW_REQUIRED", "모든 기존 판의 이관 또는 원본 유지 결정을 명시하십시오.")
        mapped = {d["profile_id"]: d for d in decisions}
        used = {n["process_id"] for n in payload["nodes"]}
        for row in rows:
            d = mapped.get(row["profile_id"], {})
            if (set(d) != {"profile_id", "source_digest", "decision", "confirmed_context", "key_mapping"} or
                    d["source_digest"] != fingerprint(row) or d["confirmed_context"] != boundary.model_dump() or
                    d["decision"] not in ("MIGRATE", "KEEP_LEGACY")):
                raise ProcessError("PROCESS_CONTEXT_REVIEW_REQUIRED", "기존 판의 원본 지문과 회사·모드·범위 확인이 필요합니다.")
            raw = json.loads(row["payload_json"])
            if d["decision"] == "KEEP_LEGACY":
                if d["key_mapping"]:
                    raise ProcessError("PROCESS_MIGRATION_INVALID", "원본 유지에는 새 업무 대응을 지정하지 않습니다.", 422)
                payload["migration_map"].append(copy.deepcopy(d))
                continue
            items = raw.get("nodes")
            if not isinstance(items, list) or any(not isinstance(n, dict) or not isinstance(n.get("key"), str) or not n["key"] for n in items):
                raise ProcessError("PROCESS_MIGRATION_INVALID", "v1 업무 key 원형을 확인할 수 없습니다.", 422)
            keys = [n["key"] for n in items]
            if len(set(keys)) != len(keys) or d["key_mapping"] != {key: key for key in keys}:
                raise ProcessError("PROCESS_MIGRATION_INVALID", "기존 key는 이름 추정 없이 같은 process_id로 명시 보존해야 합니다.", 422)
            for n in items:
                key = n["key"]
                if key in used:
                    raise ProcessError("PROCESS_MIGRATION_CONFLICT", "동일 key가 여러 원본에 있습니다. 자동 병합하지 않고 대응 재검토를 요구합니다.")
                used.add(key)
                node = ProcessNode(process_id=key, level="L1", label=n.get("label") or key,
                                   note=n.get("note") or "", origin="LEGACY", legacy_fields=copy.deepcopy(n),
                                   owner_scope_node_id=boundary.scope_node_id or boundary.context_root_id,
                                   source_ref=row["profile_id"]).model_dump()
                payload["nodes"].append(node)
                payload["placements"].append(dict(placement_id="placement_" + fingerprint([row["profile_id"], key])[:32],
                    process_id=key, parent_process_id="", kind="CANONICAL", position=len(payload["placements"]), hidden=False))
            # 명시적 null과 누락 및 노드 외 원본 필드도 버리지 않는다.
            payload["migration_map"].append({**copy.deepcopy(d), "source_payload": raw})

    def plan(self, *, boundary, actor, context, artifact_digest, business_kit_ids,
             expected_head_version, base_profile_id, base_fingerprint, legacy_decisions=None,
             template_mapping=None, instance_id="", reason="", upgrade_from_artifact_digest=""):
        if not isinstance(reason, str) or not reason.strip():
            raise ProcessError("PROCESS_CHANGE_INVALID", "설치 이유가 필요합니다.", 422)
        if (not isinstance(business_kit_ids, list) or not business_kit_ids or
                any(not isinstance(k, str) for k in business_kit_ids) or len(set(business_kit_ids)) != len(business_kit_ids)):
            raise ProcessError("PROCESS_PACK_SELECTION_INVALID", "업무키트를 중복 없이 선택하십시오.", 422)
        with self.transaction() as conn:
            rights = self._authorize(conn, boundary, actor, context, "propose")
            head = self._head(conn, boundary)
            version, pid = (head["head_version"], head["active_profile_id"]) if head else (0, "")
            if type(expected_head_version) is not int or version != expected_head_version or pid != base_profile_id:
                raise ProcessError("PROCESS_HEAD_CONFLICT", "계획의 기준 업무판이 달라졌습니다.")
            payload = self._profile(conn, pid, head)[1] if pid else None
            if (fingerprint(payload) if payload else "") != base_fingerprint:
                raise ProcessError("PROCESS_DIGEST_CONFLICT", "계획 기준판 지문이 다릅니다.")
            legacy, token = self._legacy(conn, boundary)
            bundle = self._bundle(artifact_digest)
            # 합성 Starter를 REAL로 설치하지 않는다. 운영 골격 팩에는 실제값 자체가 없다.
            profile = bundle["profile"]
            if payload:
                existing_source = next((s for s in payload["template_sources"] if s["artifact_digest"] == artifact_digest), None)
                if existing_source and instance_id != existing_source["kit_instance_ref"]:
                    raise ProcessError("PROCESS_INSTANCE_SELECTION_REQUIRED", "이미 설치된 팩의 인스턴스를 명시 선택하십시오.")
            if boundary.entity_mode != "VIRTUAL" and (profile.get("mode") == "DEMO/SYNTHETIC" or
                    profile.get("data_class") == "SYNTHETIC" or profile.get("entity_mode") == "VIRTUAL"):
                raise ProcessError("PROCESS_PACK_MODE_MISMATCH", "합성 Starter는 VIRTUAL 문맥에서만 적용할 수 있습니다.", 422)
            upgrade = bool(upgrade_from_artifact_digest)
            if upgrade:
                if not instance_id or not payload:
                    raise ProcessError("PROCESS_PACK_UPGRADE_INVALID", "업그레이드는 승인 업무판에 설치된 적용본을 명시해야 합니다.", 422)
                self._upgradable_instance(instance_id, boundary, upgrade_from_artifact_digest, bundle)
            elif instance_id:
                self._existing_instance(instance_id, boundary, bundle)
            plan = {"boundary": boundary.model_dump(), "configuration_id": head["configuration_id"] if head else "",
                    "artifact_digest": artifact_digest, "business_kit_ids": sorted(business_kit_ids),
                    "expected_head_version": version, "base_profile_id": pid, "base_fingerprint": base_fingerprint,
                    "legacy_token": token, "legacy_decisions": legacy_decisions or [],
                    "template_mapping": template_mapping or {}, "instance_id": instance_id, "reason": reason}
            if upgrade:
                #: 설치 계획의 지문은 종전과 같게 둔다 — 업그레이드일 때만 이 열쇠가 생긴다.
                plan["upgrade_from_artifact_digest"] = upgrade_from_artifact_digest
            draft = self._document(plan, bundle, payload, legacy, head["configuration_id"] if head else "preview", "preview")
            result = {"plan": plan, "plan_digest": fingerprint(plan), "preview": draft,
                      "state": "PLANNED", "data_ready": False, "apps_ready": False,
                      "warnings": ["DOMAIN_REVIEW_REQUIRED", "DATA_BINDINGS_UNRESOLVED", "DISTINCT_PUBLISHER_REQUIRED"],
                      "capabilities": sorted(rights.capabilities)}
            if upgrade:
                result["upgrade"] = self._upgrade_summary(plan, bundle, payload, draft)
                #: 기존 인증은 이력으로 남지만 새 계약 지문이 없어 운영에는 재인증 뒤에 쓴다.
                result["warnings"].append("RECERTIFICATION_REQUIRED")
            return result

    def _document(self, plan, bundle, previous, legacy, configuration_id, instance_id):
        try:
            return self._build_document(plan, bundle, previous, legacy, configuration_id, instance_id)
        except ProcessError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise ProcessError("PROCESS_MAPPING_INVALID", "명시 이관·표준 대응의 형식과 원본 필드를 확인하십시오.", 422) from exc

    # ── [2026-09-25] 판본 업그레이드 — 같은 적용본, 같은 업무 대응, 새 원본 ─────────────────
    #
    # ★ 업무판을 새로 짓지 않는다. 승인된 현재 판을 **그대로 복사**하고, 그 적용본의 원본 참조
    #   (지문·판본·표준 지문)와 앱 후보의 판본 참조만 바꾼다 — 사용자가 고친 이름·사용 여부·
    #   추가 업무·바로가기·데이터 요구 상태는 손대지 않는다.
    # ⚠️ 설치된 표준 업무의 내용이 두 판본 사이에서 바뀌었으면 자동으로 옮기지 않는다
    #   (`PROCESS_PACK_UPGRADE_REVIEW_REQUIRED`). 앱 후보의 판본 표기 외의 차이는 사람이 검토한다.

    @staticmethod
    def _comparable(template):
        value = copy.deepcopy(template)
        for ref in value.get("suggested_blueprint_refs") or []:
            ref["version"] = ""
        return value

    def _upgrade_basis(self, plan, bundle, previous):
        if not previous:
            raise ProcessError("PROCESS_PACK_UPGRADE_INVALID", "업그레이드할 승인 업무판이 없습니다.", 422)
        from_digest = plan["upgrade_from_artifact_digest"]
        sources = [s for s in previous["template_sources"]
                   if s["kit_instance_ref"] == plan["instance_id"] and s["artifact_digest"] == from_digest]
        if len(sources) != 1:
            raise ProcessError("PROCESS_PACK_UPGRADE_CONFLICT", "현재 승인 업무판에 그 판본의 적용본이 하나로 있지 않습니다.")
        if plan["template_mapping"]:
            raise ProcessError("PROCESS_MAPPING_INVALID", "업그레이드는 기존 업무 대응을 그대로 씁니다.", 422)
        old = self._bundle(from_digest)
        if old["kit_id"] != bundle["kit_id"] or sources[0]["kit_version"] != old["version"]:
            raise ProcessError("PROCESS_PACK_UPGRADE_INVALID", "같은 키트의 설치 원본만 업그레이드합니다.", 422)
        old_templates = {t["template_key"]: t for t in old["pack"]["templates"]}
        new_templates = {t["template_key"]: t for t in bundle["pack"]["templates"]}
        installed = sources[0]["template_process_ids"]
        kits = sorted({old_templates[key]["business_kit_id"] for key in installed if key in old_templates})
        if plan["business_kit_ids"] != kits:
            raise ProcessError("PROCESS_PACK_SELECTION_INVALID", "업그레이드는 설치된 업무키트를 그대로 선택해야 합니다.", 422)
        changed = sorted(key for key in installed if key not in new_templates or key not in old_templates
                         or self._comparable(old_templates[key]) != self._comparable(new_templates[key]))
        if changed:
            raise ProcessError("PROCESS_PACK_UPGRADE_REVIEW_REQUIRED",
                               f"설치된 표준 업무 {len(changed)}개가 새 판본에서 바뀌어 자동으로 옮기지 않습니다 — 업무 대응 검토가 필요합니다.")
        return sources[0], old, installed

    def _upgrade_document(self, plan, bundle, previous):
        _, old, installed = self._upgrade_basis(plan, bundle, previous)
        doc = copy.deepcopy(previous)
        doc["base_profile_id"], doc["base_fingerprint"] = plan["base_profile_id"], plan["base_fingerprint"]
        source = next(s for s in doc["template_sources"]
                      if s["kit_instance_ref"] == plan["instance_id"] and s["artifact_digest"] == plan["upgrade_from_artifact_digest"])
        source.update(artifact_digest=bundle["artifact_digest"], kit_version=bundle["version"],
                      pack_id=bundle["pack"]["pack_id"], pack_version=bundle["pack"]["version"],
                      accepted_standard_digest=bundle["pack_digest"])
        process_ids = set(installed.values())
        #: 표준 노드는 자기 원본 지문(`source_ref`)을 적어 둔다 — 같은 노드(같은 process_id)의 원본만 옮긴다.
        for node in doc["nodes"]:
            if node["process_id"] in process_ids and node["source_ref"] == plan["upgrade_from_artifact_digest"]:
                node["source_ref"] = bundle["artifact_digest"]
        for binding in doc["bindings"]:
            if (binding["kind"] == "BLUEPRINT_SUGGESTION" and binding["process_id"] in process_ids
                    and binding["kit_id"] == old["kit_id"] and binding["kit_version"] == old["version"]):
                binding["kit_version"] = bundle["version"]
        return validate_document(doc)

    def _upgrade_summary(self, plan, bundle, previous, draft):
        _, old, installed = self._upgrade_basis(plan, bundle, previous)
        before = [b for b in previous["bindings"] if b["kind"] == "BLUEPRINT_SUGGESTION"]
        after = [b for b in draft["bindings"] if b["kind"] == "BLUEPRINT_SUGGESTION"]
        return {"instance_id": plan["instance_id"],
                "from": {"version": old["version"], "artifact_digest": old["artifact_digest"],
                         "pack_version": old["pack"]["version"]},
                "to": {"version": bundle["version"], "artifact_digest": bundle["artifact_digest"],
                       "pack_version": bundle["pack"]["version"]},
                "templates_kept": len(installed),
                "process_ids_preserved": sorted(installed.values()) == sorted(
                    next(s for s in draft["template_sources"] if s["kit_instance_ref"] == plan["instance_id"]
                         and s["artifact_digest"] == bundle["artifact_digest"])["template_process_ids"].values()),
                "blueprint_suggestions_updated": sum(1 for x, y in zip(before, after) if x != y),
                "dataset_contracts": len(((bundle.get("dataset_contracts") or {}).get("contracts")) or [])}

    def _build_document(self, plan, bundle, previous, legacy, configuration_id, instance_id):
        if plan.get("upgrade_from_artifact_digest"):
            return self._upgrade_document(plan, bundle, previous)
        boundary = ProcessBoundary(**plan["boundary"])
        doc = copy.deepcopy(previous) if previous else ProcessDocument(configuration_id=configuration_id).model_dump()
        doc["configuration_id"], doc["base_profile_id"], doc["base_fingerprint"] = configuration_id, plan["base_profile_id"], plan["base_fingerprint"]
        if not previous:
            self._migrate(doc, legacy, plan["legacy_decisions"], boundary)
        elif plan["legacy_decisions"]:
            raise ProcessError("PROCESS_MIGRATION_INVALID", "v1 이관은 첫 승인판에서만 수행합니다.", 422)
        templates = bundle["pack"]["templates"]
        known_kits = {t["business_kit_id"] for t in templates}
        if set(plan["business_kit_ids"]) - known_kits:
            raise ProcessError("PROCESS_PACK_SELECTION_INVALID", "이 팩에 없는 업무키트입니다.", 422)
        selected = [t for t in templates if t["business_kit_id"] in plan["business_kit_ids"]]
        selected.sort(key=lambda t: (t["level"], t["template_key"]))
        known = {n["process_id"]: n for n in doc["nodes"]}
        mapping = plan["template_mapping"]
        if not isinstance(mapping, dict) or set(mapping) - {t["template_key"] for t in selected}:
            raise ProcessError("PROCESS_MAPPING_INVALID", "선택한 표준 업무의 명시 대응만 허용합니다.", 422)
        source = next((s for s in doc["template_sources"] if s["artifact_digest"] == bundle["artifact_digest"]), None)
        if source and source["kit_instance_ref"] != instance_id and instance_id != "preview":
            raise ProcessError("PROCESS_INSTANCE_CONFLICT", "기존에 이 팩을 적용한 인스턴스를 명시 선택하십시오.")
        if not source:
            digest = bundle["pack_digest"]
            source = dict(artifact_digest=bundle["artifact_digest"], pack_id=bundle["pack"]["pack_id"],
                          pack_version=bundle["pack"]["version"], kit_id=bundle["kit_id"], kit_version=bundle["version"],
                          initial_standard_digest=digest, accepted_standard_digest=digest,
                          template_process_ids={}, kit_instance_ref=instance_id)
            doc["template_sources"].append(source)
        ids = source["template_process_ids"]
        existing_keys = {n["template_key"]: n["process_id"] for n in doc["nodes"] if n["template_key"]}
        for t in selected:
            key = t["template_key"]
            if key in ids:
                if key in mapping and mapping[key] != ids[key]:
                    raise ProcessError("PROCESS_MAPPING_CONFLICT", "이미 고정된 표준 업무 대응과 다릅니다.")
                continue
            if key in existing_keys:
                raise ProcessError("PROCESS_PACK_UPGRADE_REQUIRED", "다른 팩 판본의 업무 대응은 업데이트 검토가 필요합니다.")
            parent = ids.get(t["parent_template_key"], "")
            pid = mapping.get(key) or "proc_" + fingerprint([boundary.model_dump(), key])[:32]
            if pid in known:
                if key not in mapping or known[pid]["level"] != t["level"] or known[pid]["parent_process_id"] != parent:
                    raise ProcessError("PROCESS_MAPPING_CONFLICT", "기존 업무와 표준의 계층·부모 대응을 명시 검토하십시오.")
                node = known[pid]
                if node["template_key"]:
                    raise ProcessError("PROCESS_MAPPING_CONFLICT", "이미 다른 표준에 대응된 업무입니다.")
                doc["local_overrides"].append({"command": {"op": "ATTACH_TEMPLATE", "process_id": pid, "template_key": key}})
            else:
                if key in mapping:
                    raise ProcessError("PROCESS_MAPPING_INVALID", "대응할 기존 업무를 찾지 못했습니다.", 422)
                node = ProcessNode(process_id=pid, level=t["level"], parent_process_id=parent,
                                   label=t["label"], note=t.get("description", ""), enabled=t["default_selected"],
                                   owner_scope_node_id=boundary.scope_node_id or boundary.context_root_id).model_dump()
                doc["nodes"].append(node)
                known[pid] = node
                doc["placements"].append(dict(placement_id="placement_" + pid, process_id=pid,
                    parent_process_id=parent, kind="CANONICAL", position=len(doc["placements"]), hidden=False))
            node.update(origin="STANDARD", template_key=key, source_ref=bundle["artifact_digest"])
            ids[key] = pid
            for req in t["data_requirements"]:
                doc["bindings"].append(dict(kind="DATA_REQUIREMENT", process_id=pid,
                    requirement_key=req["logical_requirement_key"], candidate_dataset_keys=req["candidate_dataset_keys"],
                    mandatory=req["mandatory"], state="UNRESOLVED"))
            for ref in t["suggested_blueprint_refs"]:
                doc["bindings"].append(dict(kind="BLUEPRINT_SUGGESTION", process_id=pid, kit_id=ref["kit_id"],
                    kit_version=ref["version"], app_id=ref["app_id"], state="CANDIDATE_ONLY"))
        # 바로가기만 필요한 다른 키트의 정본 노드를 자동 생성하지 않는다.
        all_ids = {n["template_key"]: n["process_id"] for n in doc["nodes"] if n["template_key"]}
        for t in selected:
            for ref in t["shortcut_refs"]:
                if any(r["from_process_id"] == ids[t["template_key"]] and r["target_template_key"] == ref["target_template_key"] for r in doc["relations"]):
                    continue
                target = all_ids.get(ref["target_template_key"], "")
                doc["relations"].append(dict(kind="SHORTCUT_REQUIREMENT", from_process_id=ids[t["template_key"]],
                    target_template_key=ref["target_template_key"], target_business_kit_id=ref["target_business_kit_id"],
                    target_process_id=target, state="RESOLVED" if target else "UNINSTALLED"))
        for ref in doc["relations"]:
            target = all_ids.get(ref["target_template_key"], "")
            ref.update(target_process_id=target, state="RESOLVED" if target else "UNINSTALLED")
        return validate_document(doc)

    def start(self, *, plan_digest, client_request_id, boundary, actor, context, **request):
        if not isinstance(client_request_id, str) or not client_request_id.strip():
            raise ProcessError("PROCESS_CHANGE_INVALID", "설치 멱등키가 필요합니다.", 422)
        request_fp = fingerprint({"request": request, "plan_digest": plan_digest, "actor": actor})
        with self.transaction(write=True) as conn:
            self._authorize(conn, boundary, actor, context, "propose")
            prior = conn.execute("SELECT * FROM enterprise_process_installations WHERE tenant_id=? AND context_root_id=? AND entity_mode=? AND scope_node_id=? AND client_request_id=?",
                                 (*boundary.key()[:4], client_request_id)).fetchone()
            if prior:
                if prior["request_fingerprint"] != request_fp:
                    raise ProcessError("PROCESS_IDEMPOTENCY_CONFLICT", "동일 설치 키에 다른 요청이 들어왔습니다.")
                return self._response(dict(prior), conn, actor, context)
        preview = self.plan(boundary=boundary, actor=actor, context=context, **request)
        if preview["plan_digest"] != plan_digest:
            raise ProcessError("PROCESS_PLAN_CONFLICT", "검토한 설치 계획이 달라졌습니다. 계획을 다시 확인하십시오.")
        plan = preview["plan"]
        with self.transaction(write=True) as conn:
            rights = self._authorize(conn, boundary, actor, context, "propose")
            prior = conn.execute("SELECT * FROM enterprise_process_installations WHERE tenant_id=? AND context_root_id=? AND entity_mode=? AND scope_node_id=? AND client_request_id=?",
                                 (*boundary.key()[:4], client_request_id)).fetchone()
            if prior:
                if prior["request_fingerprint"] != request_fp:
                    raise ProcessError("PROCESS_IDEMPOTENCY_CONFLICT", "동일 설치 키에 다른 요청이 들어왔습니다.")
                return self._response(dict(prior), conn, actor, context)
            head = self._head(conn, boundary)
            if not head:
                conn.execute("INSERT INTO enterprise_process_heads(configuration_id,tenant_id,context_root_id,entity_mode,scope_node_id,configuration_kind) VALUES(?,?,?,?,?,?)", (uid("process_config"), *boundary.key()))
                head = self._head(conn, boundary)
            self._check_plan(conn, plan, head, boundary)
            now = self._now()
            from core.admin_capability import PROCESS_CONFIG_EDIT, PROJECT_CREATE
            stage = "PLANNED" if rights.has(PROCESS_CONFIG_EDIT) and rights.has(PROJECT_CREATE) else "AWAITING_INSTALLER"
            row = dict(operation_id=uid("process_install"), **boundary.model_dump(), configuration_id=head["configuration_id"],
                       plan_digest=plan_digest, plan_json=canonical(plan), actor=actor, client_request_id=client_request_id,
                       request_fingerprint=request_fp, stage=stage, created_at=now, updated_at=now)
            conn.execute(f"INSERT INTO enterprise_process_installations ({','.join(row)}) VALUES ({','.join('?' for _ in row)})", tuple(row.values()))
            return self._response(dict(conn.execute("SELECT * FROM enterprise_process_installations WHERE operation_id=?", (row["operation_id"],)).fetchone()), conn, actor, context)

    def _check_plan(self, conn, plan, head, boundary):
        if not head:
            raise ProcessError("PROCESS_PROFILE_UNAVAILABLE", "설치 계획의 업무 head를 확인하지 못했습니다.", 503)
        if head["head_version"] != plan["expected_head_version"] or head["active_profile_id"] != plan["base_profile_id"]:
            raise ProcessError("PROCESS_HEAD_CONFLICT", "계획 이후 승인 업무판이 바뀌었습니다. 원본을 보존하고 새 계획을 만드십시오.")
        if self._legacy(conn, boundary)[1] != plan["legacy_token"] and head["head_version"] == 0:
            raise ProcessError("PROCESS_LEGACY_CONFLICT", "이관 원본이 바뀌었습니다. 계획을 다시 검토하십시오.")
        if head["active_profile_id"] and fingerprint(self._profile(conn, head["active_profile_id"], head)[1]) != plan["base_fingerprint"]:
            raise ProcessError("PROCESS_DIGEST_CONFLICT", "고정 기준판의 지문이 다릅니다.")

    def _operation(self, conn, operation_id, actor, context, action="read"):
        row = conn.execute("SELECT * FROM enterprise_process_installations WHERE operation_id=?", (operation_id,)).fetchone()
        if not row:
            raise missing()
        row = dict(row)
        boundary = ProcessBoundary(**{k: row[k] for k in ProcessBoundary.model_fields})
        self._authorize(conn, boundary, actor, context, action)
        self._read_plan(row, boundary)
        return row, boundary

    @staticmethod
    def _read_plan(row, boundary):
        try:
            plan = json.loads(row["plan_json"])
            if (not isinstance(plan, dict) or fingerprint(plan) != row["plan_digest"]
                    or plan["boundary"] != boundary.model_dump()
                    or plan["configuration_id"] not in ("", row["configuration_id"])):
                raise ValueError("plan identity")
            return plan
        except (KeyError, TypeError, ValueError) as exc:
            raise ProcessError("PROCESS_PLAN_UNAVAILABLE", "설치 계획의 고정 지문·문맥을 확인하지 못했습니다.", 503) from exc

    def _verified_result(self, row, conn, boundary):
        """목록과 단건 GET의 동일 검증. 과거 APPLIED를 현재 head와 같다고 요구하지 않는다."""
        plan = self._read_plan(row, boundary)
        try:
            head = self._head(conn, boundary)
            stages = {"PLANNED", "AWAITING_INSTALLER", "PREPARING", "AWAITING_APPROVAL", "APPLIED",
                      "FAILED_BLOCKED", "FAILED_RETRYABLE", "CANCELLED"}
            if (not head or head["configuration_id"] != row["configuration_id"]
                    or row["stage"] not in stages or type(row["revision"]) is not int or row["revision"] < 0):
                raise ValueError("operation identity")
            change = None
            if row["change_id"]:
                change = conn.execute("SELECT * FROM enterprise_process_changes WHERE change_id=?",
                                      (row["change_id"],)).fetchone()
                expected_status = {"AWAITING_APPROVAL": "DRAFT", "APPLIED": "APPLIED",
                                   "FAILED_BLOCKED": "REJECTED"}.get(row["stage"])
                if (not change or not expected_status or change["status"] != expected_status
                        or change["configuration_id"] != row["configuration_id"]
                        or change["actor"] != row["actor"]
                        or change["base_head_version"] != plan["expected_head_version"]
                        or change["reason"] != plan["reason"] or change["legacy_token"] != plan["legacy_token"]
                        or change["client_request_id"] != "installation:" + row["operation_id"]
                        or change["request_fingerprint"] != row["request_fingerprint"]
                        or json.loads(change["patch_json"]) != {"op": "INSTALL_PACK", "operation_id": row["operation_id"]}):
                    raise ValueError("change identity")
                _, payload = self._profile(conn, change["draft_profile_id"], head, approved=row["stage"] == "APPLIED")
                if (fingerprint(payload) != change["draft_digest"] or not row["kit_instance_ref"]
                        or payload["base_profile_id"] != plan["base_profile_id"]
                        or payload["base_fingerprint"] != plan["base_fingerprint"]
                        or not any(s["artifact_digest"] == plan["artifact_digest"]
                                   and s["kit_instance_ref"] == row["kit_instance_ref"] for s in payload["template_sources"])):
                    raise ValueError("change digest or instance")
            elif row["stage"] in ("AWAITING_APPROVAL", "APPLIED"):
                raise ValueError("change missing")
            if row["stage"] == "APPLIED":
                result = json.loads(row["result_json"])
                if (not isinstance(result, dict) or result != json.loads(change["result_json"])
                        or result["status"] != "APPLIED" or result["change_id"] != row["change_id"]
                        or result["configuration_id"] != row["configuration_id"]
                        or result["profile_id"] != row["applied_profile_id"]
                        or result["profile_id"] != change["draft_profile_id"]
                        or result["digest"] != change["draft_digest"]
                        or result["head_version"] != change["base_head_version"] + 1 or not row["applied_at"]):
                    raise ValueError("applied result")
                event = conn.execute("SELECT * FROM enterprise_process_outbox WHERE event_id=?", (result["event_id"],)).fetchone()
                if not event or event["configuration_id"] != row["configuration_id"] or event["change_id"] != row["change_id"]:
                    raise ValueError("approval evidence")
                proof = json.loads(event["payload_json"])
                if (event["event_type"] != "PROCESS_CONFIGURATION_APPROVED"
                        or fingerprint(proof) != event["payload_digest"] or proof["boundary"] != boundary.model_dump()
                        or any(proof.get(k) != v for k, v in result.items())):
                    raise ValueError("approval evidence digest")
            elif row["result_json"] or row["applied_profile_id"] or row["applied_at"]:
                raise ValueError("unapplied result")
            return self._result(row, conn)
        except ProcessError as exc:
            if exc.status_code == 503:
                raise
            # 자원 접근은 이미 검사했다. 여기서 유실된 고정 승인판은 비가시 404가 아니라 손상이다.
            raise ProcessError("PROCESS_INSTALLATION_UNAVAILABLE", "설치 작업의 고정 승인판을 확인하지 못했습니다.", 503) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise ProcessError("PROCESS_INSTALLATION_UNAVAILABLE", "설치 작업과 연결된 변경안·승인 결과의 무결성을 확인하지 못했습니다.", 503) from exc

    @staticmethod
    def _result(row, conn):
        result = {k: row[k] for k in ("operation_id", "configuration_id", "plan_digest", "stage", "error_code",
                   "kit_instance_ref", "change_id", "actor", "installer", "applied_profile_id", "applied_at", "revision")}
        if row["change_id"]:
            change = conn.execute("SELECT * FROM enterprise_process_changes WHERE change_id=?", (row["change_id"],)).fetchone()
            if change:
                result["change"] = ProcessConfigurationService._change_result(dict(change))
        result.update(data_ready=False, apps_ready=False)
        if row["result_json"]:
            result["applied_result"] = json.loads(row["result_json"])
        return result

    def _operation_actions(self, row, conn, boundary, actor, context):
        """현재 단계·정확한 범위 권한으로 재개 행동을 투영한다. 저장된 결과에는 섞지 않는다."""
        from core.admin_capability import PROJECT_CREATE
        self._authorize(conn, boundary, actor, context, "read")
        actions = []
        if not row["change_id"] and row["stage"] in ("PLANNED", "AWAITING_INSTALLER", "PREPARING", "FAILED_RETRYABLE"):
            try:
                rights = self._authorize(conn, boundary, actor, context, "edit")
            except ProcessError as exc:
                if exc.status_code != 403 or exc.reason_code != "PROCESS_ACTION_FORBIDDEN":
                    raise
            else:
                if rights.has(PROJECT_CREATE):
                    plan = self._read_plan(row, boundary)
                    try:
                        self._check_plan(conn, plan, self._head(conn, boundary), boundary)
                    except ProcessError as exc:
                        if exc.status_code != 409 or exc.reason_code not in ("PROCESS_HEAD_CONFLICT", "PROCESS_LEGACY_CONFLICT", "PROCESS_DIGEST_CONFLICT"):
                            raise
                    except (KeyError, TypeError, ValueError) as exc:
                        raise ProcessError("PROCESS_PLAN_UNAVAILABLE", "재개할 설치 계획의 필수 필드를 확인하지 못했습니다.", 503) from exc
                    else:
                        actions = ["resume" if actor == (row["installer"] or row["actor"]) else "adopt"]
        self._authorize(conn, boundary, actor, context, "read")
        return actions

    def upgrade_view(self, row, plan, conn, actor=None):
        """[§19.1] 업그레이드 작업의 판본 활성화 상태. 업그레이드가 아니면 `None`. `conn` 은 ECM 연결.

        ECM 단계와 DP 고정 이력에서 **유도**한다(따로 저장한 상태가 없다):
        승인 전 `NOT_REQUESTED`·`AWAITING_APPROVAL`, 반려·취소 `NOT_ACTIVATED`,
        승인 뒤 이 작업의 고정이 이력에 있으면 `ACTIVE`, 없으면 `ACTIVATION_PENDING`
        (+ 마지막 활성화 실패 사유 `activation_error` — 감사 사건에서 읽는다. 시도 전이면 빈 문자열).

        ★ [2026-09-26 Codex §20 결정] 복구는 **같은 승인자의 같은 승인 재요청**만이다. 그래서 활성화
          대기일 때 그 승인자(`actor == review_by`)에게만 다시 보낼 값(`retry`)을 준다 — 화면이 원래
          승인 이유를 기억하지 않아도 같은 요청을 재현할 수 있게. 다른 사람에게는 주지 않는다."""
        from core.data_preparation.process_kit_instances import pin_for_store
        if not plan.get("upgrade_from_artifact_digest"):
            return None
        stage = row["stage"]
        view = {"instance_id": plan["instance_id"], "from_artifact_digest": plan["upgrade_from_artifact_digest"],
                "to_artifact_digest": plan["artifact_digest"],
                "from_version": self._bundle(plan["upgrade_from_artifact_digest"])["version"],
                "to_version": self._bundle(plan["artifact_digest"])["version"]}
        if stage == "APPLIED":
            instance = self.store.get_instance(plan["instance_id"])
            pin = pin_for_store(self.store, instance, plan["artifact_digest"]) if instance else None
            if pin and pin["operation_id"] == row["operation_id"]:
                return {**view, "activation": "ACTIVE"}
            last = conn.execute("SELECT payload_json FROM enterprise_process_outbox WHERE change_id=? AND event_type=? "
                                "ORDER BY created_at DESC, event_id DESC LIMIT 1",
                                (row["change_id"], ACTIVATION_FAILED)).fetchone()
            view.update(activation="ACTIVATION_PENDING",
                        activation_error=json.loads(last["payload_json"])["reason_code"] if last else "")
            change = conn.execute("SELECT * FROM enterprise_process_changes WHERE change_id=?", (row["change_id"],)).fetchone()
            if actor and change and change["status"] == "APPLIED" and change["review_by"] == actor:
                view["retry"] = {"change_id": change["change_id"], "expected_head_version": change["base_head_version"],
                                 "draft_digest": change["draft_digest"], "reason": change["review_reason"]}
            return view
        return {**view, "activation": {"AWAITING_APPROVAL": "AWAITING_APPROVAL", "FAILED_BLOCKED": "NOT_ACTIVATED",
                                       "CANCELLED": "NOT_ACTIVATED"}.get(stage, "NOT_REQUESTED")}

    def _with_upgrade(self, result, row, boundary, conn, actor=None):
        view = self.upgrade_view(row, self._read_plan(row, boundary), conn, actor)
        return {**result, "upgrade": view} if view else result

    def _response(self, row, conn, actor, context):
        boundary = ProcessBoundary(**{k: row[k] for k in ProcessBoundary.model_fields})
        return self._with_upgrade({**self._result(row, conn),
                                   "permitted_actions": self._operation_actions(row, conn, boundary, actor, context)},
                                  row, boundary, conn, actor)

    def get(self, *, operation_id, actor, context):
        with self.transaction() as conn:
            row, boundary = self._operation(conn, operation_id, actor, context)
            result = self._with_upgrade(self._verified_result(row, conn, boundary), row, boundary, conn, actor)
            result["permitted_actions"] = self._operation_actions(row, conn, boundary, actor, context)
            self._authorize(conn, boundary, actor, context, "read")
            return result

    def list_operations(self, *, boundary, actor, context, limit=20, offset=0):
        """정확한 경계 한 곳만 읽는다. 재개/DP 생성/감사 outbox 전달을 수행하지 않는다."""
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= 2**63 - 1:
            raise ProcessError("PROCESS_PAGE_INVALID", "페이지 크기는 1~100, offset은 0 이상의 정수여야 합니다.", 422)
        with self.transaction() as conn:
            self._authorize(conn, boundary, actor, context, "read")
            self._head(conn, boundary)
            rows = conn.execute(f"SELECT * FROM enterprise_process_installations WHERE {KEY_WHERE} "
                                "ORDER BY created_at DESC, operation_id DESC LIMIT ? OFFSET ?",
                                (*boundary.key(), limit + 1, offset)).fetchall()
            items = [self._with_upgrade({**self._verified_result(dict(row), conn, boundary),
                                         "permitted_actions": self._operation_actions(dict(row), conn, boundary, actor, context)},
                                        dict(row), boundary, conn, actor)
                     for row in rows[:limit]]
            # 조회 중 다른 연결에서 회수한 권한도 응답 직전에 재조회한다.
            self._authorize(conn, boundary, actor, context, "read")
            return {"items": items, "next_offset": offset + limit if len(rows) > limit else None}

    def resume(self, *, operation_id, actor, context, expected_revision, adopt=False):
        # ECM 승인판을 잠근 채 다른 DB를 분산 commit하지 않는다. 각 경계에서 현재 권한 재조회.
        with self.transaction(write=True) as conn:
            row, boundary = self._operation(conn, operation_id, actor, context, "edit")
            if row["stage"] == "APPLIED":
                return self._response(row, conn, actor, context)
            if type(expected_revision) is not int or row["revision"] != expected_revision:
                raise ProcessError("PROCESS_OPERATION_CONFLICT", "설치 작업의 시도가 변경되었습니다. 최신 상태를 확인하십시오.")
            if row["stage"] in ("CANCELLED", "FAILED_BLOCKED"):
                raise ProcessError("PROCESS_INSTALLATION_BLOCKED", "새 계획이나 검토가 필요한 설치 작업입니다.")
            if actor != (row["installer"] or row["actor"]) and adopt is not True:
                raise ProcessError("PROCESS_INSTALLER_ADOPTION_REQUIRED", "다른 작성자의 계획을 담당 설치자로 명시 인수하십시오.", 403)
            from core.admin_capability import PROJECT_CREATE
            rights = self._authorize(conn, boundary, actor, context, "edit")
            if not rights.has(PROJECT_CREATE):
                raise ProcessError("PROCESS_INSTALLER_REQUIRED", "인스턴스를 적용할 현재 권한이 필요합니다.", 403)
            plan = json.loads(row["plan_json"])
            head = self._head(conn, boundary)
            self._check_plan(conn, plan, head, boundary)
            if row["change_id"]:
                return self._response(row, conn, actor, context)
            attempt_id = uid("install_attempt")
            now = self._now()
            conn.execute("UPDATE enterprise_process_installations SET stage='PREPARING',installer=?,error_code='',revision=revision+1,attempt_id=?,updated_at=? WHERE operation_id=? AND revision=?",
                         (actor, attempt_id, now, operation_id, expected_revision))
            event = {"operation_id": operation_id, "attempt_id": attempt_id, "previous_installer": row["installer"],
                     "installer": actor, "adopted": adopt, "revision": expected_revision + 1, "plan_digest": row["plan_digest"]}
            conn.execute("INSERT INTO enterprise_process_outbox(event_id,configuration_id,change_id,event_type,payload_json,payload_digest,created_at) VALUES(?,?,?,'PROCESS_INSTALLATION_RESUMED',?,?,?)",
                         (uid("process_event"), row["configuration_id"], "", canonical(event), fingerprint(event), now))
        try:
            bundle = self._bundle(plan["artifact_digest"])
            if plan.get("upgrade_from_artifact_digest"):
                #: ★★ [2026-09-25 Codex §19.1] 명시 적용은 **승인 대기 기록만** 만든다 — 이 작업의
                #:   AWAITING_APPROVAL 과 초안이 그 기록이다. DP 고정 판본은 바꾸지 않는다(검토한 현재
                #:   고정 지문 CAS 만 다시 확인). 활성 판본 전환은 업무판 승인이 커밋된 **뒤**
                #:   `activate_approved_upgrade` 가 한다 — 반려·취소·승인 전에는 옛 판본이 그대로 활성이다.
                with self.transaction() as conn:
                    if not self._authorize(conn, boundary, actor, context, "edit").has(PROJECT_CREATE):
                        raise ProcessError("PROCESS_INSTALLER_REQUIRED", "적용본을 업그레이드할 현재 권한이 필요합니다.", 403)
                instance = self._upgradable_instance(plan["instance_id"], boundary,
                                                     plan["upgrade_from_artifact_digest"], bundle)
            elif plan["instance_id"]:
                instance = self._existing_instance(plan["instance_id"], boundary, bundle)
            else:
                from core.data_preparation.process_kit_instances import create_or_get
                # 권한 확인 실패 시 DP의 생성 부작용 없이 멈춘다.
                with self.transaction() as conn:
                    if not self._authorize(conn, boundary, actor, context, "edit").has(PROJECT_CREATE):
                        raise ProcessError("PROCESS_INSTALLER_REQUIRED", "인스턴스를 적용할 현재 권한이 필요합니다.", 403)
                instance = create_or_get(self.store, operation_id=operation_id, bundle=bundle, boundary=boundary, actor=actor)
            with self.transaction(write=True) as conn:
                row, boundary = self._operation(conn, operation_id, actor, context, "edit")
                if row["change_id"] or row["stage"] == "APPLIED":
                    return self._response(row, conn, actor, context)
                if row["stage"] != "PREPARING" or row["installer"] != actor or row["attempt_id"] != attempt_id:
                    raise ProcessError("PROCESS_INSTALLATION_CONFLICT", "설치 단계가 변경되었습니다.")
                head = self._head(conn, boundary)
                self._check_plan(conn, plan, head, boundary)
                previous = self._profile(conn, head["active_profile_id"], head)[1] if head["active_profile_id"] else None
                legacy = self._legacy(conn, boundary)[0]
                doc = self._document(plan, bundle, previous, legacy, head["configuration_id"], instance["instance_id"])
                pid, cid, now = uid("prof"), uid("process_change"), self._now()
                self._insert_profile(conn, pid, head, doc, now)
                conn.execute("INSERT INTO enterprise_process_changes(change_id,configuration_id,base_head_version,draft_profile_id,draft_digest,patch_json,legacy_token,actor,reason,status,client_request_id,request_fingerprint,created_at) VALUES(?,?,?,?,?,?,?,?,?,'DRAFT',?,?,?)",
                             (cid, head["configuration_id"], head["head_version"], pid, fingerprint(doc),
                              canonical({"op": "INSTALL_PACK", "operation_id": operation_id}), plan["legacy_token"],
                              row["actor"], plan["reason"], "installation:" + operation_id, row["request_fingerprint"], now))
                conn.execute("UPDATE enterprise_process_installations SET stage='AWAITING_APPROVAL',kit_instance_ref=?,change_id=?,revision=revision+1,updated_at=? WHERE operation_id=? AND attempt_id=?", (instance["instance_id"], cid, now, operation_id, attempt_id))
                return self._response(dict(conn.execute("SELECT * FROM enterprise_process_installations WHERE operation_id=?", (operation_id,)).fetchone()), conn, actor, context)
        except (ProcessError, sqlite3.Error) as exc:
            # 실패한 DP 단계는 보존. 복구 상태 기록마저 실패해도 원 요청 오류를 숨기지 않는다.
            code = getattr(exc, "reason_code", "PROCESS_STORAGE_UNAVAILABLE")
            blocked = code in {"PROCESS_HEAD_CONFLICT", "PROCESS_LEGACY_CONFLICT", "PROCESS_PLAN_UNAVAILABLE", "IMMUTABLE_VERSION_CONFLICT",
                               "PROCESS_PACK_UPGRADE_CONFLICT", "PROCESS_PACK_UPGRADE_INVALID",
                               "PROCESS_PACK_UPGRADE_REVIEW_REQUIRED"}
            try:
                with self.transaction(write=True) as conn:
                    conn.execute("UPDATE enterprise_process_installations SET stage=?,error_code=?,revision=revision+1,updated_at=? WHERE operation_id=? AND stage='PREPARING' AND attempt_id=?",
                                 ("FAILED_BLOCKED" if blocked else "FAILED_RETRYABLE", code, self._now(), operation_id, attempt_id))
            except ProcessError:
                pass
            if isinstance(exc, ProcessError):
                raise
            raise ProcessError("PROCESS_STORAGE_UNAVAILABLE", "설치 입력과 생성된 인스턴스를 보존했습니다. 같은 작업으로 재개하십시오.", 503) from exc

    def cancel(self, *, operation_id, actor, context):
        with self.transaction(write=True) as conn:
            row, _ = self._operation(conn, operation_id, actor, context, "propose")
            if row["actor"] != actor:
                raise ProcessError("PROCESS_ACTION_FORBIDDEN", "계획 작성자만 취소할 수 있습니다.", 403)
            if row["stage"] not in ("PLANNED", "AWAITING_INSTALLER", "FAILED_BLOCKED", "FAILED_RETRYABLE", "CANCELLED") or row["change_id"]:
                raise ProcessError("PROCESS_INSTALLATION_CONFLICT", "준비 중이거나 검토에 제출된 작업은 취소할 수 없습니다.")
            conn.execute("UPDATE enterprise_process_installations SET stage='CANCELLED',updated_at=? WHERE operation_id=?", (self._now(), operation_id))
            row["stage"] = "CANCELLED"
            return self._response(row, conn, actor, context)


def validate_installation_references(payload, boundary, *, repo=None, store=None, upgrade=None):
    """초안·승인판의 설치 참조가 DP 에 실제로 고정돼 있는가.

    ★ [2026-09-25 Codex §19.1] `upgrade` 는 **이 변경안이 승인을 기다리는** 업그레이드다
      (`pending_upgrade`). 그 원본 하나만은 아직 활성 판본이 아니므로 «지금 고정이 검토한 옛
      판본이고, 같은 키트의 더 높은 판본인가» 로 본다. 그 밖의 원본은 이미 고정돼 있어야 한다."""
    if not payload["template_sources"]:
        return
    service = ProcessInstallationService(repo, store)
    for source in payload["template_sources"]:
        bundle = service._bundle(source["artifact_digest"])
        if (upgrade and source["kit_instance_ref"] == upgrade["instance_id"]
                and source["artifact_digest"] == upgrade["to_artifact_digest"]):
            service._upgradable_instance(source["kit_instance_ref"], boundary, upgrade["from_artifact_digest"], bundle)
        else:
            service._existing_instance(source["kit_instance_ref"], boundary, bundle)
        if (source["kit_id"] != bundle["kit_id"] or source["kit_version"] != bundle["version"] or
                source["pack_id"] != bundle["pack"]["pack_id"] or source["pack_version"] != bundle["pack"]["version"] or
                source["accepted_standard_digest"] != bundle["pack_digest"]):
            raise ProcessError("PROCESS_ARTIFACT_UNAVAILABLE", "승인할 업무의 고정 팩 참조가 다릅니다.", 503)


def finish_installation(conn, change, result, now, *, rejected=False):
    """반드시 업무판 승인/반려와 같은 ECM 연결·트랜잭션에서만 호출한다."""
    row = conn.execute("SELECT * FROM enterprise_process_installations WHERE change_id=?", (change["change_id"],)).fetchone()
    if not row:
        return
    if row["stage"] != "AWAITING_APPROVAL" or row["configuration_id"] != change["configuration_id"]:
        raise ProcessError("PROCESS_INSTALLATION_CONFLICT", "업무 승인과 설치 단계가 일치하지 않습니다.")
    if rejected:
        conn.execute("UPDATE enterprise_process_installations SET stage='FAILED_BLOCKED',error_code='PROCESS_CHANGE_REJECTED',updated_at=? WHERE operation_id=?", (now, row["operation_id"]))
    else:
        conn.execute("UPDATE enterprise_process_installations SET stage='APPLIED',applied_profile_id=?,applied_at=?,result_json=?,updated_at=? WHERE operation_id=?",
                     (result["profile_id"], now, canonical(result), now, row["operation_id"]))


# ── [2026-09-25 Codex §19.1] 업그레이드: 명시 적용 = 승인 대기, 활성 판본 전환 = 승인 뒤 ──────────
#
# ★ 반려·취소·승인 전: DP 고정 이력에 아무것도 쓰지 않았으므로 옛 판본이 그대로 활성이다
#   (현재 계약·인증·프로필 불변).
# ★ 승인: ECM 승인 트랜잭션이 커밋된 **뒤** 별도 DP 트랜잭션으로 활성화한다. 두 DB 사이 원자
#   커밋을 가정하지 않는다.
# ⚠️ 승인 직후 활성화 실패: 감사 사건(`PROCESS_UPGRADE_ACTIVATION_FAILED`)에 사유를 남기고 503. 그동안 승인판은 새 판본,
#   DP 는 옛 판본이라 소비는 «활성화 대기»(409)로 막힌다. **같은 승인을 다시 요청**하면
#   (승인의 멱등 경로) 같은 operation 으로 다시 활성화한다 — `upgrade_or_get` 이 멱등이다.
# ★ 활성화 상태는 따로 저장하지 않는다 — ECM 단계와 DP 이력에서 유도한다(`upgrade_view`).

def pending_upgrade(conn, change):
    """이 변경안이 **업그레이드 설치 작업**의 초안이면 그 판본 쌍, 아니면 `None`. ECM 연결에서 읽는다."""
    try:
        patch = json.loads(change["patch_json"])
    except (TypeError, ValueError):
        return None
    if not isinstance(patch, dict) or patch.get("op") != "INSTALL_PACK":
        return None
    row = conn.execute("SELECT * FROM enterprise_process_installations WHERE change_id=?", (change["change_id"],)).fetchone()
    if not row or patch != {"op": "INSTALL_PACK", "operation_id": row["operation_id"]}:
        return None
    row = dict(row)
    plan = ProcessInstallationService._read_plan(row, ProcessBoundary(**{k: row[k] for k in ProcessBoundary.model_fields}))
    if not plan.get("upgrade_from_artifact_digest"):
        return None
    return dict(operation_id=row["operation_id"], instance_id=plan["instance_id"],
                from_artifact_digest=plan["upgrade_from_artifact_digest"], to_artifact_digest=plan["artifact_digest"])


def instance_versions(store, instance, *, repo=None):
    """[2026-09-25 Codex §19.3] 적용본 목록의 판본 표시. B2 결속이 없으면 `None`(1.0 행은 그대로).

    `version` = **승인된 활성 판본**(DP 마지막 고정 — 승인 뒤에만 쌓인다), `installed_version` = 설치
    때 판본. 승인 대기·활성화 대기 판본은 `pending_upgrade` 로 **따로** 준다 — 현재 판본으로
    오인시키지 않는다. 대기 판본은 지금 활성 판본에서 올라가는 것만 센다(다른 기준의 낡은 초안은
    검토 화면이 HEAD 충돌로 막는다)."""
    from core.data_preparation.process_kit_instances import pins
    with store.transaction() as conn:
        history = pins(conn, dict(instance))
    if not history:
        return None
    active = history[-1]
    service = ProcessInstallationService(repo, store)
    pending = None
    with service.transaction() as conn:
        rows = conn.execute("SELECT * FROM enterprise_process_installations WHERE tenant_id=? AND context_root_id=? "
                            "AND entity_mode=? AND stage IN ('AWAITING_APPROVAL','APPLIED') "
                            "ORDER BY created_at DESC, operation_id DESC",
                            (instance["tenant_id"], active["context_root_id"], instance["entity_mode"])).fetchall()
        for row in map(dict, rows):
            plan = service._read_plan(row, ProcessBoundary(**{k: row[k] for k in ProcessBoundary.model_fields}))
            if plan.get("instance_id") != instance["instance_id"] or not plan.get("upgrade_from_artifact_digest"):
                continue
            view = service.upgrade_view(row, plan, conn)
            if (view["activation"] == "ACTIVATION_PENDING"
                    or (view["activation"] == "AWAITING_APPROVAL"
                        and plan["upgrade_from_artifact_digest"] == active["artifact_digest"])):
                pending = {"operation_id": row["operation_id"], "state": view["activation"],
                           "version": service._bundle(plan["artifact_digest"])["version"],
                           "artifact_digest": plan["artifact_digest"]}
                if "activation_error" in view:
                    pending["activation_error"] = view["activation_error"]
                break
    return {"version": active["identity"]["version"], "active_artifact_digest": active["artifact_digest"],
            "installed_version": instance["version"], "pending_upgrade": pending}


def activate_approved_upgrade(service, change_id, *, actor):
    """승인이 커밋된 업그레이드의 활성 판본 전환(DP 고정 이력 한 줄). 업그레이드가 아니면 아무것도 안 한다."""
    from core.data_preparation.process_kit_instances import upgrade_or_get
    with service.transaction() as conn:
        change = conn.execute("SELECT * FROM enterprise_process_changes WHERE change_id=?", (change_id,)).fetchone()
        upgrade = pending_upgrade(conn, dict(change)) if change and change["status"] == "APPLIED" else None
        if not upgrade:
            return None
        row = dict(conn.execute("SELECT * FROM enterprise_process_installations WHERE operation_id=?",
                                (upgrade["operation_id"],)).fetchone())
    if row["stage"] != "APPLIED":
        raise ProcessError("PROCESS_INSTALLATION_CONFLICT", "업무 승인과 설치 단계가 일치하지 않습니다.")
    installer = ProcessInstallationService(service.repo, service.store)
    try:
        upgrade_or_get(installer.store, operation_id=upgrade["operation_id"], instance_id=upgrade["instance_id"],
                       bundle=installer._bundle(upgrade["to_artifact_digest"]),
                       expected_from=upgrade["from_artifact_digest"], actor=actor)
    except (ProcessError, sqlite3.Error) as exc:
        try:
            _record_activation(service, row, upgrade, ACTIVATION_FAILED, actor,
                               getattr(exc, "reason_code", "PROCESS_STORAGE_UNAVAILABLE"))
        except ProcessError:
            pass
        raise ProcessError("PROCESS_UPGRADE_ACTIVATION_PENDING",
                           "업무판 승인은 기록됐고 새 판본 활성화는 끝나지 않았습니다. 같은 승인을 다시 요청하면 활성화를 다시 시도합니다.",
                           503) from exc
    _record_activation(service, row, upgrade, ACTIVATED, actor)
    return upgrade


#: ⚠️ APPLIED 설치 작업 행은 불변이다(`process_installation_immutable_update`). 활성화의 실패·성공은
#:   그 행을 고치지 않고 **추가만 되는** ECM 감사 outbox 사건으로 남긴다.
ACTIVATED, ACTIVATION_FAILED = "PROCESS_UPGRADE_ACTIVATED", "PROCESS_UPGRADE_ACTIVATION_FAILED"


def _record_activation(service, row, upgrade, event_type, actor, reason_code=""):
    event = {"operation_id": upgrade["operation_id"], "change_id": row["change_id"],
             "instance_id": upgrade["instance_id"], "from_artifact_digest": upgrade["from_artifact_digest"],
             "to_artifact_digest": upgrade["to_artifact_digest"], "actor": actor, "reason_code": reason_code}
    with service.transaction(write=True) as conn:
        if event_type == ACTIVATED and conn.execute(
                "SELECT 1 FROM enterprise_process_outbox WHERE change_id=? AND event_type=?",
                (row["change_id"], ACTIVATED)).fetchone():
            return
        conn.execute("INSERT INTO enterprise_process_outbox(event_id,configuration_id,change_id,event_type,payload_json,payload_digest,created_at) VALUES(?,?,?,?,?,?,?)",
                     (uid("process_event"), row["configuration_id"], row["change_id"], event_type,
                      canonical(event), fingerprint(event), service._now()))
