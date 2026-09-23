"""Daily check: fetch each watched policy, detect changes, explain them, notify.

Run by GitHub Actions once a day (see .github/workflows/check.yml).
Output files (committed back to the repo and shown by the web app):
  data/snapshots/<app>.txt   last saved text of each policy
  docs/data/status.json      one entry per app for the landing page
  docs/data/changes.json     every detected change, newest first
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import push  # noqa: E402
import summarize as ai  # noqa: E402
import textdiff  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MIN_PAGE_CHARS = 1500      # less than this usually means a block page or an empty shell
MAX_CHANGES_KEPT = 300
EXCERPT_CHARS = 1500
APP_ID = re.compile(r"^[a-z0-9-]{1,40}$")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text("utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, "utf-8")
    tmp.replace(path)


def load_watchlist(root: Path) -> list[dict]:
    apps = read_json(root / "watchlist.json", {}).get("apps", [])
    valid = []
    for a in apps:
        if not APP_ID.match(str(a.get("id", ""))):
            print(f"Skipping watchlist entry with bad id: {a.get('id')!r}")
            continue
        if not str(a.get("policy_url", "")).startswith("https://"):
            print(f"Skipping {a['id']}: policy_url must start with https://")
            continue
        valid.append({"id": a["id"], "name": str(a.get("name", a["id"]))[:40], "policy_url": a["policy_url"]})
    return valid


def fallback_summary(app_name: str) -> dict:
    return {
        "meaningful": True,
        "risk": "Unreviewed",
        "risk_reason": "The automatic summary failed, so this change hasn't been rated.",
        "headline": f"{app_name} changed its privacy policy",
        "what_changed": "The policy text changed, but the automatic summary couldn't be created.",
        "what_it_means": "Compare the before and after text below to see what's different.",
        "what_you_can_do": "Review the changed text, or check again after the next daily run.",
    }


def run(root: Path = ROOT, fetch_text=None, summarizer=None, sender=None) -> dict:
    stamp = now_iso()
    apps = load_watchlist(root)
    status_path = root / "docs/data/status.json"
    changes_path = root / "docs/data/changes.json"
    status = read_json(status_path, {"apps": {}})
    changes = read_json(changes_path, {"changes": []})["changes"]
    summarizer = summarizer or ai.summarize
    new_changes, report = [], {"checked": 0, "baseline": 0, "unchanged": 0, "changed": 0, "minor": 0, "errors": 0}

    prev = status.get("apps", {})
    app_status = {}
    for app in apps:
        entry = dict(prev.get(app["id"], {}))
        entry.update({"name": app["name"], "policy_url": app["policy_url"], "last_checked": stamp})
        entry.pop("error", None)
        app_status[app["id"]] = entry
        snap = root / "data/snapshots" / f"{app['id']}.txt"
        try:
            text = textdiff.normalize(fetch_text(app["policy_url"]))
            if len(text) < MIN_PAGE_CHARS:
                raise RuntimeError("page looked empty or blocked")
        except Exception as exc:  # keep going with the other apps
            report["errors"] += 1
            entry["state"] = "error" if entry.get("state") in (None, "error") else entry["state"]
            entry["error"] = "Couldn't check today"
            print(f"[{app['id']}] fetch failed: {type(exc).__name__}: {str(exc)[:200]}")
            continue

        report["checked"] += 1
        if not snap.exists():
            write_atomic(snap, text)
            entry.update(state="watching", watching_since=stamp)
            report["baseline"] += 1
            print(f"[{app['id']}] first snapshot saved")
            continue

        old = snap.read_text("utf-8")
        if textdiff.fingerprint(old) == textdiff.fingerprint(text):
            entry.setdefault("state", "watching")
            if entry["state"] == "error":
                entry["state"] = "watching"
            report["unchanged"] += 1
            continue

        removed, added = textdiff.changed_passages(old, text)
        write_atomic(snap, text)
        if not textdiff.is_meaningful(removed, added):
            report["minor"] += 1
            print(f"[{app['id']}] tiny edit saved silently")
            continue

        removed_txt, added_txt = "\n".join(removed), "\n".join(added)
        try:
            summary = summarizer(app["name"], removed_txt, added_txt)
        except Exception as exc:
            print(f"[{app['id']}] summary failed: {str(exc)[:200]}")
            summary = fallback_summary(app["name"])
        if not summary["meaningful"]:
            report["minor"] += 1
            print(f"[{app['id']}] AI judged the edit as wording only; saved silently")
            continue

        change = {
            "id": f"{app['id']}-{stamp[:19].replace(':', '').replace('-', '')}",
            "app_id": app["id"],
            "app_name": app["name"],
            "detected_at": stamp,
            "source_url": app["policy_url"],
            "risk": summary["risk"],
            "risk_reason": summary["risk_reason"],
            "headline": summary["headline"],
            "what_changed": summary["what_changed"],
            "what_it_means": summary["what_it_means"],
            "what_you_can_do": summary["what_you_can_do"],
            "before_excerpt": textdiff.clip(removed, EXCERPT_CHARS),
            "after_excerpt": textdiff.clip(added, EXCERPT_CHARS),
            "ai_generated": True,
        }
        new_changes.append(change)
        entry.update(state="changed", last_changed=stamp, latest_change_id=change["id"])
        report["changed"] += 1
        print(f"[{app['id']}] CHANGE detected ({summary['risk']})")

    changes = (new_changes + changes)[:MAX_CHANGES_KEPT]
    write_atomic(status_path, json.dumps({"last_run": stamp, "apps": app_status}, indent=2, ensure_ascii=False))
    write_atomic(changes_path, json.dumps({"changes": changes}, indent=2, ensure_ascii=False))

    if len(new_changes) > 3:
        notes = [{
            "title": f"{len(new_changes)} apps changed their privacy policies",
            "body": ", ".join(c["app_name"] for c in new_changes),
            "url": "./",
            "tag": f"batch-{stamp[:10]}",
        }]
    else:
        notes = [{
            "title": f"{c['app_name']} · {c['risk']} risk",
            "body": c["headline"],
            "url": f"./#change={c['id']}",
            "tag": c["id"],
        } for c in new_changes]
    report["push"] = push.send_all(notes, sender=sender)
    return report


def main() -> int:
    from fetch import Browser

    with Browser() as browser:
        report = run(fetch_text=browser.page_text)
    print("Summary:", json.dumps(report))
    # Fail the run (so GitHub emails you) only if every app failed to load.
    return 1 if report["checked"] == 0 and report["errors"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
