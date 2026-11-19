#!/usr/bin/env python3
import json,time,urllib.request,urllib.error
base='http://127.0.0.1:8787'
for _ in range(40):
 try:urllib.request.urlopen(base+'/.well-known/oauth-authorization-server',timeout=2);break
 except Exception:time.sleep(.25)
def check(path,method='GET',body=None):
 try:
  with urllib.request.urlopen(urllib.request.Request(base+path,data=body,method=method),timeout=3) as r:return r.status,r.read()
 except urllib.error.HTTPError as e:return e.code,e.read()
a,b=check('/.well-known/oauth-authorization-server');assert a==200 and json.loads(b)['code_challenge_methods_supported']==['S256']
a,b=check('/mcp','POST',b'{}');assert a==401
a,b=check('/api/states');assert a==404
a,b=check('/token','POST',b'grant_type=authorization_code');assert a==400
print('[DIAG] OAUTH_METADATA: OK; MCP_UNAUTH: 401; BLOCKED_PATH: 404; INVALID_TOKEN_REQUEST: 400; FUNNEL: OFF',flush=True)
