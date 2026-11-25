"""Bounded process tree watchdog. Persist PID+birth time; never kill reused PIDs."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import psutil


def terminate_tree(pid, created, popen=None):
    """Stop a process tree. Pass the Popen object for our own child so that
    Popen (not psutil) reaps it and keeps the real exit code (Linux/macOS)."""
    try:
        parent = psutil.Process(pid)
        if abs(parent.create_time() - created) > .01:
            return False
        children = parent.children(recursive=True)
        for proc in reversed(children):
            try:
                proc.terminate()
            except psutil.NoSuchProcess:
                pass
        if popen is not None:
            popen.terminate()
            try:
                popen.wait(timeout=2)
            except subprocess.TimeoutExpired:
                popen.kill()
            waited = children
        else:
            parent.terminate()
            waited = children + [parent]
        _, alive = psutil.wait_procs(waited, timeout=2)
        for proc in alive:
            try:
                proc.kill()
            except psutil.NoSuchProcess:
                pass
        return True
    except psutil.NoSuchProcess:
        return False


def run_process(command, cwd, log_path, *, seconds=1800, memory_mb=1024,
                heartbeat=lambda **kw: None, should_stop=lambda: False, env=None,input_text=None):
    from kaggle_agent.supervisor.limits import MAX_SECONDS, memory_ceiling_mb
    if not 0 < seconds <= MAX_SECONDS or not 0 < memory_mb <= max(2048, memory_ceiling_mb()):
        raise ValueError("Invalid process bounds")
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    reason, peak = "exit", 0
    descendants={}
    with log_path.open("w", encoding="utf-8") as output:
        # Keep prompts out of Windows .cmd arguments and avoid pipe-buffer deadlocks.
        with tempfile.TemporaryFile() as input_file:
            if input_text is not None:
                input_file.write(input_text.encode("utf-8"));input_file.seek(0)
            child = subprocess.Popen(command, cwd=cwd, stdout=output, stderr=subprocess.STDOUT,
                                     stdin=input_file if input_text is not None else subprocess.DEVNULL, env=env,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        proc = psutil.Process(child.pid)
        created = proc.create_time()
        try:
            heartbeat(pid=child.pid, process_created=created)
            while child.poll() is None:
                elapsed = time.monotonic() - start
                try:
                    children=proc.children(recursive=True)
                    descendants.update({p.pid:p.create_time() for p in children})
                    rss = sum(p.memory_info().rss for p in [proc] + children if p.is_running())
                except psutil.NoSuchProcess:
                    rss = 0
                peak = max(peak, rss)
                reason = ("user_stop" if should_stop() else "timeout" if elapsed >= seconds
                          else "memory_limit" if rss > memory_mb * 1024**2 else "exit")
                heartbeat(pid=child.pid, process_created=created)
                if reason != "exit":
                    terminate_tree(child.pid, created, child)
                    break
                time.sleep(.05)
            code = child.wait(timeout=5)
        except BaseException:
            terminate_tree(child.pid, created, child)
            child.wait(timeout=5)
            raise
        finally:
            for pid,birth in descendants.items():terminate_tree(pid,birth)
    return dict(exit_code=code, termination_reason=reason, elapsed_seconds=time.monotonic()-start,
                peak_rss_bytes=peak, log=str(log_path), pid=child.pid, process_created=created)
