const $ = s => document.querySelector(s);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let book = null, view = 'people', hanjaIndex = null, hanjaState = null;
$('#newBook').onclick=()=>{paintNewBookFields();$('#bookDialog').showModal();setTimeout(()=>$('#bookForm').elements.title.focus(),0);};
$('#closeBookDialog').onclick=()=>$('#bookDialog').close();
// The sidebar width is the reader's to set, and it is remembered per browser.
const SIDE_MIN=200,SIDE_MAX=620;
let sideWidth=286;
try{sideWidth=Number(localStorage.getItem('jocbo.sideWidth'))||sideWidth;}catch{}
function applySideWidth(px){
 sideWidth=Math.min(SIDE_MAX,Math.max(SIDE_MIN,Math.round(px)));
 document.documentElement.style.setProperty('--side-width',sideWidth+'px');
 $('#sideResizer').setAttribute('aria-valuenow',String(sideWidth));
 try{localStorage.setItem('jocbo.sideWidth',String(sideWidth));}catch{}
}
applySideWidth(sideWidth);
$('#sideResizer').setAttribute('aria-valuemin',String(SIDE_MIN));
$('#sideResizer').setAttribute('aria-valuemax',String(SIDE_MAX));
$('#sideResizer').onpointerdown=event=>{
 event.preventDefault();
 const handle=$('#sideResizer'),left=$('#workspace').getBoundingClientRect().left;
 // Capture keeps the drag alive over the page; the window listeners keep it alive
 // even where capture is refused.
 try{handle.setPointerCapture(event.pointerId);}catch{}
 document.body.classList.add('resizing');
 const move=moved=>applySideWidth(moved.clientX-left);
 const stop=()=>{
  window.removeEventListener('pointermove',move);
  window.removeEventListener('pointerup',stop);
  window.removeEventListener('pointercancel',stop);
  document.body.classList.remove('resizing');
 };
 window.addEventListener('pointermove',move);
 window.addEventListener('pointerup',stop);
 window.addEventListener('pointercancel',stop);
};
$('#sideResizer').ondblclick=()=>applySideWidth(286);
$('#sideResizer').onkeydown=event=>{
 const step=event.shiftKey?48:16;
 if(event.key==='ArrowLeft'){applySideWidth(sideWidth-step);event.preventDefault();}
 if(event.key==='ArrowRight'){applySideWidth(sideWidth+step);event.preventDefault();}
};
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
// Three switches: the records on the page, the sidebar's own list and edit
// boxes, and the windows that cover them. Each stands alone, because reading one
// of them in hangul should not turn the others over with it.
let scriptMode='hanja',sideScriptMode='hanja',dialogScriptMode='hanja';
try{
 scriptMode=localStorage.getItem('jocbo.script')==='hangul'?'hangul':'hanja';
 sideScriptMode=localStorage.getItem('jocbo.sideScript')==='hangul'?'hangul':'hanja';
 dialogScriptMode=localStorage.getItem('jocbo.dialogScript')==='hangul'?'hangul':'hanja';
}catch{}
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
  // A surname reads as a surname where a name begins: before 氏, or at the start of
  // a word, which is what 金之岱 is inside 英憲公(金之岱).
  const opensWord=index===0||!/[一-鿿]/.test(chars[index-1]);
  if(HANJA_SURNAME[ch]&&(chars[index+1]==='氏'||opensWord)){changed=true;return HANJA_SURNAME[ch];}
  let reading=(hanjaReadings[ch]||'').split(/[,/\s]+/)[0];
  if(!reading)return ch;
  if(index===0&&INITIAL_SOUND[reading])reading=INITIAL_SOUND[reading];
  changed=true;
  return reading;
 }).join('');
 return changed?collapseEcho(out):'';
}
// Records often write a name as 東錫(동석); once the hanja is read the bracket
// only repeats what precedes it, so 동석(동석) collapses back to 동석.
function collapseEcho(text){
 let out='';
 for(let index=0;index<text.length;index++){
  if(text[index]==='('){
   const close=text.indexOf(')',index);
   const inner=close>index?text.slice(index+1,close):'';
   if(inner&&out.endsWith(inner)){index=close;continue;}
  }
  out+=text[index];
 }
 return out;
}
// What a label should say in the chosen script; falls back to the record itself.
function scriptText(text){
 return scriptMode==='hangul'?(readingOf(text)||text):text;
}
function sideScriptText(text){
 return sideScriptMode==='hangul'?(readingOf(text)||text):text;
}
function dialogScriptText(text){
 return dialogScriptMode==='hangul'?(readingOf(text)||text):text;
}
// 성별 is a fixed choice rather than a transcribed name, so its hanja is set
// here instead of looked up. These are the characters the book itself uses for a
// son and a daughter — 子 and 女, not 男 and 女. What is stored stays hangul in
// either script.
const GENDER_HANJA={미상:'未詳',남:'子',여:'女'};
function genderText(gender,mode=scriptMode){
 return mode==='hangul'?gender:(GENDER_HANJA[gender]||gender);
}
const BOOK_SCRIPT_FIELDS=['title','clan_name','bon_gwan','branch_name','founder'];
// The edit fields read in whichever script is switched on. Each remembers what is
// on record and what it was shown as, so reading a book in hangul and saving it
// never overwrites the hanja — only a field the user actually typed into changes.
function paintBookFields(){
 if(!book)return;
 for(const name of BOOK_SCRIPT_FIELDS){
  const input=$('#bookInfoForm').elements[name];
  if(!input)continue;
  const stored=book[name]||'';
  input.dataset.stored=stored;
  input.value=sideScriptText(stored);
  input.dataset.shown=input.value;
 }
}
function bookFormValues(form){
 const data=formData(form);
 for(const name of BOOK_SCRIPT_FIELDS){
  const input=form.elements[name];
  if(input&&input.value===input.dataset.shown)data[name]=input.dataset.stored;
 }
 return data;
}
function paintReadingFor(input,text){
 if(!input)return;
 // The hint belongs under the whole row, not between the box and its 한자 button.
 const row=input.closest('label')||input.parentElement;
 let hint=row.querySelector('.reading');
 if(!hint){hint=document.createElement('small');hint.className='reading';row.append(hint);}
 // Only hanja needs explaining; in hangul the box already reads plainly. A
 // select shows a label rather than its value, so it passes its own reading in.
 const reading=text===undefined?readingOf(input.value):text;
 hint.textContent=reading;
 hint.hidden=!reading;
}
// A new book has no record behind it yet, so each box is its own: what is typed
// becomes the value, and the switch only changes how it is shown back.
function paintNewBookFields(){
 const form=$('#bookForm');
 for(const name of BOOK_SCRIPT_FIELDS){
  const input=form.elements[name];
  if(!input)continue;
  if(input.value!==input.dataset.shown)input.dataset.stored=input.value;
  input.value=dialogScriptText(input.dataset.stored||'');
  input.dataset.shown=input.value;
  paintReadingFor(input);
 }
}
function paintReadings(){
 if(!book)return;
 for(const name of BOOK_SCRIPT_FIELDS)paintReadingFor($('#bookInfoForm').elements[name]);
}
const SCRIPT_SWITCHES={
 page:{key:'jocbo.script',get:()=>scriptMode,set:mode=>{scriptMode=mode;}},
 side:{key:'jocbo.sideScript',get:()=>sideScriptMode,set:mode=>{sideScriptMode=mode;}},
 dialog:{key:'jocbo.dialogScript',get:()=>dialogScriptMode,set:mode=>{dialogScriptMode=mode;}}
};
async function toggleScript(button){
 await busy(button,'불러오는 중…',loadHanjaDict).catch(err=>message(err.message,'error'));
 if(!hanjaReadings)return;
 const which=button.dataset.scriptToggle||'page',switcher=SCRIPT_SWITCHES[which];
 switcher.set(switcher.get()==='hangul'?'hanja':'hangul');
 try{localStorage.setItem(switcher.key,switcher.get());}catch{}
 paintScriptToggle();
 // A window's switch turns that window over and leaves the page behind it alone.
 if(which==='dialog'){paintPersonScript();paintRelativeBanner();paintNewBookFields();return;}
 await loadBooks(book?book.id:undefined);
}
// One switch beside the view tabs, one the windows share, and the sidebar's own.
document.querySelectorAll('[data-script-toggle]').forEach(button=>{
 button.onclick=()=>toggleScript(button);
});
// The book's own details read across the page under its title, where there is
// room for them, instead of stacking down a 286px sidebar and running off screen.
function paintBookFacts(){
 const box=$('#bookFacts');
 if(!book){box.hidden=true;return;}
 const items=[['성씨 / 가문',book.clan_name],['본관',book.bon_gwan],['파명',book.branch_name],
  ['권',book.volume?book.volume+'권':''],['시조',book.founder]]
  .filter(([,value])=>value);
 box.hidden=!items.length;
 box.innerHTML=items.map(([label,value])=>{
  const primary=scriptText(value),other=primary===value?readingOf(value):value;
  return `<div><dt>${esc(label)}</dt><dd>${esc(primary)}${other?`<span>${esc(other)}</span>`:''}</dd></div>`;
 }).join('');
}
function paintScriptToggle(){
 document.querySelectorAll('[data-script-toggle]').forEach(button=>{
  const mode=SCRIPT_SWITCHES[button.dataset.scriptToggle||'page'].get();
  button.textContent=mode==='hangul'?'한자로 보기':'한글로 보기';
  button.setAttribute('aria-pressed',String(mode==='hangul'));
 });
}
// A person's 본관 is a stored hanja value like the book's, so it reads in the
// chosen script and remembers what it was shown as before it is saved.
const PERSON_SCRIPT_FIELDS=['bon_gwan','note'];
function setPersonScriptField(name,value){
 const input=$('#personForm').elements[name];
 if(!input)return;
 input.dataset.stored=value||'';
 input.value=dialogScriptText(value||'');
 input.dataset.shown=input.value;
 if(name==='bon_gwan')paintReadingFor(input);
}
function paintGenderScript(){
 const select=$('#personForm').elements.gender;
 if(!select)return;
 const hanja=dialogScriptMode!=='hangul';
 for(const option of select.options)option.textContent=hanja?GENDER_HANJA[option.value]||option.value:option.value;
 paintReadingFor(select,hanja?select.value:'');
}
function setPersonScriptFields(person){
 setPersonScriptField('bon_gwan',person.bon_gwan);
 setPersonScriptField('note',person.note);
 paintGenderScript();
}
function paintPersonScript(){
 for(const name of PERSON_SCRIPT_FIELDS){
  const input=$('#personForm').elements[name];
  if(input)setPersonScriptField(name,input.dataset.stored??input.value);
 }
 paintGenderScript();
}
// Asked before anything is written. Enter in a form submits it straight away, so
// a stray keypress used to file a record with no sign of where it went; this
// stops and says what is about to happen and where it will land. 취소 takes the
// focus, so a second stray Enter turns the save down rather than waving it past.
let confirmSettle=null;
function ask(question,okLabel='확인'){
 $('#confirmText').textContent=question;
 $('#confirmOk').textContent=okLabel;
 if(!$('#confirmDialog').open)$('#confirmDialog').showModal();
 setTimeout(()=>$('#confirmCancel').focus(),0);
 return new Promise(resolve=>{confirmSettle=resolve;});
}
function settleConfirm(answer){
 const settle=confirmSettle;
 confirmSettle=null;
 if($('#confirmDialog').open)$('#confirmDialog').close();
 if(settle)settle(answer);
}
$('#confirmOk').onclick=()=>settleConfirm(true);
$('#confirmCancel').onclick=()=>settleConfirm(false);
// Esc closes a dialog on its own, and that is a no.
$('#confirmDialog').addEventListener('close',()=>settleConfirm(false));
// The notice now covers part of the page, so it clears itself once it has been
// read — an error is left up longer than a confirmation.
let messageTimer;
function message(text, type='success') {
 const el=$('#message');
 el.textContent=text;
 el.classList.toggle('error',type==='error');
 clearTimeout(messageTimer);
 if(text)messageTimer=setTimeout(()=>{el.textContent='';},type==='error'?14000:4500);
}
$('#message').onclick=()=>message('');
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
// Every rule a date has to keep, in one place and asked first. The form carries
// novalidate so that this speaks before the browser refuses the submit with a
// bubble of its own — which is what used to happen, leaving nothing filed and
// nothing said. reportValidity still follows, for the required boxes.
function dateProblem(get){
 const today=todayISO();
 for(const [name,label] of [['birth_date','출생일'],['death_date','사망일']]){
  const box=get(name);
  if(!box)continue;
  // A date the browser could not make sense of — 31 February, 29 February in a
  // year with 28 — reads back empty while its segments still show the typing.
  if(box.validity.badInput)
   return [box,`${label} — 없는 날짜 · 월 1~12, 일은 해당 월의 마지막 날까지 · 예: 1956-02-07`];
  if(box.value&&!validDate(box.value))
   return [box,`${label} — 연도 4자리 형식 · 예: 1956-02-07`];
  if(box.value&&box.value>today)
   return [box,`${label} — 아직 오지 않은 날 · 오늘(${today}) 이후 불가`];
 }
 const birth=get('birth_date'),death=get('death_date');
 if(birth&&death&&birth.value&&death.value&&death.value<birth.value)
  return [death,'사망일이 출생일보다 이름'];
 return null;
}
// By the browser's own clock, not UTC: in Korea the two differ for the first
// nine hours of every day, and a birth recorded this morning is not the future.
function todayISO(){
 const now=new Date();
 return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
}
// 1956-04-27 read back as words, so a month the box quietly corrected is seen
// before it is filed. Typing 43 for a month leaves 4 behind without a murmur.
function plainDate(value){
 const [y,m,d]=value.split('-').map(Number);
 return `${y}년 ${m}월 ${d}일`;
}
function validDate(value){if(!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;const [y,m,d]=value.split('-').map(Number),parsed=new Date(Date.UTC(y,m-1,d));return parsed.getUTCFullYear()===y&&parsed.getUTCMonth()===m-1&&parsed.getUTCDate()===d;}
async function enter(){await api('/me');$('#auth').hidden=true;$('#workspace').hidden=false;$('#logout').hidden=false;// The readings are wanted the moment the workspace opens, not after a click.
 await loadHanjaDict().catch(()=>{});await loadBooks();}
async function loadBooks(selected){const all=await api('/books');paintScriptToggle();$('#bookSelect').innerHTML=all.map(b=>`<option value="${b.id}">${esc(sideScriptText(b.title))}</option>`).join('');if(selected)$('#bookSelect').value=selected;await refresh();}
async function refresh(){const bid=$('#bookSelect').value;book=bid?await api('/books/'+bid):null;if(book)normalizeBookGenerations();$('#bookTitle').textContent=book?scriptText(book.title):'족보 없음';$('#relationsPanel').hidden=!book;$('#print').disabled=!book;$('#newPerson').disabled=!book;$('#bookInfoForm').hidden=!book;if(book){for(const name of ['volume','description'])$('#bookInfoForm').elements[name].value=book[name]||'';paintBookFields();}paintReadings();paintBookFacts();render();renderRelations();}
$('#authForm').onsubmit=run(async e=>{e.preventDefault();await api('/login','POST',formData(e.target));await enter();});
$('#register').onclick=run(async()=>{if(!$('#authForm').reportValidity())return;const r=await api('/register','POST',formData($('#authForm')));message(r.message);});
$('#logout').onclick=run(async()=>{await api('/logout','POST');location.reload();});
$('#bookForm').onsubmit=run(async e=>{e.preventDefault();const r=await api('/books','POST',bookFormValues(e.target));e.target.reset();e.target.elements.volume.value='1';paintNewBookFields();$('#bookDialog').close();await loadBooks(r.id);message('새 족보 생성 완료');});
$('#bookInfoForm').oninput=paintReadings;
$('#bookInfoForm').onsubmit=run(async e=>{e.preventDefault();await busy(e.target.querySelector('button'),'저장 중…',()=>api('/books/'+book.id,'PUT',bookFormValues(e.target)));await loadBooks(book.id);message('족보 기본정보 저장 완료');});
$('#bookSelect').onchange=run(refresh);
$('#search').oninput=()=>{render();renderRelations();};
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{view=b.dataset.view;render();});
function personName(id){return book.persons.find(p=>p.id===id)?.korean_name||'';}
function hanjaNumber(value){const n=Number(value);if(!Number.isInteger(n)||n<0||n>99)return String(value||'');const digits='零一二三四五六七八九';if(n<10)return digits[n];if(n===10)return '十';const tens=n>19?digits[Math.floor(n/10)]+'十':'十';return tens+(n%10?digits[n%10]:'');}
function normalizeBookGenerations(){const byId=new Map(book.persons.map(p=>[p.id,p])),parents=book.relations.filter(r=>r.kind==='parent');for(let pass=0;pass<book.persons.length;pass++){let changed=false;for(const r of parents){const parent=byId.get(r.source_id),child=byId.get(r.target_id);if(parent&&child&&child.generation<parent.generation+1){child.generation=parent.generation+1;changed=true;}}if(!changed)break;}}
function render(){document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===view));searchNotice.hidden=true;if(!book){$('#view').innerHTML='<p class="empty">족보 없음 — 왼쪽에서 새 족보 또는 예제 추가</p>';return;}
 const q=$('#search').value.toLowerCase().trim();const people=book.persons.filter(p=>[p.korean_name,p.hanja_name,p.note].join(' ').toLowerCase().includes(q));
 // A search narrows the list. The tree and the book are drawings of the whole
 // family, so they keep everyone and move to the person who was found instead.
 if(q){
  searchNotice.hidden=false;
  searchNotice.innerHTML=(view==='people'
   ?`<span>검색 <strong>${esc($('#search').value.trim())}</strong> · 전체 ${book.persons.length}명 중 <strong>${people.length}명</strong></span>`
   :`<span>검색 <strong>${esc($('#search').value.trim())}</strong> · ${people.length?'<strong>'+esc(displayName(people[0]).primary)+'</strong> 위치로 이동':'결과 없음'}</span>`)
   +'<button type="button" id="clearSearch">전체 보기</button>';
  // Clearing the box puts the list back and takes the ring off the tree.
  $('#clearSearch').onclick=()=>{
   $('#search').value='';
   $('#relationForm').elements.source_id.value='';
   zoomScrollAt.delete(view);
   render();
   renderRelations();
   const frame=$('.zoom-scroll');
   if(frame)frame.scrollTo(0,0);
  };
 }
 if(view==='tree'){renderTree(book.persons);markFound(q?people[0]:null,'[data-tree-person]');return;}
 if(view==='book'){const sheets=bookHTML(book.persons);$('#view').innerHTML=sheets.includes('traditional-book')?wrapZoom(sheets):sheets;bindZoom('book');markFound(q?people[0]:null,'[data-book-person]');return;}
 $('#view').innerHTML=people.length?'<div class="cards">'+people.map(personCard).join('')+'</div>':'<p class="empty">등록된 인물 없음</p>';
 document.querySelectorAll('[data-person]').forEach(b=>b.onclick=()=>editPerson(Number(b.dataset.person)));
}
// A whole tree or a whole book is too large to search by eye, so the person who
// was searched for is brought into view and ringed.
function markFound(person,selector){
 document.querySelectorAll('.found').forEach(node=>node.classList.remove('found'));
 if(!person)return;
 const node=document.querySelector(`${selector.slice(0,-1)}="${person.id}"]`);
 if(!node)return;
 node.classList.add('found');
 const frame=node.closest('.zoom-scroll');
 if(!frame){node.scrollIntoView({block:'center',inline:'center'});return;}
 // scrollIntoView would drag the page about too, so the frame is moved on its own.
 const spot=node.getBoundingClientRect(),within=frame.getBoundingClientRect();
 frame.scrollLeft+=spot.left-within.left-(within.width-spot.width)/2;
 frame.scrollTop+=spot.top-within.top-(within.height-spot.height)/2;
}
const HANJA_DIGITS='○一二三四五六七八九';
const HANJA_STEMS='甲乙丙丁戊己庚辛壬癸';
const HANJA_BRANCHES='子丑寅卯辰巳午未申酉戌亥';
const BOOK_ROWS=6;
function hanjaYear(year){return String(year).split('').map(d=>HANJA_DIGITS[Number(d)]??d).join('');}
function ganji(year){const n=year-4;return HANJA_STEMS[((n%10)+10)%10]+HANJA_BRANCHES[((n%12)+12)%12];}
const KR_STEMS='갑을병정무기경신임계';
const KR_BRANCHES='자축인묘진사오미신유술해';
function ganjiKorean(year){const n=year-4;return KR_STEMS[((n%10)+10)%10]+KR_BRANCHES[((n%12)+12)%12];}
// The sheet keeps its shape in either script; only the words change.
function bookDate(iso,kind){
 if(!/^\d{4}-\d{2}-\d{2}$/.test(iso||''))return '';
 const [y,m,d]=iso.split('-').map(Number);
 if(scriptMode==='hangul')return `${y}년 ${ganjiKorean(y)} ${m}월 ${d}일${kind==='生'?'생':'졸'}`;
 return `${hanjaYear(y)}年${ganji(y)}${hanjaNumber(m)}月${hanjaNumber(d)}日${kind}`;
}
function bookWord(hanja,hangul){return scriptMode==='hangul'?hangul:hanja;}
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
 const born=bookDate(spouse.birth_date,'生'),died=bookDate(spouse.death_date,'卒');
 const note=scriptMode==='hangul'?(readingOf(spouse.note)||spouse.note):spouse.note;
 const tail=[note,born,died].filter(Boolean).join(' ');
 if(spouse.gender==='남'){
  const origin=spouse.bon_gwan?`${scriptText(spouse.bon_gwan)}${bookWord('人',' 사람')}`:'';
  const name=scriptMode==='hangul'?spouse.korean_name:`${hanja||spouse.korean_name}(${spouse.korean_name})`;
  return `${bookWord('夫','남편 ')}${name} ${origin} ${tail}`.replace(/\s+/g,' ').trim();
 }
 if(scriptMode==='hangul'){
  const clan=spouse.bon_gwan?`${readingOf(spouse.bon_gwan)||spouse.bon_gwan} `:'';
  return `배우자 ${clan}${spouse.korean_name} ${tail}`.replace(/\s+/g,' ').trim();
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
 const hangul=scriptMode==='hangul';
 const prefix=person.gender==='여'?bookWord('女','딸'):bookWord('子','아들'),name=lineName(person,surname);
 const lines=[bookDate(person.birth_date,'生'),bookDate(person.death_date,'卒')].filter(Boolean);
 const note=hangul?(readingOf(person.note)||person.note):person.note;
 return `<section class="genealogy-person" data-book-person="${person.id}"><strong><i>${prefix}</i>`
  +`${esc(hangul?name.korean:name.hanja)}<em>${esc(hangul?name.hanja:name.korean)}</em></strong>`
  +lines.map(line=>`<span>${esc(line)}</span>`).join('')
  +(note?`<span class="genealogy-note">${esc(note)}</span>`:'')
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
// Which of a person's two names leads, and which follows underneath.
function displayName(person,mode=scriptMode){
 const hanja=person.hanja_name||'',korean=person.korean_name||'';
 return mode==='hangul'
  ?{primary:korean,other:hanja}
  :{primary:hanja||korean,other:hanja?korean:''};
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
  +`<strong>${esc(displayName(person).primary)}</strong>`
  +`<span class="person-hanja">${esc(displayName(person).other||'한자명 미등록')}</span>`
  +`<small>${esc(dates)}</small>`
  +`<span class="badge">${person.generation}세대 · ${esc(genderText(person.gender))}</span>`
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
 const volume=book.volume?bookWord(`卷之${hanjaNumber(book.volume)}`,`${book.volume}권`):'';
 const origin=book.founder?bookWord('始祖 '+book.founder,'시조 '+scriptText(book.founder)):'';
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
   rows.push(`<section class="genealogy-generation"><h3>${bookWord(hanjaNumber(generation)+'世',generation+'세')}</h3><div class="genealogy-entries">${entries}</div></section>`);
  }
  pages.push(`<article class="book-page traditional-book"><aside class="genealogy-side"><strong>${esc(scriptText(book.title))}</strong>${volume?`<span>${esc(volume)}</span>`:''}${origin?`<small>${esc(origin)}</small>`:''}</aside><aside class="genealogy-branch">${esc(scriptText(book.branch_name||book.bon_gwan||''))}</aside><div class="genealogy-body">${rows.join('')}</div></article>`);
 }
 return pages.join('');
}
// Which details each tree card shows. The set is shared by every card so one card
// height fits all, and it is remembered per browser.
const TREE_FIELDS=[['generation','세대'],['hanja','이름 병기'],['bon_gwan','본관'],['birth','출생일'],['death','사망일'],['age','나이'],['photo','사진'],['note','기록/생애'],['gender','성별 색']];
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
  rows.push([treeOptions.generation?person.generation+'세대':'',treeOptions.hanja?displayName(person).other:''].filter(Boolean).join(' · '));
 if(treeOptions.bon_gwan)rows.push(person.bon_gwan?'본관 '+scriptText(person.bon_gwan):'');
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
// Zooming keeps the point under the pointer still, so a wide tree can be pulled
// back to see its shape and pushed in to read a card without losing your place.
const ZOOM_MIN=0.25,ZOOM_MAX=3;
function wrapZoom(inner){
 return '<div class="zoom-bar">'
  +'<button type="button" class="secondary" data-zoom="out" aria-label="축소">−</button>'
  +'<span class="zoom-level">100%</span>'
  +'<button type="button" class="secondary" data-zoom="in" aria-label="확대">+</button>'
  +'<button type="button" class="secondary" data-zoom="reset">100%</button>'
  +'<button type="button" class="secondary" data-zoom="fit">맞추기</button>'
  +'<small>끌어서 이동 · Ctrl + 휠로 확대·축소</small></div>'
  +`<div class="zoom-scroll"><div class="zoom-sizer"><div class="zoom-body">${inner}</div></div></div>`;
}
// Switching script or a display option redraws the whole view, so where the
// reader had scrolled to is kept and put back rather than snapping to the corner.
const zoomScrollAt=new Map();
function bindZoom(key){
 const scroll=$('.zoom-scroll'),sizer=$('.zoom-sizer'),body=$('.zoom-body'),level=$('.zoom-level');
 if(!scroll)return;
 const wasAt=zoomScrollAt.get(key);
 body.style.transform='none';
 const base={w:body.scrollWidth,h:body.scrollHeight};
 let zoom=1;
 try{zoom=Number(localStorage.getItem('jocbo.zoom.'+key))||1;}catch{}
 const apply=(next,pointerX,pointerY)=>{
  const previous=zoom;
  zoom=Math.min(ZOOM_MAX,Math.max(ZOOM_MIN,next));
  const box=scroll.getBoundingClientRect();
  const ax=pointerX===undefined?box.width/2:pointerX-box.left;
  const ay=pointerY===undefined?box.height/2:pointerY-box.top;
  const px=(scroll.scrollLeft+ax)/previous,py=(scroll.scrollTop+ay)/previous;
  body.style.transform=`scale(${zoom})`;
  sizer.style.width=Math.round(base.w*zoom)+'px';
  sizer.style.height=Math.round(base.h*zoom)+'px';
  scroll.scrollLeft=px*zoom-ax;
  scroll.scrollTop=py*zoom-ay;
  level.textContent=Math.round(zoom*100)+'%';
  try{localStorage.setItem('jocbo.zoom.'+key,String(zoom));}catch{}
 };
 apply(zoom);
 if(wasAt){scroll.scrollLeft=wasAt.left;scroll.scrollTop=wasAt.top;}
 scroll.addEventListener('scroll',()=>zoomScrollAt.set(key,{left:scroll.scrollLeft,top:scroll.scrollTop}));
 // Dragging the canvas beats reaching for the scrollbar once the tree is wider
 // than the window. The plain wheel keeps scrolling; Ctrl with it zooms about the
 // pointer, which stays put while everything around it grows.
 scroll.addEventListener('wheel',event=>{
  if(!event.ctrlKey&&!event.metaKey)return;
  event.preventDefault();
  apply(zoom*(event.deltaY<0?1.12:1/1.12),event.clientX,event.clientY);
 },{passive:false});
 let pan=null,dragged=false;
 // Where the press lands decides what the drag means. Running prose is left alone
 // so it can be swept and copied; everywhere else — canvas, cards, the handles on
 // them — moves the view, since a press inside a button never starts a selection
 // anyway and a drag there would otherwise do nothing at all. A press that does
 // not move still counts as a click.
 const KEEPS_ITS_OWN_DRAG='.tree-card strong,.tree-card small,.tree-line,.genealogy-person,.genealogy-side,.genealogy-branch,.genealogy-generation h3,input,textarea,select,a';
 // Nothing is cancelled on the press itself: doing so swallows the click the
 // browser would fire afterwards, and a card could no longer be opened. The press
 // only notes where it began; the drag declares itself on the first real movement.
 scroll.addEventListener('pointerdown',event=>{
  const middle=event.button===1;
  if(!middle&&event.button!==0)return;
  if(!middle&&event.target.closest(KEEPS_ITS_OWN_DRAG))return;
  pan={x:event.clientX,y:event.clientY,left:scroll.scrollLeft,top:scroll.scrollTop};
  dragged=false;
 });
 scroll.addEventListener('pointermove',event=>{
  if(!pan)return;
  const dx=event.clientX-pan.x,dy=event.clientY-pan.y;
  if(!dragged&&Math.abs(dx)<4&&Math.abs(dy)<4)return;
  if(!dragged){
   dragged=true;
   scroll.classList.add('panning');
   // A selection may have begun before this became a drag; drop it.
   const selection=window.getSelection();
   if(selection)selection.removeAllRanges();
   try{scroll.setPointerCapture(event.pointerId);}catch{}
  }
  event.preventDefault();
  scroll.scrollLeft=pan.left-dx;
  scroll.scrollTop=pan.top-dy;
 });
 const endPan=()=>{pan=null;scroll.classList.remove('panning');};
 scroll.addEventListener('pointerup',endPan);
 scroll.addEventListener('pointercancel',endPan);
 // A drag that ends on a card must not also open that card.
 scroll.addEventListener('click',event=>{
  if(!dragged)return;
  dragged=false;
  event.preventDefault();
  event.stopPropagation();
 },true);
 $('[data-zoom="in"]').onclick=()=>apply(zoom*1.2);
 $('[data-zoom="out"]').onclick=()=>apply(zoom/1.2);
 $('[data-zoom="reset"]').onclick=()=>apply(1);
 $('[data-zoom="fit"]').onclick=()=>apply((scroll.clientWidth-26)/base.w);
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
 // A sibling is reached through a shared parent, so the handle says up front when
 // there is no parent to share.
 const addButton=(id,kind,glyph,unavailable)=>{
  const label=unavailable?'형제자매 추가 — 부모 등록 먼저':RELATIVE_LABELS[kind]+' 추가';
  return `<button type="button" class="tree-add ${kind}${unavailable?' off':''}" data-add="${kind}" data-person="${id}" title="${label}" aria-label="${label}">${glyph}</button>`;
 };
 const cards=people.filter(p=>pos.has(p.id)).map(p=>{
  const at=pos.get(p.id),photo=photoOf(p.id);
  const tone=treeOptions.gender&&p.gender!=='미상'?(p.gender==='남'?' male':' female'):'';
  return `<div class="tree-node" style="left:${at.x}px;top:${at.y}px;width:${nodeW}px;height:${nodeH}px">`
   +`<div class="tree-card${tone}" data-tree-person="${p.id}" role="button" tabindex="0">`
   +(treeOptions.photo?`<span class="tree-photo">${photo?`<img src="/api/files/${photo.id}" alt="">`:''}</span>`:'')
   +`<strong>${esc(displayName(p).primary)}</strong>`
   +treeDetails(p).map(row=>`<span class="tree-line">${esc(row)}</span>`).join('')
   +(treeOptions.note?`<small>${esc(scriptText(p.note||''))}</small>`:'')
   +'</div>'
   +addButton(p.id,'parent','+')+addButton(p.id,'child','+')
   +addButton(p.id,'spouse','+')+addButton(p.id,'sibling','+',!parentsOf.has(p.id))
   +'</div>';
 }).join('');
 $('#view').innerHTML=options+wrapZoom(`<div class="tree-canvas" style="width:${width}px;height:${height}px">`
  +`<svg class="family-tree" width="${width}" height="${height}" aria-hidden="true">${parentLines}${mateLines}${labels}</svg>${cards}</div>`);
 bindTreeOptions();
 bindZoom('tree');
 document.querySelectorAll('[data-tree-person]').forEach(node=>{
  const open=()=>editPerson(Number(node.dataset.treePerson));
  node.onclick=()=>{
   // Finishing a sweep inside the card means the reader wanted the text, not the
   // person window. A plain click leaves the selection collapsed, so the hand
   // shaking by a pixel never costs you the click.
   const selection=window.getSelection();
   if(selection&&!selection.isCollapsed&&String(selection).trim()&&node.contains(selection.anchorNode))return;
   open();
  };
  node.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();open();}};
 });
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
  message(`${anchor.korean_name} — 부모 기록 없음 · 형제자매는 공통 부모로 연결 · 부모 등록 먼저 필요`,'error');
  return;
 }
 editPerson();
 const mates=kind==='child'?spousesOf(anchor.id):[];
 pendingRelative={kind,anchor,mateId:mates.length?mates[0].id:null};
 $('#personHeading').textContent=`${RELATIVE_LABELS[kind]} 등록`;
 $('#relativeBanner').hidden=false;
 $('#relativeMateWrap').hidden=mates.length<1;
 $('#relativeMate').onchange=event=>{pendingRelative.mateId=event.target.value?Number(event.target.value):null;};
 paintRelativeBanner();
 const form=$('#personForm');
 form.elements.generation.value=relativeGeneration(kind,anchor);
 if(kind!=='spouse')setPersonScriptField('bon_gwan',anchor.bon_gwan||book.bon_gwan||'');
 $('#relativePickMode').hidden=book.persons.length<2;
 setRelativeMode(false);
}
// The banner and both pickers name people, so they are written in the window's
// own script and repainted whenever its switch is thrown.
function paintRelativeBanner(){
 if(!pendingRelative)return;
 const {kind,anchor}=pendingRelative,name=p=>esc(displayName(p,dialogScriptMode).primary);
 $('#relativeText').innerHTML=kind==='sibling'
  ? `<strong>${name(anchor)}</strong>의 형제자매로 등록 · 부모 ${parentsOfPerson(anchor.id).map(name).join('·')}에 함께 연결`
  : `<strong>${name(anchor)}</strong>의 ${RELATIVE_LABELS[kind]}로 등록`;
 // Repainting must not quietly move either choice, so each is put back.
 const mate=$('#relativeMate'),chosenMate=mate.value;
 mate.innerHTML=(kind==='child'?spousesOf(anchor.id):[])
  .map(m=>`<option value="${m.id}">${name(m)}</option>`).join('')
  +'<option value="">배우자 없이 (이 사람만)</option>';
 mate.value=chosenMate;
 const pick=$('#relativePick'),chosenPick=pick.value;
 pick.innerHTML=book.persons.filter(p=>p.id!==anchor.id)
  .map(p=>`<option value="${p.id}">${name(p)} (${p.generation}세대)</option>`).join('');
 pick.value=chosenPick;
}
// Registering someone new and picking someone already recorded are both offered
// at once; a single toggle kept whichever one it was not showing out of sight.
function setRelativeMode(pick){
 $('#relativePickWrap').hidden=!pick;
 $('#relativeLink').hidden=!pick;
 $('#personForm').querySelector('.form-grid').hidden=pick;
 $('#personNoteField').hidden=pick;
 $('#savePerson').hidden=pick;
 $('#relativeNew').setAttribute('aria-pressed',String(!pick));
 $('#relativePickMode').setAttribute('aria-pressed',String(pick));
}
$('#relativeNew').onclick=()=>setRelativeMode(false);
$('#relativePickMode').onclick=()=>setRelativeMode(true);
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
  message('가족 관계 추가 완료');
 }catch(err){dialogError(err.message);}
};
function editPerson(id){
 const f=$('#personForm');
 f.reset();dialogError();
 pendingRelative=null;
 $('#relativeBanner').hidden=true;
 setRelativeMode(false);
 f.elements.id.value=id||'';
 const p=book.persons.find(p=>p.id===id);
 if(!p)f.elements.bon_gwan.value=book.bon_gwan||'';
 if(p)Object.entries(p).forEach(([k,v])=>{if(f.elements.namedItem(k))f.elements.namedItem(k).value=v;});
 $('#personHeading').textContent=p?'인물 수정':'인물 등록';
 $('#deletePerson').hidden=!p;
 $('#addFamily').hidden=!p;
 $('#attachments').hidden=!p;
 $('#fileInput').value='';
 $('#fileList').innerHTML=p?book.files.filter(x=>x.person_id===id).map(x=>`<p><a href="/api/files/${x.id}">${esc(x.name)}</a></p>`).join(''):'';
 setPersonScriptFields(p||{bon_gwan:book.bon_gwan||'',note:''});
 paintDateClears();
 // The relation window reopens this one in place, so it may already be up.
 if(!$('#personDialog').open)$('#personDialog').showModal();
 personSnapshot=personState();
 setTimeout(()=>f.elements.korean_name.focus(),0);
}
// What the form held when it opened, so an unsaved edit is not thrown away
// silently when the relation window takes the form over.
let personSnapshot='';
function personState(){return JSON.stringify(formData($('#personForm')));}
let relativeAnchorId=null;
async function openRelativeKinds(){
 const anchor=book.persons.find(p=>p.id===Number($('#personForm').elements.id.value));
 if(!anchor)return;
 if(personState()!==personSnapshot
  &&!await ask('저장하지 않은 수정 내용 있음 · 가족 추가로 이동 시 소멸','계속'))return;
 relativeAnchorId=anchor.id;
 $('#relativeKindText').innerHTML=`<strong>${esc(displayName(anchor,dialogScriptMode).primary)}</strong> — 맺을 관계 선택`;
 const hasParents=parentsOfPerson(anchor.id).length>0;
 const sibling=$('#relativeKindList').querySelector('[data-kind="sibling"]');
 sibling.classList.toggle('off',!hasParents);
 sibling.title=hasParents?'형제자매 추가':'부모 등록 먼저';
 $('#relativeKindNote').hidden=true;
 $('#relativeKindDialog').showModal();
}
$('#addFamily').onclick=openRelativeKinds;
$('#closeRelativeKind').onclick=()=>$('#relativeKindDialog').close();
$('#relativeKindList').querySelectorAll('[data-kind]').forEach(button=>button.onclick=()=>{
 const kind=button.dataset.kind;
 // The refusal is written inside this window; a notice on the page would sit
 // behind the dialog that is covering it.
 if(kind==='sibling'&&!parentsOfPerson(relativeAnchorId).length){
  const note=$('#relativeKindNote');
  note.textContent='형제자매는 공통 부모로 연결 — 부모 등록 먼저 필요';
  note.hidden=false;
  return;
 }
 $('#relativeKindDialog').close();
 addRelative(kind,relativeAnchorId);
});
// A date box has no clear of its own: emptying it means deleting the year, the
// month and the day one at a time. This empties the whole date in one press, and
// stays greyed out while there is nothing in it to clear.
// The calendar stops at today as well, so a later day is never offered.
for(const name of ['birth_date','death_date']){
 const input=$('#personForm').elements[name];
 if(input)input.max=todayISO();
}
function paintDateClears(){
 for(const button of document.querySelectorAll('[data-clear-date]')){
  const input=$('#personForm').elements[button.dataset.clearDate];
  button.disabled=!input||!input.value;
 }
}
for(const button of document.querySelectorAll('[data-clear-date]')){
 const input=$('#personForm').elements[button.dataset.clearDate];
 if(!input)continue;
 button.onclick=()=>{
  input.value='';
  input.dispatchEvent(new Event('input',{bubbles:true}));
  input.focus();
 };
 input.addEventListener('input',paintDateClears);
 input.addEventListener('change',paintDateClears);
}
$('#personForm').elements.gender.onchange=paintGenderScript;
$('#newPerson').onclick=()=>editPerson();$('#cancelPerson').onclick=()=>$('#personDialog').close();$('#closePersonDialog').onclick=()=>$('#personDialog').close();
async function loadHanjaIndex(){if(hanjaIndex)return hanjaIndex;const data=await fetch('/hanjaeum.json').then(r=>{if(!r.ok)throw Error('한자 사전을 불러오지 못했습니다.');return r.json();});hanjaIndex={};for(const [hanja,readings] of Object.entries(data))for(const reading of readings.split(/[,/\s]+/)){if(!hanjaIndex[reading])hanjaIndex[reading]=[];hanjaIndex[reading].push(hanja);}return hanjaIndex;}
// The picker walks a queue of fields, one syllable at a time, writing each
// finished field back where it came from. A person's name is a queue of one.
const HANJA_FIELD_LABELS={title:'족보명',clan_name:'성씨 / 가문',bon_gwan:'본관',branch_name:'파명',founder:'시조',hanja_name:'한자명'};
function hanjaCandidates(syllable,index){const surnameAliases={김:['김','금'],이:['이','리'],임:['임','림'],유:['유','류'],나:['나','라'],노:['노','로'],여:['여','려'],양:['양','량']},readings=index===0?(surnameAliases[syllable]||[syllable]):[syllable],preferred={김:'金',이:'李',박:'朴',최:'崔',정:'鄭',강:'姜',조:'趙',윤:'尹',장:'張',임:'林',한:'韓',오:'吳',서:'徐',신:'申',권:'權',황:'黃',안:'安',송:'宋',전:'全',홍:'洪',유:'柳',고:'高',문:'文',양:'梁',손:'孫',배:'裵',백:'白',허:'許',남:'南',심:'沈',노:'盧'};const result=[...new Set(readings.flatMap(r=>hanjaIndex[r]||[]))].sort((a,b)=>{const common=c=>{const n=c.codePointAt(0);return n>=0x4e00&&n<=0x9fff?0:1;};return common(a)-common(b)||a.localeCompare(b,'ko');}),first=index===0?preferred[syllable]:null;if(first&&result.includes(first))return [first,...result.filter(x=>x!==first)];return result;}
function finishHanjaField(){
 const {target,chosen,rest}=hanjaState;
 target.value=chosen.join('')+rest;
 target.dispatchEvent(new Event('input',{bubbles:true}));
 startHanjaField();
}
function startHanjaField(){
 const queue=hanjaState?hanjaState.queue:[];
 const next=queue.shift();
 if(!next){$('#hanjaDialog').close();hanjaState=null;return;}
 // Only hangul syllables are picked; anything else rides along untouched.
 const text=next.value.trim(),chars=Array.from(text).filter(ch=>/[가-힣]/.test(ch));
 const rest=Array.from(text).filter(ch=>!/[가-힣]/.test(ch)).join('');
 if(!chars.length){hanjaState.queue=queue;startHanjaField();return;}
 hanjaState={chars,chosen:[],index:0,target:next,rest,queue,label:HANJA_FIELD_LABELS[next.name]||''};
 if(!$('#hanjaDialog').open)$('#hanjaDialog').showModal();
 renderHanjaStep();
}
function renderHanjaStep(){
 const {chars,chosen,index,label}=hanjaState;
 if(index>=chars.length){finishHanjaField();return;}
 const syllable=chars[index];
 const candidates=hanjaCandidates(syllable,index);
 $('#hanjaStep').textContent=`${label?label+' — ':''}'${syllable}'의 한자를 고르세요`;
 $('#hanjaPreview').textContent=`${chars.join('')} · 고른 글자: ${chosen.join('')||'아직 없음'}`;
 $('#hanjaCandidates').innerHTML=candidates.length
  ?candidates.map(h=>`<button type="button" data-hanja="${h}" title="${syllable}">${h}</button>`).join('')
  :`<p>'${esc(syllable)}' 음의 한자가 사전에 없습니다. 그대로 두고 넘어갑니다.</p>`;
 if(!candidates.length){chosen.push(syllable);hanjaState.index++;renderHanjaStep();return;}
 document.querySelectorAll('[data-hanja]').forEach(button=>button.onclick=()=>{
  chosen.push(button.dataset.hanja);hanjaState.index++;renderHanjaStep();
 });
}
async function openHanjaPicker(fields,busyButton){
 const queue=fields.filter(field=>field&&field.value.trim());
 if(!queue.length)return '한글로 적은 칸이 없습니다.';
 await busy(busyButton,'사전 여는 중…',loadHanjaIndex);
 hanjaState={queue};
 startHanjaField();
 return '';
}
$('#closeHanja').onclick=()=>{
 if(hanjaState&&hanjaState.target)finishHanjaField();
 else{$('#hanjaDialog').close();hanjaState=null;}
};
$('#convertHanja').onclick=async()=>{
 const form=$('#personForm'),name=form.elements.korean_name.value.trim();
 if(Array.from(name).filter(ch=>/[가-힣]/.test(ch)).length<2){
  dialogError('한글 성명을 먼저 입력하세요.',form.elements.korean_name);return;
 }
 dialogError();
 // The picker writes into 한자명, so it reads the hangul name through a stand-in.
 const source=Object.assign(document.createElement('input'),{name:'hanja_name',value:name});
 try{
  await openHanjaPicker([source],$('#convertHanja'));
  if(hanjaState)hanjaState.target=form.elements.hanja_name;
 }catch(err){dialogError(err.message);}
};
// One button per field, beside the box it fills.
document.querySelectorAll('[data-hanja-field]').forEach(button=>{
 button.onclick=async()=>{
  const input=button.parentElement.querySelector('input');
  try{
   const note=await openHanjaPicker([input],button);
   if(note)message('한글로 먼저 적어 주세요.','error');
  }catch(err){message(err.message,'error');}
 };
});
$('#personForm').oninput=event=>{if(event.target.name==='bon_gwan')paintReadingFor(event.target);};
$('#personForm').onsubmit=async e=>{e.preventDefault();const f=e.target;dialogError();
 const problem=dateProblem(name=>f.elements[name]);
 if(problem){dialogError(problem[1],problem[0]);return;}
 if(!f.reportValidity())return;
 const birth=f.elements.birth_date,death=f.elements.death_date;const data=formData(f),id=data.id;delete data.id;data.generation=Number(data.generation);for(const name of PERSON_SCRIPT_FIELDS){const box=f.elements[name];if(box&&box.dataset.shown!==undefined&&box.value===box.dataset.shown)data[name]=box.dataset.stored;}const relative=pendingRelative;
 const who=data.korean_name;
 const question=relative
  ?`${relative.anchor.korean_name}의 ${RELATIVE_LABELS[relative.kind]}로 ${who} — ${relative.anchor.korean_name}의 ${RELATIVE_LABELS[relative.kind]}로 등록`
  :id?`${who} — 수정 내용 저장`
  :`${who} — ${data.generation}세대 인물로 신규 등록 · 인물 목록과 가계도에 반영`;
 const dates=[birth.value?`출생 ${plainDate(birth.value)}`:'',
  death.value?`사망 ${plainDate(death.value)}`:''].filter(Boolean).join('  ·  ');
 if(!await ask(dates?`${question}\n\n${dates}`:question,'저장'))return;
 try{const saved=await busy($('#savePerson'),'저장 중…',()=>api(id?'/persons/'+id:'/books/'+book.id+'/persons',id?'PUT':'POST',data));if(!id&&relative){pendingRelative=relative;await linkRelative(saved.id);pendingRelative=null;}$('#personDialog').close();if(!id)$('#search').value='';await refresh();message(id?`${who} — 저장 완료`:relative?`${who} — ${relative.anchor.korean_name}의 ${RELATIVE_LABELS[relative.kind]}로 등록 완료`:`${who} — 등록 완료 · 검색어 해제됨`);}catch(err){dialogError(err.message);}};
