import { useState, useEffect, useRef } from 'react';

interface ServerLogPopupProps {
  onClose: () => void;
}

export default function ServerLogPopup({ onClose }: ServerLogPopupProps) {
  const [logs, setLogs] = useState<string[]>([]);
  /** [설계 §9.3] 「Timeline 로그 **500건 제한**과 virtualization」.
   *
   * ⚠️ 서버 버퍼는 1,000줄인데 그것을 **전부 `<div>` 로 그리고 있었다.** 로그창은 켜 두는
   *   화면이라 그 1,000개가 계속 살아 있고, 새로고침마다 다시 만들어진다.
   *   virtualization 라이브러리를 들이는 대신 **기본은 최근 300줄만** 그리고, 필요할 때만
   *   전체를 편다 — 로그를 «지우는» 것이 아니라 **그리는 양**을 줄이는 것이다. */
  const [showAll, setShowAll] = useState(false);
  const [loading, setLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  
  //: ⚠️ [2026-08-23] **못 읽은 이유를 말한다.** 종전에는 `res.ok` 가 아니면 조용히
  //:   지나가 로그가 **빈 채로** 남았다 — 사용자는 「로그가 없다」로 읽는다.
  //:   서버 로그는 이제 관리자 전용이므로(스택 트레이스가 담긴다) 일반 계정은 403 을
  //:   받는다. 그 사실을 화면이 말하지 않으면 «고장» 으로 읽힌다.
  const [blocked, setBlocked] = useState('');

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const { API_BASE_URL } = await import('../store/useFactoryStore');
      const res = await fetch(`${API_BASE_URL}/api/v1/factory/logs`);
      if (res.ok) {
        setBlocked('');
        const json = await res.json();
        if (json.data && Array.isArray(json.data)) {
          setLogs(json.data);
        }
      } else if (res.status === 403) {
        setBlocked('서버 로그는 관리자만 볼 수 있습니다 — 로그에는 내부 경로와 오류 추적이 담깁니다.');
      } else if (res.status === 401) {
        setBlocked('로그인이 필요합니다.');
      } else {
        setBlocked(`로그를 불러오지 못했습니다 (${res.status}).`);
      }
    } catch (e) {
      setBlocked('서버에 연결하지 못했습니다.');
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
          {/* ⚠️ 라벨이 «최근 1,000줄» 이라고 단언하고 있었다 — 실제로 서버가 그만큼 갖고
              있는지, 지금 몇 줄을 그리고 있는지와 무관했다. **세어서 말한다.** */}
          <span className="text-xs text-gray-500">
            {logs.length === 0 ? '' :
              showAll ? `전체 ${logs.length}줄`
                : logs.length > 300 ? `최근 300줄 / 전체 ${logs.length}줄` : `${logs.length}줄`}
          </span>
        </div>
        <div className="flex gap-2">
          {logs.length > 300 && (
            <button
              onClick={() => setShowAll((v) => !v)}
              className="bg-gray-700 hover:bg-gray-600 text-white px-3 py-1 rounded text-xs font-bold transition-colors"
            >
              {showAll ? '최근 300줄만' : `전체 ${logs.length}줄 보기`}
            </button>
          )}
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
        {/* ⚠️ 「없다」와 「못 봤다」를 가른다 — 이 저장소가 반복해서 잡아 온 구분이다.
            권한이 없어서 못 본 것을 「로그가 없습니다」로 적으면 서버가 조용한 줄 안다. */}
        {blocked ? (
          <div className="text-amber-300 flex items-center justify-center h-full text-center px-6">
            {blocked}
          </div>
        ) : logs.length === 0 ? (
          <div className="text-gray-500 italic flex items-center justify-center h-full">표시할 로그가 없습니다.</div>
        ) : (
          //: 기본은 **뒤에서 300줄** — 로그는 최신이 중요하고, 옛것은 «전체 보기» 로 편다.
          (showAll ? logs : logs.slice(-300))
            .map((l, i) => <div key={i} className="mb-0.5 break-all">{l}</div>)
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
}
