"""Ordered causal replay, atomic episode deduplication and durable SSE."""
from __future__ import annotations
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import re
import threading
from typing import Annotated
from uuid import UUID, uuid4
from fastapi import APIRouter, Header, Query, Request, Response
from starlette.concurrency import run_in_threadpool
from starlette.responses import StreamingResponse
from backend.app.errors import ServiceError
from backend.app.schemas import PredictRequest, ErrorResponse
from backend.app.replay_schemas import (CreateReplay, ReplayCommand, ReplaySnapshot, ReplayPrediction,
    ReplayEvent, ReplayEventPage, ReplayEpisode)

TERMINAL={'stopped','completed','failed'}
LOGGER=logging.getLogger('oilwell.api')

def now():
    return datetime.now(timezone.utc)

def serialized(value):
    return value.model_dump(mode='json')

def digest(body):
    return hashlib.sha256(json.dumps(serialized(body),sort_keys=True,separators=(',',':')).encode()).hexdigest()

def key_valid(key):
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',key):
        raise ServiceError('INVALID_IDEMPOTENCY_KEY','Unsupported idempotency key',422)

class ReplayService:
    def __init__(self,registry,runtime,store):
        self.registry=registry; self.runtime=runtime; self.store=store

    def create(self,body:CreateReplay,key:str):
        key_valid(key)
        def build():
            record=self.registry.record(body.source_instance_id); info=self.runtime.info()
            end=len(record.frame)-1 if body.end_position is None else body.end_position
            if not 0<=body.start_position<=end<len(record.frame):
                raise ServiceError('INVALID_REPLAY_RANGE','Replay bounds are outside the source',422)
            # A complete source can be replayed; disk event retention is bounded by source length.
            if end-body.start_position+1>1_000_000:
                raise ServiceError('REPLAY_TOO_LARGE','Replay exceeds one million observations',422)
            if body.model_version is not None and body.model_version!=info['model_version']:
                raise ServiceError('MODEL_VERSION_MISMATCH','Requested model is unavailable',422)
            stamp=now(); rid=uuid4()
            s=serialized(ReplaySnapshot(replay_id=rid,state='created',version=1,
                source_instance_id=body.source_instance_id,well_id=record.source.well_id,
                model_version=info['model_version'],source_sha256=record.source.sha256,
                model_artifact_sha256=info['model_artifact_sha256'],preprocessor_fingerprint=info['preprocessor_fingerprint'],
                threshold=info['threshold'],speed_multiplier=body.speed_multiplier,start_position=body.start_position,
                end_position=end,cursor_position=None,source_start=record.frame.index[body.start_position].isoformat(),
                source_end=record.frame.index[end].isoformat(),cursor_timestamp=None,last_sequence=0,
                alert_episode=None,created_at=stamp,updated_at=stamp,failure=None))
            events=[]; self._state(s,events)
            return s,events
        result,repeated=self.store.create(key,digest(body),build)
        self._log('replay_created',result,repeated=repeated)
        return result,repeated

    def command(self,replay_id,body:ReplayCommand,key:str):
        key_valid(key)
        def apply(s,due):
            if s['version']!=body.expected_version:
                raise ServiceError('REPLAY_VERSION_CONFLICT','Replay version changed',409,{'current_version':s['version']})
            state=s['state']; cmd=body.command
            valid=(cmd=='start' and state=='created' or cmd=='pause' and state=='running'
                or cmd=='resume' and state=='paused' or cmd=='stop' and state not in TERMINAL
                or cmd=='set_speed' and state not in TERMINAL)
            if not valid:
                raise ServiceError('REPLAY_STATE_CONFLICT','Command is invalid in current replay state',409)
            if cmd=='set_speed':
                s['speed_multiplier']=body.speed_multiplier
            else:
                s['state']={'start':'running','resume':'running','pause':'paused','stop':'stopped'}[cmd]
            s['version']+=1; s['updated_at']=now().isoformat()
            due=now() if s['state']=='running' else None
            events=[]; self._state(s,events)
            return deepcopy(s),events,due
        result,repeated=self.store.atomic(replay_id,apply,key=key,digest=digest(body))
        self._log('replay_command_committed',result,command=body.command,repeated=repeated)
        return result,repeated

    def _log(self,event,s,**fields):
        LOGGER.info(json.dumps({'event':event,'replay_id':s['replay_id'],
            'state':s['state'],'last_sequence':s['last_sequence'],**fields},allow_nan=False))

    def _event(self,s,events,kind,payload):
        s['last_sequence']+=1
        events.append(serialized(ReplayEvent(replay_id=s['replay_id'],sequence=s['last_sequence'],
            event_type=kind,emitted_at=now(),payload=payload)))
    def _state(self,s,events):
        # Payload watermark includes its own state event.
        snapshot=deepcopy(s); snapshot['last_sequence']+=1
        self._event(s,events,'replay_state',snapshot)

    def _check_binding(self,s,record,info):
        if (record.source.sha256!=s['source_sha256'] or record.source.well_id!=s['well_id']
            or any(info[k]!=s[k] for k in ('model_version','model_artifact_sha256','preprocessor_fingerprint','threshold'))
            or s['policy_version']!='replay-episode-ge-no-dwell-v1'):
            raise ServiceError('REPLAY_BINDING_CHANGED','Frozen replay source or model no longer matches',503)

    def step(self,replay_id,ignore_schedule=False):
        committed_logs=[]
        def apply(s,due):
            stamp=now()
            if s['state']!='running' or (not ignore_schedule and due is not None and stamp<due):
                return False,[],due
            record=self.registry.record(s['source_instance_id']); info=self.runtime.info()
            self._check_binding(s,record,info)
            position=s['start_position'] if s['cursor_position'] is None else s['cursor_position']+1
            page=self.registry.telemetry(s['well_id'],s['source_instance_id'],position,1,None)
            if len(page['items'])!=1:
                raise ServiceError('REPLAY_SOURCE_UNAVAILABLE','Next source observation is unavailable',503)
            sample=page['items'][0]; events=[]
            s['cursor_position']=position; s['cursor_timestamp']=sample['timestamp']; s['updated_at']=stamp.isoformat()
            self._event(s,events,'telemetry',{'mode':'historical_replay','simulated_playback':True,
                'source_kind':s['source_kind'],'source_instance_id':s['source_instance_id'],'well_id':s['well_id'],
                'source_position':position,'time_basis':s['time_basis'],**sample})
            if position-s['start_position']>=59 and (position-59)%10==0:
                prediction=self.runtime.predict(PredictRequest(source_instance_id=s['source_instance_id'],
                    endpoint_position=position,model_version=s['model_version']),uuid4(),stamp)
                # Validate adapter identity and causal temporal bounds before any commit.
                if (prediction.model_version!=s['model_version'] or prediction.threshold!=s['threshold']
                    or prediction.provenance.source_instance_id!=s['source_instance_id']
                    or prediction.well_id!=s['well_id']
                    or prediction.provenance.model_artifact_sha256!=s['model_artifact_sha256']
                    or prediction.provenance.preprocessor_fingerprint!=s['preprocessor_fingerprint']
                    or prediction.window.sample_count!=60
                    or prediction.window.start.replace(tzinfo=None)!=record.frame.index[position-59].to_pydatetime()
                    or prediction.provenance.source_sha256!=s['source_sha256']
                    or prediction.provenance.source_timestamp!=sample['timestamp']
                    or prediction.window.start.replace(tzinfo=None)<datetime.fromisoformat(s['source_start'])
                    or prediction.window.end.replace(tzinfo=None)>datetime.fromisoformat(sample['timestamp'])):
                    raise ServiceError('REPLAY_PREDICTION_MISMATCH','Prediction does not match replay boundary',503)
                old=deepcopy(s['alert_episode']); transition=None; episode=s['alert_episode']
                if prediction.alert_status=='alert':
                    if episode is None:
                        episode=serialized(ReplayEpisode(episode_id=uuid4(),replay_id=s['replay_id'],
                            opened_by_prediction_id=prediction.prediction_id,opened_at=prediction.timestamp,
                            last_prediction_id=prediction.prediction_id,last_prediction_at=prediction.timestamp,
                            last_data_status='alert',threshold=s['threshold'],model_version=s['model_version']))
                        transition='opened'
                    else:
                        episode.update(last_prediction_id=str(prediction.prediction_id),last_prediction_at=prediction.timestamp.isoformat(),last_data_status='alert')
                        transition='updated'
                elif prediction.alert_status=='normal' and episode is not None:
                    transition='resolved'; episode=None
                elif prediction.alert_status=='insufficient_data' and episode is not None:
                    episode.update(last_prediction_id=str(prediction.prediction_id),last_prediction_at=prediction.timestamp.isoformat(),last_data_status='insufficient_data')
                    transition='updated'
                s['alert_episode']=episode
                envelope=serialized(ReplayPrediction(replay_id=s['replay_id'],sequence=s['last_sequence']+1,
                    source_position=position,speed_multiplier=s['speed_multiplier'],alert_episode=deepcopy(episode),prediction=prediction))
                self._event(s,events,'prediction',envelope)
                if transition:
                    self._event(s,events,'alert_episode',{'mode':'historical_replay','simulated_playback':True,
                        'transition':transition,'episode_id':(episode or old)['episode_id'],
                        'alert_episode':deepcopy(episode),'caused_by_prediction_id':str(prediction.prediction_id),
                        'source_position':position,'timestamp':prediction.timestamp.isoformat()})
            if position==s['end_position']:
                s['state']='completed'; s['version']+=1; due=None; self._state(s,events)
            else:
                interval=(record.frame.index[position+1]-record.frame.index[position]).total_seconds()
                due=stamp+timedelta(seconds=interval/s['speed_multiplier'])
            for event in events:
                if event['event_type'] in {'prediction','alert_episode','replay_state'}:
                    fields={'event':'replay_'+event['event_type']+'_committed','replay_id':s['replay_id'],
                        'sequence':event['sequence'],'source_position':position,'model_version':s['model_version']}
                    if event['event_type']=='prediction':
                        fields['prediction_id']=event['payload']['prediction']['prediction_id']
                    elif event['event_type']=='alert_episode':
                        fields['transition']=event['payload']['transition']; fields['episode_id']=event['payload']['episode_id']
                    committed_logs.append(fields)
            return True,events,due
        result=self.store.atomic(replay_id,apply)
        for entry in committed_logs:
            LOGGER.info(json.dumps(entry,allow_nan=False))
        return result

    def fail(self,replay_id,code):
        def apply(s,due):
            if s['state'] in TERMINAL:
                return False,[],due
            s['state']='failed'; s['version']+=1; s['updated_at']=now().isoformat()
            s['failure']={'code':code,'message':'Replay stopped; retained cursor and events remain available'}
            events=[]; self._event(s,events,'replay_error',s['failure']); self._state(s,events)
            return True,events,None
        return self.store.atomic(replay_id,apply)

