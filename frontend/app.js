const $ = s => document.querySelector(s);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let book = null, view = 'people', hanjaIndex = null, hanjaState = null;
$('#bookInfoForm').querySelector('h3').textContent='선택한 족보 정보';
$('#newBook').onclick=()=>{$('#bookDialog').showModal();setTimeout(()=>$('#bookForm').elements.title.focus(),0);};
$('#closeBookDialog').onclick=()=>$('#bookDialog').close();
const searchNotice=document.createElement('p');
searchNotice.id='searchNotice';searchNotice.className='search-notice';searchNotice.hidden=true;
$('#view').before(searchNotice);
$('#bookForm').elements.volume.value='1';
$('#bookForm').elements.volume.readOnly=true;
$('#bookInfoForm').elements.volume.readOnly=true;
// A 족보 records its names in hanja, which most readers cannot sound out. The
// dictionary gives one reading per character; a surname before 氏 and the
// initial-sound rule are the two places that plain lookup gets wrong.
const HANJA_SURNAME={金:'김',李:'이',柳:'유',劉:'유',羅:'나',盧:'노',梁:'양',林:'임',呂:'여',龍:'용',廉:'염',雷:'뇌',陸:'육',陰:'음'};
const INITIAL_SOUND={라:'나',래:'내',로:'노',뢰:'뇌',루:'누',르:'느',리:'이',량:'양',려:'여',력:'역',련:'연',렬:'열',렴:'염',령:'영',례:'예',룡:'용',류:'유',륙:'육',륜:'윤',률:'율',름:'늠',릉:'능',림:'임',립:'입',녀:'여',뇨:'요',뉴:'유',니:'이',냑:'약',녕:'영'};
let hanjaReadings=null;
let scriptMode='hanja';
try{scriptMode=localStorage.getItem('jocbo.script')==='hangul'?'hangul':'hanja';}catch{}
async function loadHanjaDict(){
 if(hanjaReadings)return hanjaReadings;
 hanjaReadings=await fetch('/hanjaeum.json').then(r=>{if(!r.ok)throw Error('한자 사전을 불러오지 못했습니다.');return r.json();});
 return hanjaReadings;
}
function readingOf(text){
 if(!hanjaReadings||!text)return '';
 const chars=Array.from(String(text));
 let changed=false;
 const out=chars.map((ch,index)=>{
  if(!/[一-鿿]/.test(ch))return ch;
  if(chars[index+1]==='氏'&&HANJA_SURNAME[ch]){changed=true;return HANJA_SURNAME[ch];}
  let reading=(hanjaReadings[ch]||'').split(/[,/\s]+/)[0];
  if(!reading)return ch;
  if(index===0&&INITIAL_SOUND[reading])reading=INITIAL_SOUND[reading];
  changed=true;
  return reading;
 }).join('');
 return changed?out:'';
}
// What a label should say in the chosen script; falls back to the record itself.
function scriptText(text){
 return scriptMode==='hangul'?(readingOf(text)||text):text;
}
function paintReadings(){
 if(!book)return;
 for(const name of ['title','clan_name','bon_gwan','branch_name']){
  const input=$('#bookInfoForm').elements[name];
  if(!input)continue;
  let hint=input.parentElement.querySelector('.reading');
  if(!hint){hint=document.createElement('small');hint.className='reading';input.after(hint);}
  const reading=readingOf(input.value);
  hint.textContent=reading;
  hint.hidden=!reading;
 }
}
$('#scriptToggle').onclick=async()=>{
 await busy($('#scriptToggle'),'불러오는 중…',loadHanjaDict).catch(err=>message(err.message,'error'));
 if(!hanjaReadings)return;
 scriptMode=scriptMode==='hangul'?'hanja':'hangul';
 try{localStorage.setItem('jocbo.script',scriptMode);}catch{}
 await loadBooks(book?book.id:undefined);
};
function paintScriptToggle(){
 const button=$('#scriptToggle');
 button.textContent=scriptMode==='hangul'?'한자로 보기':'한글로 보기';
 button.setAttribute('aria-pressed',String(scriptMode==='hangul'));
}
function message(text, type='success') { const el=$('#message');el.textContent=text;el.classList.toggle('error',type==='error'); }
function errorText(detail) {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(x => x.msg?.replace(/^Value error, /, '') || '입력값을 확인해 주세요.').join('\n');
  return '요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.';
}
async function api(path, method='GET', data) {
  const options = {method, credentials:'same-origin'};
  if (data instanceof FormData) options.body=data;
  else if (data !== undefined) {options.body=JSON.stringify(data);options.headers={'Content-Type':'application/json'};}
  const r=await fetch('/api'+path,options);let result={};try{result=await r.json();}catch{}
  if(!r.ok) throw Error(errorText(result.detail));
  return result;
}
function run(fn){return async e=>{try{message('');await fn(e);}catch(err){message(err.message,'error');}};}
function formData(form){return Object.fromEntries(new FormData(form));}
async function busy(button, label, task){const original=button.textContent;button.disabled=true;button.classList.add('busy');button.textContent=label;try{return await task();}finally{button.disabled=false;button.classList.remove('busy');button.textContent=original;}}
function dialogError(text='', field){const el=$('#personError');el.classList.remove('success');el.textContent=text;el.hidden=!text;$('#personForm').querySelectorAll('[aria-invalid]').forEach(x=>x.removeAttribute('aria-invalid'));if(field){field.setAttribute('aria-invalid','true');field.focus();}}
function validDate(value){if(!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;const [y,m,d]=value.split('-').map(Number),parsed=new Date(Date.UTC(y,m-1,d));return parsed.getUTCFullYear()===y&&parsed.getUTCMonth()===m-1&&parsed.getUTCDate()===d;}
async function enter(){await api('/me');$('#auth').hidden=true;$('#workspace').hidden=false;$('#logout').hidden=false;// The readings are wanted the moment the workspace opens, not after a click.
 await loadHanjaDict().catch(()=>{});await loadBooks();}
async function loadBooks(selected){const all=await api('/books');paintScriptToggle();$('#bookSelect').innerHTML=all.map(b=>`<option value="${b.id}">${esc(scriptText(b.title))}</option>`).join('');if(selected)$('#bookSelect').value=selected;await refresh();}
async function refresh(){const bid=$('#bookSelect').value;book=bid?await api('/books/'+bid):null;if(book)normalizeBookGenerations();$('#bookTitle').textContent=book?scriptText(book.title):'새 족보를 만들어 주세요';$('#relationsPanel').hidden=!book;$('#print').disabled=!book;$('#newPerson').disabled=!book;$('#bookInfoForm').hidden=!book;if(book)for(const name of ['title','clan_name','bon_gwan','branch_name','volume','description'])$('#bookInfoForm').elements[name].value=book[name]||'';paintReadings();render();renderRelations();}
$('#authForm').onsubmit=run(async e=>{e.preventDefault();await api('/login','POST',formData(e.target));await enter();});
$('#register').onclick=run(async()=>{if(!$('#authForm').reportValidity())return;const r=await api('/register','POST',formData($('#authForm')));message(r.message);});
$('#logout').onclick=run(async()=>{await api('/logout','POST');location.reload();});
$('#bookForm').onsubmit=run(async e=>{e.preventDefault();const r=await api('/books','POST',formData(e.target));e.target.reset();e.target.elements.volume.value='1';$('#bookDialog').close();await loadBooks(r.id);message('새 족보를 만들었습니다.');});
$('#bookInfoForm').oninput=paintReadings;
$('#bookInfoForm').onsubmit=run(async e=>{e.preventDefault();await busy(e.target.querySelector('button'),'저장 중…',()=>api('/books/'+book.id,'PUT',formData(e.target)));await loadBooks(book.id);message('족보 기본정보를 저장했습니다.');});
$('#bookSelect').onchange=run(refresh);
$('#search').oninput=render;
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{view=b.dataset.view;render();});
function personName(id){return book.persons.find(p=>p.id===id)?.korean_name||'';}
function hanjaNumber(value){const n=Number(value);if(!Number.isInteger(n)||n<0||n>99)return String(value||'');const digits='零一二三四五六七八九';if(n<10)return digits[n];if(n===10)return '十';const tens=n>19?digits[Math.floor(n/10)]+'十':'十';return tens+(n%10?digits[n%10]:'');}
function normalizeBookGenerations(){const byId=new Map(book.persons.map(p=>[p.id,p])),parents=book.relations.filter(r=>r.kind==='parent');for(let pass=0;pass<book.persons.length;pass++){let changed=false;for(const r of parents){const parent=byId.get(r.source_id),child=byId.get(r.target_id);if(parent&&child&&child.generation<parent.generation+1){child.generation=parent.generation+1;changed=true;}}if(!changed)break;}}
function render(){document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===view));searchNotice.hidden=true;if(!book){$('#view').innerHTML='<p class="empty">왼쪽에서 족보를 만들거나 가상 가족 예제를 추가해 보세요.</p>';return;}
 const q=$('#search').value.toLowerCase().trim();const people=book.persons.filter(p=>[p.korean_name,p.hanja_name,p.note].join(' ').toLowerCase().includes(q));
 // A filter left in the search box silently empties the tree and the book, so say so.
 if(q){searchNotice.hidden=false;searchNotice.innerHTML=`<span>검색 <strong>${esc($('#search').value.trim())}</strong> · 전체 ${book.persons.length}명 중 <strong>${people.length}명</strong>만 보고 있습니다.</span><button type="button" id="clearSearch">전체 보기</button>`;$('#clearSearch').onclick=()=>{$('#search').value='';render();};}
 if(view==='tree'){renderTree(people);return;}
 if(view==='book'){$('#view').innerHTML=bookHTML(people);return;}
 $('#view').innerHTML=people.length?'<div class="cards">'+people.map(personCard).join('')+'</div>':'<p class="empty">등록된 인물 또는 검색 결과가 없습니다.</p>';
 document.querySelectorAll('[data-person]').forEach(b=>b.onclick=()=>editPerson(Number(b.dataset.person)));
}
const HANJA_DIGITS='○一二三四五六七八九';
const HANJA_STEMS='甲乙丙丁戊己庚辛壬癸';
const HANJA_BRANCHES='子丑寅卯辰巳午未申酉戌亥';
const BOOK_ROWS=6;
function hanjaYear(year){return String(year).split('').map(d=>HANJA_DIGITS[Number(d)]??d).join('');}
function ganji(year){const n=year-4;return HANJA_STEMS[((n%10)+10)%10]+HANJA_BRANCHES[((n%12)+12)%12];}
function hanjaDate(iso,suffix){if(!/^\d{4}-\d{2}-\d{2}$/.test(iso||''))return '';const [y,m,d]=iso.split('-').map(Number);return `${hanjaYear(y)}年${ganji(y)}${hanjaNumber(m)}月${hanjaNumber(d)}日${suffix}`;}
function clanSurname(){const hanja=(book.clan_name||'').replace(/[氏씨\s]/g,'');return {hanja:/[一-鿿]/.test(hanja)?hanja[0]:'',korean:/[가-힣]/.test(hanja)?hanja[0]:''};}
// A married-in spouse shares the row with the lineage member but is printed inside
// that member's column, so only the lineage member may open a column of its own.
function lineageScore(person,parentTargets,surname){
 let score=parentTargets.has(person.id)?4:0;
 if(surname.hanja&&person.hanja_name?.[0]===surname.hanja)score+=2;
 if(surname.korean&&person.korean_name?.[0]===surname.korean)score+=2;
 return score;
}
function spousePhrase(spouse){
 const hanja=spouse.hanja_name||'',surname=hanja.slice(0,1),given=hanja.slice(1);
 const born=hanjaDate(spouse.birth_date,'生'),died=hanjaDate(spouse.death_date,'卒');
 const tail=[spouse.note,born,died].filter(Boolean).join(' ');
 if(spouse.gender==='남'){
  const origin=spouse.bon_gwan?`${spouse.bon_gwan}人`:'';
  return `夫${hanja||spouse.korean_name}(${spouse.korean_name}) ${origin} ${tail}`.replace(/\s+/g,' ').trim();
 }
 const body=spouse.bon_gwan&&given?`${spouse.bon_gwan}${surname}氏${given}`:(hanja||spouse.korean_name);
 return `配${body}(${spouse.korean_name}) ${tail}`.replace(/\s+/g,' ').trim();
}
// The book drops the clan surname from a lineage member's own name and keeps it
// only for a married-in spouse, who belongs to another clan.
function lineName(person,surname){
 const hanja=person.hanja_name||'',korean=person.korean_name||'';
 if(surname.hanja&&hanja[0]===surname.hanja&&hanja.length>1)
  return {hanja:hanja.slice(1),korean:korean.length>1&&korean[0]!==hanja[0]?korean.slice(1):korean};
 return {hanja:hanja||korean,korean};
}
function personEntry(person,spouses,surname){
 const prefix=person.gender==='여'?'女':'子',name=lineName(person,surname);
 const lines=[hanjaDate(person.birth_date,'生'),hanjaDate(person.death_date,'卒')].filter(Boolean);
 return `<section class="genealogy-person"><strong><i>${prefix}</i>${esc(name.hanja)}<em>${esc(name.korean)}</em></strong>`
  +lines.map(line=>`<span>${esc(line)}</span>`).join('')
  +(person.note?`<span class="genealogy-note">${esc(person.note)}</span>`:'')
  +spouses.map(spouse=>`<span>${esc(spousePhrase(spouse))}</span>`).join('')
  +'</section>';
}
// Columns are printed in the book's own order: each father's children stand under
// him, sons by age before daughters, so a person sorts by its ancestors' keys first.
function columnKey(person,byId,fatherOf){
 const path=[];
 for(let node=person,guard=0;node&&guard<200;guard++){
  path.unshift([node.gender==='여'?1:0,node.birth_date||'9999-99-99',node.id]);
  node=byId.get(fatherOf.get(node.id));
 }
 return path;
}
function compareKeys(a,b){
 for(let i=0;i<Math.min(a.length,b.length);i++)
  for(let j=0;j<3;j++)if(a[i][j]!==b[i][j])return a[i][j]<b[i][j]?-1:1;
 return a.length-b.length;
}
// Pairs every marriage down to one lineage member (the host) and the partner who
// married in (the guest), which both the book page and the tree need.
function spouseHosts(){
 const byId=new Map(book.persons.map(p=>[p.id,p]));
 const parentTargets=new Set(book.relations.filter(r=>r.kind==='parent').map(r=>r.target_id));
 const surname=clanSurname(),married=new Map(),hostOf=new Map();
 for(const link of book.relations.filter(r=>r.kind==='spouse')){
  const a=byId.get(link.source_id),b=byId.get(link.target_id);
  if(!a||!b)continue;
  const scoreA=lineageScore(a,parentTargets,surname),scoreB=lineageScore(b,parentTargets,surname);
  const [host,guest]=scoreA===scoreB?(a.id<b.id?[a,b]:[b,a]):(scoreA>scoreB?[a,b]:[b,a]);
  if(!married.has(host.id))married.set(host.id,[]);
  married.get(host.id).push(guest);
  hostOf.set(guest.id,host.id);
 }
 return {byId,surname,married,hostOf};
}
function fatherIndex(byId){
 const fatherOf=new Map();
 for(const link of book.relations){
  const parent=byId.get(link.source_id);
  if(link.kind==='parent'&&parent&&parent.gender!=='여')fatherOf.set(link.target_id,parent.id);
 }
 return fatherOf;
}
// The list card carries the portrait and the same facts the tree card shows, so
// browsing the list feels like reading the book rather than a bare index.
function personCard(person){
 const photo=book.files.find(file=>file.person_id===person.id&&/\.(png|jpe?g)$/i.test(file.name));
 const tone=person.gender==='남'?' male':person.gender==='여'?' female':'';
 const dates=[person.birth_date||'출생일 미상',person.death_date?'— '+person.death_date:''].filter(Boolean).join(' ');
 return `<button type="button" class="person-card${tone}" data-person="${person.id}">`
  +`<span class="person-portrait">${photo?`<img src="/api/files/${photo.id}" alt="">`:esc(person.korean_name.slice(0,1))}</span>`
  +'<span class="person-body">'
  +`<strong>${esc(person.korean_name)}</strong>`
  +`<span class="person-hanja">${esc(person.hanja_name||'한자명 미등록')}</span>`
  +`<small>${esc(dates)}</small>`
  +`<span class="badge">${person.generation}세대 · ${esc(person.gender)}</span>`
  +'</span></button>';
}
function bookHTML(people){
 const {byId,surname,married,hostOf}=spouseHosts();
 const printed=new Set(hostOf.keys());
 const keys=new Map(book.persons.map(p=>[p.id,columnKey(p,byId,fatherIndex(byId))]));
 const columns=people.filter(p=>!printed.has(p.id)).sort((a,b)=>compareKeys(keys.get(a.id),keys.get(b.id)));
 if(!columns.length)return '<p class="empty">인쇄할 기록이 없습니다.</p>';
 const generations=columns.map(p=>p.generation);
 const first=Math.min(...generations),last=Math.max(...generations);
 const volume=book.volume?`卷之${hanjaNumber(book.volume)}`:'';
 const origin=(book.description||'').trim().split(String.fromCharCode(10))[0].slice(0,24);
 const pages=[];
 // Traditional pages hold six 世 rows and repeat the last one as the next page's
 // first row, so the linking generation appears on both sheets.
 for(let top=first;top<=last;top+=BOOK_ROWS-1){
  // The first row repeats the previous sheet's last generation, so a sheet with
  // nothing below that row would only reprint what the reader already has.
  if(top>first&&!columns.some(p=>p.generation>top&&p.generation<top+BOOK_ROWS))break;
  const rows=[];
  for(let offset=0;offset<BOOK_ROWS;offset++){
   const generation=top+offset;
   const entries=columns.filter(p=>p.generation===generation)
    .map(p=>personEntry(p,married.get(p.id)||[],surname)).join('');
   rows.push(`<section class="genealogy-generation"><h3>${hanjaNumber(generation)}世</h3><div class="genealogy-entries">${entries}</div></section>`);
  }
  pages.push(`<article class="book-page traditional-book"><aside class="genealogy-side"><strong>${esc(book.title)}</strong>${volume?`<span>${esc(volume)}</span>`:''}${origin?`<small>${esc(origin)}</small>`:''}</aside><aside class="genealogy-branch">${esc(book.branch_name||book.bon_gwan||'')}</aside><div class="genealogy-body">${rows.join('')}</div></article>`);
 }
 return pages.join('');
}
// Which details each tree card shows. The set is shared by every card so one card
// height fits all, and it is remembered per browser.
const TREE_FIELDS=[['generation','세대'],['hanja','한자명'],['bon_gwan','본관'],['birth','출생일'],['death','사망일'],['age','나이'],['photo','사진'],['note','기록/생애'],['gender','성별 색']];
let treeOptions={generation:true,hanja:true,bon_gwan:false,birth:false,death:false,age:false,photo:false,note:false,gender:true};
try{Object.assign(treeOptions,JSON.parse(localStorage.getItem('jocbo.tree')||'{}'));}catch{}
function saveTreeOptions(){try{localStorage.setItem('jocbo.tree',JSON.stringify(treeOptions));}catch{}}
function ageText(person){
 if(!validDate(person.birth_date||''))return '';
 const dead=validDate(person.death_date||''),end=dead?person.death_date:new Date().toISOString().slice(0,10);
 let years=Number(end.slice(0,4))-Number(person.birth_date.slice(0,4));
 if(end.slice(5)<person.birth_date.slice(5))years--;
 // No 졸년 on a long-past birth means the record is simply unfinished, not a 139-year-old.
 if(years<0||(!dead&&years>120))return '';
 return (dead?'향년 ':'만 ')+years+'세';
}
// Every card keeps the same number of detail rows, empty ones included, so the rows
// of the tree stay level.
function treeDetailRows(){
 return [treeOptions.generation||treeOptions.hanja,treeOptions.bon_gwan,treeOptions.birth||treeOptions.death,treeOptions.age].filter(Boolean).length;
}
function treeDetails(person){
 const rows=[];
 if(treeOptions.generation||treeOptions.hanja)
  rows.push([treeOptions.generation?person.generation+'세대':'',treeOptions.hanja?person.hanja_name:''].filter(Boolean).join(' · '));
 if(treeOptions.bon_gwan)rows.push(person.bon_gwan?'본관 '+person.bon_gwan:'');
 if(treeOptions.birth||treeOptions.death)
  rows.push([treeOptions.birth?person.birth_date:'',treeOptions.death&&person.death_date?'— '+person.death_date:''].filter(Boolean).join(' '));
 if(treeOptions.age)rows.push(ageText(person));
 return rows;
}
function treeOptionsHTML(){
 return `<form id="treeOptions" class="tree-options"><strong>표시 항목</strong>${TREE_FIELDS.map(([name,label])=>
  `<label><input type="checkbox" name="${name}"${treeOptions[name]?' checked':''}>${label}</label>`).join('')}</form>`;
}
const RELATIVE_LABELS={parent:'부모',child:'자녀',spouse:'배우자',sibling:'형제자매'};
// Spouses alternate to the right and left of the lineage member so that every
// couple stays side by side, which is what a remarriage needs: each marriage owns
// its own children and its own line down to them.
function orderMembers(host,mates){
 const left=[],right=[];
 mates.forEach((mate,index)=>(index%2?left:right).push(mate));
 return [...left.reverse(),host,...right];
}
function renderTree(people){
 const options=treeOptionsHTML();
 if(!people.length){$('#view').innerHTML=options+'<p class="empty">표시할 인물이 없습니다.</p>';bindTreeOptions();return;}
 const {byId,married,hostOf}=spouseHosts();
 const visible=new Set(people.map(p=>p.id));
 const units=new Map(),unitOf=new Map();
 for(const p of people){
  const host=hostOf.has(p.id)&&visible.has(hostOf.get(p.id))?byId.get(hostOf.get(p.id)):p;
  if(!units.has(host.id)){
   const mates=(married.get(host.id)||[]).filter(mate=>visible.has(mate.id));
   units.set(host.id,{host,members:orderMembers(host,mates),families:[],children:[],x:0});
  }
 }
 for(const unit of units.values())for(const member of unit.members)unitOf.set(member.id,unit);
 const keys=new Map(book.persons.map(p=>[p.id,columnKey(p,byId,fatherIndex(byId))]));
 const byBookOrder=(a,b)=>compareKeys(keys.get(a.host.id),keys.get(b.host.id));
 const parentsOf=new Map();
 for(const link of book.relations){
  if(link.kind!=='parent'||!visible.has(link.source_id)||!visible.has(link.target_id))continue;
  if(!parentsOf.has(link.target_id))parentsOf.set(link.target_id,new Set());
  parentsOf.get(link.target_id).add(link.source_id);
 }
 // Children hang off the marriage they belong to, not off the person, so a second
 // marriage gets its own group and its own descent line.
 const attached=new Set();
 for(const childUnit of units.values()){
  const ids=[...(parentsOf.get(childUnit.host.id)||[])];
  const candidates=ids.map(id=>unitOf.get(id)).filter(Boolean);
  const parentUnit=candidates.find(u=>ids.includes(u.host.id))||candidates[0];
  if(!parentUnit||parentUnit===childUnit)continue;
  const mate=ids.map(id=>parentUnit.members.find(m=>m.id===id)).find(m=>m&&m.id!==parentUnit.host.id)||null;
  let family=parentUnit.families.find(f=>(f.mate?f.mate.id:null)===(mate?mate.id:null));
  if(!family){family={mate,children:[]};parentUnit.families.push(family);}
  family.children.push(childUnit);
  attached.add(childUnit.host.id);
 }
 for(const unit of units.values()){
  unit.families.sort((a,b)=>unit.members.indexOf(a.mate||unit.host)-unit.members.indexOf(b.mate||unit.host));
  unit.families.forEach(family=>family.children.sort(byBookOrder));
  unit.children=unit.families.flatMap(family=>family.children);
 }
 const roots=[...units.values()].filter(u=>!attached.has(u.host.id))
  .sort((a,b)=>a.host.generation-b.host.generation||byBookOrder(a,b));
 // Rows are the 世 numbers actually recorded, so 30세대 never shares a row with 21세대.
 const levels=[...new Set([...units.values()].map(u=>u.host.generation))].sort((a,b)=>a-b);
 const rowOf=new Map(levels.map((generation,index)=>[generation,index]));
 const detailRows=treeDetailRows();
 const nodeW=treeOptions.note?210:treeOptions.photo?188:164;
 const nodeH=30+22+detailRows*16+(treeOptions.photo?100:0)+(treeOptions.note?32:0);
 // Card size follows the chosen fields, so the gaps that the connector lines run
 // through have to grow with it instead of staying at a fixed height.
 const mateGap=18,unitGap=52,rowGap=Math.max(86,Math.round(nodeH*0.45)),padX=82,padY=46;
 const unitWidth=unit=>unit.members.length*nodeW+(unit.members.length-1)*mateGap;
 // A broken parent chain could point a branch back at itself; the seen sets keep a
 // bad record from locking the browser up while laying the tree out.
 const shift=(unit,dx,seen=new Set())=>{
  if(seen.has(unit))return;
  seen.add(unit);unit.x+=dx;unit.children.forEach(child=>shift(child,dx,seen));
 };
 const placed=new Set();
 let cursor=padX;
 // Children take the next free slots and the parents centre over them, sliding the
 // whole branch right when centring would collide with the branch already placed.
 const place=unit=>{
  if(placed.has(unit))return;
  placed.add(unit);
  if(!unit.children.length){unit.x=cursor;cursor+=unitWidth(unit)+unitGap;return;}
  const start=cursor;
  unit.children.forEach(place);
  const first=unit.children[0],last=unit.children[unit.children.length-1];
  let x=(first.x+unitWidth(first)/2+last.x+unitWidth(last)/2)/2-unitWidth(unit)/2;
  if(x<start){unit.children.forEach(child=>shift(child,start-x));x=start;}
  unit.x=x;
  cursor=Math.max(cursor,x+unitWidth(unit)+unitGap);
 };
 roots.forEach(place);
 const pos=new Map();
 for(const unit of units.values()){
  const y=padY+rowOf.get(unit.host.generation)*(nodeH+rowGap);
  unit.members.forEach((member,index)=>pos.set(member.id,{x:unit.x+index*(nodeW+mateGap),y}));
 }
 const width=Math.max(820,cursor-unitGap+padX);
 const height=padY*2+levels.length*(nodeH+rowGap)-rowGap;
 const mateLines=[...units.values()].flatMap(unit=>unit.members.filter(m=>m!==unit.host).map(mate=>{
  const a=pos.get(unit.host.id),b=pos.get(mate.id),left=a.x<b.x?a:b,right=a.x<b.x?b:a;
  return `<path class="spouse-line" d="M ${left.x+nodeW} ${left.y+nodeH/2} H ${right.x}"/>`;
 })).join('');
 const parentLines=[...units.values()].flatMap(unit=>unit.families.filter(f=>f.children.length).map(family=>{
  const host=pos.get(unit.host.id);
  const mateIndex=family.mate?unit.members.indexOf(family.mate):-1;
  const hostIndex=unit.members.indexOf(unit.host);
  const adjacent=mateIndex>=0&&Math.abs(mateIndex-hostIndex)===1;
  const mate=family.mate?pos.get(family.mate.id):null;
  // A couple drops its line from the gap between the pair; anything else drops it
  // from under the card that owns the children.
  const sx=adjacent?(Math.min(host.x,mate.x)+nodeW+Math.max(host.x,mate.x))/2
   :mate?mate.x+nodeW/2:host.x+nodeW/2;
  const sy=adjacent?host.y+nodeH/2:host.y+nodeH;
  const tops=family.children.map(child=>pos.get(child.host.id));
  const bottom=host.y+nodeH,ty=Math.min(...tops.map(top=>top.y)),railY=bottom+(ty-bottom)/2;
  const centers=tops.map(top=>top.x+nodeW/2);
  return `<path class="parent-line" d="M ${sx} ${sy} V ${railY} M ${Math.min(sx,...centers)} ${railY} H ${Math.max(sx,...centers)}"/>`
   +centers.map((cx,index)=>`<path class="parent-line" d="M ${cx} ${railY} V ${tops[index].y}"/>`).join('');
 })).join('');
 const labels=levels.map((generation,index)=>`<text class="level-label" x="16" y="${padY+index*(nodeH+rowGap)+34}">${generation}세대</text>`).join('');
 const photoOf=id=>treeOptions.photo?book.files.find(file=>file.person_id===id&&/\.(png|jpe?g)$/i.test(file.name)):null;
 const addButton=(id,kind,glyph)=>`<button type="button" class="tree-add ${kind}" data-add="${kind}" data-person="${id}" title="${RELATIVE_LABELS[kind]} 추가" aria-label="${RELATIVE_LABELS[kind]} 추가">${glyph}</button>`;
 const cards=people.filter(p=>pos.has(p.id)).map(p=>{
  const at=pos.get(p.id),photo=photoOf(p.id);
  const tone=treeOptions.gender&&p.gender!=='미상'?(p.gender==='남'?' male':' female'):'';
  return `<div class="tree-node" style="left:${at.x}px;top:${at.y}px;width:${nodeW}px;height:${nodeH}px">`
   +`<button type="button" class="tree-card${tone}" data-tree-person="${p.id}">`
   +(treeOptions.photo?`<span class="tree-photo">${photo?`<img src="/api/files/${photo.id}" alt="">`:''}</span>`:'')
   +`<strong>${esc(p.korean_name)}</strong>`
   +treeDetails(p).map(row=>`<span>${esc(row)}</span>`).join('')
   +(treeOptions.note?`<small>${esc(p.note||'')}</small>`:'')
   +'</button>'
   +addButton(p.id,'parent','+')+addButton(p.id,'child','+')
   +addButton(p.id,'spouse','+')+addButton(p.id,'sibling','+')
   +'</div>';
 }).join('');
 $('#view').innerHTML=options+`<div class="tree-scroll"><div class="tree-canvas" style="width:${width}px;height:${height}px">`
  +`<svg class="family-tree" width="${width}" height="${height}" aria-hidden="true">${parentLines}${mateLines}${labels}</svg>${cards}</div></div>`;
 bindTreeOptions();
 document.querySelectorAll('[data-tree-person]').forEach(node=>node.onclick=()=>editPerson(Number(node.dataset.treePerson)));
 document.querySelectorAll('[data-add]').forEach(node=>node.onclick=()=>addRelative(node.dataset.add,Number(node.dataset.person)));
}
function bindTreeOptions(){
 $('#treeOptions').onchange=event=>{
  treeOptions[event.target.name]=event.target.checked;
  saveTreeOptions();
  render();
 };
}
// Set while the person dialog is opened from a + button on a tree card, so saving
// creates the person and the relationship in one go.
let pendingRelative=null;
function spousesOf(id){
 return book.relations.filter(r=>r.kind==='spouse'&&(r.source_id===id||r.target_id===id))
  .map(r=>book.persons.find(p=>p.id===(r.source_id===id?r.target_id:r.source_id))).filter(Boolean);
}
function parentsOfPerson(id){
 return book.relations.filter(r=>r.kind==='parent'&&r.target_id===id)
  .map(r=>book.persons.find(p=>p.id===r.source_id)).filter(Boolean);
}
// The edges a new or picked relative needs, given who it was added from.
function relativeEdges(kind,anchor,otherId,mateId){
 if(kind==='parent')return [{source_id:otherId,target_id:anchor.id,kind:'parent'}];
 if(kind==='spouse')return [{source_id:anchor.id,target_id:otherId,kind:'spouse'}];
 if(kind==='child'){
  const edges=[{source_id:anchor.id,target_id:otherId,kind:'parent'}];
  if(mateId)edges.push({source_id:mateId,target_id:otherId,kind:'parent'});
  return edges;
 }
 return parentsOfPerson(anchor.id).map(parent=>({source_id:parent.id,target_id:otherId,kind:'parent'}));
}
function relativeGeneration(kind,anchor){
 if(kind==='parent')return Math.max(1,anchor.generation-1);
 if(kind==='child')return anchor.generation+1;
 return anchor.generation;
}
function addRelative(kind,personId){
 const anchor=book.persons.find(p=>p.id===personId);
 if(!anchor)return;
 if(kind==='sibling'&&!parentsOfPerson(anchor.id).length){
  message(`${anchor.korean_name}의 부모가 아직 없습니다. 형제자매는 부모를 통해 이어지므로 부모부터 등록해 주세요.`,'error');
  return;
 }
 editPerson();
 const mates=kind==='child'?spousesOf(anchor.id):[];
 pendingRelative={kind,anchor,mateId:mates.length?mates[0].id:null};
 $('#personHeading').textContent=`${RELATIVE_LABELS[kind]} 등록`;
 $('#relativeBanner').hidden=false;
 $('#relativeText').innerHTML=kind==='sibling'
  ? `<strong>${esc(anchor.korean_name)}</strong>의 형제자매로 등록합니다. 부모 ${esc(parentsOfPerson(anchor.id).map(p=>p.korean_name).join('·'))}에 함께 이어집니다.`
  : `<strong>${esc(anchor.korean_name)}</strong>의 ${RELATIVE_LABELS[kind]}로 등록합니다.`;
 $('#relativeMateWrap').hidden=mates.length<1;
 $('#relativeMate').innerHTML=mates.map(mate=>`<option value="${mate.id}">${esc(mate.korean_name)}</option>`).join('')
  +'<option value="">배우자 없이 (이 사람만)</option>';
 $('#relativeMate').onchange=event=>{pendingRelative.mateId=event.target.value?Number(event.target.value):null;};
 const form=$('#personForm');
 form.elements.generation.value=relativeGeneration(kind,anchor);
 if(kind!=='spouse')form.elements.bon_gwan.value=anchor.bon_gwan||book.bon_gwan||'';
 const pool=book.persons.filter(p=>p.id!==anchor.id);
 $('#relativePick').innerHTML=pool.map(p=>`<option value="${p.id}">${esc(p.korean_name)} (${p.generation}세대)</option>`).join('');
 $('#relativePickWrap').hidden=true;
 $('#relativeLink').hidden=true;
 $('#relativeToggle').hidden=!pool.length;
 $('#relativeToggle').textContent='기존 인물에서 고르기';
}
$('#relativeToggle').onclick=()=>{
 const showing=$('#relativePickWrap').hidden;
 $('#relativePickWrap').hidden=!showing;
 $('#relativeLink').hidden=!showing;
 $('#relativeToggle').textContent=showing?'새 인물로 등록하기':'기존 인물에서 고르기';
 $('#personForm').querySelector('.form-grid').hidden=showing;
 $('#savePerson').hidden=showing;
};
async function linkRelative(otherId){
 const {kind,anchor,mateId}=pendingRelative;
 for(const edge of relativeEdges(kind,anchor,otherId,mateId)){
  try{await api('/relations','POST',edge);}
  catch(err){if(!/이미 등록된 관계/.test(err.message))throw err;}
 }
}
$('#relativeLink').onclick=async()=>{
 dialogError();
 const otherId=Number($('#relativePick').value);
 if(!otherId){dialogError('연결할 인물을 선택하세요.',$('#relativePick'));return;}
 try{
  await busy($('#relativeLink'),'연결 중…',()=>linkRelative(otherId));
  $('#personDialog').close();
  await refresh();
  message('가족 관계를 추가했습니다.');
 }catch(err){dialogError(err.message);}
};
function editPerson(id){
 const f=$('#personForm');
 f.reset();dialogError();
 $('#hanjaPicker').hidden=true;
 pendingRelative=null;
 $('#relativeBanner').hidden=true;
 f.querySelector('.form-grid').hidden=false;
 $('#savePerson').hidden=false;
 f.elements.id.value=id||'';
 const p=book.persons.find(p=>p.id===id);
 if(!p)f.elements.bon_gwan.value=book.bon_gwan||'';
 if(p)Object.entries(p).forEach(([k,v])=>{if(f.elements.namedItem(k))f.elements.namedItem(k).value=v;});
 $('#personHeading').textContent=p?'인물 수정':'인물 등록';
 $('#deletePerson').hidden=!p;
 $('#attachments').hidden=!p;
 $('#fileInput').value='';
 $('#fileList').innerHTML=p?book.files.filter(x=>x.person_id===id).map(x=>`<p><a href="/api/files/${x.id}">${esc(x.name)}</a></p>`).join(''):'';
 $('#personDialog').showModal();
 setTimeout(()=>f.elements.korean_name.focus(),0);
}
$('#newPerson').onclick=()=>editPerson();$('#cancelPerson').onclick=()=>$('#personDialog').close();$('#closePersonDialog').onclick=()=>$('#personDialog').close();
async function loadHanjaIndex(){if(hanjaIndex)return hanjaIndex;const data=await fetch('/hanjaeum.json').then(r=>{if(!r.ok)throw Error('한자 사전을 불러오지 못했습니다.');return r.json();});hanjaIndex={};for(const [hanja,readings] of Object.entries(data))for(const reading of readings.split(/[,/\s]+/)){if(!hanjaIndex[reading])hanjaIndex[reading]=[];hanjaIndex[reading].push(hanja);}return hanjaIndex;}
function hanjaCandidates(syllable,index){const surnameAliases={김:['김','금'],이:['이','리'],임:['임','림'],유:['유','류'],나:['나','라'],노:['노','로'],여:['여','려'],양:['양','량']},readings=index===0?(surnameAliases[syllable]||[syllable]):[syllable],preferred={김:'金',이:'李',박:'朴',최:'崔',정:'鄭',강:'姜',조:'趙',윤:'尹',장:'張',임:'林',한:'韓',오:'吳',서:'徐',신:'申',권:'權',황:'黃',안:'安',송:'宋',전:'全',홍:'洪',유:'柳',고:'高',문:'文',양:'梁',손:'孫',배:'裵',백:'白',허:'許',남:'南',심:'沈',노:'盧'};const result=[...new Set(readings.flatMap(r=>hanjaIndex[r]||[]))].sort((a,b)=>{const common=c=>{const n=c.codePointAt(0);return n>=0x4e00&&n<=0x9fff?0:1;};return common(a)-common(b)||a.localeCompare(b,'ko');}),first=index===0?preferred[syllable]:null;if(first&&result.includes(first))return [first,...result.filter(x=>x!==first)];return result;}
function renderHanjaStep(){const {chars,chosen,index}=hanjaState;if(index>=chars.length){$('#personForm').elements.hanja_name.value=chosen.join('');$('#hanjaPicker').hidden=true;return;}const syllable=chars[index],candidates=hanjaCandidates(syllable,index),givenName=chars.slice(1).join('');$('#hanjaStep').textContent=index===0?`성 '${syllable}'의 한자를 선택하세요`:`이름 '${givenName}' 중 '${syllable}'의 한자를 선택하세요`;$('#hanjaPreview').textContent=`선택 결과: ${chosen.join('')||'아직 선택하지 않음'}`;$('#hanjaCandidates').innerHTML=candidates.length?candidates.map(h=>`<button type="button" data-hanja="${h}" title="${syllable}">${h}</button>`).join(''):'<p>해당 음의 한자 후보가 없습니다.</p>';document.querySelectorAll('[data-hanja]').forEach(button=>button.onclick=()=>{chosen.push(button.dataset.hanja);hanjaState.index++;renderHanjaStep();});}
$('#convertHanja').onclick=async()=>{const f=$('#personForm'),chars=Array.from(f.elements.korean_name.value.trim());if(chars.length<2){dialogError('한글 성명을 먼저 입력하세요.',f.elements.korean_name);return;}dialogError();try{await busy($('#convertHanja'),'불러오는 중…',loadHanjaIndex);hanjaState={chars,chosen:[],index:0};$('#hanjaPicker').hidden=false;renderHanjaStep();}catch(err){dialogError(err.message);}};
$('#closeHanja').onclick=()=>{$('#hanjaPicker').hidden=true;};
$('#personForm').onsubmit=async e=>{e.preventDefault();const f=e.target;dialogError();if(!f.reportValidity())return;const birth=f.elements.birth_date,death=f.elements.death_date;if(birth.value&&!validDate(birth.value)){dialogError('출생일은 유효한 날짜를 연도 4자리로 입력하세요. 예: 1956-02-07',birth);return;}if(death.value&&!validDate(death.value)){dialogError('사망일은 유효한 날짜를 연도 4자리로 입력하세요. 예: 2020-02-07',death);return;}if(birth.value&&death.value&&death.value<birth.value){dialogError('사망일은 출생일보다 빠를 수 없습니다.',death);return;}const data=formData(f),id=data.id;delete data.id;data.generation=Number(data.generation);try{const relative=pendingRelative;const saved=await busy($('#savePerson'),'저장 중…',()=>api(id?'/persons/'+id:'/books/'+book.id+'/persons',id?'PUT':'POST',data));if(!id&&relative){pendingRelative=relative;await linkRelative(saved.id);pendingRelative=null;}$('#personDialog').close();if(!id)$('#search').value='';await refresh();message(id?'인물을 저장했습니다.':relative?`${relative.anchor.korean_name}의 ${RELATIVE_LABELS[relative.kind]}로 등록했습니다.`:'인물을 등록했습니다. 검색어를 해제해 전체를 보여 드립니다.');}catch(err){dialogError(err.message);}};
$('#deletePerson').onclick=async()=>{if(!confirm('이 인물과 연결된 관계 및 첨부파일이 모두 삭제됩니다. 계속할까요?'))return;dialogError();try{await busy($('#deletePerson'),'삭제 중…',()=>api('/persons/'+$('#personForm').elements.id.value,'DELETE'));$('#personDialog').close();await refresh();message('인물을 삭제했습니다.');}catch(err){dialogError(err.message);}};
$('#upload').onclick=async()=>{dialogError();const file=$('#fileInput').files[0];if(!file){dialogError('업로드할 파일을 먼저 선택하세요.',$('#fileInput'));return;}if(file.size>5*1024*1024){dialogError('파일은 5MB 이하만 업로드할 수 있습니다.',$('#fileInput'));return;}const id=Number($('#personForm').elements.id.value),data=new FormData();data.append('file',file);try{await busy($('#upload'),'업로드 중…',()=>api('/persons/'+id+'/files','POST',data));await refresh();$('#fileList').innerHTML=book.files.filter(x=>x.person_id===id).map(x=>`<p><a href="/api/files/${x.id}">${esc(x.name)}</a></p>`).join('');$('#fileInput').value='';const el=$('#personError');el.textContent='첨부파일을 저장했습니다.';el.hidden=false;el.classList.add('success');}catch(err){dialogError(err.message);}};
function renderRelations(){if(!book)return;const options=book.persons.map(p=>`<option value="${p.id}">${esc(p.korean_name)} (${p.generation}세대)</option>`).join('');['source_id','target_id'].forEach(n=>$('#relationForm').elements[n].innerHTML=options);$('#relationForm').querySelector('button').disabled=book.persons.length<2;$('#relationList').innerHTML=book.relations.map(r=>`<div class="relation-row"><span>${esc(personName(r.source_id))} ${r.kind==='parent'?'→ 자녀':'↔ 배우자'} ${esc(personName(r.target_id))}</span><button class="secondary" data-relation="${r.id}">관계 삭제</button></div>`).join('')||(book.persons.length<2?'<p class="muted">관계를 등록하려면 인물을 2명 이상 추가하세요.</p>':'');document.querySelectorAll('[data-relation]').forEach(b=>b.onclick=run(async()=>{if(!confirm('이 관계를 삭제할까요?'))return;await api('/relations/'+b.dataset.relation,'DELETE');await refresh();message('관계를 삭제했습니다.');}));}
$('#relationForm').onsubmit=run(async e=>{e.preventDefault();const d=formData(e.target);if(d.source_id===d.target_id)throw Error('서로 다른 인물을 선택하세요.');d.source_id=Number(d.source_id);d.target_id=Number(d.target_id);await api('/relations','POST',d);await refresh();message('가족 관계를 추가했습니다.');});
$('#print').onclick=()=>{view='book';$('#search').value='';render();window.print();};
$('#sample').onclick=run(async()=>{const button=$('#sample');button.disabled=true;try{const b=await api('/books','POST',{title:'가상 가족의 기록 (샘플)',clan_name:'예시 김씨',description:'실존 인물과 무관한 예제입니다.'});const people=[{korean_name:'김예시',hanja_name:'金例示',generation:1,birth_date:'1940-01-01',gender:'남'},{korean_name:'이샘플',hanja_name:'李樣本',generation:1,birth_date:'1942-02-02',gender:'여'},{korean_name:'김가상',hanja_name:'金假想',generation:2,birth_date:'1970-03-03',gender:'남'},{korean_name:'김미래',hanja_name:'金未來',generation:3,birth_date:'2000-04-04',gender:'미상'}];const ids=[];for(const p of people)ids.push((await api('/books/'+b.id+'/persons','POST',{...p,note:'실제 개인정보가 아닌 가상 인물입니다.'})).id);for(const [s,t,kind] of [[0,1,'spouse'],[0,2,'parent'],[1,2,'parent'],[2,3,'parent']])await api('/relations','POST',{source_id:ids[s],target_id:ids[t],kind});await loadBooks(b.id);message('가상 가족 예제를 추가했습니다.');}finally{button.disabled=false;}});
enter().catch(()=>{});
