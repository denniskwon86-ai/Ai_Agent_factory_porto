# 기존 코드에 다음 메서드를 추가 (Diff 형식 적용)
import re
import ast  # 🚨 파이썬 구문 분석용 내장 모듈 추가
from typing import Dict, Any, Tuple

class LocalSyntaxChecker:

    @staticmethod
    def check_javascript_syntax(code: str) -> Tuple[bool, str]:
        """프론트엔드(JS/TS/JSX/TSX) 코드의 치명적 구문 결함을 경량 검사한다.
        브라우저/Node 파서 의존 없이, 빈 코드·괄호 불균형·미닫힌 문자열 등
        빌드를 즉시 깨뜨리는 1차 결함만 차단한다(완전한 파싱은 샌드박스 Babel이 담당).
        """
        if not code or not code.strip():
            return False, "🚨 에러: 산출된 프론트엔드(JS/TS) 코드 문자열이 비어 있습니다."

        # 1) 라인/블록 주석과 문자열 리터럴을 제거해 오탐을 줄인다.
        scrubbed = re.sub(r'/\*[\s\S]*?\*/', '', code)
        scrubbed = re.sub(r'//[^\n]*', '', scrubbed)
        scrubbed = re.sub(r'"(?:\\.|[^"\\])*"', '""', scrubbed)
        scrubbed = re.sub(r"'(?:\\.|[^'\\])*'", "''", scrubbed)
        scrubbed = re.sub(r'`(?:\\.|[^`\\])*`', '``', scrubbed)

        # 2) 괄호/중괄호/대괄호 균형 검사
        pairs = {')': '(', ']': '[', '}': '{'}
        openers = set(pairs.values())
        stack = []
        for ch in scrubbed:
            if ch in openers:
                stack.append(ch)
            elif ch in pairs:
                if not stack or stack[-1] != pairs[ch]:
                    return False, f"🚨 JS/TS SyntaxError: 짝이 맞지 않는 괄호 '{ch}' 발견."
                stack.pop()
        if stack:
            return False, f"🚨 JS/TS SyntaxError: 닫히지 않은 괄호 '{stack[-1]}' {len(stack)}개 발견."

        # 3) 미닫힌 문자열/템플릿 리터럴 흔적 검사
        if scrubbed.count('`') % 2 != 0:
            return False, "🚨 JS/TS SyntaxError: 닫히지 않은 템플릿 리터럴(`) 발견."

        return True, "Success"

    @staticmethod
    def check_python_syntax(code: str) -> Tuple[bool, str]:
        """백엔드 파이썬 코드의 치명적인 Syntax, Indentation 에러를 검사합니다."""
        if not code.strip():
            return False, "🚨 에러: 산출된 백엔드(Python) 코드 문자열이 비어 있습니다."
        
        try:
            # 파이썬 내장 AST 파서를 활용해 구문 무결성 100% 1차 검증
            ast.parse(code)
            return True, "Success"
        except SyntaxError as e:
            error_msg = f"🚨 Python SyntaxError at line {e.lineno}, offset {e.offset}: {e.msg}\n"
            if e.text:
                error_msg += f"Problematic code: {e.text.strip()}"
            return False, error_msg
        except IndentationError as e:
            return False, f"🚨 Python IndentationError at line {e.lineno}: {e.msg}"
        except Exception as e:
            return False, f"🚨 Python Parsing Error: {str(e)}"