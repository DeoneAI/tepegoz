import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

// Run the actual phone lifecycle with controlled HTTP completion and a minimal DOM.
const source=(await readFile(new URL('../web/phone.js',import.meta.url),'utf8')).replace(/^import .*;\r?\n/gm,'');
function phone(post,request=async()=>({})){
  const elements=new Map();
  const $=id=>{if(!elements.has(id))elements.set(id,{hidden:false,disabled:false,textContent:'',value:'',srcObject:null});return elements.get(id);};
  const pairing={server:'https://collector.test',session:'0123456789abcdef01234567',key:'a'.repeat(48),mode:'tunnel'};
  $('target-fps').value='10';$('target-width').value='640';
  Object.assign($('phone-video'),{videoWidth:640,videoHeight:360,currentTime:0});
  const context=vm.createContext({$,post,request,fmt:()=>'',stamp:ms=>String(Math.round(ms*1e6)),finiteVector:()=>false,
    validateServer:value=>value,location:{hash:'',pathname:'/phone.html',hostname:'phone.test'},
    sessionStorage:{getItem:()=>JSON.stringify(pairing)},isSecureContext:true,URLSearchParams,
    document:{createElement:()=>({getContext:()=>({drawImage(){}}),toBlob:callback=>callback({})}),addEventListener(){}},window:{addEventListener(){},removeEventListener(){}},
    performance:{now:()=>0},clearInterval(){},setInterval(){},requestAnimationFrame:()=>1,cancelAnimationFrame(){}});
  vm.runInContext(source+`\nglobalThis.capture={begin(){running=true;},queue,flush,frame,stop,get pending(){return buffer.length;}};`,context);
  context.capture.begin();
  return {capture:context.capture,$,enqueue(value){context.capture.queue('accelerometer',{x:value,y:0,z:0},'m_s2',value);}};
}
const deferred=()=>{let resolve,reject;const promise=new Promise((ok,fail)=>{resolve=ok;reject=fail;});return {promise,resolve,reject};};

test('phone Stop waits for the final JPEG acknowledgment before inviting PC finalization',async()=>{
  const ack=deferred();let requested=false;
  const client=phone(async()=>({}),async()=>{requested=true;await ack.promise;return {};});
  const frame=client.capture.frame(100,{captureTime:90,mediaTime:0.1});
  await Promise.resolve();assert.equal(requested,true);
  let stopped=false;const stop=client.$('stop-capture').onclick().then(()=>{stopped=true;});
  await Promise.resolve();await Promise.resolve();assert.equal(stopped,false);
  ack.resolve();await frame;await stop;
  assert.match(client.$('phone-status').textContent,/Use Stop & save/);
});

test('phone Stop waits for active upload then drains samples captured while it was in flight',async()=>{
  const first=deferred(),calls=[];
  const client=phone(async(server,key,route,payload)=>{calls.push(payload);if(calls.length===1)await first.promise;return {accepted:payload.samples.length};});
  client.enqueue(1);const upload=client.capture.flush();await Promise.resolve();client.enqueue(2);
  let stopped=false;const stop=client.$('stop-capture').onclick().then(()=>{stopped=true;});
  await Promise.resolve();await Promise.resolve();
  assert.equal(stopped,false);assert.equal(calls.length,1);
  first.resolve();await upload;await stop;
  assert.deepEqual(calls.map(c=>Array.from(c.samples,s=>s.sequence_id)),[[0],[1]]);
  assert.equal(client.capture.pending,0);assert.equal(client.$('stop-capture').hidden,true);
  assert.match(client.$('phone-status').textContent,/Use Stop & save/);
});

test('phone Stop retries an active failed batch without losing subsequent queued samples',async()=>{
  const first=deferred(),calls=[];
  const client=phone(async(server,key,route,payload)=>{calls.push(payload);if(calls.length===1)await first.promise;return {};});
  client.enqueue(1);const upload=client.capture.flush();await Promise.resolve();client.enqueue(2);
  const stop=client.$('stop-capture').onclick();first.reject(new Error('Connection lost'));await upload;await stop;
  assert.deepEqual(calls.map(c=>Array.from(c.samples,s=>s.sequence_id)),[[0],[0,1]]);
  assert.equal(client.capture.pending,0);
});

test('phone Stop waits for an upload even when the waiting buffer is empty',async()=>{
  const first=deferred();const client=phone(()=>first.promise);
  client.enqueue(1);client.capture.flush();let stopped=false;
  const stop=client.capture.stop().then(()=>{stopped=true;});
  await Promise.resolve();await Promise.resolve();assert.equal(stopped,false);
  first.resolve({});await stop;assert.equal(client.capture.pending,0);
});

test('failed stop keeps telemetry and offers a retry before PC finalization',async()=>{
  let offline=true,calls=0;
  const client=phone(async()=>{calls++;if(offline)throw new Error('Offline');return {};});
  client.enqueue(1);await client.$('stop-capture').onclick();
  assert.equal(calls,4,'stop retries are bounded');assert.equal(client.capture.pending,1);
  assert.equal(client.$('stop-capture').hidden,false);assert.equal(client.$('stop-capture').disabled,false);
  assert.match(client.$('phone-status').textContent,/1 telemetry samples still queued/);
  offline=false;await client.$('stop-capture').onclick();
  assert.equal(client.capture.pending,0);assert.equal(client.$('stop-capture').hidden,true);
  assert.match(client.$('phone-status').textContent,/Use Stop & save/);
});

test('ended sessions report unsent telemetry instead of claiming a successful flush',async()=>{
  const client=phone(async()=>{throw Object.assign(new Error('Session stopped'),{status:409});});
  client.enqueue(1);await client.$('stop-capture').onclick();
  assert.equal(client.capture.pending,1);assert.equal(client.$('stop-capture').hidden,true);
  assert.match(client.$('phone-status').textContent,/1 telemetry samples not uploaded/);
});
