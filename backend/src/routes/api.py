import os,json
import redis
from fastapi import APIRouter,Depends,HTTPException,Response
from sqlalchemy.exc import IntegrityError
from src.config.database import db
from src.models.entities import User,Sample,Run,Review,Audit,ReconDay,ReconVersion
from src.schemas.business import Login,SampleInput,RunInput,ReviewInput,ReconInput
from src.middlewares.auth import current,editor,admin
from src.utils.security import verify,token
from src.services.business import audit,dump
from src.controllers.business import ensure_run
from src.controllers.recon import ensure_recon,ensure_version
from src.services import recon_business
router=APIRouter()
@router.post('/auth/login')
def login(data:Login,s=Depends(db)):
 u=s.query(User).filter_by(email=data.email).first()
 if not u or not verify(data.password,u.password):raise HTTPException(401,'账号或密码错误')
 return {'token':token(u),'user':dump(u)}
@router.get('/me')
def me(u=Depends(current)):return dump(u)
@router.get('/samples')
def samples(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Sample).order_by(Sample.hour).all()]
@router.post('/samples')
def create(data:SampleInput,u=Depends(editor),s=Depends(db)):
 r=Sample(**data.model_dump());s.add(r)
 try:s.commit()
 except IntegrityError:s.rollback();raise HTTPException(409,'该小时已存在，请使用修订功能')
 # 迟到实测入库：使引用该小时的已发布对账立即失效；补值从不写入samples，故训练只见到实测
 stale=recon_business.mark_late(s,r.hour)
 audit(s,u,'录入小时 '+r.hour+('（迟到实测，失效对账：'+','.join(stale)+'）' if stale else ''));return dump(r)
@router.put('/samples/{i}')
def edit(i:int,data:SampleInput,u=Depends(editor),s=Depends(db)):
 r=s.get(Sample,i)
 if not r:raise HTTPException(404,'小时样本不存在')
 for k,v in data.model_dump().items():setattr(r,k,v)
 try:s.commit()
 except IntegrityError:s.rollback();raise HTTPException(409,'小时重复')
 audit(s,u,'修订样本 '+str(i));return dump(r)
@router.get('/runs')
def runs(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Run).order_by(Run.id.desc()).all()]
@router.post('/runs')
def train(data:RunInput,u=Depends(editor),s=Depends(db)):
 # 仅实测入库（samples）；对账补值source=filled且独立存放，始终不进入训练快照
 rows=[dump(r) for r in s.query(Sample).order_by(Sample.hour).all()];r=Run(**data.model_dump(),result={'snapshot':rows});s.add(r);s.commit()
 try:redis.Redis.from_url(os.environ['REDIS_URL']).rpush('airpower:runs',r.id)
 except redis.RedisError:r.state='failed';r.error='队列暂不可用，请稍后重试';s.commit();raise HTTPException(503,r.error)
 audit(s,u,'提交模型 '+str(r.id));return dump(r)
