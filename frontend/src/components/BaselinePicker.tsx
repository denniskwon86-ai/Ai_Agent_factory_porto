import { useEffect, useState } from 'react';

import {
  DataPrepError, listInstances, listSnapshots,
} from '../lib/dataPrepApi';

// [Wave H / H-2] 기준선 고르개 — 시나리오·의사결정 두 화면이 **같은 부품**을 쓴다.
//
// ★★★ 왜 부품으로 뽑았나
//   두 화면 모두 사용자에게 `ki_…` 와 `ds_…` 를 **타이핑하라**고 요구하고 있었다.
//   그 id 는 화면 어디에도 없다 — 다른 화면을 열어 눈으로 옮겨 적어야 했다.
//   기능은 도는데 사람이 시작할 수 없으면 그것은 도는 것이 아니다.
//
// ⚠️ 이 화면이 지켜야 할 것 셋
//   ① **인증된 판만 고를 수 있다.** 인증 전 판을 기준선에 넣으면 그 숫자는 검사받지
//      않은 데이터 위에 서고, 화면은 그것을 말해 주지 않는다. 서버도 막지만 **누르기
//      전에** 말한다.
//   ② **못 읽음과 0건을 구분한다.** 실패를 빈 목록으로 그리면 사용자는 원인을
//      데이터에서 찾는다.
//   ③ **고른 것을 «최신으로 알아서» 로 바꾸지 않는다.** 고른 id 집합이 그대로
//      기준선이 된다 — 그래야 다음 주에 같은 답이 나온다.

//: 인증된 판만 기준선에 들어간다. ★ 서버(`core.data_preparation.models`)의
//:   `DEMO_CERTIFIED` · `CERTIFIED` 와 같아야 한다.
const CERTIFIED = new Set(['DEMO_CERTIFIED', 'CERTIFIED']);

export type BaselineChoice = { instanceId: string; snapshotIds: string[] };

