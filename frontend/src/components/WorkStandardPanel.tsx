// [이관 3/10] 업무표준 — 에이전트가 따르는 «법규·사규»
//
// 각 단계의 에이전트가 무엇을 어떤 기준으로 판정해 다음 단계로 넘기는지를 정의한 제도 문서다.
// 저장소는 M1 기준정보(master.db)이며 개정 시 새 버전이 생기고 구판은 리니지로 보존된다.
//   · 업무규정(regulation) — 판정 에이전트. 통과/반려 권한이 있다.
//   · 업무지침(guideline)  — 생성 에이전트. 작성 표준을 따르며 판정 권한이 없다.
//
// ★★ 이 화면이 지키는 것(이관 완료 조건):
//   ① 사용자 용어만 노출한다. `RFP` · `regulation` · `active` 같은 내부 값은 `design/terms.ts`
//      사전을 거친다. 단, `STD-QA` 처럼 **실제 식별자**는 그대로 둔다 — 사용자도 그 문자열로 찾는다.
//   ② Jarvis 는 **실제로 가능한 행동만** 안내한다(`actingScope`). 읽기 상태만 보고 판단하지
//      않는다 — 읽기는 되고 쓰기는 안 되는 사용자가 대다수다.
//   ③ 조회 실패 · 자료 없음 · 미지정을 각각 구분한다. 실패를 «없습니다»로 쓰지 않는다.
//
// ⚠️ 종전 구현에서 제거한 것:
//   · 자체 `API_BASE_URL` 선언과 직접 `fetch` → 공용 어댑터(`lib/standardApi.ts`)
//   · `confirm()` → 화면 안 확인(`ConfirmInline`). 브라우저 대화상자는 키보드·스크린리더·스타일
//     모두 대응이 안 되고 승인 시안에도 없다.
//   · 손으로 만든 `fixed inset-0` 모달 → `HubDialog`(포커스 트랩·Escape·배경 inert·스크롤 잠금)
//   · `Number(std.pass_threshold) * gateW` → 임계값이 없으면 NaN 이 화면에 찍혔다. 상태를 구분한다.
import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  ConfirmInline, EvidenceStrip, FoundationList, FoundationToolbar, VersionHistory, useConfirm,
  type FoundationRow,
} from '../design/DataFoundationShell';
import { EmptyOrError, Metric, failed, loading, ok, type Loaded } from '../design/DataState';
import { useLatestOnly } from '../design/useLatestOnly';
import { HubDialog } from '../design/HubDialog';
import { Banner, HubShell, Panel, ScreenHead, type RailItem } from '../design/HubShell';
import { JarvisRail } from '../design/JarvisRail';
import {
  agentKo, checkTypeKo, recordStatusKo, stageKo, standardKindKo, standardSourceKo,
} from '../design/terms';
import { actingScope, UNKNOWN_SCOPE, type ActingScope } from '../lib/actingScope';
import { reportRequestFailure, reportRequestSuccess } from '../lib/backendHealth';
import { errorTitle } from '../lib/closedLoopFetch';
import {
  standardApi, type HistoryRow, type StandardCheck, type StandardDetail, type StandardRow,
} from '../lib/standardApi';

type View = 'regulation' | 'guideline' | 'history' | 'brief';

const MODULE: Record<View, { kicker: string; title: string; subtitle: string; desc: string }> = {
  regulation: {
    kicker: 'REGULATION', title: '업무규정',
    subtitle: '앞 단계 산출물을 받아 통과·반려를 정합니다.',
    desc: '판정 권한이 있는 단계입니다. 통과선에 못 미치면 다음 단계로 넘어가지 않습니다.',
  },
  guideline: {
    kicker: 'GUIDELINE', title: '업무지침',
    subtitle: '산출물을 만드는 단계의 작성 표준입니다.',
    desc: '판정 권한이 없습니다. 스스로 점검하고, 판정은 뒤의 규정 단계가 합니다.',
  },
  history: {
    kicker: 'LINEAGE', title: '개정 연혁',
    subtitle: '언제 무엇이 바뀌었는지 봅니다.',
    desc: '개정은 구판을 지우지 않습니다. 지난 산출물의 판정 근거는 그때의 버전입니다.',
  },
  brief: {
    kicker: 'AGENT BRIEF', title: '에이전트 고지문',
    subtitle: '에이전트가 실제로 받는 문장 그대로입니다.',
    desc: '화면에 보기 좋게 정리한 것이 아니라, 모델에게 전달되는 원문입니다.',
  },
};

