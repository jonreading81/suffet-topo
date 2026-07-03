from topo.lines import catmull, parse_line


def test_parse_line_empty():
    assert parse_line(None) == []
    assert parse_line("") == []


def test_parse_line_single_point():
    assert parse_line("10,20") == [(10.0, 20.0)]


def test_parse_line_multiple_points():
    assert parse_line("10,20 30.5,40 50,60.5") == [
        (10.0, 20.0),
        (30.5, 40.0),
        (50.0, 60.5),
    ]


def test_catmull_passthrough_when_short():
    assert catmull([]) == []
    assert catmull([(0, 0)]) == [(0, 0)]


def test_catmull_endpoints_preserved():
    # First and last input points should appear in the interpolated output.
    pts = [(0, 0), (10, 0), (10, 10), (20, 10)]
    out = catmull(pts, steps=5)
    assert out[0] == pts[0]
    assert out[-1] == pts[-1]


def test_catmull_output_size_grows_with_steps():
    pts = [(0, 0), (1, 0), (2, 0)]
    assert len(catmull(pts, steps=1)) < len(catmull(pts, steps=10))
