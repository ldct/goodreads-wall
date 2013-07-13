import os, logging

import webapp2
from sessions import sessions

from google.appengine.api.urlfetch import fetch, GET, POST
from urllib import urlencode, urlopen
from urlparse import parse_qs

from google.appengine.ext import ndb

from lxml import etree

import oauth2 as oauth
import urlparse

from google.appengine.api import urlfetch

with open("goodreads/DEV_KEY_SECRET") as f:
  DEV_KEY_SECRET = f.read()

url = 'http://www.goodreads.com'
request_token_url = '%s/oauth/request_token' % url
authorize_url = '%s/oauth/authorize' % url
access_token_url = '%s/oauth/access_token' % url

DEV_KEY = 'Wv8SrNCmt7v9V4zt8xQw'
consumer = oauth.Consumer(
  key= DEV_KEY,
  secret=DEV_KEY_SECRET)

class RequestTokenPair(ndb.Model):
    oauth_token = ndb.StringProperty()
    oauth_token_secret = ndb.StringProperty()

class RequestTokenHandler(sessions.BaseHandler):
  def get(self):

    client = oauth.Client(consumer)

    response, content = client.request(request_token_url, 'GET')
    if response['status'] != '200':
        raise Exception('Invalid response: %s' % response['status'])
     
    request_token = dict(urlparse.parse_qsl(content))
    
    token = RequestTokenPair()
    token.oauth_token = request_token['oauth_token']
    token.oauth_token_secret = request_token['oauth_token_secret']
    token.put()

    authorize_link = '%s?oauth_token=%s' % \
      (authorize_url, request_token['oauth_token'])
    self.redirect(authorize_link)
    
class AccessTokenHandler(sessions.BaseHandler):
  def get(self):

    oauth_token = self.request.get('oauth_token')
    oauth_token_secret = RequestTokenPair.query(RequestTokenPair.oauth_token == oauth_token).get().oauth_token_secret

    token = oauth.Token(oauth_token, oauth_token_secret)
    client = oauth.Client(consumer, token)

    print "getting access token...",
    response, content = client.request(access_token_url, 'POST')
    if response['status'] != '200':
      raise Exception('Invalid response: %s' % response['status'])
    
    access_token = dict(urlparse.parse_qsl(content))
    print "got ", access_token['oauth_token']

    token = oauth.Token(access_token['oauth_token'],
                        access_token['oauth_token_secret'])
    client = oauth.Client(consumer, token)

    response, content = client.request('%s/review/list?format=xml&v=2&per_page=200&shelf=read' % url,'GET')

    def rreplace(s, old, new, occurrence=1):
      li = s.rsplit(old, occurrence)
      return new.join(li)

    proc = []
    for review in etree.fromstring(content).find('reviews'):
      book = review.find('book')
      rating = review.findtext('rating')
      image = book.findtext('image_url')
      proc.append({'image': rreplace(image, 'm/', 'l/'), 'title': book.findtext('title'), 'isbn': book.findtext('isbn'), 'rating': rating})

    get_cover_queue = []
    covered = []
    for book in proc:
      if 'nocover' not in book['image']:
        covered.append(book)
      else:
        get_cover_queue.append(book)

    rpc_queue = []

    for book in get_cover_queue:
      print "added", book['isbn'], "to queue"
      rpc = urlfetch.create_rpc()
      urlfetch.make_fetch_call(rpc, "https://www.googleapis.com/books/v1/volumes?q=isbn%3A" + book['isbn'] + "&country=US")
      rpc_queue.append(rpc)

    for rpc in rpc_queue:
      print "getting rpc"
      result = rpc.get_result().content
      import json
      j = json.loads("".join(result))      
      try:
        if j['totalItems'] == 0:
          #self.response.write("<pre> %s: not on google books </pre>" % (book['title']))
          continue #todo: handle somehow!
      except:
        self.response.write(result)
        continue
      items = j['items']
      title = items[0]["volumeInfo"]["title"]

      try:
        image = items[0]["volumeInfo"]["imageLinks"]["thumbnail"]
        #image = image.replace("zoom=1", "zoom=0") #todo: try to append
        covered.append({'image': image, 'title': title, 'rating': 0})
      except:
        #self.response.write("no images for " + title)
        continue

    seq = ""
    for book in covered:
      seq += '{"image": "%s", "title": "%s", "rating": "%s"},\n' % (book['image'], book['title'], book['rating'])

    template = """
<script>
books = [
%s
]
</script>

<style>
img {
  width:148px;
  height:223px;
  padding:1px;
}
img.rated-4, img.rated-5 {
  width:298px;
  height:448px;
  padding:1px;
}
</style>

<script src="../isicp/js/jquery.min.js"></script>
<script src="http://isotope.metafizzy.co/jquery.isotope.min.js"></script>

<body>
  <div id="container"></div>
  <script>
  for (b in books) {
    img = $("<div class='item'>").append($("<img>", {'src': books[b].image, 'title': books[b].title, 'class': "rated-" + books[b].rating}))

    $("#container").append(img);
  }

  $("#container").isotope({
    itemSelector: '.item',
    sortBy: 'random',
    masonry: {
      columnWidth: 50
    },
  });
  </script>
</body>
    """
    self.response.write(template % seq)

app = webapp2.WSGIApplication(
  [('/goodreads/request', RequestTokenHandler),
   ('/goodreads/access', AccessTokenHandler)],
  debug=True, config=sessions.config)
