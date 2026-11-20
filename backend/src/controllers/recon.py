from fastapi import HTTPException
from src.models.entities import ReconDay,ReconVersion
def ensure_recon(s,rid):
 row=s.get(ReconDay,rid)
 if not row:raise HTTPException(404,'对账日不存在')
 return row
def ensure_version(s,row,no):
 v=s.query(ReconVersion).filter_by(recon_id=row.id,version_no=no).first()
 if not v:raise HTTPException(404,'对账版本不存在')
 return v
