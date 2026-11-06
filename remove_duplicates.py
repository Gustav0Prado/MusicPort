from ytmusicapi import YTMusic

ytmusic = YTMusic("browser.json")

original_post = ytmusic._session.post

def debug_post(*args, **kwargs):
    response = original_post(*args, **kwargs)

    print("\n--- REMOVAL RESPONSE ---")
    print("HTTP Status:", response.status_code)
    print("Content-Type:", response.headers.get("Content-Type"))
    print("Size:", len(response.text))
    print("Response:", repr(response.text[:1000]))

    return response

# ytmusic._session.post = debug_post

playlist_id = "PLWGCtAPYgt_k"

print(f"Loading playlist {playlist_id}...")

playlist = ytmusic.get_playlist(playlist_id, limit=None)

tracks = playlist["tracks"]

print(f"Playlist loaded! {len(tracks)} songs found.")
print(f"Total reported by YouTube: {playlist.get('trackCount')}")

tracks = playlist["tracks"]

seen = set()
duplicates = []

for track in tracks:
    video_id = track.get("videoId")

    if not video_id:
        continue

    if video_id in seen:
        # Store the original object returned by the API
        duplicates.append(track)
    else:
        seen.add(video_id)

print(f"Total songs: {len(tracks)}")
print(f"Duplicates found: {len(duplicates)}")

if duplicates:
    answer = input(
        f"Remove {len(duplicates)} duplicate(s)? (y/n): "
    ).strip().lower()
else:
    answer = "n"

if answer == "y":

    print("Starting individual removal...")

    success = 0
    failures = []

    for i, track in enumerate(duplicates, 1):
        video_id = track.get("videoId")
        set_video_id = track.get("setVideoId")

        if not video_id or not set_video_id:
            print(f"[{i}/{len(duplicates)}] Missing IDs. Skipping.")
            failures.append(track)
            continue

        try:
            ytmusic.remove_playlist_items(
                playlist_id,
                [track]
            )

            success += 1
            print(f"[{i}/{len(duplicates)}] Removed: {track.get('title')}")

        except Exception as e:
            print(f"[{i}/{len(duplicates)}] ERROR: {track.get('title')}")
            print(f"  {e}")
            failures.append(track)

    print("\n--- RESULT ---")
    print(f"Removed: {success}")
    print(f"Failures: {len(failures)}")

    print("Operation complete!")
else:
    print("No duplicates removed.")
