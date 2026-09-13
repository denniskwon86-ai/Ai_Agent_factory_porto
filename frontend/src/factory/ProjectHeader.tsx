/**
 * [트랙 E · §2.1] Project Header — 프로젝트명 · 실행/중지 상태 · 지표 · 일시정지.
 *
 * 근거: 구현 명세 §2.1(상시 노출) · §8 기능 게이트(«Sprint … 일시정지 … 가 보존된다»).
 * 시각 SSOT: `adaptive-production-studio/index.html` 의 `.project-head`.
 *
 * ## 왜 이제 만드는가
 *
 * §7 의 7단계 목록에는 이 헤더가 없다. 그런데 §2.1 은 **상시 노출**로 못 박고, §8 기능 게이트는
 * 「Sprint 시작·일시정지·정지·재개·복구·재분할·Release·Export 가 보존된다」를 요구한다. 즉
 * **7단계(기존 3패널 제거)의 전제**다 — 이것 없이 3패널을 지우면 사용자가 실행을 멈출 수 없다.
 *
 * ## 지키는 것
 *
 * · **없는 지표를 0 으로 채우지 않는다.** 누적 LLM 비용은 이 store 에 없다 → 「측정값 없음」.
 *   ₩0 으로 쓰면 «공짜로 돌고 있다» 로 읽힌다.
 * · **상태를 낱말로 말한다**(§6). 색은 거들 뿐이고, 「가동 중」·「사용자 결정 대기」·
 *   「쿼터 소진으로 동결」·「마지막 실행 실패」·「대기」가 글자로 나온다.
 * · **일시정지는 중지할 것이 있을 때만 누를 수 있다.** 비활성 이유를 `title` 로 말한다 —
 *   회색 버튼만 보이면 사용자는 고장으로 읽는다.
 *
 * ⚠️ Sprint **시작**은 여기 없다. 그 경로는 아이디어 입력과 `project_state_payload` 조립이
 *   얽혀 있어(기존 `ControlPanel` 234행) 옮기려면 그 폼 전체를 가져와야 한다. 7단계 승격
 *   작업으로 남긴다 — 지금 옮기면 두 화면이 서로 다른 payload 를 보낼 위험이 있다.
 */
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';

import { useFactoryStore } from '../store/useFactoryStore';

import type { FactoryStudioViewModel } from './factoryViewModel';
import { studioIdentityKey } from './studioInputMemory';
import { hasExecutionPending, subscribeExecutionRecords } from '../lib/studioExecutionApi';

function subscribeExecutionUI(listener: () => void) {
  const events = ['factory:session-changed', 'factory:acting-user-changed', 'factory:enterprise-context-changed'];
  const unsubscribe = subscribeExecutionRecords(listener);
  events.forEach(name => window.addEventListener(name, listener));
  return () => { unsubscribe(); events.forEach(name => window.removeEventListener(name, listener)); };
}

export interface ProjectHeaderProps {
  vm: FactoryStudioViewModel;
  /** 「현재 결과 검토」 — 구현 단계 Canvas 로 옮긴다. */
  onReviewResult: () => void;
}

export function ProjectHeader(props: ProjectHeaderProps) {
  const identity = useSyncExternalStore(subscribeExecutionUI, studioIdentityKey, studioIdentityKey);
  return <CurrentProjectHeader key={JSON.stringify([identity, props.vm.project.id])} {...props} />;
}

