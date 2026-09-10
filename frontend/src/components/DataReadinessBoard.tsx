import { useEffect, useMemo, useState } from 'react';
import {
  DataPrepError, getReadiness,
  type DatasetReadiness, type DatasetState, type InstanceReadiness, type OutputReadiness,
} from '../lib/dataPrepApi';
import { KitAppPanel } from './KitAppPanel';
import { KitGettingStarted } from './KitGettingStarted';

// [BDR-5 / Wave H] 데이터 준비 보드 — **「지금 무엇까지 믿고 만들 수 있는가」.**
//
// ⚠️ 이 화면이 지켜야 할 단 하나: **준비되지 않은 것을 «0» 으로 그리지 않는다.**
//   「아직 아니다」와 「값이 0이다」가 같아 보이면 사용자는 그 화면 위에서 보고서를
//   만들고, 그 보고서는 완성돼 보인다.
//
// ⚠️ 판정하지 않는다. 서버가 준 상태·다음 행동·책임자를 **그대로 옮긴다** — 화면이
//   자기 규칙으로 다시 판단하면 두 판정이 갈라진다.

// 상태별 표시. ★ **색만으로 구분하지 않는다**(설계 §12 UI 규칙) — 이름표와 기호를
// 함께 단다. 색각 이상·흑백 인쇄·저조도 화면에서 색은 사라진다.
const STATE_VIEW: Record<DatasetState,
  { label: string; mark: string; tone: string }> = {
  NOT_CONFIGURED:        { label: '원천 미지정',   mark: '○', tone: 'var(--surface-text-muted)' },
  SOURCE_CONFIGURED:     { label: '파일 대기',     mark: '◔', tone: 'var(--surface-text-muted)' },
  DATA_AVAILABLE:        { label: '검사 대기',     mark: '◑', tone: 'var(--state-warn-fg)' },
  QUALITY_FAILED:        { label: '품질 격리',     mark: '✕', tone: 'var(--state-error-fg)' },
  RECONCILIATION_FAILED: { label: '대사 불일치',   mark: '✕', tone: 'var(--state-error-fg)' },
  APPROVAL_PENDING:      { label: '인증 대기',     mark: '◕', tone: 'var(--state-warn-fg)' },
  READY:                 { label: '준비됨',       mark: '●', tone: 'var(--state-success-fg)' },
  STALE:                 { label: '기준시점 경과', mark: '◐', tone: 'var(--state-warn-fg)' },
  UNAVAILABLE:           { label: '읽을 수 없음',  mark: '⚠', tone: 'var(--state-error-fg)' },
};

const OUTPUT_VIEW: Record<string, { label: string; tone: string }> = {
  AVAILABLE:              { label: '가능',        tone: 'var(--state-success-fg)' },
  AVAILABLE_WITH_WARNING: { label: '제한적 가능', tone: 'var(--state-warn-fg)' },
  BLOCKED:                { label: '막힘',        tone: 'var(--state-error-fg)' },
};

function AsOf({ value }: { value: string }) {
  // ⚠️ 기준시점이 없으면 **비워 두지 않는다.** 빈 칸은 「방금 것」으로 읽힌다.
  if (!value) return <span style={{ color: 'var(--state-warn-fg)' }}>기준시점 없음</span>;
  return <span style={{ color: 'var(--surface-text-muted)' }}>{value.slice(0, 16).replace('T', ' ')}</span>;
}

