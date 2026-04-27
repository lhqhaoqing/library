import argparse
import logging
import shutil
import threading
from pathlib import Path
from typing import List

import gradio as gr

logger = logging.getLogger(__name__)

from config import load_config
from document_loader import SUPPORTED_EXTENSIONS
from qa_agent import KnowledgeAgent
from retriever import KnowledgeIndex


def build_agent(config: dict) -> KnowledgeAgent:
    retriever_cfg = config.get('retriever', {})
    index = KnowledgeIndex(
        root_path=config['knowledge_dir'],
        top_k=retriever_cfg.get('top_k', 5),
        chunk_size=retriever_cfg.get('chunk_size', 1200),
        chunk_overlap=retriever_cfg.get('chunk_overlap', 200),
        bm25_weight=retriever_cfg.get('bm25_weight', 0.4),
        vector_weight=retriever_cfg.get('vector_weight', 0.6),
        retriever_type=retriever_cfg.get('type', 'hybrid'),
        enable_rerank=retriever_cfg.get('rerank', False),
    )
    index.build_index()
    function_list = []
    if config.get('tools', {}).get('enable_code_interpreter', False):
        function_list.append('code_interpreter')
    
    # 缓存配置
    cache_cfg = config.get('cache', {})
    evaluation_cfg = config.get('evaluation', {})

    agent = KnowledgeAgent(
        retriever=index,
        llm_config=config.get('model', {}),
        function_list=function_list or None,
        system_message='你是一个企业内部知识库问答助手。回答必须严格依据检索到的知识片段。',
        enable_cache=cache_cfg.get('enabled', True),
        cache_capacity=cache_cfg.get('capacity', 100),
        cache_ttl=cache_cfg.get('ttl', 3600),
        enable_evaluation=evaluation_cfg.get('enabled', True),
    )
    return agent


def watch_folder(agent: KnowledgeAgent, paths: List[str]) -> None:
    try:
        from watchfiles import watch
    except ImportError:
        logger.warning('watchfiles not installed, file watching disabled')
        return

    valid_paths = [str(Path(p).resolve()) for p in paths if Path(p).exists()]
    if not valid_paths:
        logger.warning('Watch folder: no valid paths found, skipping monitoring.')
        return

    def _observer() -> None:
        for changes in watch(*valid_paths):
            logger.info(f'Detected {len(changes)} file change(s), updating index...')
            try:
                # 提取变化的文件路径
                changed_files = [Path(change[1]) for change in changes]
                # 使用增量更新
                agent.retriever.incremental_update(changed_files)
                logger.info('Index update completed.')
            except Exception as exc:
                logger.error(f'Index update failed: {exc}', exc_info=True)
                # 如果增量更新失败,回退到全量重建
                try:
                    logger.info('Falling back to full index rebuild...')
                    agent.retriever.build_index()
                    logger.info('Full index rebuild completed.')
                except Exception as fallback_exc:
                    logger.error(f'Full index rebuild also failed: {fallback_exc}', exc_info=True)

    thread = threading.Thread(target=_observer, daemon=True)
    thread.start()


def chat_with_agent(query: str, history: List[dict], agent: KnowledgeAgent):
    if not query:
        return history, ''
    result = agent.answer(query)
    history = history + [
        {'role': 'user', 'content': query},
        {'role': 'assistant', 'content': result['answer']},
    ]
    sources = '\n'.join(result['sources']) if result['sources'] else '未检索到引用来源。'
    return history, sources


