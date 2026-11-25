"""Submission quality checks are available; network submission is deliberately absent."""
import csv
from kaggle_agent.execution.gates import require, GateError
from .validation import aligned,finite


def validate_submission(path,expected_ids,columns,*,id_column,lower=None,upper=None,eligible=False,quota=0,authorized=False,constraint_checker=None):
    require(eligible and quota>0 and authorized,"Rules, quota and explicit submission authorization required")
    with open(path,newline="",encoding="utf-8-sig") as stream:
        reader=csv.DictReader(stream)
        require(reader.fieldnames==columns,"Wrong submission columns/order")
        rows=list(reader)
    ids=[r[id_column] for r in rows]
    require(ids==[str(x) for x in expected_ids],"Submission ID order mismatch")
    aligned(ids,rows,[str(x) for x in expected_ids])
    values=[[float(row[c]) for c in columns if c!=id_column] for row in rows]
    require(finite(values),"Nonfinite submission values")
    for row in values:
        require(all((lower is None or x>=lower) and (upper is None or x<=upper) for x in row),"Submission bounds violation")
    if constraint_checker:require(constraint_checker(rows),"Submission constraint violation")
    return dict(valid=True,rows=len(rows))


def submit(*args,**kwargs):
    raise GateError("Network submission backend disabled; use reviewed manual workflow after separate authorization")
