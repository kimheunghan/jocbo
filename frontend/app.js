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
// 가려진 칸(비밀번호, API 키) 오른쪽의 눈 단추로 적은 것을 보거나 다시 가립니다.
const EYE='<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>';
const EYE_OFF='<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M4 4l16 16" stroke="currentColor" stroke-width="1.8"/></svg>';
for(const field of document.querySelectorAll('input[type="password"]')){
 const wrap=document.createElement('span');wrap.className='reveal';
 field.replaceWith(wrap);wrap.append(field);
 const eye=document.createElement('button');
 eye.type='button';eye.className='reveal-eye';eye.innerHTML=EYE;eye.title='보이기';eye.setAttribute('aria-label','보이기');
 eye.onclick=()=>{const shown=field.type==='text';field.type=shown?'password':'text';eye.innerHTML=shown?EYE:EYE_OFF;eye.title=eye.ariaLabel=shown?'보이기':'가리기';field.focus();};
 wrap.append(eye);
}
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
 let changed=false,given=-1;
 const out=chars.map((ch,index)=>{
  if(!/[一-鿿]/.test(ch))return ch;
  // A surname reads as a surname where a name begins: before 氏, or at the start of
  // a word, which is what 金之岱 is inside 英憲公(金之岱).
  const opensWord=index===0||!/[一-鿿]/.test(chars[index-1]);
  if(HANJA_SURNAME[ch]&&(chars[index+1]==='氏'||opensWord)){
   changed=true;
   // The given name after it is a word of its own and takes the same initial
   // sound as one: 金魯錫 is 김노석, not 김로석.
   if(chars[index+1]!=='氏')given=index+1;
   return HANJA_SURNAME[ch];
  }
  let reading=(hanjaReadings[ch]||'').split(/[,/\s]+/)[0];
  if(!reading)return ch;
  if((index===0||index===given)&&INITIAL_SOUND[reading])reading=INITIAL_SOUND[reading];
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
 const mode=switcher.get()==='hangul'?'hanja':'hangul';
 // The 한글/漢字 switch under the title turns everything over at once — the
 // sidebar and the windows too; the smaller switches still turn their own part.
 const turned=button.classList.contains('title-script')?Object.values(SCRIPT_SWITCHES):[switcher];
 for(const one of turned){one.set(mode);try{localStorage.setItem(one.key,mode);}catch{}}
 paintScriptToggle();
 if(turned.length>1){paintPersonScript();paintRelativeBanner();paintNewBookFields();paintScanScript();}
 // A window's switch turns that window over and leaves the page behind it alone.
 if(which==='dialog'){paintPersonScript();paintRelativeBanner();paintNewBookFields();paintScanScript();return;}
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
  ['권',book.volume?book.volume+'권':''],['페이지',book.page],['시조',book.founder]]
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
  // The page's own switch shows both sides, the one in view filled, so the
  // mode reads at a glance; the others say what a press will do.
  if(button.classList.contains('title-script')){
   button.innerHTML=`<span class="${mode==='hangul'?'on':''}">한글</span><span class="${mode==='hangul'?'':'on'}">漢字</span>`;
   button.title=mode==='hangul'?'한자로 보기':'한글로 보기';
   button.setAttribute('aria-label',`표기 전환 — 지금 ${mode==='hangul'?'한글':'한자'}`);
  }else button.textContent=mode==='hangul'?'한자로 보기':'한글로 보기';
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
  // Past the free number of people the server answers 402; the window says so, and
  // the error is kept quiet so the same words do not show twice.
  if(r.status===402){const text=errorText(result.detail);paywall(text);throw Object.assign(Error(text),{quiet:true});}
  if(!r.ok) throw Error(errorText(result.detail));
  return result;
}
// 무료 인원을 넘으면 그렇다고 알리고, [정식판 안내]로 구매·키 입력 창을 엽니다.
function paywall(text){
 $('#confirmHeading').textContent='정식판으로 전환';
 ask(`${text}
정식판은 인원 제한 없이 등록할 수 있습니다.`,'정식판 안내')
  .then(ok=>{$('#confirmHeading').textContent='확인';if(ok)openLicense();});
}
// 정식판 창. 무료 계정에는 구매와 키 등록을, 정식판 계정에는 쓰고 있다는 것만 보여 줍니다.
const PRICE='₩29,000';
async function openLicense(){
 let me;try{me=await api('/me');}catch(err){message(err.message,'error');return;}
 const body=$('#licenseBody');
 if(me.plan!=='free'){
  $('#licenseHeading').textContent='정식판 사용 중';
  body.innerHTML='<p>이 계정은 정식판입니다. 인물 수 제한 없이 씁니다.</p>'
   +(me.licensed?'<p class="muted">키 하나로 PC 2대까지 씁니다. 다른 PC로 옮기려면 이 PC의 등록을 먼저 풀어 주십시오.</p>'
    +'<div class="actions"><button type="button" id="licenseRelease" class="danger">이 PC 등록 풀기</button></div>':'');
  if(me.licensed)$('#licenseRelease').onclick=run(async()=>{
   if(!await ask('이 PC 등록 풀기\n\n이 계정은 무료판(인물 20명)으로 돌아갑니다. 기록은 그대로 남습니다.','등록 풀기'))return;
   await busy($('#licenseRelease'),'푸는 중…',()=>api('/license','DELETE'));
   $('#licenseDialog').close();paintPlan();message('이 PC 등록을 풀었습니다');
  });
 }else{
  $('#licenseHeading').textContent='정식판으로 전환';
  body.innerHTML=`<p>지금은 <b>무료판</b>입니다. 무료판은 인물 <b>${me.free_people}명까지</b> 등록할 수 있고(지금 ${me.people}명), 그 이상 등록하려면 정식판(유료)으로 전환해야 합니다. 정식판은 인원 제한이 없고, 한 번 구매로 PC 2대에서 씁니다.</p>`
   +'<ol class="license-steps"><li>[구매하기]로 결제합니다.</li><li>결제 화면과 이메일로 라이선스 키가 옵니다.</li><li>아래 칸에 키를 붙여 넣고 [키 등록]을 누릅니다.</li></ol>'
   +`<div class="actions"><button type="button" id="licenseBuy">구매하기 ${PRICE}</button></div>`
   +'<form id="licenseForm"><label>이미 구매했다면 라이선스 키<input name="key" required minlength="8" maxlength="100" autocomplete="off" spellcheck="false" placeholder="결제 확인 이메일의 키를 입력하세요"></label>'
   +'<div class="actions"><button class="secondary">키 등록</button></div></form>';
  $('#licenseBuy').onclick=()=>{if(me.checkout_url)window.open(me.checkout_url,'_blank');else message('결제 페이지를 준비하고 있습니다. 곧 열립니다.');};
  $('#licenseForm').onsubmit=run(async e=>{
   e.preventDefault();
   await busy(e.target.querySelector('button'),'확인하는 중…',()=>api('/license','POST',{key:e.target.elements.key.value.trim()}));
   $('#licenseDialog').close();paintPlan();message('정식판으로 바뀌었습니다. 인물 수 제한이 없습니다.');
  });
 }
 if(!$('#licenseDialog').open)$('#licenseDialog').showModal();
}
$('#closeLicense').onclick=()=>$('#licenseDialog').close();
$('#licenseOpen').onclick=openLicense;
// 왼쪽 칸에 무료 인원과 지금 인원을 늘 보여 줍니다. 누르면 정식판 창이 열립니다.
// 정식판이면 그렇다고 적고, 정식판이 생기기 전부터 있던 계정이면 감춥니다.
async function paintPlan(){
 let me;try{me=await api('/me');}catch{return;}
 // 위쪽: 무료 계정에는 할 일([정식판으로 전환]), 정식판 계정에는 지금 상태(정식판)를 적습니다.
 const top=$('#licenseOpen'),free=me.plan==='free';
 top.textContent=free?'정식판으로 전환':'정식판';
 top.classList.toggle('upgrade',free);
 top.title=free?'구매하거나 라이선스 키를 넣어 인원 제한을 풉니다':'정식판 사용 중';
 top.hidden=false;
 const note=$('#planNote');
 note.hidden=me.plan!=='free'&&!me.licensed;
 if(note.hidden)return;
 note.onclick=openLicense;
 if(me.licensed){note.classList.remove('full');note.textContent='정식판 사용 중 · 인물 수 제한 없음';return;}
 const full=me.people>=me.free_people;
 note.classList.toggle('full',full);
 note.textContent=full
  ?`무료판은 인물 ${me.free_people}명까지 등록할 수 있습니다. ${me.free_people}명을 다 등록했습니다. 더 등록하려면 정식판(유료)으로 전환해 주십시오. ▸ 눌러서 전환`
  :`무료판은 인물 ${me.free_people}명까지 등록할 수 있고, 그 이상은 정식판(유료)으로 전환해야 합니다. 지금 ${me.people}명 등록.`;
}
function run(fn){return async e=>{try{message('');await fn(e);}catch(err){if(!err.quiet)message(err.message,'error');}};}
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
  const shown=dateShown(box);
  // A year, a month or a day may be left empty; each one filled keeps its rule.
  if(box.dataset.problem)return [shown,`${label} — ${box.dataset.problem}`];
  // A date the browser could not make sense of — 31 February, 29 February in a
  // year with 28 — reads back empty while its segments still show the typing.
  if(box.validity.badInput)
   return [shown,`${label} — 없는 날짜 · 월 1~12, 일은 해당 월의 마지막 날까지 · 예: 1956-02-07`];
  if(box.value&&!validDate(box.value))
   return [shown,`${label} — 연도 4자리 형식 · 예: 1956-02-07`];
  if(box.value&&!box.value.startsWith('--')&&box.value>today.slice(0,box.value.length))
   return [shown,`${label} — 아직 오지 않은 날 · 오늘(${today}) 이후 불가`];
 }
 const birth=get('birth_date'),death=get('death_date');
 if(birth&&death&&birth.value&&death.value&&!birth.value.startsWith('--')&&!death.value.startsWith('--')){
  // Only as far as both are known: 1956 and 1956-03-02 do not contradict.
  const known=Math.min(birth.value.length,death.value.length);
  if(death.value.slice(0,known)<birth.value.slice(0,known))return [dateShown(death),'사망일이 출생일보다 이름'];
 }
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
 const {y,m,d}=dateParts(value);
 return [y?`${y}년`:'',m?`${m}월`:'',d?`${d}일`:''].filter(Boolean).join(' ');
}
// A kept date as far as it goes: {y:1956,m:3,d:0} for 1956-03, y is 0 without a year.
function dateParts(value){
 const text=String(value||'');
 const yearless=/^--(\d{2})-(\d{2})$/.exec(text);
 if(yearless)return {y:0,m:Number(yearless[1]),d:Number(yearless[2])};
 const [y,m,d]=text.split('-').map(Number);
 return {y:y||0,m:m||0,d:d||0};
}
// A list or a tree shows a whole date as it is kept and a part of one in words.
function shownDate(value){
 return /^\d{4}-\d{2}-\d{2}$/.test(value||'')?value:plainDate(value);
}
function validDate(value){
 if(!/^(\d{4}(-\d{2}(-\d{2})?)?|--\d{2}-\d{2})$/.test(value))return false;
 // A leap year stands in for a missing one, so that 29 February is let through.
 const {y,m,d}=dateParts(value),year=y||2000,month=m||1,day=d||1;
 if(!value.startsWith('--')&&!y)return false;
 const parsed=new Date(Date.UTC(2000,month-1,day));
 parsed.setUTCFullYear(year,month-1,day);
 return parsed.getUTCFullYear()===year&&parsed.getUTCMonth()===month-1&&parsed.getUTCDate()===day;
}
async function enter(){await api('/me');$('#search').value='';$('#auth').hidden=true;$('#workspace').hidden=false;$('#logout').hidden=false;// The readings are wanted the moment the workspace opens, not after a click.
 await loadHanjaDict().catch(()=>{});await loadBooks();}
