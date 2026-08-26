import { useCallback, useEffect, useRef, useState } from 'react';
import {
  approveAppContract, buildKitApp, DataPrepError, draftAppContract, listKitApps,
  promoteKitApp, type AppContractStatus, type KitAppRow,
} from '../lib/dataPrepApi';
import {
  issueAppProof, listAppDatasets, readAppRecords,
  type AppDatasetRow, type AppRecords,
} from '../lib/kitAppViewApi';
import {
  datasetDisplayName, KitBusinessView, preferredDatasetName,
} from './KitBusinessView';
import { shortId } from '../lib/displayId';

// [2026-08-23] 키트로 앱 만들기 — **여정의 빈 칸.**
//
// ⚠️⚠️ 이 패널이 없던 동안 준비도 보드는 「지금 만들 수 있는 것: 가능」을 그렸고
//   **누를 것이 없었다.** 「보여 주는 것」과 「되는 것」이 다르면, 보여 주는 쪽이
//   거짓말을 한다.
//
// ⚠️ 판정하지 않는다. 준비도도 계약 상태도 서버가 준 것을 **그대로 옮긴다** —
//   화면이 자기 규칙으로 다시 판단하면 두 판정이 갈라지고, 갈린 날 사용자는 서버가
//   막은 것을 화면이 허용하는 상태를 본다.

// ★ 앱 분류. **서버의 닫힌 목록**(`core/app_manifest.APP_CLASSES`)과 같아야 한다.
// ⚠️ 기본값을 두지 않는다 — 「모르면 departmental」이 되면 추측한 분류가 나중에
//   권한 판단의 근거로 쓰인다. 사람이 고르게 한다.
const APP_CLASSES: { value: string; label: string; hint: string }[] = [
  { value: 'departmental', label: '부서용', hint: '한 부서가 쓰는 앱' },
  { value: 'enterprise', label: '전사용', hint: '여러 부서가 함께 쓰는 앱' },
  { value: 'personal', label: '개인용', hint: '만든 사람만 쓰는 앱' },
];

const READINESS_VIEW: Record<string, { label: string; tone: string }> = {
  AVAILABLE: { label: '가능', tone: 'var(--state-success-fg)' },
  AVAILABLE_WITH_WARNING: { label: '제한적 가능', tone: 'var(--state-warn-fg)' },
  BLOCKED: { label: '막힘', tone: 'var(--state-error-fg)' },
};

// ★★★ 계약 상태 셋은 **서로 다른 사실**이다. 하나로 뭉개면 화면이 다음 할 일을
//   말해 줄 수 없다 — 「없음」은 만들라는 뜻이고 「초안」은 승인을 받으라는 뜻이다.
function contractView(status: AppContractStatus): { label: string; tone: string } {
  if (status === null) return { label: '계약 없음', tone: 'var(--surface-text-muted)' };
  if (status === 'DRAFT') return { label: '승인 대기', tone: 'var(--state-warn-fg)' };
  if (status === 'APPROVED') return { label: '승인됨', tone: 'var(--state-success-fg)' };
  if (status === 'SUPERSEDED') return { label: '이전 판(대체됨)', tone: 'var(--surface-text-muted)' };
  // ⚠️ 모르는 상태를 «승인됨» 으로 떨어뜨리지 않는다.
  return { label: `알 수 없음(${status})`, tone: 'var(--state-error-fg)' };
}

type Notice = { tone: 'ok' | 'warn' | 'err'; text: string };

const NOTICE_STYLE: Record<Notice['tone'], { bg: string; border: string }> = {
  ok: { bg: 'var(--state-success-bg)', border: 'var(--state-success-fg)' },
  warn: { bg: '#fffbeb', border: 'var(--state-warn-fg)' },
  err: { bg: 'var(--state-error-bg)', border: 'var(--state-error-fg)' },
};

