import http from 'node:http';
import { randomBytes, timingSafeEqual } from 'node:crypto';
import { mkdir, readFile, writeFile, readdir, open, rm } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { mono, ns, validateSample, percentile, sequenceUpdate, measuredRate } from './core.mjs';
import { createUsbBridge, isLocalUsbRequest } from './usb.mjs';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const dataRoot=path.resolve(process.env.DATA_DIR || path.join(root,'data'));
await mkdir(dataRoot,{recursive:true});
const port=Number(process.env.PORT||8787);
const usb=createUsbBridge({port,root});
const keyFile=path.join(dataRoot,'.collector-key');
let admin=process.env.COLLECTOR_TOKEN;
if(!admin) { try {admin=(await readFile(keyFile,'utf8')).trim();} catch {admin=randomBytes(32).toString('hex');await writeFile(keyFile,admin,{mode:0o600});} }
const allowed=new Set((process.env.ALLOWED_ORIGINS||`http://localhost:${port},http://127.0.0.1:${port}`).split(',').map(x=>x.trim()));
const sessions=new Map();
const secret=()=>randomBytes(24).toString('hex');
const same=(a,b)=>typeof a==='string'&&typeof b==='string'&&a.length===b.length&&timingSafeEqual(Buffer.from(a),Buffer.from(b));
const json=(res,status,obj)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(obj));};
const safeId=id=>/^[a-f0-9]{24}$/.test(id||'');
const sessionDir=id=>path.join(dataRoot,id);
const persist=s=>writeFile(path.join(sessionDir(s.id),'manifest.json'),JSON.stringify(s.manifest,null,2));
async function appendRecords(id,records) {
  const files=[];
  try {
    for(const [name,text] of records){
      // Logs already exist. Read/write access also permits rollback truncation on Windows.
      const file=await open(path.join(sessionDir(id),name),'r+');
      const entry={file,size:null};files.push(entry);const stat=await file.stat();
      if(!stat.isFile())throw new Error('Recording log must be a regular file');
      entry.size=stat.size;
      const bytes=Buffer.from(text);let offset=0;
      while(offset<bytes.length){
        const {bytesWritten}=await file.write(bytes,offset,bytes.length-offset,entry.size+offset);
        if(!bytesWritten)throw new Error('Recording write made no progress');
        offset+=bytesWritten;
      }
      await file.sync();
    }
  }catch(error){
    // Restore completed/partial appends before accepting a retry. This is not crash atomicity.
    const failures=[];
    for(const {file,size} of files){if(size===null)continue;try{await file.truncate(size);await file.sync();}catch(e){failures.push(e);}}
    if(failures.length){
      sessions.get(id).storageError=true;
      throw Object.assign(new AggregateError([error,...failures],'Recording storage could not be restored. Stop the collector and inspect this session before continuing.'),{status:503});
    }
    throw error;
  }finally{await Promise.allSettled(files.map(({file})=>file.close()));}
}
const append=(id,name,text)=>appendRecords(id,[[name,text]]);
async function body(req,limit=2_000_000) {
  const parts=[];let n=0;for await(const p of req){n+=p.length;if(n>limit)throw Object.assign(new Error('Request too large'),{status:413});parts.push(p);}return Buffer.concat(parts);
}
function metrics(s) {
  const elapsed=Math.max(.001,((s.stopAt||mono())-s.startAt)/1000);
  return {frames:s.frameCount,samples:s.sampleCount,fps:s.frameCount/elapsed,imu_hz:measuredRate(s.sensorTiming?.accelerometer),
    per_sensor_hz:Object.fromEntries(Object.entries(s.sensorTiming||{}).map(([k,v])=>[k,measuredRate(v)])),
    sensor_counts:s.sensorCounts,sequence_gaps:s.counters.gaps,sequence_gaps_by_stream:s.counters.by_stream||{},phone_dropped_frames:s.phoneDropped||0,phone_dropped_samples:s.phoneDroppedSamples||0,
    latency_p50_ms:percentile(s.latency,.5),latency_p95_ms:percentile(s.latency,.95),jitter_ms:s.latency.length>1?Math.sqrt(s.latency.reduce((a,x)=>a+(x-s.latency.reduce((a,b)=>a+b,0)/s.latency.length)**2,0)/s.latency.length):null,
    clock_rtt_ms:s.clock?.rtt_ms??null,clock_offset_ms:s.clock?.offset_ms??null,
    clock_drift_ppm:s.driftPpm??null,clock_uncertainty_ms:s.clock?s.clock.rtt_ms/2:null,
    duration_s:elapsed,bytes:s.bytes,recording:s.recording,phone_connected:mono()-s.lastSeen<5000};
}
function view(s,sensor) {return {id:s.id,name:s.manifest.name,created_at:s.manifest.created_at,device:s.device,last_frame:s.lastFrame,
  latest:s.latest,telemetry:sensor?s.telemetry.filter(x=>x.sensor_type===sensor).slice(-150):s.telemetry,clock:s.clock,metrics:metrics(s),recording:s.recording};}
