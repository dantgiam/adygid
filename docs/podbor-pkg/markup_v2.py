#!/usr/bin/env python3
"""Draft data markup v2 for podbor (DRAFT — for Frank's approval).
Input: DEMO-data-trails.json / DEMO-data-checkpoints.json (public API snapshot).
Output: podbor-markup.json — one record per route (25) and per place (show_as_place, 66).
Every derived field carries a *_src (evidence basis). Editorial lists are drafts.
"""
import json,re,math,pathlib,datetime
P=pathlib.Path(__file__).resolve().parent
places_raw=[x for x in json.loads((P/'DEMO-data-checkpoints.json').read_text()) if x.get('show_as_place')]
allcp={x['id']:x for x in json.loads((P/'DEMO-data-checkpoints.json').read_text())}
routes_raw=json.loads((P/'DEMO-data-trails.json').read_text())
def clean(t):return re.sub(r'\s+',' ',re.sub('<[^>]+>',' ',t or '')).strip()

AREAS={ # anchor coordinates (approx. village/town centres) used for nearest-area grouping and base start
 'maykop':('Майкоп',44.605,40.100),'tulsky':('Тульский и Цветочный',44.490,40.160),
 'khadzhokh':('Каменномостский (Хаджох)',44.295,40.185),'dakhovskaya':('Даховская',44.235,40.210),
 'lago':('Лаго-Наки',44.085,40.015),'valley':('Хамышки и Гранитный каньон',44.125,40.110),
 'guzeripl':('Гузерипль',44.000,40.136),'sakhray':('Сахрай',44.174,40.300),
 'pobeda':('Победа',44.288,40.330),'novosvobodnaya':('Новосвободная',44.417,40.346),
 'north':('Гончарка (равнина)',44.807,39.947)}
def km(a,b,c,d):
 R=6371;p=math.radians;dl=p(c-a);dn=p(d-b);h=math.sin(dl/2)**2+math.cos(p(a))*math.cos(p(c))*math.sin(dn/2)**2;return 2*R*math.asin(math.sqrt(h))
def area(lat,lon):return min(AREAS,key=lambda k:km(lat,lon,AREAS[k][1],AREAS[k][2]))

CAT_TAGS={'Пещера':['caves'],'Водопад':['water'],'Каньон / ущелье':['water'],'Река / озеро':['water'],'Смотровая':['views'],'Плато / гора':['views'],
 'Скала-памятник':['views'],'Музей':['culture'],'Монастырь / храм':['culture'],'Дольмен':['culture'],'Археологический объект':['culture'],
 'Аул / этнообъект':['culture','familyfun'],'Термальный источник':['thermal'],'Заповедник / парк':['familyfun']}
NAME_TAGS=[('водопад|каньон|теснин|ущель|лагун|сплав','water'),('пещер|грот','caves'),('смотров|панорам|плато|гора |гора$|скала|перевал|канатн|вершин','views'),
 ('музе|галере|мечет|дольмен|монастыр|пустын|крест|печи|чай|мост','culture'),('терм|аква|кедров|псыгуп','thermal'),('вольер|парк|сыровар|ферм|аммонит|беловод|чай|канатн','familyfun')]
def tags_for(name,cat):
 out=list(CAT_TAGS.get(cat,[]));src=['категория «%s»'%cat] if cat in CAT_TAGS else []
 for rx,t in NAME_TAGS:
  if re.search(rx,name.lower()) and t not in out:out.append(t);src.append('название')
 return out,', '.join(dict.fromkeys(src)) or 'не определено'

# Editorial DRAFT lists — expert guess, Frank approves
BEST_P={24,40,55,25,52,48,50,56,75,67,30,57}
UNUSUAL_P={87,44,88,89,90,94,91,81,79,42,99,51,60,36,86,93,41}
BEST_R={12,16,13}
UNUSUAL_R={22,26,27,28,29,20,25,24,30}
INDOOR={45,62,69,76,77,83,80}          # museums / indoor (category-based)
# Known steps/stairs from v1 editorial pass (descriptions) — kept as evidence "v1-разметка"
STEP_V1={24,25,40,44,50,58,59,61,73,74,78,82,84}
TIERS=[('quick','⚡','20–45 мин',20,30,45),('short','🕐','1–2 ч',60,90,120),('medium','🕒','2–4 ч',120,180,240),('half','🌄','полдня, 4–6 ч',240,300,360),('full','🏔','весь день, 6+ ч',360,480,600)]
def tier_of(m):
 return 'quick' if m<=45 else 'short' if m<=120 else 'medium' if m<=240 else 'half' if m<=360 else 'full'
