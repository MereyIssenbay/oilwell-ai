"""Durable replay transactions. Memory implementation is test injection only."""
from __future__ import annotations
from copy import deepcopy
from contextlib import contextmanager
import json
from pathlib import Path
import threading
from backend.app.errors import ServiceError
from backend.app.repository import PostgresRepository

ACTIVE = {'created','running','paused'}

class PostgresReplayRepository(PostgresRepository):
    def initialize(self):
        super().initialize()
        with self._connection() as connection:
            connection.execute('SELECT pg_advisory_xact_lock(%s)', (64934935862810,))
            connection.execute((Path(__file__).resolve().parents[1]/'migrations/002_historical_replay.sql').read_text(), prepare=False)
            connection.execute((Path(__file__).resolve().parents[1]/'migrations/003_dashboard_indexes.sql').read_text(), prepare=False)

    @contextmanager
    def _connection(self):
        import psycopg
        try:
            with self._connect() as connection:
                yield connection
        except psycopg.Error as exc:
            raise ServiceError('DATABASE_UNAVAILABLE','Replay database is unavailable',503) from exc

    def create(self, key, digest, build):
        from psycopg.types.json import Jsonb
        with self._connection() as c:
            c.execute('SELECT pg_advisory_xact_lock(%s)', (64934935862811,))
            existing = c.execute("SELECT request_sha256,response FROM oilwell_replay_requests WHERE scope='create' AND key=%s", (key,)).fetchone()
            if existing:
                return _retry(existing,digest), True
            if c.execute("SELECT 1 FROM oilwell_replays WHERE state IN ('created','running','paused') LIMIT 1").fetchone():
                raise ServiceError('REPLAY_ACTIVE','Only one replay may be active',409)
            s, events = build()
            c.execute('INSERT INTO oilwell_replays(replay_id,state,payload) VALUES(%s,%s,%s)', (s['replay_id'],s['state'],Jsonb(s)))
            self._append(c,s,events)
            c.execute("INSERT INTO oilwell_replay_requests(scope,key,request_sha256,response) VALUES('create',%s,%s,%s)", (key,digest,Jsonb(s)))
            return s,False

    def atomic(self, replay_id, operation, *, key=None, digest=None):
        from psycopg.types.json import Jsonb
        with self._connection() as c:
            row = c.execute('SELECT payload,due_at FROM oilwell_replays WHERE replay_id=%s FOR UPDATE', (str(replay_id),)).fetchone()
            if not row:
                raise ServiceError('REPLAY_NOT_FOUND','Replay not found',404)
            scope = str(replay_id)
            if key is not None:
                existing = c.execute('SELECT request_sha256,response FROM oilwell_replay_requests WHERE scope=%s AND key=%s', (scope,key)).fetchone()
                if existing:
                    return _retry(existing,digest),True
            s,due = row
            result,events,due = operation(s,due)
            if events or key is not None:
                c.execute('UPDATE oilwell_replays SET state=%s,payload=%s,due_at=%s WHERE replay_id=%s', (s['state'],Jsonb(s),due,scope))
            self._append(c,s,events)
            if key is not None:
                c.execute('INSERT INTO oilwell_replay_requests(scope,key,request_sha256,response) VALUES(%s,%s,%s,%s)', (scope,key,digest,Jsonb(result)))
                return result,False
            return result

    def _append(self,c,s,events):
        from psycopg.types.json import Jsonb
        for e in events:
            c.execute('INSERT INTO oilwell_replay_events(replay_id,sequence,event_type,payload) VALUES(%s,%s,%s,%s)', (s['replay_id'],e['sequence'],e['event_type'],Jsonb(e)))

    def get(self,replay_id):
        with self._connection() as c:
            row = c.execute('SELECT payload FROM oilwell_replays WHERE replay_id=%s',(str(replay_id),)).fetchone()
            if not row:
                raise ServiceError('REPLAY_NOT_FOUND','Replay not found',404)
            return row[0]

    def running(self):
        with self._connection() as c:
            return [str(r[0]) for r in c.execute("SELECT replay_id FROM oilwell_replays WHERE state='running'").fetchall()]

    def list_replays(self, cursor: str | None = None, limit: int = 100) -> dict:
        from backend.app.dashboard import decode_replay_cursor, replay_list_page
        boundary = decode_replay_cursor(cursor)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ServiceError('INVALID_CURSOR', 'Replay list limit is invalid', 400)
        with self._connection() as c:
            if boundary is None:
                rows = c.execute('SELECT created_at,replay_id,payload FROM oilwell_replays '
                                 'ORDER BY created_at DESC,replay_id DESC LIMIT %s', (limit + 1,)).fetchall()
            else:
                rows = c.execute('SELECT created_at,replay_id,payload FROM oilwell_replays '
                                 'WHERE (created_at,replay_id)<(%s,%s) '
                                 'ORDER BY created_at DESC,replay_id DESC LIMIT %s',
                                 (*boundary, limit + 1)).fetchall()
        return replay_list_page(rows, limit)

    def events(self,replay_id,after_sequence=0,limit=1000,kind=None):
        with self._connection() as c:
            row = c.execute('SELECT payload FROM oilwell_replays WHERE replay_id=%s',(str(replay_id),)).fetchone()
            if not row:
                raise ServiceError('REPLAY_NOT_FOUND','Replay not found',404)
            _cursor(row[0],after_sequence,limit)
            if kind is None:
                rows = c.execute('SELECT payload FROM oilwell_replay_events WHERE replay_id=%s AND sequence>%s ORDER BY sequence LIMIT %s',(str(replay_id),after_sequence,limit+1)).fetchall()
            else:
                rows = c.execute('SELECT payload FROM oilwell_replay_events WHERE replay_id=%s AND sequence>%s AND event_type=%s ORDER BY sequence LIMIT %s',(str(replay_id),after_sequence,kind,limit+1)).fetchall()
            values = [r[0] for r in rows]
            return _page(values,limit)

