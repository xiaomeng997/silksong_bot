"""A/A v2 analysis, derived from frozen v1: separate batches, retain known watchdog failures."""
import argparse, json, math
from pathlib import Path
import numpy as np
BASE=Path(__file__).parent

def rate(rows): return 60*sum(r['audit']['metrics']['L'] for r in rows)/sum(r['audit']['metrics']['T'] for r in rows)
def mean(rows,key):
    if key in ('p50','p99','gap_ge3'): return float(np.mean([r['main_ticks'][key] for r in rows]))
    if key=='L': return float(np.mean([r['audit']['metrics']['L'] for r in rows]))
    if key=='failure': return float(np.mean([not r['audit']['success'] for r in rows]))
    if key=='K_star': return float(np.mean([r['audit']['K_star'] for r in rows]))
    raise KeyError(key)

def cp_upper(k,n,alpha=.0125):
    if k==n:return 1.
    lo,hi=0.,1.
    for _ in range(80):
        p=(lo+hi)/2
        cdf=sum(math.comb(n,j)*p**j*(1-p)**(n-j) for j in range(k+1))
        if cdf>alpha:lo=p
        else:hi=p
    return (lo+hi)/2

def block(rows):
    assert len(rows)==4 and len({(x['instance'],x['label']) for x in rows})==4
    arms={a:[x for x in rows if x['label']==a] for a in ('A','B')}
    result={'block':rows[0]['block'],'period':rows[0]['period'],'seed':rows[0]['seed'],'arms':{}}
    for a,r in arms.items():
        result['arms'][a]={'R':rate(r),**{k:mean(r,k) for k in ('L','failure','K_star','p50','p99','gap_ge3')},
          'any_failure':any(not x['audit']['success'] for x in r),'both_failure':all(not x['audit']['success'] for x in r)}
    result['differences']={k:result['arms']['B'][k]-result['arms']['A'][k] for k in ('R','L','failure','p50','p99','gap_ge3')}
    result['ratios']={k:result['arms']['B'][k]/result['arms']['A'][k] for k in ('K_star','p99')}
    result['instance_R']=float(np.mean([rate([x for x in arms[a] if x['instance']==1])-rate([x for x in arms[a] if x['instance']==0]) for a in ('A','B')]))
    result['order_R']=float(np.mean([rate([x for x in arms[a] if x['round']==1])-rate([x for x in arms[a] if x['round']==0]) for a in ('A','B')]))
    result['instance_p99']=float(np.mean([mean([x for x in arms[a] if x['instance']==1],'p99')-mean([x for x in arms[a] if x['instance']==0],'p99') for a in ('A','B')]))
    result['order_p99']=float(np.mean([mean([x for x in arms[a] if x['round']==1],'p99')-mean([x for x in arms[a] if x['round']==0],'p99') for a in ('A','B')]))
    result['failure_discordant']=any(arms['A'][i]['audit']['success'] != next(x for x in arms['B'] if x['instance']==arms['A'][i]['instance'])['audit']['success'] for i in range(2))
    result['mean_p99']=mean(rows,'p99')
    return result

def indices_for(blocks,reps=20000,seed=28100000):
    rng=np.random.default_rng(seed); pieces=[]
    for p in sorted({b['period'] for b in blocks}):
        idx=np.array([i for i,b in enumerate(blocks) if b['period']==p])
        pieces.append(rng.choice(idx,size=(reps,len(idx)),replace=True))
    return np.concatenate(pieces,axis=1)

def estimate(values,indices):
    x=np.asarray(values,float);boot=x[indices].mean(axis=1)
    ci=np.percentile(boot,[2.5,97.5]).tolist()
    return {'estimate':float(x.mean()),'ci95':ci,'block_sd':float(x.std(ddof=1)) if len(x)>1 else None,'bias_signal':bool(ci[0]>0 or ci[1]<0)}

def ceil4(x):return int(4*math.ceil(x/4))

