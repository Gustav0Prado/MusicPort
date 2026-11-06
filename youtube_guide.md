# YouTube Music credentials guide (`browser.json`)

This project uses [`ytmusicapi`](https://ytmusicapi.readthedocs.io/) with **browser request-header authentication** and expects a file named `browser.json` in the project root.

With this method you do **not** need a Google Cloud project, OAuth client ID, client secret, or API key. You reuse the session headers from a logged-in YouTube Music browser tab.

> **Note:** `ytmusicapi` 1.12.x still supports browser authentication but marks it as deprecated in favor of OAuth. This project is built around `browser.json`, so this guide covers the request-header method. If `ytmusicapi` removes it in a future release, the project will need to switch to OAuth.

> **Security warning:** `browser.json` gives access to your logged-in YouTube Music/Google account. Treat it like a password. Never commit it, paste it into chats/issues, or share screenshots showing its contents.

---

## 1. What is inside `browser.json`?

`ytmusicapi` needs a small set of headers copied from an authenticated YouTube Music request:

| Header | Why it matters |
| --- | --- |
| `Cookie` | The real credential. It must contain `__Secure-3PAPISID`. |
| `Authorization` | Must contain `SAPISIDHASH`. Used to detect browser authentication; `ytmusicapi` refreshes it from the cookie. |
| `X-Goog-AuthUser` | Selects the Google account index. Usually `0`. |
| `x-origin` | Should be `https://music.youtube.com`. |
| `Accept` / `Content-Type` | Normal request headers; included in the minimal template. |

The important parts are the **cookie** and the **authorization** headers. If `__Secure-3PAPISID` is missing from the cookie, `ytmusicapi` cannot authenticate.

---

## 2. Copy the request headers from your browser

Use a desktop browser and make sure you are logged into **YouTube Music**, not just regular YouTube.

### Firefox (recommended)

1. Open <https://music.youtube.com> and confirm you are logged in.
2. Press `F12` (or right-click → **Inspect**).
3. Open the **Network** tab.
4. In the filter box, type `/browse`.
5. Reload the page, or click **Library** in the top bar, until a request appears.
6. Select a request that is:
   - **Status:** `200`
   - **Method:** `POST`
   - **Domain:** `music.youtube.com`
   - **File:** `browse?...`
7. Right-click the request and choose **Copy → Copy Request Headers**.

### Chrome / Edge

1. Open <https://music.youtube.com> and confirm you are logged in.
2. Press `F12` (or right-click → **Inspect**).
3. Open the **Network** tab.
4. In the filter box, type `/browse`.
5. Reload the page, or click **Library** in the top bar, until a request appears.
6. Select a `browse?...` request with status `200` and method `POST`.
7. Click it, open the **Headers** tab, and scroll to **Request Headers**.
8. Select everything from `accept: */*` to the end of the request-header section and copy it.

On newer Chrome/Edge versions you can instead right-click the request and use **Copy → Copy as fetch (Node.js)**, then keep only the fields shown in the manual template in section 4.

> Do not copy the URL, the response body, or a cURL command. `ytmusicapi` expects raw `Header: value` lines.

---

## 3. Create `browser.json` with the CLI

The installed package provides a `ytmusicapi` command. From the project root, run:

```bash
.venv/bin/ytmusicapi browser --file browser.json
```

If your virtual environment is activated, this is simply:

```bash
ytmusicapi browser --file browser.json
```

The command prints:

```text
Please paste the request headers from Firefox or Chrome/Edge and press Ctrl-D to continue:
```

Paste the headers you copied, then press `Ctrl-D` on Linux/macOS. On Windows, press `Enter`, then `Ctrl-Z`, then `Enter`.

The command writes `browser.json` in the current directory. If you leave out `--file`, it still defaults to `browser.json`.

### Safer overwrite workflow

If you already have a working `browser.json`, write the new credentials to a temporary file first:

```bash
.venv/bin/ytmusicapi browser --file browser_new.json
```

Validate it with the steps in section 5, then replace the old file:

```bash
mv browser_new.json browser.json
```

---

## 4. Manual `browser.json` creation

If you prefer not to use the CLI, create `browser.json` manually with this structure:

```json
{
  "Accept": "*/*",
  "Authorization": "PASTE_AUTHORIZATION",
  "Content-Type": "application/json",
  "X-Goog-AuthUser": "0",
  "x-origin": "https://music.youtube.com",
  "Cookie": "PASTE_COOKIE"
}
```

Where:

- `PASTE_AUTHORIZATION` is the value of the **Authorization** request header. It should start with `SAPISIDHASH`.
- `PASTE_COOKIE` is the entire **Cookie** request header, a long semicolon-separated string. It must contain `__Secure-3PAPISID=...`.

Important:

- The file must be valid JSON.
- Do not add comments or trailing commas.
- Do not put line breaks inside the `Cookie` or `Authorization` values.
- If you use a **brand account**, copy the headers while that brand account is selected. `X-Goog-AuthUser` may be `1`, `2`, etc. instead of `0`.

---

## 5. Validate the credentials

First, check that the file is valid JSON:

```bash
.venv/bin/python -m json.tool browser.json > /dev/null && echo "browser.json is valid JSON"
```

Then verify that authentication actually works:

```bash
.venv/bin/python - <<'PY'
from ytmusicapi import YTMusic

ytmusic = YTMusic("browser.json")
print("Auth type:", ytmusic.auth_type)
print("Library playlists:", len(ytmusic.get_library_playlists(limit=None)))
PY
```

A successful result looks like:

```text
Auth type: AuthType.BROWSER
Library playlists: 12
```

You can also run the project:

```bash
python main.py
```

A successful start includes:

```text
Checking YouTube Music credentials...
  YouTube Music OK: N playlists
```

---

## 6. How `main.py` uses it

By default, `main.py` loads:

```text
browser.json
```

through:

```python
ytmusic = YTMusic(YOUTUBE_AUTH)
```

You can point the project at a different file with the `YOUTUBE_AUTH` environment variable:

```bash
YOUTUBE_AUTH="path/to/browser.json" python main.py
```

---

## 7. Protect `browser.json`

Add this to `.gitignore` if the project becomes a Git repository:

```gitignore
browser.json
```

On Linux/macOS you can restrict the file permissions:

```bash
chmod 600 browser.json
```

Keep it out of cloud-synced folders, backups, and screenshots.

---

## 8. Common errors

| Error | Meaning | Fix |
| --- | --- | --- |
| `Invalid auth JSON string or file path provided.` | `browser.json` is missing, is not valid JSON, or the path is wrong. | Check the filename and validate the JSON. |
| `The following entries are missing in your headers: cookie, x-goog-authuser` | The copied text did not include those request headers. | Copy the full **Request Headers** section from a `browse` POST request. |
| `Your cookie is missing the required value __Secure-3PAPISID` | The cookie is incomplete, or the headers came from a logged-out request. | Log in again at <https://music.youtube.com> and copy fresh headers. |
| `Server returned HTTP 401` or `403` | The session expired or Google rejected the credentials. | Log out and back in, then recopy the headers. |
| `Please provide authentication before using this function` | `YTMusic` was created without credentials, or authentication was not detected. | Make sure `main.py` points to a valid `browser.json`. |
| `400 Bad Request` after it worked previously | The browser session changed or expired. | Generate a fresh `browser.json`. |
| Library appears empty | You are authenticated as a different account than expected. | Copy headers from the account whose playlists you want to compare. |
| Brand-account playlists are missing | The headers were copied from the wrong account index. | Select the brand account in YouTube Music and copy the headers again. |

---

## 9. Expiry and renewal

Browser credentials typically stay valid for a long time, but they are tied to your Google session. They stop working if:

- You log out of Google/YouTube in that browser.
- You change your Google password.
- Google revokes the session.
- `ytmusicapi` or YouTube changes the authentication format.

If authentication suddenly fails, repeat section 2 and regenerate `browser.json`.

---

## 10. Why not OAuth?

`ytmusicapi` recommends OAuth for most new projects because browser authentication is deprecated. However:

- This project currently expects a `browser.json` request-header file.
- Browser authentication requires no Google Cloud setup.
- OAuth would require changing `main.py` to pass `OAuthCredentials` to `YTMusic(...)`.

For now, the request-header method is the simplest way to get this project running.
