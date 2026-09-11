"""합성 키트 선행 5종의 사본 문맥 정렬. 조직 승인·인증·가격 보정을 하지 않는다."""
from collections import Counter, defaultdict
from datetime import datetime

from core.data_preparation.kit_logistics_revision import fingerprint
from core.data_preparation.kit_sample_audit import inspect_rows

FOUNDATION = ("FND-01", "FND-03", "MDM-04", "MDM-08", "EXT-02")
COMMON = {"data_class": "SYNTHETIC", "data_origin": "SYNTHETIC",
          "quality_status": "PENDING_VALIDATION", "certification_status": "UNVERIFIED_CANDIDATE"}


def unique(rows, fields):
    result = {}
    for row in rows:
        key = tuple(row.get(field, "") for field in fields)
        if any(not value for value in key) or key in result:
            raise ValueError("누락/중복 기준자료 키: " + ",".join(fields))
        result[key] = row
    return result


def prepare_foundation(source, contracts, organization, *, source_tenant, tenant, company,
                       factories, as_of):
    """현재 조직 구조만 투영한다. 알 수 없는 과거 유효기간은 빈 값으로 보존한다."""
    when = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    if when.tzinfo is None or len(factories) != 2 or len(set(factories.values())) != 2:
        raise ValueError("시점/검토된 두 공장 매핑이 필요합니다")
    for key in FOUNDATION:
        if not source.get(key):
            raise ValueError("빈 선행자료: " + key)
        unique(source[key], contracts[key]["business_keys"])
        for row in source[key]:
            if (row.get("tenant_id"), row.get("data_class"), row.get("data_origin"),
                    row.get("certification_status")) != (
                    source_tenant, "SYNTHETIC", "SYNTHETIC", "CERTIFIED_FOR_DEMO"):
                raise ValueError("검토된 원천 합성 자료만 정렬합니다")
    source_org = unique(source["FND-01"], ["node_id"])
    roots = [r["node_id"] for r in source["FND-01"] if r.get("node_type") == "ENTERPRISE_GROUP"]
    if len(roots) != 1:
        raise ValueError("공통 자료의 원천 그룹이 유일하지 않습니다")
    nodes = unique(organization["nodes"], ["node_id"])
    entities = unique(organization["entities"], ["entity_id"])

    def node(key):
        row = nodes.get((key,))
        entity = entities.get((row.get("entity_id"),)) if row else None
        if not row or not entity or row["tenant_id"] != tenant or entity["tenant_id"] != tenant:
            raise ValueError("조직 회사 경계 불일치")
        if row["status"] != "ACTIVE" or entity["status"] != "ACTIVE" or entity["entity_mode"] != "REAL":
            raise ValueError("목표 조직은 검토된 활성 REAL 문맥이어야 합니다")
        return row

    if node(company)["node_type"] != "legal_entity":
        raise ValueError("목표 회사 종류 불일치")
    selected = {}
    for original, target in factories.items():
        src = source_org.get((original,))
        if not src or src["node_type"] != "PLANT" or src["entity_mode"] != "VIRTUAL":
            raise ValueError("미검토 원천 공장")
        if node(target)["node_type"] != "site_plant":
            raise ValueError("목표 공장 종류 불일치")
        cursor, visited = target, set()
        while cursor:
            if cursor in visited:
                raise ValueError("조직 부모 순환")
            visited.add(cursor)
            row = node(cursor)
            selected[cursor] = row
            parent = row["default_parent_id"]
            if parent:
                relation = "LEGAL_OWNERSHIP" if row["node_type"] == "legal_entity" else "OPERATING_PARENT"
                edges = [e for e in organization["edges"] if e["tenant_id"] == tenant
                    and e["from_node_id"] == parent and e["to_node_id"] == cursor
                    and e["relation_type"] == relation and e["status"] == "ACTIVE"]
                if len(edges) != 1:
                    raise ValueError("조직 부모 연결이 없거나 모호합니다")
                for field, lower in (("effective_from", True), ("effective_to", False)):
                    if edges[0].get(field):
                        boundary = datetime.fromisoformat(edges[0][field].replace("Z", "+00:00"))
                        if boundary.tzinfo is None or (when < boundary if lower else when >= boundary):
                            raise ValueError("사본 관측시점의 조직 연결이 유효하지 않습니다")
            cursor = parent
        if company not in visited:
            raise ValueError("공장이 목표 회사의 자손이 아닙니다")

    candidate, changes, held = {key: [] for key in FOUNDATION}, [], []
    fields = [f["name"] for f in contracts["FND-01"]["schema"]["fields"]]
    for key, row in sorted(selected.items()):
        identity = fingerprint({"node": row, "as_of": as_of})[:20]
        candidate["FND-01"].append({**dict.fromkeys(fields, ""), **COMMON,
            "record_id": "foundation-" + identity, "lineage_id": "copy-org-" + identity,
            "tenant_id": tenant, "scope_node_id": company, "business_data_kind": "REFERENCE",
            "as_of_date": when.date().isoformat(), "node_id": key,
            "node_type": "PLANT" if row["node_type"] == "site_plant" else row["node_type"].upper(),
            "name": row["name_ko"], "parent_id": row["default_parent_id"], "entity_mode": "REAL"})
    for key in FOUNDATION[1:]:
        for row in source[key]:
            scope = row["scope_node_id"]
            if key == "MDM-04":
                if row["site_id"] != scope:
                    raise ValueError("창고 site와 소유 범위 불일치")
                if scope not in factories:
                    src = source_org.get((scope,))
                    if not src or src["entity_mode"] != "VIRTUAL_EXPANSION" or row["active"].lower() != "false":
                        raise ValueError("검토되지 않은 창고 범위를 자동 제외하지 않습니다")
                    held.append({"dataset": key, "reason": "UNMAPPED_VIRTUAL_EXPANSION", "source_row": dict(row)})
                    continue
                target = factories[scope]
            else:
                if scope != roots[0]:
                    raise ValueError("공통 기준자료의 원천 범위 변경")
                target = company
            updated = {**row, **COMMON, "tenant_id": tenant, "scope_node_id": target}
            if key == "MDM-04":
                updated["site_id"] = target
            candidate[key].append(updated)
            changes.append({"dataset": key, "record_id": row["record_id"], "lineage_id": row["lineage_id"],
                "from_tenant": source_tenant, "from_scope": scope, "to_tenant": tenant, "to_scope": target,
                "changed_fields": [field for field in row if row[field] != updated[field]],
                "rule": "REVIEWED_FACTORY" if key == "MDM-04" else "COMPANY_REFERENCE_COPY_NOT_ENTITY_ALIAS"})
    return {"candidate_rows": candidate, "candidate_rows_fingerprint": fingerprint(candidate),
        "changes": changes, "held_source_rows": held, "organization_projection": {
            "source_template_rows_preserved": len(source["FND-01"]), "target_node_count": len(selected),
            "copied_organization_fingerprint": fingerprint(organization), "observed_at": as_of,
            "historical_validity_asserted": False, "legal_entity_alias_created": False},
        "installed": False, "executable": False, "certified": False}


