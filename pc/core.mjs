export const mono = () => Number(process.hrtime.bigint()) / 1e6;
export const ns = ms => String(Math.round(ms * 1e6));
export const finiteVector = v => v && ['x','y','z'].every(k => typeof v[k] === 'number' && Number.isFinite(v[k]));
export function validateSample(s) {
  if (!s || !['accelerometer','linear_acceleration','gyroscope','gnss'].includes(s.sensor_type)) return false;
  if(!/^[a-f0-9]{24}$/.test(s.session_id||'')||typeof s.quality!=='string'||!s.quality)return false;
  if(s.units!==({accelerometer:'m_s2',linear_acceleration:'m_s2',gyroscope:'rad_s',gnss:'deg_m_mps'})[s.sensor_type])return false;
  if(s.frame_axes!==(s.sensor_type==='gnss'?'wgs84_geodetic':'phone_portrait_x_right_y_up_z_out'))return false;
  if (!Number.isSafeInteger(s.sequence_id) || s.sequence_id < 0 || !/^\d{1,18}$/.test(s.timestamp_ns)) return false;
  if (s.sensor_type === 'gnss') return s.values && Number.isFinite(s.values.latitude) && Math.abs(s.values.latitude)<=90 && Number.isFinite(s.values.longitude) && Math.abs(s.values.longitude)<=180 && Number.isFinite(s.accuracy_m) && s.accuracy_m>=0;
  return finiteVector(s.values);
}
export function nearest(samples, target, maxGapMs = 100) {
  if (!samples.length) return null;
  let lo=0, hi=samples.length;
  while(lo<hi) { const mid=(lo+hi)>>>1; if(Number(samples[mid].timestamp_ns)<target) lo=mid+1; else hi=mid; }
  const candidates=[samples[lo-1],samples[lo]].filter(Boolean);
  const best=candidates.reduce((a,b)=>Math.abs(Number(a.timestamp_ns)-target)<=Math.abs(Number(b.timestamp_ns)-target)?a:b);
  const delta=(Number(best.timestamp_ns)-target)/1e6;
  return Math.abs(delta)<=maxGapMs ? {...best,alignment_delta_ms:delta} : null;
}
export function percentile(values,p) { if(!values.length)return null; const a=[...values].sort((a,b)=>a-b);return a[Math.min(a.length-1,Math.floor((a.length-1)*p))]; }
export function clockEstimate(t0,t1,t2,t3) {
  return { offset_ms: ((t1-t0)+(t2-t3))/2, rtt_ms: Math.max(0,(t3-t0)-(t2-t1)) };
}
export function sequenceUpdate(counters,key,seq) {
  const last=counters.last[key];
  if (last!==undefined && seq<=last) return false;
  const gaps=last===undefined?seq:Math.max(0,seq-last-1);
  counters.gaps+=gaps;
  counters.by_stream??={};counters.by_stream[key]=(counters.by_stream[key]||0)+gaps;
  counters.last[key]=seq;
  return true;
}
export function measuredRate(timing) {
  if(!timing||timing.count<2||timing.last_ns<=timing.first_ns)return null;
  return (timing.count-1)*1e9/Number(timing.last_ns-timing.first_ns);
}
