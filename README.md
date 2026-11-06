# MusicPort: Spotify ↔ YouTube Music Playlist Auditor 🎵

A command-line tool that compares your **Spotify playlists** (public and private) with the **YouTube Music library playlists** that share the same name. It reports songs duplicated inside each service, songs missing from the other service, and "approximate" matches where the metadata differs between platforms.

Every comparison is exported as a set of CSV reports, so you can review the results in a spreadsheet.

> ⚠️ This project relies on **unofficial** access: `spotifyscraper` (cookie-based scraping) and `ytmusicapi` (browser request-header auth). It does **not** use the official Spotify Web API. Credentials are sensitive — treat them like passwords.

---

## ✨ What it does

- 🔐 Validates both Spotify and YouTube Music credentials before doing anything.
- 📚 Loads all Spotify playlists owned by your account (public and private) and all YouTube Music library playlists.
- 🔗 Matches playlists **by normalized name** (case, accents and punctuation ignored).
- 🔁 Detects duplicates inside each playlist using `title + first artist`.
- ➖ Lists songs present on one platform but missing on the other.
- 🧠 Runs a second fuzzy pass to pair songs whose metadata is formatted differently (e.g. `"Artist - Song"` YouTube uploads).
- 📄 Exports everything to CSV under `results/<playlist>/`.

---

## 🗂️ Project structure

```text
.
├── main.py                  # 🚀 Entry point: auth, playlist matching, orchestration
├── compare.py               # ⚖️ Comparison engine (normalization, matching, CSV export)
├── gui.py                   # 🖥️ Streamlit GUI to review CSV results and run comparisons
├── remove_duplicates.py     # 🧹 Standalone utility to remove duplicates from one YT Music playlist
├── test_connection.py       # 🔌 Checks Spotify and YouTube Music connectivity
├── requirements.txt         # 📦 Pinned Python dependencies
├── .gitignore               # 🙈 Excludes venv, secrets, caches and generated reports
├── browser.json             # 🔑 YouTube Music auth headers (SECRET — never commit)
├── spotify_cookies.txt      # 🔑 Spotify sp_dc cookie file (SECRET — never commit)
├── youtube_guide.md         # 📘 How to create browser.json
├── spotify_guide.md         # 📘 How to create spotify_cookies.txt
├── README.md                # 📖 This file
├── results/                 # 📊 Generated reports (one folder per matched playlist pair)
```

---

## 📜 Scripts

### 🚀 `main.py` — entry point and orchestrator

The main program. Run it with:

```bash
python main.py
```

It opens the Streamlit GUI (`streamlit run gui.py`). The actual comparison is triggered from the GUI's **"Check Playlists"** button, which calls the shared `run_comparison()` function.

What `run_comparison()` does, step by step:

1. Reads the Spotify username from `SPOTIFY_USER` or from a `# SPOTIFY_USER=...` comment in the cookies file.
2. Checks that the cookie file and the YouTube auth file exist.
3. Validates both services and prints an OK line for each.
4. Loads your Spotify playlists (public and private) and all YouTube Music library playlists.
5. Indexes YouTube playlists by normalized name.
6. For every pair of playlists with matching normalized names, calls `compare_playlists(...)`.
7. Prints a final summary with the number of matched pairs and any comparisons that errored.

It exits with an error message if credentials are missing or invalid (`FileNotFoundError`, `RuntimeError`, `ValueError`).

### 🖥️ `gui.py` — Streamlit GUI

The GUI lets you browse and review the comparison reports saved under `results/`:

1. On the home page, click **"Check Playlists"** to run a fresh comparison. The same messages that appear in the terminal are streamed on screen as each playlist is processed.
2. After the check finishes, select a playlist from the dropdown (real playlist name) and explore its tabs:
   - **Spotify Duplicates / YouTube Duplicates** — tracks repeated within each service.
   - **Missing from Spotify / Missing from YouTube** — tracks present on one side but not the other.
   - **Approximate Matches** — fuzzy pairs matched despite different metadata.
3. Columns shown per table: **Title, Album, Artists, Duration** (and the Spotify/YouTube variants for approximate matches).
4. Use **Download filename** on any tab to export a single CSV, or **Download all playlist results (ZIP)** to export everything.

