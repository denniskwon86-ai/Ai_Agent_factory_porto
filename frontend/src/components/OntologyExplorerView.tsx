import { useCallback, useEffect, useMemo, useState } from 'react';

import { Banner, Panel, ScreenHead } from '../design/HubShell';
import { EmptyOrError, Metric, failed, loading, ok, type Loaded } from '../design/DataState';
import { ConfirmInline, FormField, useConfirm } from '../design/DataFoundationShell';
import { OntologyGraphPanel } from './OntologyGraphPanel';
import {
  ontologyApi, type ImpactResult, type OntologyConstraint, type OntologyModelContract,
  type OntologyModelStatus, type OntologyObject, type OntologyObjectList,
  type OntologyProposalContext, type OntologyRelationList,
} from '../lib/ontologyApi';

const now = () => new Date().toISOString();
const refLabel = (o: OntologyObject) => `${o.namespace}:${o.object_type}:${o.object_id}`;

/** 승인된 관계를 사람이 직접 탐색하는 읽기 화면. 모델 설치·관계 승인은 기존 통제 API가 맡는다. */
export function OntologyExplorerView() {
  const [asOf, setAsOf] = useState(now());
  const [namespace, setNamespace] = useState('');
  const [model, setModel] = useState<Loaded<OntologyModelStatus>>(loading<OntologyModelStatus>());
  const [objects, setObjects] = useState<Loaded<OntologyObjectList>>(loading<OntologyObjectList>());
  const [modelContract, setModelContract] = useState<Loaded<OntologyModelContract> | null>(null);
  const [relations, setRelations] = useState<Loaded<OntologyRelationList>>(loading<OntologyRelationList>());
  const [proposalContext, setProposalContext] = useState<Loaded<OntologyProposalContext>>(
    loading<OntologyProposalContext>());
  const [relationFilter, setRelationFilter] = useState('');
  const [selectedRelation, setSelectedRelation] = useState('');
  const [showProposal, setShowProposal] = useState(false);
  const [proposal, setProposal] = useState({
    constraint: '', subject: '', object: '', effective_from: now(), effective_to: '',
    evidence: '', lineage: '',
  });
  const [actionReason, setActionReason] = useState('');
  const [actionBusy, setActionBusy] = useState(false);
  const [actionMessage, setActionMessage] = useState<{ tone: 'info' | 'error'; text: string } | null>(null);
  const [root, setRoot] = useState<OntologyObject | null>(null);
  const [impact, setImpact] = useState<Loaded<ImpactResult>>(ok<ImpactResult>({
    query_id: '', status: '', as_of: '', paths: [], warnings: [],
  }));
  const confirmAction = useConfirm<string>();

  const load = useCallback(async () => {
    setModel(loading<OntologyModelStatus>()); setObjects(loading<OntologyObjectList>());
    const [m, o] = await Promise.allSettled([
      ontologyApi.modelStatus(), ontologyApi.objects(asOf, namespace),
    ]);
    setModel(m.status === 'fulfilled' ? ok(m.value) : failed<OntologyModelStatus>(m.reason));
    setObjects(o.status === 'fulfilled' ? ok(o.value) : failed<OntologyObjectList>(o.reason));
    if (o.status === 'fulfilled') {
      setRoot((prev) => prev && o.value.objects.some((v) => refLabel(v) === refLabel(prev))
        ? prev : null);
    }
  }, [asOf, namespace]);

  useEffect(() => { load(); }, [load]);
  const loadGovernance = useCallback(async () => {
    setRelations(loading<OntologyRelationList>()); setProposalContext(loading<OntologyProposalContext>());
    const [r, c] = await Promise.allSettled([
      ontologyApi.relations(relationFilter), ontologyApi.proposalContext(),
    ]);
    setRelations(r.status === 'fulfilled' ? ok(r.value) : failed<OntologyRelationList>(r.reason));
    setProposalContext(c.status === 'fulfilled' ? ok(c.value) : failed<OntologyProposalContext>(c.reason));
    if (r.status === 'fulfilled') setSelectedRelation((v) =>
      r.value.relations.some((item) => item.relation_id === v) ? v : (r.value.relations[0]?.relation_id || ''));
  }, [relationFilter]);

  useEffect(() => { loadGovernance(); }, [loadGovernance]);
  useEffect(() => {
    // 상단 회사·조직 문맥을 바꾸면 이전 범위의 객체·관계를 화면에 남기지 않는다.
    // 전체 새로고침에 기대면 선택기 상태와 다른 화면의 캐시가 서로 다른 시점에 갱신된다.
    const refresh = () => { load(); loadGovernance(); };
    window.addEventListener('factory:enterprise-context-changed', refresh);
    return () => window.removeEventListener('factory:enterprise-context-changed', refresh);
  }, [load, loadGovernance]);
  useEffect(() => {
    const contract = model.value?.contracts?.[0];
    if (!contract?.contract_id) { setModelContract(null); return; }
    setModelContract(loading<OntologyModelContract>());
    ontologyApi.modelContract(contract.contract_id, contract.contract_version || '')
      .then((v) => setModelContract(ok(v)))
      .catch((e) => setModelContract(failed<OntologyModelContract>(e)));
  }, [model.value]);

  const run = async () => {
    if (!root) return;
    setImpact(loading<ImpactResult>());
    try { setImpact(ok(await ontologyApi.impact(root, asOf))); }
    catch (e) { setImpact(failed<ImpactResult>(e)); }
  };

  const splitLines = (value: string) => value.split(/\r?\n/).map((v) => v.trim()).filter(Boolean);

  const proposeRelation = async () => {
    if (!selectedConstraint || !proposalSubject || !proposalObject || !proposalContext.value?.ready
      || !proposal.evidence.trim()) return;
    setActionBusy(true); setActionMessage(null);
    try {
      await ontologyApi.propose({
        subject: proposalSubject, relation_type_id: selectedConstraint.relation,
        object: proposalObject, tenant_id: proposalContext.value.tenant_id,
        enterprise_scope_id: proposalContext.value.enterprise_scope_id,
        entity_mode: proposalContext.value.entity_mode,
        owner_organization_id: proposalContext.value.owner_organization_id,
        effective_from: proposal.effective_from, effective_to: proposal.effective_to,
        origin: 'user', evidence_refs: splitLines(proposal.evidence),
        source_lineage: splitLines(proposal.lineage),
        calculation_ref: selectedConstraint.calculation_ref || '', classification: 'INTERNAL',
        scope_type: 'ORG_PRIVATE',
        scope_assignments: [proposalContext.value.enterprise_scope_id],
      });
      setProposal((v) => ({ ...v, subject: '', object: '', evidence: '', lineage: '' }));
      setShowProposal(false);
      setActionMessage({ tone: 'info', text: '관계를 초안으로 제안했습니다. 검토 요청 전에는 영향 경로에 나타나지 않습니다.' });
      await loadGovernance();
    } catch (e) {
      setActionMessage({ tone: 'error', text: e instanceof Error ? e.message : '관계를 제안하지 못했습니다.' });
    } finally { setActionBusy(false); }
  };

  const runRelationAction = async (actionKey: string) => {
    const relation = selectedRelationRow;
    if (!relation) return;
    setActionBusy(true); setActionMessage(null);
    try {
      if (actionKey === 'submit') await ontologyApi.submit(relation.relation_id);
      if (actionKey === 'approve') await ontologyApi.decideApprove(
        relation.relation_id, actionReason.trim());
      if (actionKey === 'reject') await ontologyApi.reject(relation.relation_id, actionReason.trim());
      if (actionKey === 'retire') await ontologyApi.decideRetire(
        relation.relation_id, actionReason.trim());
      setActionReason('');
      setActionMessage({ tone: 'info', text: actionKey === 'submit' ? '관계를 검토 요청 상태로 전환했습니다.'
        : actionKey === 'approve' ? '관계 전용 승인 사건을 원장에 기록하고 관계를 승인했습니다.'
          : actionKey === 'reject' ? '사유와 함께 관계를 반려했습니다.' : '승인 관계를 폐지했습니다.' });
      await loadGovernance(); await load();
    } catch (e) {
      setActionMessage({ tone: 'error', text: e instanceof Error ? e.message : '관계 상태를 변경하지 못했습니다.' });
    } finally { setActionBusy(false); }
  };

  const rows = objects.value?.objects || [];
  const types = objects.value?.object_types || [];
  const namespaces = useMemo(() => Array.from(new Set(rows.map((o) => o.namespace))).sort(), [rows]);
  const paths = impact.value?.paths || [];
  const contractConstraints = modelContract?.value?.constraints || [];
  const contractTypes = modelContract?.value?.relation_types || [];
  const selectedConstraint: OntologyConstraint | null = contractConstraints.find((c) =>
    `${c.subject_namespace}:${c.subject_type}|${c.relation}|${c.object_namespace}:${c.object_type}`
      === proposal.constraint) || null;
  const proposalSubjects = selectedConstraint ? rows.filter((o) => o.namespace === selectedConstraint.subject_namespace
    && o.object_type === selectedConstraint.subject_type) : [];
  const proposalObjects = selectedConstraint ? rows.filter((o) => o.namespace === selectedConstraint.object_namespace
    && o.object_type === selectedConstraint.object_type) : [];
  const proposalSubject = proposalSubjects.find((o) => refLabel(o) === proposal.subject) || null;
  const proposalObject = proposalObjects.find((o) => refLabel(o) === proposal.object) || null;
  const relationRows = relations.value?.relations || [];
  const selectedRelationRow = relationRows.find((r) => r.relation_id === selectedRelation) || null;

  return (
    <>
      <ScreenHead kicker="ONTOLOGY" title="업무 온톨로지"
        description="승인되고 현재 유효한 업무 관계만 따라가며, 어떤 객체와 근거가 연결되는지 확인합니다."
        chip={{ label: model.value?.status || '확인 중',
          tone: model.value?.status === 'READY' ? 'success'
            : model.value?.status === 'NOT_READY' ? 'danger' : 'warn' }} />

      <Banner tone="info" title="승인된 의미만 표시합니다">
        이 화면은 문서의 단어를 임의로 연결하지 않습니다. 설치된 의미계약과 승인된 관계,
        현재 사용자에게 보이는 범위를 모두 통과한 객체만 표시합니다.
      </Banner>

      {actionMessage && <Banner tone={actionMessage.tone} title={actionMessage.tone === 'error'
        ? '관계 상태를 변경하지 못했습니다' : '온톨로지 관리 결과'}>{actionMessage.text}</Banner>}

      <div className="metric-row">
        <Metric label="설치 계약" state={model.status} value={model.value?.count} hint="의미계약 판" />
        <Metric label="보이는 객체" state={objects.status} value={rows.length}
          hint={objects.value?.truncated ? '일부만 표시' : '승인 관계의 끝점'} />
        <Metric label="객체 유형" state={objects.status} value={types.length} hint="현재 범위" />
        <Metric label="영향 경로" state={impact.status} value={impact.value?.query_id ? paths.length : null}
          hint={impact.value?.status || '시작점 선택 전'} />
      </div>

      <Panel kicker="RELATION GRAPH" title="업무 객체 상관 그래프">
        <div style={{ padding: 15, display: 'grid', gap: 10 }}>
          <Banner tone="info" title="현재 권한과 기준 시각에서 조회된 관계만 그립니다">
            노드와 간선은 아래 관계 등록부와 같은 응답을 사용합니다. 보이지 않는 관계의 존재나 수를
            추정하지 않으며, 빈 구간을 임의 연결하지 않습니다.
          </Banner>
          {relations.status !== 'ok' ? (
            <EmptyOrError state={relations.status} error={relations.error} onRetry={loadGovernance}
              emptyText="시각화할 관계가 없습니다." />
          ) : <OntologyGraphPanel relations={relationRows} selectedRelationId={selectedRelation}
            selectedRoot={root} onSelectRelation={(relationId) => {
              setSelectedRelation(relationId); setActionReason('');
            }} onSelectRoot={setRoot} />}
        </div>
      </Panel>

      <Panel kicker="MODEL" title="설치된 의미계약">
        {model.status !== 'ok' ? (
          <EmptyOrError state={model.status} error={model.error} onRetry={load}
            emptyText="설치된 의미계약이 없습니다." />
        ) : (model.value?.contracts || []).length === 0 ? (
          <div className="empty-note">설치된 의미계약이 없습니다. 설계 계약만으로는 관계를 운영에 쓰지 않습니다.</div>
        ) : (
          <div className="people-list" style={{ padding: 15 }}>
            {model.value!.contracts.map((c, i) => (
              <div className="person" key={`${c.contract_id || 'contract'}-${c.contract_version || i}`}>
                <i aria-hidden="true">계</i>
                <div>
                  <b>{c.contract_id || '계약 ID 미상'} · {c.contract_version || '판 미상'}</b>
                  <small>{c.integrity_status || c.status || '상태 미상'} · 승인자 {c.approved_by || '미상'}
                    {' · '}지문 {(c.contract_fingerprint || '').slice(0, 16) || '미상'}</small>
                </div>
              </div>
            ))}
          </div>
        )}

        {modelContract && modelContract.status !== 'ok' && (
          <EmptyOrError state={modelContract.status} error={modelContract.error}
            emptyText="설치 계약의 상세를 확인할 수 없습니다." />
        )}
        {modelContract?.status === 'ok' && (
          <div style={{ padding: '0 15px 15px', display: 'grid', gap: 12 }}>
            <Banner tone="info" title="설치된 계약 원문을 운영 기준으로 확인합니다">
              관계 유형과 허용된 주어·목적어 조합을 조회합니다. 새 계약 설치는 원문 검증과 별도 승인 절차를 거쳐야 하므로
              이 화면에서 임의 JSON을 직접 설치하지 않습니다.
            </Banner>
            <div className="afs-table-wrap">
              <table className="afs-table"><thead><tr><th>관계 유형</th><th>표시명</th><th>역관계</th><th>정량</th></tr></thead>
                <tbody>{contractTypes.map((t) => <tr key={t.id}>
                  <td><b>{t.id}</b></td><td>{t.name_ko || '—'}</td><td>{t.inverse || '—'}</td>
                  <td><span className={`state-chip ${t.quantitative ? 'warn' : 'muted'}`}>
                    {t.quantitative ? '계산 필요' : '정성'}</span></td>
                </tr>)}</tbody>
              </table>
            </div>
            <div className="afs-table-wrap">
              <table className="afs-table"><thead><tr><th>주어</th><th>관계</th><th>목적어</th><th>필수 근거·계산</th></tr></thead>
                <tbody>{contractConstraints.map((c, i) => <tr key={`${c.relation}-${i}`}>
                  <td>{c.subject_namespace}:{c.subject_type}</td><td><b>{c.relation}</b></td>
                  <td>{c.object_namespace}:{c.object_type}</td>
                  <td>{(c.evidence || []).join(' · ') || '근거 규칙 없음'}
                    {c.calculation_ref ? <><br /><small className="afs-muted">{c.calculation_ref}</small></> : null}</td>
                </tr>)}</tbody>
              </table>
            </div>
          </div>
        )}
      </Panel>

      <Panel kicker="GOVERNANCE" title="관계 제안과 승인 관리"
        action={<button className="primary-button" onClick={() => setShowProposal((v) => !v)}>
          {showProposal ? '제안 입력 닫기' : '새 관계 제안'}</button>}>
        <div style={{ padding: 15, display: 'grid', gap: 13 }}>
          {proposalContext.status !== 'ok' ? (
            <EmptyOrError state={proposalContext.status} error={proposalContext.error}
              onRetry={loadGovernance} emptyText="관계 제안 문맥을 확인할 수 없습니다." />
          ) : proposalContext.value?.ready ? (
            <Banner tone="info" title="현재 운영 문맥에 제안합니다">
              테넌트 {proposalContext.value.tenant_id} · 범위 {proposalContext.value.enterprise_scope_id}
              {' · '}소유 부서 {proposalContext.value.owner_organization_id}
            </Banner>
          ) : (
            <Banner tone="warn" title="관계를 저장할 조직 범위를 선택하십시오">
              {!proposalContext.value?.enterprise_scope_id
                ? '현재 ‘권한 범위 전체’는 조회 문맥입니다. 관계를 저장하려면 화면 상단 OPERATING CONTEXT에서 귀속할 회사·조직 범위를 하나 선택하십시오.'
                : proposalContext.value?.reason
                  || '쓰기 가능한 소유 부서를 확인하지 못했습니다. 회사·조직 권한 설정을 점검하십시오.'}
            </Banner>
          )}

          {showProposal && (
            <section className="panel" style={{ padding: 15 }}>
              <h3 style={{ margin: '0 0 5px' }}>계약에 허용된 관계 제안</h3>
              <p className="section-text" style={{ marginTop: 0 }}>
                설치 계약의 제약과 현재 보이는 업무 객체에서만 선택합니다. 제안은 초안으로 저장되며 승인 전에는 영향 경로에 나타나지 않습니다.
              </p>
              <div className="reg-filters" style={{ gridTemplateColumns: 'repeat(2, minmax(220px, 1fr))' }}>
                <FormField label="허용 관계" required hint="주어·관계·목적어 조합은 설치 계약이 정합니다.">
                  <select className="afs-select" value={proposal.constraint}
                    onChange={(e) => setProposal((v) => ({ ...v, constraint: e.target.value, subject: '', object: '' }))}>
                    <option value="">관계를 선택하세요</option>
                    {contractConstraints.map((c, i) => {
                      const key = `${c.subject_namespace}:${c.subject_type}|${c.relation}|${c.object_namespace}:${c.object_type}`;
                      return <option value={key} key={`${key}-${i}`}>
                        {c.subject_type} → {c.relation} → {c.object_type}
                      </option>;
                    })}
                  </select>
                </FormField>
                <FormField label="계산 참조" hint="정량 관계는 승인된 계산 능력이 별도로 필요합니다.">
                  <input className="afs-input" readOnly value={selectedConstraint?.calculation_ref || '정성 관계'} />
                </FormField>
                <FormField label="주어 업무 객체" required>
                  <select className="afs-select" value={proposal.subject}
                    onChange={(e) => setProposal((v) => ({ ...v, subject: e.target.value }))}>
                    <option value="">주어를 선택하세요</option>
                    {proposalSubjects.map((o) => <option key={refLabel(o)} value={refLabel(o)}>{refLabel(o)}</option>)}
                  </select>
                </FormField>
                <FormField label="목적어 업무 객체" required>
                  <select className="afs-select" value={proposal.object}
                    onChange={(e) => setProposal((v) => ({ ...v, object: e.target.value }))}>
                    <option value="">목적어를 선택하세요</option>
                    {proposalObjects.map((o) => <option key={refLabel(o)} value={refLabel(o)}>{refLabel(o)}</option>)}
                  </select>
                </FormField>
                <FormField label="유효 시작" required hint="끝점 자료가 인증된 시점보다 이를 수 없습니다.">
                  <input className="afs-input" value={proposal.effective_from}
                    onChange={(e) => setProposal((v) => ({ ...v, effective_from: e.target.value }))} />
                </FormField>
                <FormField label="유효 종료" hint="비우면 폐지 전까지 유효합니다.">
                  <input className="afs-input" value={proposal.effective_to}
                    onChange={(e) => setProposal((v) => ({ ...v, effective_to: e.target.value }))} />
                </FormField>
              </div>
              <FormField label="근거 참조" required hint="한 줄에 하나씩 입력합니다. 필수 근거 유형은 계약 상세에서 확인합니다.">
                <textarea className="afs-textarea" rows={3} value={proposal.evidence}
                  onChange={(e) => setProposal((v) => ({ ...v, evidence: e.target.value }))}
                  placeholder="예: dataset://snapshot/evidence-id" />
              </FormField>
              <FormField label="출처 계보" hint="원천·변환·검증 이력을 한 줄에 하나씩 입력합니다.">
                <textarea className="afs-textarea" rows={2} value={proposal.lineage}
                  onChange={(e) => setProposal((v) => ({ ...v, lineage: e.target.value }))} />
              </FormField>
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <button className="primary-button" onClick={proposeRelation} disabled={actionBusy
                  || !proposalContext.value?.ready || !selectedConstraint || !proposalSubject || !proposalObject
                  || !proposal.evidence.trim()}>초안으로 제안</button>
              </div>
            </section>
          )}

          <div className="chip-row" style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
            {[['', '전체'], ['DRAFT', '초안'], ['IN_REVIEW', '검토 중'], ['APPROVED', '승인'],
              ['REJECTED', '반려'], ['RETIRED', '폐지']].map(([value, label]) =>
              <button key={value || 'all'} className={relationFilter === value ? 'primary-button' : 'secondary-button'}
                onClick={() => setRelationFilter(value)}>{label}</button>)}
          </div>

          {relations.status !== 'ok' ? (
            <EmptyOrError state={relations.status} error={relations.error} onRetry={loadGovernance}
              emptyText="관리할 관계가 없습니다." />
          ) : relationRows.length === 0 ? (
            <div className="empty-note">현재 관리 범위에서 보이는 이 상태의 관계가 없습니다.
              보이지 않는 관계의 수는 공개하지 않으며, 계약에 허용된 객체 조합만 새 관계로 제안할 수 있습니다.</div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, .8fr) minmax(360px, 1.2fr)', gap: 12 }}>
              <div className="people-list" style={{ padding: 0 }}>
                {relationRows.map((r) => <button type="button" className="person" key={r.relation_id}
                  onClick={() => { setSelectedRelation(r.relation_id); setActionReason(''); }}
                  style={{ width: '100%', textAlign: 'left', cursor: 'pointer', borderColor:
                    r.relation_id === selectedRelation ? 'var(--action-primary)' : undefined }}>
                  <i aria-hidden="true">관</i><div><b>{r.relation_type_id}</b>
                    <small>{r.subject.object_id} → {r.object.object_id}</small></div>
                  <span className={`state-chip ${r.approval_status === 'APPROVED' ? 'success'
                    : r.approval_status === 'IN_REVIEW' ? 'warn' : 'muted'}`}>{r.approval_status}</span>
                </button>)}
              </div>

              {selectedRelationRow && <section className="panel" style={{ padding: 15 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'start' }}>
                  <div><small className="afs-muted">{selectedRelationRow.relation_id}</small>
                    <h3 style={{ margin: '3px 0 0' }}>{refLabel(selectedRelationRow.subject)}</h3>
                    <p className="section-text" style={{ margin: '5px 0' }}>
                      <b>{selectedRelationRow.relation_type_id}</b> → {refLabel(selectedRelationRow.object)}</p></div>
                  <span className={`state-chip ${selectedRelationRow.approval_status === 'APPROVED' ? 'success'
                    : selectedRelationRow.approval_status === 'IN_REVIEW' ? 'warn' : 'muted'}`}>
                    {selectedRelationRow.approval_status}</span>
                </div>
                <dl className="confirm-facts" style={{ marginTop: 12 }}>
                  <div><dt>유효 기간</dt><dd>{selectedRelationRow.effective_from} → {selectedRelationRow.effective_to || '폐지 전'}</dd></div>
                  <div><dt>소유·범위</dt><dd>{selectedRelationRow.owner_organization_id} · {selectedRelationRow.enterprise_scope_id}</dd></div>
                  <div><dt>근거</dt><dd>{selectedRelationRow.evidence_refs.join(' · ') || '없음'}</dd></div>
                  <div><dt>계산 참조</dt><dd>{selectedRelationRow.calculation_ref || '정성 관계'}</dd></div>
                  <div><dt>제출·승인</dt><dd>{selectedRelationRow.submitted_by || '미제출'} · {selectedRelationRow.approved_by || '미승인'}</dd></div>
                  <div><dt>결정 원장</dt><dd>{selectedRelationRow.ledger_correlation_id || '아직 결속되지 않음'}</dd></div>
                </dl>

                {selectedRelationRow.approval_status === 'IN_REVIEW' && (
                  <Banner tone="info" title="승인 버튼이 전용 원장 사건을 기록합니다">
                    임의 원장 ID를 입력하지 않습니다. 확인한 사람이 승인 사유를 적으면 서버가 이 관계를 대상으로
                    ONTOLOGY_RELATION_APPROVED 사건을 기록하고 관계에 즉시 결속합니다. 제안자 본인의 승인은 거부됩니다.
                  </Banner>
                )}
                {selectedRelationRow.approval_status === 'APPROVED' && (
                  <Banner tone="info" title="폐지도 별도 결정으로 기록합니다">
                    폐지 사유를 확인하면 ONTOLOGY_RELATION_RETIRED 사건을 기록한 뒤 현재 관계를 종료합니다.
                    원 승인 사건과 폐지 사건은 모두 보존됩니다.
                  </Banner>
                )}
                <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'flex-end', gap: 7 }}>
                  {selectedRelationRow.approval_status === 'DRAFT' && <button className="primary-button"
                    onClick={() => confirmAction.ask('submit')}>검토 요청</button>}
                  {selectedRelationRow.approval_status === 'IN_REVIEW' && <>
                    <button className="secondary-button" onClick={() => confirmAction.ask('reject')}>반려</button>
                    <button className="primary-button"
                      onClick={() => confirmAction.ask('approve')}>원장 기록 후 승인</button>
                  </>}
                  {selectedRelationRow.approval_status === 'APPROVED' && <button className="danger-solid"
                    onClick={() => confirmAction.ask('retire')}>관계 폐지</button>}
                </div>

                <ConfirmInline open={confirmAction.open}
                  title={confirmAction.target === 'submit' ? '관계를 검토 요청하시겠습니까?'
                    : confirmAction.target === 'approve' ? '승인 결정을 원장에 기록하시겠습니까?'
                      : confirmAction.target === 'reject' ? '관계를 반려하시겠습니까?' : '승인 관계를 폐지하시겠습니까?'}
                  body={confirmAction.target === 'approve' || confirmAction.target === 'retire'
                    ? '서버가 이 관계를 대상으로 전용 Decision Ledger 사건을 만들고 즉시 상태에 결속합니다.' : undefined}
                  confirmLabel={confirmAction.target === 'submit' ? '검토 요청'
                    : confirmAction.target === 'approve' ? '원장 기록 후 승인'
                      : confirmAction.target === 'reject' ? '사유와 함께 반려' : '원장 기록 후 폐지'}
                  danger={confirmAction.target === 'reject' || confirmAction.target === 'retire'}
                  changes={confirmAction.target === 'submit' ? '초안이 검토 중 상태로 바뀝니다.'
                    : confirmAction.target === 'approve' ? '승인 관계가 영향 경로에 사용될 수 있습니다.'
                      : confirmAction.target === 'reject' ? '검토 관계가 반려 상태로 종료됩니다.'
                        : '이 관계는 폐지 시각 이후 영향 경로에서 제외됩니다.'}
                  affects={`${selectedRelationRow.relation_type_id} · ${selectedRelationRow.enterprise_scope_id}`}
                  reversible={confirmAction.target === 'submit' ? '검토 중에는 승인 또는 반려로 종료합니다.'
                    : confirmAction.target === 'approve' ? '직접 되돌리지 않고 별도 폐지 승인으로 종료합니다.'
                      : confirmAction.target === 'reject' ? '새 관계 제안이 필요합니다.' : '새 승인 관계를 다시 제안해야 합니다.'}
                  approval={confirmAction.target === 'approve' || confirmAction.target === 'retire'
                    ? '현재 승인자의 관리 권한 · 대상 결속된 전용 원장 사건' : '현재 관계 관리 권한'}
                  reason={confirmAction.target === 'approve' || confirmAction.target === 'reject'
                    || confirmAction.target === 'retire' ? {
                    value: actionReason, onChange: setActionReason, required: true,
                    placeholder: confirmAction.target === 'approve'
                      ? '검토한 근거와 승인 판단을 입력하세요.' : '감사 원장에 남길 구체적인 사유를 입력하세요.',
                  } : undefined}
                  onCancel={() => { confirmAction.cancel(); setActionReason(''); }}
                  onConfirm={() => confirmAction.run((kind) => { void runRelationAction(kind); })} />
              </section>}
            </div>
          )}
        </div>
      </Panel>

      <Panel kicker="OBJECTS" title="업무 객체와 영향 경로">
        <div style={{ padding: 15, display: 'grid', gap: 12 }}>
          <div className="reg-filters" style={{ gridTemplateColumns: 'minmax(220px, 1fr) minmax(160px, .5fr) auto' }}>
            <label className="reg-filter"><span>기준 시각</span>
              <input className="afs-input" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
            </label>
            <label className="reg-filter"><span>네임스페이스</span>
              <select className="afs-select" value={namespace} onChange={(e) => setNamespace(e.target.value)}>
                <option value="">전체</option>
                {(namespaces.length ? namespaces : ['ecm', 'dataset']).map((v) => <option key={v}>{v}</option>)}
              </select>
            </label>
            <button className="secondary-button" style={{ alignSelf: 'end' }} onClick={load}>다시 조회</button>
          </div>

          {objects.status !== 'ok' ? (
            <EmptyOrError state={objects.status} error={objects.error} onRetry={load}
              emptyText="현재 범위에서 보이는 업무 객체가 없습니다." />
          ) : rows.length === 0 ? (
            <div className="empty-note">승인된 활성 관계에서 시작할 수 있는 객체가 없습니다.</div>
          ) : (
            <div className="afs-table-wrap">
              <table className="afs-table"><thead><tr><th>네임스페이스</th><th>유형</th><th>업무 객체</th><th /></tr></thead>
                <tbody>{rows.map((o) => {
                  const selected = root && refLabel(root) === refLabel(o);
                  return <tr key={refLabel(o)} className={selected ? 'on' : ''}>
                    <td>{o.namespace}</td><td>{o.object_type}</td><td>{o.object_id}</td>
                    <td><button className="text-button" onClick={() => setRoot(o)}>
                      {selected ? '선택됨' : '시작점 선택'}</button></td>
                  </tr>;
                })}</tbody>
              </table>
            </div>
          )}
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button className="primary-button" disabled={!root || impact.status === 'loading'} onClick={run}>
              선택 객체의 영향 경로 확인
            </button>
          </div>
        </div>
      </Panel>

      {impact.status === 'error' && <Banner tone="error" title="영향 경로를 확인하지 못했습니다">{impact.error}</Banner>}
      {!!impact.value?.query_id && (
        <Panel kicker="IMPACT" title={`영향 경로 (${paths.length})`}>
          {paths.length === 0 ? <div className="empty-note">현재 기준 시각과 권한 범위에서 보이는 영향 경로가 없습니다.</div>
            : <div style={{ padding: 15, display: 'grid', gap: 10 }}>
              {paths.map((p, i) => <section className="panel" style={{ padding: 13 }} key={p.path_fingerprint}>
                <b>경로 {i + 1}</b>
                <p className="section-text">{(p.nodes || []).map(refLabel).join(' → ')}</p>
                <small className="afs-muted">관계 {(p.edges || []).map((e) => e.relation_type_id || '미상').join(' · ')}
                  {' · '}경로 지문 {p.path_fingerprint.slice(0, 16)}</small>
              </section>)}
            </div>}
        </Panel>
      )}
    </>
  );
}
