"""Operator CLI for a fixed isolated library namespace; four queries cannot accept arbitrary paths."""
import argparse
import json
import sys
from pathlib import Path
from bundle_contract import key,BundleError
from bundle_store import BundleStore
from learning_queries import LearningQueries

BASE=Path(__file__).resolve().parent
ENV={'app_package':'edu.sydney.transferlab','app_build':'6','environment_id':'existing-workflow-lab',
     'ui_revision':'native-multi-v6','domain':'EXPERIMENT_APP'}

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--library-id',default='p2-native-final-r28');s=p.add_subparsers(dest='operation',required=True)
    s.add_parser('list_pages')
    a=s.add_parser('inspect_page');a.add_argument('page_id')
    a=s.add_parser('inspect_region');a.add_argument('page_id');a.add_argument('region_id')
    a=s.add_parser('search_semantic_targets');a.add_argument('--text');a.add_argument('--role')
    a=p.parse_args(argv)
    try:
        key(a.library_id);path=BASE/'libraries'/(a.library_id+'.sqlite')
        with BundleStore(path,read_only=True) as store:
            q=LearningQueries(store)
            if a.operation=='list_pages':r=q.list_pages(ENV)
            elif a.operation=='inspect_page':r=q.inspect_page(ENV,a.page_id)
            elif a.operation=='inspect_region':r=q.inspect_region(ENV,a.page_id,a.region_id)
            else:r=q.search_semantic_targets(ENV,text=a.text,role=a.role)
        print(json.dumps(r,ensure_ascii=False));return 0
    except BundleError as e:
        print(json.dumps({'status':'ERROR','error':str(e),'execution_authority':False,'implicit_observe_calls':0,'device_action_calls':0}));return 1

if __name__=='__main__':raise SystemExit(main())
