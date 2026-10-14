/* Admin archiving: copy and verify first; cleanup is a separate opt-in operation. */
const adminBeforeArchive=$('#navAdmin').onclick;
$('#navAdmin').onclick=async function(){
 await adminBeforeArchive();
 if(me.role!=='admin'||!$('#settingsForm'))return;
 try{
  const data=await api('/archive/status');const panel=document.createElement('section');panel.className='panel';panel.style.marginTop='24px';
  panel.innerHTML=`<h2>One-year Archive</h2><p>Completed records older than one year: <strong>${data.eligible}</strong>. Archived records retain Portal report information and become read-only.</p><p>${data.available?'C drive staging is available.':'Local staging is unavailable. Initialize the C drive staging folder first.'}</p><div class="toolbar"><button id="copyArchive" ${data.available?'':'disabled'}>Generate verified archives</button><button id="purgeArchive" class="secondary" ${false?'':'disabled'}>Use offline transfer script</button></div><p>Generate complete offline records first. Use scripts/Move-ArchiveOffline.ps1 when the external drive is connected. It verifies the external copies, records their location, and clears local attachments and staged copies. The external drive can then be disconnected.</p><p id="archiveProgress" role="status"></p><div>${data.records.slice(0,50).map(r=>`<p><strong>${escape(r.number)}</strong> — ${escape(r.state)}<br><small>${escape(r.path)}</small></p>`).join('')||'No archives yet.'}</div>`;
  $('#otherView').append(panel);
  const run=async mode=>{if(mode==='purge'&&!confirm('Confirm the archive is on external storage with another backup copy. Each archive will be verified before online attachment cleanup. Continue?'))return;$('#copyArchive').disabled=true;$('#purgeArchive').disabled=true;let count=0;try{while(true){const result=await api('/archive/'+mode,{});if(!result.item)break;count++;$('#archiveProgress').textContent=count+' completed — '+result.item.number}toast(count+' archive operations completed');await $('#navAdmin').onclick()}catch(x){$('#archiveProgress').textContent=x.message;toast(x.message);$('#copyArchive').disabled=!data.available;$('#purgeArchive').disabled=true}};
  $('#copyArchive').onclick=()=>run('run');$('#purgeArchive').onclick=()=>run('purge');
 }catch(x){toast(x.message)}
};
