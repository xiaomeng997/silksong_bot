"""The nonempty support paths must not acquire new signatures during a fight."""
import numpy as np

from ssbot.combat import enemy_tables, fastquery, multi_forecast
from ssbot.train.measurement import warm_query_kernels


def test_warmup_covers_actual_query_call_signatures_without_mutating_control_state():
    report = warm_query_kernels()
    dispatchers = [enemy_tables._query_win_par, multi_forecast._bbox_boxes,
                   multi_forecast._box_hits, fastquery._query_par]
    signatures = [list(d.signatures) for d in dispatchers]
    bits = np.zeros(1, np.uint8)
    ints = np.zeros(0, np.int64)
    floats = np.zeros(0, np.float64)
    loff = np.zeros((0, 1), np.int64)
    tk = np.zeros(1, np.float64)
    points = np.zeros((1, 1), np.float64)
    out = np.zeros((1, 1), np.bool_)
    pbox = np.zeros((0, 4), np.float64)
    cbox = np.zeros((1, 4), np.float64)
    enemy_tables._query_win_par(bits, loff, np.zeros((0, 9), np.int64),
                                np.zeros((0, 7)), tk, points, points, out, 1, pbox, cbox)
    fastquery._query_par(bits, ints, np.zeros((0, 10), np.int64), np.zeros((0, 6)),
                        bits, tk, points, points, out, 1, pbox, cbox)
    boxes = multi_forecast._bbox_boxes(tk, np.zeros((1, 4)), loff, ints,
                                      floats, floats, floats, floats, floats, floats, floats,
                                      ints, floats, 1 / 60)
    hits = multi_forecast._box_hits(points, points, *boxes, 0.0, 0.0)
    assert not hits.any() and not out.any()
    assert [list(d.signatures) for d in dispatchers] == signatures
    assert len(report) == 4 and all(x["warmup_ms"] >= 0 for x in report.values())
