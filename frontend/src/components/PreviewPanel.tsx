import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useFactoryStore } from '../store/useFactoryStore';
import TraceabilityGraph from './TraceabilityGraph';

// 마크다운을 간단히 HTML로 변환하는 경량 렌더러 (외부 라이브러리 없음)
// ★ [2026-08-06] `export` 를 붙였다 — 신규 Studio 의 산출물 Canvas 가 같은 렌더러를 쓴다.
//   복사하면 마크다운 해석 규칙이 두 벌이 되고, 그때 같은 문서가 두 화면에서 다르게 보인다.
//   동작은 종전과 동일하다(선언만 바뀌었다).
export function ManualRenderer({ markdown }: { markdown: string }) {
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
         <button onClick={() => setCurrentSlide(s => Math.max(0, s - 1))} disabled={currentSlide === 0} className="text-gray-100 disabled:text-gray-500 font-bold px-3">이전</button>
         <span className="text-gray-300 font-mono flex items-center">{currentSlide + 1} / {slides.length}</span>
         <button onClick={() => setCurrentSlide(s => Math.min(slides.length - 1, s + 1))} disabled={currentSlide === slides.length - 1} className="text-gray-100 disabled:text-gray-500 font-bold px-3">다음</button>
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
  /** 팝업이 차단됐다는 사실. `alert()` 대신 화면에 남긴다. */
  const [popupBlocked, setPopupBlocked] = useState(false);
  //: [P0-1A] 생성 앱이 실데이터를 부르려다 격리에 막힌 사실. **빈 화면으로 두지 않는다.**
  const [dataBlocked, setDataBlocked] = useState(false);
  //: [P0-1A 보정] 자가복구를 **사람이** 누를 수 있게 제안만 한다(자동 호출 금지 — LLM 비용).
  const [healOffered, setHealOffered] = useState(false);
  const [healRequested, setHealRequested] = useState(false);
  /** ★ [P0-1A 보정] Preview 세션 경계.
   *
   * ⚠️ 이것은 **생성 코드를 신뢰하게 만드는 수단이 아니다**(같은 문서 안이라 코드가 읽을 수
   *   있다). 목적은 하나다 — **이전 iframe 이 뒤늦게 보낸 메시지를 구별해 버리는 것.**
   *   재로딩 직후 옛 프레임의 `PREVIEW_ERROR` 가 도착하면 이미 고쳐진 오류를 다시 띄우고,
   *   사용자가 그것을 보고 자가복구를 누르면 LLM 비용이 헛되이 나간다. */
  const previewSidRef = useRef<string>('');
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
        <!-- ★★★ [P0-1A] CSP — **CORS 에 기대지 않는다.**
             opaque origin(=allow-same-origin 제거) 이어도 생성 코드는 외부로 전송을 시도할 수
             있다. 그래서 네트워크를 CSP 로 끊는다. connect-src 'none' 이 핵심이다.
             ⚠️ script-src 에 CDN 두 곳을 명시적으로 연다 — 지금 Preview 는 tailwind·react·
               babel·lucide 를 CDN 에서 받아 동작하며, 이것을 막으면 미리보기 자체가 죽는다.
               'unsafe-eval' 은 Babel standalone 이 new Function 을 쓰기 때문이다.
               **스크립트 출처는 열되 데이터 전송로는 닫는다** 가 이 정책의 요지다. -->
        <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://unpkg.com; style-src 'unsafe-inline' https://cdn.tailwindcss.com; img-src data: blob:; font-src data:; connect-src 'none'; form-action 'none'; object-src 'none'; frame-src 'none'; base-uri 'none';" />
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
          // ★★★ [P0-1A] 격리 shim — **이 블록이 없으면 격리가 제품을 망가뜨린다.**
          //
          // «allow-same-origin« 을 떼면 문서는 opaque origin 이 되고, 그 순간
          //   ① «window.localStorage« 접근이 **SecurityError** 를 던진다
          //   ② 생성 앱 다수가 localStorage 를 쓰므로 미리보기가 통째로 깨진다
          //   ③ 깨진 오류가 «PREVIEW_ERROR« 로 부모에 올라가 **자가치유(LLM)가 오발동**한다
          // 코드 주석이 «allow-same-origin« 을 유지한 이유로 정확히 이것을 적어 두었다.
          //
          // 그래서 **메모리 기반 저장소**로 갈아끼운다. 앱 입장에서는 그대로 동작하고,
          // 부모의 진짜 localStorage(세션 토큰이 있는 곳)에는 닿지 못한다 — 목적 달성.
          (function () {
            // ⚠️ local 과 session 은 **서로 다른 저장소**다. 하나의 객체를 공유하면 앱이
            //   sessionStorage 에 쓴 값이 localStorage 에서 읽히는 «없는 동작» 이 생긴다.
            function makeStore() {
              var mem = {};
              var st = {
                getItem: function (k) { return Object.prototype.hasOwnProperty.call(mem, k) ? mem[k] : null; },
                setItem: function (k, v) { mem[String(k)] = String(v); },
                removeItem: function (k) { delete mem[String(k)]; },
                clear: function () { mem = {}; },
                key: function (i) { var ks = Object.keys(mem); return i < ks.length ? ks[i] : null; }
              };
              Object.defineProperty(st, 'length', { get: function () { return Object.keys(mem).length; } });
              return st;
            }
            var needed = false;
            try { window.localStorage.getItem('__afs_probe__'); } catch (e) { needed = true; }
            if (needed) {
              try {
                Object.defineProperty(window, 'localStorage', { value: makeStore(), configurable: true });
                Object.defineProperty(window, 'sessionStorage', { value: makeStore(), configurable: true });
              } catch (e) { /* 정의 실패해도 아래 네트워크 차단은 유효하다 */ }
            }
          })();

          // ★★ [P0-1A] 실데이터 연결 차단을 **조용히** 하지 않는다.
          //   CSP 가 이미 막지만, 그때 앱이 받는 것은 알 수 없는 TypeError 뿐이고 화면은
          //   빈 채로 남는다. 여기서 가로채 **왜 비었는지**를 부모에 알린다.
          //   ⚠️ «PREVIEW_ERROR« 로 보내지 않는다 — 그것은 자가치유(LLM)를 깨운다. 격리는
          //     고칠 결함이 아니라 **의도된 상태**다.
          (function () {
            function notifyBlocked(kind, target) {
              try {
                (window.opener || window.parent).postMessage(
                  { type: 'AFS_DATA_BLOCKED', sid: '__AFS_SID__', kind: kind, target: String(target).slice(0, 200) }, '*');
              } catch (e) { /* 알림 실패가 앱을 죽이지 않는다 */ }
            }
            var MSG = '안전 격리 중이므로 실데이터는 연결되지 않습니다. Host Runtime 적용 후 지원됩니다.';
            window.fetch = function (input) {
              notifyBlocked('fetch', (input && input.url) || input);
              return Promise.reject(new TypeError(MSG));
            };
            var OrigXHR = window.XMLHttpRequest;
            if (OrigXHR) {
              window.XMLHttpRequest = function () {
                var x = new OrigXHR();
                var open = x.open;
                x.open = function (m, u) { notifyBlocked('xhr', u); return open.apply(x, arguments); };
                return x;
              };
            }
            if (window.WebSocket) {
              window.WebSocket = function (u) { notifyBlocked('websocket', u); throw new Error(MSG); };
            }
            if (navigator && navigator.sendBeacon) {
              navigator.sendBeacon = function (u) { notifyBlocked('beacon', u); return false; };
            }
          })();

          window.onerror = function(msg) {
            (window.opener || window.parent).postMessage({ type: 'PREVIEW_ERROR', sid: '__AFS_SID__', message: msg }, '*');
            return false;
          };

          function notifyReady() {
            if (typeof Babel === 'undefined' || typeof React === 'undefined' || typeof ReactDOM === 'undefined') {
              setTimeout(notifyReady, 50);
              return;
            }
            (window.opener || window.parent).postMessage({ type: 'IFRAME_READY', sid: '__AFS_SID__' }, '*');
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
                (window.opener || window.parent).postMessage({ type: 'PREVIEW_ERROR', sid: '__AFS_SID__', message: err.message }, '*');
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
    // ★★★ [P0-1A] **비활성화됨.** `window.open('')` + `document.write()` 는 새 창을 부모와
    //   **같은 출처**로 만든다. 그러면 생성 코드가 `window.opener` 를 통해 부모 DOM·세션에
    //   접근할 수 있다 — iframe 의 `allow-same-origin` 을 떼도 이 경로가 열려 있으면 소용없다.
    //   버튼은 숨기지 않고 **잠그고 사유를 보여 준다**(숨기면 사용자는 기능이 사라진 줄 안다).
    //   I-3 Host Runtime Bridge 완성 후 **별도 격리 Origin** 으로 정식 복구한다.
    //
    // ⚠️⚠️ 종전에는 `return;` 한 줄만 앞에 두고 `window.open` + `document.write` 본문을
    //   **그대로 남겨 두었다.** 두 가지가 나빴다.
    //     ① `return` 한 줄만 지우면 구멍이 그대로 되살아난다 — 「왜 막았는지」를 모르는
    //        사람에게는 그것이 가장 자연스러운 복구 방법으로 보인다.
    //     ② 도달 불가 코드도 타입 검사는 받는데, 그 자리에서는 흐름 분석이 좁혀 주지 않아
    //        `tsc -b` 가 TS18047 5건으로 깨졌다(`npx tsc -p tsconfig.json` 은 솔루션 파일이라
    //        0개 파일을 검사하고 조용히 통과해서, 커밋 시점에 이것을 못 봤다).
    //   복구할 때는 위 설명대로 **격리 Origin 을 먼저 만들고** 새로 쓴다. 되살릴 코드가
    //   아니므로 남겨 두지 않는다.
  }, []);

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

  // ESC 로 전체화면 해제 + 전체화면 동안의 접근성 처리
  //
  // ⚠️ [이관 F 7/8] **`HubDialog` 를 쓰지 않는다.** 그것은 `createPortal` 로 `document.body`
  //   에 옮겨 붙이는데, 그러면 이 패널의 **iframe 이 재마운트**되어 실행 중인 생성 앱의
  //   상태(가상 모듈 레지스트리·localStorage 핸들·postMessage 준비 상태)가 통째로 날아간다.
  //   다른 7개 화면과 달리 여기는 «옮기면 회귀» 인 자산이다(2026-08-06 인계 §재사용 3곳).
  //   → 셸을 옮기는 대신 **그 자리에서** 모달 의미론만 갖춘다.
  //
  // ⚠️ 배경 `inert` 도 걸지 않는다 — 이 패널 자신이 `#root` 안에 있어서 `#root` 를 inert 로
  //   만들면 **자기 자신이 죽는다.** 대신 배경 스크롤을 잠그고 `aria-modal` 로 알린다.
  useEffect(() => {
    if (!isFullscreen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setIsFullscreen(false); };
    window.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [isFullscreen]);

  // 언마운트 시 열린 팝업 정리
  useEffect(() => () => { if (popupRef.current && !popupRef.current.closed) popupRef.current.close(); }, []);

  // PREVIEW 탭 진입 시 iframe 재초기화
  useEffect(() => {
    if (iframeRef.current && activeTab === 'PREVIEW') {
      isIframeReadyRef.current = false;
      setIsIframeReady(false);
      // 새 Preview 세션 — 매 로딩마다 새 ID 를 발급해 옛 프레임 메시지를 끊는다.
      previewSidRef.current = (crypto as any)?.randomUUID?.()
        || `sid_${Date.now()}_${Math.random().toString(36).slice(2)}`;
      iframeRef.current.srcdoc = htmlTemplate.replace(/__AFS_SID__/g, previewSidRef.current);
    }
  }, [activeTab]);

  // rawCode 변경 → 파일 추출 → 캐시 저장 → 준비됐으면 즉시 전송
  useEffect(() => {
    if (!rawCode || isLoading || activeTab !== 'PREVIEW') return;
    const files = extractCodeFiles(rawCode);
    if (!files.length) return;

    pendingFilesRef.current = files;
    setError(null);

    // ⚠️ 새 코드를 실행할 때마다 이전 화면의 오류·차단·복구 제안을 지운다 —
    //   남겨 두면 이미 고쳐진 오류에 대해 자가복구를 다시 누르게 된다.
    setError(null); setDataBlocked(false); setHealOffered(false); setHealRequested(false);
    if (isIframeReadyRef.current) sendExecuteFiles(files);
  }, [rawCode, isLoading, activeTab, isIframeReady, extractCodeFiles, sendExecuteFiles]);

  // IFRAME_READY 수신 → 즉시 전송 (타이밍 경쟁 해소)
  useEffect(() => {
    /** ★★ [P0-1A] postMessage 계약.
     *
     * ⚠️ `allow-same-origin` 을 떼면 iframe 의 `event.origin` 은 문자열 `"null"` 이 된다.
     *   그러므로 **origin 으로는 아무것도 판별할 수 없다** — 어떤 악성 프레임도 같은 값을
     *   갖는다. 신뢰의 근거는 오직 **`event.source` 객체 동일성**이다.
     * ⚠️ 미등록 타입·형식 위반은 조용히 버리지 않고 콘솔에 남긴다 — 조용히 버리면 계약이
     *   깨졌을 때 아무도 모른다. */
    const ALLOWED = new Set(['PREVIEW_ERROR', 'IFRAME_READY', 'AFS_DATA_BLOCKED']);
    const MAX_LEN = 4000;   // payload 크기 상한 — 거대한 문자열로 부모를 밀어내지 못하게

    const handleMessage = (event: MessageEvent) => {
      // ① 소스 동일성 — 우리 iframe 이 보낸 것만 받는다(팝아웃은 P0-1A 로 비활성화됨)
      if (event.source !== iframeRef.current?.contentWindow) return;

      const d: any = event.data;
      // ② 형태 검증
      if (!d || typeof d !== 'object' || typeof d.type !== 'string') return;
      // ③ 타입 화이트리스트
      if (!ALLOWED.has(d.type)) {
        console.warn('[Preview] 미등록 메시지 타입을 버렸습니다:', String(d.type).slice(0, 40));
        return;
      }
      // ④ Preview 세션 경계 — 이전 iframe 이 뒤늦게 보낸 메시지를 버린다
      if (previewSidRef.current && d.sid !== previewSidRef.current) {
        console.warn('[Preview] 지난 Preview 세션의 메시지를 버렸습니다.');
        return;
      }
      // ⑤ 허용하지 않은 필드가 붙어 오면 계약 위반이다
      const FIELDS: Record<string, string[]> = {
        PREVIEW_ERROR: ['type', 'sid', 'message'],
        IFRAME_READY: ['type', 'sid'],
        AFS_DATA_BLOCKED: ['type', 'sid', 'kind', 'target'],
      };
      const extra = Object.keys(d).filter((k) => !FIELDS[d.type].includes(k));
      if (extra.length) {
        console.warn('[Preview] 계약에 없는 필드를 버렸습니다:', extra.slice(0, 5).join(','));
        return;
      }
      // ⑥ kind 는 정해진 넷 중 하나여야 한다
      if (d.type === 'AFS_DATA_BLOCKED'
          && !['fetch', 'xhr', 'websocket', 'beacon'].includes(d.kind)) {
        console.warn('[Preview] 알 수 없는 차단 종류를 버렸습니다:', String(d.kind).slice(0, 20));
        return;
      }
      // ④ 스키마·크기
      if (d.message !== undefined && (typeof d.message !== 'string' || d.message.length > MAX_LEN)) {
        console.warn('[Preview] message 스키마 위반 — 버립니다.');
        return;
      }
      if (d.target !== undefined && (typeof d.target !== 'string' || d.target.length > 512)) {
        console.warn('[Preview] target 스키마 위반 — 버립니다.');
        return;
      }

      // ★ 격리로 인한 데이터 차단은 **결함이 아니라 의도된 상태**다.
      //   자가치유(LLM)를 깨우지 않고 화면에 사유만 남긴다.
      if (d.type === 'AFS_DATA_BLOCKED') {
        setDataBlocked(true);
        return;
      }
      if (event.data?.type === 'PREVIEW_ERROR') {
        // ★★★ [P0-1A 보정] **자동 자가치유를 호출하지 않는다.**
        //
        // `event.source` 검증은 「우리 iframe 에서 왔다」만 증명한다. 그런데 **그 iframe 안에서
        // 도는 코드가 바로 신뢰할 수 없는 대상**(LLM 생성물)이다. 생성 코드가 직접
        // `postMessage({type:'PREVIEW_ERROR'})` 를 보내거나 오류를 반복해서 던지면
        // **LLM 호출과 비용이 무한히 발생**한다. 종전에는 그것이 자동으로 일어났다.
        //
        // 이제 오류는 화면에 보여 주고 **사람이 「자가복구 요청」을 눌러야** 나간다.
        // 향후 Host Runtime 의 «신뢰된 검증 결과» 가 생기면 그것만 자동 트리거로 쓴다.
        setError(event.data.message);
        setHealOffered(isConnectedRef.current && !!event.data.message && !releaseRef.current);
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
    <div
      // 전체화면이면 화면 전체를 덮으므로 **대화상자로 알린다** — 그러지 않으면 스크린리더에
      // 그냥 문서 일부로 읽히고, 사용자는 배경이 아직 살아 있다고 오해한다.
      role={isFullscreen ? 'dialog' : undefined}
      aria-modal={isFullscreen ? true : undefined}
      aria-label={isFullscreen ? '생성 앱 미리보기 — 전체화면 (Esc 로 축소)' : undefined}
      className={`flex flex-col bg-gray-900 shadow-inner overflow-hidden relative ${isFullscreen ? 'fixed inset-0 z-50' : 'w-full h-full rounded-lg'}`}>
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
            {/* ★ [P0-1A] 새 창은 **잠그되 숨기지 않는다.** 숨기면 사용자는 기능이 사라진 줄
                알고, 잠그면 «왜 지금 못 쓰는가» 를 그 자리에서 읽는다. */}
            <button onClick={openPopout} disabled
              title="안전 격리 중입니다 — 새 창은 부모 창과 같은 출처를 갖게 되어 생성 앱이 세션에 접근할 수 있습니다. Host Runtime 적용 후 별도 격리 창으로 지원됩니다."
              className="text-xs font-bold text-gray-500 bg-gray-800 px-2.5 py-1 rounded cursor-not-allowed opacity-60">↗ 새 창 <span className="opacity-70">(격리 중)</span></button>
            <button onClick={() => setIsFullscreen(v => !v)} title={isFullscreen ? '축소 (Esc)' : '전체화면'} className="text-xs font-bold text-gray-300 hover:text-gray-100 bg-gray-700 hover:bg-gray-600 px-2.5 py-1 rounded transition-colors">{isFullscreen ? '✕ 축소' : '⛶ 전체화면'}</button>
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
            {error && !isLoading && (
              <div className="absolute top-[30px] left-0 w-full p-3 bg-red-50 text-red-600 text-sm z-10 border-b border-red-200 shadow-sm flex items-start gap-2">
                <span aria-hidden="true">🚨</span>
                <div className="flex-1 overflow-hidden">
                  <strong>렌더링 에러:</strong> {error}
                  {/* ★★ [P0-1A 보정] 자가복구는 **사람이 누른다.** 자동으로 걸면 생성 코드가
                      오류를 반복해 던지는 것만으로 LLM 비용이 무한히 나간다. */}
                  {healOffered && !healRequested && (
                    <div className="mt-2 flex items-center gap-2">
                      <button
                        onClick={() => { setHealRequested(true); triggerSelfHealing(error); }}
                        className="text-xs font-bold text-white bg-red-600 hover:bg-red-500 px-3 py-1.5 rounded transition-colors">
                        자가복구 요청
                      </button>
                      <span className="text-[12px] text-red-500 opacity-90">
                        AI 가 코드를 고쳐 다시 시도합니다 — <b>LLM 비용이 발생</b>합니다.
                      </span>
                    </div>
                  )}
                  {healRequested && (
                    <div className="mt-2 text-[12px] text-red-500">자가복구를 요청했습니다.</div>
                  )}
                </div>
              </div>
            )}
            {/* ★★★ [P0-1A · 2026-08-09] `allow-same-origin` 을 **제거했다.**
                종전 주석은 「생성 앱이 localStorage 를 쓰는데 opaque origin 에서는 SecurityError 로
                프리뷰가 깨지고 자가치유가 오발동한다」를 유지 이유로 들었다. 그 진단은 옳았지만
                결론이 틀렸다 — `allow-scripts` 와 함께 주면 **sandbox 가 무력화되어** iframe 안
                코드가 `parent.localStorage` 의 **세션 토큰을 읽을 수 있다.** LLM 이 생성한 코드에
                그 권한을 주고 있었다.
                깨짐 문제는 격리를 포기하는 대신 **템플릿의 storage shim 으로** 해결했다(메모리
                기반). 앱은 그대로 동작하고 부모 저장소에는 닿지 못한다. */}
            {/* ★ 팝업 차단은 사용자가 **설정을 바꾸는 동안** 계속 보여야 한다 —
                `alert()` 는 닫는 순간 사라져서 문구를 다시 볼 수 없었다. */}
            {/* ★ [P0-1A] 「안전 미리보기」 상태를 **항상** 보여 준다. 사용자가 데이터가 안 보이는
                이유를 화면에서 알 수 있어야 한다 — 조용한 빈 화면은 허용하지 않는다. */}
            <div className="absolute top-0 left-0 w-full px-3 py-1.5 bg-slate-800/90 text-slate-100 text-[12px] z-10 flex items-center gap-2">
              <span aria-hidden="true">🔒</span>
              <b>안전 미리보기</b>
              <span className="opacity-80">· 실데이터 연결 제한</span>
              <span className="ml-auto opacity-70">Host Runtime 적용 후 지원됩니다</span>
            </div>

            {dataBlocked && (
              <div role="status" className="absolute top-[30px] left-0 w-full p-3 bg-sky-50 text-sky-900 text-sm z-10 border-b border-sky-200 flex items-start gap-2">
                <span aria-hidden="true">ℹ️</span>
                <div className="flex-1">
                  <strong>이 앱이 실데이터를 불러오려 했습니다.</strong> 안전 격리 중이므로 실데이터는
                  연결되지 않습니다. Host Runtime 적용 후 지원됩니다.
                  <br />
                  <span className="opacity-80">앱에 포함된 샘플 데이터와 화면 조작은 그대로 확인하실 수 있습니다.</span>
                </div>
                <button onClick={() => setDataBlocked(false)} className="shrink-0 text-sky-700 hover:text-sky-900 font-bold px-1" aria-label="이 안내 닫기">✕</button>
              </div>
            )}

            {popupBlocked && (
              <div role="alert" className="absolute top-0 left-0 w-full p-3 bg-amber-50 text-amber-800 text-sm z-10 border-b border-amber-200 shadow-sm flex items-start gap-2">
                <span aria-hidden="true">🪟</span>
                <div className="flex-1">
                  <strong>새 창이 차단되었습니다.</strong> 브라우저 주소창의 팝업 차단 아이콘에서
                  이 사이트를 허용한 뒤 다시 «↗ 새 창» 을 누르십시오. 허용하지 않아도
                  아래 미리보기는 그대로 동작합니다.
                </div>
                <button onClick={() => setPopupBlocked(false)} className="shrink-0 text-amber-700 hover:text-amber-900 font-bold px-1" aria-label="이 안내 닫기">✕</button>
              </div>
            )}
            <iframe ref={iframeRef} title="AI Factory Preview Sandbox" className="w-full h-full border-none flex-1 bg-transparent" sandbox="allow-scripts" />
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
