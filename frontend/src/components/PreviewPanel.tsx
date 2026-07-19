import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useFactoryStore } from '../store/useFactoryStore';
import TraceabilityGraph from './TraceabilityGraph';

// 마크다운을 간단히 HTML로 변환하는 경량 렌더러 (외부 라이브러리 없음)
function ManualRenderer({ markdown }: { markdown: string }) {
  const lines = markdown.split('\n');
  const elements: React.ReactNode[] = [];
  let key = 0;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith('### ')) {
      elements.push(<h3 key={key++} className="text-base font-bold text-gray-800 mt-5 mb-1">{line.slice(4)}</h3>);
    } else if (line.startsWith('## ')) {
      elements.push(<h2 key={key++} className="text-lg font-bold text-gray-900 border-b border-gray-200 pb-1 mt-6 mb-2">{line.slice(3)}</h2>);
    } else if (line.startsWith('# ')) {
      elements.push(<h1 key={key++} className="text-xl font-extrabold text-blue-700 mb-4">{line.slice(2)}</h1>);
    } else if (/^(\d+)\. /.test(line)) {
      elements.push(<div key={key++} className="flex gap-2 text-sm text-gray-700 my-0.5 pl-2"><span className="font-bold text-blue-600 shrink-0">{line.match(/^(\d+)\. /)![1]}.</span><span>{line.replace(/^\d+\. /, '')}</span></div>);
    } else if (line.startsWith('- ') || line.startsWith('* ')) {
      elements.push(<div key={key++} className="flex gap-2 text-sm text-gray-700 my-0.5 pl-2"><span className="text-blue-500 shrink-0">•</span><span>{line.slice(2)}</span></div>);
    } else if (line.startsWith('**Q:') || line.startsWith('**Q :')) {
      elements.push(<p key={key++} className="text-sm font-bold text-gray-800 mt-3 mb-0.5">{line.replace(/\*\*/g, '')}</p>);
    } else if (line.startsWith('A:') || line.startsWith('A :')) {
      elements.push(<p key={key++} className="text-sm text-gray-600 mb-2 pl-3">{line}</p>);
    } else if (line.trim() === '') {
      elements.push(<div key={key++} className="h-2" />);
    } else {
      // 인라인 **bold** 처리
      const parts = line.split(/\*\*(.*?)\*\*/g);
      elements.push(
        <p key={key++} className="text-sm text-gray-700 leading-relaxed">
          {parts.map((p, idx) => idx % 2 === 1 ? <strong key={idx}>{p}</strong> : p)}
        </p>
      );
    }
  }
  return <>{elements}</>;
}


// --- Viewers ---
function MarkdownViewer({ rawCode }: { rawCode: string }) {
  const content = rawCode.replace(/^```(?:markdown)?\n/, '').replace(/\n```$/, '');
  return (
    <div className="w-full h-full bg-gray-100 overflow-y-auto p-8 flex justify-center">
      <div className="bg-white p-10 shadow-lg rounded-sm max-w-4xl w-full min-h-[1056px] prose prose-sm md:prose-base">
        <ManualRenderer markdown={content} />
      </div>
    </div>
  );
}

function JsonViewer({ rawCode }: { rawCode: string }) {
  let formatted = rawCode;
  try {
    let jsonStr = rawCode.trim();
    const mdMatch = jsonStr.match(/^```(?:json)?\s*(\{[\s\S]*\}|\[[\s\S]*\])\s*```$/);
    if (mdMatch) jsonStr = mdMatch[1];
    formatted = JSON.stringify(JSON.parse(jsonStr), null, 2);
  } catch(e) {}
  return (
    <div className="w-full h-full bg-gray-900 text-green-400 overflow-y-auto p-6 font-mono text-sm whitespace-pre-wrap">
      {formatted}
    </div>
  );
}

