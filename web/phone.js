import {probeSensors,finiteVector} from './sensors.js';
import {$,fmt,stamp,post,request,validateServer} from './common.js';
const hash=new URLSearchParams(location.hash.slice(1));
let pairing=null;
try{if(hash.has('key')){pairing={server:validatePairingServer(hash.get('server'),hash.get('mode')),session:hash.get('session'),key:hash.get('key'),mode:hash.get('mode')||'tunnel'};if(!/^[a-f0-9]{24}$/.test(pairing.session)||!/^[a-f0-9]{48}$/.test(pairing.key))throw new Error('Invalid link');sessionStorage.setItem('sensorlink-pairing',JSON.stringify(pairing));history.replaceState(null,'',location.pathname);}else{pairing=JSON.parse(sessionStorage.getItem('sensorlink-pairing')||'null');if(pairing)validatePairingServer(pairing.server,pairing.mode);}}catch{pairing=null;}
let running=false,starting=false,stream=null,wake=null,geo=null,flushTimer=null,syncTimer=null,statsTimer=null,frameHandle=null;
let buffer=[],sendingFrame=false,sequence={},frameIndex=0,storedFrames=0,dropped=0,droppedSamples=0,lastFrameAt=-Infinity,startTime=0,accelEvents=0,lastAccel=null,lastGyro=null,clock=null;
let sampleUpload=null,frameUpload=null,sessionEnded=false;
let accelValid=false,gyroValid=false,hasGNSS=false,genericGyro=null,capabilities=null,preflightAccepted=false;
const base=()=>`/api/sessions/${pairing.session}`;
const send=(route,value)=>post(pairing.server,pairing.key,base()+route,value);
const status=text=>$('phone-status').textContent=text;
if(!pairing){status('Open a fresh pairing link from the PC dashboard to start.');$('start-capture').disabled=true;}else{status('Paired link ready. Allow camera and motion access to begin.');}
if(!isSecureContext){status('HTTPS is required for camera and sensor access.');$('start-capture').disabled=true;}
function queue(type,values,units,timestampMs,extra={}){if(!running)return;const sequence_id=sequence[type]??0;sequence[type]=sequence_id+1;buffer.push({session_id:pairing.session,sensor_type:type,timestamp_ns:stamp(timestampMs),sequence_id,frame_axes:'phone_portrait_x_right_y_up_z_out',values,units,quality:'browser_accuracy_unavailable',...extra});if(buffer.length>2000){const removed=buffer.length-2000;buffer.splice(0,removed);droppedSamples+=removed;}}
const valid=finiteVector;
function eventTime(e){return Number.isFinite(e.timeStamp)&&e.timeStamp>=0&&Math.abs(e.timeStamp-performance.now())<60000?e.timeStamp:performance.now();}
function motion(e){if(!running)return;const t=eventTime(e);if(valid(e.accelerationIncludingGravity)){accelValid=true;accelEvents++;lastAccel=e.accelerationIncludingGravity;queue('accelerometer',{x:lastAccel.x,y:lastAccel.y,z:lastAccel.z},'m_s2',t,{timestamp_source:'browser_event_time',includes_gravity:true});}if(valid(e.acceleration))queue('linear_acceleration',{x:e.acceleration.x,y:e.acceleration.y,z:e.acceleration.z},'m_s2',t,{timestamp_source:'browser_event_time',includes_gravity:false});const r=e.rotationRate;if(r&&['alpha','beta','gamma'].every(k=>typeof r[k]==='number'&&Number.isFinite(r[k]))){gyroValid=true;if(genericGyro){genericGyro.stop();genericGyro=null;}const k=Math.PI/180;lastGyro={x:r.beta*k,y:r.gamma*k,z:r.alpha*k};queue('gyroscope',lastGyro,'rad_s',t,{timestamp_source:'browser_event_time'});}}
async function syncClock(){if(!pairing)return;const estimates=[];for(let i=0;i<5;i++){const t0=performance.now();const r=await send('/sync',{t0});if(!r.recording){await stop();status('The session was stopped on the PC. Create a new session to continue.');return;}const t3=performance.now();estimates.push({offset_ms:((r.t1-t0)+(r.t2-t3))/2,rtt_ms:Math.max(0,(t3-t0)-(r.t2-r.t1)),phone_ms:(t0+t3)/2});}estimates.sort((a,b)=>a.rtt_ms-b.rtt_ms);clock=estimates[0];await send('/clock',{...clock,method:'minimum RTT of 5 NTP-style exchanges',samples:estimates});}
function flush(){
  if(sampleUpload)return sampleUpload;
  if(!buffer.length||sessionEnded)return Promise.resolve();
  const batch=buffer.splice(0,500);
  sampleUpload=Promise.resolve().then(async()=>{
    try{await send('/samples',{samples:batch,dropped_frames:dropped,dropped_samples:droppedSamples});}
    catch(e){
      buffer.unshift(...batch);
      if(buffer.length>2000){droppedSamples+=buffer.length-2000;buffer.length=2000;}
      if(e.status===409||e.status===410){sessionEnded=true;await stop(false);status('Session ended. Remaining telemetry could not be uploaded. Create a new session on the PC.');}
      else status('Upload interrupted. Retrying a bounded telemetry queue…');
    }
  }).finally(()=>{sampleUpload=null;});
  return sampleUpload;
}
const canvas=document.createElement('canvas');
async function uploadFrame(index,meta){
  try{
    const video=$('phone-video');const width=Number($('target-width').value);
    canvas.width=Math.min(width,video.videoWidth);canvas.height=Math.round(canvas.width*video.videoHeight/video.videoWidth);
    canvas.getContext('2d',{alpha:false}).drawImage(video,0,0,canvas.width,canvas.height);
    const t=typeof meta.captureTime==='number'?meta.captureTime:typeof meta.presentationTime==='number'?meta.presentationTime:performance.now();
    const source=typeof meta.captureTime==='number'?'captureTime':typeof meta.presentationTime==='number'?'presentationTime_estimate':'callback_estimate';
    const payload={frame_index:index,timestamp_ns:stamp(t),timestamp_source:source,media_time_s:meta.mediaTime??video.currentTime,width:canvas.width,height:canvas.height};
    const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.75));if(!blob)throw new Error('JPEG encoding failed');
    await request(pairing.server,pairing.key,base()+'/frame',{method:'POST',headers:{'Content-Type':'image/jpeg','X-Frame-Meta':JSON.stringify(payload)},body:blob});storedFrames++;
  }catch(e){dropped++;if(e.status===409||e.status===410){await stop(false);status('Recording ended on the PC.');}else status('Frame upload failed. Check your connection; skipped frames are counted.');}
}
function frame(now,meta={}){
  if(!running)return;scheduleFrame();const interval=1000/Number($('target-fps').value);
  if(now-lastFrameAt<interval-2)return;
  lastFrameAt=now;const index=frameIndex++;
  if(sendingFrame){dropped++;return;}
  sendingFrame=true;
  frameUpload=uploadFrame(index,meta).finally(()=>{sendingFrame=false;frameUpload=null;});
  return frameUpload;
}
function scheduleFrame(){const video=$('phone-video');frameHandle=video.requestVideoFrameCallback?video.requestVideoFrameCallback(frame):requestAnimationFrame(now=>frame(now));}
async function getWake(){try{if('wakeLock'in navigator)wake=await navigator.wakeLock.request('screen');}catch{}}
function updateStats(){const elapsed=Math.max(.001,(performance.now()-startTime)/1000);$('phone-frames').textContent=storedFrames;$('phone-drops').textContent=dropped;$('phone-hz').textContent=fmt(accelEvents/elapsed)+' Hz';const cap=$('phone-capabilities');cap.replaceChildren();for(const [name,present]of [['Accelerometer',accelValid],['Gyroscope',gyroValid],['GNSS',hasGNSS]]){const d=document.createElement('div');d.textContent=`${name}: ${present?'receiving real samples':elapsed<4?'checking…':'unavailable / permission blocked'}`;cap.append(d);}if(elapsed>4&&!gyroValid)status('Capture active. Gyroscope is unavailable or blocked: the full Week 01 IMU gate is not yet satisfied.');}
async function startCapture(){if(running||starting||!pairing)return;starting=true;$('start-capture').disabled=true;try{if(!capabilities){await checkSensors();return;}if(capabilities.sensors.gyroscope.state!=='available'&&!preflightAccepted){showSensorResult();return;}status('Checking the collector and synchronizing clocks…');await syncClock();if(!clock)throw new Error('Session is not recording. Create a fresh session.');const width=Number($('target-width').value);stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:width},height:{ideal:Math.round(width*9/16)},frameRate:{ideal:30,max:30}},audio:false});const video=$('phone-video');video.srcObject=stream;await video.play();const settings=stream.getVideoTracks()[0].getSettings();await send('/device',{user_agent:navigator.userAgent,platform:navigator.platform,camera:settings,requested_jpeg_fps:Number($('target-fps').value),requested_width:width,clock_origin_ms:performance.timeOrigin,client:'browser-v2',connection_mode:pairing.mode,capabilities,sensor_accuracy:'not exposed by DeviceMotionEvent'});
  running=true;startTime=performance.now();$('phone-camera-empty').hidden=true;$('start-capture').hidden=true;$('stop-capture').hidden=false;$('target-fps').disabled=true;$('target-width').disabled=true;$('enable-gnss').disabled=true;$('phone-state').textContent='● LIVE · SENDING';$('phone-resolution').textContent=`${settings.width}×${settings.height}`;window.addEventListener('devicemotion',motion);startGenericGyro();$('check-sensors').disabled=true;await getWake();
  if($('enable-gnss').checked&&navigator.geolocation)geo=navigator.geolocation.watchPosition(pos=>{hasGNSS=true;const t=performance.now()-(Date.now()-pos.timestamp);queue('gnss',{latitude:pos.coords.latitude,longitude:pos.coords.longitude,altitude:pos.coords.altitude,speed:pos.coords.speed,heading:pos.coords.heading},'deg_m_mps',Math.max(0,t),{accuracy_m:pos.coords.accuracy,altitude_accuracy_m:pos.coords.altitudeAccuracy,frame_axes:'wgs84_geodetic',quality:'browser_geolocation_accuracy',timestamp_source:'geolocation_wall_to_monotonic_estimate'});},e=>status('GPS unavailable: '+e.message),{enableHighAccuracy:true,maximumAge:0,timeout:15000});
  flushTimer=setInterval(flush,100);syncTimer=setInterval(()=>syncClock().catch(()=>status('Clock resynchronization failed; last estimate retained.')),15000);statsTimer=setInterval(updateStats,1000);scheduleFrame();status('Streaming to your PC. Keep this page visible.');
}catch(e){await stop(false);status(e.message==='Failed to fetch'?'Collector unreachable. Check tunnel, PC server, and allowed origin.':e.message);}finally{starting=false;$('start-capture').disabled=false;}}
$('start-capture').onclick=startCapture;
async function stop(flushPending=true){running=false;try{genericGyro?.stop();}catch{}genericGyro=null;window.removeEventListener('devicemotion',motion);clearInterval(flushTimer);clearInterval(syncTimer);clearInterval(statsTimer);if(geo!==null){navigator.geolocation.clearWatch(geo);geo=null;}const v=$('phone-video');if(frameHandle!==null){if(v.cancelVideoFrameCallback)v.cancelVideoFrameCallback(frameHandle);else cancelAnimationFrame(frameHandle);}stream?.getTracks().forEach(t=>t.stop());stream=null;v.srcObject=null;try{await wake?.release();}catch{}wake=null;
  if(flushPending){
    $('stop-capture').disabled=true;status('Stopping capture and finishing frame and telemetry uploads…');
    // Finish the JPEG already drawn before the camera stream was released.
    if(frameUpload)await frameUpload;
    // An in-flight request owns samples outside buffer. Wait for its ACK or requeue before draining.
    if(sampleUpload)await sampleUpload;
    let tries=0;while(buffer.length&&!sessionEnded&&tries++<4)await flush();
  }
  $('stop-capture').hidden=!buffer.length||sessionEnded;$('stop-capture').disabled=false;$('stop-capture').textContent='Retry remaining telemetry uploads';
  $('start-capture').hidden=false;$('start-capture').textContent='Open a new session to capture again';$('start-capture').disabled=true;$('phone-state').textContent='● STOPPED';
  return !buffer.length;
}
$('stop-capture').onclick=async()=>{
  const complete=await stop();
  status(complete?'Phone capture stopped. Use Stop & save on the PC to finalize this session.':sessionEnded?`Session ended with ${buffer.length} telemetry samples not uploaded. Create a new session on the PC.`:`Capture stopped with ${buffer.length} telemetry samples still queued. Keep this page open, restore the connection, then tap Retry remaining telemetry uploads before saving on the PC.`);
};
document.addEventListener('visibilitychange',()=>{if(document.hidden&&running)status('Page hidden: capture may pause. Return to this page to continue.');else if(running)getWake();});window.addEventListener('pagehide',()=>{running=false;stream?.getTracks().forEach(t=>t.stop());});

