let strat='contiguous', hist=[], hi=-1;

async function init(){
  const d=await(await fetch('/api/disk')).json();
  renderAll(d);
}
function setSt(s,el){strat=s;document.querySelectorAll('.stab').forEach(t=>t.classList.remove('active'));el.classList.add('active');}

function renderAll(d){
  renderDisk(d);
  renderTree(d.tree);
  document.getElementById('cwdB').textContent='cwd: '+d.cwd;
  document.getElementById('sCw').textContent=d.cwd;
  document.getElementById('sFr').textContent=d.free_count;
  document.getElementById('sUs').textContent=d.used_count;
  document.getElementById('sIn').textContent=Object.keys(d.inode_table||{}).length;
  document.getElementById('pl').textContent=(d.cwd==='/'?'user@sim:/$ ':'user@sim:'+d.cwd+'$ ');
}

function renderDisk(d){
  const g=document.getElementById('dg');
  g.innerHTML='';
  const sl={0:'SB',1:'BB',2:'IB',3:'IT'};
  for(let i=0;i<d.total_blocks;i++){
    const el=document.createElement('div');
    el.className='block'; el.id='b'+i;
    const t=d.block_types[i],o=d.blocks[i];
    if(t==='system')el.classList.add('system');
    else if(t==='index')el.classList.add('index');
    else if(t==='data'&&o){
      const ino=Object.values(d.inode_table||{}).find(n=>n.blocks&&n.blocks.includes(i));
      el.classList.add(ino&&ino.strategy==='linked'?'linked':'data');
    }else el.classList.add('free');
    const sh=o?(o.split('/').pop()||'').substring(0,5):'';
    el.innerHTML=`<span class="bn">${i}</span><span class="bl">${sl[i]||sh}</span>`;
    el.title=o?`Block ${i} - ${o} (${t})`:`Block ${i} - free`;
    el.onclick=()=>toast(o?`Block ${i}: ${o} | ${t}`:`Block ${i} - free`,false);
    g.appendChild(el);
  }
}

function renderTree(node,container,indent){
  if(!container){container=document.getElementById('fst');container.innerHTML='';}
  if(!node){container.textContent='(empty)';return;}
  const entries=node.entries||[];
  if(!indent&&entries.length===0){container.textContent='(empty filesystem)';return;}
  for(const e of entries){
    const isD=e.file_type==='d';
    const row=document.createElement('div');
    row.className='ti '+(isD?'d':'f');
    row.innerHTML=`<span class="ic">${isD?'[d]':'[f]'}</span><span class="nm">${e.name}${isD?'/':''}</span><span class="pm">${e.permissions}</span>`;
    row.title=`${e.full_path} | inode #${e.inode_num} | ${e.strategy} | blocks:${e.blocks}`;
    row.onclick=ev=>{ev.stopPropagation();toast(`${e.full_path} | #${e.inode_num} | ${e.strategy} | blocks:[${e.blocks}]`,false);};
    container.appendChild(row);
    if(isD&&e.entries&&e.entries.length>0){
      const sub=document.createElement('div');sub.className='ti-sub';
      container.appendChild(sub);renderTree(e,sub,true);
    }
  }
}

async function animSteps(steps){
  const log=document.getElementById('al');
  log.innerHTML='';
  for(const s of steps){
    await sleep(260);
    const fc=s.type==='READ'?'fr':'fw';
    for(const b of(s.blocks||[])){
      const el=document.getElementById('b'+b);
      if(el){el.classList.add(fc);setTimeout(()=>el.classList.remove(fc),640);}
    }
    const row=document.createElement('div');
    row.className='le';
    row.innerHTML=`<span class="lo ${s.type==='READ'?'lr':'lw2'}">${s.type}</span>
      <span class="lb">[${(s.blocks||[]).join(',')}]</span>
      <span class="ld2">${s.desc}</span>`;
    log.appendChild(row);
    log.scrollTop=log.scrollHeight;
  }
}
function sleep(ms){return new Promise(r=>setTimeout(r,ms));}

async function allocFile(){
  const filename=document.getElementById('fn').value.trim();
  const size_kb=parseInt(document.getElementById('fs').value);
  const content=document.getElementById('fc').value;
  if(!filename){toast('Enter a path',true);return;}
  const res=await fetch('/api/allocate',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({filename,size_kb,strategy:strat,content})});
  const data=await res.json();
  if(data.error){toast(data.error,true);return;}
  renderAll(data.disk);
  await animSteps(data.steps);
  toast('Allocated '+filename,false);
  document.getElementById('fn').value='';
  document.getElementById('fc').value='';
}

async function resetDisk(){
  const data=await(await fetch('/api/reset',{method:'POST'})).json();
  renderAll(data.disk);
  document.getElementById('al').innerHTML='<div class="lem">Disk reset</div>';
  document.getElementById('to').innerHTML='<div class="tl ti2">Disk reset - ready</div>';
  toast('Disk reset',false);
}

document.getElementById('ti').addEventListener('keydown',async e=>{
  const inp=e.target;
  if(e.key==='Enter'){
    const cmd=inp.value.trim();if(!cmd)return;
    hist.unshift(cmd);hi=-1;inp.value='';
    await runCmd(cmd);
  }else if(e.key==='ArrowUp'){hi=Math.min(hi+1,hist.length-1);inp.value=hist[hi]||'';e.preventDefault();}
  else if(e.key==='ArrowDown'){hi=Math.max(hi-1,-1);inp.value=hi===-1?'':hist[hi];e.preventDefault();}
});

async function runCmd(cmd){
  const out=document.getElementById('to');
  const cl=document.createElement('div');cl.className='tl';
  const pr=document.getElementById('pl').textContent;
  cl.innerHTML=`<span class="tp">${pr}</span><span class="tc">${cmd.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}</span>`;
  out.appendChild(cl);
  if(cmd==='clear'){out.innerHTML='';return;}
  const data=await(await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({command:cmd})})).json();
  if(data.output||data.error){
    const ol=document.createElement('div');
    ol.className='tl '+(data.error?'te':'tx');
    ol.textContent=data.output||data.error;
    out.appendChild(ol);
  }
  out.scrollTop=out.scrollHeight;
  if(data.disk)renderAll(data.disk);
  if(data.steps&&data.steps.length)await animSteps(data.steps);
}

function toast(msg,isErr){
  const t=document.getElementById('toast');
  t.textContent=msg;t.className='toast show'+(isErr?' err':'');
  setTimeout(()=>t.className='toast',3000);
}
document.getElementById('fn').addEventListener('keydown',e=>{if(e.key==='Enter')allocFile();});
init();