export function WorkStandardPanel({ onClose }: { onClose: () => void }) {
  //: [설계 §6.1] 늦게 온 응답을 버리는 표 — 다른 것을 고른 뒤 옛 응답이 그려지지 않게.
  const claim = useLatestOnly();
  const [view, setView] = useState<View>('regulation');
  const [list, setList] = useState<Loaded<StandardRow[]>>(loading<StandardRow[]>());
  const [selectedStage, setSelectedStage] = useState('');
  const [detail, setDetail] = useState<Loaded<StandardDetail | null>>(ok(null));
  const [hist, setHist] = useState<Loaded<HistoryRow[]>>(ok<HistoryRow[]>([]));
  const [search, setSearch] = useState('');
  const [scope, setScope] = useState<ActingScope | null>(actingScope.peek());
  const [err, setErr] = useState<{ msg: string; status?: number } | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const reseed = useConfirm<string>();

  // ── 조회 ────────────────────────────────────────────────────────────────
  const loadList = useCallback(async () => {
    setList(loading<StandardRow[]>());
    try {
      const r = await standardApi.list();
      reportRequestSuccess();
      // ⚠️ 차단은 «실패»가 아니라 «권한 없음»이다. 상태를 구분해 담는다 —
      //   같은 코드로 흘리면 화면이 "조회 실패"라고 말하고 사용자는 재시도만 반복한다.
      setList(r.blockedReason
        ? { status: 'forbidden', value: null, error: r.blockedReason, httpStatus: 403 }
        : ok(r.rows));
    } catch (e: any) {
      setList(failed<StandardRow[]>(e)); reportRequestFailure(e?.status);
    }
  }, []);

  const loadDetail = useCallback(async (stage: string) => {
    if (!stage) { setDetail(ok(null)); setHist(ok<HistoryRow[]>([])); return; }
    const isCurrent = claim();   // §6.1 — 요청 직전에 표를 뽑는다
    setDetail(loading<StandardDetail | null>());
    setHist(loading<HistoryRow[]>());
    // ⚠️ 두 조회를 **따로** 담는다. 이력 조회가 실패했다고 본문까지 «없음»으로 만들지 않는다.
    const [d, h] = await Promise.allSettled([
      standardApi.detail(stage), standardApi.history(stage),
    ]);
    // ★ [§6.1] 단계를 연달아 고르면 다른 단계의 표준 본문이 그려질 수 있다.
    if (!isCurrent()) return;
    if (d.status === 'fulfilled') { setDetail(ok(d.value)); reportRequestSuccess(); }
    else {
      setDetail(failed<StandardDetail | null>(d.reason));
      reportRequestFailure((d.reason as any)?.status);
    }
    setHist(h.status === 'fulfilled' ? ok(h.value) : failed<HistoryRow[]>(h.reason));
  }, []);

  useEffect(() => { loadList(); }, [loadList]);
  useEffect(() => { actingScope.load().then(setScope).catch(() => setScope(UNKNOWN_SCOPE)); }, []);
  useEffect(() => actingScope.subscribe(setScope), []);

  // 사용자가 바뀌면 이전 사용자의 목록·상세를 즉시 버린다 — 권한 범위가 다르다.
  useEffect(() => {
    const onUser = () => {
      setSelectedStage(''); setDetail(ok(null)); setHist(ok<HistoryRow[]>([]));
      setErr(null); setFlash(null); loadList();
      actingScope.load().then(setScope).catch(() => setScope(UNKNOWN_SCOPE));
    };
    window.addEventListener('factory:acting-user-changed', onUser);
    return () => window.removeEventListener('factory:acting-user-changed', onUser);
  }, [loadList]);

  // ── 파생 ────────────────────────────────────────────────────────────────
  const rows = list.value || [];
  const kindOfView = view === 'guideline' ? 'guideline' : 'regulation';
  const listKind = view === 'regulation' || view === 'guideline' ? kindOfView : '';
  const shown = useMemo(() => {
    const base = listKind ? rows.filter((r) => r.kind === listKind) : rows;
    const q = search.trim().toLowerCase();
    if (!q) return base;
    // 사용자는 한국어 단계명으로도 찾는다. 영문 코드만 검색하면 «없다»가 나온다.
    return base.filter((r) => `${stageKo(r.stage)} ${r.stage} ${r.master_code} ${agentKo(r.agent_id)}`
      .toLowerCase().includes(q));
  }, [rows, listKind, search]);

  const selected = rows.find((r) => r.stage === selectedStage) || null;
  const std = detail.value?.standard || null;
  const checks: StandardCheck[] = std?.checks || [];
  const gate = checks.filter((c) => !c.advisory);
  const advisory = checks.filter((c) => c.advisory);
  const gateWeight = gate.reduce((s, c) => s + Number(c.weight ?? 1), 0);
  const threshold = std?.pass_threshold;
  const hasThreshold = typeof threshold === 'number' && Number.isFinite(threshold);

  const canRevise = Boolean(scope?.canManageStandard || scope?.unrestricted);
  const railItems: RailItem[] = [
    // ⚠️ 단계 수를 count 배지로 쓰지 않는다. 셸의 배지는 빨강이고 «처리해야 할 N건»으로
    //   읽힌다(협업 화면의 대기 건수와 같은 모양이다). 규정 4개는 처리 대기가 아니라 구성이다.
    //   개수는 위 지표와 목록 자체가 말한다.
    { id: 'regulation', label: '업무규정', hint: '통과·반려를 정한다', icon: 'standard' },
    { id: 'guideline', label: '업무지침', hint: '판정 권한이 없다', icon: 'checklist' },
    { id: 'history', label: '개정 연혁', hint: '구판은 보존된다', icon: 'revise' },
    { id: 'brief', label: '에이전트 고지문', hint: '모델이 받는 원문', icon: 'inject' },
  ];

  // ★★ 완료 조건 ②: 권한이 **있는 사람에게만** 행동을 안내한다. 권한을 모르는 동안(`scope`
  //   가 아직 null)에는 아무것도 약속하지 않는다 — 그 짧은 순간에 눌러도 403 이다.
  const jarvisActions = canRevise ? ['개정 등록', '기본값 재시드'] : [];
  const jarvisContext = {
    current_module: `work_standard/${view}`,
    selected_object_type: 'work_standard',
    selected_object_id: selected?.master_code || '',
    object_snapshot: selected
      ? {
        stage: selected.stage, kind: selected.kind, version: selected.version,
        gate_count: selected.gate_count, advisory_count: selected.advisory_count,
        pass_threshold: selected.pass_threshold,
      }
      : { load_status: list.status, total: rows.length },
    available_actions: jarvisActions,
    evidence_refs: selected ? [{ master_code: selected.master_code, version: selected.version }] : [],
  };

  const jarvisTitle = selected
    ? `${stageKo(selected.stage)} ${standardKindKo(selected.kind)}`
    : list.status === 'ok' ? MODULE[view].title : '조회 불가';
  const jarvisDesc = selected
    ? `${selected.master_code} · v${selected.version} · 관문 ${selected.gate_count}개`
    : list.status === 'ok'
      ? '왼쪽에서 단계를 고르면 그 표준을 문맥으로 씁니다.'
      : '업무표준 목록을 가져오지 못했습니다 — «없다»가 아닙니다.';

  const selectStage = (stage: string) => { setSelectedStage(stage); loadDetail(stage); };

  const doReseed = async () => {
    setBusy('재시드'); setErr(null); setFlash(null);
    try {
      const r = await standardApi.reseed();
      reportRequestSuccess();
      setFlash(`코드 기본값에서 재등록했습니다. 구판은 보존됩니다. (${JSON.stringify(r)})`);
      await loadList();
      if (selectedStage) await loadDetail(selectedStage);
    } catch (e: any) {
      reportRequestFailure(e?.status);
      setErr({ msg: e?.message || String(e), status: e?.status });
    } finally { setBusy(null); }
  };

  const listRows: FoundationRow[] = shown.map((r) => ({
    id: r.stage,
    title: stageKo(r.stage),
    meta: `${r.master_code} · v${r.version} · ${r.agent_id ? agentKo(r.agent_id) : '담당 미지정'}`,
    // ★ 관문 0개는 «반려 권한 없음»이라는 중요한 사실이다. 조용히 0 으로 두지 않는다.
    chip: r.gate_count === 0
      ? { label: '반려 권한 없음', tone: 'warn' }
      : { label: `관문 ${r.gate_count}개`, tone: 'data' },
  }));

  return (
    <HubDialog label="업무표준 — 에이전트가 따르는 판정 기준" onClose={onClose}>
      <div className="afs-dialog-bar">
        <b>업무표준</b>
        <span>에이전트가 무엇을 보고 통과를 정하는지가 여기 적혀 있습니다</span>
        <div className="bar-actions">
          {busy && <span className="busy">{busy} 중…</span>}
          <button className="secondary-button" onClick={onClose}>
            닫기 <span aria-hidden="true" style={{ opacity: .7 }}>(Esc)</span>
          </button>
        </div>
      </div>

      <div className="afs-dialog-body">
        <HubShell
          kicker={MODULE[view].kicker} title={MODULE[view].title} subtitle={MODULE[view].subtitle}
          items={railItems} activeId={view} onSelect={(id) => setView(id as View)}
          footer={
            <div className="inheritance-card">
              <span>LINEAGE</span>
              <b>개정은 구판을 지우지 않습니다</b>
              <p>지난 산출물의 판정 근거는 그때 시행 중이던 버전입니다.</p>
            </div>
          }
          jarvis={<JarvisRail contextTitle={jarvisTitle} contextDescription={jarvisDesc}
            context={jarvisContext}
            evidence={selected ? [
              { label: '표준 코드', value: selected.master_code },
              { label: '버전', value: `v${selected.version}` },
              { label: '효력', value: recordStatusKo(selected.status) },
            ] : []}
            quickQuestions={[
              '이 단계는 무엇을 보고 통과를 정합니까?',
              '이 항목이 미달이면 어떻게 됩니까?',
              '지난 버전과 무엇이 달라졌습니까?',
            ]} />}
        >
          {err && <Banner tone="error" title={errorTitle(err.status)}>{err.msg}</Banner>}
          {flash && <Banner tone="info">{flash}</Banner>}

          <ScreenHead kicker={MODULE[view].kicker} title={MODULE[view].title}
            description={MODULE[view].desc}
            chip={list.status !== 'ok'
              ? list.status === 'loading'
                ? { label: '확인 중', tone: 'muted' }
                : { label: list.status === 'forbidden' ? '접근 불가' : '조회 불가', tone: 'danger' }
              : { label: `${rows.length}개 단계`, tone: rows.length ? 'data' : 'muted' }} />

          <div className="metric-row">
            <Metric label="규정 단계" state={list.status}
              value={list.status === 'ok' ? rows.filter((r) => r.kind === 'regulation').length : null}
              hint="통과·반려 권한 있음" />
            <Metric label="지침 단계" state={list.status}
              value={list.status === 'ok' ? rows.filter((r) => r.kind === 'guideline').length : null}
              hint="판정 권한 없음" />
            <Metric label="선택 단계 관문" state={detail.status}
              value={std ? gate.length : null}
              notes={{ loading: '표준 조회 중', error: '표준 조회 불가',
                forbidden: '표준 조회 불가', empty: '단계 미선택' }} />
            {/* ⚠️ 임계값이 없을 때 «0» 을 쓰지 않는다 — 0 은 «무엇이든 통과»로 읽힌다. */}
            <Metric label="통과선" state={detail.status}
              value={std && hasThreshold
                ? `${(Number(threshold) * gateWeight).toFixed(1)} / ${gateWeight}` : null}
              notes={{ loading: '표준 조회 중', error: '표준 조회 불가',
                forbidden: '표준 조회 불가',
                empty: std ? '통과선 미지정' : '단계 미선택' }} />
          </div>

          {(view === 'regulation' || view === 'guideline') && (
            <>
              <FoundationToolbar search={search} onSearch={setSearch}
                placeholder="단계명·표준 코드·담당으로 찾기"
                actions={canRevise ? (
                  <button className="secondary-button" disabled={!!busy}
                    onClick={() => reseed.ask('all')}>기본값 재시드</button>
                ) : undefined}
                /* ⚠️ 세 갈래를 구분한다. 익명에게 «조회만 가능합니다» 라고 쓰면 거짓이다 —
                   조회 자체가 막혀 있다(실측에서 그렇게 나왔다). 목록이 차단된 상태에서는
                   아래 카드가 이미 이유를 말하므로 여기서 덧붙이지 않는다. */
                hint={list.status !== 'ok' ? undefined
                  : canRevise
                    ? '재시드는 코드 기본값에서 전 단계를 새 버전으로 등록합니다. 구판은 보존됩니다.'
                    : '개정 권한이 없어 조회만 가능합니다 — 변경은 데이터 관리자에게 요청하십시오.'} />

              <ConfirmInline open={reseed.open}
                title="코드 기본값에서 전 단계를 재등록합니다"
                body={<>지금 시행 중인 개정본은 <b>구판으로 보존</b>되고 새 버전이 시행됩니다.
                  판정 기준이 바뀌므로 이후 산출물의 통과·반려가 달라질 수 있습니다.</>}
                confirmLabel="재시드 실행"
                onConfirm={() => reseed.run(doReseed)} onCancel={reseed.cancel} />

              <div className="inbox-layout">
                <FoundationList state={list} rows={listRows} selectedId={selectedStage}
                  onSelect={selectStage} onRetry={loadList}
                  kicker={kindOfView === 'regulation' ? 'REGULATIONS' : 'GUIDELINES'}
                  title={`등록된 ${MODULE[view].title}`}
                  emptyText={search
                    ? `«${search}» 와 일치하는 단계가 없습니다. 검색어를 지우면 전체를 봅니다.`
                    : `등록된 ${MODULE[view].title}이 없습니다.`} />

                <Panel kicker="STANDARD" title={selected ? stageKo(selected.stage) : '단계 상세'}>
                  {/* ⚠️ `EmptyOrError` 를 무조건 렌더링하지 않는다. 종전에는 정상 조회에도 «가져오지
                      못했습니다» 가 원문 **바로 위에** 함께 떠서 서로 모순됐다(실측). 상태별로
                      정확히 하나만 말한다: 미선택 · 실패·차단 · 표준 없음 · 정상. */}
                  {!selectedStage ? (
                    <div className="empty-note">왼쪽에서 단계를 선택하십시오.</div>
                  ) : detail.status !== 'ok' ? (
                    <EmptyOrError state={detail.status} error={detail.error}
                      emptyText="이 단계의 표준 원문을 가져오지 못했습니다."
                      onRetry={() => loadDetail(selectedStage)} />
                  ) : !std ? (
                    <div className="empty-note">
                      이 단계에는 등록된 표준이 없습니다 — 코드 기본값도 찾지 못했습니다.
                    </div>
                  ) : null}
                  {std && (
                    <div style={{ padding: '0 14px 14px' }}>
                      <EvidenceStrip items={[
                        { label: '표준 코드', value: std._meta?.master_code || '미상' },
                        { label: '버전', value: std._meta?.version ? `v${std._meta.version}` : '미상' },
                        { label: '출처', value: standardSourceKo(std._meta?.source || '') },
                      ]} note="출처가 «코드 기본값»이면 아직 사람이 개정하지 않은 상태입니다." />

                      {std.role_statement && <Field label="이 단계의 역할" value={std.role_statement} />}
                      {std.standard_kind === 'guideline' ? (
                        <>
                          {std.inputs && <Field label="입력(근거)" value={std.inputs} />}
                          {std.deliverable && <Field label="산출물" value={std.deliverable} />}
                          <ListBlock title="반드시 포함할 것" items={std.must_include} />
                          <ListBlock title="작성 원칙" items={std.principles} />
                        </>
                      ) : (
                        std.evaluates && <Field label="평가 대상" value={std.evaluates} />
                      )}

                      {gate.length > 0 ? (
                        <CheckTable
                          title={std.standard_kind === 'guideline'
                            ? '자가 점검 항목' : '통과·반려를 결정하는 항목'}
                          note={hasThreshold
                            ? `통과선 ${(Number(threshold) * gateWeight).toFixed(1)} / ${gateWeight}`
                            : '통과선이 지정되지 않았습니다'}
                          checks={gate} hardFail={std.hard_fail_checks || []} />
                      ) : (
                        <Banner tone="warn" title="이 단계는 관문이 아닙니다">
                          반려 권한이 없으며 권고 의견만 남깁니다. 판정은 뒤의 규정 단계가 합니다.
                        </Banner>
                      )}

                      {advisory.length > 0 && (
                        <CheckTable title="참고 항목" note="반려 사유가 아닙니다 — 리포트로만 전달"
                          checks={advisory} hardFail={[]} />
                      )}

                      <ListBlock title="금지 사항" items={std.must_not} danger />
                    </div>
                  )}
                </Panel>
              </div>
            </>
          )}

          {view === 'history' && (
            <Panel kicker="LINEAGE" title={selected ? `${stageKo(selected.stage)} 개정 연혁` : '개정 연혁'}>
              {!selectedStage ? (
                <div className="empty-note">
                  «업무규정» 또는 «업무지침» 에서 단계를 먼저 선택하십시오 — 연혁은 단계별로 봅니다.
                </div>
              ) : hist.status !== 'ok' ? (
                <EmptyOrError state={hist.status} error={hist.error}
                  emptyText="이 단계의 개정 연혁을 가져오지 못했습니다."
                  onRetry={() => loadDetail(selectedStage)} />
              ) : (
                <div style={{ padding: 12 }}>
                  <VersionHistory
                    rows={(hist.value || []).map((h) => ({
                      id: `v${h.version}`,
                      version: `v${h.version}`,
                      at: (h.valid_from || '').slice(0, 10) || '시행일 미기재',
                      actor: standardSourceKo(h.source || ''),
                      summary: historySummary(h, hist.value || []),
                    }))}
                    emptyText="개정 연혁이 없습니다 — 아직 한 번도 개정되지 않았습니다." />
                </div>
              )}
            </Panel>
          )}

          {view === 'brief' && (
            <Panel kicker="AGENT BRIEF"
              title={selected ? `${stageKo(selected.stage)} 고지문` : '에이전트 고지문'}>
              {!selectedStage ? (
                <div className="empty-note">
                  «업무규정» 또는 «업무지침» 에서 단계를 먼저 선택하십시오.
                </div>
              ) : detail.status !== 'ok' ? (
                <EmptyOrError state={detail.status} error={detail.error}
                  emptyText="고지문을 가져오지 못했습니다."
                  onRetry={() => loadDetail(selectedStage)} />
              ) : !detail.value?.agent_brief ? (
                <div className="empty-note">
                  이 단계에는 고지문이 만들어지지 않았습니다 — 표준이 등록되지 않은 상태입니다.
                </div>
              ) : (
                <div style={{ padding: 12 }}>
                  <p className="hint-line">
                    아래는 <b>모델에게 전달되는 원문</b>입니다. 화면용으로 다시 쓴 것이 아닙니다.
                  </p>
                  <pre className="mdm-preview-block">{detail.value.agent_brief}</pre>
                </div>
              )}
            </Panel>
          )}
        </HubShell>
      </div>
    </HubDialog>
  );
}

