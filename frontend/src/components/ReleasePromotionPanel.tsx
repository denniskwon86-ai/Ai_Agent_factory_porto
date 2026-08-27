import { useEffect, useState } from 'react';

import { HubDialog } from '../design/HubDialog';
import { Panel } from '../design/HubShell';
import { DataPrepError } from '../lib/dataPrepApi';
import { promote, promotionCheck, listReleases } from '../lib/promotionApi';
import type { Check, ReleaseItem } from '../lib/promotionApi';

// [I-4 7 / Wave H-4] 운영 승격 — **후보를 운영으로 올리는 단 하나의 문.**
//
// ★★★ 왜 이 화면이 필요한가 (2026-08-19 실측)
//   승격 경로(검사 다섯 · 원자 전이 · 데이터 지문 봉인)는 전부 만들어져 있었는데
//   **화면이 없어서 API 로만 닿았다.** 사용자는 파일럿 동선의 마지막 칸을 끝낼 수
//   없었다. 만들어 놓고 아무도 쓸 수 없으면 만들어진 것이 아니다.
//
// ⚠️ 이 화면이 지켜야 할 것 넷
//   ① **누르기 전에 무엇이 막는지 말한다.** 같은 검사를 같은 순서로 미리 돌린다
//      (`promotion-check`). 눌러 보고 막히면 사용자는 「고장」으로 읽는다.
//   ② **화면이 판단하지 않는다.** 다섯 검사의 결과를 그대로 옮긴다. 화면이 자기
//      규칙으로 「올려도 되겠다」를 만들면 두 판정이 갈라진다.
//   ③ **「업무 데이터를 안 쓴다」를 사람이 명시한다.** 비워 두면 «확인하지 못함» 이고
//      그것은 통과가 아니다 — 그래서 기본값이 꺼짐이고, 켤 때 무슨 뜻인지 적는다.
//   ④ **승격 뒤에 무엇이 봉인됐는지 보여 준다.** 「어느 데이터 위에서 올렸나」에
//      나중에 답하려면 그 값이 화면에 한 번은 나와야 한다.

const STATUS_VIEW: Record<string, { label: string; tone: string; mark: string }> = {
  candidate: { label: '후보', mark: '◔', tone: 'var(--state-warn-fg)' },
  active: { label: '운영', mark: '●', tone: 'var(--state-success-fg)' },
  deprecated: { label: '사용 중단 예고', mark: '◐', tone: 'var(--state-warn-fg)' },
  disabled: { label: '사용 차단', mark: '✕', tone: 'var(--state-error-fg)' },
};

function StatusChip({ item }: { item: ReleaseItem }) {
  const v = STATUS_VIEW[item.lifecycle_status] ?? {
    // ⚠️ 모르는 상태를 «운영» 으로 떨어뜨리지 않는다.
    label: `알 수 없는 상태(${item.lifecycle_status})`, mark: '⚠', tone: 'var(--state-error-fg)',
  };
  return (
    <span style={{ color: v.tone, fontSize: 13, whiteSpace: 'nowrap' }}>
      {/* ★ 색만으로 구분하지 않는다(설계 §12) — 기호와 이름표를 함께 단다. */}
      <span aria-hidden style={{ marginRight: 4 }}>{v.mark}</span>{v.label}
      {/* ★★★ 추정과 관리자의 결정을 구분한다. 같게 보이면 «승인됨» 이라는 거짓 기록이 된다. */}
      {!item.lifecycle_recorded && (
        <span style={{ color: 'var(--surface-text-muted)', marginLeft: 6, fontSize: 12 }}>(미기록)</span>
      )}
    </span>
  );
}

