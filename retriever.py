import hashlib
import json
import logging
import math
import pickle
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import jieba
import numpy as np
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

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
    enable_rerank: bool = False
    chunks: List[KnowledgeChunk] = field(default_factory=list)
    bm25: Optional[BM25Okapi] = None
    vector_store: Any = None
    vector_embeddings: Any = None
    vector_metadata: List[KnowledgeChunk] = field(default_factory=list)
    index_cache_dir: Optional[str] = None
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    reranker: Any = None

    def __post_init__(self) -> None:
        if not self.index_cache_dir:
            self.index_cache_dir = str((Path(self.root_path).resolve().parent / '.index_cache').resolve())
        
        # 初始化reranker
        if self.enable_rerank:
            try:
                from FlagEmbedding import FlagReranker
                self.reranker = FlagReranker('BAAI/bge-reranker-base', use_fp16=True)
                logger.info('Reranker initialized successfully')
            except ImportError:
                logger.warning('FlagEmbedding not installed, rerank disabled')
                self.enable_rerank = False
            except Exception as exc:
                logger.warning(f'Failed to initialize reranker: {exc}')
                self.enable_rerank = False

    def load_documents(self) -> List[Dict[str, Any]]:
        return list(iter_text_segments(self.root_path))

    def build_index(self) -> None:
        with self._lock:
            if self.try_load_persisted_index():
                return
            self.rebuild_index()

    def rebuild_index(self) -> None:
        # 注意：调用此方法前应该已经获取了锁
        logger.info('Starting full index rebuild...')
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
                logger.warning(f'Vector store initialization failed: {exc}', exc_info=True)
                self.vector_store = None
        self.persist_index()
        logger.info(f'Index rebuild completed with {len(self.chunks)} chunks')

    def incremental_update(self, changed_files: List[Path]) -> None:
        """增量更新索引，仅处理变化的文件"""
        with self._lock:
            logger.info(f'Starting incremental update for {len(changed_files)} files...')
            
            # 移除旧chunks中属于这些文件的
            changed_file_names = {f.name for f in changed_files}
            self.chunks = [
                chunk for chunk in self.chunks
                if chunk.metadata.get('file_name') not in changed_file_names
            ]
            
            # 重新解析这些文件
            new_chunks_count = 0
            for file_path in changed_files:
                if not file_path.exists() or file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                
                try:
                    from document_loader import iter_text_segments
                    documents = list(iter_text_segments(str(file_path.parent)))
                    for doc in documents:
                        if doc['metadata'].get('file_name') != file_path.name:
                            continue
                        segments = split_text(doc['content'], self.chunk_size, self.chunk_overlap)
                        doc_idx = len(self.chunks)
                        for seg_idx, segment in enumerate(segments, start=1):
                            chunk_id = f"{file_path.name}_{doc_idx}_{seg_idx}"
                            source = doc['source']
                            metadata = {**doc['metadata'], 'chunk_id': chunk_id}
                            self.chunks.append(KnowledgeChunk(
                                content=segment, source=source, metadata=metadata, chunk_id=chunk_id
                            ))
                            new_chunks_count += 1
                except Exception as exc:
                    logger.error(f'Failed to process {file_path}: {exc}', exc_info=True)
            
            # 重建索引
            self.build_bm25()
            if VECTOR_SUPPORT and self.retriever_type != 'bm25':
                try:
                    self.build_vector_store()
                except Exception as exc:
                    logger.warning(f'Vector store rebuild failed: {exc}', exc_info=True)
                    self.vector_store = None
            
            self.persist_index()
            logger.info(f'Incremental update completed. Added {new_chunks_count} new chunks, total: {len(self.chunks)}')

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
            logger.debug('No persisted index found')
            return False
        try:
            with paths['meta'].open('r', encoding='utf-8') as f:
                saved_meta = json.load(f)
            current_meta = self._meta_payload()
            if saved_meta != current_meta:
                logger.info('Index metadata changed, rebuilding...')
                return False

            with paths['chunks'].open('rb') as f:
                self.chunks = pickle.load(f)
            self.build_bm25()

            if VECTOR_SUPPORT and self.retriever_type != 'bm25':
                if not paths['faiss'].exists():
                    logger.warning('FAISS index file missing')
                    return False
                self.vector_embeddings = DashScopeEmbeddings(model='text-embedding-v1')
                self.vector_store = faiss.read_index(str(paths['faiss']))
                self.vector_metadata = self.chunks.copy()
            else:
                self.vector_store = None
                self.vector_metadata = []
            logger.info(f'Loaded persisted index with {len(self.chunks)} chunks')
            return True
        except Exception as exc:
            logger.warning(f'Failed to load persisted index: {exc}', exc_info=True)
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
            logger.info(f'Index persisted successfully with {len(self.chunks)} chunks')
        except Exception as exc:
            logger.error(f'Failed to persist index: {exc}', exc_info=True)

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
        logger.info(f'Building vector store for {len(self.chunks)} chunks...')
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
        logger.info('Vector store built successfully')

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
        
        # 分数归一化处理
        bm25_scores = [score for _, score in bm25_results]
        vector_scores = [score for _, score in vector_results]
        
        # Min-Max 归一化
        def normalize_scores(scores: List[float]) -> Dict[str, float]:
            if not scores:
                return {}
            min_score = min(scores)
            max_score = max(scores)
            if max_score == min_score:
                return {i: 0.5 for i in range(len(scores))}
            return {i: (s - min_score) / (max_score - min_score) for i, s in enumerate(scores)}
        
        bm25_normalized = normalize_scores(bm25_scores)
        vector_normalized = normalize_scores(vector_scores)
        
        # 使用字典优化查找效率
        chunk_map: Dict[str, KnowledgeChunk] = {chunk.chunk_id: chunk for chunk in self.chunks}
        score_map: Dict[str, float] = {}
        
        for idx, (chunk, _) in enumerate(bm25_results):
            normalized_score = bm25_normalized.get(idx, 0.0)
            score_map[chunk.chunk_id] = score_map.get(chunk.chunk_id, 0.0) + normalized_score * self.bm25_weight
        
        for idx, (chunk, _) in enumerate(vector_results):
            normalized_score = vector_normalized.get(idx, 0.0)
            score_map[chunk.chunk_id] = score_map.get(chunk.chunk_id, 0.0) + normalized_score * self.vector_weight

        if not score_map and self.bm25:
            return [SearchResult(chunk=chunk, score=0.0) for chunk, _ in bm25_results[: self.top_k]]

        # 直接从字典获取chunk，避免线性查找
        ranked = sorted(
            ((chunk_map[chunk_id], score) for chunk_id, score in score_map.items()),
            key=lambda item: item[1],
            reverse=True,
        )
        
        # Rerank阶段
        if self.enable_rerank and self.reranker and len(ranked) > 1:
            logger.debug(f'Applying rerank on {len(ranked)} candidates')
            # 取前top_k*2个候选进行rerank
            candidates = ranked[:min(self.top_k * 2, len(ranked))]
            pairs = [(query, chunk.content) for chunk, _ in candidates]
            
            try:
                rerank_scores = self.reranker.compute_score(pairs, normalize=True)
                if isinstance(rerank_scores, float):
                    rerank_scores = [rerank_scores]
                
                # 结合原始分数和rerank分数
                reranked = []
                for (chunk, original_score), rerank_score in zip(candidates, rerank_scores):
                    # 加权组合：原始分数占40%，rerank分数占60%
                    combined_score = original_score * 0.4 + rerank_score * 0.6
                    reranked.append(SearchResult(chunk=chunk, score=combined_score))
                
                # 重新排序并取top_k
                reranked.sort(key=lambda x: x.score, reverse=True)
                return reranked[:self.top_k]
            except Exception as exc:
                logger.warning(f'Rerank failed, using original ranking: {exc}')
        
        return [SearchResult(chunk=chunk, score=score) for chunk, score in ranked[:self.top_k]]

    def search(self, query: str) -> List[SearchResult]:
        if not query or not self.chunks:
            return []
        with self._lock:
            return self.hybrid_search(query)
