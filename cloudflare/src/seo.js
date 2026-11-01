const trimDescription = text => {
  text = String(text || '').replace(/<[^>]+>/g,'').replace(/\s+/g,' ').trim();
  return text.length <= 160 ? text : text.slice(0,157).replace(/\s+\S*$/,'')+'...';
};
const titleCase = text => text.replace(/\b\w/g,char => char.toUpperCase());
function settings(env) {
  const address = env.SITE_URL || 'https://example.invalid';
  return {base:address.replace(/\/$/,''),name:env.SITE_NAME || 'Mirai Wire'};
}
function meta(title,description,canonical,env,image=null,article=false,index=true) {
  const {name} = settings(env);
  const result = {title,description,canonical,language:'en',robots:index ? 'index,follow,max-image-preview:large' : 'noindex,follow',
    open_graph:{'og:title':title,'og:description':description,'og:url':canonical,'og:type':article ? 'article' : 'website','og:site_name':name,'og:locale':'en_US'},
    twitter:{'twitter:card':image ? 'summary_large_image' : 'summary','twitter:title':title,'twitter:description':description}};
  if (image) {result.open_graph['og:image']=image; result.twitter['twitter:image']=image;}
  return result;
}
export function articleSeo(story,env) {
  const {base,name}=settings(env);
  const slug=story.title.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,100).replace(/-$/,'');
  const canonical=`${base}/news/${story.id}/${slug}`;
  const description=trimDescription(story.summary || story.title);
  const result=meta(`${story.title} | ${name}`,description,canonical,env,story.image_url,true);
  const schema={'@context':'https://schema.org','@type':'NewsArticle','@id':canonical+'#article',headline:story.title,description,url:canonical,
    mainEntityOfPage:{'@type':'WebPage','@id':canonical},datePublished:story.published_at,inLanguage:'en',articleSection:story.category,
    publisher:{'@type':'Organization',name:story.source},isBasedOn:story.url};
  if (story.image_url) schema.image=[story.image_url];
  result.open_graph['article:published_time']=story.published_at;
  result.open_graph['article:section']=story.category;
  result.json_ld=[schema,{'@context':'https://schema.org','@type':'BreadcrumbList',itemListElement:[
    {'@type':'ListItem',position:1,name:'Home',item:base+'/'},
    {'@type':'ListItem',position:2,name:titleCase(story.category),item:base+'/?'+new URLSearchParams({category:story.category})},
    {'@type':'ListItem',position:3,name:story.title,item:canonical}]}];
  return result;
}
export function listingSeo(stories,env,category='',query='',page=1) {
  const {base,name}=settings(env), params=new URLSearchParams();
  if (category) params.set('category',category);
  if (query) params.set('q',query);
  if (page>1) params.set('page',page);
  const canonical=base+(query ? '/search' : '/')+(params.size ? '?'+params : '');
  const label=query ? 'Search: '+query : category ? titleCase(category)+' News' : 'Latest English News';
  const description=trimDescription(`Read ${label} on ${name}. `+(stories.length ? 'Latest: '+stories[0].title : 'News from India and around the world.'));
  const result=meta(`${label} | ${name}`,description,canonical,env,null,false,!query);
  result.json_ld=[{'@context':'https://schema.org','@type':query ? 'SearchResultsPage' : 'CollectionPage',name:label,url:canonical,description,inLanguage:'en',
    mainEntity:{'@type':'ItemList',itemListElement:stories.map((story,i) => ({'@type':'ListItem',position:i+1,url:articleSeo(story,env).canonical,name:story.title}))}}];
  if (!query && !category && page===1) {
    const publisher={'@type':'Organization',name,url:base};
    if (env.SITE_LOGO_URL) publisher.logo={'@type':'ImageObject',url:env.SITE_LOGO_URL};
    result.json_ld.push({'@context':'https://schema.org','@type':'WebSite',name,url:base+'/',inLanguage:'en',publisher});
  }
  return result;
}
