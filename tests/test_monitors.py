import math

from simulation_engine.monitors import LevelMonitor, TallyMonitor


def test_level_monitor_time_weighted_mean():
    m = LevelMonitor("q")
    m.set(1, 1.0)   # value 0 for [0,1)
    m.set(3, 2.0)   # value 1 for [1,2)
    m.finalize(4.0)  # value 3 for [2,4)
    assert m.mean() == (0 * 1 + 1 * 1 + 3 * 2) / 4
    assert m.maximum() == 3
    assert m.duration() == 4.0


def test_level_monitor_warmup_reset_keeps_value():
    m = LevelMonitor("q")
    m.set(5, 1.0)
    m.reset(10.0)          # discard history, keep value 5
    m.finalize(20.0)
    assert m.mean() == 5.0
    assert m.duration() == 10.0


def test_level_monitor_percentile_weighted():
    m = LevelMonitor("q")
    m.set(10, 9.0)   # value 0 for 9 time units, then 10 for 1
    m.finalize(10.0)
    assert m.percentile(50) == 0
    assert m.percentile(95) == 10


def test_tally_monitor():
    t = TallyMonitor("w")
    for v in [1, 2, 3, 4, 100]:
        t.observe(v)
    assert t.n == 5
    assert t.mean() == 22
    assert t.median() == 3
    t.reset()
    assert t.n == 0 and math.isnan(t.mean())


def test_level_monitor_rejects_time_travel():
    m = LevelMonitor("q")
    m.set(1, 5.0)
    try:
        m.set(2, 4.0)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
