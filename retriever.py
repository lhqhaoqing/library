import hashlib
import json
import math
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import jieba
import numpy as np
from rank_bm25 import BM25Okapi

from document_loader import SUPPORTED_EXTENSIONS, iter_text_segments

try:
    import faiss
    from langchain_community.embeddings import DashScopeEmbeddings
    VECTOR_SUPPORT = True
except ImportError:
    VECTOR_SUPPORT = False


def tokenize(text: str) -> List[str]:
    if not text:
        return []
    tokens = [token.strip() for token in jieba.lcut(text) if token.strip()]
    return tokens


def split_text(text: str, max_length: int, overlap: int) -> List[str]:
    if len(text) <= max_length:
        return [text.strip()]

    segments: List[str] = []
    current = ''
    for sentence in text.replace('\n', ' ').split('。'):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(current) + len(sentence) + 1 <= max_length:
            current = f'{current}。{sentence}' if current else sentence
        else:
            segments.append(current.strip())
            current = sentence
    if current:
        segments.append(current.strip())

    final_segments: List[str] = []
    for segment in segments:
        if len(segment) <= max_length:
            final_segments.append(segment)
            continue
        start = 0
        while start < len(segment):
            end = min(start + max_length, len(segment))
            final_segments.append(segment[start:end].strip())
            start += max_length - overlap
    return final_segments


@dataclass
class KnowledgeChunk:
    content: str
    source: str
    metadata: Dict[str, Any]
    chunk_id: str


@dataclass
class SearchResult:
    chunk: KnowledgeChunk
    score: float


