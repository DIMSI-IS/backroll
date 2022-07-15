## Licensed to the Apache Software Foundation (ASF) under one
## or more contributor license agreements.  See the NOTICE file
## distributed with this work for additional information
## regarding copyright ownership.  The ASF licenses this file
## to you under the Apache License, Version 2.0 (the
## "License"); you may not use this file except in compliance
## with the License.  You may obtain a copy of the License at
##
##   http://www.apache.org/licenses/LICENSE-2.0
##
## Unless required by applicable law or agreed to in writing,
## software distributed under the License is distributed on an
## "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
## KIND, either express or implied.  See the License for the
## specific language governing permissions and limitations
## under the License.

#!/usr/bin/env python
import uuid as uuid_pkg
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field, Json
from sqlmodel import Session, select
from fastapi.encoders import jsonable_encoder
from celery import Celery, states
from celery.exceptions import Ignore

from app import app
from app import celery as celeryWorker
from app import celery

from app import auth
from app import database
from app.database import Policies
from app.database import Pools
from app.database import Hosts

class items_create_pool(BaseModel):
  name: str
  policy_id: uuid_pkg.UUID
  class Config:
      schema_extra = {
          "example": {
              "name": "example_pool",
              "policy_id": "49072d92-a39f-11ec-b909-0242ac120002",
          }
      }

@celery.task(name='filter_pool_by_id')
def filter_pool_by_id(pool_id):
  try:
    engine = database.init_db_connection()
  except Exception as e:
    raise HTTPException(status_code=500, detail=jsonable_encoder(e))
  try:
    with Session(engine) as session:
      statement = select(Pools).where(Pools.id == pool_id)
      results = session.exec(statement)
      pool = results.one()
      if not pool:
        reason = f'Pool with id {pool_id} not found'
        raise HTTPException(status_code=404, detail=reason)
    return pool
  except Exception as e:
    raise HTTPException(status_code=500, detail=jsonable_encoder(e))

def api_create_pool(name, policyid):
  try:
    engine = database.init_db_connection()
  except Exception as e:
    raise HTTPException(status_code=500, detail=jsonable_encoder(e))
  with Session(engine) as session:
    statement = select(Policies).where(Policies.id == policyid)
    results = session.exec(statement)
    policy = results.first()
    if not policy:
      reason = f'Policy with id {str(policyid)} not found'
      raise HTTPException(status_code=404, detail=reason)
  try:
    new_pool = Pools(name=name, policy_id=policyid)
    with Session(engine) as session:
        session.add(new_pool)
        session.commit()
        session.refresh(new_pool)
    return new_pool
  except Exception as e:
    raise HTTPException(status_code=400, detail=jsonable_encoder(e))

@celery.task(name='Update pool')
def api_update_pool(pool_id, name, policy_id):
  try:
    engine = database.init_db_connection()
  except:
    raise HTTPException(status_code=500, detail='Unable to connect to database.')
  with Session(engine) as session:
    statement = select(Pools).where(Pools.id == pool_id)
    results = session.exec(statement)
    data_pool = results.one()
  if not data_pool:
    raise HTTPException(status_code=404, detail=f'Storage with id {pool_id} not found')
  try:
    if name:
      data_pool.name = name
    if policy_id:
      data_pool.policy_id = policy_id
    with Session(engine) as session:
      session.add(data_pool)
      session.commit()
      session.refresh(data_pool)
    return jsonable_encoder(data_pool)
  except Exception as e:
    print(e)
    raise HTTPException(status_code=500, detail=jsonable_encoder(e))

def api_delete_pool(pool_id):
  try:
    engine = database.init_db_connection()
  except Exception as e:
    raise HTTPException(status_code=500, detail=jsonable_encoder(e))

  records = []
  with Session(engine) as session:
    statement = select(Hosts).where(Hosts.pool_id == pool_id)
    results = session.exec(statement)
    for host in results:
      records.append(host)
    if len(records) > 0:
      reason = f'One or more hosts are attached to this pool'
      raise HTTPException(status_code=500, detail=reason)
  try:
    pool = filter_pool_by_id(pool_id)
    with Session(engine) as session:
      session.delete(pool)
      session.commit()
    return {'state': 'SUCCESS'}
  except Exception as e:
    raise HTTPException(status_code=400, detail=jsonable_encoder(e))  


@celery.task(name='List registered pools')
def retrieve_pool():
  try:
    engine = database.init_db_connection()
  except Exception as e:
    raise HTTPException(status_code=500, detail=jsonable_encoder(e))
  records = []
  with Session(engine) as session:
      statement = select(Pools)
      results = session.exec(statement)
      for pool in results:
        records.append(pool)
  return jsonable_encoder(records)

@app.post('/api/v1/pools', status_code=201)
def create_pool(item: items_create_pool, identity: Json = Depends(auth.valid_token)):
  name = item.name
  policy_id = item.policy_id
  return api_create_pool(name, policy_id)


@app.get('/api/v1/pools', status_code=202)
def list_pools(identity: Json = Depends(auth.valid_token)):
    task = retrieve_pool.delay()
    return {'Location': app.url_path_for('retrieve_task_status', task_id=task.id)}

@app.patch('/api/v1/pools/{pool_id}', status_code=200)
def update_pool(pool_id, item: items_create_pool, identity: Json = Depends(auth.valid_token)):
  try:
      uuid_obj = uuid_pkg.UUID(pool_id)
  except ValueError:
      raise HTTPException(status_code=404, detail='Given uuid is not valid')
  name = item.name
  policy_id = item.policy_id
  return api_update_pool(pool_id, name, policy_id)

@app.delete('/api/v1/pools/{pool_id}', status_code=200)
def delete_pool(pool_id, identity: Json = Depends(auth.valid_token)):
  try:
      uuid_obj = uuid_pkg.UUID(pool_id)
  except ValueError:
      raise HTTPException(status_code=404, detail='Given uuid is not valid')

  if not pool_id: raise HTTPException(status_code=404, detail='Pool not found')
  return api_delete_pool(pool_id)