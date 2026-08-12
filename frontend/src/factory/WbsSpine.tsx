/**
 * [트랙 E · 2단계] WBS Spine — 작업, 선후행 의존관계, Agent, 차단 이유.
 *
 * 근거: 구현 명세 §2.1 · §4(`ControlPanel` WBS → `WbsSpine`, «의존관계·Agent·차단 이유 보강»)
 *       · §8 신뢰성.
 * 시각 SSOT: `adaptive-production-studio/index.html` 의 `.work-map`.
 *
 * ## 이 컴포넌트가 지키는 것
 *
 * 1. **«WBS 를 아직 만들지 않았다» 와 «0개» 를 구분한다.** 프로토타입도 그래서 «제작 준비 현황»
 *    이라는 별도 상태를 갖는다. 0개로 보여주면 사용자는 분할이 실패했다고 읽고 재분할을 누른다.
 * 2. **차단은 이유와 함께 말한다.** «차단» 세 글자만 보이면 사용자가 할 수 있는 일이 없다.
 *    무엇이 끝나야 풀리는지를 같은 줄에 적는다.
 * 3. **완료/진행/대기를 센 숫자는 실제 status 에서만 온다.** 프로토타입의 5/1/6 은 예시다.
 */
import { useMemo } from 'react';

import type { FactoryStudioViewModel, FactoryWbsKind, FactoryWbsVm } from './factoryViewModel';

export interface WbsSpineProps {
  vm: FactoryStudioViewModel;
  onSelectTask: (taskId: string) => void;
}

/** ★★★ [2026-08-06] **여기서 종류를 판정하지 않는다.** 종전에는 이 파일이 `status` 를 보고
 *  정하고 ViewModel 이 `blockedBy` 를 따로 계산했는데, 두 판정이 갈라져 **완료·진행 중인 작업이
 *  「차단」으로** 표시됐다(ViewModel 은 `'COMPLETED'` 만 완료로 봤고 실제 데이터는 `'DONE'`).
 *  판정은 `factoryViewModel` 의 `kind` 하나이고 이 컴포넌트는 그것을 **표시만** 한다. */
const KIND_KO: Record<FactoryWbsKind, string> = {
  // ⚠️ «사용자 대기» 와 «진행» 을 가른다 — 전자는 **내가** 움직여야 하고 후자는 기다리면 된다.
  //   사용자가 해야 할 일이 다르므로 같은 낱말로 묶으면 안 된다.
  done: '완료', awaiting: '사용자 대기', active: '진행', blocked: '차단', waiting: '대기',
};

/** 둘째 줄. 담당 Agent 와 차단 이유를 **있는 것만** 적는다(없는 것을 «미지정» 으로 채우지 않는다). */
function note(t: FactoryWbsVm, kind: FactoryWbsKind): string {
  if (kind === 'blocked' && t.blockedBy?.length) {
    return `${t.blockedBy.join(', ')} 완료 후 시작`;
  }
  // 사람이 답해야 넘어간다는 것을 그 줄에서 말한다 — Dock 까지 가야 알 수 있으면 늦다.
  if (kind === 'awaiting') return t.agent ? `${t.agent} · 내 승인이 필요합니다` : '내 승인이 필요합니다';
  return t.agent || '';
}

export function WbsSpine({ vm, onSelectTask }: WbsSpineProps) {
  const counts = useMemo(() => {
    const c = { done: 0, awaiting: 0, active: 0, waiting: 0, blocked: 0 };
    for (const t of vm.wbs) c[t.kind] += 1;
    return c;
  }, [vm.wbs]);

  // WBS 가 아직 없다 — «0개» 가 아니라 «만들기 전» 이다.
  if (!vm.wbs.length) {
    return (
      <aside className="work-map">
        <header className="map-head">
          <b>제작 준비 현황</b>
          <span>WBS 생성 전</span>
        </header>
        {vm.loadState === 'forbidden' || vm.loadState === 'error' ? (
          // 못 읽은 것을 «아직 만들지 않았다» 로 말하면 거짓이 된다(§8).
          <div className="studio-note" data-tone={vm.loadState}>
            <b>작업 목록을 읽지 못했습니다</b>
            <p>{vm.loadReason || '사유를 알 수 없습니다. 잠시 후 다시 시도하십시오.'}</p>
          </div>
        ) : (
          <div className="pre-wbs">
            <article className="pre-wbs-card">
              <h3>아직 WBS를 만들지 않았습니다</h3>
              <p>
                요구사항을 명확히 한 뒤 승인된 RFP와 기획서를 기준으로 작업을 분할합니다.
                분할 전에는 표시할 작업이 없습니다 — <b>작업 0개와는 다릅니다.</b>
              </p>
              <div className="deliverable-contract">
                <div><b>1</b> 선택형 요구 명확화</div>
                <div><b>2</b> RFP 초안과 사용자 승인</div>
                <div><b>3</b> 기획·아키텍처 확정</div>
                <div><b>4</b> WBS와 의존관계 생성</div>
              </div>
            </article>
          </div>
        )}
      </aside>
    );
  }

  return (
    <aside className="work-map">
      <header className="map-head">
        <b>WBS · 실행 구조</b>
        {/* ★ 내가 답해야 하는 것이 있으면 그것을 먼저 말한다 — «활성 N» 보다 급한 정보다. */}
        <span>{counts.awaiting ? `내 승인 대기 ${counts.awaiting}`
          : counts.active ? `활성 ${counts.active}` : '활성 없음'}</span>
      </header>

      <div className="map-summary">
        <div><b>{counts.done}</b><small>완료</small></div>
        {/* ⚠️ «사용자 대기» 를 «진행» 에 합치지 않는다 — 사용자가 해야 할 일이 다르다.
            합계에서도 빠뜨리지 않는다(빠지면 완료+진행+대기 ≠ 전체가 되어 표가 거짓이 된다). */}
        <div><b>{counts.awaiting}</b><small>사용자 대기</small></div>
        <div><b>{counts.active}</b><small>진행</small></div>
        {/* 대기와 차단을 한 칸에 합치되 **차단 수를 숨기지 않는다** — 차단은 사람이 볼 것이 있다. */}
        <div>
          <b>{counts.waiting + counts.blocked}</b>
          <small>{counts.blocked ? `대기 (차단 ${counts.blocked})` : '대기'}</small>
        </div>
      </div>

      <section className="map-section">
        <header>작업 {vm.wbs.length}개 · 완료 {counts.done}</header>
        {vm.wbs.map((t) => {
          const kind = t.kind;
          const sub = note(t, kind);
          const selected = vm.selectedWbsId === t.id;
          return (
            <button
              key={t.id}
              type="button"
              className="wbs-item"
              data-kind={kind}
              aria-current={selected || undefined}
              aria-label={`${t.id} ${t.title} — ${KIND_KO[kind]}${sub ? ` · ${sub}` : ''}`}
              onClick={() => onSelectTask(t.id)}
            >
              <i aria-hidden="true">{kind === 'done' ? '✓' : kind === 'awaiting' ? '⏸'
                : kind === 'active' ? '▶' : t.id.slice(-2)}</i>
              <span>
                <b>{t.id} {t.title}</b>
                {sub && <small>{sub}</small>}
              </span>
              <em>{KIND_KO[kind]}</em>
            </button>
          );
        })}
      </section>
    </aside>
  );
}
