"""
快速测试脚本 - 验证问答功能是否正常
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import load_config
from qa_agent import KnowledgeAgent
from retriever import KnowledgeIndex


def test_basic_qa():
    """测试基本问答功能"""
    print("="*60)
    print("测试基本问答功能")
    print("="*60)
    
    try:
        # 加载配置
        config = load_config()
        print(f"✓ 配置加载成功")
        print(f"  知识库目录: {config['knowledge_dir']}")
        
        # 初始化检索器
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
        print(f"✓ 检索器初始化成功")
        
        # 构建索引
        print("正在构建索引...")
        index.build_index()
        print(f"✓ 索引构建完成,共 {len(index.chunks)} 个chunks")
        
        # 初始化Agent
        cache_cfg = config.get('cache', {})
        evaluation_cfg = config.get('evaluation', {})
        
        agent = KnowledgeAgent(
            retriever=index,
            llm_config=config.get('model', {}),
            enable_cache=cache_cfg.get('enabled', True),
            cache_capacity=cache_cfg.get('capacity', 100),
            cache_ttl=cache_cfg.get('ttl', 3600),
            enable_evaluation=evaluation_cfg.get('enabled', True),
        )
        print(f"✓ Agent初始化成功")
        
        # 测试查询
        test_queries = [
            "测试",
            "你好",
        ]
        
        for query in test_queries:
            print(f"\n{'-'*60}")
            print(f"查询: {query}")
            print(f"{'-'*60}")
            
            result = agent.answer(query)
            print(f"回答长度: {len(result['answer'])} 字符")
            print(f"来源数量: {len(result['sources'])}")
            
            if result['sources']:
                print("\n来源:")
                for source in result['sources'][:3]:  # 只显示前3个
                    print(f"  {source}")
            
            # 检查缓存
            if agent.cache:
                stats = agent.get_cache_stats()
                print(f"\n缓存统计: 命中率={stats['hit_rate']}, 大小={stats['size']}")
        
        print("\n" + "="*60)
        print("✅ 所有测试通过!")
        print("="*60)
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = test_basic_qa()
    sys.exit(0 if success else 1)
