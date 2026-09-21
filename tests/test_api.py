import json, os, subprocess, tempfile, time, unittest, urllib.error, urllib.request

class ApiTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.db=tempfile.NamedTemporaryFile(delete=False); cls.db.close(); cls.port='18765'; env={**os.environ,'PORT':cls.port,'JASINE_DB':cls.db.name}
  cls.proc=subprocess.Popen(['python','server.py'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  for _ in range(30):
   try: urllib.request.urlopen(f'http://localhost:{cls.port}/api/health'); break
   except Exception: time.sleep(.1)
 @classmethod
 def tearDownClass(cls): cls.proc.terminate(); cls.proc.wait(); os.unlink(cls.db.name)
 def req(self,path,method='GET',body=None,token=None):
  headers={'Content-Type':'application/json'}
  if token:headers['Authorization']='Bearer '+token
  r=urllib.request.urlopen(urllib.request.Request(f'http://localhost:{self.port}/api'+path,json.dumps(body).encode() if body is not None else None,headers,method=method)); return r,json.load(r) if r.headers.get_content_type()=='application/json' else None
 def test_complete_cross_conversation_memory_loop_and_feedback(self):
  _,a=self.req('/register','POST',{'email':'a@example.com','password':'strongpass'}); t=a['token']
  _,c=self.req('/conversations','POST',{},t); cid=c['id']
  r,_=self.req(f'/conversations/{cid}/chat','POST',{'message':"My dog's name is Pixel."},t); lines=[json.loads(x) for x in r.read().splitlines()]; self.assertEqual(lines[-1]['type'],'done')
  _,c2=self.req('/conversations','POST',{},t); r,_=self.req(f"/conversations/{c2['id']}/chat",'POST',{'message':"What is my dog's name?"},t); recalled=''.join(json.loads(x).get('text','') for x in r.read().splitlines()); self.assertIn('Pixel',recalled)
  r,_=self.req(f"/conversations/{c2['id']}/chat",'POST',{'message':"My dog's name is Luna now."},t); r.read()
  _,c3=self.req('/conversations','POST',{},t); r,_=self.req(f"/conversations/{c3['id']}/chat",'POST',{'message':"What is my dog's name?"},t); events=[json.loads(x) for x in r.read().splitlines()]; self.assertIn('Luna',''.join(x.get('text','') for x in events))
  assistant=events[-1]['messageId']; _,saved=self.req('/feedback','POST',{'messageId':assistant,'kind':'up'},t); self.assertTrue(saved['saved'])
  _,reflection=self.req('/reflections','POST',{},t); self.assertIn('Luna',reflection['content'])
  _,messages=self.req('/messages?conversationId='+c3['id'],token=t); self.assertEqual(len(messages),2)
  _,forgot=self.req('/memories/forget','POST',{'query':"dog's name Luna"},t); self.assertGreater(forgot['forgotten'],0)
  _,hits=self.req("/memories/search?q=dog%27s%20name%20Luna",token=t); self.assertEqual(hits,[])
 def test_authentication_required(self):
  with self.assertRaises(urllib.error.HTTPError) as x:self.req('/conversations')
  self.assertEqual(x.exception.code,401)

if __name__=='__main__': unittest.main()