function validatePairingServer(server,mode){
 const local=mode==='usb-adb'&&['localhost','127.0.0.1'].includes(location.hostname);
 const origin=validateServer(server,{local});
 if(local&&origin!==location.origin)throw new Error('USB pairing must use the same localhost origin as this phone page.');
 return origin;
}
function startGenericGyro(){
 if(capabilities?.sensors.gyroscope.source!=='GenericSensor.Gyroscope'||!window.Gyroscope)return;
 try{
  genericGyro=new Gyroscope({frequency:60});
  genericGyro.addEventListener('reading',()=>{if(running&&valid(genericGyro)){gyroValid=true;lastGyro={x:genericGyro.x,y:genericGyro.y,z:genericGyro.z};queue('gyroscope',lastGyro,'rad_s',genericGyro.timestamp??performance.now(),{timestamp_source:'generic_sensor_monotonic'});}});
  genericGyro.addEventListener('error',()=>status('Gyroscope access was lost. Existing records are kept; check sensor permissions.'));
  genericGyro.start();
 }catch(error){status('Gyroscope could not start: '+error.message);}
}
function showSensorResult(){
 const rows=$('sensor-check-results');rows.replaceChildren();
 for(const [name,value]of Object.entries(capabilities.sensors)){
  const row=document.createElement('div');row.textContent=`${name}: ${value.state} · ${fmt(value.measured_hz)} Hz · ${value.source}`;rows.append(row);
 }
 const available=capabilities.sensors.gyroscope.state==='available';
 $('sensor-dialog-title').textContent=available?'Sensor check complete':'Gyroscope data is not available';
 $('sensor-check-warning').textContent=available?'Real gyro samples were observed. Achieved capture rates are measured again during recording.':'This browser returned no usable gyro samples. The sensor may be absent, blocked, or not exposed by this browser. Check Motion sensors permission or another browser. Continuing records available sensors; it does not pass the full IMU gate.';
 $('sensor-continue').textContent=available?'Continue to capture':'Continue with available sensors';
 if(!$('sensor-dialog').open)$('sensor-dialog').showModal();
}
async function checkSensors(){
 if(running)return;const button=$('check-sensors');button.disabled=true;
 try{status('Checking real sensor readings before recording…');capabilities=await probeSensors();preflightAccepted=false;showSensorResult();status('Sensor check complete. Review the result before starting capture.');}
 catch(error){status('Sensor check could not finish: '+error.message);}finally{button.disabled=false;}
}
$('check-sensors').onclick=checkSensors;
$('sensor-close').onclick=()=>$('sensor-dialog').close();
$('sensor-continue').onclick=()=>{preflightAccepted=true;$('sensor-dialog').close();startCapture();};
