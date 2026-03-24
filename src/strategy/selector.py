"""持仓选择器模块"""
from typing import Dict, List, Optional
from dataclasses import dataclass
from src.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ETFScore:
    """ETF得分"""
    code: str
    name: str
    score: float
    return_20: float
    return_60: float
    above_ma: bool
    ma_value: float
    current_price: float


class PositionSelector:
    """持仓选择器"""

    def __init__(self, hold_count: int = 1, allow_cash: bool = True):
        """
        Args:
            hold_count: 持仓数量
            allow_cash: 是否允许空仓
        """
        self.hold_count = hold_count
        self.allow_cash = allow_cash

    def select_target_position(
        self,
        scores: Dict[str, Dict],
        trend_status: Dict[str, Dict],
        etf_names: Dict[str, str]
    ) -> Optional[str]:
        """
        选择目标持仓

        Args:
            scores: {symbol: {'score': float, 'return_20': float, 'return_60': float}}
            trend_status: {symbol: {'above_ma': bool, 'ma_value': float, 'current_price': float}}
            etf_names: {symbol: name}

        Returns:
            目标持仓代码，如果无合格标的则返回None
        """
        logger.info("Selecting target position")

        # 构建ETFScore列表
        etf_scores = []
        for symbol in scores.keys():
            score_data = scores[symbol]
            trend_data = trend_status.get(symbol, {})

            # 跳过无效数据
            if score_data['score'] is None:
                logger.warning(f"{symbol}: invalid score, skipping")
                continue

            etf_score = ETFScore(
                code=symbol,
                name=etf_names.get(symbol, symbol),
                score=score_data['score'],
                return_20=score_data['return_20'],
                return_60=score_data['return_60'],
                above_ma=trend_data.get('above_ma', False),
                ma_value=trend_data.get('ma_value'),
                current_price=trend_data.get('current_price')
            )
            etf_scores.append(etf_score)

        if not etf_scores:
            logger.warning("No valid ETF scores")
            return None

        # 按得分降序排序
        etf_scores.sort(key=lambda x: x.score, reverse=True)

        # 应用趋势过滤
        qualified_etfs = [etf for etf in etf_scores if etf.above_ma]

        if not qualified_etfs:
            logger.warning("No ETF passed trend filter")
            if self.allow_cash:
                logger.info("Moving to cash")
                return None
            else:
                # 如果不允许空仓，选择得分最高的（即使不满足趋势条件）
                logger.warning("Cash not allowed, selecting highest score ETF despite trend filter")
                target = etf_scores[0].code
                logger.info(f"Selected: {target} (score={etf_scores[0].score:.4f}, above_ma=False)")
                return target

        # 选择得分最高的合格ETF
        target = qualified_etfs[0]
        logger.info(f"Selected: {target.code} ({target.name}), score={target.score:.4f}, "
                   f"r20={target.return_20:.4f}, r60={target.return_60:.4f}")

        return target.code

    def get_all_scores(
        self,
        scores: Dict[str, Dict],
        trend_status: Dict[str, Dict],
        etf_names: Dict[str, str]
    ) -> List[ETFScore]:
        """
        获取所有ETF的得分列表（用于报告）

        Args:
            scores: 动量得分
            trend_status: 趋势状态
            etf_names: ETF名称映射

        Returns:
            ETFScore列表，按得分降序排序
        """
        etf_scores = []
        for symbol in scores.keys():
            score_data = scores[symbol]
            trend_data = trend_status.get(symbol, {})

            if score_data['score'] is None:
                continue

            etf_score = ETFScore(
                code=symbol,
                name=etf_names.get(symbol, symbol),
                score=score_data['score'],
                return_20=score_data['return_20'],
                return_60=score_data['return_60'],
                above_ma=trend_data.get('above_ma', False),
                ma_value=trend_data.get('ma_value'),
                current_price=trend_data.get('current_price')
            )
            etf_scores.append(etf_score)

        # 按得分降序排序
        etf_scores.sort(key=lambda x: x.score, reverse=True)
        return etf_scores
