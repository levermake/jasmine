import os, tempfile, unittest
from app.database import Database
from app.brain import BrainService, embed, similarity, now

class BrainTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.NamedTemporaryFile(delete=False); self.tmp.close(); self.db=Database(self.tmp.name); self.brain=BrainService(self.db)
  self.u1,self.u2='u1','u2'
  for uid in (self.u1,self.u2): self.db.run('INSERT INTO users(id,email,password_hash,created_at) VALUES(?,?,?,?)',(uid,uid+'@test.dev','x',now()))
  self.db.run('INSERT INTO conversations VALUES(?,?,?,?,?)',('c1',self.u1,'First',now(),now()))
 def tearDown(self): os.unlink(self.tmp.name)
 def learn(self,text,uid=None):
  uid=uid or self.u1; mid=self.db.id(); self.db.run('INSERT INTO messages VALUES(?,?,?,?,?,?)',(mid,'c1','user',text,now(),None)); return self.brain.extract(uid,'c1',mid,text)
 def test_embedding_similarity_and_ranking(self):
  self.assertGreater(similarity(embed('dog Pixel'),embed('my dog Pixel')),similarity(embed('dog Pixel'),embed('database postgres')))
  self.learn("My dog's name is Pixel."); hits=self.brain.retrieve(self.u1,"What is my dog's name?"); self.assertIn('Pixel',hits[0]['content']); self.assertIn('score',hits[0])
 def test_memory_creation_metadata_and_persistence(self):
  ids=self.learn('My favorite editor is Neovim.'); self.assertTrue(ids); row=self.db.one('SELECT * FROM memories WHERE id=?',(ids[0],)); self.assertEqual(row['type'],'semantic'); self.assertEqual(row['access_count'],0)
  other=Database(self.tmp.name); self.assertEqual(other.one('SELECT count(*) n FROM memories')['n'],1)
 def test_user_isolation(self):
  self.learn('My secret is marigold.'); self.assertEqual(self.brain.retrieve(self.u2,'secret marigold'),[])
 def test_correction_preserves_and_supersedes(self):
  first=self.learn("My dog's name is Pixel.")[0]; second=self.learn("My dog's name is Luna now.")[0]
  old=self.db.one('SELECT * FROM memories WHERE id=?',(first,)); new=self.db.one('SELECT * FROM memories WHERE id=?',(second,))
  self.assertFalse(old['active']); self.assertEqual(old['superseded_by_id'],second); self.assertEqual(new['supersedes_id'],first)
  self.assertIn('Luna',self.brain.retrieve(self.u1,"dog's name")[0]['content'])
 def test_forgetting_deactivates_retrieval(self):
  self.learn('My favorite editor is Neovim.'); self.assertGreater(self.brain.forget(self.u1,'favorite editor Neovim'),0); self.assertEqual(self.brain.retrieve(self.u1,'favorite editor Neovim'),[])
 def test_context_bounds_and_injection_separation(self):
  self.learn('My preference is concise answers.'); memories=self.brain.retrieve(self.u1,'preference'); ctx=self.brain.context(memories,[{'role':'user','content':'hello'}]*30,'answer')
  self.assertIn('UNTRUSTED MEMORY DATA',ctx[0]['content']); self.assertLessEqual(len(ctx[1]['content']),10030); self.assertEqual(ctx[-1]['content'],'answer')
 def test_entity_linking(self):
  self.learn('My project is Atlas.'); self.assertIsNotNone(self.db.one("SELECT * FROM entities WHERE user_id=? AND name='Atlas'",(self.u1,)))
 def test_reflection_is_derived_and_has_provenance(self):
  self.learn('My favorite editor is Neovim.')
  reflection=self.brain.reflect(self.u1); self.assertIn('Neovim',reflection['content']); self.assertTrue(reflection['provenance'])
  memory=self.db.one("SELECT * FROM memories WHERE user_id=? AND type='reflection'",(self.u1,)); self.assertIn('derived',memory['metadata'])
  self.brain.reflect(self.u1); self.assertEqual(self.db.one('SELECT count(*) n FROM reflections')['n'],1)

if __name__=='__main__': unittest.main()
