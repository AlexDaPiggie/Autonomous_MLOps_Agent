from contextlib import redirect_stdout,redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from kaggle_agent.__main__ import main
from kaggle_agent.storage.database import Store
from kaggle_agent.evaluation.validation import promote
from kaggle_agent.execution.gates import GateError


class Integration(unittest.TestCase):
    def invoke(self,db,*args):
        output=io.StringIO();errors=io.StringIO()
        with redirect_stdout(output),redirect_stderr(errors):
            code=main(["--db",str(db),*args])
        return code,json.loads(output.getvalue() if code==0 else errors.getvalue())

    def test_local_pipeline_each_domain_paths_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="kaggle integration ") as temp:
            root=Path(temp);db=root/"global.sqlite3"
            for task in ("classification","regression","optimization","forecasting"):
                with self.subTest(task=task):
                    directory=root/task;directory.mkdir()
                    code,result=self.invoke(db,"init","--competition",str(directory),"--task",task,"--demo")
                    self.assertEqual(code,0,result)
                    code,result=self.invoke(db,"start","--competition",str(directory),"--agent","mock")
                    self.assertTrue(result["dry_run"])
                    self.assertFalse((directory/".kaggle-agent"/"jobs").exists())
                    code,result=self.invoke(db,"start","--competition",str(directory),"--agent","mock","--execute")
                    self.assertEqual(code,0,result)
                    self.assertEqual(result["state"],"COMPLETED",result)
                    self.assertEqual(len(result["completed"]),1)
                    code,result=self.invoke(db,"resume","--competition",str(directory),"--execute")
                    self.assertEqual(code,0,result)
                    self.assertEqual(result["completed"],[]) # duplicate fingerprint, no second worker
                    self.assertTrue((directory/".kaggle-agent"/"checkpoint.json").is_file())
            store=Store(db)
            self.assertEqual(len(store.rows("SELECT * FROM experiments WHERE state='COMPLETED'")),4)
            self.assertEqual(len(store.rows("SELECT * FROM costs")),0)
            self.assertEqual(len(store.rows("SELECT * FROM predictions")),4)
            # Mutation after evaluation blocks promotion even if DB result is complete.
            row=store.rows("SELECT * FROM predictions")[0]
            exp=store.rows("SELECT * FROM experiments WHERE id=?",(row["experiment"],))[0]
            Path(row["path"]).write_text("{}")
            with self.assertRaises(GateError):promote(store,exp["competition"],exp["id"])

    def test_initializer_does_not_overwrite_and_stop_requires_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);db=root/"db.sqlite3"
            self.invoke(db,"init","--competition",temp,"--demo")
            code,result=self.invoke(db,"init","--competition",temp,"--demo")
            self.assertEqual(code,2)
            self.invoke(db,"status","--competition",temp)
            self.invoke(db,"stop","--competition",temp)
            code,result=self.invoke(db,"start","--competition",temp,"--execute")
            self.assertEqual(code,0)
            self.assertEqual(result["completed"],[])
