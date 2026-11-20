from sqlalchemy import Column,Integer,String,Float,JSON,Text,ForeignKey,UniqueConstraint
from src.config.database import Base
class User(Base):
 __tablename__='users'
 id=Column(Integer,primary_key=True);email=Column(String(100),unique=True);password=Column(String(200));role=Column(String(20))
class Sample(Base):
 __tablename__='samples'
 id=Column(Integer,primary_key=True);hour=Column(String(30),unique=True,nullable=False);pressure=Column(Float);flow=Column(Float);temperature=Column(Float);machines=Column(Integer);sensor_noise=Column(Float);kwh=Column(Float);note=Column(Text,default='')
class Run(Base):
 __tablename__='runs'
 id=Column(Integer,primary_key=True);name=Column(String(100));features=Column(JSON);alphas=Column(JSON);state=Column(String(20),default='queued');result=Column(JSON);error=Column(Text,default='')
class Review(Base):
 __tablename__='reviews'
 id=Column(Integer,primary_key=True);run_id=Column(Integer,ForeignKey('runs.id'));title=Column(String(100));finding=Column(Text);action=Column(Text);status=Column(String(20),default='draft')
class Audit(Base):
 __tablename__='audits'
 id=Column(Integer,primary_key=True);actor=Column(String(100));action=Column(String(200));created=Column(String(40))
class ReconDay(Base):
 __tablename__='recon_days'
 id=Column(Integer,primary_key=True);day=Column(String(10),unique=True,nullable=False);daily_total=Column(Float,nullable=False);upper_limits=Column(JSON,nullable=False);active_version=Column(Integer,nullable=True);status=Column(String(20),default='open')
class ReconVersion(Base):
 __tablename__='recon_versions'
 id=Column(Integer,primary_key=True);recon_id=Column(Integer,ForeignKey('recon_days.id'),nullable=False);version_no=Column(Integer,nullable=False);state=Column(String(20),default='pending');input_snapshot=Column(JSON);result=Column(JSON);error=Column(Text,default='');created_by=Column(String(100));created=Column(String(40));reason=Column(Text,default='')
 __table_args__=(UniqueConstraint('recon_id','version_no',name='uq_recon_version'),)
