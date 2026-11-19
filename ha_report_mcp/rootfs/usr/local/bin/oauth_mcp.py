#!/usr/bin/env python3
"""OAuth 2.0 authorization server + read-only MCP; experimental, Funnel fail-closed."""
import base64, hashlib, hmac, json, os, secrets, sqlite3, time, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from report_mcp import dispatch

ISSUER=os.environ.get('PUBLIC_BASE_URL','').rstrip('/')
GITHUB_ID=os.environ.get('GITHUB_CLIENT_ID','')
GITHUB_SECRET=os.environ.get('GITHUB_CLIENT_SECRET','')
ALLOWED=os.environ.get('GITHUB_ALLOWED_LOGIN','')
ALLOWED_ID=os.environ.get('GITHUB_ALLOWED_ID','')
DB='/data/oauth.sqlite3'
Path('/data').mkdir(exist_ok=True)
db=sqlite3.connect(DB,check_same_thread=False)
db.executescript('''CREATE TABLE IF NOT EXISTS clients (client_id TEXT PRIMARY KEY, redirect_uris TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pending (state TEXT PRIMARY KEY, client_id TEXT, redirect_uri TEXT, challenge TEXT, client_state TEXT, expires INTEGER);
CREATE TABLE IF NOT EXISTS codes (code_hash TEXT PRIMARY KEY, client_id TEXT, redirect_uri TEXT, challenge TEXT, expires INTEGER);
CREATE TABLE IF NOT EXISTS tokens (token_hash TEXT PRIMARY KEY, client_id TEXT NOT NULL, expires INTEGER);
CREATE TABLE IF NOT EXISTS refresh_tokens (token_hash TEXT PRIMARY KEY, client_id TEXT NOT NULL, expires INTEGER);''')
db.commit()

def digest(s): return hashlib.sha256(s.encode()).hexdigest()
def safe_redirect(uri):
 try:
  p=urllib.parse.urlsplit(uri)
  return (p.scheme=='https' and p.hostname in ('chatgpt.com','chat.openai.com')
          and p.port in (None,443) and not p.username and not p.password
          and not p.fragment and not p.query and p.path.startswith('/')
          and len(uri)<1024)
 except ValueError:
  return False

def valid_pkce(value):
 return (isinstance(value,str) and len(value)==43 and
         all(c.isascii() and (c.isalnum() or c in '-_') for c in value))

def token_pair(client_id):
 access=secrets.token_urlsafe(48);refresh=secrets.token_urlsafe(48)
 db.execute('INSERT INTO tokens VALUES(?,?,?)',(digest(access),client_id,int(time.time())+900))
 db.execute('INSERT INTO refresh_tokens VALUES(?,?,?)',(digest(refresh),client_id,int(time.time())+30*86400))
 return {'access_token':access,'refresh_token':refresh,'token_type':'Bearer','expires_in':900,'scope':'reports:read'}

def urlwith(uri, **params):
 p=urllib.parse.urlsplit(uri); q=urllib.parse.parse_qsl(p.query,keep_blank_values=True);q.extend(params.items());return urllib.parse.urlunsplit((p.scheme,p.netloc,p.path,urllib.parse.urlencode(q),''))
def post_form(url,values):
 req=urllib.request.Request(url,data=urllib.parse.urlencode(values).encode(),headers={'Accept':'application/json','Content-Type':'application/x-www-form-urlencoded','User-Agent':'HA-Report-MCP'},method='POST')
 with urllib.request.urlopen(req,timeout=10) as r:return json.load(r)
