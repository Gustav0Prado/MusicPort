import csv
import os
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from functools import lru_cache


# ==========================================
# NORMALIZATION
# ==========================================

FEATURING_WORDS = r"feat\.?|ft\.?|featuring"

# Qualifiers that do not change the recording itself, so they can be dropped
# when comparing the same song across platforms. This makes e.g.
# "1979 - Remastered 2012" and "1979" match.
NEUTRAL_QUALIFIER = re.compile(
    r"\b(?:remaster(?:ed)?|master(?:ed)?|feat\.?|ft\.?|featuring|bonus|"
    r"deluxe|b-sides?|digital|edition|track|album|single|version|original)\b",
    re.IGNORECASE,
)

# Qualifiers that identify a different recording/version (live, acoustic,
# alternate take, etc.). They must be kept, otherwise a studio track and its
# live/acoustic version would be treated as the same song.
# "version" and "single" are deliberately not listed here: tags such as
# "Single Version", "Album Version" and "Original Version" describe the same
# recording for comparison purposes. Performance/recording qualifiers still
# win because they are checked first, so "Live Version" and
# "Acoustic Version" remain distinct.
RECORDING_SPECIFIC = re.compile(
    r"\b(?:live|acoustic|unplugged|edit|mix|take|alternate|radio|"
    r"instrumental|demo|mono|stereo|soundtrack|remix|rerecording|"
    r"rerecorded|cover|extended)\b",
    re.IGNORECASE,
)

PARENTHETICAL_BLOCK = re.compile(r"\s*[\(\[]([^)\]]*)[\)\]]")

# Video/audio descriptors that are not part of the song title.
NOISE_PHRASES = re.compile(
    r"\s*[-\u2013\u2014]?\s*\b(?:lyric video|official music video|"
    r"official video|official audio)\b",
    re.IGNORECASE,
)

# Whitespace-surrounded dashes only, so titles such as "Cul-de-sac" and
# "Blue-Eyes White Dragon" are left untouched.
DASH_SEPARATOR = re.compile(r"\s+[-\u2013\u2014](?:\s+|$)")

FEATURING_START = re.compile(rf"(?:{FEATURING_WORDS})\b", re.IGNORECASE)

# Featured artists appended without a dash, e.g. "Song feat. Artist". The
# negated closing bracket keeps this from eating part of a parenthetical block.
TRAILING_FEATURING = re.compile(
    rf"\s+(?:{FEATURING_WORDS})\b[^)\]]*$",
    re.IGNORECASE,
)


def normalize(text):
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("&", " and ")
    return re.sub(r"[^\w]", "", text)


def _strip_parenthetical_qualifier(match):
    content = match.group(1)

    if RECORDING_SPECIFIC.search(content):
        return match.group(0)

    if NEUTRAL_QUALIFIER.search(content):
        return ""

    return match.group(0)


def _strip_dash_qualifier(title):
    matches = list(DASH_SEPARATOR.finditer(title))

    if not matches:
        return title

    separator = matches[-1]
    suffix = title[separator.end():]

    if FEATURING_START.match(suffix):
        return title[:separator.start()]

    if RECORDING_SPECIFIC.search(suffix):
        return title

    if NEUTRAL_QUALIFIER.search(suffix):
        return title[:separator.start()]

    return title


def normalize_title(title):
    title = NOISE_PHRASES.sub("", title)
    title = PARENTHETICAL_BLOCK.sub(_strip_parenthetical_qualifier, title)
    title = _strip_dash_qualifier(title)
    title = TRAILING_FEATURING.sub("", title)
    return normalize(title)


# ------------------------------------------
# Artists
# ------------------------------------------

# Separators between artists. They require whitespace on both sides (except
# comma/semicolon) so names such as "AC/DC" are not split.
ARTIST_SEPARATORS = re.compile(
    r"\s+(?:and|with|vs\.?|feat\.?|ft\.?|featuring|\+|/)\s+|\s*[,;]\s*",
    re.IGNORECASE,
)

# YouTube Music sometimes disambiguates artists with a country suffix
# (e.g. "The Chameleons UK"), while Spotify uses the plain name.
ARTIST_COUNTRY_SUFFIXES = {"uk", "us", "usa"}


