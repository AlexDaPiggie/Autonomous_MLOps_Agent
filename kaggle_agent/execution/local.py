"""Durable local runner. Restart reconciles intent/PID/artifacts without relaunch."""
import json
import os
from pathlib import Path
import sys
import psutil
from kaggle_agent.execution.gates import require
from kaggle_agent.storage.export_state import atomic_write
from kaggle_agent.supervisor.watchdog import run_process,terminate_tree


class LocalProvider:
    name="local"

    def __init__(self,directory,*,seconds=60,memory_mb=1024,heartbeat=lambda **kw:None,should_stop=lambda:False):
        self.directory=Path(directory).resolve()
        self.seconds=seconds;self.memory_mb=memory_mb
        self.heartbeat=heartbeat;self.should_stop=should_stop

    def launch(self,key,payload):
        root=self.directory/key
        require(not root.exists(),"Existing local launch intent; reconcile rather than relaunch")
        root.mkdir(parents=True)
        atomic_write(root/"plan.json",json.dumps(payload,allow_nan=False))
        state=dict(state="INTENT",job_id=key)
        atomic_write(root/"status.json",json.dumps(state))
        def heartbeat(**process):
            state.update(state="RUNNING",**process)
            atomic_write(root/"status.json",json.dumps(state))
            self.heartbeat(**process)
        env=os.environ.copy()
        env.update(OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1",NUMEXPR_NUM_THREADS="1")
        env.update(KAGGLE_AGENT_MAX_SECONDS=str(self.seconds),KAGGLE_AGENT_MAX_MB=str(self.memory_mb))
        # Resolve package from its installed/source location even outside repository.
        env["PYTHONPATH"]=str(Path(__file__).resolve().parents[2])
        outcome=run_process([sys.executable,"-m","kaggle_agent.worker",str(root/"plan.json")],root,root/"worker.log",
                            seconds=self.seconds,memory_mb=self.memory_mb,heartbeat=heartbeat,should_stop=self.should_stop,env=env)
        state.update(state="COMPLETED" if outcome["exit_code"]==0 and outcome["termination_reason"]=="exit" else "STOPPED" if outcome["termination_reason"]=="user_stop" else "FAILED",outcome=outcome)
        atomic_write(root/"status.json",json.dumps(state))
        return key

    def reconcile(self,key):
        root=self.directory/key
        if not (root/"status.json").is_file():return dict(state="UNKNOWN")
        state=json.loads((root/"status.json").read_text())
        if state["state"] in {"RUNNING","INTENT"}:
            try:
                proc=psutil.Process(state["pid"])
                alive=abs(proc.create_time()-state["process_created"])<.01 and proc.is_running()
            except (KeyError,psutil.NoSuchProcess):alive=False
            if not alive:
                # A complete result still requires independent supervisor evaluation.
                state["state"]="COMPLETED" if (root/"result.json").is_file() else "FAILED"
                state["reason"]="local_process_exit_after_supervisor_loss"
        return state

    def cancel(self,key):
        state=self.reconcile(key)
        if state.get("pid"):terminate_tree(state["pid"],state["process_created"])
        state["state"]="STOPPED"
        atomic_write(self.directory/key/"status.json",json.dumps(state))
