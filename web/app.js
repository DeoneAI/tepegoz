import {$,fmt,request,post,validateServer,nearestSample} from './common.js';
let config=JSON.parse(sessionStorage.getItem('sensorlink-connection')||'null');
let active=null,online=false,polling=false,currentSensor='accelerometer',frameURL=null,lastFrame=-1,pairURL=null;
let replay=null,replayPlaying=false,replayTimer=null,replayURL=null,replayVersion=0,replayAnchor=null;
const toast=message=>{$('toast').textContent=message;$('toast').classList.add('show');clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').classList.remove('show'),4500);};
const dashboardServer=server=>['localhost','127.0.0.1'].includes(location.hostname)?location.origin:server;
const api=(route,options)=>{if(!config)throw new Error('Connect your PC collector first.');return request(dashboardServer(config.server),config.token,route,options);};
const apiPost=(route,value)=>post(dashboardServer(config.server),config.token,route,value);
function setOnline(value){online=value;$('collector-status').classList.toggle('online',value);$('collector-status').lastChild.textContent=value?' Collector online':' Collector offline';$('step-server').classList.toggle('done',value);$('check-server').textContent=value?'✓':'—';}
function page(name){for(const x of ['live','sessions','guide'])$(x+'-page').hidden=x!==name;document.querySelectorAll('[data-page]').forEach(x=>x.classList.toggle('active',x.dataset.page===name));$('crumb').textContent={live:'Live acquisition',sessions:'Session library',guide:'Setup & protocol'}[name];if(name==='sessions')loadSessions();}
document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>page(b.dataset.page));
document.querySelectorAll('.close-dialog').forEach(b=>b.onclick=()=>b.closest('dialog').close());
document.querySelectorAll('dialog').forEach(d=>d.addEventListener('click',e=>{if(e.target===d){const r=d.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)d.close();}}));
function settings(){$('connection-mode').value=config?.mode||'tunnel';$('usb-setup').hidden=$('connection-mode').value!=='usb-adb';$('server-url').value=config?.server||((location.hostname==='localhost'||location.hostname==='127.0.0.1')?location.origin:'');$('server-token').value=config?.token||'';$('connection-error').textContent='';$('settings-dialog').showModal();}
$('settings-btn').onclick=settings;
$('connection-form').onsubmit=async e=>{e.preventDefault();const button=e.submitter;button.disabled=true;try{const mode=$('connection-mode').value;const token=$('server-token').value.trim();let server;
if(mode==='usb-adb'){
 if(!['localhost','127.0.0.1'].includes(location.hostname))throw new Error('For USB, open http://localhost:8787 on this PC.');
 const connected=await request(location.origin,token,'/api/usb',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({serial:$('usb-device').value}),signal:AbortSignal.timeout(45000)}).then(r=>r.json());server=connected.phone_origin;
}else{server=validateServer($('server-url').value.trim());}
await request(dashboardServer(server),token,'/api/sessions');config={server,token,mode};sessionStorage.setItem('sensorlink-connection',JSON.stringify(config));setOnline(true);active=null;lastFrame=-1;$('settings-dialog').close();toast('PC collector connected. Create a session to pair your phone.');await loadSessions();}catch(e){$('connection-error').textContent=e.message==='Failed to fetch'?'Cannot reach the collector. Check HTTPS URL, tunnel, and ALLOWED_ORIGINS.':e.message;}finally{button.disabled=false;}};
function create(){if(!config||!online)return settings();if(active?.recording){toast('Stop & save the current session before creating another.');return;}if(config.mode!=='usb-adb'&&config.server.startsWith('http:'))toast('Use the HTTPS tunnel URL to pair a physical phone. Localhost works only on this PC.');$('create-dialog').showModal();}
['new-session','pair-create','pair-shortcut'].forEach(x=>$(x).onclick=create);
$('create-form').onsubmit=async e=>{e.preventDefault();e.submitter.disabled=true;try{active=await apiPost('/api/sessions',{name:$('new-name').value,connection_mode:config.mode||'tunnel'});lastFrame=-1;const link=new URL('/phone.html',['localhost','127.0.0.1'].includes(location.hostname)?config.server:location.origin);link.hash=new URLSearchParams({server:config.server,session:active.id,key:active.phone_key,mode:config.mode||'tunnel'}).toString();pairURL=link.href;$('phone-link').value=pairURL;$('connection-mode-tag').textContent=config.mode==='usb-adb'?'USB / ADB':'HTTPS';$('pairing-empty').hidden=true;$('pairing-ready').hidden=false;const box=$('qr-wrap');box.replaceChildren();try{const qr=window.qrcode();qr.addData(pairURL);qr.make();box.innerHTML=qr.createSvgTag();}catch{const div=document.createElement('div');div.className='qr-fallback';div.textContent='Pairing link ready ↗\nUse Copy or Share below';box.append(div);}$('create-dialog').close();page('live');render(active);toast('Session created. Open the link on your phone.');}catch(e){toast(e.message);}finally{e.submitter.disabled=false;}};
$('copy-link').onclick=async()=>{try{await navigator.clipboard.writeText(pairURL);toast('Pairing link copied.');}catch{$('phone-link').select();toast('Select and copy the pairing link.');}};
$('share-link').onclick=async()=>{try{if(navigator.share)await navigator.share({title:'Sensorlink · Galaxy A15 capture',url:pairURL});else await navigator.clipboard.writeText(pairURL);toast('Pairing link ready to share.');}catch(e){if(e.name!=='AbortError')toast('Use Copy link to share this session.');}};
$('stop-session').onclick=async()=>{if(!active)return;try{active=await apiPost(`/api/sessions/${active.id}/stop`,{});render(active);toast('Session saved to your PC. Replay is ready.');}catch(e){toast(e.message);}};
$('replay-current').onclick=()=>active&&openReplay(active.id);
function render(s){const m=s.metrics||{};$('session-name').textContent=s.name;$('session-id').textContent=s.id;$('session-duration').textContent=`${String(Math.floor((m.duration_s||0)/60)).padStart(2,'0')}:${String(Math.floor((m.duration_s||0)%60)).padStart(2,'0')}`;
  $('fps').textContent=m.frames?fmt(m.fps):'—';$('hz').textContent=m.samples?fmt(m.imu_hz):'—';$('latency').textContent=fmt(m.latency_p95_ms,0);$('gaps').textContent=m.sequence_gaps??'—';$('dropped').textContent=m.phone_dropped_frames??0;
  const live=m.phone_connected;['sidebar-dot','session-dot'].forEach(id=>$(id).classList.toggle('online',!!live));$('record-dot').classList.toggle('online',!!s.recording&&!!live);$('record-label').textContent=s.recording?(live?'Recording to PC':'Waiting for phone'):'Saved to PC';$('stop-session').disabled=!s.recording;$('replay-current').disabled=!m.frames;$('feed-status').textContent=!s.recording?'● SESSION SAVED':live?'● LIVE · RECORDING':'● AWAITING DEVICE';
  $('step-phone').classList.toggle('done',!!live);$('check-phone').textContent=live?'✓':'—';$('step-stream').classList.toggle('done',!!m.samples&&!!m.frames);$('check-stream').textContent=m.samples&&m.frames?'✓':'—';
  $('clock-offset').textContent=fmt(m.clock_offset_ms,2)+' ms';$('clock-rtt').textContent=fmt(m.clock_rtt_ms,1)+' ms';$('clock-error').textContent='± '+fmt(m.clock_uncertainty_ms,1)+' ms';$('clock-drift').textContent=fmt(m.clock_drift_ppm,1)+' ppm';$('sync-tag').textContent=s.clock?'ESTIMATED':'UNSYNCED';$('sync-tag').classList.toggle('accent-tag',!!s.clock);
  const sample=s.latest?.[currentSensor];['x','y','z'].forEach(k=>$('axis-'+k).textContent=fmt(sample?.values?.[k],3));$('sensor-status').textContent=sample?`${fmt(m.per_sensor_hz?.[currentSensor])} Hz · browser accuracy unknown`:'No measurements / sensor may be unavailable';
  renderInventory(s);
  drawChart(s.telemetry?.filter(x=>x.sensor_type===currentSensor).slice(-150)||[]);
  if(s.last_frame){const f=s.last_frame;$('frame-number').textContent='FRAME '+String(f.frame_index).padStart(6,'0');$('frame-time').textContent=(Number(f.timestamp_ns)/1e9).toFixed(3)+' s · '+f.timestamp_source;$('frame-size').textContent=`${f.width} × ${f.height}`;$('camera-format').textContent=`${f.width} × ${f.height} / JPEG`;}
}
function drawChart(samples){const canvas=$('imu-chart'),r=canvas.getBoundingClientRect(),dpr=devicePixelRatio||1;if(!r.width)return;canvas.width=r.width*dpr;canvas.height=r.height*dpr;const c=canvas.getContext('2d');c.scale(dpr,dpr);const w=r.width,h=r.height;c.strokeStyle='#26313a';c.lineWidth=.6;for(let i=0;i<5;i++){const y=12+i*(h-24)/4;c.beginPath();c.moveTo(0,y);c.lineTo(w,y);c.stroke();}for(let i=0;i<9;i++){const x=i*w/8;c.beginPath();c.moveTo(x,7);c.lineTo(x,h-7);c.stroke();}$('chart-empty').hidden=!!samples.length;if(samples.length<2)return;const values=samples.flatMap(s=>Object.values(s.values));const min=Math.min(-1,...values),max=Math.max(1,...values),pad=(max-min)*.1;const start=Number(samples[0].timestamp_ns),end=Number(samples.at(-1).timestamp_ns);['x','y','z'].forEach((key,index)=>{c.strokeStyle=['#c9f279','#67d4e6','#c69af3'][index];c.lineWidth=1.5;c.beginPath();samples.forEach((s,i)=>{const x=(Number(s.timestamp_ns)-start)/(end-start)*w,y=h-10-(s.values[key]-min+pad)/(max-min+2*pad)*(h-20);i?c.lineTo(x,y):c.moveTo(x,y);});c.stroke();});}
function sensor(name){currentSensor=name;$('accel-tab').classList.toggle('active',name==='accelerometer');$('gyro-tab').classList.toggle('active',name==='gyroscope');$('sensor-unit').replaceChildren(document.createTextNode(name==='accelerometer'?'m/s² ':'rad/s '));const span=document.createElement('span');span.textContent=name==='accelerometer'?'including gravity':'phone axes';$('sensor-unit').append(span);if(active)render(active);}
$('accel-tab').onclick=()=>sensor('accelerometer');$('gyro-tab').onclick=()=>sensor('gyroscope');window.addEventListener('resize',()=>active&&render(active));
// Keep image requests independent of chart/status requests. Only the newest saved JPEG is sent.
let imagePolling=false;
async function updateImage(){
  if(!config||!active||imagePolling)return;
  imagePolling=true;const sessionId=active.id;const connection=config;let next=null;
  try{
    const response=await api(`/api/sessions/${sessionId}/live-image`,{headers:{'X-After-Frame':String(lastFrame)}});
    if(response.status===204)return;
    const meta=JSON.parse(response.headers.get('X-Frame-Meta'));
    const blob=await response.blob();next=URL.createObjectURL(blob);
    const img=new Image();img.src=next;await img.decode();
    if(active?.id!==sessionId||config!==connection)return;
    const old=frameURL;frameURL=next;next=null;
    $('live-image').src=frameURL;$('live-image').hidden=false;$('camera-empty').hidden=true;
    lastFrame=meta.frame_index;
    if(old)URL.revokeObjectURL(old);
  }catch(e){/* Status polling reports collector connectivity; keep the last displayed image. */}
  finally{if(next)URL.revokeObjectURL(next);imagePolling=false;}
}
async function tick(){
  if(!config||polling)return;polling=true;
  const sessionId=active?.id;const connection=config;
  try{
    if(sessionId){
      const s=await api(`/api/sessions/${sessionId}?sensor=${currentSensor}`).then(r=>r.json());
      if(config!==connection||active?.id!==sessionId)return;
      if(s.metrics){active={...active,...s};render(active);}
    }else await api('/api/sessions');
    if(config===connection)setOnline(true);
  }catch(e){if(config===connection)setOnline(false);}finally{polling=false;}
}
setInterval(tick,250);setInterval(updateImage,80);if(config)tick();
async function loadSessions(){if(!config){$('library-empty').hidden=false;return;}try{const list=await api('/api/sessions').then(r=>r.json());$('session-rows').replaceChildren();$('library-empty').hidden=!!list.length;for(const s of list){const row=document.createElement('tr');const first=document.createElement('td');first.textContent=s.name;const small=document.createElement('small');small.textContent=s.id;first.append(small);row.append(first);for(const value of [new Date(s.created_at).toLocaleString(),s.live?.recording?'recording':s.status==='recording'?'interrupted':s.status,s.live?.metrics?.frames??s.metrics?.frames??'—']){const td=document.createElement('td');td.textContent=value;row.append(td);}const actions=document.createElement('td');const play=document.createElement('button');play.className='button secondary small';play.textContent='▷ Replay';play.onclick=()=>openReplay(s.id);actions.append(play);const exp=document.createElement('button');exp.className='button secondary small';exp.textContent='↓ IMU CSV';exp.onclick=()=>download(s.id,'imu.csv');actions.append(exp);const manifest=document.createElement('button');manifest.className='button secondary small';manifest.textContent='↓ Manifest';manifest.onclick=()=>download(s.id,'manifest.json');actions.append(manifest);row.append(actions);$('session-rows').append(row);}setOnline(true);}catch(e){toast(e.message);}}
$('refresh-sessions').onclick=loadSessions;
async function download(id,name){try{const blob=await api(`/api/sessions/${id}/export?file=${name}`).then(r=>r.blob());const u=URL.createObjectURL(blob),a=document.createElement('a');a.href=u;a.download=`${id}-${name}`;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}catch(e){toast(e.message);}}
async function openReplay(id){stopReplay();$('replay-dialog').showModal();$('replay-loading').hidden=false;$('replay-loading').textContent='Loading recorded session…';try{const data=await api(`/api/sessions/${id}/replay`).then(r=>r.json());data.frames.sort((a,b)=>Number(a.timestamp_ns)-Number(b.timestamp_ns)||a.frame_index-b.frame_index);data.samples.sort((a,b)=>Number(a.timestamp_ns)-Number(b.timestamp_ns)||a.sequence_id-b.sequence_id);replay={...data,id,index:0,groups:{}};for(const sample of data.samples)(replay.groups[sample.sensor_type]??=[]).push(sample);$('replay-name').textContent=data.manifest.name;$('replay-range').max=Math.max(0,data.frames.length-1);$('replay-range').value=0;if(!data.frames.length){$('replay-loading').textContent='No recorded frames in this session.';$('play-replay').disabled=true;return;}$('play-replay').disabled=false;await replayFrame(0);}catch(e){$('replay-loading').textContent=e.message;}}
async function replayFrame(index){if(!replay?.frames[index])return;const version=++replayVersion;replay.index=index;const f=replay.frames[index];$('replay-range').value=index;const target=Number(f.timestamp_ns);const aligned=['accelerometer','gyroscope','gnss'].map(type=>{const s=nearestSample(replay.groups[type]||[],target);return s?`${type}: ${JSON.stringify(s.values)}   Δ ${fmt(s.alignment_delta_ms,2)} ms`:`${type}: unavailable within ±100 ms`;});$('replay-meta').textContent=`Frame ${f.frame_index} · ${(target/1e9).toFixed(6)} s · ${f.timestamp_source}\n${aligned.join('\n')}`;try{const blob=await api(`/api/sessions/${replay.id}/image?index=${f.frame_index}`).then(r=>r.blob());if(version!==replayVersion)return;const u=URL.createObjectURL(blob);if(replayURL)URL.revokeObjectURL(replayURL);replayURL=u;$('replay-image').src=u;$('replay-loading').hidden=true;}catch(e){toast(e.message);}}
function stopReplay(){replayPlaying=false;clearTimeout(replayTimer);$('play-replay').textContent='▷ Play';}
function playStep(){if(!replayPlaying||!replay)return;const index=replay.index;if(index>=replay.frames.length-1){stopReplay();return;}const due=replayAnchor.wall+(Number(replay.frames[index+1].timestamp_ns)-replayAnchor.phone)/1e6/replayAnchor.speed;replayTimer=setTimeout(async()=>{if(!replayPlaying)return;await replayFrame(index+1);if(replayPlaying)playStep();},Math.max(0,due-performance.now()));}
$('play-replay').onclick=async()=>{if(replayPlaying)return stopReplay();if(!replay?.frames.length)return;if(replay.index>=replay.frames.length-1)await replayFrame(0);replayAnchor={wall:performance.now(),phone:Number(replay.frames[replay.index].timestamp_ns),speed:Number($('replay-speed').value)};replayPlaying=true;$('play-replay').textContent='Ⅱ Pause';playStep();};
$('replay-speed').onchange=stopReplay;
$('replay-range').oninput=()=>{stopReplay();replayFrame(Number($('replay-range').value));};$('replay-dialog').addEventListener('close',()=>{stopReplay();replayVersion++;});

