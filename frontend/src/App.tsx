import React, { Component, ErrorInfo, ReactNode, useEffect, useState } from 'react';
import { useFactoryStore } from './store/useFactoryStore';

import ControlPanel from './components/ControlPanel';
import TimelinePanel from './components/TimelinePanel';
import PreviewPanel from './components/PreviewPanel';

// 🛡️ 최상단 무결성 래퍼 (WSOD 셧다운 방어)
interface EBProps { children: ReactNode; }
interface EBState { hasError: boolean; error: Error | null; }

class ErrorBoundary extends Component<EBProps, EBState> {
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

export default function App() {
  const connectSSE = useFactoryStore((state) => state.connectSSE);
  const isConnected = useFactoryStore((state) => state.isConnected);
  const projects = useFactoryStore((state) => state.projects);
  const currentProjectId = useFactoryStore((state) => state.currentProjectId);
  const fetchProjects = useFactoryStore((state) => state.fetchProjects);
  const createProject = useFactoryStore((state) => state.createProject);
  const setCurrentProject = useFactoryStore((state) => state.setCurrentProject);

  const [newProjectId, setNewProjectId] = useState("");

  useEffect(() => {
    connectSSE();
    fetchProjects();
  }, [connectSSE, fetchProjects]);

  const handleCreateProject = async () => {
    if (!newProjectId.trim()) return;
    const success = await createProject(newProjectId.trim());
    if (success) {
      setNewProjectId("");
      setCurrentProject(newProjectId.trim());
    } else {
      alert("프로젝트 생성에 실패했습니다. (중복된 ID일 수 있습니다)");
    }
  };

  // 🚀 오리지널 런처(프로젝트 대장) 뷰어 렌더링
  if (!currentProjectId) {
    return (
      <ErrorBoundary>
        <div className="min-h-screen w-screen bg-gray-900 text-gray-100 flex flex-col font-sans">
          <header className="h-16 bg-gray-800 border-b border-gray-700 flex items-center justify-between px-8 shrink-0">
            <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
              🏭 V5.2 Private AI Cockpit
            </h1>
            <div className="flex items-center gap-3">
              <span className="text-sm text-gray-400 font-medium">통신망 상태:</span>
              <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500 animate-pulse'}`} />
            </div>
          </header>

          <main className="flex-1 flex flex-col items-center p-10 overflow-y-auto">
            <div className="w-full max-w-4xl">
              <h2 className="text-xl font-bold text-gray-300 mb-6 flex items-center gap-2">
                📂 나의 프로젝트 가동 대장 (Vault Registry)
              </h2>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
                {projects.map((proj) => (
                  <div key={proj.id} className="bg-gray-800 border border-gray-700 rounded-lg p-6 hover:border-blue-500 transition-colors shadow-lg flex flex-col">
                    <div className="flex items-start justify-between mb-4">
                      <h3 className="text-lg font-bold text-blue-400 truncate">{proj.name}</h3>
                      <span className="text-xs px-2 py-1 bg-gray-900 rounded text-gray-400 font-mono">{proj.id}</span>
                    </div>
                    <div className="flex-1 text-sm text-gray-400 mb-6">
                      이 프로젝트 볼트(Vault)는 완벽히 격리된 독립 환경에서 가동됩니다.
                    </div>
                    <button
                      onClick={() => setCurrentProject(proj.id)}
                      className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 rounded transition-colors flex items-center justify-center gap-2"
                    >
                      🔌 이 프로젝트 통제실로 진입
                    </button>
                  </div>
                ))}
              </div>

              <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 flex items-center gap-4 shadow-lg">
                <div className="flex-1">
                  <label className="block text-sm font-bold text-gray-400 mb-2">➕ 신규 독립 프로젝트 생성 (영문 ID)</label>
                  <input
                    type="text"
                    value={newProjectId}
                    onChange={(e) => setNewProjectId(e.target.value)}
                    placeholder="예: smart-life-app"
                    className="w-full bg-gray-900 border border-gray-600 rounded p-3 text-sm text-white focus:outline-none focus:border-green-500"
                  />
                </div>
                <button
                  onClick={handleCreateProject}
                  disabled={!newProjectId.trim()}
                  className="mt-6 bg-green-600 hover:bg-green-500 disabled:bg-gray-700 text-white font-bold py-3 px-6 rounded transition-colors whitespace-nowrap"
                >
                  신규 기획 공간 할당
                </button>
              </div>
            </div>
          </main>
        </div>
      </ErrorBoundary>
    );
  }

  // 🚀 오리지널 메인 통제실 뷰어 (3-Column Layout)
  return (
    <ErrorBoundary>
      <div className="h-screen w-screen bg-gray-900 text-gray-100 flex flex-col font-sans overflow-hidden">
        <header className="h-14 bg-gray-800 border-b border-gray-700 flex items-center justify-between px-6 shrink-0">
          <div className="flex items-center gap-4">
            <button 
              onClick={() => setCurrentProject(null)}
              className="text-sm font-bold text-gray-400 hover:text-white flex items-center gap-1 bg-gray-700 px-3 py-1.5 rounded transition-colors"
            >
              ◀ 런처 복귀
            </button>
            <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
              <span className="text-blue-400">[{currentProjectId}]</span> 통제실
            </h1>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-400 font-medium">실시간 통신망:</span>
            <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500 animate-pulse'}`} />
          </div>
        </header>

        <div className="flex-1 flex w-full h-full overflow-hidden">
          {/* 좌측: 제어반 */}
          <div className="w-1/5 bg-gray-800 flex flex-col border-r border-gray-700 shrink-0 min-w-[300px]">
            <ControlPanel />
          </div>

          {/* 중앙: 타임라인 */}
          <div className="w-2/5 bg-gray-900 flex flex-col relative border-r border-gray-700 shrink-0 min-w-[350px]">
            <TimelinePanel />
          </div>

          {/* 우측: 다중 탭 및 렌더링 샌드박스 */}
          <div className="flex-1 bg-gray-800 flex flex-col min-w-[350px]">
            <PreviewPanel />
          </div>
        </div>
      </div>
    </ErrorBoundary>
  );
}