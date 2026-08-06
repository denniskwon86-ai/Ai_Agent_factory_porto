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

import type { FactoryClarifyVm, FactoryStudioViewModel } from './factoryViewModel';

export interface AdaptivePhaseCanvasProps {
  vm: FactoryStudioViewModel;
  /** 지금 보고 있는 단계 id(선택이 없으면 현재 단계). */
  shownStageId: string;
  shownStageLabel: string;
}

/** 이 단계가 어느 Canvas 를 쓰는가. **단계 id 로만 판정한다** — 라벨은 템플릿마다 다르다. */
type CanvasKind = 'clarification' | 'implementation' | 'not_yet';

/** 구현으로 볼 단계 id. 커스텀 템플릿이 `EXECUTION`·`BUILD` 를 쓰는 것을 실측으로 확인했다. */
const IMPLEMENTATION_STAGES = new Set(['EXECUTION', 'BUILD', 'IMPLEMENTATION', 'CODE']);

function canvasKindOf(stageId: string): CanvasKind {
  const id = (stageId || '').toUpperCase();
  if (id === 'CLARIFICATION') return 'clarification';
  if (IMPLEMENTATION_STAGES.has(id)) return 'implementation';
  return 'not_yet';
}

/** 요구 확인 Canvas. 질문·추천 이유를 보여 주고 **답변은 받지 않는다**(4단계). */
function ClarificationCanvas({ clarify }: { clarify: FactoryClarifyVm }) {
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
            <div className="choice-grid">
              {q.options.map((o) => (
                <div
                  className={`choice${o.recommended ? ' recommended' : ''}`}
                  key={o.label}
                  // ⚠️ `button` 이 아니라 `div` 다. 3단계는 읽기 전용이고, 누를 수 있게 보이면
                  //   «눌렀는데 아무 일도 없는» 상태가 된다(그 오독을 이번 세션에 이미 한 번 겪었다).
                >
                  <b>{o.label}{o.recommended && <span className="rec-mark">추천</span>}</b>
                  {o.description && <small>{o.description}</small>}
                </div>
              ))}
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
            아래 <b>사용자 결정</b> 영역에서 답변을 제출합니다. 이 화면은 질문과 추천 근거를
            보여 주는 곳입니다.
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

/** 아직 이식하지 않은 단계. **무엇이 올 것인지와 지금 어디서 보는지**를 말한다. */
const NOT_YET_PLAN: Record<string, { what: string; where: string }> = {
  RFP: { what: 'RFP 본문·변경점·사용자 승인', where: '종전 통제실의 «요구정의(RFP)» 탭' },
  PLANNING: { what: '기능·업무 흐름·수용 기준과 RFP 대비 Diff', where: '종전 통제실의 «기획서» 탭' },
  UI_DESIGN: { what: 'UI 흐름과 주요 결정', where: '종전 통제실의 «UI 디자인» 탭' },
  VISION_QA: { what: '화면 검증 결과', where: '종전 통제실의 산출물 탭' },
  ARCHITECTURE: { what: '구조도·데이터 계약·주요 결정', where: '종전 통제실의 «아키텍처» 탭' },
  PMO: { what: '작업 분해·의존관계·Agent 배정', where: '왼쪽 WBS 실행 구조' },
  TECH_SPEC: { what: '기술 설계 명세', where: '종전 통제실의 «기술사양» 탭' },
  CODE_REVIEW: { what: '테스트·품질 게이트·결함과 수정 전후', where: '종전 통제실의 «리뷰» 탭' },
  QA: { what: '통합 검수 판정과 근거', where: '종전 통제실의 «QA» 탭' },
  SUPERVISOR: { what: '수용 검수 판정', where: '종전 통제실의 산출물 탭' },
  MANUAL: { what: '사용자 매뉴얼', where: '종전 통제실의 «매뉴얼» 탭' },
};

export function AdaptivePhaseCanvas({ vm, shownStageId, shownStageLabel }: AdaptivePhaseCanvasProps) {
  const kind = canvasKindOf(shownStageId);

  if (kind === 'clarification') return <ClarificationCanvas clarify={vm.clarify} />;
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