def sample_design(blocks):
    z=1.96+.842;gates={}
    def add(name,values,margin):
        s=float(np.std(values,ddof=1));gates[name]={'block_sd':s,'margin':margin,'required_blocks_normal':ceil4(max(32,(z*1.25*s/margin)**2))}
    r=np.array([b['differences']['R'] for b in blocks]);sigma=1.25*float(r.std(ddof=1))
    gates['step2_R']={'block_sd':float(r.std(ddof=1)),'design_true_improvement':1.,'point_threshold':-.5,'required_blocks_normal':ceil4(max(32,(z*sigma)**2,(.842*sigma/.5)**2))}
    for key,margin in [('R',.25),('L',.25),('failure',.05),('p50',1.),('p99',2.),('gap_ge3',.01)]:add(key,[b['differences'][key] for b in blocks],margin)
    for key,margin in [('K_star',math.log(1.05)),('p99',math.log(1.1))]:add(key+'_log_ratio',[math.log(b['ratios'][key]) for b in blocks],margin)
    if all(b['arms'][a]['failure']==0 for b in blocks for a in ('A','B')):
        gates['failure']['required_blocks_normal']=max(88,gates['failure']['required_blocks_normal'])
        gates['failure']['zero_failure_exact_floor']=88
    step2=max(v['required_blocks_normal'] for k,v in gates.items() if k!='R')
    retire=max(v['required_blocks_normal'] for k,v in gates.items() if k!='step2_R')
    # A frozen approximation to bootstrap power: centered, 1.25-inflated block
    # residuals, equally represented periods, fixed design shift. Not joint power.
    checks={}
    for name,g in gates.items():
        B=min(128,g['required_blocks_normal']);rng=np.random.default_rng(28100001)
        vals=(r if name=='step2_R' else np.log([b['ratios'][name[:-10]] for b in blocks]) if name.endswith('_log_ratio') else np.array([b['differences'][name] for b in blocks]))
        vals=np.asarray(vals,float);vals=1.25*(vals-vals.mean());parts=[]
        for p in range(4):
            ix=np.array([i for i,b in enumerate(blocks) if b['period']==p]);parts.append(vals[rng.choice(ix,size=(20000,B//4),replace=True)])
        noise=np.concatenate(parts,axis=1).mean(axis=1);upper=float(np.percentile(noise,97.5))
        power=float(np.mean((noise-1+upper<0)&(noise-1<=-.5))) if name=='step2_R' else float(np.mean(noise+upper<=g['margin']))
        if name=='failure' and all(v==0 for v in vals):power=None
        checks[name]={'evaluated_blocks':B,'power_approx':power,'budget_capped':g['required_blocks_normal']>128}
    return {'sigma_multiplier':1.25,'gates':gates,'step2_required_blocks_normal':step2,'retire_rules_required_blocks_normal_without_w7':retire,'budget_blocks':128,'budget_exceeded':step2>128 or retire>128,'power_checks':checks,'w7_hammer_gate':'own w7 pilot variance required for stage 3; w13 cannot substitute','warning':'normal requirements and shifted residual power are approximations; not joint gate power; unexplained A/A bias must be resolved first'}

def analyze(rows,final=False):
    if any(r.get("protocol_version") != 2 or not r.get("production_eligible") or not r.get("complete") for r in rows):
        raise ValueError("v2 analysis requires complete, production-eligible v2 data only")
    if rows and (len({r.get('protocol_sha256') for r in rows})!=1 or rows[0].get('protocol_sha256') is None
                 or len({r['behavior_sha256'] for r in rows})!=1):
        raise ValueError("mixed or missing v2 protocol/configuration identity")
    grouped={}
    for r in rows:grouped.setdefault(r['block'],[]).append(r)
    blocks=[block(grouped[b]) for b in sorted(grouped) if len(grouped[b])==4]
    if final: assert len(blocks)==32 and len(rows)==128
    if not blocks:return {'final':False,'complete_blocks':0,'episodes':len(rows)}
    ix=indices_for(blocks);est={}
    for k in ('R','L','failure','p50','p99','gap_ge3'):est['label_'+k]=estimate([b['differences'][k] for b in blocks],ix)
    for k in ('instance_R','order_R','instance_p99','order_p99'):est[k]=estimate([b[k] for b in blocks],ix)
    for k in ('K_star','p99'):
        a=np.array([b['arms']['A'][k] for b in blocks]);b=np.array([b['arms']['B'][k] for b in blocks]);boot=b[ix].mean(axis=1)/a[ix].mean(axis=1)
        est['label_'+k+'_ratio']={'estimate':float(b.mean()/a.mean()),'ci95':np.percentile(boot,[2.5,97.5]).tolist(),'block_log_ratio_sd':float(np.log(b/a).std(ddof=1)) if len(a)>1 else None}
    periods=[]
    for p in sorted({b['period'] for b in blocks}):
        bs=[b for b in blocks if b['period']==p]
        periods.append({'period':p,'blocks':len(bs),'A_R':float(np.mean([b['arms']['A']['R'] for b in bs])),'B_R':float(np.mean([b['arms']['B']['R'] for b in bs])),'mean_R':float(np.mean([(b['arms']['A']['R']+b['arms']['B']['R'])/2 for b in bs]))})
    stop=[]
    if len(blocks)%8==0:
        if est['label_R']['estimate']>=2:stop.append('B-A HP/min >= +2 at 8-block check')
        if est['label_failure']['estimate']>=.20:stop.append('B-A failure >= +20pp at 8-block check')
    if len(blocks)>=2 and all(b['mean_p99']>100 for b in blocks[-2:]):stop.append('two consecutive block means of episode p99 >100ms')
    signals=[k for k,v in est.items() if v.get('bias_signal')]
    drift=max(p['mean_R'] for p in periods)-min(p['mean_R'] for p in periods)
    discord=sum(b['failure_discordant'] for b in blocks)
    sparse=None
    if discord<5:
        n=len(blocks);u=cp_upper(sum(b['arms']['B']['any_failure'] for b in blocks),n);l=1-cp_upper(n-sum(b['arms']['A']['both_failure'] for b in blocks),n)
        sparse={'discordant_blocks':discord,'conservative_upper_difference':min(1.,u-l),'method':'U98.75%(B any failure)-L98.75%(A both failure), one-sided Clopper-Pearson; no degenerate bootstrap precision claim'}
    result={'final':final,'status':'bias clues require investigation' if signals else 'data usable for design','complete_blocks':len(blocks),'episodes':len(rows),'blocks':blocks,'estimates':est,'periods':periods,'period_mean_R_range':drift,'drift_signal_gt1':drift>1,'bias_signals':signals,'stop_reasons':stop,'sparse_failure_bound':sparse,'formal_equivalence_proven':False,'bootstrap':{'reps':20000,'seed':28100000,'unit':'whole crossover block, resampled within period'},'warning':'partial snapshots are not the final A/A report; unadjusted diagnostic intervals are clues, not proof of systematic bias; no nonsignificance-as-equivalence claim'}
    result['watchdog_failures']=sum(r.get('outcome')=='WATCHDOG' for r in rows)
    result['exposure_estimand']='damage rate over observed operation until the first protocol endpoint, including known watchdog failure; joint failure and K_star gates remain mandatory'
    if final:result['sample_design']=sample_design(blocks)
    return result

def load_rows(root):return [json.loads(p.read_text()) for p in sorted(root.glob('period_*/b*_r*/verified_i*_e*.json'))]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=BASE/'run_20261028');ap.add_argument('--out',type=Path,required=True);ap.add_argument('--final',action='store_true');a=ap.parse_args()
    result=analyze(load_rows(a.root),a.final)
    with a.out.open('x',encoding='utf-8') as f:json.dump(result,f,indent=1,allow_nan=False)
    print(json.dumps({k:result.get(k) for k in ('final','complete_blocks','episodes','status','bias_signals','stop_reasons')},indent=1))
if __name__=='__main__':main()
