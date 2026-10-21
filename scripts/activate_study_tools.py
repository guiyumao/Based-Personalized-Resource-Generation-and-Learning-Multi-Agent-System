"""Back up the actual user-service DB, rehearse additive tables on its copy, then reload only 8001."""
import argparse
import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path

import psutil
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


def counts(path):
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        return {table:db.execute('select count(*) from '+table).fetchone()[0] for table in ('users','study_notes','review_cards')}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user-pid',type=int,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--activate-current-runtime',action='store_true',required=True)
    args=parser.parse_args()
    process=psutil.Process(args.user_pid)
    assert 'services.user_service.app.main:app' in process.cmdline()
    env=process.environ()
    source=Path(make_url(env['DATABASE_URL']).database).resolve(strict=True)
    root=args.output.resolve()
    root.mkdir(parents=True,exist_ok=False)
    before=counts(source)
    backup=root/'runtime-backup.sqlite'
    rehearsal=root/'rehearsal.sqlite'
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as db:
        for target in (backup,rehearsal):
            with sqlite3.connect(target) as destination:
                db.backup(destination)
                assert destination.execute('pragma quick_check').fetchone()[0]=='ok'
    from common.models.study import CardKnowledgeBinding, CardReviewReceipt, NoteRevision
    models=(NoteRevision,CardKnowledgeBinding,CardReviewReceipt)
    for target in (rehearsal,source):
        engine=create_engine('sqlite:///'+target.as_posix(),connect_args={'timeout':30})
        with engine.begin() as connection:
            note_columns={column['name'] for column in inspect(connection).get_columns('study_notes')}
            # Historical runtime was bootstrapped without 0028's nullable
            # columns. Rehearse this explicit additive compatibility delta too.
            for name, ddl in (('learning_context_id','VARCHAR(36) REFERENCES learning_contexts(id)'),
                              ('source_resource_version','VARCHAR(64)'),('source_locator','VARCHAR(300)')):
                if name not in note_columns:
                    connection.execute(text(f'ALTER TABLE study_notes ADD COLUMN {name} {ddl}'))
            for model in models:
                if inspect(connection).has_table(model.__tablename__):
                    assert {c['name'] for c in inspect(connection).get_columns(model.__tablename__)}==set(model.__table__.columns.keys())
                else:
                    model.__table__.create(connection)
        engine.dispose()
        assert counts(target)==before
    executable,command,cwd=process.exe(),process.cmdline()[1:],process.cwd()
    process.terminate()
    process.wait(timeout=20)
    with (root/'user-service.log').open('wb') as log:
        child=subprocess.Popen([executable,*command],cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    time.sleep(3)
    state={'user_pid':child.pid,'old_pid':args.user_pid,'source_database':str(source),'backup':str(backup),
           'rehearsal_passed':True,'old_row_counts_preserved':before,'added_tables':[model.__tablename__ for model in models],
           'nullable_note_compatibility_columns':['learning_context_id','source_resource_version','source_locator'],
           'alembic_stamped':False,'other_services_restarted':False}
    (root/'state.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    assert child.poll() is None,'User service did not start; see local log'
    print(json.dumps({'user_pid':child.pid,'backup_verified':True,'copy_rehearsal_passed':True}))


if __name__=='__main__':
    main()