async function loadBooks(selected){const all=await api('/books');paintScriptToggle();$('#bookSelect').innerHTML=all.map(b=>`<option value="${b.id}">${esc(sideScriptText(b.title))}</option>`).join('');if(selected)$('#bookSelect').value=selected;await refresh();}
async function refresh(){const bid=$('#bookSelect').value;book=bid?await api('/books/'+bid):null;if(book)normalizeBookGenerations();$('#bookTitle').textContent=book?scriptText(book.title):'족보 없음';$('#relationsPanel').hidden=!book;$('#print').disabled=!book;$('#printTree').disabled=!book;$('#newPerson').disabled=!book;$('#bookInfoForm').hidden=!book;if(book){for(const name of ['volume','page','page_breaks','description'])$('#bookInfoForm').elements[name].value=book[name]||'';paintBookFields();}paintReadings();paintBookFacts();render();renderRelations();paintShare();paintPlan();}
$('#authForm').onsubmit=run(async e=>{e.preventDefault();await api('/login','POST',formData(e.target));await enter();});
$('#register').onclick=run(async()=>{if(!$('#authForm').reportValidity())return;const r=await api('/register','POST',formData($('#authForm')));message(r.message);});
$('#logout').onclick=run(async()=>{await api('/logout','POST');location.reload();});
$('#bookForm').onsubmit=run(async e=>{e.preventDefault();const r=await api('/books','POST',bookFormValues(e.target));e.target.reset();e.target.elements.volume.value='1';paintNewBookFields();$('#bookDialog').close();await loadBooks(r.id);message('새 족보 생성 완료');});
$('#bookInfoForm').oninput=paintReadings;
// 웹 공유: 가족이 링크로 가계도를 봅니다. 고친 내용은 서버가 알아서 올립니다.
let shareTimer=null;
function shareTime(seconds){if(!seconds)return '';const d=new Date(seconds*1000);return `${d.getMonth()+1}월 ${d.getDate()}일 ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;}
async function paintShare(){
 clearTimeout(shareTimer);
 const panel=$('#sharePanel'),body=$('#shareBody');panel.hidden=!book;if(!book)return;
 const bid=book.id;let state;
 // 웹 공유는 족보 선택보다 위에 있으므로, 어느 족보를 공유하는지 제목 옆에 적습니다.
 $('#shareBook').textContent=sideScriptText(book.title);
 try{state=await api(`/books/${bid}/share`);}catch(err){body.innerHTML=`<p class="muted">${esc(err.message)}</p>`;return;}
 if(!book||book.id!==bid)return;
 if(!state.shared){
  body.innerHTML='<p class="muted">링크로 가족과 가계도 공유</p><button type="button" id="shareStart">공유 시작</button>';
  $('#shareStart').onclick=run(async()=>{await busy($('#shareStart'),'올리는 중…',()=>api(`/books/${bid}/share`,'POST'));await paintShare();message('웹 공유 시작 · 링크를 가족에게 보내 주십시오');});
  return;
 }
 const status=state.error?`<p class="share-status error">올리지 못함 · 잠시 뒤 다시 시도<br>${esc(state.error)}</p>`
  :state.pending?'<p class="share-status">올리는 중…</p>'
  :`<p class="share-status">자동 반영 · ${esc(shareTime(state.synced_at))}</p>`;
 body.innerHTML=`<label>링크<input id="shareLink" readonly value="${esc(state.link)}"></label>`
  +'<div class="share-actions"><button type="button" id="shareCopy">링크 복사</button><button type="button" id="shareOpen" class="secondary">열어 보기</button></div>'+status
  +'<button type="button" id="shareStop" class="danger share-stop">공유 끝내기</button>';
 $('#shareLink').onclick=e=>e.target.select();
 $('#shareCopy').onclick=run(async()=>{try{await navigator.clipboard.writeText(state.link);}catch{$('#shareLink').select();document.execCommand('copy');}message('공유 링크 복사됨');});
 $('#shareOpen').onclick=()=>window.open(state.link,'_blank');
 $('#shareStop').onclick=run(async()=>{if(!await ask('웹 공유 끝내기\n\n공유 사이트의 사본을 지웁니다. 보내 둔 링크는 더 열리지 않습니다.','공유 끝내기'))return;await busy($('#shareStop'),'끝내는 중…',()=>api(`/books/${bid}/share`,'DELETE'));await paintShare();message('웹 공유 끝남');});
 // 올리는 중이거나 실패했으면 곧 다시, 아니면 가끔 상태를 새로 봅니다.
 shareTimer=setTimeout(()=>{if(!$('#sharePanel').contains(document.activeElement))paintShare();},state.pending?2000:state.error?5000:30000);
}
$('#bookInfoForm').onsubmit=run(async e=>{e.preventDefault();await busy(e.target.querySelector('button'),'저장 중…',()=>api('/books/'+book.id,'PUT',bookFormValues(e.target)));await loadBooks(book.id);message('족보 기본정보 저장 완료');});
$('#bookSelect').onchange=run(refresh);
$('#search').oninput=()=>{render();renderRelations();};
// Chrome fills the saved sign-in e-mail into the search box whatever autocomplete
// says, and then the list shows nobody. It leaves a read-only box alone, so the box
// is read-only until it is taken hold of, and again once it is left empty.
for(const type of ['pointerdown','focus'])$('#search').addEventListener(type,()=>$('#search').removeAttribute('readonly'));
$('#search').addEventListener('blur',()=>{if(!$('#search').value)$('#search').setAttribute('readonly','');});
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{view=b.dataset.view;render();});
function personName(id){return book.persons.find(p=>p.id===id)?.korean_name||'';}
function hanjaNumber(value){const n=Number(value);if(!Number.isInteger(n)||n<0||n>99)return String(value||'');const digits='零一二三四五六七八九';if(n<10)return digits[n];if(n===10)return '十';const tens=n>19?digits[Math.floor(n/10)]+'十':'十';return tens+(n%10?digits[n%10]:'');}
// A child stands a generation below its parent, and husband and wife in one:
// someone who married in, entered at 1, takes the generation of the one married.
function normalizeBookGenerations(){const byId=new Map(book.persons.map(p=>[p.id,p])),parents=book.relations.filter(r=>r.kind==='parent'),spouses=book.relations.filter(r=>r.kind==='spouse');for(let pass=0;pass<book.persons.length;pass++){let changed=false;for(const r of parents){const parent=byId.get(r.source_id),child=byId.get(r.target_id);if(parent&&child&&child.generation<parent.generation+1){child.generation=parent.generation+1;changed=true;}}for(const r of spouses){const one=byId.get(r.source_id),other=byId.get(r.target_id);if(one&&other&&one.generation!==other.generation){one.generation=other.generation=Math.max(one.generation,other.generation);changed=true;}}if(!changed)break;}}
function render(){document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===view));$('#viewTools').replaceChildren();searchNotice.hidden=true;if(!book){$('#view').innerHTML='<p class="empty">족보 없음 — 왼쪽에서 새 족보 또는 예제 추가</p>';return;}
 const q=$('#search').value.toLowerCase().trim();const people=book.persons.filter(p=>searchMatches(p,q));
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
 $('#view').innerHTML=people.length?'<div class="cards">'+inBookOrder(people).map(personCard).join('')+'</div>':'<p class="empty">등록된 인물 없음</p>';
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
 // The frame may be taller than the window, or the page scrolled elsewhere:
 // then the page moves too, until the card stands in the middle of the window.
 const seen=node.getBoundingClientRect(),bar=document.querySelector('.view-bar');
 const top=bar?bar.getBoundingClientRect().bottom:0;
 if(seen.top<top||seen.bottom>window.innerHeight)
  window.scrollBy(0,seen.top+seen.height/2-(top+window.innerHeight)/2);
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
 if(!validDate(iso||''))return '';
 // Set down only as far as the date is known.
 const {y,m,d}=dateParts(iso);
 if(scriptMode==='hangul')
  return [y?`${y}년 ${ganjiKorean(y)}`:'',m?`${m}월`:'',d?`${d}일`:''].filter(Boolean).join(' ')+(kind==='生'?'생':'졸');
 return (y?`${hanjaYear(y)}年${ganji(y)}`:'')+(m?`${hanjaNumber(m)}月`:'')+(d?`${hanjaNumber(d)}日`:'')+kind;
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
// 一 is a single stroke in a full square, so in a column it leaves a wider gap
// around it than its neighbours do; it is marked so the sheet can close the gap.
function evenText(text){return esc(text).replace(/一/g,'<b class="thin-one">一</b>');}
function personEntry(person,spouses,surname){
 const hangul=scriptMode==='hangul';
 const prefix=person.gender==='여'?bookWord('女','딸'):bookWord('子','아들'),name=lineName(person,surname);
 const lines=[bookDate(person.birth_date,'生'),bookDate(person.death_date,'卒')].filter(Boolean);
 const note=hangul?(readingOf(person.note)||person.note):person.note;
 return `<section class="genealogy-person" data-book-person="${person.id}"><strong><i>${prefix}</i>`
  +`${esc(hangul?name.korean:name.hanja)}<em>${esc(hangul?name.hanja:name.korean)}</em></strong>`
  +lines.map(line=>`<span>${evenText(line)}</span>`).join('')
  +(note?`<span class="genealogy-note">${evenText(note)}</span>`:'')
  +spouses.map(spouse=>`<span>${evenText(spousePhrase(spouse))}</span>`).join('')
  +'</section>';
}
// Columns are printed in the book's own order: each father's children stand under
// him, sons by age before daughters, so a person sorts by its ancestors' keys first.
function columnKey(person,byId,fatherOf){
 const path=[];
 for(let node=person,guard=0;node&&guard<200;guard++){
  path.unshift([node.gender==='여'?1:0,/^\d{4}/.test(node.birth_date||'')?node.birth_date:'9999-99-99',node.id]);
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
// The list is read the way the book is: generation by generation, and within
// one each father's children together, sons before daughters, eldest first.
// Those who married in take no part in that order: they come after the line's
// own people of their generation, in the order of the spouses they married.
function inBookOrder(people){
 const {byId,hostOf}=spouseHosts();
 const fatherOf=fatherIndex(byId),keys=new Map();
 const guest=person=>byId.has(hostOf.get(person.id))?1:0;
 const keyOf=person=>{
  if(!keys.has(person.id)){
   const host=byId.get(hostOf.get(person.id));
   keys.set(person.id,host?[...columnKey(host,byId,fatherOf),[1,'',person.id]]:columnKey(person,byId,fatherOf));
  }
  return keys.get(person.id);
 };
 return people.slice().sort((a,b)=>a.generation-b.generation||guest(a)-guest(b)||compareKeys(keyOf(a),keyOf(b)));
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
// A person was once called by more than one name: 字, given on coming of age,
// 初名 from childhood, 號. The record carries them as 字 龍鶴, and each is shown
// beside the name and found by a search in either script.
function otherNames(person){
 const found=[];
 for(const match of String(person.note||'').matchAll(/(字|初名|號|諱)\s*([一-鿿]{1,4}|[가-힣]{2,4})/g)){
  const hanja=/[一-鿿]/.test(match[2])?match[2]:'';
  found.push({kind:match[1],hanja,korean:hanja?readingOf(hanja)||'':match[2]});
 }
 return found;
}
// The family name a person's own name opens with: 김 of 김상석, 제갈 of 제갈지봉.
// A given name is two characters almost without exception.
function familyName(name){
 const text=String(name||'').trim();
 return text.length>=4?text.slice(0,2):text.slice(0,1);
}
// Another name is looked for as the whole name it makes with the family name —
// 김용학, 金龍鶴 — as well as by itself.
function searchText(person){
 const korean=familyName(person.korean_name),hanja=familyName(person.hanja_name);
 const others=otherNames(person).flatMap(name=>[
  name.korean,name.korean&&korean+name.korean,name.hanja&&hanja+name.hanja]);
 return [person.korean_name,person.hanja_name,person.note,...others].filter(Boolean).join(' ').toLowerCase();
}
// Spaces are not held against a search: 김 용학 finds 김용학.
function searchMatches(person,query){
 const text=searchText(person),q=String(query||'').toLowerCase().trim();
 return text.includes(q)||text.replace(/\s+/g,'').includes(q.replace(/\s+/g,''));
}
function personCard(person){
 const photo=book.files.find(file=>file.person_id===person.id&&/\.(png|jpe?g)$/i.test(file.name));
 const tone=person.gender==='남'?' male':person.gender==='여'?' female':'';
 const dates=[person.birth_date?shownDate(person.birth_date):'출생일 미상',person.death_date?'— '+shownDate(person.death_date):''].filter(Boolean).join(' ');
 return `<button type="button" class="person-card${tone}" data-person="${person.id}">`
  +`<span class="person-portrait">${photo?`<img src="/api/files/${photo.id}?size=240" alt="">`:esc(person.korean_name.slice(0,1))}</span>`
  +'<span class="person-body">'
  +`<strong>${esc(displayName(person).primary)}</strong>`
  +`<span class="person-hanja">${esc(displayName(person).other||'한자명 미등록')}</span>`
  +otherNames(person).map(name=>`<span class="person-other"><i>${esc(name.kind)}</i> ${esc(name.hanja||name.korean)}${name.hanja&&name.korean?` <em>${esc(name.korean)}</em>`:''}</span>`).join('')
  +`<small>${esc(dates)}</small>`
  +`<span class="badge">${person.generation}세대 · ${esc(genderText(person.gender))}</span>`
  +'</span></button>';
}
// The book records one lineage. Whoever married into it is set under their
// spouse as 配, and their own forebears — kept so the marriage can be traced —
// belong to another clan's book, not to a 世 of this one. Anyone whose only
// issue married in is in the record for that reason alone, and so is anyone
// above them.
function outsideTheLine(hostOf){
 const parentsOf=new Map(),childrenOf=new Map();
 for(const link of book.relations){
  if(link.kind!=='parent')continue;
  if(!childrenOf.has(link.source_id))childrenOf.set(link.source_id,[]);
  childrenOf.get(link.source_id).push(link.target_id);
  if(!parentsOf.has(link.target_id))parentsOf.set(link.target_id,[]);
  parentsOf.get(link.target_id).push(link.source_id);
 }
 const outside=new Set(hostOf.keys());
 for(let pass=0;pass<book.persons.length;pass++){
  let grew=false;
  for(const person of book.persons){
   if(outside.has(person.id))continue;
   const children=childrenOf.get(person.id)||[];
   if(!children.length||!children.every(id=>outside.has(id)))continue;
   // Someone with a forebear of this line in the book is of it, whoever they married.
   if((parentsOf.get(person.id)||[]).some(id=>!outside.has(id)))continue;
   outside.add(person.id);
   grew=true;
  }
  if(!grew)break;
 }
 return outside;
}
// How wide each person's column comes out, and how much of a row a sheet has
// room for, taken from a sheet laid out off screen in the same type.
// '31세 660쪽, 36세 702쪽' → 31 → 660, 36 → 702.
function pageBreaks(text){
 const jumps=new Map();
 for(const match of String(text||'').matchAll(/(\d{1,3})\s*(?:세|世)?\D*?(\d{2,5})/g))jumps.set(Number(match[1]),Number(match[2]));
 return jumps;
}
function measureBookEntries(entryHTML){
 const probe=document.createElement('div');
 probe.style.cssText='position:absolute;left:-20000px;top:0;visibility:hidden';
 const rows=Array.from({length:BOOK_ROWS},(_,index)=>`<section class="genealogy-generation"><h3>世</h3><div class="genealogy-entries">${index?'':[...entryHTML.values()].join('')}</div></section>`).join('');
 probe.innerHTML=`<article class="book-page traditional-book"><aside class="genealogy-side"></aside><aside class="genealogy-branch"></aside><div class="genealogy-body">${rows}</div></article>`;
 document.body.append(probe);
 const widths=new Map();
 probe.querySelectorAll('[data-book-person]').forEach(one=>widths.set(Number(one.dataset.bookPerson),Math.ceil(one.getBoundingClientRect().width)));
 const room=Math.max(120,Math.floor(probe.querySelector('.genealogy-entries').clientWidth));
 probe.remove();
 return {widths,room};
}
function bookHTML(people){
 const {byId,surname,married,hostOf}=spouseHosts();
 const printed=outsideTheLine(hostOf);
 const keys=new Map(book.persons.map(p=>[p.id,columnKey(p,byId,fatherIndex(byId))]));
 const columns=people.filter(p=>!printed.has(p.id)).sort((a,b)=>compareKeys(keys.get(a.id),keys.get(b.id)));
 if(!columns.length)return '<p class="empty">인쇄할 기록이 없습니다.</p>';
 const generations=columns.map(p=>p.generation);
 const first=Math.min(...generations),last=Math.max(...generations);
 const volume=book.volume?bookWord(`卷之${hanjaNumber(book.volume)}`,`${book.volume}권`):'';
 const origin=book.founder?bookWord('始祖 '+book.founder,'시조 '+scriptText(book.founder)):'';
 const pages=[],sheetTops=[];
 const jumps=pageBreaks(book.page_breaks);
 const entryHTML=new Map(columns.map(p=>[p.id,personEntry(p,married.get(p.id)||[],surname)]));
 const {widths,room}=measureBookEntries(entryHTML);
 // Whose column each one hangs under: the father, or else the parent on record
 // — through the one they married where that parent married into the line.
 const inBook=new Set(columns.map(p=>p.id)),fatherOf=fatherIndex(byId),parentOf=new Map();
 for(const person of columns){
  let parent=fatherOf.get(person.id);
  if(!inBook.has(parent)){
   const link=book.relations.find(r=>r.kind==='parent'&&r.target_id===person.id
    &&(inBook.has(r.source_id)||inBook.has(hostOf.get(r.source_id))));
   parent=link?(inBook.has(link.source_id)?link.source_id:hostOf.get(link.source_id)):undefined;
  }
  if(inBook.has(parent)&&parent!==person.id)parentOf.set(person.id,parent);
 }
 // Brothers and sisters as the book sets them: sons eldest first, then daughters.
 const rank=person=>person.gender==='남'?0:person.gender==='여'?2:1;
 const born=person=>/^\d{4}/.test(person.birth_date||'')?person.birth_date:'9999';
 const bySiblings=(a,b)=>rank(a)-rank(b)||(born(a)<born(b)?-1:born(a)>born(b)?1:0)||a.id-b.id;
 const childrenOf=new Map();
 for(const person of columns){
  if(!parentOf.has(person.id))continue;
  if(!childrenOf.has(parentOf.get(person.id)))childrenOf.set(parentOf.get(person.id),[]);
  childrenOf.get(parentOf.get(person.id)).push(person);
 }
 // Traditional pages hold six 世 rows and repeat the last one as the next page's
 // first row, so the linking generation appears on both sheets.
 for(let top=first;top<=last;top+=BOOK_ROWS-1){
  // The first row repeats the previous sheet's last generation, so a sheet with
  // nothing below that row would only reprint what the reader already has.
  // — unless the printed book picks the line up again on a page of its own at
  // that generation (31세 660쪽): that page is made even before anyone below
  // it is entered, as the book has it.
  if(top>first&&!columns.some(p=>p.generation>top&&p.generation<top+BOOK_ROWS)&&!jumps.has(top))break;
  // Each person's column stands where the book would set it: the first child
  // begins under the parent and brothers and sisters follow to the left, each
  // with all of their line below them. The next brother starts only past the
  // whole of the one before, so every column sits under its own parent and no
  // cousin wanders in under an uncle.
  const inGroup=p=>p.generation>=top&&p.generation<top+BOOK_ROWS;
  const at=new Map(),blocks=new Map();
  const kidsOf=person=>(childrenOf.get(person.id)||[]).filter(inGroup).sort(bySiblings);
  const block=person=>{
   if(!blocks.has(person.id)){
    blocks.set(person.id,widths.get(person.id)||40);
    blocks.set(person.id,Math.max(widths.get(person.id)||40,kidsOf(person).reduce((sum,kid)=>sum+block(kid),0)));
   }
   return blocks.get(person.id);
  };
  // A column is never cut between two sheets: one that would cross the edge of
  // a sheet starts on the next, and so does a whole family that would fit on one.
  const fits=(r,w)=>w>=room||Math.floor(r/room)===Math.floor((r+w-1)/room);
  const next=r=>Math.ceil(r/room)*room;
  const place=(person,r)=>{
   const w=widths.get(person.id)||40,whole=block(person);
   if(whole<=room?!fits(r,whole):!fits(r,w))r=next(r);
   at.set(person.id,r);
   const kids=kidsOf(person);
   let end=r;
   kids.forEach(kid=>{end=place(kid,end);});
   // Children that had to start on the next sheet take their parent with them.
   const under=kids.length?at.get(kids[0].id):r;
   if(under>r&&fits(under,w))at.set(person.id,under);
   return Math.max(at.get(person.id)+w,end);
  };
  let end=0;
  columns.filter(p=>inGroup(p)&&!(parentOf.has(p.id)&&inGroup(byId.get(parentOf.get(p.id)))))
   .forEach(root=>{end=place(root,end);});
  const reach=Math.max(0,...[...at].map(([id,r])=>r+(widths.get(id)||40)));
  // What will not go on one sheet runs on over the next, the rows repeated.
  for(let sheet=0;sheet<Math.max(1,Math.ceil(reach/room));sheet++){
   const rows=[];
   let any=false;
   for(let offset=0;offset<BOOK_ROWS;offset++){
    const generation=top+offset;
    const entries=columns.filter(p=>p.generation===generation&&at.has(p.id)&&Math.floor(at.get(p.id)/room)===sheet)
     .map(p=>{any=true;return entryHTML.get(p.id).replace('<section class="genealogy-person"',`<section class="genealogy-person placed" style="right:${at.get(p.id)-sheet*room}px"`);}).join('');
    rows.push(`<section class="genealogy-generation"><h3>${bookWord(hanjaNumber(generation)+'世',generation+'세')}</h3><div class="genealogy-entries">${entries}</div></section>`);
   }
   if(!any&&sheet>0)continue;
   sheetTops.push({top,first:sheet===0});
   // The first sheet carries the book's name and its 파 in two columns at the
   // right, as the book opens; every sheet after it carries them at the left
   // in one column, the name above the 파, and keeps only the 世 at its right.
   const branch=esc(scriptText(book.branch_name||book.bon_gwan||''));
   const margin=pages.length
    ?`<aside class="genealogy-margin"><strong>${esc(scriptText(book.title))}</strong>${branch?`<b>${branch}</b>`:''}${volume?`<span>${esc(volume)}</span>`:''}${origin?`<small>${esc(origin)}</small>`:''}</aside>`
    :`<aside class="genealogy-side"><strong>${esc(scriptText(book.title))}</strong>${volume?`<span>${esc(volume)}</span>`:''}${origin?`<small>${esc(origin)}</small>`:''}</aside><aside class="genealogy-branch">${branch}</aside>`;
   pages.push(`<article class="book-page traditional-book${pages.length?' margin-left':''}">${margin}<div class="genealogy-body">${rows.join('')}</div></article>`);
  }
 }
 // Each sheet is printed on paper of its own, headed with the page of the
 // printed book it stands for (617, 618, …) and when it was printed, and footed
 // with its place among the sheets. The browser's own lines — the app's title,
 // its address — are left off the paper.
 // Numbered from the book's first page one sheet at a time, except where the
 // printed book jumps as a generation begins (31세 660쪽): the sheet that
 // opens with that generation takes that page, and the count goes on from it.
 let number=parseInt(book.page,10);
 const numbers=pages.map((page,index)=>{
  if(index)number+=1;
  if(sheetTops[index].first&&jumps.has(sheetTops[index].top))number=jumps.get(sheetTops[index].top);
  return Number.isFinite(number)?number:'';
 });
 return pages.map((page,index)=>`<section class="book-sheet"><div class="sheet-head">`
  +`<span class="sheet-page">${numbers[index]}</span><span class="sheet-date"></span></div>${page}`
  +`<div class="sheet-foot">${index+1} / ${pages.length}</div></section>`).join('');
}
// The moment of printing, as the sheet heads it: 2026. 9. 25. 오후 10:50.
function stampSheets(){
 const now=new Date().toLocaleString('ko-KR',{year:'numeric',month:'numeric',day:'numeric',hour:'numeric',minute:'2-digit'});
 document.querySelectorAll('.sheet-date').forEach(one=>{one.textContent=now;});
}
window.addEventListener('beforeprint',stampSheets);
// Which details each tree card shows. The set is shared by every card so one card
// height fits all, and it is remembered per browser.
const TREE_FIELDS=[['generation','세대'],['hanja','이름 병기'],['bon_gwan','본관'],['birth','출생일'],['death','사망일'],['age','나이'],['photo','사진'],['note','기록/생애'],['gender','성별 색']];
let treeOptions={generation:true,hanja:true,bon_gwan:false,birth:false,death:false,age:false,photo:false,note:false,gender:true};
try{Object.assign(treeOptions,JSON.parse(localStorage.getItem('jocbo.tree')||'{}'));}catch{}
function saveTreeOptions(){try{localStorage.setItem('jocbo.tree',JSON.stringify(treeOptions));}catch{}}
function ageText(person){
 // An age needs both years; the month and day only settle a birthday not yet reached.
 if(!/^\d{4}/.test(person.birth_date||''))return '';
 const dead=/^\d{4}/.test(person.death_date||''),end=dead?person.death_date:todayISO();
 let years=Number(end.slice(0,4))-Number(person.birth_date.slice(0,4));
 if(end.length===10&&person.birth_date.length===10&&end.slice(5)<person.birth_date.slice(5))years--;
 // No 졸년 on a long-past birth means the record is simply unfinished, not a 139-year-old.
 if(years<0||(!dead&&years>120))return '';
 return (dead?'향년 ':'만 ')+years+'세';
}
// Every card keeps the same number of detail rows, empty ones included, so the rows
// of the tree stay level.
function treeDetailRows(){
 return [treeOptions.generation||treeOptions.hanja,treeOptions.bon_gwan,treeOptions.birth||treeOptions.death,treeOptions.age].filter(Boolean).length;
}
function treeDetails(person,outside){
 const rows=[];
 if(treeOptions.generation||treeOptions.hanja)
  rows.push([treeOptions.generation?(outside?'外家':person.generation+'세대'):'',treeOptions.hanja?displayName(person).other:''].filter(Boolean).join(' · '));
 if(treeOptions.bon_gwan)rows.push(person.bon_gwan?'본관 '+scriptText(person.bon_gwan):'');
 if(treeOptions.birth||treeOptions.death)
  rows.push([treeOptions.birth&&person.birth_date?shownDate(person.birth_date):'',treeOptions.death&&person.death_date?'— '+shownDate(person.death_date):''].filter(Boolean).join(' '));
 if(treeOptions.age)rows.push(ageText(person));
 return rows;
}
function treeOptionsHTML(){
 return `<form id="treeOptions" class="tree-options"><strong>표시 항목</strong>${TREE_FIELDS.map(([name,label])=>
  `<label><input type="checkbox" name="${name}"${treeOptions[name]?' checked':''}>${label}</label>`).join('')}</form>`
  ;
}
function treeLegendHTML(){
 const clan=book?[book.bon_gwan,book.clan_name].filter(Boolean).map(scriptText).join(' '):'';
 return `<p class="tree-legend"><span><i class="line-solid"></i>${esc(clan||'이 족보')} 계대</span>`
  +'<span><i class="line-dashed"></i>혼인으로 들어온 분의 친가</span></p>';
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
function wrapZoom(inner,trailing=''){
 return '<div class="zoom-bar" title="끌어서 이동 · Ctrl + 휠로 확대·축소">'
  +'<button type="button" class="secondary" data-zoom="out" aria-label="축소">−</button>'
  +'<span class="zoom-level">100%</span>'
  +'<button type="button" class="secondary" data-zoom="in" aria-label="확대">+</button>'
  +'<button type="button" class="secondary" data-zoom="reset">100%</button>'
  +'<button type="button" class="secondary" data-zoom="fit">맞추기</button>'
  +'<button type="button" class="secondary" data-zoom="full" aria-pressed="false">전체 화면</button>'
  // Printing is looked for where the drawing is, not only at the top of the page.
  +'<button type="button" class="secondary" data-zoom-print>인쇄 / PDF</button>'
  // The view tabs' own 한글/한자 switch is covered in 전체 화면, so it rides
  // along on this bar there.
  +'<button type="button" class="secondary zoom-script" data-script-toggle="page">한글로 보기</button>'
  +'<small><span class="long">끌어서 이동 · Ctrl + 휠로 확대·축소</span><span class="short">끌어서 이동<br>Ctrl+휠 확대</span></small>'+trailing+'</div>'
  +`<div class="zoom-scroll"><div class="zoom-sizer"><div class="zoom-body">${inner}</div></div></div>`
  +'<div class="frame-resizer" role="separator" aria-orientation="horizontal" tabindex="0" aria-label="보기 높이 조절" title="끌어서 높이 조절 · 두 번 누르면 기본 높이"></div>';
}
// The window onto a wide tree can be dragged taller from the rule under it, and
// the height is kept; or the view can take the whole browser window. That is a
// class on <body> rather than the browser's fullscreen, so it survives the redraw
// after a person is saved, and the dialogs still open above it.
const FRAME_MIN=240;
let frameHeight=0;
try{frameHeight=Number(localStorage.getItem('jocbo.frameHeight'))||0;}catch{}
function applyFrameHeight(px){
 frameHeight=px?Math.max(FRAME_MIN,Math.round(px)):0;
 const scroll=$('.zoom-scroll');
 if(scroll){scroll.style.height=frameHeight?frameHeight+'px':'';scroll.style.maxHeight=frameHeight?'none':'';}
 try{frameHeight?localStorage.setItem('jocbo.frameHeight',String(frameHeight)):localStorage.removeItem('jocbo.frameHeight');}catch{}
 if(!frameHeight)fitFrame();
}
function setViewFull(on){
 document.body.classList.toggle('view-full',on);
 // In 전체 화면 the bar floats over the whole window, which it cannot do from
 // inside the sticky row of tabs; it goes back there after.
 const bar=$('.zoom-bar');
 if(bar)(on?document.body:$('#viewTools')).append(bar);
 if(!on)fitFrame();
 document.querySelectorAll('[data-zoom="full"]').forEach(button=>{button.textContent=on?'전체 화면 닫기':'전체 화면';button.setAttribute('aria-pressed',String(on));});
}
document.addEventListener('keydown',event=>{
 if(event.key==='Escape'&&document.body.classList.contains('view-full')&&!document.querySelector('dialog[open]'))setViewFull(false);
});
function bindFrame(){
 const handle=$('.frame-resizer'),scroll=$('.zoom-scroll');
 if(!handle||!scroll)return;
 applyFrameHeight(frameHeight);
 setViewFull(document.body.classList.contains('view-full'));
 $('[data-zoom="full"]').onclick=()=>setViewFull(!document.body.classList.contains('view-full'));
 const script=$('.zoom-bar [data-script-toggle]');
 if(script){script.onclick=()=>toggleScript(script);paintScriptToggle();}
 handle.onpointerdown=event=>{
  event.preventDefault();
  try{handle.setPointerCapture(event.pointerId);}catch{}
  document.body.classList.add('resizing-rows');
  const move=moved=>applyFrameHeight(moved.clientY-scroll.getBoundingClientRect().top);
  const stop=()=>{
   window.removeEventListener('pointermove',move);
   window.removeEventListener('pointerup',stop);
   window.removeEventListener('pointercancel',stop);
   document.body.classList.remove('resizing-rows');
  };
  window.addEventListener('pointermove',move);
  window.addEventListener('pointerup',stop);
  window.addEventListener('pointercancel',stop);
 };
 handle.ondblclick=()=>applyFrameHeight(0);
 handle.onkeydown=event=>{
  const step=event.shiftKey?120:40,now=scroll.getBoundingClientRect().height;
  if(event.key==='ArrowDown'){applyFrameHeight(now+step);event.preventDefault();}
  if(event.key==='ArrowUp'){applyFrameHeight(now-step);event.preventDefault();}
 };
}
// Switching script or a display option redraws the whole view, so where the
// reader had scrolled to is kept and put back rather than snapping to the corner.
const zoomScrollAt=new Map();
// Where the frame's top stands once the row of tabs has stuck at the top of
// the window: just under that row.
function underTabs(){
 const bar=document.querySelector('.view-bar');
 return bar?(parseFloat(getComputedStyle(bar).top)||0)+bar.getBoundingClientRect().height+8:0;
}
// Unless the reader has set the frame's height, it takes what is left of the
// window under the row of tabs.
function fitFrame(){
 const frame=$('.zoom-scroll');
 if(!frame||frameHeight||document.body.classList.contains('view-full'))return;
 frame.style.maxHeight=Math.max(240,window.innerHeight-underTabs()-14)+'px';
}
window.addEventListener('resize',()=>fitFrame());
// How many turns of the wheel rest at the foot of the drawing before the
// page goes on below it, and the count of those taken so far.
const FOOT_REST_TURNS=2;
const footRest={count:0,last:0};
function bindZoom(key){
 const scroll=$('.zoom-scroll'),sizer=$('.zoom-sizer'),body=$('.zoom-body'),level=$('.zoom-level');
 if(!scroll)return;
 // The controls sit in the row of the view tabs, where there is room, rather
 // than on a line of their own above the drawing.
 const bar=$('#view .zoom-bar');
 // A bar left floating over the window from before this drawing goes; only
 // the new one stays.
 document.querySelectorAll('body > .zoom-bar').forEach(old=>old.remove());
 if(bar)$('#viewTools').append(bar);
 bindFrame();
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
 fitFrame();
 if(wasAt){scroll.scrollLeft=wasAt.left;scroll.scrollTop=wasAt.top;}
 scroll.addEventListener('scroll',()=>zoomScrollAt.set(key,{left:scroll.scrollLeft,top:scroll.scrollTop}));
 // Dragging the canvas beats reaching for the scrollbar once the tree is wider
 // than the window. The plain wheel keeps scrolling; Ctrl with it zooms about the
 // pointer, which stays put while everything around it grows.
 scroll.addEventListener('wheel',event=>{
  if(!event.ctrlKey&&!event.metaKey){
   // At the top or foot of the frame the wheel goes on to the page. Left to
   // the browser, a turn of the wheel that began inside the frame stays with
   // it after it has reached its end, and the page stands still until the
   // wheel rests.
   if(document.body.classList.contains('view-full')||!event.deltaY)return;
   const step=event.deltaY*(event.deltaMode===1?40:event.deltaMode===2?window.innerHeight:1);
   // Going down, the page comes first: it scrolls until the row of tabs
   // sticks at the top of the window and the frame fills the rest under it,
   // and only then does the drawing inside it move.
   if(step>0){
    const gap=scroll.getBoundingClientRect().top-underTabs();
    const room=document.documentElement.scrollHeight-window.innerHeight-window.scrollY;
    if(gap>1&&room>1){
     event.preventDefault();
     window.scrollBy(0,Math.min(step,gap,room));
     return;
    }
   }
   const atTop=scroll.scrollTop<=0,atFoot=scroll.scrollTop+scroll.clientHeight>=scroll.scrollHeight-1;
   // At the foot of the drawing the page waits: two more turns rest there,
   // so the end of the tree or the book is seen whole, and the third goes
   // on down to 가족 관계 below it.
   if(step>0&&atFoot){
    event.preventDefault();
    const now=Date.now();
    if(now-footRest.last>1500)footRest.count=0;
    footRest.last=now;
    if(++footRest.count<=FOOT_REST_TURNS)return;
    window.scrollBy(0,step);
    return;
   }
   footRest.count=0;
   if(step<0&&atTop){
    event.preventDefault();
    window.scrollBy(0,step);
   }
   return;
  }
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
  // The book is text from edge to edge, so there a drag moves the sheets, as
 // on the tree, and Shift with it selects the text instead.
 if(!middle&&event.target.closest(KEEPS_ITS_OWN_DRAG)&&(key!=='book'||event.shiftKey))return;
  pan={x:event.clientX,y:event.clientY,left:scroll.scrollLeft,top:scroll.scrollTop,page:window.scrollY};
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
  const want=pan.top-dy;
  scroll.scrollTop=want;
  // Past the top or foot of the frame the drag carries on with the page, so
  // the forebears at the top of the tree come down into view even when the
  // page itself was scrolled past them.
  if(!document.body.classList.contains('view-full'))window.scrollTo(window.scrollX,pan.page+want-scroll.scrollTop);
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
 // Two fingers spread or pinched zoom about the point between them, as on a
 // phone's photos; one finger still scrolls. The frame's touch-action leaves
 // the pinch to this page rather than to the browser, which would zoom the
 // whole page instead of the drawing.
 let pinch=null;
 const spread=touches=>Math.hypot(touches[0].clientX-touches[1].clientX,touches[0].clientY-touches[1].clientY);
 scroll.addEventListener('touchstart',event=>{
  if(event.touches.length!==2)return;
  pan=null;scroll.classList.remove('panning');
  pinch={distance:spread(event.touches)||1,zoom};
 },{passive:true});
 scroll.addEventListener('touchmove',event=>{
  if(!pinch||event.touches.length!==2)return;
  event.preventDefault();
  const [a,b]=event.touches;
  apply(pinch.zoom*spread(event.touches)/pinch.distance,(a.clientX+b.clientX)/2,(a.clientY+b.clientY)/2);
 },{passive:false});
 const endPinch=event=>{if(event.touches.length<2)pinch=null;};
 scroll.addEventListener('touchend',endPinch);
 scroll.addEventListener('touchcancel',endPinch);
 $('[data-zoom="in"]').onclick=()=>apply(zoom*1.2);
 $('[data-zoom="out"]').onclick=()=>apply(zoom/1.2);
 $('[data-zoom="reset"]').onclick=()=>apply(1);
 $('[data-zoom="fit"]').onclick=()=>apply((scroll.clientWidth-26)/base.w);
 $('[data-zoom-print]').onclick=()=>{setViewFull(false);(key==='tree'?$('#printTree'):$('#print')).click();};
}
function renderTree(people){
 const options=treeOptionsHTML();
 if(!people.length){$('#view').innerHTML=options+'<p class="empty">표시할 인물이 없습니다.</p>';bindTreeOptions();return;}
 const {byId,married,hostOf}=spouseHosts();
 const beyond=outsideTheLine(hostOf);
 // A 配 keeps the 세 they married into; it is their own forebears who have none.
 const outside=new Set([...beyond].filter(id=>!hostOf.has(id)));
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
 // Someone who married in may have their own forebears in the book. Their unit
 // hangs from the marriage, not from those forebears, so the descent to them is
 // kept as a link of its own and drawn to the single card rather than by
 // attaching the whole unit — which would make their spouse a child too.
 const marriedIn=[];
 for(const unit of units.values()){
  for(const member of unit.members){
   if(member.id===unit.host.id)continue;
   const ids=[...(parentsOf.get(member.id)||[])];
   const parentUnit=ids.map(id=>unitOf.get(id)).find(Boolean);
   if(!parentUnit||parentUnit===unit)continue;
   marriedIn.push({parentUnit,member,ids});
  }
 }
 // With one marriage there is one family: a child with only the father on
 // record and a brother with both belong to the same couple, and splitting them
 // put the brother apart from the rest.
 for(const unit of units.values()){
  if(unit.members.length===2&&unit.families.length>1){
   const mate=unit.members.find(m=>m!==unit.host);
   unit.families=[{mate,children:unit.families.flatMap(family=>family.children)}];
  }
 }
 // Brothers and sisters stand left to right as a 가계도 sets them: the sons,
 // eldest first, then the daughters, eldest first; an unknown birth goes last.
 const rank=person=>person.gender==='남'?0:person.gender==='여'?2:1;
 const born=person=>/^\d{4}/.test(person.birth_date||'')?person.birth_date:'9999';
 const bySiblingOrder=(a,b)=>rank(a.host)-rank(b.host)||(born(a.host)<born(b.host)?-1:born(a.host)>born(b.host)?1:0)||a.host.id-b.host.id;
 for(const unit of units.values()){
  unit.families.sort((a,b)=>unit.members.indexOf(a.mate||unit.host)-unit.members.indexOf(b.mate||unit.host));
  unit.families.forEach(family=>family.children.sort(bySiblingOrder));
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
  // Children come from between the couple. Often only one parent is on record —
  // a mother not yet identified — and the line must still start in the middle of
  // the marriage, which is where a 가계도 puts it. Where there is more than one
  // marriage there is no telling which it belongs to, so it drops from under the
  // parent who is on record instead.
  const spouses=unit.members.filter(m=>m!==unit.host);
  const partner=family.mate||(spouses.length===1?spouses[0]:null);
  const mateIndex=partner?unit.members.indexOf(partner):-1;
  const hostIndex=unit.members.indexOf(unit.host);
  const adjacent=mateIndex>=0&&Math.abs(mateIndex-hostIndex)===1;
  const mate=partner?pos.get(partner.id):null;
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
 // Drawn like any other descent, but ending at the one card instead of a rail
 // of siblings.
 const marriedInLines=marriedIn.map(({parentUnit,member,ids})=>{
  const target=pos.get(member.id);
  const from=ids.map(id=>pos.get(id)).filter(Boolean);
  if(!target||!from.length)return '';
  const sx=from.reduce((sum,at)=>sum+at.x+nodeW/2,0)/from.length;
  const sy=Math.max(...from.map(at=>at.y))+nodeH;
  if(sy>=target.y)return '';
  const cx=target.x+nodeW/2,railY=sy+(target.y-sy)/2;
  return `<path class="parent-line married-in" d="M ${sx} ${sy} V ${railY} H ${cx} V ${target.y}"/>`;
 }).join('');
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
  const tone=(treeOptions.gender&&p.gender!=='미상'?(p.gender==='남'?' male':' female'):'')
   +(outside.has(p.id)?' outside':'');
  return `<div class="tree-node" style="left:${at.x}px;top:${at.y}px;width:${nodeW}px;height:${nodeH}px">`
   +`<div class="tree-card${tone}" data-tree-person="${p.id}" role="button" tabindex="0">`
   +(treeOptions.photo?`<span class="tree-photo">${photo?`<img src="/api/files/${photo.id}?size=240" alt="">`:''}</span>`:'')
   +`<strong>${esc(displayName(p).primary)}</strong>`
   +treeDetails(p,outside.has(p.id)).map(row=>`<span class="tree-line">${esc(row)}</span>`).join('')
   +(treeOptions.note?`<small>${esc(scriptText(p.note||''))}</small>`:'')
   +'</div>'
   +addButton(p.id,'parent','+')+addButton(p.id,'child','+')
   +addButton(p.id,'spouse','+')+addButton(p.id,'sibling','+',!parentsOf.has(p.id))
   +'</div>';
 }).join('');
 // Solid for this book's own line, dashed for a forebear of someone who married
 // in — a different clan, and no part of the 계대 this book records. Easy to read
 // once said, impossible to guess until then, so it is said beside the drawing.
 $('#view').innerHTML=options+wrapZoom(`<div class="tree-canvas" style="width:${width}px;height:${height}px">`
  +`<svg class="family-tree" width="${width}" height="${height}" aria-hidden="true">${parentLines}${marriedInLines}${mateLines}${labels}</svg>${cards}</div>`,
  marriedIn.length?treeLegendHTML():'');
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
 const {kind,anchor}=pendingRelative;
 try{
  await busy($('#relativeLink'),'연결 중…',()=>linkRelative(otherId));
  $('#personDialog').close();
  const also=await settleMarriage(kind,anchor.id,otherId);
  await refresh();
  message('가족 관계 추가 완료'+also);
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
 $('#fileList').innerHTML=p?fileListHTML(id):'';
 setPersonScriptFields(p||{bon_gwan:book.bon_gwan||'',note:''});
 paintDateBoxes(f);
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
// ── 날짜 칸 ──
// The browser's date box gives back nothing at all while one of its year, month
// and day is empty, so a date the book gives only in part could not be kept.
// It is replaced by a box of the same look — 연도-월-일 and a calendar at the
// end — whose parts may each be left empty. Every part filled keeps its rule:
// a year of four figures, a month of 1 to 12, a day up to the end of its month.
// The date is kept in a hidden box under the field's name, as 1956, 1956-03,
// 1956-03-02, or --03-02 when there is no year.
const CALENDAR_ICON='<svg viewBox="0 0 16 16" width="15" height="15" aria-hidden="true"><path fill="currentColor" d="M4 0h1.5v2h5V0H12v2h2a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1h2zM2.5 6v8.5h11V6z"/></svg>';
function dateShown(box){
 const shell=box.previousElementSibling;
 return shell&&shell.classList.contains('date-box')?shell.querySelector('[data-seg="y"]'):box;
}
function dateFromSegments(y,m,d){
 if(!y&&!m&&!d)return {value:''};
 if(y&&!/^\d{4}$/.test(y))return {problem:'연도 4자리 형식 · 예: 1956',seg:'y'};
 if(y&&Number(y)<1)return {problem:'연도는 1년부터',seg:'y'};
 if(m&&!(Number(m)>=1&&Number(m)<=12))return {problem:'월은 1~12',seg:'m'};
 if(d&&!(Number(d)>=1&&Number(d)<=31))return {problem:'일은 1~31',seg:'d'};
 if(d&&!m)return {problem:'월 없이 일만은 불가 · 월 입력',seg:'m'};
 if(!y&&!d)return {problem:'연도 없이 월만은 불가 · 일도 입력',seg:'d'};
 const pad=n=>String(Number(n)).padStart(2,'0');
 const value=y?[y,m&&pad(m),d&&pad(d)].filter(Boolean).join('-'):`--${pad(m)}-${pad(d)}`;
 if(!validDate(value))return {problem:`${Number(m)}월에는 ${Number(d)}일이 없음 · 일은 해당 월의 마지막 날까지`,seg:'d'};
 return {value};
}
function readDateBox(shell){
 const hidden=shell.nextElementSibling;
 const seg=name=>shell.querySelector(`[data-seg="${name}"]`).value.trim();
 const found=dateFromSegments(seg('y'),seg('m'),seg('d'));
 hidden.value=found.value||'';
 hidden.dataset.problem=found.problem||'';
 hidden.dataset.seg=found.seg||'';
 hidden.dataset.typed=['y','m','d'].some(name=>seg(name))?'1':'';
 shell.classList.toggle('empty',!hidden.dataset.typed);
 paintDateClears();
}
// After a date is set in code — a record opened, a reading filled in, 지우기 —
// its parts are shown from it.
function paintDateBoxes(root){
 for(const shell of root.querySelectorAll('.date-box')){
  const hidden=shell.nextElementSibling,{y,m,d}=dateParts(hidden.value);
  shell.querySelector('[data-seg="y"]').value=y?String(y).padStart(4,'0'):'';
  shell.querySelector('[data-seg="m"]').value=m?String(m).padStart(2,'0'):'';
  shell.querySelector('[data-seg="d"]').value=d?String(d).padStart(2,'0'):'';
  hidden.dataset.problem='';
  hidden.dataset.seg='';
  hidden.dataset.typed=hidden.value?'1':'';
  shell.classList.toggle('empty',!hidden.value);
 }
 paintDateClears();
}
function upgradeDateInput(native){
 const name=native.name;
 const shell=document.createElement('div');
 shell.className='date-box empty';
 shell.innerHTML='<input data-seg="y" inputmode="numeric" maxlength="4" placeholder="연도" autocomplete="off" aria-label="연도">'
  +'<span>-</span><input data-seg="m" inputmode="numeric" maxlength="2" placeholder="월" autocomplete="off" aria-label="월">'
  +'<span>-</span><input data-seg="d" inputmode="numeric" maxlength="2" placeholder="일" autocomplete="off" aria-label="일">'
  +`<button type="button" class="date-calendar" tabindex="-1" title="달력에서 고르기" aria-label="달력에서 고르기">${CALENDAR_ICON}</button>`;
 const hidden=document.createElement('input');
 hidden.type='hidden';
 hidden.name=name;
 native.removeAttribute('name');
 native.tabIndex=-1;
 native.setAttribute('aria-hidden','true');
 native.classList.add('date-native');
 native.replaceWith(shell);
 shell.append(native);
 shell.after(hidden);
 const segs=['y','m','d'].map(seg=>shell.querySelector(`[data-seg="${seg}"]`));
 segs.forEach((box,index)=>{
  // As the browser's box does: figures only, and on to the next part once
  // this one can take no more.
  box.addEventListener('input',()=>{
   box.value=box.value.replace(/\D/g,'');
   const full=box.value.length>=Number(box.maxLength)
    ||(box.dataset.seg==='m'&&Number(box.value)>1)||(box.dataset.seg==='d'&&Number(box.value)>3);
   if(full&&segs[index+1])segs[index+1].focus(),segs[index+1].select();
   readDateBox(shell);
  });
  box.addEventListener('keydown',event=>{
   if(event.key==='Backspace'&&!box.value&&segs[index-1]){event.preventDefault();segs[index-1].focus();}
   if((event.key==='-'||event.key==='/'||event.key==='.')&&segs[index+1]){event.preventDefault();segs[index+1].focus();segs[index+1].select();}
  });
  box.addEventListener('blur',()=>{
   if(box.dataset.seg!=='y'&&/^\d$/.test(box.value)&&box.value!=='0')box.value='0'+box.value;
   readDateBox(shell);
  });
 });
 shell.querySelector('.date-calendar').onclick=()=>{
  // The calendar stops at today, so a later day is never offered.
  native.max=todayISO();
  native.value=/^\d{4}-\d{2}-\d{2}$/.test(hidden.value)?hidden.value:'';
  try{native.showPicker();}catch{native.focus();}
 };
 native.addEventListener('change',()=>{
  if(!native.value)return;
  hidden.value=native.value;
  paintDateBoxes(shell.parentElement);
 });
 // 지우기 and anything else that sets the date from outside.
 hidden.addEventListener('input',()=>paintDateBoxes(shell.parentElement));
}
for(const native of $('#personForm').querySelectorAll('input[type="date"]'))upgradeDateInput(native);
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
  button.disabled=!input||!(input.value||input.dataset.typed);
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
// 金 is filed in the dictionary under 금; 김 is how it is read as a surname. The
// surname sits at the head of a person's name but in the middle of a book's —
// 청도김씨대동보 — so the reading is tried wherever the syllable stands, with the
// plain reading's characters first and the surname's own put at the front.
const SURNAME_READINGS={김:'금',이:'리',임:'림',유:'류',나:'라',노:'로',여:'려',양:'량',륙:'유',령:'영'};
const SURNAME_HANJA={김:'金',이:'李',박:'朴',최:'崔',정:'鄭',강:'姜',조:'趙',윤:'尹',장:'張',임:'林',한:'韓',오:'吳',서:'徐',신:'申',권:'權',황:'黃',안:'安',송:'宋',전:'全',홍:'洪',유:'柳',고:'高',문:'文',양:'梁',손:'孫',배:'裴',백:'白',허:'許',남:'南',심:'沈',노:'盧',추:'秋',우:'禹',구:'具',류:'柳'};
function hanjaCandidates(syllable){
 const byStroke=(a,b)=>{
  const common=ch=>{const at=ch.codePointAt(0);return at>=0x4e00&&at<=0x9fff?0:1;};
  return common(a)-common(b)||a.localeCompare(b,'ko');
 };
 const readings=[syllable];
 if(SURNAME_READINGS[syllable])readings.push(SURNAME_READINGS[syllable]);
 const seen=new Set(),result=[];
 for(const reading of readings)
  for(const hanja of (hanjaIndex[reading]||[]).slice().sort(byStroke))
   if(!seen.has(hanja)){seen.add(hanja);result.push(hanja);}
 const first=SURNAME_HANJA[syllable];
 if(first&&result.includes(first))return [first,...result.filter(one=>one!==first)];
 return result;
}

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
 const candidates=hanjaCandidates(syllable);
 $('#hanjaStep').textContent=`${label?label+' — ':''}'${syllable}'의 한자를 고르세요`;
 $('#hanjaPreview').textContent=`${chars.join('')} · 고른 글자: ${chosen.join('')||'아직 없음'}`;
 $('#hanjaCandidates').innerHTML=candidates.length
  ?candidates.map(h=>`<button type="button" data-hanja="${h}" title="${syllable}">${h}</button>`).join('')
  :`<p class="hanja-none">'${esc(syllable)}' 음의 한자 없음 · 한글 그대로 두고 다음 글자로</p>`
   +`<button type="button" class="secondary" data-hanja="${esc(syllable)}">'${esc(syllable)}' 그대로 두기</button>`;
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
 try{const saved=await busy($('#savePerson'),'저장 중…',()=>api(id?'/persons/'+id:'/books/'+book.id+'/persons',id?'PUT':'POST',data));if(!id&&relative){pendingRelative=relative;await linkRelative(saved.id);pendingRelative=null;}$('#personDialog').close();
  const alsoTook=relative&&!id?await settleMarriage(relative.kind,relative.anchor.id,saved.id):'';if(!id)$('#search').value='';await refresh();message(id?`${who} — 저장 완료`:relative?`${who} — ${relative.anchor.korean_name}의 ${RELATIVE_LABELS[relative.kind]}로 등록 완료${alsoTook}`:`${who} — 등록 완료 · 검색어 해제됨`);}catch(err){dialogError(err.message);}};
$('#deletePerson').onclick=async()=>{if(!await ask(`${$('#personForm').elements.korean_name.value} — 연결된 관계와 첨부파일까지 모두 삭제 · 되돌릴 수 없음`,'삭제'))return;dialogError();try{await busy($('#deletePerson'),'삭제 중…',()=>api('/persons/'+$('#personForm').elements.id.value,'DELETE'));$('#personDialog').close();await refresh();message('삭제 완료');}catch(err){dialogError(err.message);}};
$('#upload').onclick=async()=>{dialogError();const file=$('#fileInput').files[0];if(!file){dialogError('업로드할 파일을 먼저 선택하세요.',$('#fileInput'));return;}if(file.size>5*1024*1024){dialogError('파일은 5MB 이하만 업로드할 수 있습니다.',$('#fileInput'));return;}const id=Number($('#personForm').elements.id.value),data=new FormData();data.append('file',file);try{await busy($('#upload'),'업로드 중…',()=>api('/persons/'+id+'/files','POST',data));await refresh();$('#fileList').innerHTML=fileListHTML(id);$('#fileInput').value='';const el=$('#personError');el.textContent='첨부파일을 저장했습니다.';el.hidden=false;el.classList.add('success');}catch(err){dialogError(err.message);}};
// Each attachment with a 삭제 beside it; a wrong photo is taken off again.
function fileListHTML(id){
 return book.files.filter(x=>x.person_id===id).map(x=>`<p class="file-row"><a href="/api/files/${x.id}">${esc(x.name)}</a>`
  +`<button type="button" class="danger small" data-remove-file="${x.id}">삭제</button></p>`).join('');
}
$('#fileList').onclick=async event=>{
 const button=event.target.closest('[data-remove-file]');
 if(!button)return;
 const file=book.files.find(x=>x.id===Number(button.dataset.removeFile));
 if(!file||!await ask(`${file.name} — 첨부파일 삭제 · 되돌릴 수 없음`,'삭제'))return;
 dialogError();
 try{
  await busy(button,'삭제 중…',()=>api('/files/'+file.id,'DELETE'));
  await refresh();
  $('#fileList').innerHTML=fileListHTML(file.person_id);
  const el=$('#personError');el.textContent='첨부파일을 삭제했습니다.';el.hidden=false;el.classList.add('success');
 }catch(err){dialogError(err.message);}
};
function renderRelations(){if(!book)return;const options='<option value="">인물 선택</option>'+book.persons.map(p=>`<option value="${p.id}">${esc(displayName(p).primary)} (${p.generation}세대)</option>`).join('');const anchor=$('#relationForm').elements.source_id;const kept=anchor.value;anchor.innerHTML=options;
 // Whoever was searched for is the one the reader has in mind, so the form
 // starts from them rather than from the first name in the book.
 const q=$('#search').value.toLowerCase().trim();
 const found=q?book.persons.find(p=>searchMatches(p,q)):null;
 anchor.value=found?String(found.id):kept;
 $('#relationForm').querySelector('button').disabled=!book.persons.length;
 // A search is about one family. The book holds other branches that never meet
 // it, and listing those under a name the reader just searched for is noise.
 const chosen=book.persons.find(p=>p.id===Number(anchor.value));
 const kin=chosen?directLine(chosen.id):null;
 const shown=(kin?book.relations.filter(r=>kin.has(r.source_id)&&kin.has(r.target_id)):book.relations).slice();
 // The list was in the order the relations happened to be entered, so a forebear
 // registered late sat under his own descendants. It reads like the book now:
 // the oldest generation first, and each person's marriage before their issue.
 const whom=new Map(book.persons.map(p=>[p.id,p]));
 const order=new Map(book.persons.map((p,index)=>[p.id,index]));
 const rank=link=>[
  whom.get(link.source_id)?whom.get(link.source_id).generation:999,
  order.has(link.source_id)?order.get(link.source_id):999,
  link.kind==='spouse'?0:1,
  whom.get(link.target_id)?whom.get(link.target_id).generation:999,
  order.has(link.target_id)?order.get(link.target_id):999];
 shown.sort((a,b)=>{
  const x=rank(a),y=rank(b);
  for(let at=0;at<x.length;at++)if(x[at]!==y[at])return x[at]-y[at];
  return 0;
 });
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
$('#print').onclick=()=>{view='book';$('#search').value='';render();stampSheets();window.print();};
// The tree goes on one landscape sheet, shrunk to fit whatever its size, with
// the book's name and the moment of printing above it. The + handles and the
// screen's controls stay off the paper.
// The tree printed as the reader can read it. The first sheet shows the whole
// tree small. The sheets after it are the tree branch by branch at a readable
// size: a sheet holds whole families, each from its forebears at the top down
// to its youngest generation, and the forebears are drawn again on every sheet
// that needs them, so no line is cut off from the ones above it. A branch too
// wide for one sheet is shared out a generation further down, the same way.
// A4, 10mm margin: lying down, or standing where the tree is too tall to read
// lying down.
const TREE_SHEET={width:1047,height:660};
const TREE_SHEET_TALL={width:718,height:990};
const TREE_READABLE=0.75;
// The strip at a sheet's left that holds the 世 of its rows, clear of the cards.
const TREE_GUTTER=64;
function treeBranches(limit){
 const {hostOf}=spouseHosts();
 const byId=new Map(book.persons.map(p=>[p.id,p]));
 const parentsOf=new Map(),childrenOf=new Map();
 for(const r of book.relations){
  if(r.kind!=='parent'||!byId.has(r.source_id)||!byId.has(r.target_id))continue;
  if(!childrenOf.has(r.source_id))childrenOf.set(r.source_id,new Set());
  childrenOf.get(r.source_id).add(r.target_id);
  if(!parentsOf.has(r.target_id))parentsOf.set(r.target_id,new Set());
  parentsOf.get(r.target_id).add(r.source_id);
 }
 const mates=id=>book.relations.filter(r=>r.kind==='spouse'&&(r.source_id===id||r.target_id===id))
  .map(r=>r.source_id===id?r.target_id:r.source_id).filter(other=>byId.has(other));
 const rank=p=>p.gender==='남'?0:p.gender==='여'?2:1;
 const born=p=>/^\d{4}/.test(p.birth_date||'')?p.birth_date:'9999';
 const order=(a,b)=>rank(a)-rank(b)||(born(a)<born(b)?-1:born(a)>born(b)?1:0)||a.id-b.id;
 // A family's children are those of either partner.
 const kidsOf=id=>[...new Set([id,...mates(id)].flatMap(one=>[...(childrenOf.get(one)||[])]))]
  .map(kid=>byId.get(kid)).filter(kid=>kid&&!hostOf.has(kid.id)).sort(order).map(kid=>kid.id);
 const line=(id,into=new Set())=>{
  if(into.has(id))return into;
  into.add(id);mates(id).forEach(mate=>into.add(mate));
  kidsOf(id).forEach(kid=>line(kid,into));
  return into;
 };
 // Drawing the tree to measure it is the slow part, so each set of people is
 // drawn once.
 const widths=new Map();
 const width=ids=>{
  const key=[...ids].sort((a,b)=>a-b).join(',');
  if(!widths.has(key)){renderTree(book.persons.filter(p=>ids.has(p.id)));const canvas=$('.tree-canvas');widths.set(key,canvas?canvas.offsetWidth:0);}
  return widths.get(key);
 };
 const sheets=[];
 // The families under one head, shared out over as few sheets as they fill,
 // each sheet with the head and the forebears above it.
 const share=(heads,branches)=>{
  let group=new Set();
  const flush=()=>{if(group.size){sheets.push(new Set([...heads,...group]));group=new Set();}};
  for(const branch of branches){
   const whole=line(branch);
   if(width(new Set([...heads,...whole]))>limit){
    flush();
    const above=new Set([...heads,branch,...mates(branch)]);
    const kids=kidsOf(branch);
    if(kids.length)share(above,kids);else sheets.push(new Set([...heads,...whole]));
    continue;
   }
   if(group.size&&width(new Set([...heads,...group,...whole]))>limit)flush();
   whole.forEach(id=>group.add(id));
  }
  flush();
 };
 const roots=book.persons.filter(p=>!hostOf.has(p.id)&&!(parentsOf.get(p.id)||new Set()).size)
  .sort((a,b)=>a.generation-b.generation||a.id-b.id).map(p=>p.id);
 share(new Set(),roots);
 return sheets;
}
function treePrintHTML(){
 view='tree';render();
 const full=$('.tree-canvas');
 if(!full)return '';
 const W=full.offsetWidth,H=full.offsetHeight;
 const tall=TREE_SHEET.height/H<TREE_READABLE;
 const sheet=tall?TREE_SHEET_TALL:TREE_SHEET;
 const scale=Math.min(1,sheet.height/H);
 // The whole tree on a standing sheet; a tree wider than it is tall is
 // turned a quarter clockwise to lie along the sheet's length, the eldest
 // generation at the right and the line running on leftward, as a 족보 is
 // read.
 const paper=TREE_SHEET_TALL,turned=W>H;
 const best={paper,turned,scale:turned?Math.min(paper.width/H,paper.height/W,1):Math.min(paper.width/W,paper.height/H,1)};
 const overviewDrawing=full.outerHTML;
 const branches=treeBranches(sheet.width/scale-TREE_GUTTER);
 const parts=branches.map(ids=>{
  renderTree(book.persons.filter(p=>ids.has(p.id)));
  const canvas=$('.tree-canvas');
  const levels=[...canvas.querySelectorAll('.level-label')].map(label=>({y:Number(label.getAttribute('y')),text:label.textContent}));
  return {html:canvas.outerHTML,w:canvas.offsetWidth,h:canvas.offsetHeight,levels};
 });
 render();
 const title=esc(scriptText(book.title))+' 가계도';
 const total=parts.length+1;
 const page=`tree-page${tall?' tall':''}`;
 const head=number=>`<div class="tree-print-head"><strong>${title}</strong><span>${number} / ${total} · <span class="sheet-date"></span></span></div>`;
 const k=best.scale;
 const drawnWhole=`<div class="tree-tile" style="zoom:${k};width:${W}px;height:${H}px">${overviewDrawing}</div>`;
 const overview=`<section class="tree-page${best.paper===TREE_SHEET_TALL?' tall':''}">${head(1)}`
  +(best.turned
   ?`<div class="tree-turned" style="width:${Math.ceil(H*k)}px;height:${Math.ceil(W*k)}px"><div class="tree-turned-inner" style="width:${Math.ceil(W*k)}px;height:${Math.ceil(H*k)}px;transform:translateX(${Math.ceil(H*k)}px) rotate(90deg)">${drawnWhole}</div></div>`
   :drawnWhole)
  +'</section>';
 const pages=parts.map((part,index)=>{
  const labels=part.levels.map(level=>`<span class="tree-tile-level" style="top:${level.y-14}px">${esc(level.text)}</span>`).join('');
  return `<section class="${page}">${head(index+2)}<div class="tree-tile tree-tile-part" style="zoom:${scale};width:${part.w+TREE_GUTTER}px;height:${part.h}px">`
   +`<div class="tree-tile-shift" style="left:${TREE_GUTTER}px;top:0">${part.html}</div>${labels}</div></section>`;
 }).join('');
 return `<div class="tree-print-pages">${overview}${pages}</div>`;
}
$('#printTree').onclick=()=>{
 view='tree';$('#search').value='';
 document.querySelector('.tree-print-pages')?.remove();
 const pages=treePrintHTML();
 if(!pages)return;
 $('#view').insertAdjacentHTML('beforeend',pages);
 stampSheets();
 document.body.classList.add('print-tree');
 window.print();
};
window.addEventListener('afterprint',()=>{
 if(!document.body.classList.contains('print-tree'))return;
 document.body.classList.remove('print-tree');
 document.querySelector('.tree-print-pages')?.remove();
});
$('#sample').onclick=run(async()=>{const button=$('#sample');button.disabled=true;try{const b=await api('/books/sample','POST');await loadBooks(b.id);message('예제 족보 추가 완료 — 金海金氏族譜 (가상 인물 20명)');}finally{button.disabled=false;}});
enter().catch(()=>{});

// ── 스캔 보고 옮겨 적기 ────────────────────────
// A photographed page is read by eye and typed in beside it. Nothing is filed
// until the whole page is confirmed, and the server takes the lines together or
// not at all, so a page is never left half entered.
let scanRowSeq=0,scanZoom=1;
function scanError(text='',field){
 const box=$('#scanError');
 box.classList.remove('success');
 box.textContent=text;
 box.hidden=!text;
 if(field)field.focus();
}
// The notice the page shows for a save sits under the open dialog, which the
// browser keeps above everything; what a line's own save did is said inside it.
function scanNotice(text){
 const box=$('#scanError');
 box.classList.add('success');
 box.textContent=text;
 box.hidden=!text;
}
function scanRowFields(row){
 return name=>row.querySelector(`[name="${name}"]`);
}
// The image window's 한글/한자 switch turns each line's 본관 and 기록 over as
// the person window's does: what is shown may be the reading, what is kept
// is the text as read or typed.
const SCAN_SCRIPT_FIELDS=['bon_gwan','note'];
function scanStored(input){
 return input.dataset.shown!==undefined&&input.value===input.dataset.shown?input.dataset.stored:input.value;
}
function paintScanScript(){
 for(const row of document.querySelectorAll('.scan-row')){
  for(const name of SCAN_SCRIPT_FIELDS){
   const input=scanRowFields(row)(name);
   if(!input)continue;
   if(input.value!==input.dataset.shown)input.dataset.stored=input.value;
   input.value=dialogScriptText(input.dataset.stored||'');
   input.dataset.shown=input.value;
  }
  paintScanMatch(row);
 }
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
  <label>사망일<input name="death_date" type="date" min="0001-01-01" max="${todayISO()}"></label>
  <label>기록<textarea name="note" rows="2" maxlength="10000" autocomplete="off"></textarea></label>
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
 if($('#scanFamily'))added.dataset.family='1';
 for(const native of added.querySelectorAll('input[type="date"]'))upgradeDateInput(native);
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
 ['gender','미상','성별'],['birth_date','','출생일'],['death_date','','사망일'],['note','','기록']];
// A name already in the book is far likelier to be the same person read again
// than a second person of the same name, so the line offers to fill that record
// in rather than quietly making a double.
function scanMatch(row){
 if(!book)return null;
 // A family read off the same spread but not of this book's line is not matched
 // against it: its 金鍾煥 is another man than this book's 金鍾煥.
 if(row.dataset.family==='1'&&scanFamilyTarget()!=='same')return null;
 const get=scanRowFields(row);
 const korean=get('korean_name').value.trim(),hanja=get('hanja_name').value.trim();
 if(!korean&&!hanja)return null;
 const generation=Number(get('generation').value)||0;
 const hits=book.persons.filter(person=>
  (korean&&person.korean_name===korean)||(hanja&&person.hanja_name&&person.hanja_name===hanja));
 if(!hits.length)return null;
 // The same characters are the same person before a shared hangul name is:
 // 金哲純 is not 金澈純, though both are 김철순.
 const exact=hits.filter(person=>hanja&&person.hanja_name===hanja);
 const pool=exact.length?exact:hits;
 return pool.find(person=>person.generation===generation)||pool[0];
}
// Another person with the same hangul name: the characters on the line and on
// record are both there and differ, or the book already holds more than one
// person of that name.
function isNamesake(row,found){
 const hanja=scanRowFields(row)('hanja_name').value.trim();
 if(hanja&&found.hanja_name&&found.hanja_name!==hanja)return true;
 if(otherPerson(row,found))return true;
 return book.persons.filter(person=>person.korean_name===found.korean_name).length>1;
}
// The same name is another person when the page puts the line in another
// 세대, or when it is a clan name alone (崔氏, a wife named by her clan) with
// another 본관: 全州崔氏 and 慶州崔氏 are two women.
function otherPerson(row,found){
 const get=scanRowFields(row);
 const generation=Number(get('generation').value)||0;
 if(generation&&found.generation&&generation!==found.generation)return true;
 const bon=get('bon_gwan').value.trim();
 return clanOnly(row,found)&&!!bon&&!!found.bon_gwan&&bon!==found.bon_gwan;
}
// 崔氏, 최씨: named by the clan alone, as a wife who married in is.
function clanOnly(row,found){
 const get=scanRowFields(row);
 return /[氏씨]$/.test(get('hanja_name').value.trim()||get('korean_name').value.trim()||found.hanja_name||'');
}
// The same rule the server keeps when it updates a note: an item is said
// already when, readings in brackets and spacing aside, the old note holds it.
// A second 父 or 字 is a misreading of the one on record, not news.
// A grave is one place too: the one on record, perhaps set right by hand, is
// kept over another reading of it.
const NOTE_ONE_OF=new Set(['父','夫','字','初名','一名','號','諱','墓','墓는']);
function mergedNote(old,fresh){
 const bare=text=>text.replace(/[\s·]|[(（][^)）]*[)）]/g,'');
 const held=bare(old);
 // 墓는 and 墓 are the one label.
 const head=item=>item.split(/\s+/)[0].replace(/는$/,'');
 const said=new Set(old.split(/\s*·\s*|\n/).map(item=>head(item.trim())).filter(Boolean));
 const extra=fresh.split(/\s*·\s*|\n/).map(item=>item.trim())
  .filter(item=>item&&bare(item)&&!held.includes(bare(item))
   &&!(NOTE_ONE_OF.has(head(item))&&said.has(head(item))));
 return extra.length?old+extra.map(item=>'\n'+item).join(''):old;
}
function paintScanMatch(row){
 const found=scanMatch(row),note=row.querySelector('.scan-match');
 if(!found){
  row.dataset.matchId='';
  row.dataset.fillId='';
  row.classList.remove('filling');
  // A line with a name that is not in the book yet says so, so every line
  // shows whether it adds a person or updates one.
  const get=scanRowFields(row);
  const named=get('korean_name').value.trim()||get('hanja_name').value.trim();
  note.hidden=!named;
  note.innerHTML=named?'<span>족보에 없는 인물</span><button type="button" class="scan-new" data-save-row title="이 줄만 지금 족보에 등록">신규 등록</button>':'';
  if(named)note.querySelector('[data-save-row]').onclick=()=>saveScanRow(row);
  return;
 }
 // A 동명이인 — the same hangul name, other characters — may be someone else
 // altogether, so the line offers both: update the one on record, or enter a
 // new person. Filing the page takes it as the new person the characters say
 // it is, unless 업데이트 was chosen.
 // The very characters of a record are that record, even with a 동명이인 in
 // the book; only other characters make the line a question of who it is.
 const sameHanja=scanRowFields(row)('hanja_name').value.trim()===found.hanja_name;
 // Another 세대, or another 본관 for a clan name alone: likely someone else, so
 // the line asks, and is filed as a person apart unless 업데이트 is chosen.
 const other=otherPerson(row,found);
 // 崔氏 in the same 세대 and 본관 is likely the one on record, yet two brothers'
 // wives can both be 全州崔氏: the line may still be filed apart.
 const namesakes=book.persons.filter(person=>person.korean_name===found.korean_name).length>1||clanOnly(row,found);
 if((isNamesake(row,found)&&!sameHanja)||other){
  row.dataset.matchId=String(found.id);
  row.dataset.replace='';
  row.dataset.shownId='';
  // Filed with the page, a line with other characters is a new person; one
  // with the very characters of a record is that record.
  const same=scanRowFields(row)('hanja_name').value.trim()===found.hanja_name;
  if(row.dataset.namesake!==String(found.id)){row.dataset.namesake=String(found.id);row.dataset.fillId=same&&!other?String(found.id):'';}
  row.classList.remove('filling');
  note.hidden=false;
  const bon=found.bon_gwan&&clanOnly(row,found)?` · ${esc(found.bon_gwan)}`:'';
  note.innerHTML=`<span>동명이인: <strong>${esc(displayName(found,dialogScriptMode).primary)}</strong> · ${found.generation}세대${bon}</span>`
   +'<button type="button" class="scan-new scan-update" data-namesake="update" title="기존 인물의 빈칸·미상만 채움">업데이트</button>'
   +'<button type="button" class="scan-new" data-namesake="apart" title="다른 사람으로 따로 등록">별도 등록</button>';
  note.querySelector('[data-namesake="update"]').onclick=()=>{row.dataset.fillId=String(found.id);saveScanRow(row);};
  note.querySelector('[data-namesake="apart"]').onclick=()=>{row.dataset.fillId='';saveScanRow(row);};
  return;
 }
 // A name already in the book is that person read again, so the line always
 // updates the record; there is no second copy to make.
 row.dataset.matchId=String(found.id);
 row.dataset.fillId=String(found.id);
 row.classList.add('filling');
 // The line shows the record as 업데이트 will leave it, and 업데이트 keeps it
 // as the line shows it, corrections and all. Once, when the line first
 // meets the record: what the book already holds stands in each field, the
 // reading fills what it lacks, and the note has the book's items first and
 // the reading's new ones under them. After that the line is the reader's to
 // correct, and nothing puts back what was taken out.
 const get=scanRowFields(row);
 if(row.dataset.shownId!==String(found.id)){
  row.dataset.shownId=String(found.id);
  for(const [name,blank] of SCAN_FILLABLE){
   if(name==='note'||!found[name]||found[name]===blank)continue;
   get(name).value=found[name];
  }
  get('generation').value=found.generation;
  if(found.note)get('note').value=mergedNote(found.note,get('note').value);
  paintDateBoxes(row);
 }
 row.dataset.replace='1';
 const noteBox=get('note');
 noteBox.rows=Math.min(6,Math.max(2,noteBox.value.split('\n').length));
 const blanks=SCAN_FILLABLE.filter(([name,blank])=>found[name]===blank).map(([,,label])=>label);
 note.hidden=false;
 note.innerHTML=`<span>기존 인물: <strong>${esc(displayName(found,dialogScriptMode).primary)}</strong> · ${found.generation}세대 · `
  +(blanks.length?`빈칸 ${esc(blanks.join('·'))}`:'빈칸 없음')+'</span>'
  +'<button type="button" class="scan-new scan-update" data-save-row title="이 줄만 지금 반영 · 줄에 보이는 그대로 기존 인물에 저장">업데이트</button>'
  +(namesakes?'<button type="button" class="scan-new" data-namesake="apart" title="다른 사람으로 따로 등록">별도 등록</button>':'');
 note.querySelector('[data-save-row]').onclick=()=>{row.dataset.fillId=String(found.id);saveScanRow(row);};
 const apart=note.querySelector('[data-namesake="apart"]');
 if(apart)apart.onclick=()=>{row.dataset.fillId='';saveScanRow(row);};
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
 $('#claudeKeyBox').hidden=true;
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
// ── 다른 가족 ─────────────────────────────
// A spread carries this book's family on from the right-hand page and may start
// another family on the left. That family is set apart under a rule of its own
// and goes, by default, into a book (계통) of its own rather than into this one.
function scanFamilyHTML(people){
 const others=people.filter(person=>person.family===1&&person.hanja_name&&person.generation);
 const top=others.reduce((best,person)=>!best||person.generation<best.generation?person:best,null);
 const books=[...$('#bookSelect').options].filter(option=>Number(option.value)!==book.id)
  .map(option=>`<option value="book:${option.value}">${esc(option.textContent)}에 등록</option>`).join('');
 return `<div class="scan-family" id="scanFamily">
  <strong>여기부터 다른 가족</strong>
  <span>${top?`${top.generation}世 ${esc(top.hanja_name)}부터 · `:''}앞 가족보다 윗세대에서 새로 시작하는 계통 — 이 족보의 가족과 섞지 않음</span>
  <label>등록할 곳<select id="scanFamilyTarget">
   <option value="new">새 족보(계통)로 따로 만들기</option>
   <option value="same">이 족보에 함께 등록</option>
   <option value="skip">등록하지 않음</option>${books}
  </select></label>
 </div>`;
}
function scanFamilyTarget(){
 const select=$('#scanFamilyTarget');
 return select?select.value:'same';
}
function bindScanFamily(){
 const select=$('#scanFamilyTarget');
 if(!select)return;
 select.onchange=()=>{
  for(const row of document.querySelectorAll('.scan-row[data-family="1"]'))paintScanMatch(row);
  $('#scanFamily').classList.toggle('skipped',select.value==='skip');
 };
}
// The given name of the new family's eldest, which the new book is traced from.
function scanFamilyLineage(people){
 const top=people.reduce((best,person)=>!best||person.generation<best.generation?person:best,null);
 if(!top)return '';
 const name=top.hanja_name||top.korean_name;
 const surname=(book.clan_name||'').replace(/[氏씨\s]/g,'')[0];
 return surname&&name.length>2&&name[0]===surname?name.slice(1):name;
}
// One line as a record, or null once the line's own problem has been shown.
function scanLineRecord(line,label){
 const {get}=line;
 if(!line.korean){
  scanError(`${label} — 한글명 없음 · 한자만으로는 등록 불가`,get('korean_name'));
  return null;
 }
 const generation=Number(get('generation').value);
 if(!(generation>=1&&generation<=200)){
  scanError(`${label} — 세대는 1~200`,get('generation'));
  return null;
 }
 const problem=dateProblem(get);
 if(problem){scanError(`${label} — ${problem[1]}`,problem[0]);return null;}
 const fillId=Number(line.row.dataset.fillId)||0;
 return {
  korean_name:line.korean,hanja_name:line.hanja,
  bon_gwan:scanStored(get('bon_gwan')).trim(),generation,
  gender:get('gender').value,birth_date:get('birth_date').value,
  death_date:get('death_date').value,note:scanStored(get('note')).trim(),
  ...(fillId?{id:fillId}:{}),
  ...(fillId&&line.row.dataset.replace==='1'&&line.row.dataset.shownId===String(fillId)?{replace:true}:{}),
  family:line.row.dataset.family==='1'?1:0,
  key:line.row.dataset.key,spouse:line.row.dataset.spouse
 };
}
// 업데이트 and 신규 등록 file their own line at once, into this book. A line of
// another family waits for 모두 등록, which knows where that family goes.
async function saveScanRow(row){
 scanError();
 if(row.dataset.family==='1'&&scanFamilyTarget()!=='same'){
  scanError('다른 가족의 줄 — [모두 등록]에서 정한 곳으로 등록');
  return;
 }
 const get=scanRowFields(row);
 const line={row,get,korean:get('korean_name').value.trim(),hanja:get('hanja_name').value.trim()};
 const record=scanLineRecord(line,line.korean||'이 줄');
 if(!record)return;
 const updating=Boolean(record.id);
 delete record.family;delete record.key;delete record.spouse;
 const button=row.querySelector(updating?'[data-save-row],[data-namesake="update"]':'[data-namesake="apart"],[data-save-row]');
 try{
  const done=await busy(button,'반영 중…',()=>api('/books/'+book.id+'/persons/bulk','POST',{people:[record]}));
  await refresh();
  const fields=(done.filled||[])[0]?.fields||[];
  const labels={korean_name:'한글명',generation:'세대',...Object.fromEntries(SCAN_FILLABLE.map(([name,,label])=>[name,label]))};
  row.classList.add('saved');
  paintScanMatch(row);
  const said=updating
   ?(fields.length?`업데이트 완료 · ${fields.map(name=>labels[name]||name).join('·')} 반영`:'업데이트 완료 · 새로 채울 내용 없음(기존과 같음)')
   :'신규 등록 완료';
  // Said on the line itself, where the button was pressed, and above.
  const status=row.querySelector('.scan-match span');
  if(status)status.innerHTML=`<strong class="scan-done">✓ ${esc(said)}</strong>`;
  scanNotice(`${record.korean_name} — ${said}`);
 }catch(err){scanError(err.message);}
}
$('#scanSave').onclick=async()=>{
 scanError();
 const written=scanLines().filter(line=>line.korean||line.hanja);
 if(!written.length){scanError('입력된 인물 없음');return;}
 const people=[];
 for(const [index,line] of written.entries()){
  const record=scanLineRecord(line,`${index+1}번째 줄`);
  if(!record)return;
  people.push(record);
 }
 const target=scanFamilyTarget();
 const apart=target==='same'?[]:people.filter(person=>person.family===1);
 const here=people.filter(person=>target==='same'||person.family!==1);
 // The key and spouse ride along only as far as the save; the record has no
 // place for them.
 const pairing=new Map(people.map(person=>[person,{key:person.key,spouse:person.spouse}]));
 for(const person of people){delete person.family;delete person.key;delete person.spouse;}
 const fresh=here.filter(person=>!person.id),refined=here.filter(person=>person.id);
 const lineage=scanFamilyLineage(apart);
 const picked=target.startsWith('book:')?$('#bookSelect').querySelector(`option[value="${target.slice(5)}"]`):null;
 const elsewhere=target==='new'?`새 족보 「${book.title} (${lineage} 계통)」`:picked?`「${picked.textContent}」`:'';
 const lines=[];
 if(fresh.length)lines.push(`신규 등록 ${fresh.length}명 — ${fresh.map(person=>person.korean_name).join(', ')}`);
 if(refined.length)lines.push(`업데이트 ${refined.length}명 — ${refined.map(person=>person.korean_name).join(', ')}`);
 const question=`「${book.title}」에 ${here.length}줄 반영\n\n${lines.join('\n')}`
  +(apart.length&&target!=='skip'?`\n\n다른 가족 ${apart.length}명 — ${elsewhere}에 등록\n${apart.map(person=>person.korean_name).join(', ')}`:'')
  +(apart.length&&target==='skip'?`\n\n다른 가족 ${apart.length}명 — 등록하지 않음`:'')
  +(refined.length?'\n\n업데이트 — 빈칸·미상만 채움 · 기재된 값과 세대는 유지':'')
  +'\n\n배우자(配·夫)는 함께 연결 · 부모·자녀 관계는 반영 후 [가족 추가]에서 지정';
 if(!await ask(question,'반영'))return;
 try{
  const done=here.length?await busy($('#scanSave'),'반영 중…',()=>api('/books/'+book.id+'/persons/bulk','POST',{people:here})):{added:[],filled:[]};
  // Each line's record, by its key: a new one takes the next id the save
  // handed back, a line that updated someone keeps theirs.
  const filed=new Map();
  const note=(lines,added,where)=>{
   let next=0;
   for(const person of lines){
    const id=person.id||added[next++];
    const {key}=pairing.get(person);
    if(id&&key!=='')filed.set(key,{id,where});
   }
  };
  note(here,done.added||[],book.id);
  let apartDone=0;
  if(apart.length&&target!=='skip'){
   let other=Number(target.slice(5))||0;
   if(target==='new'){
    // The new book keeps this one's clan, 본관, 파, 권, 쪽 and 시조, and is
    // named for the eldest of the family it holds.
    const keep=['clan_name','bon_gwan','branch_name','volume','page','founder'];
    const values=Object.fromEntries(keep.map(name=>[name,book[name]||'']));
    other=(await api('/books','POST',{...values,title:`${book.title} (${lineage} 계통)`,
     description:`「${book.title}」${book.page?` ${book.page}쪽`:''} 판독에서 나뉜 가족 — ${lineage} 계통`})).id;
   }
   const across=await busy($('#scanSave'),'반영 중…',()=>api('/books/'+other+'/persons/bulk','POST',{people:apart}));
   note(apart,across.added||[],other);
   apartDone=apart.length;
  }
  // Spouses the page names are joined now. A pair split across books, or one of
  // whom was left out, is not; one already joined is left as it is.
  let joined=0;
  for(const [person,{key,spouse}] of pairing){
   if(spouse===''||spouse===undefined||!filed.has(key)||!filed.has(spouse))continue;
   const one=filed.get(key),other=filed.get(spouse);
   if(one.where!==other.where)continue;
   // Only the one who married in names a partner: the line member is the
   // source, the spouse the target.
   try{await api('/relations','POST',{source_id:other.id,target_id:one.id,kind:'spouse'});joined++;}
   catch{}
  }
  $('#scanDialog').close();
  $('#search').value='';
  await loadBooks(book.id);
  const touched=(done.filled||[]).filter(one=>one.fields.length).length;
  const untouched=(done.filled||[]).length-touched;
  message([`신규 등록 ${(done.added||[]).length}명`,
   touched?`업데이트 ${touched}명`:'',
   untouched?`변경 없음 ${untouched}명`:'',
   apartDone?`다른 가족 ${apartDone}명 — ${elsewhere}`:'',
   joined?`배우자 ${joined}쌍 연결`:'',
   '부모·자녀 관계는 [가족 추가]에서 지정'].filter(Boolean).join(' · '));
 }catch(err){scanError(err.message);}
};

// ── 판독 ─────────────────────────────────
// The reader proposes; it never files. Every line it offers lands in the same
// boxes a hand would have typed into, so it is corrected before it counts — and
// a woodblock page will always give it some trouble.
// The book prints a name's hangul beside it — 學龍(학룡) — and a note reads the
// same way: each run of two or more hanja gets its reading in brackets, where
// the reading is known for every character and the page gave none already.
const NOTE_LABELS=new Set(['初名','一名','系子','生父']);
// A line the reader marked with () takes readings only there, each for the
// words just before it, as the page prints them: 陽里(대구시 달성군 유가면 양리)
// covers 大邱市 達城郡 瑜伽面 陽里.
function fillMarkedReadings(line){
 const words=line.split(' ');
 for(let i=0;i<words.length;i++){
  if(!words[i].endsWith('()'))continue;
  const base=words[i].slice(0,-2),group=[base];
  for(let j=i-1;j>=0;j--){
   const word=words[j];
   if(!/^[\u3400-\u9fff\uf900-\ufaff]+$/.test(word)||/^[〇一二三四五六七八九十百千]+$/.test(word)||NOTE_LABELS.has(word))break;
   group.unshift(word);
  }
  const reading=base?readingOf(group.join(' ')):'';
  words[i]=base+(reading&&/^[가-힣 ]+$/.test(reading)?`(${reading})`:'');
 }
 return words.filter(Boolean).join(' ');
}
function withReadings(text){
 if(text.includes('()'))return text.split('\n').map(line=>line.includes('()')?fillMarkedReadings(line):withReadings(line)).join('\n');
 return text.replace(/[㐀-鿿豈-﫿]{2,}(?![(（][가-힣])/g,run=>{
  if(NOTE_LABELS.has(run))return run;
  // A lot number (一六五一) is read as figures, not as a word.
  if(/^[〇一二三四五六七八九十百千]+$/.test(run))return run;
  // 忌는 九月十九日: a day is written in figures too, with no reading after it.
  if(/^[〇一二三四五六七八九十]+月[〇一二三四五六七八九十]+日$/.test(run))return run;
  const reading=readingOf(run);
  return reading&&/^[가-힣]+$/.test(reading)?`${run}(${reading})`:run;
 });
}
function scanFillRow(row,person,generation){
 const get=scanRowFields(row);
 get('generation').value=generation;
 get('hanja_name').value=person.hanja_name||'';
 // The page gives the characters; the reading follows from them — unless the
 // reader could read the hangul the page prints beside the name itself.
 get('korean_name').value=person.korean_name||readingOf(person.hanja_name||'')||'';
 // Someone who married in (a 配 wife, a daughter's 夫) is of another family:
 // the book's own 본관 is not theirs, so only what the page gives stands.
 get('bon_gwan').value=person.bon_gwan||(person.married_in?'':(book?book.bon_gwan||'':''));
 get('gender').value=person.gender||'미상';
 get('birth_date').value=person.birth_date||'';
 get('death_date').value=person.death_date||'';
 paintDateBoxes(row);
 // 字·初名·墓, a daughter's husband, a day remembered without a year.
 get('note').value=withReadings(person.note||'');
 get('note').rows=Math.min(6,Math.max(2,get('note').value.split('\n').length));
 // A year and its 간지 that disagree mean one of the two was misread.
 row.classList.toggle('doubted',person.ganji_agrees===false);
 // Who this line married, as the page says (配 after a son, 夫 in a daughter's
 // entry), so the two are joined when the page is filed.
 row.dataset.key=person.key??'';
 row.dataset.spouse=person.spouse??'';
 row.title=person.ganji_agrees===false?'간지 불일치 — 원본 대조 필요':'';
 paintScanMatch(row);
}
// Two readers fill the same lines: the one on this computer, which knows hanja
// only, and Claude, which reads the hangul beside every name and the notes too
// but needs the photo sent to Anthropic and a key to do it.
$('#scanRead').onclick=()=>readScan('',$('#scanRead'),'판독 중…');
$('#scanReadClaude').onclick=async()=>{
 scanError();
 let status;
 try{status=await api('/claude');}catch(err){scanError(err.message);return;}
 if(!status.available){scanError('Claude 판독 꾸러미 미설치 — start.bat을 다시 실행해 주세요');return;}
 if(!status.configured){
  $('#claudeKeyBox').hidden=false;
  $('#claudeKey').focus();
  scanError('Claude API 키 입력 필요 — 한 번만 넣으면 됩니다');
  return;
 }
 await readScan('claude',$('#scanReadClaude'),'Claude 판독 중… (1~3분)');
};
$('#claudeKeySave').onclick=async()=>{
 scanError();
 const key=$('#claudeKey').value.trim();
 if(!key){scanError('API 키 입력 필요',$('#claudeKey'));return;}
 try{
  await busy($('#claudeKeySave'),'확인 중…',()=>api('/claude/key','PUT',{key}));
 }catch(err){scanError(err.message,$('#claudeKey'));return;}
 $('#claudeKey').value='';
 $('#claudeKeyBox').hidden=true;
 message('Claude API 키 저장 완료 — [Claude로 판독]을 다시 누르세요');
};
async function readScan(engine,button,waiting){
 scanError();
 const id=Number($('#scanPick').value);
 if(!id){scanError('족보 이미지 없음 — 먼저 올리기');return;}
 let found;
 try{
  found=await busy(button,waiting,()=>api('/scans/'+id+'/read'+(engine?'?engine='+engine:''),'POST'));
 }catch(err){
  if(engine==='claude'&&/키/.test(err.message))$('#claudeKeyBox').hidden=false;
  scanError(err.message);
  return;
 }
 const people=found.people||[];
 const note=$('#scanReadNote');
 note.hidden=false;
 // The page number as the photo prints it; blank when it could not be read,
 // and open to correction either way.
 $('#scanPage').value=found.page||'';
 $('#scanPageBox').hidden=false;
 if(!people.length){
  note.textContent='판독 결과 없음';
  return;
 }
 // Where the margin names each band's generation (二十六世), the page says it;
 // otherwise the bands count on from the first one found below, or from 1,
 // and each line's own 세대 box is there to set it right.
 let first=1;
 const labelled=people.some(person=>person.generation);
 // Where the margin's 世 could not be read, a son headed by his forebears
 // (芝淑 相錫 正煥 over 澈純) still tells it: his father 正煥 is in the book at
 // 30世, so the son's band is 31世 and the bands above and below follow.
 if(!labelled){
  const surname=clanSurname().hanja;
  for(const person of people){
   const father=(person.forebears||[]).slice(-1)[0];
   if(!father)continue;
   const known=book.persons.find(one=>one.hanja_name===surname+father||one.hanja_name===father);
   if(known){first=known.generation+1-(person.band||0);break;}
  }
 }
 $('#scanList').innerHTML='';
 scanRowSeq=0;
 // Each generation the page holds is headed in the list, with how many it has,
 // so a later one is not lost below the fold of a long first one.
 const generationOf=person=>Math.min(200,person.generation||first+(person.band||0));
 const counts=new Map();
 for(const person of people)counts.set(generationOf(person),(counts.get(generationOf(person))||0)+1);
 let heading=null;
 for(const person of people){
  if(person.family===1&&!$('#scanFamily'))$('#scanList').insertAdjacentHTML('beforeend',scanFamilyHTML(people));
  if(generationOf(person)!==heading){
   heading=generationOf(person);
   $('#scanList').insertAdjacentHTML('beforeend',`<p class="scan-generation">${heading}세 · ${counts.get(heading)}명</p>`);
  }
  const row=scanAddRow();
  scanFillRow(row,person,generationOf(person));
 }
 bindScanFamily();
 // Just the count; the lines say the rest.
 note.textContent=(found.engine==='claude'?'Claude ':'')+`판독 ${people.length}명`;
 if(dialogScriptMode==='hangul')paintScanScript();
 paintScanCount();
}

// ── 혼인과 자녀 ─────────────────────────────────────
// A child recorded under one parent alone belongs to that parent's marriage as
// soon as there is one, so the first spouse is entered as a parent too. A second
// marriage is a question the record cannot answer by itself — which children are
// of which — so it is asked rather than guessed.
function childrenOf(id){
 return book.relations.filter(r=>r.kind==='parent'&&r.source_id===id)
  .map(r=>book.persons.find(p=>p.id===r.target_id)).filter(Boolean);
}
function otherParentsOf(childId,exceptId){
 return book.relations.filter(r=>r.kind==='parent'&&r.target_id===childId&&r.source_id!==exceptId)
  .map(r=>book.persons.find(p=>p.id===r.source_id)).filter(Boolean);
}
let marriageState=null;
async function settleMarriage(kind,anchorId,spouseId){
 if(kind!=='spouse')return '';
 await refresh();
 const anchor=book.persons.find(p=>p.id===anchorId);
 const spouse=book.persons.find(p=>p.id===spouseId);
 if(!anchor||!spouse)return '';
 const spouses=spousesOf(anchorId);
 if(spouses.length<=1&&spousesOf(spouseId).length<=1){
  // The first marriage takes in the children already standing under one parent,
  // whichever of the two they were standing under.
  let taken=0;
  for(const [parent,partner] of [[anchorId,spouseId],[spouseId,anchorId]]){
   for(const child of childrenOf(parent).filter(one=>!otherParentsOf(one.id,parent).length)){
    try{await api('/relations','POST',{source_id:partner,target_id:child.id,kind:'parent'});taken++;}
    catch(err){if(!/이미 등록된 관계/.test(err.message))throw err;}
   }
   await refresh();
  }
  return taken?` 자녀 ${taken}명도 두 분의 자녀로 함께 기록`:'';
 }
 openMarriageDialog(anchorId,spouseId);
 return '';
}
function openMarriageDialog(anchorId,spouseId){
 const anchor=book.persons.find(p=>p.id===anchorId);
 const spouse=book.persons.find(p=>p.id===spouseId);
 if(!anchor||!spouse)return;
 marriageState={anchorId,spouseId,mates:spousesOf(anchorId).map(m=>m.id)};
 const name=p=>esc(displayName(p,dialogScriptMode).primary);
 $('#marriageText').innerHTML=`<strong>${name(anchor)}</strong> · <strong>${name(spouse)}</strong> 혼인 · `
  +`${name(anchor)}의 배우자 ${marriageState.mates.length}명 — 자녀가 어느 혼인 소생인지 기록 필요`;
 const children=childrenOf(anchorId);
 $('#marriageChildren').innerHTML=children.length?children.map(child=>{
  const others=otherParentsOf(child.id,anchorId).filter(p=>p.id!==spouseId);
  const here=otherParentsOf(child.id,anchorId).some(p=>p.id===spouseId);
  const where=here?`이 혼인`:(others.length?others.map(p=>esc(displayName(p,dialogScriptMode).primary)).join('·'):'미정');
  return `<label class="marriage-child"><input type="checkbox" value="${child.id}"${here?' disabled':''}>`
   +`<span><strong>${name(child)}</strong> · ${child.generation}세대</span>`
   +`<em>${esc(where)}</em></label>`;
 }).join(''):'<p class="muted">기준 인물에게 기록된 자녀 없음</p>';
 $('#marriageMove').disabled=!children.length;
 if(!$('#marriageDialog').open)$('#marriageDialog').showModal();
}
$('#closeMarriage').onclick=()=>$('#marriageDialog').close();
$('#marriageSkip').onclick=()=>$('#marriageDialog').close();
$('#marriageNew').onclick=()=>{
 const {anchorId,spouseId}=marriageState||{};
 $('#marriageDialog').close();
 if(!anchorId)return;
 addRelative('child',anchorId);
 // The new child belongs to the marriage just made, so that is the one set.
 if(pendingRelative)pendingRelative.mateId=spouseId;
 const mate=$('#relativeMate');
 if(mate)mate.value=String(spouseId);
};
$('#marriageMove').onclick=async()=>{
 const picked=[...document.querySelectorAll('#marriageChildren input:checked')].map(box=>Number(box.value));
 if(!picked.length){message('옮길 자녀 선택 필요','error');return;}
 const {anchorId,spouseId,mates}=marriageState;
 const names=picked.map(id=>displayName(book.persons.find(p=>p.id===id)).primary).join(', ');
 const spouse=displayName(book.persons.find(p=>p.id===spouseId)).primary;
 if(!await ask(`${names} — ${spouse}과(와)의 혼인 소생으로 옮김\n\n다른 배우자와의 부모 연결은 끊김 · 기준 인물은 그대로 부모`,'옮기기'))return;
 try{
  await busy($('#marriageMove'),'옮기는 중…',async()=>{
   for(const childId of picked){
    // Only the anchor's other marriages are let go of; a parent recorded outside
    // them is nothing to do with this choice.
    for(const link of book.relations.filter(r=>r.kind==='parent'&&r.target_id===childId
      &&r.source_id!==anchorId&&r.source_id!==spouseId&&mates.includes(r.source_id)))
     await api('/relations/'+link.id,'DELETE');
    try{await api('/relations','POST',{source_id:spouseId,target_id:childId,kind:'parent'});}
    catch(err){if(!/이미 등록된 관계/.test(err.message))throw err;}
   }
  });
  $('#marriageDialog').close();
  await refresh();
  message(`${names} — ${spouse}과(와)의 혼인 소생으로 기록`);
 }catch(err){message(err.message,'error');}
};
