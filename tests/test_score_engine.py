import pytest
from scoring.score_engine import calculate_score


def test_calculate_score_produces_opportunity_fields():
    module_results = {
        'technical_analysis': {'score': 18},
        'momentum_analysis': {'score': 15},
        'volume_analysis': {'score': 12},
        'trend_analysis': {'score': 16},
        'breadth_analysis': {'score': 9},
        'sector_strength': {'score': 11},
    }

    score_data = calculate_score(module_results)

    assert 'final_score' in score_data
    assert 'final_opportunity_score' in score_data
    assert 'opportunity_classification' in score_data
    assert score_data['final_score'] != 0
    assert isinstance(score_data['final_opportunity_score'], float)
    assert score_data['opportunity_classification'] in [
        'Exceptional Opportunity',
        'High Probability',
        'Good Opportunity',
        'Watchlist',
        'Ignore',
    ]
