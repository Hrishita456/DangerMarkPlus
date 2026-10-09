"""Small offline regression tests for risks specific to geospatial preparation."""
import importlib.util
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'preprocessing'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'validation'))
import numpy as np
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from shapely.geometry import Point, box
from common import write_json
from prepare import conservative_population, feature, grid_for, save_features, study_geometry
from validate_dataset import validate_vector


def transfer(values, boundary, resolution, nodata=-9999):
    # Synthetic projected cells are only test inputs, never pilot data.
    values = np.asarray(values, dtype='float64')
    grid = {'crs': 'EPSG:32643', 'transform': from_origin(500000, 1000020, resolution, resolution),
            'height': int(20 / resolution), 'width': int(values.shape[1] * 10 / resolution)}
    with MemoryFile() as memory:
        with memory.open(driver='GTiff', width=values.shape[1], height=values.shape[0],
                         count=1, dtype='float64', crs='EPSG:32643',
                         transform=from_origin(500000, 1000020, 10, 10), nodata=nodata) as src:
            src.write(values, 1)
            return conservative_population(src, boundary, grid)


def test_population_conserves_counts_when_resolution_changes():
    boundary = box(500000, 1000000, 500020, 1000020)
    values, coverage, totals = transfer([[10, 20], [30, 40]], boundary, 5)
    assert values.sum() == pytest.approx(100)
    assert values[0, 0] == pytest.approx(2.5)
    assert np.all(coverage == 1)
    assert totals['absolute_conservation_error'] < 1e-9


def test_population_fractional_boundary_does_not_keep_whole_edge_cells():
    boundary = box(500005, 1000000, 500015, 1000020)
    values, coverage, totals = transfer([[10, 20], [30, 40]], boundary, 20)
    assert values[0, 0] == pytest.approx(50)
    assert totals['source_fractional_pilot_total'] == pytest.approx(50)
    assert coverage[0, 0] == pytest.approx(1)


def test_unknown_population_is_not_silently_zero():
    boundary = box(500000, 1000000, 500020, 1000020)
    values, coverage, totals = transfer([[10, -9999], [0, -9999]], boundary, 10)
    assert values[1, 0] == 0  # A real source zero is preserved.
    assert np.all(values[:, 1] == -9999)
    assert np.all(coverage[:, 1] == 0)
    coarse, fraction, _ = transfer([[10, -9999], [0, -9999]], boundary, 20)
    assert coarse[0, 0] == pytest.approx(10)
    assert fraction[0, 0] == pytest.approx(.5)
    assert totals['source_nodata_reinterpreted_as_zero'] is False


def test_all_unknown_population_fails():
    with pytest.raises(ValueError, match='No valid population'):
        transfer([[-9999, -9999], [-9999, -9999]], box(500000, 1000000, 500020, 1000020), 10)


def test_metric_crs_required_and_grids_nested():
    pilot = {'bbox_wgs84': [77.215, 28.590, 77.305, 28.715], 'metric_crs': 'EPSG:32643', 'grid_snap_m': 90}
    _, metric = study_geometry(pilot)
    fine, coarse = grid_for(pilot, metric, 30), grid_for(pilot, metric, 90)
    assert fine['bounds'] == coarse['bounds']
    assert fine['width'] == 3 * coarse['width'] and fine['height'] == 3 * coarse['height']
    with pytest.raises(ValueError, match='must use metres'):
        study_geometry({**pilot, 'metric_crs': 'EPSG:4326'})
    with pytest.raises(ValueError, match='divide'):
        grid_for(pilot, metric, 40)


def test_swapped_coordinates_and_duplicate_ids_rejected(tmp_path):
    boundary = box(77.2, 28.5, 77.4, 28.8)
    path = tmp_path / 'points.geojson'
    save_features(path, [feature(Point(28.65, 77.25), {'id': 'x'})])
    with pytest.raises(ValueError, match='intersect'):
        validate_vector(path, boundary, 'EPSG:4326')
    save_features(path, [feature(Point(77.25, 28.65), {'id': 'x'})] * 2)
    with pytest.raises(ValueError, match='unique'):
        validate_vector(path, boundary, 'EPSG:4326')


