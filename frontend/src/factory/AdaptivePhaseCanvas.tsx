/**
 * [트랙 E · 3단계] AdaptivePhaseCanvas — 단계에 따라 중앙 화면을 바꾼다.
 *
 * 근거: 구현 명세 §2.2(단계별 Adaptive Canvas 표) · §7-3(«요구 확인·구현/실행 두 극단 먼저») ·
 *       §8 신뢰성.
 * 시각 SSOT: `adaptive-production-studio/index.html` 의 `.clarify-layout` · `.run-frame`.
 *
 * ## 왜 두 극단부터인가
 *
 * 요구 확인은 **아무 산출물이 없는 상태**이고 구현은 **실행 가능한 앱이 있는 상태**다. 이 둘이
 * 가장 멀기 때문에 먼저 만들면 나머지 여섯 단계는 그 사이에 들어간다. 중간 단계(RFP·기획·
 * 아키텍처·WBS·검증·Release)는 §7-6 의 순차 이식 대상이다.
 *
 * ## 아직 만들지 않은 단계를 어떻게 다루는가
 *
 * **빈 화면을 주지 않는다.** 그 단계가 무엇을 보여 줄 것인지, 지금은 어디서 볼 수 있는지 적는다.
 * 검토하는 사람이 빈 흰 화면을 만나면 «망가졌다» 로 읽고, 그 오독은 되돌리기 어렵다.
 *
 * ⚠️ **이 Canvas 는 읽기만 한다.** 답변 제출·승인은 4단계(Decision Dock)의 일이다(§2.3).
 *   여기에 제출 버튼을 미리 달면 «누르면 되는데 안 되는» 상태가 생긴다.
 */
import { GeneratedAppRuntime } from './GeneratedAppRuntime';
import { ReleaseCanvas, StageArtifactCanvas } from './StageArtifactCanvas';

import type { ClarifySelections } from './clarifyAnswers';
import type { FactoryClarifyVm, FactoryStudioViewModel } from './factoryViewModel';

export interface AdaptivePhaseCanvasProps {
  vm: FactoryStudioViewModel;
  /** 지금 보고 있는 단계 id(선택이 없으면 현재 단계). */
  shownStageId: string;
  shownStageLabel: string;
  /** [4단계] 요구 확인 선택 상태. **제출은 Dock 이 한다** — 선택과 제출을 나눈 것은 §2.2/§2.3 의
   *  분업이고, 그래서 상태는 둘의 공통 부모(Studio)가 갖는다. */
  selections: ClarifySelections;
  onToggleChoice: (questionId: string, label: string, multi: boolean) => void;
}

/** 이 단계가 어느 Canvas 를 쓰는가. **단계 id 로만 판정한다** — 라벨은 템플릿마다 다르다. */
type CanvasKind = 'clarification' | 'implementation' | 'wbs' | 'release' | 'artifact' | 'not_yet';

/** 구현으로 볼 단계 id. 커스텀 템플릿이 `EXECUTION`·`BUILD` 를 쓰는 것을 실측으로 확인했다. */
const IMPLEMENTATION_STAGES = new Set(['EXECUTION', 'BUILD', 'IMPLEMENTATION', 'CODE']);
/** [6단계] 산출물 성격의 단계 전부. `StageArtifactCanvas` 가 세 경우를 **한 곳에서** 판정한다:
 *  본문 있음 / 아직 없음 / **서버가 요약 필드를 아예 주지 않음**.
 *
 *  ★ [2026-08-06 실측] `UI_DESIGN`·`VISION_QA` 를 이 집합에서 빼 두었더니 「작업면이 아직 이
 *    화면에 없습니다 — 올 예정입니다」로 나갔다. **그것은 거짓이다** — 서버가 그 단계 요약을
 *    주지 않으므로 기다려도 생기지 않는다. 「아직」과 「없다」를 두 컴포넌트가 나눠 판정하면
 *    이렇게 어긋난다. 그래서 둘도 여기 넣고 판정을 한 곳으로 모았다. */
const ARTIFACT_STAGES = new Set([
  'RFP', 'PLANNING', 'ARCHITECTURE', 'TECH_SPEC', 'CODE_REVIEW', 'QA', 'SUPERVISOR', 'MANUAL',
  'UI_DESIGN', 'VISION_QA',
]);

function canvasKindOf(stageId: string): CanvasKind {
  const id = (stageId || '').toUpperCase();
  if (id === 'CLARIFICATION') return 'clarification';
  if (IMPLEMENTATION_STAGES.has(id)) return 'implementation';
  if (id === 'PMO' || id === 'WBS') return 'wbs';
  if (id === 'RELEASE') return 'release';
  if (ARTIFACT_STAGES.has(id)) return 'artifact';
  return 'not_yet';
}