/** 연혁 한 줄의 뜻. ★★ 이 저장소는 개정할 때 구판을 `status='retired'` 로 스탬프한다
 *  (`core/master_data.py` — 물리 삭제를 하지 않는다). 그래서 `retired` 는 **두 가지를 겸한다**:
 *  «개정으로 대체된 구판»과 «시행 중인 버전이 없는 폐지». 둘을 같은 «폐지»로 쓰면, v2 가
 *  시행 중인데도 사용자는 이 표준이 더는 쓰이지 않는다고 읽는다(실측에서 그렇게 보였다).
 *  ⚠️ 백엔드 값을 바꾸지 않는다 — 저장소 계약이고 다른 조회 경로가 그 값을 쓴다.
 *    구분은 «더 높은 버전이 존재하는가»라는 사실로 화면에서 판단한다. */
function historySummary(h: HistoryRow, all: HistoryRow[]): string {
  if (h.status === 'active' && !h.valid_to) return '시행 중';
  const supersededBy = all.find((x) => x.version > h.version);
  const until = h.valid_to ? `${(h.valid_to || '').slice(0, 10)} 까지 시행` : '';
  if (supersededBy) {
    return `개정으로 대체(구판) · v${supersededBy.version} 로 교체${until ? ` · ${until}` : ''}`;
  }
  // 뒤에 버전이 없는데 시행 중이 아니다 = 지금 시행 중인 표준이 없다. 그건 경고할 사실이다.
  return `폐지 — 시행 중인 버전이 없습니다${until ? ` · ${until}` : ''}`;
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ marginTop: 12 }}>
      <span className="field-label">{label}</span>
      <p className="section-text">{value}</p>
    </div>
  );
}

