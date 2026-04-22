from typing import Dict, List, Optional

from qwen_agent.agent import Agent
from qwen_agent.llm import get_chat_model
from qwen_agent.llm.schema import ASSISTANT, Message, SYSTEM, USER

from retriever import KnowledgeIndex, SearchResult


class KnowledgeAgent(Agent):
    def __init__(self,
                 retriever: KnowledgeIndex,
                 llm_config: Dict,
                 function_list: Optional[List[str]] = None,
                 system_message: str = '',
                 memory_window: int = 6,
                 **kwargs):
        llm = get_chat_model(llm_config)
        super().__init__(function_list=function_list, llm=llm, system_message=system_message, **kwargs)
        self.retriever = retriever
        self.memory_window = memory_window
        self.history: List[Dict] = []

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
            fragments.append(
                f'[{idx}] 来源: {result.chunk.source} | 分数: {result.score:.4f}\n{content}'
            )
        return '请仅依据以下知识片段回答用户问题，严格不要凭空编造。如无法回答，请直接回复“未找到相关资料”。\n\n' + '\n\n'.join(fragments)

    def _run(self, messages: List[Message], lang: str = 'zh', **kwargs):
        if not messages:
            yield []
            return

        user_message = messages[-1]
        query = user_message.content if isinstance(user_message.content, str) else ''
        search_results = self.retriever.search(query)
        context_text = self._compose_context(query, search_results)

        prompt_messages = [Message(role=SYSTEM, content=f'{self.system_message}\n\n{context_text}')]
        for item in self.history:
            prompt_messages.append(Message(role=item['role'], content=item['content']))
        prompt_messages.append(Message(role=USER, content=query))

        llm_stream = self._call_llm(prompt_messages, stream=True, extra_generate_cfg=kwargs.get('extra_generate_cfg'))
        for response in llm_stream:
            yield response

    def answer(self, query: str) -> Dict[str, object]:
        user_message = {'role': USER, 'content': query}
        responses = self.run_nonstream([user_message])
        if not responses:
            return {'answer': '未找到相关资料', 'sources': []}

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

        top_hits = self.retriever.search(query)
        sources = [f"{idx + 1}. {hit.chunk.source}" for idx, hit in enumerate(top_hits)]
        return {'answer': answer, 'sources': sources}