$('#deletePerson').onclick=async()=>{if(!await ask(`${$('#personForm').elements.korean_name.value} — 연결된 관계와 첨부파일까지 모두 삭제 · 되돌릴 수 없음`,'삭제'))return;dialogError();try{await busy($('#deletePerson'),'삭제 중…',()=>api('/persons/'+$('#personForm').elements.id.value,'DELETE'));$('#personDialog').close();await refresh();message('삭제 완료');}catch(err){dialogError(err.message);}};
$('#upload').onclick=async()=>{dialogError();const file=$('#fileInput').files[0];if(!file){dialogError('업로드할 파일을 먼저 선택하세요.',$('#fileInput'));return;}if(file.size>5*1024*1024){dialogError('파일은 5MB 이하만 업로드할 수 있습니다.',$('#fileInput'));return;}const id=Number($('#personForm').elements.id.value),data=new FormData();data.append('file',file);try{await busy($('#upload'),'업로드 중…',()=>api('/persons/'+id+'/files','POST',data));await refresh();$('#fileList').innerHTML=book.files.filter(x=>x.person_id===id).map(x=>`<p><a href="/api/files/${x.id}">${esc(x.name)}</a></p>`).join('');$('#fileInput').value='';const el=$('#personError');el.textContent='첨부파일을 저장했습니다.';el.hidden=false;el.classList.add('success');}catch(err){dialogError(err.message);}};
function renderRelations(){if(!book)return;const options='<option value="">인물 선택</option>'+book.persons.map(p=>`<option value="${p.id}">${esc(displayName(p).primary)} (${p.generation}세대)</option>`).join('');const anchor=$('#relationForm').elements.source_id;const kept=anchor.value;anchor.innerHTML=options;
 // Whoever was searched for is the one the reader has in mind, so the form
 // starts from them rather than from the first name in the book.
 const q=$('#search').value.toLowerCase().trim();
 const found=q?book.persons.find(p=>[p.korean_name,p.hanja_name,p.note].join(' ').toLowerCase().includes(q)):null;
 anchor.value=found?String(found.id):kept;
 $('#relationForm').querySelector('button').disabled=!book.persons.length;
 // A search is about one family. The book holds other branches that never meet
 // it, and listing those under a name the reader just searched for is noise.
 const chosen=book.persons.find(p=>p.id===Number(anchor.value));
 const kin=chosen?directLine(chosen.id):null;
 const shown=kin?book.relations.filter(r=>kin.has(r.source_id)&&kin.has(r.target_id)):book.relations;
 $('#relationScope').hidden=!chosen;
 if(chosen)$('#relationScope').textContent=`${displayName(chosen).primary} 직계 · 관계 ${shown.length}건 (전체 ${book.relations.length}건)`;
 $('#relationList').innerHTML=shown.map(r=>`<div class="relation-row"><span>${esc(personName(r.source_id))} ${r.kind==='parent'?'→ 자녀':'↔ 배우자'} ${esc(personName(r.target_id))}</span><button class="secondary" data-relation="${r.id}">관계 삭제</button></div>`).join('')||(book.persons.length<2?'<p class="muted">인물 2명 이상 등록 후 관계 지정 가능</p>':'<p class="muted">등록된 관계 없음</p>');document.querySelectorAll('[data-relation]').forEach(b=>b.onclick=run(async()=>{if(!await ask('가족 관계만 삭제 · 인물 기록은 유지','삭제'))return;await api('/relations/'+b.dataset.relation,'DELETE');await refresh();message('관계 삭제 완료');}));}
