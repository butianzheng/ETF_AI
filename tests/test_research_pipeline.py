import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from scripts.run_research import _load_candidate_specs
from src.core.config import config_loader
from src.research_pipeline import run_research_pipeline
from src.storage.database import init_db
from src.storage.repositories import PriceRepository


def _seed_symbol(symbol: str, start_date: date, days: int, base: float, slope: float) -> None:
    rows = []
    for idx in range(days):
        current_date = start_date + timedelta(days=idx)
        if current_date.weekday() >= 5:
            continue
        close = round(base + slope * idx, 4)
        rows.append(
            {
                "trade_date": current_date,
                "open": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": 100000 + idx,
                "amount": close * (100000 + idx),
                "source": "test",
            }
        )
    repo = PriceRepository()
    try:
        repo.save_prices(symbol, pd.DataFrame(rows))
    finally:
        repo.close()


def _seed_research_db() -> None:
    init_db()
    start = date(2024, 12, 1)
    _seed_symbol("510300", start, 520, 4.0, 0.001)
    _seed_symbol("510500", start, 520, 3.5, 0.0045)
    _seed_symbol("159915", start, 520, 3.0, 0.0025)
    _seed_symbol("515180", start, 520, 2.8, 0.0018)


def test_research_pipeline_generates_outputs():
    _seed_research_db()
    result = run_research_pipeline(
        start_date=date(2025, 12, 1),
        end_date=date(2026, 3, 11),
        log_level="INFO",
    )
    assert result["comparison_rows"]
    assert {row["strategy_id"] for row in result["comparison_rows"]} == {"trend_momentum", "risk_adjusted_momentum"}
    assert {row["candidate_name"] for row in result["comparison_rows"]} == {"baseline_trend", "risk_adjusted_baseline"}
    assert result["research_output"].ranked_candidates
    assert Path(result["report_paths"]["markdown"]).exists()
    assert Path(result["report_paths"]["json"]).exists()
    assert Path(result["report_paths"]["csv"]).exists()


def test_research_pipeline_outputs_regime_analysis_sections():
    _seed_research_db()
    result = run_research_pipeline(
        start_date=date(2025, 12, 1),
        end_date=date(2026, 3, 11),
        log_level="INFO",
    )

    assert result["regime_daily_labels"]
    assert result["candidate_regime_metrics"]["baseline_trend"]["by_regime_metrics"]["risk_on"]["observation_count"] >= 0
    assert result["candidate_sample_split_metrics"]["baseline_trend"]["out_of_sample_metrics"]["observation_count"] > 0
    assert isinstance(result["candidate_regime_transition_metrics"]["baseline_trend"], list)

    payload = json.loads(Path(result["report_paths"]["json"]).read_text(encoding="utf-8"))
    assert "regime_config_snapshot" in payload
    assert "regime_daily_labels" in payload
    assert "candidate_regime_metrics" in payload
    assert "candidate_sample_split_metrics" in payload
    assert "candidate_regime_transition_metrics" in payload


def test_default_research_config_loaded():
    research_config = config_loader.load_research_config()
    assert research_config.candidates
    assert research_config.candidates[0].name == "baseline_trend"
    assert research_config.candidates[0].strategy_id == "trend_momentum"
    assert research_config.candidates[1].strategy_id == "risk_adjusted_momentum"


def test_load_candidate_specs_from_yaml(tmp_path):
    config_path = tmp_path / "research.yaml"
    config_path.write_text(
        """
research:
  candidates:
    - name: fast_rebalance
      strategy_id: risk_adjusted_momentum
      description: test candidate
      overrides:
        strategy_params:
          volatility_penalty_weight: 0.8
""".strip(),
        encoding="utf-8",
    )

    candidate_specs = _load_candidate_specs(str(config_path))

    assert candidate_specs == [
        {
            "name": "fast_rebalance",
            "strategy_id": "risk_adjusted_momentum",
            "description": "test candidate",
            "overrides": {"strategy_params": {"volatility_penalty_weight": 0.8}},
        }
    ]