def test_json_refuses_nan_preserving_existing_file(tmp_path):
    path = tmp_path / 'metadata.json'
    write_json(path, {'value': None})
    previous = path.read_bytes()
    with pytest.raises(ValueError):
        write_json(path, {'value': float('nan')})
    assert path.read_bytes() == previous


def test_download_does_not_overwrite_partial_or_accept_truncation(tmp_path):
    module_path = Path(__file__).resolve().parents[1] / 'download/acquire.py'
    spec = importlib.util.spec_from_file_location('acquire', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class Response:
        headers = {'Content-Length': '10'}
        def raise_for_status(self):
            pass
        def iter_content(self, _):
            yield b'short'

    destination = tmp_path / 'source.tif'
    with pytest.raises(RuntimeError, match='Incomplete'):
        module.save_response(Response(), destination, 100)
    assert not destination.exists()
    assert destination.with_suffix('.tif.part').read_bytes() == b'short'
    with pytest.raises(RuntimeError, match='Partial download exists'):
        module.save_response(Response(), destination, 100)

    # requests transparently decompresses HTTP payloads: Content-Length then
    # describes wire bytes and must not be compared to decoded output length.
    class CompressedResponse(Response):
        headers = {'Content-Length': '3', 'Content-Encoding': 'gzip'}
    decoded = tmp_path / 'decoded.xml'
    module.save_response(CompressedResponse(), decoded, 100)
    assert decoded.read_bytes() == b'short'


def test_local_population_registration_never_uses_network(tmp_path, monkeypatch):
    import common
    import rasterio
    module_path = Path(__file__).resolve().parents[1] / 'download/acquire.py'
    spec = importlib.util.spec_from_file_location('local_acquire', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(common, 'ROOT', tmp_path)
    monkeypatch.setattr(common, 'CATALOG', tmp_path / 'catalog')
    monkeypatch.setattr(module, 'RAW', tmp_path / 'raw')
    def forbidden_network(*args, **kwargs):
        raise AssertionError('Local population input must never trigger HTTP')
    monkeypatch.setattr(module.SESSION, 'get', forbidden_network)
    path = tmp_path / 'raw/population/provided.tif'
    path.parent.mkdir(parents=True)
    with rasterio.open(path, 'w', driver='GTiff', width=100, height=100, count=1,
                       dtype='float32', crs='EPSG:4326', nodata=-99999,
                       transform=from_origin(77.2, 28.8, 1/120, 1/120)) as src:
        src.write(np.full((100, 100), 10, dtype='float32'), 1)
    digest = common.sha256(path)
    source = {'kind': 'local_raster', 'category': 'population', 'raw_name': 'native.tif',
              'local_source_name': 'provided.tif', 'expected_local_sha256': digest,
              'url': 'https://example.invalid/catalogue', 'units': 'estimated persons per native pixel'}
    pilot = {'bbox_wgs84': [77.24, 28.70, 77.27, 28.74]}
    module.raster_window('test_population', source, pilot)
    assert common.sha256(path) == digest
    with rasterio.open(tmp_path / 'raw/population/native.tif') as crop:
        assert crop.width < 100 and crop.height < 100
        assert crop.res == pytest.approx((1/120, 1/120))
        assert np.all(crop.read(1) == 10)  # Counts unchanged, no density conversion.
    manifest = common.read_json(tmp_path / 'catalog/manifests/test_population.json')
    assert manifest['acquisition_method'] == 'user_supplied_local_file'
    assert len(manifest['raw_files']) == 2
    module.raster_window('test_population', source, pilot)  # Cached path is offline too.
