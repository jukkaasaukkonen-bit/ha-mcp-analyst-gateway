import base64, hashlib, json, os, pathlib, sqlite3, tempfile, unittest, urllib.parse, urllib.request, threading, time
from http.server import HTTPServer
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT/'rootfs/usr/local/bin'))
os.environ.update(PUBLIC_BASE_URL='https://ha-report-mcp.tail2ce3bd.ts.net',GITHUB_CLIENT_ID='test-id',GITHUB_CLIENT_SECRET='test-secret',GITHUB_ALLOWED_LOGIN='test-user',GITHUB_ALLOWED_ID='123')
import oauth_mcp as app

class OAuthTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory()
  app.db.close()
  app.db=sqlite3.connect(':memory:',check_same_thread=False)
  app.db.executescript("""CREATE TABLE clients (client_id TEXT PRIMARY KEY, redirect_uris TEXT NOT NULL);
  CREATE TABLE pending (state TEXT PRIMARY KEY, client_id TEXT, redirect_uri TEXT, challenge TEXT, client_state TEXT, expires INTEGER);
  CREATE TABLE codes (code_hash TEXT PRIMARY KEY, client_id TEXT, redirect_uri TEXT, challenge TEXT, expires INTEGER);
  CREATE TABLE tokens (token_hash TEXT PRIMARY KEY, client_id TEXT NOT NULL, expires INTEGER);
  CREATE TABLE refresh_tokens (token_hash TEXT PRIMARY KEY, client_id TEXT NOT NULL, expires INTEGER);""")
  cls.server=HTTPServer(('127.0.0.1',0),app.Handler)
  cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
  cls.base='http://127.0.0.1:'+str(cls.server.server_port)
 @classmethod
 def tearDownClass(cls):cls.server.shutdown();cls.thread.join();app.db.close();cls.temp.cleanup()
 def request(self,path,data=None,headers=None):
  req=urllib.request.Request(self.base+path,data=(json.dumps(data).encode() if isinstance(data,dict) else data),headers=headers or {},method='POST' if data is not None else 'GET')
  try:
   with urllib.request.urlopen(req,timeout=3) as r:return r.status,dict(r.headers),r.read()
  except urllib.error.HTTPError as e:return e.code,dict(e.headers),e.read()
 def test_redirect_restrictions(self):
  self.assertTrue(app.safe_redirect('https://chatgpt.com/connector_platform_oauth_redirect'))
  for url in ['https://evil.example/cb','https://chatgpt.com.evil.example/cb','http://chatgpt.com/cb','http://localhost/cb','https://chatgpt.com@evil.example/cb']:
   self.assertFalse(app.safe_redirect(url))
 def test_discovery(self):
  status,_,body=self.request('/.well-known/oauth-authorization-server')
  self.assertEqual(status,200)
  self.assertIn('refresh_token',json.loads(body)['grant_types_supported'])
  status,_,body=self.request('/.well-known/oauth-protected-resource/mcp')
  self.assertEqual(status,200)
 def test_register_rejects_untrusted(self):
  status,_,_=self.request('/register',{'redirect_uris':['https://evil.example/cb']})
  self.assertEqual(status,400)
 def test_oauth_exchange_refresh_and_replay(self):
  redirect='https://chatgpt.com/connector_platform_oauth_redirect'
  status,_,body=self.request('/register',{'redirect_uris':[redirect]})
  self.assertEqual(status,201);cid=json.loads(body)['client_id']
  verifier='a'*43
  challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
  params=urllib.parse.urlencode({'client_id':cid,'redirect_uri':redirect,'response_type':'code','code_challenge_method':'S256','code_challenge':challenge,'state':'client-state','scope':'reports:read'})
  opener=urllib.request.build_opener(urllib.request.HTTPHandler())
  # Do not follow the GitHub redirect; inspect its Location instead.
  class NoRedirect(urllib.request.HTTPRedirectHandler):
   def redirect_request(self,*args):return None
  with self.assertRaises(urllib.error.HTTPError) as caught:
   urllib.request.build_opener(NoRedirect).open(self.base+'/authorize?'+params)
  self.assertEqual(caught.exception.code,302)
  state=urllib.parse.parse_qs(urllib.parse.urlsplit(caught.exception.headers['Location']).query)['state'][0]
  with patch.object(app,'github_identity',return_value={'login':'test-user','id':123}):
   with self.assertRaises(urllib.error.HTTPError) as cb:
    urllib.request.build_opener(NoRedirect).open(self.base+'/oauth/github/callback?'+urllib.parse.urlencode({'state':state,'code':'mock-github-code'}))
  self.assertEqual(cb.exception.code,302)
  code=urllib.parse.parse_qs(urllib.parse.urlsplit(cb.exception.headers['Location']).query)['code'][0]
  def form(v):return self.request('/token',urllib.parse.urlencode(v).encode(),{'Content-Type':'application/x-www-form-urlencoded'})
  request={'grant_type':'authorization_code','client_id':cid,'redirect_uri':redirect,'code':code,'code_verifier':'wrong'*10}
  self.assertEqual(form(request)[0],400)
  request['code_verifier']=verifier
  status,_,body=form(request);self.assertEqual(status,200);tokens=json.loads(body)
  self.assertEqual(form(request)[0],400)
  self.assertEqual(self.request('/mcp',{'jsonrpc':'2.0','id':1,'method':'tools/list'})[0],401)
  status,_,body=self.request('/mcp',{'jsonrpc':'2.0','id':1,'method':'tools/list'},{'Authorization':'Bearer '+tokens['access_token']})
  self.assertEqual(status,200);self.assertEqual(len(json.loads(body)['result']['tools']),3)
  refresh={'grant_type':'refresh_token','client_id':cid,'refresh_token':tokens['refresh_token']}
  self.assertEqual(form(refresh)[0],200)
  self.assertEqual(form(refresh)[0],400)
 def test_expired_token_denied(self):
  token='expired-test-token'
  app.db.execute('INSERT INTO tokens VALUES(?,?,?)',(app.digest(token),'expired-client',int(time.time())-1));app.db.commit()
  self.assertEqual(self.request('/mcp',{'jsonrpc':'2.0','id':1,'method':'tools/list'},{'Authorization':'Bearer '+token})[0],401)
 def test_invalid_origin(self):
  self.assertEqual(self.request('/mcp',{'jsonrpc':'2.0','id':1,'method':'ping'},{'Origin':'https://evil.example'})[0],403)
 def test_no_funnel(self):
  s=(ROOT/'rootfs/etc/services.d/report-mcp/run').read_text()
  self.assertNotIn('tailscale funnel --bg',s)
if __name__=='__main__':unittest.main()
