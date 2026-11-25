"""Provider protocol and deterministic fault-injection provider. No cloud SDKs."""
from typing import Protocol


class Provider(Protocol):
    name: str
    def launch(self, key: str, payload: dict) -> str: ...
    def reconcile(self, key: str) -> dict: ...
    def cancel(self, key: str) -> None: ...


class MockProvider:
    name = "mock"

    def __init__(self, fault=None):
        self.fault = fault
        self.jobs = {}
        self.launches = 0

    def launch(self, key, payload):
        if key in self.jobs:
            return key
        self.launches += 1
        self.jobs[key] = dict(job_id=key, state="RUNNING", result=payload.get("result"))
        if self.fault == "ambiguous":
            raise ConnectionError("Injected disconnect after launch")
        return key

    def reconcile(self, key):
        if self.fault == "unreconcilable":
            return dict(state="UNKNOWN")
        return self.jobs.get(key, dict(state="UNKNOWN"))

    def cancel(self, key):
        if key in self.jobs:
            self.jobs[key]["state"] = "STOPPED"

    def complete(self, key):
        self.jobs[key]["state"] = "COMPLETED"


class DisabledProvider:
    def __init__(self, name):
        self.name = name

    def launch(self, key, payload):
        from .gates import paid_launch
        paid_launch()

    def reconcile(self, key):
        return dict(state="UNKNOWN", reason="No authorized backend; inspect provider manually")

    def cancel(self, key):
        raise RuntimeError("No authorized backend; manual cancellation required")
