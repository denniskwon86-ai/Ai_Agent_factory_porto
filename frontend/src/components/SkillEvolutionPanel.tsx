// [이관 8/10] 스킬 개선안 — 에이전트가 스스로 제안한 행동 규칙을 사람이 검토하는 관문
//
// 에이전트가 작업 중 반복되는 실수를 인식하면 자기 프롬프트 규칙(마크다운)에 넣을 문장을 제안한다.
// 사람이 승인하면 그 문장이 **영구적으로** 스킬 문서에 들어가고, 다음 실행부터 에이전트가 따른다.
//
// ★★★ 이 화면은 «관문»이다. 그래서 두 가지를 반드시 말해야 한다:
//   ① 승인이 **무엇을 영구히 바꾸는지** — 「나중에 되돌리기」가 준비돼 있지 않다.
//   ② 대기열이 **비었는지, 못 봤는지** — 종전 구현은 `if (res.ok)` 만 처리하고 else 를 버려서
//      403 이어도 «제안이 없습니다» 라고 말했다. 검토해야 할 제안을 아무도 보지 못한 채
//      «대기열이 비었다»고 믿게 되고, 그건 관문이 조용히 열린 것과 같다.
//
// ⚠️ 종전 구현에서 제거한 것: 자체 `fixed inset-0` 모달 · `alert()` 4곳 ·
//   실패를 삼키던 `catch { console.error }` · 1차 행동에 쓰인 보라색(구조색 Navy 로 모았다).
import { useCallback, useEffect, useState } from 'react';

import { ConfirmInline, EvidenceStrip, FoundationList, useConfirm, type FoundationRow }
  from '../design/DataFoundationShell';
import { EmptyOrError, Refreshing, Metric, failed, loading, ok, refreshing, type Loaded } from '../design/DataState';
import { HubDialog } from '../design/HubDialog';
import { Banner, HubShell, Panel, ScreenHead, type RailItem } from '../design/HubShell';
import { JarvisRail } from '../design/JarvisRail';
import { actingScope, UNKNOWN_SCOPE, type ActingScope } from '../lib/actingScope';
import { reportRequestFailure, reportRequestSuccess } from '../lib/backendHealth';
import { errorTitle } from '../lib/closedLoopFetch';
import { skillApi, type SkillProposal } from '../lib/skillApi';

