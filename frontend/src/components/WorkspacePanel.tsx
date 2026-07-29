// 부서 워크스페이스 화면 (명세서 §9 / §14 M3)
//
// ⚠️ 기능 확인용 최소 화면. 데이터 계층(`lib/workspaceApi.ts`)만 재사용 가능하게 두었다.
//
// 이 화면의 목적은 "승격 버튼"이 아니라 **왜 막혔는지 보여주는 것**이다.
// 게이트가 막았는데 이유를 못 보면 사용자는 우회로를 찾거나 포기한다. 둘 다 나쁘다.
//   ① 5개 검사 항목의 상태와 **다음 조치**를 그대로 노출한다
//   ② `unverifiable` 을 `pass` 와 다른 색으로 둔다 — 확인 못 한 것은 통과가 아니다
//   ③ 통과하지 못하면 승격 버튼이 잠긴다(백엔드가 어차피 409 지만, 누르기 전에 알아야 한다)
//   ④ 공유와 승격을 화면에서도 분리한다 — 묶어 보이면 같은 행위로 오해한다
import { useCallback, useEffect, useState } from 'react';
import type {
  Checklist, ChecklistStep, Fork, Gate, GateCheck, Promotion, RollbackResult, Share,
} from '../lib/workspaceApi';
import {
  createShare, fetchChecklist, fetchForks, fetchGate, fetchPromotions, fetchShares,
  ownerApprove, promoteRelease, rejectPromotion, requestPromotion, revokeShare,
  rollbackRelease,
} from '../lib/workspaceApi';

type Props = { onClose: () => void };

const STATE: Record<string, { label: string; cls: string }> = {
  pass: { label: '통과', cls: 'text-emerald-400' },
  fail: { label: '차단', cls: 'text-red-400' },
  // ★ 통과와 같은 톤이면 "확인 못 한 것"이 "괜찮은 것"으로 읽힌다.
  unverifiable: { label: '확인 불가(통과 아님)', cls: 'text-violet-300' },
};

const CHECK_LABEL: Record<string, string> = {
  asset_linkage: '사용 자산 연결',
  data_contract: '데이터 계약',
  security: '보안(민감도·PII)',
  quality: '품질 게이트',
  data_owner_approval: '데이터 오너 승인',
};

const STEP_STATE: Record<string, { label: string; cls: string }> = {
  pass: { label: '통과', cls: 'text-emerald-400' },
  fail: { label: '차단', cls: 'text-red-400' },
  unverifiable: { label: '확인 불가(통과 아님)', cls: 'text-violet-300' },
  // ★ '해당 없음'을 통과와 같은 색으로 두면 검사한 것처럼 읽힌다. 회색으로 구분한다.
  not_required: { label: '해당 없음(§8.2)', cls: 'text-slate-500' },
};

const STEP_LABEL: Record<string, string> = {
  artifacts: '① 코드·문서·스키마',
  traceability: '② 요구사항 추적성',
  tests: '③ 핵심 업무 테스트',
  permission_contract: '④ 권한·데이터 계약',
  acceptance: '⑤ 사용자 수용검수',
  shadow_mode: '⑥ Shadow Mode',
  release_approval: '⑦ 릴리스 승인',
};

const PROMO: Record<string, { label: string; cls: string }> = {
  draft: { label: '초안', cls: 'text-slate-400' },
  requested: { label: '신청됨', cls: 'text-amber-300' },
  approved: { label: '오너 승인', cls: 'text-sky-300' },
  rejected: { label: '반려', cls: 'text-red-400' },
  promoted: { label: '전사 승격', cls: 'text-emerald-400' },
};

