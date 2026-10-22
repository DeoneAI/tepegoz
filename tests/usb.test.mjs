import test from 'node:test';
import assert from 'node:assert/strict';
import {createUsbBridge,parseDevices,isLocalUsbRequest} from '../pc/usb.mjs';

test('USB discovery preserves unauthorized devices and reports missing ADB',async()=>{
  assert.deepEqual(parseDevices('List of devices attached\nABC unauthorized usb:1\nDEF device product:x model:Galaxy_A15 transport_id:1\n'),[
    {serial:'ABC',state:'unauthorized',model:null},{serial:'DEF',state:'device',model:'Galaxy_A15'}]);
  const bridge=createUsbBridge({run:async()=>{throw Object.assign(new Error('missing'),{code:'ENOENT'});}});
  assert.equal((await bridge.status()).available,false);
});
test('USB setup verifies physical transport and confirms the reverse mapping',async()=>{
  const calls=[];const bridge=createUsbBridge({port:8787,run:async args=>{
    calls.push(args);if(args[0]==='devices')return 'ABC device model:Galaxy_A15\n';
    if(args.includes('get-devpath'))return 'usb:1-2';if(args.includes('--list'))return 'UsbFfs tcp:8787 tcp:8787\n';return '';
  }});
  const result=await bridge.connect('ABC');assert.equal(result.connected,true);assert.equal(result.phone_origin,'http://localhost:8787');
  assert.deepEqual(calls[2],['-s','ABC','reverse','tcp:8787','tcp:8787']);
  await assert.rejects(()=>bridge.connect('ABC;whoami'),/valid Android/);
});
test('USB setup rejects wireless, unauthorized and missing mappings',async()=>{
  for(const [state,devpath,mapping,error]of [['unauthorized','usb:1','',/approve/],['device','192.168.0.2:5555','',/physical USB/],['device','usb:1','',/confirm/]]){
    const bridge=createUsbBridge({run:async args=>args[0]==='devices'?`ABC ${state}\n`:args.includes('get-devpath')?devpath:mapping});
    await assert.rejects(()=>bridge.connect('ABC'),error);
  }
});
test('USB controls require local socket, Host and Origin even through a local reverse proxy',()=>{
  const req={socket:{remoteAddress:'127.0.0.1'},headers:{host:'localhost:8787',origin:'http://localhost:8787'}};
  assert.equal(isLocalUsbRequest(req,8787),true);
  assert.equal(isLocalUsbRequest({...req,headers:{...req.headers,host:'public.trycloudflare.com'}},8787),false);
  assert.equal(isLocalUsbRequest({...req,headers:{...req.headers,origin:'https://untrusted.test'}},8787),false);
  assert.equal(isLocalUsbRequest({...req,socket:{remoteAddress:'192.168.1.2'}},8787),false);
});
