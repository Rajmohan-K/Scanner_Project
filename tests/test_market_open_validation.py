import pandas as pd
from analysis.market_open_validation import build_market_open_validation


def test_build_market_open_validation_returns_expected_keys():
    index = pd.date_range(start='2026-06-07 09:08', periods=8, freq='min')
    df = pd.DataFrame(
        {
            'Open': [100, 101, 102, 103, 104, 105, 106, 107],
            'High': [101, 102, 103, 104, 105, 106, 107, 108],
            'Low': [99, 100, 101, 102, 103, 104, 105, 106],
            'Close': [101, 102, 103, 104, 105, 106, 107, 108],
            'Volume': [1000, 1200, 1100, 1300, 1400, 1500, 1600, 1700],
        },
        index=index,
    )

    quote_data = {
        'previous_close': 99.0,
        'open': 100.0,
        'current_price': 108.0,
        'current_volume': 2500,
        'premarket_price': 99.5,
        'premarket_volume': 1800,
    }

    result = build_market_open_validation(
        symbol='TEST',
        quote_data=quote_data,
        intraday_df=df,
        open_time='09:08',
        key_levels={'vwap': 102.0, 'ema20': 103.0},
    )

    assert isinstance(result, dict)
    assert result['symbol'] == 'TEST'
    assert 'gap_up_pct' in result
    assert 'order_flow_strength' in result
    assert 'final_trade_quality_score' in result
    assert 'opportunity_classification' in result
    assert result['current_price'] == 108.0
    assert isinstance(result['candidate_flags'], dict)
