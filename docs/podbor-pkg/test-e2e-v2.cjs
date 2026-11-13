// E2E (headless Chrome): node test-e2e-v2.cjs  → qa-v2/*.png + QA-v2-e2e.json
const puppeteer=require('/home/box/tools/pptr/node_modules/puppeteer-core');const assert=require('assert');const fs=require('fs');
const URL='file://'+__dirname+'/DEMO-trip-selector.html';const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{let STEP="";const b=await puppeteer.launch({executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});const out={checks:[],errors:[]};
 const ok=(c,m)=>{assert(c,m);out.checks.push(m)};
 for(const [vw,vh,tag] of [[1280,900,'desktop'],[390,844,'mobile']]){const p=await b.newPage();await p.setViewport({width:vw,height:vh,deviceScaleFactor:1});p.on('pageerror',e=>out.errors.push(tag+': '+e.message));p.on('console',m=>{if(m.type()==='error')out.errors.push(tag+' console: '+m.text())});
  await p.goto(URL,{waitUntil:'load'});
  const noOverflow=async(step)=>{const w=await p.evaluate(()=>document.documentElement.scrollWidth-innerWidth);ok(w<=1,tag+' no horizontal overflow @'+step+' ('+w+')')};
  ok(await p.$eval('#pwidget',e=>e.innerText.includes('Хотите, подберём для вас маршрут поездки абсолютно бесплатно, прямо на сайте')&&e.innerText.includes('под ваши интересы, с учётом времени пребывания')),tag+' widget exact text');
  await noOverflow('home');await p.screenshot({path:`qa-v2/${tag}-01-home-widget.png`});
  // click season chip in widget → podbor + overlay
  await p.click('[data-act="widget"][data-season="winter"]');await sleep(300);
  ok(await p.$eval('#reaction',e=>e.classList.contains('show')),tag+' analysis overlay shows on answer');await p.screenshot({path:`qa-v2/${tag}-02-overlay.png`});await sleep(2000);
  ok(await p.$eval('#wizard',e=>e.innerText.includes('Вопрос 2 из 7')),tag+' widget chip answered Q1 → Q2 of 7');
  const ans=async(q,a)=>{await p.click(`[data-act="choose"][data-q="${q}"][data-answer="${a}"]`);await sleep(2150)};
  await ans('duration','short');await ans('base','dakhovskaya');await ans('party','family');
  ok(await p.$eval('#wizard',e=>e.innerText.includes('Вы уже бывали в Адыгее?')&&e.innerText.includes('Пропустить вопрос')),tag+' «бывали» question with skip');await p.screenshot({path:`qa-v2/${tag}-03-been-question.png`});
  await p.click('[data-act="choose"][data-q="been"][data-answer="some"]');await sleep(400);const rt=await p.$eval('#reactiontext',e=>e.textContent);ok(rt.length>5,tag+' been reaction: '+rt);await sleep(1800);
  await ans('pace','balanced');
  await ans('interests','water');
  const live=await p.evaluate(()=>{const m=[...document.querySelectorAll('#main-cards .card')].length,a=[...document.querySelectorAll('#also-cards .card')].length;return {m,a,txt:document.getElementById('results').innerText}});
  ok(live.m>0,tag+' interest cards shown ('+live.m+')');ok(live.txt.includes('Ещё может понравиться')||live.a===0,tag+' also block labelled');
  await noOverflow('live');await p.screenshot({path:`qa-v2/${tag}-04-live-results.png`,fullPage:false});
  await p.click('[data-act="finish"]');await sleep(2200);ok(await p.$('#confirm-plan')!==null,tag+' editable summary shown');await p.screenshot({path:`qa-v2/${tag}-05-summary.png`});
  await p.click('#confirm-plan');await sleep(2200);
  const fin=await p.evaluate(()=>({days:document.querySelectorAll('.day').length,rows:document.querySelectorAll('.tlrow').length,txt:document.getElementById('results').innerText}));
  ok(fin.days===3,tag+' 3 days for 2–3 дня');ok(fin.txt.includes('≈')&&fin.txt.includes('оценка'),tag+' times marked ≈ / оценка');ok(fin.txt.includes('уточняем, скоро появится :)'),tag+' unknown cost wording');
  await noOverflow('final');await p.screenshot({path:`qa-v2/${tag}-06-plan.png`,fullPage:true});
  // «Уже был тут» replaces a row
  const firstKey=await p.$eval('.tlrow',e=>e.dataset.type+e.dataset.id);await p.click('.tlrow [data-act="seen"]');await sleep(800);
  ok(await p.evaluate(k=>![...document.querySelectorAll('.tlrow')].some(e=>e.dataset.type+e.dataset.id===k),firstKey),tag+' «Уже был тут» removes item');ok(await p.evaluate(()=>document.body.innerText.includes('Скрыто как «уже был»: 1')),tag+' hidden counter + undo');
  // feedback footer
  await p.click('[data-act="pv"][data-v="down"]');await sleep(200);await p.click('[data-act="reason"][data-r="dense"]');await sleep(200);
  ok(await p.evaluate(()=>!!document.querySelector('[data-act="fix"][data-f="calm"]')),tag+' 👎 → reasons → «пересобрать спокойнее»');
  await p.click('[data-act="density"][data-d="high"]');await p.click('[data-act="bot"]');await sleep(300);
  ok(await p.evaluate(()=>document.querySelector('.botmock')?.innerText.includes('заглушка')&&/plan_[a-z0-9]{6}/.test(document.querySelector('.botmock').innerText)),tag+' MAX stub with context id');
  await sleep(2300);await p.$eval('#feedback',e=>e.scrollIntoView());await p.screenshot({path:`qa-v2/${tag}-07-feedback.png`});
  await p.click('[data-act="fix"][data-f="calm"]').catch(()=>{});
  // events log
  await p.evaluate(()=>document.getElementById('logbox').open=true);const log=await p.$eval('#logbody',e=>e.innerText);ok(log.includes('anonymous_session_id')&&!/"ip"|ym_uid|clientID/i.test(log),tag+' analytics log anonymous');
  // honest few-matches: small kids + winter + caves
  await p.evaluate(()=>restart());await sleep(200);
  for(const [q,a] of [['season','winter'],['duration','one'],['base','guzeripl'],['party','small'],['been','any'],['pace','calm'],['interests','caves']])await ans(q,a);
  const fewTxt=await p.$eval('#results',e=>e.innerText);ok(/нашлось только|совпадений нет/.test(fewTxt),tag+' honest few/none mode');await p.evaluate(()=>[...document.querySelectorAll('#results .notice')].find(e=>/нашлось только|совпадений нет/.test(e.innerText))?.scrollIntoView());await sleep(300);await p.screenshot({path:`qa-v2/${tag}-08-few-matches.png`});
  await p.close()}
 await b.close();out.ok=out.errors.length===0;fs.writeFileSync(__dirname+'/QA-v2-e2e.json',JSON.stringify(out,null,1));console.log(out.checks.length,'checks passed; errors:',out.errors)})().catch(e=>{console.error('FAIL',e.message);process.exit(1)});
