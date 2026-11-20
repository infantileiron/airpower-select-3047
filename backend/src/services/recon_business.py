from datetime import datetime,timezone
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from src.models.entities import ReconDay,ReconVersion,Sample
from src.config import database as dbconf
from src.services.reconcile import reconcile as run_reconcile
from src.services.business import audit
def _now():return datetime.now(timezone.utc).isoformat()
def _snapshot(s,day):
 # 目标日之前的实测（补值不参与同班次曲线）
 rows=s.query(Sample).filter(Sample.hour<day+'T00:00').order_by(Sample.hour).all()
 return [{'hour':r.hour,'kwh':r.kwh,'source':'measured'} for r in rows]
def _day_measured(s,day):
 rows=s.query(Sample).filter(Sample.hour>=day+'T00:00',Sample.hour<day+'T23:59').order_by(Sample.hour).all()
 return [{'hour':r.hour,'kwh':r.kwh} for r in rows]
def _inputs(s,row):
 measured=_day_measured(s,row.day);measured_hours={r['hour'] for r in measured}
 # 迟到实测入库后，已变实测的小时不再是缺测，重算时自动从上限中剥离
 limits={h:c for h,c in row.upper_limits.items() if h not in measured_hours}
 return {'day':row.day,'daily_total':row.daily_total,'upper_limits':limits,
         'measured':measured,'history':_snapshot(s,row.day)}
def detect_stale(s,row):
 # 迟到实测入库后，已发布版本引用的缺测小时若已有实测，则该版本与对账失效
 if row.status!='published' or not row.active_version:return False
 v=s.get(ReconVersion,row.active_version)
 if not v or v.state!='published' or not v.result:return False
 missing=set(v.result.get('missing_hours',[]))
 have={r.hour for r in s.query(Sample).filter(Sample.hour.in_(missing)).all()} if missing else set()
 if have:
  v.state='stale';v.error='迟到实测入库：%s；旧对账自动失效，需重算'%('，'.join(sorted(have)))
  if row.status=='published':row.status='stale'
  s.commit();return True
 return False
def get_recon(s,rid):
 row=s.get(ReconDay,rid)
 if not row:raise HTTPException(404,'对账日不存在')
 detect_stale(s,row);return row
def list_versions(s,row):
 return s.query(ReconVersion).filter_by(recon_id=row.id).order_by(ReconVersion.version_no).all()
def create_recon(s,u,data):
 row=ReconDay(day=data.day,daily_total=data.daily_total,upper_limits=data.upper_limits,status='open')
 s.add(row)
 try:s.commit()
 except IntegrityError:
  s.rollback();raise HTTPException(409,'该日对账已存在，请对原记录重算，不要并发新建')
 return _compute(s,u,row,reason='首次补算')
def recompute(s,u,row,reason='重算'):
 # 旧版不在此处提前下线；仅当新版本在独立事务成功发布时才置为superseded，失败则旧版保持published
 return _compute(s,u,row,reason=reason)
def _next_no(s,rid):
 return s.query(ReconVersion).filter_by(recon_id=rid).count()+1
def _compute(s,u,row,reason):
 # 乐观并发：记录基线活跃版本，长计算不持行锁；发布在独立新事务重新读取后校验
 base_active=row.active_version;rid=row.id;day=row.day;new_no=_next_no(s,rid)
 inputs=_inputs(s,row)
 v=ReconVersion(recon_id=rid,version_no=new_no,state='pending',
   input_snapshot=inputs,created_by=u.email,created=_now(),reason=reason)
 s.add(v);s.commit();vid=v.id
 try:
  result=run_reconcile(**inputs)
 except Exception as e:
  # 重算失败：保留旧版与失败原因，新行记录failed，不改变已发布结果
  with dbconf.Session() as fs:
   failed=fs.get(ReconVersion,vid)
   failed.state='failed';failed.error=str(e)[:1000];fs.commit()
  audit(s,u,'对账补算失败 '+day)
  raise HTTPException(422,'补算失败，已保留旧版：'+str(e))
 # 独立新事务发布：能读到并发事务已提交的活跃版本，规避可重复读快照导致的过期发布
 with dbconf.Session() as fs:
  fresh=fs.get(ReconDay,rid);ver=fs.get(ReconVersion,vid)
  if fresh.active_version!=base_active:
   ver.state='discarded';ver.result=result
   ver.error='并发补录：检测到更新版本已发布，本次过期结果不发布'
   fs.commit();audit(s,u,'对账过期结果丢弃 '+day)
   raise HTTPException(409,'已有更新的对账版本发布，本次结果已丢弃，请刷新后查看')
  ver.state='published';ver.result=result;ver.error=''
  if base_active:
   old=fs.get(ReconVersion,base_active)
   if old and old.state=='published':old.state='superseded'
  fresh.active_version=ver.id;fresh.status='published'
  fresh.daily_total=inputs['daily_total'];fresh.upper_limits=inputs['upper_limits']
  fs.commit()
 s.expire_all();audit(s,u,reason+'对账 '+day+' v'+str(new_no))
 return s.get(ReconDay,rid)
def mark_late(s,hour):
 # 迟到实测入库时调用：凡引用该小时的已发布对账立即失效
 rows=s.query(ReconDay).filter(ReconDay.status=='published').all()
 changed=[]
 for row in rows:
  v=s.get(ReconVersion,row.active_version) if row.active_version else None
  if v and v.result and hour in set(v.result.get('missing_hours',[])):
   v.state='stale';v.error='迟到实测入库：%s；旧对账自动失效，需重算'%hour
   row.status='stale';changed.append(row.day)
 if changed:s.commit()
 return changed
