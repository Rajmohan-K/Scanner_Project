from __future__ import annotations

from typing import Any
import pandas as pd

from ui.stock_data_service import build_rule_analysis

class CentralizedAnalysisEngine:
    @staticmethod
    def analyze(
        symbol: str,
        quote: dict[str, Any],
        historical: pd.DataFrame,
        intraday: pd.DataFrame,
        benchmark: pd.DataFrame | None = None,
    ) -> dict[str, Any]:
        """
        Consolidated analysis entry point. Wraps the single rule-based analysis implementation
        defined in stock_data_service to ensure all pages and background scanner tasks utilize
        exactly the same indicators, breakout calculations, and targets.
        """
        return build_rule_analysis(symbol, quote, historical, intraday, benchmark)

# Centralized singleton instance
centralized_analysis_engine = CentralizedAnalysisEngine()
