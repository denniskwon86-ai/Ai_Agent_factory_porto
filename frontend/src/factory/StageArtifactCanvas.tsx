/**
 * [트랙 E · 6단계] 단계별 산출물 Canvas — RFP · 기획 · 아키텍처 · 기술명세 · 검수 · 매뉴얼 · Release.
 *
 * 근거: 구현 명세 §2.2(단계별 Adaptive Canvas 표) · §7-6(«순차 이식») · §8 신뢰성.
 *
 * ## 왜 여섯 컴포넌트가 아니라 하나인가
 *
 * 명세 §2.2 의 여섯 행은 «무엇을 보여 주는가» 만 다르고 **구조는 같다** — 문서 본문 + (있으면)
 * 판정 + 보조 검토 안내. 여섯 벌로 만들면 「없는 것을 어떻게 말하는가」 같은 규칙이 여섯 곳에
 * 흩어지고, 그중 한 곳만 고쳐지는 날이 온다. 그래서 **표로 선언하고 렌더는 한 번만** 한다.
 * 단계별로 정말 다른 둘(WBS·Release)만 분기한다.
 *
 * ## 지키는 것
 *
 * · **마크다운 렌더러를 새로 만들지 않는다.** `components/PreviewPanel.tsx` 의 `ManualRenderer`
 *   를 쓴다 — 복사하면 같은 문서가 두 화면에서 다르게 보인다.
 * · **«아직 없다» 와 «서버가 주지 않는다» 를 구분한다**(§8). 전자는 기다리면 생기고, 후자는
 *   기다려도 생기지 않는다 — 사용자가 해야 할 일이 다르다.
 * · **보조 검토 항목을 지어내지 않는다.** 명세는 「변경점」·「RFP 대비 Diff」·「영향 분석」·
 *   「수정 전후」를 요구하지만 서버가 그 재료를 주지 않는다. 빈 탭을 만들어 두는 대신 **무엇이
 *   없는지 적는다.**
 */
import { ManualRenderer } from '../components/PreviewPanel';

import type { FactoryStudioViewModel } from './factoryViewModel';

export interface StageArtifactCanvasProps {
  vm: FactoryStudioViewModel;
  stageId: string;
  stageLabel: string;
}

/** 단계별 표시 계약.
 *  · `aux` — **아직 없는 보조 검토**를 정직하게 적는 문구.
 *  · `noSource` — 채워져 있으면 **서버가 이 단계 요약을 아예 주지 않는다**는 뜻이다. 그 단계는
 *    기다려도 문서가 생기지 않으므로 «아직» 과 다르게 말해야 한다. */
const PLAN: Record<string, { title: string; aux: string; noSource?: string }> = {
  RFP: {
    title: '요구사항 정의서',
    aux: '요구 추적성·누락 조건 비교는 아직 없습니다 — 서버가 추적 매트릭스를 제공하지 않습니다.',
  },
  PLANNING: {
    title: '기획서(PRD)',
    aux: 'RFP 대비 Diff 는 아직 없습니다 — 두 문서의 차이를 서버가 계산해 주지 않습니다.',
  },
  ARCHITECTURE: {
    title: '아키텍처 설계',
    aux: '영향 분석·승인 이력은 아직 없습니다. 구조도는 문서 안의 설명으로만 제공됩니다.',
  },
  TECH_SPEC: {
    title: '기술 설계 명세',
    aux: '데이터 계약을 별도 표로 보여 주지 않습니다 — 문서 본문에 포함돼 있습니다.',
  },
  CODE_REVIEW: {
    title: '코드 심사 결과',
    aux: '수정 전후 비교는 아직 없습니다 — 서버가 diff 를 남기지 않습니다.',
  },
  QA: {
    title: '품질 검증 보고',
    aux: '테스트 목록·품질 게이트 상세는 문서 본문에 있습니다. 결정론적 로그는 근거·상태에서 봅니다.',
  },
  SUPERVISOR: {
    title: '수용 검수 보고',
    aux: '이 판정이 완료·배포 게이트입니다.',
  },
  MANUAL: {
    title: '사용자 매뉴얼',
    aux: '',
  },
  // ★ 아래 둘은 **서버가 요약 필드를 주지 않는다.** `text` 소스가 없으므로 `vm.docs` 에 키가
  //   영원히 생기지 않는다 — 그래서 «아직» 이 아니라 «없다» 로 말해야 한다. `noSource` 로 표시해
  //   그 문구를 따로 쓴다(같은 «아직 없습니다» 로 묶으면 사용자가 기다리게 된다).
  UI_DESIGN: {
    title: 'UI 흐름과 주요 결정',
    aux: '',
    noSource: '화면 설계는 이미지·목업으로 만들어지고 서버가 텍스트 요약을 남기지 않습니다.',
  },
  VISION_QA: {
    title: '화면 검증 결과',
    aux: '',
    noSource: '화면 검증은 스크린샷 판정이라 서버가 텍스트 요약을 남기지 않습니다.',
  },
};

/** 판정을 색이 아니라 **낱말과 색을 함께**로 말한다(§6). */
function verdictTone(v: string): 'pass' | 'fail' | 'unknown' {
  const s = v.trim().toUpperCase();
  if (s === 'PASS') return 'pass';
  if (s === 'FAIL' || s === 'REJECT') return 'fail';
  return 'unknown';
}

