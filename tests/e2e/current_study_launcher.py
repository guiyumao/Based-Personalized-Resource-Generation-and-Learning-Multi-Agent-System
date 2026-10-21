"""Current-runtime notes/cards acceptance using a clearly labeled private demo account."""
import argparse
import json
import os
import secrets
import subprocess
from pathlib import Path

import psutil

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--user-pid',type=int,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
os.environ.update(psutil.Process(args.user_pid).environ())
os.environ['APP_LOAD_DOTENV']='false'
from common.db.session import SessionLocal  # noqa: E402
from common.models.learning import KnowledgePoint, LearningPath, Resource, User, UserProfile  # noqa: E402
from common.resource_version import resource_version  # noqa: E402
from common.security.auth import create_access_token, hash_password  # noqa: E402

with SessionLocal() as db:
    user=db.query(User).filter_by(username='local-study-acceptance-20261021').first()
    if user is None:
        user=User(username='local-study-acceptance-20261021',role='student',is_active=True,password_hash=hash_password(secrets.token_urlsafe(24)))
        db.add(user);db.flush()
        db.add(UserProfile(user_id=user.id,mastery_json={}))
    resource=db.query(Resource).filter_by(assistant_operation_key='local-study-evidence-demo-20261021').first()
    if resource is None:
        point=KnowledgePoint(name='笔记闪卡验收要点',subject_id=None,construction_status='PERSONAL_DRAFT')
        db.add(point);db.flush()
        resource=Resource(title='笔记闪卡功能验收材料',type='courseware',content='# 本地功能验收\n\n本例仅用于保存、历史和复习功能验收，不是模型生成内容。',
            generated_for_user_id=user.id,knowledge_point_id=point.id,assistant_operation_key='local-study-evidence-demo-20261021',publish_status='draft')
        db.add(resource)
        plan=LearningPath(user_id=user.id,status='active',path_data_json={'subject':'功能验收学科','stages':[{'stage_id':'s1','tasks':[{'task_id':'t1','title':'功能验收任务','knowledge_point':point.name,'completed':False}]}]})
        db.add(plan);db.flush()
    else:
        plan=db.query(LearningPath).filter_by(user_id=user.id).first()
    db.commit()
    payload={'output':str(args.output.resolve()),'auth':{'token':create_access_token(str(user.id)),'user':{'userId':user.id,'username':user.username,'role':'student'}},
        'binding':{'client_request_id':'study-demo-context-20261021','plan_id':plan.id,'module_id':'s1','task_key':'t1','resource_id':resource.id,'expected_resource_version':resource_version(resource)},
        'pointId':resource.knowledge_point_id}
args.output.parent.mkdir(parents=True,exist_ok=True)
with args.output.with_suffix('.log').open('w',encoding='utf-8') as log:
    result=subprocess.run(['node','tests/e2e/verify_current_study.mjs'],input=json.dumps(payload),text=True,stdout=log,stderr=subprocess.STDOUT,timeout=300)
print('current_study_browser_exit',result.returncode)
raise SystemExit(result.returncode)
