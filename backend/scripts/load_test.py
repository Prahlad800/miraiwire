"""One 100-client simultaneous burst per public GET endpoint."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import threading
import time
from urllib.request import urlopen

parser=argparse.ArgumentParser()
parser.add_argument('--base',default='http://127.0.0.1:5000')
parser.add_argument('--users',type=int,default=100)
args=parser.parse_args()
def get(path):
 with urlopen(args.base+path,timeout=45) as r:
  return r.status,json.load(r)
status,page=get('/api/v1/home?limit=1')
story_id=page['data'][0]['id']
paths=['/api/v1/home?page=1&limit=20','/api/v1/home?category=technology&page=1&limit=20',f'/api/v1/news/{story_id}',f'/api/v1/news/{story_id}/related?limit=6','/api/v1/news/search?q=AI&page=1&limit=20','/api/v1/news/search?q=AI&category=technology','/api/v1/feeds','/api/v1/feeds/details','/health','/ready']
report={'base_url':args.base,'concurrent_users':args.users,'kind':'one simultaneous burst per endpoint; not sustained 100 requests/second','endpoints':[]}
for path in paths:
 status,body=get(path)
 gate=threading.Barrier(args.users+1)
 def request_one(index):
  gate.wait()
  started=time.perf_counter()
  try:
   code,data=get(path)
   valid= isinstance(data,dict) and (('data' in data) if '/news/' in path or '/home' in path else True)
   return {'status':code,'valid':valid,'start':started,'seconds':time.perf_counter()-started}
  except Exception as exc:
   return {'status':getattr(exc,'code',0),'valid':False,'start':started,'seconds':time.perf_counter()-started,'error':type(exc).__name__}
 with ThreadPoolExecutor(max_workers=args.users) as pool:
  tasks=[pool.submit(request_one,i) for i in range(args.users)]
  gate.wait()
  results=[task.result() for task in tasks]
 durations=sorted(r['seconds'] for r in results)
 starts=[r['start'] for r in results]
 elapsed=max(r['start']+r['seconds'] for r in results)-min(starts)
 item={'path':path,'functional_status':status,'requests':len(results),'passed':sum(r['status']==200 and r['valid'] for r in results),'errors':sum(r['status']!=200 or not r['valid'] for r in results),'launch_window_ms':round((max(starts)-min(starts))*1000,1),'average_ms':round(sum(durations)/len(durations)*1000,1),'p95_ms':round(durations[math.ceil(.95*len(durations))-1]*1000,1),'max_ms':round(max(durations)*1000,1),'burst_completion_seconds':round(elapsed,2),'completed_requests_per_second':round(len(results)/elapsed,2),'error_types':sorted(set(r.get('error','HTTP '+str(r['status'])) for r in results if r['status']!=200))}
 report['endpoints'].append(item)
 print(json.dumps(item),flush=True)
 Path('data').mkdir(exist_ok=True)
 Path('data/load-test.json').write_text(json.dumps(report,indent=2))
print('REPORT: data/load-test.json',flush=True)
