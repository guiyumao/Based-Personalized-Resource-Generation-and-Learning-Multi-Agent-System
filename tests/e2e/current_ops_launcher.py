"""Explicit no-paid-call acceptance on an already backed-up current runtime."""
import argparse
import json
import os
import subprocess
from pathlib import Path

import psutil

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--api-pid',type=int,required=True)
parser.add_argument('--output',type=Path,required=True)
args = parser.parse_args()
os.environ.update(psutil.Process(args.api_pid).environ())
os.environ['APP_LOAD_DOTENV'] = 'false'
from common.db.session import SessionLocal  # noqa: E402
from common.models.learning import Resource, User  # noqa: E402
from common.resource_version import resource_version  # noqa: E402
from common.security.auth import create_access_token  # noqa: E402


def auth(user):
    return {'token':create_access_token(str(user.id)),
            'user':{'userId':user.id,'username':user.username,'role':user.role}}


with SessionLocal() as db:
    admin = db.query(User).filter_by(role='admin',is_active=True).first()
    student, resource = db.get(User,3), db.get(Resource,135)
    payload = {'output':str(args.output.resolve()),'admin':auth(admin),'student':auth(student),
               'binding':{'client_request_id':'current-activation-media-20261021','plan_id':144,'module_id':'1',
                          'task_key':'101','resource_id':135,'expected_resource_version':resource_version(resource)}}
    demo = db.query(Resource).filter_by(assistant_operation_key='activation-map-demo-20261021').first()
    if demo is None:
        demo = Resource(title='导图编辑验收示例',type='mind_map',format='json',generated_for_user_id=student.id,
                        knowledge_point_id=resource.knowledge_point_id,content='# 导图编辑验收示例\n\n- 主节点\n- 子节点',
                        structured_json=json.dumps({'structured':{'root_id':'root','nodes':[
                            {'id':'root','label':'主节点','parent_id':None},{'id':'child','label':'子节点','parent_id':'root'}]},
                            'source':'LOCAL_ACCEPTANCE_TEMPLATE'},ensure_ascii=False),
                        generation_status='generated',audit_status='passed',publish_status='draft',
                        assistant_operation_key='activation-map-demo-20261021')
        db.add(demo)
        db.commit()
    payload['demoMapId'] = demo.id
args.output.parent.mkdir(parents=True,exist_ok=True)
with args.output.with_suffix('.log').open('w',encoding='utf-8') as log:
    result = subprocess.run(['node','tests/e2e/verify_current_operations.mjs'],input=json.dumps(payload),text=True,
                            stdout=log,stderr=subprocess.STDOUT,timeout=360)
print('browser_exit',result.returncode)
raise SystemExit(result.returncode)
