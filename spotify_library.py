"""Read the logged-in Spotify user's playlists, including private ones."""

import json
from dataclasses import dataclass
from urllib.parse import urlencode

# Spotify rotates persisted-query hashes between web-player releases. If this
# query starts failing, update the hash from:
# https://github.com/Jigen-Ohtsusuki/spotify-gql-registry/blob/main/hashes.json
LIBRARY_V3_HASH = "390c78e5b951029bad359785e69b07b536a509c581cbcd0aded5e5067f187455"
LIBRARY_V3_URL = "https://api-partner.spotify.com/pathfinder/v1/query"
PAGE_SIZE = 100


@dataclass(frozen=True)
class PlaylistRef:
    id: str
    name: str
    url: str


def fetch_owned_playlists(spotify, user_id):
    """Return every playlist owned by ``user_id``, public or private."""
    token = spotify._cookie_provider().token()
    headers = {
        "Authorization": f"Bearer {token}",
        "app-platform": "WebPlayer",
        "Accept": "application/json",
    }

    playlists = {}
    offset = 0

    while True:
        variables = {
            "filters": ["Playlists"],
            "order": None,
            "textFilter": "",
            "features": [],
            "limit": PAGE_SIZE,
            "offset": offset,
            "flatten": False,
            "expandedFolders": [],
            "folderUri": None,
            "includeFoldersWhenFlattening": True,
            "withCuration": False,
        }
        extensions = {
            "persistedQuery": {"version": 1, "sha256Hash": LIBRARY_V3_HASH}
        }
        params = {
            "operationName": "libraryV3",
            "variables": json.dumps(variables, separators=(",", ":")),
            "extensions": json.dumps(extensions, separators=(",", ":")),
        }
        response = spotify._transport.get(
            f"{LIBRARY_V3_URL}?{urlencode(params)}",
            headers=headers,
        )
        library = response.json()["data"]["me"]["libraryV3"]
        items = library.get("items") or []

        for entry in items:
            item = entry.get("item") or {}
            data = item.get("data") or {}
            owner = (data.get("ownerV2") or {}).get("data") or {}
            uri = item.get("_uri")

            if owner.get("id") == user_id and uri:
                playlist_id = uri.split(":")[-1]
                playlists[uri] = PlaylistRef(
                    id=playlist_id,
                    name=data.get("name") or "",
                    url=f"https://open.spotify.com/playlist/{playlist_id}",
                )

        offset += len(items)
        total = library.get("totalCount")

        if not items or (total is not None and offset >= total):
            break

    return list(playlists.values())