@router.get('/runs/{i}')
def detail(i:int,u=Depends(current),s=Depends(db)):return dump(ensure_run(s,i))
@router.get('/runs/{i}/export')
def export(i:int,u=Depends(current),s=Depends(db)):
 r=ensure_run(s,i)
 if r.state!='done':raise HTTPException(409,'仅成功版本可导出')
 return Response(json.dumps(dump(r),ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="airpower-select-{i}.json"'})
@router.get('/reviews')
def reviews(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Review).order_by(Review.id.desc()).all()]
@router.post('/reviews')
def review(data:ReviewInput,u=Depends(editor),s=Depends(db)):
 if ensure_run(s,data.run_id).state!='done':raise HTTPException(409,'模型计算完成后才能起草评议')
 r=Review(**data.model_dump());s.add(r);s.commit();audit(s,u,'起草节能评议 '+str(r.id));return dump(r)
@router.put('/reviews/{i}')
def edit_review(i:int,data:ReviewInput,u=Depends(editor),s=Depends(db)):
 r=s.get(Review,i)
 if not r:raise HTTPException(404,'评议不存在')
 if r.status!='draft':raise HTTPException(409,'已签核评议冻结，请新建')
 if ensure_run(s,data.run_id).state!='done':raise HTTPException(409,'需要已成功模型')
 for k,v in data.model_dump().items():setattr(r,k,v)
 s.commit();audit(s,u,'修订评议 '+str(i));return dump(r)
@router.post('/reviews/{i}/approve')
def approve(i:int,u=Depends(admin),s=Depends(db)):
 r=s.get(Review,i)
 if not r:raise HTTPException(404,'评议不存在')
 if r.status!='draft':raise HTTPException(409,'已签核评议不能重复签核')
 r.status='approved';s.commit();audit(s,u,'签核节能评议 '+str(i));return dump(r)
@router.get('/reviews/{i}/export')
def export_review(i:int,u=Depends(current),s=Depends(db)):
 r=s.get(Review,i)
 if not r:raise HTTPException(404,'评议不存在')
 return Response(json.dumps(dump(r),ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="airpower-review-{i}.json"'})
@router.get('/audits')
def audits(u=Depends(admin),s=Depends(db)):return [dump(r) for r in s.query(Audit).order_by(Audit.id.desc()).limit(100)]
# ---- 日电量对账补录 ----
@router.get('/reconciliations')
def recon_list(u=Depends(current),s=Depends(db)):
 out=[]
 for row in s.query(ReconDay).order_by(ReconDay.day.desc()).all():
  recon_business.detect_stale(s,row)
  active=s.get(ReconVersion,row.active_version) if row.active_version else None
  out.append({**dump(row),'active':dump(active) if active else None,
   'versions':[{'version_no':v.version_no,'state':v.state,'error':v.error,'created':v.created,'reason':v.reason} for v in recon_business.list_versions(s,row)]})
 return out
@router.post('/reconciliations')
def recon_create(data:ReconInput,u=Depends(editor),s=Depends(db)):
 row=recon_business.create_recon(s,u,data);return recon_detail(row.id,u,s)
@router.get('/reconciliations/{rid}')
def recon_detail(rid:int,u=Depends(current),s=Depends(db)):
 row=recon_business.get_recon(s,rid)
 active=s.get(ReconVersion,row.active_version) if row.active_version else None
 return {**dump(row),'active':dump(active) if active else None,
  'versions':[dump(v) for v in recon_business.list_versions(s,row)]}
@router.post('/reconciliations/{rid}/recompute')
def recon_recompute(rid:int,u=Depends(editor),s=Depends(db)):
 row=recon_business.get_recon(s,rid);recon_business.recompute(s,u,row);return recon_detail(rid,u,s)
@router.put('/reconciliations/{rid}')
def recon_update(rid:int,data:ReconInput,u=Depends(editor),s=Depends(db)):
 row=recon_business.get_recon(s,rid)
 if data.day!=row.day:raise HTTPException(422,'对账日期不可变更；请新建对账日')
 row.daily_total=data.daily_total;row.upper_limits=data.upper_limits;s.commit()
 recon_business.recompute(s,u,row,reason='调整口径重算');return recon_detail(rid,u,s)
@router.get('/reconciliations/{rid}/versions/{no}')
def recon_version(rid:int,no:int,u=Depends(current),s=Depends(db)):
 row=recon_business.get_recon(s,rid);return dump(ensure_version(s,row,no))
@router.get('/reconciliations/{rid}/export')
def recon_export(rid:int,u=Depends(current),s=Depends(db)):
 row=recon_business.get_recon(s,rid)
 if not row.active_version:raise HTTPException(409,'尚无已发布对账版本')
 v=s.get(ReconVersion,row.active_version)
 if v.state!='published':raise HTTPException(409,'当前无有效已发布版本可导出')
 return Response(json.dumps(dump(v),ensure_ascii=False,indent=2),media_type='application/json',
  headers={'Content-Disposition':f'attachment; filename="daily-recon-{row.day}-v{v.version_no}.json"'})