// One person's line: up through their forebears, down through their issue, and
// whoever married into either. Not their forebears' other children, which is
// where a separate branch of the book would come in.
function directLine(id){
 const up=new Set([id]),down=new Set([id]);
 const parents=book.relations.filter(r=>r.kind==='parent');
 for(let pass=0;pass<book.persons.length;pass++){
  let grew=false;
  for(const r of parents){
   if(up.has(r.target_id)&&!up.has(r.source_id)){up.add(r.source_id);grew=true;}
   if(down.has(r.source_id)&&!down.has(r.target_id)){down.add(r.target_id);grew=true;}
  }
  if(!grew)break;
 }
 const kin=new Set([...up,...down]);
 for(const r of book.relations){
  if(r.kind!=='spouse')continue;
  if(kin.has(r.source_id))kin.add(r.target_id);
  else if(kin.has(r.target_id))kin.add(r.source_id);
 }
 return kin;
}
// 부모 → 자녀 and 배우자 ↔ 배우자 were the only two shapes this form could make,
// and it could not make a sibling at all. All four are on the list now, and the
// button opens the same registration the tree cards use, already set to the one
// that was picked — so a new person can be entered or an existing one chosen.
// Choosing someone in the box narrows the list to them at once.
$('#relationForm').elements.source_id.onchange=renderRelations;
$('#relationForm').onsubmit=e=>{
 e.preventDefault();
 const form=$('#relationForm'),id=Number(form.elements.source_id.value);
 if(!id){message('기준 인물 선택 필요','error');return;}
 addRelative(form.elements.kind.value,id);
};
$('#print').onclick=()=>{view='book';$('#search').value='';render();window.print();};
$('#sample').onclick=run(async()=>{const button=$('#sample');button.disabled=true;try{const b=await api('/books','POST',{title:'가상 가족의 기록 (샘플)',clan_name:'예시 김씨',description:'실존 인물과 무관한 예제입니다.'});const people=[{korean_name:'김예시',hanja_name:'金例示',generation:1,birth_date:'1940-01-01',gender:'남'},{korean_name:'이샘플',hanja_name:'李樣本',generation:1,birth_date:'1942-02-02',gender:'여'},{korean_name:'김가상',hanja_name:'金假想',generation:2,birth_date:'1970-03-03',gender:'남'},{korean_name:'김미래',hanja_name:'金未來',generation:3,birth_date:'2000-04-04',gender:'미상'}];const ids=[];for(const p of people)ids.push((await api('/books/'+b.id+'/persons','POST',{...p,note:'실제 개인정보가 아닌 가상 인물입니다.'})).id);for(const [s,t,kind] of [[0,1,'spouse'],[0,2,'parent'],[1,2,'parent'],[2,3,'parent']])await api('/relations','POST',{source_id:ids[s],target_id:ids[t],kind});await loadBooks(b.id);message('예제 족보 추가 완료');}finally{button.disabled=false;}});
enter().catch(()=>{});