def inspect_foundation_links(data, contracts):
    """현재 구조·업무 참조와 과거 유효성 보류를 분리한다. 통과가 사용 승인은 아니다."""
    issues = inspect_rows(data, {key: contracts[key] for key in data})
    links = Counter()
    locations = unique(data["MDM-04"], ["tenant_id", "location_id"])
    terms = unique(data["MDM-08"], ["tenant_id", "reference_type", "code"])
    calendar = unique(data["FND-03"], ["tenant_id", "reference_type", "reference_key", "effective_date"])
    benchmarks = defaultdict(list)
    for row in data["EXT-02"]:
        observed, published, vintage = (datetime.fromisoformat(row[k]).date()
            for k in ("observed_at", "published_at", "vintage_date"))
        if observed > published or published > vintage:
            issues.append({"code": "PRICE_OBSERVATION_ORDER", "dataset": "EXT-02", "record_id": row["record_id"]})
        benchmarks[row["tenant_id"], row["commodity_code"]].append(row)
    def check(ok, code, dataset, record):
        if ok:
            links[code] += 1
        else:
            issues.append({"code": code, "dataset": dataset, "record_id": record["record_id"]})
    for row in data.get("LOG-05", []):
        location = locations.get((row["tenant_id"], row["destination_location_id"]))
        check(location is not None and location["scope_node_id"] == row["scope_node_id"]
              and location["site_id"] == row["scope_node_id"] and location["active"].lower() == "true",
              "TRANSPORT_LOCATION", "LOG-05", row)
    for key in ("PRC-01", "PRC-02"):
        for row in data.get(key, []):
            for field, kind in (("incoterm", "INCOTERM"), ("payment_terms", "PAYMENT_TERM")):
                if field in row:
                    check((row["tenant_id"], kind, row[field]) in terms, "REFERENCE_" + kind, key, row)
            if key == "PRC-01":
                check(bool(benchmarks[row["tenant_id"], row["benchmark_code"]]), "BENCHMARK_CODE", key, row)
            else:
                day = row["order_date"]
                check((row["tenant_id"], "FISCAL_CALENDAR", day, day) in calendar, "ORDER_CALENDAR", key, row)
    unknown_history = [r["node_id"] for r in data["FND-01"] if not r["effective_from"] or not r["effective_to"]]
    return {"structural_issues": issues, "reference_counts": dict(links),
        "historical_org_nodes_unverified": unknown_history,
        "usage_holds": ["OWNERSHIP_AND_CERTIFICATION_REQUIRED", "HISTORICAL_ORGANIZATION_VALIDITY_REQUIRED",
                        "PRICE_VINTAGE_AND_CONVERSION_POLICY_REQUIRED"],
        "executable": False, "certified": False}
