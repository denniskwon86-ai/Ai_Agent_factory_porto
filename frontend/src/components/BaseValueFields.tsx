import { useState } from 'react';

import { BASE_FIELDS } from '../lib/calcFields';
import { DataPrepError, deriveBaseValues } from '../lib/dataPrepApi';
import type { BaselineChoice } from './BaselinePicker';

// [H-3] 기준값 입력 — 시나리오·의사결정 두 화면이 **같은 부품**을 쓴다.
//
// ★★★ 왜 「고른 판에서 채우기」가 있나
//   이 화면들은 기준값 7개를 전부 사람에게 받고 있었다. 그런데 그중 셋(생산량 ·
//   구매지급 · 기간)은 이미 올려서 인증까지 마친 판 안에 있다. 있는 것을 다시 묻는
//   화면은 「데이터를 올리면 숫자가 나온다」는 이 제품의 약속을 지키지 않는다.
//
// ⚠️ 이 부품이 지켜야 할 것 셋
//   ① **유도한 값과 사람이 넣은 값을 구분해 보여 준다.** 섞으면 「이 숫자는 어디서
//      왔나」에 답할 수 없고, 회의에서 그 질문이 나오면 자료 전체가 흔들린다.
//   ② **못 뽑은 칸을 0으로 채우지 않는다.** 대신 왜 못 뽑았는지를 그 칸 옆에 적는다.
//   ③ **사람이 고친 값을 «유도됨» 으로 계속 표시하지 않는다.** 손대는 순간 그것은
//      사람의 값이다.

export function BaseValueFields({ pick, values, onChange }: {
  pick: BaselineChoice;
  values: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
}) {
  //: 키 → 유도 사유·출처. `null` = 아직 뽑아 본 적 없음.
  const [meta, setMeta] = useState<Record<string, { source: string; reason: string }> | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const ready = !!pick.instanceId && pick.snapshotIds.length > 0;

  async function fill() {
    setErr(null);
    setBusy(true);
    try {
      const d = await deriveBaseValues(pick.instanceId, pick.snapshotIds);
      const next = { ...values };
      const m: Record<string, { source: string; reason: string }> = {};
      for (const f of d.fields) {
        m[f.key] = { source: f.source, reason: f.reason };
        //: ⚠️ `null` 을 '0' 으로 쓰지 않는다 — 그러면 「못 뽑았다」가 「0이다」가 된다.
        if (f.value !== null && f.value !== undefined) next[f.key] = String(f.value);
      }
      setMeta(m);
      onChange(next);
    } catch (e) {
      setErr((e as DataPrepError)?.message || '기준값을 뽑지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  function edit(key: string, v: string) {
    //: ③ 손댄 칸은 더 이상 «유도됨» 이 아니다.
    if (meta?.[key]?.source === 'DERIVED') {
      setMeta({ ...meta, [key]: { source: 'MANUAL', reason: '직접 넣은 값입니다.' } });
    }
    onChange({ ...values, [key]: v });
  }

  return (
    <>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10, margin: '12px 0 8px',
      }}>
        <h4 style={{ margin: 0, fontSize: 15 }}>기준값</h4>
        <button onClick={fill} disabled={!ready || busy} style={{
          padding: '5px 12px', fontSize: 13, borderRadius: 6, fontFamily: 'inherit',
          border: `1px solid ${ready ? '#2563eb' : '#d1d5db'}`,
          background: '#fff', color: ready ? '#2563eb' : '#9ca3af',
          cursor: ready && !busy ? 'pointer' : 'default',
        }}>{busy ? '뽑는 중…' : '고른 판에서 채우기'}</button>
        {!ready && (
          <span style={{ fontSize: 12, color: '#6b7280' }}>
            먼저 기준선을 고르면 뽑을 수 있는 값을 채워 드립니다.
          </span>
        )}
      </div>

      {err && (
        <div style={{ fontSize: 13, color: '#b91c1c', marginBottom: 8 }}>{err}</div>
      )}
      {meta && (
        <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 8 }}>
          {/* ★ 「몇 칸을 아직 사람이 채워야 하는가」가 이 줄의 핵심이다. */}
          인증된 판에서 뽑을 수 있는 값만 채웠습니다 — 나머지는 회사 실적에서 직접
          넣어 주십시오. 없는 값을 0으로 채우지 않습니다.
        </div>
      )}

      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))',
        gap: 10, marginBottom: 12,
      }}>
        {BASE_FIELDS.map((f) => {
          const m = meta?.[f.key];
          const derived = m?.source === 'DERIVED';
          return (
            <label key={f.key} style={{ fontSize: 13, color: '#374151' }}>
              {f.label} <span style={{ color: '#6b7280' }}>({f.unit})</span>
              {/* ★ 색만으로 «유도됨» 을 나타내지 않는다(설계 §12) — 글자로도 적는다. */}
              {derived && (
                <span style={{ color: '#15803d', marginLeft: 6, fontSize: 12 }}>
                  · 판에서 뽑음
                </span>
              )}
              <input value={values[f.key] || ''} inputMode="decimal"
                onChange={(e) => edit(f.key, e.target.value)}
                style={{
                  display: 'block', width: '100%', marginTop: 4, padding: '8px 10px',
                  border: `1px solid ${derived ? '#6ee7b7' : '#d1d5db'}`,
                  borderRadius: 6, fontSize: 14,
                  background: derived ? '#f0fdf4' : '#fff',
                }} />
              {/* ⚠️ 못 뽑은 이유를 그 칸 옆에 둔다 — 화면 아래 한 줄로 몰면 안 읽힌다. */}
              {m && !derived && m.reason && (
                <span style={{ fontSize: 12, color: '#6b7280' }}>{m.reason}</span>
              )}
            </label>
          );
        })}
      </div>
    </>
  );
}
