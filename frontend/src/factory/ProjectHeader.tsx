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
import { useState } from 'react';

import { useFactoryStore } from '../store/useFactoryStore';

import type { FactoryStudioViewModel } from './factoryViewModel';

export interface ProjectHeaderProps {
  vm: FactoryStudioViewModel;
  /** 「현재 결과 검토」 — 구현 단계 Canvas 로 옮긴다. */
  onReviewResult: () => void;
}

export function ProjectHeader({ vm, onReviewResult }: ProjectHeaderProps) {
  const stopSprint = useFactoryStore((s) => s.stopSprint);
  const [busy, setBusy] = useState(false);

  const { run } = vm;
  const canPause = !!(run.sprintId && vm.project.id);

  const pause = async () => {
    if (!canPause || busy) return;
    setBusy(true);
    try {
      // 기존 화면과 **같은 store 액션**을 부른다 — 별도 fetch 를 쓰면 중지 후 상태 정리가
      // 두 벌이 되고, 한쪽만 고쳐지는 날이 온다.
      await stopSprint(vm.project.id, run.sprintId);
    } finally {
      setBusy(false);
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
        <small>{run.wbsTotal ? 'WBS 완료' : 'WBS 상태'}</small>
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
          onClick={pause}
          disabled={!canPause || busy}
          title={canPause
            ? '진행 중인 스프린트를 중지합니다. 마지막 체크포인트에서 재개할 수 있습니다.'
            : '지금 중지할 스프린트가 없습니다(가동 중이 아닙니다).'}
        >
          {busy ? '중지 중…' : '일시정지'}
        </button>
        <button type="button" className="primary" onClick={onReviewResult}>
          현재 결과 검토
        </button>
      </div>
    </header>
  );
}