@dataclass
class KnowledgeIndex:
    root_path: str
    top_k: int = 5
    chunk_size: int = 1200
    chunk_overlap: int = 200
    bm25_weight: float = 0.4
    vector_weight: float = 0.6
    retriever_type: str = 'hybrid'
    chunks: List[KnowledgeChunk] = field(default_factory=list)
    bm25: Optional[BM25Okapi] = None
    vector_store: Any = None
    vector_embeddings: Any = None
    vector_metadata: List[KnowledgeChunk] = field(default_factory=list)
    index_cache_dir: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.index_cache_dir:
            self.index_cache_dir = str((Path(self.root_path).resolve().parent / '.index_cache').resolve())

    def load_documents(self) -> List[Dict[str, Any]]:
        return list(iter_text_segments(self.root_path))

    def build_index(self) -> None:
        if self.try_load_persisted_index():
            return
        self.rebuild_index()

    def rebuild_index(self) -> None:
        documents = self.load_documents()
        self.chunks = []
        for doc_idx, doc in enumerate(documents):
            segments = split_text(doc['content'], self.chunk_size, self.chunk_overlap)
            for seg_idx, segment in enumerate(segments, start=1):
                chunk_id = f"{doc['metadata'].get('file_name', 'unknown')}_{doc_idx}_{seg_idx}"
                source = doc['source']
                metadata = {**doc['metadata'], 'chunk_id': chunk_id}
                self.chunks.append(KnowledgeChunk(content=segment, source=source, metadata=metadata, chunk_id=chunk_id))

        self.build_bm25()
        if VECTOR_SUPPORT and self.retriever_type != 'bm25':
            try:
                self.build_vector_store()
            except Exception as exc:
                print(f'Warning: vector store initialization failed: {exc}')
                self.vector_store = None
        self.persist_index()

    def _cache_paths(self) -> Dict[str, Path]:
        cache_root = Path(self.index_cache_dir).resolve()
        cache_root.mkdir(parents=True, exist_ok=True)
        return {
            'faiss': cache_root / 'faiss.index',
            'chunks': cache_root / 'chunks.pkl',
            'meta': cache_root / 'meta.json',
        }

    def _snapshot_library(self) -> str:
        root = Path(self.root_path)
        files = []
        for path in sorted(root.rglob('*')):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            stat = path.stat()
            files.append(
                {
                    'path': str(path.relative_to(root)).replace('\\', '/'),
                    'mtime': stat.st_mtime,
                    'size': stat.st_size,
                }
            )
        payload = json.dumps(files, ensure_ascii=False, separators=(',', ':'))
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def _meta_payload(self) -> Dict[str, Any]:
        return {
            'root_path': str(Path(self.root_path).resolve()),
            'snapshot': self._snapshot_library(),
            'chunk_size': self.chunk_size,
            'chunk_overlap': self.chunk_overlap,
            'retriever_type': self.retriever_type,
            'vector_support': bool(VECTOR_SUPPORT and self.retriever_type != 'bm25'),
        }

    def try_load_persisted_index(self) -> bool:
        paths = self._cache_paths()
        if not paths['chunks'].exists() or not paths['meta'].exists():
            return False
        try:
            with paths['meta'].open('r', encoding='utf-8') as f:
                saved_meta = json.load(f)
            current_meta = self._meta_payload()
            if saved_meta != current_meta:
                return False

            with paths['chunks'].open('rb') as f:
                self.chunks = pickle.load(f)
            self.build_bm25()

            if VECTOR_SUPPORT and self.retriever_type != 'bm25':
                if not paths['faiss'].exists():
                    return False
                self.vector_embeddings = DashScopeEmbeddings(model='text-embedding-v1')
                self.vector_store = faiss.read_index(str(paths['faiss']))
                self.vector_metadata = self.chunks.copy()
            else:
                self.vector_store = None
                self.vector_metadata = []
            return True
        except Exception as exc:
            print(f'Warning: failed to load persisted index: {exc}')
            return False

    def persist_index(self) -> None:
        paths = self._cache_paths()
        try:
            with paths['chunks'].open('wb') as f:
                pickle.dump(self.chunks, f)
            with paths['meta'].open('w', encoding='utf-8') as f:
                json.dump(self._meta_payload(), f, ensure_ascii=False, indent=2)
            if VECTOR_SUPPORT and self.retriever_type != 'bm25' and self.vector_store is not None:
                faiss.write_index(self.vector_store, str(paths['faiss']))
            elif paths['faiss'].exists():
                paths['faiss'].unlink()
        except Exception as exc:
            print(f'Warning: failed to persist index: {exc}')

    def build_bm25(self) -> None:
        corpus = [tokenize(chunk.content) for chunk in self.chunks]
        if corpus:
            self.bm25 = BM25Okapi(corpus)
        else:
            self.bm25 = None

    def build_vector_store(self) -> None:
        if not VECTOR_SUPPORT:
            raise RuntimeError('Vector support is unavailable. Install langchain_community and faiss.')
        if not self.chunks:
            self.vector_store = None
            return
        self.vector_embeddings = DashScopeEmbeddings(model='text-embedding-v1')
        texts = [chunk.content for chunk in self.chunks]
        embeddings = self.vector_embeddings.embed_documents(texts)
        vectors = np.array(embeddings, dtype=np.float32)
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        faiss.normalize_L2(vectors)
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        self.vector_store = index
        self.vector_metadata = self.chunks.copy()

    def score_bm25(self, query: str) -> List[Tuple[KnowledgeChunk, float]]:
        if not self.bm25:
            return []
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        scores = self.bm25.get_scores(query_tokens)
        return sorted(((chunk, float(score)) for chunk, score in zip(self.chunks, scores)), key=lambda x: x[1], reverse=True)

    def score_vector(self, query: str) -> List[Tuple[KnowledgeChunk, float]]:
        if not self.vector_store or not self.vector_embeddings:
            return []
        query_vector = np.array(self.vector_embeddings.embed_query(query), dtype=np.float32)
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)
        faiss.normalize_L2(query_vector)
        distances, indices = self.vector_store.search(query_vector, min(self.top_k * 3, len(self.vector_metadata)))
        results = []
        for idx, score in zip(indices[0], distances[0]):
            if idx < 0 or idx >= len(self.vector_metadata):
                continue
            results.append((self.vector_metadata[idx], float(score)))
        return results

    def hybrid_search(self, query: str) -> List[SearchResult]:
        bm25_results = self.score_bm25(query)
        vector_results = self.score_vector(query) if self.retriever_type != 'bm25' else []
        score_map: Dict[str, float] = {}
        for chunk, score in bm25_results:
            score_map[chunk.chunk_id] = score_map.get(chunk.chunk_id, 0.0) + score * self.bm25_weight
        for chunk, score in vector_results:
            score_map[chunk.chunk_id] = score_map.get(chunk.chunk_id, 0.0) + score * self.vector_weight

        if not score_map and self.bm25:
            return [SearchResult(chunk=chunk, score=0.0) for chunk, _ in bm25_results[: self.top_k]]

        ranked = sorted(
            ((next(chunk for chunk in self.chunks if chunk.chunk_id == chunk_id), score) for chunk_id, score in score_map.items()),
            key=lambda item: item[1],
            reverse=True,
        )[: self.top_k]
        return [SearchResult(chunk=chunk, score=score) for chunk, score in ranked]

    def search(self, query: str) -> List[SearchResult]:
        if not query or not self.chunks:
            return []
        return self.hybrid_search(query)
