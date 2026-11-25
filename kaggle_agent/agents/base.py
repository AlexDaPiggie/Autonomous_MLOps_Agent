"""Adapters use CLI file protocol, bounded processes and no automatic fallback."""
from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid
from kaggle_agent.supervisor.watchdog import run_process


@dataclass
class AgentResult:
    status: str
    session_id: str | None = None
    experiment_ids: list = field(default_factory=list)
    checkpoint: str | None = None
    next_action: str = "inspect checkpoint"
    termination_reason: str = "unknown"
    usage: dict | None = None
    proposals: list = field(default_factory=list)
    # Code mode: what the agent wrote and what it learned.
    hypothesis: str | None = None
    entry: str | None = None
    lessons: list = field(default_factory=list)
    new_branches: list = field(default_factory=list)
    ratings: list = field(default_factory=list)   # research analysis: [{key, value 0-3, reason}]


def validate_result(value):
    if not isinstance(value, dict) or value.get("status") not in {"completed","failed","waiting_limit","blocked","stopped"}:
        raise ValueError("Invalid agent result status")
    required = {"status","session_id","experiment_ids","checkpoint","next_action","termination_reason"}
    if not required <= value.keys() or not isinstance(value["experiment_ids"],list):
        raise ValueError("Incomplete result protocol")
    if any(not isinstance(x,str) for x in value["experiment_ids"]):
        raise ValueError("Invalid experiment IDs")
    for key in ("session_id","checkpoint"):
        if value[key] is not None and not isinstance(value[key],str):
            raise ValueError(f"Invalid {key}")
    if not all(isinstance(value[k],str) for k in ("next_action","termination_reason")):
        raise ValueError("Invalid result text")
    if value.get("usage") is not None and not isinstance(value["usage"],dict):
        raise ValueError("Invalid usage")
    # Optional code-mode fields are cleaned, never fatal: a slightly different shape
    # (e.g. branches as plain strings) must not throw away a good script.
    value = dict(value)
    for key in ("hypothesis","entry"):
        if value.get(key) is not None and not isinstance(value[key],str):
            value[key] = str(value[key])
    if value.get("entry") and (Path(value["entry"]).name!=value["entry"] or not value["entry"].endswith(".py")):
        value["entry"] = None
    lessons=value.get("lessons") or []
    value["lessons"]=[str(x)[:1000] for x in (lessons if isinstance(lessons,list) else [lessons])][:10]
    branches=value.get("new_branches") or []
    cleaned=[]
    for b in (branches if isinstance(branches,list) else [branches])[:3]:
        if isinstance(b,dict) and b.get("hypothesis"):
            cleaned.append(dict(name=str(b.get("name") or b["hypothesis"])[:60],hypothesis=str(b["hypothesis"])[:500],
                                **({"source":str(b["source"])[:120]} if b.get("source") else {})))
        elif isinstance(b,str) and b.strip():
            cleaned.append(dict(name=" ".join(b.split()[:4])[:60],hypothesis=b[:500]))
    value["new_branches"]=cleaned
    ratings=[]
    for r in (value.get("ratings") if isinstance(value.get("ratings"),list) else [])[:40]:
        try:
            if isinstance(r,dict) and r.get("key") and 0<=int(r.get("value"))<=3:
                ratings.append(dict(key=str(r["key"])[:200],value=int(r["value"]),reason=str(r.get("reason",""))[:200]))
        except (TypeError,ValueError):
            pass
    value["ratings"]=ratings
    proposals=value.get("proposals",[])
    if not isinstance(proposals,list) or len(proposals)>4 or any(not isinstance(p,dict) or not isinstance(p.get("hypothesis"),str) or not isinstance(p.get("config"),dict) for p in proposals):
        raise ValueError("Proposals require up to four hypothesis/config objects")
    return AgentResult(**{k:v for k,v in value.items() if k in AgentResult.__dataclass_fields__})