def est_tier(kind,cat,diff,access):
 if kind=='route':return {'hard':'half','extreme':'full'}.get(diff,'medium')
 if diff in('hard',):return 'medium' if cat=='Пещера' else 'half'
 if diff=='extreme':return 'full'
 if cat in('Музей','Монастырь / храм','Дольмен','Археологический объект','Скала-памятник','Смотровая'):return 'short' if access in('foot_only','hike') else 'quick'
 return 'short'

recs=[]
def base_rec(x,kind):
 desc=clean(x.get('description'));cat=(x.get('category') or {}).get('name','')
 return desc,cat
for x in places_raw:
 desc,cat=base_rec(x,'place');t,tsrc=tags_for(x['name'],cat)
 d=x.get('duration_minutes')
 if d:tid=tier_of(d);vt={'min':round(d*.75),'typ':d,'max':round(d*1.25),'source':'card','note':'по данным карточки сайта'}
 else:
  tid=est_tier('place',cat,x.get('difficulty'),x.get('access_type'));T=next(z for z in TIERS if z[0]==tid);vt={'min':T[3],'typ':T[4],'max':T[5],'source':'estimate','note':'оценка по типу места и сложности'}
 seas=x.get('seasonality');diff=x.get('difficulty');acc=x.get('access_type')
 if seas=='summer_only':w,ws='no','сезонность «только лето» в карточке'
 elif re.search(r'сух\w* бесснеж|только.{0,18}сух.{0,30}снег',desc,re.I):w,ws='no','в описании — только сухое бесснежное время'
 elif diff in('hard','extreme') or x['id'] in {84,29,56,59,61,66,75,73,74}:w,ws='unknown','круглый год по карточке, но сложный подход — зимой не подтверждено'
 elif acc in('foot_only','hike','high_clearance'):w,ws='unknown','круглый год по карточке; подход пешком/по грунтовке — зимой уточнить'
 else:w,ws='yes','«круглый год» в карточке + асфальтовый подъезд (состояние на дату — уточнять)'
 surf=x.get('surface_types') or []
 if re.search('сплав|рафтинг',x['name'].lower()):st,sts='no','активность на воде'
 elif x['id'] in STEP_V1 or re.search('ступен|лестниц',desc.lower()):st,sts='no','ступени/лестницы в описании или v1-разметке'
 elif acc in('foot_only','hike') or 'scramble' in surf or 'trail' in surf:st,sts='no','тропа/пеший подход по карточке'
 elif acc=='paved' and set(surf)<= {'asphalt'} and surf:st,sts='maybe','асфальт по карточке; входы не проверены'
 else:st,sts='unknown','нет данных о покрытии у входа'
 lat,lon=x['lat'],x['lon'];ph=(x.get('photos') or [{}]);ph=ph[0] if ph else {}
 recs.append({'type':'place','id':x['id'],'name':x['name'],'category':cat,'url':'https://www.adygid.ru/mesta/%d'%x['id'],'lat':lat,'lon':lon,
  'area':area(lat,lon),'tags':t,'tags_src':tsrc,'difficulty':diff,'kid':x.get('kid_friendly'),'season':seas,'access':acc,'weather':x.get('weather_warning'),
  'winter_ok':w,'winter_src':ws,'stroller':st,'stroller_src':sts,'tier':tid,'visit':vt,'checked':x.get('checked_at'),'indoor':x['id'] in INDOOR,
  'editorial':'best' if x['id'] in BEST_P else 'unusual' if x['id'] in UNUSUAL_P else '','is_paid':x.get('is_paid'),'price_note':x.get('price_note') or '',
  'description':desc[:500],'photoUrl':ph.get('thumb_url') or ph.get('url'),'photoCaption':ph.get('caption') or 'Фотография из карточки АдыГида; авторство — на странице источника'})