// ── 만든 앱 열어 보기 ──────────────────────────────────────────────────────
//
// ⚠️⚠️ [2026-08-24 실측] 이 자리가 **비어 있었다.** 「앱 만들기」를 눌러 200 을 받고
//   나면 그 다음에 할 수 있는 일이 화면에 없었다 — 만든 것을 볼 방법이 없으니
//   「만들어졌다」는 글자만 남는다. 여정이 여기서 끊겼다.
//: 봉투 칸(레코드 관리용)만 남긴다 — 업무 칸 **뒤**에 붙이기 위해서다.
//: ⚠️ 버리지 않는다. `record_id` 는 사용자가 특정 행을 지목할 때 유일한 근거다.
const ENVELOPE_KEYS = ['record_id', 'created_at', 'updated_at', 'deleted'] as const;

function stripEnvelope(row: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const k of ENVELOPE_KEYS) if (k in row) out[k] = row[k];
  return out;
}

function AppViewer({
  releaseId, appId, appLabel,
}: { releaseId: string; appId: string; appLabel: string }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [sets, setSets] = useState<AppDatasetRow[] | null>(null);
  const [picked, setPicked] = useState('');
  const [rows, setRows] = useState<AppRecords | null>(null);
  //: ★★★ 증명은 **메모리에만** 둔다 — 저장소·URL·로그 어디에도 두지 않는다.
  const proofRef = useRef('');

  const load = useCallback(async () => {
    setBusy(true); setErr('');
    try {
      const ds = await listAppDatasets(releaseId);
      setSets(ds);
      if (!proofRef.current) proofRef.current = await issueAppProof(releaseId);
      if (ds.length) {
        const first = preferredDatasetName(appId, ds);
        setPicked(first);
        setRows(await readAppRecords(proofRef.current, first));
      }
    } catch (e: any) {
      //: ⚠️ 사유를 삼키지 않는다. 후보 판이면 403 이고, 그때 할 일은 «운영 전환» 이다.
      setErr(e?.message || '열지 못했습니다.');
    } finally { setBusy(false); }
  }, [appId, releaseId]);

  async function pick(name: string) {
    setPicked(name); setRows(null); setErr('');
    try {
      setRows(await readAppRecords(proofRef.current, name));
    } catch (e: any) { setErr(e?.message || '읽지 못했습니다.'); }
  }

  if (!open) {
    return (
      <button type="button" style={{ fontSize: 13, padding: '5px 12px' }}
              onClick={() => { setOpen(true); void load(); }}>
        앱 열어 보기
      </button>
    );
  }

  //: ⚠️⚠️ [2026-08-24 실측] 응답 모양이 **두 가지**다. 인증판을 통해 오는 행은 업무
  //:   칸이 평평하게 오고, 앱 자체 레코드는 `{record_id, created_at, …, payload}` 봉투에
  //:   담겨 온다. 봉투만 그렸더니 12,000건을 읽고도 화면에는 `record_id`·`created_at`
  //:   네 칸만 떴다 — 「데이터가 없다」보다 나쁘다(있는데 엉뚱한 것을 보여 준다).
  //: ★ 봉투가 있으면 **벗겨서** 합친다. 봉투 칸은 뒤로 민다.
  const flat = (rows?.records || []).map((r) => {
    const pay = (r as any).payload;
    return (pay && typeof pay === 'object') ? { ...pay, ...stripEnvelope(r) } : r;
  });
  //: ★ 원본 열은 버리지 않는다. 다만 사용자의 첫 화면은 앱 계약에 선언한 **업무 열**을
  //:   먼저 보여 주고, 거버넌스·기술 열은 접힌 관리자 진단으로 내린다. 원본 표를 그대로
  //:   내놓는 것은 앱이 아니라 데이터 브라우저다.
  const pickedDataset = (sets || []).find((dataset) => dataset.name === picked);

  return (
    <div style={{
      marginTop: 8, border: '1px solid var(--surface-border)', borderRadius: 8,
      padding: 10, background: 'var(--surface-raised)', display: 'grid', gap: 8,
    }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <strong style={{ fontSize: 13 }}>{appLabel}</strong>
        {(sets || []).map((d) => (
          <button key={d.name} type="button" onClick={() => void pick(d.name)}
                  style={{
                    fontSize: 12, padding: '3px 9px', borderRadius: 6,
                    border: '1px solid var(--surface-border-control)',
                    background: d.name === picked ? 'var(--surface-selected)' : 'transparent',
                    fontWeight: d.name === picked ? 600 : 400,
                  }}>
            {datasetDisplayName(appId, d)}
          </button>
        ))}
        <button type="button" onClick={() => setOpen(false)}
                style={{ fontSize: 12, padding: '3px 9px', marginLeft: 'auto' }}>닫기</button>
      </div>

      {busy && <div style={{ fontSize: 13 }}>여는 중…</div>}
      {err && (
        <div style={{ fontSize: 13, color: 'var(--state-error-fg)' }}>{err}</div>
      )}
      {rows && (
        <div>
          <div style={{ fontSize: 12, color: 'var(--surface-text-muted)', marginBottom: 4 }}>
            {/* ⚠️ 보인 건수를 «전부» 로 읽지 않게 총계를 함께 적는다. */}
            {flat.length}건 표시 · 총 {rows.total}건
          </div>
          <KitBusinessView
            appId={appId}
            datasetName={picked}
            datasetLabel={pickedDataset?.label || picked}
            records={flat}
            total={rows.total}
            asOf={rows.as_of}
            stale={rows.stale}
          />
        </div>
      )}
    </div>
  );
}

function AppRow({
  row, instanceId, onChanged, notice, setNotice, mode,
}: {
  row: KitAppRow; instanceId: string; onChanged: () => void;
  mode: 'build' | 'operate';
  //: ★★★ [2026-08-23 실측] **알림은 부모가 들고 있어야 한다.**
  //:
  //: ⚠️⚠️ 종전에는 이 행의 지역 상태였다. 그런데 성공하면 `onChanged()` 가 목록을
  //:   다시 불러 행을 **새로 그리고**, 그 순간 알림이 사라졌다. 실측에서 「앱 만들기」
  //:   가 200 을 받았는데 **화면에는 아무 일도 안 일어난 것처럼** 보였다.
  notice: Notice | null; setNotice: (n: Notice | null) => void;
}) {
  const [appClass, setAppClass] = useState('');
  const [rationale, setRationale] = useState('');
  const [promoteReason, setPromoteReason] = useState('');
  const [busy, setBusy] = useState('');

  const rv = READINESS_VIEW[row.readiness_state]
    // ⚠️ 서버가 새 상태를 내면 화면은 그것을 «모른다» 고 말해야 한다.
    ?? { label: `알 수 없는 상태(${row.readiness_state})`, tone: 'var(--state-error-fg)' };
  const cv = contractView(row.contract_status);
  const blocked = row.readiness_state === 'BLOCKED';

  // ★ 서버 문구를 **그대로** 옮긴다. 여기서 새 문구를 지으면 같은 사실이 두 가지로
  //   설명되고, 사용자는 어느 쪽을 믿을지 모른다.
  const run = useCallback(async (what: string, fn: () => Promise<unknown>) => {
    setBusy(what);
    setNotice(null);
    try {
      await fn();
      onChanged();
      setNotice({ tone: 'ok', text: `${what}을(를) 마쳤습니다.` });
    } catch (e: unknown) {
      const err = e as DataPrepError;
      setNotice({
        tone: err?.status === 503 ? 'warn' : 'err',
        text: err?.message || `${what}에 실패했습니다.`,
      });
    } finally {
      setBusy('');
    }
  }, [onChanged, setNotice]);

  return (
    <li style={{
      border: '1px solid var(--surface-border)', borderRadius: 8, padding: 12, marginBottom: 10,
      listStyle: 'none',
    }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
        <strong style={{ fontSize: 15 }}>{row.label || row.app_id}</strong>
        <span style={{ fontSize: 12, color: 'var(--surface-text-muted)' }}>{row.app_id}</span>
        {/* ★ 색만으로 구분하지 않는다(설계 §12) — 이름표를 함께 단다. */}
        <span style={{ color: rv.tone, fontSize: 13 }}>준비: {rv.label}</span>
        <span style={{ color: cv.tone, fontSize: 13 }}>계약: {cv.label}</span>
        {row.contract_revision !== null && (
          <span style={{ color: 'var(--surface-text-muted)', fontSize: 12 }}>
            개정 {row.contract_revision}
          </span>
        )}
      </div>

      {row.user_message && (
        <div style={{ color: 'var(--surface-text-muted)', fontSize: 13, marginTop: 4 }}>{row.user_message}</div>
      )}
      {row.next_action && (
        <div style={{ fontSize: 13, marginTop: 2 }}>→ {row.next_action}</div>
      )}

      {/* ★★★ 막힌 것에는 **버튼을 그리지 않는다.** 「일부라도 열어 주자」가 위험하다 —
          열린 앱은 빈 화면을 보여 주고, 사용자는 그것을 「우리 회사에 자료가 없다」로
          읽는다. 실제로는 우리가 아직 준비하지 못한 것이다. */}
      {blocked ? (
        <div style={{ marginTop: 8, fontSize: 13, color: 'var(--state-error-fg)' }}>
          데이터가 준비되면 만들 수 있습니다.
        </div>
      ) : (
        <div style={{ marginTop: 10, display: 'grid', gap: 8 }}>
          {row.contract_status === null && mode === 'build' && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <label style={{ fontSize: 13 }}>
                앱 분류{' '}
                <select value={appClass} onChange={(e) => setAppClass(e.target.value)}
                        style={{ fontSize: 13, padding: '4px 6px' }}>
                  {/* ⚠️ 빈 선택을 **기본값으로 남긴다.** 미리 골라 두면 사람이 고른
                      것처럼 보이고, 그 값이 권한 판단의 근거가 된다. */}
                  <option value="">— 고르십시오 —</option>
                  {APP_CLASSES.map((c) => (
                    <option key={c.value} value={c.value}>{c.label} ({c.hint})</option>
                  ))}
                </select>
              </label>
              <button type="button" disabled={!appClass || !!busy}
                      onClick={() => run('계약 초안 만들기',
                                         () => draftAppContract(instanceId, row.app_id, appClass))}
                      style={{ fontSize: 13, padding: '5px 12px' }}>
                {busy === '계약 초안 만들기' ? '만드는 중…' : '계약 초안 만들기'}
              </button>
            </div>
          )}

          {row.contract_status === null && mode === 'operate' && (
            <div style={{ fontSize: 13, color: 'var(--surface-text-muted)' }}>
              아직 만들지 않은 앱입니다 — 앱 제작에서 분류와 계약을 준비하십시오.
            </div>
          )}

          {row.contract_status === 'DRAFT' && mode === 'build' && (
            <div style={{ display: 'grid', gap: 6 }}>
              <div style={{ fontSize: 13, color: 'var(--surface-text-muted)' }}>
                {/* ★★★ 직무 분리를 화면이 **말한다.** 눌러 보고 403 을 받는 것보다,
                    누르기 전에 아는 편이 낫다. */}
                {row.drafted_by ? `${row.drafted_by} 님이 만들었습니다 — ` : ''}
                만든 사람이 아닌 <strong>다른 사람</strong>이 승인해야 합니다.
              </div>
              <input value={rationale} onChange={(e) => setRationale(e.target.value)}
                     placeholder="승인 근거 — 왜 이 앱을 여는지"
                     style={{ fontSize: 13, padding: '5px 8px' }} />
              <div>
                <button type="button"
                        disabled={!rationale.trim() || !!busy || row.contract_revision === null}
                        onClick={() => run('계약 승인', () => approveAppContract(
                          instanceId, row.app_id, row.contract_revision as number,
                          rationale))}
                        style={{ fontSize: 13, padding: '5px 12px' }}>
                  {busy === '계약 승인' ? '승인하는 중…' : '계약 승인'}
                </button>
              </div>
            </div>
          )}

          {row.contract_status === 'DRAFT' && mode === 'operate' && (
            <div style={{ fontSize: 13, color: 'var(--state-warn-fg)' }}>
              계약 승인 대기 중입니다 — 승인된 뒤 앱을 만들 수 있습니다.
            </div>
          )}

          {row.contract_status === 'APPROVED' && (
            <div style={{ display: 'grid', gap: 6 }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <span style={{ fontSize: 13, color: 'var(--surface-text-muted)' }}>
                  {row.approved_by ? `${row.approved_by} 님이 승인했습니다.` : '승인되었습니다.'}
                </span>
                {mode === 'build' && (
                  <button type="button" disabled={!!busy}
                          onClick={() => run('앱 만들기',
                                             () => buildKitApp(instanceId, row.app_id))}
                          style={{ fontSize: 13, padding: '5px 12px', fontWeight: 600 }}>
                    {busy === '앱 만들기'
                      ? '만드는 중…'
                      : (row.built_datasets ? '다시 만들기' : '앱 만들기')}
                  </button>
                )}
              </div>
              {/* ★★★ **된 것을 보여 준다.** 눌러서 200 이 왔는데 화면이 그대로면
                  사용자는 눌리지 않았다고 읽는다(실측 2026-08-23). */}
              <div style={{ fontSize: 13 }}>
                {row.built_datasets === null ? (
                  // ⚠️ 「지금 확인하지 못했다」를 「안 만들어졌다」로 그리지 않는다.
                  <span style={{ color: 'var(--state-warn-fg)' }}>
                    만들어졌는지 지금 확인하지 못했습니다.
                  </span>
                ) : row.built_datasets > 0 ? (
                  <div style={{ display: 'grid', gap: 6 }}>
                    <span style={{ color: 'var(--state-success-fg)' }}>
                      ● 만들어졌습니다 — 데이터셋 {row.built_datasets}개
                      <span style={{ color: 'var(--surface-text-muted)', marginLeft: 6, fontSize: 12 }}>
                        <span title={row.release_id}>{shortId(row.release_id)}</span>
                      </span>
                    </span>

                    {/* ★★★ **만든 것과 쓸 수 있는 것은 다르다.**
                        ⚠️⚠️ [2026-08-24 실측] 만든 앱은 시연 평면의 «후보 판» 이고,
                          그 상태로 열면 표만 보이고 **레코드가 0** 이다. 그것을
                          「우리 회사에 자료가 없다」로 읽는다. 여기서 다음 할 일을
                          말한다. */}
                    {row.lifecycle_state === 'candidate' && (
                      <div style={{ display: 'grid', gap: 6 }}>
                        <div style={{ fontSize: 13, color: 'var(--state-warn-fg)' }}>
                          아직 <strong>시연용 후보 판</strong>입니다 — 실제 업무 데이터를
                          읽으려면 운영으로 올려야 합니다.
                        </div>
                        <input value={promoteReason}
                               onChange={(e) => setPromoteReason(e.target.value)}
                               placeholder="운영 전환 근거 — 왜 지금 이 앱을 운영에 올리는지"
                               style={{ fontSize: 13, padding: '5px 8px' }} />
                        <div>
                          <button type="button"
                                  disabled={!promoteReason.trim() || !!busy}
                                  onClick={() => run('운영 전환', () => promoteKitApp(
                                    instanceId, row.app_id, promoteReason))}
                                  style={{ fontSize: 13, padding: '5px 12px', fontWeight: 600 }}>
                            {busy === '운영 전환' ? '올리는 중…' : '운영으로 올리기'}
                          </button>
                          <span style={{ fontSize: 12, color: 'var(--surface-text-muted)', marginLeft: 8 }}>
                            상태·계약·정적 검사·계약 승인·데이터 준비도 다섯 가지를 다시 봅니다.
                          </span>
                        </div>
                      </div>
                    )}

                    {row.lifecycle_state === 'active' && (
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                        <span style={{ fontSize: 13, color: 'var(--state-success-fg)' }}>
                          ● 운영 중 — 인증된 업무 데이터를 읽습니다.
                        </span>
                        <AppViewer releaseId={row.release_id} appId={row.app_id}
                                   appLabel={row.label || row.app_id} />
                      </div>
                    )}
                  </div>
                ) : (
                  <span style={{ color: 'var(--surface-text-muted)' }}>아직 만들지 않았습니다.</span>
                )}
              </div>
            </div>
          )}

          {row.contract_status === 'SUPERSEDED' && (
            <div style={{ fontSize: 13, color: 'var(--state-warn-fg)' }}>
              {/* ⚠️ 이 상태를 «없음» 으로 그리면 사용자는 초안을 또 만들고, 왜 안 되는지
                  모른다. 무엇이 일어났는지 말한다. */}
              이 개정은 더 새로운 개정에 밀려났습니다 — 새 개정을 승인해야 만들 수 있습니다.
            </div>
          )}
        </div>
      )}

      {notice && (
        <div style={{
          marginTop: 8, padding: '6px 10px', fontSize: 13, borderRadius: 6,
          background: NOTICE_STYLE[notice.tone].bg,
          border: `1px solid ${NOTICE_STYLE[notice.tone].border}`,
        }}>
          {notice.text}
          {notice.tone === 'warn' && (
            // ★ 503 은 「입력을 고쳐 다시 하라」가 아니다 — 사람이 정리할 상태다.
            <div style={{ color: 'var(--surface-text-muted)', marginTop: 2 }}>
              지금 처리할 수 없는 상태입니다 — 잠시 후 다시 시도하거나 관리자에게
              알려 주십시오.
            </div>
          )}
        </div>
      )}
    </li>
  );
}

export function KitAppPanel({
  instanceId, mode = 'build',
}: { instanceId: string; mode?: 'build' | 'operate' }) {
  const [rows, setRows] = useState<KitAppRow[] | null>(null);
  const [error, setError] = useState<{ message: string; status: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  //: ★ 앱별 알림. 목록을 다시 불러도 **행이 아니라 여기** 있으므로 살아남는다.
  const [notices, setNotices] = useState<Record<string, Notice | null>>({});

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    listKitApps(instanceId)
      .then((d) => { if (alive) setRows(d.apps); })
      .catch((e: unknown) => {
        if (!alive) return;
        const err = e as DataPrepError;
        setError({ message: err?.message || '불러오지 못했습니다.', status: err?.status || 0 });
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [instanceId, tick]);

  if (loading) return <div style={{ padding: 16 }}>앱 목록을 확인하는 중…</div>;

  // ★★★ **조회 실패와 0건을 구분한다.** 실패를 빈 목록으로 그리면 사용자는
  //   「만들 수 있는 앱이 없다」로 읽고, 원인을 데이터에서 찾는다.
  if (error) {
    return (
      <div style={{ padding: 16, border: '1px solid var(--state-error-fg)', borderRadius: 8 }}>
        <strong style={{ color: 'var(--state-error-fg)' }}>앱 목록을 불러오지 못했습니다</strong>
        <div style={{ marginTop: 6, fontSize: 14 }}>{error.message}</div>
        <div style={{ marginTop: 6, fontSize: 13, color: 'var(--surface-text-muted)' }}>
          {error.status === 404
            ? '이 키트 인스턴스를 찾을 수 없습니다 — 조직 범위를 확인해 주십시오.'
            : '만들 수 있는 앱이 없는 것이 아니라 지금 확인하지 못한 상태입니다.'}
        </div>
      </div>
    );
  }
  if (!rows) return null;

  return (
    <div style={{ padding: 16 }}>
      <h3 style={{ fontSize: 16, margin: '0 0 4px' }}>
        {mode === 'build' ? '키트로 앱 만들기' : '업무 앱 운영'}
      </h3>
      <div style={{ fontSize: 13, color: 'var(--surface-text-muted)', marginBottom: 10 }}>
        {/* ★ 「만드는 사람 ≠ 승인하는 사람」을 화면 맨 위에 적는다 — 나중에 403 을
            받고 나서 알게 하지 않는다. */}
        {mode === 'build' ? <>
          계약을 만든 뒤 <strong>다른 사람의 승인</strong>을 받아야 앱을 만들 수 있습니다.
        </> : <>
          운영 중인 앱을 열고, 후보 앱의 운영 전환 상태를 확인합니다.
        </>}
      </div>
      {rows.length === 0 ? (
        // ⚠️ 산출물 선언이 없는 키트를 «전부 가능» 으로 보이게 두지 않는다.
        <div style={{ fontSize: 14, color: 'var(--state-warn-fg)' }}>
          이 키트는 만들 수 있는 앱을 선언하지 않았습니다.
        </div>
      ) : (
        <ul style={{ padding: 0, margin: 0 }}>
          {rows.map((r) => (
            <AppRow key={r.app_id} row={r} instanceId={instanceId}
                    mode={mode}
                    notice={notices[r.app_id] ?? null}
                    setNotice={(n) => setNotices((m) => ({ ...m, [r.app_id]: n }))}
                    onChanged={() => setTick((t) => t + 1)} />
          ))}
        </ul>
      )}
    </div>
  );
}