def github_identity(code):
 token=post_form('https://github.com/login/oauth/access_token',{'client_id':GITHUB_ID,'client_secret':GITHUB_SECRET,'code':code,'redirect_uri':ISSUER+'/oauth/github/callback'}).get('access_token')
 if not token:raise ValueError('GitHub token exchange failed')
 req=urllib.request.Request('https://api.github.com/user',headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','User-Agent':'HA-Report-MCP'})
 with urllib.request.urlopen(req,timeout=10) as r:return json.load(r)
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def send_json(self,status,data,extra=None):
  raw=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(raw)))
  for k,v in (extra or {}).items():self.send_header(k,v)
  self.end_headers();self.wfile.write(raw)
 def redirect(self,uri):self.send_response(302);self.send_header('Location',uri);self.send_header('Cache-Control','no-store');self.send_header('Content-Length','0');self.end_headers()
 def form(self):
  n=int(self.headers.get('Content-Length','0'))
  if n<1 or n>8192:raise ValueError('Invalid form size')
  return dict(urllib.parse.parse_qsl(self.rfile.read(n).decode(),keep_blank_values=True))
 def do_GET(self):
  p=urllib.parse.urlsplit(self.path);q=dict(urllib.parse.parse_qsl(p.query))
  if p.path=='/.well-known/oauth-authorization-server':return self.send_json(200,{'issuer':ISSUER,'authorization_endpoint':ISSUER+'/authorize','token_endpoint':ISSUER+'/token','registration_endpoint':ISSUER+'/register','response_types_supported':['code'],'grant_types_supported':['authorization_code','refresh_token'],'code_challenge_methods_supported':['S256'],'token_endpoint_auth_methods_supported':['none'],'scopes_supported':['reports:read']})
  if p.path in ('/.well-known/oauth-protected-resource','/.well-known/oauth-protected-resource/mcp'):return self.send_json(200,{'resource':ISSUER+'/mcp','authorization_servers':[ISSUER]})
  if p.path=='/authorize':
   cid=q.get('client_id',''); red=q.get('redirect_uri',''); challenge=q.get('code_challenge',''); state=q.get('state','')
   row=db.execute('SELECT redirect_uris FROM clients WHERE client_id=?',(cid,)).fetchone()
   if not row or red not in json.loads(row[0]) or q.get('response_type')!='code' or q.get('code_challenge_method')!='S256' or not valid_pkce(challenge) or not state or q.get('resource',ISSUER+'/mcp')!=ISSUER+'/mcp' or q.get('scope','reports:read')!='reports:read':return self.send_json(400,{'error':'invalid_request'})
   nonce=secrets.token_urlsafe(32); github_state=secrets.token_urlsafe(32)
   db.execute('INSERT INTO pending VALUES(?,?,?,?,?,?)',(github_state,cid,red,challenge,state,int(time.time())+300));db.commit()
   return self.redirect('https://github.com/login/oauth/authorize?'+urllib.parse.urlencode({'client_id':GITHUB_ID,'redirect_uri':ISSUER+'/oauth/github/callback','state':github_state,'scope':''}))
  if p.path=='/oauth/github/callback':
   if q.get('error'): return self.send_json(403,{'error':'access_denied'})
   st=q.get('state',''); row=db.execute('SELECT client_id,redirect_uri,challenge,client_state,expires FROM pending WHERE state=?',(st,)).fetchone()
   if not row or row[4]<time.time():return self.send_json(400,{'error':'invalid_state'})
   db.execute('DELETE FROM pending WHERE state=?',(st,));db.commit()
   try:
    who=github_identity(q.get('code',''))
    if who.get('login','').casefold()!=ALLOWED.casefold() or str(who.get('id',''))!=ALLOWED_ID:raise ValueError('GitHub user not permitted')
   except Exception:return self.send_json(403,{'error':'access_denied'})
   code=secrets.token_urlsafe(40)
   db.execute('INSERT INTO codes VALUES(?,?,?,?,?)',(digest(code),row[0],row[1],row[2],int(time.time())+120));db.commit()
   return self.redirect(urlwith(row[1],code=code,state=row[3]))
  return self.send_json(404,{'error':'not_found'})
 def do_POST(self):
  p=urllib.parse.urlsplit(self.path).path
  try:
   if p=='/register':
    n=int(self.headers.get('Content-Length','0'))
    if n<1 or n>8192:raise ValueError('Invalid body')
    data=json.loads(self.rfile.read(n)); redirects=data.get('redirect_uris',[])
    if not isinstance(redirects,list) or not 1<=len(redirects)<=2 or not all(isinstance(x,str) and safe_redirect(x) for x in redirects):return self.send_json(400,{'error':'invalid_redirect_uri'})
    cid=secrets.token_urlsafe(24);db.execute('INSERT INTO clients VALUES(?,?)',(cid,json.dumps(redirects)));db.commit()
    return self.send_json(201,{'client_id':cid,'redirect_uris':redirects,'token_endpoint_auth_method':'none','grant_types':['authorization_code','refresh_token'],'response_types':['code']})
   if p=='/token':
    data=self.form()
    if data.get('grant_type')=='refresh_token':
     old=data.get('refresh_token','')
     if not old or len(old)>256:return self.send_json(400,{'error':'invalid_grant'})
     row=db.execute('SELECT client_id,expires FROM refresh_tokens WHERE token_hash=?',(digest(old),)).fetchone()
     if not row or row[1]<=time.time() or data.get('client_id')!=row[0]:return self.send_json(400,{'error':'invalid_grant'})
     db.execute('DELETE FROM refresh_tokens WHERE token_hash=?',(digest(old),))
     payload=token_pair(row[0]);db.commit()
     return self.send_json(200,payload)
    code=data.get('code','');verifier=data.get('code_verifier','')
    if data.get('grant_type')!='authorization_code' or not (43<=len(verifier)<=128) or not all(c.isalnum() or c in '-._~' for c in verifier):return self.send_json(400,{'error':'invalid_grant'})
    row=db.execute('SELECT client_id,redirect_uri,challenge,expires FROM codes WHERE code_hash=?',(digest(code),)).fetchone()
    if not row or row[3]<time.time() or data.get('client_id')!=row[0] or data.get('redirect_uri')!=row[1]:return self.send_json(400,{'error':'invalid_grant'})
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    if not hmac.compare_digest(challenge,row[2]):return self.send_json(400,{'error':'invalid_grant'})
    # Consume authorization code before minting a token.
    db.execute('DELETE FROM codes WHERE code_hash=?',(digest(code),))
    payload=token_pair(row[0]);db.commit()
    return self.send_json(200,payload)
   if p=='/mcp':
    origin=self.headers.get('Origin')
    if origin and origin not in ('https://chatgpt.com','https://chat.openai.com'):
     return self.send_json(403,{'error':'invalid_origin'})
    auth=self.headers.get('Authorization','')
    bearer=auth[7:] if auth.startswith('Bearer ') else ''
    row=db.execute('SELECT expires FROM tokens WHERE token_hash=?',(digest(bearer),)).fetchone() if bearer else None
    if not row or row[0]<time.time():return self.send_json(401,{'error':'invalid_token'},{'WWW-Authenticate':'Bearer resource_metadata="'+ISSUER+'/.well-known/oauth-protected-resource"'})
    try:
     length=int(self.headers.get('Content-Length','0'))
     if length < 1 or length > 65536: return self.send_json(413,{'error':'request_too_large'})
     request=json.loads(self.rfile.read(length))
     if not isinstance(request,dict) or request.get('jsonrpc')!='2.0':return self.send_json(400,{'error':'invalid_jsonrpc'})
     response=dispatch(request)
     if response is None:
      self.send_response(202);self.send_header('Content-Length','0');self.end_headers();return
     return self.send_json(200,response)
    except Exception:return self.send_json(400,{'error':'invalid_request'})
   return self.send_json(404,{'error':'not_found'})
  except (ValueError,TypeError,KeyError,json.JSONDecodeError):return self.send_json(400,{'error':'invalid_request'})
if __name__=='__main__':
 if not GITHUB_ID or not GITHUB_SECRET or not ALLOWED or not ALLOWED_ID.isdecimal() or not ISSUER.startswith('https://'):raise SystemExit('OAuth configuration missing')
 HTTPServer(('127.0.0.1',8787),Handler).serve_forever()