def _retry(existing,digest):
    if existing[0] != digest:
        raise ServiceError('IDEMPOTENCY_CONFLICT','Idempotency key was used for another request',409)
    return deepcopy(existing[1])

def _cursor(s,after,limit):
    if type(after) is not int or not 0 <= after <= s['last_sequence'] or type(limit) is not int or not 1 <= limit <=1000:
        raise ServiceError('INVALID_CURSOR','Replay cursor or limit is invalid',400)

def _page(values,limit):
    return {'items':values[:limit], 'next_after_sequence':values[limit-1]['sequence'] if len(values)>limit else None}

class MemoryReplayRepository:
    def __init__(self):
        self.sessions={}; self.history={}; self.requests={}; self.due={}; self.lock=threading.RLock()
    def initialize(self):
        pass
    def create(self,key,digest,build):
        with self.lock:
            if ('create',key) in self.requests:
                return _retry(self.requests['create',key],digest),True
            if any(s['state'] in ACTIVE for s in self.sessions.values()):
                raise ServiceError('REPLAY_ACTIVE','Only one replay may be active',409)
            s,events=build(); rid=s['replay_id']
            self.sessions[rid]=deepcopy(s); self.history[rid]=deepcopy(events); self.due[rid]=None
            self.requests['create',key]=(digest,deepcopy(s))
            return deepcopy(s),False
    def atomic(self,replay_id,operation,*,key=None,digest=None):
        with self.lock:
            rid=str(replay_id); s=self.get(rid)
            if key is not None and (rid,key) in self.requests:
                return _retry(self.requests[rid,key],digest),True
            result,events,due=operation(s,self.due[rid])
            self.sessions[rid]=deepcopy(s); self.history[rid].extend(deepcopy(events)); self.due[rid]=due
            if key is not None:
                self.requests[rid,key]=(digest,deepcopy(result)); return deepcopy(result),False
            return deepcopy(result)
    def get(self,replay_id):
        with self.lock:
            if str(replay_id) not in self.sessions:
                raise ServiceError('REPLAY_NOT_FOUND','Replay not found',404)
            return deepcopy(self.sessions[str(replay_id)])
    def running(self):
        with self.lock:
            return [rid for rid,s in self.sessions.items() if s['state']=='running']
    def list_replays(self, cursor: str | None = None, limit: int = 100) -> dict:
        from datetime import datetime
        from uuid import UUID
        from backend.app.dashboard import decode_replay_cursor, replay_list_page
        boundary = decode_replay_cursor(cursor)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ServiceError('INVALID_CURSOR', 'Replay list limit is invalid', 400)
        with self.lock:
            rows = [(datetime.fromisoformat(s['created_at'].replace('Z', '+00:00')), UUID(rid), deepcopy(s))
                    for rid, s in self.sessions.items()]
            rows.sort(key=lambda row: (row[0], row[1]), reverse=True)
            if boundary is not None:
                rows = [row for row in rows if (row[0], row[1]) < boundary]
            return replay_list_page(rows[:limit + 1], limit)
    def events(self,replay_id,after_sequence=0,limit=1000,kind=None):
        with self.lock:
            s=self.get(replay_id); _cursor(s,after_sequence,limit)
            values=[deepcopy(e) for e in self.history[str(replay_id)] if e['sequence']>after_sequence and (kind is None or e['event_type']==kind)]
            return _page(values,limit)
