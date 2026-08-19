import { useState } from 'react';

import { HubDialog } from '../design/HubDialog';
import { Panel } from '../design/HubShell';
import { DataPrepError, simulate } from '../lib/dataPrepApi';

// [G4 / Wave H] 시나리오 시뮬레이션 화면 — 파일럿 동선 10~11칸.
//
// ⚠️ 이 화면이 지켜야 할 것 셋
//   ① **숫자를 화면이 만들지 않는다.** 서버가 준 값을 그대로 옮긴다 — 화면이 계산하면
//      두 곳이 갈라지고, 갈린 날 어느 쪽이 맞는지 아무도 모른다.
//   ② **기준선 없이 못 돌린다.** Snapshot 집합을 명시해야 한다. 「최신으로 알아서」는
//      재현할 수 없는 숫자를 낳는다.
//   ③ **비율만 크게 보여주지 않는다.** 작은 기준값에서 «+300%» 가 나오고, 그것이
//      회의에서 실제 규모보다 크게 읽힌다. 값과 비율을 함께 둔다.

// ★ Driver 이름·단위는 서버(`core/calc_graph.DRIVERS`)와 **같아야** 한다.
const DRIVERS: { key: string; label: string; unit: string; hint: string }[] = [
  { key: 'fx_rate_pct', label: '환율', unit: '%', hint: '오르면 수입 원료 대금이 늘어납니다' },
  { key: 'lead_time_days', label: '도입 지연', unit: '일', hint: '늦어진 만큼 생산이 줄어듭니다' },
  { key: 'power_price_pct', label: '전력단가', unit: '%', hint: '생산량에 비례해 원가에 붙습니다' },
];

// 기준값 — 사용자가 회사 실적에서 채운다. ⚠️ 기본값을 «그럴듯한 숫자» 로 채우지
// 않는다. 채우면 사용자가 그것을 자기 회사 값으로 착각한 채 회의에 들고 간다.
const BASE_FIELDS: { key: string; label: string; unit: string }[] = [
  { key: 'production_qty', label: '생산량', unit: 'ton' },
  { key: 'ending_inventory', label: '기말재고', unit: 'ton' },
  { key: 'purchase_payment', label: '구매지급', unit: '원' },
  { key: 'ending_cash', label: '기말현금', unit: '원' },
  { key: 'operating_profit', label: '영업이익', unit: '원' },
  { key: 'power_cost', label: '전력비', unit: '원' },
  { key: 'period_days', label: '기간', unit: '일' },
];

