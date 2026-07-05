from app.propagation.tr38901 import uma_pathloss, umi_pathloss, log_distance_pathloss


def test_pathloss_monotonic_in_distance():
    for fn in (uma_pathloss, umi_pathloss, log_distance_pathloss):
        near = fn(50, 20, 3, 1.9e9, los=True)
        far = fn(500, 20, 3, 1.9e9, los=True)
        assert far.pathloss_db > near.pathloss_db


def test_nlos_at_least_los_pathloss():
    for fn in (uma_pathloss, umi_pathloss):
        los = fn(300, 20, 3, 1.9e9, los=True)
        nlos = fn(300, 20, 3, 1.9e9, los=False)
        assert nlos.pathloss_db >= los.pathloss_db


def test_pathloss_positive_and_finite():
    for fn in (uma_pathloss, umi_pathloss, log_distance_pathloss):
        r = fn(1000, 25, 3, 0.9e9, los=False)
        assert 0 < r.pathloss_db < 300