// ── 스캔 보고 옮겨 적기 ────────────────────────
// A photographed page is read by eye and typed in beside it. Nothing is filed
// until the whole page is confirmed, and the server takes the lines together or
// not at all, so a page is never left half entered.
let scanRowSeq=0,scanZoom=1;
function scanError(text='',field){
 const box=$('#scanError');
 box.textContent=text;
 box.hidden=!text;
 if(field)field.focus();
}
function scanRowFields(row){
 return name=>row.querySelector(`[name="${name}"]`);
}
function scanRowHTML(id,generation){
 const genders=['미상','남','여']
  .map(value=>`<option value="${value}">${value}</option>`).join('');
 return `<div class="scan-row" data-row="${id}">
  <label>세대<input name="generation" type="number" min="1" max="200" value="${generation}"></label>
  <label>한글명<input name="korean_name" maxlength="100" autocomplete="off"></label>
  <label>한자명<input name="hanja_name" maxlength="100" autocomplete="off"></label>
  <button type="button" class="secondary scan-hanja" data-hanja-row="${id}">한자</button>
  <label>성별<select name="gender">${genders}</select></label>
  <button type="button" class="scan-drop" data-drop="${id}" aria-label="이 줄 지우기" title="이 줄 지우기">×</button>
  <label>본관<input name="bon_gwan" maxlength="200" autocomplete="off"></label>
  <label>출생일<input name="birth_date" type="date" min="0001-01-01" max="${todayISO()}"></label>
  <label>기록<input name="note" maxlength="10000" autocomplete="off" placeholder="예: 父 東國(동국)"></label>
  <p class="scan-match" hidden></p>
 </div>`;
}
function scanAddRow(){
 const rows=[...document.querySelectorAll('.scan-row')];
 const last=rows[rows.length-1];
 // A page runs down one generation at a time, so a new line starts where the
 // one above it left off rather than back at 1.
 const generation=last?(scanRowFields(last)('generation').value||1):1;
 $('#scanList').insertAdjacentHTML('beforeend',scanRowHTML(++scanRowSeq,generation));
 const added=$('#scanList').lastElementChild;
 scanRowFields(added)('bon_gwan').value=book?dialogScriptText(book.bon_gwan||''):'';
 bindScanRow(added);
 paintScanCount();
 return added;
}
function bindScanRow(row){
 row.querySelector('[data-drop]').onclick=()=>{
  row.remove();
  if(!document.querySelector('.scan-row'))scanAddRow();
  paintScanCount();
 };
 const hanja=row.querySelector('[data-hanja-row]');
 hanja.onclick=async()=>{
  const korean=scanRowFields(row)('korean_name');
  if(!korean.value.trim()){scanError('한글명 입력 필요',korean);return;}
  scanError();
  // The picker writes into whatever field it was handed, so the hangul name is
  // read through a stand-in and the choice lands in 한자명.
  const source=Object.assign(document.createElement('input'),{name:'hanja_name',value:korean.value.trim()});
  try{
   const note=await openHanjaPicker([source],hanja);
   if(note){scanError(note);return;}
   hanjaState.target=scanRowFields(row)('hanja_name');
  }catch(err){scanError(err.message);}
 };
 for(const name of ['korean_name','hanja_name','generation'])
  row.querySelector(`[name="${name}"]`).addEventListener('input',()=>{
   paintScanMatch(row);
   paintScanCount();
  });
}
// What a clearer reading is allowed to fill in, and what counts as nothing known.
const SCAN_FILLABLE=[['hanja_name','','한자명'],['bon_gwan','','본관'],
 ['gender','미상','성별'],['birth_date','','출생일'],['note','','기록']];
