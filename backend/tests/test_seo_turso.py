import json,unittest
from unittest.mock import patch
from database import TursoConnection
from seo import article_seo,listing_seo
from worker import interval_minutes,is_english

class SeoTursoTests(unittest.TestCase):
 def test_dynamic_metadata(self):
  story=dict(id=42,title='New AI launch',summary='A useful English news summary. '*20,source='BBC News',category='technology',image_url=None,published_at='2026-11-01T10:00:00+00:00',url='https://www.bbc.com/news/example')
  seo=article_seo(story)
  self.assertLessEqual(len(seo['description']),160)
  self.assertIn('/news/new-ai-launch-42',seo['canonical'])
  self.assertEqual(seo['json_ld'][0]['@type'],'NewsArticle')
  self.assertEqual(seo['json_ld'][0]['publisher']['name'],'BBC News')
  self.assertNotIn('author',seo['json_ld'][0])
  self.assertNotIn('dateModified',seo['json_ld'][0])
  self.assertNotIn('image',seo['json_ld'][0])
  self.assertEqual(listing_seo([story],query='AI')['robots'],'noindex,follow')
  self.assertEqual(listing_seo([story])['json_ld'][1]['@type'],'WebSite')
 def test_provider_intervals_and_language(self):
  settings={'fetch_interval_minutes':30,'provider_intervals_minutes':{'bbc':15}}
  with patch.dict('os.environ',{'RSS_BBC_FETCH_MINUTES':'12'}):
   self.assertEqual(interval_minutes({'provider':'bbc'},settings),15)
  self.assertTrue(is_english('Artificial intelligence news','A technology company has released a new software product for developers around the world.'))
  self.assertFalse(is_english('?? ?? ???? ???','???? ??? ?? ?? ????? ?? ????? ?? ?? ???'))
 def test_turso_parameter_encoding_and_response(self):
  result={'results':[{'type':'ok','response':{'type':'execute','result':{'cols':[{'name':'id'},{'name':'title'}],'rows':[[{'type':'integer','value':'42'},{'type':'text','value':'News'}]],'affected_row_count':1}}}]}
  with patch('database.urlopen') as mock:
   mock.return_value.__enter__.return_value.read.return_value=json.dumps(result).encode()
   db=TursoConnection('libsql://example.turso.io','test-token')
   cursor=db.execute('SELECT ? AS id, ? AS title',(42,'News'))
   self.assertEqual(dict(cursor.fetchone()),{'id':42,'title':'News'})
   self.assertEqual(cursor.fetchone()[0],42)
   req=mock.call_args.args[0]
   self.assertEqual(req.full_url,'https://example.turso.io/v2/pipeline')
   self.assertEqual(json.loads(req.data)['requests'][0]['stmt']['args'][0],{'type':'integer','value':'42'})
 def test_turso_sql_errors(self):
  with patch('database.urlopen') as mock:
   mock.return_value.__enter__.return_value.read.return_value=b'{"results":[{"type":"error","error":{"code":"SQL_ERROR"}}]}'
   with self.assertRaises(RuntimeError): TursoConnection('libsql://example.turso.io','test').execute('BAD SQL')
 def test_no_blank_credentials(self):
  with self.assertRaises(ValueError): TursoConnection('libsql://example.turso.io','')

if __name__=='__main__': unittest.main()
