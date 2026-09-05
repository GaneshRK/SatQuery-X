import pytest
from apps.geospatial.math import calculate_pixel_area_m2, calculate_polygon_ground_area_m2
from shapely.geometry import Polygon


def test_pixel_area_projected_vs_geographic():
    """Verify UTM (meters) vs EPSG:4326 (degrees) pixel area calculation."""
    # UTM projected (10m x 10m pixels)
    affine_utm = [10.0, 0.0, 500000.0, 0.0, -10.0, 1400000.0]
    area_utm = calculate_pixel_area_m2(affine_utm, "EPSG:32644")
    assert pytest.approx(area_utm, rel=1e-3) == 100.0

    # Geographic degrees (approx 0.0001 deg at equator ~ 11.13m)
    affine_geo = [0.0001, 0.0, 80.0, 0.0, -0.0001, 13.0]
    area_geo = calculate_pixel_area_m2(affine_geo, "EPSG:4326", bounds_wgs84={"south": 12.9, "north": 13.1})
    # Must be in plausible ground meter range, never arbitrary 1e10
    assert 50.0 < area_geo < 200.0


def test_geodesic_area_shapely_no_arbitrary_multiplier():
    """Verify calculate_polygon_ground_area_m2 computes real physical area without fake constants."""
    # 0.01 deg x 0.01 deg box near Chennai (lat ~ 13.0)
    # Approx 1.11 km x 1.08 km ~ 1.2 km² ~ 1,200,000 m²
    poly = Polygon([(80.0, 13.0), (80.01, 13.0), (80.01, 13.01), (80.0, 13.01), (80.0, 13.0)])
    area_m2 = calculate_polygon_ground_area_m2(poly, "EPSG:4326")
    assert 1_000_000 < area_m2 < 1_400_000
    area_km2 = area_m2 / 1e6
    assert 1.0 < area_km2 < 1.4
