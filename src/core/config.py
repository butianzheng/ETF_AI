"""配置加载模块"""
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
import yaml
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.execution.trade_policy import TradePolicy


class ETFPoolItem(BaseModel):
    """ETF池配置项"""
    code: str
    name: str
    category: str
    enabled: bool = True


class ScoreFormulaConfig(BaseModel):
    """动量评分配置"""
    return_20_weight: float = 0.5
    return_60_weight: float = 0.5


class TrendFilterConfig(BaseModel):
    """趋势过滤配置"""
    enabled: bool = True
    ma_period: int = 120
    ma_type: str = "sma"


class DefensiveModeConfig(BaseModel):
    """防御模式配置"""
    enabled: bool = False
    defensive_etf: Optional[str] = None


class StrategyConfig(BaseModel):
    """策略配置"""
    name: str
    version: str
    rebalance_frequency: Literal["monthly", "biweekly"]
    hold_count: int
    trade_policy: TradePolicy
    score_formula: ScoreFormulaConfig
    trend_filter: TrendFilterConfig
    defensive_mode: DefensiveModeConfig
    allow_cash: bool = True

    @model_validator(mode="before")
    @classmethod
    def _normalize_trade_policy(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        trade_policy = dict(normalized.get("trade_policy") or {})
        frequency = trade_policy.get("rebalance_frequency") or normalized.get("rebalance_frequency") or "monthly"
        trade_policy["rebalance_frequency"] = frequency
        normalized["trade_policy"] = trade_policy
        normalized["rebalance_frequency"] = frequency
        return normalized


class AgentItemConfig(BaseModel):
    """单个Agent配置"""
    enabled: bool = True
    model: str = "gpt-4o-mini"
    temperature: float = 0.5
    max_tokens: int = 2000


class AgentConstraintsConfig(BaseModel):
    """Agent约束配置"""
    allow_agent_modify_production_strategy: bool = False
    allow_agent_execute_order: bool = False


class LLMConfig(BaseModel):
    """LLM配置"""
    provider: str = "openai"
    api_base: Optional[str] = None
    timeout: int = 30
    max_retries: int = 3


class AgentConfig(BaseModel):
    """Agent总配置"""
    data_qa: AgentItemConfig
    research: AgentItemConfig
    risk_monitor: AgentItemConfig
    report: AgentItemConfig
    constraints: AgentConstraintsConfig
    llm: LLMConfig


class ResearchCandidateConfig(BaseModel):
    """研究候选参数配置"""
    name: str
    strategy_id: str
    description: Optional[str] = None
    overrides: Dict[str, Any] = Field(default_factory=dict)


class ResearchConfig(BaseModel):
    """研究配置"""
    candidates: List[ResearchCandidateConfig] = Field(default_factory=list)


class Settings(BaseSettings):
    """环境变量配置"""
    model_config = SettingsConfigDict(
        env_file="config/.env",
        env_file_encoding="utf-8",
    )

    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    database_url: str = "sqlite:///data/db/etf_rotation.db"
    log_level: str = "INFO"
    environment: str = "development"


class ConfigLoader:
    """配置加载器"""

    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self._strategy_config: Optional[StrategyConfig] = None
        self._strategy_doc: Optional[Dict[str, Any]] = None
        self._production_strategy_id: Optional[str] = None
        self._etf_pool: Optional[List[ETFPoolItem]] = None
        self._agent_config: Optional[AgentConfig] = None
        self._research_config: Optional[ResearchConfig] = None
        self._settings: Optional[Settings] = None

    def _load_strategy_document(self) -> Dict[str, Any]:
        if self._strategy_doc is None:
            config_path = self.config_dir / "strategy.yaml"
            with open(config_path, "r", encoding="utf-8") as f:
                self._strategy_doc = yaml.safe_load(f)
        return self._strategy_doc

    def load_strategy_config(self) -> StrategyConfig:
        """加载策略配置"""
        if self._strategy_config is None:
            data = self._load_strategy_document()
            self._strategy_config = StrategyConfig(**data["strategy"])
        return self._strategy_config

    def load_production_strategy_id(self) -> str:
        """加载生产策略标识。"""
        if self._production_strategy_id is None:
            data = self._load_strategy_document()
            self._production_strategy_id = data.get("production_strategy_id") or self.load_strategy_config().name
        return self._production_strategy_id

    def load_etf_pool(self) -> List[ETFPoolItem]:
        """加载ETF池配置"""
        if self._etf_pool is None:
            config_path = self.config_dir / "etf_pool.yaml"
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            self._etf_pool = [ETFPoolItem(**item) for item in data["etf_pool"]]
        return self._etf_pool

    def load_agent_config(self) -> AgentConfig:
        """加载Agent配置"""
        if self._agent_config is None:
            config_path = self.config_dir / "agent.yaml"
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            merged_data = {
                **data["agents"],
                "constraints": data["constraints"],
                "llm": data["llm"],
            }
            self._agent_config = AgentConfig(**merged_data)
        return self._agent_config

    def load_settings(self) -> Settings:
        """加载环境变量配置"""
        if self._settings is None:
            self._settings = Settings()
        return self._settings

    def load_research_config(self) -> ResearchConfig:
        """加载研究配置"""
        if self._research_config is None:
            config_path = self.config_dir / "research.yaml"
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            self._research_config = ResearchConfig(**data["research"])
        return self._research_config

    def get_enabled_etf_codes(self) -> List[str]:
        """获取启用的ETF代码列表"""
        etf_pool = self.load_etf_pool()
        return [item.code for item in etf_pool if item.enabled]


# 全局配置加载器实例
config_loader = ConfigLoader()
