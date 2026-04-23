# 项目依赖说明

## 📦 依赖清单

所有依赖已整理到 [requirements.txt](../requirements.txt),按功能分类组织。

## 🔧 核心依赖

### 1. 核心框架
- **qwen-agent[rag,code_interpreter]** - Qwen-Agent框架
  - 提供Agent基础能力
  - 包含RAG检索增强生成
  - 包含代码解释器功能
  - 自动安装 dashscope SDK

### 2. Web界面
- **gradio>=4.0.0** - Web UI框架
  - 提供聊天界面
  - 支持流式输出
  - 文件上传功能

### 3. 向量检索
- **faiss-cpu>=1.7.0** - Facebook AI向量搜索引擎
  - CPU版本(无需GPU)
  - 向量相似度搜索
  - 高效的最近邻查询

- **langchain-community>=0.0.10** - LangChain社区版
  - 提供DashScopeEmbeddings
  - 文本嵌入接口

- **numpy>=1.24.0** - 数值计算库
  - FAISS依赖
  - 向量运算

### 4. 文本处理
- **jieba>=0.42.1** - 中文分词库
  - BM25检索的分词器
  - 中文文本处理

- **rank-bm25>=0.2.2** - BM25算法实现
  - 关键词检索
  - 与向量检索混合使用

### 5. 文档解析
- **pdfplumber>=0.10.0** - PDF文件解析
  - 提取PDF文本
  - 保留页码信息

- **python-docx>=1.0.0** - Word文档解析
  - 读取.docx文件
  - 提取段落内容

- **openpyxl>=3.1.0** - Excel文件解析
  - 读取.xlsx文件
  - 支持多工作表

- **PyYAML>=6.0** - YAML配置文件解析
  - 读取config.yaml
  - 配置管理

### 6. 文件监听
- **watchfiles>=0.20.0** - 文件系统监听
  - 知识库热更新
  - 自动重建索引

## 🎯 可选依赖

### Rerank重排序 (推荐启用)
```bash
pip install FlagEmbedding
```
- 提升检索相关度15-25%
- 使用BGE Reranker模型
- 在config.yaml中设置 `rerank: true`

### 开发工具
```bash
pip install pylint pytest
```
- **pylint** - 代码静态检查
- **pytest** - 单元测试框架

## 📋 依赖关系图

```
qwen-agent (核心)
├── dashscope (API调用)
├── gradio (UI)
└── langchain (可选)

faiss-cpu (向量检索)
└── numpy

retriever (检索模块)
├── jieba (分词)
├── rank-bm25 (关键词)
└── faiss-cpu (向量)

document_loader (文档解析)
├── pdfplumber (PDF)
├── python-docx (Word)
└── openpyxl (Excel)

app.py (应用入口)
├── gradio (Web界面)
├── watchfiles (文件监听)
└── PyYAML (配置)
```

## 🚀 安装方法

### 标准安装
```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 启用Rerank
```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install FlagEmbedding
```

### 最小化安装 (仅核心功能)
```bash
.venv\Scripts\python.exe -m pip install qwen-agent[rag] gradio PyYAML
```

## ⚠️ 注意事项

### 1. Python版本要求
- **最低版本**: Python 3.8
- **推荐版本**: Python 3.10+
- 检查版本: `python --version`

### 2. 虚拟环境
强烈建议使用虚拟环境:
```bash
# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境 (Windows)
.venv\Scripts\activate

# 激活虚拟环境 (Linux/Mac)
source .venv/bin/activate
```

### 3. 依赖冲突
如果遇到依赖冲突:
```bash
# 清除缓存重新安装
pip cache purge
pip install -r requirements.txt --force-reinstall
```

### 4. 网络问题
如果下载速度慢,使用国内镜像:
```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 5. FAISS GPU版本
如果有GPU,可以使用GPU版本:
```bash
pip uninstall faiss-cpu
pip install faiss-gpu
```

## 📊 依赖大小估算

| 依赖包 | 安装大小 | 说明 |
|--------|----------|------|
| qwen-agent | ~50MB | 核心框架 |
| gradio | ~30MB | Web界面 |
| faiss-cpu | ~20MB | 向量数据库 |
| langchain-community | ~15MB | Embeddings |
| pdfplumber | ~10MB | PDF解析 |
| 其他 | ~25MB | 各种工具库 |
| **总计** | **~150MB** | 不含FlagEmbedding |

启用FlagEmbedding额外增加: ~400MB (模型文件)

## 🔄 依赖更新策略

### 定期检查更新
```bash
# 检查过时的包
pip list --outdated

# 更新所有包
pip install -r requirements.txt --upgrade
```

### 锁定版本 (生产环境)
```bash
# 生成精确版本列表
pip freeze > requirements_locked.txt

# 使用锁定版本安装
pip install -r requirements_locked.txt
```

### 版本兼容性测试
更新依赖后运行测试:
```bash
.venv\Scripts\python.exe test_quick.py
.venv\Scripts\python.exe app.py
```

## 🐛 常见问题

### Q1: 导入错误 "No module named 'xxx'"
**解决**: 确认虚拟环境已激活
```bash
.venv\Scripts\activate
pip install -r requirements.txt
```

### Q2: 版本冲突
**解决**: 删除虚拟环境重新创建
```bash
rm -rf .venv
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Q3: FlagEmbedding安装失败
**解决**: 先安装torch
```bash
pip install torch
pip install FlagEmbedding
```

### Q4: Gradio启动失败
**解决**: 检查端口占用
```bash
# Windows
netstat -ano | findstr :80

# 修改config.yaml中的端口
app:
  port: 7860
```

## 📝 依赖添加流程

当需要添加新依赖时:

1. **确定必要性**
   - 是否真的需要这个包?
   - 是否有更轻量的替代方案?

2. **选择版本**
   - 使用 `>=` 指定最低版本
   - 避免使用 `==` 锁定 exact 版本(除非必要)

3. **分类添加**
   - 添加到requirements.txt的合适分类下
   - 添加注释说明用途

4. **测试验证**
   - 在新环境中测试安装
   - 运行所有测试用例
   - 确认功能正常

5. **更新文档**
   - 更新本说明文档
   - 记录添加原因

## 🔗 相关资源

- [Qwen-Agent官方文档](https://github.com/QwenLM/Qwen-Agent)
- [Gradio文档](https://www.gradio.app/docs)
- [FAISS文档](https://faiss.ai/)
- [LangChain文档](https://python.langchain.com/)

---

**最后更新**: 2026-04-23  
**维护者**: AI开发团队  
**Python版本**: >= 3.8