export function BaselinePicker({ value, onChange }: {
  value: BaselineChoice;
  onChange: (next: BaselineChoice) => void;
}) {
  //: `null` = 아직 못 읽음, `[]` = 정말 0건.
  const [instances, setInstances] = useState<any[] | null>(null);
  const [snapshots, setSnapshots] = useState<any[] | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);

  useEffect(() => {
    listInstances()
      .then((d) => setInstances(d.instances || []))
      .catch((e: unknown) => {
        setInstances(null);
        setLoadErr((e as DataPrepError)?.message || '');
      });
  }, []);

  useEffect(() => {
    if (!value.instanceId) { setSnapshots(null); return; }
    let live = true;
    listSnapshots(value.instanceId)
      .then((d) => { if (live) setSnapshots(d.snapshots || []); })
      .catch(() => { if (live) setSnapshots(null); });
    return () => { live = false; };
  }, [value.instanceId]);

  function pickInstance(id: string) {
    //: ⚠️ 인스턴스를 바꾸면 고른 판을 **비운다** — 남겨 두면 남의 인스턴스 판 id 가
    //:   섞인 채 요청이 나가고, 서버는 404 로 막지만 사용자는 이유를 모른다.
    onChange({ instanceId: id, snapshotIds: [] });
  }

  function toggle(sid: string) {
    const has = value.snapshotIds.includes(sid);
    onChange({
      instanceId: value.instanceId,
      snapshotIds: has ? value.snapshotIds.filter((x) => x !== sid)
        : [...value.snapshotIds, sid],
    });
  }

  const certified = (snapshots || []).filter((s) => CERTIFIED.has(String(s.state)));
  const uncertified = (snapshots || []).filter((s) => !CERTIFIED.has(String(s.state)));

  return (
    <div style={{ marginBottom: 12 }}>
      <h4 style={{ margin: '0 0 8px', fontSize: 15 }}>기준선</h4>

      {/* ── ① 인스턴스 ─────────────────────────────────────────────── */}
      {instances === null ? (
        <div style={{ fontSize: 13, color: 'var(--state-warn-fg)', marginBottom: 8 }}>
          업무키트 목록을 지금 확인하지 못했습니다{loadErr ? ` — ${loadErr}` : ''}.
          {' '}데이터가 없는 것이 아니라 지금 읽지 못한 상태입니다.
        </div>
      ) : instances.length === 0 ? (
        <div style={{ fontSize: 13, color: 'var(--surface-text-muted)', marginBottom: 8 }}>
          이 조직 범위에 적용된 업무키트가 아직 없습니다 — 「업무 데이터 준비」에서
          먼저 키트를 적용하십시오.
        </div>
      ) : (
        <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 10px' }}>
          {instances.map((it: any) => {
            const on = it.instance_id === value.instanceId;
            return (
              <li key={it.instance_id} style={{ marginBottom: 6 }}>
                <button onClick={() => pickInstance(it.instance_id)} style={{
                  display: 'flex', alignItems: 'center', gap: 10, width: '100%',
                  textAlign: 'left', padding: '9px 12px', fontFamily: 'inherit',
                  border: `1px solid ${on ? 'var(--action-primary-bg)' : 'var(--surface-border)'}`, borderRadius: 6,
                  background: on ? 'var(--state-info-bg)' : '#fff', cursor: 'pointer', fontSize: 14,
                  color: 'inherit',
                }}>
                  {/* ★ 색만으로 «고름» 을 나타내지 않는다(설계 §12) — 기호를 함께 둔다. */}
                  <span aria-hidden>{on ? '◉' : '○'}</span>
                  <span style={{ flex: 1 }}>
                    <strong>{it.label || it.kit_id}</strong>
                    <span style={{ color: 'var(--surface-text-muted)', marginLeft: 8, fontSize: 12 }}>
                      {it.scope_node_id} · {it.entity_mode}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {/* ── ② 판 ──────────────────────────────────────────────────── */}
      {value.instanceId && (snapshots === null ? (
        <div style={{ fontSize: 13, color: 'var(--state-warn-fg)' }}>
          데이터 판 목록을 지금 확인하지 못했습니다.
        </div>
      ) : certified.length === 0 ? (
        <div style={{ fontSize: 13, color: 'var(--state-warn-fg)' }}>
          인증된 데이터 판이 없습니다 — 인증되지 않은 판으로는 기준선을 만들 수
          없습니다{uncertified.length
            ? ` (검사·인증 대기 ${uncertified.length}건은 「업무 데이터 준비」에서 진행합니다)`
            : ''}.
        </div>
      ) : (
        <>
          <div style={{ fontSize: 13, color: 'var(--surface-text-muted)', marginBottom: 6 }}>
            기준선에 넣을 판을 고르십시오. 고른 집합이 그대로 고정됩니다 —
            「최신으로 알아서」는 다음 주에 다른 숫자를 냅니다.
          </div>
          <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 6px' }}>
            {certified.map((s: any) => (
              <li key={s.snapshot_id} style={{ marginBottom: 4 }}>
                <label style={{
                  display: 'flex', alignItems: 'center', gap: 8, padding: '7px 10px',
                  border: '1px solid var(--surface-border)', borderRadius: 6, fontSize: 14,
                  cursor: 'pointer',
                }}>
                  <input type="checkbox"
                    checked={value.snapshotIds.includes(s.snapshot_id)}
                    onChange={() => toggle(s.snapshot_id)} />
                  <span style={{ flex: 1 }}>
                    {/* ★ 사람이 읽는 이름이 먼저다(설계 §12). 이름이 없을 때만
                        계약키를 그대로 쓴다. */}
                    {s.label || s.dataset_contract_key}
                    <span style={{ color: 'var(--surface-text-muted)', marginLeft: 8, fontSize: 12 }}>
                      {s.row_count}행 · {String(s.certified_at || '').slice(0, 16).replace('T', ' ')}
                    </span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
          {/* ⚠️ 인증 안 된 판이 있으면 «없는 셈» 치지 않고 그 사실을 말한다. */}
          {uncertified.length > 0 && (
            <div style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>
              인증되지 않은 판 {uncertified.length}건은 여기에 나오지 않습니다.
            </div>
          )}
        </>
      ))}
    </div>
  );
}
