import math,json,hashlib
from datetime import datetime,timedelta
import numpy as np
from scipy.optimize import minimize
# 补值目标权重：贴近历史同班次曲线 w_p，减小与缺口两端实测落差 w_b
W_PROFILE=1.0
W_BOUNDARY=2.0
ROUND_ND=3
def _dt(hour):return datetime.strptime(hour,'%Y-%m-%dT%H:00')
def _key(h):return _dt(h).strftime('%Y-%m-%dT%H:00')
def build_profile(history,target_day):
 # history: 同站点此前（不含目标日）实测小时列表 [{hour,kwh,source?}]，按小时班次0..23取均值
 buckets={h:[] for h in range(24)}
 for r in history:
  d=_dt(r['hour'])
  if d.strftime('%Y-%m-%d')==target_day:continue
  if r.get('source')=='filled':continue
  v=r.get('kwh')
  if v is None or not math.isfinite(v):continue
  buckets[d.hour].append(float(v))
 allv=[v for vs in buckets.values() for v in vs]
 fallback=float(np.mean(allv)) if allv else 0.0
 return {h:(float(np.mean(buckets[h])) if buckets[h] else fallback) for h in range(24)}
def _segments(missing_idx):
 # 把连续缺测小时切成段，便于定位每段两端的实测邻居
 idx=sorted(missing_idx);out=[]
 if not idx:return out
 start=prev=idx[0]
 for i in idx[1:]:
  if i==prev+1:prev=i
  else:out.append((start,prev));start=prev=i
 out.append((start,prev));return out
def optimize(day_hours,measured_map,missing,upper,profile,gap):
 m=sorted(missing)
 seg_list=_segments(missing)
 # 每段两端实测邻居（落在当日边界外则为None，表示无该侧落差约束）
 seg_bounds=[]
 for a,b in seg_list:
  seg_bounds.append((a,b,measured_map.get(a-1),measured_map.get(b+1)))
 target=np.array([profile[_dt(day_hours[i]).hour] for i in m],dtype=float)
 caps=np.array([float(upper[day_hours[i]]) for i in m],dtype=float)
 pos={i:k for k,i in enumerate(m)}
 def cost(x):
  prof=W_PROFILE*float(np.sum((x-target)**2));bound=0.0
  for a,b,left,right in seg_bounds:
   if left is not None:bound+=(x[pos[a]]-left)**2
   if right is not None:bound+=(x[pos[b]]-right)**2
  return prof+W_BOUNDARY*bound
 def grad(x):
  g=2.0*W_PROFILE*(x-target)
  for a,b,left,right in seg_bounds:
   if left is not None:g[pos[a]]+=2.0*W_BOUNDARY*(x[pos[a]]-left)
   if right is not None:g[pos[b]]+=2.0*W_BOUNDARY*(x[pos[b]]-right)
  return g
 x0=np.minimum(np.maximum(target,0.0),caps)
 cons=[{'type':'eq','fun':lambda x:float(np.sum(x))-gap,'jac':lambda x:np.ones_like(x)}]
 res=minimize(cost,x0,method='SLSQP',jac=grad,bounds=[(0.0,float(c)) for c in caps],
              constraints=cons,options={'maxiter':500,'ftol':1e-12})
 if not res.success:raise ValueError('补算求解失败：'+str(res.message))
 if np.any(res.x>caps+1e-8) or abs(float(np.sum(res.x))-gap)>1e-6:
  raise ValueError('补算求解失败：约束不满足')
 return res.x,seg_bounds
def _exact_round(vals,caps,target,gap):
 # 四舍五入到ROUND_ND位，并把残差摊回，保证逐小时之和精确等于缺口且不越上限
 vals=np.maximum(0.0,np.minimum(np.array(vals,dtype=float),caps))
 base=np.round(vals,ROUND_ND)
 unit=10**-ROUND_ND;steps=int(round((gap-float(np.sum(base)))/unit))
 if steps:
  # 优先调整最贴近班次曲线且有余量的小时；残差为负时优先下调值较大的小时
  order=sorted(range(len(vals)),key=lambda k:-(target[k]+vals[k])/2.0)
  if steps>0:
   for k in order:
    while steps>0 and base[k]+unit<=caps[k]+1e-12:base[k]=round(base[k]+unit,ROUND_ND);steps-=1
  else:
   for k in order:
    while steps<0 and base[k]-unit>=-1e-12:base[k]=round(base[k]-unit,ROUND_ND);steps+=1
 if steps!=0:
  raise ValueError('上限约束下无法把逐小时之和精确配平到日总量，请放宽缺测小时上限')
 return base
