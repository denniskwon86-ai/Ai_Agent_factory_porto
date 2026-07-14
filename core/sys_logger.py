import sys
import collections

# 전역 로그 버퍼 (최대 1,000줄 저장)
global_log_buffer = collections.deque(maxlen=1000)

class StdoutInterceptor:
    """
    파이썬 표준 출력(sys.stdout, sys.stderr)을 가로채서 
    원래 목적지(콘솔)에도 출력하고, 메모리 큐에도 보관하는 래퍼 클래스입니다.
    """
    def __init__(self, original_stream):
        self.original_stream = original_stream

    def __getattr__(self, name):
        return getattr(self.original_stream, name)

    def write(self, msg):
        # 1. 원래 콘솔(터미널)에 그대로 출력
        self.original_stream.write(msg)
        if hasattr(self.original_stream, "flush"):
            self.original_stream.flush()
        
        # 2. 메모리 버퍼에 저장 (빈 줄이나 개행만 있는 경우는 제외)
        stripped = msg.strip()
        if stripped:
            global_log_buffer.append(stripped)
            
        return len(msg)

    def flush(self):
        if hasattr(self.original_stream, "flush"):
            self.original_stream.flush()

def get_recent_logs():
    """버퍼에 쌓인 최근 로그 리스트를 반환합니다."""
    return list(global_log_buffer)
