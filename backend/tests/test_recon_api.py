import os, sys
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('JWT_SECRET', 'test-secret-3110')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/15')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.config import database as dbconf
from src.models import entities
from src.routes.api import router
from src.config.database import db
from src.models.entities import User, Sample
from src.utils.security import hash_password, token

DAY = '2026-11-01'

@pytest.fixture()
def client():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False},
                           poolclass=StaticPool)
    entities.Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine, expire_on_commit=False)
    dbconf.engine = engine; dbconf.Session = S
    with S() as s:
        for role in ('admin', 'analyst', 'viewer'):
            s.add(User(email=role + '@demo.local', role=role, password=hash_password('Demo123!')))
        from datetime import datetime, timedelta
        import math
        base = datetime(2026, 10, 1)
        for i in range(20 * 24):
            hour = (base + timedelta(hours=i)).strftime('%Y-%m-%dT%H:00')
            h = i % 24
            s.add(Sample(hour=hour, pressure=6.5, flow=9.0, temperature=22.0, machines=3,
                         sensor_noise=0.1, kwh=round(60 + 25 * math.sin((h - 6) * math.pi / 12), 3), note='h'))
        # 目标日实测，缺 03,04,05
        d0 = datetime.strptime(DAY, '%Y-%m-%d')
        for i in range(24):
            if i in (3, 4, 5):
                continue
            hour = (d0 + timedelta(hours=i)).strftime('%Y-%m-%dT%H:00')
            s.add(Sample(hour=hour, pressure=6.5, flow=9.0, temperature=22.0, machines=3,
                         sensor_noise=0.1, kwh=round(55 + 20 * math.sin((i - 6) * math.pi / 12), 3), note='m'))
        s.commit()
    app = FastAPI(); app.include_router(router)
    def override_db():
        with S() as s:
            yield s
    app.dependency_overrides[db] = override_db
    return TestClient(app), S

def auth(client, role):
    c, S = client
    with S() as s:
        u = s.query(User).filter_by(email=role + '@demo.local').first()
        return {'Authorization': 'Bearer ' + token(u)}

def payload(client):
    c, S = client
    with S() as s:
        measured_sum = sum(r.kwh for r in s.query(Sample).filter(Sample.hour.like(DAY + '%')).all())
    missing = [f'{DAY}T03:00', f'{DAY}T04:00', f'{DAY}T05:00']
    return {'day': DAY, 'daily_total': round(measured_sum + 180.0, 3),
            'upper_limits': {h: 120.0 for h in missing}}

def test_viewer_cannot_create_recon(client):
    c, _ = client
    r = c.post('/reconciliations', json=payload(client), headers=auth(client, 'viewer'))
    assert r.status_code == 403

def test_full_recon_flow_and_hour_sources(client):
    c, _ = client
    r = c.post('/reconciliations', json=payload(client), headers=auth(client, 'analyst'))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['status'] == 'published'
    rid = body['id']
    active = body['active']
    assert active['state'] == 'published'
    result = active['result']
    # 逐小时来源可核对
    src = {h['hour']: h['source'] for h in result['hours']}
    assert src[f'{DAY}T03:00'] == 'filled'
    assert src[f'{DAY}T06:00'] == 'measured'
    assert result['residual'] == 0
    # 差额字段
    assert result['gap'] == result['filled_sum']
    # 列表与详情
    assert c.get('/reconciliations', headers=auth(client, 'admin')).json()[0]['id'] == rid
    detail = c.get(f'/reconciliations/{rid}', headers=auth(client, 'admin')).json()
    assert detail['versions'][0]['version_no'] == 1

def test_recompute_keeps_history_and_publishes_new_version(client):
    c, _ = client
    h = auth(client, 'analyst')
    rid = c.post('/reconciliations', json=payload(client), headers=h).json()['id']
    r2 = c.post(f'/reconciliations/{rid}/recompute', headers=h)
    assert r2.status_code == 200
    body = r2.json()
    assert body['active']['version_no'] == 2
    states = [v['state'] for v in body['versions']]
    assert states == ['superseded', 'published']

def test_failed_recompute_preserves_old_version(client, monkeypatch):
    c, S = client
    h = auth(client, 'analyst')
    rid = c.post('/reconciliations', json=payload(client), headers=h).json()['id']
    import src.services.recon_business as rb
    def boom(**kwargs):
        raise RuntimeError('模拟求解器失败')
    monkeypatch.setattr(rb, 'run_reconcile', boom)
    r = c.post(f'/reconciliations/{rid}/recompute', headers=h)
    assert r.status_code == 422
    # 旧版仍为已发布，失败版保留原因
    body = c.get(f'/reconciliations/{rid}', headers=h).json()
    assert body['status'] == 'published'
    assert body['active']['version_no'] == 1
    assert body['active']['state'] == 'published'  # 旧版保持有效
    failed = [v for v in body['versions'] if v['state'] == 'failed']
    assert failed and '模拟求解器失败' in failed[0]['error']