def _fold_artist(artist):
    text = unicodedata.normalize("NFKD", (artist or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.replace("&", " and ")


def _artist_tokens(text):
    tokens = re.findall(r"\w+", text)
    without_articles = [t for t in tokens if t != "the"]

    # Keep the original name for artists made up only of articles ("The The").
    if without_articles:
        tokens = without_articles

    while len(tokens) > 1 and tokens[-1] in ARTIST_COUNTRY_SUFFIXES:
        tokens.pop()

    return tokens


def _artist_key(text):
    return "".join(_artist_tokens(text))


def artist_keys(artists):
    """Return a frozenset of normalized artist keys.

    Accepts a single artist string or a list of artist names. For each name
    the set holds the full name plus each individual artist, so that
    "Prince & The Revolution" matches "Prince" (shared key: "prince") and
    "Simon & Garfunkel" still matches itself (full-name key).

    Tracks without any artist get {""}, so they only match other tracks
    without an artist.
    """
    if artists is None or isinstance(artists, str):
        artists = [artists or ""]

    keys = set()

    for artist in artists:
        text = _fold_artist(artist)
        keys.add(_artist_key(text))
        keys.update(_artist_key(part) for part in ARTIST_SEPARATORS.split(text))

    keys.discard("")

    return frozenset(keys) or frozenset({""})


@lru_cache(maxsize=None)
def _artist_token_names(artists_text):
    """Full name plus each individual artist, as token tuples."""
    text = _fold_artist(artists_text)

    names = {tuple(_artist_tokens(text))}
    names.update(tuple(_artist_tokens(part)) for part in ARTIST_SEPARATORS.split(text))
    names.discard(())

    return frozenset(names)


def _contains_tokens(big, small):
    size = len(small)
    return any(big[i:i + size] == small for i in range(len(big) - size + 1))


def artists_related(artists_a, artists_b):
    """True when an artist name of one side is contained, token by token, in
    an artist name of the other side.

    Handles credits that differ by an extra word, e.g. Spotify's
    "Jimi Hendrix" vs YouTube Music's "The Jimi Hendrix Experience". Matching
    is per token, so "Prince" is NOT related to "Princess".

    Takes the tracks' "artists" strings ("A, B"). This is too loose for the
    exact pass, so it is only used by the approximate pass, which also
    requires a similar title and a similar duration.
    """
    for name_a in _artist_token_names(artists_a or ""):
        for name_b in _artist_token_names(artists_b or ""):
            if _contains_tokens(name_a, name_b) or _contains_tokens(name_b, name_a):
                return True

    return False


def make_key(title, artists):
    """Build the comparison key: (normalized title, frozenset of artist keys).

    Because the artist part is a set, keys must be compared with
    keys_match() rather than used directly as dict/set keys.
    """
    return normalize_title(title or ""), artist_keys(artists)


# ==========================================
# HELPERS
# ==========================================

def extract_youtube_id(value):
    """Accept either a playlist URL or a bare playlist ID."""
    value = value.strip()

    if "list=" in value:
        value = value.split("list=", 1)[1]

    return value.split("&", 1)[0]


def keys_match(key_a, key_b):
    """Same song: equal normalized title and at least one shared artist key."""
    return key_a[0] == key_b[0] and bool(key_a[1] & key_b[1])


def has_empty_key(track):
    title_key, artists = track["key"]
    return not title_key and not any(artists)


def build_index(tracks):
    """Group tracks by normalized title; artists are compared inside a group."""
    index = defaultdict(list)

    for track in tracks:
        index[track["key"][0]].append(track)

    return index


def find_match(track, index):
    """Return a track from `index` that is the same song as `track`, or None."""
    for other in index.get(track["key"][0], ()):
        if keys_match(track["key"], other["key"]):
            return other

    return None


def split_unique_and_duplicates(tracks):
    """Split a playlist into first occurrences and repeated occurrences.

    Songs are matched by normalized title + shared artist, not by platform ID.
    This catches the same song added twice even when the two entries have
    different Spotify / YouTube IDs (for example, different uploads or
    different album versions).

    Returns (unique, duplicates); `duplicates` holds every occurrence after
    the first of the same song.
    """
    seen = defaultdict(list)
    unique = []
    duplicates = []

    for track in tracks:
        # Entries with no title and no artist carry nothing to compare.
        if has_empty_key(track):
            unique.append(track)
            continue

        title_key, artists = track["key"]

        if any(artists & other for other in seen[title_key]):
            duplicates.append(track)
        else:
            unique.append(track)

        # Duplicates are indexed too, so a later track that only shares an
        # artist with the duplicate (and not with the first one) still counts.
        seen[title_key].append(artists)

    return unique, duplicates


def export_csv(filename, tracks, *, verbose=False):
    """Write a CSV with a header even when there are no records.

    Writing an empty file with a header is intentional: it prevents a stale
    report from a previous run from being mistaken for the current result.
    """
    with open(filename, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["id", "name", "title", "album", "artist", "artists", "duration"],
        )

        writer.writeheader()

        for track in tracks:
            row = {key: track[key] for key in writer.fieldnames}
            row["duration"] = format_duration(track["duration"])
            writer.writerow(row)

    if verbose:
        print(f"Generated: {filename} ({len(tracks)} records)")


def export_approximate_matches(filename, matches, *, verbose=False):
    """Write the fuzzy/approximate matches so they can be reviewed."""
    fieldnames = [
        "spotify_id",
        "spotify_name",
        "spotify_album",
        "spotify_title",
        "spotify_artist",
        "spotify_duration",
        "youtube_id",
        "youtube_name",
        "youtube_album",
        "youtube_title",
        "youtube_artist",
        "youtube_duration",
        "similarity",
        "duration_diff_seconds",
    ]

    with open(filename, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)

        writer.writeheader()

        for spotify_track, youtube_track, similarity, duration_diff in matches:
            writer.writerow({
                "spotify_id": spotify_track["id"],
                "spotify_name": spotify_track["name"],
                "spotify_album": spotify_track["album"],
                "spotify_title": spotify_track["title"],
                "spotify_artist": spotify_track["artist"],
                "spotify_duration": format_duration(spotify_track["duration"]),
                "youtube_id": youtube_track["id"],
                "youtube_name": youtube_track["name"],
                "youtube_album": youtube_track["album"],
                "youtube_title": youtube_track["title"],
                "youtube_artist": youtube_track["artist"],
                "youtube_duration": format_duration(youtube_track["duration"]),
                "similarity": f"{similarity:.3f}",
                "duration_diff_seconds": f"{duration_diff:.2f}",
            })

    if verbose:
        print(f"Generated: {filename} ({len(matches)} records)")


# ==========================================
# PLAYLIST LOADING
# ==========================================

def load_spotify_tracks(spotify_client, spotify_url):
    playlist = spotify_client.get_playlist(spotify_url, max_tracks=None)

    tracks = []
    skipped = 0

    for entry in playlist.tracks:
        track = entry.track

        if track is None:
            skipped += 1
            continue

        artists = [artist.name for artist in track.artists]
        artist = artists[0] if artists else ""

        album = track.album.name if track.album else None
        key = make_key(track.name, artists)
        tracks.append({
            "id": track.id,
            "title": track.name,
            "album": album,
            "artist": artist,
            "artists": ", ".join(artists),
            "duration": track.duration_ms,
            "key": key,
            "name": key[0],
        })

    return playlist.name, tracks, skipped


def load_youtube_tracks(ytmusic, youtube_id):
    playlist = ytmusic.get_playlist(youtube_id, limit=None)

    tracks = []
    skipped = 0

    for track in playlist["tracks"]:
        video_id = track.get("videoId")

        # Entries without a video ID are unavailable/removed and cannot be
        # matched or meaningfully compared.
        if not video_id:
            skipped += 1
            continue

        artists = [
            artist["name"]
            for artist in (track.get("artists") or [])
        ]

        artist = artists[0] if artists else ""
        title = track.get("title") or ""

        key = make_key(title, artists)
        album = (track.get("album") or {}).get("name") or None
        tracks.append({
            "id": video_id,
            "title": title,
            "album": album,
            "artist": artist,
            "artists": ", ".join(artists),
            "duration": track.get("duration", ""),
            "key": key,
            "name": key[0],
        })

    return playlist.get("title") or "", tracks, skipped


# ==========================================
# APPROXIMATE MATCHING
# ==========================================

# A second pass catches cases where the metadata itself differs between
# platforms, for example a YouTube upload titled "Artist - Song" whose artist
# field is the uploader's channel name.
TITLE_SIMILARITY_THRESHOLD = 0.90
DURATION_TOLERANCE_SECONDS = 3.0


def parse_duration(value):
    """Return a duration in seconds.

    Spotify stores milliseconds as a number; YouTube Music returns a string
    such as "4:27" (or "1:02:03" for long videos).
    """
    if value is None or value == "":
        return None

    if isinstance(value, (int, float)):
        return float(value) / 1000

    text = str(value).strip()

    if text.isdigit():
        return float(text) / 1000

    parts = text.split(":")

    try:
        seconds = 0.0

        for part in parts:
            seconds = seconds * 60 + int(part)

        return seconds
    except ValueError:
        return None


def format_duration(value):
    """Return a duration as ``m:ss`` (or ``h:mm:ss`` when an hour or more).

    Spotify durations arrive in milliseconds and YouTube Music durations
    arrive as ``"m:ss"`` / ``"h:mm:ss"``, so both are normalized before
    being written to the reports.
    """
    seconds = parse_duration(value)

    if seconds is None:
        return "" if value is None or value == "" else str(value)

    total_seconds = int(round(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"

    return f"{minutes}:{secs:02d}"


def strip_artist_prefix(title, artists):
    """Remove a leading artist name from a title, when present.

    YouTube uploads often use titles like "The Gloria Record - Torch Yourself"
    while the artist field contains the uploader's channel name. `artists` is
    the set of artist keys of the track on the other platform. Returns the
    remaining title and whether a prefix was actually removed.
    """
    title_key = normalize_title(title)

    # Longest first, so "princeandrevolution" is tried before "prince".
    for artist_key in sorted(artists, key=len, reverse=True):
        if not artist_key:
            continue

        # Accept both "Artist - Song" and "The Artist - Song".
        for prefix in (artist_key, "the" + artist_key):
            if title_key.startswith(prefix) and len(title_key) > len(prefix):
                return title_key[len(prefix):], True

    return title_key, False


def approximate_match_score(spotify_track, youtube_track):
    """Score two tracks that did not match by their normalized key.

    Returns (title similarity, duration difference) when they are close
    enough to be considered the same song, otherwise None.
    """
    spotify_title = normalize_title(spotify_track["title"])
    youtube_title = normalize_title(youtube_track["title"])

    spotify_stripped, spotify_prefixed = strip_artist_prefix(
        spotify_track["title"],
        youtube_track["key"][1],
    )
    youtube_stripped, youtube_prefixed = strip_artist_prefix(
        youtube_track["title"],
        spotify_track["key"][1],
    )

    variants = [(spotify_title, youtube_title)]

    if spotify_prefixed:
        variants.append((spotify_stripped, youtube_title))

    if youtube_prefixed:
        variants.append((spotify_title, youtube_stripped))

    if spotify_prefixed and youtube_prefixed:
        variants.append((spotify_stripped, youtube_stripped))

    similarities = [
        SequenceMatcher(None, left, right).ratio()
        for left, right in variants
        if left and right
    ]

    if not similarities:
        return None

    similarity = max(similarities)

    if similarity < TITLE_SIMILARITY_THRESHOLD:
        return None

    same_artist = (
        bool(spotify_track["key"][1] & youtube_track["key"][1])
        or artists_related(spotify_track["artists"], youtube_track["artists"])
    )

    if not (same_artist or spotify_prefixed or youtube_prefixed):
        return None

    spotify_duration = parse_duration(spotify_track["duration"])
    youtube_duration = parse_duration(youtube_track["duration"])

    if spotify_duration is None or youtube_duration is None:
        return None

    duration_diff = abs(spotify_duration - youtube_duration)

    if duration_diff > DURATION_TOLERANCE_SECONDS:
        return None

    return similarity, duration_diff


def find_approximate_matches(spotify_tracks, youtube_tracks):
    """Pair unmatched tracks by similar title and duration.

    Pairs are chosen greedily, best score first, so each track is used only
    once.
    """
    candidates = []

    for spotify_index, spotify_track in enumerate(spotify_tracks):
        for youtube_index, youtube_track in enumerate(youtube_tracks):
            result = approximate_match_score(spotify_track, youtube_track)

            if result is None:
                continue

            similarity, duration_diff = result
            candidates.append(
                (similarity, duration_diff, spotify_index, youtube_index)
            )

    candidates.sort(key=lambda item: (-item[0], item[1]))

    used_spotify = set()
    used_youtube = set()
    matches = []

    for similarity, duration_diff, spotify_index, youtube_index in candidates:
        if spotify_index in used_spotify or youtube_index in used_youtube:
            continue

        used_spotify.add(spotify_index)
        used_youtube.add(youtube_index)

        matches.append((
            spotify_tracks[spotify_index],
            youtube_tracks[youtube_index],
            similarity,
            duration_diff,
        ))

    return matches


# ==========================================
# COMPARISON
# ==========================================

def compare_playlists(spotify_url, youtube_id, output_dir, *, spotify_client, ytmusic, verbose=False):
    """Compare one Spotify playlist with one YouTube Music playlist.

    Args:
        spotify_url: Spotify playlist URL, URI, or ID.
        youtube_id: YouTube Music playlist ID or playlist URL.
        output_dir: Directory where the report CSVs will be written.
        spotify_client: An authenticated spotify_scraper.SpotifyClient.
        ytmusic: An authenticated ytmusicapi.YTMusic instance.
        verbose: Print detailed diagnostics and per-playlist summaries.
    """
    os.makedirs(output_dir, exist_ok=True)
    youtube_id = extract_youtube_id(youtube_id)

    # ==========================================
    # SPOTIFY
    # ==========================================

    if verbose:
        print("[1/4] Loading Spotify playlist...")

    spotify_title, spotify_tracks, spotify_skipped = load_spotify_tracks(
        spotify_client,
        spotify_url,
    )

    if verbose:
        print(f"Spotify: {len(spotify_tracks)} songs ({spotify_title})")

        if spotify_skipped:
            print(f"Skipped {spotify_skipped} unavailable Spotify entries.")

    # ==========================================
    # YOUTUBE MUSIC
    # ==========================================

    if verbose:
        print("\n[2/4] Loading YouTube Music playlist...")

    youtube_title, youtube_tracks, youtube_skipped = load_youtube_tracks(
        ytmusic,
        youtube_id,
    )

    if verbose:
        print(f"YouTube Music: {len(youtube_tracks)} songs ({youtube_title})")

        if youtube_skipped:
            print(f"Skipped {youtube_skipped} unavailable YouTube Music entries.")

    # ==========================================
    # INTERNAL DUPLICATES
    # ==========================================

    if verbose:
        print("\n[3/4] Checking for duplicates and comparing playlists...")

    spotify_unique, spotify_duplicates = split_unique_and_duplicates(
        spotify_tracks
    )
    youtube_unique, youtube_duplicates = split_unique_and_duplicates(
        youtube_tracks
    )

    # Index by normalized title; artists are compared by shared keys.
    spotify_index = build_index(spotify_tracks)
    youtube_index = build_index(youtube_tracks)

    # Songs with no equivalent on the other service. Only first occurrences
    # are checked, so an internal duplicate is not also listed as "missing".
    missing_youtube = [
        track for track in spotify_unique
        if find_match(track, youtube_index) is None
    ]

    missing_spotify = [
        track for track in youtube_unique
        if find_match(track, spotify_index) is None
    ]

    # Second pass: pair tracks whose metadata is formatted differently, such
    # as YouTube uploads titled "Artist - Song" whose artist is the channel.
    approximate_matches = find_approximate_matches(
        missing_youtube,
        missing_spotify,
    )

    approximate_spotify = {
        id(track) for track, _, _, _ in approximate_matches
    }
    approximate_youtube = {
        id(track) for _, track, _, _ in approximate_matches
    }

    missing_youtube = [
        track for track in missing_youtube
        if id(track) not in approximate_spotify
    ]
    missing_spotify = [
        track for track in missing_spotify
        if id(track) not in approximate_youtube
    ]

    # ==========================================
    # CONCISE RESULT
    # ==========================================

    print(
        f"Spotify: {len(spotify_tracks)} songs | "
        f"YT Music: {len(youtube_tracks)} songs",
        flush=True,
    )

    print(
        f"        {'Spotify:':<10} Missing: {len(missing_youtube):02d} "
        f"| Duplicates: {len(spotify_duplicates)}",
        flush=True,
    )

    print(
        f"        {'YT Music:':<10} Missing: {len(missing_spotify):02d} "
        f"| Duplicates: {len(youtube_duplicates)}",
        flush=True,
    )

    # ==========================================
    # DIAGNOSTICS (verbose only)
    # ==========================================

    if verbose:
        print("\n========== DIAGNOSTICS ==========")

        print(f"Spotify: {len(spotify_tracks)}")
        print(f"YouTube Music: {len(youtube_tracks)}")
        print(f"Same number of songs: {'yes' if len(spotify_tracks) == len(youtube_tracks) else 'no'}")

        print(f"Unique songs Spotify: {len(spotify_unique)}")
        print(f"Unique songs YouTube Music: {len(youtube_unique)}")

        print(f"\nSpotify duplicates: {len(spotify_duplicates)}")
        for track in spotify_duplicates:
            print(f" - {track['artist']} - {track['title']}")

        print(f"\nYouTube Music duplicates: {len(youtube_duplicates)}")
        for track in youtube_duplicates:
            print(f" - {track['artist']} - {track['title']}")

        print(f"\nApproximate matches: {len(approximate_matches)}")
        for spotify_track, youtube_track, similarity, duration_diff in approximate_matches:
            print(
                f" - {spotify_track['artist']} - {spotify_track['title']}  <->  "
                f"{youtube_track['artist']} - {youtube_track['title']} "
                f"({similarity:.0%}, {duration_diff:.1f}s)"
            )

        print("\nMissing from YouTube Music:")
        for track in missing_youtube:
            print(f" - {track['artist']} - {track['title']}")

        if not missing_youtube:
            print(" - none")

        print("\nMissing from Spotify:")
        for track in missing_spotify:
            print(f" - {track['artist']} - {track['title']}")

        if not missing_spotify:
            print(" - none")

    # ==========================================
    # CSV EXPORT
    # ==========================================

    if verbose:
        print("\n[4/4] Generating reports...")

    export_csv(
        os.path.join(output_dir, "spotify_duplicates.csv"),
        spotify_duplicates,
        verbose=verbose,
    )

    export_csv(
        os.path.join(output_dir, "youtube_duplicates.csv"),
        youtube_duplicates,
        verbose=verbose,
    )

    export_csv(
        os.path.join(output_dir, "missing_from_youtube.csv"),
        missing_youtube,
        verbose=verbose,
    )

    export_csv(
        os.path.join(output_dir, "missing_from_spotify.csv"),
        missing_spotify,
        verbose=verbose,
    )

    export_approximate_matches(
        os.path.join(output_dir, "approximate_matches.csv"),
        approximate_matches,
        verbose=verbose,
    )

    # ==========================================
    # SUMMARY (verbose only)
    # ==========================================

    if verbose:
        print("\n========== SUMMARY ==========")

        print(f"Spotify: {len(spotify_tracks)}")
        print(f"YouTube Music: {len(youtube_tracks)}")

        print(f"\nSpotify duplicates: {len(spotify_duplicates)}")
        print(f"YouTube Music duplicates: {len(youtube_duplicates)}")

        print(f"\nApproximate matches: {len(approximate_matches)}")

        print(f"\nMissing from YouTube Music: {len(missing_youtube)}")
        print(f"Missing from Spotify: {len(missing_spotify)}")