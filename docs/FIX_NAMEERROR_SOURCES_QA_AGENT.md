# NameError: sources 变量未定义修复

## 错误信息
```
NameError: name 'sources' is not defined
File "qa_agent.py", line 204, in answer
    self.evaluator.record_query(query, answer, sources, response_time)
```

## 问题原因

在 `qa_agent.py` 的 `answer()` 方法中：

1. **第180行**：定义了变量 `sources_detailed`
   ```python
   sources_detailed = []
   ```

2. **第195行**：使用 `sources_detailed` 构建 result
   ```python
   result = {'answer': answer, 'sources': sources_detailed}
   ```

3. **第204行**：❌ 错误地使用了不存在的 `sources` 变量
   ```python
   self.evaluator.record_query(query, answer, sources, response_time)
   ```

这是一个典型的**变量名不一致**错误。

## 修复方案

将第204行的 `sources` 改为 `sources_detailed`：

```python
# ❌ 修复前
self.evaluator.record_query(query, answer, sources, response_time)

# ✅ 修复后
self.evaluator.record_query(query, answer, sources_detailed, response_time)
```

## 完整上下文

```python
def answer(self, query: str) -> Dict[str, object]:
    import time
    start_time = time.time()
    
    # ... 缓存检查和LLM调用 ...
    
    # 构建详细的来源信息（包含页码/段落）
    sources_detailed = []  # ✅ 正确的变量名
    for idx, hit in enumerate(search_results):
        metadata = hit.chunk.metadata
        source_info = hit.chunk.source
        
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
        # ✅ 使用正确的变量名
        self.evaluator.record_query(query, answer, sources_detailed, response_time)
    
    return result
```

## 预防措施

### 1. 使用IDE的类型检查
- PyCharm、VS Code 等IDE会高亮未定义的变量
- 启用 Python linter (pylint, flake8)

### 2. 代码审查清单
- [ ] 所有变量在使用前都已定义
- [ ] 变量名拼写一致
- [ ] 作用域正确（局部/全局）

### 3. 单元测试
```python
def test_answer_records_evaluation():
    agent = KnowledgeAgent(...)
    result = agent.answer("测试问题")
    
    # 验证返回结果
    assert 'answer' in result
    assert 'sources' in result
    assert isinstance(result['sources'], list)
    
    # 验证评估记录
    if agent.evaluator:
        metrics = agent.evaluator.calculate_metrics()
        assert metrics['total_queries'] >= 1
```

### 4. 静态分析工具
```bash
# 安装 pylint
pip install pylint

# 运行检查
pylint qa_agent.py
```

## 相关文件

- [qa_agent.py - answer()](file://c:\lhq\work\hyh_knowledge_lab\qa_agent.py#L137-L206)

## 测试验证

```bash
.venv\Scripts\python.exe app.py
```

在 Web 界面中输入问题，应该能正常收到回答，不再有 NameError。

---

**修复日期**: 2026-04-23  
**错误类型**: NameError - 变量未定义  
**严重程度**: 🔴 高（导致功能完全不可用）  
**根本原因**: 变量名拼写不一致