def test_late_measurement_invalidates_published_recon(client):
    c, S = client
    h = auth(client, 'analyst')
    rid = c.post('/reconciliations', json=payload(client), headers=h).json()['id']
    # 迟到实测入库（原本缺测的04点）
    sample = {'hour': f'{DAY}T04:00', 'pressure': 6.5, 'flow': 9.0, 'temperature': 22.0,
              'machines': 3, 'sensor_noise': 0.1, 'kwh': 70.0, 'note': 'late'}
    r = c.post('/samples', json=sample, headers=h)
    assert r.status_code == 200
    body = c.get(f'/reconciliations/{rid}', headers=h).json()
    assert body['status'] == 'stale'
    assert body['active']['state'] == 'stale'
    # 失效版本不可导出
    assert c.get(f'/reconciliations/{rid}/export', headers=h).status_code == 409

def test_filled_values_never_enter_training_snapshot(client):
    c, S = client
    h = auth(client, 'analyst')
    c.post('/reconciliations', json=payload(client), headers=h)
    # 训练快照直接来自 samples 表；补值只存在 recon_versions，samples 行数不增加补值
    with S() as s:
        sample_hours = {r.hour for r in s.query(Sample).all()}
    assert f'{DAY}T04:00' not in sample_hours  # 仍是缺测，未被补值污染
    from src.models.entities import ReconVersion
    with S() as s:
        v = s.query(ReconVersion).first()
        filled_hours = set(v.result['missing_hours'])
    assert filled_hours.isdisjoint(sample_hours)

def test_duplicate_day_conflict(client):
    c, _ = client
    h = auth(client, 'analyst')
    p = payload(client)
    assert c.post('/reconciliations', json=p, headers=h).status_code == 200
    assert c.post('/reconciliations', json=p, headers=h).status_code == 409

def test_update_inputs_then_recompute(client):
    c, _ = client
    h = auth(client, 'analyst')
    created = c.post('/reconciliations', json=payload(client), headers=h).json()
    rid = created['id']
    p = payload(client)
    p['daily_total'] = round(p['daily_total'] + 30.0, 3)
    r = c.put(f'/reconciliations/{rid}', json=p, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body['active']['version_no'] == 2
    assert body['active']['result']['daily_total'] == p['daily_total']
    # 改日期被拒绝
    bad = dict(p); bad['day'] = '2026-11-02'
    assert c.put(f'/reconciliations/{rid}', json=bad, headers=h).status_code == 422

def test_stale_recovers_after_recompute(client):
    c, S = client
    h = auth(client, 'analyst')
    rid = c.post('/reconciliations', json=payload(client), headers=h).json()['id']
    sample = {'hour': f'{DAY}T04:00', 'pressure': 6.5, 'flow': 9.0, 'temperature': 22.0,
              'machines': 3, 'sensor_noise': 0.1, 'kwh': 70.0, 'note': 'late'}
    c.post('/samples', json=sample, headers=h)
    assert c.get(f'/reconciliations/{rid}', headers=h).json()['status'] == 'stale'
    # 重算：04点已变实测，新缺口缩小，重新配平后恢复 published
    r = c.post(f'/reconciliations/{rid}/recompute', headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body['status'] == 'published'
    src = {x['hour']: x['source'] for x in body['active']['result']['hours']}
    assert src[f'{DAY}T04:00'] == 'measured'
    assert body['active']['result']['residual'] == 0

def test_concurrent_stale_result_not_published(client, monkeypatch):
    c, S = client
    h = auth(client, 'analyst')
    rid = c.post('/reconciliations', json=payload(client), headers=h).json()['id']
    import src.services.recon_business as rb
    real = rb.run_reconcile
    # 在重算进行期间，模拟另一个事务已发布更新版本（active_version 改变）
    def racing(**kwargs):
        out = real(**kwargs)
        with S() as s:
            from src.models.entities import ReconDay, ReconVersion
            day = s.get(ReconDay, rid)
            other = ReconVersion(recon_id=rid, version_no=99, state='published',
                                  result={'missing_hours': []}, created_by='x', created='t', reason='race')
            s.add(other); s.flush(); day.active_version = other.id; s.commit()
        return out
    monkeypatch.setattr(rb, 'run_reconcile', racing)
    r = c.post(f'/reconciliations/{rid}/recompute', headers=h)
    assert r.status_code == 409
    body = c.get(f'/reconciliations/{rid}', headers=h).json()
    # 活跃的仍是并发事务发布的版本；本次结果被丢弃
    assert body['active']['version_no'] == 99
    assert any(v['state'] == 'discarded' for v in body['versions'])
