#!/usr/bin/env python3
"""Stateless, read-only MCP JSON-RPC server. No HA API credentials or writes."""
import hmac
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DATA = Path('/share/ha_analyst_reports')
KEY = os.environ.get('REPORT_MCP_KEY', '')
TOOLS = [
 {'name':'get_latest_report','description':'Read the latest Home Assistant Analyst Engine report (read-only).',
  'inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
 {'name':'list_report_dates','description':'List dates of available daily reports (read-only).',
  'inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
 {'name':'get_report_by_date','description':'Read a report by ISO date (read-only).',
  'inputSchema':{'type':'object','properties':{'date':{'type':'string','description':'YYYY-MM-DD'}},'required':['date'],'additionalProperties':False}},
]
def read_report(name):
 if name!='latest.json' and not re.fullmatch(r'\d{4}-\d{2}-\d{2}\.json',name):
  raise ValueError('Invalid report name')
 path=DATA/name
 if not path.is_file(): raise FileNotFoundError('Report unavailable')
 if path.stat().st_size>512_000: raise ValueError('Report exceeds size limit')
 return json.loads(path.read_text(encoding='utf-8'))

def dispatch(message):
 method=message.get('method'); rid=message.get('id')
 if method=='notifications/initialized': return None
 if method=='initialize':
  result={'protocolVersion':'2025-03-26','capabilities':{'tools':{'listChanged':False}},
          'serverInfo':{'name':'ha-report-mcp','version':'0.1.1'}}
 elif method=='ping': result={}
 elif method=='tools/list': result={'tools':TOOLS}
 elif method=='tools/call':
  params=message.get('params') or {}; name=params.get('name'); args=params.get('arguments') or {}
  if name not in {t['name'] for t in TOOLS}: raise ValueError('Unknown tool')
  if not isinstance(args,dict): raise ValueError('Invalid arguments')
  if name=='get_latest_report': value=read_report('latest.json')
  elif name=='list_report_dates':
   value={'dates':sorted(p.stem for p in DATA.glob('????-??-??.json') if re.fullmatch(r'\d{4}-\d{2}-\d{2}',p.stem))[-120:]}
  else:
   date=args.get('date','')
   if not isinstance(date,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',date): raise ValueError('Invalid date')
   value=read_report(date+'.json')
  result={'content':[{'type':'text','text':json.dumps(value,ensure_ascii=False)}], 'isError':False}
 else: return {'jsonrpc':'2.0','id':rid,'error':{'code':-32601,'message':'Method not found'}}
 return {'jsonrpc':'2.0','id':rid,'result':result}

class Handler(BaseHTTPRequestHandler):
 def log_message(self, fmt, *args): pass
 def reply(self, code, obj=None):
  data=json.dumps(obj or {}).encode()
  self.send_response(code)
  self.send_header('Content-Type','application/json')
  self.send_header('Cache-Control','no-store')
  self.send_header('X-Content-Type-Options','nosniff')
  self.send_header('Content-Length',str(len(data)))
  self.end_headers();self.wfile.write(data)
 def authorized(self):
  expected='Bearer '+KEY
  return len(KEY)>=32 and hmac.compare_digest(self.headers.get('Authorization',''),expected)
 def do_GET(self): self.reply(405,{'error':'POST required'})
 def do_POST(self):
  if self.path!='/mcp': return self.reply(404,{'error':'Not found'})
  origin=self.headers.get('Origin')
  if origin and origin not in ('https://chatgpt.com','https://chat.openai.com'):
   return self.reply(403,{'error':'Origin rejected'})
  if not self.authorized(): return self.reply(401,{'error':'Unauthorized'})
  try: n=int(self.headers.get('Content-Length','-1'))
  except ValueError: n=-1
  if not 0<n<=65536: return self.reply(413,{'error':'Invalid request size'})
  try:
   msg=json.loads(self.rfile.read(n))
   if not isinstance(msg,dict): raise ValueError('JSON-RPC object required')
   if msg.get('jsonrpc')!='2.0': raise ValueError('JSON-RPC 2.0 required')
   res=dispatch(msg)
   if res is None:
    self.send_response(202);self.send_header('Content-Length','0');self.end_headers();return
   self.reply(200,res)
  except (ValueError,FileNotFoundError,json.JSONDecodeError) as exc:
   self.reply(200,{'jsonrpc':'2.0','id':msg.get('id') if isinstance(locals().get('msg'),dict) else None,
                   'error':{'code':-32602,'message':str(exc)[:120]}})

if __name__=='__main__':
 if len(KEY)<32: raise SystemExit('Missing API key')
 ThreadingHTTPServer(('127.0.0.1',8787),Handler).serve_forever()
