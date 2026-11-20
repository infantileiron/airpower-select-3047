from datetime import datetime
from pydantic import BaseModel,Field,field_validator,model_validator
from typing import Literal
Feature=Literal['pressure','flow','temperature','machines','sensor_noise']
class Login(BaseModel):email:str;password:str
class SampleInput(BaseModel):
 hour:str
 pressure:float=Field(ge=0,le=20,allow_inf_nan=False)
 flow:float=Field(ge=0,le=1000,allow_inf_nan=False)
 temperature:float=Field(ge=-30,le=100,allow_inf_nan=False)
 machines:int=Field(ge=0,le=20)
 sensor_noise:float=Field(ge=-100,le=100,allow_inf_nan=False)
 kwh:float=Field(ge=0,le=10000,allow_inf_nan=False)
 note:str=Field(default='',max_length=1000)
 @field_validator('hour')
 @classmethod
 def hourly(cls,v):
  d=datetime.fromisoformat(v)
  if d.tzinfo or d.minute or d.second or d.microsecond:raise ValueError('使用工厂本地整点小时，不带时区偏移')
  return d.strftime('%Y-%m-%dT%H:00')
class RunInput(BaseModel):
 name:str=Field(min_length=2,max_length=100)
 features:list[Feature]=Field(default=['pressure','flow','temperature','machines'],min_length=1,max_length=5)
 alphas:list[float]=Field(default=[.01,.1,1.,10.,100.],min_length=1,max_length=8)
 @field_validator('features','alphas')
 @classmethod
 def unique(cls,v):
  if len(v)!=len(set(v)):raise ValueError('候选项不能重复')
  return v
 @field_validator('alphas')
 @classmethod
 def positive(cls,v):
  import math
  if any(not math.isfinite(a) or a<=0 or a>10000 for a in v):raise ValueError('alpha必须为0到10000之间的有限正数')
  return v
class ReviewInput(BaseModel):
 run_id:int=Field(gt=0)
 title:str=Field(min_length=2,max_length=100)
 finding:str=Field(min_length=8,max_length=2000)
 action:str=Field(min_length=8,max_length=2000)
class ReconInput(BaseModel):
 day:str
 daily_total:float=Field(gt=0,le=1_000_000,allow_inf_nan=False)
 upper_limits:dict[str,float]=Field(min_length=1,max_length=24)
 @field_validator('day')
 @classmethod
 def day_only(cls,v):
  d=datetime.fromisoformat(v)
  if d.tzinfo or d.hour or d.minute or d.second or d.microsecond:raise ValueError('day使用本地日期，格式YYYY-MM-DD')
  return d.strftime('%Y-%m-%d')
 @field_validator('upper_limits')
 @classmethod
 def limits_valid(cls,v):
  import math
  seen=set()
  for hour,cap in v.items():
   d=datetime.fromisoformat(hour)
   key=d.strftime('%Y-%m-%dT%H:00')
   if d.tzinfo or d.minute or d.second or d.microsecond:raise ValueError('缺测小时使用本地整点，不带时区偏移')
   if key in seen:raise ValueError('缺测小时重复')
   seen.add(key)
   if not math.isfinite(cap) or cap<0 or cap>100000:raise ValueError('缺测小时上限须为0到100000之间的有限数')
  return {k:v[k] for k in sorted(v)}
