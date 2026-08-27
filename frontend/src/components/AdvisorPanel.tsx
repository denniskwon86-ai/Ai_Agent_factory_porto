import { useCallback, useEffect, useMemo, useState } from 'react';

import { ConfirmInline, useConfirm } from '../design/DataFoundationShell';
import { EmptyOrError, failed, ok, type Loaded } from '../design/DataState';
import { HubDialog } from '../design/HubDialog';
import { HubShell, type RailItem } from '../design/HubShell';
import { JarvisRail } from '../design/JarvisRail';
import {
  advisorApi, DATA_KIND_KO, NECESSITY_KO, REQ_STATUS_KO, REQ_TYPE_KO,
  type Blueprint, type Consultation, type LedgerEvent, type PlaybookSummary,
  type Progress, type Question, type Readiness, type ReqStatus,
} from '../lib/advisorApi';

// 업무·데이터 설계 상담사 (마스터 명세서 §4 / M0)
//
// ⚠️ 이 화면의 목적은 **디자인 완성도가 아니라 M0 기능 전체를 조작·확인할 수 있는 상태**다.
//   디자인 시안 확정 후 대대적으로 개편할 예정이므로:
//    · 데이터 획득·호출은 전부 `lib/advisorApi.ts` 에 있고 여기에는 없다(그 파일은 개편 후에도 재사용).
//    · 기존 패널(TelemetryPanel 등)의 다크 모달 패턴과 클래스를 그대로 쓴다. 새 디자인 언어를 만들지 않는다.
//    · 4단계를 한 패널에서 순서대로 보여준다(§4.4 대화/상담결과/데이터/실행 보드).
//
// 한 화면에서 M0-a~e 전부를 확인할 수 있다:
//   플레이북 선택 → 선택형 상담 → 준비도 → Blueprint 초안 → 승인 → 프로젝트 생성 → 결정 이력

type Step = 'pick' | 'interview' | 'status' | 'blueprint';

// ★ [이관 F 8/8] 화면 전체의 색을 이 네 상수로 모은다 — 92곳에 흩어져 있던 회색 팔레트
//   직접 지정을 디자인 토큰으로 옮긴다. 여기만 바꾸면 나머지가 따라온다.
const CARD = 'afs-bg-card afs-border';
const BTN_PRIMARY = 'primary-button';
const BTN_DANGER = 'danger-solid';
const BTN_GHOST = 'secondary-button';

