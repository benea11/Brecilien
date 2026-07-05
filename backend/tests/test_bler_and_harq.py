import numpy as np

from app.phy.mcs_table import get_mcs
from app.linklevel.bler_curves import build_bler_curve
from app.harq.incremental_redundancy import simulate_harq


def test_bler_monotonically_decreasing_in_mi():
    mcs = get_mcs("2")
    curve = build_bler_curve(mcs, coded_block_bits=736)
    mis = np.linspace(0.0, curve.cap_mi, 20)
    blers = [curve.bler_from_mi(m) for m in mis]
    assert all(b1 >= b2 for b1, b2 in zip(blers, blers[1:]))


def test_bler_near_zero_at_cap_for_all_mcs():
    for key in ("0", "2", "4"):
        mcs = get_mcs(key)
        curve = build_bler_curve(mcs, coded_block_bits=736)
        assert curve.bler_from_mi(curve.cap_mi) < 1e-3


def test_high_sinr_gives_near_certain_single_round_success():
    mcs = get_mcs("2")
    curve = build_bler_curve(mcs, coded_block_bits=736)
    rng = np.random.default_rng(0)
    successes = 0
    trials = 300
    for _ in range(trials):
        outcome = simulate_harq(
            rng,
            model="uma",
            los=True,
            avg_sinr_linear=10 ** (35.0 / 10.0),
            bits_per_symbol=mcs.bits_per_symbol,
            num_subcarriers=54,
            subcarrier_spacing_hz=27_000,
            bler_curve=curve,
            max_extra_rounds=2,
        )
        successes += outcome.success
    assert successes / trials > 0.95


def test_harq_extra_rounds_improve_pdr_at_marginal_sinr():
    mcs = get_mcs("2")
    curve = build_bler_curve(mcs, coded_block_bits=736)

    def pdr(max_extra_rounds: int, seed: int) -> float:
        rng = np.random.default_rng(seed)
        trials = 800
        successes = 0
        for _ in range(trials):
            outcome = simulate_harq(
                rng,
                model="uma",
                los=False,
                avg_sinr_linear=10 ** (curve.center_sinr_db / 10.0),
                bits_per_symbol=mcs.bits_per_symbol,
                num_subcarriers=54,
                subcarrier_spacing_hz=27_000,
                bler_curve=curve,
                max_extra_rounds=max_extra_rounds,
            )
            successes += outcome.success
        return successes / trials

    pdr_no_harq = pdr(0, seed=1)
    pdr_with_harq = pdr(4, seed=1)
    assert pdr_with_harq >= pdr_no_harq