async function loadStored(id) {return JSON.parse(await readFile(path.join(sessionDir(id),'manifest.json'),'utf8'));}
// All per-session mutations are serialized. Stop, frame writes and telemetry cannot race.
const queues=new Map();
function serial(id,fn,allowStorageError=false) {const previous=queues.get(id)||Promise.resolve();const next=previous.catch(()=>{}).then(()=>{if(sessions.get(id)?.storageError&&!allowStorageError)throw Object.assign(new Error('Recording storage needs inspection. Restart with a fresh session.'),{status:503});return fn();});queues.set(id,next);next.finally(()=>{if(queues.get(id)===next)queues.delete(id);}).catch(()=>{});return next;}
export const server=http.createServer(async(req,res)=>{
  const origin=req.headers.origin;
  res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('Referrer-Policy','no-referrer');
  if(origin) {
    if(!allowed.has(origin))return json(res,403,{error:'Origin not allowed. Add the exact frontend origin to ALLOWED_ORIGINS and restart.'});
    res.setHeader('Access-Control-Allow-Origin',origin);res.setHeader('Vary','Origin');
    res.setHeader('Access-Control-Allow-Headers','Authorization, Content-Type, X-Frame-Meta, X-After-Frame');res.setHeader('Access-Control-Allow-Methods','GET,POST,OPTIONS');
    res.setHeader('Access-Control-Max-Age','600');
    res.setHeader('Access-Control-Expose-Headers','X-Frame-Meta');
  }
  if(req.method==='OPTIONS'){res.writeHead(204);return res.end();}
  const url=new URL(req.url,'http://collector.local');
  try {
    if(url.pathname==='/health')return json(res,200,{ok:true,version:1});
    if(!url.pathname.startsWith('/api/')) {
      if(req.method!=='GET')return json(res,405,{error:'Method not allowed'});
      const name=url.pathname==='/'?'index.html':url.pathname.slice(1);
      if(!/^[a-zA-Z0-9_./-]+$/.test(name)||name.includes('..'))return json(res,404,{error:'Not found'});
      const file=path.join(root,'web',name);
      const bytes=await readFile(file);
      res.writeHead(200,{'Content-Type':({'html':'text/html','css':'text/css','js':'text/javascript','svg':'image/svg+xml'})[name.split('.').pop()]||'application/octet-stream',
        'Permissions-Policy':'camera=(self), microphone=(), geolocation=(self), accelerometer=(self), gyroscope=(self)'});return res.end(bytes);
    }
    const token=req.headers.authorization?.replace(/^Bearer /,'');
    const isAdmin=same(token,admin);
    if(url.pathname==='/api/usb') {
      if(!isAdmin)return json(res,401,{error:'Collector admin token required'});
      if(!isLocalUsbRequest(req,port))return json(res,403,{error:'Manage USB from http://localhost:'+port+' on the collector PC.'});
      if(req.method==='GET')return json(res,200,await usb.status());
      if(req.method==='POST'){const input=JSON.parse((await body(req,10000)).toString());return json(res,200,await usb.connect(input.serial));}
      return json(res,405,{error:'Method not allowed'});
    }
    const parts=url.pathname.split('/').filter(Boolean);
    const id=parts[2];const action=parts[3];
    if(id&&!safeId(id))return json(res,400,{error:'Invalid session ID'});
    const s=id?sessions.get(id):null;
    const isPhone=s&&same(token,s.phoneKey);
    if(!isAdmin&&!isPhone)return json(res,401,{error:'Invalid pairing key or collector token'});
    if(url.pathname==='/api/time'&&isAdmin)return json(res,200,{server_ms:mono()});
    if(parts[1]!=='sessions')return json(res,404,{error:'Not found'});
    if(!id&&req.method==='GET'&&isAdmin) {
      const list=[];for(const d of await readdir(dataRoot)){if(!safeId(d))continue;try{const m=await loadStored(d);list.push({...m,live:sessions.has(d)?view(sessions.get(d)):null});}catch{}}
      return json(res,200,list.sort((a,b)=>b.created_at.localeCompare(a.created_at)));
    }
    if(!id&&req.method==='POST'&&isAdmin) {
      const input=JSON.parse((await body(req,10000)).toString());
      if(input.connection_mode!==undefined&&!['tunnel','usb-adb'].includes(input.connection_mode))return json(res,400,{error:'Invalid connection mode'});
      const id=randomBytes(12).toString('hex');const now=mono();
      const session={id,phoneKey:secret(),startAt:now,lastSeen:-Infinity,frameCount:0,sampleCount:0,motionCount:0,sensorCounts:{},sensorTiming:{},bytes:0,
        latest:{},telemetry:[],lastFrame:null,recording:true,latency:[],counters:{last:{},gaps:0},
        manifest:{schema_version:2,id,name:String(input.name||'Untitled session').slice(0,80),created_at:new Date().toISOString(),status:'recording',
          clock_basis:'phone performance.now() monotonic milliseconds serialized as decimal nanoseconds; not hardware precision',
          server_boot_id:bootId,frame_time_quality:'See frames.csv timestamp_source. Browser capture or composition estimate, not Camera2 hardware time.',
          axes:'Phone portrait: +x right, +y top, +z out of display. Browser axes; camera/vehicle extrinsics uncalibrated.',
          alignment:'Nearest same-phone-clock sensor sample per type, max 100 ms; explicit missing values. Offline replay is authoritative.',
          calibration:{intrinsics:null,distortion:null,phone_to_vehicle:null,status:'uncalibrated'},connection_mode:input.connection_mode||'tunnel',
          files:['imu.csv','gnss.csv','telemetry.jsonl','frames.csv','frames.jsonl','clock.jsonl','frames/']}};
      await mkdir(path.join(sessionDir(id),'frames'),{recursive:true});
      await writeFile(path.join(sessionDir(id),'imu.csv'),'session_id,sensor_type,timestamp_ns,sequence_id,x,y,z,units,quality,server_receive_ns\n');
      await writeFile(path.join(sessionDir(id),'gnss.csv'),'session_id,timestamp_ns,sequence_id,latitude,longitude,altitude,speed,heading,accuracy_m,altitude_accuracy_m,server_receive_ns\n');
      await writeFile(path.join(sessionDir(id),'frames.csv'),'frame_index,timestamp_ns,timestamp_source,media_time_s,server_receive_ns,width,height,bytes,clock_offset_ms,clock_rtt_ms\n');
      for(const file of ['telemetry.jsonl','frames.jsonl','clock.jsonl'])await writeFile(path.join(sessionDir(id),file),'');
      await persist(session);sessions.set(id,session);return json(res,201,{...view(session),phone_key:session.phoneKey});
    }
    if(!action&&req.method==='GET'&&isAdmin){if(s)return json(res,200,view(s,url.searchParams.get('sensor')));return json(res,200,await loadStored(id));}
    if(action==='live-image'&&req.method==='GET'&&isAdmin) {
      res.setHeader('Cache-Control','no-store');
      if(!s?.lastJpeg||String(s.lastFrame.frame_index)===req.headers['x-after-frame']){res.writeHead(204);return res.end();}
      res.writeHead(200,{'Content-Type':'image/jpeg','X-Frame-Meta':JSON.stringify(s.lastFrame)});
      return res.end(s.lastJpeg);
    }
    if(action==='replay'&&req.method==='GET'&&isAdmin) {
      const m=await loadStored(id);const readLines=async name=>(await readFile(path.join(sessionDir(id),name),'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse);
      return json(res,200,{manifest:m,frames:await readLines('frames.jsonl'),samples:await readLines('telemetry.jsonl')});
    }
    if(action==='export'&&req.method==='GET'&&isAdmin) {
      const name=url.searchParams.get('file');if(!['manifest.json','imu.csv','gnss.csv','frames.csv','telemetry.jsonl','clock.jsonl','frames.jsonl'].includes(name))return json(res,400,{error:'Invalid export'});
      const b=await readFile(path.join(sessionDir(id),name));res.writeHead(200,{'Content-Type':'application/octet-stream','Content-Disposition':`attachment; filename="${id}-${name}"`});return res.end(b);
    }
    if(action==='image'&&req.method==='GET'&&isAdmin) {
      const index=url.searchParams.get('index');if(!/^\d{1,12}$/.test(index||''))return json(res,400,{error:'Invalid frame'});
      const b=await readFile(path.join(sessionDir(id),'frames',`${index.padStart(8,'0')}.jpg`));res.writeHead(200,{'Content-Type':'image/jpeg','Cache-Control':'no-store'});return res.end(b);
    }
    if(!s)return json(res,410,{error:'Session is no longer active. Create a new session after server restart.'});
    if(action==='sync'&&req.method==='POST'&&isPhone) {
      const t1=mono();const input=JSON.parse((await body(req,10000)).toString());
      s.lastSeen=mono();return json(res,200,{t0:input.t0,t1,t2:mono(),recording:s.recording});
    }
    if(action==='clock'&&req.method==='POST'&&isPhone) {
      const c=JSON.parse((await body(req,20000)).toString());
      if(!Number.isFinite(c.offset_ms)||!Number.isFinite(c.rtt_ms)||c.rtt_ms<0||!Number.isFinite(c.phone_ms))return json(res,400,{error:'Invalid clock estimate'});
      return await serial(id,async()=>{if(!s.recording)return json(res,409,{error:'Session stopped'});s.lastSeen=mono();
        if(s.firstClock&&c.phone_ms>s.firstClock.phone_ms+1000)s.driftPpm=(c.offset_ms-s.firstClock.offset_ms)/(c.phone_ms-s.firstClock.phone_ms)*1e6;
        s.firstClock??=c;s.clock=c;await append(id,'clock.jsonl',JSON.stringify({...c,server_receive_ns:ns(mono())})+'\n');return json(res,200,{ok:true});});
    }
    if(action==='samples'&&req.method==='POST'&&isPhone) {
      const input=JSON.parse((await body(req,300000)).toString());
      if(!Array.isArray(input.samples)||input.samples.length>1000||!input.samples.every(x=>validateSample(x)&&x.session_id===id))return json(res,400,{error:'Invalid telemetry schema, units, axes or session ID'});
      return await serial(id,async()=>{if(!s.recording)return json(res,409,{error:'Session stopped'});const accepted=[],counters=structuredClone(s.counters);let csv='',gnssCsv='';
        for(const raw of input.samples){if(!sequenceUpdate(counters,raw.sensor_type,raw.sequence_id))continue;
          const sample={...raw,session_id:id,server_receive_ns:ns(mono())};accepted.push(sample);
          const v=sample.values;if(sample.sensor_type!=='gnss')csv+=`${id},${sample.sensor_type},${sample.timestamp_ns},${sample.sequence_id},${v.x},${v.y},${v.z},${sample.units},browser_accuracy_unavailable,${sample.server_receive_ns}\n`;
          if(sample.sensor_type==='gnss')gnssCsv+=`${id},${sample.timestamp_ns},${sample.sequence_id},${v.latitude},${v.longitude},${v.altitude??''},${v.speed??''},${v.heading??''},${sample.accuracy_m},${sample.altitude_accuracy_m??''},${sample.server_receive_ns}\n`;
        }
        const records=[];if(csv)records.push(['imu.csv',csv]);if(gnssCsv)records.push(['gnss.csv',gnssCsv]);if(accepted.length)records.push(['telemetry.jsonl',accepted.map(x=>JSON.stringify(x)).join('\n')+'\n']);
        await appendRecords(id,records);s.counters=counters;
        for(const sample of accepted){
          s.latest[sample.sensor_type]=sample;
          s.sensorCounts[sample.sensor_type]=(s.sensorCounts[sample.sensor_type]||0)+1;if(sample.sensor_type==='accelerometer')s.motionCount++;
          const timestamp=BigInt(sample.timestamp_ns);const timing=s.sensorTiming[sample.sensor_type]??={count:0,first_ns:timestamp,last_ns:timestamp};
          timing.count++;if(timestamp<timing.first_ns)timing.first_ns=timestamp;if(timestamp>timing.last_ns)timing.last_ns=timestamp;
        }
        s.sampleCount+=accepted.length;s.telemetry.push(...accepted);s.telemetry=s.telemetry.slice(-1500);s.lastSeen=mono();s.phoneDropped=Math.max(s.phoneDropped||0,Number(input.dropped_frames)||0);s.phoneDroppedSamples=Math.max(s.phoneDroppedSamples||0,Number(input.dropped_samples)||0);
        return json(res,200,{accepted:accepted.length,recording:s.recording});});
    }
    if(action==='frame'&&req.method==='POST'&&isPhone) {
      const meta=JSON.parse(req.headers['x-frame-meta']||url.searchParams.get('meta')||'{}');
      if(!Number.isSafeInteger(meta.frame_index)||meta.frame_index<0||meta.frame_index>999999999999||!/^\d{1,18}$/.test(meta.timestamp_ns)||!['captureTime','presentationTime_estimate','callback_estimate'].includes(meta.timestamp_source)||!Number.isInteger(meta.width)||!Number.isInteger(meta.height)||meta.width<1||meta.width>1920||meta.height<1||meta.height>1920)return json(res,400,{error:'Invalid frame metadata'});
      const jpeg=await body(req,2_000_000);const received=mono();
      if(jpeg[0]!==0xff||jpeg[1]!==0xd8)return json(res,400,{error:'Expected JPEG'});
      return await serial(id,async()=>{if(!s.recording)return json(res,409,{error:'Session stopped'});
        const counters=structuredClone(s.counters);
        if(!sequenceUpdate(counters,'frame',meta.frame_index))return json(res,409,{error:'Duplicate/out of order frame'});
        const f={...meta,session_id:id,server_receive_ns:ns(received),bytes:jpeg.length,clock_offset_ms:s.clock?.offset_ms??null,clock_rtt_ms:s.clock?.rtt_ms??null};
        const imageFile=path.join(sessionDir(id),'frames',`${String(f.frame_index).padStart(8,'0')}.jpg`);
        try{
          await writeFile(imageFile,jpeg);
          await appendRecords(id,[['frames.jsonl',JSON.stringify(f)+'\n'],['frames.csv',`${f.frame_index},${f.timestamp_ns},${f.timestamp_source},${Number(f.media_time_s)||0},${f.server_receive_ns},${f.width},${f.height},${jpeg.length},${f.clock_offset_ms??''},${f.clock_rtt_ms??''}\n`]]);
        }catch(error){await rm(imageFile,{force:true}).catch(()=>{});throw error;}
        s.counters=counters;
        if(s.clock){s.latency.push(Math.max(0,received-(Number(f.timestamp_ns)/1e6+s.clock.offset_ms)));s.latency=s.latency.slice(-600);}
        s.lastFrame=f;s.lastJpeg=jpeg;s.frameCount++;s.bytes+=jpeg.length;s.lastSeen=mono();return json(res,200,{stored:true,frame_index:f.frame_index});});
    }
    if(action==='device'&&req.method==='POST'&&isPhone){const input=JSON.parse((await body(req,20000)).toString());return await serial(id,async()=>{s.device=input;s.manifest.device=input;await persist(s);return json(res,200,{ok:true});});}
    if(action==='stop'&&req.method==='POST'&&isAdmin)return await serial(id,async()=>{if(s.recording){s.stopAt=mono();s.recording=false;s.manifest.status='completed';s.manifest.ended_at=new Date().toISOString();s.manifest.metrics=metrics(s);await persist(s);}return json(res,200,view(s));});
    return json(res,404,{error:'Not found'});
  }catch(e){if(res.headersSent){res.destroy();return;}json(res,e.status||(e.code==='ENOENT'?404:e instanceof SyntaxError?400:500),{error:e.code==='ENOENT'?'Not found':e.message});}
});
const bootId=randomBytes(12).toString('hex');
server.requestTimeout=30000;server.headersTimeout=15000;
if(process.env.SENSORLINK_TEST!=='1')server.listen(port,process.env.HOST||'127.0.0.1',()=>{
  console.log(`\nSENSORLINK • Week 01 collector\nDashboard: http://localhost:${port}\nData directory: ${dataRoot}\n`);
  console.log(`Collector token (paste into Connection settings):\n${admin}\n`);
  console.log('For phone access: run an HTTPS tunnel to this port, then use its https:// URL in Connection settings.');
});
let closing=false;
async function shutdown(){if(closing)return;closing=true;for(const s of sessions.values())await serial(s.id,async()=>{if(s.recording){s.recording=false;s.stopAt=mono();s.manifest.status='interrupted';if(s.storageError)s.manifest.storage_error='Rollback failed; inspect raw files before using this session.';s.manifest.metrics=metrics(s);await persist(s);}},true);server.close(()=>process.exit(0));}
process.on('SIGINT',shutdown);process.on('SIGTERM',shutdown);