class ReplayWorker:
    def __init__(self,service):
        self.service=service; self.stop_event=threading.Event(); self.thread=None; self.failures={}
    def start(self):
        self.thread=threading.Thread(target=self.run,name='oilwell-replay',daemon=True); self.thread.start()
    def stop(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=10)
    def run(self):
        while not self.stop_event.is_set():
            try:
                running=self.service.store.running()
                for rid in running:
                    try:
                        self.service.step(rid); self.failures.pop(rid,None)
                    except Exception as exc:
                        count=self.failures.get(rid,0)+1; self.failures[rid]=count
                        LOGGER.warning(json.dumps({'event':'replay_step_failed','replay_id':rid,'attempt':count,'error_code':getattr(exc,'code','REPLAY_PROCESSING_FAILED')}))
                        if count>=3:
                            self.service.fail(rid,getattr(exc,'code','REPLAY_PROCESSING_FAILED'))
            except Exception:
                LOGGER.warning(json.dumps({'event':'replay_worker_database_unavailable'}))
                self.stop_event.wait(1)
            self.stop_event.wait(.025)


def replay_router(app):
    router=APIRouter(prefix='/replays',tags=['historical replay'],responses={s:{'model':ErrorResponse} for s in (400,404,409,422,503)})
    def service():
        if not getattr(app.state,'replay_ready',False):
            raise ServiceError('REPLAY_UNAVAILABLE','Replay service is unavailable',503)
        return app.state.replay_service

    @router.post('',response_model=ReplaySnapshot,status_code=201)
    def create(body:CreateReplay,response:Response,idempotency_key:Annotated[str,Header(alias='Idempotency-Key',min_length=1,max_length=128)]):
        result,repeated=service().create(body,idempotency_key); response.headers['Idempotency-Replayed']=str(repeated).lower(); return result
    @router.get('/{replay_id}',response_model=ReplaySnapshot)
    def snapshot(replay_id:UUID):
        return service().store.get(replay_id)
    @router.post('/{replay_id}/commands',response_model=ReplaySnapshot)
    def command(replay_id:UUID,body:ReplayCommand,response:Response,idempotency_key:Annotated[str,Header(alias='Idempotency-Key',min_length=1,max_length=128)]):
        result,repeated=service().command(replay_id,body,idempotency_key); response.headers['Idempotency-Replayed']=str(repeated).lower(); return result
    @router.get('/{replay_id}/event-history',response_model=ReplayEventPage)
    def history(replay_id:UUID,after_sequence:Annotated[int,Query(ge=0)]=0,limit:Annotated[int,Query(ge=1,le=1000)]=100):
        return service().store.events(replay_id,after_sequence,limit)
    @router.get('/{replay_id}/predictions',response_model=ReplayEventPage)
    def predictions(replay_id:UUID,after_sequence:Annotated[int,Query(ge=0)]=0,limit:Annotated[int,Query(ge=1,le=1000)]=100):
        return service().store.events(replay_id,after_sequence,limit,'prediction')
    @router.get('/{replay_id}/alerts',response_model=ReplayEventPage)
    def alerts(replay_id:UUID,after_sequence:Annotated[int,Query(ge=0)]=0,limit:Annotated[int,Query(ge=1,le=1000)]=100):
        return service().store.events(replay_id,after_sequence,limit,'alert_episode')
    @router.get('/{replay_id}/events',response_class=StreamingResponse,responses={200:{'content':{'text/event-stream':{}}}})
    async def stream(replay_id:UUID,request:Request,after_sequence:Annotated[int,Query(ge=0)]=0,
        last_event_id:Annotated[str|None,Header(alias='Last-Event-ID',max_length=128)]=None):
        srv=service(); after=after_sequence
        if last_event_id is not None:
            prefix,separator,number=last_event_id.rpartition(':')
            if prefix!=str(replay_id) or not separator or not number.isascii() or not number.isdigit():
                raise ServiceError('INVALID_CURSOR','Last-Event-ID must identify this replay and sequence',400)
            after=int(number)
            if after_sequence and after_sequence!=after:
                raise ServiceError('INVALID_CURSOR','Replay cursor parameters disagree',400)
        await run_in_threadpool(srv.store.events,replay_id,after,1)
        async def generate():
            cursor=after; heartbeat=0
            while not await request.is_disconnected():
                try:
                    page=await run_in_threadpool(srv.store.events,replay_id,cursor,100)
                    for event in page['items']:
                        cursor=event['sequence']
                        yield f"id: {replay_id}:{cursor}\nevent: {event['event_type']}\ndata: {json.dumps(event,separators=(',',':'),allow_nan=False)}\n\n"
                    state=await run_in_threadpool(srv.store.get,replay_id)
                    if state['state'] in TERMINAL and cursor>=state['last_sequence']:
                        break
                    heartbeat+=1
                    if heartbeat>=20:
                        yield ': heartbeat\n\n'; heartbeat=0
                    if not page['next_after_sequence']:
                        await asyncio.sleep(.25)
                except Exception:
                    yield 'event: stream_error\ndata: {"code":"STREAM_UNAVAILABLE","message":"Reconnect using the last received event ID"}\n\n'
                    break
        return StreamingResponse(generate(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})
    return router