function SlideViewer({ rawCode }: { rawCode: string }) {
  const [currentSlide, setCurrentSlide] = React.useState(0);
  const content = rawCode.replace(/^```(?:markdown)?\n/, '').replace(/\n```$/, '');
  const slides = content.split('\n---\n').filter(s => s.trim() !== '');
  
  if (slides.length === 0) return <div className="p-8 text-center">슬라이드가 없습니다.</div>;

  return (
    <div className="w-full h-full bg-gray-900 flex flex-col items-center justify-center p-4 relative">
      <div className="w-full max-w-5xl aspect-video bg-white rounded-xl shadow-2xl p-12 overflow-y-auto flex flex-col justify-center">
         <div className="prose max-w-none"><ManualRenderer markdown={slides[currentSlide]} /></div>
      </div>
      <div className="absolute bottom-6 flex gap-4 bg-gray-800/80 px-4 py-2 rounded-full backdrop-blur">
         <button onClick={() => setCurrentSlide(s => Math.max(0, s - 1))} disabled={currentSlide === 0} className="text-white disabled:text-gray-500 font-bold px-3">이전</button>
         <span className="text-gray-300 font-mono flex items-center">{currentSlide + 1} / {slides.length}</span>
         <button onClick={() => setCurrentSlide(s => Math.min(slides.length - 1, s + 1))} disabled={currentSlide === slides.length - 1} className="text-white disabled:text-gray-500 font-bold px-3">다음</button>
      </div>
    </div>
  );
}

function MermaidViewer({ rawCode }: { rawCode: string }) {
  const containerRef = React.useRef<HTMLDivElement>(null);
  
  React.useEffect(() => {
    let code = rawCode.trim();
    const match = code.match(/^```mermaid\s*\n([\s\S]*?)\n```$/);
    if (match) code = match[1];

    if (!containerRef.current) return;
    
    const scriptId = 'mermaid-script';
    let script = document.getElementById(scriptId) as HTMLScriptElement;
    
    const renderDiagram = () => {
       const m = (window as any).mermaid;
       if (m) {
         m.initialize({ startOnLoad: false, theme: 'default' });
         containerRef.current!.innerHTML = '<div class="mermaid">' + code + '</div>';
         m.init(undefined, containerRef.current!.querySelectorAll('.mermaid'));
       }
    };

    if (!script) {
      script = document.createElement('script');
      script.id = scriptId;
      script.src = 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js';
      script.onload = () => {
         renderDiagram();
      };
      document.body.appendChild(script);
    } else {
      renderDiagram();
    }
  }, [rawCode]);

  return (
    <div className="w-full h-full bg-white overflow-auto p-8 flex items-center justify-center">
      <div ref={containerRef} className="max-w-full" />
    </div>
  );
}


interface PreviewPanelProps {
  rawCode: string;
  isLoading?: boolean;
  // 라이브러리 결과물 보기 모드: 문서 탭을 이 스냅샷에서 읽는다(현재/다른 프로젝트 state 노출 방지)
  release?: any;
}

type TabType = string;

interface CodeFile {
  file_path: string;
  code: string;
}

