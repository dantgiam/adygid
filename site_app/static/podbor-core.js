/* АдыГид · podbor-core v2 — чистая логика подбора (без DOM). Готова к переносу в site.js / FastAPI.
   Экспорт: UMD → window.PodborCore в браузере, module.exports в Node (тесты).
   Все расстояния и времена дороги — ОЦЕНКИ по координатам (≈), не навигация. */
(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory();else root.PodborCore=factory()})(typeof self!=='undefined'?self:this,function(){
'use strict';
const VERSION='podbor-core 2.0 · 2026-11-09';
const AREAS={maykop:['Майкоп',44.605,40.100],tulsky:['Тульский и Цветочный',44.490,40.160],khadzhokh:['Каменномостский (Хаджох)',44.295,40.185],dakhovskaya:['Даховская',44.235,40.210],lago:['Лаго-Наки',44.085,40.015],valley:['Хамышки и Гранитный каньон',44.125,40.110],guzeripl:['Гузерипль',44.000,40.136],sakhray:['Сахрай',44.174,40.300],pobeda:['Победа',44.288,40.330],novosvobodnaya:['Новосвободная',44.417,40.346],north:['Гончарка (равнина)',44.807,39.947],other:['Адыгея',null,null]};
const PARAMS={ // все числа — оценки/гипотезы, вынесены в данные для правки
  speedKmh:50, mountainFactor:1.3, plainFactor:1.2, plainLat:44.45, parkingMin:10, maxHopMin:40, hopWeight:1.5, otherAreaPenalty:15,
  paceBudget:{calm:330,balanced:450,active:570,any:450},          // мин: ≈5,5 / 7,5 / 9,5 / 7,5 ч
  daylight:{winter:540,summer:840,any:660},                        // ≈ светлое время, мин
  paceCap:{calm:3,balanced:4,active:5,any:4},                      // потолок точек в день
  smallKidsFactor:0.8, buffer:1.15, alsoShare:0.25, fewThreshold:4, secondaryCap:150,
  interestBase:1000, interestFraction:300, oftenKeepBest:2, oftenBestBonus:70
};
const INTERESTS=['views','water','culture','thermal','familyfun','caves'];
function km(a,b,c,d){const R=6371,p=x=>x*Math.PI/180,dl=p(c-a),dn=p(d-b),h=Math.sin(dl/2)**2+Math.cos(p(a))*Math.cos(p(c))*Math.sin(dn/2)**2;return 2*R*Math.asin(Math.sqrt(h))}
function point(x){if(!x)return null;if(Array.isArray(x))return x[0]==null?null:{lat:x[0],lon:x[1]};return x.lat==null?null:{lat:x.lat,lon:x.lon}}
function baseAnchor(base){const a=AREAS[base];return a&&a[1]!=null?{lat:a[1],lon:a[2]}:null}
/* Дорога ≈ прямая × горный коэффициент / средняя скорость + парковка. Округление до 5 мин. */
function driveMin(from,to){const a=point(from),b=point(to);if(!a||!b)return null;const d=km(a.lat,a.lon,b.lat,b.lon);if(d<0.4)return 0;const f=(a.lat>PARAMS.plainLat&&b.lat>PARAMS.plainLat)?PARAMS.plainFactor:PARAMS.mountainFactor;return Math.max(5,Math.round((d*f/PARAMS.speedKmh*60+PARAMS.parkingMin)/5)*5)}
function smallKids(a){return a.party==='small'||(['small','family'].includes(a.party)&&['tiny','preschool'].includes(a.childage))}
function interestCount(x,interests){return (interests||[]).filter(t=>x.tags.includes(t)).length}
/* Жёсткие ограничения: безопасность/сезон/явные исключения. Возвращает список причин (пусто = подходит). */
function exclusionReasons(x,a){a=a||{};const r=[];const d=x.difficulty;
  if(a.season==='winter'){if(x.winter_ok==='no')r.push('ноябрь–декабрь: в карточке «только лето» или сухое время');else if(x.winter_ok==='unknown'&&['hard','extreme'].includes(d))r.push('ноябрь–декабрь: сложный подход, зимой не подтверждён')}
  if(a.season==='summer'&&false)r.push('');
  if(smallKids(a)&&(!x.kid||d!=='easy'||x.visit.typ>300))r.push('маленькие дети: нужен лёгкий формат с отметкой «с детьми»');
  else if(a.party==='family'&&(!x.kid||['hard','extreme'].includes(d)))r.push('семья с детьми: нет отметки «с детьми» или высокая сложность');
  if(a.pace==='calm'&&['medium','hard','extreme'].includes(d))r.push('спокойный темп: в карточке нагрузка выше');
  if(a.pace==='balanced'&&['hard','extreme'].includes(d))r.push('сбалансированный темп: в карточке сложный уровень');
  if(a.exclude==='thermal'&&x.tags.includes('thermal'))r.push('выбрано «Без терм»');
  if(a.exclude==='culture'&&x.tags.includes('culture'))r.push('выбрано «Без музеев и культурной программы»');
  if(a.exclude==='cable'&&((x.type==='place'&&x.id===48)||(x.stops||[]).includes(48)))r.push('выбрано «Без канатной дороги»');
  if(a.walking==='stepfree'&&x.stroller==='no')r.push('коляска / без ступеней: известны ступени или тропа');
  if(a.walking==='short'&&x.visit.typ>(x.type==='place'?90:180))r.push('короткие посещения: по времени дольше выбранного формата');
  if(a.distance==='local'&&AREAS[a.base]&&a.base!=='other'&&x.area!==a.base)r.push('выбран только район базы');
  if(a.rain==='indoor'&&!x.indoor)r.push('выбран музейный день под крышей');
  return r}
/* Вторичная оценка (≤ secondaryCap): база, состав, темп, сезон, опыт, свежесть. Никогда не перекрывает интересы. */
function secondary(x,a,o){a=a||{};o=o||{};let s=0;const parts={};const add=(k,v)=>{if(v){parts[k]=(parts[k]||0)+v;s+=v}};const t=x.tags,d=x.difficulty;
  const b=baseAnchor(a.base);if(b){const m=driveMin(b,x);if(m!=null)add('близко к базе',Math.max(0,Math.round(40-m/3)))}
  if(a.party==='family'&&t.includes('familyfun'))add('семейное',12);if(smallKids(a)&&x.stroller==='maybe')add('удобный подход',8);
  if(a.party==='couple'&&(t.includes('views')||t.includes('thermal')))add('вдвоём',6);if(a.party==='solo'&&x.type==='route')add('маршрут',6);
  if(a.pace==='calm'&&d==='easy')add('темп',10);if(a.pace==='active'&&['medium','hard'].includes(d))add('темп',10);if(a.pace==='active'&&x.type==='route')add('темп',6);
  if(a.season==='winter'){if(t.includes('thermal')||t.includes('culture')||x.indoor)add('сезон',8);if(x.winter_ok==='yes')add('сезон',6)}
  if(a.season==='summer'&&(t.includes('water')||t.includes('views')))add('сезон',8);
  if(a.duration==='one'&&x.visit.typ<=180)add('длительность',6);if(a.duration==='short'&&x.type==='route')add('длительность',5);
  const ex=a.been;if(ex==='first'&&x.editorial==='best')add('лучшее Адыгеи',35);
  if(ex==='some'){if(x.editorial==='best')add('лучшее Адыгеи',10);if(x.editorial==='unusual')add('необычное',25)}
  if(ex==='often'){if(x.editorial==='best')add('уже известное',-15);if(x.editorial==='unusual')add('необычное',45)}
  if(a.childage==='school'&&t.includes('familyfun'))add('возраст детей',8);if(a.childage==='teen'&&(t.includes('water')||t.includes('views')))add('возраст детей',4);
  if(a.walking==='short'&&x.visit.typ<=60)add('короткое',8);if(a.walking==='long'&&x.visit.typ>=180)add('длинное',6);if(a.rain==='backup'&&x.indoor)add('под крышей',6);
  if(x.checked)add('проверено',2);if(x.photoUrl||x.image)add('фото',1);
  if(o.lastKey&&o.lastAnswer!=='any'){const n=lastAnswerBoost(x,a,o.lastKey);if(n)add('последний ответ',n)}
  s=Math.max(-40,Math.min(PARAMS.secondaryCap,s));return {score:s,parts}}
function lastAnswerBoost(x,a,k){const t=x.tags;if(k==='season')return (a.season==='winter'&&(t.includes('thermal')||t.includes('culture')))||(a.season==='summer'&&(t.includes('water')||t.includes('views')))?6:0;if(k==='party')return a.party==='family'&&t.includes('familyfun')?6:0;if(k==='pace')return a.pace==='calm'&&(t.includes('culture')||t.includes('thermal'))?4:0;if(k==='been')return x.editorial==='unusual'&&a.been!=='first'?6:0;return 0}
/* Итоговая оценка: интерес — «старший разряд». Любая совпавшая карточка > любой несовпавшей. */
function score(x,a,o){a=a||{};const ints=a.interests||[];const c=interestCount(x,ints);const prim=ints.length&&c?PARAMS.interestBase+Math.round(PARAMS.interestFraction*c/ints.length):0;const sec=secondary(x,a,o);return {total:prim+sec.score,primary:prim,match:c,secondary:sec.score,parts:sec.parts}}
function rotate(list,phase){if(!list.length)return list;const k=phase%list.length;return list.slice(k).concat(list.slice(0,k))}
function sortWithReshuffle(list,phase){const groups=new Map();list.forEach(z=>{const key=z.s.primary*10+Math.floor(z.s.secondary/8);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(z)});let out=[];[...groups.keys()].sort((p,q)=>q-p).forEach(k=>{const g=groups.get(k).sort((p,q)=>q.s.total-p.s.total||p.x.id-q.x.id);out=out.concat(rotate(g,phase||0))});return out}
function diversify(list){const out=[],counts={},rest=list.slice();while(rest.length){let best=0,bv=-1e9;for(let i=0;i<rest.length;i++){const z=rest[i];const pen=Math.min(24,8*(counts[z.x.area]||0))+(out.some(y=>(y.x.type==='route'&&z.x.type==='place'&&y.x.stops.includes(z.x.id))||(z.x.type==='route'&&y.x.type==='place'&&z.x.stops.includes(y.x.id)))?6:0);const v=z.s.primary+z.s.secondary-pen-i*0.001;if(v>bv){bv=v;best=i}}const z=rest.splice(best,1)[0];counts[z.x.area]=(counts[z.x.area]||0)+1;out.push(z)}return out}
/* Главная функция ранжирования. seen — Set ключей «type:id» («Уже был тут»). */
function rankAll(items,a,o){a=a||{};o=o||{};const seen=o.seen||new Set();const ints=a.interests||[];const ok=[],excluded=[],hidden=[];
  for(const x of items){const key=x.type+':'+x.id;if(seen.has(key)){hidden.push(x);continue}const r=exclusionReasons(x,a);if(r.length)excluded.push({x,reasons:r});else ok.push({x,s:score(x,a,o)})}
  // «Часто бываю»: 2 самых сильных «лучших» остаются лакомыми, остальные лучшие чуть ниже
  if(a.been==='often'){ok.filter(z=>z.x.editorial==='best'&&(!ints.length||z.s.match)).sort((p,q)=>q.s.total-p.s.total).slice(0,PARAMS.oftenKeepBest).forEach(b=>{b.s.total+=PARAMS.oftenBestBonus;b.s.secondary+=PARAMS.oftenBestBonus;b.s.parts['лакомое из лучших']=PARAMS.oftenBestBonus})}
  const matchList=ints.length?ok.filter(z=>z.s.match>0):ok, other=ints.length?ok.filter(z=>z.s.match===0):[];
  const main=diversify(sortWithReshuffle(matchList,o.phase)), rest=diversify(sortWithReshuffle(other,o.phase));
  const alsoMax=Math.floor(main.length*PARAMS.alsoShare/(1-PARAMS.alsoShare)); // also/(main+also) ≤ 25%
  const also=rest.slice(0,alsoMax);
  const mode=!ints.length?'all':main.length===0?'none':main.length<PARAMS.fewThreshold?'few':'ok';
  return {main,also,alternatives:rest.slice(0,4),excluded,hidden,mode,interests:ints}}
function daysFor(a,override){if(override)return override;return {one:1,short:3,long:4}[a.duration]||1}
function dayBudget(a){const pace=PARAMS.paceBudget[a.pace]?a.pace:'any';const dl=PARAMS.daylight[a.season]||PARAMS.daylight.any;let b=Math.min(PARAMS.paceBudget[pace],dl-30);if(smallKids(a))b=Math.round(b*PARAMS.smallKidsFactor);return {budget:b,limit:Math.round(b/PARAMS.buffer),cap:PARAMS.paceCap[pace],daylight:dl}}
function overlaps(x,used){if(used.has(x.type+':'+x.id))return true;if(x.type==='route')return x.stops.some(id=>used.has('place:'+id));if(x.type==='place')return used.has('stop:'+x.id);return false}
function markUsed(x,used){used.add(x.type+':'+x.id);if(x.type==='route')x.stops.forEach(id=>{used.add('stop:'+id);used.add('place:'+id)})}
/* План по дням: жадная сборка в бюджет времени с запасом 15%, проверяется весь день целиком. */
function planDays(ranked,a,o){a=a||{};o=o||{};const n=daysFor(a,o.days);const B=dayBudget(a);const base=baseAnchor(a.base);const used=new Set(),areaUse={},days=[];
  const pools=[ranked.main.map(z=>({...z,kind:'main'})),ranked.also.map(z=>({...z,kind:'also'}))];
  for(let d=0;d<n;d++){let seed=null,sv=-1e9;for(const pool of pools){for(const z of pool){if(overlaps(z.x,used)||!point(z.x))continue;const toBase=base?driveMin(base,z.x):0;if(base&&toBase>150)continue;const v=z.s.total-60*(areaUse[z.x.area]||0)-(base?toBase/2:0);if(v>sv){sv=v;seed=z}}if(seed)break}
    if(!seed){days.push({empty:true,stops:[]});continue}
    const stops=[];const startDrive=base?driveMin(base,seed.x):null;let total=(startDrive||0)+seed.x.visit.typ;stops.push({x:seed.x,s:seed.s,kind:seed.kind,drive:startDrive,visit:seed.x.visit});markUsed(seed.x,used);
    const long=seed.x.visit.typ+(startDrive||0)*2>B.limit;
    while(!long&&stops.length<B.cap){const last=stops[stops.length-1].x;let pick=null,pv=-1e9;
      for(const pool of pools){for(const z of pool){if(overlaps(z.x,used)||!point(z.x))continue;const hop=driveMin(last,z.x);if(hop==null||hop>PARAMS.maxHopMin)continue;const back=base?driveMin(z.x,base):0;if(total+hop+z.x.visit.typ+back>B.limit)continue;const v=z.s.total-PARAMS.hopWeight*hop-(z.x.area!==seed.x.area?PARAMS.otherAreaPenalty:0);if(v>pv){pv=v;pick={...z,hop}}}if(pick)break}
      if(!pick)break;stops.push({x:pick.x,s:pick.s,kind:pick.kind,drive:pick.hop,visit:pick.x.visit});total+=pick.hop+pick.x.visit.typ;markUsed(pick.x,used)}
    const ret=base?driveMin(stops[stops.length-1].x,base):null;total+=ret||0;areaUse[seed.x.area]=(areaUse[seed.x.area]||0)+1;
    const drive=stops.reduce((s,z)=>s+(z.drive||0),0)+(ret||0);
    days.push({area:seed.x.area,stops,startDrive,returnDrive:ret,totalMin:total,driveMin:drive,visitMin:total-drive,budget:B.budget,limit:B.limit,daylight:B.daylight,long,estimated:stops.some(z=>z.visit.source==='estimate')})}
  return days}
function fmtMin(m){if(m==null)return '';m=Math.round(m/5)*5;const h=Math.floor(m/60),r=m%60;return h?(h+' ч'+(r?' '+r+' мин':'')):(r+' мин')}
function fmtRange(v){if(v.source==='card'||v.min===v.max)return fmtMin(v.typ);if(v.min%60===0&&v.max%60===0)return (v.min/60)+'–'+(v.max/60)+' ч';if(v.max<=60)return v.min+'–'+v.max+' мин';return fmtMin(v.min)+' – '+fmtMin(v.max)}
function contextId(){const al='abcdefghjkmnpqrstuvwxyz23456789';let s='';const c=(typeof crypto!=='undefined'&&crypto.getRandomValues)?crypto.getRandomValues(new Uint8Array(8)):Array.from({length:8},()=>Math.floor(Math.random()*256));for(const b of c)s+=al[b%al.length];return s}
/* Событие для серверного журнала (гибрид): без IP, без ID Метрики, без свободного текста. */
function makeEvent(session,type,f){f=f||{};return {event_id:contextId(),anonymous_session_id:session,event_type:type,ts:new Date().toISOString(),question_id:f.question_id||null,answer_code:f.answer_code==null?null:String(f.answer_code),skipped:!!f.skipped,item_key:f.item_key||null,plan_id:f.plan_id||null,algorithm_version:VERSION}}
return {VERSION,AREAS,PARAMS,INTERESTS,km,driveMin,baseAnchor,exclusionReasons,secondary,score,rankAll,planDays,dayBudget,daysFor,fmtMin,fmtRange,contextId,makeEvent,smallKids,interestCount}
});
