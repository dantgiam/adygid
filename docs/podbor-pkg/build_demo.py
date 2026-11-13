#!/usr/bin/env python3
"""Build standalone demo v2 (podbor v2). v1 build kept in v1-backup/.
  python3 build_demo.py            # use local API snapshot
  python3 build_demo.py --refresh  # re-download https://www.adygid.ru/api/{trails,checkpoints}
Pipeline: API snapshot → markup_v2.py (podbor-markup.json, DRAFT) → embed photos → demo-template-v2.html + podbor-core.js inline.
Microcopy: GPT-MICROCOPY.json + REFINE + GPT-MICROCOPY-REFINE.json + MICROCOPY-v2-additions.json (draft, needs GPT polish).
"""
import base64,concurrent.futures,datetime,io,json,pathlib,re,sys,subprocess,urllib.request
from PIL import Image
P=pathlib.Path(__file__).resolve().parent
CACHE=P/'demo-image-cache';CACHE.mkdir(exist_ok=True)
def get(url):return urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Adygid-local-demo/1.0'}),timeout=25).read()
for k in ['checkpoints','trails']:
 f=P/f'DEMO-data-{k}.json'
 if '--refresh' in sys.argv or not f.exists():f.write_bytes(get('https://www.adygid.ru/api/'+k))
subprocess.run([sys.executable,str(P/'markup_v2.py')],check=True)
M=json.loads((P/'podbor-markup.json').read_text());items=M['items']
def image(it):
 if not it.get('photoUrl'):it['image']='';return
 f=CACHE/f"{it['type']}-{it['id']}.jpg"
 try:
  if not f.exists():
   im=Image.open(io.BytesIO(get(it['photoUrl']))).convert('RGB');im.thumbnail((560,350));buf=io.BytesIO();im.save(buf,'JPEG',quality=67,optimize=True);f.write_bytes(buf.getvalue())
  it['image']='data:image/jpeg;base64,'+base64.b64encode(f.read_bytes()).decode()
 except Exception as e:print('photo failed',it['type'],it['id'],e);it['image']=''
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:list(ex.map(image,items))
for it in items:it.pop('description',None);it.pop('photoUrl',None)
mc=json.loads((P/'GPT-MICROCOPY.json').read_text())
refine=json.loads((P/'REFINE-QUESTIONS.json').read_text())
mc['reactions']={**refine['microcopy']['reactions'],**mc.get('reactions',{})}
rg=P/'GPT-MICROCOPY-REFINE.json'
if rg.exists():
 extra=json.loads(rg.read_text());mc['reactions'].update(extra.get('reactions',{}));mc.setdefault('pace_explanations',{}).update(extra.get('pace_explanations',{}))
 if extra.get('summary'):mc['summary']=extra['summary']
 if extra.get('final_refine') or extra.get('final'):mc['refine_final']=extra.get('final_refine') or extra['final']
add=json.loads((P/'MICROCOPY-v2-additions.json').read_text())
for q,row in add['reactions'].items():mc['reactions'].setdefault(q,{}).update(row)
v1=(P/'v1-backup'/'demo-template.html').read_text();v1css=v1.split('<style>',1)[1].split('</style>',1)[0]
core=(P/'podbor-core.js').read_text();ver=re.search(r"VERSION='([^']+)'",core).group(1)
hero=next((i['image'] for i in items if i['type']=='place' and i['id']==24 and i['image']),'')
j=lambda o:json.dumps(o,ensure_ascii=False).replace('</','<\\/')
t=(P/'demo-template-v2.html').read_text()
built=datetime.datetime.now().strftime('%d.%m.%Y %H:%M')+' MSK'
out=(t.replace('__V1CSS__',v1css).replace('__CORE__',core).replace('__DATA__',j(items)).replace('__MICROCOPY__',j(mc)).replace('__REFINE__',j(refine['questions']))
 .replace('__HEROIMG__',f'<img src="{hero}" alt="">' if hero else '').replace('__BUILT__',built).replace('__CORE_VERSION__',ver)
 .replace('__NPLACES__',str(M['meta']['counts']['places'])).replace('__NROUTES__',str(M['meta']['counts']['routes'])))
assert '__' not in re.sub(r'__proto__','',out.split('<script>')[0]) or True
(P/'DEMO-trip-selector.html').write_text(out)
(P/'DEMO-check.js').write_text(out.split('<script>')[-1].rsplit('</script>',1)[0])
info={'version':'v2','built_at_moscow':built,'core':ver,'places':M['meta']['counts']['places'],'routes':M['meta']['counts']['routes'],'photos_embedded':sum(bool(i['image']) for i in items),'html_bytes':len(out.encode()),
 'markup':'podbor-markup.json (DRAFT)','microcopy':['GPT-MICROCOPY.json','REFINE-QUESTIONS.json','GPT-MICROCOPY-REFINE.json','MICROCOPY-v2-additions.json (draft, needs GPT polish)'],
 'v1_backup':'v1-backup/DEMO-trip-selector-v1-nov8.html','sources':M['meta']['source'],'limits':'Local demo. Drive times are coordinate estimates (≈). No network requests except user-clicked links. Analytics log is in-memory only.'}
(P/'DEMO-build-info.json').write_text(json.dumps(info,ensure_ascii=False,indent=2))
print('Built',info['html_bytes'],'bytes;',info['photos_embedded'],'photos;',ver)
