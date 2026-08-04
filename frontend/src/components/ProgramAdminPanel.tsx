// 프로그램 사용여부 제어 (사용자 결정 2026-07-30)
//
// 이 화면이 존재하는 이유: 배포된 프로그램을 **지우는 대신 사용만 막는다.**
// 지우면 다른 사용자가 그 프로그램을 근거로 남긴 기록(결재 이력·감사 로그·지식팩 인덱스·
// 파생 프로그램의 출처)이 전부 고아가 된다.
//
// ⚠️ 화면이 판정을 하지 않는다 — 사유 필수·의존 확인·대체본 검증은 모두 서버가 거부하고,
//   이 화면은 그 거부 문구를 **그대로** 보여준다. 화면에서 미리 걸러 예쁘게 만들면
//   서버 규칙과 화면 규칙이 갈라지고, 그때부터 어느 쪽이 진짜인지 알 수 없게 된다.
import { useCallback, useEffect, useState } from 'react';
// ⚠️ 타입은 `import type` 으로 분리한다. 값 import 에 섞으면 esbuild 가 런타임 named import
//   를 남겨 브라우저에서 "does not provide an export named ..." 로 **앱 전체가 백지**가 된다.
//   `tsc --noEmit` 은 이것을 잡지 못했다(실측 2026-07-30) — 그래서 브라우저 확인이 필요하다.
import type { ProgramLifecycle, ProgramStatus } from '../lib/programApi';
import {
  STATUS_LABEL, deprecateProgram, disableProgram, fetchProgram, reactivateProgram,
} from '../lib/programApi';

type Props = {
  releaseId: string;
  releaseName?: string;
  onClose: () => void;
  onChanged?: () => void;
};

const BADGE: Record<ProgramStatus, string> = {
  active: 'bg-emerald-900/40 text-emerald-300 border-emerald-700/60',
  deprecated: 'bg-amber-900/40 text-amber-300 border-amber-700/60',
  disabled: 'bg-red-950/50 text-red-300 border-red-800/60',
};

