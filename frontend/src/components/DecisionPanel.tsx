import { useEffect, useState } from 'react';

import { HubDialog } from '../design/HubDialog';
import { Panel } from '../design/HubShell';
import { createDecision, DataPrepError, getImpactPath } from '../lib/dataPrepApi';
import { BASE_FIELDS, DRIVER_FIELDS, num } from '../lib/calcFields';
import { BaselinePicker, type BaselineChoice } from './BaselinePicker';
import { BaseValueFields } from './BaseValueFields';

// [Wave G 11.4 / Wave H] 의사결정 안건 — 파일럿 동선 9·12칸.
//
// 시뮬레이션 결과 하나가 회의 안건이 되려면 세 가지가 더 필요하다:
//   ① 3관점 검토서  ② 실행 책임자와 기한  ③ 근거의 계보
//
// ⚠️ 이 화면이 지켜야 할 것 셋
//   ① **책임자·기한 없이 만들 수 없다.** 서버가 거부하지만, 화면이 **먼저** 말한다 —
//      누르고 나서 막히면 사용자는 「고장」으로 읽는다.
//   ② **관점마다 다른 숫자를 만들지 않는다.** 서버가 준 같은 표를 순서만 바꿔 보여
//      준다. 관점별로 값이 다르면 회의에서 「어느 게 맞습니까」가 나온다.
//   ③ **근거 없는 단계를 숨기지 않는다.** 숨기면 그 보고가 «전부 설명된 것» 으로 읽힌다.

const CHAIN = [
  { key: 'material', label: '원료' },
  { key: 'purchase_order', label: '구매주문' },
  { key: 'shipment', label: '선적·통관' },
  { key: 'arrival', label: '입고·재고' },
  { key: 'production_plan', label: '생산계획' },
  { key: 'product', label: '제품' },
  { key: 'cash_pl', label: '현금·손익' },
];



function ImpactPath({ from, to, pick }: {
  from: string; to: string; pick: BaselineChoice;
}) {
  const [data, setData] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setErr(null);
    getImpactPath(from, to, pick.instanceId, pick.snapshotIds)
      .then((d) => { if (alive) setData(d); })
      .catch((e: unknown) => {
        if (alive) setErr((e as DataPrepError)?.message || '경로를 읽지 못했습니다.');
      });
    return () => { alive = false; };
    //: ⚠️ 고른 판이 바뀌면 다시 잇는다 — 안 그러면 위쪽 경고와 아래쪽 안건이
    //:   서로 다른 기준선을 말한다.
  }, [from, to, pick.instanceId, pick.snapshotIds.join(',')]);

  if (err) return <div style={{ fontSize: 13, color: '#b91c1c' }}>{err}</div>;
  if (!data) return <div style={{ fontSize: 13, color: '#6b7280' }}>경로 확인 중…</div>;

  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
        {(data.path || []).map((n: any, i: number) => (
          <span key={n.key} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {i > 0 && <span style={{ color: '#9ca3af' }}>→</span>}
            <span style={{
              padding: '4px 10px', borderRadius: 14, fontSize: 13,
              // ★ 근거가 있는 칸과 없는 칸을 **색만이 아니라 기호로도** 나눈다.
              background: n.snapshot_id ? '#ecfdf5' : '#fef3c7',
              border: `1px solid ${n.snapshot_id ? '#6ee7b7' : '#fcd34d'}`,
            }}>
              {n.snapshot_id ? '●' : '○'} {n.label}
            </span>
          </span>
        ))}
      </div>
      {/* ★★★ 「아직 안 봤다」와 「근거가 없다」를 **다르게** 말한다.
          섞으면 고르지도 않은 사용자에게 「근거가 없다」고 말하게 되고, 같은 화면
          아래의 안건은 그 판을 근거로 쓴다 — 한 화면에 두 답이 뜬다. */}
      {!data.evidence_checked ? (
        <div style={{ fontSize: 12, color: '#6b7280', marginTop: 6 }}>
          아래에서 기준선을 고르면 각 단계가 어느 데이터 판에 서 있는지 표시합니다.
        </div>
      ) : (data.missing_steps || []).length > 0 ? (
        <div style={{ fontSize: 12, color: '#b45309', marginTop: 6 }}>
          {/* ★ 계약키가 아니라 **사람이 읽는 단계 이름**으로 말한다(설계 §12). */}
          ⚠️ 아직 근거가 없는 단계:{' '}
          {data.missing_steps.map((s: any) => s.label).join(' · ')} — 이 경로는 아직 다
          설명되지 않습니다.
        </div>
      ) : (
        <div style={{ fontSize: 12, color: '#15803d', marginTop: 6 }}>
          이 경로의 모든 단계가 고른 기준선 위에 서 있습니다.
        </div>
      )}
    </div>
  );
}

