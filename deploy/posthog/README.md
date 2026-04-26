# PostHog analytics — opt-in setup

Anonymous, cookie-free analytics for tdoc.xyz. Off by default until you
add your own PostHog project key.

## Why opt-in is the default

`product/web/analytics.js` honours four guards:

1. `navigator.doNotTrack === "1"` — the user told the browser to not be tracked.
2. `localStorage["tdoc-analytics-opt-out"] === "1"` — explicit opt-out.
3. **No project key** — until you add one, the script exits in the first
   ten lines and makes zero network requests.
4. No cookies. The anonymous distinct id lives in `localStorage` and is
   regenerated when the user clears site data.

## Enable in 2 minutes (free tier, no card)

1. Sign up at https://posthog.com (EU or US region — both supported).
2. Create a project named **tdoc**. Copy its **project API key**
   (looks like `phc_…`).
3. Drop a one-line file at `product/web/analytics-config.js`:

   ```js
   window.TDOC_PH_KEY = "phc_YOUR_KEY_HERE";
   // Optional override; defaults to https://eu.i.posthog.com:
   // window.TDOC_PH_HOST = "https://us.i.posthog.com";
   ```

4. Commit + push. CF Pages picks it up; analytics activates on next page load.

## Events that fire

| Event             | Where           | Properties                     |
|-------------------|-----------------|--------------------------------|
| `pageview`        | every page      | `$pathname`, `$referrer`       |
| `try_uploaded`    | /try            | `ext`, `size_kb`               |
| `try_tab_switched`| /try            | `tab`                          |
| `try_downloaded`  | /try            | `format` (pdf / tdoc)          |
| `view_uploaded`   | /view           | `ext`, `size_kb`               |
| `view_downloaded` | /view           | `format`                       |
| `view_printed`    | /view           | —                              |
| `download_clicked`| any download link  | `href` (path only)         |
| `outbound_clicked`| any external link  | `host` (no path)           |

No event records the document content, the API key, or the user identity.

## CSP

`product/web/_headers` already includes the PostHog hosts in `connect-src`:
`https://eu.i.posthog.com https://us.i.posthog.com https://app.posthog.com`.

## Removing analytics later

Delete `product/web/analytics-config.js` and push. Script becomes a no-op
again, no other change needed.

## Honouring user opt-out

A user can opt out at any time without contacting us by running this
in their browser DevTools console once:

```js
localStorage.setItem("tdoc-analytics-opt-out", "1");
```

The script reads the flag on every load and exits early if set.
