"""Send push notifications to your phone.

Security:
- Push subscriptions and the VAPID private key live only in GitHub Secrets.
- The page never sends subscriptions anywhere: you paste yours into a Secret yourself,
  so there is no public endpoint that anyone could abuse.
- Logs show only counts and status codes, never subscription URLs or keys.
"""
import json
import os


def load_subscriptions() -> list[dict]:
    raw = os.environ.get("PUSH_SUBSCRIPTIONS", "").strip()
    if not raw:
        return []
    data = json.loads(raw)
    subs = data if isinstance(data, list) else [data]
    valid = []
    for s in subs:
        if (
            isinstance(s, dict)
            and str(s.get("endpoint", "")).startswith("https://")
            and isinstance(s.get("keys"), dict)
            and {"p256dh", "auth"} <= set(s["keys"])
        ):
            valid.append(s)
    return valid


def send_all(notifications: list[dict], sender=None) -> dict:
    """notifications: [{"title", "body", "url", "tag"}]. Returns counts for the log."""
    counts = {"sent": 0, "failed": 0, "expired": 0, "skipped": 0}
    subs = load_subscriptions()
    key = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    contact = os.environ.get("VAPID_CONTACT", "").strip() or "mailto:admin@example.com"
    if not notifications:
        return counts
    if not subs or not key:
        counts["skipped"] = len(notifications)
        return counts

    if sender is None:
        from pywebpush import WebPushException, webpush

        def sender(sub, payload):
            try:
                webpush(
                    subscription_info=sub,
                    data=payload,
                    vapid_private_key=key,
                    vapid_claims={"sub": contact},
                    ttl=24 * 3600,
                )
                return 201
            except WebPushException as exc:
                return getattr(exc.response, "status_code", 0) or 0

    for note in notifications:
        payload = json.dumps(note, ensure_ascii=False)[:3000]  # push payloads must stay small
        for sub in subs:
            status = sender(sub, payload)
            if 200 <= status < 300:
                counts["sent"] += 1
            elif status in (404, 410):
                counts["expired"] += 1
            else:
                counts["failed"] += 1
    return counts
