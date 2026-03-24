__all__ = [
    "OrderCheckResult",
    "OrderChecker",
    "OrderRequest",
    "ExecutionResult",
    "RebalanceExecutor",
]


def __getattr__(name):
    if name in {"OrderCheckResult", "OrderChecker", "OrderRequest"}:
        from src.execution.checker import OrderCheckResult, OrderChecker, OrderRequest

        return {
            "OrderCheckResult": OrderCheckResult,
            "OrderChecker": OrderChecker,
            "OrderRequest": OrderRequest,
        }[name]

    if name in {"ExecutionResult", "RebalanceExecutor"}:
        from src.execution.executor import ExecutionResult, RebalanceExecutor

        return {
            "ExecutionResult": ExecutionResult,
            "RebalanceExecutor": RebalanceExecutor,
        }[name]

    raise AttributeError(f"module 'src.execution' has no attribute {name!r}")
