import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {createHandler} from '../src/index.js';
import {SCHEMA,TursoDatabase} from '../src/database.js';
import {parseFeed,runScheduled,imageFromEntry} from '../src/rss.js';
import config from '../../backend/feeds.json' with {type:'json'};
import {newsSlug} from '../src/seo.js';
function memoryDb(){
 const sqlite=new DatabaseSync(':memory:');
 return {async ensureSchema(){for(const sql of SCHEMA)sqlite.exec(sql);},
 async query(sql,args=[]){const stmt=sqlite.prepare(sql);if(/^(SELECT|.*RETURNING)/s.test(sql))return {rows:stmt.all(...args),affected:0};const result=stmt.run(...args);return {rows:[],affected:Number(result.changes)};},
 async batch(statements){return Promise.all(statements.map(({sql,args=[]})=>this.query(sql,args)));},close(){sqlite.close();}};
}
const env={SITE_URL:'https://mirai.example',SITE_NAME:'Mirai Wire'};
async function setup(){
 const db=memoryDb();await db.ensureSchema();
 for(const [title,category,image] of [['AI launch','technology','https://images.example/a.jpg'],['New AI chip','technology','https://images.example/b.jpg'],['Cricket news','sports','https://images.example/c.jpg'],['Hidden AI','technology',null]])
  await db.query('INSERT INTO news(title,url,summary,source,category,image_url,published_at,fetched_at) VALUES(?,?,?,?,?,?,?,?)',[title,'https://news.example/'+encodeURIComponent(title),'English news summary for testing','BBC',category,image,'2026-11-01T12:00:00Z','2026-11-01T12:00:00Z']);
 const handler=createHandler({dbFactory:()=>db});
 const get=async path=>{const response=await handler(new Request('https://api.example'+path),env);return {status:response.status,body:await response.json()};};
 return {db,handler,get};
}
test('all database-backed API routes and SEO contract',async()=>{
 const {db,get}=await setup();try {
  const home=await get('/api/v1/home?limit=2');assert.equal(home.body.total,3);assert.equal(home.body.data.length,2);assert.equal(home.body.seo.json_ld[0]['@type'],'CollectionPage');
  assert.equal((await get('/api/v1/home?page=2&limit=2')).body.data.length,1);
  assert.equal((await get('/api/v1/home?category=sports')).body.total,1);
  const single=await get('/api/v1/news/1');assert.equal(single.body.seo.json_ld[0]['@type'],'NewsArticle');assert.match(single.body.seo.canonical,/mirai.example\/news\/ai-launch-1/);
  assert.equal((await get('/api/v1/news/1/related')).body.total,1);
  assert.equal((await get('/api/v1/news/4')).status,404);
  assert.equal((await get('/api/v1/news/search?q=AI')).body.total,2);
  assert.equal((await get('/api/v1/news/search?q=AI&category=sports')).body.total,0);
  assert.equal((await get('/api/v1/news/search?q=%25')).body.total,0);
  assert.equal((await get('/api/v1/news/search?q=AI')).body.seo.robots,'noindex,follow');
  const feeds=(await get('/api/v1/feeds')).body;assert.equal(feeds.google_news.feeds.length,100);assert.equal(feeds.bbc.fetch_interval_minutes,15);assert.equal(feeds.bbc.last_fetched_at,null);assert.equal(feeds.bbc.feeds[0].url,undefined);
  assert.equal((await get('/api/v1/feeds/details')).body.total,108);
  assert.equal((await get('/health')).body.status,'ok');assert.equal((await get('/ready')).body.database,'turso');
 } finally {db.close();}
});
test('invalid inputs, missing IDs, method handling and CORS',async()=>{
 const {db,get,handler}=await setup();try {
  for(const path of ['/api/v1/home?page=0','/api/v1/home?limit=101','/api/v1/home?page=NaN','/api/v1/news/search','/api/v1/news/search?q=%20'])assert.equal((await get(path)).status,400,path);
  for(const path of ['/api/v1/news/999','/api/v1/news/999/related','/missing'])assert.equal((await get(path)).status,404,path);
  const post=await handler(new Request('https://api.example/health',{method:'POST'}),env);assert.equal(post.status,405);
  const options=await handler(new Request('https://api.example/health',{method:'OPTIONS'}),env);assert.equal(options.status,204);assert.equal(options.headers.get('Access-Control-Allow-Origin'),'*');
 }finally{db.close();}
});
test('database errors are sanitized; health remains independent',async()=>{
 const handler=createHandler({dbFactory:()=>{throw Error('private-token-secret');}});
 const response=await handler(new Request('https://api.example/ready'),env);assert.equal(response.status,503);assert.doesNotMatch(await response.text(),/private-token/);
 assert.equal((await handler(new Request('https://api.example/health'),env)).status,200);
});
const rss=`<?xml version="1.0"?><rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel><title>Example</title><language>en</language>
 <item><title>Artificial intelligence company launches a new product for software developers</title><link>https://news.example/new</link><description>A technology company has announced new software for customers around the world.</description><media:thumbnail url="https://images.example/new.jpg"/><pubDate>Sun, 01 Nov 2026 12:00:00 GMT</pubDate></item>
 <item><title>English story without an image</title><link>https://news.example/no-image</link></item></channel></rss>`;
