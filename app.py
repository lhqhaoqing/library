import argparse
import shutil
import threading
from pathlib import Path
from typing import List

import gradio as gr

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
    )
    index.build_index()
    function_list = []
    if config.get('tools', {}).get('enable_code_interpreter', False):
        function_list.append('code_interpreter')

    agent = KnowledgeAgent(
        retriever=index,
        llm_config=config.get('model', {}),
        function_list=function_list or None,
        system_message='你是一个企业内部知识库问答助手。回答必须严格依据检索到的知识片段。',
    )
    return agent


def watch_folder(agent: KnowledgeAgent, paths: List[str]) -> None:
    try:
        from watchfiles import watch
    except ImportError:
        return

    valid_paths = [str(Path(p).resolve()) for p in paths if Path(p).exists()]
    if not valid_paths:
        print('Warning: watch folder 未找到有效路径，已跳过监听。')
        return

    def _observer() -> None:
        for _change in watch(*valid_paths):
            print('检测到知识库更新，正在重建索引...')
            try:
                agent.retriever.build_index()
                print('索引重建完成。')
            except Exception as exc:
                print(f'索引重建失败: {exc}')

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

        state = gr.State([])

        message.submit(
            fn=chat_with_agent,
            inputs=[message, state],
            outputs=[chatbot, sources, state, message],
        )
        submit_btn.click(
            fn=chat_with_agent,
            inputs=[message, state],
            outputs=[chatbot, sources, state, message],
        )

        demo.launch(server_name=config['app'].get('host', '0.0.0.0'), server_port=config['app'].get('port', 80))


def main() -> None:
    parser = argparse.ArgumentParser(description='知识库问答系统')
    parser.add_argument('--no-ui', action='store_true', help='不启动 Gradio 界面，仅打印输出')
    args = parser.parse_args()

    config = load_config()
    agent = build_agent(config)
    if config.get('watch', {}).get('enabled', False):
        watch_paths = config.get('watch', {}).get('paths', [])
        if watch_paths:
            watch_folder(agent, watch_paths)

    if args.no_ui or not config.get('app', {}).get('enable_gradio', True):
        print('已启动命令行问答模式。输入 exit 或 quit 退出。')
        while True:
            query = input('问题: ').strip()
            if query.lower() in {'exit', 'quit'}:
                break
            result = agent.answer(query)
            print('\n回答:\n', result['answer'])
            print('\n来源:\n', '\n'.join(result['sources']) or '未检索到引用来源。')
            print('-' * 50)
    else:
        launch_ui(agent, config)


if __name__ == '__main__':
    main()