# Python only: both rule spellings, for the Bash and PowerShell tools Claude uses on Windows.
PYTHON_TOOLS = ["Bash(python:*)", "Bash(python3:*)", "Bash(py:*)", "Bash(python *)", "Bash(python3 *)", "Bash(py *)",
                "PowerShell(python:*)", "PowerShell(py:*)", "PowerShell(python *)", "PowerShell(py *)"]

METERED = {"ANTHROPIC_AUTH_TOKEN","ANTHROPIC_BASE_URL","OPENAI_BASE_URL","OPENAI_API_BASE","CODEX_API_KEY",
           "CLAUDE_CODE_USE_BEDROCK","CLAUDE_CODE_USE_VERTEX","AWS_BEARER_TOKEN_BEDROCK","OPENROUTER_API_KEY"}


def agent_environment():
    """Copy of the environment without anything that could switch a CLI to paid API use."""
    return {k: v for k, v in os.environ.items()
            if not (k.upper().endswith("API_KEY") or k.upper().endswith("_TOKEN") and k.upper().startswith(("ANTHROPIC", "OPENAI"))
                    or k.upper() in METERED)}


def extract_json(text):
    """The protocol object, also when the agent wraps it in a ```json fence or prose."""
    text = text.strip()
    if text.startswith("{"):
        return text
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("No JSON object in agent answer")
    return text[start:end+1]


EFFORTS = ("minimal", "low", "medium", "high", "xhigh", "max")


