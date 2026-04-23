# System Message 重复问题修复

## 错误信息
```
Error code: 400. Error message: The input messages must contain no more than one system message. 
And the system message, if exists, must be the first message.
```

## 问题原因

在 `_run` 方法中构建 prompt 时：

1. **首先添加了 system message**（第98行）
   ```python
   prompt_messages = [Message(role=SYSTEM, content=f'{self.system_message}\n\n{context_text}')]
   ```

2. **然后遍历历史消息时，可能再次添加 system message**
   ```python
   for item in messages[:-1]:
       if isinstance(item, dict):
           prompt_messages.append(Message(role=item['role'], content=item['content']))
   ```

3. **如果历史消息中包含 system role，就会导致重复**

## 修复方案

在遍历历史消息时，**过滤掉 system message**，只保留 user 和 assistant 消息：

```python
# 构建prompt：system message必须是第一个且只能有一个
prompt_messages = [Message(role=SYSTEM, content=f'{self.system_message}\n\n{context_text}')]

# 添加历史消息（排除system message，只保留user和assistant）
for item in messages[:-1]:  # 排除最后一个用户消息
    if isinstance(item, dict):
        role = item.get('role', '')
        # ✅ 只添加user和assistant消息，跳过system消息
        if role in ['user', 'assistant', USER, ASSISTANT]:
            prompt_messages.append(Message(role=role, content=item['content']))
    elif hasattr(item, 'role'):
        # ✅ 如果是Message对象，也跳过system消息
        if item.role in ['user', 'assistant', USER, ASSISTANT]:
            prompt_messages.append(item)

# 最后添加当前用户消息
prompt_messages.append(Message(role=USER, content=query))
```

## 关键改动

### 修改前
```python
for item in messages[:-1]:
    if isinstance(item, dict):
        prompt_messages.append(Message(role=item['role'], content=item['content']))
    else:
        prompt_messages.append(item)
```
❌ 无条件添加所有历史消息，包括可能的 system message

### 修改后
```python
for item in messages[:-1]:
    if isinstance(item, dict):
        role = item.get('role', '')
        # 只添加user和assistant消息，跳过system消息
        if role in ['user', 'assistant', USER, ASSISTANT]:
            prompt_messages.append(Message(role=role, content=item['content']))
    elif hasattr(item, 'role'):
        # 如果是Message对象，也跳过system消息
        if item.role in ['user', 'assistant', USER, ASSISTANT]:
            prompt_messages.append(item)
```
✅ 显式过滤，确保只有 user 和 assistant 消息被添加

## Prompt 结构

修复后的正确结构：
```
1. SYSTEM (唯一) - 包含系统指令和检索上下文
2. USER/ASSISTANT (交替) - 历史对话
3. USER (最后) - 当前问题
```

示例：
```
[SYSTEM] 你是一个知识库助手。请依据以下知识回答...
[USER] 什么是RAG?
[ASSISTANT] RAG是检索增强生成...
[USER] 它有什么优点?  ← 当前问题
```

## 测试验证

### 1. 单轮对话测试
```python
agent = KnowledgeAgent(...)
result = agent.answer("测试问题")
print(result['answer'])
```

### 2. 多轮对话测试
```python
# 第一轮
result1 = agent.answer("什么是RAG?")
print(result1['answer'])

# 第二轮（应该能记住上下文）
result2 = agent.answer("它有什么优点?")
print(result2['answer'])
```

### 3. Web界面测试
```bash
.venv\Scripts\python.exe app.py
```

在浏览器中：
1. 输入第一个问题 → 应该正常回答
2. 输入第二个问题（追问）→ 应该能理解上下文
3. 检查控制台无 400 错误

## 相关文件

- [qa_agent.py - _run()](file://c:\lhq\work\hyh_knowledge_lab\qa_agent.py#L86-L124) - 修复的核心方法

## 注意事项

### 1. Role 常量
Qwen-Agent 使用字符串常量：
- `USER` = 'user'
- `ASSISTANT` = 'assistant'  
- `SYSTEM` = 'system'

代码中同时检查字符串和常量，确保兼容性：
```python
if role in ['user', 'assistant', USER, ASSISTANT]:
```

### 2. 历史消息格式
历史消息可能是：
- **dict 格式**: `{'role': 'user', 'content': '...'}`
- **Message 对象**: `Message(role='user', content='...')`

代码都做了兼容处理。

### 3. 内部历史 vs 传入消息
- `self.history` - Agent 内部维护的对话历史
- `messages` 参数 - 调用时传入的消息列表

在 `_run` 中使用 `messages` 参数，确保使用最新的上下文。

## 为什么会出现这个问题？

可能的触发场景：

1. **Gradio 传递了完整的消息历史**
   - 包括之前的 system message
   - 导致重复

2. **多轮对话累积**
   - 每次调用都添加 system message
   - 没有清理旧的

3. **不同的调用路径**
   - `answer()` 和 `_run()` 可能有不同的消息构建逻辑
   - 导致不一致

## 预防措施

### 1. 始终验证 prompt 结构
```python
def validate_prompt(messages: List[Message]):
    system_count = sum(1 for m in messages if m.role == SYSTEM)
    assert system_count <= 1, f"Expected <= 1 system message, got {system_count}"
    if system_count == 1:
        assert messages[0].role == SYSTEM, "System message must be first"
```

### 2. 日志记录
```python
logger.debug(f"Prompt messages count: {len(prompt_messages)}")
logger.debug(f"Roles: {[m.role for m in prompt_messages]}")
```

### 3. 单元测试
```python
def test_no_duplicate_system():
    agent = KnowledgeAgent(...)
    messages = [
        {'role': 'system', 'content': '...'},  # 不应该被重复添加
        {'role': 'user', 'content': '问题1'},
        {'role': 'assistant', 'content': '回答1'},
        {'role': 'user', 'content': '问题2'},
    ]
    
    # 调用 _run 并验证
    # ...
```

## 相关错误码

| 错误码 | 含义 | 解决方法 |
|--------|------|----------|
| 400 - duplicate system | system message 重复 | 过滤历史中的 system |
| 400 - system not first | system 不在第一位 | 确保 system 是第一个 |
| 400 - empty messages | 消息列表为空 | 至少需要一个 user 消息 |

---

**修复日期**: 2026-04-23  
**影响范围**: 所有使用 `_run()` 方法的场景  
**严重程度**: 🔴 高（导致功能完全不可用）
