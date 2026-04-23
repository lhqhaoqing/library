# NameError: sources is not defined 修复

## 错误信息
```
回答生成失败: name 'sources' is not defined
```

## 问题原因

在 `chat_with_agent_stream` 函数中存在两个问题：

### 问题1：yield 返回值不一致
```python
# ❌ 错误的写法
yield history, '正在检索知识库...', [], ''  # 第三个参数是空列表
```

Gradio 的 State 组件期望接收一致的类型，第一次返回 `[]`，后续返回 `history`（list of dicts），可能导致内部状态混乱。

### 问题2：原地修改 history 导致状态问题
```python
# ❌ 错误的写法
history.append({'role': 'assistant', 'content': f'回答生成失败: {str(e)}'})
yield history, '回答生成失败', history, ''
```

在 Gradio 中，直接修改传入的 list 对象可能导致：
- 状态同步问题
- 引用混乱
- 不可预期的行为

## 修复方案

### 修复1：保持一致的返回值
```python
# ✅ 正确的写法
yield history, '正在检索知识库...', history, ''
```

所有 yield 语句的第三个参数都应该是 `history`（State 的值）。

### 修复2：使用不可变方式更新历史
```python
# ✅ 正确的写法
error_history = history + [{'role': 'assistant', 'content': f'回答生成失败: {str(e)}'}]
yield error_history, '回答生成失败', error_history, ''
```

通过创建新列表而不是修改原列表，确保：
- 状态清晰
- 无副作用
- 符合函数式编程原则

## 完整修复代码

```python
def chat_with_agent_stream(query: str, history: List[dict]):
    """流式聊天函数"""
    if not query:
        return history, '', history, ''
    
    # ✅ 先添加用户消息到历史
    history = history + [{'role': 'user', 'content': query}]
    yield history, '正在检索知识库...', history, ''  # ✅ 第三个参数是 history
    
    try:
        # 直接调用answer方法获取结果（非流式，但更可靠）
        result = agent.answer(query)
        answer = result['answer']
        sources_list = result['sources']
        
        # ✅ 添加助手回答（创建新列表）
        history = history + [{'role': 'assistant', 'content': answer}]
        
        # 格式化来源
        sources_text = '\n'.join(sources_list) if sources_list else '未检索到引用来源。'
        
        yield history, sources_text, history, ''
    except Exception as e:
        logger.error(f'Chat error: {e}', exc_info=True)
        # ✅ 创建新的 error_history，不修改原 history
        error_history = history + [{'role': 'assistant', 'content': f'回答生成失败: {str(e)}'}]
        yield error_history, '回答生成失败', error_history, ''
```

## Gradio State 组件最佳实践

### 1. 始终返回一致的类型
```python
# ✅ 好：所有分支返回相同类型
state = gr.State([])

def handler(input, state):
    new_state = state + [item]  # 总是返回 list
    return output, new_state
```

### 2. 避免原地修改
```python
# ❌ 坏：原地修改
state.append(item)
return output, state

# ✅ 好：创建新对象
new_state = state + [item]
return output, new_state
```

### 3. 保持返回值数量一致
```python
# outputs=[chatbot, sources, state, message]
# 必须返回4个值
yield history, sources_text, history, ''
```

## 常见错误模式

### 错误1：返回值数量不匹配
```python
# 定义了4个outputs
outputs=[chatbot, sources, state, message]

# ❌ 但只返回3个值
yield history, sources_text, history

# ✅ 应该返回4个值
yield history, sources_text, history, ''
```

### 错误2：类型不一致
```python
# ❌ 有时返回list，有时返回None
if condition:
    return output, []
else:
    return output, None

# ✅ 始终返回相同类型
return output, [] if not items else items
```

### 错误3：原地修改状态
```python
# ❌ 修改传入的状态对象
def handler(data, state):
    state['count'] += 1  # 原地修改
    return output, state

# ✅ 创建新对象
def handler(data, state):
    new_state = {**state, 'count': state['count'] + 1}
    return output, new_state
```

## 调试技巧

### 1. 添加日志
```python
def chat_with_agent_stream(query: str, history: List[dict]):
    logger.debug(f"Input history type: {type(history)}, length: {len(history)}")
    
    # ... 处理逻辑 ...
    
    logger.debug(f"Output history type: {type(history)}, length: {len(history)}")
    yield history, sources_text, history, ''
```

### 2. 类型检查
```python
assert isinstance(history, list), f"Expected list, got {type(history)}"
assert len(history) % 2 == 0, "History should have pairs of user/assistant"
```

### 3. 简化测试
```python
# 最小化测试用例
def test_handler():
    history = []
    result = list(chat_with_agent_stream("test", history))
    print(f"Yield count: {len(result)}")
    for i, yield_val in enumerate(result):
        print(f"Yield {i}: {[type(v).__name__ for v in yield_val]}")
```

## 相关文件

- [app.py - chat_with_agent_stream()](file://c:\lhq\work\hyh_knowledge_lab\app.py#L103-L128)

## 测试验证

```bash
.venv\Scripts\python.exe app.py
```

在 Web 界面中：
1. 输入一个问题
2. 应该看到：
   - 用户消息显示
   - "正在检索知识库..." 提示
   - AI 回答正常显示
   - 来源信息显示
3. 如果出错，应该看到友好的错误提示，而不是 "name 'sources' is not defined"

## 总结

这个错误的根本原因是 **Gradio 状态管理的不当使用**。关键原则：

1. ✅ 返回值数量和类型必须一致
2. ✅ 避免原地修改状态对象
3. ✅ 使用不可变方式更新状态（创建新对象）
4. ✅ 所有代码路径都要返回正确数量的值

遵循这些原则可以避免大多数 Gradio 相关的状态错误。

---

**修复日期**: 2026-04-23  
**错误类型**: NameError  
**严重程度**: 🔴 高（导致功能完全不可用）
