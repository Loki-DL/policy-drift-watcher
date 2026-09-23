# Policy Drift Watcher (Step 1 prototype)

A home-screen web app that watches 10 apps' privacy policies once a day. When a policy
changes, it flags the app on the landing page with a red **Changed** badge and a risk
level, and sends a push notification to your phone with a plain-English explanation.

- **Daily checker:** runs free on GitHub Actions (`checker/`, `.github/workflows/check.yml`)
- **Web app:** hosted free on GitHub Pages (`docs/`)
- **AI summaries:** Claude API
- **Apps watched:** edit `watchlist.json`

All setup steps can be done from your iPhone in Safari.

---

## Setup (about 20 minutes)

### 1. Lock down your accounts first
- GitHub: **Settings → Password and authentication → Enable two-factor authentication.**
- Anthropic: sign in at console.anthropic.com and turn on two-factor login too.

### 2. Get a Claude API key
1. At console.anthropic.com, go to **API Keys → Create key** and name it `policy-drift-watcher`.
2. Copy the key. You'll paste it in step 3. Don't save it anywhere else.
3. Under **Billing / Limits**, set a low monthly spend limit (e.g. $5). Daily checks of 10 policies cost
   very little, and a limit caps the damage if the key ever leaks.

### 3. Add the secrets to GitHub
In your repository, go to **Settings → Secrets and variables → Actions → New repository secret**
and add each of these:

| Name | Value |
| --- | --- |
| `ANTHROPIC_API_KEY` | The key from step 2 |
| `VAPID_PRIVATE_KEY` | The private alert key from the `vapid_private_key.txt` file Claude gave you. Delete that file afterwards. |
| `VAPID_CONTACT` | `mailto:` followed by your email address, e.g. `mailto:you@example.com` |

Leave `PUSH_SUBSCRIPTIONS` for step 6.

### 4. Turn on the website
**Settings → Pages → Source: Deploy from a branch → Branch: `main`, folder: `/docs` → Save.**
After about a minute your app is live at `https://<your-username>.github.io/policy-drift-watcher/`.

### 5. Run the first check
**Actions → Daily policy check → Run workflow.** The first run saves a copy of each policy.
You won't get alerts from this run, because there's nothing to compare against yet. After that
it runs every day by itself.

### 6. Install the app on your iPhone and turn on alerts
1. Open your app's address in **Safari**.
2. Tap **Share → Add to Home Screen → Add**.
3. Open **Drift Watch** from your Home Screen (not from Safari) and tap **Turn on alerts → Allow**.
4. Tap **Copy key**, then add it on GitHub as a new secret named **`PUSH_SUBSCRIPTIONS`**.
5. Tap **Test alert** to check that notifications appear, then tap **I've saved it — hide this**.

Alerts need iOS 16.4 or later. If you reinstall the app, repeat step 6 and replace the
`PUSH_SUBSCRIPTIONS` secret with the new key.

---

## Everyday use
- **Red "Changed" badge:** a new change you haven't opened yet. Tap it to see what changed, what
  it means for you and what to do. The badge clears once you've read it.
- **"Couldn't check today":** the site blocked the check or the page moved. It retries the next day.
  If it keeps happening, the policy URL in `watchlist.json` probably needs updating.
- **Add or remove apps:** edit `watchlist.json` on GitHub (the pencil icon). Each app needs a
  short lowercase `id`, a `name`, and an `https://` policy link.
- **Run a check now:** Actions → Daily policy check → Run workflow.

## How it keeps you safe (secure by default)
- **No accounts, no tracking, no data collected.** The app has no analytics or third-party code,
  and "seen" markers stay on your phone.
- **Keys stay in GitHub Secrets.** The API key, the private alert key and your phone's alert
  subscription are never in the code or on the website.
- **Nobody else can send you alerts.** The website has no way to accept data from visitors.
  Only the daily job, running with your secrets, can send a notification.
- **Pages from other sites are treated as untrusted.** Only the visible text is kept, the AI is
  told to ignore any instructions hidden in it, and its reply must match a strict format
  (fixed fields, allowed risk levels, length limits, plain text only), or it's rejected.
- **Locked-down web app.** A strict Content Security Policy allows only the app's own files. All
  text is displayed as plain text, and notifications can only open pages inside the app.
- **Least privilege.** The workflow is read-only except for the one step that saves results.
  Dependabot flags outdated libraries weekly.
- **Tested.** `tests/` has 17 offline tests covering change detection, noise filtering, AI reply
  validation, prompt-injection wrapping and unsafe watchlist entries. They run before every check.

### If a key leaks
- **Claude API key:** delete it in the Anthropic console, create a new one and update the secret.
- **Alert keys:** ask Claude to generate a new VAPID key pair, update `docs/config.js` and the
  `VAPID_PRIVATE_KEY` secret, then redo step 6.

## Limits of this prototype
- Only privacy policies are watched. Terms of service and app store labels come later.
- Some sites block automated checks. Those apps show "Couldn't check today".
- Summaries are AI-generated and are not legal advice. Always check the before/after wording.
- The model is set to `claude-sonnet-5`. To change it, add an Actions **variable** (not a secret)
  named `CLAUDE_MODEL`.
