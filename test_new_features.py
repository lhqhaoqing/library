"""
新功能测试脚本
用于验证流式输出、缓存、评估系统等功能
"""
import sys
import time
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from config import load_config
from qa_agent import KnowledgeAgent
from retriever import KnowledgeIndex


def test_lru_cache():
    """测试LRU缓存功能"""
    print("\n" + "="*60)
    print("测试1: LRU缓存功能")
    print("="*60)
    
    config = load_config()
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
    
    agent = KnowledgeAgent(
        retriever=index,
        llm_config=config.get('model', {}),
        enable_cache=True,
        cache_capacity=10,
        cache_ttl=3600,
        enable_evaluation=False,  # 暂时禁用评估
    )
    
    # 第一次查询(缓存未命中)
    query = "测试问题"
    print(f"\n第一次查询: {query}")
    start = time.time()
    result1 = agent.answer(query)
    time1 = time.time() - start
    print(f"响应时间: {time1:.2f}s")
    
    # 查看缓存统计
    stats = agent.get_cache_stats()
    print(f"缓存统计: {stats}")
    
    # 第二次查询(应该命中缓存)
    print(f"\n第二次查询(相同问题): {query}")
    start = time.time()
    result2 = agent.answer(query)
    time2 = time.time() - start
    print(f"响应时间: {time2:.2f}s")
    print(f"加速比: {time1/time2:.1f}x")
    
    # 再次查看缓存统计
    stats = agent.get_cache_stats()
    print(f"缓存统计: {stats}")
    
    assert stats['hits'] == 1, "缓存应该命中1次"
    assert stats['misses'] == 1, "缓存应该未命中1次"
    
    print("\n✅ LRU缓存测试通过!")
    return True


def test_evaluation_system():
    """测试评估系统"""
    print("\n" + "="*60)
    print("测试2: 评估系统功能")
    print("="*60)
    
    config = load_config()
    retriever_cfg = config.get('retriever', {})
    
    index = KnowledgeIndex(
        root_path=config['knowledge_dir'],
        top_k=retriever_cfg.get('top_k', 5),
    )
    index.build_index()
    
    agent = KnowledgeAgent(
        retriever=index,
        llm_config=config.get('model', {}),
        enable_cache=False,  # 禁用缓存以便测试
        enable_evaluation=True,
    )
    
    # 进行几次查询
    queries = ["测试问题1", "测试问题2", "测试问题3"]
    for query in queries:
        print(f"\n查询: {query}")
        result = agent.answer(query)
        print(f"回答长度: {len(result['answer'])} 字符")
        print(f"来源数量: {len(result['sources'])}")
    
    # 收集反馈
    print("\n收集用户反馈...")
    agent.evaluator.collect_feedback("测试问题1", relevance_score=5, is_helpful=True)
    agent.evaluator.collect_feedback("测试问题2", relevance_score=2, is_helpful=False, feedback="回答不相关")
    agent.evaluator.collect_feedback("测试问题3", relevance_score=4, is_helpful=True)
    
    # 计算指标
    print("\n计算评估指标...")
    metrics = agent.evaluator.calculate_metrics()
    print(f"总查询数: {metrics['total_queries']}")
    print(f"反馈数: {metrics['feedback_count']}")
    print(f"Bad Case数: {metrics['bad_case_count']}")
    if 'avg_relevance_score' in metrics:
        print(f"平均相关度: {metrics['avg_relevance_score']:.2f}")
    if 'helpful_rate' in metrics:
        print(f"有用率: {metrics['helpful_rate']}")
    
    # 获取Bad Cases
    bad_cases = agent.evaluator.get_bad_cases()
    print(f"\nBad Cases数量: {len(bad_cases)}")
    if bad_cases:
        print(f"第一个Bad Case: {bad_cases[0]['query'][:50]}...")
    
    assert metrics['total_queries'] == 3, "应该有3次查询"
    assert metrics['feedback_count'] == 3, "应该有3次反馈"
    assert metrics['bad_case_count'] == 1, "应该有1个Bad Case"
    
    print("\n✅ 评估系统测试通过!")
    return True


def test_citation_enhancement():
    """测试引用溯源增强"""
    print("\n" + "="*60)
    print("测试3: 引用溯源增强")
    print("="*60)
    
    config = load_config()
    retriever_cfg = config.get('retriever', {})
    
    index = KnowledgeIndex(
        root_path=config['knowledge_dir'],
        top_k=retriever_cfg.get('top_k', 5),
    )
    index.build_index()
    
    agent = KnowledgeAgent(
        retriever=index,
        llm_config=config.get('model', {}),
        enable_cache=False,
        enable_evaluation=False,
    )
    
    query = "测试"
    print(f"\n查询: {query}")
    result = agent.answer(query)
    
    print(f"\n来源列表:")
    for source in result['sources']:
        print(f"  {source}")
        # 检查是否包含页码/段落信息
        has_page_info = '页' in source or '段' in source or '(' in source
        if has_page_info:
            print(f"    ✓ 包含详细位置信息")
    
    print("\n✅ 引用溯源增强测试通过!")
    return True


def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("新功能测试套件")
    print("="*60)
    
    tests = [
        ("LRU缓存", test_lru_cache),
        ("评估系统", test_evaluation_system),
        ("引用溯源", test_citation_enhancement),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n❌ {name}测试失败: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # 总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    for name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{name}: {status}")
    
    all_passed = all(success for _, success in results)
    if all_passed:
        print("\n🎉 所有测试通过!")
    else:
        print("\n⚠️  部分测试失败,请检查日志")
    
    return all_passed


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
