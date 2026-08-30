import { closedLoopFetch as req } from './closedLoopFetch';

export type OntologyObject = {
  namespace: string;
  object_type: string;
  object_id: string;
  display_name?: string;
  display_fingerprint?: string;
};

export type ModelContractStatus = {
  contract_id?: string;
  contract_version?: string;
  status?: string;
  integrity_status?: string;
  effective_from?: string;
  approved_by?: string;
  contract_fingerprint?: string;
};

export type OntologyRelationType = {
  id: string;
  name_ko: string;
  inverse: string;
  quantitative: boolean;
};

export type OntologyConstraint = {
  subject_namespace: string;
  subject_type: string;
  relation: string;
  object_namespace: string;
  object_type: string;
  evidence: string[];
  calculation_ref: string;
};

export type OntologyModelContract = ModelContractStatus & {
  approval_status?: string;
  ledger_correlation_id?: string;
  installed_by?: string;
  installed_at?: string;
  relation_types: OntologyRelationType[];
  constraints: OntologyConstraint[];
};

export type OntologyModelStatus = {
  status: 'NOT_INSTALLED' | 'READY' | 'NOT_READY' | string;
  contracts: ModelContractStatus[];
  count: number;
};

export type OntologyNamespaceStatus = {
  namespace: string;
  label: string;
  contract_object_type_count: number;
  resolver_object_type_count: number;
  display_object_type_count: number;
  materialized_object_type_count: number;
  resolver_status: 'READY' | 'PARTIAL' | 'BLOCKED' | 'CONTRACT_REQUIRED' | string;
  display_status: 'READY' | 'PARTIAL' | 'BLOCKED' | 'CONTRACT_REQUIRED' | string;
  message: string;
  next_action: string;
};

export type OntologyRuntimeStatus = {
  status: 'READY' | 'PARTIAL' | 'BLOCKED' | string;
  namespace_count: number;
  resolver_available_namespace_count: number;
  fully_ready_namespace_count: number;
  contract_object_type_count: number;
  resolver_object_type_count: number;
  display_object_type_count: number;
  materialized_object_type_count: number;
  namespaces: OntologyNamespaceStatus[];
};

export type OntologyObjectList = {
  as_of: string;
  truncated: boolean;
  objects: OntologyObject[];
  object_types: string[];
};

export type ImpactPath = {
  nodes: OntologyObject[];
  edges: Array<{ relation_id?: string; relation_type_id?: string; calculation_ref?: string }>;
  path_fingerprint: string;
  bindings?: Record<string, string>;
};

export type ImpactResult = {
  query_id: string;
  status: string;
  as_of: string;
  paths: ImpactPath[];
  warnings?: string[];
};

export type OntologyRelation = {
  relation_id: string;
  subject: OntologyObject;
  relation_type_id: string;
  object: OntologyObject;
  version: number;
  approval_status: 'DRAFT' | 'IN_REVIEW' | 'APPROVED' | 'REJECTED' | 'SUPERSEDED' | 'RETIRED' | string;
  effective_from: string;
  effective_to?: string;
  tenant_id: string;
  enterprise_scope_id: string;
  entity_mode: string;
  owner_organization_id: string;
  origin: string;
  classification: string;
  scope_type: string;
  evidence_refs: string[];
  source_lineage: string[];
  calculation_ref?: string;
  submitted_by?: string;
  approved_by?: string;
  ledger_correlation_id?: string;
  updated_at?: string;
};

export type OntologyRelationList = {
  relations: OntologyRelation[];
  truncated: boolean;
  approval_status: string;
};

export type OntologyRelationDecision = {
  relation: OntologyRelation;
  decision_event: {
    event_id: string;
    event_type: string;
    subject_type: string;
    subject_id: string;
    actor_id: string;
    rationale: string;
    created_at: string;
  };
  idempotent: boolean;
};

export type OntologyProposalContext = {
  tenant_id: string;
  enterprise_scope_id: string;
  entity_mode: string;
  owner_organization_id: string;
  ready: boolean;
  reason: string;
};

export type OntologyRelationProposal = {
  subject: OntologyObject;
  relation_type_id: string;
  object: OntologyObject;
  tenant_id: string;
  enterprise_scope_id: string;
  entity_mode: string;
  owner_organization_id: string;
  effective_from: string;
  effective_to?: string;
  origin: 'user' | 'derived' | 'suggested';
  evidence_refs: string[];
  source_lineage: string[];
  calculation_ref?: string;
  classification: string;
  scope_type: string;
  scope_assignments: string[];
};

export const ontologyApi = {
  modelStatus: () => req<OntologyModelStatus>('GET', '/api/v1/ontology/model/status'),
  runtimeStatus: () => req<OntologyRuntimeStatus>('GET', '/api/v1/ontology/runtime/status'),
  modelContract: (contractId: string, version = '') => {
    const q = new URLSearchParams();
    if (version) q.set('contract_version', version);
    return req<OntologyModelContract>('GET',
      `/api/v1/ontology/model/${encodeURIComponent(contractId)}${q.size ? `?${q}` : ''}`);
  },
  relations: (status = '') => {
    const q = new URLSearchParams({ limit: '300' });
    if (status) q.set('approval_status', status);
    return req<OntologyRelationList>('GET', `/api/v1/ontology/relations?${q}`);
  },
  proposalContext: () => req<OntologyProposalContext>('GET', '/api/v1/ontology/proposal/context'),
  propose: (body: OntologyRelationProposal) => req<OntologyRelation>(
    'POST', '/api/v1/ontology/relations/propose', body),
  submit: (relationId: string) => req<OntologyRelation>(
    'POST', `/api/v1/ontology/relations/${encodeURIComponent(relationId)}/submit`),
  decideApprove: (relationId: string, rationale: string) => req<OntologyRelationDecision>(
    'POST', `/api/v1/ontology/relations/${encodeURIComponent(relationId)}/decisions/approve`,
    { rationale }),
  reject: (relationId: string, reason: string) => req<OntologyRelation>(
    'POST', `/api/v1/ontology/relations/${encodeURIComponent(relationId)}/reject`, { reason }),
  decideRetire: (relationId: string, rationale: string) => req<OntologyRelationDecision>(
    'POST', `/api/v1/ontology/relations/${encodeURIComponent(relationId)}/decisions/retire`,
    { rationale }),
  evidence: (relationId: string, asOf: string) => req<Record<string, unknown>>(
    'GET', `/api/v1/ontology/relations/${encodeURIComponent(relationId)}/evidence?as_of=${encodeURIComponent(asOf)}`),
  objects: (asOf: string, namespace = '', objectType = '') => {
    const q = new URLSearchParams({ as_of: asOf, limit: '300' });
    if (namespace) q.set('namespace', namespace);
    if (objectType) q.set('object_type', objectType);
    return req<OntologyObjectList>('GET', `/api/v1/ontology/objects?${q.toString()}`);
  },
  impact: (root: OntologyObject, asOf: string) => req<ImpactResult>(
    'POST', '/api/v1/ontology/query/impact', {
      roots: [root], target_types: [], relation_types: [], as_of: asOf,
      max_depth: 6, max_paths: 20,
    }),
};
