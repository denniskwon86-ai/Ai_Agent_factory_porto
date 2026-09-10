"""기존 부서를 권위로 삼는 키트 문맥 전환 계획. 적용·승인·권한 부여 기능은 없다."""
from __future__ import annotations

from collections import Counter
from contextlib import closing
from pathlib import Path
import sqlite3

from core.data_preparation.kit_logistics_revision import KEYS, fingerprint

DEPARTMENTS = ("hq", "procurement", "logistics", "production_copper", "production_battery")
FACTORY_DEPARTMENTS = {"plant-afs-smelting-01": "production_copper",
                       "plant-afs-battery-02": "production_battery"}


def _read(path: Path, queries: dict[str, str]) -> dict:
    # 서비스 초기화/DDL을 부르지 않는다. 없는 DB는 만들지 않고 실패한다.
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        return {key: [dict(r) for r in conn.execute(sql)] for key, sql in queries.items()}


def read_organization(master_path: Path, ecm_path: Path) -> dict:
    """공개 조직 메타만 읽는다. 사용자·암호·토큰은 조회하지 않는다."""
    return {**_read(master_path, {"departments":
        "SELECT dept_id,name_ko,parent_id,scope_node_id,version,status,valid_to FROM departments"}),
        **_read(ecm_path, {
            "nodes": "SELECT node_id,entity_id,tenant_id,node_type,name_ko,default_parent_id,status FROM organization_nodes",
            "entities": "SELECT entity_id,tenant_id,entity_mode,status FROM enterprise_entities",
            "edges": "SELECT tenant_id,from_node_id,to_node_id,relation_type,status,effective_from,effective_to FROM organization_edges"})}


