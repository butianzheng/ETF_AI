"""数据验证模块"""
from datetime import date
from typing import Dict, List, Optional
from dataclasses import dataclass
import pandas as pd
import numpy as np
from src.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DataIssue:
    """数据问题"""
    code: str
    issue_type: str  # missing_price, price_jump, volume_anomaly, missing_dates
    date: Optional[date]
    description: str
    severity: str  # low, medium, high


@dataclass
class ValidationResult:
    """验证结果"""
    status: str  # ok, warning, error
    issues: List[DataIssue]
    allow_strategy_run: bool
    summary: str


class DataValidator:
    """数据验证器"""

    def __init__(self, price_jump_threshold: float = 0.15):
        """
        Args:
            price_jump_threshold: 价格跳变阈值（默认15%）
        """
        self.price_jump_threshold = price_jump_threshold

    def validate_price_data(
        self,
        symbol: str,
        df: pd.DataFrame,
        required_days: int = 120
    ) -> ValidationResult:
        """
        验证单个ETF的价格数据

        Args:
            symbol: ETF代码
            df: 价格数据
            required_days: 需要的最少天数

        Returns:
            ValidationResult
        """
        logger.info(f"Validating price data for {symbol}")
        issues = []

        # 检查数据量
        if len(df) < required_days:
            issues.append(DataIssue(
                code=symbol,
                issue_type="insufficient_data",
                date=None,
                description=f"只有{len(df)}天数据，需要至少{required_days}天",
                severity="high"
            ))

        # 检查缺失值
        missing_issues = self._check_missing_values(symbol, df)
        issues.extend(missing_issues)

        # 检查价格跳变
        jump_issues = self._check_price_jumps(symbol, df)
        issues.extend(jump_issues)

        # 检查成交量异常
        volume_issues = self._check_volume_anomalies(symbol, df)
        issues.extend(volume_issues)

        # 判断状态
        high_severity_count = sum(1 for issue in issues if issue.severity == "high")
        medium_severity_count = sum(1 for issue in issues if issue.severity == "medium")

        if high_severity_count > 0:
            status = "error"
            allow_run = False
            summary = f"{symbol}: 发现{high_severity_count}个严重问题，不允许运行策略"
        elif medium_severity_count > 0:
            status = "warning"
            allow_run = True
            summary = f"{symbol}: 发现{medium_severity_count}个中等问题，可以运行但需注意"
        else:
            status = "ok"
            allow_run = True
            summary = f"{symbol}: 数据质量良好"

        logger.info(summary)
        return ValidationResult(
            status=status,
            issues=issues,
            allow_strategy_run=allow_run,
            summary=summary
        )

    def validate_multi_symbols(
        self,
        data_dict: Dict[str, pd.DataFrame],
        required_days: int = 120
    ) -> ValidationResult:
        """
        验证多个ETF的数据

        Args:
            data_dict: {symbol: DataFrame}
            required_days: 需要的最少天数

        Returns:
            ValidationResult
        """
        logger.info(f"Validating data for {len(data_dict)} symbols")
        all_issues = []
        error_count = 0

        for symbol, df in data_dict.items():
            result = self.validate_price_data(symbol, df, required_days)
            all_issues.extend(result.issues)
            if result.status == "error":
                error_count += 1

        # 综合判断
        if error_count > 0:
            status = "error"
            allow_run = False
            summary = f"发现{error_count}个ETF存在严重问题，不允许运行策略"
        elif len(all_issues) > 0:
            status = "warning"
            allow_run = True
            summary = f"发现{len(all_issues)}个问题，可以运行但需注意"
        else:
            status = "ok"
            allow_run = True
            summary = "所有ETF数据质量良好"

        logger.info(summary)
        return ValidationResult(
            status=status,
            issues=all_issues,
            allow_strategy_run=allow_run,
            summary=summary
        )

    def _check_missing_values(self, symbol: str, df: pd.DataFrame) -> List[DataIssue]:
        """检查缺失值"""
        issues = []

        for col in ['open', 'close', 'high', 'low']:
            if col in df.columns:
                missing_count = df[col].isna().sum()
                if missing_count > 0:
                    # 找到缺失的日期
                    missing_dates = df[df[col].isna()]['trade_date'].tolist()
                    issues.append(DataIssue(
                        code=symbol,
                        issue_type="missing_price",
                        date=missing_dates[0] if missing_dates else None,
                        description=f"{col}列有{missing_count}个缺失值",
                        severity="high"
                    ))

        return issues

    def _check_price_jumps(self, symbol: str, df: pd.DataFrame) -> List[DataIssue]:
        """检查价格异常跳变"""
        issues = []

        if 'close' not in df.columns or len(df) < 2:
            return issues

        # 计算日收益率
        returns = df['close'].pct_change()

        # 找出异常跳变
        abnormal_mask = np.abs(returns) > self.price_jump_threshold
        abnormal_indices = df[abnormal_mask].index

        for idx in abnormal_indices:
            if idx > 0:
                trade_date = df.loc[idx, 'trade_date']
                return_value = returns.loc[idx]
                issues.append(DataIssue(
                    code=symbol,
                    issue_type="price_jump",
                    date=trade_date,
                    description=f"价格跳变{return_value:.2%}，超过阈值{self.price_jump_threshold:.2%}",
                    severity="medium"
                ))

        return issues

    def _check_volume_anomalies(self, symbol: str, df: pd.DataFrame) -> List[DataIssue]:
        """检查成交量异常"""
        issues = []

        if 'volume' not in df.columns or len(df) < 10:
            return issues

        # 检查连续多日成交量为0
        zero_volume_mask = df['volume'] == 0
        if zero_volume_mask.sum() > len(df) * 0.1:  # 超过10%的天数成交量为0
            issues.append(DataIssue(
                code=symbol,
                issue_type="volume_anomaly",
                date=None,
                description=f"有{zero_volume_mask.sum()}天成交量为0，占比{zero_volume_mask.sum()/len(df):.1%}",
                severity="low"
            ))

        return issues