function num(v: string): number | null {
  if (!v.trim()) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export function ScenarioPanel({ onClose }: { onClose: () => void }) {
  const [instanceId, setInstanceId] = useState('');
  const [snapshotIds, setSnapshotIds] = useState('');
  const [base, setBase] = useState<Record<string, string>>({});
  const [drivers, setDrivers] = useState<Record<string, string>>({});
  const [result, setResult] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setError(null);
    setResult(null);

    const ids = snapshotIds.split(/[\s,]+/).filter(Boolean);
    if (!instanceId.trim() || ids.length === 0) {
      // ★★★ 서버가 막을 자리를 **누르기 전에** 말한다.
      setError('키트 인스턴스와 Snapshot ID 를 지정해 주십시오 — 「최신으로 알아서」는 '
        + '재현할 수 없는 숫자를 만듭니다.');
      return;
    }
    const baseValues: Record<string, number> = {};
    const missing: string[] = [];
    for (const f of BASE_FIELDS) {
      const v = num(base[f.key] || '');
      // ⚠️ 빈 칸을 0으로 채우지 않는다 — 「데이터가 없다」가 「값이 0이다」가 되면
      //   결과가 완성돼 보인다.
      if (v === null) missing.push(f.label);
      else baseValues[f.key] = v;
    }
    if (missing.length) {
      setError(`기준값이 비었습니다: ${missing.join(', ')} — 빈 값을 0으로 채우지 않습니다.`);
      return;
    }
    const assumptions: Record<string, number> = {};
    for (const d of DRIVERS) {
      const v = num(drivers[d.key] || '');
      if (v !== null) assumptions[d.key] = v;
    }

    setBusy(true);
    try {
      setResult(await simulate(instanceId.trim(), ids, baseValues, assumptions));
    } catch (e) {
      const err = e as DataPrepError;
      setError(err?.message || '시뮬레이션을 돌리지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <HubDialog label="시나리오 시뮬레이션 — 환율·지연·전력단가" onClose={onClose}>
      <div className="afs-dialog-bar">
        <b>시나리오 시뮬레이션</b>
        <span>고정된 기준선 위에서만 계산합니다 — 같은 입력이면 같은 답입니다</span>
        <div className="bar-actions">
          {busy && <span className="busy">계산 중…</span>}
          <button onClick={onClose}>닫기</button>
        </div>
      </div>

      <div className="afs-dialog-body" style={{
        overflow: 'auto', padding: 18, display: 'flex', flexDirection: 'column',
      }}>
        <Panel className="afs-fill">
          <h4 style={{ margin: '0 0 8px', fontSize: 15 }}>기준선</h4>
          <div style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
            <input value={instanceId} onChange={(e) => setInstanceId(e.target.value)}
              placeholder="키트 인스턴스 id"
              style={{ flex: 1, padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: 6 }} />
            <input value={snapshotIds} onChange={(e) => setSnapshotIds(e.target.value)}
              placeholder="Snapshot id (공백/쉼표로 여러 개)"
              style={{ flex: 2, padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: 6 }} />
          </div>
          <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 16 }}>
            {/* ★ 왜 명시해야 하는지를 화면이 말한다 — 이유를 모르면 사용자는
                「왜 자동으로 안 되나」로 읽는다. */}
            판을 직접 고정합니다. 「최신」을 가리키면 한 달 뒤 같은 보고서가 다른 답을 냅니다.
          </div>

          <h4 style={{ margin: '0 0 8px', fontSize: 15 }}>기준값</h4>
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
            gap: 10, marginBottom: 16,
          }}>
            {BASE_FIELDS.map((f) => (
              <label key={f.key} style={{ fontSize: 13 }}>
                {f.label} <span style={{ color: '#6b7280' }}>({f.unit})</span>
                <input value={base[f.key] || ''} inputMode="decimal"
                  onChange={(e) => setBase({ ...base, [f.key]: e.target.value })}
                  style={{
                    width: '100%', marginTop: 4, padding: '6px 8px',
                    border: '1px solid #d1d5db', borderRadius: 6, fontSize: 14,
                  }} />
              </label>
            ))}
          </div>

          <h4 style={{ margin: '0 0 8px', fontSize: 15 }}>가정</h4>
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
            gap: 10, marginBottom: 16,
          }}>
            {DRIVERS.map((d) => (
              <label key={d.key} style={{ fontSize: 13 }}>
                {d.label} <span style={{ color: '#6b7280' }}>({d.unit})</span>
                <input value={drivers[d.key] || ''} inputMode="decimal" placeholder="0"
                  onChange={(e) => setDrivers({ ...drivers, [d.key]: e.target.value })}
                  style={{
                    width: '100%', marginTop: 4, padding: '6px 8px',
                    border: '1px solid #d1d5db', borderRadius: 6, fontSize: 14,
                  }} />
                <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>{d.hint}</div>
              </label>
            ))}
          </div>

          <button onClick={run} disabled={busy} style={{
            padding: '9px 20px', border: '1px solid #2563eb', background: '#2563eb',
            color: '#fff', borderRadius: 6, cursor: busy ? 'default' : 'pointer', fontSize: 14,
          }}>{busy ? '계산 중…' : '시뮬레이션 실행'}</button>

          {error && (
            <div style={{
              marginTop: 12, padding: '10px 12px', background: '#fef2f2',
              border: '1px solid #fca5a5', borderRadius: 6, fontSize: 14, color: '#991b1b',
            }}>{error}</div>
          )}

          {result && (
            <div style={{ marginTop: 20 }}>
              {/* ★★★ 성격 표시를 결과 **바로 위**에 둔다 — 빠지면 이 숫자가 실적으로 읽힌다. */}
              <div style={{
                padding: '8px 12px', background: '#fef3c7', border: '1px solid #fcd34d',
                borderRadius: 6, fontSize: 13, marginBottom: 10,
              }}>
                {result.baseline?.display_label || '성격을 알 수 없는 기준선입니다'}
                <span style={{ color: '#6b7280', marginLeft: 8 }}>
                  기준시점 {result.baseline?.as_of?.slice(0, 16).replace('T', ' ') || '없음'}
                </span>
              </div>

              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid #d1d5db', textAlign: 'left' }}>
                    <th style={{ padding: 8, fontSize: 13 }}>결과</th>
                    <th style={{ padding: 8, fontSize: 13, textAlign: 'right' }}>기준</th>
                    <th style={{ padding: 8, fontSize: 13, textAlign: 'right' }}>시나리오</th>
                    <th style={{ padding: 8, fontSize: 13, textAlign: 'right' }}>변화</th>
                  </tr>
                </thead>
                <tbody>
                  {(result.compare || []).map((r: any) => (
                    <tr key={r.key} style={{ borderBottom: '1px solid #e5e7eb' }}>
                      <td style={{ padding: 8, fontSize: 14 }}>
                        {r.label} <span style={{ color: '#6b7280', fontSize: 12 }}>{r.unit}</span>
                      </td>
                      <td style={{ padding: 8, fontSize: 14, textAlign: 'right' }}>
                        {r.base.toLocaleString()}
                      </td>
                      <td style={{ padding: 8, fontSize: 14, textAlign: 'right' }}>
                        {r.scenario.toLocaleString()}
                      </td>
                      <td style={{
                        padding: 8, fontSize: 14, textAlign: 'right',
                        color: r.delta < 0 ? '#b91c1c' : r.delta > 0 ? '#15803d' : '#6b7280',
                      }}>
                        {r.delta > 0 ? '+' : ''}{r.delta.toLocaleString()}
                        {/* ★ 비율은 값 **옆에** 작게 — 비율만 크게 두면 작은 기준값에서
                            실제 규모보다 크게 읽힌다. 기준이 0이면 비율은 없다. */}
                        <span style={{ color: '#6b7280', fontSize: 12, marginLeft: 6 }}>
                          {r.delta_pct === null ? '비율 없음' : `${r.delta_pct > 0 ? '+' : ''}${r.delta_pct}%`}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div style={{ fontSize: 12, color: '#6b7280', marginTop: 10 }}>
                {/* ★★★ 계보를 화면에 남긴다 — 「이 숫자는 무엇으로 만들었나」에
                    다음 회의에서 답할 수 있어야 한다. */}
                산식 {result.scenario?.calc_version} · 기준선 지문{' '}
                {String(result.baseline?.fingerprint || '').slice(0, 12)} · 결과 지문{' '}
                {String(result.scenario?.fingerprint || '').slice(0, 12)}
              </div>
            </div>
          )}
        </Panel>
      </div>
    </HubDialog>
  );
}
