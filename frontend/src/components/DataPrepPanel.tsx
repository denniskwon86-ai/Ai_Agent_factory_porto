import { useEffect, useState } from 'react';

// ★★★ 손수 모달을 만들지 않는다 — 승인된 제품 셸을 쓴다(설계 §12 UI 규칙).
//   `HubDialog` 가 dialog semantics · 배경 inert · 포커스 트랩 · Escape 를 준다.
import { HubDialog } from '../design/HubDialog';
import { Panel } from '../design/HubShell';
import { DataReadinessBoard } from './DataReadinessBoard';
import {
  certifySnapshot, DataPrepError, getInstance, listInstances, listKits,
  listSnapshots, uploadSnapshot,
} from '../lib/dataPrepApi';

// [BDR-2·3·5 / Wave H] 업무 데이터 준비 패널.
//
// 파일럿 동선의 2~4칸을 한 화면에서 끝낸다:
//   업무키트 확인 → 원천 결속 상태 → 파일 등록 → 준비 상태 확인
//
// ⚠️ 이 화면이 지켜야 할 것 셋
//   ① **조회 실패와 0건을 구분한다.** 실패를 빈 목록으로 그리면 사용자는 「데이터가
//      없다」로 읽고 원인을 데이터에서 찾는다.
//   ② **기술 ID 를 앞세우지 않는다**(설계 §12 UI 규칙). 사람이 읽는 이름이 먼저다.
//   ③ **파일 등록 실패의 사유를 그대로 보여 준다.** 「올라가지 않는다」만 남으면
//      사용자는 파일이 아니라 시스템을 의심한다.

function Err({ error }: { error: { message: string; status: number } }) {
  return (
    <div style={{
      padding: 12, border: '1px solid #fca5a5', borderRadius: 6,
      background: '#fef2f2', fontSize: 14,
    }}>
      <strong style={{ color: '#b91c1c' }}>불러오지 못했습니다</strong>
      <div style={{ marginTop: 4 }}>{error.message}</div>
      <div style={{ marginTop: 4, fontSize: 13, color: '#6b7280' }}>
        {/* ⚠️ 「없음」과 「지금 못 읽음」은 사용자가 할 일이 다르다. */}
        {error.status === 404
          ? '찾을 수 없습니다 — 조직 범위를 확인해 주십시오.'
          : '데이터가 없는 것이 아니라 지금 확인하지 못한 상태입니다.'}
      </div>
    </div>
  );
}

