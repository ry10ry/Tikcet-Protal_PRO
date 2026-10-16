/* Local clipboard editor: no external scripts, resources or pasted styles. */
const FaultEditor=(()=>{
 const editor=document.querySelector('#faultDescriptionEditor'),field=document.querySelector('#createForm [name="description"]');
 const allowed=new Set('P DIV BR SPAN B STRONG I EM U S UL OL LI TABLE THEAD TBODY TFOOT TR TH TD CAPTION BLOCKQUOTE PRE'.split(' '));
 const blocked=new Set('SCRIPT STYLE IFRAME OBJECT EMBED SVG MATH TEMPLATE HEAD LINK META FORM INPUT BUTTON IMG VIDEO AUDIO'.split(' '));
 function clean(value){const doc=document.createElement('template');doc.innerHTML=value;const walk=node=>{for(const child of [...node.children]){if(blocked.has(child.tagName)){child.remove();continue}walk(child);if(!allowed.has(child.tagName)){child.replaceWith(...child.childNodes);continue}for(const a of [...child.attributes]){if(!(['TD','TH'].includes(child.tagName)&&['colspan','rowspan'].includes(a.name)&&/^\d+$/.test(a.value)&&Number(a.value)>=1&&Number(a.value)<=100))child.removeAttribute(a.name)}}};walk(doc.content);return doc.innerHTML}
 function text(){return editor.innerText.replace(/\u00a0/g,' ').trim()}
 function sync(){field.value=text();editor.dataset.empty=String(!field.value&&!editor.querySelector('table'))}
 function set(value){editor.textContent=value;sync()}
 function paste(e){e.preventDefault();const data=e.clipboardData;let value=data.getData('text/html');if(value)value=clean(value);else {const plain=data.getData('text/plain');if(plain.includes('\t')){const table=document.createElement('table');for(const line of plain.replace(/\r/g,'').replace(/\n$/,'').split('\n')){const tr=table.insertRow();for(const cell of line.split('\t'))tr.insertCell().textContent=cell}value=table.outerHTML}else{const div=document.createElement('div');div.textContent=plain;value=div.innerHTML.replace(/\r?\n/g,'<br>')}}document.execCommand('insertHTML',false,value);sync()}
 editor.addEventListener('paste',paste);editor.addEventListener('input',sync);
 editor.addEventListener('drop',e=>e.preventDefault());
 return {clean,set,text,body(){sync();if(field.value.length<5||field.value.length>20000)throw Error('Description must contain 5 to 20,000 text characters');const value=clean(editor.innerHTML);if(value.length>100000)throw Error('Formatted description is too large');return value}};
})();