const PreviewPanel: React.FC<PreviewPanelProps> = ({ rawCode, isLoading, release }) => {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('PREVIEW');

  const [isIframeReady, setIsIframeReady] = useState<boolean>(false);
  const isIframeReadyRef = useRef<boolean>(false);
  // pendingFilesRef: 멀티파일 배열 캐시 (IFRAME_READY 수신 시 즉시 전송)
  const pendingFilesRef = useRef<CodeFile[]>([]);

  // 전체화면(인앱 오버레이) / 새 창(독립 OS 창) 상태
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isPoppedOut, setIsPoppedOut] = useState(false);
  const popupRef = useRef<Window | null>(null);

  const statePayload = useFactoryStore((s) => s.state);
  // release(라이브러리 결과물)가 주어지면 문서 탭은 그 스냅샷에서 읽는다. 그렇지 않으면 현재 프로젝트 state.
  const docs: any = release ?? statePayload;
  const isConnected = useFactoryStore((s) => s.isConnected);
  const triggerSelfHealing = useFactoryStore((s) => s.triggerSelfHealing);
  const isConnectedRef = useRef(isConnected);
  useEffect(() => { isConnectedRef.current = isConnected; }, [isConnected]);
  // release(라이브러리 결과물) 보기 모드 추적 — message 핸들러 재구독 없이 최신값 참조
  const releaseRef = useRef<any>(null);
  useEffect(() => { releaseRef.current = release; }, [release]);

  const currentTemplateData = useFactoryStore((s) => s.currentTemplateData);
  const isDynamic = currentTemplateData && currentTemplateData.agents && currentTemplateData.id !== 'default' && currentTemplateData.pipeline_name !== '소프트웨어 개발 팩토리';

  // ─────────────────────────────────────────────────────────────────────────
  // iframe HTML 템플릿
  // 가상 모듈 레지스트리: 여러 파일을 순서대로 컴파일·등록 후 App을 렌더링
  // ─────────────────────────────────────────────────────────────────────────
  const htmlTemplate = `
    <!DOCTYPE html>
    <html lang="ko">
      <head>
        <meta charset="UTF-8" />
        <title>AI Factory Preview</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <script src="https://unpkg.com/react@18/umd/react.development.js" crossorigin></script>
        <script src="https://unpkg.com/react-dom@18/umd/react-dom.development.js" crossorigin></script>
        <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
        <script src="https://unpkg.com/lucide@latest"></script>
        <style>
          body { margin: 0; padding: 0; font-family: sans-serif; background: #f8fafc; }
          #root { min-height: 100vh; display: flex; flex-direction: column; }
          .loader { padding: 20px; color: #64748b; font-weight: bold; text-align: center; }
        </style>
      </head>
      <body>
        <div id="root"><div class="loader">컴포넌트 렌더링 대기 중...</div></div>

        <script>
          window.onerror = function(msg) {
            (window.opener || window.parent).postMessage({ type: 'PREVIEW_ERROR', message: msg }, '*');
            return false;
          };

          function notifyReady() {
            if (typeof Babel === 'undefined' || typeof React === 'undefined' || typeof ReactDOM === 'undefined') {
              setTimeout(notifyReady, 50);
              return;
            }
            (window.opener || window.parent).postMessage({ type: 'IFRAME_READY' }, '*');
          }
          notifyReady();

          // ── 유틸 ──────────────────────────────────────────────────────────
          function isRenderable(v) {
            if (typeof v === 'function') return true;
            if (v && typeof v === 'object' && v.$$typeof) return true;
            return false;
          }

          function createModuleStub() {
            var stub = function Stub() { return null; };
            stub.__esModule = true;
            stub.default = function Stub() { return null; };
            if (typeof Proxy !== 'undefined') {
              return new Proxy(stub, {
                get: function(t, p) { return (p in t) ? t[p] : function Stub() { return null; }; }
              });
            }
            return stub;
          }

          // ── 가상 모듈 레지스트리 ──────────────────────────────────────────
          // key: 정규화된 경로(예: "pages/RawMaterialPage")
          // value: { default, [named exports] }
          var moduleRegistry = {};

          function normalizePath(p) {
            // src/ prefix 제거, 확장자 제거
            return p.replace(/^\\.\\//,'').replace(/^src\\//,'').replace(/\\.(tsx?|jsx?)$/,'');
          }

          function resolveRelative(from, to) {
            var fromParts = from.split('/');
            fromParts.pop();
            var toParts = to.replace(/^\\.\\//,'').split('/');
            for (var i = 0; i < toParts.length; i++) {
              var seg = toParts[i];
              if (seg === '..') fromParts.pop();
              else if (seg !== '.') fromParts.push(seg);
            }
            return fromParts.join('/');
          }

          function lookupRegistry(key) {
            var norm = normalizePath(key);
            // exact match
            if (moduleRegistry[norm]) return moduleRegistry[norm];
            // prefix match (src/ stripped)
            var keys = Object.keys(moduleRegistry);
            for (var i = 0; i < keys.length; i++) {
              if (normalizePath(keys[i]) === norm) return moduleRegistry[keys[i]];
            }
            return null;
          }

          function makeRequire(fromPath) {
            return function require(mod) {
              if (mod === 'react') return window.React;
              if (mod === 'react-dom' || mod === 'react-dom/client') return window.ReactDOM;
              if (mod === 'lucide-react' && typeof window.lucide !== 'undefined') return window.lucide;

              if (mod.startsWith('.')) {
                var resolved = resolveRelative(fromPath, mod);
                var found = lookupRegistry(resolved);
                if (found) return found;
              }
              return createModuleStub();
            };
          }

          function compileAndRegister(file) {
            try {
              var compiled = Babel.transform(file.code, {
                presets: [
                  ['env', { modules: 'commonjs' }],
                  ['react', { runtime: 'classic' }],
                  'typescript'
                ],
                filename: file.file_path
              }).code;

              var fileExports = {};
              var fileModule = { exports: fileExports };
              var fn = new Function('exports', 'module', 'require', 'React', compiled);
              fn(fileExports, fileModule, makeRequire(file.file_path), window.React);

              var result = fileModule.exports.__esModule ? fileModule.exports : fileExports;
              var key = normalizePath(file.file_path);
              moduleRegistry[key] = result;
            } catch (e) {
              console.warn('[VMR] 컴파일 실패:', file.file_path, e.message);
            }
          }

          function renderRoot(TargetComponent) {
            if (!window.__reactRoot) {
              window.__reactRoot = ReactDOM.createRoot(document.getElementById('root'));
            }
            window.__reactRoot.render(React.createElement(TargetComponent));
          }

          // ── 메인 실행 핸들러 ──────────────────────────────────────────────
          function executeFiles(files) {
            // main.tsx / index.tsx 는 DOM 마운트 코드라 제외
            var filtered = files.filter(function(f) {
              return !f.file_path.match(/[\\/](main|index)\\.(tsx?|jsx?)$/)
                  && !f.file_path.match(/^(main|index)\\.(tsx?|jsx?)$/);
            });

            // App.tsx 마지막에 컴파일되도록 정렬 (의존성 먼저)
            filtered.sort(function(a, b) {
              var aIsApp = /[\\/]App\\.(tsx?|jsx?)$/i.test(a.file_path) || /^App\\.(tsx?|jsx?)$/i.test(a.file_path);
              var bIsApp = /[\\/]App\\.(tsx?|jsx?)$/i.test(b.file_path) || /^App\\.(tsx?|jsx?)$/i.test(b.file_path);
              return (aIsApp ? 1 : 0) - (bIsApp ? 1 : 0);
            });

            // 가상 레지스트리 초기화 후 순서대로 등록
            moduleRegistry = {};
            filtered.forEach(compileAndRegister);

            // App 컴포넌트 탐색
            var TargetComponent = null;

            // 1순위: App.tsx
            var appKeys = Object.keys(moduleRegistry).filter(function(k) {
              return /[\\/]App$/i.test(k) || k.toLowerCase() === 'app';
            });
            for (var i = 0; i < appKeys.length; i++) {
              var exp = moduleRegistry[appKeys[i]];
              var cand = exp.default || Object.values(exp).find(isRenderable);
              if (isRenderable(cand)) { TargetComponent = cand; break; }
            }

            // 2순위: 가장 많은 코드를 가진 컴포넌트 파일
            if (!TargetComponent) {
              var sortedBySize = filtered
                .filter(function(f) { return !/[\\/]App\\./i.test(f.file_path) && !/^App\\./i.test(f.file_path); })
                .sort(function(a, b) { return (b.code || '').length - (a.code || '').length; });
              for (var j = 0; j < sortedBySize.length; j++) {
                var key = normalizePath(sortedBySize[j].file_path);
                var exp2 = moduleRegistry[key];
                if (!exp2) continue;
                var cand2 = exp2.default || Object.values(exp2).find(isRenderable);
                if (isRenderable(cand2)) { TargetComponent = cand2; break; }
              }
            }

            // 3순위: 레지스트리 전체 탐색
            if (!TargetComponent) {
              var allKeys = Object.keys(moduleRegistry);
              for (var k = 0; k < allKeys.length; k++) {
                var exp3 = moduleRegistry[allKeys[k]];
                var cand3 = exp3.default || Object.values(exp3).find(isRenderable);
                if (isRenderable(cand3)) { TargetComponent = cand3; break; }
              }
            }

            if (TargetComponent) {
              renderRoot(TargetComponent);
            } else {
              throw new Error('렌더링 가능한 컴포넌트를 찾을 수 없습니다. (등록된 파일: ' + Object.keys(moduleRegistry).join(', ') + ')');
            }
          }

          window.addEventListener('message', function(event) {
            if (event.data.type === 'EXECUTE_FILES') {
              try {
                executeFiles(event.data.files || []);
              } catch (err) {
                document.getElementById('root').innerHTML =
                  '<div style="background:#fee2e2;color:#b91c1c;padding:20px;margin:10px;border-radius:8px;border:1px solid #f87171;">' +
                  '<h3 style="margin-top:0;">🚨 렌더링 에러</h3><pre style="white-space:pre-wrap;font-size:13px;">' + err.message + '</pre></div>';
                (window.opener || window.parent).postMessage({ type: 'PREVIEW_ERROR', message: err.message }, '*');
              }
            }
          });
        </script>
      </body>
    </html>
  `;

  // ── rawCode 에서 코드파일 배열 추출 ────────────────────────────────────────
  const extractCodeFiles = useCallback((raw: string): CodeFile[] => {
    if (!raw) return [];

    // 1차: JSON { files: [...] }
    try {
      let jsonStr = raw.trim();
      const mdMatch = jsonStr.match(/`{3}(?:json)?\s*(\{[\s\S]*\})\s*`{3}/);
      if (mdMatch) jsonStr = mdMatch[1];
      const parsed = JSON.parse(jsonStr);
      const files: any[] = parsed.files || [];
      const codeFiles = files.filter((f: any) =>
        f.code && f.file_path &&
        /\.(tsx?|jsx?)$/.test(f.file_path)
      );
      if (codeFiles.length > 0) return codeFiles as CodeFile[];
    } catch (_) {}

    // 2차: 단일 코드블록 → App.tsx 하나짜리 배열로 포장
    let codeToRender = '';
    const blockMatch = raw.match(/`{3}(?:tsx|jsx|ts|js|javascript|react)?\s*\n([\s\S]*?)`{3}/);
    codeToRender = blockMatch ? blockMatch[1] : '';
    if (!codeToRender && !raw.trim().startsWith('{')) codeToRender = raw;
    if (codeToRender && !codeToRender.trim().startsWith('{')) {
      const firstImport = codeToRender.indexOf('import ');
      if (firstImport > 0) codeToRender = codeToRender.substring(firstImport);
      return [{ file_path: 'App.tsx', code: codeToRender.trim() }];
    }

    return [];
  }, []);

  // EXECUTE_FILES 전송 — 팝업이 열려 있으면 팝업으로, 아니면 인앱 iframe 으로 라우팅
  const sendExecuteFiles = useCallback((files: CodeFile[]) => {
    if (!files.length) return;
    const target: Window | null | undefined =
      (popupRef.current && !popupRef.current.closed) ? popupRef.current : iframeRef.current?.contentWindow;
    if (!target) return;
    target.postMessage({ type: 'EXECUTE_FILES', files }, '*');
  }, []);

  // ↗ 새 창: 독립 OS 창에 동일 샌드박스를 띄운다(싱글톤). 사용자 제스처(클릭) 안에서 호출 → 팝업 차단 회피.
  const openPopout = useCallback(() => {
    if (popupRef.current && !popupRef.current.closed) { popupRef.current.focus(); return; }
    const w = window.open('', 'omega_preview', 'width=1024,height=768,resizable=yes,scrollbars=yes');
    if (!w) { alert('팝업이 차단되었습니다. 브라우저에서 이 사이트의 팝업을 허용해 주세요.'); return; }
    w.document.open();
    w.document.write(htmlTemplate);
    w.document.close();
    popupRef.current = w;
    // 새 타깃(팝업) 준비 대기 → 팝업이 IFRAME_READY 를 보내면 핸들러가 pending 파일을 전송
    isIframeReadyRef.current = false;
    setIsPoppedOut(true);
  }, [htmlTemplate]);

  // 팝업 닫고 메인(iframe)으로 복귀
  const closePopout = useCallback(() => {
    if (popupRef.current && !popupRef.current.closed) popupRef.current.close();
    popupRef.current = null;
    setIsPoppedOut(false);
    if (pendingFilesRef.current.length) sendExecuteFiles(pendingFilesRef.current);
  }, [sendExecuteFiles]);

  // 팝업을 사용자가 직접 닫으면 자동으로 메인 복원
  useEffect(() => {
    if (!isPoppedOut) return;
    const id = window.setInterval(() => {
      if (!popupRef.current || popupRef.current.closed) {
        window.clearInterval(id);
        popupRef.current = null;
        setIsPoppedOut(false);
        if (pendingFilesRef.current.length) sendExecuteFiles(pendingFilesRef.current);
      }
    }, 600);
    return () => window.clearInterval(id);
  }, [isPoppedOut, sendExecuteFiles]);

  // ESC 로 전체화면 해제
  useEffect(() => {
    if (!isFullscreen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setIsFullscreen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isFullscreen]);

  // 언마운트 시 열린 팝업 정리
  useEffect(() => () => { if (popupRef.current && !popupRef.current.closed) popupRef.current.close(); }, []);

  // PREVIEW 탭 진입 시 iframe 재초기화
  useEffect(() => {
    if (iframeRef.current && activeTab === 'PREVIEW') {
      isIframeReadyRef.current = false;
      setIsIframeReady(false);
      iframeRef.current.srcdoc = htmlTemplate;
    }
  }, [activeTab]);

  // rawCode 변경 → 파일 추출 → 캐시 저장 → 준비됐으면 즉시 전송
  useEffect(() => {
    if (!rawCode || isLoading || activeTab !== 'PREVIEW') return;
    const files = extractCodeFiles(rawCode);
    if (!files.length) return;

    pendingFilesRef.current = files;
    setError(null);

    if (isIframeReadyRef.current) sendExecuteFiles(files);
  }, [rawCode, isLoading, activeTab, isIframeReady, extractCodeFiles, sendExecuteFiles]);

  // IFRAME_READY 수신 → 즉시 전송 (타이밍 경쟁 해소)
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      // 신뢰 소스 검증: 우리 프리뷰 iframe/팝업이 보낸 메시지만 처리 - 임베드된 임의 콘텐츠가
      // PREVIEW_ERROR 를 스푸핑해 /heal 호출·경고를 유발하는 것 차단
      const trusted =
        event.source === iframeRef.current?.contentWindow ||
        (popupRef.current && !popupRef.current.closed && event.source === popupRef.current);
      if (!trusted) return;
      if (event.data?.type === 'PREVIEW_ERROR') {
        setError(event.data.message);
        // 릴리스/결과물 프리뷰 보기 모드에서는 자가치유(/heal) 트리거 금지
        // — 옛 결과물의 렌더 에러가 무관한 현재 작업 프로젝트의 실제 빌드를 오염시키는 것 방지
        if (isConnectedRef.current && event.data.message && !releaseRef.current) {
          triggerSelfHealing(event.data.message);
        }
      } else if (event.data?.type === 'IFRAME_READY') {
        isIframeReadyRef.current = true;
        setIsIframeReady(true);
        if (pendingFilesRef.current.length) sendExecuteFiles(pendingFilesRef.current);
      }
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [sendExecuteFiles]);

  // useMemo: SSE 상태 갱신마다 렌더당 최대 3회씩 재계산되던 탭 콘텐츠를 캐시
  const tabContent = useMemo(() => {
    if (!docs) return "데이터 로딩 대기 중...";
    if (isDynamic && activeTab !== 'PREVIEW') {
      return docs.artifacts?.[activeTab] || "산출물이 아직 없습니다.";
    }
    switch (activeTab) {
      case 'RFP': return docs.rfp_summary || "요구사항 정의서(RFP)가 아직 없습니다.";
      case 'PRD': return docs.prd_summary || "기획서가 없습니다.";
      case 'ARCH': return docs.architecture_summary || "아키텍처가 없습니다.";
      case 'UI_DESIGN': return docs.ui_mockup_summary || "UI 디자인 목업이 없습니다.";
      case 'TECH': return docs.tech_spec_summary || "기술 사양이 없습니다.";
      case 'FRONTEND': return docs.frontend_code_summary || "프론트엔드 코드가 없습니다.";
      case 'BACKEND': return docs.backend_code_summary || "백엔드 코드가 없습니다.";
      case 'REVIEW': return docs.code_review_report_summary || "리뷰 리포트가 없습니다.";
      case 'QA': return docs.qa_report_summary || "QA(통합검수) 리포트가 없습니다.";
      case 'ACCEPT': return docs.supervisor_report_summary || "고객사 수용검수 리포트가 아직 없습니다.\nQA 통과 후 최종 수용검수가 수행됩니다.";
      case 'MANUAL': return docs.user_manual_summary || "사용자 매뉴얼이 아직 생성되지 않았습니다.\n최종 수용검수 통과 후 자동으로 작성됩니다.";
      default: return "";
    }
  }, [docs, activeTab, isDynamic]);

  const deliverable_type = currentTemplateData?.deliverable_type || 'software_app';
  const isDocType = deliverable_type === 'document_report';
  const isHybrid = deliverable_type === 'hybrid_simulation';

  let tabs: { id: TabType; label: string }[] = [];
  if (isDynamic) {
    if (isDocType) tabs = [{ id: 'PREVIEW', label: '📄 최종 보고서' }];
    else if (isHybrid) tabs = [{ id: 'PREVIEW', label: '📊 종합 보고서' }];
    else tabs = [{ id: 'PREVIEW', label: '🖥️ 실시간 대시보드' }];
    
    const agents = [...currentTemplateData.agents].sort((a: any, b: any) => a.order - b.order);
    agents.forEach((a: any) => {
      tabs.push({ id: a.id, label: `📑 ${a.name_ko || a.id}` });
    });

  } else {
    tabs = [
      { id: 'PREVIEW', label: '🖥️ 실시간 샌드박스' }, { id: 'RFP', label: '📋 요구정의(RFP)' }, { id: 'PRD', label: '📄 기획서' },
      { id: 'UI_DESIGN', label: '🎨 UI 디자인' },
      { id: 'ARCH', label: '🏗️ 아키텍처' }, { id: 'TECH', label: '🛠️ 기술사양' },
      { id: 'FRONTEND', label: '🎨 프론트엔드' }, { id: 'BACKEND', label: '⚙️ 백엔드' },
      { id: 'REVIEW', label: '📝 리뷰' }, { id: 'QA', label: '🧪 QA' },
      { id: 'ACCEPT', label: '🧑‍⚖️ 수용검수' }, { id: 'MANUAL', label: '📘 사용자 매뉴얼' },
      { id: 'TRACE', label: '🔗 추적성' }
    ];
  }

  return (
    <div className={`flex flex-col bg-gray-900 shadow-inner overflow-hidden relative ${isFullscreen ? 'fixed inset-0 z-50' : 'w-full h-full rounded-lg'}`}>
      <div className="flex items-center bg-gray-800 border-b border-gray-700 shrink-0 select-none">
        <div className="flex overflow-x-auto">
          {tabs.map((tab) => (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)} className={`px-4 py-2.5 text-xs font-bold border-r border-gray-700 whitespace-nowrap transition-colors ${activeTab === tab.id ? 'bg-gray-900 text-blue-400 border-b-2 border-b-blue-500' : 'text-gray-400 hover:bg-gray-750 hover:text-gray-200'}`}>
              {tab.label}
            </button>
          ))}
        </div>
        {activeTab === 'PREVIEW' && (
          <div className="flex items-center gap-1 ml-auto px-2 shrink-0">
            <button onClick={openPopout} title="독립 OS 창으로 실행" className="text-xs font-bold text-gray-300 hover:text-white bg-gray-700 hover:bg-gray-600 px-2.5 py-1 rounded transition-colors">↗ 새 창</button>
            <button onClick={() => setIsFullscreen(v => !v)} title={isFullscreen ? '축소 (Esc)' : '전체화면'} className="text-xs font-bold text-gray-300 hover:text-white bg-gray-700 hover:bg-gray-600 px-2.5 py-1 rounded transition-colors">{isFullscreen ? '✕ 축소' : '⛶ 전체화면'}</button>
          </div>
        )}
      </div>
      <div className="flex-1 min-h-0 relative bg-white">
        {activeTab === 'PREVIEW' ? (
          docs?.view_type === 'markdown' ? <MarkdownViewer rawCode={rawCode} /> :
          docs?.view_type === 'json' ? <JsonViewer rawCode={rawCode} /> :
          docs?.view_type === 'slide' ? <SlideViewer rawCode={rawCode} /> :
          docs?.view_type === 'mermaid' ? <MermaidViewer rawCode={rawCode} /> :
          <>
            {isLoading && (<div className="absolute inset-0 bg-white/70 backdrop-blur-sm flex flex-col items-center justify-center z-20"><div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mb-4"></div><span className="text-gray-600 font-medium animate-pulse text-sm">에이전트가 코드를 컴파일하는 중입니다...</span></div>)}
            {error && !isLoading && (<div className="absolute top-0 left-0 w-full p-3 bg-red-50 text-red-600 text-sm z-10 border-b border-red-200 shadow-sm flex items-start gap-2"><span>🚨</span><div className="flex-1 overflow-hidden overflow-ellipsis"><strong>렌더링 에러:</strong> {error}</div></div>)}
            {/* allow-same-origin 유지 이유: 생성 앱 다수가 localStorage 를 쓰는데 opaque origin 에서는
                SecurityError 로 프리뷰가 전부 깨져 자가치유 오발동을 유발한다. 대신 message 핸들러의
                event.source 검증으로 스푸핑을 차단한다. */}
            <iframe ref={iframeRef} title="AI Factory Preview Sandbox" className="w-full h-full border-none flex-1 bg-transparent" sandbox="allow-scripts allow-same-origin" />
            {isPoppedOut && (
              <div className="absolute inset-0 bg-gray-900/95 flex flex-col items-center justify-center gap-4 z-20">
                <div className="text-5xl">🪟</div>
                <div className="text-gray-300 text-sm font-medium">새 창에서 실행 중입니다</div>
                <div className="flex gap-2">
                  <button onClick={() => { if (popupRef.current && !popupRef.current.closed) popupRef.current.focus(); }} className="text-xs font-bold text-white bg-blue-600 hover:bg-blue-500 px-3 py-1.5 rounded transition-colors">새 창 포커스</button>
                  <button onClick={closePopout} className="text-xs font-bold text-gray-300 bg-gray-700 hover:bg-gray-600 px-3 py-1.5 rounded transition-colors">메인으로 복귀</button>
                </div>
              </div>
            )}
          </>
        ) : activeTab === 'MANUAL' ? (
          <div className="w-full h-full bg-white overflow-y-auto">
            <div className="max-w-3xl mx-auto p-8 prose prose-sm">
              {docs?.user_manual_summary
                ? <ManualRenderer markdown={docs.user_manual_summary} />
                : <p className="text-gray-400 text-sm mt-8 text-center">사용자 매뉴얼이 아직 생성되지 않았습니다.<br />QA 승인 완료 후 자동으로 작성됩니다.</p>
              }
            </div>
          </div>
        ) : activeTab === 'TRACE' ? (
          <TraceabilityGraph />
        ) : (
          <div className="w-full h-full bg-white overflow-y-auto">
            {typeof tabContent === 'string' && tabContent.includes('<html') ? (
              <iframe srcDoc={tabContent.match(/```[a-z]*\n([\s\S]*?)```/)?.[1] || tabContent} className="w-full h-full border-none bg-white" sandbox="allow-scripts" />
            ) : (
              <div className="max-w-4xl mx-auto p-6 text-gray-800">
                <MarkdownViewer rawCode={(() => {
                  const content = tabContent;
                  if (activeTab === 'FRONTEND' || activeTab === 'BACKEND') {
                    try {
                      const parsed = JSON.parse(content);
                      if (parsed.files && Array.isArray(parsed.files)) {
                        return parsed.files.map((f: any) => `### 📄 \`${f.file_path || f.filename}\`\n\n\`\`\`${f.file_path?.endsWith('.py') ? 'python' : 'tsx'}\n${f.code}\n\`\`\``).join('\n\n---\n\n');
                      }
                    } catch(e) {}
                  }
                  return content;
                })()} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default PreviewPanel;
