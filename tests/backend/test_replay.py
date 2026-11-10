"""Replay lifecycle, transactional persistence, and deterministic causal fixtures."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from backend.app.errors import ServiceError
from backend.app.main import create_app
from backend.app.registry import Registry,RegisteredSource
from backend.app.repository import MemoryRepository
from backend.app.replay import ReplayService
from backend.app.replay_repository import MemoryReplayRepository,PostgresReplayRepository
from backend.app.replay_schemas import CreateReplay,ReplayCommand
from backend.app.settings import Settings
from ml.data_pipeline.models import SENSOR_COLUMNS
from tests.backend.test_api import FixtureRuntime, prediction, SOURCE, WELL

class Runtime(FixtureRuntime):
    def __init__(self):
        super().__init__(); self.positions=[]; self.scores={}
    def predict(self,request,prediction_id,generated_at):
        pos=request.endpoint_position; self.positions.append(pos)
        return prediction(prediction_id,generated_at,pos,self.scores.get(pos,.8))

def components(store=None,rows=100):
    registry=Registry(Path('.')); registry.ready=True; registry.sensor_names=tuple(SENSOR_COLUMNS)
    frame=pd.DataFrame(0.,index=pd.date_range('2020-01-01',periods=rows,freq='s'),columns=SENSOR_COLUMNS)
    source=SimpleNamespace(well_id=WELL,sha256='b'*64,instance_id=SOURCE)
    registry.records={SOURCE:RegisteredSource(source,frame)}
    runtime=Runtime(); store=store or MemoryReplayRepository()
    return registry,runtime,store,ReplayService(registry,runtime,store)

def start(service,**kwargs):
    s,_=service.create(CreateReplay(source_instance_id=SOURCE,**kwargs),str(uuid4()))
    s,_=service.command(s['replay_id'],ReplayCommand(command='start',expected_version=s['version']),str(uuid4()))
    return s

def drain(service,rid):
    while service.step(rid,ignore_schedule=True):
        pass


def test_order_causality_episode_dedup_and_speed():
    registry,runtime,store,svc=components()
    s=start(svc,speed_multiplier=20.); rid=s['replay_id']
    runtime.scores[79]=.1
    drain(svc,rid)
    events=store.events(rid)['items']
    telemetry=[e for e in events if e['event_type']=='telemetry']
    assert [e['payload']['source_position'] for e in telemetry]==list(range(100))
    assert runtime.positions==[59,69,79,89,99]
    episodes=[e['payload'] for e in events if e['event_type']=='alert_episode']
    assert [e['transition'] for e in episodes]==['opened','updated','resolved','opened','updated']
    assert episodes[0]['episode_id']==episodes[1]['episode_id']
    assert episodes[0]['episode_id']!=episodes[3]['episode_id']
    assert len([e for e in episodes if e['transition']=='opened'])==2
    predictions=store.events(rid,kind='prediction')['items']
    assert predictions[0]['payload']['alert_episode']['last_prediction_at'].startswith('2020-01-01T00:00:59')
    assert predictions[2]['payload']['alert_episode'] is None
    assert store.get(rid)['state']=='completed'
    assert [e['sequence'] for e in events]==list(range(1,len(events)+1))


def test_nonzero_start_and_pause_resume_exact_cursor():
    _,runtime,store,svc=components(rows=150)
    s=start(svc,start_position=7,end_position=99);rid=s['replay_id']
    for _ in range(60):
        assert svc.step(rid,True)
    assert runtime.positions==[]
    s,_=svc.command(rid,ReplayCommand(command='pause',expected_version=s['version']),'pause')
    assert not svc.step(rid,True); assert store.get(rid)['cursor_position']==66
    resumed,_=svc.command(rid,ReplayCommand(command='resume',expected_version=s['version']),'resume')
    drain(svc,rid);assert runtime.positions==[69,79,89,99]
    repeated,replayed=svc.command(rid,ReplayCommand(command='resume',expected_version=s['version']),'resume')
    assert repeated==resumed and replayed


def test_commands_conflicts_bounds_idempotency():
    _,_,store,svc=components()
    body=CreateReplay(source_instance_id=SOURCE)
    s,_=svc.create(body,'same');again,repeated=svc.create(body,'same');assert s==again and repeated
    with pytest.raises(ServiceError,match='Only one'):
        svc.create(body,'another')
    with pytest.raises(ServiceError):
        svc.command(s['replay_id'],ReplayCommand(command='pause',expected_version=1),'bad')
    s,_=svc.command(s['replay_id'],ReplayCommand(command='set_speed',expected_version=1,speed_multiplier=.1),'speed')
    with pytest.raises(ServiceError):
        svc.command(s['replay_id'],ReplayCommand(command='start',expected_version=1),'stale')
    s,_=svc.command(s['replay_id'],ReplayCommand(command='stop',expected_version=s['version']),'stop')
    assert s['state']=='stopped'
    with pytest.raises(ServiceError):
        svc.command(s['replay_id'],ReplayCommand(command='start',expected_version=s['version']),'terminal')


def test_binding_mismatch_does_not_advance():
    registry,_,store,svc=components();s=start(svc);rid=s['replay_id']
    registry.record(SOURCE).source.sha256='f'*64
    with pytest.raises(ServiceError): svc.step(rid,True)
    assert store.get(rid)['cursor_position'] is None
    assert len(store.events(rid)['items'])==2


def test_api_stream_reconnect_and_cursor_errors():
    registry,runtime,store,svc=components(rows=60)
    registry.startup=lambda:None
    with TestClient(create_app(Settings(),registry=registry,runtime=runtime,repository=MemoryRepository(),
        replay_repository=store,replay_worker_enabled=False)) as client:
        s=client.post('/replays',json={'source_instance_id':SOURCE},headers={'Idempotency-Key':'create'}).json();rid=s['replay_id']
        assert client.post(f'/replays/{rid}/commands',json={'command':'start','expected_version':1},headers={'Idempotency-Key':'start'}).status_code==200
        drain(svc,rid)
        response=client.get(f'/replays/{rid}/events');assert response.status_code==200
        assert f'id: {rid}:1\n' in response.text
        resumed=client.get(f'/replays/{rid}/events',headers={'Last-Event-ID':f'{rid}:60'})
        assert f'id: {rid}:60\n' not in resumed.text
        assert f'id: {rid}:61\n' in resumed.text
        for cursor in ('bad',f'{uuid4()}:1',f'{rid}:999999'):
            assert client.get(f'/replays/{rid}/events',headers={'Last-Event-ID':cursor}).status_code==400
        assert client.get(f'/replays/{rid}/event-history?after_sequence=999999').status_code==400
        assert client.get(f'/replays/{rid}/predictions').json()['items'][0]['payload']['simulated_playback'] is True

@pytest.fixture
def pg_store():
    url=os.environ.get('OILWELL_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Dedicated PostgreSQL test URL is required')
    store=PostgresReplayRepository(Settings(database_url=url));store.initialize()
    with store._connection() as c:
        c.execute('TRUNCATE oilwell_replay_events,oilwell_replay_requests,oilwell_replays')
    yield store
    with store._connection() as c:
        c.execute('TRUNCATE oilwell_replay_events,oilwell_replay_requests,oilwell_replays')


def test_postgres_restart_concurrent_step_and_atomic_rollback(pg_store):
    registry,runtime,store,svc=components(pg_store,rows=60);s=start(svc);rid=s['replay_id']
    for _ in range(59):svc.step(rid,True)
    original=store._append
    def fail(c,s,events):
        original(c,s,events)
        raise RuntimeError('injected before commit')
    store._append=fail
    with pytest.raises(RuntimeError):svc.step(rid,True)
    assert store.get(rid)['cursor_position']==58
    assert not store.events(rid,kind='prediction')['items']
    store._append=original
    restarted=ReplayService(registry,runtime,PostgresReplayRepository(store.settings))
    with ThreadPoolExecutor(4) as pool:
        results=list(pool.map(lambda _:restarted.step(rid,True),range(4)))
    assert sum(results)==1
    assert store.get(rid)['state']=='completed'
    assert len(store.events(rid,kind='prediction')['items'])==1
    assert len([e for e in store.events(rid,kind='alert_episode')['items'] if e['payload']['transition']=='opened'])==1
