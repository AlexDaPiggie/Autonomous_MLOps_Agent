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
    return AgentResult(**{k:v for k,v in value.items() if k in AgentResult.__dataclass_fields__})


class CLIAdapter:
    def __init__(self, name):
        if name not in {"codex","claude"}:
            raise ValueError("Choose codex or claude explicitly")
        self.name = name
        self.cancelled = False
        self.last_result = None

    def binary(self):
        # Windows npm CLI shims need their supported .cmd launcher, not a .ps1 file.
        return shutil.which(self.name + ".cmd") if os.name == "nt" else shutil.which(self.name)

    def doctor(self):
        binary = self.binary()
        if not binary:
            return dict(available=False,reason="missing_binary")
        result = subprocess.run([binary,"--version"],capture_output=True,text=True,timeout=15)
        return dict(available=result.returncode == 0,version=result.stdout.strip())

    def command(self, prompt):
        binary = self.binary()
        if not binary:
            raise FileNotFoundError(self.name)
        if self.name == "codex":
            return [binary,"exec","--sandbox","read-only",prompt]
        return [binary,"--print","--permission-mode","plan","--output-format","json",prompt]

    def run(self, task, directory, *, authorized=False, seconds=300, heartbeat=lambda **kw: None,
            should_stop=lambda: False):
        if not authorized:
            return AgentResult("blocked",termination_reason="agent_execution_not_enabled")
        # Same-user agents cannot be safely isolated from credentials. Adapters only
        # support reviewed research tasks, not arbitrary provider execution.
        if any(k.endswith("API_KEY") or k in {"ANTHROPIC_AUTH_TOKEN","OPENAI_BASE_URL","ANTHROPIC_BASE_URL"} for k in os.environ):
            return AgentResult("blocked",termination_reason="metered_provider_environment_present")
        if not self.binary():
            return AgentResult("blocked",termination_reason="missing_binary")
        run_id = uuid.uuid4().hex
        folder = Path(directory)/".kaggle-agent"/"sessions"/run_id
        folder.mkdir(parents=True)
        result_path = folder/"result.json"
        template = asdict(AgentResult("completed",termination_reason="task_completed"))
        prompt = (task + "\nRead shared rules explicitly. No paid work, remote mutations, submissions or pushes. "
                  "Return only a JSON object using this protocol: " + json.dumps(template))
        outcome = run_process(self.command(prompt),directory,folder/"output.log",seconds=seconds,
                              heartbeat=heartbeat,should_stop=lambda:self.cancelled or should_stop())
        if outcome["termination_reason"] != "exit":
            result = AgentResult("stopped" if outcome["termination_reason"] == "user_stop" else "failed",
                                 checkpoint=str(folder),termination_reason=outcome["termination_reason"])
        else:
            # CLI output is untrusted. JSON envelope/text is validated, never executed.
            raw = (folder/"output.log").read_text(encoding="utf-8")
            lower = raw.lower()
            if any(marker in lower for marker in ("rate limit","usage limit","limit reached")):
                result = AgentResult("waiting_limit",checkpoint=str(folder),termination_reason="usage_limit")
            elif any(marker in lower for marker in ("not logged in","authentication failed","unauthorized")):
                result = AgentResult("blocked",checkpoint=str(folder),termination_reason="authentication")
            elif outcome["exit_code"]:
                result = AgentResult("failed",checkpoint=str(folder),termination_reason="agent_exit")
            else:
                try:
                    value = json.loads(raw)
                    if self.name == "claude" and "result" in value:
                        envelope = value
                        value = json.loads(envelope["result"])
                        value["session_id"] = envelope.get("session_id")
                        value["usage"] = envelope.get("usage")
                    result = validate_result(value)
                except (ValueError,TypeError,KeyError):
                    result = AgentResult("blocked",checkpoint=str(folder),termination_reason="malformed_output")
        result_path.write_text(json.dumps(asdict(result),indent=2),encoding="utf-8")
        self.last_result = result
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
