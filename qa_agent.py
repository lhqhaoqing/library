from typing import Dict, List, Optional
import hashlib
import logging

from qwen_agent.agent import Agent
from qwen_agent.llm import get_chat_model
from qwen_agent.llm.schema import ASSISTANT, Message, SYSTEM, USER

from retriever import KnowledgeIndex, SearchResult
from cache import LRUCache
from evaluator import Evaluator

logger = logging.getLogger(__name__)


class KnowledgeAgent(Agent):
    def __init__(self,
                 retriever: KnowledgeIndex,
                 llm_config: Dict,
                 function_list: Optional[List[str]] = None,
                 system_message: str = '',
                 memory_window: int = 6,
                 enable_cache: bool = True,
                 cache_capacity: int = 100,
                 cache_ttl: int = 3600,
                 enable_evaluation: bool = True,
                 **kwargs):
        llm = get_chat_model(llm_config)
        super().__init__(function_list=function_list, llm=llm, system_message=system_message, **kwargs)
        self.retriever = retriever
        self.memory_window = memory_window
        self.history: List[Dict] = []
        self._last_search_results: Optional[List[SearchResult]] = None
        
        # LRU缓存
        self.enable_cache = enable_cache
        if enable_cache:
            self.cache = LRUCache(capacity=cache_capacity, ttl=cache_ttl)
            logger.info(f'LRU cache enabled (capacity={cache_capacity}, ttl={cache_ttl}s)')
        else:
            self.cache = None
        
        # 评估器
        self.enable_evaluation = enable_evaluation
        if enable_evaluation:
            self.evaluator = Evaluator()
            logger.info('Evaluation system enabled')
        else:
            self.evaluator = None

    def add_memory(self, role: str, content: str) -> None:
        self.history.append({'role': role, 'content': content})
        if len(self.history) > self.memory_window * 2:
            self.history = self.history[-self.memory_window * 2:]

    def reset_memory(self) -> None:
        self.history = []

    def _compose_context(self, query: str, search_results: List[SearchResult]) -> str:
        if not search_results:
            return '当前知识库未检索到相关资料。请直接返回“未找到相关资料”，不要编造答案。'

        fragments = []
        for idx, result in enumerate(search_results, start=1):
            content = result.chunk.content.strip().replace('\n', ' ').replace('  ', ' ')
            if len(content) > 1200:
                content = content[:1200].rstrip() + '...'
            
            # 构建详细来源信息
            metadata = result.chunk.metadata
            source_info = result.chunk.source
            
            # 添加页码/段落信息
            if 'page' in metadata:
                source_info += f" (第{metadata['page']}页)"
            elif 'paragraph' in metadata:
                source_info += f" (第{metadata['paragraph']}段)"
            elif 'sheet_name' in metadata:
                source_info += f" ({metadata['sheet_name']})"
            
            fragments.append(
                f'[{idx}] 来源: {source_info} | 分数: {result.score:.4f}\n{content}'
            )
        return '请仅依据以下知识片段回答用户问题，严格不要凭空编造。如无法回答，请直接回复“未找到相关资料”。\n\n' + '\n\n'.join(fragments)

    def _run(self, messages: List[Message], lang: str = 'zh', **kwargs):
        if not messages:
            yield []
            return

        user_message = messages[-1]
        query = user_message.content if isinstance(user_message.content, str) else ''
        search_results = self.retriever.search(query)
        # 缓存检索结果，避免重复检索
        self._last_search_results = search_results
        context_text = self._compose_context(query, search_results)

        # 构建prompt：system message必须是第一个且只能有一个
        prompt_messages = [Message(role=SYSTEM, content=f'{self.system_message}\n\n{context_text}')]
        
        # 添加历史消息（排除system message，只保留user和assistant）
        for item in messages[:-1]:  # 排除最后一个用户消息
            if isinstance(item, dict):
                role = item.get('role', '')
                # 只添加user和assistant消息，跳过system消息
                if role in ['user', 'assistant', USER, ASSISTANT]:
                    prompt_messages.append(Message(role=role, content=item['content']))
            elif hasattr(item, 'role'):
                # 如果是Message对象，也跳过system消息
                if item.role in ['user', 'assistant', USER, ASSISTANT]:
                    prompt_messages.append(item)
        
        # 最后添加当前用户消息
        prompt_messages.append(Message(role=USER, content=query))

        llm_stream = self._call_llm(prompt_messages, stream=True, extra_generate_cfg=kwargs.get('extra_generate_cfg'))
        full_response = ''
        for response in llm_stream:
            if response and len(response) > 0:
                last_msg = response[-1]
                if hasattr(last_msg, 'content'):
                    full_response = last_msg.content
            yield response
        
        # 流式结束后，更新内部历史
        if full_response:
            self.add_memory(USER, query)
            self.add_memory(ASSISTANT, full_response)

    def _get_cache_key(self, query: str) -> str:
        """生成缓存键"""
        return hashlib.md5(query.encode('utf-8')).hexdigest()
    
    def answer(self, query: str) -> Dict[str, object]:
        import time
        start_time = time.time()
        
        # 检查缓存
        if self.enable_cache and self.cache:
            cache_key = self._get_cache_key(query)
            cached_result = self.cache.get(cache_key)
            if cached_result:
                logger.info(f'Cache hit for query: {query[:50]}...')
                return cached_result
        
        user_message = {'role': USER, 'content': query}
        responses = self.run_nonstream([user_message])
        if not responses:
            result = {'answer': '未找到相关资料', 'sources': []}
            # 缓存结果
            if self.enable_cache and self.cache:
                self.cache.put(cache_key, result)
            # 记录评估
            if self.enable_evaluation and self.evaluator:
                response_time = (time.time() - start_time) * 1000
                self.evaluator.record_query(query, result['answer'], result['sources'], response_time)
            return result

        if isinstance(responses, dict):
            assistant_message = responses
        elif isinstance(responses, list) and responses and isinstance(responses[0], list):
            assistant_message = responses[-1][-1] if responses[-1] else responses[0][0]
        elif isinstance(responses, list):
            assistant_message = responses[-1]
        else:
            assistant_message = responses

        if isinstance(assistant_message, dict):
            answer = assistant_message.get('content', '')
        else:
            answer = assistant_message.content if hasattr(assistant_message, 'content') else str(assistant_message)

        self.add_memory(USER, query)
        self.add_memory(ASSISTANT, answer)

        # 使用缓存的检索结果，避免重复检索
        search_results = self._last_search_results or self.retriever.search(query)
        
        # 构建详细的来源信息（包含页码/段落）
        sources_detailed = []
        for idx, hit in enumerate(search_results):
            metadata = hit.chunk.metadata
            source_info = hit.chunk.source
            
            # 添加页码/段落信息
            if 'page' in metadata:
                source_info += f" (第{metadata['page']}页)"
            elif 'paragraph' in metadata:
                source_info += f" (第{metadata['paragraph']}段)"
            elif 'sheet_name' in metadata:
                source_info += f" ({metadata['sheet_name']})"
            
            sources_detailed.append(f"{idx + 1}. {source_info}")
        
        result = {'answer': answer, 'sources': sources_detailed}
        
        # 缓存结果
        if self.enable_cache and self.cache:
            self.cache.put(cache_key, result)
        
        # 记录评估
        if self.enable_evaluation and self.evaluator:
            response_time = (time.time() - start_time) * 1000
            self.evaluator.record_query(query, answer, sources_detailed, response_time)
        
        return result
    
    def get_cache_stats(self) -> Dict[str, any]:
        """获取缓存统计信息"""
        if self.cache:
            return self.cache.stats()
        return {'enabled': False}
