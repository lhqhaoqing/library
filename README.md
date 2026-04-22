# 智能知识库问答系统

基于 `Qwen-Agent` 的本地知识库问答系统原型。

## 目录结构

- `app.py`: 启动入口，支持 Gradio 界面与命令行模式。
- `config.yaml`: 系统配置，包括知识库目录、模型参数、检索策略和监听设置。
- `config.py`: 读取配置并处理环境变量。
- `document_loader.py`: 解析 PDF、Word、TXT、Markdown、Excel 文件。
- `retriever.py`: 构建 BM25 与可选向量检索索引。
- `qa_agent.py`: 基于 Qwen-Agent 的定制问答 Agent。

## 快速启动

1. 安装依赖

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

2. 设置 DashScope API Key（若使用 `dashscope` 模型）

```bash
set DASHSCOPE_API_KEY=your_api_key
```

3. 运行系统

```bash
.venv\Scripts\python.exe app.py
```

4. 如果没有启动 Gradio，可以指定命令行模式

```bash
.venv\Scripts\python.exe app.py --no-ui
```

## 配置说明

- `knowledge_dir`: 本地知识库目录，默认指向 `library`。
- `model`: Qwen-Agent 模型配置，支持 DashScope 远程模型或 OpenAI 兼容接口。
- `retriever`: 检索参数，包括 `top_k`、分块大小、BM25 与向量权重等。
- `watch`: 本地文件夹热更新监听配置。
- `app`: Gradio 服务地址与端口。

## 功能说明

- 支持多格式文件解析：PDF、Word、TXT、Markdown、Excel。
- 采用 BM25 与向量检索混合检索策略。
- 支持对话记忆与检索上下文约束回答。
- 提供 Gradio Web 界面与命令行两种交互方式。
