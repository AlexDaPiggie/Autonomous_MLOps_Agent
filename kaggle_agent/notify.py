"""Optional phone alerts. Best effort: an alert failure never stops a run.

Configure with `ka setup`:
  ntfy:     install the free ntfy app, subscribe to a long random topic name.
  telegram: create a bot with @BotFather, send it a message, use its token + your chat id.
"""
import json
import urllib.parse
import urllib.request


def send(settings, title, message):
    alerts = (settings or {}).get("alerts") or {}
    sent = []
    try:
        if alerts.get("ntfy_topic"):
            server = alerts.get("ntfy_server", "https://ntfy.sh").rstrip("/")
            request = urllib.request.Request(f"{server}/{urllib.parse.quote(alerts['ntfy_topic'])}",
                                             data=message.encode("utf-8"), headers={"Title": title[:200]})
            urllib.request.urlopen(request, timeout=10).read()
            sent.append("ntfy")
    except Exception:
        pass
    try:
        if alerts.get("telegram_token") and alerts.get("telegram_chat"):
            body = urllib.parse.urlencode(dict(chat_id=alerts["telegram_chat"], text=f"{title}\n{message}")).encode()
            urllib.request.urlopen(f"https://api.telegram.org/bot{alerts['telegram_token']}/sendMessage", data=body, timeout=10).read()
            sent.append("telegram")
    except Exception:
        pass
    return sent
