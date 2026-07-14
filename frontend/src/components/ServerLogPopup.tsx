import React, { useState, useEffect, useRef } from 'react';
import { useFactoryStore } from '../store/useFactoryStore';

interface ServerLogPopupProps {
  onClose: () => void;
}

export default function ServerLogPopup({ onClose }: ServerLogPopupProps) {
  const [logs, setLogs] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  
  const fetchLogs = async () => {
    setLoading(true);
    try {
      const { API_BASE_URL } = await import('../store/useFactoryStore');
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/logs`);
      if (res.ok) {
        const json = await res.json();
        if (json.data && Array.isArray(json.data)) {
          setLogs(json.data);
        }
      }
    } catch (e) {
      console.error("로그 불러오기 실패:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  return (
    <div className="absolute right-0 top-10 w-[600px] h-[400px] bg-black/95 backdrop-blur-md border border-gray-700 rounded-xl shadow-2xl flex flex-col z-50 overflow-hidden font-sans transform origin-top-right animate-fade-in">
      <div className="p-3 bg-gray-900 border-b border-gray-700 flex justify-between items-center shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-gray-300 font-bold text-sm">🖥️ 백엔드 서버 로그</span>
          <span className="text-xs text-gray-500">(최근 1,000줄)</span>
        </div>
        <div className="flex gap-2">
          <button 
            onClick={fetchLogs} 
            disabled={loading}
            className="bg-blue-600/80 hover:bg-blue-500 disabled:bg-gray-700 text-white px-3 py-1 rounded text-xs font-bold transition-colors"
          >
            {loading ? '⏳ 불러오는 중...' : '🔄 새로고침'}
          </button>
          <button 
            onClick={onClose}
            className="bg-gray-700 hover:bg-red-600 text-white px-3 py-1 rounded text-xs font-bold transition-colors"
          >
            ✕ 닫기
          </button>
        </div>
      </div>
      <div className="p-4 flex-1 overflow-y-auto whitespace-pre-wrap leading-relaxed text-green-400 font-mono text-[11px]">
        {logs.length === 0 ? (
          <div className="text-gray-500 italic flex items-center justify-center h-full">표시할 로그가 없습니다.</div>
        ) : (
          logs.map((l, i) => <div key={i} className="mb-0.5 break-all">{l}</div>)
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
}
