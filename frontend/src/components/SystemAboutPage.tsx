import { useEffect } from 'react';
import { PRODUCT_EDITION, PRODUCT_NAME, PRODUCT_NAME_KO } from '../lib/brand';
import '../design/system-about.css';

type Props = {
  company: string;
  onBack: () => void;
  onCompanySetup: () => void;
};

const FLOW = [
  ['01', '현업 실행', '업무키트와 AI 비서가 현업의 업무 수행과 데이터 생성을 돕습니다.'],
  ['02', '신뢰 가능한 데이터', '출처·조직 범위·인증판·계보를 분리해 무엇을 믿고 쓸 수 있는지 밝힙니다.'],
  ['03', '경영 시뮬레이션', '같은 기준선에서 계획·실적·가정을 비교하고 영향 경로를 계산합니다.'],
  ['04', '의사결정과 실행', '근거가 결속된 안건을 검토하고 책임자·기한·후속 실적까지 연결합니다.'],
];

const PRINCIPLES = [
  ['현업 AX와 경영 AX를 하나의 흐름으로', '현업이 만든 업무 데이터가 경영 판단으로 이어지고, 경영의 결정은 다시 실행 현장으로 돌아갑니다.'],
  ['이중 입력이 아닌 Native-first', '업무키트는 기존 시스템과 역할이 겹치는 입력을 반복시키지 않고, 필요한 보완 업무만 LAXS 안에서 수행하도록 설계합니다.'],
  ['실적·가정·합성자료를 혼동하지 않음', '실제 실적, 시나리오 입력, 시연용 합성자료를 명시적으로 구분해 테스트 숫자가 경영 실적으로 읽히지 않게 합니다.'],
  ['승인과 증거가 없는 실행은 열지 않음', '계약·권한·데이터 준비도·산식 승인을 통과한 경로만 실행하고, 막힌 이유는 사용자가 다음 행동을 알 수 있게 설명합니다.'],
];

export function SystemAboutPage({ company, onBack, onCompanySetup }: Props) {
  const activeCompany = company || '회사 문맥 확인 중';

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
  }, []);

  return (
    <main className="laxs-about" aria-labelledby="laxs-about-title">
      <section className="laxs-about-hero">
        <div className="laxs-about-hero-copy">
          <span className="laxs-about-kicker">SYSTEM IDENTITY · {PRODUCT_EDITION}</span>
          <h1 id="laxs-about-title">LS의 일과 경영에 AX를 내재화하다.</h1>
          <p className="laxs-about-lead">
            <b>{PRODUCT_NAME} ({PRODUCT_NAME_KO})</b>는 <b>AX embedded in LS</b>의 의미를 담아,
            현업의 실행과 경영의 판단을 AX로 연결하는 LS 전용 업무·경영 운영체계입니다.
          </p>
          <div className="laxs-about-actions">
            <button type="button" className="laxs-about-primary" onClick={onBack}>경영 홈으로</button>
            <button type="button" className="laxs-about-secondary" onClick={onCompanySetup}>회사 연결구성 보기</button>
          </div>
        </div>
        <div className="laxs-about-logo-stack" aria-label="LAXS 로고 색상 체계">
          <figure className="laxs-about-logo-card laxs-about-logo-dark">
            <img src="/brand/laxs-logo-primary-on-navy-v2.png" alt="LAXS 어두운 배경 기본형" />
            <figcaption><b>기본형</b><span>어두운 배경</span></figcaption>
          </figure>
          <figure className="laxs-about-logo-card laxs-about-logo-light">
            <img src="/brand/laxs-logo-primary-on-white-v3.png" alt="LAXS 밝은 배경 반전형" />
            <figcaption><b>반전형</b><span>밝은 배경</span></figcaption>
          </figure>
          <p className="laxs-about-edition"><b>{PRODUCT_EDITION}</b><span>LS MnM 기준 첫 적용본</span></p>
        </div>
      </section>

      <section className="laxs-name-story" aria-labelledby="laxs-name-title">
        <div>
          <span className="laxs-about-kicker">NAME CONSTRUCTION</span>
          <h2 id="laxs-name-title">L과 S 사이에 AX를 심다</h2>
          <p>이름 자체가 시스템의 역할을 설명합니다. AX는 별도 도구로 옆에 붙는 것이 아니라 LS의 업무와 경영 안에 내재화됩니다.</p>
        </div>
        <div className="laxs-name-formula" aria-label="L 더하기 AX 더하기 S는 LAXS">
          <strong>L</strong><span>AX</span><strong>S</strong>
        </div>
        <blockquote>
          <b>LAXS — AX at the core of LS</b>
          <span>현업의 실행과 경영의 판단을 AX로 연결하다.</span>
        </blockquote>
      </section>

      <section className="laxs-about-section" aria-labelledby="laxs-flow-title">
        <span className="laxs-about-kicker">OPERATING MODEL</span>
        <h2 id="laxs-flow-title">하나의 데이터 흐름, 하나의 의사결정 폐루프</h2>
        <div className="laxs-flow-grid">
          {FLOW.map(([no, title, desc]) => (
            <article key={no}>
              <span>{no}</span><h3>{title}</h3><p>{desc}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="laxs-about-section laxs-about-split" aria-labelledby="laxs-principles-title">
        <div>
          <span className="laxs-about-kicker">DESIGN PRINCIPLES</span>
          <h2 id="laxs-principles-title">LAXS가 지키는 운영 원칙</h2>
          <p className="laxs-about-intro">빠르게 자동화하되, 데이터의 의미와 책임이 흐려지는 자동화는 만들지 않습니다.</p>
        </div>
        <div className="laxs-principle-list">
          {PRINCIPLES.map(([title, desc]) => (
            <article key={title}><h3>{title}</h3><p>{desc}</p></article>
          ))}
        </div>
      </section>

      <section className="laxs-about-section laxs-about-assistant" aria-labelledby="laxs-assistant-title">
        <div>
          <span className="laxs-about-kicker">AI MANAGEMENT ASSISTANT</span>
          <h2 id="laxs-assistant-title">자비스 · AI 경영비서</h2>
          <p>자비스는 회사 전체의 문맥과 사용자의 권한 범위 안에서 질문을 받고, 근거를 찾아 다음 행동을 제안합니다. 계산·승인·발간처럼 책임이 필요한 일은 전용 기능과 사람의 결정을 거칩니다.</p>
        </div>
        <aside>
          <small>CURRENT OPERATING CONTEXT</small>
          <b>{activeCompany}</b>
          <span>화면의 회사·조직 문맥이 데이터 조회와 답변 범위를 결정합니다.</span>
        </aside>
      </section>
    </main>
  );
}
