import sqlite3, threading, uuid

SCHEMA='''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,created_at TEXT NOT NULL,is_developer INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,title TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS conversations_owner ON conversations(user_id,updated_at DESC);
CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,role TEXT NOT NULL CHECK(role IN('user','assistant','system')),content TEXT NOT NULL,created_at TEXT NOT NULL,parent_id TEXT);
CREATE INDEX IF NOT EXISTS messages_conversation ON messages(conversation_id,created_at);
CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,type TEXT NOT NULL,content TEXT NOT NULL,importance REAL NOT NULL,confidence REAL NOT NULL,embedding TEXT NOT NULL,source_conversation_id TEXT,source_message_id TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,last_accessed_at TEXT,access_count INTEGER DEFAULT 0,active INTEGER DEFAULT 1,supersedes_id TEXT,superseded_by_id TEXT,valid_from TEXT,valid_until TEXT,subject_key TEXT,metadata TEXT);
CREATE INDEX IF NOT EXISTS memory_owner_active ON memories(user_id,active,type);
CREATE TABLE IF NOT EXISTS entities(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,name TEXT NOT NULL,type TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(user_id,name));
CREATE TABLE IF NOT EXISTS relationships(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,from_entity_id TEXT NOT NULL,to_entity_id TEXT NOT NULL,type TEXT NOT NULL,memory_id TEXT,created_at TEXT NOT NULL,UNIQUE(user_id,from_entity_id,to_entity_id,type,memory_id));
CREATE TABLE IF NOT EXISTS feedback(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,message_id TEXT NOT NULL,kind TEXT NOT NULL,comment TEXT,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reflections(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,content TEXT NOT NULL,provenance TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS model_runs(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,conversation_id TEXT NOT NULL,model TEXT NOT NULL,latency_ms INTEGER,token_usage INTEGER,retrieval TEXT,memory_writes TEXT,error TEXT,created_at TEXT NOT NULL);
'''
class Database:
 def __init__(self,path): self.path=path; self.local=threading.local(); self.conn().executescript(SCHEMA)
 def conn(self):
  if not hasattr(self.local,'c'): self.local.c=sqlite3.connect(self.path,check_same_thread=False); self.local.c.row_factory=sqlite3.Row
  return self.local.c
 def run(self,sql,args=()): c=self.conn().execute(sql,args); self.conn().commit(); return c
 def one(self,sql,args=()): return self.conn().execute(sql,args).fetchone()
 def all(self,sql,args=()): return self.conn().execute(sql,args).fetchall()
 @staticmethod
 def id(): return str(uuid.uuid4())
