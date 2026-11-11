"""Isolated QA tests: no application engine imports or behavior changes."""
import csv
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('ngsim_qa', Path(__file__).resolve().parents[2] / 'scripts/data_quality/analyze_ngsim.py')
QA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QA)


def report(tmp_path, changes=()):
    rows = [dict(location='i-80', vehicle_id='1', global_time=str(1000 + i * 100), local_x='0', local_y=str(i * 10), v_length='16', v_width='6', v_vel='100', v_acc='0') for i in range(3)]
    for index, fields in changes:
        rows[index].update(fields)
    path = tmp_path / 'tiny.csv'
    with path.open('w', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=QA.REQUIRED)
        writer.writeheader()
        writer.writerows(rows)
    return QA.analyze(path)


def test_valid_and_feet_conversion(tmp_path):
    result = report(tmp_path, [(i, {'local_y': '0', 'v_vel': '0'}) for i in range(3)])
    assert QA.FT == 0.3048
    assert result['row_count'] == 3
    assert result['unique_vehicles_by_location_and_id'] == 1
    assert result['speed_position_residual_mps']['count'] == 2
    assert result['speed_position_residual_mps']['max'] == 0


def test_conversion_in_residual(tmp_path):
    result = report(tmp_path, [(i, {'v_vel': '0'}) for i in range(3)])
    assert result['speed_position_residual_mps']['mean'] == pytest.approx(30.48)


def test_repeated_and_reversed_time(tmp_path):
    result = report(tmp_path, [(1, {'global_time': '1000'}), (2, {'global_time': '900'})])
    assert result['counts']['duplicate_vehicle_time'] == 1
    assert result['counts']['nonmonotonic_vehicle_time'] == 2
    assert result['missing_records_assessment']['status'] == 'not evaluated'
    assert result['missing_records_assessment']['count'] is None


def test_velocity_discrepancy_and_teleport(tmp_path):
    result = report(tmp_path, [(1, {'local_y': '1000'})])
    assert result['counts']['speed_position_inconsistency'] == 2
    assert result['counts']['teleport_or_id_mismatch_candidate'] == 2


@pytest.mark.parametrize('value', ['', 'NaN', 'inf', 'bad'])
def test_missing_or_invalid_coordinate(tmp_path, value):
    result = report(tmp_path, [(1, {'local_x': value})])
    assert result['counts']['invalid_local_x'] == 1
    assert result['speed_position_residual_mps']['count'] == 0


@pytest.mark.parametrize('field,value', [('v_length', '-1'), ('v_width', '100'), ('v_length', '')])
def test_bad_dimensions(tmp_path, field, value):
    assert report(tmp_path, [(1, {field: value})])['counts']['bad_dimensions'] == 1


def test_false_certainty_guard(tmp_path):
    result = report(tmp_path)
    assert result['collision_check']['status'] == 'not evaluated'
    assert result['collision_check']['overlap_count'] is None
    assert result['coordinate_semantics']['center_validated'] is False
    assert 'MUST NOT cause on-road alerts' in result['scope']


def test_gap_and_site_specific_identity(tmp_path):
    result = report(tmp_path, [(1, {'global_time': '1300'}), (2, {'location': 'us-101'})])
    assert result['counts']['missing_records_inferred'] == 2
    assert result['unique_vehicles_by_location_and_id'] == 2


def test_header_rejection(tmp_path):
    path = tmp_path / 'bad.csv'
    path.write_text('vehicle_id\n1\n')
    with pytest.raises(ValueError, match='Invalid headers'):
        QA.analyze(path)


def test_invalid_fields(tmp_path):
    result = report(tmp_path, [(0, {'vehicle_id': 'bad'}), (1, {'v_vel': '-1', 'v_acc': '100'})])
    assert result['counts']['invalid_identity_or_time'] == 1
    assert result['counts']['implausible_speed'] == 1
    assert result['counts']['implausible_acceleration'] == 1


def test_site_axes_sign_and_rotation(tmp_path):
    result = report(tmp_path, [(i, {'local_y': '0', 'local_x': str(-i * 10)}) for i in range(3)])
    assert result['speed_position_residual_mps']['max'] == pytest.approx(0)


def test_nonadjacent_duplicate(tmp_path):
    result = report(tmp_path, [(2, {'global_time': '1000'})])
    assert result['counts']['duplicate_vehicle_time'] == 1


def test_empty_csv(tmp_path):
    path = tmp_path / 'empty.csv'
    path.write_text(','.join(QA.REQUIRED) + '\n')
    result = QA.analyze(path)
    assert result['row_count'] == 0
    assert result['time_span_ms']['duration'] is None
    assert result['speed_position_residual_mps']['mean'] is None
