#!/usr/bin/env python3
import hashlib, hmac, json, mimetypes, os, re, secrets, time
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from app.database import Database
from app.brain import BrainService, now

ROOT=Path(__file__).parent; db=Database(os.getenv('JASINE_DB',str(ROOT/'jasine.db'))); brain=BrainService(db)
def password(raw,salt=None):
 salt=salt or secrets.token_hex(16); digest=hashlib.pbkdf2_hmac('sha256',raw.encode(),bytes.fromhex(salt),240000).hex(); return salt+'$'+digest
def check(raw,encoded):
 salt=encoded.split('$')[0]; return hmac.compare_digest(password(raw,salt),encoded)

class API(BaseHTTPRequestHandler):
 server_version='Jasine/1.0'
 protocol_version='HTTP/1.1'
 rate_buckets={}
 def log_message(self,fmt,*args): print('[jasine]',fmt%args)
 def send_json(self,status,obj):
  data=json.dumps(obj).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',len(data)); self.end_headers(); self.wfile.write(data)
 def body(self):
  try: return json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))) or b'{}')
  except Exception: return None
 def user(self):
  token=self.headers.get('Authorization','').removeprefix('Bearer ').strip()
  return db.one("SELECT users.* FROM sessions JOIN users ON users.id=sessions.user_id WHERE token=? AND expires_at>?",(token,now())) if token else None
 def require(self):
  u=self.user()
  if not u: self.send_json(401,{'error':'Authentication required'})
  return u
 def limited(self,key,maximum=90,window=60):
  stamp=time.time(); bucket=[x for x in self.rate_buckets.get(key,[]) if stamp-x<window]
  if len(bucket)>=maximum:
   self.send_json(429,{'error':'Too many requests. Please wait a moment.'}); return True
  bucket.append(stamp); self.rate_buckets[key]=bucket; return False
 def conversation(self,cid,uid): return db.one('SELECT * FROM conversations WHERE id=? AND user_id=?',(cid,uid))
 def do_GET(self):
  p=urlparse(self.path); path=p.path
  if path=='/api/health': return self.send_json(200,{'status':'ok'})
  if path=='/api/me':
   u=self.require(); return self.send_json(200,{'id':u['id'],'email':u['email'],'developer':bool(u['is_developer'])}) if u else None
  if path.startswith('/api/'):
   u=self.require()
   if not u:return
   if path=='/api/conversations': return self.send_json(200,[dict(x) for x in db.all('SELECT * FROM conversations WHERE user_id=? ORDER BY updated_at DESC',(u['id'],))])
   if path=='/api/messages':
    cid=parse_qs(p.query).get('conversationId',[''])[0]
    if not self.conversation(cid,u['id']): return self.send_json(404,{'error':'Conversation not found'})
    return self.send_json(200,[dict(x) for x in db.all('SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at',(cid,))])
   m=re.fullmatch(r'/api/conversations/([^/]+)',path)
   if m:
    c=self.conversation(m.group(1),u['id'])
    if not c:return self.send_json(404,{'error':'Not found'})
    return self.send_json(200,{**dict(c),'messages':[dict(x) for x in db.all('SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at',(c['id'],))]})
   if path=='/api/memories': return self.send_json(200,[dict(x) for x in db.all('SELECT * FROM memories WHERE user_id=? ORDER BY active DESC,updated_at DESC',(u['id'],))])
   if path=='/api/memories/search': return self.send_json(200,brain.retrieve(u['id'],parse_qs(p.query).get('q',[''])[0]))
   if path=='/api/entities': return self.send_json(200,{'entities':[dict(x) for x in db.all('SELECT * FROM entities WHERE user_id=?',(u['id'],))],'relationships':[dict(x) for x in db.all('SELECT * FROM relationships WHERE user_id=?',(u['id'],))]})
   if path=='/api/reflections': return self.send_json(200,[dict(x) for x in db.all('SELECT * FROM reflections WHERE user_id=?',(u['id'],))])
   if path=='/api/inspector':
    if not u['is_developer']: return self.send_json(403,{'error':'Developer access required'})
    return self.send_json(200,{k:[dict(x) for x in db.all(f'SELECT * FROM {k} WHERE user_id=? ORDER BY created_at DESC LIMIT 100',(u['id'],))] for k in ('memories','entities','relationships','reflections','feedback','model_runs')})
   return self.send_json(404,{'error':'Unknown endpoint'})
  file=ROOT/'index.html' if path=='/' else ROOT/'web'/path.lstrip('/')
  if not file.is_file() or (file != ROOT/'index.html' and ROOT/'web' not in file.resolve().parents): file=ROOT/'index.html'
  data=file.read_bytes(); self.send_response(200); self.send_header('Content-Type',mimetypes.guess_type(file)[0] or 'text/plain'); self.send_header('Content-Length',len(data)); self.end_headers(); self.wfile.write(data)
 def do_POST(self):
  path=urlparse(self.path).path; b=self.body()
  if b is None:return self.send_json(400,{'error':'Invalid JSON'})
  if path=='/api/register':
   if self.limited('auth:'+self.client_address[0],10,60): return
   email=str(b.get('email','')).strip().lower(); pw=str(b.get('password',''))
   if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email) or len(pw)<8:return self.send_json(422,{'error':'Valid email and 8+ character password required'})
   try: uid=db.id(); db.run('INSERT INTO users VALUES(?,?,?,?,?)',(uid,email,password(pw),now(),int(os.getenv('JASINE_DEV_EMAIL')==email)))
   except Exception:return self.send_json(409,{'error':'Account already exists'})
   return self.session(uid)
  if path=='/api/login':
   if self.limited('auth:'+self.client_address[0],10,60): return
   u=db.one('SELECT * FROM users WHERE email=?',(str(b.get('email','')).lower(),))
   if not u or not check(str(b.get('password','')),u['password_hash']): return self.send_json(401,{'error':'Invalid credentials'})
   return self.session(u['id'])
  u=self.require()
  if not u:return
  if self.limited('user:'+u['id']): return
  if path=='/api/logout':
   token=self.headers.get('Authorization','').removeprefix('Bearer ').strip(); db.run('DELETE FROM sessions WHERE token=? AND user_id=?',(token,u['id'])); return self.send_json(200,{'signedOut':True})
  if path=='/api/conversations':
   cid=db.id(); ts=now(); title=str(b.get('title') or 'New conversation')[:80]; db.run('INSERT INTO conversations VALUES(?,?,?,?,?)',(cid,u['id'],title,ts,ts)); return self.send_json(201,{'id':cid,'title':title,'created_at':ts,'updated_at':ts})
  if path=='/api/memories/forget':
   query=str(b.get('query','')).strip()[:500]
   if not query:return self.send_json(422,{'error':'A memory description is required'})
   return self.send_json(200,{'forgotten':brain.forget(u['id'],query)})
  if path=='/api/reflections':
   reflection=brain.reflect(u['id']); return self.send_json(201,reflection or {'content':'There is not enough knowledge to reflect on yet.'})
  if path=='/api/feedback':
   kind=b.get('kind'); mid=b.get('messageId')
   owned=db.one('SELECT m.id FROM messages m JOIN conversations c ON c.id=m.conversation_id WHERE m.id=? AND c.user_id=?',(mid,u['id']))
   if kind not in ('up','down','correction','regenerate') or not owned:return self.send_json(422,{'error':'Invalid feedback'})
   comment=str(b.get('comment','')).strip()[:1000]
   db.run('INSERT INTO feedback VALUES(?,?,?,?,?,?)',(db.id(),u['id'],mid,kind,comment,now()))
   learned=[]
   if kind=='correction' and comment:
    message=db.one('SELECT conversation_id FROM messages WHERE id=?',(mid,)); learned=brain.extract(u['id'],message['conversation_id'],mid,comment)
   return self.send_json(201,{'saved':True,'memoryWrites':len(learned)})
  m=re.fullmatch(r'/api/conversations/([^/]+)/chat',path)
  if m:return self.chat(u,m.group(1),str(b.get('message','')).strip(),b.get('parentId'))
  return self.send_json(404,{'error':'Unknown endpoint'})
 def do_PATCH(self):
  u=self.require(); b=self.body()
  if not u or b is None:return
  m=re.fullmatch(r'/api/conversations/([^/]+)',urlparse(self.path).path)
  if not m or not self.conversation(m.group(1),u['id']):return self.send_json(404,{'error':'Not found'})
  db.run('UPDATE conversations SET title=?,updated_at=? WHERE id=?',(str(b.get('title','Untitled'))[:80],now(),m.group(1))); self.send_json(200,{'updated':True})
 def do_DELETE(self):
  u=self.require()
  if not u:return
  m=re.fullmatch(r'/api/conversations/([^/]+)',urlparse(self.path).path)
  if not m or not self.conversation(m.group(1),u['id']):return self.send_json(404,{'error':'Not found'})
  db.run('DELETE FROM conversations WHERE id=?',(m.group(1),)); self.send_json(200,{'deleted':True})
 def session(self,uid):
  token=secrets.token_urlsafe(32); expires=(datetime.now(timezone.utc)+timedelta(days=30)).isoformat(); db.run('INSERT INTO sessions VALUES(?,?,?)',(token,uid,expires)); self.send_json(200,{'token':token})
 def chat(self,u,cid,text,parent):
  if not self.conversation(cid,u['id']):return self.send_json(404,{'error':'Conversation not found'})
  if not text or len(text)>12000:return self.send_json(422,{'error':'Message must be 1–12,000 characters'})
  start=time.time(); umid=db.id(); ts=now(); db.run('INSERT INTO messages VALUES(?,?,?,?,?,?)',(umid,cid,'user',text,ts,parent))
  if db.one('SELECT count(*) n FROM messages WHERE conversation_id=?',(cid,))['n']==1: db.run('UPDATE conversations SET title=? WHERE id=?',(text[:55],cid))
  if re.search(r'\bforget\b',text,re.I): count=brain.forget(u['id'],re.sub(r'.*?\bforget\b','',text,flags=re.I)); answer=f"Done — I deactivated {count} relevant memor{'y' if count==1 else 'ies'} so they will no longer be retrieved."
  else:
   memories=brain.retrieve(u['id'],text); messages=[dict(x) for x in db.all('SELECT role,content FROM messages WHERE conversation_id=? ORDER BY created_at DESC LIMIT 16',(cid,))][::-1]
   ctx=brain.context(memories,messages,text)
   try: answer=brain.answer(ctx,memories); err=None
   except Exception as e: answer='I could not reach the configured language model. Please try again.'; err=str(e)
  amid=db.id(); db.run('INSERT INTO messages VALUES(?,?,?,?,?,?)',(amid,cid,'assistant',answer,now(),umid)); writes=brain.extract(u['id'],cid,umid,text); db.run('UPDATE conversations SET updated_at=? WHERE id=?',(now(),cid))
  direct_count=db.one("SELECT count(*) n FROM memories WHERE user_id=? AND type!='reflection'",(u['id'],))['n']
  if writes and direct_count%5==0: brain.reflect(u['id'])
  db.run('INSERT INTO model_runs VALUES(?,?,?,?,?,?,?,?,?,?)',(db.id(),u['id'],cid,os.getenv('JASINE_MODEL','local-grounded'),int((time.time()-start)*1000),None,json.dumps([{'id':m['id'],'score':m['score']} for m in locals().get('memories',[])]),json.dumps(writes),locals().get('err'),now()))
  # Send each event immediately. Connection-close framing works with browsers and
  # avoids buffering the full response behind a Content-Length header.
  self.send_response(200); self.send_header('Content-Type','application/x-ndjson'); self.send_header('Cache-Control','no-cache, no-transform'); self.send_header('X-Accel-Buffering','no'); self.send_header('Connection','close'); self.end_headers()
  for i in range(0,len(answer),24):
   self.wfile.write((json.dumps({'type':'delta','text':answer[i:i+24]})+'\n').encode()); self.wfile.flush()
  self.wfile.write((json.dumps({'type':'done','messageId':amid})+'\n').encode()); self.wfile.flush(); self.close_connection=True

if __name__=='__main__':
 port=int(os.getenv('PORT','8000')); print(f'Jasine running at http://localhost:{port}'); ThreadingHTTPServer(('0.0.0.0',port),API).serve_forever()