function CheckList({ checks }: { checks: Check[] }) {
  return (
    <ul style={{ listStyle: 'none', padding: 0, margin: '8px 0 0' }}>
      {checks.map((c) => (
        <li key={c.name} style={{
          display: 'flex', gap: 10, padding: '7px 10px', fontSize: 14,
          borderBottom: '1px solid var(--surface-border)',
        }}>
          <span aria-hidden style={{ color: c.ok ? 'var(--state-success-fg)' : 'var(--state-error-fg)' }}>
            {c.ok ? '●' : '✕'}
          </span>
          <span style={{ width: 130 }}>{c.name}</span>
          <span style={{ flex: 1, color: c.ok ? 'var(--state-success-fg)' : 'var(--state-error-fg)' }}>
            {/* ⚠️ 사유를 뭉개지 않는다 — 무엇을 고쳐야 하는지가 여기에만 있다. */}
            {c.ok ? '통과' : c.reason}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function ReleasePromotionPanel({ onClose, page = false }: { onClose: () => void; page?: boolean }) {
  //: `null` = 아직 못 읽음, `[]` = 정말 0건.
  const [items, setItems] = useState<ReleaseItem[] | null>(null);
  const [loadErr, setLoadErr] = useState<{ message: string; status: number } | null>(null);
  const [picked, setPicked] = useState<ReleaseItem | null>(null);
  const [noData, setNoData] = useState(false);
  const [reason, setReason] = useState('');
  const [checks, setChecks] = useState<{ ok: boolean; checks: Check[] } | null>(null);
  const [checkErr, setCheckErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<{ status: string; data_fingerprint: string } | null>(null);

  function reload() {
    listReleases()
      .then((d) => setItems(d || []))
      .catch((e: unknown) => {
        const err = e as DataPrepError;
        setItems(null);
        setLoadErr({ message: err?.message || '', status: err?.status || 0 });
      });
  }

  useEffect(reload, []);

  //: ① 고르는 즉시 «무엇이 막는가» 를 미리 본다 — 누르기 전에 말하기 위해서.
  useEffect(() => {
    if (!picked) { setChecks(null); setCheckErr(null); return; }
    let alive = true;
    setCheckErr(null);
    setChecks(null);
    promotionCheck(picked.project_id, picked.release_id, noData)
      .then((d) => { if (alive) setChecks(d); })
      .catch((e: unknown) => {
        if (alive) setCheckErr((e as DataPrepError)?.message || '점검하지 못했습니다.');
      });
    return () => { alive = false; };
  }, [picked?.release_id, picked?.project_id, noData]);

  async function run() {
    if (!picked) return;
    setBusy(true);
    setCheckErr(null);
    try {
      const out = await promote(picked.project_id, picked.release_id, reason, noData);
      setDone({ status: out.status, data_fingerprint: out.data_fingerprint });
      reload();
    } catch (e) {
      //: ⚠️ 실패 사유를 그대로 보여 준다. 「올라가지 않는다」만 남으면 사용자는
      //:   무엇을 고쳐야 하는지 알 수 없다.
      setCheckErr((e as DataPrepError)?.message || '승격하지 못했습니다.');
    } finally {
      setBusy(false);
    }
  }

  const candidates = (items || []).filter((i) => i.lifecycle_status === 'candidate');
  const blocked = !picked ? '올릴 판을 고르십시오.'
    : checks === null ? ''
      : !checks.ok ? '아래 점검에서 막힌 항목이 있습니다 — 고친 뒤 다시 시도하십시오.'
        : '';

  return (
    <HubDialog label="운영 승격 — 후보 판을 운영으로 올립니다" onClose={onClose} page={page}>
      {/* ★ 제품 셸의 머리 바. ⚠️ 빠뜨리면 제목도 「닫기」도 없는 창이 되고, 사용자는
          Escape 를 아는 사람만 닫을 수 있다(첫 판에서 실제로 그랬다). */}
      {!page && <div className="afs-dialog-bar">
        <b>운영 승격</b>
        <span>후보 판을 운영으로 — 다섯 검사를 모두 지나야 올라갑니다</span>
        <div className="bar-actions">
          {busy && <span className="busy">올리는 중…</span>}
          <button onClick={onClose} className="secondary-button" style={{ minHeight: 32 }}>
            닫기 <span aria-hidden="true" style={{ opacity: .7 }}>(Esc)</span>
          </button>
        </div>
      </div>}

      <div className="afs-dialog-body" style={{
        overflow: 'auto', padding: 18, display: 'flex', flexDirection: 'column',
      }}>
        <Panel className="afs-fill">
          <h4 style={{ margin: '0 0 8px', fontSize: 15 }}>올릴 후보 판</h4>

          {items === null ? (
            <div style={{
              padding: 12, border: '1px solid var(--state-error-fg)', borderRadius: 6,
              background: 'var(--state-error-bg)', fontSize: 14,
            }}>
              <strong style={{ color: 'var(--state-error-fg)' }}>불러오지 못했습니다</strong>
              <div style={{ marginTop: 4 }}>{loadErr?.message}</div>
              <div style={{ marginTop: 4, fontSize: 13, color: 'var(--surface-text-muted)' }}>
                {/* ⚠️ 「없음」과 「지금 못 읽음」은 사용자가 할 일이 다르다. */}
                결과물이 없는 것이 아니라 지금 확인하지 못한 상태입니다.
              </div>
            </div>
          ) : candidates.length === 0 ? (
            <div style={{ fontSize: 13, color: 'var(--surface-text-muted)' }}>
              올릴 후보 판이 없습니다 — 게시하면 후보가 되고, 미리보기로 확인한 뒤
              여기서 운영으로 올립니다.
            </div>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 12px' }}>
              {candidates.map((it) => {
                const on = picked?.release_id === it.release_id;
                return (
                  <li key={it.release_id} style={{ marginBottom: 6 }}>
                    <button onClick={() => { setPicked(it); setDone(null); }} style={{
                      display: 'flex', alignItems: 'center', gap: 10, width: '100%',
                      textAlign: 'left', padding: '10px 12px', fontFamily: 'inherit',
                      border: `1px solid ${on ? 'var(--action-primary-bg)' : 'var(--surface-border)'}`, borderRadius: 6,
                      background: on ? 'var(--state-info-bg)' : '#fff', cursor: 'pointer',
                      fontSize: 14, color: 'inherit',
                    }}>
                      <span aria-hidden>{on ? '◉' : '○'}</span>
                      <span style={{ flex: 1 }}>
                        {/* 사람이 읽는 이름이 먼저다(설계 §12). */}
                        <strong>{it.project_name || it.release_id}</strong>
                        <span style={{ color: 'var(--surface-text-muted)', marginLeft: 8, fontSize: 12 }}>
                          {String(it.created_at || '').slice(0, 16).replace('T', ' ')}
                          {' · '}{it.release_id}
                        </span>
                      </span>
                      <StatusChip item={it} />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}

          {picked && (
            <>
              <h4 style={{ margin: '12px 0 4px', fontSize: 15 }}>올리기 전 점검</h4>
              <label style={{
                display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 13,
                color: 'var(--surface-text)', margin: '6px 0 10px',
              }}>
                <input type="checkbox" checked={noData}
                  onChange={(e) => setNoData(e.target.checked)} style={{ marginTop: 3 }} />
                <span>
                  이 앱은 업무 데이터를 쓰지 않습니다
                  <div style={{ color: 'var(--surface-text-muted)', fontSize: 12 }}>
                    {/* ★★★ 「확인하지 못함」과 「해당 없음」은 다른 사실이다. */}
                    켜지 않으면 업무 데이터 준비도를 확인합니다. 확인하지 못한 것을
                    «준비됨» 으로 세지 않습니다.
                  </div>
                </span>
              </label>

              {checkErr && (
                <div style={{ fontSize: 13, color: 'var(--state-error-fg)', marginBottom: 8 }}>
                  {checkErr}
                </div>
              )}
              {checks === null && !checkErr ? (
                <div style={{ fontSize: 13, color: 'var(--surface-text-muted)' }}>점검 중…</div>
              ) : checks && <CheckList checks={checks.checks} />}

              <div style={{ margin: '14px 0 8px' }}>
                <label style={{ fontSize: 13, color: 'var(--surface-text)' }}>
                  승격 사유 <span style={{ color: 'var(--surface-text-muted)' }}>(선택)</span>
                  <input value={reason} onChange={(e) => setReason(e.target.value)}
                    placeholder="예: 미리보기에서 확인 완료"
                    style={{
                      display: 'block', width: '100%', marginTop: 4, padding: '8px 10px',
                      border: '1px solid var(--surface-border)', borderRadius: 6, fontSize: 14,
                    }} />
                </label>
              </div>

              {/* ★★★ 막힌 이유를 **누르기 전에** 말한다. */}
              {blocked && (
                <div style={{ fontSize: 13, color: 'var(--state-warn-fg)', marginBottom: 8 }}>
                  {blocked}
                </div>
              )}
              <button onClick={run} disabled={busy || !!blocked || checks === null}
                style={{
                  padding: '9px 20px', borderRadius: 6, fontSize: 14, fontFamily: 'inherit',
                  border: `1px solid ${blocked || checks === null ? 'var(--surface-border)' : 'var(--action-primary-bg)'}`,
                  background: blocked || checks === null ? 'var(--surface-sunken)' : 'var(--action-primary-bg)',
                  color: blocked || checks === null ? 'var(--surface-text-faint)' : '#fff',
                  cursor: busy || blocked || checks === null ? 'default' : 'pointer',
                }}>{busy ? '올리는 중…' : '운영으로 올리기'}</button>

              {done && (
                <div style={{
                  marginTop: 14, padding: 12, borderRadius: 6, fontSize: 14,
                  background: 'var(--state-success-bg)', border: '1px solid var(--state-success-fg)',
                }}>
                  <strong>운영으로 올렸습니다.</strong>
                  {/* ★★★ 「어느 데이터 위에서 올렸나」에 나중에 답하려면 그 값이 화면에
                      한 번은 나와야 한다. */}
                  <div style={{ marginTop: 6, fontSize: 13, color: 'var(--surface-text)' }}>
                    봉인된 업무 데이터 지문:{' '}
                    <code>{done.data_fingerprint || '(없음)'}</code>
                    {done.data_fingerprint === 'NOT_APPLICABLE' && (
                      <span style={{ color: 'var(--surface-text-muted)' }}> — 업무 데이터를 쓰지 않는 앱</span>
                    )}
                  </div>
                  <div style={{ marginTop: 4, fontSize: 12, color: 'var(--surface-text-muted)' }}>
                    이 판으로 열어 둔 미리보기 증명은 더 이상 쓸 수 없습니다 — 앱을 다시
                    여십시오.
                  </div>
                </div>
              )}
            </>
          )}
        </Panel>
      </div>
    </HubDialog>
  );
}
