"""Bounded retry policy; uncertain remote launches are never retried."""
def recovery_action(reason,attempt,*,maximum=3):
    if reason in {"usage_limit","rate_limit"}:
        return dict(state="WAITING_LIMIT",retry=False,delay_seconds=None,next_action="checkpoint; wait for plan reset")
    if reason in {"ambiguous_launch","authentication","missing_binary","malformed_output","safety","unknown_price"}:
        return dict(state="BLOCKED",retry=False,delay_seconds=None,next_action="inspect and reconcile; no fallback")
    if reason in {"user_stop","deadline","budget"}:
        return dict(state="STOPPED",retry=False,delay_seconds=None,next_action="preserve checkpoint")
    retry=attempt<maximum
    return dict(state="PENDING" if retry else "FAILED",retry=retry,
                delay_seconds=min(60,2**attempt) if retry else None,next_action="bounded resume from checkpoint" if retry else "inspect exhausted attempts")
