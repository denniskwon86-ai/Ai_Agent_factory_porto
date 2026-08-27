import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

import { Banner } from "../design/HubShell";
import "../design/afs.css";

interface EBProps { children: ReactNode; }
interface EBState { hasError: boolean; error: Error | null; }

export default class ErrorBoundary extends Component<EBProps, EBState> {
  constructor(props: EBProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error: Error): EBState {
    return { hasError: true, error };
  }
  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("🚨 React 컴포넌트 트리 크래시 방어:", error, errorInfo);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="afs-scope afs-page"
          style={{ minHeight: "100dvh", width: "100%", display: "grid", placeItems: "center", padding: 24 }}>
          <section role="alert" aria-label="화면 표시 오류"
            style={{
              width: "min(540px, 100%)", display: "flex", flexDirection: "column", gap: 18,
              padding: "34px 36px", border: "1px solid var(--surface-border)", borderRadius: 12,
              background: "var(--surface-card)", boxShadow: "var(--surface-shadow)",
            }}>
            <img src="/brand/laxs-logo-primary-on-white-v3.png" alt="LAXS"
              style={{ display: "block", width: 250, maxWidth: "82%", height: "auto", margin: "0 auto 4px" }} />
            <Banner tone="error" title="현재 화면을 표시할 수 없습니다">
              화면 처리 중 오류가 발생했습니다. 저장된 업무 데이터가 삭제된 것은 아닙니다.
            </Banner>
            <p className="afs-muted" style={{ margin: 0, fontSize: 13, lineHeight: 1.65, textAlign: "center" }}>
              다시 시도해도 같은 문제가 반복되면 시스템 관리자에게 현재 메뉴와 발생 시각을 알려 주십시오.
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <button type="button" className="secondary-button"
                onClick={() => { window.location.href = "/?space=enterprise"; }}>
                경영 홈으로
              </button>
              <button type="button" className="primary-button" onClick={() => window.location.reload()}>
                다시 시도
              </button>
            </div>
          </section>
        </div>
      );
    }
    return this.props.children;
  }
}