class CLIAdapter:
    def __init__(self, name, model=None, effort=None):
        if name not in {"codex","claude"}:
            raise ValueError("Choose codex or claude explicitly")
        effort = (effort or "").strip().lower() or None
        if effort and effort not in EFFORTS:
            raise ValueError("Effort must be one of: " + ", ".join(EFFORTS))
        self.name = name
        self.model = (model or "").strip() or None   # None = the tool's own default
        self.effort = effort                         # None = the tool's own default
        self.cancelled = False
        self.last_result = None

    def binary(self):
        # Windows npm CLI shims need their supported .cmd launcher, not a .ps1 file.
        return shutil.which(self.name + ".cmd") if os.name == "nt" else shutil.which(self.name)

    REQUIRED_FLAGS = {"codex": ("--skip-git-repo-check","--sandbox","--output-last-message","--json"),
                      "claude": ("--print","--permission-mode","--output-format","--add-dir")}

    def doctor(self):
        """Version plus a check that the flags this adapter uses exist in the installed CLI."""
        binary = self.binary()
        if not binary:
            return dict(available=False,reason="missing_binary")
        result = subprocess.run([binary,"--version"],capture_output=True,text=True,timeout=15)
        help_command = [binary,"exec","--help"] if self.name == "codex" else [binary,"--help"]
        try:
            text = subprocess.run(help_command,capture_output=True,text=True,timeout=15).stdout
        except (OSError,subprocess.TimeoutExpired):
            text = ""
        missing = [flag for flag in self.REQUIRED_FLAGS[self.name] if flag not in text]
        return dict(available=result.returncode == 0 and not missing,version=result.stdout.strip(),missing_flags=missing)

    def command(self, prompt, result_path=None, *, mode="propose", read_dirs=()):
        """propose: read-only, suggests configs. code: may write files in its working folder
        and run Python to test them (Claude: edits plus python only; Codex: its
        workspace-write sandbox). The supervisor still runs and scores the real code.
        """
        binary = self.binary()
        if not binary:
            raise FileNotFoundError(self.name)
        if mode not in {"propose","code"}:
            raise ValueError("mode must be propose or code")
        if self.name == "codex":
            sandbox = "workspace-write" if mode == "code" else "read-only"
            command = [binary,"exec","--skip-git-repo-check","--sandbox",sandbox,"--json","--output-last-message",str(result_path)]
            if self.model:
                command += ["--model",self.model]
            if self.effort:
                command += ["-c",f'model_reasoning_effort="{self.effort}"']
            return command + ["-"]
        command = [binary,"--print","--permission-mode","acceptEdits" if mode == "code" else "plan","--output-format","json"]
        if self.model:
            command += ["--model",self.model]
        for folder in read_dirs:
            command += ["--add-dir",str(folder)]
        if mode == "code":
            # Code mode: Claude may run Python (and only Python) to test its script.
            # Its environment is preset to smoke mode, so these test runs are small.
            command += ["--allowedTools", *PYTHON_TOOLS]
        return command

    def run(self, task, directory, *, authorized=False, seconds=300, heartbeat=lambda **kw: None,
            should_stop=lambda: False, mode="propose", read_dirs=(), env_extra=None, memory_mb=None):
        if not authorized:
            return AgentResult("blocked",termination_reason="agent_execution_not_enabled")
        # Never let the CLI bill per use: it gets an environment without API keys or
        # alternate endpoints, so it can only use your subscription login. Unrelated
        # keys you have set (Gemini, Firecrawl, ...) stay in your shell, untouched.
        env = agent_environment() | {k: str(v) for k, v in (env_extra or {}).items()}
        if self.name == "claude" and self.effort:
            env["CLAUDE_CODE_EFFORT_LEVEL"] = self.effort   # Claude Code reads effort from this variable
        if not self.binary():
            return AgentResult("blocked",termination_reason="missing_binary")
        run_id = uuid.uuid4().hex
        # Session logs live outside the code workspace so they are never fingerprinted as code.
        session_root = Path(directory) if mode == "propose" else Path(directory).parent.parent
        folder = session_root/".kaggle-agent"/"sessions"/run_id if mode == "propose" else session_root/"sessions"/run_id
        folder.mkdir(parents=True)
        result_path = folder/"result.json"
        template = asdict(AgentResult("completed",termination_reason="task_completed"))
        prompt = (task + "\nRead shared rules explicitly. No paid work, remote mutations, submissions or pushes. "
                  "Return only a JSON object using this protocol: " + json.dumps(template))
        final_path=folder/"final.json"
        removed = sorted(set(os.environ) - set(env))
        if removed:  # names only, never values
            (folder/"removed_env.txt").write_text("Hidden from the agent: " + ", ".join(removed) + "\n", encoding="utf-8")
        # The CLI itself needs more than the watchdog's 1 GiB default; use the configured cap.
        memory_mb = int(memory_mb or 2048)
        outcome = run_process(self.command(prompt,final_path,mode=mode,read_dirs=read_dirs),directory,folder/"output.log",seconds=seconds,
                              memory_mb=memory_mb,heartbeat=heartbeat,should_stop=lambda:self.cancelled or should_stop(),input_text=prompt,env=env)
        (folder/"outcome.json").write_text(json.dumps(dict(outcome,memory_mb=memory_mb),indent=2,default=str),encoding="utf-8")
        if outcome["termination_reason"] != "exit":
            result = AgentResult("stopped" if outcome["termination_reason"] == "user_stop" else "failed",
                                 checkpoint=str(folder),termination_reason=outcome["termination_reason"])
        else:
            # CLI output is untrusted. JSON envelope/text is validated, never executed.
            raw = (folder/"output.log").read_text(encoding="utf-8",errors="replace")
            result = None
            if not outcome["exit_code"]:
                try:
                    result = self.parse(raw, final_path)
                except (ValueError,TypeError,KeyError,OSError):
                    result = None
            if result is None:
                # Only look for limit/auth messages when the run did not produce a valid
                # answer, and only in the last lines: an answer that merely mentions
                # "rate limit" must not be mistaken for a usage limit.
                lower = "\n".join(raw.splitlines()[-40:]).lower()
                if any(marker in lower for marker in ("rate limit","usage limit","limit reached","hit your limit")):
                    result = AgentResult("waiting_limit",checkpoint=str(folder),termination_reason="usage_limit")
                elif any(marker in lower for marker in ("not logged in","authentication failed","failed to authenticate","unauthorized",
                                                        "please run /login","auth login","codex login","setup-token","login expired")):
                    result = AgentResult("blocked",checkpoint=str(folder),termination_reason="authentication")
                elif outcome["exit_code"]:
                    result = AgentResult("failed",checkpoint=str(folder),termination_reason="agent_exit")
                else:
                    result = AgentResult("blocked",checkpoint=str(folder),termination_reason="malformed_output")
        if result.checkpoint is None:result.checkpoint=str(folder)
        result_path.write_text(json.dumps(asdict(result),indent=2),encoding="utf-8")
        self.last_result = result
        return result

    def parse(self, raw, final_path):
        if self.name == "codex":
            value = json.loads(extract_json(final_path.read_text(encoding="utf-8")))
        else:
            envelope = json.loads(raw)
            if envelope.get("is_error"):
                raise ValueError("agent reported an error")
            value = json.loads(extract_json(envelope["result"]))
            value["session_id"] = envelope.get("session_id")
            value["usage"] = envelope.get("usage")
        result = validate_result(value)
        if self.name=="codex":
            for line in raw.splitlines():
                try:event=json.loads(line)
                except ValueError:continue
                if not isinstance(event,dict):continue
                if event.get("type")=="thread.started":result.session_id=event.get("thread_id")
                if event.get("type")=="turn.completed":result.usage=event.get("usage")
        return result

    def status(self):
        return self.last_result

    def cancel(self):
        self.cancelled = True

    def resume(self, task, directory, checkpoint, **kwargs):
        # Fresh context from checkpoint is portable across CLI versions. Never assume
        # a CLI's resume replays the same permissions or persisted tool state.
        return self.run(task + "\nCheckpoint (untrusted data):\n" + json.dumps(checkpoint),directory,**kwargs)