// A name already in the book is far likelier to be the same person read again
// than a second person of the same name, so the line offers to fill that record
// in rather than quietly making a double.
function scanMatch(row){
 if(!book)return null;
 const get=scanRowFields(row);
 const korean=get('korean_name').value.trim(),hanja=get('hanja_name').value.trim();
 if(!korean&&!hanja)return null;
 const generation=Number(get('generation').value)||0;
 const hits=book.persons.filter(person=>
  (korean&&person.korean_name===korean)||(hanja&&person.hanja_name&&person.hanja_name===hanja));
 if(!hits.length)return null;
 return hits.find(person=>person.generation===generation)||hits[0];
}
function paintScanMatch(row){
 const found=scanMatch(row),note=row.querySelector('.scan-match');
 if(!found){
  note.hidden=true;
  row.dataset.matchId='';
  row.dataset.fillId='';
  row.classList.remove('filling');
  return;
 }
 // Filling is the opening offer whenever a fresh match turns up.
 if(row.dataset.matchId!==String(found.id)){
  row.dataset.matchId=String(found.id);
  row.dataset.fillId=String(found.id);
 }
 const filling=row.dataset.fillId===String(found.id);
 row.classList.toggle('filling',filling);
 const blanks=SCAN_FILLABLE.filter(([name,blank])=>found[name]===blank).map(([,,label])=>label);
 note.hidden=false;
 note.innerHTML=`<span>기존 인물: <strong>${esc(displayName(found,dialogScriptMode).primary)}</strong> · ${found.generation}세대 · `
  +(blanks.length?`빈칸 ${esc(blanks.join('·'))}`:'빈칸 없음')+'</span>'
  +`<button type="button" class="secondary" data-fill aria-pressed="${filling}">빈칸만 채우기</button>`
  +`<button type="button" class="secondary" data-fresh aria-pressed="${!filling}">따로 등록</button>`;
 note.querySelector('[data-fill]').onclick=()=>{row.dataset.fillId=String(found.id);paintScanMatch(row);};
 note.querySelector('[data-fresh]').onclick=()=>{row.dataset.fillId='';paintScanMatch(row);};
}
function scanLines(){
 return [...document.querySelectorAll('.scan-row')].map(row=>{
  const get=scanRowFields(row);
  return {row,get,korean:get('korean_name').value.trim(),hanja:get('hanja_name').value.trim()};
 });
}
function paintScanCount(){
 const written=scanLines().filter(line=>line.korean||line.hanja).length;
 $('#scanCount').textContent=written?`입력 ${written}명`:'입력된 인물 없음';
 $('#scanSave').disabled=!written;
}
// ── 스캔 보기 ──────────────────────────────
// The width is a share of the frame, so 100% is the page fitted to it and
// anything more scrolls — which is what reading small print off a scan needs.
function paintScanZoom(){
 $('#scanImage').style.width=Math.round(scanZoom*100)+'%';
 $('#scanLevel').textContent=Math.round(scanZoom*100)+'%';
}
function setScanZoom(next,anchor){
 const frame=$('#scanFrame'),was=scanZoom;
 scanZoom=Math.min(8,Math.max(0.2,next));
 if(anchor){
  const rect=frame.getBoundingClientRect();
  const x=anchor.clientX-rect.left+frame.scrollLeft,y=anchor.clientY-rect.top+frame.scrollTop;
  paintScanZoom();
  const grew=scanZoom/was;
  frame.scrollLeft=x*grew-(anchor.clientX-rect.left);
  frame.scrollTop=y*grew-(anchor.clientY-rect.top);
  return;
 }
 paintScanZoom();
}
function showScan(id){
 const image=$('#scanImage'),empty=$('#scanEmpty');
 if(!id){image.hidden=true;image.removeAttribute('src');empty.hidden=false;return;}
 empty.hidden=true;
 image.hidden=false;
 image.src='/api/scans/'+id;
 scanZoom=1;
 paintScanZoom();
 $('#scanFrame').scrollTo(0,0);
}
function paintScanList(keep){
 const pick=$('#scanPick'),scans=(book&&book.scans)||[];
 pick.innerHTML=scans.map(scan=>`<option value="${scan.id}">${esc(scan.name)}</option>`).join('')
  ||'<option value="">올려둔 스캔이 없습니다</option>';
 const chosen=scans.some(scan=>scan.id===keep)?keep:(scans[0]&&scans[0].id);
 pick.value=chosen||'';
 pick.disabled=!scans.length;
 $('#scanDelete').disabled=!scans.length;
 showScan(chosen);
}
async function openScanDialog(){
 if(!book){message('족보 선택 필요','error');return;}
 scanError();
 $('#scanFile').value='';
 $('#scanList').innerHTML='';
 scanRowSeq=0;
 scanAddRow();
 paintScanList();
 if(!$('#scanDialog').open)$('#scanDialog').showModal();
}
$('#openScan').onclick=openScanDialog;
$('#closeScan').onclick=()=>$('#scanDialog').close();
$('#scanCancel').onclick=()=>$('#scanDialog').close();
$('#scanAddRow').onclick=()=>{
 const row=scanAddRow();
 scanRowFields(row)('korean_name').focus();
};
$('#scanPick').onchange=event=>showScan(Number(event.target.value)||0);
document.querySelectorAll('[data-scan-zoom]').forEach(button=>{
 button.onclick=()=>{
  const how=button.dataset.scanZoom;
  if(how==='fit'){scanZoom=1;paintScanZoom();$('#scanFrame').scrollTo(0,0);return;}
  setScanZoom(how==='in'?scanZoom*1.25:scanZoom/1.25);
 };
});
$('#scanFrame').addEventListener('wheel',event=>{
 if(!event.ctrlKey)return;
 event.preventDefault();
 setScanZoom(scanZoom*(event.deltaY<0?1.12:1/1.12),event);
},{passive:false});
// The scan is a picture, so dragging it can only mean moving it about.
let scanPan=null;
$('#scanFrame').addEventListener('pointerdown',event=>{
 if(event.button!==0||$('#scanImage').hidden)return;
 scanPan={x:event.clientX,y:event.clientY,left:$('#scanFrame').scrollLeft,top:$('#scanFrame').scrollTop};
 $('#scanFrame').setPointerCapture(event.pointerId);
 $('#scanFrame').classList.add('dragging');
 event.preventDefault();
});
$('#scanFrame').addEventListener('pointermove',event=>{
 if(!scanPan)return;
 $('#scanFrame').scrollLeft=scanPan.left-(event.clientX-scanPan.x);
 $('#scanFrame').scrollTop=scanPan.top-(event.clientY-scanPan.y);
});
for(const kind of ['pointerup','pointercancel'])$('#scanFrame').addEventListener(kind,()=>{
 scanPan=null;
 $('#scanFrame').classList.remove('dragging');
});
$('#scanUpload').onclick=async()=>{
 scanError();
 const file=$('#scanFile').files[0];
 if(!file){scanError('파일 선택 필요',$('#scanFile'));return;}
 if(file.size>20*1024*1024){scanError('20MB 초과 — 올릴 수 없음',$('#scanFile'));return;}
 const data=new FormData();
 data.append('file',file);
 try{
  const made=await busy($('#scanUpload'),'올리는 중…',()=>api('/books/'+book.id+'/scans','POST',data));
  $('#scanFile').value='';
  await refresh();
  paintScanList(made.id);
 }catch(err){scanError(err.message);}
};
$('#scanDelete').onclick=async()=>{
 scanError();
 const id=Number($('#scanPick').value);
 if(!id)return;
 const name=$('#scanPick').selectedOptions[0].textContent;
 if(!await ask(`${name} — 삭제 · 등록된 인물은 유지`,'지우기'))return;
 try{
  await busy($('#scanDelete'),'지우는 중…',()=>api('/scans/'+id,'DELETE'));
  await refresh();
  paintScanList();
 }catch(err){scanError(err.message);}
};
$('#scanSave').onclick=async()=>{
 scanError();
 const written=scanLines().filter(line=>line.korean||line.hanja);
 if(!written.length){scanError('입력된 인물 없음');return;}
 const people=[];
 for(const [index,line] of written.entries()){
  const {get}=line;
  if(!line.korean){
   scanError(`${index+1}번째 줄 — 한글명 없음 · 한자만으로는 등록 불가`,get('korean_name'));
   return;
  }
  const generation=Number(get('generation').value);
  if(!(generation>=1&&generation<=200)){
   scanError(`${index+1}번째 줄 — 세대는 1~200`,get('generation'));
   return;
  }
  const problem=dateProblem(get);
  if(problem){scanError(`${index+1}번째 줄 — ${problem[1]}`,problem[0]);return;}
  const fillId=Number(line.row.dataset.fillId)||0;
  people.push({
   korean_name:line.korean,hanja_name:line.hanja,
   bon_gwan:get('bon_gwan').value.trim(),generation,
   gender:get('gender').value,birth_date:get('birth_date').value,
   death_date:'',note:get('note').value.trim(),
   ...(fillId?{id:fillId}:{})
  });
 }
 const fresh=people.filter(person=>!person.id),refined=people.filter(person=>person.id);
 const lines=[];
 if(fresh.length)lines.push(`새로 등록 ${fresh.length}명 — ${fresh.map(person=>person.korean_name).join(', ')}`);
 if(refined.length)lines.push(`빈칸만 채움 ${refined.length}명 — ${refined.map(person=>person.korean_name).join(', ')}`);
 const question=`「${book.title}」에 ${people.length}줄 반영\n\n${lines.join('\n')}`
  +(refined.length?'\n\n채우기 — 빈칸·미상만 대상 · 기재된 값과 세대는 유지':'')
  +'\n\n가족 관계는 반영 후 [가족 추가]에서 지정';
 if(!await ask(question,'반영'))return;
 try{
  const done=await busy($('#scanSave'),'반영 중…',()=>api('/books/'+book.id+'/persons/bulk','POST',{people}));
  $('#scanDialog').close();
  $('#search').value='';
  await refresh();
  const touched=(done.filled||[]).filter(one=>one.fields.length).length;
  const untouched=(done.filled||[]).length-touched;
  message([`새로 등록 ${(done.added||[]).length}명`,
   touched?`빈칸 채움 ${touched}명`:'',
   untouched?`변경 없음 ${untouched}명`:'',
   '가족 관계는 [가족 추가]에서 지정'].filter(Boolean).join(' · '));
 }catch(err){scanError(err.message);}
};

