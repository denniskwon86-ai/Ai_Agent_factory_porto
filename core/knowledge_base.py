import os
import json
try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    chromadb = None

CHROMA_DB_DIR = os.path.join("data", "chroma_db")

class KnowledgeBase:
    """
    과거 성공적으로 배포된 결과물(Vault)을 벡터 DB(ChromaDB)에 인덱싱하고,
    새로운 프로젝트 기동 시 유사 사례를 검색(RAG)하여 컨텍스트로 제공합니다.
    """
    def __init__(self):
        self.client = None
        self.collection = None
        if chromadb:
            os.makedirs(CHROMA_DB_DIR, exist_ok=True)
            try:
                self.client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
                self.collection = self.client.get_or_create_collection(
                    name="project_releases",
                    metadata={"hnsw:space": "cosine"}
                )
            except Exception as e:
                print(f"⚠️ [KnowledgeBase] ChromaDB 초기화 실패: {e}")

    def chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 200) -> list:
        chunks = []
        start = 0
        while start < len(text):
            chunks.append(text[start:start+chunk_size])
            start += chunk_size - overlap
        return chunks

    def index_release(self, project_id: str, release_id: str, files_content: dict, metadata: dict = None):
        """배포된 산출물 파일들을 청크로 나누어 인덱싱"""
        if not self.collection:
            return

        documents = []
        metadatas = []
        ids = []

        chunk_idx = 0
        for filename, content in files_content.items():
            if not isinstance(content, str) or not content.strip():
                continue
            
            # 너무 큰 바이너리나 불필요한 파일은 건너뛰기
            if filename.endswith(('.png', '.jpg', '.pdf', '.exe', '.zip')):
                continue

            chunks = self.chunk_text(content)
            for i, chunk in enumerate(chunks):
                doc_meta = {
                    "project_id": project_id,
                    "release_id": release_id,
                    "filename": filename,
                    "chunk_index": i
                }
                if metadata:
                    doc_meta.update({k: str(v) for k, v in metadata.items() if isinstance(v, (str, int, float, bool))})
                
                documents.append(chunk)
                metadatas.append(doc_meta)
                ids.append(f"{release_id}_{filename}_{i}")
                chunk_idx += 1

        if documents:
            try:
                self.collection.add(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids
                )
                print(f" [KnowledgeBase] 프로젝트 '{project_id}' 배포판 '{release_id}' 인덱싱 완료 ({len(documents)} chunks)")
            except Exception as e:
                print(f"⚠️ [KnowledgeBase] 인덱싱 실패: {e}")

    def search_similar(self, query: str, n_results: int = 5) -> list:
        if not self.collection:
            return []
            
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results
            )
            
            snippets = []
            if results and results["documents"] and results["documents"][0]:
                for i in range(len(results["documents"][0])):
                    doc = results["documents"][0][i]
                    meta = results["metadatas"][0][i] if results["metadatas"] else {}
                    snippets.append({
                        "content": doc,
                        "metadata": meta
                    })
            return snippets
        except Exception as e:
            print(f"⚠️ [KnowledgeBase] 검색 실패: {e}")
            return []

    def get_relevant_context(self, project_state) -> str:
        """ProjectState를 기반으로 연관된 과거 사례 검색 컨텍스트 문자열 생성"""
        if not self.collection:
            return ""
            
        query = project_state.initial_idea or project_state.project_name
        if not query:
            return ""
            
        snippets = self.search_similar(query, n_results=3)
        if not snippets:
            return ""
            
        context = "이전에 성공적으로 배포된 유사한 프로젝트의 산출물 파편(Chunks)입니다. 새로운 결과물을 작성할 때 참고하세요:\n\n"
        for i, snippet in enumerate(snippets):
            meta = snippet["metadata"]
            project = meta.get("project_id", "Unknown")
            filename = meta.get("filename", "Unknown")
            content = snippet["content"]
            context += f"--- [과거 사례 {i+1}: 프로젝트 {project} / {filename}] ---\n"
            context += f"{content}\n\n"
            
        return context

knowledge_base = KnowledgeBase()
