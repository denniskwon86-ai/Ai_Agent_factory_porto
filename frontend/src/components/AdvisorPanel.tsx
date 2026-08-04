import { useCallback, useEffect, useMemo, useState } from 'react';
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

const CARD = 'bg-gray-900 border border-gray-700 rounded-lg';
const BTN = 'text-sm font-bold px-4 py-2 rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed';
const BTN_PRIMARY = `${BTN} text-white bg-indigo-600 hover:bg-indigo-500`;
const BTN_GHOST = `${BTN} text-gray-300 bg-white/5 hover:bg-white/10 border border-white/10`;

/** 준비도 5축 막대. 측정되지 않은 축은 **만점이 아니라 '미측정'** 으로 표시한다. */
function ReadinessBoard({ r }: { r: Readiness }) {
  return (
    <div className={`${CARD} p-4`}>
      <div className="flex items-baseline gap-3 mb-3">
        <span className="text-xs text-gray-400">데이터 준비도</span>
        <span className="text-2xl font-bold text-gray-100">{r.score}</span>
        <span className="text-xs text-gray-500">/ 100</span>
        {r.unmeasured_weight > 0 && (
          <span className="text-[11px] text-amber-400/90">
            ⚠️ {r.unmeasured_weight}점 구간 미측정 (플레이북에 해당 축 요구사항이 없음)
          </span>
        )}
      </div>
      <div className="space-y-1.5">
        {r.dimensions.map((d) => (
          <div key={d.dimension} className="flex items-center gap-2">
            <span className="text-[11px] text-gray-400 w-40 shrink-0">{d.name_ko}</span>
            <div className="flex-1 bg-gray-950 rounded h-4 overflow-hidden border border-gray-800">
              <div
                className={`h-full ${d.measured ? 'bg-gradient-to-r from-emerald-600 to-teal-500' : 'bg-gray-700'}`}
                style={{ width: `${d.weight ? Math.max(2, (d.score / d.weight) * 100) : 2}%` }}
              />
            </div>
            <span className="text-[11px] text-gray-400 w-20 text-right tabular-nums">
              {d.score.toFixed(1)}/{d.weight}
            </span>
            {!d.measured && <span className="text-[10px] text-gray-600">미측정</span>}
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
      <h4 className="text-sm font-bold text-amber-300 mb-2">{title} <span className="text-gray-500 font-normal">({gaps.length}건)</span></h4>
      <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
        {gaps.map((g) => (
          <div key={g.key} className="text-xs border-l-2 border-amber-700/60 pl-2.5 py-0.5">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="font-bold text-gray-200">{g.canonical_term}</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-400">
                {NECESSITY_KO[g.necessity] || g.necessity}
              </span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-400">
                {REQ_STATUS_KO[g.status as ReqStatus] || g.status}
              </span>
              {g.owner_department && (
                <span className="text-[10px] text-sky-400">담당 {g.owner_department}</span>
              )}
              {!g.counts_toward_score && (
                <span className="text-[10px] text-gray-600">점수 미반영</span>
              )}
            </div>
            {g.impact && <div className="text-gray-400 mt-0.5">없으면: {g.impact}</div>}
            {g.next_action && <div className="text-emerald-400/90 mt-0.5">조치: {g.next_action}</div>}
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
  const [ledger, setLedger] = useState<LedgerEvent[]>([]);
  const [projectId, setProjectId] = useState('');
  const [notice, setNotice] = useState('');
  const [rejectReason, setRejectReason] = useState('');

  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | null> => {
    setBusy(true); setErr('');
    try { return await fn(); }
    catch (e: any) { setErr(e?.message || '알 수 없는 오류'); return null; }
    finally { setBusy(false); }
  }, []);

  useEffect(() => {
    run(async () => {
      const [pbs, cons] = await Promise.all([
        advisorApi.listPlaybooks(), advisorApi.listConsultations().catch(() => []),
      ]);
      setPlaybooks(pbs);
      setRecent(cons.slice(0, 8));
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
      setAsked([]); setPreview(null); setBlueprint(null); setLedger([]);
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
        setLedger(await advisorApi.ledgerHistory(bp.blueprint_id).catch(() => []));
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
      setLedger([]);
      setStep('blueprint');
    });

  const decide = (decision: 'approved' | 'rejected') =>
    run(async () => {
      if (!blueprint) return;
      const r = await advisorApi.decide(blueprint.blueprint_id, decision, rejectReason);
      const fresh = await advisorApi.getBlueprint(blueprint.blueprint_id);
      setBlueprint(fresh);
      setLedger(await advisorApi.ledgerHistory(blueprint.blueprint_id).catch(() => []));
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
      setLedger(await advisorApi.ledgerHistory(blueprint.blueprint_id).catch(() => []));
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
      setLedger(await advisorApi.ledgerHistory(blueprint.blueprint_id).catch(() => []));
      setNotice(r.created.length
        ? `데이터 준비 태스크 ${r.created.length}건을 WBS에 추가했습니다: ${r.created.map((t) => t.task_id).join(', ')}`
        : (r.message || '추가할 미확보 데이터가 없습니다.'));
    });

  const gapsForStatus = preview?.gaps || [];
  const selectedPlaybook = useMemo(
    () => playbooks.find((p) => p.playbook_id === playbookId), [playbooks, playbookId]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-70 p-4">
      <div className="bg-gray-800 rounded-xl shadow-2xl border border-gray-700 w-full max-w-5xl max-h-[92vh] flex flex-col text-gray-200">
        {/* 헤더 */}
        <div className="p-4 border-b border-gray-700 flex justify-between items-center bg-gray-900 rounded-t-xl">
          <div className="flex items-center gap-3 min-w-0">
            <span className="text-xl">🧭</span>
            <h2 className="text-lg font-bold shrink-0">업무·데이터 설계 상담</h2>
            <span className="text-xs text-gray-500 truncate">
              무엇을 만들지와 어떤 데이터가 필요한지를 선택형 대화로 정하고, 승인하면 프로젝트가 됩니다
            </span>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-100 shrink-0">✕</button>
        </div>

        {/* 진행 단계 */}
        <div className="px-6 py-2 border-b border-gray-700/70 bg-gray-900/50 flex items-center gap-2 text-[11px]">
          {([['pick', '1. 업무 선택'], ['interview', '2. 선택형 상담'],
             ['status', '3. 데이터 보유 확인'], ['blueprint', '4. 청사진·승인·생성']] as [Step, string][])
            .map(([s, label]) => (
              <span key={s}
                className={`px-2 py-1 rounded ${step === s ? 'bg-indigo-600 text-white font-bold' : 'text-gray-500'}`}>
                {label}
              </span>
            ))}
          {progress && (
            <span className="ml-auto text-gray-400">
              질문 {progress.answered}/{progress.total}
              {consultation && <span className="text-gray-600 ml-2">
                문맥 {consultation.tenant_id} · {consultation.enterprise_scope_id || '범위 미지정'} · {consultation.entity_mode}
              </span>}
            </span>
          )}
        </div>

        <div className="p-6 overflow-y-auto flex-1 space-y-5">
          {err && (
            <div className="bg-red-950/60 border border-red-800 rounded-lg px-4 py-3 text-sm text-red-200">
              ⚠️ {err}
            </div>
          )}
          {notice && (
            <div className="bg-emerald-950/50 border border-emerald-800 rounded-lg px-4 py-3 text-sm text-emerald-200 flex justify-between gap-3">
              <span>{notice}</span>
              <button onClick={() => setNotice('')} className="text-emerald-500 hover:text-emerald-300 shrink-0">✕</button>
            </div>
          )}

          {/* ── 1. 업무 선택 ── */}
          {step === 'pick' && (
            <>
              <div className={`${CARD} p-5`}>
                <h3 className="text-sm font-bold text-indigo-300 mb-3">어떤 업무를 하시려나요?</h3>
                <div className="space-y-2">
                  {playbooks.map((pb) => (
                    <label key={pb.playbook_id}
                      className={`block border rounded-lg p-3 cursor-pointer transition-colors ${
                        playbookId === pb.playbook_id
                          ? 'border-indigo-500 bg-indigo-950/40'
                          : 'border-gray-700 hover:border-gray-600'}`}>
                      <div className="flex items-start gap-2">
                        <input type="radio" checked={playbookId === pb.playbook_id}
                          onChange={() => setPlaybookId(pb.playbook_id)} className="mt-1" />
                        <div className="min-w-0">
                          <div className="text-sm font-bold text-gray-100">{pb.name_ko}</div>
                          <div className="text-xs text-gray-400 mt-1">{pb.description}</div>
                          <div className="text-[11px] text-gray-600 mt-1">
                            질문 {pb.question_count}개 · 데이터 요구 {pb.requirement_count}건
                            {pb.recommended_template_id && ` · 추천 워크플로우 ${pb.recommended_template_id}`}
                          </div>
                        </div>
                      </div>
                    </label>
                  ))}
                  {!playbooks.length && !busy && (
                    <div className="text-sm text-gray-500">등록된 플레이북이 없습니다.</div>
                  )}
                </div>
              </div>

              <div className={`${CARD} p-5`}>
                <h3 className="text-sm font-bold text-gray-300 mb-2">
                  하시려는 일을 자유롭게 적어 주세요 <span className="text-gray-600 font-normal">(선택 — 비워도 진행됩니다)</span>
                </h3>
                <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3}
                  placeholder="예) 내년도 사업계획 데이터를 만들고 부서별로 승인받고 싶습니다."
                  className="w-full bg-gray-950 border border-gray-700 rounded-lg p-3 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-indigo-500" />
                <div className="flex justify-end mt-3">
                  <button onClick={startConsultation} disabled={busy || !playbookId} className={BTN_PRIMARY}>
                    상담 시작 {selectedPlaybook ? `· ${selectedPlaybook.name_ko}` : ''}
                  </button>
                </div>
              </div>

              {!!recent.length && (
                <div className={`${CARD} p-4`}>
                  <h3 className="text-sm font-bold text-gray-400 mb-2">이어서 하기</h3>
                  <div className="space-y-1">
                    {recent.map((c) => (
                      <button key={c.consultation_id} onClick={() => resume(c.consultation_id)}
                        className="w-full text-left text-xs px-3 py-2 rounded hover:bg-white/5 flex items-center gap-2">
                        <span className="text-gray-300 truncate flex-1">
                          {c.initial_prompt || '(입력 없음)'}
                        </span>
                        <span className="text-[10px] text-gray-600">{c.playbook_id}</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-400">{c.status}</span>
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
                  <h4 className="text-xs font-bold text-gray-500 mb-2">지금까지 정한 것</h4>
                  <div className="space-y-1">
                    {asked.map(({ q, chosen }) => (
                      <div key={q.id} className="text-xs flex gap-2">
                        <span className="text-gray-500 shrink-0">{q.question}</span>
                        <span className="text-emerald-300">
                          {q.options.filter((o) => chosen.includes(o.value)).map((o) => o.label).join(', ') || '선택 없음'}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className={`${CARD} p-5`}>
                <div className="text-[11px] text-gray-500 mb-1">{question.stage}</div>
                <h3 className="text-base font-bold text-gray-100">{question.question}</h3>
                {question.why && <p className="text-xs text-gray-400 mt-1">{question.why}</p>}

                <div className="space-y-2 mt-4">
                  {question.options.map((o) => {
                    const on = picked.includes(o.value);
                    return (
                      <label key={o.value}
                        className={`block border rounded-lg p-3 cursor-pointer transition-colors ${
                          on ? 'border-indigo-500 bg-indigo-950/40' : 'border-gray-700 hover:border-gray-600'}`}>
                        <div className="flex items-start gap-2">
                          <input
                            type={question.multi ? 'checkbox' : 'radio'} checked={on} className="mt-1"
                            onChange={() => setPicked((prev) => question.multi
                              ? (prev.includes(o.value) ? prev.filter((v) => v !== o.value) : [...prev, o.value])
                              : [o.value])} />
                          <div className="min-w-0">
                            <div className="text-sm text-gray-100 flex items-center gap-2">
                              {o.label}
                              {o.recommended && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-900/70 text-indigo-200">추천</span>
                              )}
                            </div>
                            {o.description && <div className="text-xs text-gray-400 mt-0.5">{o.description}</div>}
                          </div>
                        </div>
                      </label>
                    );
                  })}
                </div>

                <div className="mt-3">
                  <input value={freeText} onChange={(e) => setFreeText(e.target.value)}
                    placeholder="직접 입력 (선택 — 적어두면 청사진의 문제 기술에 함께 남습니다)"
                    className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2 text-xs text-gray-100 placeholder-gray-600 focus:outline-none focus:border-indigo-500" />
                </div>

                <div className="flex justify-end mt-4">
                  <button onClick={submitAnswer} disabled={busy || (!picked.length && !freeText.trim())}
                    className={BTN_PRIMARY}>다음</button>
                </div>
              </div>

              {preview && (
                <div>
                  <div className="text-[11px] text-gray-500 mb-1">
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
                <h3 className="text-sm font-bold text-indigo-300 mb-1">이 데이터들을 지금 갖고 계신가요?</h3>
                <p className="text-xs text-gray-400 mb-4">
                  모르는 항목은 <b>부족</b>으로 둡니다 — 모르는 것을 보유로 치면 준비도가 실제보다 높게 나옵니다.
                </p>
                <div className="space-y-1.5 max-h-[46vh] overflow-y-auto pr-1">
                  {gapsForStatus.map((g) => (
                    <div key={g.key} className="flex items-center gap-2 border-b border-gray-800 pb-1.5">
                      <div className="min-w-0 flex-1">
                        <div className="text-xs text-gray-100 flex items-center gap-1.5 flex-wrap">
                          {g.canonical_term}
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-400">
                            {NECESSITY_KO[g.necessity] || g.necessity}
                          </span>
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-500">
                            {REQ_TYPE_KO[g.requirement_type] || g.requirement_type}
                          </span>
                          {g.owner_department && <span className="text-[10px] text-sky-400">담당 {g.owner_department}</span>}
                        </div>
                      </div>
                      <div className="flex gap-1 shrink-0">
                        {(['held', 'needs_verification', 'missing'] as ReqStatus[]).map((s) => (
                          <button key={s} onClick={() => setStatuses((p) => ({ ...p, [g.key]: s }))}
                            className={`text-[11px] px-2 py-1 rounded border ${
                              (statuses[g.key] || 'missing') === s
                                ? 'bg-indigo-600 border-indigo-500 text-white'
                                : 'border-gray-700 text-gray-400 hover:border-gray-600'}`}>
                            {REQ_STATUS_KO[s]}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                  {!gapsForStatus.length && (
                    <div className="text-sm text-gray-500">확인할 데이터 요구사항이 없습니다.</div>
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
                    <h3 className="text-base font-bold text-gray-100">{blueprint.title}</h3>
                    <div className="text-[11px] text-gray-500 mt-0.5">
                      {blueprint.blueprint_id} · v{blueprint.version} · {blueprint.playbook_id}
                      {' · '}문맥 {blueprint.tenant_id}/{blueprint.enterprise_scope_id || '-'}/{blueprint.entity_mode}
                    </div>
                  </div>
                  <span className={`text-xs font-bold px-2.5 py-1 rounded shrink-0 ${
                    blueprint.status === 'approved' ? 'bg-emerald-900/70 text-emerald-200'
                    : blueprint.status === 'rejected' ? 'bg-red-900/70 text-red-200'
                    : 'bg-gray-700 text-gray-300'}`}>
                    {blueprint.status === 'approved' ? '승인됨' : blueprint.status === 'rejected' ? '반려됨' : '초안'}
                  </span>
                </div>

                <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2 mt-4 text-xs">
                  <div><dt className="text-gray-500">목적</dt><dd className="text-gray-200">{blueprint.business.objective || '-'}</dd></div>
                  <div><dt className="text-gray-500">범위</dt><dd className="text-gray-200">{blueprint.business.in_scope.join(', ') || '-'}</dd></div>
                  <div className="md:col-span-2">
                    <dt className="text-gray-500">제외 범위 <span className="text-gray-600">(고르지 않은 것 = 만들지 않을 것)</span></dt>
                    <dd className="text-amber-300/90">{blueprint.business.out_of_scope.join(' · ') || '-'}</dd>
                  </div>
                  <div><dt className="text-gray-500">이 산출물로 내릴 결정</dt><dd className="text-gray-200">{blueprint.business.decision_makers.join(', ') || '-'}</dd></div>
                  <div><dt className="text-gray-500">추천 워크플로우</dt><dd className="text-gray-200">{blueprint.system.template_id || '-'}</dd></div>
                </dl>

                {blueprint.business.problem && (
                  <div className="mt-3 text-xs">
                    <div className="text-gray-500">사용자가 적은 것</div>
                    <div className="text-gray-300 whitespace-pre-wrap bg-gray-950 border border-gray-800 rounded p-2 mt-1 max-h-28 overflow-y-auto">
                      {blueprint.business.problem}
                    </div>
                  </div>
                )}

                {/* 출처 표시 — §5.2 AI 추천과 사람 확정을 구분 */}
                <div className="flex gap-1.5 flex-wrap mt-3">
                  {Object.entries(blueprint.provenance || {}).map(([k, v]) => (
                    <span key={k} className="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-400"
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
                <h4 className="text-sm font-bold text-gray-300 mb-2">
                  데이터 요구사항 <span className="text-gray-500 font-normal">({blueprint.data_requirements.length}건)</span>
                </h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-[11px]">
                    <thead>
                      <tr className="text-gray-500 border-b border-gray-700 text-left">
                        <th className="py-1 pr-2">업무 용어</th><th className="pr-2">종류</th>
                        <th className="pr-2">구분</th><th className="pr-2">필요도</th>
                        <th className="pr-2">담당</th><th className="pr-2">상태</th><th>단위·최신성</th>
                      </tr>
                    </thead>
                    <tbody>
                      {blueprint.data_requirements.map((r) => (
                        <tr key={r.key} className="border-b border-gray-800/70">
                          <td className="py-1 pr-2 text-gray-200">{r.canonical_term}</td>
                          <td className="pr-2 text-gray-400">{REQ_TYPE_KO[r.requirement_type] || r.requirement_type}</td>
                          <td className="pr-2 text-gray-400">
                            {DATA_KIND_KO[r.data_kind] || r.data_kind}
                            {r.external && <span className="text-sky-400 ml-1">{r.external.grade.toUpperCase()}</span>}
                          </td>
                          <td className="pr-2 text-gray-400">{NECESSITY_KO[r.necessity] || r.necessity}</td>
                          <td className="pr-2 text-sky-400/80">{r.owner_department || '-'}</td>
                          <td className={`pr-2 ${r.readiness_status === 'held' ? 'text-emerald-400'
                            : r.readiness_status === 'needs_verification' ? 'text-amber-400' : 'text-red-400'}`}>
                            {REQ_STATUS_KO[r.readiness_status as ReqStatus] || r.readiness_status}
                          </td>
                          <td className="text-gray-500">{r.expected_grain || '-'} / {r.freshness_requirement || '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* 위험 · 권장 순서 (§4.4 실행 보드) */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className={`${CARD} p-4`}>
                  <h4 className="text-sm font-bold text-gray-300 mb-2">권장 구축 순서</h4>
                  <ol className="text-xs text-gray-300 space-y-1 list-decimal list-inside">
                    {blueprint.recommended_sequence.map((s, i) => <li key={i}>{s.replace(/^\d+\)\s*/, '')}</li>)}
                  </ol>
                </div>
                <div className={`${CARD} p-4`}>
                  <h4 className="text-sm font-bold text-gray-300 mb-2">
                    위험요인 <span className="text-gray-500 font-normal">({blueprint.risks.length}건)</span>
                  </h4>
                  <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
                    {blueprint.risks.map((r, i) => (
                      <div key={i} className="text-[11px] border-l-2 border-gray-700 pl-2">
                        <span className="text-[10px] px-1 py-0.5 rounded bg-gray-800 text-gray-400 mr-1">{r.category}</span>
                        <span className="text-gray-300">{r.description}</span>
                        {r.mitigation && <div className="text-emerald-400/80 mt-0.5">→ {r.mitigation}</div>}
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* 승인 / 프로젝트 생성 */}
              <div className={`${CARD} p-5`}>
                <h4 className="text-sm font-bold text-indigo-300 mb-3">실행</h4>
                {blueprint.status === 'draft' ? (
                  <div className="space-y-3">
                    {!!blueprint.blocking_gap_count && (
                      <div className="text-xs text-amber-300">
                        ⚠️ 미확보 필수 데이터 {blueprint.blocking_gap_count}건이 있습니다. 승인은 가능하지만
                        무엇을 안고 승인했는지가 결정 이력에 남습니다.
                      </div>
                    )}
                    {!!blueprint.unverified_kpis?.length && (
                      <div className="text-xs text-amber-300">
                        ⚠️ 공식·단위가 없어 계산할 수 없는 지표: {blueprint.unverified_kpis.join(', ')}
                      </div>
                    )}
                    <div className="flex items-center gap-2 flex-wrap">
                      <button onClick={() => decide('approved')} disabled={busy} className={BTN_PRIMARY}>승인</button>
                      <input value={rejectReason} onChange={(e) => setRejectReason(e.target.value)}
                        placeholder="반려 사유 (반려 시 필수)"
                        className="flex-1 min-w-[200px] bg-gray-950 border border-gray-700 rounded px-3 py-2 text-xs text-gray-100 placeholder-gray-600" />
                      <button onClick={() => decide('rejected')} disabled={busy || !rejectReason.trim()}
                        className={`${BTN} text-red-200 bg-red-900/50 hover:bg-red-800/70 border border-red-800`}>반려</button>
                    </div>
                  </div>
                ) : blueprint.status === 'approved' ? (
                  <div className="space-y-3">
                    <div className="text-xs text-gray-400">
                      승인자 {blueprint.approved_by} · {blueprint.approved_at}
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <input value={projectId} onChange={(e) => setProjectId(e.target.value)}
                        placeholder="새 프로젝트 ID (영문/숫자/_/-)"
                        className="flex-1 min-w-[220px] bg-gray-950 border border-gray-700 rounded px-3 py-2 text-xs text-gray-100 placeholder-gray-600" />
                      <button onClick={bootstrap} disabled={busy || !projectId.trim()} className={BTN_PRIMARY}>
                        프로젝트 생성
                      </button>
                      <button onClick={dataTasks} disabled={busy || !projectId.trim()} className={BTN_GHOST}
                        title="미확보 데이터를 WBS 준비 태스크로 추가합니다. 기획(WBS 생성) 완료 후에만 동작합니다">
                        데이터 준비 태스크 추가
                      </button>
                    </div>
                    <p className="text-[11px] text-gray-500">
                      프로젝트를 만들면 요구 확인 인터뷰부터 정상 진행됩니다 — 이 청사진은 상위 입력값으로만 주입됩니다.
                    </p>
                  </div>
                ) : (
                  <div className="text-xs text-red-300">반려됨 · 사유: {blueprint.rejected_reason || '-'}</div>
                )}
              </div>

              {/* 결정 이력 (Decision Ledger) */}
              {!!ledger.length && (
                <div className={`${CARD} p-4`}>
                  <h4 className="text-sm font-bold text-gray-300 mb-2">
                    결정 이력 <span className="text-gray-500 font-normal">— 왜 이렇게 됐는지의 근거(수정 불가)</span>
                  </h4>
                  <div className="space-y-2">
                    {ledger.map((e) => (
                      <div key={e.event_id} className="text-[11px] border-l-2 border-indigo-700/70 pl-2.5">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-gray-500">#{e.seq}</span>
                          <span className="font-bold text-indigo-300">{e.event_type}</span>
                          <span className="text-gray-400">{e.actor_type}:{e.actor_id || '-'}</span>
                          <span className="text-gray-600">{e.created_at}</span>
                          {!e.is_substantiated && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-950/60 text-amber-300">근거 없음</span>
                          )}
                        </div>
                        <div className="text-gray-200">{e.decision}</div>
                        {e.rationale && <div className="text-gray-400">{e.rationale}</div>}
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
            <div className="flex justify-center py-4">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-500" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
