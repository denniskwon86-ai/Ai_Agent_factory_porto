import React, { Component, useEffect, useState } from 'react';
import type { ErrorInfo, ReactNode } from 'react';

import { useFactoryStore } from './store/useFactoryStore';

import { Group, Panel, Separator } from 'react-resizable-panels';

import ControlPanel from './components/ControlPanel';
import TimelinePanel from './components/TimelinePanel';
import PreviewPanel from './components/PreviewPanel';
import WorkflowStrip from './components/WorkflowStrip';
import AgentMasterPanel from './components/AgentMasterPanel';

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
  const deleteProject = useFactoryStore((state) => state.deleteProject);
  const setCurrentProject = useFactoryStore((state) => state.setCurrentProject);
  const statePayload = useFactoryStore((state) => state.state);
  const releases = useFactoryStore((state) => state.releases);
  const viewingRelease = useFactoryStore((state) => state.viewingRelease);
  const fetchReleases = useFactoryStore((state) => state.fetchReleases);
  const viewRelease = useFactoryStore((state) => state.viewRelease);
  const closeRelease = useFactoryStore((state) => state.closeRelease);
  const deleteRelease = useFactoryStore((state) => state.deleteRelease);
  const showAgentPanel = useFactoryStore((state) => state.showAgentPanel);
  const openAgentPanel = useFactoryStore((state) => state.openAgentPanel);
  const templates = useFactoryStore((state) => state.templates);
  const selectedTemplateId = useFactoryStore((state) => state.selectedTemplateId);
  const setSelectedTemplate = useFactoryStore((state) => state.setSelectedTemplate);
  const fetchTemplates = useFactoryStore((state) => state.fetchTemplates);

  const [newProjectId, setNewProjectId] = useState("");

  useEffect(() => {
    connectSSE();
    fetchProjects();
    fetchReleases();
    fetchTemplates();  // 신규 프로젝트 생성 시 고를 수 있는 워크플로우 템플릿 목록
  }, [connectSSE, fetchProjects, fetchReleases, fetchTemplates]);

  const handleCreateProject = async () => {
    if (!newProjectId.trim()) return;
    // 선택한 워크플로우 템플릿으로 프로젝트를 생성(범용 플랫폼) — 실패 사유는 store 가 alert 로 표면화
    const success = await createProject(newProjectId.trim(), selectedTemplateId);
    if (success) {
      setNewProjectId("");
      setCurrentProject(newProjectId.trim());
    }
  };

  const handleDeleteProject = async (id: string, name: string, e: React.MouseEvent) => {
    e.stopPropagation(); // 카드 진입 이벤트 전파 방지
    if (!confirm(`⚠️ [경고] 프로젝트 볼트 '${name} (${id})'를 완전히 삭제하시겠습니까?\n이 작업은 물리 디스크의 모든 산출물을 지우며 복구할 수 없습니다.`)) return;
    
    const success = await deleteProject(id);
    if (success) {
      alert("프로젝트가 안전하게 삭제되었습니다.");
    } else {
      alert("프로젝트 삭제 중 에러가 발생했습니다.");
    }
  };

  if (showAgentPanel) {
    return (
      <ErrorBoundary>
        <AgentMasterPanel />
      </ErrorBoundary>
    );
  }

  if (viewingRelease) {
    return (
      <ErrorBoundary>
        <div className="h-screen w-screen bg-gray-900 text-gray-100 flex flex-col font-sans overflow-hidden">
          <header className="h-14 bg-gray-800 border-b border-gray-700 flex items-center justify-between px-6 shrink-0">
            <div className="flex items-center gap-4 min-w-0">
              <button onClick={closeRelease} className="text-sm font-bold text-gray-400 hover:text-white bg-gray-700 px-3 py-1.5 rounded transition-colors shrink-0">◀ 라이브러리</button>
              <h1 className="text-lg font-bold text-white truncate">
                📦 결과물 실행: <span className="text-emerald-400">{viewingRelease.project_name}</span>
                <span className="text-xs text-gray-500 font-normal ml-2">{viewingRelease.created_at}</span>
              </h1>
            </div>
          </header>
          <div className="flex-1 overflow-hidden">
            <PreviewPanel rawCode={viewingRelease.frontend_code_summary || ""} release={viewingRelease} />
          </div>
        </div>
      </ErrorBoundary>
    );
  }

  if (!currentProjectId) {
    return (
      <ErrorBoundary>
        <div className="min-h-screen w-screen bg-gray-900 text-gray-100 flex flex-col font-sans">
          <header className="h-16 bg-gray-800 border-b border-gray-700 flex items-center justify-between px-8 shrink-0">
            <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
              🏭 V5.2 Private AI Cockpit
            </h1>
            <div className="flex items-center gap-4">
              <button
                onClick={openAgentPanel}
                className="text-sm font-bold text-gray-200 bg-gray-700 hover:bg-gray-600 px-3 py-1.5 rounded transition-colors"
                title="각 에이전트의 역할·스킬·모델·순서·HOTL을 설정"
              >
                ⚙️ 에이전트 마스터 제어판
              </button>
              <div className="flex items-center gap-2">
                <span className="text-sm text-gray-400 font-medium">통신망 상태:</span>
                <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500 animate-pulse'}`} />
              </div>
            </div>
          </header>

          <main className="flex-1 flex flex-col items-center p-10 overflow-y-auto">
            <div className="w-full max-w-4xl">
              <h2 className="text-xl font-bold text-gray-300 mb-6 flex items-center gap-2">
                📂 나의 프로젝트 가동 대장 (Vault Registry)
              </h2>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
                {projects.map((proj) => (
                  <div key={proj.id} className="bg-gray-800 border border-gray-700 rounded-lg p-6 hover:border-blue-500 transition-colors shadow-lg flex flex-col relative group">
                    {/* 🗑️ 독립 프로젝트 물리 삭제 버튼 추가 */}
                    <button
                      onClick={(e) => handleDeleteProject(proj.id, proj.name, e)}
                      className="absolute top-4 right-4 text-xs bg-red-950 hover:bg-red-600 text-red-400 hover:text-white border border-red-800 rounded px-2.5 py-1 transition-colors z-10"
                      title="프로젝트 폴더 영구 삭제"
                    >
                      🗑️ 완전 삭제
                    </button>

                    <div className="flex items-start justify-between mb-4 pr-24">
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

              <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 flex items-end gap-4 shadow-lg">
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
                <div className="w-64">
                  <label className="block text-sm font-bold text-gray-400 mb-2">🧩 워크플로우 템플릿</label>
                  <select
                    value={selectedTemplateId}
                    onChange={(e) => setSelectedTemplate(e.target.value)}
                    className="w-full bg-gray-900 border border-gray-600 rounded p-3 text-sm text-white focus:outline-none focus:border-green-500"
                    title="이 프로젝트가 사용할 에이전트 파이프라인을 선택합니다 (제어판에서 복사·편집)"
                  >
                    {templates.length === 0 && <option value="default">기본 워크플로우</option>}
                    {templates.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name || t.id}{t.builtin ? " (기본)" : ""}
                      </option>
                    ))}
                  </select>
                </div>
                <button
                  onClick={handleCreateProject}
                  disabled={!newProjectId.trim()}
                  className="bg-green-600 hover:bg-green-500 disabled:bg-gray-700 text-white font-bold py-3 px-6 rounded transition-colors whitespace-nowrap"
                >
                  신규 기획 공간 할당
                </button>
              </div>

              {/* 📦 결과물 라이브러리 (배포된 최종 산출물) */}
              <div className="mt-12">
                <h2 className="text-xl font-bold text-gray-300 mb-4 flex items-center gap-2">
                  📦 결과물 라이브러리 <span className="text-sm font-normal text-gray-500">— 배포된 최종 산출물</span>
                </h2>
                {releases.length === 0 ? (
                  <div className="text-gray-600 text-sm italic border border-dashed border-gray-700 rounded-lg p-6 text-center">
                    아직 배포된 결과물이 없습니다. 프로젝트를 완료한 뒤 통제실에서 <span className="text-gray-400">"최종 결과물 저장(배포)"</span>을 누르면 여기에 모입니다.
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {releases.map((rel: any) => (
                      <div key={rel.release_id} className="bg-gray-800 border border-gray-700 rounded-lg p-5 hover:border-emerald-500 transition-colors flex flex-col">
                        <div className="flex items-start justify-between mb-2 gap-2">
                          <h3 className="text-base font-bold text-emerald-400 truncate">{rel.project_name}</h3>
                          <button
                            onClick={() => { if (confirm(`결과물 '${rel.project_name}'을(를) 삭제하시겠습니까?`)) deleteRelease(rel.release_id); }}
                            className="text-xs text-red-400 hover:text-white hover:bg-red-600 border border-red-800 rounded px-2 py-0.5 shrink-0"
                            title="결과물 삭제"
                          >🗑</button>
                        </div>
                        <div className="text-xs text-gray-500 mb-4">{rel.created_at} · 태스크 {rel.task_count}개</div>
                        <button
                          onClick={() => viewRelease(rel.release_id)}
                          className="mt-auto w-full bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-2.5 rounded transition-colors"
                        >▶ 결과물 실행 / 미리보기</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </main>
        </div>
      </ErrorBoundary>
    );
  }

  // 🚀 [3단 레이아웃 독립 스크롤 최적화 설계 구조 적용]
  return (
    <ErrorBoundary>
      <div className="h-screen w-screen bg-gray-900 text-gray-100 flex flex-col font-sans overflow-hidden">
        <header className="h-14 bg-gray-800 border-b border-gray-700 flex items-center justify-between px-6 shrink-0 z-20">
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

        {/* 전체 워크플로우 진행 스트립 */}
        <WorkflowStrip />

        {/* 3단 레이아웃 — 드래그로 크기 조절 가능 (react-resizable-panels) */}
        <Group orientation="horizontal" className="flex-1 w-full h-full overflow-hidden flex">
          {/* 좌측: 제어반 */}
          <Panel defaultSize="22%" minSize="14%" className="h-full">
            <div className="bg-gray-800 flex flex-col h-full overflow-hidden">
              <ControlPanel />
            </div>
          </Panel>
          <Separator className="w-1.5 bg-gray-700 hover:bg-blue-500 transition-colors cursor-col-resize shrink-0" />

          {/* 중앙: 슈퍼바이저 콘솔 */}
          <Panel defaultSize="40%" minSize="20%" className="h-full">
            <div className="bg-gray-900 flex flex-col relative h-full overflow-hidden">
              <TimelinePanel />
            </div>
          </Panel>
          <Separator className="w-1.5 bg-gray-700 hover:bg-blue-500 transition-colors cursor-col-resize shrink-0" />

          {/* 우측: 다중 탭 및 렌더링 샌드박스 */}
          <Panel defaultSize="38%" minSize="20%" className="h-full">
            <div className="bg-gray-800 flex flex-col h-full overflow-hidden">
              <PreviewPanel rawCode={statePayload?.frontend_code_summary || ""} />
            </div>
          </Panel>
        </Group>
      </div>
    </ErrorBoundary>
  );
}