def plan_alignment(organization: dict, logistics: dict, instance: dict, *, as_of: str) -> dict:
    """확인된 설치본의 두 공장만 계획한다. 이름 유사성으로 노드·부서를 합치지 않는다.

    공장과 사업부는 다른 낟알이다. target_scope_node_id가 비어 있는 명세를
    승인 요청으로 쓰지 않으며, 현행 운영 데이터/과거 봉인 근거는 수정하지 않는다.
    """
    from datetime import datetime
    when = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    if when.tzinfo is None:
        raise ValueError("조회 시각에 시간대가 필요합니다")
    if logistics.get("proposal_fingerprint") != fingerprint({k: v for k, v in logistics.items() if k != "proposal_fingerprint"}):
        raise ValueError("부모 후보 지문이 다릅니다")
    if (logistics.get("status") != "REVIEW_ONLY" or logistics.get("installed") is not False
            or logistics.get("candidate_check") != "PASS_CHECKED_SCOPE"):
        raise ValueError("검증된 비설치 후보가 필요합니다")
    if logistics.get("candidate_rows_fingerprint") != fingerprint(logistics.get("candidate_rows")):
        raise ValueError("후보 행 지문이 다릅니다")

    def unique(rows, key):
        result = {}
        for row in rows:
            value = row.get(key)
            if not value or value in result:
                raise ValueError(f"누락 또는 중복 식별자: {key}")
            result[value] = row
        return result

    departments = unique([d for d in organization["departments"]
                          if d.get("valid_to") is None and d.get("status") == "active"], "dept_id")
    nodes = unique(organization["nodes"], "node_id")
    entities = unique(organization["entities"], "entity_id")

    def node(node_id):
        row = nodes.get(node_id)
        if not row or row.get("status") != "ACTIVE":
            raise ValueError("연결할 활성 조직 노드가 없습니다")
        entity = entities.get(row["entity_id"])
        if (not entity or entity.get("status") != "ACTIVE" or entity.get("entity_mode") != "REAL"
                or not row.get("tenant_id") or row["tenant_id"] != entity.get("tenant_id")):
            raise ValueError("조직의 회사·실행 문맥이 일치하지 않습니다")
        return row

    selected = {}
    for dept_id in DEPARTMENTS:
        dept = departments.get(dept_id)
        if not dept:
            raise ValueError(f"기존 활성 부서가 없습니다: {dept_id}")
        selected[dept_id] = {**dept, "node": node(dept.get("scope_node_id"))}
    company = selected["hq"]["node"]
    if company["node_type"] != "legal_entity":
        raise ValueError("기존 본사의 연결 범위가 법인이 아닙니다")
    for key in ("procurement", "logistics"):
        if selected[key]["node"]["node_id"] != company["node_id"]:
            raise ValueError("기존 구매·물류의 회사 범위가 다릅니다")

    def effective(edge):
        for field, is_start in (("effective_from", True), ("effective_to", False)):
            value = edge.get(field)
            if not value:
                continue
            point = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if point.tzinfo is None:
                raise ValueError("조직 관계 시각에 시간대가 없습니다")
            if (is_start and when < point) or (not is_start and when >= point):
                return False
        return True

    factories = []
    for source_id, dept_id in FACTORY_DEPARTMENTS.items():
        source, target = node(source_id), selected[dept_id]["node"]
        if source["tenant_id"] != instance.get("tenant_id") or source["node_type"] != "site_plant":
            raise ValueError("원천 공장과 현재 설치 회사가 다릅니다")
        if target["tenant_id"] != company["tenant_id"] or target["node_type"] != "business_division":
            raise ValueError("생산 부서의 회사·조직 유형이 다릅니다")
        parents = [e for e in organization["edges"] if e["to_node_id"] == target["node_id"]
                   and e["relation_type"] == "OPERATING_PARENT" and e["status"] == "ACTIVE"
                   and effective(e)]
        if (len(parents) != 1 or parents[0]["from_node_id"] != company["node_id"]
                or parents[0]["tenant_id"] != company["tenant_id"]
                or target["default_parent_id"] != company["node_id"]):
            raise ValueError("생산 사업부의 유일한 운영 상위 법인을 확인할 수 없습니다")
        factories.append({"source_scope_node_id": source_id, "source_name": source["name_ko"],
                          "production_department_id": dept_id,
                          "target_parent_node_id": target["node_id"], "target_node_type": "site_plant",
                          "target_scope_node_id": None,
                          "action": "REVIEW_EXISTING_SITE_OR_REGISTER_UNDER_DIVISION"})

    owners = []
    if set(logistics["candidate_rows"]) != set(KEYS):
        raise ValueError("물류 5종 모수가 다릅니다")
    for key, identity in KEYS.items():
        counts, seen = Counter(), set()
        for row in logistics["candidate_rows"][key]:
            scope, oid = row.get("scope_node_id"), row.get(identity)
            if (scope not in FACTORY_DEPARTMENTS or row.get("tenant_id") != instance["tenant_id"]
                    or row.get("data_class") != "SYNTHETIC" or row.get("data_origin") != "SYNTHETIC"):
                raise ValueError("알 수 없는 회사·공장 또는 실제 자료는 자동 연결하지 않습니다")
            if not oid or oid in seen:
                raise ValueError("업무키가 없거나 중복됐습니다")
            seen.add(oid)
            counts[scope] += 1
        if set(counts) != set(FACTORY_DEPARTMENTS):
            raise ValueError("두 공장의 전체 모수가 필요합니다")
        for source in sorted(counts):
            owners.append({"dataset_contract_key": key, "source_scope_node_id": source,
                           "owner_dept_id": "procurement" if key == "PRC-02" else "logistics",
                           "affected_rows": counts[source], "target_scope_node_id": None,
                           "effective_from": None, "approval_event_id": None})

    report = {"schema": "laxs.existing_department_alignment.v1", "status": "PLANNED_NOT_APPLIED",
              "executable": False, "installed": False, "as_of": as_of,
              "parent_logistics_fingerprint": logistics["proposal_fingerprint"],
              "organization_fingerprint": fingerprint(organization),
              "instance_fingerprint": fingerprint(instance),
              "source_tenant_id": instance["tenant_id"],
              "target_tenant_id": company["tenant_id"], "target_company_node_id": company["node_id"],
              "existing_departments": [{k: v for k, v in d.items() if k != "node"} for d in selected.values()],
              "factory_targets": factories, "ownership_targets": owners,
              "affected_rows": sum(r["affected_rows"] for r in owners),
              "new_department_count": 0, "role_changes": [],
              "preserve": ["existing department IDs, memberships and scopes", "old nodes and sealed snapshots",
                           "approval ledger, calculation results and decision evidence"],
              "remaining_before_switch": ["resolve two site targets without collapsing site into division",
                  "align remaining dataset references and certify new versions with approved ownership",
                  "rebind applications and obtain fresh calculation approvals for changed inputs",
                  "verify ordinary-user and unauthorized-user access in isolated rehearsal",
                  "switch installation context only after backup and all consumers are ready"],
              "not_verified": ["historical organization validity", "PDP authorization", "installation or browser workflow"]}
    report["plan_fingerprint"] = fingerprint(report)
    return report
