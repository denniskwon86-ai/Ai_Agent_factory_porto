import os
import re

def extract_signatures(code: str, ext: str) -> str:
    """
    정규식을 활용한 초경량 JIT 문맥 추출기 (심볼 시그니처만 추출)
    함수 구현부 전체 대신 함수/클래스/인터페이스 선언부만 추출하여 토큰을 대폭 절감합니다.
    """
    lines = code.split("\n")
    signatures = []
    
    if ext in [".ts", ".tsx", ".js", ".jsx"]:
        for line in lines:
            line_s = line.strip()
            # 클래스, 인터페이스, 타입, 익스포트 함수 시그니처 추출
            if re.match(r'^(export )?(class|interface|type|const|let|var) \w+', line_s):
                signatures.append(line_s)
            elif re.match(r'^(export )?(async )?function \w+\(.*\)', line_s):
                signatures.append(line_s)
    elif ext in [".py"]:
        for line in lines:
            line_s = line.strip()
            if line_s.startswith("def ") or line_s.startswith("async def ") or line_s.startswith("class "):
                signatures.append(line_s)
                
    # 결과가 없으면 일부 상단 내용(Imports 등)만 제한적으로 반환
    if not signatures:
        return "\n".join(lines[:10]) + "\n... (omitted)"
        
    return "\n".join(signatures)

def build_jit_context(workspace_root: str, file_paths: list[str]) -> str:
    """주어진 파일들의 시그니처 요약본을 생성하여 RAG 대비 정밀한 JIT(Just-In-Time) 문맥 반환"""
    context = ["[JIT 심볼 종속성 문맥 (세부 구현 로직 생략, 시그니처만 제공됨)]"]
    for rel_path in file_paths:
        abs_path = os.path.join(workspace_root, rel_path)
        if os.path.exists(abs_path):
            with open(abs_path, 'r', encoding='utf-8') as f:
                code = f.read()
                _, ext = os.path.splitext(rel_path)
                sig = extract_signatures(code, ext)
                context.append(f"\n--- {rel_path} ---")
                context.append(sig)
    return "\n".join(context)
