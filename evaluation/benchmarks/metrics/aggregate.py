import math, random, statistics
from collections import Counter, defaultdict

def percentile(values,p):
    s=sorted(values)
    if not s: return None
    i=(len(s)-1)*p; lo=math.floor(i); hi=math.ceil(i)
    return s[lo]+(s[hi]-s[lo])*(i-lo)

def stats(values,seed=170):
    v=[float(x) for x in values if x is not None]
    if not v: return {'n':0,'mean_ms':None,'p50_ms':None,'p90_ms':None,'p95_ms':None,'p99_ms':None,'max_ms':None,'mean_ci95_ms':None}
    rng=random.Random(seed)
    means=[statistics.mean(rng.choices(v,k=len(v))) for _ in range(500)] if len(v)>1 else []
    return {'n':len(v),'mean_ms':statistics.mean(v), 'max_ms':max(v),
        **{f'p{int(p*100)}_ms':percentile(v,p) for p in (.5,.9,.95,.99)},
        'mean_ci95_ms':[percentile(means,.025),percentile(means,.975)] if means else None,
        'percentile_warning':'Small sample; especially p99 is unstable' if len(v)<100 else None,
        'ci_method':'request bootstrap; correlated concurrency samples limit inference'}

def classification(expected,actual):
    labels=sorted(set(expected+actual)); matrix={e:{a:0 for a in labels} for e in labels}
    for e,a in zip(expected,actual): matrix[e][a]+=1
    per={}
    for l in labels:
        tp=matrix[l][l]; fp=sum(matrix[x][l] for x in labels if x!=l); fn=sum(matrix[l][x] for x in labels if x!=l)
        p=tp/(tp+fp) if tp+fp else 0; r=tp/(tp+fn) if tp+fn else 0
        per[l]={'precision':p,'recall':r,'f1':2*p*r/(p+r) if p+r else 0,'support':sum(matrix[l].values())}
    n=len(expected)
    return {'n':n,'accuracy':sum(e==a for e,a in zip(expected,actual))/n if n else None,
        'macro_f1':statistics.mean(x['f1'] for x in per.values()) if per else None,'per_class':per,'confusion_matrix':matrix}

def aggregate(rows,batches,seed):
    groups=defaultdict(list)
    for r in rows: groups[(r['scenario'],r['concurrency'],r['category'],r['arrival'],r['mode'])].append(r)
    result=[]
    for (s,c,cat,arrival,mode),rr in groups.items():
        complete=sum(r.get('outcome_reached',False) for r in rr)
        result.append({'scenario':s,'concurrency':c,'category':cat,'arrival':arrival,'mode':mode,'n':len(rr),
            'ack':stats([r.get('ack_ms') for r in rr],seed),'upload':stats([r.get('upload_ms') for r in rr],seed),
            'end_to_end':stats([r.get('final_ms') for r in rr],seed),'scheduling_skew':stats([r.get('skew_ms') for r in rr],seed),
            'error_rate':sum(bool(r.get('error')) for r in rr)/len(rr),
            'timeout_rate':sum(bool(r.get('timeout')) for r in rr)/len(rr),
            'outcome_rate':complete/len(rr),'unfinished':len(rr)-complete,
            'http_statuses':dict(Counter(str(r.get('status_code')) for r in rr))})
    return result
