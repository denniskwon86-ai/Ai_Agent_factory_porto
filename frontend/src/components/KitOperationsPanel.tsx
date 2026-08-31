import { useEffect, useRef, useState } from 'react';

import { HubDialog } from '../design/HubDialog';
import { EmptyOrError } from '../design/DataState';
import { DataPrepError, listInstances } from '../lib/dataPrepApi';
import { HubShell, type RailItem } from '../design/HubShell';
import { JarvisRail } from '../design/JarvisRail';
import { getEnterpriseContext } from '../lib/api';
import { KitAppPanel } from './KitAppPanel';

type Props = { onClose?: () => void; onOpenBuild: () => void; page?: boolean };
type OperationsView = 'all' | 'active' | 'candidate' | 'pending';

const OPERATIONS_ITEMS: { id: OperationsView; label: string; hint: string }[] = [
  { id: 'all', label: '전체 앱', hint: '현재 회사에 적용된 업무 앱 전체' },
  { id: 'active', label: '운영 중', hint: '인증 데이터를 읽는 앱' },
  { id: 'candidate', label: '운영 전환', hint: '검토·승격이 필요한 앱' },
  { id: 'pending', label: '승인 대기', hint: '계약 검토가 남은 앱' },
];

const VIEW_TITLE: Record<OperationsView, { title: string; description: string }> = {
  all: {
    title: '현재 회사의 업무 앱',
    description: '운영 중인 앱과 운영 전환이 필요한 앱을 상태별로 확인합니다.',
  },
  active: {
    title: '운영 중인 앱',
    description: '승인된 계약과 인증 데이터를 사용해 현재 실행할 수 있는 앱입니다.',
  },
  candidate: {
    title: '운영 전환 검토',
    description: '만들기는 끝났지만 운영 승격의 근거와 최종 점검이 필요한 앱입니다.',
  },
  pending: {
    title: '계약 승인 대기',
    description: '운영 전에 계약 검토와 직무 분리 승인이 남아 있는 앱입니다.',
  },
};

function contextLabel(value: unknown): string {
  const normalized = String(value || '').trim().toUpperCase();
  if (normalized === 'REAL') return '실제 운영 문맥';
  if (normalized === 'VIRTUAL') return '가상 시연 문맥';
  return normalized || '문맥 미기록';
}

function instanceStatusLabel(value: unknown): string {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'active') return '적용 중';
  if (normalized === 'draft') return '준비 중';
  if (normalized === 'retired') return '사용 종료';
  return normalized || '상태 미기록';
}

