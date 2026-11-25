"""Feasible knapsack reference pipeline; general problems supply independent checkers."""
import math
import random
import time
from kaggle_agent.execution.gates import require


def check_knapsack(candidate,weights,values,capacity):
    require(len(candidate)==len(weights)==len(values),"Candidate shape mismatch")
    require(all(type(x) is int and x in (0,1) for x in candidate),"Nonbinary decision")
    require(all(math.isfinite(x) and x>=0 for x in weights+values) and math.isfinite(capacity) and capacity>=0,"Invalid optimization instance")
    weight=sum(x*w for x,w in zip(candidate,weights))
    require(weight<=capacity+1e-9,"Infeasible candidate")
    return sum(x*v for x,v in zip(candidate,values))


def solve_knapsack(weights,values,capacity,*,seed=42,iterations=100,seconds=2,operator="anneal"):
    require(0<seconds<=1800 and 0<iterations<=100000,"Optimization resource cap")
    if operator=="exact":return solve_knapsack_exact(weights,values,capacity,seconds=seconds)
    require(operator in {"greedy","local","anneal","restart"},"Unknown neighborhood")
    candidate=[0]*len(weights);check_knapsack(candidate,weights,values,capacity)
    remaining=capacity
    for i in sorted(range(len(weights)),key=lambda i:values[i]/max(weights[i],1e-12),reverse=True):
        if weights[i]<=remaining:candidate[i]=1;remaining-=weights[i]
    rng=random.Random(seed);score=check_knapsack(candidate,weights,values,capacity)
    best,best_score=candidate[:],score;archive={tuple(best):score};started=time.monotonic()
    for step in range(0 if operator=="greedy" else iterations):
        if time.monotonic()-started>=seconds:break
        proposal=candidate[:]
        if not proposal:break
        indices=rng.sample(range(len(proposal)),min(len(proposal),2 if step%3==0 else 1))
        for i in indices:proposal[i]=1-proposal[i]
        if sum(x*w for x,w in zip(proposal,weights))>capacity:continue
        new_score=check_knapsack(proposal,weights,values,capacity)
        temperature=max(.01,(1-step/iterations)*max(1,best_score)*.05)
        if new_score>=score or operator=="anneal" and rng.random()<math.exp(max(-700,(new_score-score)/temperature)):
            candidate,score=proposal,new_score
        if new_score>best_score:best,best_score=proposal[:],new_score
        if operator=="restart" and step%20==19:candidate=[0]*len(weights);score=0
        archive[tuple(proposal)]=new_score
    return dict(candidate=best,score=check_knapsack(best,weights,values,capacity),
                archive=[dict(candidate=list(k),score=v) for k,v in sorted(archive.items(),key=lambda p:p[1],reverse=True)[:10]],seed=seed)


def solve_knapsack_exact(weights,values,capacity,*,seconds=2):
    import numpy as np
    from scipy.optimize import milp,Bounds,LinearConstraint
    require(0<seconds<=1800,"Exact solver time bound required")
    check_knapsack([0]*len(weights),weights,values,capacity)
    result=milp(-np.asarray(values,dtype=float),integrality=np.ones(len(weights)),bounds=Bounds(0,1),
                constraints=LinearConstraint(np.asarray(weights,dtype=float),-np.inf,capacity),options=dict(time_limit=seconds))
    require(result.x is not None,"Exact solver returned no feasible incumbent")
    candidate=np.rint(result.x).astype(int).tolist()
    return dict(candidate=candidate,score=check_knapsack(candidate,weights,values,capacity),
                archive=[],optimal=bool(result.success),solver_status=int(result.status))