export function SkillEvolutionPanel({ onClose, page = false }: { onClose: () => void; page?: boolean }) {
  const [list, setList] = useState<Loaded<SkillProposal[]>>(loading<SkillProposal[]>());
  const [selected, setSelected] = useState('');
  const [scope, setScope] = useState<ActingScope | null>(actingScope.peek());
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<{ msg: string; status?: number } | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const approve = useConfirm<SkillProposal>();
  const reject = useConfirm<SkillProposal>();

  const load = useCallback(async () => {
    // ★ [설계 §6.2] 재조회는 **값을 비우지 않는다** — 행동 뒤 목록이 사라졌다
    //   돌아오면 방금 무엇이 바뀌었는지 비교할 수 없고 스크롤 위치도 잃는다.
    setList(refreshing);
    try {
      const rows = await skillApi.proposals();
      reportRequestSuccess();
      setList(ok(rows));
      setSelected((cur) => (rows.some((r) => r.id === cur) ? cur : rows[0]?.id || ''));
    } catch (e: any) {
      reportRequestFailure(e?.status);
      // ⚠️ 403 은 «없다»가 아니라 «못 봤다»다. 상태를 구분해 담는다.
      setList(e?.status === 403 || e?.status === 401
        ? { status: 'forbidden', value: null, error: e?.message || '볼 권한이 없습니다.',
          httpStatus: e.status }
        : failed<SkillProposal[]>(e));
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { actingScope.load().then(setScope).catch(() => setScope(UNKNOWN_SCOPE)); }, []);
  useEffect(() => actingScope.subscribe(setScope), []);
  useEffect(() => {
    const onUser = () => { setSelected(''); setErr(null); setFlash(null); load(); };
    window.addEventListener('factory:acting-user-changed', onUser);
    return () => window.removeEventListener('factory:acting-user-changed', onUser);
  }, [load]);

  const rows = list.value || [];
  const current = rows.find((r) => r.id === selected) || null;
  const canDecide = Boolean(scope?.canManageStandard || scope?.unrestricted);

  const act = async (label: string, fn: () => Promise<unknown>, note: string) => {
    setBusy(label); setErr(null); setFlash(null);
    try {
      await fn(); reportRequestSuccess(); setFlash(note); setSelected(''); await load();
    } catch (e: any) {
      reportRequestFailure(e?.status);
      setErr({ msg: e?.message || String(e), status: e?.status });
    } finally { setBusy(null); }
  };

  const railItems: RailItem[] = [
    { id: 'queue', label: '승인 대기열', hint: '사람이 봐야 넘어간다', icon: 'checklist',
      // 대기 건수는 «처리해야 할 일»이다 — 배지의 뜻과 맞는다. 0 은 표시하지 않는다.
      count: list.status === 'ok' && rows.length ? rows.length : undefined,
      countLabel: `검토 대기 ${rows.length}건` },
  ];

  const listRows: FoundationRow[] = rows.map((p) => ({
    id: p.id,
    title: p.agent_id,
    meta: `규칙 ${p.proposed_rules?.length ?? 0}개 제안 · `
      + `${p.created_at ? new Date(p.created_at).toLocaleString() : '등록 시각 미상'}`,
    chip: { label: `${p.proposed_rules?.length ?? 0}개 규칙`, tone: 'warn' },
  }));

  return (
    <HubDialog label="AI 스킬 진화 — 에이전트가 제안한 행동 규칙 검토" onClose={onClose} page={page}>
      {!page && <div className="afs-dialog-bar">
        <b>AI 스킬 진화</b>
        <span>승인하면 에이전트의 행동 규칙이 영구히 바뀝니다<Refreshing on={list.refreshing} /></span>
        <div className="bar-actions">
          {busy && <span className="busy">{busy} 중…</span>}
          <button className="secondary-button" onClick={onClose}>
            닫기 <span aria-hidden="true" style={{ opacity: .7 }}>(Esc)</span>
          </button>
        </div>
      </div>}

      <div className="afs-dialog-body">
        <HubShell layoutClassName={page ? 'product-page-shell' : ''}
          kicker="SKILL EVOLUTION" title="승인 대기열"
          subtitle="에이전트가 스스로 제안한 규칙입니다."
          items={railItems} activeId="queue" onSelect={() => { /* 항목이 하나다 */ }}
          footer={
            <div className="inheritance-card">
              <span>PERMANENT</span>
              <b>승인은 영구 반영입니다</b>
              <p>규칙이 스킬 문서에 들어가고 다음 실행부터 적용됩니다. 되돌리는 화면은 아직 없습니다.</p>
            </div>
          }
          jarvis={<JarvisRail
            contextTitle={current ? current.agent_id
              : list.status === 'ok' ? '승인 대기열' : '조회 불가'}
            contextDescription={current
              ? `규칙 ${current.proposed_rules?.length ?? 0}개 제안`
              : list.status === 'ok'
                ? (rows.length ? `검토를 기다리는 제안 ${rows.length}건` : '검토를 기다리는 제안이 없습니다.')
                : '대기열을 가져오지 못했습니다 — «제안 없음»이 아닙니다.'}
            context={{
              current_module: 'skill_evolution/queue',
              selected_object_type: 'skill_proposal',
              selected_object_id: current?.id || '',
              object_snapshot: current
                ? { agent_id: current.agent_id, rules: current.proposed_rules?.length ?? 0 }
                : { load_status: list.status, pending: rows.length },
              // 권한이 없으면 아무 행동도 약속하지 않는다.
              available_actions: canDecide ? ['승인', '거부'] : [],
              evidence_refs: [],
            }}
            evidence={current ? [
              { label: '에이전트', value: current.agent_id },
              { label: '제안 규칙', value: `${current.proposed_rules?.length ?? 0}개` },
              { label: '등록', value: (current.created_at || '').slice(0, 10) || '미상' },
            ] : []}
            quickQuestions={[
              '이 규칙을 승인하면 무엇이 달라집니까?',
              '이 제안은 어떤 실패에서 나왔습니까?',
              '되돌리려면 어떻게 해야 합니까?',
            ]} />}
        >
          {err && <Banner tone="error" title={errorTitle(err.status)}>{err.msg}</Banner>}
          {flash && <Banner tone="info">{flash}</Banner>}
          {!canDecide && list.status === 'ok' && (
            <Banner tone="warn" title="검토만 가능합니다">
              승인·거부 권한이 없습니다. 승인은 에이전트의 행동 규칙을 <b>영구히</b> 바꾸므로
              데이터 관리자·관리자만 할 수 있습니다.
            </Banner>
          )}

          <ScreenHead kicker="SKILL EVOLUTION" title="승인 대기열"
            description="에이전트가 작업 중 인식한 개선점을 규칙 문장으로 제안합니다. 승인하면 스킬 문서에 들어가고 다음 실행부터 적용됩니다."
            chip={list.status !== 'ok'
              ? list.status === 'loading'
                ? { label: '확인 중', tone: 'muted' }
                : { label: list.status === 'forbidden' ? '접근 불가' : '조회 불가', tone: 'danger' }
              : rows.length
                ? { label: `검토 대기 ${rows.length}건`, tone: 'warn' }
                : { label: '대기 없음', tone: 'success' }} />

          <div className="metric-row">
            <Metric label="검토 대기" state={list.status}
              value={list.status === 'ok' ? rows.length : null}
              notes={{ forbidden: '권한 없음', error: '조회 불가', empty: '대기 없음' }}
              hint="사람이 봐야 넘어갑니다" />
            <Metric label="제안 규칙 합계" state={list.status}
              value={list.status === 'ok'
                ? rows.reduce((s, p) => s + (p.proposed_rules?.length ?? 0), 0) : null}
              notes={{ forbidden: '권한 없음', error: '조회 불가', empty: '없음' }} />
            <Metric label="제안한 에이전트" state={list.status}
              value={list.status === 'ok' ? new Set(rows.map((p) => p.agent_id)).size : null}
              notes={{ forbidden: '권한 없음', error: '조회 불가', empty: '없음' }} />
          </div>

          <ConfirmInline open={approve.open}
            title={`«${approve.target?.agent_id || ''}» 의 개선안을 승인합니다`}
            body={<>제안된 규칙이 에이전트의 스킬 문서에 <b>영구히</b> 들어갑니다. 다음 실행부터
              이 에이전트가 그 규칙을 따르며, <b>되돌리는 화면은 아직 없습니다.</b></>}
            confirmLabel="승인 및 적용" danger={false}
            onConfirm={() => approve.run((p) => act('승인', () => skillApi.approve(p.id),
              `«${p.agent_id}» 의 개선안을 승인했습니다 — 스킬 문서에 반영됐습니다.`))}
            onCancel={approve.cancel} />

          <ConfirmInline open={reject.open}
            title={`«${reject.target?.agent_id || ''}» 의 개선안을 거부합니다`}
            body={<>스킬 문서는 <b>바뀌지 않습니다.</b> 제안은 보관소로 옮겨지며, 같은 문제가
              반복되면 에이전트가 다시 제안할 수 있습니다.</>}
            confirmLabel="거부"
            onConfirm={() => reject.run((p) => act('거부', () => skillApi.reject(p.id),
              `«${p.agent_id}» 의 개선안을 거부했습니다 — 스킬 문서는 그대로입니다.`))}
            onCancel={reject.cancel} />

          <div className="inbox-layout">
            <FoundationList state={list} rows={listRows} selectedId={selected}
              onSelect={setSelected} onRetry={load}
              kicker="PENDING" title="검토를 기다리는 제안"
              emptyText={<>검토를 기다리는 제안이 없습니다. 에이전트가 작업 중 개선점을 인식하면
                여기에 등록됩니다.</>} />

            <Panel kicker="PROPOSAL" title={current ? current.agent_id : '제안 상세'}>
              {list.status !== 'ok' ? (
                <EmptyOrError state={list.status} error={list.error}
                  emptyText="대기열을 가져오지 못했습니다 — «제안 없음»이 아닙니다."
                  onRetry={load} />
              ) : !current ? (
                <div className="empty-note">왼쪽에서 제안을 선택하십시오.</div>
              ) : (
                <div style={{ padding: '0 14px 14px' }}>
                  <EvidenceStrip items={[
                    { label: '에이전트', value: current.agent_id },
                    { label: '제안 규칙', value: `${current.proposed_rules?.length ?? 0}개` },
                    { label: '등록', value: current.created_at
                      ? new Date(current.created_at).toLocaleString() : '미상' },
                  ]} note="제안은 에이전트가 스스로 만든 것입니다 — 사람이 확인해야 반영됩니다." />

                  {/* ★ [설계 §5.7 Skill Evolution] 「제안 카드마다 **실패 근거, 현재 규칙,
                      추가 규칙, 영향 Agent, 예상 회귀**를 나란히 표시한다」.
                      ⚠️ 이전에는 자기 진단과 추가 규칙 둘뿐이었다. **현재 규칙을 보지 못하면
                        추가 규칙이 기존 규칙과 충돌하는지 알 수 없고**, 충돌은 승인 뒤
                        에이전트가 이상하게 행동할 때에야 드러난다. */}
                  <div className="section-grid" style={{ marginTop: 12 }}>
                    <section className={current.analysis ? '' : 'missing'}>
                      <h4>실패 근거<em>에이전트의 자기 진단</em></h4>
                      {current.analysis
                        ? <p className="section-text">{current.analysis}</p>
                        : <p className="section-missing">
                            진단이 비어 있습니다 — 근거 없이 규칙을 넣는 것은 위험합니다.
                          </p>}
                    </section>
                  </div>

                  {/* 현재 규칙 ↔ 추가 규칙을 **나란히** 둔다 — 비교가 승인 판단 그 자체다. */}
                  <div className="rule-diff">
                    <section className={current.current_rules_readable === false ? 'missing' : ''}>
                      <h4>현재 규칙<em>{current.skill_file || '대상 파일 미상'}</em></h4>
                      {current.current_rules_readable === false ? (
                        <p className="section-missing">
                          현재 규칙 파일을 읽지 못했습니다 — <b>규칙이 없다는 뜻이 아닙니다.</b>
                          무엇과 합쳐지는지 모르는 상태로는 승인하지 마십시오.
                        </p>
                      ) : current.current_rules?.trim() ? (
                        <pre className="rule-current">{current.current_rules}</pre>
                      ) : (
                        <p className="section-text">
                          이 파일에는 아직 규칙이 없습니다 — 이 제안이 첫 규칙이 됩니다.
                        </p>
                      )}
                    </section>

                    <section className={current.proposed_rules?.length ? '' : 'missing'}>
                      <h4>추가하려는 규칙<em>승인 시 영구 반영</em></h4>
                      {current.proposed_rules?.length ? (
                        <ul className="section-list">
                          {current.proposed_rules.map((rule, i) => (
                            <li key={`${i}-${rule.slice(0, 16)}`}>{rule}</li>
                          ))}
                        </ul>
                      ) : (
                        <p className="section-missing">제안된 규칙이 없습니다 — 승인할 내용이 없습니다.</p>
                      )}
                    </section>
                  </div>

                  <div className="section-grid" style={{ marginTop: 12 }}>
                    <section className={current.affected_agents?.length ? 'missing' : ''}>
                      <h4>영향 Agent<em>같은 스킬 파일을 쓰는 에이전트</em></h4>
                      {current.affected_agents?.length ? (
                        <>
                          <p className="section-text">
                            <b>{current.agent_id}</b> 외에{' '}
                            <b>{current.affected_agents.join(', ')}</b> 도 같은 파일을 씁니다 —
                            승인하면 <b>{current.affected_agents.length + 1}개 에이전트</b>의
                            행동이 함께 바뀝니다.
                          </p>
                          {/* 예상 회귀 — ⚠️ 회귀를 실제로 재현해 보는 경로가 없다. 없는 수치를
                              지어내는 대신 **무엇을 모르는지** 적는다. */}
                          <p className="section-missing">
                            예상 회귀: 이 시스템에는 규칙 변경을 되돌려 검증하는 경로가 아직
                            없습니다 — 반영 뒤 위 에이전트들의 산출물을 직접 확인하십시오.
                          </p>
                        </>
                      ) : (
                        <p className="section-text">
                          <b>{current.agent_id}</b> 만 이 파일을 씁니다 — 다른 에이전트에는
                          영향이 없습니다.
                        </p>
                      )}
                    </section>
                  </div>

                  {canDecide ? (
                    <div style={{ display: 'flex', gap: 7, marginTop: 14, justifyContent: 'flex-end' }}>
                      <button className="danger-ghost" disabled={!!busy}
                        onClick={() => reject.ask(current)}>거부</button>
                      <button className="primary-button"
                        disabled={!!busy || !current.proposed_rules?.length}
                        onClick={() => approve.ask(current)}>승인 및 적용</button>
                    </div>
                  ) : (
                    <p className="hint-line">
                      승인·거부 권한이 없습니다 — 데이터 관리자에게 검토를 요청하십시오.
                    </p>
                  )}
                </div>
              )}
            </Panel>
          </div>
        </HubShell>
      </div>
    </HubDialog>
  );
}