// ── 판독 ─────────────────────────────────
// The reader proposes; it never files. Every line it offers lands in the same
// boxes a hand would have typed into, so it is corrected before it counts — and
// a woodblock page will always give it some trouble.
function scanFillRow(row,person,generation){
 const get=scanRowFields(row);
 get('generation').value=generation;
 get('hanja_name').value=person.hanja_name||'';
 // The page gives the characters; the reading follows from them.
 get('korean_name').value=readingOf(person.hanja_name||'')||'';
 get('bon_gwan').value=person.bon_gwan||(book?book.bon_gwan||'':'');
 get('gender').value=person.gender||'미상';
 get('birth_date').value=person.birth_date||'';
 get('note').value='';
 // A year and its 간지 that disagree mean one of the two was misread.
 row.classList.toggle('doubted',person.ganji_agrees===false);
 row.title=person.ganji_agrees===false?'간지 불일치 — 원본 대조 필요':'';
 paintScanMatch(row);
}
$('#scanRead').onclick=async()=>{
 scanError();
 const id=Number($('#scanPick').value);
 if(!id){scanError('족보 이미지 없음 — 먼저 올리기');return;}
 let found;
 try{
  found=await busy($('#scanRead'),'판독 중…',()=>api('/scans/'+id+'/read','POST'));
 }catch(err){scanError(err.message);return;}
 const people=found.people||[];
 const note=$('#scanReadNote');
 note.hidden=false;
 if(!people.length){
  note.textContent='판독 결과 없음 — 더 선명한 이미지 또는 직접 입력';
  return;
 }
 const first=Number($('#scanFirstGeneration').value)||1;
 $('#scanList').innerHTML='';
 scanRowSeq=0;
 for(const person of people){
  const row=scanAddRow();
  scanFillRow(row,person,Math.min(200,first+(person.band||0)));
 }
 const doubted=people.filter(person=>person.ganji_agrees===false).length;
 note.textContent=`판독 ${people.length}명 · 원본 대조 후 등록 — 목판 인쇄는 누락·오독 있음`
  +(doubted?` · 간지 불일치 ${doubted}줄(붉은 줄)`:' · 간지 전수 일치');
 paintScanCount();
};