export function DecisionPanel({ onClose }: { onClose: () => void }) {
  const [form, setForm] = useState({
    title: '', owner: '', due: '', from: 'purchase_order', to: 'cash_pl',
  });
  //: * id 를 타이핑하게 하지 않는다 — 고르개가 목록에서 집어 준다.
  const [pick, setPick] = useState<BaselineChoice>({ instanceId: '', snapshotIds: [] });
  //: ★★★ 기준값을 **이름으로** 받는다. 순서로 받으면 한 칸 밀려도 오류가 나지 않고,
  //:   「기말현금」 자리의 「영업이익」이 그럴듯한 표가 되어 회의에 올라간다.
  const [base, setBase] = useState<Record<string, string>>({});
  const [drivers, setDrivers] = useState<Record<string, string>>({});
  const [pkg, setPkg] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // ★ 서버가 막을 자리를 **누르기 전에** 말한다.
  const blocked = !form.title.trim() ? '안건 제목이 필요합니다.'
    : !form.owner.trim() ? '실행 책임자가 필요합니다 — 없는 안건은 「검토하겠습니다」로 끝납니다.'
      : !form.due.trim() ? '기한이 필요합니다 — 기한 없는 결정은 결정이 아닙니다.'
      : !pick.instanceId || pick.snapshotIds.length === 0
        ? '기준선으로 쓸 업무키트와 인증된 데이터 판을 고르십시오.'
        : BASE_FIELDS.some((f) => num(base[f.key] || '') === null)
          ? '기준값을 모두 채워 주십시오 — 빈 칸을 0으로 채우면 결과가 완성돼 보입니다.'
          : '';

  async function run() {
    setError(null);
    setPkg(null);
    const baseValues: Record<string, number> = {};
    for (const f of BASE_FIELDS) {
      const n = num(base[f.key] || '');
      if (n === null) {
        // ⚠️ 빈 값을 0으로 채우지 않는다 — 그러면 결과가 완성돼 보인다.
        setError(`기준값 «${f.label}» 이 비었습니다 — 빈 칸을 0으로 채우지 않습니다.`);
        return;
      }
      baseValues[f.key] = n;
    }
    const assumptions: Record<string, number> = {};
    for (const d of DRIVER_FIELDS) {
      const n = num(drivers[d.key] || '');
      if (n !== null) assumptions[d.key] = n;
    }

    setBusy(true);
    try {
      setPkg(await createDecision({
        instance_id: pick.instanceId,
        snapshot_ids: pick.snapshotIds,
        base_values: baseValues, assumptions,
        title: form.title.trim(), owner: form.owner.trim(), due: form.due.trim(),
        path_from: form.from, path_to: form.to,
      }));
    } catch (e) {
      setError((e as DataPrepError)?.message || '안건을 만들지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  const field = (k: keyof typeof form, ph: string, flex = 1) => (
    <input value={form[k]} placeholder={ph}
      onChange={(e) => setForm({ ...form, [k]: e.target.value })}
      style={{ flex, padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 14 }} />
  );

  return (
    <HubDialog label="의사결정 안건 — 3관점 검토서와 경영 브리핑" onClose={onClose}>
      <div className="afs-dialog-bar">
        <b>의사결정 안건</b>
        <span>숫자에서 «누가 무엇을 언제» 까지 — 근거의 계보를 함께 남깁니다</span>
        <div className="bar-actions">
          {busy && <span className="busy">만드는 중…</span>}
          <button onClick={onClose}>닫기</button>
        </div>
      </div>

      <div className="afs-dialog-body" style={{
        overflow: 'auto', padding: 18, display: 'flex', flexDirection: 'column',
      }}>
        <Panel className="afs-fill">
          <h4 style={{ margin: '0 0 8px', fontSize: 15 }}>영향 경로</h4>
          <ImpactPath from={form.from} to={form.to} pick={pick} />
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            {(['from', 'to'] as const).map((side) => (
              <label key={side} style={{ fontSize: 13 }}>
                {side === 'from' ? '시작' : '끝'}
                <select value={form[side]}
                  onChange={(e) => setForm({ ...form, [side]: e.target.value })}
                  style={{
                    display: 'block', marginTop: 4, padding: '6px 8px',
                    border: '1px solid #d1d5db', borderRadius: 6, fontSize: 14,
                  }}>
                  {CHAIN.map((n) => <option key={n.key} value={n.key}>{n.label}</option>)}
                </select>
              </label>
            ))}
          </div>

          <h4 style={{ margin: '0 0 8px', fontSize: 15 }}>안건</h4>
          <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
            {field('title', '안건 제목', 2)}
            {field('owner', '실행 책임자')}
            {field('due', '기한 (예: 2026-08-30)')}
          </div>
          <BaselinePicker value={pick} onChange={setPick} />

          <BaseValueFields pick={pick} values={base} onChange={setBase} />

          <h4 style={{ margin: '12px 0 8px', fontSize: 15 }}>가정</h4>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            {DRIVER_FIELDS.map((d) => (
              <label key={d.key} style={{ flex: 1, fontSize: 13, color: '#374151' }}>
                {d.label} <span style={{ color: '#6b7280' }}>({d.unit})</span>
                <input value={drivers[d.key] || ''} inputMode="decimal" placeholder="0"
                  onChange={(e) => setDrivers({ ...drivers, [d.key]: e.target.value })}
                  style={{
                    display: 'block', width: '100%', marginTop: 4, padding: '8px 10px',
                    border: '1px solid #d1d5db', borderRadius: 6, fontSize: 14,
                  }} />
                {/* * 이 숫자가 무엇을 움직이는지 옆에 적는다. */}
                <span style={{ fontSize: 12, color: '#6b7280' }}>{d.hint}</span>
              </label>
            ))}
          </div>

          {/* ★★★ 막힌 이유를 **누르기 전에** 말한다. */}
          {blocked && (
            <div style={{ fontSize: 13, color: '#b45309', marginBottom: 8 }}>{blocked}</div>
          )}
          <button onClick={run} disabled={busy || !!blocked} style={{
            padding: '9px 20px', borderRadius: 6, fontSize: 14,
            border: `1px solid ${blocked ? '#d1d5db' : '#2563eb'}`,
            background: blocked ? '#f3f4f6' : '#2563eb',
            color: blocked ? '#9ca3af' : '#fff',
            cursor: busy || blocked ? 'default' : 'pointer',
          }}>{busy ? '만드는 중…' : '안건 만들기'}</button>

          {error && (
            <div style={{
              marginTop: 12, padding: '10px 12px', background: '#fef2f2',
              border: '1px solid #fca5a5', borderRadius: 6, fontSize: 14, color: '#991b1b',
            }}>{error}</div>
          )}

          {pkg && (
            <div style={{ marginTop: 20 }}>
              <div style={{
                padding: '8px 12px', background: '#fef3c7', border: '1px solid #fcd34d',
                borderRadius: 6, fontSize: 13, marginBottom: 12,
              }}>{pkg.display_label}</div>

              <h4 style={{ margin: '0 0 4px', fontSize: 16 }}>{pkg.title}</h4>
              <div style={{ fontSize: 14, marginBottom: 12 }}>{pkg.question}</div>
              <div style={{ fontSize: 13, color: '#374151', marginBottom: 16 }}>
                실행 책임자 <strong>{pkg.owner}</strong> · 기한 <strong>{pkg.due}</strong>
              </div>

              {/* ★★★ 3관점 — 같은 표를 **순서만 바꿔** 보여 준다. */}
              {(pkg.views || []).map((v: any) => (
                <div key={v.view} style={{ marginBottom: 14 }}>
                  <div style={{ fontSize: 14, fontWeight: 600 }}>{v.view}</div>
                  <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>
                    {v.question}
                  </div>
                  <ul style={{ paddingLeft: 18, margin: 0 }}>
                    {(v.highlights || []).map((r: any) => (
                      <li key={r.key} style={{ fontSize: 14 }}>
                        {r.label}: {r.base.toLocaleString()} → {r.scenario.toLocaleString()}
                        {r.unit}
                        <span style={{
                          marginLeft: 8,
                          color: r.delta < 0 ? '#b91c1c' : r.delta > 0 ? '#15803d' : '#6b7280',
                        }}>
                          {r.delta > 0 ? '+' : ''}{r.delta.toLocaleString()}
                          {r.delta_pct !== null && ` (${r.delta_pct > 0 ? '+' : ''}${r.delta_pct}%)`}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}

              <h4 style={{ margin: '16px 0 6px', fontSize: 15 }}>경영 브리핑</h4>
              <pre style={{
                background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 6,
                padding: 12, fontSize: 13, whiteSpace: 'pre-wrap', margin: 0,
                fontFamily: 'inherit',
              }}>{(pkg.briefing || []).join('\n')}</pre>

              <div style={{ fontSize: 12, color: '#6b7280', marginTop: 10 }}>
                근거: 기준선 {String(pkg.evidence?.baseline_fingerprint || '').slice(0, 12)}
                {' · '}산식 {pkg.evidence?.calc_version}
                {' · '}판 {(pkg.evidence?.snapshot_ids || []).length}개
                {' · '}기준시점 {pkg.evidence?.as_of || '없음'}
              </div>
            </div>
          )}
        </Panel>
      </div>
    </HubDialog>
  );
}
