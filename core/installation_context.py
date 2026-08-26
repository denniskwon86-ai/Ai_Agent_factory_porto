"""설치본 회사·조직 문맥을 제품 저장소에 멱등 결속한다.

`data/instance.json`은 이 설치본이 어느 tenant를 쓰는지 정한다. 회사 이름만 저장하고
조직 노드를 만들지 않으면 인증 세션은 새 tenant를 말하지만 ECM은 옛 tenant의 노드만
돌려준다. 화면에서 이름을 하드코딩해도 권한·조회·SSE 문맥은 계속 갈라진다.

이 모듈은 기존 조직을 이동하지 않는다. 설치 설정에 명시한 법인 홈과 실제 데이터 범위만
같은 tenant에 세운다. 같은 ID가 다른 tenant에 이미 있으면 덮어쓰지 않고 실패한다.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Mapping, Optional

from core.enterprise_context.models import (
    REL_OPERATING_PARENT,
    STATUS_ACTIVE,
    EnterpriseEntity,
    OrganizationEdge,
    OrganizationNode,
)


class InstallationContextError(RuntimeError):
    """설치 설정이 없거나 기존 정본과 충돌한다."""


def _required(value: Any, label: str) -> str:
    out = str(value or "").strip()
    if not out:
        raise InstallationContextError(f"{label} 값이 필요합니다.")
    return out


def load_settings(path: str) -> Dict[str, Any]:
    """설치 설정을 읽는다. 판독 실패를 기본값으로 접지 않는다."""
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        raise InstallationContextError(f"설치 설정을 읽지 못했습니다: {exc}") from exc
    if not isinstance(data, dict):
        raise InstallationContextError("설치 설정의 최상위는 객체여야 합니다.")
    return data


def _assert_entity_slot(repo: Any, entity_id: str, tenant_id: str) -> None:
    current = repo.get_entity(entity_id)
    if current and current.tenant_id != tenant_id:
        raise InstallationContextError(
            f"법인 ID {entity_id}는 이미 다른 tenant({current.tenant_id})에 결속돼 있습니다.")


def _assert_node_slot(repo: Any, node_id: str, tenant_id: str) -> None:
    current = repo.get_node(node_id)
    if current and current.tenant_id != tenant_id:
        raise InstallationContextError(
            f"조직 노드 {node_id}는 이미 다른 tenant({current.tenant_id})에 결속돼 있습니다.")


def apply_settings(settings: Mapping[str, Any], *, repo: Any = None,
                   config_module: Any = None) -> Dict[str, Any]:
    """설치 tenant·회사명·법인 홈·업무 범위를 같은 축에 세운다.

    `organization`이 없으면 회사명까지만 적용한다. 조직을 명시했다면 법인 홈과 모든
    `scope_nodes`를 한 번에 검증한 뒤 저장한다. 중간 검증 실패로 반쪽 결속을 만들지 않는다.
    """
    if not settings:
        return {"applied": False, "tenant_id": "", "scope_node_ids": []}

    tenant_id = _required(settings.get("tenant_id"), "tenant_id")
    company_name = _required(settings.get("company_name"), "company_name")
    legal_name = str(settings.get("company_legal_name") or "").strip()

    if repo is None:
        from core.enterprise_context.repository import ecm_repository
        repo = ecm_repository
    if config_module is None:
        import config as config_module

    organization = settings.get("organization") or {}
    if not isinstance(organization, dict):
        raise InstallationContextError("organization은 객체여야 합니다.")

    entity_id = legal_node_id = ""
    scope_specs = organization.get("scope_nodes") or []
    if not isinstance(scope_specs, list):
        raise InstallationContextError("organization.scope_nodes는 배열이어야 합니다.")

    if organization:
        entity_id = _required(organization.get("entity_id"), "organization.entity_id")
        legal_node_id = _required(
            organization.get("legal_node_id"), "organization.legal_node_id")
        _assert_entity_slot(repo, entity_id, tenant_id)
        _assert_node_slot(repo, legal_node_id, tenant_id)
        seen = {legal_node_id}
        for idx, spec in enumerate(scope_specs):
            if not isinstance(spec, dict):
                raise InstallationContextError(f"scope_nodes[{idx}]는 객체여야 합니다.")
            node_id = _required(spec.get("node_id"), f"scope_nodes[{idx}].node_id")
            if node_id in seen:
                raise InstallationContextError(f"조직 노드 ID가 중복됐습니다: {node_id}")
            seen.add(node_id)
            _required(spec.get("name_ko"), f"scope_nodes[{idx}].name_ko")
            _required(spec.get("code"), f"scope_nodes[{idx}].code")
            _assert_node_slot(repo, node_id, tenant_id)

    # 검증이 끝난 뒤에만 실제 정본을 쓴다.
    config_module.ECM_DEFAULT_TENANT_ID = tenant_id
    repo.upsert_tenant(tenant_id, company_name, legal_name)

    made: list[str] = []
    if organization:
        current_entity = repo.get_entity(entity_id)
        entity = EnterpriseEntity(
            entity_id=entity_id,
            tenant_id=tenant_id,
            entity_type="legal_entity",
            entity_mode="REAL",
            legal_name=legal_name,
            name_ko=company_name,
            industry_code=str(organization.get("industry_code") or "").strip(),
            status=STATUS_ACTIVE,
            approved_by=(current_entity.approved_by if current_entity else "installation-config"),
            approved_at=(current_entity.approved_at if current_entity else "installation-config"),
            source_ref="data/instance.json",
        )
        repo.upsert_entity(entity)
        repo.upsert_node(OrganizationNode(
            node_id=legal_node_id,
            entity_id=entity_id,
            tenant_id=tenant_id,
            node_type="legal_entity",
            code=_required(organization.get("legal_node_code"),
                           "organization.legal_node_code"),
            name_ko=company_name,
            dept_id=str(organization.get("legal_dept_id") or "").strip(),
            status=STATUS_ACTIVE,
        ))
        made.append(legal_node_id)

        for spec in scope_specs:
            node_id = str(spec["node_id"]).strip()
            repo.upsert_node(OrganizationNode(
                node_id=node_id,
                entity_id=entity_id,
                tenant_id=tenant_id,
                node_type=str(spec.get("node_type") or "site_plant").strip(),
                code=str(spec["code"]).strip(),
                name_ko=str(spec["name_ko"]).strip(),
                default_parent_id=legal_node_id,
                path_hint=f"{company_name} / {str(spec['name_ko']).strip()}",
                dept_id=str(spec.get("dept_id") or "").strip(),
                status=STATUS_ACTIVE,
            ))
            repo.add_edge(OrganizationEdge(
                edge_id=f"edge_install_{legal_node_id}_{node_id}",
                tenant_id=tenant_id,
                from_node_id=legal_node_id,
                to_node_id=node_id,
                relation_type=REL_OPERATING_PARENT,
                status=STATUS_ACTIVE,
            ))
            made.append(node_id)

    return {"applied": True, "tenant_id": tenant_id,
            "company_name": company_name, "scope_node_ids": made}


def apply_file(path: str, *, repo: Optional[Any] = None,
               config_module: Optional[Any] = None) -> Dict[str, Any]:
    return apply_settings(load_settings(path), repo=repo, config_module=config_module)
