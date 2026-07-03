"""EXIF parsing tests — uses the sample photo committed under data/photos/."""
import os

from topo.exif import read_gps

FIXTURE = os.path.join(
    os.path.dirname(__file__), "..", "data", "photos", "38.jpg"
)


def test_read_gps_from_fixture():
    """The sample boulder photo has GPS EXIF; read_gps should return lat/lon."""
    gps = read_gps(FIXTURE)
    assert gps is not None, "fixture photo should have GPS EXIF"
    assert isinstance(gps["lat"], float)
    assert isinstance(gps["lon"], float)
    # Refuge du Suffet is in the French Alps — sanity-check the ballpark.
    assert 44 < gps["lat"] < 46
    assert 6 < gps["lon"] < 7


def test_read_gps_missing_returns_none(tmp_path):
    """A photo without GPS EXIF should return None, not throw."""
    from PIL import Image

    p = tmp_path / "no_gps.jpg"
    Image.new("RGB", (10, 10), "white").save(p, "JPEG")
    assert read_gps(str(p)) is None