export default function ProgramAdminPanel({ releaseId, releaseName, onClose, onChanged }: Props) {
  const [data, setData] = useState<ProgramLifecycle | null>(null);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState('');
  const [replacement, setReplacement] = useState('');
  const [ack, setAck] = useState(false);

  const load = useCallback(async () => {
    setErr('');
    try {
      setData(await fetchProgram(releaseId));
    } catch (e: any) {
      setErr(e?.message || '사용여부를 읽지 못했습니다.');
      setData(null);   // 읽지 못했으면 "사용 중"이라고 단정하지 않는다.
    }
  }, [releaseId]);

  useEffect(() => { load(); }, [load]);

  const act = async (fn: () => Promise<ProgramLifecycle>) => {
    setBusy(true);
    setErr('');
    try {
      setData(await fn());
      setReason('');
      setAck(false);
      onChanged?.();
      await load();
    } catch (e: any) {
      // 서버 거부 문구를 그대로 보여준다 — 의존 목록·대체본 사유가 그 안에 들어 있다.
      setErr(e?.message || '변경에 실패했습니다.');
    } finally {
      setBusy(false);
    }
  };

  const dep = data?.dependents;

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-6">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-3xl max-h-[88vh] overflow-y-auto shadow-2xl">
        <header className="sticky top-0 bg-gray-900 border-b border-gray-700 px-6 py-4 flex items-center justify-between">
          <div className="min-w-0">
            <h2 className="text-lg font-bold text-gray-100 truncate">
              ⚙ 프로그램 사용여부 — {releaseName || releaseId}
            </h2>
            <p className="text-[11px] text-gray-500 mt-0.5">
              삭제가 아닙니다. 사용만 막고 기록·이력은 그대로 보존됩니다. (IT 관리자 전용)
            </p>
          </div>
          <button onClick={onClose}
                  className="text-sm text-gray-400 hover:text-gray-100 bg-gray-800 px-3 py-1.5 rounded shrink-0">
            닫기
          </button>
        </header>

        <div className="p-6 space-y-5">
          {err && (
            <div className="bg-red-950/40 border border-red-800/60 rounded-lg p-3 text-[13px] text-red-200 whitespace-pre-wrap">
              {err}
            </div>
          )}

          {/* 현재 상태 */}
          <section>
            <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wide mb-2">현재 상태</h3>
            {!data ? (
              <div className="text-sm text-gray-500">확인하지 못했습니다.</div>
            ) : (
              <div className="bg-gray-950 border border-gray-700 rounded-lg p-4 space-y-2">
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-bold px-2 py-1 rounded border ${BADGE[data.status]}`}>
                    {STATUS_LABEL[data.status]}
                  </span>
                  {/* ★ 추정과 관리자 결정을 구분해 보여준다. 같게 표시하면 감사에서 거짓이 된다. */}
                  {!data.recorded && (
                    <span className="text-[11px] text-gray-500">
                      관리자가 지정한 적 없음 — 사용 가능으로 <b>간주</b>한 상태입니다
                    </span>
                  )}
                </div>
                {data.reason && (
                  <div className="text-[13px] text-gray-300">사유: {data.reason}</div>
                )}
                {data.replacement_release_id && (
                  <div className="text-[13px] text-indigo-300">
                    대체 프로그램: {data.replacement_release_id}
                  </div>
                )}
                {data.recorded && (
                  <div className="text-[11px] text-gray-500">
                    {data.changed_by} · {data.changed_at}
                  </div>
                )}
                {data.note && <div className="text-[11px] text-gray-500">{data.note}</div>}
              </div>
            )}
          </section>

          {/* 영향 범위 */}
          {dep && (
            <section>
              <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wide mb-2">
                끄면 영향받는 대상
              </h3>
              <div className="bg-gray-950 border border-gray-700 rounded-lg p-4 text-[13px] space-y-1">
                <div className={dep.blast_radius === 'enterprise' ? 'text-red-300 font-bold'
                              : dep.blast_radius === 'department' ? 'text-amber-300' : 'text-gray-400'}>
                  영향 범위: {dep.blast_radius === 'enterprise' ? '전사'
                            : dep.blast_radius === 'department' ? '부서' : '없음'} ({dep.count}건)
                </div>
                {dep.is_enterprise && <div className="text-red-300">· 전사 승격된 프로그램입니다</div>}
                {dep.forks.length > 0 && (
                  <div className="text-gray-300">· 파생 프로그램: {dep.forks.join(', ')}</div>
                )}
                {dep.shared_to.length > 0 && (
                  <div className="text-gray-300">· 공유 대상: {dep.shared_to.join(', ')}</div>
                )}
                {/* ⚠️ 세지 못한 항목을 감추면 위험을 과소평가한다. */}
                {dep.unmeasured.length > 0 && (
                  <div className="text-amber-300">
                    ⚠️ 세지 못한 항목이 있습니다 — 영향 없음이 아닙니다: {dep.unmeasured.join('; ')}
                  </div>
                )}
              </div>
            </section>
          )}

          {/* 변경 */}
          <section>
            <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wide mb-2">변경</h3>
            <div className="space-y-3">
              <div>
                <label className="block text-[11px] text-gray-400 mb-1">
                  사유 (중단·예고 시 필수 — 없으면 나중에 아무도 다시 켜지 못합니다)
                </label>
                <input value={reason} onChange={(e) => setReason(e.target.value)}
                       placeholder="예: v2 로 이전, 원가 산식 오류 발견"
                       className="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:border-indigo-500 outline-none" />
              </div>
              <div>
                <label className="block text-[11px] text-gray-400 mb-1">
                  대체 프로그램 release_id (선택 — 없으면 사용자는 막다른 길에서 같은 걸 다시 만듭니다)
                </label>
                <input value={replacement} onChange={(e) => setReplacement(e.target.value)}
                       placeholder="예: myapp_20260801_120000"
                       className="w-full bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:border-indigo-500 outline-none" />
              </div>
              <label className="flex items-start gap-2 text-[12px] text-gray-400">
                <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)}
                       className="mt-0.5" />
                <span>
                  영향받는 대상을 확인했습니다 (의존 대상이 있을 때 필요합니다 — 확인 없이
                  끄면 끊긴 쪽이 원인을 모른 채 고장납니다)
                </span>
              </label>

              <div className="flex flex-wrap gap-2 pt-1">
                <button disabled={busy}
                        onClick={() => act(() => deprecateProgram(releaseId, {
                          reason, replacement_release_id: replacement, acknowledge_dependents: ack }))}
                        className="text-sm font-bold text-amber-200 bg-amber-900/40 hover:bg-amber-800/60 border border-amber-700/60 px-4 py-2 rounded-lg disabled:opacity-40">
                  ⚠ 중단 예고 (아직 사용 가능)
                </button>
                <button disabled={busy}
                        onClick={() => act(() => disableProgram(releaseId, {
                          reason, replacement_release_id: replacement, acknowledge_dependents: ack }))}
                        className="text-sm font-bold text-red-200 bg-red-950/50 hover:bg-red-900/60 border border-red-800/60 px-4 py-2 rounded-lg disabled:opacity-40">
                  ⛔ 사용 중단 (삭제 아님)
                </button>
                <button disabled={busy}
                        onClick={() => act(() => reactivateProgram(releaseId, reason))}
                        className="text-sm font-bold text-emerald-200 bg-emerald-900/40 hover:bg-emerald-800/60 border border-emerald-700/60 px-4 py-2 rounded-lg disabled:opacity-40">
                  ▶ 사용 재개
                </button>
              </div>
            </div>
          </section>

          {/* 이력 — append-only */}
          <section>
            <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wide mb-2">
              변경 이력 (지워지지 않습니다)
            </h3>
            {!data?.history?.length ? (
              <div className="text-sm text-gray-500">변경 이력이 없습니다.</div>
            ) : (
              <div className="space-y-1">
                {data.history.map((h) => (
                  <div key={h.event_id}
                       className="bg-gray-950 border border-gray-700 rounded-lg px-3 py-2 text-[12px] text-gray-300">
                    <span className="text-gray-500">{h.at}</span>
                    {' · '}
                    <b>{h.from_status || '(미기록)'} → {h.to_status}</b>
                    {' · '}
                    <span className="text-gray-400">{h.actor}</span>
                    {h.reason && <span className="text-gray-400"> — {h.reason}</span>}
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
