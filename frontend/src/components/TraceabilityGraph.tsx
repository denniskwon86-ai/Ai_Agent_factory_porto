import { useEffect, useState } from 'react';
import { useFactoryStore, API_BASE_URL } from '../store/useFactoryStore';

interface Mapping {
  task_id: string;
  fr_ids: string[];
  files: string[];
}

export default function TraceabilityGraph() {
  const currentProjectId = useFactoryStore((s) => s.currentProjectId);
  const [mappings, setMappings] = useState<Mapping[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!currentProjectId) return;
    setLoading(true);
    fetch(`${API_BASE_URL}/api/v1/factory/${currentProjectId}/traceability`)
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success') {
          setMappings(data.data || []);
        } else {
          setError(data.message || '데이터 조회 실패');
        }
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [currentProjectId]);

  if (!currentProjectId) return <div className="p-4 text-gray-400">프로젝트를 선택하세요.</div>;
  if (loading) return <div className="p-4 text-purple-300 animate-pulse">추적성 데이터를 불러오는 중...</div>;
  if (error) return <div className="p-4 text-red-400">오류: {error}</div>;
  if (mappings.length === 0) return <div className="p-4 text-gray-400">아직 매핑된 추적성 데이터가 없습니다. 구현 태스크가 완료되어야 생성됩니다.</div>;

  return (
    <div className="p-6 h-full overflow-y-auto bg-gray-900 text-gray-200">
      <h2 className="text-2xl font-bold text-gray-100 mb-6 flex items-center gap-2">
        🔗 산출물 추적성 엔진 (Traceability)
      </h2>
      <div className="space-y-6">
        {mappings.map((m, idx) => (
          <div key={idx} className="bg-gray-800 border border-gray-700 rounded-lg p-5 shadow-lg flex flex-col gap-4">
            <div className="flex justify-between items-center border-b border-gray-700 pb-3">
              <span className="text-lg font-bold text-purple-400">Task: {m.task_id}</span>
              <span className="text-xs bg-gray-700 text-gray-300 px-2 py-1 rounded">결정론적 매핑</span>
            </div>
            <div className="flex flex-col md:flex-row gap-6 items-start">
              {/* 기획 요구사항 블록 */}
              <div className="flex-1 bg-gray-900/50 p-4 rounded border border-gray-700/50 w-full">
                <h3 className="text-sm font-semibold text-gray-400 mb-3 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-blue-500"></span> 기획 요구사항 (PRD)
                </h3>
                {m.fr_ids && m.fr_ids.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {m.fr_ids.map(fr => (
                      <span key={fr} className="bg-blue-900/40 text-blue-300 px-3 py-1.5 rounded text-sm border border-blue-800/50 shadow-sm font-mono">
                        {fr}
                      </span>
                    ))}
                  </div>
                ) : (
                  <span className="text-sm text-gray-500 italic">요구사항(FR-ID) 매핑 없음</span>
                )}
              </div>

              {/* 화살표 */}
              <div className="hidden md:flex items-center justify-center text-gray-500 self-center">
                <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 8l4 4m0 0l-4 4m4-4H3"></path></svg>
              </div>

              {/* 산출물 코드 파일 블록 */}
              <div className="flex-1 bg-gray-900/50 p-4 rounded border border-gray-700/50 w-full">
                <h3 className="text-sm font-semibold text-gray-400 mb-3 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-emerald-500"></span> 산출물 소스코드
                </h3>
                {m.files && m.files.length > 0 ? (
                  <ul className="space-y-1.5">
                    {m.files.map(f => (
                      <li key={f} className="text-sm text-emerald-300 bg-emerald-900/20 px-2 py-1 rounded border border-emerald-800/30 break-all font-mono">
                        📄 {f}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <span className="text-sm text-gray-500 italic">생성된 파일 없음</span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