/** [6단계] WBS 단계 Canvas — 작업 분해·의존관계·Agent 배정. **문서가 아니라 구조**라 따로 둔다.
 *
 * ⚠️ 왼쪽 WBS Spine 과 같은 데이터를 쓴다(`vm.wbs`) — 다른 소스를 쓰면 두 곳의 수가 갈라진다.
 *   Spine 은 «지금 무엇이 돌고 있나» 를 좁게 보여 주고, 여기서는 **의존관계와 배정을 펼친다.** */
function WbsCanvas({ vm }: { vm: FactoryStudioViewModel }) {
  if (!vm.wbs.length) {
    return (
      <div className="studio-note" data-tone="loading">
        <b>작업 분해가 아직 없습니다</b>
        <p>승인된 기획·아키텍처를 기준으로 작업을 분할하면 이 자리에 의존관계와 배정이 나타납니다.</p>
      </div>
    );
  }
  const KIND_KO: Record<string, string> = {
    done: '완료', active: '진행', blocked: '차단', waiting: '대기',
  };
  return (
    <article className="artifact-canvas">
      <header>
        <div>
          <small className="eyebrow">WORK BREAKDOWN</small>
          <h2>작업 {vm.wbs.length}개 · 의존관계와 배정</h2>
        </div>
      </header>
      <div className="artifact-body">
        <table className="wbs-table">
          <thead>
            <tr><th>작업</th><th>상태</th><th>담당</th><th>선행 조건</th></tr>
          </thead>
          <tbody>
            {vm.wbs.map((t) => (
              <tr key={t.id} data-kind={t.kind}>
                <th scope="row"><b>{t.id}</b> {t.title}</th>
                <td>{KIND_KO[t.kind] || t.kind}</td>
                {/* 없는 것을 «미지정» 으로 채우지 않는다 — 서버가 배정을 안 남긴 것과 아무도
                    배정되지 않은 것은 다르고, 화면은 그것을 구분할 근거가 없다. */}
                <td>{t.agent || '—'}</td>
                <td>
                  {t.blockedBy?.length
                    ? `${t.blockedBy.join(', ')} 완료 후 시작`
                    : (t.kind === 'waiting' ? '선행 조건 없음(순서 대기)' : '—')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <footer className="artifact-aux">
        <b>보조 검토</b>
        <p>
          재분할·잠금은 아직 이 화면에 없습니다 — 종전 통제실에서 «WBS 재분할» 을 쓰십시오.
          차단 사유는 위 표의 «선행 조건» 열이 그대로 말합니다.
        </p>
      </footer>
    </article>
  );
}

/** 요구 확인 Canvas. 질문·추천 이유를 보여 주고 **선택을 받는다**. 제출은 Dock 이 한다(§2.3). */
function ClarificationCanvas({ clarify, selections, onToggle }: {
  clarify: FactoryClarifyVm;
  selections: ClarifySelections;
  onToggle: (questionId: string, label: string, multi: boolean) => void;
}) {
  // 요약이 있으면 이 단계는 지나갔다. 그때 질문 카드를 다시 띄우면 «또 답해야 하나» 로 읽힌다.
  if (clarify.summary) {
    return (
      <div className="clarify-layout">
        <article className="clarify-main">
          <small className="eyebrow">GUIDED REQUIREMENT DISCOVERY</small>
          <h2>요구 확인이 끝났습니다</h2>
          <p>아래 요약이 다음 단계(RFP)의 입력으로 쓰입니다.</p>
          <section className="question-card">
            <h3>확정된 요구 요약</h3>
            <p>{clarify.summary}</p>
          </section>
        </article>
      </div>
    );
  }

  if (!clarify.questions.length) {
    return (
      <div className="studio-note" data-tone="loading">
        <b>질문을 아직 만들지 않았습니다</b>
        <p>
          요구 확인 단계가 시작되면 선택형 질문이 이 자리에 나타납니다. 긴 문서를 쓰지 않고
          추천안을 고르는 방식이며, 고른 내용이 그대로 RFP 로 이어집니다.
        </p>
      </div>
    );
  }

  return (
    <div className="clarify-layout">
      <article className="clarify-main">
        <small className="eyebrow">GUIDED REQUIREMENT DISCOVERY</small>
        <h2>무엇을 만들지 함께 구체화합니다</h2>
        <p>
          긴 문서를 작성할 필요 없이 추천안과 선택지를 통해 업무 목적을 정리하면 RFP 와 이후
          기획서에 그대로 연결됩니다.
        </p>

        {clarify.questions.map((q, i) => (
          <section className="question-card" key={q.id}>
            <h3>Q{i + 1}. {q.question}</h3>
            {/* 추천 근거를 밝힌다 — «왜 이것을 추천하는가» 가 없으면 사용자는 고를 수 없다. */}
            {clarify.initialIdea && (
              <p>처음 적은 «{clarify.initialIdea}» 를 기준으로 추천합니다.</p>
            )}
            {q.multi && <p>여러 개를 고를 수 있는 질문입니다.</p>}
            <div className="choice-grid" role={q.multi ? 'group' : 'radiogroup'}>
              {q.options.map((o) => {
                const picked = (selections[q.id] || []).includes(o.label);
                return (
                  // [4단계] 이제 **고를 수 있다.** 3단계에서는 `div` 로 두었다 — 제출 경로가
                  // 없는데 누를 수 있게 보이면 «눌렀는데 아무 일도 없는» 상태가 되기 때문이다.
                  <button
                    type="button"
                    className={`choice${o.recommended ? ' recommended' : ''}${picked ? ' picked' : ''}`}
                    key={o.label}
                    role={q.multi ? 'checkbox' : 'radio'}
                    aria-checked={picked}
                    onClick={() => onToggle(q.id, o.label, q.multi)}
                  >
                    <b>
                      {/* 고른 것을 **글자로도** 표시한다 — 테두리·배경만으로는 색을 구분하지
                          못하는 사용자에게 «무엇을 골랐는지» 가 사라진다(§6). */}
                      {picked ? '✓ ' : ''}{o.label}
                      {o.recommended && <span className="rec-mark">추천</span>}
                    </b>
                    {o.description && <small>{o.description}</small>}
                  </button>
                );
              })}
            </div>
          </section>
        ))}
      </article>

      <aside className="readiness">
        <h3>답변 진행</h3>
        <p>고른 내용이 RFP 초안의 근거가 됩니다.</p>
        {/* ⚠️ 명세 §2.2 는 «답변 준비도»·«권장 데이터» 도 요구하지만 **서버 상태에 그 근거가
            없다.** 없는 점수를 만들어 넣지 않는다 — 셀 수 있는 것은 질문 수뿐이다. */}
        <div className="ready-score">
          <b>{clarify.questions.length}</b>
          <span>개 질문</span>
        </div>
        <div className="need-list">
          <div>
            <strong>지금 할 일</strong>
            여기서 답을 고르고, 아래 <b>사용자 결정 대기</b> 영역에서 제출합니다. 고르지 않은
            질문은 추천안대로 진행됩니다.
          </div>
          <div>
            <strong>준비도 점수는 아직 없습니다</strong>
            서버가 답변 충분성을 계산해 주면 이 자리에 표시합니다. 지금 임의로 채우면 그 숫자가
            판단을 왜곡합니다.
          </div>
        </div>
      </aside>
    </div>
  );
}

/** 어느 Canvas 에도 해당하지 않는 단계 — **커스텀 워크플로우의 낯선 단계**를 위한 안내다.
 *
 * ★ [6단계] 기본 14단계는 이제 모두 Canvas 를 갖는다(요구 확인 · 구현 · WBS · Release ·
 *   산출물 8종 + 서버가 요약을 주지 않는 2종). 그래서 이 표는 비어 있고, 아래 기본 문구만
 *   남는다 — 커스텀 템플릿이 `MARKET_RESEARCH` 같은 단계를 정의하면 그때 여기로 온다.
 * ⚠️ 항목을 미리 채워 두지 않는다. 도달하지 않는 문구는 다음 사람이 «아직 안 됐구나» 로 읽는다. */
const NOT_YET_PLAN: Record<string, { what: string; where: string }> = {};

export function AdaptivePhaseCanvas({
  vm, shownStageId, shownStageLabel, selections, onToggleChoice,
}: AdaptivePhaseCanvasProps) {
  const kind = canvasKindOf(shownStageId);

  if (kind === 'clarification') {
    return (
      <ClarificationCanvas clarify={vm.clarify} selections={selections} onToggle={onToggleChoice} />
    );
  }
  if (kind === 'wbs') return <WbsCanvas vm={vm} />;
  if (kind === 'release') return <ReleaseCanvas vm={vm} />;
  if (kind === 'artifact') {
    return <StageArtifactCanvas vm={vm} stageId={shownStageId} stageLabel={shownStageLabel} />;
  }
  if (kind === 'implementation') return <GeneratedAppRuntime vm={vm} />;

  const plan = NOT_YET_PLAN[(shownStageId || '').toUpperCase()];
  return (
    <div className="canvas-pending">
      <h3>{shownStageLabel || '이 단계'}의 작업면은 아직 이 화면에 없습니다</h3>
      {plan ? (
        <>
          <p>여기에는 <b>{plan.what}</b>이 올 예정입니다(구현 순서 6단계).</p>
          <p>지금은 <b>{plan.where}</b>에서 볼 수 있습니다 — 종전 통제실은 그대로 있습니다.</p>
        </>
      ) : (
        <p>
          이 단계의 작업면은 아직 연결하지 않았습니다. 산출물은 종전 통제실의 해당 탭에서 볼 수
          있습니다.
        </p>
      )}
      <p>
        지금 이 화면이 실제 서버 상태로 보여 주는 것은 <b>전체 제작 단계</b>와
        <b> WBS 실행 구조</b>, 그리고 <b>요구 확인·구현</b> 두 단계의 작업면입니다.
      </p>
    </div>
  );
}