$('connection-mode').onchange=()=>{
 const usb=$('connection-mode').value==='usb-adb';$('usb-setup').hidden=!usb;
 if(usb)$('server-url').value=location.hostname==='localhost'||location.hostname==='127.0.0.1'?location.origin:'http://localhost:8787';
};
$('usb-check').onclick=async()=>{
 const button=$('usb-check');button.disabled=true;
 try{
  if(!['localhost','127.0.0.1'].includes(location.hostname))throw new Error('Open http://localhost:8787 on the collector PC to configure USB.');
  const result=await request(location.origin,$('server-token').value.trim(),'/api/usb').then(r=>r.json());
  const select=$('usb-device');select.replaceChildren();
  for(const device of result.devices){const option=document.createElement('option');option.value=device.serial;option.textContent=`${device.model||device.serial} · ${device.state}`;option.disabled=device.state!=='device';select.append(option);}
  $('usb-status').textContent=!result.available?result.error:result.devices.length?'Select an authorized device, then Test & connect.':'No Android device found. Check the USB cable, driver and debugging authorization.';
 }catch(error){$('usb-status').textContent=error.message;}finally{button.disabled=false;}
};
function renderInventory(session){
 const rows=$('sensor-inventory-rows');rows.replaceChildren();
 $('device-route').textContent=config?.mode==='usb-adb'?'USB / ADB':'HTTPS';
 for(const [name,label]of [['accelerometer','Accelerometer / m/s²'],['linear_acceleration','Linear acceleration / m/s²'],['gyroscope','Gyroscope / rad/s'],['gnss','GNSS / deg, m, m/s']]){
  const row=document.createElement('tr');const capability=session.device?.capabilities?.sensors?.[name];
  for(const value of [label,capability?.state||'not checked',fmt(session.metrics?.per_sensor_hz?.[name],1),session.metrics?.sensor_counts?.[name]??0,session.metrics?.sequence_gaps_by_stream?.[name]??0]){const cell=document.createElement('td');cell.textContent=value;row.append(cell);}rows.append(row);
 }
 $('sample-drop-summary').textContent='Phone buffer drops: '+(session.metrics?.phone_dropped_samples??0)+' | Received sequence gaps: '+(session.metrics?.sequence_gaps??0);
 const gnss=session.latest?.gnss;$('gnss-latest').textContent=gnss?`GNSS: ${fmt(gnss.values.latitude,6)}, ${fmt(gnss.values.longitude,6)} · horizontal accuracy ${fmt(gnss.accuracy_m)} m`:'GNSS: no received fix. Location is optional; no coordinate is invented.';
}
