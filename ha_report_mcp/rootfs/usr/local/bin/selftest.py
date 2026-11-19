#!/usr/bin/env python3
"""Startup diagnostics, never print bearer credentials or report contents."""
import json, os, time, urllib.request, urllib.error
base='http://127.0.0.1:8787'
key=os.environ['REPORT_MCP_KEY']
def request(path, token=None, method='POST', payload=None):
    headers={'Content-Type':'application/json'}
    if token is not None: headers['Authorization']='Bearer '+token
    data=json.dumps(payload or {'jsonrpc':'2.0','id':1,'method':'tools/list'}).encode() if method=='POST' else None
    req=urllib.request.Request(base+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=5) as resp:
            return resp.status, json.loads(resp.read() or b'{}')
    except urllib.error.HTTPError as err:
        return err.code, {}
for _ in range(30):
    try:
        code,_=request('/mcp',None)
        break
    except (OSError,TimeoutError): time.sleep(.2)
else: raise SystemExit('[DIAG] FAIL: MCP server did not start')
assert code==401, f'Unauthenticated request: {code}'
print('[DIAG] UNAUTH: HTTP_401',flush=True)
code,_=request('/mcp','incorrect')
assert code==401, f'Invalid credential: {code}'
print('[DIAG] INVALID_KEY: HTTP_401',flush=True)
code,obj=request('/mcp',key)
assert code==200 and len(obj.get('result',{}).get('tools',[]))==3, 'Tool list unavailable'
print('[DIAG] AUTH_TOOLS: OK (3)',flush=True)
code,obj=request('/mcp',key,payload={'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'get_latest_report','arguments':{}}})
assert code==200, f'Report read returned {code}'
result=obj.get('result',{})
if result:
    txt=result.get('content',[{}])[0].get('text','{}')
    report=json.loads(txt)
    assert isinstance(report,dict) and 'date' in report and 'status' in report
    print('[DIAG] REPORT_READ: OK date='+str(report['date'])+' status='+str(report['status']),flush=True)
else:
    error=obj.get('error',{}).get('message','unknown')
    print('[DIAG] REPORT_READ: NOT_READY '+str(error)[:80],flush=True)
code,_=request('/api/states',key)
assert code==404, f'Unexpected path allowed: {code}'
print('[DIAG] BLOCKED_PATH: HTTP_404',flush=True)
print('[DIAG] FUNNEL: OFF',flush=True)