/** 준비도 5축 막대. 측정되지 않은 축은 **만점이 아니라 '미측정'** 으로 표시한다. */
function ReadinessBoard({ r }: { r: Readiness }) {
  return (
    <div className={`${CARD} p-4`}>
      <div className="flex items-baseline gap-3 mb-3">
        <span className="text-xs afs-muted">데이터 준비도</span>
        <span className="text-2xl font-bold afs-ink">{r.score}</span>
        <span className="text-xs afs-muted">/ 100</span>
        {r.unmeasured_weight > 0 && (
          <span className="text-xs afs-warn-fg">
            ⚠️ {r.unmeasured_weight}점 구간 미측정 (플레이북에 해당 축 요구사항이 없음)
          </span>
        )}
      </div>
      <div className="space-y-1.5">
        {r.dimensions.map((d) => (
          <div key={d.dimension} className="flex items-center gap-2">
            <span className="text-xs afs-muted w-40 shrink-0">{d.name_ko}</span>
            <div className="flex-1 afs-bg-sunken rounded h-4 overflow-hidden border afs-border">
              <div
                className={`h-full ${d.measured ? 'afs-success-bg' : 'afs-bg-raised'}`}
                style={{ width: `${d.weight ? Math.max(2, (d.score / d.weight) * 100) : 2}%` }}
              />
            </div>
            <span className="text-xs afs-muted w-20 text-right tabular-nums">
              {d.score.toFixed(1)}/{d.weight}
            </span>
            {!d.measured && <span className="text-xs afs-muted">미측정</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

/** 결손 목록. §4.3 F-DA-05 — 점수와 함께 **결손·영향·다음 조치**를 반드시 함께 보여준다. */
function GapList({ gaps, title }: { gaps: Readiness['gaps']; title: string }) {
  if (!gaps.length) return null;
  return (
    <div className={`${CARD} p-4`}>
      <h4 className="text-sm font-bold afs-warn-fg mb-2">{title} <span className="afs-muted font-normal">({gaps.length}건)</span></h4>
      <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
        {gaps.map((g) => (
          <div key={g.key} className="text-xs border-l-2 border-amber-700/60 pl-2.5 py-0.5">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="font-bold afs-ink">{g.canonical_term}</span>
              <span className="text-xs px-1.5 py-0.5 rounded afs-bg-raised afs-muted">
                {NECESSITY_KO[g.necessity] || g.necessity}
              </span>
              <span className="text-xs px-1.5 py-0.5 rounded afs-bg-raised afs-muted">
                {REQ_STATUS_KO[g.status as ReqStatus] || g.status}
              </span>
              {g.owner_department && (
                <span className="text-xs afs-info-fg">담당 {g.owner_department}</span>
              )}
              {!g.counts_toward_score && (
                <span className="text-xs afs-muted">점수 미반영</span>
              )}
            </div>
            {g.impact && <div className="afs-muted mt-0.5">없으면: {g.impact}</div>}
            {g.next_action && <div className="afs-success-fg mt-0.5">조치: {g.next_action}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}

export function AdvisorPanel(
  { onClose, onProjectCreated }: { onClose: () => void; onProjectCreated?: () => void },
) {
  const [step, setStep] = useState<Step>('pick');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const [playbooks, setPlaybooks] = useState<PlaybookSummary[]>([]);
  const [recent, setRecent] = useState<Consultation[]>([]);
  const [recentFailed, setRecentFailed] = useState(false);
  const [playbookId, setPlaybookId] = useState('');
  const [prompt, setPrompt] = useState('');

  const [consultation, setConsultation] = useState<Consultation | null>(null);
  const [question, setQuestion] = useState<Question | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [preview, setPreview] = useState<Readiness | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [freeText, setFreeText] = useState('');
  const [asked, setAsked] = useState<{ q: Question; chosen: string[] }[]>([]);

  const [statuses, setStatuses] = useState<Record<string, ReqStatus>>({});
  const [blueprint, setBlueprint] = useState<Blueprint | null>(null);
  // ★★ 결정 이력은 «왜 이렇게 됐는지» 의 근거다. 종전에는 `.catch(() => [])` 로 받아
  //   조회 실패가 «이력 없음» 이 됐고, 그러면 그 구획이 통째로 사라져 사용자는 근거가
  //   **원래 없는 줄** 안다. 감사 자리에서 가장 나쁜 형태의 침묵이다.
  const [ledger, setLedger] = useState<Loaded<LedgerEvent[]>>(ok<LedgerEvent[]>([]));
  const [projectId, setProjectId] = useState('');
  const [notice, setNotice] = useState('');
  const [rejectReason, setRejectReason] = useState('');

  // ⚠️ 승인은 «미확보 필수 데이터를 안고» 진행될 수 있다 — 그 사실을 **승인 후**가 아니라
  //   승인 전에 보여준다(종전에는 완료 문구로만 알려줬다).
  const confirmApprove = useConfirm<true>();

  /** 결정 이력 조회. **실패를 «이력 없음» 으로 바꾸지 않는다.** */
  const loadLedger = useCallback(async (bpId: string): Promise<Loaded<LedgerEvent[]>> => {
    try {
      return ok(await advisorApi.ledgerHistory(bpId));
    } catch (e: any) {
      return e?.status === 403 || e?.status === 401
        ? { status: 'forbidden', value: null, error: e?.message || '볼 권한이 없습니다.',
          httpStatus: e.status }
        : failed<LedgerEvent[]>(e);
    }
  }, []);

  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | null> => {
    setBusy(true); setErr('');
    try { return await fn(); }
    catch (e: any) { setErr(e?.message || '알 수 없는 오류'); return null; }
    finally { setBusy(false); }
  }, []);

  useEffect(() => {
    run(async () => {
      const [pbs, cons] = await Promise.all([
        advisorApi.listPlaybooks(), advisorApi.listConsultations().catch(() => null),
      ]);
      setPlaybooks(pbs);
      // ⚠️ `null` 은 «못 읽었다» 다 — 빈 배열(«없다»)과 구분한다.
      setRecentFailed(cons === null);
      setRecent((cons || []).slice(0, 8));
      if (pbs.length && !playbookId) setPlaybookId(pbs[0].playbook_id);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 질문이 바뀌면 추천안을 기본 선택으로 — §4.3 F-DA-02 "추천안만 선택해도 진행 가능"
  useEffect(() => {
    if (!question) { setPicked([]); return; }
    const rec = question.options.find((o) => o.recommended);
    setPicked(rec ? [rec.value] : []);
    setFreeText('');
  }, [question?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const startConsultation = () =>
    run(async () => {
      const r = await advisorApi.start(prompt, playbookId);
      setConsultation(r.consultation);
      setQuestion(r.next_question);
      setProgress(r.progress);
      setAsked([]); setPreview(null); setBlueprint(null); setLedger(ok<LedgerEvent[]>([]));
      setStep('interview');
    });

  const resume = (id: string) =>
    run(async () => {
      const r = await advisorApi.get(id);
      setConsultation(r.consultation);
      setQuestion(r.next_question);
      setProgress(r.progress);
      setAsked([]);
      if (r.blueprints?.length) {
        const bp = await advisorApi.getBlueprint(r.blueprints[0].blueprint_id);
        setBlueprint(bp);
        setLedger(await loadLedger(bp.blueprint_id));
        setStep('blueprint');
      } else {
        setStep(r.next_question ? 'interview' : 'status');
      }
    });

  const submitAnswer = () =>
    run(async () => {
      if (!consultation || !question) return;
      const cur = question;
      const r = await advisorApi.answer(consultation.consultation_id, cur.id, picked, freeText);
      setAsked((prev) => [...prev, { q: cur, chosen: picked }]);
      setQuestion(r.next_question);
      setProgress(r.progress);
      setPreview(r.readiness_preview);
      if (!r.next_question) {
        // 답변이 끝나면 데이터 보유 상태 입력으로 넘어간다. 초기값은 전부 '부족' —
        // 모르는 것을 보유로 치지 않는다(백엔드 기본값과 동일).
        const init: Record<string, ReqStatus> = {};
        (r.readiness_preview?.gaps || []).forEach((g) => { init[g.key] = 'missing'; });
        setStatuses(init);
        setStep('status');
      }
    });

  const draft = () =>
    run(async () => {
      if (!consultation) return;
      const bp = await advisorApi.draftBlueprint(consultation.consultation_id, statuses);
      setBlueprint(bp);
      setLedger(ok<LedgerEvent[]>([]));
      setStep('blueprint');
    });

  const decide = (decision: 'approved' | 'rejected') =>
    run(async () => {
      if (!blueprint) return;
      const r = await advisorApi.decide(blueprint.blueprint_id, decision, rejectReason);
      const fresh = await advisorApi.getBlueprint(blueprint.blueprint_id);
      setBlueprint(fresh);
      setLedger(await loadLedger(blueprint.blueprint_id));
      setNotice(
        decision === 'approved'
          ? `승인 완료. ${r.approved_with_blocking_gaps.length
              ? `⚠️ 미확보 필수 데이터 ${r.approved_with_blocking_gaps.length}건을 안고 승인했습니다: ${r.approved_with_blocking_gaps.join(', ')}`
              : '차단 결손 없음.'}`
          : '반려 처리했습니다.');
    });

  const bootstrap = () =>
    run(async () => {
      if (!blueprint) return;
      const r = await advisorApi.bootstrapProject(blueprint.blueprint_id, projectId.trim());
      setLedger(await loadLedger(blueprint.blueprint_id));
      // ⚠️ 런처의 프로젝트 목록은 마운트 시점에 한 번만 불린다. 여기서 갱신을 알리지 않으면
      //   상담으로 만든 프로젝트가 목록에 나타나지 않아 사용자가 "안 만들어졌나?" 하고 혼란한다
      //   (실측으로 발견 — 백엔드에는 있는데 화면에만 없었다).
      onProjectCreated?.();
      setNotice(`프로젝트 '${r.project_id}' 생성 완료 (템플릿 ${r.template_id}). ${r.next_step}`);
    });

  const dataTasks = () =>
    run(async () => {
      if (!blueprint) return;
      const r = await advisorApi.createDataTasks(blueprint.blueprint_id, projectId.trim());
      setLedger(await loadLedger(blueprint.blueprint_id));
      setNotice(r.created.length
        ? `데이터 준비 태스크 ${r.created.length}건을 WBS에 추가했습니다: ${r.created.map((t) => t.task_id).join(', ')}`
        : (r.message || '추가할 미확보 데이터가 없습니다.'));
    });

  const gapsForStatus = preview?.gaps || [];
  const selectedPlaybook = useMemo(
    () => playbooks.find((p) => p.playbook_id === playbookId), [playbooks, playbookId]);

  const railItems: RailItem[] = [
    { id: 'pick', label: '업무 선택', hint: '목표와 상담 유형을 고릅니다', icon: 'apps' },
    { id: 'interview', label: '선택형 상담',
      hint: consultation ? '선택한 조건을 구체화합니다' : '업무 선택 후 열립니다', icon: 'inbox',
      count: progress?.total ? Math.max(progress.total - progress.answered, 0) : undefined,
      countLabel: progress?.total ? `남은 질문 ${Math.max(progress.total - progress.answered, 0)}건` : undefined },
    { id: 'status', label: '데이터 보유 확인',
      hint: preview ? '보유·검증필요·부족을 구분합니다' : '상담 완료 후 열립니다', icon: 'checklist',
      count: preview?.gaps?.length || undefined,
      countLabel: preview?.gaps?.length ? `확인할 데이터 ${preview.gaps.length}건` : undefined },
    { id: 'blueprint', label: '청사진·승인·생성',
      hint: blueprint ? '승인 근거와 생성 결과를 확인합니다' : '데이터 확인 후 열립니다', icon: 'standard' },
  ];

  const selectRailStep = (id: string) => {
    const next = id as Step;
    const available = next === 'pick'
      || (next === 'interview' && !!consultation)
      || (next === 'status' && !!preview)
      || (next === 'blueprint' && !!blueprint);
    if (available) {
      setStep(next);
      return;
    }
    setNotice(next === 'interview'
      ? '업무를 선택하고 상담을 시작하면 열립니다.'
      : next === 'status'
        ? '선택형 상담을 마치면 데이터 보유 상태를 확인할 수 있습니다.'
        : '데이터 보유 상태를 확인해 청사진을 만든 뒤 열립니다.');
  };

  const selectedObjectId = blueprint?.blueprint_id || consultation?.consultation_id || playbookId;
  const jarvisTitle = blueprint?.title || question?.question || selectedPlaybook?.name_ko
    || '상담할 업무를 선택하십시오';
  const jarvisDescription = step === 'pick'
    ? '업무 목적과 필요한 데이터의 범위를 정하는 단계입니다.'
    : step === 'interview'
      ? `선택형 질문 ${progress?.answered || 0}/${progress?.total || 0}에 답하고 있습니다.`
      : step === 'status'
        ? '보유·검증 필요·부족을 구분해야 준비도가 실제보다 높게 보이지 않습니다.'
        : '청사진의 범위·제외 범위·데이터 결손과 승인 근거를 검토합니다.';

  return (
    <HubDialog label="업무·데이터 설계 상담 — 무엇을 만들지와 어떤 데이터가 필요한지" onClose={onClose}>
      <div className="afs-dialog-bar">
        <b>업무·데이터 설계 상담</b>
        <span>선택형 대화로 정하고, 승인하면 프로젝트가 됩니다</span>
        <div className="bar-actions">
          {busy && <span className="busy">처리 중…</span>}
          <button className="secondary-button" onClick={onClose}>
            닫기 <span aria-hidden="true" style={{ opacity: .7 }}>(Esc)</span>
          </button>
        </div>
      </div>

      <div className="afs-dialog-body">
        <HubShell
          kicker="BUSINESS & DATA DESIGN"
          title="업무·데이터 설계 상담"
          subtitle="필요한 데이터와 추진 순서를 선택형 대화로 정합니다"
          items={railItems}
          activeId={step}
          onSelect={selectRailStep}
          footer={
            <div className="inheritance-card">
              <span>현재 진행</span>
              <b>{railItems.find((item) => item.id === step)?.label}</b>
              <p>{progress
                ? `질문 ${progress.answered}/${progress.total} · 답하지 않은 항목은 보유로 간주하지 않습니다.`
                : '선택과 승인 결과는 회사·조직·REAL/VIRTUAL 문맥에 결속됩니다.'}</p>
            </div>
          }
          jarvis={<JarvisRail
            contextKicker="현재 상담 문맥"
            contextTitle={jarvisTitle}
            contextDescription={jarvisDescription}
            context={{
              current_module: `advisor/${step}`,
              selected_object_type: blueprint ? 'solution_blueprint'
                : consultation ? 'advisor_consultation' : 'advisor_playbook',
              selected_object_id: selectedObjectId,
              object_snapshot: {
                step,
                readiness_score: blueprint?.readiness?.score ?? preview?.score ?? null,
                blocking_gap_count: blueprint?.readiness?.blocking_gaps?.length
                  ?? preview?.blocking_gaps?.length ?? null,
                blueprint_status: blueprint?.status ?? null,
              },
              available_actions: step === 'pick'
                ? ['업무 선택', '상담 시작']
                : step === 'interview'
                  ? ['질문 답변', '준비도 미리보기']
                  : step === 'status'
                    ? ['보유 상태 확인', '청사진 만들기']
                    : ['범위 검토', '승인·반려', '프로젝트 생성'],
              evidence_refs: ledger.status === 'ok'
                ? (ledger.value || []).map((event) => ({
                    event_id: event.event_id,
                    event_type: event.event_type,
                    created_at: event.created_at,
                  })) : [],
            }}
            evidence={[
              { label: '진행 단계', value: railItems.find((item) => item.id === step)?.label || step },
              ...(progress ? [{ label: '상담 진행', value: `${progress.answered}/${progress.total}` }] : []),
              ...(blueprint ? [{ label: '준비도', value: `${blueprint.readiness.score}/100` }] : []),
            ]}
            quickQuestions={[
              '이 단계에서 반드시 결정할 것은 무엇입니까?',
              '아직 확인하지 못한 데이터는 무엇입니까?',
              '다음 단계로 가기 전에 누가 승인해야 합니까?',
            ]} />}
        >
        <div className="space-y-5">
          {err && (
            <div className="bg-red-950/60 border border-red-800 rounded-lg px-4 py-3 text-sm text-red-200">
              ⚠️ {err}
            </div>
          )}
          {notice && (
            <div className="bg-emerald-950/50 border border-emerald-800 rounded-lg px-4 py-3 text-sm text-emerald-200 flex justify-between gap-3">
              <span>{notice}</span>
              <button onClick={() => setNotice('')} className="text-emerald-500 hover:afs-success-fg shrink-0">✕</button>
            </div>
          )}

          {/* ── 1. 업무 선택 ── */}
          {step === 'pick' && (
            <>
              <div className={`${CARD} p-5`}>
                <h3 className="text-sm font-bold afs-action-fg mb-3">어떤 업무를 하시려나요?</h3>
                <div className="space-y-2">
                  {playbooks.map((pb) => (
                    <label key={pb.playbook_id}
                      className={`block border rounded-lg p-3 cursor-pointer transition-colors ${
                        playbookId === pb.playbook_id
                          ? 'afs-action-border afs-info-bg'
                          : 'afs-border afs-hover-border'}`}>
                      <div className="flex items-start gap-2">
                        <input type="radio" checked={playbookId === pb.playbook_id}
                          onChange={() => setPlaybookId(pb.playbook_id)} className="mt-1" />
                        <div className="min-w-0">
                          <div className="text-sm font-bold afs-ink">{pb.name_ko}</div>
                          <div className="text-xs afs-muted mt-1">{pb.description}</div>
                          <div className="text-xs afs-muted mt-1">
                            질문 {pb.question_count}개 · 데이터 요구 {pb.requirement_count}건
                            {pb.recommended_template_id && ` · 추천 워크플로우 ${pb.recommended_template_id}`}
                          </div>
                        </div>
                      </div>
                    </label>
                  ))}
                  {!playbooks.length && !busy && (
                    <div className="text-sm afs-muted">등록된 플레이북이 없습니다.</div>
                  )}
                </div>
              </div>

              <div className={`${CARD} p-5`}>
                <h3 className="text-sm font-bold afs-ink mb-2">
                  하시려는 일을 자유롭게 적어 주세요 <span className="afs-muted font-normal">(선택 — 비워도 진행됩니다)</span>
                </h3>
                <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3}
                  placeholder="예) 내년도 사업계획 데이터를 만들고 부서별로 승인받고 싶습니다."
                  className="w-full afs-bg-sunken border afs-border rounded-lg p-3 text-sm afs-ink  focus:outline-none " />
                <div className="flex justify-end mt-3">
                  <button onClick={startConsultation} disabled={busy || !playbookId} className={BTN_PRIMARY}>
                    상담 시작 {selectedPlaybook ? `· ${selectedPlaybook.name_ko}` : ''}
                  </button>
                </div>
              </div>

              {recentFailed && (
                <p className="afs-warn-fg" style={{ fontSize: 13 }}>
                  ⚠️ 최근 상담 목록을 불러오지 못했습니다 — <b>«상담 기록이 없다» 는 뜻이
                  아닙니다.</b> 이어서 할 상담이 있어도 여기 보이지 않습니다.
                </p>
              )}
              {!!recent.length && (
                <div className={`${CARD} p-4`}>
                  <h3 className="text-sm font-bold afs-muted mb-2">이어서 하기</h3>
                  <div className="space-y-1">
                    {recent.map((c) => (
                      <button key={c.consultation_id} onClick={() => resume(c.consultation_id)}
                        className="w-full text-left text-xs px-3 py-2 rounded hover:bg-white/5 flex items-center gap-2">
                        <span className="afs-ink truncate flex-1">
                          {c.initial_prompt || '(입력 없음)'}
                        </span>
                        <span className="text-xs afs-muted">{c.playbook_id}</span>
                        <span className="text-xs px-1.5 py-0.5 rounded afs-bg-raised afs-muted">{c.status}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

          {/* ── 2. 선택형 상담 (§4.4 대화 영역) ── */}
          {step === 'interview' && question && (
            <>
              {!!asked.length && (
                <div className={`${CARD} p-4`}>
                  <h4 className="text-xs font-bold afs-muted mb-2">지금까지 정한 것</h4>
                  <div className="space-y-1">
                    {asked.map(({ q, chosen }) => (
                      <div key={q.id} className="text-xs flex gap-2">
                        <span className="afs-muted shrink-0">{q.question}</span>
                        <span className="afs-success-fg">
                          {q.options.filter((o) => chosen.includes(o.value)).map((o) => o.label).join(', ') || '선택 없음'}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className={`${CARD} p-5`}>
                <div className="text-xs afs-muted mb-1">{question.stage}</div>
                <h3 className="text-base font-bold afs-ink">{question.question}</h3>
                {question.why && <p className="text-xs afs-muted mt-1">{question.why}</p>}

                <div className="space-y-2 mt-4">
                  {question.options.map((o) => {
                    const on = picked.includes(o.value);
                    return (
                      <label key={o.value}
                        className={`block border rounded-lg p-3 cursor-pointer transition-colors ${
                          on ? 'afs-action-border afs-info-bg' : 'afs-border afs-hover-border'}`}>
                        <div className="flex items-start gap-2">
                          <input
                            type={question.multi ? 'checkbox' : 'radio'} checked={on} className="mt-1"
                            onChange={() => setPicked((prev) => question.multi
                              ? (prev.includes(o.value) ? prev.filter((v) => v !== o.value) : [...prev, o.value])
                              : [o.value])} />
                          <div className="min-w-0">
                            <div className="text-sm afs-ink flex items-center gap-2">
                              {o.label}
                              {o.recommended && (
                                <span className="text-xs px-1.5 py-0.5 rounded afs-info-bg afs-action-fg">추천</span>
                              )}
                            </div>
                            {o.description && <div className="text-xs afs-muted mt-0.5">{o.description}</div>}
                          </div>
                        </div>
                      </label>
                    );
                  })}
                </div>

                <div className="mt-3">
                  <input value={freeText} onChange={(e) => setFreeText(e.target.value)}
                    placeholder="직접 입력 (선택 — 적어두면 청사진의 문제 기술에 함께 남습니다)"
                    className="w-full afs-bg-sunken border afs-border rounded px-3 py-2 text-xs afs-ink  focus:outline-none " />
                </div>

                <div className="flex justify-end mt-4">
                  <button onClick={submitAnswer} disabled={busy || (!picked.length && !freeText.trim())}
                    className={BTN_PRIMARY}>다음</button>
                </div>
              </div>

              {preview && (
                <div>
                  <div className="text-xs afs-muted mb-1">
                    현재 준비도 미리보기 — 보유 상태를 아직 확인하지 않았으므로 <b>하한</b>입니다
                  </div>
                  <ReadinessBoard r={preview} />
                </div>
              )}
            </>
          )}

          {/* ── 3. 데이터 보유 확인 (§4.4 데이터 보드) ── */}
          {step === 'status' && (
            <>
              <div className={`${CARD} p-5`}>
                <h3 className="text-sm font-bold afs-action-fg mb-1">이 데이터들을 지금 갖고 계신가요?</h3>
                <p className="text-xs afs-muted mb-4">
                  모르는 항목은 <b>부족</b>으로 둡니다 — 모르는 것을 보유로 치면 준비도가 실제보다 높게 나옵니다.
                </p>
                <div className="space-y-1.5 max-h-[46vh] overflow-y-auto pr-1">
                  {gapsForStatus.map((g) => (
                    <div key={g.key} className="flex items-center gap-2 border-b afs-border pb-1.5">
                      <div className="min-w-0 flex-1">
                        <div className="text-xs afs-ink flex items-center gap-1.5 flex-wrap">
                          {g.canonical_term}
                          <span className="text-xs px-1.5 py-0.5 rounded afs-bg-raised afs-muted">
                            {NECESSITY_KO[g.necessity] || g.necessity}
                          </span>
                          <span className="text-xs px-1.5 py-0.5 rounded afs-bg-raised afs-muted">
                            {REQ_TYPE_KO[g.requirement_type] || g.requirement_type}
                          </span>
                          {g.owner_department && <span className="text-xs afs-info-fg">담당 {g.owner_department}</span>}
                        </div>
                      </div>
                      <div className="flex gap-1 shrink-0">
                        {(['held', 'needs_verification', 'missing'] as ReqStatus[]).map((s) => (
                          <button key={s} onClick={() => setStatuses((p) => ({ ...p, [g.key]: s }))}
                            className={`text-xs px-2 py-1 rounded border ${
                              (statuses[g.key] || 'missing') === s
                                ? 'primary-button'
                                : 'afs-border afs-muted afs-hover-border'}`}>
                            {REQ_STATUS_KO[s]}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                  {!gapsForStatus.length && (
                    <div className="text-sm afs-muted">확인할 데이터 요구사항이 없습니다.</div>
                  )}
                </div>
                <div className="flex justify-between items-center mt-4">
                  <button onClick={() => setStep('interview')} className={BTN_GHOST}>◀ 상담으로</button>
                  <button onClick={draft} disabled={busy} className={BTN_PRIMARY}>청사진 만들기</button>
                </div>
              </div>
            </>
          )}

          {/* ── 4. 청사진 · 승인 · 생성 (§4.4 상담결과/실행 보드) ── */}
          {step === 'blueprint' && blueprint && (
            <>
              <div className={`${CARD} p-5`}>
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="min-w-0">
                    <h3 className="text-base font-bold afs-ink">{blueprint.title}</h3>
                    <div className="text-xs afs-muted mt-0.5">
                      {blueprint.blueprint_id} · v{blueprint.version} · {blueprint.playbook_id}
                      {' · '}문맥 {blueprint.tenant_id}/{blueprint.enterprise_scope_id || '-'}/{blueprint.entity_mode}
                    </div>
                  </div>
                  <span className={`text-xs font-bold px-2.5 py-1 rounded shrink-0 ${
                    blueprint.status === 'approved' ? 'bg-emerald-900/70 text-emerald-200'
                    : blueprint.status === 'rejected' ? 'bg-red-900/70 text-red-200'
                    : 'afs-bg-raised afs-ink'}`}>
                    {blueprint.status === 'approved' ? '승인됨' : blueprint.status === 'rejected' ? '반려됨' : '초안'}
                  </span>
                </div>

                <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2 mt-4 text-xs">
                  <div><dt className="afs-muted">목적</dt><dd className="afs-ink">{blueprint.business.objective || '-'}</dd></div>
                  <div><dt className="afs-muted">범위</dt><dd className="afs-ink">{blueprint.business.in_scope.join(', ') || '-'}</dd></div>
                  <div className="md:col-span-2">
                    <dt className="afs-muted">제외 범위 <span className="afs-muted">(고르지 않은 것 = 만들지 않을 것)</span></dt>
                    <dd className="afs-warn-fg/90">{blueprint.business.out_of_scope.join(' · ') || '-'}</dd>
                  </div>
                  <div><dt className="afs-muted">이 산출물로 내릴 결정</dt><dd className="afs-ink">{blueprint.business.decision_makers.join(', ') || '-'}</dd></div>
                  <div><dt className="afs-muted">추천 워크플로우</dt><dd className="afs-ink">{blueprint.system.template_id || '-'}</dd></div>
                </dl>

                {blueprint.business.problem && (
                  <div className="mt-3 text-xs">
                    <div className="afs-muted">사용자가 적은 것</div>
                    <div className="afs-ink whitespace-pre-wrap afs-bg-sunken border afs-border rounded p-2 mt-1 max-h-28 overflow-y-auto">
                      {blueprint.business.problem}
                    </div>
                  </div>
                )}

                {/* 출처 표시 — §5.2 AI 추천과 사람 확정을 구분 */}
                <div className="flex gap-1.5 flex-wrap mt-3">
                  {Object.entries(blueprint.provenance || {}).map(([k, v]) => (
                    <span key={k} className="text-xs px-1.5 py-0.5 rounded afs-bg-raised afs-muted"
                      title={v.note}>
                      {k}: {v.origin === 'ai' ? 'AI 제안' : v.origin === 'user' ? '사용자 답변' : '규칙'}
                      {v.confirmed ? ' · 확정' : ' · 미확정'}
                    </span>
                  ))}
                </div>
              </div>

              <ReadinessBoard r={blueprint.readiness} />
              <GapList gaps={blueprint.readiness.blocking_gaps} title="🚫 미확보 필수 데이터" />
              <GapList
                gaps={blueprint.readiness.gaps.filter((g) => g.status !== 'missing' || g.necessity !== 'required')}
                title="그 밖에 확인이 필요한 데이터" />

              {/* 데이터 요구사항 전체 */}
              <div className={`${CARD} p-4`}>
                <h4 className="text-sm font-bold afs-ink mb-2">
                  데이터 요구사항 <span className="afs-muted font-normal">({blueprint.data_requirements.length}건)</span>
                </h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="afs-muted border-b afs-border text-left">
                        <th className="py-1 pr-2">업무 용어</th><th className="pr-2">종류</th>
                        <th className="pr-2">구분</th><th className="pr-2">필요도</th>
                        <th className="pr-2">담당</th><th className="pr-2">상태</th><th>단위·최신성</th>
                      </tr>
                    </thead>
                    <tbody>
                      {blueprint.data_requirements.map((r) => (
                        <tr key={r.key} className="border-b afs-border/70">
                          <td className="py-1 pr-2 afs-ink">{r.canonical_term}</td>
                          <td className="pr-2 afs-muted">{REQ_TYPE_KO[r.requirement_type] || r.requirement_type}</td>
                          <td className="pr-2 afs-muted">
                            {DATA_KIND_KO[r.data_kind] || r.data_kind}
                            {r.external && <span className="afs-info-fg ml-1">{r.external.grade.toUpperCase()}</span>}
                          </td>
                          <td className="pr-2 afs-muted">{NECESSITY_KO[r.necessity] || r.necessity}</td>
                          <td className="pr-2 afs-info-fg/80">{r.owner_department || '-'}</td>
                          <td className={`pr-2 ${r.readiness_status === 'held' ? 'afs-success-fg'
                            : r.readiness_status === 'needs_verification' ? 'afs-warn-fg' : 'afs-danger-fg'}`}>
                            {REQ_STATUS_KO[r.readiness_status as ReqStatus] || r.readiness_status}
                          </td>
                          <td className="afs-muted">{r.expected_grain || '-'} / {r.freshness_requirement || '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* 위험 · 권장 순서 (§4.4 실행 보드) */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className={`${CARD} p-4`}>
                  <h4 className="text-sm font-bold afs-ink mb-2">권장 구축 순서</h4>
                  <ol className="text-xs afs-ink space-y-1 list-decimal list-inside">
                    {blueprint.recommended_sequence.map((s, i) => <li key={i}>{s.replace(/^\d+\)\s*/, '')}</li>)}
                  </ol>
                </div>
                <div className={`${CARD} p-4`}>
                  <h4 className="text-sm font-bold afs-ink mb-2">
                    위험요인 <span className="afs-muted font-normal">({blueprint.risks.length}건)</span>
                  </h4>
                  <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
                    {blueprint.risks.map((r, i) => (
                      <div key={i} className="text-xs border-l-2 afs-border pl-2">
                        <span className="text-xs px-1 py-0.5 rounded afs-bg-raised afs-muted mr-1">{r.category}</span>
                        <span className="afs-ink">{r.description}</span>
                        {r.mitigation && <div className="afs-success-fg/80 mt-0.5">→ {r.mitigation}</div>}
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* 승인 / 프로젝트 생성 */}
              <div className={`${CARD} p-5`}>
                <h4 className="text-sm font-bold afs-action-fg mb-3">실행</h4>
                {blueprint.status === 'draft' ? (
                  <div className="space-y-3">
                    {!!blueprint.blocking_gap_count && (
                      <div className="text-xs afs-warn-fg">
                        ⚠️ 미확보 필수 데이터 {blueprint.blocking_gap_count}건이 있습니다. 승인은 가능하지만
                        무엇을 안고 승인했는지가 결정 이력에 남습니다.
                      </div>
                    )}
                    {!!blueprint.unverified_kpis?.length && (
                      <div className="text-xs afs-warn-fg">
                        ⚠️ 공식·단위가 없어 계산할 수 없는 지표: {blueprint.unverified_kpis.join(', ')}
                      </div>
                    )}
                    <div className="flex items-center gap-2 flex-wrap">
                      <button onClick={() => confirmApprove.ask(true)} disabled={busy}
                        className={BTN_PRIMARY}>승인</button>
                      <input value={rejectReason} onChange={(e) => setRejectReason(e.target.value)}
                        placeholder="반려 사유 (반려 시 필수)"
                        className="afs-input" style={{ flex: 1, minWidth: 200 }} />
                      <button onClick={() => decide('rejected')} disabled={busy || !rejectReason.trim()}
                        className={BTN_DANGER}>반려</button>
                    </div>

                    {/* ★ 무엇을 «안고» 승인하는지 승인 전에 보여준다. 종전에는 승인 완료
                        문구에서야 「미확보 필수 데이터 N건을 안고 승인했습니다」가 나왔다 —
                        그때는 이미 결정 이력에 남은 뒤다. */}
                    <ConfirmInline open={confirmApprove.open}
                      title="이 청사진을 승인합니다"
                      danger={Boolean(blueprint.blocking_gap_count)}
                      body={<>
                        승인하면 <b>이 청사진으로 프로젝트를 만들 수 있게 됩니다.</b> 승인 사실과
                        조건은 <b>결정 이력에 영구히</b> 남습니다(수정 불가).
                        {!!blueprint.blocking_gap_count && (
                          <><br />⚠️ <b>미확보 필수 데이터 {blueprint.blocking_gap_count}건</b>을
                            안고 승인하게 됩니다 — 무엇을 안고 승인했는지가 이력에 남습니다.</>
                        )}
                        {!!blueprint.unverified_kpis?.length && (
                          <><br />⚠️ 공식·단위가 없어 계산할 수 없는 지표:{' '}
                            {blueprint.unverified_kpis.join(', ')}</>
                        )}
                      </>}
                      confirmLabel="승인"
                      onCancel={confirmApprove.cancel}
                      onConfirm={() => confirmApprove.run(() => decide('approved'))} />
                  </div>
                ) : blueprint.status === 'approved' ? (
                  <div className="space-y-3">
                    <div className="text-xs afs-muted">
                      승인자 {blueprint.approved_by} · {blueprint.approved_at}
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <input value={projectId} onChange={(e) => setProjectId(e.target.value)}
                        placeholder="새 프로젝트 ID (영문/숫자/_/-)"
                        className="flex-1 min-w-[220px] afs-bg-sunken border afs-border rounded px-3 py-2 text-xs afs-ink " />
                      <button onClick={bootstrap} disabled={busy || !projectId.trim()} className={BTN_PRIMARY}>
                        프로젝트 생성
                      </button>
                      <button onClick={dataTasks} disabled={busy || !projectId.trim()} className={BTN_GHOST}
                        title="미확보 데이터를 WBS 준비 태스크로 추가합니다. 기획(WBS 생성) 완료 후에만 동작합니다">
                        데이터 준비 태스크 추가
                      </button>
                    </div>
                    <p className="text-xs afs-muted">
                      프로젝트를 만들면 요구 확인 인터뷰부터 정상 진행됩니다 — 이 청사진은 상위 입력값으로만 주입됩니다.
                    </p>
                  </div>
                ) : (
                  <div className="text-xs afs-danger-fg">반려됨 · 사유: {blueprint.rejected_reason || '-'}</div>
                )}
              </div>

              {/* 결정 이력 (Decision Ledger) */}
              {(ledger.status !== 'ok' || !!(ledger.value || []).length) && (
                <div className={`${CARD} p-4`}>
                  <h4 className="text-sm font-bold afs-ink mb-2">
                    결정 이력 <span className="afs-muted font-normal">— 왜 이렇게 됐는지의 근거(수정 불가)</span>
                  </h4>
                  {/* ★★ 못 읽은 것을 «이력 없음» 으로 두지 않는다 — 감사 자리에서 가장 나쁜 침묵이다. */}
                  {ledger.status !== 'ok' && (
                    <EmptyOrError state={ledger.status} error={ledger.error}
                      emptyText="결정 이력이 없습니다."
                      onRetry={() => blueprint && loadLedger(blueprint.blueprint_id).then(setLedger)} />
                  )}
                  <div className="space-y-2">
                    {(ledger.value || []).map((e) => (
                      <div key={e.event_id} className="text-xs border-l-2 afs-action-border pl-2.5">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="afs-muted">#{e.seq}</span>
                          <span className="font-bold afs-action-fg">{e.event_type}</span>
                          <span className="afs-muted">{e.actor_type}:{e.actor_id || '-'}</span>
                          <span className="afs-muted">{e.created_at}</span>
                          {!e.is_substantiated && (
                            <span className="text-xs px-1.5 py-0.5 rounded bg-amber-950/60 afs-warn-fg">근거 없음</span>
                          )}
                        </div>
                        <div className="afs-ink">{e.decision}</div>
                        {e.rationale && <div className="afs-muted">{e.rationale}</div>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex justify-between">
                <button onClick={() => setStep('status')} className={BTN_GHOST}>◀ 데이터 보유 확인</button>
                <button onClick={() => { setStep('pick'); setBlueprint(null); setConsultation(null); }}
                  className={BTN_GHOST}>새 상담 시작</button>
              </div>
            </>
          )}

          {busy && (
            <p className="afs-muted" style={{ textAlign: 'center', padding: '16px 0', fontSize: 13 }}>
              처리 중…
            </p>
          )}
        </div>
        </HubShell>
      </div>
    </HubDialog>
  );
}