export function DataPrepPanel({ onClose }: { onClose: () => void }) {
  const [kits, setKits] = useState<any[] | null>(null);
  const [error, setError] = useState<{ message: string; status: number } | null>(null);
  const [instanceId, setInstanceId] = useState('');
  //: `null` = 아직 못 읽음, `[]` = 정말 0건. ⚠️ 둘을 같은 화면으로 그리면 사용자가
  //:   원인을 데이터에서 찾는다.
  const [instances, setInstances] = useState<any[] | null>(null);
  const [instance, setInstance] = useState<any | null>(null);
  const [snapshots, setSnapshots] = useState<any[]>([]);
  const [busy, setBusy] = useState('');
  //: 계약 이름 → 사람이 읽는 이름. ⚠️ 화면이 제 나름의 번역표를 만들지 않는다 —
  //:   서버가 계약과 함께 준 것만 쓴다(없으면 계약 이름 그대로).
  const labelOf = (key: string) =>
    (instance?.required_datasets || []).find(
      (d: any) => d.dataset_contract_key === key)?.label || key;
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    listKits()
      .then((d) => setKits(d.kits || []))
      .catch((e: unknown) => {
        const err = e as DataPrepError;
        setError({ message: err?.message || '', status: err?.status || 0 });
      });
    //: ⚠️ 목록 실패가 키트 화면까지 막지 않는다 — 실패는 목록 자리에만 남긴다.
    listInstances()
      .then((d) => setInstances(d.instances || []))
      .catch(() => setInstances(null));
  }, []);

  async function openInstance(id: string) {
    setInstanceId(id);
    setInstance(null);
    setSnapshots([]);
    setNotice(null);
    if (!id.trim()) return;
    try {
      setInstance(await getInstance(id.trim()));
      setSnapshots((await listSnapshots(id.trim())).snapshots || []);
    } catch (e) {
      const err = e as DataPrepError;
      setNotice({ ok: false, text: err?.message || '인스턴스를 열지 못했습니다.' });
    }
  }

  async function onCertify(snapshotId: string, rowCount: number) {
    setBusy(snapshotId);
    setNotice(null);
    try {
      // ⚠️ 원천 합계를 모르면 **행 수만이라도** 대사한다. 아무것도 안 주면 대사가
      //   «건너뛴 것» 이 되고, 잘린 파일이 그대로 인증된다.
      const out = await certifySnapshot(snapshotId, { row_count: rowCount });
      setNotice(out.state === 'DEMO_CERTIFIED'
        ? { ok: true, text: `인증됨 — ${out.display_label}` }
        // ★ 격리도 «실패» 가 아니라 **결과**다. 사유를 그대로 옮긴다.
        : { ok: false, text: `${out.state}: ${out.quarantine?.reason || '검사에서 멈췄습니다'}` });
      setSnapshots((await listSnapshots(instanceId)).snapshots || []);
    } catch (e) {
      const err = e as DataPrepError;
      setNotice({ ok: false, text: err?.message || '인증하지 못했습니다.' });
    } finally {
      setBusy('');
    }
  }

  async function onUpload(bindingId: string, file: File | null) {
    if (!file) return;
    setBusy(bindingId);
    setNotice(null);
    try {
      const snap = await uploadSnapshot(bindingId, file);
      setNotice({ ok: true, text: `${file.name} — ${snap.row_count}행 등록됨` });
      setSnapshots((await listSnapshots(instanceId)).snapshots || []);
    } catch (e) {
      // ★★★ 사유를 **그대로** 보여 준다. 「올라가지 않는다」만 남으면 사용자는
      //   파일이 아니라 시스템을 의심한다.
      const err = e as DataPrepError;
      setNotice({ ok: false, text: err?.message || '등록하지 못했습니다.' });
    } finally {
      setBusy('');
    }
  }

  return (
    <HubDialog label="업무 데이터 준비 — 업무키트·원천 결속·파일 판" onClose={onClose}>
      <div className="afs-dialog-bar">
        <b>업무 데이터 준비</b>
        <span>업무키트를 조직에 적용하고 · 원천을 연결하고 · 파일 판을 인증합니다</span>
        <div className="bar-actions">
          <button onClick={onClose}>닫기</button>
        </div>
      </div>

      {/* ★★★ `.afs-dialog-body` 가 셸의 배경·여백 규약이다. 이걸 빼고 손수
          `padding` 만 주면 **배경이 없어 뒤 화면이 그대로 비친다** — 감사 게이트는
          그것을 잡지 못하고 통과시킨다(실측). */}
      <div className="afs-dialog-body" style={{
        overflow: 'auto', padding: 18,
        // ⚠️ 카드가 내용 높이만큼만 차지하면 **아래가 텅 비고** 뒤 화면이 그 자리로
        //   비친다. 사용자는 그것을 「화면이 덜 그려졌다」로 읽는다.
        display: 'flex', flexDirection: 'column',
      }}>
        <Panel className="afs-fill">
          {error ? <Err error={error} /> : (
            <>
              <h4 style={{ margin: '0 0 8px', fontSize: 15 }}>등록된 업무 데이터 키트</h4>
              {kits === null ? (
                <div style={{ fontSize: 14, color: '#6b7280' }}>불러오는 중…</div>
              ) : kits.length === 0 ? (
                // ⚠️ 「0건」은 실패가 아니다 — 그 사실을 **그대로** 말한다.
                <div style={{ fontSize: 14, color: '#6b7280' }}>
                  등록된 키트가 없습니다. `docs/data-kits/` 에 키트 문서를 두면 여기 나타납니다.
                </div>
              ) : (
                <ul style={{ paddingLeft: 18, margin: '0 0 16px' }}>
                  {kits.map((k) => (
                    <li key={`${k.kit_id}@${k.version}`} style={{ fontSize: 14, marginBottom: 4 }}>
                      {/* ★ 사람이 읽는 이름이 먼저, 기술 ID 는 뒤에 작게. */}
                      <strong>{k.name || k.kit_id}</strong>
                      <span style={{ color: '#6b7280', marginLeft: 8, fontSize: 12 }}>
                        {k.kit_id} · v{k.version} · {k.mode}
                      </span>
                    </li>
                  ))}
                </ul>
              )}

              <h4 style={{ margin: '16px 0 8px', fontSize: 15 }}>키트 인스턴스 열기</h4>

              {/* ★★★ 먼저 «이미 있는 것» 을 보여 준다. id 를 외워 오라고 하지 않는다. */}
              {instances === null ? (
                <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 8 }}>
                  인스턴스 목록을 지금 확인하지 못했습니다 — 아래에 id 를 직접 넣어
                  열 수 있습니다.
                </div>
              ) : instances.length === 0 ? (
                <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 8 }}>
                  이 조직 범위에 적용된 업무키트가 아직 없습니다.
                </div>
              ) : (
                <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 12px' }}>
                  {instances.map((it: any) => (
                    <li key={it.instance_id} style={{ marginBottom: 6 }}>
                      {/* ★ 줄 전체가 하나의 누를 곳이다 — 이름 옆에 작은 «열기» 를
                          따로 두면 누를 곳이 이름과 어긋난다. */}
                      <button
                        onClick={() => { setInstanceId(it.instance_id);
                                         openInstance(it.instance_id); }}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 10, width: '100%',
                          textAlign: 'left', padding: '10px 12px',
                          border: '1px solid #e5e7eb', borderRadius: 6,
                          background: '#fff', cursor: 'pointer', fontSize: 14,
                          fontFamily: 'inherit', color: 'inherit',
                        }}>
                        <span style={{ flex: 1 }}>
                          {/* 사람이 읽는 이름이 먼저다(설계 §12). */}
                          <strong>{it.label || it.kit_id}</strong>
                          <span style={{ color: '#6b7280', marginLeft: 8, fontSize: 12 }}>
                            {it.scope_node_id} · {it.entity_mode} · {it.instance_id}
                          </span>
                        </span>
                        <span style={{ color: '#2563eb', fontSize: 13 }}>열기</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                <input
                  value={instanceId}
                  onChange={(e) => setInstanceId(e.target.value)}
                  placeholder="목록에 없는 인스턴스 id 를 직접 넣습니다(선택)"
                  style={{
                    flex: 1, padding: '8px 10px', border: '1px solid #d1d5db',
                    borderRadius: 6, fontSize: 14,
                  }} />
                <button onClick={() => openInstance(instanceId)} style={{
                  padding: '8px 16px', border: '1px solid #2563eb', background: '#2563eb',
                  color: '#fff', borderRadius: 6, cursor: 'pointer', fontSize: 14,
                }}>열기</button>
              </div>

              {notice && (
                <div style={{
                  padding: '8px 12px', borderRadius: 6, fontSize: 14, marginBottom: 12,
                  background: notice.ok ? '#ecfdf5' : '#fef2f2',
                  border: `1px solid ${notice.ok ? '#6ee7b7' : '#fca5a5'}`,
                  color: notice.ok ? '#065f46' : '#991b1b',
                }}>{notice.text}</div>
              )}

              {instance && (
                <>
                  <h4 style={{ margin: '16px 0 8px', fontSize: 15 }}>원천 결속과 파일 등록</h4>
                  {(instance.bindings || []).length === 0 ? (
                    <div style={{ fontSize: 14, color: '#6b7280' }}>
                      아직 원천이 연결되지 않았습니다.
                    </div>
                  ) : (
                    <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 16 }}>
                      <thead>
                        <tr style={{ borderBottom: '2px solid #d1d5db', textAlign: 'left' }}>
                          <th style={{ padding: 8, fontSize: 13 }}>업무 데이터</th>
                          <th style={{ padding: 8, fontSize: 13 }}>결속 상태</th>
                          <th style={{ padding: 8, fontSize: 13 }}>파일 등록</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(instance.bindings || []).map((b: any) => (
                          <tr key={b.binding_id} style={{ borderBottom: '1px solid #e5e7eb' }}>
                            <td style={{ padding: 8, fontSize: 14 }}>
                              {labelOf(b.dataset_contract_key)}
                              <div style={{ fontSize: 12, color: '#6b7280' }}>
                                {b.dataset_contract_key}
                              </div>
                            </td>
                            <td style={{ padding: 8, fontSize: 14 }}>
                              {b.state}
                              {b.blocked_reason && (
                                <div style={{ color: '#b91c1c', fontSize: 12 }}>
                                  {b.blocked_reason}
                                </div>
                              )}
                            </td>
                            <td style={{ padding: 8, fontSize: 13 }}>
                              {/* ⚠️ 활성 결속에만 올릴 수 있다 — 서버가 막기 전에 말한다. */}
                              {b.state === 'ACTIVE' ? (
                                <input type="file" accept=".csv"
                                  disabled={busy === b.binding_id}
                                  onChange={(e) => onUpload(b.binding_id,
                                    e.target.files?.[0] || null)} />
                              ) : (
                                <span style={{ color: '#6b7280' }}>
                                  결속을 활성화한 뒤 올릴 수 있습니다.
                                </span>
                              )}
                            </td>
                          </tr>
                        ))}
                        {/* ★★★ 계약이 요구하는데 **아직 연결되지 않은** 것도 한 줄로
                            남긴다. 연결된 것만 보이면 화면은 「다 됐다」처럼 보인다. */}
                        {(instance.required_datasets || [])
                          .filter((d: any) => !d.bound)
                          .map((d: any) => (
                            <tr key={d.dataset_contract_key}
                                style={{ borderBottom: '1px solid #e5e7eb' }}>
                              <td style={{ padding: 8, fontSize: 14 }}>
                                {d.label || d.dataset_contract_key}
                                <div style={{ fontSize: 12, color: '#6b7280' }}>
                                  {d.dataset_contract_key}
                                </div>
                              </td>
                              <td style={{ padding: 8, fontSize: 14, color: '#b45309' }}>
                                원천 미지정
                                <div style={{ fontSize: 12, color: '#6b7280' }}>
                                  이 데이터를 어디서 가져올지 아직 고르지 않았습니다.
                                </div>
                              </td>
                              <td style={{ padding: 8, fontSize: 13, color: '#6b7280' }}>
                                원천을 고른 뒤 올릴 수 있습니다.
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  )}

                  {snapshots.length > 0 && (
                    <>
                      <h4 style={{ margin: '16px 0 8px', fontSize: 15 }}>등록된 데이터 판</h4>
                      <ul style={{ paddingLeft: 18, margin: '0 0 16px' }}>
                        {snapshots.map((s) => (
                          <li key={s.snapshot_id} style={{ fontSize: 14, marginBottom: 8 }}>
                            {labelOf(s.dataset_contract_key)} · {s.state} · {s.row_count}행
                            {/* ★ 성격 표시는 서버가 준 문구를 그대로 쓴다 — 화면마다
                                각자 붙이면 한 화면에서 빠진다. */}
                            <div style={{ fontSize: 12, color: '#6b7280' }}>
                              {s.display_label}
                            </div>
                            {/* ★★★ 인증은 «이 판을 공식으로 쓴다» 는 선언이다.
                                ⚠️ 이미 인증된 판·격리된 판에는 버튼을 두지 않는다 —
                                  누를 수 없는 버튼은 「고장」으로 읽힌다. */}
                            {s.state === 'RAW' ? (
                              <button disabled={busy === s.snapshot_id}
                                onClick={() => onCertify(s.snapshot_id, s.row_count)}
                                style={{
                                  marginTop: 4, padding: '4px 12px', fontSize: 13,
                                  border: '1px solid #2563eb', background: '#fff',
                                  color: '#2563eb', borderRadius: 6, cursor: 'pointer',
                                }}>
                                {busy === s.snapshot_id ? '검사 중…' : '품질·대사 검사 후 시연 인증'}
                              </button>
                            ) : s.state === 'QUARANTINED' ? (
                              <div style={{ fontSize: 12, color: '#b91c1c', marginTop: 2 }}>
                                격리됨 — {s.quarantine?.reason || '사유 미기재'}. 고친 파일을 다시 올리십시오.
                              </div>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    </>
                  )}

                  <div style={{ borderTop: '1px solid #e5e7eb', marginTop: 8 }}>
                    <DataReadinessBoard instanceId={instanceId.trim()} />
                  </div>
                </>
              )}
            </>
        )}
        </Panel>
      </div>
    </HubDialog>
  );
}
