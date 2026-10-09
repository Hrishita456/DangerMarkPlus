import argparse
import json
from app.services.evacuation import get_evacuation

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Plan using an existing Phase 3 run; no acquisition or flood recomputation.')
    parser.add_argument('run_id')
    args=parser.parse_args()
    result=get_evacuation(args.run_id)
    print(json.dumps({'run_id':result['run_id'],'planning_id':result['planning_id'],'counts':result['counts']},indent=2))
