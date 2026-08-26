// [이관 F 2/8] 프로그램 사용여부 제어 (사용자 결정 2026-07-30)
//
// 이 화면이 존재하는 이유: 배포된 프로그램을 **지우는 대신 사용만 막는다.**
// 지우면 다른 사용자가 그 프로그램을 근거로 남긴 기록(결재 이력·감사 로그·지식팩 인덱스·
// 파생 프로그램의 출처)이 전부 고아가 된다.
//
// ⚠️ 화면이 판정을 하지 않는다 — 사유 필수·의존 확인·대체본 검증은 모두 서버가 거부하고,
//   이 화면은 그 거부 문구를 **그대로** 보여준다. 화면에서 미리 걸러 예쁘게 만들면
//   서버 규칙과 화면 규칙이 갈라지고, 그때부터 어느 쪽이 진짜인지 알 수 없게 된다.
//
// ## ★ 이 화면이 반드시 구분해야 하는 두 쌍
//
//   ① **«관리자가 사용 가능으로 지정했다» 와 «아무도 지정한 적이 없다»** — `recorded`.
//      같게 표시하면 감사에서 거짓이 된다. (종전 구현도 지키고 있었다. 유지한다.)
//   ② **«영향 없음» 과 «세지 못했다»** — `unmeasured`. 세지 못한 것을 감추면 위험을
//      과소평가하고, 끈 뒤에 끊긴 쪽이 원인을 모른 채 고장난다.
//
// ## 종전 구현에서 제거한 것
//
//   · 자체 `fixed inset-0` 모달 — `role="dialog"`·포커스 트랩·Escape·배경 `inert` 없음
//     → `HubDialog`
//   · 조회 실패를 `data=null` 한 값으로 뭉갠 것 → `Loaded<T>`(권한 없음과 장애를 가른다)
//   · **11px 글자 7곳** → 본문 12px 이상(감사 UIUX-AUDIT-29 ③)
//   · Tailwind 색 직접 지정 → 디자인 토큰(행동색과 상태색을 섞지 않는다)
import { useCallback, useEffect, useState } from 'react';

import { ConfirmInline, useConfirm } from '../design/DataFoundationShell';
import { EmptyOrError, failed, loading, ok, refreshing, type Loaded } from '../design/DataState';
import { HubDialog } from '../design/HubDialog';
import { Banner, Panel, ScreenHead } from '../design/HubShell';
import { reportRequestFailure, reportRequestSuccess } from '../lib/backendHealth';
// ⚠️ 타입은 `import type` 으로 분리한다. 값 import 에 섞으면 esbuild 가 런타임 named import
//   를 남겨 브라우저에서 "does not provide an export named ..." 로 **앱 전체가 백지**가 된다.
//   `tsc --noEmit` 은 이것을 잡지 못했다(실측 2026-07-30) — 그래서 브라우저 확인이 필요하다.
import type { ProgramLifecycle, ProgramStatus } from '../lib/programApi';
import {
  STATUS_LABEL, deprecateProgram, disableProgram, fetchProgram, reactivateProgram,
} from '../lib/programApi';
import { orgApi } from '../lib/orgApi';

type Props = {
  releaseId: string;
  releaseName?: string;
  onClose: () => void;
  onChanged?: () => void;
};

/** 상태 → 칩 색. **상태색이며 행동색이 아니다**(1차 행동은 구조색 Navy). */
const TONE: Record<ProgramStatus, string> = {
  active: 'success', deprecated: 'warn', disabled: 'danger',
};

function localTime(value?: string): string {
  const raw = String(value || '').trim();
  if (!raw) return '시각 미기록';
  // 시간대가 없는 레거시 값은 임의 해석하지 않는다. Z 또는 offset이 있는 값만 현지화한다.
  if (!/(?:Z|[+-]\d\d:\d\d)$/.test(raw)) return raw;
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(date);
}

function actorLabel(actor: string, names: Record<string, string>): string {
  const raw = String(actor || '').trim();
  if (!raw) return '행위자 미기록';
  const local = raw.includes('@') ? raw.split('@', 1)[0] : raw;
  return names[raw] || names[local] || local;
}

function historyStatusLabel(value?: string): string {
  const raw = String(value || '').trim();
  if (!raw) return '미기록';
  const labels: Record<string, string> = {
    active: '사용 중', candidate: '운영 후보', deprecated: '중단 예고', disabled: '사용 중단',
  };
  return labels[raw] || raw;
}

