import { useState, useEffect } from 'react';
import { create } from 'zustand';

// 주의: 단일 파일 샌드박스 환경에서의 컴파일 오류를 방지하기 위해 전역 스토어를 임시로 파일 내부에 선언했습니다. 
// 실제 로컬 프로젝트에 적용하실 때는 이 부분을 지우고 기존처럼 '../store/useFactoryStore'에서 import 해주세요.
export interface ProjectState {
  prd_summary?: string;
  architecture_summary?: string;
  tech_spec_summary?: string;
  frontend_code_summary?: string;
  backend_code_summary?: string;
  code_review_report_summary?: string;
}

interface FactoryStore {
  state: ProjectState | null;
}

const useFactoryStore = create<FactoryStore>(() => ({
  state: null
}));

export default function PreviewPanel() {
  const [activeTab, setActiveTab] = useState<'preview' | 'code'>('preview');
  const [iframeHtml, setIframeHtml] = useState<string>('');
  
  const state = useFactoryStore((s) => s.state);

  const getCodeContent = () => {
    if (!state) return "// [System] 팩토리 대기 중...\n/* 팩토리가 가동되면 생성된 산출물이 여기에 실시간으로 표시됩니다. */";
    
    let content = "";
    if (state.prd_summary) content += `\n\n=======================================================\n[🎯 Master PRD]\n=======================================================\n${state.prd_summary}`;
    if (state.architecture_summary) content += `\n\n=======================================================\n[📐 Architecture Decision]\n=======================================================\n${state.architecture_summary}`;
    if (state.tech_spec_summary) content += `\n\n=======================================================\n[🛠️ Tech Spec]\n=======================================================\n${state.tech_spec_summary}`;
    if (state.frontend_code_summary) content += `\n\n=======================================================\n[🎨 Frontend Code]\n=======================================================\n${state.frontend_code_summary}`;
    if (state.backend_code_summary) content += `\n\n=======================================================\n[⚙️ Backend Code]\n=======================================================\n${state.backend_code_summary}`;
    if (state.code_review_report_summary) content += `\n\n=======================================================\n[📝 Review Report]\n=======================================================\n${state.code_review_report_summary}`;

    return content.trim() || "// [System] 에이전트 작업 진행 중...";
  };

  useEffect(() => {
    if (!state?.frontend_code_summary) {
      setIframeHtml('');
      return;
    }

    const rawCode = state.frontend_code_summary;
    
    // 정규식 내 백틱(backtick) 3개 연속 사용 시 마크다운 파서와 충돌하는 문제를 방지하기 위해 {3} 수량자를 사용합니다.
    const regex = new RegExp('`{3}(?:tsx|jsx|javascript|js|typescript|ts)?\\n([\\s\\S]*?)`{3}');
    const match = rawCode.match(regex);
    let code = match ? match[1] : rawCode;

    code = code.replace(/import\s+.*?from\s+['"].*?['"];?\n?/g, '');

    let componentName = "App"; 
    const exportDefaultMatch = code.match(/export\s+default\s+(?:function\s+)?(\w+)/);
    if (exportDefaultMatch) {
        componentName = exportDefaultMatch[1];
        code = code.replace(/export\s+default\s+function/, 'function');
        code = code.replace(/export\s+default\s+\w+;?/, '');
    } else {
        const funcMatch = code.match(/function\s+(\w+)/);
        if (funcMatch) componentName = funcMatch[1];
    }

    const html = `
      <!DOCTYPE html>
      <html lang="ko">
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Live Preview Sandbox</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <script crossorigin src="https://unpkg.com/react@18/umd/react.development.js"></script>
        <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>
        <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
        <style>
          body { margin: 0; padding: 1.5rem; background-color: #ffffff; color: #1f2937; height: 100vh; overflow: auto; }
          * { box-sizing: border-box; }
        </style>
      </head>
      <body>
        <div id="root"></div>
        <script type="text/babel">
          try {
            ${code}
            
            const root = ReactDOM.createRoot(document.getElementById('root'));
            root.render(<${componentName} />);
          } catch (err) {
            document.getElementById('root').innerHTML = '<div style="color:#b91c1c; font-family:monospace; padding:20px; border:1px solid #f87171; background:#fef2f2; border-radius:8px;"><strong>🚨 AI 코드 컴파일 에러:</strong><br/><br/>' + err.message + '</div>';
          }
        </script>
      </body>
      </html>
    `;
    
    setIframeHtml(html);
  }, [state?.frontend_code_summary]);

  return (
    <div className="flex flex-col h-full bg-gray-900 overflow-hidden">
      
      <div className="flex bg-gray-800 border-b border-gray-700 shrink-0 px-2 pt-2">
        <button 
          onClick={() => setActiveTab('preview')}
          className={`px-4 py-2 text-sm font-semibold rounded-t-md transition-colors ${
            activeTab === 'preview' 
              ? 'bg-gray-900 text-blue-400 border-t border-x border-gray-700' 
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          👁️ Live Preview
        </button>
        <button 
          onClick={() => setActiveTab('code')}
          className={`px-4 py-2 text-sm font-semibold rounded-t-md transition-colors ${
            activeTab === 'code' 
              ? 'bg-gray-900 text-blue-400 border-t border-x border-gray-700' 
              : 'text-gray-400 hover:text-gray-200'
          }`}
        >
          💻 Generated Docs & Code
        </button>
      </div>

      <div className="flex-1 overflow-auto bg-gray-900 p-4">
        {activeTab === 'preview' ? (
          <div className="w-full h-full bg-white rounded-lg shadow-inner border-2 border-gray-700 overflow-hidden relative">
            {iframeHtml ? (
              <iframe 
                srcDoc={iframeHtml} 
                className="w-full h-full border-none"
                title="Live Preview Sandbox"
                sandbox="allow-scripts allow-same-origin"
              />
            ) : (
              <div className="flex flex-col items-center justify-center w-full h-full text-center">
                <span className="text-5xl mb-4 animate-pulse">⚙️</span>
                <p className="text-gray-500 font-bold text-lg">에이전트 산출물 대기 중...</p>
                <p className="text-sm text-gray-400 mt-2">Frontend Worker가 UI 코드를 생성하면 이곳에 렌더링됩니다.</p>
              </div>
            )}
          </div>
        ) : (
          <div className="w-full h-full bg-gray-950 rounded-lg border border-gray-700 p-4 overflow-auto shadow-inner">
            <pre className="text-gray-300 font-mono text-[13px] leading-relaxed whitespace-pre-wrap">
              {getCodeContent()}
            </pre>
          </div>
        )}
      </div>
      
    </div>
  );
}