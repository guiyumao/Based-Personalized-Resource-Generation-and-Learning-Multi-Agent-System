"""Private revision CAS, attributed review replay, source boundaries and task evidence."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.db.base import Base
from common.db.session import get_db
from common.learning_context import create_context
from common.models.learning import (
    CardReviewEvent,
    KnowledgePoint,
    LearningPath,
    Resource,
    ReviewCard,
    SystemSubject,
    User,
    UserProfile,
)
from common.models.study import NoteRevision
from common.resource_version import resource_version
from common.security.auth import create_access_token
from services.user_service.app.main import app


@pytest.fixture
def study(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path/'study.sqlite'}",connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine)
    with factory() as db:
        db.add_all([User(id=1,username='study-owner',password_hash='unused'),User(id=2,username='study-other',password_hash='unused')])
        db.add(SystemSubject(id=1,name='网络',code='network',description='test'))
        db.flush()
        db.add(KnowledgePoint(id=1,name='TCP',subject_id=1))
        db.add(LearningPath(id=1,user_id=1,status='active',path_data_json={'subject':'网络','stages':[{'stage_id':'s1','tasks':[{'task_id':'t1','knowledge_point':'TCP','completed':False}]}]}))
        db.add_all([Resource(id=1,type='courseware',title='TCP',content='source',knowledge_point_id=1,generated_for_user_id=1),
                    Resource(id=2,type='courseware',title='PRIVATE',content='private source',knowledge_point_id=1,generated_for_user_id=2,publish_status='published',audit_status='passed')])
        db.add(UserProfile(user_id=1,mastery_json={'graded_point':88}))
        db.commit()
        ctx=create_context(db,1,client_request_id='study-context-1',plan_id=1,module_id='s1',task_key='t1',resource_id=1,expected_resource_version=resource_version(db.get(Resource,1))).id
    def database():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db]=database
    client=TestClient(app)
    owner={'Authorization':'Bearer '+create_access_token('1')}
    other={'Authorization':'Bearer '+create_access_token('2')}
    yield client,factory,ctx,owner,other
    app.dependency_overrides.clear()
    engine.dispose()


def make_note(client,ctx,headers):
    response=client.post('/study/notes',headers=headers,json={'title':'TCP笔记','body':'先确认再重传','learning_context_id':ctx,'source_locator':'第2节'})
    assert response.status_code==201,response.text
    return response.json()


def test_history_versions_classification_and_lost_update_protection(study):
    client,factory,ctx,owner,other=study
    note=make_note(client,ctx,owner)
    assert note['classification']=={'subject':'网络','knowledge_point_id':1,'knowledge_point':'TCP'}
    assert note['source_resource_version']
    body={'title':'TCP笔记','body':'更正：累计确认','expected_version':note['version']}
    changed=client.put(f"/study/notes/{note['id']}",headers=owner,json=body)
    assert changed.status_code==200,changed.text
    assert changed.json()['source_locator']=='第2节'
    assert client.put(f"/study/notes/{note['id']}",headers=owner,json=body).status_code==409
    history=client.get(f"/study/notes/{note['id']}/history",headers=owner).json()['items']
    assert len(history)==2
    assert history[-1]['snapshot']['body']=='先确认再重传'
    assert client.get(f"/study/notes/{note['id']}/history",headers=other).status_code==404
    for params in ({'subject':'网络'},{'resource_id':1},{'knowledge_point_id':1},{'q':'累计确认'}):
        assert client.get('/study/notes',headers=owner,params=params).json()['total']==1
    assert client.get('/study/notes',headers=owner,params={'subject':'其他'}).json()['total']==0
    assert client.delete(f"/study/notes/{note['id']}",headers=owner).status_code==204
    with factory() as db:
        assert db.query(NoteRevision).count()==0


def test_card_review_replay_profile_and_task_are_one_transaction(study):
    client,factory,ctx,owner,other=study
    note=make_note(client,ctx,owner)
    card=client.post('/study/cards',headers=owner,json={'front':'如何确认？','back':'累计确认','source_note_id':note['id']}).json()
    assert card['knowledge_point_id']==1
    request={'grade':4,'client_request_id':'review-once-1'}
    endpoint=f"/study/cards/{card['id']}/review"
    first=client.post(endpoint,headers=owner,json=request)
    assert first.status_code==200,first.text
    assert first.json()['review_evidence']['review_count']==1
    assert first.json()['interval_days']==1
    assert client.post(endpoint,headers=owner,json=request).status_code==200
    assert client.post(endpoint,headers=owner,json={**request,'grade':1}).status_code==409
    assert client.post(endpoint,headers=other,json=request).status_code==404
    with factory() as db:
        assert db.query(CardReviewEvent).count()==1
        assert db.get(ReviewCard,card['id']).review_count==1
        profile=db.query(UserProfile).filter_by(user_id=1).one()
        assert profile.mastery_json['graded_point']==88
        assert profile.mastery_json['flashcard_review']['1']['recall_rate']==1
        task=db.get(LearningPath,1).path_data_json['stages'][0]['tasks'][0]
        assert not task['completed']
        assert task['learning_evidence']['flashcard_reviews'][str(card['id'])]['grade']==4
    assert client.delete(f"/study/cards/{card['id']}",headers=owner).status_code==204
    with factory() as db:
        assert not db.query(UserProfile).filter_by(user_id=1).one().mastery_json['flashcard_review']


def test_old_source_can_be_reviewed_without_writing_new_plan_evidence(study):
    client,factory,ctx,owner,_=study
    note=make_note(client,ctx,owner)
    card=client.post('/study/cards',headers=owner,json={'front':'Q','back':'A','source_note_id':note['id']}).json()
    with factory() as db:
        db.get(Resource,1).content='changed source'
        db.commit()
    response=client.post(f"/study/cards/{card['id']}/review",headers=owner,json={'grade':1,'client_request_id':'old-source-review'})
    assert response.status_code==200,response.text
    assert response.json()['interval_days']==0
    with factory() as db:
        task=db.get(LearningPath,1).path_data_json['stages'][0]['tasks'][0]
        assert 'learning_evidence' not in task
        assert db.query(CardReviewEvent).count()==1


def test_other_users_published_private_resource_cannot_be_note_source(study):
    client,_,_,owner,_=study
    response=client.post('/study/notes',headers=owner,json={'title':'test','body':'test','source_resource_id':2})
    assert response.status_code==404


def test_failed_plan_write_rolls_back_review_schedule_event_and_profile(study,monkeypatch):
    from fastapi import HTTPException

    from services.user_service.app.api.routes import study_tools
    client,factory,ctx,owner,_=study
    note=make_note(client,ctx,owner)
    card=client.post('/study/cards',headers=owner,json={'front':'Q','back':'A','source_note_id':note['id']}).json()
    original=study_tools.record_card_evidence
    def conflict(db,card,event):
        original(db,card,event)
        raise HTTPException(409,'Concurrent plan edit')
    monkeypatch.setattr(study_tools,'record_card_evidence',conflict)
    response=client.post(f"/study/cards/{card['id']}/review",headers=owner,json={'grade':4,'client_request_id':'rollback-review'})
    assert response.status_code==409
    with factory() as db:
        assert db.query(CardReviewEvent).count()==0
        assert db.get(ReviewCard,card['id']).review_count==0
        assert db.query(UserProfile).filter_by(user_id=1).one().mastery_json=={'graded_point':88}


def test_note_model_request_has_authenticated_usage_attribution(study,monkeypatch):
    from common.performance import get_current_trace
    from services.agent_service.app.services.llm_factory import LLMFactory
    client,_,ctx,owner,_=study
    note=make_note(client,ctx,owner)
    class Model:
        def invoke(self,messages):
            trace=get_current_trace()
            assert str(trace.user_id)=='1'
            assert trace.task_type==f"POST /study/notes/{note['id']}/organize"
            return type('Result',(),{'content':json.dumps({'organized_note':'verified fixture','cards':[{'front':'Q','back':'A'}]})})()
    monkeypatch.setattr(LLMFactory,'build_for_task',lambda *_args,**_kwargs:Model())
    response=client.post(f"/study/notes/{note['id']}/organize",headers=owner)
    assert response.status_code==200,response.text
    assert response.headers.get('X-Request-ID')
