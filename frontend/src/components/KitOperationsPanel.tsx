import { useEffect, useState } from 'react';

import { HubDialog } from '../design/HubDialog';
import { EmptyOrError } from '../design/DataState';
import { ScreenHead } from '../design/HubShell';
import { DataPrepError, listInstances } from '../lib/dataPrepApi';
import { KitAppPanel } from './KitAppPanel';

type Props = { onClose: () => void; onOpenBuild: () => void };

/** 현재 조직에 실제 적용된 업무키트 앱을 찾고 실행하는 제품 진입점. */
export function KitOperationsPanel({ onClose, onOpenBuild }: Props) {
  const [instances, setInstances] = useState<any[] | null>(null);
  const [selected, setSelected] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
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
  }, []);

  return (
    <HubDialog label="업무 앱 운영" onClose={onClose}>
      <div className="afs-dialog-bar">
        <b>업무 앱 운영</b>
        <span>현재 회사·조직에 적용된 업무키트 앱을 열고 운영 상태를 확인합니다</span>
        <div className="bar-actions">
          <button className="secondary-button" onClick={onOpenBuild}>새 업무키트 앱 만들기</button>
          <button className="secondary-button" onClick={onClose}>닫기 (Esc)</button>
        </div>
      </div>
      <div className="afs-dialog-body">
        <div className="hub-main">
          <ScreenHead kicker="업무 앱" title="현재 운영 가능한 앱"
            description="업무키트 적용본별로 운영 앱·후보 앱·승인 대기 앱을 구분합니다. 내부 식별자를 직접 입력하지 않습니다." />

          {error ? (
            <EmptyOrError state="error" error={error} emptyText="업무 앱이 없습니다." />
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
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {instances.map((row) => {
                  const id = String(row.instance_id || '');
                  const active = selected === id;
                  return (
                    <button key={id} type="button" aria-pressed={active}
                      className={active ? 'primary-button' : 'secondary-button'}
                      onClick={() => setSelected(id)}>
                      {row.label || row.kit_id || '이름 없는 적용본'}
                      <span style={{ opacity: .7, marginLeft: 6, fontSize: 11 }}>
                        {row.entity_mode || '문맥 미기록'} · {row.status || '상태 미기록'}
                      </span>
                    </button>
                  );
                })}
              </div>
              {selected && (
                <div style={{ border: '1px solid var(--surface-border)', borderRadius: 8,
                  background: 'var(--surface-card)' }}>
                  <KitAppPanel instanceId={selected} mode="operate" />
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </HubDialog>
  );
}
