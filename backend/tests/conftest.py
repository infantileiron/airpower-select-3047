import os, sys, math
from datetime import datetime, timedelta
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('JWT_SECRET', 'test-secret-3110')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/15')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.config import database as dbconf
from src.models import entities
from src.models.entities import User, Sample, ReconDay, ReconVersion
from src.utils.security import hash_password

@pytest.fixture()
def session():
    engine = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False})
    entities.Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    # 让应用内部使用的 Session/engine 指向测试库
    dbconf.engine = engine
    dbconf.Session = TestSession
    with TestSession() as s:
        for role in ('admin', 'analyst', 'viewer'):
            s.add(User(email=role + '@demo.local', role=role, password=hash_password('Demo123!')))
        rng_seed = 7
        # 30 天历史实测（不含目标日），带明显班次曲线
        base = datetime(2026, 10, 1)
        for i in range(30 * 24):
            hour = (base + timedelta(hours=i)).strftime('%Y-%m-%dT%H:00')
            h = i % 24
            kwh = round(60 + 25 * math.sin((h - 6) * math.pi / 12) + (i % 5) * 0.7, 3)
            s.add(Sample(hour=hour, pressure=6.5, flow=9.0, temperature=22.0, machines=3,
                         sensor_noise=0.1, kwh=kwh, note='history'))
        s.commit()
        yield s

@pytest.fixture()
def users(session):
    q = session.query(User)
    return {u.role: u for u in q.all()}

def make_day_measured(session, day, missing_hours):
    base = datetime.strptime(day, '%Y-%m-%d')
    for i in range(24):
        hour = (base + timedelta(hours=i)).strftime('%Y-%m-%dT%H:00')
        if hour in missing_hours:
            continue
        h = i
        kwh = round(60 + 25 * math.sin((h - 6) * math.pi / 12), 3)
        session.add(Sample(hour=hour, pressure=6.5, flow=9.0, temperature=22.0, machines=3,
                           sensor_noise=0.1, kwh=kwh, note='measured'))
    session.commit()
