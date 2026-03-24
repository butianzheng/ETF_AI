"""Agent 基类与通用工具。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
import json
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.agents.llm_client import LLMClient
from src.core.config import config_loader
from src.core.logger import get_logger
from src.storage.repositories import AgentLogRepository

logger = get_logger(__name__)


def _to_jsonable(value: Any) -> Any:
    """将常见 Python 对象转换为可审计的 JSON 结构。"""
    if isinstance(value, BaseModel):
        return _to_jsonable(value.model_dump())
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return value


class AgentInput(BaseModel):
    """所有 Agent 输入的基类。"""

    model_config = ConfigDict(extra="allow")


class AgentOutput(BaseModel):
    """所有 Agent 输出的基类。"""

    model_config = ConfigDict(extra="allow")

    status: str
    message: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)
    source: str = "fallback"


class BaseAgent(ABC):
    """统一封装提示词、LLM 调用、离线回退和日志记录。"""

    def __init__(self, name: str):
        self.name = name
        self.logger = get_logger(name)
        agent_cfg = config_loader.load_agent_config()
        llm_cfg = agent_cfg.llm
        self.agent_cfg = getattr(agent_cfg, name)
        self.constraints = agent_cfg.constraints
        self.llm = LLMClient(
            provider=llm_cfg.provider,
            api_key=None,
            api_base=llm_cfg.api_base,
            timeout=llm_cfg.timeout,
            max_retries=llm_cfg.max_retries,
        )

    @abstractmethod
    def prepare_prompt(self, input_data: AgentInput) -> str:
        """将结构化输入转为提示词。"""

    @abstractmethod
    def parse_output(self, raw_output: str) -> AgentOutput:
        """将 LLM 输出解析为结构化结果。"""

    @abstractmethod
    def fallback_output(self, input_data: AgentInput) -> AgentOutput:
        """无 LLM 或 LLM 失败时的本地回退逻辑。"""

    def _extract_json(self, raw_output: str) -> Dict[str, Any]:
        content = raw_output.strip()
        if "```json" in content:
            content = content.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in content:
            content = content.split("```", 1)[1].split("```", 1)[0].strip()
        return json.loads(content)

    def _log_execution(self, input_data: AgentInput, output: AgentOutput) -> None:
        repo = AgentLogRepository()
        try:
            repo.add_log(
                name=self.name,
                input_summary=_to_jsonable(input_data),
                output_text=json.dumps(_to_jsonable(output), ensure_ascii=False),
                status=output.status,
            )
        except Exception as exc:
            self.logger.warning(f"Failed to persist agent log: {exc}")
        finally:
            repo.close()

    def run(self, input_data: AgentInput) -> AgentOutput:
        """默认优先走 LLM，失败时自动退回本地规则。"""
        try:
            if self.agent_cfg.enabled and self.llm.is_available():
                prompt = self.prepare_prompt(input_data)
                raw = self.llm.call(
                    messages=[{"role": "user", "content": prompt}],
                    model=self.agent_cfg.model,
                    temperature=self.agent_cfg.temperature,
                    max_tokens=self.agent_cfg.max_tokens,
                )
                output = self.parse_output(raw)
                output.source = "llm"
            else:
                output = self.fallback_output(input_data)
        except Exception as exc:
            self.logger.warning(f"Agent {self.name} fallback due to error: {exc}")
            output = self.fallback_output(input_data)
            output.message = str(exc)
            output.source = "fallback"

        self._log_execution(input_data, output)
        self.logger.info(f"Agent {self.name} completed with status {output.status} via {output.source}")
        return output
