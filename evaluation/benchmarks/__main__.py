import argparse,asyncio,os
from evaluation.benchmarks.common import BENCH,read,Run

def main():
    parser=argparse.ArgumentParser(description='Isolated MLAI evaluation; never targets a production backend')
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ('smoke','load','policy','suite','vlm'):
        p=sub.add_parser(name);p.add_argument('--config',default=str(BENCH/'config.json'));p.add_argument('--label',default=name)
        p.add_argument('--concurrency',type=int,nargs='+');p.add_argument('--scenarios',nargs='+',choices=['no_proof','ready','cold','mixed','contention'])
        p.add_argument('--arrival',choices=['burst','staggered','both']);p.add_argument('--repetitions',type=int)
        p.add_argument('--live-vlm',action='store_true')
    p=sub.add_parser('compare');p.add_argument('--baseline',required=True);p.add_argument('--optimized',required=True);p.add_argument('--output',required=True)
    args=parser.parse_args()
    if args.command=='compare':
        from evaluation.benchmarks.reports.compare import compare
        compare(args.baseline,args.optimized,args.output);return
    config=read(args.config)
    if args.concurrency:
        if any(n not in [1,5,10,15,20,30] for n in args.concurrency):parser.error('Supported concurrency: 1,5,10,15,20,30')
        config['concurrency_levels']=args.concurrency
    if args.scenarios:config['scenarios']=args.scenarios
    if args.arrival:config['arrival']=args.arrival
    if args.repetitions:config['repetitions']=args.repetitions
    if args.live_vlm:
        config['model_mode']='real'
        config['completion_timeout_seconds']=config.get('real_completion_timeout_seconds',1800)
    if args.command=='smoke':config.update(concurrency_levels=[1,5],scenarios=['no_proof','cold'],repetitions=1)
    if config['model_mode']=='real' and not args.live_vlm:parser.error('Real model config requires explicit --live-vlm')
    if config['repetitions']<1:parser.error('Repetitions must be positive')
    os.environ.update(OLLAMA_BASE=config['ollama_base'],VLM_OLLAMA_BASE=config['ollama_base'],
        VLM_TARGET_MODEL=config['vlm_model'],VLM_MAX_IMAGE_DIM=str(config['vlm_max_image_dim']))
    run=Run(config,args.label)
    if args.command in ('smoke','suite','policy'):
        from evaluation.benchmarks.runners.policy_eval import run_policy
        run_policy(run)
    if args.command in ('smoke','suite'):
        from evaluation.benchmarks.runners.reliability_eval import run_reliability
        run_reliability(run,existing=args.command=='suite')
    if args.command in ('smoke','suite','load'):
        from evaluation.benchmarks.runners.load_test import run_load
        asyncio.run(run_load(run,arrivals=['burst','staggered'] if config['arrival']=='both' else None))
    if args.command in ('smoke','suite','vlm'):
        from evaluation.benchmarks.runners.vlm_eval import run_vlm
        run_vlm(run,live=args.live_vlm)
    run.finish()
    if any(r['status']=='failed' for r in run.correctness) or any(r.get('error') for r in run.requests):raise SystemExit(1)

if __name__=='__main__':main()