def launch_ui(agent: KnowledgeAgent, config: dict) -> None:
    knowledge_dir = Path(config['knowledge_dir']).resolve()
    supported_upload_types = sorted(SUPPORTED_EXTENSIONS)

    def chat_with_agent_stream(query: str, history: List[dict]):
        """流式聊天函数"""
        if not query:
            return history, '', history, ''
        
        # 先添加用户消息到历史
        history = history + [{'role': 'user', 'content': query}]
        yield history, '正在检索知识库...', history, ''
        
        try:
            # 直接调用answer方法获取结果（非流式，但更可靠）
            result = agent.answer(query)
            answer = result['answer']
            sources_list = result['sources']
            
            # 添加助手回答
            history = history + [{'role': 'assistant', 'content': answer}]
            
            # 格式化来源
            sources_text = '\n'.join(sources_list) if sources_list else '未检索到引用来源。'
            
            yield history, sources_text, history, ''
        except Exception as e:
            logger.error(f'Chat error: {e}', exc_info=True)
            error_history = history + [{'role': 'assistant', 'content': f'回答生成失败: {str(e)}'}]
            yield error_history, '回答生成失败', error_history, ''

    def chat_with_agent(query: str, history: List[dict]):
        if not query:
            return history, '', history, ''
        result = agent.answer(query)
        history = history + [
            {'role': 'user', 'content': query},
            {'role': 'assistant', 'content': result['answer']},
        ]
        sources = '\n'.join(result['sources']) if result['sources'] else '未检索到引用来源。'
        return history, sources, history, ''

    def upload_files(files):
        if not files:
            return '请先选择要上传的文件。', gr.update(value='上传并更新索引', interactive=True)

        knowledge_dir.mkdir(parents=True, exist_ok=True)
        uploaded = []
        overwritten = []
        skipped = []

        for file_path in files:
            source_path = Path(file_path)
            if not source_path.exists():
                skipped.append(f'{source_path.name}（临时文件不存在）')
                continue

            if source_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                skipped.append(f'{source_path.name}（不支持的格式）')
                continue

            target_path = knowledge_dir / source_path.name
            if target_path.exists():
                overwritten.append(source_path.name)
            else:
                uploaded.append(source_path.name)
            shutil.copy2(source_path, target_path)

        if uploaded or overwritten:
            try:
                agent.retriever.build_index()
            except Exception as exc:
                return f'文件已上传，但索引更新失败：{exc}', gr.update(value='上传并更新索引', interactive=True)

        messages = []
        if uploaded:
            messages.append('新增文件：' + '、'.join(uploaded))
        if overwritten:
            messages.append('覆盖更新：' + '、'.join(overwritten))
        if skipped:
            messages.append('跳过文件：' + '、'.join(skipped))
        if not messages:
            return '没有可处理的上传文件。', gr.update(value='上传并更新索引', interactive=True)
        messages.append('索引已自动更新。')
        return '\n'.join(messages), gr.update(value='上传并更新索引', interactive=True)

    def start_upload():
        return '上传中，请稍候...', gr.update(value='上传中...', interactive=False)

    custom_css = '''
    .gradio-container {
        background: #f3f6fb;
    }
    #page-wrap {
        max-width: 1080px;
        margin: 0 auto;
    }
    #app-title {
        text-align: center;
        margin-bottom: 4px;
    }
    #app-subtitle {
        text-align: center;
        color: #6b7280;
        margin-top: 0;
        margin-bottom: 18px;
    }
    #main-card, #source-card, #upload-card {
        border: 1px solid #d8e1ee;
        border-radius: 14px;
        padding: 14px;
        background: #ffffff;
        box-shadow: 0 4px 14px rgba(15, 23, 42, 0.06);
        margin-bottom: 12px;
    }
    .section-title {
        margin: 0 0 10px 0 !important;
        font-weight: 700;
        color: #0f172a;
    }
    #chat-box {
        border: 1px solid #dbe3ef;
        border-radius: 12px;
        background: #fbfdff;
    }
    #source-box {
        max-height: 180px;
        overflow-y: auto;
        border: 1px dashed #b8c6dc;
        border-radius: 10px;
        padding: 10px 12px;
        background: #f8fbff;
    }
    #composer-wrap {
        position: relative;
    }
    #input-box textarea {
        font-size: 14px !important;
        min-height: 64px !important;
        padding-right: 52px !important;
    }
    #input-box > label > span {
        display: none !important;
    }
    #ask-btn {
        position: absolute !important;
        right: 21px;
        top: 50%;
        transform: translateY(-50%);
        min-width: 36px !important;
        width: 36px !important;
        height: 36px !important;
        padding: 0 !important;
        z-index: 20;
    }
    #ask-btn, #upload-btn {
        border-radius: 8px !important;
        font-weight: 600 !important;
    }
    #upload-zone {
        border: 1px solid #d8e1ee;
        border-radius: 10px;
        padding: 10px;
        background: #f8fbff;
        margin-bottom: 12px;
    }
    #upload-btn-wrap {
        border-top: 1px dashed #c7d2e4;
        padding-top: 12px;
        margin-top: 4px;
    }
    '''

    theme = gr.themes.Soft(primary_hue='blue', secondary_hue='slate')
    with gr.Blocks(theme=theme, css=custom_css) as demo:
        with gr.Column(elem_id='page-wrap'):
            gr.Markdown('## 智能知识库问答系统', elem_id='app-title')
            gr.Markdown('企业知识检索问答 · 支持文档上传后自动更新索引', elem_id='app-subtitle')

            with gr.Column(elem_id='main-card'):
                gr.Markdown('### 问答区', elem_classes=['section-title'])
                chatbot = gr.Chatbot(type='messages', elem_id='chat-box', height=460)
                with gr.Group(elem_id='composer-wrap'):
                    message = gr.Textbox(
                        label='',
                        placeholder='例如：这份合同的保修期是多久？',
                        elem_id='input-box',
                    )
                    submit_btn = gr.Button('➤', variant='primary', elem_id='ask-btn')
                
                # 反馈按钮
                with gr.Row():
                    feedback_good = gr.Button('👍 有帮助', variant='secondary', size='sm')
                    feedback_bad = gr.Button('👎 无帮助', variant='secondary', size='sm')
                feedback_status = gr.Markdown('', visible=False)

            with gr.Column(elem_id='source-card'):
                gr.Markdown('### 引用来源', elem_classes=['section-title'])
                with gr.Accordion('查看引用来源明细', open=False):
                    sources = gr.Markdown('未检索到引用来源。', elem_id='source-box')

            with gr.Column(elem_id='upload-card'):
                gr.Markdown('### 文件上传区', elem_classes=['section-title'])
                with gr.Accordion('上传文件到知识库（library）', open=False):
                    with gr.Column(elem_id='upload-zone'):
                        upload_files_input = gr.File(
                            label='选择要上传的文件（支持多选）',
                            file_count='multiple',
                            file_types=supported_upload_types,
                            type='filepath',
                        )
                    with gr.Row(elem_id='upload-btn-wrap'):
                        upload_btn = gr.Button('上传并更新索引', variant='secondary', elem_id='upload-btn')
                    upload_status = gr.Markdown('')
                    upload_btn.click(fn=start_upload, outputs=[upload_status, upload_btn]).then(
                        fn=upload_files,
                        inputs=[upload_files_input],
                        outputs=[upload_status, upload_btn],
                    )
            
            # 评估指标面板
            with gr.Column(elem_id='upload-card'):
                gr.Markdown('### 评估指标', elem_classes=['section-title'])
                with gr.Accordion('查看系统评估数据', open=False):
                    metrics_display = gr.JSON(label='性能指标')
                    bad_cases_display = gr.JSON(label='Bad Cases (最近20条)')
                    refresh_metrics_btn = gr.Button('刷新指标', variant='secondary')
                    
                    def refresh_metrics():
                        if agent.evaluator:
                            metrics = agent.evaluator.calculate_metrics()
                            bad_cases = agent.evaluator.get_bad_cases(limit=20)
                            cache_stats = agent.get_cache_stats()
                            return {
                                'system_metrics': metrics,
                                'cache_stats': cache_stats,
                            }, bad_cases
                        return {'error': '评估功能未启用'}, []
                    
                    refresh_metrics_btn.click(
                        fn=refresh_metrics,
                        outputs=[metrics_display, bad_cases_display]
                    )

        state = gr.State([])

        # 使用流式输出
        message.submit(
            fn=chat_with_agent_stream,
            inputs=[message, state],
            outputs=[chatbot, sources, state, message],
        )
        submit_btn.click(
            fn=chat_with_agent_stream,
            inputs=[message, state],
            outputs=[chatbot, sources, state, message],
        )
        
        # 反馈处理
        def handle_feedback(is_good: bool):
            if not state.value or len(state.value) < 2:
                return '请先进行对话'
            last_user_msg = state.value[-2]['content'] if state.value[-2]['role'] == 'user' else None
            if last_user_msg and agent.evaluator:
                agent.evaluator.collect_feedback(
                    query=last_user_msg,
                    is_helpful=is_good,
                    relevance_score=5 if is_good else 1
                )
                metrics = agent.evaluator.calculate_metrics()
                return f"反馈已记录！总查询:{metrics['total_queries']}, 有用率:{metrics.get('helpful_rate', 'N/A')}"
            return '反馈功能未启用'
        
        feedback_good.click(fn=lambda: handle_feedback(True), outputs=[feedback_status])
        feedback_bad.click(fn=lambda: handle_feedback(False), outputs=[feedback_status])

        demo.launch(server_name=config['app'].get('host', '0.0.0.0'), server_port=config['app'].get('port', 7680))


def main() -> None:
    parser = argparse.ArgumentParser(description='知识库问答系统')
    parser.add_argument('--no-ui', action='store_true', help='不启动 Gradio 界面，仅打印输出')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='日志级别 (default: INFO)')
    args = parser.parse_args()

    # 初始化日志系统
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('knowledge_base.log', encoding='utf-8')
        ]
    )

    config = load_config()
    agent = build_agent(config)
    if config.get('watch', {}).get('enabled', False):
        watch_paths = config.get('watch', {}).get('paths', [])
        if watch_paths:
            watch_folder(agent, watch_paths)

    if args.no_ui or not config.get('app', {}).get('enable_gradio', True):
        logger.info('Started in command-line Q&A mode. Type exit or quit to quit.')
        while True:
            query = input('问题: ').strip()
            if query.lower() in {'exit', 'quit'}:
                break
            result = agent.answer(query)
            print('\n回答:\n', result['answer'])
            print('\n来源:\n', '\n'.join(result['sources']) or '未检索到引用来源。')
            print('-' * 50)
    else:
        logger.info(f'Starting Gradio UI on {config["app"].get("host", "0.0.0.0")}:{config["app"].get("port", 80)}')
        launch_ui(agent, config)


if __name__ == '__main__':
    main()
