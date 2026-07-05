from app.propagation.diffraction import excess_diffraction_loss_db, MAX_DIFFRACTION_LOSS_DB
from app.propagation.los import Obstruction


def test_no_obstructions_no_loss():
    assert excess_diffraction_loss_db(500, 10, 3, [], 1.9e9) == 0.0


def test_obstruction_adds_loss():
    obs = [Obstruction(building_id="b1", distance_along_path_m=250, height_m=25)]
    loss = excess_diffraction_loss_db(500, 10, 3, obs, 1.9e9)
    assert loss > 0.0


def test_loss_is_capped():
    obs = [
        Obstruction(building_id=f"b{i}", distance_along_path_m=d, height_m=50)
        for i, d in enumerate([50, 100, 150, 200, 250, 300, 350, 400])
    ]
    loss = excess_diffraction_loss_db(500, 10, 3, obs, 1.9e9)
    assert 0.0 <= loss <= MAX_DIFFRACTION_LOSS_DB


def test_taller_obstruction_worse():
    low = [Obstruction(building_id="b1", distance_along_path_m=250, height_m=12)]
    high = [Obstruction(building_id="b1", distance_along_path_m=250, height_m=40)]
    loss_low = excess_diffraction_loss_db(500, 10, 3, low, 1.9e9)
    loss_high = excess_diffraction_loss_db(500, 10, 3, high, 1.9e9)
    assert loss_high >= loss_low
