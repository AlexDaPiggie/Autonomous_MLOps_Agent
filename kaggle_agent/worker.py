"""Bounded local child entrypoint. Receives JSON, never shell commands or web code."""
import argparse
import json
import os
from pathlib import Path
import threading
import time
from kaggle_agent.benchmarks import run_dataset
from kaggle_agent.storage.database import checksum,fingerprint
from kaggle_agent.storage.export_state import atomic_write


def main():
    parser=argparse.ArgumentParser();parser.add_argument("plan");args=parser.parse_args()
    plan=json.loads(Path(args.plan).read_text(encoding="utf-8"));root=Path(args.plan).parent
    # The child retains its own cap if the supervisor/watchdog process disappears.
    started=time.monotonic()
    def guard():
        import psutil
        seconds=float(os.environ.get("KAGGLE_AGENT_MAX_SECONDS","60"))
        memory_mb=int(os.environ.get("KAGGLE_AGENT_MAX_MB","1024"))
        process=psutil.Process()
        while True:
            if time.monotonic()-started>seconds or process.memory_info().rss>memory_mb*1024**2:
                atomic_write(root/"child-limit.json",json.dumps(dict(reason="child resource cap")))
                os._exit(124)
            time.sleep(.1)
    threading.Thread(target=guard,daemon=True).start()
    data=json.loads(Path(plan["dataset"]).read_text(encoding="utf-8"))
    if plan.get("benchmark_configs"):
        pair=[run_dataset(data,config) for config in plan["benchmark_configs"]]
        atomic_write(root/"benchmark-pair.json",json.dumps(pair,allow_nan=False))
        artifact=pair[-1]
    else:artifact=run_dataset(data,plan["config"])
    atomic_write(root/"predictions.json",json.dumps(artifact,allow_nan=False))
    result=dict(complete=True,evaluator_hash=plan["evaluator_hash"],config_hash=fingerprint(plan["config"]),
                data_hash=plan["data_hash"],split_hash=plan["split_hash"],fold_scores=artifact["fold_scores"],
                score_type=artifact["score_type"],artifacts={"predictions.json":checksum(root/"predictions.json")})
    if "ensemble_baseline_scores" in artifact:result["ensemble_baseline_scores"]=artifact["ensemble_baseline_scores"]
    atomic_write(root/"result.json",json.dumps(result,allow_nan=False))


if __name__=="__main__":main()
