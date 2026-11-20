/** @typedef {{id:number,hour:string,pressure:number,flow:number,temperature:number,machines:number,sensor_noise:number,kwh:number,note:string}} Sample */
/** @typedef {{id:number,name:string,features:string[],alphas:number[],state:string,result:object,error:string}} Run */
/** @typedef {{id:number,run_id:number,title:string,finding:string,action:string,status:string}} Review */
/** @typedef {{id:number,day:string,daily_total:number,upper_limits:Object<string,number>,active_version:?number,status:string,active:?ReconVersion,versions:ReconVersionSummary[]}} ReconDay */
/** @typedef {{id:number,recon_id:number,version_no:number,state:string,input_snapshot:object,result:?ReconResult,error:string,created_by:string,created:string,reason:string}} ReconVersion */
/** @typedef {{version_no:number,state:string,error:string,created:string,reason:string}} ReconVersionSummary */
/** @typedef {{day:string,daily_total:number,measured_sum:number,gap:number,filled_sum:number,hour_sum:number,residual:number,missing_hours:string[],hours:ReconHour[],profile:Object<string,number>,boundary_jumps:object[],weights:{profile:number,boundary:number},checksum:string,method:string}} ReconResult */
/** @typedef {{hour:string,source:'measured'|'filled',kwh:number,profile:?number,upper:?number,left_measured:?number,right_measured:?number,left_gap:?number,right_gap:?number}} ReconHour */
