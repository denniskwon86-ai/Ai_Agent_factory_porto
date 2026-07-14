import { useEffect, useState } from 'react';
import { useFactoryStore, API_BASE_URL } from '../store/useFactoryStore';

export default function MegaBoardroomPanel() {
  const state = useFactoryStore((s) => s.state);
  const setCurrentProject = useFactoryStore((s) => s.setCurrentProject);
  
  const [subStates, setSubStates] = useState<Record<string, any>>({});
  const [initialIdeaInput, setInitialIdeaInput] = useState("");

  useEffect(() => {
    // Fetch state for all sub-projects
    const fetchSubStates = async () => {
      if (!state || !state.sub_projects_map) return;
      const newSubStates: Record<string, any> = {};
      for (const projId of Object.values(state.sub_projects_map)) {
        try {
          const res = await fetch(`${API_BASE_URL}/api/v1/factory/${projId}/state/latest`);
          if (res.ok) {
            const data = await res.json();
            newSubStates[projId as string] = data;
          }
        } catch (e) {
          console.error(`Failed to fetch state for ${projId}`, e);
        }
      }
      setSubStates(newSubStates);
    };

    fetchSubStates();
    const interval = setInterval(fetchSubStates, 3000);
    return () => clearInterval(interval);
  }, [state]);

  if (!state || !state.is_mega_project) {
    return <div className="p-10 text-white text-center">Not a Mega Project</div>;
  }

  const handleStartAll = async () => {
    const currentProjectId = useFactoryStore.getState().currentProjectId;
    if (!currentProjectId) return;
    if (!confirm("연결된 모든 서브 프로젝트의 시뮬레이션을 일괄 가동하시겠습니까?")) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/${currentProjectId}/mega/start_all`, {
        method: 'POST'
      });
      if (res.ok) {
        alert("일괄 가동이 시작되었습니다.");
      } else {
        alert("가동 실패");
      }
    } catch (e) {
      console.error(e);
    }
  };

  const getSubProjectProgress = (projId: string) => {
    const subState = subStates[projId];
    if (!subState) return 0;
    if (subState.factory_mode === 'QA_RELEASE') return 100;
    if (subState.factory_mode === 'PLANNING') return 10;
    if (subState.factory_mode === 'EXECUTION') return 50;
    if (subState.factory_mode === 'EXECUTION') return 50;
    return 0;
  };

  const DOMAIN_TEMPLATES: Record<string, string> = {
    sales: "수요 및 시장 예측 (manufacturing-market-forecast)",
    procurement: "원가 분석 및 재무 (manufacturing-cost-analysis)",
    production: "생산 시뮬레이션 (manufacturing-production)",
    quality: "품질 검증 (manufacturing-qc)",
    logistics: "생산 및 물류 시뮬레이션 (manufacturing-production)",
    marketing: "콘텐츠 마케팅 기획 (content-marketing)",
    finance: "원가 분석 및 재무 (manufacturing-cost-analysis)",
    accounting: "원가 분석 및 재무 (manufacturing-cost-analysis)"
  };

  return (
    <div className="h-full w-full bg-gray-950 flex flex-col font-sans overflow-hidden text-gray-200">
      <header className="h-16 bg-purple-900 border-b border-purple-700 flex items-center justify-between px-6 shrink-0 shadow-lg">
        <div className="flex items-center gap-4">
          <button onClick={() => setCurrentProject(null)} className="text-sm font-bold text-purple-200 hover:text-white bg-purple-800 px-3 py-1.5 rounded transition-colors">
            ◀ 런처로 복귀
          </button>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            🌟 {state.project_name} <span className="text-sm font-normal text-purple-300">| 마스터 관제 보드룸</span>
          </h1>
        </div>
        <div className="flex gap-4">
          <button onClick={handleStartAll} className="bg-emerald-600 hover:bg-emerald-500 text-white font-bold px-4 py-2 rounded shadow-lg transition-colors">
            ▶ 전체 시뮬레이션 가동
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto p-8">
        <div className="max-w-7xl mx-auto">
          {/* 중앙 마스터 버스 대시보드 */}
          <div className="bg-gray-900 border border-purple-600 rounded-lg p-6 mb-8 shadow-2xl">
            <h2 className="text-xl font-bold text-purple-400 mb-4 flex items-center gap-2">
              🧠 중앙 마스터 데이터 버스 (Shared Ledger)
            </h2>
            <div className="text-sm text-gray-400 mb-4">
              마스터 프로젝트에서 설정한 전사 경영 목표 및 거시 변수입니다. 모든 서브 프로젝트 에이전트의 컨텍스트에 실시간 주입됩니다.
            </div>
            <textarea
              className="w-full h-32 bg-gray-950 border border-gray-700 rounded p-4 text-sm font-mono text-purple-200 focus:outline-none focus:border-purple-500"
              placeholder="예: {'환율': 1400, '올해 영업이익 목표': '15% 상향'}"
              readOnly
              value={state.master_data || "초기 데이터가 설정되지 않았습니다."}
            />
          </div>

          {/* 마스터 초기 기획 수집 (HOTL) */}
          {(!state.master_data || Object.keys(state.master_data).length === 0) && (
            <div className="bg-amber-900/20 border border-amber-500 rounded-lg p-6 mb-8 shadow-xl">
              <h2 className="text-xl font-bold text-amber-400 mb-4 flex items-center gap-2">
                💡 초기 기획 수립 및 마스터 데이터 정의 (전문가 개입)
              </h2>
              <div className="text-sm text-gray-300 mb-4">
                첫 번째 마스터 에이전트가 사용자님의 기획을 바탕으로 필요한 초기 데이터(예: 예산, 타겟 시장, 주요 제약사항)를 추천해 드립니다.<br/>
                어떤 시나리오를 구성하실지 편하게 말씀해 주세요.
              </div>
              <textarea
                className="w-full h-24 bg-gray-900 border border-amber-700/50 rounded p-4 text-sm text-gray-100 focus:outline-none focus:border-amber-500 mb-4"
                placeholder="예: 니켈 원재료 가격 상승에 대비하여, 3분기 생산 공정의 원가를 분석하고 물류 최적화 방안을 도출하는 시뮬레이션을 돌리고 싶어."
                value={initialIdeaInput}
                onChange={(e) => setInitialIdeaInput(e.target.value)}
              />
              <button 
                onClick={async () => {
                  const currentProjectId = useFactoryStore.getState().currentProjectId;
                  if (!currentProjectId) return;
                  if (!initialIdeaInput.trim()) return alert("기획안을 입력해주세요.");
                  
                  try {
                    const res = await fetch(`${API_BASE_URL}/api/v1/factory/${currentProjectId}/mega/plan`, {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ initial_idea: initialIdeaInput })
                    });
                    if (res.ok) {
                      await res.json();
                      alert("초기 마스터 데이터가 설정되었습니다.");
                    } else {
                      alert("마스터 데이터 도출에 실패했습니다.");
                    }
                  } catch (e) {
                    console.error(e);
                  }
                }}
                className="bg-amber-600 hover:bg-amber-500 text-white font-bold px-6 py-2 rounded transition-colors shadow-lg"
              >
                🚀 기획안 전달 및 초기 데이터 추천받기
              </button>
            </div>
          )}

          {/* 서브 프로젝트 네트워크 맵 */}
          <h2 className="text-xl font-bold text-gray-300 mb-6 flex items-center gap-2">
            🌐 자율 연동망 (Agent Swarm Network)
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {Object.entries(state.sub_projects_map || {}).map(([domain, projId]) => {
              const subState = subStates[projId as string];
              const progress = getSubProjectProgress(projId as string);
              return (
                <div key={domain} className="bg-gray-800 border border-gray-700 rounded-xl p-5 hover:border-blue-500 transition-colors relative group shadow-lg flex flex-col">
                  <div className="flex justify-between items-start mb-2">
                    <h3 className="text-lg font-bold text-blue-400 uppercase">{domain}</h3>
                    <div className="text-xs font-mono bg-gray-900 px-2 py-1 rounded text-gray-500">{projId as string}</div>
                  </div>
                  <div className="text-xs text-purple-300 mb-4 h-8">
                    {DOMAIN_TEMPLATES[domain] || "범용 워크플로우 (default)"}
                  </div>
                  
                  <div className="flex-1 mb-4">
                    <div className="text-sm text-gray-300 mb-2">상태: <span className="font-bold text-white">{subState ? subState.factory_mode : '로딩중...'}</span></div>
                    <div className="w-full bg-gray-700 rounded-full h-2.5 mb-2">
                      <div className="bg-blue-500 h-2.5 rounded-full transition-all duration-500" style={{ width: `${progress}%` }}></div>
                    </div>
                  </div>
                  
                  <button onClick={() => setCurrentProject(projId as string)} className="w-full mt-auto bg-gray-700 hover:bg-blue-600 text-white font-bold py-2 rounded transition-colors text-sm">
                    🔍 상세 뷰 진입
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