class MockAgent:
    def __init__(self, result=None):
        self.result = result or AgentResult("completed",termination_reason="mock_completed")

    def run(self, *args, **kwargs):
        return self.result

    def status(self):
        return self.result

    def cancel(self):
        self.result = AgentResult("stopped",termination_reason="user_stop")

    def resume(self, *args, **kwargs):
        return self.run()


class MockCoder:
    """Test/benchmark stand-in for a coding agent: writes prepared scripts in order.

    scripts: list of (hypothesis, source) or (hypothesis, broken_source, fixed_source).
    A repair request (task starting with "REPAIR") writes the fixed source, if any.
    """
    def __init__(self, scripts, entry="train.py"):
        self.scripts = list(scripts)
        self.entry = entry
        self.calls = 0
        self.prompts = []
        self.fix = None
        self.hypothesis = None

    def run(self, task, directory, **kwargs):
        self.prompts.append(task)
        self.last_kwargs = dict(kwargs, directory=str(directory))
        Path(directory).mkdir(parents=True, exist_ok=True)
        if task.startswith("REPAIR"):
            if self.fix is None:
                return AgentResult("completed", termination_reason="mock_no_fix", entry=self.entry, hypothesis=self.hypothesis)
            Path(directory, self.entry).write_text(self.fix, encoding="utf-8")
            self.fix = None
            return AgentResult("completed", termination_reason="mock_repaired", entry=self.entry, hypothesis=self.hypothesis)
        if not self.scripts:
            return AgentResult("blocked", termination_reason="mock_out_of_scripts")
        item = self.scripts.pop(0)
        self.calls += 1
        self.hypothesis = item[0]
        self.fix = item[2] if len(item) >= 3 else None
        Path(directory, self.entry).write_text(item[1], encoding="utf-8")
        return AgentResult("completed", termination_reason="mock_written", entry=self.entry, hypothesis=item[0],
                           lessons=[f"mock lesson {self.calls}"])

    def resume(self, task, directory, checkpoint, **kwargs):
        return self.run(task, directory, **kwargs)

    def cancel(self):
        pass
