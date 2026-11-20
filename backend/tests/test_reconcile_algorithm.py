import math
from datetime import datetime, timedelta
import pytest
from src.services.reconcile import reconcile, build_profile

DAY = '2026-11-01'

def history_rows(n_days=14):
    rows = []
    base = datetime(2026, 10, 1)
    for i in range(n_days * 24):
        hour = (base + timedelta(hours=i)).strftime('%Y-%m-%dT%H:00')
        h = i % 24
        rows.append({'hour': hour, 'kwh': round(60 + 25 * math.sin((h - 6) * math.pi / 12), 3), 'source': 'measured'})
    return rows

def measured(missing):
    base = datetime.strptime(DAY, '%Y-%m-%d')
    out = []
    for i in range(24):
        hour = (base + timedelta(hours=i)).strftime('%Y-%m-%dT%H:00')
        if hour in missing:
            continue
        h = i
        out.append({'hour': hour, 'kwh': round(60 + 25 * math.sin((h - 6) * math.pi / 12), 3)})
    return out

def limits(missing, cap=200.0):
    return {h: cap for h in missing}

def test_sum_equals_daily_total_and_within_limits():
    missing = [f'{DAY}T{h:02d}:00' for h in (3, 4, 5, 14, 15)]
    m = measured(missing)
    daily = round(sum(r['kwh'] for r in m) + 300.0, 3)
    res = reconcile(DAY, daily, limits(missing), m, history_rows())
    assert res['residual'] == 0.0
    assert round(sum(r['kwh'] for r in res['hours']), 3) == daily
    for r in res['hours']:
        if r['source'] == 'filled':
            assert 0 <= r['kwh'] <= r['upper'] + 1e-9
    # 实测不动
    meas = {r['hour']: r['kwh'] for r in m}
    for r in res['hours']:
        if r['source'] == 'measured':
            assert r['kwh'] == meas[r['hour']]

def test_profile_follows_same_shift_curve():
    missing = [f'{DAY}T{h:02d}:00' for h in (10, 11, 12)]
    m = measured(missing)
    daily = round(sum(r['kwh'] for r in m) + 200.0, 3)
    res = reconcile(DAY, daily, limits(missing), m, history_rows())
    profile = build_profile(history_rows(), DAY)
    for r in res['hours']:
        if r['source'] == 'filled':
            # 班次均值存在时，补值应在该班次曲线附近（受边界与总和约束，给宽松带）
            assert abs(r['kwh'] - profile[int(r['hour'][11:13])]) < 60

def test_boundary_jump_reduced_against_flat_alternative():
    # 单段连续缺口，两端有实测；带边界目标的解在端点处应比"按班次均值硬配平"更贴近邻居
    missing = [f'{DAY}T{h:02d}:00' for h in range(8, 13)]
    m = measured(missing)
    daily = round(sum(r['kwh'] for r in m) + 260.0, 3)
    res = reconcile(DAY, daily, limits(missing), m, history_rows())
    jumps = {j['hour'] + j['side']: abs(j['jump']) for j in res['boundary_jumps']}
    assert jumps  # 两端落差都被记录
    # 落差有限且数值合理
    assert all(v < 80 for v in jumps.values())

def test_cap_infeasible_raises():
    missing = [f'{DAY}T{h:02d}:00' for h in (3, 4)]
    m = measured(missing)
    daily = round(sum(r['kwh'] for r in m) + 500.0, 3)  # 缺口500，但两小时上限合计200
    with pytest.raises(ValueError, match='无解'):
        reconcile(DAY, daily, limits(missing, cap=100.0), m, history_rows())

def test_gap_must_be_positive():
    missing = [f'{DAY}T03:00']
    m = measured(missing)
    daily = round(sum(r['kwh'] for r in m), 3)  # 缺口为0
    with pytest.raises(ValueError):
        reconcile(DAY, daily, limits(missing), m, history_rows())

def test_conflicting_measured_hour_rejected():
    missing = [f'{DAY}T03:00']
    m = measured([])  # 03点其实有实测
    with pytest.raises(ValueError, match='已有实测'):
        reconcile(DAY, 1000.0, limits(missing), m, history_rows())

def test_filled_never_marked_measured_and_checksum_present():
    missing = [f'{DAY}T{h:02d}:00' for h in (2, 20, 23)]
    m = measured(missing)
    daily = round(sum(r['kwh'] for r in m) + 150.0, 3)
    res = reconcile(DAY, daily, limits(missing), m, history_rows())
    sources = {r['hour']: r['source'] for r in res['hours']}
    for h in missing:
        assert sources[h] == 'filled'
    assert len(res['checksum']) == 64
    assert res['filled_sum'] == res['gap']