function DatasetRow({ row, onPrepare }: { row: DatasetReadiness; onPrepare?: (key: string) => void }) {
  const v = STATE_VIEW[row.state] ?? {
    // ⚠️ 모르는 상태를 «준비됨» 으로 떨어뜨리지 않는다 — 서버가 새 상태를 내면
    //   화면은 그것을 «모른다» 고 말해야 한다.
    label: `알 수 없는 상태(${row.state})`, mark: '⚠', tone: 'var(--state-error-fg)',
  };
  return (
    <tr style={{ borderBottom: '1px solid var(--surface-border)' }}>
      <td style={{ padding: '10px 8px', fontSize: 14 }}>
        {/* 기술 계약키는 화면에 내놓지 않는다. 문의·감사는 서버 로그와 원장 식별자로
            처리하고, 사용자는 업무 이름만 본다. 이름이 없으면 결손 자체를 말한다. */}
        {row.label || '이름이 등록되지 않은 업무 데이터'}
      </td>
      <td style={{ padding: '10px 8px', fontSize: 14, color: v.tone, whiteSpace: 'nowrap' }}>
        <span aria-hidden style={{ marginRight: 6 }}>{v.mark}</span>{v.label}
      </td>
      <td style={{ padding: '10px 8px', fontSize: 13 }}>
        {/* ★ 다음 행동과 책임자를 **함께** 보여 준다 — 「무엇을」만 있고 「누가」가
            없으면 아무도 안 한다. */}
        {row.next_action || <span style={{ color: 'var(--surface-text-faint)' }}>—</span>}
        {row.responsible_role && (
          <span style={{ color: 'var(--surface-text-muted)', marginLeft: 8 }}>({row.responsible_role})</span>
        )}
        {row.detail && (
          <div style={{ color: 'var(--state-warn-fg)', fontSize: 12, marginTop: 2 }}>{row.detail}</div>
        )}
        {onPrepare && (
          <button type="button" onClick={() => onPrepare(row.dataset_contract_key)}
            aria-label={`${row.label || '업무 데이터'} 자료 준비`}
            style={{ display: 'block', marginTop: 6, padding: '5px 10px', fontSize: 13 }}>
            자료 준비
          </button>
        )}
      </td>
      <td style={{ padding: '10px 8px', fontSize: 13 }}><AsOf value={row.as_of} /></td>
    </tr>
  );
}

function OutputRow({ row }: { row: OutputReadiness }) {
  const v = OUTPUT_VIEW[row.state] ?? { label: row.state, tone: 'var(--state-error-fg)' };
  return (
    <li style={{ marginBottom: 10, fontSize: 14 }}>
      <strong>{row.label || '이름이 등록되지 않은 업무 결과'}</strong>
      <span style={{ color: v.tone, marginLeft: 8 }}>{v.label}</span>
      {row.user_message && (
        <div style={{ color: 'var(--surface-text-muted)', fontSize: 13, marginTop: 2 }}>{row.user_message}</div>
      )}
      {row.next_action && (
        <div style={{ fontSize: 13, marginTop: 2 }}>
          → {row.next_action}
          {row.responsible_role && (
            <span style={{ color: 'var(--surface-text-muted)', marginLeft: 6 }}>({row.responsible_role})</span>
          )}
        </div>
      )}
    </li>
  );
}

