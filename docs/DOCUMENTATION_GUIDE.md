# 文档管理规范

## 📁 文档存放位置

**所有项目文档统一存放在 `docs/` 目录下**

```
docs/
├── README.md                    # 项目说明(根目录)
├── 需求文档.md                  # 产品需求文档
├── OPTIMIZATION_SUMMARY.md      # 优化总结
├── NEW_FEATURES.md              # 新功能说明
├── FINAL_SUMMARY.md             # 完整优化总结
├── BUGFIX_STREAMING.md          # Bug修复说明
├── FIX_SYSTEM_MESSAGE.md        # System Message问题修复
├── FIX_NAMEERROR_SOURCES.md     # NameError问题修复
└── image/                       # 图片资源
    └── 需求文档/
```

## 📝 文档分类

### 1. 需求与设计
- `需求文档.md` - 产品需求、功能设计
- 未来可添加: `架构设计.md`, `API文档.md`

### 2. 优化与改进
- `OPTIMIZATION_SUMMARY.md` - 第一批优化(高/中优先级)
- `NEW_FEATURES.md` - 第二批优化(低优先级/新功能)
- `FINAL_SUMMARY.md` - 完整优化总结报告

### 3. Bug修复
- `BUGFIX_STREAMING.md` - 流式输出问题修复
- `FIX_SYSTEM_MESSAGE.md` - System Message重复问题
- `FIX_NAMEERROR_SOURCES.md` - NameError变量未定义问题

### 4. 测试与验证
- 测试脚本放在根目录: `test_*.py`
- 测试结果可以放在 `docs/test_results/` (待创建)

### 5. 用户指南
- `README.md` (根目录) - 快速开始
- 未来可添加: `用户手册.md`, `FAQ.md`

## ✍️ 文档命名规范

### 英文文档
- 使用 **UPPER_CASE** 或 **snake_case**
- 示例: `OPTIMIZATION_SUMMARY.md`, `api_guide.md`

### 中文文档
- 直接使用中文名称
- 示例: `需求文档.md`, `用户手册.md`

### Bug修复文档
- 格式: `FIX_[问题简述].md` 或 `BUGFIX_[功能模块].md`
- 示例: `FIX_SYSTEM_MESSAGE.md`, `BUGFIX_STREAMING.md`

### 版本/阶段文档
- 格式: `[阶段]_SUMMARY.md` 或 `[版本]_RELEASE.md`
- 示例: `FINAL_SUMMARY.md`, `v2.0_RELEASE.md`

## 📋 文档内容模板

### Bug修复文档模板
```markdown
# [问题标题]

## 错误信息
[粘贴完整的错误信息]

## 问题原因
[详细描述问题的根本原因]

## 修复方案
[具体的修复步骤和代码改动]

## 测试验证
[如何验证修复是否成功]

## 相关文件
- [文件路径](链接)

## 预防措施
[如何避免类似问题再次发生]
```

### 功能说明文档模板
```markdown
# [功能名称]

## 功能描述
[简要说明功能用途]

## 技术实现
[核心技术方案和关键代码]

## 配置说明
[如何启用/配置该功能]

## 使用示例
[代码示例或使用步骤]

## 性能影响
[对系统性能的影响评估]

## 注意事项
[使用时需要注意的事项]
```

### 优化总结文档模板
```markdown
# [优化阶段]总结

## 优化概览
[表格列出所有优化项]

## 详细说明
[逐项说明优化内容]

## 性能对比
[优化前后的数据对比]

## 配置调整
[相关的配置变更]

## 后续计划
[下一步优化方向]
```

## 🔧 文档维护

### 新增文档
1. 确定文档类型(需求/优化/Bug修复/指南)
2. 选择合适的命名
3. 在 `docs/` 目录下创建
4. 更新本文档的索引(如有必要)

### 更新文档
1. 保持文档版本一致性
2. 在文档开头添加"最后更新日期"
3. 重大变更时添加"变更历史"章节

### 归档文档
1. 过时的文档移动到 `docs/archive/`
2. 在文件名前添加日期: `2024-01-OLD_DOC.md`
3. 在 README 中说明归档原因

## 🚫 禁止事项

### ❌ 不要在根目录创建 .md 文档
```
❌ README_new.md
❌ CHANGELOG.md
❌ my_notes.md

✅ docs/README_new.md
✅ docs/CHANGELOG.md
✅ docs/my_notes.md
```

### ❌ 不要使用模糊的文件名
```
❌ temp.md
❌ test.md
❌ note.md

✅ docs/临时测试记录_20240423.md
✅ docs/API测试报告_v1.0.md
✅ docs/会议记录_20240423.md
```

### ❌ 不要提交敏感信息
- API Keys
- 密码
- 内部地址
- 客户数据

## 📊 文档统计

当前文档数量: **7个**
- 优化总结: 3个
- Bug修复: 3个
- 需求文档: 1个

建议定期清理:
- 合并相似的文档
- 归档过时的内容
- 更新失效的链接

## 🔗 相关资源

- [项目README](../README.md)
- [需求文档](需求文档.md)
- [完整优化总结](FINAL_SUMMARY.md)

---

**最后更新**: 2026-04-23  
**维护者**: AI开发团队  
**版本**: 1.0