function CurrentProjectHeader({ vm, onReviewResult }: ProjectHeaderProps) {
  const stopSprint = useFactoryStore((s) => s.stopSprint);
  const pauseSprint = useFactoryStore((s) => s.pauseSprint);
  const [busy, setBusy] = useState('');
  const busyRef = useRef(false);
  const active = useRef(false);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  const [confirmStop, setConfirmStop] = useState(false);
  const [message, setMessage] = useState('');
  const readPending = useCallback(() => hasExecutionPending(vm.project.id), [vm.project.id]);
  const executionPending = useSyncExternalStore(subscribeExecutionUI, readPending, () => false);

  const { run } = vm;
  const taskId = run.sprintId || vm.decisions[0]?.id || vm.inspect.suspendedTaskId;
  const canPause = !!(taskId && vm.project.id) && vm.connection === 'connected'
    && !['loading', 'error', 'forbidden'].includes(vm.loadState);

  const pause = async (stop = false) => {
    if (!canPause || busyRef.current) return;
    busyRef.current = true; setBusy(stop ? '중단' : '일시정지');
    const identity = studioIdentityKey();
    try {
      // 기존 화면과 **같은 store 액션**을 부른다 — 별도 fetch 를 쓰면 중지 후 상태 정리가
      // 두 벌이 되고, 한쪽만 고쳐지는 날이 온다.
      const result = await (stop ? stopSprint : pauseSprint)(vm.project.id, taskId);
      if (!active.current || identity !== studioIdentityKey() || useFactoryStore.getState().currentProjectId !== vm.project.id) return;
      setMessage(result.requestId
        ? `${stop ? '제작 중단' : '일시정지'} 요청 ID: ${result.requestId}. 아래 실행 요청 기록에서 원키의 접수 결과를 확인하세요. 접수 확인은 실제 중지 완료가 아닙니다.`
        : result.message || '요청 결과와 현재 실행 상태를 확인하세요.');
      if (result.ok) setConfirmStop(false);
    } catch (error) {
      if (active.current && identity === studioIdentityKey() && useFactoryStore.getState().currentProjectId === vm.project.id)
        setMessage(`중지 요청 결과를 확인하지 못했습니다. 자동 재전송하지 말고 아래 실행 요청 기록을 조회하세요. ${error instanceof Error ? error.message : ''}`);
    } finally {
      busyRef.current = false; if (active.current) setBusy('');
    }
  };

  return (
    <header className="project-head">
      <div className="project-title">
        <h1>{vm.project.name || vm.project.id || '프로젝트 미선택'}</h1>
        <p>{vm.project.mode ? `모드 ${vm.project.mode}` : 'SW 제작 작업공간'}</p>
      </div>

      {/* 실행 상태 — 낱말이 먼저, 점은 거든다. */}
      <div className={`project-state ${run.active ? 'on' : 'off'}`}>
        <i aria-hidden="true" />
        <span>{run.label}{run.sprintId && ` · ${run.sprintId}`}</span>
      </div>

      <div className="spacer" />

      <div className="head-metric">
        <b>{run.wbsTotal ? `${run.wbsDone} / ${run.wbsTotal}` : '생성 전'}</b>
        <small>{run.wbsTotal ? '작업 완료' : '작업 준비'}</small>
      </div>
      <div className="head-metric">
        <b>{vm.decisions.length}건</b>
        <small>사용자 결정</small>
      </div>
      <div className="head-metric">
        {/* ⚠️ 비용을 0 으로 채우지 않는다. «측정값 없음» 과 «₩0» 은 다른 사실이다. */}
        <b>{vm.project.cost === null ? '—' : `₩${vm.project.cost.toLocaleString()}`}</b>
        <small>{vm.project.cost === null ? '누적 비용 미측정' : '누적 LLM 비용'}</small>
      </div>

      <div className="head-actions">
        <button
          type="button"
          onClick={() => void pause()}
          disabled={!canPause || !!busy}
          title={canPause
            ? '서버가 대상 작업의 현재 상태를 다시 확인하여 일시정지를 처리합니다. 다른 명령 복구 중에도 중지 의도는 요청할 수 있습니다.'
            : '대상 작업·연결·조회 권한을 확인해야 합니다.'}
        >
          {busy === '일시정지' ? '요청 중…' : '일시정지'}
        </button>
        <button type="button" disabled={!canPause || !!busy} onClick={() => setConfirmStop(value => !value)}>제작 중단</button>
        <button type="button" className="primary" onClick={onReviewResult}>
          현재 결과 검토
        </button>
      </div>
      {confirmStop && <div className="studio-stop-confirm" role="group" aria-label="제작 중단 확인">
        <p>현재 제작 중단을 요청합니다. 화면 이동과는 다르며 기존 결과는 보존됩니다.</p>
        <button type="button" disabled={!!busy} onClick={() => setConfirmStop(false)}>계속 작업하기</button>
        <button type="button" disabled={!canPause || !!busy} onClick={() => void pause(true)}>중단 요청 보내기</button>
      </div>}
      {message && <p className="studio-command-message" role="status">{message}</p>}
      {executionPending && <p className="studio-command-message">미확정 실행 요청이 있습니다. 아래에서 원키 GET으로 확인할 수 있으며, 일시정지·제작 중단은 서버의 현재 상태 검사 후 별도로 요청할 수 있습니다.</p>}
    </header>
  );
}