/** 현재 조직에 실제 적용된 업무키트 앱을 찾고 실행하는 제품 진입점. */
export function KitOperationsPanel({ onClose, onOpenBuild, page = false }: Props) {
  const [instances, setInstances] = useState<any[] | null>(null);
  const [selected, setSelected] = useState('');
  const [error, setError] = useState('');
  const [view, setView] = useState<OperationsView>('all');
  const [revision, setRevision] = useState(0);
  const contextRef = useRef(getEnterpriseContext());

  useEffect(() => {
    let alive = true;
    setError('');
    listInstances().then((result) => {
      if (!alive) return;
      const rows = result.instances || [];
      setInstances(rows);
      if (rows.length === 1) setSelected(String(rows[0].instance_id || ''));
    }).catch((reason: unknown) => {
      if (!alive) return;
      const err = reason as DataPrepError;
      setError(err?.message || '업무 앱을 확인하지 못했습니다.');
    });
    return () => { alive = false; };
  }, [revision]);

  useEffect(() => {
    const refresh = () => {
      const next = getEnterpriseContext();
      if (next.tenantId !== contextRef.current.tenantId) {
        // 회사가 바뀌는 동안 앞 회사의 적용본을 새 회사 화면에 남겨 두지 않는다.
        setInstances(null);
        setSelected('');
      }
      contextRef.current = next;
      setRevision((value) => value + 1);
    };
    window.addEventListener('factory:enterprise-context-changed', refresh);
    return () => window.removeEventListener('factory:enterprise-context-changed', refresh);
  }, []);

  const selectedInstance = (instances || []).find(
    (row) => String(row.instance_id || '') === selected,
  );
  const operationsIcons: Record<OperationsView, RailItem['icon']> = {
    all: 'apps', active: 'inject', candidate: 'revise', pending: 'contract',
  };
  const railItems: RailItem[] = OPERATIONS_ITEMS.map((item) => ({
    ...item, icon: operationsIcons[item.id],
    count: item.id === 'all' ? (instances?.length || 0) : undefined,
    countLabel: item.id === 'all' ? `${instances?.length || 0}개` : undefined,
  }));

  const content = (
    <div className={page ? 'product-page-content' : 'afs-scope'} style={page ? undefined : {
      background: 'var(--surface-page)', minHeight: '100%', padding: 24,
      display: 'flex', flexDirection: 'column', gap: 16,
    }}>
      <div>
        <small style={{ display: 'block', color: 'var(--ls-red)', fontSize: 11,
          fontWeight: 800, letterSpacing: '.1em' }}>APP OPERATIONS</small>
        <h1 style={{ margin: '5px 0 4px', color: 'var(--surface-text)',
          fontSize: 26, lineHeight: 1.25 }}>앱 운영</h1>
        <p style={{ margin: 0, color: 'var(--surface-text-muted)', fontSize: 14 }}>
          현재 회사에 적용된 업무 앱을 열고, 계약·데이터 준비도와 운영 전환 상태를 관리합니다.
        </p>
      </div>

      <div style={{ display: 'flex', gap: 16, alignItems: 'center',
        justifyContent: 'space-between', flexWrap: 'wrap' }}>
        {!page && <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {OPERATIONS_ITEMS.map((item) => {
            const on = view === item.id;
            return (
              <button key={item.id} type="button" onClick={() => setView(item.id)}
                title={item.hint} aria-pressed={on} style={{
                  height: 36, padding: '0 14px', fontSize: 13, borderRadius: 6,
                  cursor: 'pointer', border: `1px solid ${on ? 'var(--ls-navy)' : 'var(--surface-border)'}`,
                  background: on ? 'var(--action-primary-bg)' : 'var(--surface-card)',
                  color: on ? 'var(--action-primary-fg)' : 'var(--surface-text-muted)',
                  fontWeight: on ? 700 : 500,
                }}>{item.label}</button>
            );
          })}
        </div>}
        <button className="primary-button" onClick={onOpenBuild}>＋ 새 업무키트 앱</button>
      </div>

      <p style={{ fontSize: 12, color: 'var(--surface-text-faint)', margin: 0 }}>
        {VIEW_TITLE[view].description} 만든 앱과 운영 앱은 다르며, 승인과 준비도를 통과한 앱만 인증 데이터를 읽습니다.
      </p>

      {error ? (
            <div style={{ display: 'grid', gap: 10 }}>
              <EmptyOrError state="error" error={error} emptyText="업무 앱이 없습니다." />
              <div>
                <button className="secondary-button"
                  onClick={() => setRevision((value) => value + 1)}>다시 확인</button>
              </div>
            </div>
          ) : instances === null ? (
            <div className="afs-muted">업무키트 적용본을 확인하는 중…</div>
          ) : instances.length === 0 ? (
            <div className="afs-bg-sunken afs-border" style={{ padding: 16, borderWidth: 1,
              borderStyle: 'solid', borderRadius: 8 }}>
              <b>현재 조직에 적용된 업무키트가 없습니다.</b>
              <div className="afs-muted" style={{ marginTop: 5 }}>
                업무 데이터 준비에서 패키지를 적용한 뒤 앱을 만들 수 있습니다.
              </div>
            </div>
          ) : (
            <div style={{ display: 'grid', gap: 14 }}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap',
                alignItems: 'center' }}>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {instances.map((row) => {
                  const id = String(row.instance_id || '');
                  const active = selected === id;
                  return (
                    <button key={id} type="button" aria-pressed={active}
                      className={active ? 'primary-button' : 'secondary-button'}
                      onClick={() => setSelected(id)}>
                      {row.label || '이름 미등록 적용본'}
                      <span style={{ opacity: .7, marginLeft: 6, fontSize: 11 }}>
                        {contextLabel(row.entity_mode)} · {instanceStatusLabel(row.status)}
                      </span>
                    </button>
                  );
                })}
                </div>
              </div>
              {selected && (
                <div style={{ border: '1px solid var(--surface-border)', borderRadius: 8,
                  background: 'var(--surface-card)' }}>
                  <KitAppPanel instanceId={selected} mode="operate" statusFilter={view} />
                </div>
              )}
            </div>
          )}
    </div>
  );

  if (page) return (
    <HubShell layoutClassName="product-page-shell"
      kicker="APP OPERATIONS" title="앱 운영"
      subtitle="적용된 업무 앱의 실행 상태와 운영 전환을 관리합니다."
      items={railItems} activeId={view} onSelect={(id) => setView(id as OperationsView)}
      footer={<div className="inheritance-card">
        <span>OPERATING GATE</span>
        <b>승인과 준비도를 함께 확인합니다</b>
        <p>만들어진 앱이라도 계약과 인증 데이터가 준비되기 전에는 운영 앱이 아닙니다.</p>
      </div>}
      jarvis={<JarvisRail
        contextTitle={selectedInstance?.label || VIEW_TITLE[view].title}
        contextDescription={selectedInstance
          ? '현재 선택한 업무키트 적용본과 그 안의 앱 상태를 기준으로 답합니다.'
          : '업무키트 적용본을 선택하면 해당 운영 문맥으로 답합니다.'}
        context={{
          current_module: 'app_operations',
          selected_object_type: selectedInstance ? 'kit_instance' : 'operations_view',
          selected_object_id: selected,
          object_snapshot: selectedInstance || { view },
          available_actions: ['업무 앱 열기', '운영 전환 확인', '계약·데이터 준비도 확인'],
        }}
        evidence={selectedInstance ? [
          { label: '실행 문맥', value: contextLabel(selectedInstance.entity_mode) },
          { label: '적용 상태', value: instanceStatusLabel(selectedInstance.status) },
        ] : []}
        quickQuestions={[
          '이 앱이 지금 운영 가능한 상태인지 설명해 주세요.',
          '운영 전환을 막고 있는 계약이나 데이터가 있습니까?',
          '현재 적용본에서 우선 점검할 항목을 알려 주세요.',
        ]} />}
    >
      {content}
    </HubShell>
  );
  return (
    <HubDialog label="업무 앱 운영" onClose={onClose || (() => {})}>
      <div className="afs-dialog-bar">
        <b>앱 운영</b>
        <span>현재 회사·조직의 업무 앱을 열고 운영 전환 상태를 관리합니다</span>
        <div className="bar-actions">
          <button className="secondary-button" onClick={onClose}>닫기 (Esc)</button>
        </div>
      </div>
      <div className="afs-dialog-body">{content}</div>
    </HubDialog>
  );
}
