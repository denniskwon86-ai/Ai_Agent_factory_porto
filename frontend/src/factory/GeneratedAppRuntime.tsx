/**
 * [트랙 E · 3단계] GeneratedAppRuntime — 구현 단계의 **기본** Canvas.
 *
 * 근거: 구현 명세 §2.2(구현 → 「생성 SW 실행 미리보기」가 중앙 기본 화면) ·
 *       §3(생성 SW 결과 계약) · §4(`PreviewPanel.tsx` → `GeneratedAppRuntime`, «구현 단계 기본
 *       Canvas로 승격»).
 * 시각 SSOT: `adaptive-production-studio/index.html` 의 `.run-frame`.
 *
 * ## 왜 iframe 런타임을 다시 쓰지 않는가
 *
 * 기존 `PreviewPanel.tsx`(658행)에는 **검증된 자산**이 들어 있다 — 샌드박스 iframe, 여러 파일을
 * 순서대로 등록하는 가상 모듈 레지스트리, `IFRAME_READY`/`EXECUTE_FILES` postMessage 프로토콜,
 * 새 창 팝업 싱글톤, 그리고 «우리 iframe 이 보낸 메시지만 처리» 하는 출처 검증.
 * 그것을 옮겨 적으면 **기능 회귀가 날 곳이 여덟 군데**다. 그래서 이 컴포넌트는 프로토타입의
 * 라이트 «실행 프레임» 만 만들고 안쪽 실행은 기존 컴포넌트에 맡긴다.
 *
 * 명세 §4 의 마지막 문단이 이 방식을 지시한다: 기존 컴포넌트를 한 번에 삭제하지 않고, 신규
 * Studio 가 **같은 API·SSE 상태를 읽는** 병행 카나리로 들어간 뒤 회귀가 없을 때 정리한다.
 * `rawCode` 는 종전 화면이 받던 값(`state.frontend_code_summary`)과 **같다** — 다른 소스를 쓰면
 * 두 화면이 다른 앱을 보여 주고, 그때 어느 쪽이 진짜인지 아무도 모른다.
 *
 * ⚠️ 「검토」·「구현 상세」 보조 화면은 아직 없다. §7-6 의 순차 이식 대상이고, **없는 것을 빈 탭으로
 *   만들어 두지 않는다** — 눌러서 아무것도 없으면 사용자는 고장으로 읽는다.
 */
import PreviewPanel from '../components/PreviewPanel';

import type { FactoryStudioViewModel } from './factoryViewModel';

export interface GeneratedAppRuntimeProps {
  vm: FactoryStudioViewModel;
}

export function GeneratedAppRuntime({ vm }: GeneratedAppRuntimeProps) {
  const { generated, project } = vm;

  // «만들어진 앱이 없다» 와 «지금 만들고 있다» 를 구분한다. 같은 빈 화면으로 보이면 사용자는
  // 기다려야 할 때 재실행을 누르고, 멈춘 것을 기다린다.
  if (!generated.runnable) {
    return (
      <div className="studio-note" data-tone={generated.building ? 'loading' : 'empty'}>
        <b>{generated.building ? '아직 만들고 있습니다' : '실행할 앱이 아직 없습니다'}</b>
        <p>
          {generated.building
            ? '구현 단계가 진행 중입니다. 코드가 나오면 이 자리에서 바로 실행됩니다 — '
              + '새로고침하지 않아도 됩니다.'
            : '구현 단계에 이르면 생성된 앱이 이 자리에서 실행됩니다. 코드와 테스트·API 계약은 '
              + '실행 결과를 검토한 뒤 보는 보조 산출물입니다.'}
        </p>
      </div>
    );
  }

  return (
    <article className="run-frame">
      <header>
        <span className="app-mark" aria-hidden="true">APP</span>
        <div>
          <h2>{project.name || '생성 SW'}</h2>
          <p>생성 SW 통합 미리보기 · 플랫폼 권한과 데이터를 상속합니다.</p>
        </div>
        <div className="spacer" />
        {/* 상태칩은 «지금 무엇을 보고 있는가» 다. 빌드 번호가 없으므로 만들지 않는다 —
            프로토타입의 «Build #14» 는 예시 데이터였다. */}
        <span className="status-chip">
          {generated.building ? '갱신 중' : '최신 산출물'}
        </span>
      </header>
      {/* ⚠️ 여기서 `PreviewPanel` 을 그대로 쓴다. 자체 탭(문서 뷰)을 갖고 있어 프로토타입의
          툴바와 겹쳐 보이지만, 지금 그것을 떼어내면 문서 열람 기능이 사라진다. §7-6 에서
          보조 검토 화면을 이식할 때 함께 정리한다. */}
      <div className="run-body">
        <PreviewPanel rawCode={generated.rawCode} isLoading={generated.building} />
      </div>
    </article>
  );
}
