"""评估指标模块 - 收集bad case和计算检索质量指标"""
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class EvaluationRecord:
    """评估记录"""
    query: str
    timestamp: str
    answer: str
    sources: List[str]
    relevance_score: Optional[float] = None  # 用户反馈的相关度(1-5)
    is_helpful: Optional[bool] = None  # 是否有用
    feedback: Optional[str] = None  # 用户反馈文本
    response_time_ms: Optional[float] = None  # 响应时间(毫秒)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Evaluator:
    """评估指标收集器"""
    
    def __init__(self, log_dir: str = 'eval_logs'):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 日志文件路径
        self.records_file = self.log_dir / 'evaluation_records.jsonl'
        self.bad_cases_file = self.log_dir / 'bad_cases.jsonl'
        self.metrics_file = self.log_dir / 'metrics_summary.json'
        
        # 内存中的统计
        self.total_queries = 0
        self.feedback_count = 0
        self.bad_case_count = 0
        self.response_times: List[float] = []
        
        logger.info(f'Evaluator initialized, logs saved to {self.log_dir}')
    
    def record_query(
        self,
        query: str,
        answer: str,
        sources: List[str],
        response_time_ms: Optional[float] = None,
    ) -> None:
        """记录查询"""
        record = EvaluationRecord(
            query=query,
            timestamp=datetime.now().isoformat(),
            answer=answer,
            sources=sources,
            response_time_ms=response_time_ms,
        )
        
        self._append_record(record)
        self.total_queries += 1
        
        if response_time_ms:
            self.response_times.append(response_time_ms)
    
    def collect_feedback(
        self,
        query: str,
        relevance_score: Optional[float] = None,
        is_helpful: Optional[bool] = None,
        feedback: Optional[str] = None,
    ) -> None:
        """收集用户反馈"""
        # 查找最近的匹配记录
        records = self._load_records()
        for record in reversed(records):
            if record.query == query:
                record.relevance_score = relevance_score
                record.is_helpful = is_helpful
                record.feedback = feedback
                
                # 更新记录
                self._save_all_records(records)
                self.feedback_count += 1
                
                # 如果是bad case (低分或无用)
                if (relevance_score and relevance_score <= 2) or (is_helpful is False):
                    self._record_bad_case(record)
                
                logger.info(f'Feedback collected for query: {query[:50]}...')
                break
    
    def _record_bad_case(self, record: EvaluationRecord) -> None:
        """记录bad case"""
        bad_case = {
            **record.to_dict(),
            'recorded_at': datetime.now().isoformat(),
        }
        
        with open(self.bad_cases_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(bad_case, ensure_ascii=False) + '\n')
        
        self.bad_case_count += 1
        logger.warning(f'Bad case recorded: {record.query[:50]}...')
    
    def calculate_metrics(self) -> Dict[str, Any]:
        """计算评估指标"""
        records = self._load_records()
        
        # 基础统计
        metrics = {
            'total_queries': self.total_queries,
            'feedback_count': self.feedback_count,
            'bad_case_count': self.bad_case_count,
            'feedback_rate': f'{(self.feedback_count / self.total_queries * 100) if self.total_queries > 0 else 0:.2f}%',
            'bad_case_rate': f'{(self.bad_case_count / self.feedback_count * 100) if self.feedback_count > 0 else 0:.2f}%',
        }
        
        # 响应时间统计
        if self.response_times:
            metrics['avg_response_time_ms'] = sum(self.response_times) / len(self.response_times)
            metrics['min_response_time_ms'] = min(self.response_times)
            metrics['max_response_time_ms'] = max(self.response_times)
        
        # 相关度统计
        scored_records = [r for r in records if r.relevance_score is not None]
        if scored_records:
            scores = [r.relevance_score for r in scored_records]
            metrics['avg_relevance_score'] = sum(scores) / len(scores)
            metrics['score_distribution'] = {
                '5_stars': len([s for s in scores if s == 5]),
                '4_stars': len([s for s in scores if s == 4]),
                '3_stars': len([s for s in scores if s == 3]),
                '2_stars': len([s for s in scores if s == 2]),
                '1_star': len([s for s in scores if s == 1]),
            }
        
        # 有用性统计
        helpful_records = [r for r in records if r.is_helpful is not None]
        if helpful_records:
            helpful_count = len([r for r in helpful_records if r.is_helpful])
            metrics['helpful_rate'] = f'{(helpful_count / len(helpful_records) * 100):.2f}%'
        
        # 保存指标
        with open(self.metrics_file, 'w', encoding='utf-8') as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2)
        
        return metrics
    
    def get_bad_cases(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取bad cases列表"""
        if not self.bad_cases_file.exists():
            return []
        
        cases = []
        with open(self.bad_cases_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    cases.append(json.loads(line))
        
        return cases[-limit:]  # 返回最近的limit条
    
    def export_records(self, output_file: str = 'exported_records.json') -> str:
        """导出所有记录"""
        records = self._load_records()
        output_path = self.log_dir / output_file
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump([r.to_dict() for r in records], f, ensure_ascii=False, indent=2)
        
        logger.info(f'Records exported to {output_path}')
        return str(output_path)
    
    def _append_record(self, record: EvaluationRecord) -> None:
        """追加记录到文件"""
        with open(self.records_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record.to_dict(), ensure_ascii=False) + '\n')
    
    def _load_records(self) -> List[EvaluationRecord]:
        """加载所有记录"""
        if not self.records_file.exists():
            return []
        
        records = []
        with open(self.records_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    records.append(EvaluationRecord(**data))
        
        return records
    
    def _save_all_records(self, records: List[EvaluationRecord]) -> None:
        """保存所有记录"""
        with open(self.records_file, 'w', encoding='utf-8') as f:
            for record in records:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + '\n')
    
    def clear(self) -> None:
        """清空所有评估数据"""
        if self.records_file.exists():
            self.records_file.unlink()
        if self.bad_cases_file.exists():
            self.bad_cases_file.unlink()
        if self.metrics_file.exists():
            self.metrics_file.unlink()
        
        self.total_queries = 0
        self.feedback_count = 0
        self.bad_case_count = 0
        self.response_times.clear()
        
        logger.info('All evaluation data cleared')
