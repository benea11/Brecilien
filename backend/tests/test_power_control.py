from app.phy.power_control import solve_tx_power, ETSI_MAX_TX_POWER_DBM


def test_power_clipped_to_etsi_limit():
    result = solve_tx_power(
        path_loss_db=200.0,
        antenna_gain_db=0.0,
        noise_floor_dbm=-100.0,
        required_sinr_db=10.0,
        max_tx_power_dbm=ETSI_MAX_TX_POWER_DBM,
    )
    assert result.tx_power_dbm == ETSI_MAX_TX_POWER_DBM
    assert result.link_closed is False


def test_power_control_respects_lower_budget_cap():
    result = solve_tx_power(
        path_loss_db=80.0,
        antenna_gain_db=5.0,
        noise_floor_dbm=-100.0,
        required_sinr_db=5.0,
        max_tx_power_dbm=10.0,
    )
    assert result.tx_power_dbm <= 10.0


def test_easy_link_uses_less_than_max_power():
    result = solve_tx_power(
        path_loss_db=60.0,
        antenna_gain_db=10.0,
        noise_floor_dbm=-100.0,
        required_sinr_db=5.0,
        max_tx_power_dbm=ETSI_MAX_TX_POWER_DBM,
    )
    assert 0.0 <= result.tx_power_dbm < ETSI_MAX_TX_POWER_DBM
    assert result.link_closed is True
