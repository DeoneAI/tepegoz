import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { nearest } from './core.mjs';
const input=process.argv[2];
if(!input){console.error('Usage: node pc/replay.mjs data/<session-id> [--realtime]');process.exit(1);}
const folder=path.resolve(input),readLines=async name=>(await readFile(path.join(folder,name),'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse);
const frames=(await readLines('frames.jsonl')).sort((a,b)=>Number(a.timestamp_ns)-Number(b.timestamp_ns)||a.frame_index-b.frame_index);
const samples=(await readLines('telemetry.jsonl')).sort((a,b)=>Number(a.timestamp_ns)-Number(b.timestamp_ns)||a.sequence_id-b.sequence_id);
const groups={};for(const s of samples)(groups[s.sensor_type]??=[]).push(s);
const realtime=process.argv.includes('--realtime');
let previous=null;
for(const f of frames){const time=Number(f.timestamp_ns);if(realtime&&previous!==null)await new Promise(r=>setTimeout(r,Math.max(0,(time-previous)/1e6)));previous=time;const aligned={};for(const type of ['accelerometer','gyroscope','gnss'])aligned[type]=nearest(groups[type]||[],time);
  console.log(JSON.stringify({frame_index:f.frame_index,timestamp_ns:f.timestamp_ns,timestamp_source:f.timestamp_source,image:path.join(folder,'frames',`${String(f.frame_index).padStart(8,'0')}.jpg`),aligned}));}