export default function ProgramAdminPanel({ releaseId, releaseName, onClose, onChanged }: Props) {
  const [prog, setProg] = useState<Loaded<ProgramLifecycle>>(loading<ProgramLifecycle>());
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState('');
  const [replacement, setReplacement] = useState('');
  const [ack, setAck] = useState(false);
  const [actorNames, setActorNames] = useState<Record<string, string>>({});

  // ⚠️ 「사용 중단」은 의존 대상을 끊는다 — 누르는 즉시 나가지 않게 화면 안에서 한 번 확인한다
  //   (디자인 시스템 규칙 ②: `alert()`/`confirm()` 을 쓰지 않고 **무엇이 끊기는지** 적는다).
  const confirmDisable = useConfirm<true>();

  const load = useCallback(async () => {
    setErr('');
    // ★ [설계 §6.2] 재조회는 **값을 비우지 않는다** — 행동 뒤 목록이 사라졌다
    //   돌아오면 방금 무엇이 바뀌었는지 비교할 수 없고 스크롤 위치도 잃는다.
    setProg(refreshing);
    try {
      const d = await fetchProgram(releaseId);
      reportRequestSuccess();
      setProg(ok(d));
    } catch (e: any) {
      reportRequestFailure(e?.status);
      // ⚠️ 읽지 못했으면 «사용 중» 이라고 단정하지 않는다. 401/403 은 «없다» 가 아니라 «못 봤다» 다.
      setProg(e?.status === 403 || e?.status === 401
        ? { status: 'forbidden', value: null, error: e?.message || '볼 권한이 없습니다.',
          httpStatus: e.status }
        : failed<ProgramLifecycle>(e));
    }
  }, [releaseId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    // 이름 보강이 실패해도 사용 상태 조회는 그대로 보여 준다. 감사 원문은 title/details에 남는다.
    orgApi.users().then((result) => {
      const mapped: Record<string, string> = {};
      result.rows.forEach((user) => {
        if (!user.user_id || !user.display_name) return;
        mapped[user.user_id] = user.display_name;
        mapped[user.user_id.split('@', 1)[0]] = user.display_name;
      });
      setActorNames(mapped);
    }).catch(() => setActorNames({}));
  }, []);

  const act = async (fn: () => Promise<ProgramLifecycle>) => {
    setBusy(true);
    setErr('');
    try {
      await fn();
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

  const data = prog.value;
  const dep = data?.dependents;

  const headChip = prog.status === 'loading' ? { label: '확인 중', tone: 'muted' as const }
    : prog.status === 'forbidden' ? { label: '권한 없음', tone: 'danger' as const }
      : prog.status === 'error' ? { label: '확인 불가', tone: 'danger' as const }
        : { label: STATUS_LABEL[data!.status], tone: TONE[data!.status] as any };

  return (
    <HubDialog label={`프로그램 사용여부 — ${releaseName || releaseId}`} onClose={onClose}>
      <div className="afs-dialog-bar">
        <b>프로그램 사용여부</b>
        <span>삭제가 아닙니다 — 사용만 막고 기록·이력은 그대로 보존됩니다 (IT 관리자 전용)</span>
        <div className="bar-actions">
          {busy && <span className="busy">변경 중…</span>}
          <button className="secondary-button" onClick={onClose}>
            닫기 <span aria-hidden="true" style={{ opacity: .7 }}>(Esc)</span>
          </button>
        </div>
      </div>

      <div className="afs-dialog-body">
        <div className="hub-main">
          <ScreenHead kicker="프로그램" title={releaseName || releaseId}
            description="배포된 프로그램을 지우는 대신 사용만 막습니다. 지우면 이 프로그램을 근거로 남긴 결재 이력·감사 로그·파생 프로그램의 출처가 전부 고아가 됩니다."
            chip={headChip} />
          <details style={{ marginTop: -8, marginBottom: 14, fontSize: 12 }}>
            <summary className="afs-muted" style={{ cursor: 'pointer' }}>식별 정보</summary>
            <code className="afs-muted" title={releaseId}>{releaseId}</code>
          </details>

          {err && (
            <div style={{ marginBottom: 14 }}>
              {/* 서버 거부 문구를 **그대로** 보여준다 — 줄바꿈을 살려야 의존 목록이 읽힌다. */}
              <Banner tone="error" title="변경하지 못했습니다">
                <span style={{ whiteSpace: 'pre-wrap' }}>{err}</span>
              </Banner>
            </div>
          )}

          <Panel kicker="상태" title="현재 상태">
            <div className="panel-body">
              {prog.status !== 'ok' ? (
                <EmptyOrError state={prog.status} error={prog.error}
                  emptyText="사용여부 기록이 없습니다." onRetry={load} />
              ) : (
                <>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                    <span className={`state-chip ${TONE[data!.status]}`}>
                      {STATUS_LABEL[data!.status]}
                    </span>
                    {/* ★ 추정과 관리자 결정을 구분해 보여준다. 같게 표시하면 감사에서 거짓이 된다. */}
                    {!data!.recorded && (
                      <span className="afs-muted" style={{ fontSize: 12 }}>
                        관리자가 지정한 적 없음 — 사용 가능으로 <b>간주</b>한 상태입니다
                      </span>
                    )}
                  </div>
                  {data!.reason && (
                    <div className="afs-ink" style={{ fontSize: 13 }}>사유: {data!.reason}</div>
                  )}
                  {data!.replacement_release_id && (
                    <div className="afs-info-fg" style={{ fontSize: 13 }}>
                      대체 프로그램: {data!.replacement_release_id}
                    </div>
                  )}
                  {data!.recorded && (
                    <div className="afs-muted" style={{ fontSize: 12 }}>
                      <span title={data!.changed_by}>{actorLabel(data!.changed_by, actorNames)}</span>
                      {' · '}{localTime(data!.changed_at)}
                    </div>
                  )}
                  {data!.note && (
                    <div className="afs-muted" style={{ fontSize: 12 }}>{data!.note}</div>
                  )}
                </>
              )}
            </div>
          </Panel>

          {dep && (
            <div style={{ marginTop: 14 }}>
              <Panel kicker="영향 범위" title="끄면 영향받는 대상">
                <div className="panel-body">
                  <div style={{ fontSize: 13 }}
                    className={dep.blast_radius === 'enterprise' ? 'afs-danger-fg'
                      : dep.blast_radius === 'department' ? 'afs-warn-fg' : 'afs-muted'}>
                    <b>영향 범위: {dep.blast_radius === 'enterprise' ? '전사'
                      : dep.blast_radius === 'department' ? '부서' : '없음'} ({dep.count}건)</b>
                  </div>
                  {dep.is_enterprise && (
                    <div className="afs-danger-fg" style={{ fontSize: 13 }}>
                      · 전사 승격된 프로그램입니다
                    </div>
                  )}
                  {dep.forks.length > 0 && (
                    <div className="afs-ink" style={{ fontSize: 13 }}>
                      · 파생 프로그램: {dep.forks.join(', ')}
                    </div>
                  )}
                  {dep.shared_to.length > 0 && (
                    <div className="afs-ink" style={{ fontSize: 13 }}>
                      · 공유 대상: {dep.shared_to.join(', ')}
                    </div>
                  )}
                  {/* ⚠️ 세지 못한 항목을 감추면 위험을 과소평가한다. */}
                  {dep.unmeasured.length > 0 && (
                    <Banner tone="warn" title="세지 못한 항목이 있습니다">
                      «영향 없음» 이 아닙니다: {dep.unmeasured.join('; ')}
                    </Banner>
                  )}
                </div>
              </Panel>
            </div>
          )}

          <div style={{ marginTop: 14 }}>
            <Panel kicker="상태 변경" title="가능한 변경">
              <div className="panel-body">
                <div>
                  <label htmlFor="pa-reason" className="afs-muted"
                    style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>
                    사유 (중단·예고 시 필수 — 없으면 나중에 아무도 다시 켜지 못합니다)
                  </label>
                  <input id="pa-reason" className="afs-input" style={{ width: '100%' }}
                    value={reason} onChange={(e) => setReason(e.target.value)}
                    placeholder="예: v2 로 이전, 원가 산식 오류 발견" />
                </div>
                <div>
                  <label htmlFor="pa-replacement" className="afs-muted"
                    style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>
                    대체 프로그램 식별자 (선택 — 없으면 사용자는 막다른 길에서 같은 걸 다시 만듭니다)
                  </label>
                  <input id="pa-replacement" className="afs-input" style={{ width: '100%' }}
                    value={replacement} onChange={(e) => setReplacement(e.target.value)}
                    placeholder="예: myapp_20260801_120000" />
                </div>
                <label className="afs-ink"
                  style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 13 }}>
                  <input type="checkbox" checked={ack} style={{ marginTop: 3 }}
                    onChange={(e) => setAck(e.target.checked)} />
                  <span>
                    영향받는 대상을 확인했습니다 (의존 대상이 있을 때 필요합니다 — 확인 없이
                    끄면 끊긴 쪽이 원인을 모른 채 고장납니다)
                  </span>
                </label>

                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  <button className="secondary-button"
                    disabled={busy || prog.status !== 'ok' || data?.status !== 'active'}
                    onClick={() => act(() => deprecateProgram(releaseId, {
                      reason, replacement_release_id: replacement, acknowledge_dependents: ack }))}>
                    ⚠ 중단 예고 (아직 사용 가능)
                  </button>
                  {/* ⚠️ 위험한 행동만 danger 색이다 — 재개까지 색을 주면 구분이 사라진다. */}
                  <button className="danger-solid"
                    disabled={busy || prog.status !== 'ok' || data?.status === 'disabled'}
                    onClick={() => confirmDisable.ask(true)}>
                    ⛔ 사용 중단 (삭제 아님)
                  </button>
                  {/* 재개는 되돌리는 행동이므로 1차 행동(구조색)이다 — 위험색을 주지 않는다. */}
                  <button className="primary-button"
                    disabled={busy || prog.status !== 'ok' || data?.status === 'active'}
                    onClick={() => act(() => reactivateProgram(releaseId, reason))}>
                    ▶ 사용 재개
                  </button>
                </div>

                {/* ★ [설계 §6.5] 운영 중단은 확인 Sheet 대상이다. */}
                <ConfirmInline open={confirmDisable.open}
                  title="이 프로그램을 지금 사용 중단합니다"
                  changes={<>삭제가 아니라 <b>사용만 막습니다</b> — 기록·이력은 그대로 남습니다.</>}
                  affects={<>지금 쓰고 있는 쪽은 <b>즉시</b> 막힙니다
                    {dep ? <> · 영향 {dep.count}건
                      {dep.is_enterprise ? ' · 전사 승격됨' : ''}
                      {dep.unmeasured.length > 0
                        ? ' · ⚠️ 세지 못한 항목이 있어 실제 영향은 더 클 수 있습니다' : ''}</>
                      : <> · ⚠️ 영향 범위를 확인하지 못했습니다(영향이 없다는 뜻이 아닙니다)</>}.</>}
                  reversible={<>«사용 재개» 로 되돌릴 수 있습니다 — 그 사이 멈춘 업무는
                    되돌아오지 않습니다.</>}
                  // ⚠️ 사유 입력란은 위 폼에 있고 **예고(schedule)와 공유**한다. Sheet 안에 또
                  //   두면 같은 값을 두 곳에서 받게 되므로 여기서는 입력한 값을 **확인만** 한다.
                  //   ⚠️ JSX **prop 자리**에는 `{/* */}` 주석을 넣을 수 없다 — 파서가 spread 로
                  //     읽어 빌드가 깨진다(2026-08-09 실측. tsc 는 통과했다).
                  approval={reason.trim()
                    ? <>사유: «{reason.trim()}» — 감사 기록에 남습니다.</>
                    : <b className="afs-danger-fg">사유가 비어 있습니다 — 위 «사유» 란을 채우십시오.
                      없으면 나중에 아무도 다시 켜지 못합니다.</b>}
                  confirmLabel="사용 중단"
                  onCancel={confirmDisable.cancel}
                  onConfirm={() => confirmDisable.run(() => act(() => disableProgram(releaseId, {
                    reason, replacement_release_id: replacement, acknowledge_dependents: ack })))} />
              </div>
            </Panel>
          </div>

          <div style={{ marginTop: 14 }}>
            <Panel kicker="변경 이력" title="변경 이력 (지워지지 않습니다)">
              <div className="panel-body">
                {prog.status !== 'ok' ? (
                  // ★ 조회에 실패했으면 «이력이 없습니다» 로 쓰지 않는다 — 있는데 못 본 것일 수 있다.
                  <EmptyOrError state={prog.status} error={prog.error}
                    emptyText="변경 이력이 없습니다." onRetry={load} />
                ) : !data!.history?.length ? (
                  <p className="afs-muted" style={{ fontSize: 13 }}>변경 이력이 없습니다.</p>
                ) : (
                  data!.history.map((h) => (
                    <div key={h.event_id} className="afs-bg-sunken afs-border"
                      style={{ borderWidth: 1, borderStyle: 'solid', borderRadius: 8,
                        padding: '8px 12px', fontSize: 13 }}>
                      <span className="afs-muted">{localTime(h.at)}</span>
                      {' · '}
                      <b>{historyStatusLabel(h.from_status)}
                        {' → '}{historyStatusLabel(h.to_status)}</b>
                      {' · '}
                      <span className="afs-muted" title={h.actor}>{actorLabel(h.actor, actorNames)}</span>
                      {h.reason && <span className="afs-muted"> — {h.reason}</span>}
                    </div>
                  ))
                )}
              </div>
            </Panel>
          </div>
        </div>
      </div>
    </HubDialog>
  );
}
