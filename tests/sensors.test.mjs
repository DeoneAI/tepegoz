import test from 'node:test';
import assert from 'node:assert/strict';
import {probeSensors} from '../web/sensors.js';

function environment({rotation,permission='granted',generic=false}={}){
  const events=new Map();let time=0,stopped=false;
  const host={isSecureContext:true,performance:{now:()=>time},
    navigator:{permissions:{query:async()=>({state:permission})},geolocation:{}},
    addEventListener:(name,fn)=>events.set(name,fn),removeEventListener:name=>events.delete(name),
    setTimeout:callback=>{for(let i=0;i<5;i++){time=i*20;events.get('devicemotion')?.({accelerationIncludingGravity:{x:0,y:0,z:9.81},rotationRate:rotation});}callback();}};
  if(generic)host.Gyroscope=class{constructor(){this.x=0;this.y=0;this.z=0;}addEventListener(name,fn){if(name==='reading')this.read=fn;}start(){this.read();}stop(){stopped=true;}};
  return {host,events,get stopped(){return stopped;}};
}
test('preflight detects real zero-valued gyro, measures rates and removes listeners',async()=>{
  const env=environment({rotation:{alpha:0,beta:0,gamma:0}});const report=await probeSensors({host:env.host,durationMs:100});
  assert.equal(report.sensors.gyroscope.state,'available');assert.equal(report.sensors.gyroscope.measured_hz,50);assert.equal(env.events.size,0);
});
test('missing gyro is explicitly ambiguous; permission denial is distinct',async()=>{
  const noGyro=await probeSensors({host:environment().host});
  assert.equal(noGyro.sensors.accelerometer.state,'available');assert.equal(noGyro.sensors.gyroscope.state,'unavailable-or-blocked');
  const denied=await probeSensors({host:environment({permission:'denied'}).host});assert.equal(denied.sensors.gyroscope.state,'permission-denied');
});
test('generic gyro fallback reports its source and stops the test sensor',async()=>{
  const env=environment({generic:true});const report=await probeSensors({host:env.host});
  assert.equal(report.sensors.gyroscope.source,'GenericSensor.Gyroscope');assert.equal(report.sensors.gyroscope.state,'available');assert.equal(env.stopped,true);
});
