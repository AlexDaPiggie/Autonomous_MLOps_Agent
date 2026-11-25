import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest
from kaggle_agent.benchmarks import synthetic,run_dataset
from kaggle_agent.evaluation.validation import evaluate,paired_improvement
from kaggle_agent.evaluation.ensemble import conditional_blend,validate_library
from kaggle_agent.evaluation.submission import validate_submission,submit
from kaggle_agent.execution.efficiency import Cache,bounded_search,next_fidelity
from kaggle_agent.execution.gates import GateError
from kaggle_agent.pipelines.forecasting import check_temporal
from kaggle_agent.pipelines.optimization import check_knapsack
from kaggle_agent.pipelines.tabular import fold_target_encode


class Performance(unittest.TestCase):
    def test_domain_smokes_and_reproducibility(self):
        for task in ("classification","regression","optimization","forecasting"):
            with self.subTest(task=task):
                data=synthetic(task,11);config=dict(metric="log_loss" if task=="classification" else "rmse",seed=11)
                first=run_dataset(data,config);second=run_dataset(data,config)
                self.assertEqual(first,second)
                self.assertTrue(first["fold_scores"])

    def test_ids_folds_and_variance(self):
        result=evaluate(["a","b","c","d"],[1,2,3,4],[0,0,1,1],["d","b","a","c"],[4,2,1,3],"rmse")
        self.assertEqual(result["mean"],0)
        with self.assertRaises(GateError):evaluate(["a","b"],[1,2],[0,1],["a","a"],[1,2],"rmse")
        with self.assertRaises(GateError):evaluate(["a","b"],[1,2],[0,1],["a","b"],[1,float("nan")],"rmse")
        with self.assertRaises(GateError):evaluate(["a","b"],[1,2],[0,1],["a","b"],[1,2],"rmse",expected_folds=[1,0])
        self.assertTrue(paired_improvement([.8]*5,[.7]*5,"maximize")["improved"])
        self.assertFalse(paired_improvement([1,1,1,1,100],[2]*5,"minimize")["improved"])

    def test_leakage_and_infeasibility(self):
        with self.assertRaises(GateError):check_temporal([1,3],[2,4])
        with self.assertRaises(GateError):check_temporal([1,2],[3,4],feature_available_times=[2,4])
        with self.assertRaises(GateError):check_knapsack([1,1],[5,6],[1,2],10)
        self.assertEqual(fold_target_encode(["x","x"],[1,3],["unseen"]),[2.])

    def test_conditional_blending_complement(self):
        import numpy as np
        y=np.linspace(-2,2,60);noise=np.sin(np.arange(60))*2
        base=dict(ids=list(range(60)),folds=[i%3 for i in range(60)],data_hash="d",split_hash="s",class_order=[],
                  scale="target",score_type="base_oof",complete=True,leakage_reviewed=True)
        a=base|dict(predictions=(y+noise).tolist());b=base|dict(predictions=(y-noise*1.3).tolist())
        one=conditional_blend([a],y.tolist(),"rmse")
        both=conditional_blend([a,b],y.tolist(),"rmse")
        self.assertLess(sum(both["fold_scores"]),sum(one["fold_scores"]))
        self.assertEqual(both["score_type"],"conditional_meta_cv")
        with self.assertRaises(GateError):validate_library([a,b|dict(split_hash="wrong")])

    def test_fidelity_cache_search(self):
        self.assertIsNone(next_fidelity("screen",False))
        self.assertEqual(next_fidelity("screen",False,explore=True),"intermediate")
        rows=bounded_search(dict(x=[3,2,1]),lambda c:c["x"],max_trials=2)
        self.assertEqual(len(rows),2)
        with tempfile.TemporaryDirectory() as temp:
            cache=Cache(temp);key=cache.key(data_hash="d",split_hash="s",config={},code_hash="c",seed=1,evaluator_hash="e")
            cache.put(key,dict(value=4));self.assertEqual(cache.get(key),dict(value=4))
            (Path(temp)/(key+".json")).write_text("{}")
            with self.assertRaises(GateError):cache.get(key)

    def test_submission_gates_no_network(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"submission.csv";path.write_text("id,target\na,0.4\nb,0.7\n")
            kwargs=dict(expected_ids=["a","b"],columns=["id","target"],id_column="id",lower=0,upper=1,eligible=True,quota=1,authorized=True)
            self.assertTrue(validate_submission(path,**kwargs)["valid"])
            with self.assertRaises(GateError):validate_submission(path,**(kwargs|dict(authorized=False)))
            path.write_text("id,target\na,nan\nb,0.7\n")
            with self.assertRaises(GateError):validate_submission(path,**kwargs)
        with self.assertRaises(GateError):submit()
