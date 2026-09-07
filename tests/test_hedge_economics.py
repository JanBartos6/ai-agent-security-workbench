from __future__ import annotations

from scripts.hedge_economics import (
    EXFIL_K8_RAW_STEADY,
    HEDGE_K8_RAW_STEADY,
    breakeven_exfil_survival,
    evaluate_hedge_scenario,
)


def test_steady_raw_values_match_public_predicate_weights() -> None:
    assert EXFIL_K8_RAW_STEADY == 128.0
    assert HEDGE_K8_RAW_STEADY == 32.0


def test_one_gpt_hedge_costs_about_quarter_public_point() -> None:
    scenario = evaluate_hedge_scenario(
        hedge_count=1,
        exfil_survival_prior=0.20,
        hedge_survival_prior=0.60,
    )

    assert scenario.public_gpt_row_loss == 0.48
    assert scenario.public_leaderboard_loss == 0.24


def test_confused_deputy_breakeven_requires_low_exfil_survival() -> None:
    assert breakeven_exfil_survival(hedge_survival_prior=0.60) == 0.15

    below = evaluate_hedge_scenario(
        hedge_count=1,
        exfil_survival_prior=0.10,
        hedge_survival_prior=0.60,
    )
    above = evaluate_hedge_scenario(
        hedge_count=1,
        exfil_survival_prior=0.20,
        hedge_survival_prior=0.60,
    )

    assert below.hedge_beats_exfil is True
    assert above.hedge_beats_exfil is False