export default function WorkspacePanel({ onClose }: Props) {
  const [promotions, setPromotions] = useState<Promotion[]>([]);
  const [releaseId, setReleaseId] = useState('');
  const [projectId, setProjectId] = useState('');
  const [fromScope, setFromScope] = useState('');
  const [gate, setGate] = useState<Gate | null>(null);
  const [shares, setShares] = useState<Share[]>([]);
  const [forks, setForks] = useState<Fork[]>([]);
  const [toScope, setToScope] = useState('');
  const [checklist, setChecklist] = useState<Checklist | null>(null);
  const [liveIntegration, setLiveIntegration] = useState(false);
  const [rollbackReason, setRollbackReason] = useState('');
  const [rollbackOut, setRollbackOut] = useState<RollbackResult | null>(null);
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  const loadList = useCallback(async () => {
    try { setPromotions(await fetchPromotions()); }
    catch (e) { setErr(String(e)); }
  }, []);
  useEffect(() => { loadList(); }, [loadList]);

  const inspect = async (rid: string, pid = '') => {
    setErr(''); setMsg('');
    setReleaseId(rid); setProjectId(pid);
    setRollbackOut(null);
    const [g, s, f, c] = await Promise.allSettled([
      fetchGate(rid, pid), fetchShares(rid), fetchForks(rid),
      fetchChecklist(rid, pid, liveIntegration),
    ]);
    setGate(g.status === 'fulfilled' ? g.value : null);
    setShares(s.status === 'fulfilled' ? s.value : []);
    setForks(f.status === 'fulfilled' ? f.value : []);
    setChecklist(c.status === 'fulfilled' ? c.value : null);
    if (g.status === 'rejected') setErr(String(g.reason));
  };

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setMsg(''); setErr('');
    try {
      await fn();
      setMsg(ok);
      await inspect(releaseId, projectId);
      loadList();
    } catch (e) {
      // 백엔드 거절 사유를 그대로 — 요약하면 무엇을 고쳐야 할지가 사라진다.
      setErr(String(e).replace(/^Error:\s*/, ''));
    }
  };

  const current = promotions.find((p) => p.release_id === releaseId);

  return (
    <div className="fixed inset-0 z-50 bg-slate-950 text-slate-200 overflow-y-auto">
      <div className="max-w-6xl mx-auto p-6 space-y-4">
        <header className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-lg font-semibold">부서 워크스페이스 — 공유 · 복제 · 전사 승격</h2>
            <p className="text-[11px] text-slate-400">
              공유는 승격이 아닙니다. 전사 승격은 데이터 계약·보안·품질·소유자 승인을
              <b> 모두</b> 통과해야 합니다(§9.3).
            </p>
          </div>
          <button onClick={onClose} className="px-3 py-1 text-xs bg-slate-600 rounded">닫기</button>
        </header>

        {err && <div className="border border-red-500/40 bg-red-500/10 text-red-200 text-xs
                                rounded px-3 py-2 whitespace-pre-wrap">{err}</div>}
        {msg && <div className="border border-emerald-500/40 bg-emerald-500/10 text-emerald-200
                                text-xs rounded px-3 py-2">{msg}</div>}

        {/* 조회 */}
        <section className="border border-slate-700 rounded-lg p-4 bg-slate-900/60">
          <h3 className="text-sm font-semibold">릴리스 점검</h3>
          <div className="flex gap-2 mt-2 flex-wrap">
            <input value={releaseId} onChange={(e) => setReleaseId(e.target.value)}
              placeholder="release_id"
              className="flex-1 min-w-[220px] bg-slate-800 border border-slate-600 rounded
                         px-2 py-1 text-xs" />
            <input value={projectId} onChange={(e) => setProjectId(e.target.value)}
              placeholder="project_id (품질 기록 조회 키)"
              className="flex-1 min-w-[200px] bg-slate-800 border border-slate-600 rounded
                         px-2 py-1 text-xs" />
            <button onClick={() => inspect(releaseId, projectId)}
              className="px-3 py-1 text-xs bg-slate-700 rounded">게이트 점검</button>
          </div>
          {promotions.length > 0 && (
            <div className="flex gap-1.5 flex-wrap mt-2">
              {promotions.map((p) => (
                <button key={p.promotion_id}
                  onClick={() => inspect(p.release_id, p.project_id)}
                  className="text-[11px] border border-slate-700 rounded px-2 py-1">
                  {p.release_id}{' '}
                  <span className={PROMO[p.status]?.cls}>{PROMO[p.status]?.label}</span>
                </button>
              ))}
            </div>
          )}
        </section>

        {gate && (
          <>
            {/* ① 게이트 — 왜 막혔는지가 이 화면의 목적이다 */}
            <section className="border border-slate-700 rounded-lg p-4 bg-slate-900/60">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <h3 className="text-sm font-semibold">
                  전사 승격 게이트 (§9.3){' '}
                  <span className={gate.promotable ? 'text-emerald-400' : 'text-red-400'}>
                    {gate.promotable ? '통과' : '차단'}
                  </span>
                </h3>
                <span className="text-[11px] text-slate-400">
                  사용 자산 {gate.linked_assets.length}건
                </span>
              </div>
              <ul className="mt-3 space-y-1.5">
                {gate.checks.map((c: GateCheck) => (
                  <li key={c.check} className="text-xs border border-slate-700 rounded
                                               px-2 py-1.5">
                    <div className="flex items-center gap-2">
                      <span className={`${STATE[c.state]?.cls} shrink-0`}>
                        [{STATE[c.state]?.label}]
                      </span>
                      <span className="font-medium">{CHECK_LABEL[c.check] || c.check}</span>
                    </div>
                    <div className="text-slate-300 mt-0.5">{c.why}</div>
                    {/* 막혔으면 무엇을 해야 하는지가 반드시 보여야 한다 */}
                    {c.state !== 'pass' && c.suggested_action && (
                      <div className="text-amber-200/90 mt-0.5">→ {c.suggested_action}</div>
                    )}
                  </li>
                ))}
              </ul>
              <p className="text-[11px] text-slate-500 mt-2">{gate.note}</p>

              <div className="flex gap-2 mt-3 flex-wrap">
                <button
                  onClick={() => act(() => requestPromotion({
                    release_id: releaseId, from_scope: fromScope || 'unknown',
                    project_id: projectId,
                  }), '승격을 신청했습니다.')}
                  className="px-3 py-1 text-xs bg-slate-700 rounded">승격 신청</button>
                <button
                  onClick={() => act(() => ownerApprove(releaseId), '데이터 오너가 승인했습니다.')}
                  className="px-3 py-1 text-xs bg-sky-800 hover:bg-sky-700 rounded">
                  데이터 오너 승인
                </button>
                <button
                  onClick={() => act(() => rejectPromotion(releaseId, '검토 결과 보류'),
                                     '반려했습니다.')}
                  className="px-3 py-1 text-xs bg-slate-700 rounded">반려</button>
                {/* ③ 통과 못 하면 잠근다 — 백엔드가 409 를 주지만 누르기 전에 알아야 한다 */}
                <button
                  disabled={!gate.promotable}
                  onClick={() => act(() => promoteRelease(releaseId), '전사 승격했습니다.')}
                  className={`px-3 py-1 text-xs rounded ${gate.promotable
                    ? 'bg-emerald-700 hover:bg-emerald-600'
                    : 'bg-slate-700 opacity-50 cursor-not-allowed'}`}>
                  전사 승격
                </button>
              </div>
              {current && current.status === 'promoted' && (
                <p className="text-[11px] text-emerald-300 mt-2">
                  전사 승격됨 · {current.promoted_by} · 승격 시점 게이트 판정이 스냅샷으로
                  보관됩니다.
                </p>
              )}
              {current?.rejected_reason && (
                <p className="text-[11px] text-red-300 mt-2">반려: {current.rejected_reason}</p>
              )}
            </section>

            {/* 운영 준비 (§8.2) — 게이트와 다른 질문이다: "지금 운영에 둘 준비가 됐나" */}
            <section className="border border-slate-700 rounded-lg p-4 bg-slate-900/60">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <h3 className="text-sm font-semibold">
                  운영 준비 체크리스트 (§8.2){' '}
                  {checklist && (
                    <span className={checklist.operations_ready
                      ? 'text-emerald-400' : 'text-red-400'}>
                      {checklist.operations_ready ? '준비됨' : '미준비'}
                    </span>
                  )}
                </h3>
                <label className="text-[11px] text-slate-400 flex items-center gap-1.5">
                  <input type="checkbox" checked={liveIntegration}
                    onChange={(e) => { setLiveIntegration(e.target.checked);
                                       inspect(releaseId, projectId); }} />
                  실운영 연계형 (Shadow Mode 요구)
                </label>
              </div>
              {!checklist && <p className="text-xs text-slate-500 mt-2">
                체크리스트를 불러오지 못했습니다.</p>}
              {checklist && (
                <>
                  <ul className="mt-3 space-y-1.5">
                    {checklist.steps.map((s2: ChecklistStep) => (
                      <li key={s2.step} className="text-xs border border-slate-700 rounded
                                                   px-2 py-1.5">
                        <div className="flex items-center gap-2">
                          <span className={`${STEP_STATE[s2.state]?.cls} shrink-0`}>
                            [{STEP_STATE[s2.state]?.label}]
                          </span>
                          <span className="font-medium">{STEP_LABEL[s2.step] || s2.step}</span>
                        </div>
                        <div className="text-slate-300 mt-0.5">{s2.why}</div>
                        {s2.state !== 'pass' && s2.state !== 'not_required'
                          && s2.suggested_action && (
                          <div className="text-amber-200/90 mt-0.5">→ {s2.suggested_action}</div>
                        )}
                      </li>
                    ))}
                  </ul>
                  <p className="text-[11px] text-slate-500 mt-2">{checklist.note}</p>
                </>
              )}

              {/* 롤백 — 한계를 반드시 함께 보여준다 */}
              <div className="mt-4 border-t border-slate-700 pt-3">
                <h4 className="text-xs font-semibold">운영에서 내리기(롤백)</h4>
                <div className="flex gap-2 mt-2">
                  <input value={rollbackReason}
                    onChange={(e) => setRollbackReason(e.target.value)}
                    placeholder="사유 (필수 — 없으면 같은 문제를 반복한다)"
                    className="flex-1 bg-slate-800 border border-slate-600 rounded px-2 py-1
                               text-xs" />
                  <button
                    onClick={async () => {
                      setMsg(''); setErr('');
                      try {
                        setRollbackOut(await rollbackRelease(releaseId, rollbackReason));
                        setMsg('롤백을 기록했습니다.');
                        await inspect(releaseId, projectId);
                        loadList();
                      } catch (e) {
                        setErr(String(e).replace(/^Error:\s*/, ''));
                      }
                    }}
                    className="px-3 py-1 text-xs bg-red-900/70 hover:bg-red-800/70 rounded">
                    롤백
                  </button>
                </div>
                {rollbackOut && (
                  <div className="mt-2 border border-amber-500/40 bg-amber-500/10 rounded
                                  px-2 py-1.5 text-xs text-amber-100">
                    {rollbackOut.revoked_promotion
                      ? '전사 승격을 철회했습니다. ' : ''}
                    {rollbackOut.limitation}
                  </div>
                )}
              </div>
            </section>

            {/* ④ 공유는 승격과 분리해서 보여준다 */}
            <div className="grid md:grid-cols-2 gap-4">
              <section className="border border-slate-700 rounded-lg p-4 bg-slate-900/60">
                <h3 className="text-sm font-semibold">부서 공유 <span
                  className="text-[11px] font-normal text-slate-400">(승격이 아닙니다)</span></h3>
                <div className="flex gap-2 mt-2">
                  <input value={fromScope} onChange={(e) => setFromScope(e.target.value)}
                    placeholder="소유 조직"
                    className="flex-1 bg-slate-800 border border-slate-600 rounded px-2 py-1
                               text-xs" />
                  <input value={toScope} onChange={(e) => setToScope(e.target.value)}
                    placeholder="공유 대상 조직"
                    className="flex-1 bg-slate-800 border border-slate-600 rounded px-2 py-1
                               text-xs" />
                  <button
                    onClick={() => act(() => createShare({
                      release_id: releaseId, from_scope: fromScope, to_scope: toScope,
                    }), '공유했습니다.')}
                    className="px-3 py-1 text-xs bg-slate-700 rounded">공유</button>
                </div>
                <ul className="mt-2 space-y-1">
                  {shares.map((s) => (
                    <li key={s.share_id} className="text-xs flex items-center justify-between
                                                    gap-2 border border-slate-700 rounded
                                                    px-2 py-1">
                      <span>{s.to_scope} · {s.mode}</span>
                      <button onClick={() => act(() => revokeShare(s.share_id), '회수했습니다.')}
                        className="text-[10px] text-slate-400 hover:text-red-300">회수</button>
                    </li>
                  ))}
                  {shares.length === 0 &&
                    <p className="text-xs text-slate-500">공유 없음</p>}
                </ul>
              </section>

              <section className="border border-slate-700 rounded-lg p-4 bg-slate-900/60">
                <h3 className="text-sm font-semibold">복제(포크) 계보</h3>
                <p className="text-[11px] text-slate-400 mt-1">
                  원본이 바뀌면 아래 프로젝트가 영향을 받습니다.
                </p>
                <ul className="mt-2 space-y-1">
                  {forks.map((f) => (
                    <li key={f.fork_id} className="text-xs border border-slate-700 rounded
                                                   px-2 py-1">
                      {f.new_project_id} <span className="text-slate-400">· {f.owner_scope}</span>
                    </li>
                  ))}
                  {forks.length === 0 && <p className="text-xs text-slate-500">복제 없음</p>}
                </ul>
              </section>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
