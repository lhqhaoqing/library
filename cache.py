"""LRU缓存模块 - 用于缓存热门查询结果"""
import logging
import time
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class LRUCache:
    """线程安全的LRU缓存实现"""
    
    def __init__(self, capacity: int = 100, ttl: int = 3600):
        """
        初始化LRU缓存
        
        Args:
            capacity: 缓存容量(最大条目数)
            ttl: 过期时间(秒),默认1小时
        """
        self.capacity = capacity
        self.ttl = ttl
        self.cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()
        self.hits = 0
        self.misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        if key not in self.cache:
            self.misses += 1
            return None
        
        value, timestamp = self.cache[key]
        
        # 检查是否过期
        if time.time() - timestamp > self.ttl:
            del self.cache[key]
            self.misses += 1
            logger.debug(f'Cache expired for key: {key[:50]}...')
            return None
        
        # 移动到末尾(最近使用)
        self.cache.move_to_end(key)
        self.hits += 1
        logger.debug(f'Cache hit for key: {key[:50]}...')
        return value
    
    def put(self, key: str, value: Any) -> None:
        """设置缓存值"""
        if key in self.cache:
            # 更新现有键,移动到末尾
            self.cache.move_to_end(key)
        elif len(self.cache) >= self.capacity:
            # 移除最久未使用的项
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
            logger.debug(f'Cache evicted oldest key: {oldest_key[:50]}...')
        
        self.cache[key] = (value, time.time())
        logger.debug(f'Cache stored key: {key[:50]}...')
    
    def clear(self) -> None:
        """清空缓存"""
        self.cache.clear()
        logger.info('Cache cleared')
    
    def size(self) -> int:
        """返回当前缓存大小"""
        return len(self.cache)
    
    def stats(self) -> Dict[str, Any]:
        """返回缓存统计信息"""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        return {
            'size': len(self.cache),
            'capacity': self.capacity,
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': f'{hit_rate:.2f}%',
            'ttl': self.ttl,
        }
    
    def cleanup_expired(self) -> int:
        """清理过期条目,返回清理数量"""
        now = time.time()
        expired_keys = [
            key for key, (_, timestamp) in self.cache.items()
            if now - timestamp > self.ttl
        ]
        for key in expired_keys:
            del self.cache[key]
        
        if expired_keys:
            logger.info(f'Cleaned up {len(expired_keys)} expired cache entries')
        
        return len(expired_keys)
