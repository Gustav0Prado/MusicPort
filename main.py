import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import defaultdict

from spotify_scraper import SpotifyClient
from spotify_scraper.errors import AuthenticationError
from ytmusicapi import YTMusic

from compare import compare_playlists
from spotify_library import fetch_owned_playlists

SPOTIFY_USER = os.environ.get("SPOTIFY_USER", "").strip()
SPOTIFY_COOKIES = os.environ.get("SPOTIFY_COOKIES", "spotify_cookies.txt")
YOUTUBE_AUTH = os.environ.get("YOUTUBE_AUTH", "browser.json")
RESULTS_DIR = "results"

SPOTIFY_USER_LINE = re.compile(
    r"^#\s*SPOTIFY_USER\s*=\s*(.*?)\s*$",
    re.IGNORECASE,
)


def read_spotify_user_from_cookies(path):
    """Return SPOTIFY_USER from a '# SPOTIFY_USER=...' line in the cookies file."""
    try:
        with open(path, encoding="utf-8") as file:
            for line in file:
                match = SPOTIFY_USER_LINE.match(line)

                if match:
                    return match.group(1).strip().strip("'\"")
    except OSError:
        return ""

    return ""


def get_spotify_user():
    if SPOTIFY_USER:
        return SPOTIFY_USER

    user = read_spotify_user_from_cookies(SPOTIFY_COOKIES)

    if user:
        return user

    raise ValueError(
        "Spotify username not found. Set the SPOTIFY_USER environment variable "
        f"or add '# SPOTIFY_USER=your_username' to {SPOTIFY_COOKIES}."
    )


def normalize_name(name):
    name = unicodedata.normalize("NFKD", name.lower())
    name = "".join(c for c in name if not unicodedata.combining(c))
    return re.sub(r"[^\w]", "", name)


def check_file(path, label):
    if not os.path.isfile(path):
        raise FileNotFoundError(f"{label} not found: {path}")


def check_credentials(user):
    """Validate both services and return them plus their playlists."""
    spotify = SpotifyClient(cookies=SPOTIFY_COOKIES)

    print("Checking Spotify credentials...")

    try:
        profile = spotify.get_user(user)
    except AuthenticationError as exc:
        spotify.close()
        raise RuntimeError(
            "Spotify authentication failed. "
            f"Check that {SPOTIFY_COOKIES} contains a valid 'sp_dc' cookie."
        ) from exc
    except Exception as exc:
        spotify.close()
        raise RuntimeError(
            f"Could not load the Spotify profile '{user}': {exc}"
        ) from exc

    print(f"  Spotify OK: {profile.name or profile.id}")

    try:
        spotify_playlists = fetch_owned_playlists(spotify, profile.id)
    except Exception:
        spotify_playlists = list(profile.public_playlists)
        print(
            "  WARNING: could not read private playlists; "
            "comparing public playlists only. "
            "Update LIBRARY_V3_HASH in spotify_library.py."
        )

    print(f"  Spotify playlists: {len(spotify_playlists)}")

    print("Checking YouTube Music credentials...")

    try:
        ytmusic = YTMusic(YOUTUBE_AUTH)
        youtube_playlists = ytmusic.get_library_playlists(limit=None)
    except Exception as exc:
        spotify.close()
        raise RuntimeError(
            "YouTube Music authentication failed. "
            f"Check that {YOUTUBE_AUTH} is a valid browser.json export."
        ) from exc

    print(f"  YouTube Music OK: {len(youtube_playlists)} playlists")

    return spotify, profile, spotify_playlists, ytmusic, youtube_playlists


def build_playlist_pairs(spotify_playlists, youtube_playlists):
    """Pair Spotify playlists with YouTube Music playlists of the same name."""
    # Index YouTube Music playlists by normalized name.
    youtube_by_name = defaultdict(list)

    for playlist in youtube_playlists:
        playlist_id = playlist.get("playlistId")

        if not playlist_id:
            continue

        key = normalize_name(playlist.get("title") or "")
        youtube_by_name[key].append(playlist)

    pairs = []
    used_output_dirs = set()

    for sp_playlist in spotify_playlists:
        key = normalize_name(sp_playlist.name)
        matches = youtube_by_name.get(key, [])

        for yt_playlist in matches:
            folder = key or sp_playlist.id
            base_output_dir = os.path.join(RESULTS_DIR, folder)
            output_dir = base_output_dir

            # Avoid two comparisons overwriting the same report folder.
            if output_dir in used_output_dirs:
                output_dir = (
                    f"{base_output_dir}_"
                    f"{sp_playlist.id}_{yt_playlist['playlistId']}"
                )

            counter = 1

            while output_dir in used_output_dirs:
                counter += 1
                output_dir = (
                    f"{base_output_dir}_"
                    f"{sp_playlist.id}_{yt_playlist['playlistId']}_"
                    f"{counter}"
                )

            used_output_dirs.add(output_dir)
            pairs.append((sp_playlist, yt_playlist, output_dir))

    return pairs


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compare Spotify playlists with YouTube Music playlists."
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed diagnostics and per-playlist summaries.",
    )
    return parser.parse_args()



def run_comparison(verbose: bool = False):
    """Run the Spotify ↔ YouTube Music comparison and write reports."""

    check_file(SPOTIFY_COOKIES, "Spotify cookies file")
    check_file(YOUTUBE_AUTH, "YouTube Music auth file")

    user = get_spotify_user()

    if not user:
        raise ValueError("Spotify username not provided.")

    os.makedirs(RESULTS_DIR, exist_ok=True)

    spotify, profile, spotify_playlists, ytmusic, youtube_playlists = (
        check_credentials(user)
    )

    try:
        pairs = build_playlist_pairs(
            spotify_playlists,
            youtube_playlists,
        )

        if not pairs:
            print(
                "No playlists with matching names were found.",
                flush=True
            )
        else:
            print(
                f"\nFound {len(pairs)} matching playlist(s).",
                flush=True
            )

        failures = 0
        playlist_names = {}

        for sp_playlist, yt_playlist, output_dir in pairs:

            playlist_names[
                normalize_name(sp_playlist.name)
            ] = sp_playlist.name

            print(
                f'\nAnalyzing playlist "{sp_playlist.name}"...',
                flush=True
            )

            try:
                compare_playlists(
                    sp_playlist.url,
                    yt_playlist["playlistId"],
                    output_dir,
                    spotify_client=spotify,
                    ytmusic=ytmusic,
                    verbose=verbose,
                )

            except Exception as exc:
                failures += 1

                print(
                    f"ERROR comparing '{sp_playlist.name}': {exc}",
                    flush=True
                )

        print("\n========== FINAL SUMMARY ==========", flush=True)
        print(f"Matched playlist pairs: {len(pairs)}", flush=True)

        if failures:
            print(f"Comparisons with errors: {failures}", flush=True)

        print(f"\nReports saved to: {RESULTS_DIR}/", flush=True)
        print("Comparison complete!", flush=True)

        with open(
            os.path.join(RESULTS_DIR, "playlist_names.json"),
            "w",
            encoding="utf-8-sig",
        ) as names_file:

            json.dump(
                playlist_names,
                names_file,
                ensure_ascii=False,
                indent=2
            )

        return {
            "pairs": len(pairs),
            "failures": failures,
        }

    finally:
        spotify.close()


def main():
    args = parse_args()

    subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "gui.py",
        ],
        check=False,
    )


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"ERROR: {exc}") from None
