import test from 'node:test';
import assert from 'node:assert/strict';
import { nearest, clockEstimate, validateSample, sequenceUpdate, percentile, measuredRate } from '../pc/core.mjs';
test('clock exchange removes server processing time and preserves offset sign',()=>{
  assert.deepEqual(clockEstimate(100,112,114,106),{offset_ms:10,rtt_ms:4});
});
test('nearest alignment respects timestamp ordering and rejects data gaps',()=>{
  const samples=[100,120,160].map(t=>({timestamp_ns:String(t*1e6),values:{x:t}}));
  assert.equal(nearest(samples,128e6).values.x,120);
  assert.equal(nearest(samples,140e6).values.x,120);
  assert.equal(nearest(samples,400e6),null);
  assert.equal(nearest([],100e6),null);
});
test('sensor schema rejects unavailable/nonfinite axes and invalid timestamps',()=>{
  const s={session_id:'0123456789abcdef01234567',sensor_type:'gyroscope',timestamp_ns:'12345',sequence_id:0,values:{x:0,y:1,z:2},units:'rad_s',frame_axes:'phone_portrait_x_right_y_up_z_out',quality:'browser_accuracy_unavailable'};
  assert.equal(validateSample(s),true);
  assert.equal(validateSample({...s,values:{x:null,y:1,z:2}}),false);
  assert.equal(validateSample({...s,timestamp_ns:'NaN'}),false);
  assert.equal(validateSample({...s,sequence_id:-1}),false);
  assert.equal(validateSample({...s,units:'deg_s'}),false);
  assert.equal(validateSample({...s,frame_axes:'vehicle'}),false);
});
test('sequence gaps include initial loss and duplicates do not inflate counts',()=>{
  const c={last:{},gaps:0};
  assert.equal(sequenceUpdate(c,'frame',2),true);assert.equal(c.gaps,2);
  assert.equal(sequenceUpdate(c,'frame',2),false);assert.equal(c.gaps,2);
  assert.equal(sequenceUpdate(c,'frame',5),true);assert.equal(c.gaps,4);
  assert.equal(sequenceUpdate(c,'gyro',0),true);assert.equal(c.gaps,4);
});
test('empty latency statistics remain unavailable',()=>{assert.equal(percentile([],.95),null);assert.equal(percentile([3,1,2],.5),2);});
test('sensor Hz uses the observed phone timestamp span, independent of session setup time',()=>{
  assert.equal(measuredRate({count:3,first_ns:1000000000000n,last_ns:1000040000000n}),50);
  assert.equal(measuredRate({count:1,first_ns:1n,last_ns:1n}),null);
  assert.equal(measuredRate(undefined),null);
});