test('RSS image filtering, English detection, date and invalid XML',()=>{
 const rows=parseFeed(rss,{name:'BBC',category:'technology'});assert.equal(rows.length,1);assert.equal(rows[0].image_url,'https://images.example/new.jpg');assert.equal(rows[0].published_at,'2026-11-01T12:00:00.000Z');
 assert.throws(()=>parseFeed('not xml',{}));assert.throws(()=>parseFeed('<!DOCTYPE rss><rss/>',{}));
 assert.equal(parseFeed(rss.replace('<language>en</language>','<language>hi</language>'),{}).length,0);
 assert.equal(imageFromEntry({'media:content':{'@_medium':'video','@_url':'https://example.com/video.mp4'}},'https://example.com'),null);
 assert.equal(imageFromEntry({description:'<img src="/photo.jpg">'},'https://example.com/news'),'https://example.com/photo.jpg');
});
test('Cron interval, database save, dedup, persisted statuses and failed fetch retry',async()=>{
 const db=memoryDb();await db.ensureSchema();
 const config={language:'en',bbc:{fetch_interval_minutes:15,feeds:[{id:101,name:'BBC',category:'technology',enabled:true,url:'https://feeds.example/rss'},{id:102,name:'Disabled',enabled:false,url:'https://feeds.example/no'}]}};
 let calls=0;const fetcher=async()=>{calls++;return new Response(rss);};const at=new Date('2026-11-01T12:00:00Z');
 try{
  const first=await runScheduled(db,config,env,fetcher,at);assert.equal(first[0].saved,1);assert.equal(first[0].error,null);
  assert.deepEqual(await runScheduled(db,config,env,fetcher,new Date(at.getTime()+14*60000)),[]);assert.equal(calls,1);
  const again=await runScheduled(db,config,env,fetcher,new Date(at.getTime()+15*60000));assert.equal(again[0].saved,0);
  const failed=await runScheduled(db,config,env,async()=>new Response('Unavailable',{status:503}),new Date(at.getTime()+30*60000));assert.match(failed[0].error,/503/);
  const state=(await db.query('SELECT * FROM feed_status WHERE feed_id=101')).rows[0];assert.equal(state.last_success_at,'2026-11-01T12:15:00.000Z');assert.equal(state.next_fetch_at,'2026-11-01T12:45:00.000Z');
  assert.equal((await db.query('SELECT COUNT(*) AS count FROM news')).rows[0].count,1);
 }finally{db.close();}
});
test('Turso protocol encoding, multiple statements, HTTP and SQL errors',async()=>{
 let sent;
 const fetcher=async(url,options)=>{sent={url,body:JSON.parse(options.body)};return Response.json({results:[{type:'ok',response:{result:{cols:[{name:'id'}],rows:[[{type:'integer',value:'7'}]],affected_row_count:0}}},{type:'ok',response:{result:{cols:[],rows:[],affected_row_count:1}}},{type:'ok',response:{type:'close'}}]});};
 const db=new TursoDatabase({TURSO_DATABASE_URL:'libsql://test.example',TURSO_AUTH_TOKEN:'test'},fetcher);
 const result=await db.batch([{sql:'SELECT ?',args:[7]},{sql:'INSERT INTO x VALUES(?)',args:[null]}]);assert.equal(result[0].rows[0].id,7);assert.equal(result[1].affected,1);assert.equal(sent.url,'https://test.example/v2/pipeline');assert.deepEqual(sent.body.requests[0].stmt.args,[{type:'integer',value:'7'}]);
 await assert.rejects(new TursoDatabase({TURSO_DATABASE_URL:'libsql://test.example',TURSO_AUTH_TOKEN:'test'},async()=>new Response('',{status:401})).query('SELECT 1'));
 await assert.rejects(new TursoDatabase({TURSO_DATABASE_URL:'libsql://test.example',TURSO_AUTH_TOKEN:'test'},async()=>Response.json({results:[{type:'error',error:{message:'secret'}}]})).query('SELECT 1'));
});

test('slug detail and related routes, unique suffixes and canonical consistency',async()=>{
 const {db,get}=await setup();try{
  const home=(await get('/api/v1/home')).body;
  const story=home.data.find(row=>row.id===1);
  assert.equal(story.slug,'ai-launch-1');assert.equal(story.api_path,'/api/v1/news/ai-launch-1');assert.equal(story.path,'/news/ai-launch-1');
  const bySlug=await get(story.api_path), byId=await get('/api/v1/news/1');
  assert.equal(bySlug.status,200);assert.deepEqual(bySlug.body,byId.body);
  const canonical=bySlug.body.seo.canonical;
  assert.equal(canonical,'https://mirai.example/news/ai-launch-1');
  assert.equal(bySlug.body.seo.open_graph['og:url'],canonical);
  assert.equal(bySlug.body.seo.json_ld[0].mainEntityOfPage['@id'],canonical);
  assert.equal(bySlug.body.seo.json_ld[1].itemListElement.at(-1).item,canonical);
  const related=(await get(story.api_path+'/related')).body;assert.equal(related.data[0].slug,'new-ai-chip-2');
  for(const path of ['/api/v1/news/wrong-title-1','/api/v1/news/wrong-title-1/related','/api/v1/news/ai-launch-999','/api/v1/news/ai-launch','/api/v1/news/hidden-ai-4'])assert.equal((await get(path)).status,404,path);
  assert.equal((await get('/api/v1/news/search?q=AI')).body.total,2);
  assert.notEqual(newsSlug({id:1,title:'Same headline'}),newsSlug({id:2,title:'Same headline'}));
  assert.equal(newsSlug({id:9,title:'!!!'}),'news-9');
  assert.equal(newsSlug({id:10,title:'x'.repeat(200)}).length,103);
 }finally{db.close();}
});
