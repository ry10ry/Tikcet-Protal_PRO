const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('app/static/app.js', 'utf8');
const elements = new Map();
const $ = id => {if (!elements.has(id)) elements.set(id, {value:'',innerHTML:''});return elements.get(id)};
const ctx = vm.createContext({$,me:{role:'admin'},tickets:[],config:{},page:1,pageSize:10,
 escape:s=>String(s??''),date:()=>'',badge:s=>s,displayStatus:s=>s==='Additional Information Requested'?'Pending Customer':s});
for (const name of ['refreshAssigneeFilter','render']) vm.runInContext(source.split('\n').find(l=>l.startsWith(`function ${name}(`)),ctx);
ctx.tickets = [
 {id:1,reference:'MOMCC-000001',title:'Network',requester:'Alice',status:'In Progress',assignee_id:7,assignee:'Engineer One',visibility:'Public'},
 {id:2,reference:'MOMCC-000002',title:'Voice',requester:'Bob',status:'New',assignee_id:null,assignee:'Unassigned',visibility:'Internal'},
 {id:3,reference:'MOMCC-000003',title:'Access',requester:'Chris',status:'Additional Information Requested',assignee_id:8,assignee:'Engineer Two',visibility:'Public'}
];
ctx.refreshAssigneeFilter();assert.match($('#assigneeFilter').innerHTML,/Engineer One/);
function check(filters, ids) {
 for(const key of ['search','statusFilter','assigneeFilter','visibilityFilter']) $('#'+key).value=filters[key]||'';
 ctx.render();const actual=[...$('#rows').innerHTML.matchAll(/data-id="(\d+)"/g)].map(m=>Number(m[1]));assert.deepEqual(actual,ids);
}
check({},[1,2,3]);check({statusFilter:'In Progress'},[1]);
check({assigneeFilter:'7',visibilityFilter:'Public',statusFilter:'In Progress'},[1]);
check({assigneeFilter:'7',visibilityFilter:'Internal'},[]);
check({assigneeFilter:'unassigned'},[2]);check({visibilityFilter:'Internal'},[2]);
check({search:'engineer two'},[3]);check({search:'pending customer'},[3]);
check({search:'in progress'},[1]);check({search:'momcc-000002'},[2]);
// Requester visibility remains controlled by the API; no Internal filter is applied.
ctx.me.role='requester';ctx.tickets=ctx.tickets.filter(t=>t.visibility==='Public');
check({visibilityFilter:'Internal'},[1,3]);
console.log('Fault filters: status, Engineer, visibility, combined filters and text search passed');