function ListBlock({ title, items, danger }: { title: string; items?: string[]; danger?: boolean }) {
  // ⚠️ 빈 목록을 숨기지 않는다 — 숨기면 «금지 사항이 검토됐다»고 믿는다(승인 시안 §비어 있는 섹션).
  return (
    <div className="section-grid" style={{ marginTop: 12 }}>
      <section className={items && items.length ? '' : 'missing'}>
        <h4>{danger ? `⚠️ ${title}` : title}</h4>
        {items && items.length ? (
          <ul className="section-list">{items.map((m, i) => <li key={`${i}-${m.slice(0, 12)}`}>{m}</li>)}</ul>
        ) : (
          <p className="section-missing">이 표준에는 «{title}» 이 적혀 있지 않습니다.</p>
        )}
      </section>
    </div>
  );
}

function CheckTable({ title, note, checks, hardFail }: {
  title: string; note: string; checks: StandardCheck[]; hardFail: string[];
}) {
  return (
    <div className="section-grid" style={{ marginTop: 12 }}>
      <section>
        <h4>{title}<em>{note}</em></h4>
        <ul className="section-list">
          {checks.map((c) => (
            <li key={c.id}>
              {/* `c.id` 는 **실제 식별자**다(리포트·로그에 같은 문자열로 남는다) — 번역하지 않는다. */}
              <b>{c.id}</b>
              <span> 가중치 {c.weight ?? 1} · {checkTypeKo(c.type || '')}</span>
              {hardFail.includes(c.id) && <span> · <b>미달 시 즉시 차단</b></span>}
              <div className="section-text">{c.desc || '설명이 적혀 있지 않습니다.'}</div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
