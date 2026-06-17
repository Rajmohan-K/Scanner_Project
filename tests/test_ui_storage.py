import os
from ui.storage import save_strategy, load_strategy, list_strategies, delete_strategy


def test_strategy_persistence_cycle():
    payload = {
        'name': 'Unit Test Strategy',
        'description': 'Simple persistence check',
        'horizon': 'Intraday',
        'conditions': [{'indicator': 'RSI', 'operator': '<', 'value': 30}],
    }

    strategy_id = save_strategy(payload)
    assert strategy_id

    strategy = load_strategy(strategy_id)
    assert strategy is not None
    assert strategy.get('name') == 'Unit Test Strategy'

    strategies = list_strategies(limit=10)
    assert any(item['strategy_id'] == strategy_id for item in strategies)

    deleted = delete_strategy(strategy_id)
    assert deleted

    missing = load_strategy(strategy_id)
    assert missing is None