const VERDICT_KO: Record<string, string> = {
  PASS: '통과', FAIL: '불합격', REJECT: '반려',
};

export function StageArtifactCanvas({ vm, stageId, stageLabel }: StageArtifactCanvasProps) {
  const id = (stageId || '').toUpperCase();
  const plan = PLAN[id];
  const doc = vm.docs[id];

  // ① 이 단계에 산출물 개념이 아예 없다 — 서버가 요약 필드를 주지 않는 단계(UI_DESIGN 등).
  if (!plan) {
    return (
      <div className="canvas-pending">
        <h3>{stageLabel || '이 단계'}의 산출물 요약이 없습니다</h3>
        <p>
          서버가 이 단계에 대한 요약 필드를 제공하지 않습니다 — <b>아직 만들어지지 않은 것과는
          다릅니다.</b> 기다려도 이 자리에는 생기지 않습니다.
        </p>
        <p>산출물 파일 자체는 종전 통제실의 해당 탭에서 확인할 수 있습니다.</p>
      </div>
    );
  }

  // ② 서버가 이 단계 요약을 **아예 주지 않는다** — 기다려도 생기지 않는다.
  if (plan.noSource) {
    return (
      <div className="canvas-pending">
        <h3>{plan.title} 요약은 이 화면에 없습니다</h3>
        <p>
          {plan.noSource} <b>기다려도 이 자리에는 생기지 않습니다</b> — 아직 만들어지지 않은
          것과는 다른 사실입니다.
        </p>
        <p>산출물 자체는 종전 통제실의 해당 탭에서 확인할 수 있습니다.</p>
      </div>
    );
  }

  // ③ 단계는 알지만 아직 만들어지지 않았다.
  if (!doc) {
    return (
      <div className="studio-note" data-tone="loading">
        <b>{plan.title}이(가) 아직 없습니다</b>
        <p>
          이 단계가 실행되면 여기에 문서가 나타납니다. 지금 비어 있는 것은 <b>«아직»</b> 이며
          «서버가 주지 않는다» 가 아닙니다 — 진행되면 채워집니다.
        </p>
      </div>
    );
  }

  const tone = doc.verdict ? verdictTone(doc.verdict) : null;

  return (
    <article className="artifact-canvas">
      <header>
        <div>
          <small className="eyebrow">DELIVERABLE</small>
          <h2>{plan.title}</h2>
        </div>
        {doc.verdict && (
          <span className={`verdict-chip ${tone}`}>
            {/* 낱말을 먼저 쓴다 — 색을 못 보는 사용자에게 이것이 유일한 정보다. */}
            {VERDICT_KO[doc.verdict.trim().toUpperCase()] || doc.verdict}
            {tone === 'unknown' && ' (알 수 없는 판정값)'}
          </span>
        )}
      </header>

      {doc.text ? (
        <div className="artifact-body">
          <ManualRenderer markdown={doc.text} />
        </div>
      ) : (
        <div className="studio-note" data-tone="empty">
          <b>판정만 있고 본문이 없습니다</b>
          <p>
            이 단계는 판정({doc.verdict})을 남겼지만 보고서 본문이 비어 있습니다 — 판정 근거를
            확인할 수 없는 상태입니다.
          </p>
        </div>
      )}

      {plan.aux && (
        <footer className="artifact-aux">
          {/* 없는 보조 검토를 «준비 중» 으로 두지 않고 무엇이 없는지 적는다. */}
          <b>보조 검토</b>
          <p>{plan.aux}</p>
        </footer>
      )}
    </article>
  );
}

/** [6단계] Release Canvas — 버전·전달·회수. 문서가 아니라 **목록**이라 따로 둔다. */
export function ReleaseCanvas({ vm }: { vm: FactoryStudioViewModel }) {
  if (!vm.releases.length) {
    return (
      <div className="studio-note" data-tone="empty">
        <b>저장된 릴리스가 없습니다</b>
        <p>
          결과물을 저장(배포)하면 이 자리에 버전이 쌓입니다. 권한 Manifest·회수·롤백은 종전
          통제실의 «결과물 라이브러리» 에서 다룹니다 — 이 화면에는 아직 옮기지 않았습니다.
        </p>
      </div>
    );
  }
  return (
    <article className="artifact-canvas">
      <header>
        <div>
          <small className="eyebrow">RELEASE</small>
          <h2>저장된 릴리스 {vm.releases.length}건</h2>
        </div>
      </header>
      <div className="artifact-body">
        {vm.releases.map((r) => (
          <div className="inspect-row" key={r.id}>
            <time>{r.at ? r.at.slice(0, 10) : '—'}</time>
            <span>
              <b>{r.id}</b>
              <small>{r.status || '상태 미기록'}</small>
            </span>
          </div>
        ))}
      </div>
      <footer className="artifact-aux">
        <b>보조 검토</b>
        <p>
          Export·회수·롤백과 권한 Manifest 는 아직 이 화면에 없습니다 — 종전 통제실의
          «결과물 라이브러리» 에서 하십시오.
        </p>
      </footer>
    </article>
  );
}
