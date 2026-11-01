"""Dynamic SEO response data for the frontend's HTML head and JSON-LD."""
import os
import re
from urllib.parse import urlencode

def base(): return os.environ.get('SITE_URL','http://localhost:3000').rstrip('/')
def site_name(): return os.environ.get('SITE_NAME','Mirai Wire')
def description(text):
    text = ' '.join(re.sub('<[^>]+>', '', text or '').split())
    return text if len(text)<=160 else text[:157].rsplit(' ',1)[0]+'...'
def organization():
    result={'@type':'Organization','name':site_name(),'url':base()}
    logo=os.environ.get('SITE_LOGO_URL','').strip()
    if logo: result['logo']={'@type':'ImageObject','url':logo}
    return result

def metadata(title, desc, canonical, image=None, article=False, index=True):
    result={'title':title,'description':desc,'canonical':canonical,'language':'en',
      'robots':'index,follow,max-image-preview:large' if index else 'noindex,follow',
      'open_graph':{'og:title':title,'og:description':desc,'og:url':canonical,'og:type':'article' if article else 'website','og:site_name':site_name(),'og:locale':'en_US'},
      'twitter':{'twitter:card':'summary_large_image' if image else 'summary','twitter:title':title,'twitter:description':desc}}
    if image:
        result['open_graph']['og:image']=image
        result['twitter']['twitter:image']=image
    return result

def news_slug(story):
    title = re.sub('[^a-z0-9]+', '-', story['title'].lower()).strip('-')[:100].rstrip('-') or 'news'
    return title + '-' + str(story['id'])

def with_slug(story):
    slug = news_slug(story)
    return dict(story, slug=slug, path='/news/' + slug, api_path='/api/v1/news/' + slug)

def article_seo(story):
    url=base()+'/news/'+news_slug(story)
    desc=description(story['summary'] or story['title'])
    result=metadata(story['title']+' | '+site_name(),desc,url,story.get('image_url'),True)
    schema={'@context':'https://schema.org','@type':'NewsArticle','@id':url+'#article',
      'headline':story['title'],'description':desc,'url':url,'mainEntityOfPage':{'@type':'WebPage','@id':url},
      'datePublished':story['published_at'],'inLanguage':'en','articleSection':story['category'],
      'publisher':{'@type':'Organization','name':story['source']},
      'isBasedOn':story['url']}
    # Do not invent an author or an updated timestamp from the fetch time.
    if story.get('author'): schema['author']={'@type':'Person','name':story['author']}
    if story.get('image_url'): schema['image']=[story['image_url']]
    result['open_graph']['article:published_time']=story['published_at']
    result['open_graph']['article:section']=story['category']
    result['json_ld']=[schema,{'@context':'https://schema.org','@type':'BreadcrumbList','itemListElement':[
      {'@type':'ListItem','position':1,'name':'Home','item':base()+'/'},
      {'@type':'ListItem','position':2,'name':story['category'].title(),'item':base()+'/?'+urlencode({'category':story['category']})},
      {'@type':'ListItem','position':3,'name':story['title'],'item':url}]}]
    return result

def listing_seo(stories,category='',query='',page=1):
    params={}
    if category: params['category']=category
    if query: params['q']=query
    if page>1: params['page']=page
    url=base()+('/search' if query else '/')+('?' + urlencode(params) if params else '')
    label=('Search: '+query) if query else ((category.title()+' News') if category else 'Latest English News')
    desc=description('Read '+label+' on '+site_name()+'. '+('Latest: '+stories[0]['title'] if stories else 'News from India and around the world.'))
    result=metadata(label+' | '+site_name(),desc,url,index=not bool(query))
    collection={'@context':'https://schema.org','@type':'SearchResultsPage' if query else 'CollectionPage',
      'name':label,'url':url,'description':desc,'inLanguage':'en','mainEntity':{'@type':'ItemList','itemListElement':[
      {'@type':'ListItem','position':i+1,'url':article_seo(story)['canonical'],'name':story['title']} for i,story in enumerate(stories)]}}
    result['json_ld']=[collection]
    if not query and not category and page==1:
        result['json_ld'].append({'@context':'https://schema.org','@type':'WebSite','name':site_name(),'url':base()+'/', 'inLanguage':'en','publisher':organization()})
    return result