export function DataReadinessBoard({ instanceId, refreshKey = 0, onPrepareDataset }: {
  instanceId: string; refreshKey?: number; onPrepareDataset?: (key: string) => void;
}) {
  const [data, setData] = useState<InstanceReadiness | null>(null);
  const [error, setError] = useState<{ message: string; status: number } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    getReadiness(instanceId)
      .then((d) => { if (alive) setData(d); })
      .catch((e: unknown) => {
        if (!alive) return;
        const err = e as DataPrepError;
        setError({ message: err?.message || '불러오지 못했습니다.', status: err?.status || 0 });
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [instanceId, refreshKey]);

  // ★ 35개 계약을 한 표로 펴지 않는다. 사용자는 먼저 구매·물류·재고 같은 업무기능을
  // 이해하고, 진단이 필요할 때만 그 안의 계약을 펼친다. 분류는 서버가 준 정본만 쓴다.
  // ⚠️ 로딩 전에도 Hook 호출 순서를 지켜야 하므로 `data`가 없으면 빈 목록을 쓴다.
  const groups = useMemo(() => {
    const byId = new Map<string, {
      id: string; name: string; description: string; order: number; rows: DatasetReadiness[];
    }>();
    for (const row of (data?.datasets || [])) {
      const id = row.business_kit_id || 'UNCLASSIFIED';
      const group = byId.get(id) || {
        id,
        name: row.business_kit_name || '미분류 — 정본 보완 필요',
        description: row.description || '',
        order: Number.isFinite(row.order) ? row.order : 999,
        rows: [],
      };
      group.rows.push(row);
      byId.set(id, group);
    }
    return [...byId.values()].sort((a, b) => a.order - b.order || a.id.localeCompare(b.id));
  }, [data?.datasets]);

  if (loading) return <div style={{ padding: 16 }}>준비 상태를 확인하는 중…</div>;

  // ★★★ **조회 실패와 0건을 구분한다**(설계 §12 UI 규칙). 실패를 빈 표로 그리면
  //   사용자는 「준비된 데이터가 없다」로 읽고, 원인을 데이터에서 찾는다.
  if (error) {
    return (
      <div style={{ padding: 16, border: '1px solid var(--state-error-fg)', borderRadius: 8 }}>
        <strong style={{ color: 'var(--state-error-fg)' }}>준비 상태를 불러오지 못했습니다</strong>
        <div style={{ marginTop: 6, fontSize: 14 }}>{error.message}</div>
        <div style={{ marginTop: 6, fontSize: 13, color: 'var(--surface-text-muted)' }}>
          {/* ⚠️ 「없음」과 「지금 못 읽음」은 사용자가 할 일이 다르다. */}
          {error.status === 404
            ? '이 키트 인스턴스를 찾을 수 없습니다 — 조직 범위를 확인해 주십시오.'
            : '데이터가 없는 것이 아니라 지금 확인하지 못한 상태입니다. 잠시 후 다시 시도해 주십시오.'}
        </div>
      </div>
    );
  }
  if (!data) return null;

  const c = data.coverage;
  //: [DAO-12] 제안은 없어도 화면이 서야 한다 — 준비도가 본문이고 이것은 곁이다.
  const hints = data.acquisition_hints;

  return (
    <div style={{ padding: 16 }}>
      {/* ★★★ 성격 표시를 **맨 위에** 둔다 — 빠지면 이 화면의 숫자가 실적으로 읽힌다. */}
      <div style={{
        padding: '8px 12px', background: 'var(--state-warn-bg)', border: '1px solid var(--state-warn-fg)',
        borderRadius: 6, fontSize: 13, marginBottom: 12,
      }}>
        {data.data_kind === 'DEMO/SYNTHETIC'
          ? '시연용 합성 데이터(DEMO/SYNTHETIC)입니다 — 실적이 아닙니다.'
          : `데이터 성격: ${data.data_kind || '알 수 없음'}`}
      </div>

      <h3 style={{ fontSize: 18, margin: '0 0 4px' }}>데이터 준비 상태</h3>
      <div style={{ fontSize: 13, color: 'var(--surface-text-muted)', marginBottom: 12 }}>
        {/* ★ 전체 진행상태와 다음 행동을 **동시에** 보여 준다(설계 §12 UI 규칙). */}
        필요 {c.required}건 중 준비 {c.ready} · 기준시점 경과 {c.stale} · 막힘 {c.blocked}
        {' · '}기준시점 <AsOf value={data.as_of} />
        {data.context_omitted > 0 && (
          <span style={{ marginLeft: 8 }}>· 현재 문맥에서 제외 {data.context_omitted}건</span>
        )}
      </div>

      <h3 style={{ fontSize: 16, margin: '0 0 8px' }}>업무기능별 준비도</h3>
      <div style={{ display: 'grid', gap: 8, marginBottom: 20 }}>
        {groups.map((group) => {
          const ready = group.rows.filter((r) => r.state === 'READY').length;
          const attention = group.rows.length - ready;
          return (
            <details key={group.id} data-business-kit={group.id} style={{
              border: '1px solid var(--surface-border)', borderRadius: 7,
              background: 'var(--surface-card)',
            }}>
              <summary style={{
                cursor: 'pointer', padding: '10px 12px', display: 'flex', alignItems: 'center',
                gap: 10, fontSize: 14,
              }}>
                <strong style={{ flex: 1 }}>{group.name}</strong>
                <span style={{ color: attention ? 'var(--state-warn-fg)' : 'var(--state-success-fg)',
                  fontSize: 13 }}>
                  준비 {ready}/{group.rows.length}{attention ? ` · 확인 ${attention}` : ''}
                </span>
              </summary>
              {group.description && (
                <div style={{ padding: '0 12px 8px', color: 'var(--surface-text-muted)', fontSize: 13 }}>
                  {group.description}
                </div>
              )}
              <KitGettingStarted kitId={data.kit_id} version={data.version} groupId={group.id}
                canPrepare={Boolean(onPrepareDataset)} />
              <div style={{ overflowX: 'auto', borderTop: '1px solid var(--surface-border)' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: '2px solid var(--surface-border)', textAlign: 'left' }}>
                      <th style={{ padding: '8px', fontSize: 13 }}>업무 데이터</th>
                      <th style={{ padding: '8px', fontSize: 13 }}>상태</th>
                      <th style={{ padding: '8px', fontSize: 13 }}>다음에 할 일</th>
                      <th style={{ padding: '8px', fontSize: 13 }}>기준시점</th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.rows.map((d) => <DatasetRow key={d.dataset_contract_key} row={d} onPrepare={onPrepareDataset} />)}
                  </tbody>
                </table>
              </div>
            </details>
          );
        })}
      </div>

      <h3 style={{ fontSize: 16, margin: '0 0 8px' }}>지금 만들 수 있는 것</h3>
      {data.outputs.length === 0 ? (
        // ⚠️ 산출물 선언이 없는 키트는 「무엇이 막혔는지」에 답할 수 없다 —
        //   그 사실을 «전부 가능» 으로 보이게 두지 않는다.
        <div style={{ fontSize: 14, color: 'var(--state-warn-fg)' }}>
          이 키트는 만들 수 있는 결과를 선언하지 않았습니다 — 무엇이 막혔는지 답할 수 없습니다.
        </div>
      ) : (
        <ul style={{ paddingLeft: 18, margin: 0 }}>
          {data.outputs.map((o) => <OutputRow key={o.output} row={o} />)}
        </ul>
      )}

      {/* ── [DAO-12] 「준비되지 않음」에서 끝내지 않는다 ────────────────
          ★★★ 이것은 **제안이지 판정이 아니다.** 위의 준비도 숫자는 이 구역 때문에
            바뀌지 않는다 — 수집만으로는 준비되지 않기 때문이다. */}
      {hints && hints.suggestions.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <h3 style={{ fontSize: 16, margin: '0 0 4px' }}>부족한 자료를 채우는 방법</h3>
          {/* 서버가 준 고지를 그대로 — 화면이 문구를 지어내지 않는다. */}
          {hints.summary.notice && (
            <div style={{ fontSize: 12, color: 'var(--surface-text-muted)', marginBottom: 8 }}>
              {hints.summary.notice}
            </div>
          )}
          <div style={{ display: 'grid', gap: 8 }}>
            {hints.suggestions.map((s) => (
              <div key={s.dataset_contract_key} style={{
                border: '1px solid var(--surface-border)', borderRadius: 6, padding: '8px 12px',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                  <strong>{s.dataset_contract_key}</strong>
                  {/* 판정은 제안 옆에 **그대로** 남는다 */}
                  <span style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>
                    준비도 {s.readiness_state}
                  </span>
                </div>
                <div style={{ fontSize: 12, marginTop: 4 }}>{s.gap_label}</div>
                {s.options.map((o) => (
                  <div key={o.provider_id} style={{ fontSize: 12, marginTop: 6 }}>
                    · <b>{o.name}</b> ({o.publisher} · {o.cost} · 등급 {o.trust_grade})
                    {' '}
                    <span style={{ color: o.credential_configured ? 'inherit' : 'var(--state-warn-fg)' }}>
                      {o.requires_credential
                        ? (o.credential_configured ? '인증키 설정됨' : '인증키 없음')
                        : '인증 불필요'}
                    </span>
                    {/* ★★★ 한계를 떼면 고르는 순간 사라진다 */}
                    {o.known_limits.length > 0 && (
                      <ul style={{ margin: '2px 0 0', paddingLeft: 18, color: 'var(--state-warn-fg)' }}>
                        {o.known_limits.map((l) => <li key={l}>{l}</li>)}
                      </ul>
                    )}
                  </div>
                ))}
                {s.collected_rows > 0 && (
                  <div style={{ fontSize: 12, marginTop: 6 }}>
                    이미 수집 {s.collected_rows}행 — <b>남은 단계</b>
                    <ol style={{ margin: '2px 0 0', paddingLeft: 20 }}>
                      {s.remaining_steps.map((t) => <li key={t}>{t}</li>)}
                    </ol>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
      {/* 힌트를 못 읽었으면 «제안 0건» 과 구분해 말한다 */}
      {hints?.unavailable_reason && (
        <div style={{ marginTop: 12, fontSize: 12, color: 'var(--state-warn-fg)' }}>
          수집 제안을 불러오지 못했습니다({hints.unavailable_reason}) — 준비도 판정은
          위 내용이 맞습니다.
        </div>
      )}

      {/* ★★★ [2026-08-23] **보여 주기 다음에 «하기» 를 붙인다.**
          ⚠️⚠️ 여기까지가 종전의 화면이었다 — 「지금 만들 수 있는 것: 가능」을 그리고
            끝났고, 누를 것이 없었다. 「보여 주는 것」과 「되는 것」이 다르면 보여 주는
            쪽이 거짓말을 한다. */}
      <div style={{ marginTop: 20, borderTop: '1px solid var(--surface-border)' }}>
        <KitAppPanel instanceId={instanceId} />
      </div>
    </div>
  );
}
