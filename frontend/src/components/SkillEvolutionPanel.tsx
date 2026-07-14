import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../store/useFactoryStore';

interface SkillProposal {
  id: string;
  agent_id: string;
  proposed_rules: string[];
  analysis: string;
  created_at: string;
  status: string;
}

export function SkillEvolutionPanel({ onClose }: { onClose: () => void }) {
  const [proposals, setProposals] = useState<SkillProposal[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchProposals = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/skills/proposals`);
      if (res.ok) {
        const json = await res.json();
        setProposals(json.data || []);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProposals();
  }, []);

  const handleApprove = async (id: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/skills/proposals/${id}/approve`, { method: 'POST' });
      if (res.ok) {
        alert("스킬 개선안이 승인되어 에이전트 마크다운에 반영되었습니다.");
        fetchProposals();
      } else {
        alert("승인 처리 중 오류가 발생했습니다.");
      }
    } catch (e) {
      console.error(e);
      alert("네트워크 오류");
    }
  };

  const handleReject = async (id: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/skills/proposals/${id}/reject`, { method: 'POST' });
      if (res.ok) {
        fetchProposals();
      } else {
        alert("거부 처리 중 오류가 발생했습니다.");
      }
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-70 p-4">
      <div className="bg-gray-800 rounded-xl shadow-2xl border border-gray-700 w-full max-w-4xl max-h-[90vh] flex flex-col text-gray-200">
        <div className="p-4 border-b border-gray-700 flex justify-between items-center bg-gray-900 rounded-t-xl">
          <div className="flex items-center gap-2">
            <span className="text-xl">🧬</span>
            <h2 className="text-lg font-bold">스킬 진화 승인 대기열 (Skill Evolution Proposals)</h2>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white">✕</button>
        </div>

        <div className="p-6 overflow-y-auto flex-1">
          {loading ? (
            <div className="flex justify-center py-10">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-500"></div>
            </div>
          ) : proposals.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 px-6 text-center bg-gray-800/30 rounded-xl border border-gray-700/50 shadow-inner">
              <div className="text-5xl mb-4">🧬</div>
              <h3 className="text-xl font-bold text-gray-200 mb-2">스킬 개선 제안이 없습니다</h3>
              <div className="max-w-lg space-y-3 text-sm text-gray-400 leading-relaxed">
                <p>
                  <strong>AI 스킬 진화(Skill Evolution)</strong>란 에이전트가 업무 수행 중 반복되는 실수나 
                  사용자의 피드백을 학습하여, 스스로 자신의 프롬프트(마크다운 규칙)를 개선하는 시스템입니다.
                </p>
                <p className="bg-gray-900/50 p-3 rounded border border-gray-700 text-left">
                  <span className="text-blue-400 font-bold block mb-1">💡 작동 방식</span>
                  1. 에이전트가 작업 중 한계점이나 개선점을 스스로 인식합니다.<br/>
                  2. 에이전트가 새로운 규칙(제안)을 이 대기열에 등록합니다.<br/>
                  3. 사용자가 제안을 검토 후 <strong>승인</strong>하면 에이전트의 핵심 행동 규칙(마크다운)이 영구적으로 업데이트됩니다.
                </p>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {proposals.map(prop => (
                <div key={prop.id} className="bg-gray-900 border border-purple-500/30 rounded-lg p-5 shadow-lg relative overflow-hidden group">
                  <div className="absolute top-0 left-0 w-1 h-full bg-gradient-to-b from-purple-500 to-blue-500"></div>
                  <div className="flex justify-between items-start mb-3">
                    <div className="flex items-center gap-3">
                      <span className="bg-purple-900/50 text-purple-300 text-xs px-2 py-1 rounded font-mono border border-purple-500/30">
                        {prop.agent_id}
                      </span>
                      <span className="text-gray-400 text-xs">
                        {new Date(prop.created_at).toLocaleString()}
                      </span>
                    </div>
                  </div>
                  
                  <div className="mb-4">
                    <h4 className="text-sm text-gray-400 mb-1">🔍 자가 반성 분석:</h4>
                    <p className="text-sm text-gray-300 bg-gray-800 p-3 rounded-md italic border border-gray-700">
                      "{prop.analysis}"
                    </p>
                  </div>
                  
                  <div className="mb-4">
                    <h4 className="text-sm text-green-400 mb-2 flex items-center gap-1">
                      <span>💡</span> 개선안 (Prompt Rule 추가 제안):
                    </h4>
                    <ul className="space-y-2">
                      {prop.proposed_rules.map((rule, idx) => (
                        <li key={idx} className="text-sm text-gray-200 bg-gray-800/80 p-2 rounded border-l-2 border-green-500 pl-3">
                          {rule}
                        </li>
                      ))}
                    </ul>
                  </div>
                  
                  <div className="flex justify-end gap-2 mt-4 pt-4 border-t border-gray-800">
                    <button 
                      onClick={() => handleReject(prop.id)}
                      className="px-4 py-1.5 rounded bg-gray-800 text-gray-300 hover:bg-red-900/50 hover:text-red-300 border border-gray-700 transition-colors text-sm"
                    >
                      거부 (Reject)
                    </button>
                    <button 
                      onClick={() => handleApprove(prop.id)}
                      className="px-4 py-1.5 rounded bg-purple-600 text-white hover:bg-purple-500 transition-colors text-sm shadow-lg shadow-purple-500/20"
                    >
                      승인 및 적용 (Approve)
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
