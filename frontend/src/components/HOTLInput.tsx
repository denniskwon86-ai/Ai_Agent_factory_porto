import { useState } from 'react';
import { useFactoryStore } from '../store/useFactoryStore';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export default function HOTLInput() {
  const [feedback, setFeedback] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  
  const state = useFactoryStore((store) => store.state);
  // 🚨 [수정 1] 글로벌 스토어에서 현재 프로젝트 ID 동적 할당
  const currentProjectId = useFactoryStore((store) => store.currentProjectId);

  const isWaitingForHuman = state?.needs_revision || false;
  const currentTask = state?.current_sprint_task_id;

  const handleSubmit = async () => {
    // 🚨 [조치] 태스크 ID 누락 방어
    if (!currentTask) {
      alert("🚨 타겟 태스크(Task ID)를 찾을 수 없습니다. 통신 지연일 수 있으니 새로고침 후 시도해주세요.");
      return;
    }

    // 🚨 [수정 2] 프로젝트 ID 누락 방어
    if (!currentProjectId) {
      alert("🚨 현재 프로젝트 ID를 찾을 수 없습니다. 프로젝트를 다시 선택해주세요.");
      return;
    }
    
    setIsSubmitting(true);
    try {
      // 🚨 [수정 3] 하드코딩 경로 제거 및 currentProjectId 기반 동적 라우팅 적용
      const response = await fetch(`${API_BASE_URL}/api/v1/factory/${currentProjectId}/hotl/resume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_id: currentTask,
          feedback: feedback.trim()
        }),
      });

      if (!response.ok) {
        throw new Error(`서버 응답 오류 (상태 코드: ${response.status})`);
      }

      setFeedback("");
      
      // 전송 성공 시 즉시 UI 락(Lock)을 걸어 중복 클릭 방지
      useFactoryStore.setState((prev) => ({
        state: prev.state ? { ...prev.state, needs_revision: false } : null
      }));

    } catch (error) {
      console.error("🚨 HOTL 재가동 실패:", error);
      alert("파이프라인 재가동에 실패했습니다. 백엔드 서버를 확인해주세요.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="p-4 border-t border-gray-700 bg-gray-800 shrink-0">
      <div className="flex flex-col gap-3">
        
        <div className="flex justify-between items-center">
          <span className={`text-sm font-semibold ${isWaitingForHuman ? 'text-yellow-400' : 'text-blue-400'}`}>
            {isWaitingForHuman ? "⏸️ 인간의 개입(설계 승인/피드백)을 대기 중입니다" : "▶️ AI 팩토리 자율 가동 중"}
          </span>
          <span className="text-xs text-gray-400">Target Task: {currentTask || "알 수 없음"}</span>
        </div>
        
        <textarea 
          disabled={!isWaitingForHuman || isSubmitting}
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          placeholder={
            isWaitingForHuman 
              ? "설계를 승인하려면 빈칸으로 두고 전송하세요. 수정이 필요하면 요구사항을 입력하세요." 
              : "현재 파이프라인이 자율 주행 중입니다. 완료 시까지 개입할 수 없습니다."
          }
          className="w-full h-24 bg-gray-900 border border-gray-600 rounded p-3 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500 resize-none disabled:opacity-50 transition-colors"
        />
        
        <button 
          disabled={!isWaitingForHuman || isSubmitting} 
          onClick={handleSubmit}
          className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white font-semibold py-2.5 rounded transition-colors shadow-lg"
        >
          {isSubmitting ? "전송 중..." : (feedback.trim() ? "피드백 적용 후 재가동" : "현재 설계 최종 승인 및 즉시 진행")}
        </button>
      </div>
    </div>
  );
}