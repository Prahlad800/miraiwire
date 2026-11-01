import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from app import create_app, connect
from worker import fetch_feed, run_once
from feed_config import load_settings

class NewsTests(unittest.TestCase):
 def setUp(self):
  self.temp = tempfile.TemporaryDirectory()
  self.db = str(Path(self.temp.name)/'test.sqlite3')
  self.client = create_app({'TESTING':True,'DATABASE':self.db}).test_client()
  with connect(self.db) as db:
   for title,category in [('AI launch','technology'),('New chip','technology'),('Cricket final','sports')]:
    db.execute('INSERT INTO news(title,url,source,category,published_at,fetched_at) VALUES(?,?,?,?,?,?)',(title,'https://example.com/'+title,'Example',category,'2026-11-01T00:00:00+00:00','2026-11-01T00:00:00+00:00'))
   db.execute("UPDATE news SET image_url='https://example.com/image.jpg'")
 def tearDown(self):
  self.temp.cleanup()
 def test_home_and_detail(self):
  self.assertEqual(self.client.get('/api/v1/home?limit=2').json['total'],3)
  self.assertEqual(len(self.client.get('/api/v1/home?limit=2&page=2').json['data']),1)
  self.assertEqual(self.client.get('/api/v1/news/1').json['data']['title'],'AI launch')
  self.assertEqual(self.client.get('/api/v1/news/999').status_code,404)
 def test_search_and_related(self):
  self.assertEqual(self.client.get('/api/v1/news/search?q=AI').json['total'],1)
  self.assertEqual(self.client.get('/api/v1/news/search?q=%25').json['total'],0)
  data=self.client.get('/api/v1/news/1/related').json['data']
  self.assertEqual([row['id'] for row in data],[2])
  self.assertEqual(self.client.get('/api/v1/home?category=sports').json['total'],1)
 def test_validation(self):
  for url in ['/api/v1/home?page=0','/api/v1/home?limit=101','/api/v1/home?page=abc','/api/v1/news/search']:
   self.assertEqual(self.client.get(url).status_code,400)
 def test_ingestion_dedup_and_failure(self):
  feed={'id':1,'name':'Test','category':'technology','url':'https://example.com/rss'}
  settings={'request_timeout_seconds':2,'max_items_per_feed':100,'fetch_interval_minutes':30}
  rss=b'<rss version="2.0"><channel><title>Test</title><item><title>Hello &amp; world</title><link>https://example.com/new</link><description>&lt;p&gt;Clean&lt;/p&gt;&lt;img src=&quot;https://example.com/photo.jpg&quot;/&gt;</description><pubDate>Sun, 01 Nov 2026 10:00:00 GMT</pubDate></item></channel></rss>'
  with patch('worker.urlopen') as mock:
   mock.return_value.__enter__.return_value.read.return_value=rss
   self.assertEqual(fetch_feed(feed,settings,self.db)['saved'],1)
   result=fetch_feed(feed,settings,self.db)
   self.assertEqual(result['saved'],0)
   self.assertIsNone(result['error'])
  with patch('worker.urlopen',side_effect=TimeoutError('timeout')):
   self.assertEqual(fetch_feed(feed,settings,self.db)['error'],'timeout')
  with connect(self.db) as db:
   status=db.execute('SELECT * FROM feed_status').fetchone()
   self.assertIsNotNone(status['last_success_at'])
   self.assertEqual(status['last_error'],'timeout')
   self.assertEqual(db.execute("SELECT summary FROM news WHERE url='https://example.com/new'").fetchone()[0],'Clean')
  path=Path(self.temp.name)/'feeds.json'
  path.write_text(json.dumps(dict(settings,feeds=[feed])))
  self.assertEqual(run_once(self.db,path),[])
 def test_grouped_feeds(self):
  data=self.client.get('/api/v1/feeds').json
  self.assertEqual(set(data),{'language','google_news','the_hindu','bbc'})
  self.assertEqual(data['language'],'en')
  self.assertEqual(len(data['google_news']['feeds']),100)
  self.assertEqual(len(data['bbc']['feeds']),4)
  self.assertIsNone(data['bbc']['last_fetched_at'])
  with connect(self.db) as db:
   db.execute('INSERT INTO feed_status(feed_id,last_attempt_at,last_success_at) VALUES(?,?,?)',(101,'2026-11-01T12:00:00+00:00','2026-11-01T10:00:00+00:00'))
  self.assertEqual(self.client.get('/api/v1/feeds').json['bbc']['last_fetched_at'],'2026-11-01T10:00:00+00:00')
  self.assertNotIn('url',data['bbc']['feeds'][0])
  self.assertEqual(self.client.get('/api/v1/feeds/details').json['total'],108)
 def test_image_only_lists_and_details(self):
  with connect(self.db) as db:
   db.execute('UPDATE news SET image_url=NULL WHERE id=2')
  self.assertEqual(self.client.get('/api/v1/home').json['total'],2)
  self.assertEqual(self.client.get('/api/v1/news/search?q=chip').json['total'],0)
  self.assertEqual(self.client.get('/api/v1/news/1/related').json['total'],0)
  self.assertEqual(self.client.get('/api/v1/news/2').status_code,404)
 def test_skip_entries_without_image(self):
  feed={'id':999,'name':'Test','category':'technology','url':'https://example.com/rss'}
  settings={'request_timeout_seconds':2,'max_items_per_feed':100,'fetch_interval_minutes':30}
  rss=b'<rss version="2.0"><channel><title>Test</title><item><title>New technology product has launched today</title><link>https://example.com/no-image</link></item></channel></rss>'
  with patch('worker.urlopen') as mock, patch('worker.is_english',return_value=True):
   mock.return_value.__enter__.return_value.read.return_value=rss
   result=fetch_feed(feed,settings,self.db)
   self.assertEqual(result['saved'],0)
   self.assertIsNone(result['error'])
 def test_provider_schedule_and_database_persistence(self):
  from datetime import datetime,timezone
  at=datetime(2026,11,1,12,0,tzinfo=timezone.utc)
  config={'language':'en'}
  for provider,minutes,feed_id in [('bbc',15,701),('the_hindu',20,702),('google_news',30,703)]:
   config[provider]={'fetch_interval_minutes':minutes,'last_fetched_at':None,'feeds':[{'id':feed_id,'name':provider,'url':'https://example.com/rss','category':'technology','enabled':True}]}
   with connect(self.db) as db:
    db.execute('INSERT INTO feed_status(feed_id,last_attempt_at) VALUES(?,?)',(feed_id,'2026-11-01T11:45:00+00:00'))
  path=Path(self.temp.name)/'grouped.json'; path.write_text(json.dumps(config))
  rss=b'<rss version="2.0"><channel><title>Test</title><item><title>A new technology product launched today</title><link>https://example.com/scheduled</link><description>&lt;img src="https://example.com/new.jpg"/&gt;Technology news today.</description></item></channel></rss>'
  with patch('worker.now',return_value=at),patch('worker.urlopen') as network,patch('worker.is_english',return_value=True):
   network.return_value.__enter__.return_value.read.return_value=rss
   result=run_once(self.db,path)
   self.assertEqual([r['feed_id'] for r in result],[701])
   self.assertEqual(result[0]['saved'],1)
   self.assertEqual(run_once(self.db,path),[])
  with connect(self.db) as db:
   state=db.execute('SELECT next_fetch_at FROM feed_status WHERE feed_id=701').fetchone()
   self.assertEqual(state[0],'2026-11-01T12:15:00+00:00')
  # A fresh app sees saved rows while outbound network calls are unavailable.
  client=create_app({'TESTING':True,'DATABASE':self.db}).test_client()
  with patch('worker.urlopen',side_effect=AssertionError('GET must not fetch RSS')):
   page=client.get('/api/v1/home?category=technology').json
   story=next(row for row in page['data'] if row['url']=='https://example.com/scheduled')
   for url in ['/api/v1/home','/api/v1/home?category=technology',f"/api/v1/news/{story['id']}",f"/api/v1/news/{story['id']}/related",'/api/v1/news/search?q=technology','/api/v1/news/search?q=technology&category=technology','/health']:
    self.assertEqual(client.get(url).status_code,200)
 def test_catalog(self):
  config=load_settings()
  self.assertEqual(len(config['feeds']),108)
  self.assertEqual(len({f['url'] for f in config['feeds']}),108)

if __name__=='__main__': unittest.main()
