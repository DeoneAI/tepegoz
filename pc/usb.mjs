import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { existsSync } from 'node:fs';
import path from 'node:path';
const exec = promisify(execFile);
const fail = (message,status=400) => Object.assign(new Error(message),{status});

export function parseDevices(output) {
  return output.split(/\r?\n/).flatMap(line=>{
    const match=line.trim().match(/^(\S+)\s+(device|unauthorized|offline)\b(.*)$/);
    if(!match)return [];
    return [{serial:match[1],state:match[2],model:(match[3].match(/\bmodel:(\S+)/)||[])[1]||null}];
  });
}

export function createUsbBridge({port=8787,root=process.cwd(),run,adbPath}={}) {
  const bundled=path.join(root,'.tools','platform-tools',process.platform==='win32'?'adb.exe':'adb');
  const executable=adbPath||process.env.ADB_PATH||(existsSync(bundled)?bundled:'adb');
  const command=run||((args)=>exec(executable,args,{timeout:10000,maxBuffer:256000,windowsHide:true}).then(r=>r.stdout));
  const phoneOrigin=`http://localhost:${port}`;
  async function status() {
    try{return {available:true,devices:parseDevices(await command(['devices','-l'])),phone_origin:phoneOrigin};}
    catch(e){if(e.code==='ENOENT')return {available:false,devices:[],phone_origin:phoneOrigin,error:'ADB not found. Install Android SDK Platform-Tools, then set ADB_PATH or put platform-tools in .tools/.'};throw fail('ADB could not list devices. Check the driver, cable and USB debugging authorization.',503);}
  }
  async function connect(serial) {
    if(typeof serial!=='string'||!serial||serial.length>128||!/^[A-Za-z0-9_.:-]+$/.test(serial))throw fail('Select a valid Android device.');
    const current=await status();
    if(!current.available)throw fail(current.error,503);
    const device=current.devices.find(d=>d.serial===serial);
    if(!device)throw fail('The selected device is no longer connected.',409);
    if(device.state!=='device')throw fail('Unlock the phone and approve its USB debugging prompt.',409);
    // ADB also supports wireless devices. Verify the actual transport before calling it USB.
    const devpath=(await command(['-s',serial,'get-devpath'])).trim();
    if(!devpath.startsWith('usb:'))throw fail('This device uses wireless ADB or an emulator. Connect a physical USB cable.');
    await command(['-s',serial,'reverse',`tcp:${port}`,`tcp:${port}`]);
    const mappings=await command(['-s',serial,'reverse','--list']);
    const mapped=mappings.split(/\r?\n/).some(line=>{
      const fields=line.trim().split(/\s+/);return fields.at(-2)===`tcp:${port}`&&fields.at(-1)===`tcp:${port}`;
    });
    if(!mapped)throw fail('ADB did not confirm the reverse port mapping.',503);
    return {connected:true,mode:'usb-adb',device,phone_origin:phoneOrigin,port};
  }
  return {status,connect};
}

export function isLocalUsbRequest(req,port) {
  const address=req.socket?.remoteAddress;
  if(!['127.0.0.1','::1','::ffff:127.0.0.1'].includes(address))return false;
  const hosts=[`localhost:${port}`,`127.0.0.1:${port}`,`[::1]:${port}`];
  if(!hosts.includes(req.headers.host))return false;
  return !req.headers.origin||hosts.map(host=>'http://'+host).includes(req.headers.origin);
}
