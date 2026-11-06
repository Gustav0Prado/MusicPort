import os
import sys

from spotify_scraper import SpotifyClient
from spotify_scraper.errors import AuthenticationError
from ytmusicapi import YTMusic

from main import SPOTIFY_COOKIES, YOUTUBE_AUTH, get_spotify_user
from spotify_library import fetch_owned_playlists


def count_owned_playlists(spotify, profile):
    try:
        playlists = fetch_owned_playlists(spotify, profile.id)
        # print(f"DEBUG: fetched {len(playlists)} playlists")
        return len(playlists), True

    except Exception as exc:
        # print(f"DEBUG: fetch_owned_playlists failed: {type(exc).__name__}: {exc}")

        if profile.public_playlists_total is not None:
            return profile.public_playlists_total, False

        return len(profile.public_playlists), False


def test_spotify():
    """Check that the Spotify cookie and username work."""
    print("Checking Spotify credentials...")

    if not os.path.isfile(SPOTIFY_COOKIES):
        print(f"  Spotify FAILED: cookies file not found: {SPOTIFY_COOKIES}")
        return False

    try:
        user = get_spotify_user()
    except ValueError as exc:
        print(f"  Spotify FAILED: {exc}")
        return False

    try:
        spotify = SpotifyClient(cookies=SPOTIFY_COOKIES)
    except Exception as exc:
        print(f"  Spotify FAILED: could not open cookies file: {exc}")
        return False

    try:
        try:
            profile = spotify.get_user(user)
        except AuthenticationError:
            print(
                "  Spotify FAILED: authentication failed. "
                f"Check that {SPOTIFY_COOKIES} contains a valid 'sp_dc' cookie."
            )
            return False
        except Exception as exc:
            print(f"  Spotify FAILED: could not load profile '{user}': {exc}")
            return False

        playlist_count, exact = count_owned_playlists(spotify, profile)
    finally:
        spotify.close()

    if exact:
        label = "playlists"
    else:
        label = "public playlists"

    print(
        f"  Spotify OK: {profile.name or profile.id} "
        f"({playlist_count} {label})"
    )

    if not exact:
        print(
            "  WARNING: could not read private playlists; "
            "update LIBRARY_V3_HASH in spotify_library.py."
        )

    return True


def test_youtube_music():
    """Check that the YouTube Music credentials work."""
    print("Checking YouTube Music credentials...")

    if not os.path.isfile(YOUTUBE_AUTH):
        print(f"  YouTube Music FAILED: auth file not found: {YOUTUBE_AUTH}")
        return False

    try:
        ytmusic = YTMusic(YOUTUBE_AUTH)
        playlists = ytmusic.get_library_playlists(limit=None)
    except Exception as exc:
        print(f"  YouTube Music FAILED: {exc}")
        return False

    print(f"  YouTube Music OK: {len(playlists)} playlists")
    return True


def main():
    spotify_ok = test_spotify()
    youtube_ok = test_youtube_music()
    print()

    if spotify_ok and youtube_ok:
        print("All connections OK.")
        return 0

    print("One or more connections failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
