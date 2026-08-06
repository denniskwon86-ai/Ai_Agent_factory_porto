/**
 * [트랙 E · 7단계 전제] 실행 통제 — Sprint 시작 · 재개 · 복구 · WBS 재분할 · Release 저장.
 *
 * 근거: 구현 명세 §8 **기능 게이트** — 「Sprint 시작·일시정지·정지·재개·복구·재분할·Release·
 * Export 가 보존된다」. 2026-08-06 인수인계 §4 가 이 다섯 개를 «7단계 전제 미충족» 으로 남겼다.
 * 지금 기존 3패널을 지우면 사용자는 **실행을 시작할 수도, 멈춘 것을 재개할 수도 없다.**
 *
 * ## 이 화면이 지키는 것
 *
 * ★ **비활성 버튼에 반드시 이유를 붙인다.** 회색 버튼만 보이면 사용자는 화면 고장으로 읽고,
 *   진짜 이유(「기획 산출물이 아직 없습니다」)는 아무에게도 도달하지 않는다. 이 저장소가
 *   결정 차단·발간 게이트에서 이미 확인한 규칙이다.
 * ★ **되돌릴 수 없는 것은 화면 안에서 확인받는다.** `confirm()` 을 쓰지 않는다 — 키보드·
 *   스크린리더 대응이 안 되고, 무엇보다 «무엇이 사라지는지» 를 적을 자리가 없다.
 * ★ **명령은 전부 `sprintActions.ts` 를 지난다.** 여기서 `fetch` 를 직접 부르지 않는다 —
 *   부르는 순간 종전 통제실과 payload 가 갈라지고, 그때 「두 화면이 다른 프로젝트를 만든다」가
 *   된다(인수인계 §4.1 경고).
 */
import { useState } from 'react';

import { useFactoryStore } from '../store/useFactoryStore';

import type { FactoryStudioViewModel } from './factoryViewModel';
import {
  REPLAN_CONFIRM, SELF_HEAL_NOTE, newPlanningTaskId, replanWbs, resumeAfterQuota, startPlanning,
  type SprintResult,
} from './sprintActions';

type Pending = null | 'start' | 'replan';

export interface RunControlsProps {
  vm: FactoryStudioViewModel;
}

