export const finiteVector=value=>value&&['x','y','z'].every(key=>typeof value[key]==='number'&&Number.isFinite(value[key]));
const finiteRotation=value=>value&&['alpha','beta','gamma'].every(key=>typeof value[key]==='number'&&Number.isFinite(value[key]));

// A browser observation cannot prove that a physical sensor is absent.
export async function probeSensors({host=globalThis,durationMs=1800}={}) {
  const stats={accelerometer:[],linear_acceleration:[],gyroscope:[]};
  const permissions={};let generic=null,genericError=null;
  const now=()=>host.performance.now();
  if(host.DeviceMotionEvent?.requestPermission){
    const permission=await host.DeviceMotionEvent.requestPermission();
    permissions.motion=permission;
  }
  const motion=event=>{
    const time=now();
    if(finiteVector(event.accelerationIncludingGravity))stats.accelerometer.push(time);
    if(finiteVector(event.acceleration))stats.linear_acceleration.push(time);
    if(finiteRotation(event.rotationRate))stats.gyroscope.push(time);
  };
  const genericTimes=[];
  const onGeneric=()=>{if(finiteVector(generic))genericTimes.push(now());};
  host.addEventListener('devicemotion',motion);
  try {
    if(host.Gyroscope&&permissions.motion!=='denied'){
      try{generic=new host.Gyroscope({frequency:60});generic.addEventListener('reading',onGeneric);generic.addEventListener('error',event=>{genericError=event.error?.name||'SensorError';});generic.start();}
      catch(error){genericError=error.name;}
    }
    await Promise.all(['accelerometer','gyroscope','geolocation','camera'].map(async name=>{
      try{permissions[name]=(await host.navigator.permissions.query({name})).state;}catch{permissions[name]='unknown';}
    }));
    await new Promise(resolve=>host.setTimeout(resolve,durationMs));
  }finally{host.removeEventListener('devicemotion',motion);try{generic?.stop();}catch{}}
  const result={checked_at:new Date().toISOString(),secure_context:host.isSecureContext,permissions,sensors:{}};
  for(const [name,motionTimes]of Object.entries(stats)){
    const genericOnly=name==='gyroscope'&&genericTimes.length>0&&!motionTimes.length;
    const times=genericOnly?genericTimes:motionTimes;const count=times.length;
    const denied=permissions.motion==='denied'||permissions[name]==='denied';
    result.sensors[name]={state:count?'available':denied?'permission-denied':!host.isSecureContext?'insecure-context':'unavailable-or-blocked',
      samples:count,measured_hz:times.length>1&&times.at(-1)>times[0]?(times.length-1)*1000/(times.at(-1)-times[0]):null,
      source:genericOnly?'GenericSensor.Gyroscope':'DeviceMotionEvent',error:name==='gyroscope'?genericError:null};
  }
  result.sensors.gnss={state:!host.navigator.geolocation?'api-unavailable':permissions.geolocation==='denied'?'permission-denied':'not-tested',measured_hz:null,source:'Geolocation.watchPosition'};
  return result;
}
