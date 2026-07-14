import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

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
        <div className="min-h-screen bg-gray-900 flex flex-col items-center justify-center p-6 text-gray-200">
          <div className="max-w-2xl w-full bg-red-900/20 border border-red-500 rounded-lg p-6">
            <h2 className="text-xl font-bold text-red-500 mb-3">🚨 System Crash Prevented</h2>
            <p className="text-sm mb-4">하얀 화면(WSOD) 방어망이 작동했습니다. 에러를 확인하고 새로고침 하세요.</p>
            <pre className="bg-black/50 p-4 rounded text-red-400 text-xs overflow-auto max-h-64">
              {this.state.error?.stack || this.state.error?.toString()}
            </pre>
            <button onClick={() => window.location.reload()} className="mt-4 px-4 py-2 bg-red-600 hover:bg-red-500 text-white font-bold rounded">
              🔄 새로고침
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
