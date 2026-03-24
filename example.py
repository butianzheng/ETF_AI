"""
ETF动量轮动策略系统 - 示例脚本

演示如何使用已实现的模块
"""
from datetime import date, datetime, timedelta
from src.core.config import config_loader
from src.core.logger import setup_logger, get_logger
from src.data.fetcher import DataFetcher
from src.data.normalizer import DataNormalizer
from src.data.validator import DataValidator
from src.strategy.engine import StrategyEngine

# 设置日志
setup_logger(log_level="INFO")
logger = get_logger(__name__)


def example_usage():
    """示例：完整的策略运行流程"""

    logger.info("=" * 60)
    logger.info("ETF动量轮动策略系统 - 示例运行")
    logger.info("=" * 60)

    # 1. 加载配置
    logger.info("\n[1] 加载配置...")
    strategy_config = config_loader.load_strategy_config()
    etf_pool = config_loader.load_etf_pool()

    logger.info(f"策略: {strategy_config.name} v{strategy_config.version}")
    logger.info(f"ETF池: {len(etf_pool)}只")
    for etf in etf_pool:
        logger.info(f"  - {etf.code}: {etf.name} ({etf.category})")

    # 2. 获取数据
    logger.info("\n[2] 获取ETF数据...")
    fetcher = DataFetcher()
    normalizer = DataNormalizer()

    # 计算日期范围（最近180天）
    end_date = date.today()
    start_date = end_date - timedelta(days=180)

    price_data = {}
    etf_names = {}

    for etf in etf_pool:
        if not etf.enabled:
            continue

        try:
            logger.info(f"获取 {etf.code} ({etf.name}) 数据...")

            # 获取数据
            df = fetcher.fetch_etf_daily(
                symbol=etf.code,
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d")
            )

            # 标准化
            df = normalizer.normalize_price_data(df)
            df = normalizer.remove_duplicates(df)

            price_data[etf.code] = df
            etf_names[etf.code] = etf.name

            logger.info(f"  获取到 {len(df)} 条记录")

        except Exception as e:
            logger.error(f"获取 {etf.code} 数据失败: {e}")

    if not price_data:
        logger.error("没有获取到任何数据，退出")
        return

    # 3. 数据验证
    logger.info("\n[3] 验证数据质量...")
    validator = DataValidator()
    validation_result = validator.validate_multi_symbols(price_data, required_days=120)

    logger.info(f"验证状态: {validation_result.status}")
    logger.info(f"允许运行策略: {validation_result.allow_strategy_run}")
    logger.info(f"总结: {validation_result.summary}")

    if validation_result.issues:
        logger.warning(f"发现 {len(validation_result.issues)} 个问题:")
        for issue in validation_result.issues[:5]:  # 只显示前5个
            logger.warning(f"  - {issue.code}: {issue.description} (严重程度: {issue.severity})")

    if not validation_result.allow_strategy_run:
        logger.error("数据质量不合格，无法运行策略")
        return

    # 4. 运行策略
    logger.info("\n[4] 运行策略引擎...")
    engine = StrategyEngine(config=strategy_config, etf_names=etf_names)

    # 假设当前持仓为空
    current_position = None
    trade_date = end_date

    result = engine.run(
        trade_date=trade_date,
        price_data=price_data,
        current_position=current_position
    )

    # 5. 输出结果
    logger.info("\n[5] 策略结果:")
    logger.info("=" * 60)
    logger.info(f"日期: {result.trade_date}")
    logger.info(f"策略版本: {result.strategy_version}")
    logger.info(f"当前持仓: {result.current_position or '空仓'}")
    logger.info(f"目标持仓: {result.target_position or '空仓'}")
    logger.info(f"是否调仓: {'是' if result.rebalance else '否'}")

    signal = engine.generate_signal_description(result)
    logger.info(f"信号: {signal}")

    logger.info("\nETF得分排名:")
    logger.info("-" * 60)
    logger.info(f"{'代码':<10} {'名称':<15} {'得分':<10} {'20日':<10} {'60日':<10} {'趋势':<8}")
    logger.info("-" * 60)

    for score in result.scores:
        trend_status = "✓" if score.above_ma else "✗"
        logger.info(
            f"{score.code:<10} {score.name:<15} "
            f"{score.score:>8.4f}  {score.return_20:>8.2%}  "
            f"{score.return_60:>8.2%}  {trend_status:<8}"
        )

    logger.info("=" * 60)
    logger.info("示例运行完成")


if __name__ == "__main__":
    try:
        example_usage()
    except Exception as e:
        logger.error(f"运行失败: {e}", exc_info=True)