def reconcile(day,daily_total,upper_limits,measured,history):
 # measured: 当日实测 [{hour,kwh}]；history: 目标日之前实测；upper_limits: 缺测小时->上限
 day_dt=datetime.strptime(day,'%Y-%m-%d')
 day_hours=[(day_dt+timedelta(hours=i)).strftime('%Y-%m-%dT%H:00') for i in range(24)]
 upper={_key(h):float(c) for h,c in upper_limits.items()}
 measured_map={}
 for r in measured:
  h=_key(r['hour'])
  if not h.startswith(day):continue
  v=r.get('kwh')
  if v is None or not math.isfinite(float(v)):raise ValueError('实测小时存在缺失耗电，不能参与对账')
  measured_map[h]=float(v)
 conflict=sorted(h for h in upper if h in measured_map)
 if conflict:raise ValueError('以下小时已有实测，不接受上限补值：'+','.join(conflict))
 unknown=sorted(h for h in upper if h not in day_hours)
 if unknown:raise ValueError('上限小时不属于对账日：'+','.join(unknown))
 missing_hours=[h for h in day_hours if h in upper]
 if not missing_hours:raise ValueError('该日没有缺测小时，无需补算')
 measured_sum=round(sum(measured_map.values()),6)
 gap=round(float(daily_total)-measured_sum,6)
 if gap<=0:raise ValueError('日总量须大于当日实测之和，缺口为正才能补算')
 cap_sum=sum(upper[h] for h in missing_hours)
 if gap>cap_sum+1e-9:
  raise ValueError('缺测小时上限之和 %.3f 小于缺口 %.3f，约束无解'%(cap_sum,gap))
 idx_of={h:i for i,h in enumerate(day_hours)}
 measured_pos={idx_of[h]:v for h,v in measured_map.items()}
 missing_pos={idx_of[h] for h in missing_hours}
 profile=build_profile(history,day)
 raw,seg_bounds=optimize(day_hours,measured_pos,missing_pos,upper,profile,gap)
 caps=np.array([upper[h] for h in missing_hours])
 target=np.array([profile[_dt(h).hour] for h in missing_hours])
 final=_exact_round(raw,caps,target,gap)
 filled={h:round(float(v),ROUND_ND) for h,v in zip(missing_hours,final)}
 hours=[]
 for i,h in enumerate(day_hours):
  if h in filled:
   left=measured_pos.get(i-1);right=measured_pos.get(i+1)
   hours.append({'hour':h,'source':'filled','kwh':filled[h],'profile':round(profile[_dt(h).hour],ROUND_ND),
                 'upper':upper[h],'left_measured':left,'right_measured':right,
                 'left_gap':round(filled[h]-left,ROUND_ND) if left is not None else None,
                 'right_gap':round(right-filled[h],ROUND_ND) if right is not None else None})
  else:
   hours.append({'hour':h,'source':'measured','kwh':round(measured_map[h],ROUND_ND),'profile':None,'upper':None,
                 'left_measured':None,'right_measured':None,'left_gap':None,'right_gap':None})
 sum_hours=round(sum(r['kwh'] for r in hours),ROUND_ND)
 boundary_jumps=[]
 for a,b,left,right in seg_bounds:
  if left is not None:boundary_jumps.append({'hour':day_hours[a],'side':'left','jump':round(filled[day_hours[a]]-left,ROUND_ND)})
  if right is not None:boundary_jumps.append({'hour':day_hours[b],'side':'right','jump':round(round(right,ROUND_ND)-filled[day_hours[b]],ROUND_ND)})
 checksum=hashlib.sha256(json.dumps({'day':day,'daily_total':daily_total,'upper':upper_limits,
   'measured':sorted(measured_map.items()),'profile':{str(k):v for k,v in profile.items()}},
   sort_keys=True,ensure_ascii=False).encode()).hexdigest()
 return {'day':day,'daily_total':round(float(daily_total),ROUND_ND),'measured_sum':round(measured_sum,ROUND_ND),
  'gap':round(gap,ROUND_ND),'filled_sum':round(sum(filled.values()),ROUND_ND),'hour_sum':sum_hours,
  'residual':round(float(daily_total)-sum_hours,ROUND_ND),'missing_hours':missing_hours,'hours':hours,
  'profile':{str(k):round(v,ROUND_ND) for k,v in profile.items()},'boundary_jumps':boundary_jumps,
  'weights':{'profile':W_PROFILE,'boundary':W_BOUNDARY},'checksum':checksum,
  'method':'缺测小时在0..上限且总和=日总量-实测之和的约束下最小化：%g·Σ(补值-同班次历史均值)²+%g·Σ每段两端与实测落差²；SLSQP求解后按0.001配平。实测小时不修改，补值来源filled且不进入训练。'%(W_PROFILE,W_BOUNDARY)}