> ⚠️ The GUI is **experimental**: it reads local CSV files and is meant to be run alongside the comparison itself.

```bash
python main.py            # opens the GUI
```

Error messages are **always** printed, regardless of the verbose flag.

---

### ⚖️ `compare.py` — comparison engine

A **library module** imported by `main.py` (`from compare import compare_playlists`). It has no `__main__` block, so running it directly does nothing.

Responsibilities:

- **Normalization** — lowercases text, strips accents (NFKD), removes punctuation, maps `&` to `and`, and drops noise/qualifiers from titles.
- **Track loading** — reads tracks from Spotify and YouTube Music, skipping unavailable/removed entries.
- **Duplicate detection** — `find_duplicates()` flags repeated `title + first artist` keys.
- **Missing detection** — compares the normalized keys from both sides.
- **Approximate matching** — `find_approximate_matches()` greedily pairs leftover tracks by title similarity and duration.
- **CSV export** — writes the reports described in [Generated files](#-generated-files).

Public helper called by `main.py`:

```python
compare_playlists(spotify_url, youtube_id, output_dir, *, spotify_client, ytmusic)
```

---

### 🧹 `remove_duplicates.py` — duplicate-removal utility

A **standalone script** for cleaning one YouTube Music playlist. Unlike `compare.py`, which detects duplicates by normalized title + artist, this script detects duplicates by **identical `videoId`** (the same video added twice).

What it does:

1. Loads the playlist whose ID is hardcoded in the file (`playlist_id`).
2. Prints how many tracks were found and how many duplicates exist.
3. Asks for confirmation: `Remove N duplicate(s)? (y/n)`.
4. If you answer `y`, removes the duplicates **one by one** with `remove_playlist_items()`.
5. Prints how many were removed and how many failed.

It also contains an optional `debug_post()` wrapper (currently commented out) that logs raw HTTP responses for troubleshooting.

> ✏️ Edit `playlist_id` in the file before running it:
>
> ```bash
> python remove_duplicates.py
> ```

---

### 🔌 `test_connection.py` — connectivity check

A small diagnostic script that verifies your credentials against both services. It checks that the auth/cookie files exist and then:

- connects to Spotify and loads your profile plus its playlist count;
- connects to YouTube Music and loads the library playlists.

```bash
python test_connection.py
```

Successful output looks like:

```text
Checking Spotify credentials...
  Spotify OK: Your Name (N playlists)
Checking YouTube Music credentials...
  YouTube Music OK: N playlists

All connections OK.
```

The script exits with code `0` when both connections succeed and `1` otherwise. It reuses the same `SPOTIFY_COOKIES`, `YOUTUBE_AUTH`, and `SPOTIFY_USER` configuration as `main.py`.

The Spotify count includes both public and private playlists owned by the account. It is read with Spotify's internal `libraryV3` query; if the script warns that it could not read private playlists, update `LIBRARY_V3_HASH` in `spotify_library.py`.

---

## ⚙️ Configuration files

| File | Purpose | Secret? |
| --- | --- | --- |
| `browser.json` | YouTube Music **browser request headers** used by `ytmusicapi`. Must contain a valid `cookie` (with `__Secure-3PAPISID`) and `authorization` (with `SAPISIDHASH`). Created with `ytmusicapi browser --file browser.json`. | 🔴 **Yes** |
| `spotify_cookies.txt` | Netscape-format cookie file containing the Spotify **`sp_dc`** cookie. May optionally include a `# SPOTIFY_USER=your_username` comment line. | 🔴 **Yes** |

### 🔧 Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `SPOTIFY_USER` | *(from cookies file)* | Spotify username or profile URL. Takes precedence over the `# SPOTIFY_USER=` line in the cookies file. |
| `SPOTIFY_COOKIES` | `spotify_cookies.txt` | Path to the Spotify cookie file. |
| `YOUTUBE_AUTH` | `browser.json` | Path to the YouTube Music auth/headers file. |

Example:

```bash
SPOTIFY_USER="your_username" \
SPOTIFY_COOKIES="path/to/spotify_cookies.txt" \
YOUTUBE_AUTH="path/to/browser.json" \
python main.py
```

### 📘 Guides

- **`youtube_guide.md`** — step-by-step instructions to obtain and validate `browser.json`, including browser-specific instructions and common errors.
- **`spotify_guide.md`** — step-by-step instructions to obtain the `sp_dc` cookie, create `spotify_cookies.txt`, and configure the username.

---

## 📊 Generated files

All output goes to **`results/`** by default (set in `main.py` as `RESULTS_DIR`).

### 📁 Folder naming

Each matched pair of playlists gets its own folder:

```text
results/<normalized_playlist_name>/
```

The folder name is the normalized playlist name (lowercase, accents and punctuation removed). If two comparisons would collide, suffixes are appended:

```text
results/<name>_<spotify_playlist_id>_<youtube_playlist_id>/
results/<name>_<spotify_playlist_id>_<youtube_playlist_id>_<n>/
```

### 📄 Report files

Each folder contains up to five CSVs:

| File | What it contains |
| --- | --- |
| `spotify_duplicates.csv` | Songs that appear more than once in the Spotify playlist (occurrences after the first). |
| `youtube_duplicates.csv` | Songs that appear more than once in the YouTube Music playlist (occurrences after the first). |
| `missing_from_youtube.csv` | Songs in the Spotify playlist that were **not found** in the YouTube Music playlist. |
| `missing_from_spotify.csv` | Songs in the YouTube Music playlist that were **not found** in the Spotify playlist. |
| `approximate_matches.csv` | Fuzzy pairs (likely the same song) that were matched despite different metadata and therefore removed from the "missing" lists. |

### 🧾 CSV columns

The four duplicate/missing reports share the same columns:

| Column | Meaning |
| --- | --- |
| `id` | Spotify track ID or YouTube video ID |
| `name` | Normalized song name (as used for matching: lowercased, accents and punctuation removed) |
| `title` | Song title |
| `album` | Album name |
| `artist` | First artist |
| `artists` | All artists, comma-separated |
| `duration` | Duration as `m:ss` (or `h:mm:ss` for long tracks); Spotify is converted from milliseconds, YouTube Music is already in `m:ss` |

`approximate_matches.csv` has its own columns:

| Column | Meaning |
| --- | --- |
| `spotify_id` / `youtube_id` | Track and video IDs |
| `spotify_name` / `youtube_name` | Normalized song names on each platform |
| `spotify_album` / `youtube_album` | Album names on each platform |
| `spotify_title` / `youtube_title` | Titles on each platform |
| `spotify_artist` / `youtube_artist` | First artist on each platform |
| `spotify_duration` / `youtube_duration` | Raw durations |
| `similarity` | Title similarity score (0–1) |
| `duration_diff_seconds` | Absolute duration difference in seconds |

> 💡 CSVs are written as **UTF-8 with BOM** (`utf-8-sig`) so accented characters display correctly in Excel. Headers are always written, even when there are zero records.

---

## 🚀 Quick start

### 1. Enter the project and create a virtual environment

```bash
cd ytmusicapi
python3 -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

Or install only the direct dependencies:

```bash
pip install ytmusicapi spotifyscraper
```

> ⚠️ Never commit `.venv/`. The virtual environment is machine-specific and is already listed in `.gitignore`; `requirements.txt` lets anyone recreate it on their own machine.

Tested with:

- 🐍 Python `3.14.10`
- 📦 `ytmusicapi` `1.12.3`
- 📦 `spotifyscraper` `3.9.2`

### 3. Provide credentials

- Follow **`youtube_guide.md`** to create `browser.json`.
- Follow **`spotify_guide.md`** to create `spotify_cookies.txt`.

At minimum, `spotify_cookies.txt` must contain:

```text
# Netscape HTTP Cookie File
.spotify.com	TRUE	/	TRUE	0	sp_dc	YOUR_sp_dc_VALUE
# SPOTIFY_USER=your_username
```

And `browser.json` must contain valid YouTube Music request headers.

### 4. Run the comparison

```bash
python main.py   # opens the Streamlit GUI
```

Click **"Check Playlists"** on the home page to run a fresh comparison.

### 5. Review the reports

Open `results/` and inspect the CSVs. Start with `missing_from_youtube.csv` and `missing_from_spotify.csv`, then double-check `approximate_matches.csv` manually.

---

## 🔄 How it works

```text
Credentials (files / env)
        │
        ▼
Validate Spotify + YouTube Music
        │
        ▼
Load playlists from both services
        │
        ▼
Match playlists by normalized name
        │
        ▼
Load tracks (skip unavailable entries)
        │
        ▼
Detect duplicates + missing + fuzzy matches
        │
        ▼
Write CSV reports to results/ + print summary
```

1. **Playlist matching** — only playlists whose normalized names are equal are compared. Private Spotify playlists are not visible, so they are ignored.
2. **Track loading** — unavailable or removed entries (no `videoId`, no track object) are skipped and counted.
3. **Duplicates** — a track is a duplicate when its normalized `title + first artist` key was already seen earlier in the same playlist.
4. **Missing** — keys present on one side but absent on the other. Only the first occurrence of each key is reported.
5. **Approximate pass** — leftover tracks are paired when:
   - title similarity is **≥ 0.90**,
   - duration difference is **≤ 3 seconds**,
   - and the artists match, or one title has a removable `"Artist - "` prefix.
6. **Export** — reports are written and a summary is printed.

---

## 🧠 Title and artist normalization

To avoid false mismatches, the comparison ignores cosmetic differences:

- Case, accents, punctuation and whitespace.
- Neutral qualifiers that do not change the recording: `remastered`, `bonus`, `deluxe`, `digital`, `edition`, `track`, `feat.`, `ft.`, `featuring`, etc.
- Video/audio noise: `lyric video`, `official music video`, `official audio`, etc.
- Leading articles in artist names (`the`).
- Country suffixes used by YouTube Music (`UK`, `US`, `USA`).

It **keeps** qualifiers that identify a different recording, such as `live`, `acoustic`, `remix`, `instrumental`, `demo`, `mono`, `stereo`, `cover`, etc., so a studio track is not confused with its live or acoustic version.

---

## 🔐 Security notes

- `browser.json` grants access to your logged-in YouTube/Google account.
- `spotify_cookies.txt` contains a session-equivalent `sp_dc` cookie.
- **Never commit, paste, or screenshot either file.** Both are already listed in the included `.gitignore`:

```gitignore
browser.json
spotify_cookies.txt
```

- Restrict file permissions on Linux/macOS:

```bash
chmod 600 browser.json spotify_cookies.txt
```

- Keep both files out of cloud-synced folders and backups.

---

## 🛠️ Troubleshooting

| Problem | Likely cause / fix |
| --- | --- |
| `Spotify cookies file not found` | `spotify_cookies.txt` is missing or `SPOTIFY_COOKIES` points to the wrong path. |
| `Spotify username not found` | Set `SPOTIFY_USER` or add `# SPOTIFY_USER=...` to the cookies file. |
| `Spotify authentication failed` | The `sp_dc` cookie is missing, expired or revoked. Copy a fresh one. |
| `YouTube Music authentication failed` | `browser.json` is invalid or expired. Regenerate it with the CLI. |
| `No playlists with matching names were found` | Playlist names differ between services. Rename them so they match. |
| Only some playlists are compared | The internal Spotify library query failed and the script fell back to public playlists. Update `LIBRARY_V3_HASH` in `spotify_library.py`. |

See `youtube_guide.md` and `spotify_guide.md` for full error tables and renewal instructions.

---

## 📌 Notes and limitations

- 🔐 Both **public and private** Spotify playlists owned by your account are read.
- 📛 Playlist matching is name-based; there are no manual mappings yet.
- 🕒 Spotify and YouTube sessions can expire at any time; regenerate credentials if they stop working.
- 🤖 `ytmusicapi` 1.12.x supports browser auth but marks it deprecated in favor of OAuth. This project is built around `browser.json`.
- 🧪 `test_connection.py` is a diagnostic script; `remove_duplicates.py` is a utility with a hardcoded playlist ID — review it before use.
- ⚖️ **Comparison is limited** — normalization and fuzzy matching can produce **false negatives** (songs that are the same but not matched) and **false positives** (different songs treated as the same). Always review `approximate_matches.csv` manually.
- 🈯 **Non-latin characters** — songs and artists with non-latin scripts (e.g. Japanese, Korean, Chinese, Cyrillic, Arabic) are **not reliably compared** because normalization strips accents/punctuation but does not transliterate non-latin characters to latin equivalents.
- 🖥️ The GUI is **experimental** and may change between versions.
