# Spotify credentials guide

This project uses [`spotify_scraper`](https://spotifyscraper.readthedocs.io/), **not** the official Spotify Web API. That means you do **not** need a Client ID, Client Secret, redirect URI, or developer app.

You only need one thing:

1. A valid **`sp_dc`** cookie from a logged-in Spotify account.
2. A `spotify_cookies.txt` file in the project root containing that cookie.
3. The Spotify **username or profile URL** whose playlists you want to compare.

> **Security warning:** `sp_dc` is equivalent to a login session for your Spotify account. Treat it like a password. Never commit it, paste it into chats/issues, or share screenshots that show it. The `.gitignore` entry below is strongly recommended.

---

## 1. Find your Spotify username / profile URL

You can enter either a username or a profile URL when `main.py` asks.

Easiest way to get the URL:

1. Open <https://open.spotify.com> and log in.
2. Click your profile picture/name in the top-right corner.
3. Open your profile.
4. Copy the URL from the address bar. It looks like:

```text
https://open.spotify.com/user/your_username
```

The username is the part after `/user/`.

> `main.py` reads playlists from this profile, including private ones owned by the logged-in account.

---

## 2. Get the `sp_dc` cookie

### Chrome / Edge

1. Open <https://open.spotify.com> and make sure you are logged in.
2. Press `F12` (or right-click → **Inspect**).
3. Go to the **Application** tab.
4. In the left sidebar, open **Cookies → `https://open.spotify.com`**.
5. Find the row named **`sp_dc`**.
6. Copy its **Value** (a long opaque string).

### Firefox

1. Open <https://open.spotify.com> and make sure you are logged in.
2. Press `F12` (or right-click → **Inspect**).
3. Go to the **Storage** tab.
4. Open **Cookies → `https://open.spotify.com`**.
5. Find the row named **`sp_dc`**.
6. Copy its **Value**.

> Only `sp_dc` is needed. You do **not** need `sp_key`, `sp_t`, or any other cookie.

---

## 3. Create `spotify_cookies.txt`

`spotify_scraper` accepts a Netscape-format cookie file. The file must be in the **project root**, next to `main.py`.

### Option A: create it manually

Create a file named `spotify_cookies.txt` with exactly one cookie line:

```text
# Netscape HTTP Cookie File
.spotify.com	TRUE	/	TRUE	0	sp_dc	PASTE_YOUR_sp_dc_VALUE_HERE
```

Important details:

- The seven fields are separated by **real TAB characters**, not spaces.
- Replace `PASTE_YOUR_sp_dc_VALUE_HERE` with the value copied from the browser.
- The `0` expiry is fine; the library only reads the cookie value.
- Do not add quotes around the value.

You can also store your Spotify username in the same file as a comment:

```text
# SPOTIFY_USER=your_username
```

`main.py` reads this line when `SPOTIFY_USER` is not set in the environment. Keep the leading `#` so `spotify_scraper` continues to ignore it as a normal Netscape cookie-file comment. An environment value takes precedence over the file.

### Option B: create it from the terminal

This avoids putting the cookie directly in your shell history:

```bash
read -rsp "Paste your sp_dc value: " SP_DC
echo
printf '# Netscape HTTP Cookie File\n.spotify.com\tTRUE\t/\tTRUE\t0\tsp_dc\t%s\n' "$SP_DC" > spotify_cookies.txt
chmod 600 spotify_cookies.txt
unset SP_DC
```

The `chmod 600` makes the file readable only by your user.

### Check that the file exists

```bash
ls -l spotify_cookies.txt
```

Do **not** use `cat` on it if someone can see your screen.

---

## 4. Protect the cookie file

If this project ever becomes a Git repository, add this to `.gitignore`:

```gitignore
spotify_cookies.txt
```

Keep the file out of backups, cloud-synced folders, and screenshots.

---

## 5. Configure the project

By default, `main.py` looks for:

```text
spotify_cookies.txt
browser.json
```

Then run:

```bash
python main.py
```

`main.py` reads your Spotify username/profile URL from the `SPOTIFY_USER` environment variable or from the `# SPOTIFY_USER=...` line in `spotify_cookies.txt`. If neither is present, it prints an error and stops. Otherwise it validates both Spotify and YouTube Music credentials and only then starts comparing playlists.

You can also set the username and file paths through environment variables:

```bash
SPOTIFY_USER="https://open.spotify.com/user/your_username" python main.py
```

```bash
SPOTIFY_COOKIES="path/to/spotify_cookies.txt" \
YOUTUBE_AUTH="path/to/browser.json" \
python main.py
```

> `SPOTIFY_COOKIES` must point to a **file** in this project. Passing the raw `sp_dc` value directly is not supported by `main.py`.

On Windows PowerShell:

```powershell
$env:SPOTIFY_USER = "your_username"
python main.py
```

---

## 6. Verify it works

A successful run starts with something like:

```text
Checking Spotify credentials...
  Spotify OK: Your Name
Checking YouTube Music credentials...
  YouTube Music OK: N playlists
```

If you want to test only the Spotify side without running the full comparison:

```python
from spotify_scraper import SpotifyClient

with SpotifyClient(cookies="spotify_cookies.txt") as client:
    profile = client.get_user("your_username")
    print(profile.name)
```

If this prints your profile name, the cookie and username are valid.

---

## 7. Common errors

| Error | Meaning | Fix |
| --- | --- | --- |
| `Spotify cookies file not found: spotify_cookies.txt` | The file is missing or in the wrong folder. | Create it in the project root, or set `SPOTIFY_COOKIES` to its path. |
| `Spotify username not found...` | Neither `SPOTIFY_USER` nor a `# SPOTIFY_USER=...` line in the cookies file is set. | Set the environment variable or add the line to `spotify_cookies.txt`. |
| `Spotify authentication failed...` | `sp_dc` is missing, expired, revoked, or malformed. | Log in again at <https://open.spotify.com>, copy a fresh `sp_dc`, and recreate the file. |
| `Could not load the Spotify profile ...` | Username/profile URL is wrong, or the profile is not public. | Use the exact profile URL from the browser and confirm the profile is public. |
| Only some playlists are compared | The internal Spotify library query failed and the script fell back to public playlists. | Update `LIBRARY_V3_HASH` in `spotify_library.py`. |
| No playlists with matching names | Names differ after normalization, or no names match between services. | Rename playlists so they match, or add manual mappings. |

---

## Notes

- The cookie is sent only to Spotify by `spotify_scraper`; it is never printed by this project.
- Spotify can expire or rotate sessions at any time. If authentication suddenly stops working, repeat step 2.
- The browser-assisted `SpotifyClient.login()` feature exists in `spotify_scraper`, but it requires the optional `browser` extra and stores the session elsewhere. This project is configured for the `spotify_cookies.txt` file approach.