export function RunControls({ vm }: RunControlsProps) {
  const setActiveSprintId = useFactoryStore((s) => s.setActiveSprintId);
  const clearSuspendedQuota = useFactoryStore((s) => s.clearSuspendedQuota);
  const clearSprintData = useFactoryStore((s) => s.clearSprintData);
  const triggerSelfHealing = useFactoryStore((s) => s.triggerSelfHealing);
  const saveRelease = useFactoryStore((s) => s.saveRelease);

  const [pending, setPending] = useState<Pending>(null);
  const [busy, setBusy] = useState('');
  const [note, setNote] = useState<{ tone: 'ok' | 'bad'; text: string } | null>(null);
  const [idea, setIdea] = useState('');
  const [masterData, setMasterData] = useState('');

  const pid = vm.project.id;
  const { run, inspect } = vm;
  const failure = inspect.failure;

  /** 서버 문구를 그대로 보여 준다 — 화면이 지어내면 서버 규칙과 갈라진다. */
  const show = (r: SprintResult, okText: string) =>
    setNote(r.ok ? { tone: 'ok', text: r.message || okText } : { tone: 'bad', text: r.message });

  const guard = async (label: string, fn: () => Promise<void>) => {
    if (busy) return;
    setBusy(label); setNote(null);
    try { await fn(); } finally { setBusy(''); }
  };

  // ── Sprint 시작 ──────────────────────────────────────────────────────────
  const doStart = () => guard('기획 가동 중', async () => {
    const taskId = newPlanningTaskId();
    const r = await startPlanning(pid, idea, masterData, taskId);
    if (r.ok) {
      // 낙관적으로 «가동 중» 을 표시하지 않는다 — 서버가 받았을 때만 표시를 옮긴다.
      setActiveSprintId(taskId);
      setIdea(''); setMasterData(''); setPending(null);
    }
    show(r, '기획을 가동했습니다.');
  });

  // ── 재개 ─────────────────────────────────────────────────────────────────
  const doResume = () => guard('재개 중', async () => {
    const r = await resumeAfterQuota(pid, inspect.suspendedTaskId);
    if (r.ok) {
      setActiveSprintId(inspect.suspendedTaskId);
      clearSuspendedQuota();
    }
    show(r, '멈춘 지점부터 재개했습니다.');
  });

  // ── 복구 ─────────────────────────────────────────────────────────────────
  const doHeal = () => guard('복구 요청 중', async () => {
    // store 액션을 그대로 쓴다 — 두 경로를 만들면 또 갈라진다.
    await triggerSelfHealing(failure?.error || '실행 실패');
    setNote({ tone: 'ok', text: `복구를 요청했습니다. ${SELF_HEAL_NOTE}` });
  });

  // ── WBS 재분할 ───────────────────────────────────────────────────────────
  const doReplan = () => guard('재분할 중', async () => {
    const r = await replanWbs(pid);
    if (r.ok) {
      clearSprintData();
      if (r.taskId) setActiveSprintId(r.taskId);
      setPending(null);
    }
    show(r, 'WBS 분할을 다시 시작했습니다.');
  });

  // ── Release 저장 ─────────────────────────────────────────────────────────
  const doRelease = () => guard('Release 저장 중', async () => {
    const rid = await saveRelease(pid);
    setNote(rid
      ? { tone: 'ok', text: `Release 를 저장했습니다 — ${rid}` }
      // ⚠️ 실패를 조용히 넘기지 않는다. 저장된 줄 알고 화면을 닫으면 산출물이 사라진 것으로 보인다.
      : { tone: 'bad', text: 'Release 를 저장하지 못했습니다. 산출물이 아직 준비되지 않았거나 권한이 없습니다.' });
  });

  // ── 왜 못 누르는가 ───────────────────────────────────────────────────────
  // ★★ 비활성 이유가 **헤더의 낱말을 그대로 인용한다.** 여기서 「가동 중」이라고 새로 쓰면
  //   헤더가 「사용자 결정 대기」일 때 두 문구가 모순된다 — 2026-08-06 실측에서 실제로 그랬다.
  //   각각은 그럴듯하고 나란히 놓아야 보인다(인계서 §1 이 여덟 번 확인한 유형이다).
  const startWhy = !pid ? '프로젝트를 먼저 선택하십시오.'
    : run.active ? `지금은 «${run.label}» 상태입니다 — 먼저 일시정지하십시오.`
      : run.wbsTotal > 0 ? '이 프로젝트는 이미 기획을 마쳤습니다. 다시 나누려면 «WBS 재분할» 을 쓰십시오.'
        : '';
  const resumeWhy = !inspect.suspendedTaskId
    ? '쿼터로 동결된 작업이 없습니다 — 재개할 지점이 없습니다.' : '';
  const healWhy = !failure ? '마지막 실행 실패 기록이 없습니다 — 복구할 대상이 없습니다.' : '';
  // ⚠️ `docs` 는 배열이 아니라 **stage 키 맵**이다. 기획 산출물은 `PLANNING` 에 들어 있고,
  //   `toDocs` 는 본문·판정이 둘 다 없으면 **키 자체를 만들지 않는다** — 즉 키의 유무가 곧
  //   «있다/아직 없다» 다(빈 문자열을 «있음» 으로 세지 않기 위해 그렇게 만들어져 있다).
  const replanWhy = !vm.docs.PLANNING
    ? '기획 산출물(PRD)이 아직 없습니다 — 나눌 대상이 없습니다.'
    : run.active ? `지금은 «${run.label}» 상태입니다 — 멈춘 뒤에 재분할할 수 있습니다.` : '';
  const releaseWhy = run.wbsTotal === 0
    ? 'WBS 가 없어 저장할 산출물이 없습니다.' : '';

  return (
    <section className="run-controls" aria-label="실행 통제">
      <header>
        <b>실행 통제</b>
        {/* 지금 무엇을 할 수 있는지 한 줄로 — 버튼 다섯 개를 훑기 전에 답을 준다. */}
        <span>{run.label}</span>
      </header>

      {note && (
        <p className={`run-note ${note.tone}`} role="status">{note.text}</p>
      )}

      <div className="run-buttons">
        <Btn label="기획 가동" why={startWhy} busy={busy === '기획 가동 중'}
          onClick={() => setPending(pending === 'start' ? null : 'start')} primary />
        <Btn label="재개" why={resumeWhy} busy={busy === '재개 중'} onClick={doResume}
          hint="쿼터가 회복된 뒤 멈춘 지점부터 다시 시작합니다(처음부터가 아닙니다)." />
        <Btn label="복구" why={healWhy} busy={busy === '복구 요청 중'} onClick={doHeal}
          hint={SELF_HEAL_NOTE} />
        <Btn label="WBS 재분할" why={replanWhy} busy={busy === '재분할 중'}
          onClick={() => setPending(pending === 'replan' ? null : 'replan')} danger />
        <Btn label="Release 저장" why={releaseWhy} busy={busy === 'Release 저장 중'}
          onClick={doRelease} hint="현재 산출물을 하나의 릴리스로 묶어 보관합니다." />
      </div>

      {/* ── 기획 가동 폼 ─────────────────────────────────────────────────── */}
      {pending === 'start' && !startWhy && (
        <div className="run-form">
          <label className="field-label" htmlFor="rc-idea">무엇을 만들지 한 문장으로 (필수)</label>
          <textarea id="rc-idea" rows={2} value={idea}
            placeholder="예: 사내 원료 재고를 조회하고 부족분을 알려 주는 화면"
            onChange={(e) => setIdea(e.target.value)} />
          <label className="field-label" htmlFor="rc-master">참고할 기준정보 (선택)</label>
          <textarea id="rc-master" rows={2} value={masterData}
            placeholder="에이전트가 확정 사실로 쓸 값이 있으면 적습니다"
            onChange={(e) => setMasterData(e.target.value)} />
          <p className="run-hint">
            가동하면 요구 확인 → 기획 → 설계 → 구현 순서로 진행됩니다. 중간에 사용자 결정이
            필요한 지점에서 멈추고 물어봅니다.
          </p>
          <div className="run-form-actions">
            <button type="button" onClick={() => setPending(null)}>취소</button>
            <button type="button" className="primary" disabled={!idea.trim() || !!busy}
              onClick={doStart}>
              {busy === '기획 가동 중' ? '가동 중…' : '기획 가동'}
            </button>
          </div>
        </div>
      )}

      {/* ── 재분할 확인 ──────────────────────────────────────────────────── */}
      {pending === 'replan' && !replanWhy && (
        <div className="run-form">
          <p className="run-hint">{REPLAN_CONFIRM}</p>
          <div className="run-form-actions">
            <button type="button" onClick={() => setPending(null)}>취소</button>
            <button type="button" className="danger" disabled={!!busy} onClick={doReplan}>
              {busy === '재분할 중' ? '재분할 중…' : '다시 나눕니다'}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

/** 비활성 이유를 **항상** 들고 다니는 버튼. 이유 없이 회색이 되는 경로를 만들지 않는다. */
function Btn({ label, why, busy, onClick, hint, primary, danger }: {
  label: string; why: string; busy: boolean; onClick: () => void;
  hint?: string; primary?: boolean; danger?: boolean;
}) {
  const disabled = !!why || busy;
  return (
    <button
      type="button"
      className={primary ? 'primary' : danger ? 'danger' : ''}
      disabled={disabled}
      onClick={onClick}
      // ⚠️ 이유를 `title` 에만 두지 않는다 — 터치·키보드에서 보이지 않는다.
      //   그래서 `aria-describedby` 대신 비활성 이유를 버튼 아래 줄로도 낸다.
      title={why || hint || label}
    >
      <span>{busy ? '진행 중…' : label}</span>
      {why && <em>{why}</em>}
    </button>
  );
}