pmap={r['id']:r for r in recs}
FALLBACK_STOPS={18:[69,70,76,77,83],19:[78,71],20:[79],21:[80,72,68],22:[81,82,36,87],23:[84],24:[85]}
for x in routes_raw:
 desc,cat=base_rec(x,'route');raw=clean(x.get('description'))
 stops=[z['id'] for z in x.get('checkpoints',[])]
 linked=[int(m) for m in re.findall(r'/mesta/(\d+)',x.get('description') or '')]
 src='точки маршрута в API'
 if not stops:stops=[i for i in dict.fromkeys(linked) if i in pmap] or FALLBACK_STOPS.get(x['id'],[]);src='ссылки /mesta/ в описании' if linked else 'v1-ручная связка'
 coords=[(allcp[i]['lat'],allcp[i]['lon']) for i in stops if i in allcp]
 lat,lon=(sum(c[0] for c in coords)/len(coords),sum(c[1] for c in coords)/len(coords)) if coords else (None,None)
 tg=[];[tg.append(t) for i in stops if i in pmap for t in pmap[i]['tags'] if t not in tg]
 nt,_=tags_for(x['name'],'')
 for t in nt:
  if t not in tg:tg.append(t)
 d=x.get('duration_minutes')
 if d:tid=tier_of(d);vt={'min':round(d*.8),'typ':d,'max':round(d*1.25),'source':'card','note':'по данным маршрута на сайте'}
 else:
  tid=est_tier('route',cat,x.get('difficulty'),x.get('access_type'));T=next(z for z in TIERS if z[0]==tid);vt={'min':T[3],'typ':T[4],'max':T[5],'source':'estimate','note':'оценка по сложности маршрута'}
 seas=x.get('seasonality');diff=x.get('difficulty')
 if seas=='summer_only':w,ws='no','сезонность «только лето»'
 elif re.search(r'сух\w* бесснеж|только.{0,18}сух.{0,30}снег',raw,re.I):w,ws='no','в описании — сухое бесснежное время'
 elif x['id'] in{23,24,15,11,10}:w,ws='unknown','прошлая разметка (v1): зимний подход не подтверждён'
 elif diff in('hard','extreme'):w,ws='unknown','сложный маршрут — зимой не подтверждено'
 else:
  sw=[pmap[i]['winter_ok'] for i in stops if i in pmap]
  w,ws=('yes','все точки «круглый год», лёгкий/средний') if sw and all(v=='yes' for v in sw) else ('unknown','часть точек без зимнего подтверждения')
 st='no' if x['id'] in{10,11,15,19,23,24} or any(pmap.get(i,{}).get('stroller')=='no' for i in stops) else 'unknown'
 ph=(x.get('photos') or [{}]);ph=ph[0] if ph else {}
 recs.append({'type':'route','id':x['id'],'name':x['name'],'category':cat,'url':'https://www.adygid.ru/marshruty/%d'%x['id'],'lat':lat,'lon':lon,
  'area':area(lat,lon) if lat else 'other','stops':stops,'stops_src':src,'tags':tg,'tags_src':'теги точек маршрута + название','difficulty':diff,'kid':x.get('kid_friendly'),'season':seas,
  'access':x.get('access_type'),'weather':x.get('weather_warning'),'winter_ok':w,'winter_src':ws,'stroller':st,'stroller_src':'по точкам маршрута / v1-разметке' if st=='no' else 'нет данных',
  'tier':tid,'visit':vt,'checked':x.get('checked_at'),'indoor':False,'editorial':'best' if x['id'] in BEST_R else 'unusual' if x['id'] in UNUSUAL_R else '',
  'is_paid':x.get('is_paid'),'price_note':x.get('price_note') or '','description':desc[:500],'photoUrl':ph.get('thumb_url') or ph.get('url'),'photoCaption':ph.get('caption') or 'Фотография из карточки АдыГида; авторство — на странице источника'})
meta={'built':datetime.datetime.now().strftime('%d.%m.%Y %H:%M MSK'),'source':['https://www.adygid.ru/api/trails','https://www.adygid.ru/api/checkpoints'],
 'counts':{'routes':sum(r['type']=='route' for r in recs),'places':sum(r['type']=='place' for r in recs)},'areas':{k:v[0] for k,v in AREAS.items()},
 'tiers':[{'id':a,'icon':b,'label':c,'min':d,'typ':e,'max':f} for a,b,c,d,e,f in TIERS],'status':'DRAFT — требует утверждения Фрэнком'}
(P/'podbor-markup.json').write_text(json.dumps({'meta':meta,'items':recs},ensure_ascii=False,indent=1))
print(meta['counts'],'estimate durations:',sum(r['visit']['source']=='estimate' for r in recs),'no-coords routes:',[r['id'] for r in recs if r['lat'] is None])
from collections import Counter
print(Counter(r['area'] for r in recs));print(Counter(t for r in recs for t in r['tags']));print('untagged',[r['name'] for r in recs if not r['tags']])
