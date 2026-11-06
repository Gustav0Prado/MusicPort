
import io
import json
import queue
import re
import sys
import threading
import traceback
import zipfile
import html
import streamlit.components.v1 as components
from pathlib import Path

import pandas as pd
import streamlit as st

from main import run_comparison


st.set_page_config(
    page_title="Playlist Comparison",
    page_icon="🎵",
    layout="wide"
)

st.title("🎵 Playlist Comparison")
st.caption("Explore playlist comparison results from your local CSV files.")


FILES = {
    "approximate_matches.csv": "Approximate Matches",
    "missing_from_spotify.csv": "Missing from Spotify",
    "missing_from_youtube.csv": "Missing from YouTube",
    "spotify_duplicates.csv": "Spotify Duplicates",
    "youtube_duplicates.csv": "YouTube Duplicates",
}


BASE_COLUMNS = (
    "id", "name", "title", "artist", "artists", "duration",
)

APPROXIMATE_COLUMNS = (
    "spotify_id",
    "spotify_name",
    "spotify_title",
    "spotify_artist",
    "spotify_duration",
    "youtube_id",
    "youtube_name",
    "youtube_title",
    "youtube_artist",
    "youtube_duration",
    "similarity",
    "duration_diff_seconds",
)

COLUMNS_BY_FILE = {
    "approximate_matches.csv": APPROXIMATE_COLUMNS,
    "missing_from_spotify.csv": BASE_COLUMNS,
    "missing_from_youtube.csv": BASE_COLUMNS,
    "spotify_duplicates.csv": BASE_COLUMNS,
    "youtube_duplicates.csv": BASE_COLUMNS,
}


BASE_DISPLAY_COLUMNS = (
    "title", "album", "artists", "duration",
)

APPROXIMATE_DISPLAY_COLUMNS = (
    "spotify_title",
    "spotify_album",
    "spotify_artist",
    "spotify_duration",
    "youtube_title",
    "youtube_album",
    "youtube_artist",
    "youtube_duration",
    "similarity",
    "duration_diff_seconds",
)

DISPLAY_COLUMNS_BY_FILE = {
    "approximate_matches.csv": APPROXIMATE_DISPLAY_COLUMNS,
    "missing_from_spotify.csv": BASE_DISPLAY_COLUMNS,
    "missing_from_youtube.csv": BASE_DISPLAY_COLUMNS,
    "spotify_duplicates.csv": BASE_DISPLAY_COLUMNS,
    "youtube_duplicates.csv": BASE_DISPLAY_COLUMNS,
}


DISPLAY_COLUMN_LABELS = {
    "title": "Title",
    "album": "Album",
    "artists": "Artists",
    "duration": "Duration",
    "spotify_title": "Spotify Title",
    "spotify_album": "Spotify Album",
    "spotify_artist": "Spotify Artist",
    "spotify_duration": "Spotify Duration",
    "youtube_title": "YouTube Title",
    "youtube_album": "YouTube Album",
    "youtube_artist": "YouTube Artist",
    "youtube_duration": "YouTube Duration",
    "similarity": "Similarity",
    "duration_diff_seconds": "Duration Diff Seconds",
}


RESULTS_DIR = Path(__file__).parent / "results"


# =========================================================
# STDOUT CAPTURE
# =========================================================

class QueueWriter:
    """
    Captures terminal output line by line while preserving
    the original terminal output.
    """

    def __init__(self, original, output_queue):
        self.original = original
        self.output_queue = output_queue
        self.buffer = ""

    def write(self, text):
        self.original.write(text)
        self.original.flush()

        self.buffer += text

        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            self.output_queue.put(line)

        return len(text)

    def flush(self):
        self.original.flush()

        if self.buffer:
            self.output_queue.put(self.buffer)
            self.buffer = ""

    def isatty(self):
        return False

    def fileno(self):
        return self.original.fileno()


def run_comparison_thread(output_queue):

    original_stdout = sys.stdout
    original_stderr = sys.stderr

    stdout_capture = QueueWriter(
        original_stdout,
        output_queue
    )

    stderr_capture = QueueWriter(
        original_stderr,
        output_queue
    )

    try:
        sys.stdout = stdout_capture
        sys.stderr = stderr_capture

        run_comparison()

    except Exception:
        traceback.print_exc()

    finally:
        stdout_capture.flush()
        stderr_capture.flush()

        sys.stdout = original_stdout
        sys.stderr = original_stderr

        output_queue.put("__COMPARISON_FINISHED__")


# =========================================================
# CSV HELPERS
# =========================================================

def load_csv(payload):

    try:
        df = pd.read_csv(
            io.BytesIO(payload),
            dtype=str,
            keep_default_na=False
        )

    except Exception:
        df = pd.read_csv(
            io.BytesIO(payload),
            sep=";",
            dtype=str,
            keep_default_na=False
        )

    df = df.loc[
        :,
        [
            c for c in df.columns
            if not str(c).startswith("Unnamed:")
        ]
    ]

    return df


def view_frame(frame, filename):

    columns = DISPLAY_COLUMNS_BY_FILE.get(
        filename,
        BASE_DISPLAY_COLUMNS
    )

    columns = [
        column for column in columns
        if column in frame.columns
    ]

    if not columns:
        return frame.rename(
            columns=lambda c: DISPLAY_COLUMN_LABELS.get(
                c,
                str(c).replace("_", " ").title()
            )
        )

    return frame.loc[:, columns].rename(
        columns={
            column: DISPLAY_COLUMN_LABELS.get(
                column,
                column.replace("_", " ").title()
            )
            for column in columns
        }
    )


def load_playlist_names():

    names_file = RESULTS_DIR / "playlist_names.json"

    if not names_file.exists():
        return {}

    try:
        with open(
            names_file,
            encoding="utf-8-sig"
        ) as f:
            return json.load(f) or {}

    except Exception:
        return {}


# =========================================================
# HOME / COMPARISON PAGE
# =========================================================

if st.session_state.get("page", "home") == "home":

    st.markdown(
        """
        <style>
        [data-testid="stBaseButton"] {
            font-size: 42px;
            font-weight: bold;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### 🚀 Check Playlists")

    st.write(
        "Press the button below to compare your Spotify playlists "
        "against your YouTube Music library."
    )

    if st.button(
        "Check Playlists",
        type="primary",
        use_container_width=True
    ):

        output_queue = queue.Queue()

        worker = threading.Thread(
            target=run_comparison_thread,
            args=(output_queue,),
            daemon=True
        )

        st.markdown("### 📜 Comparison output")

        playlist_placeholder = st.empty()
        logs_placeholder = st.empty()

        current_logs = []
        current_playlist = None

        worker.start()

        finished = False

        # Identifies the beginning of each playlist summary.
        playlist_start_pattern = re.compile(
            r'^Analyzing playlist "(.*?)"\.\.\.'
        )

        while not finished or not output_queue.empty():
           try:
               line = output_queue.get(timeout=0.2)

               if line == "__COMPARISON_FINISHED__":
                   finished = True
                   continue

               match = playlist_start_pattern.match(line)

               if match:
                   current_playlist = match.group(1)

               current_logs.append(line)

               log_html = ""

               for line in current_logs:
                   escaped = html.escape(line)

                   if "Missing:" in line and "Duplicates:" in line:
                       parts = re.match(
                           r"\s*(Spotify:|YT Music:)\s*Missing:\s*(\d+)\s*\|\s*Duplicates:\s*(\d+)",
                           line
                       )

                       if parts:
                           log_html += f"""
                           <div class="summary-row">
                               <span>{parts.group(1)}</span>
                               <span>Missing: {parts.group(2)}</span>
                               <span>Duplicates: {parts.group(3)}</span>
                           </div>
                           """
                           continue

                   log_html += f'<div class="log-line">{escaped}</div>'

               with logs_placeholder:
                   components.html(
                       f"""
                       <style>
                           .log-container {{
                               height: 500px;
                               overflow-y: auto;
                               background: #0e1117;
                               color: #fafafa;
                               padding: 12px;
                               border-radius: 6px;
                               font-family: monospace;
                               font-size: 13px;
                           }}
                           .log-line {{
                               white-space: pre;
                           }}
                           .summary-row {{
                               display: grid;
                               grid-template-columns: 100px 130px 150px;
                               padding-left: 8px;
                               white-space: nowrap;
                           }}
                       </style>
                       <div class="log-container" id="log-container">
                           {log_html}
                       </div>
                       <script>
                           const c = document.getElementById("log-container");
                           c.scrollTop = c.scrollHeight;
                       </script>
                       """,
                       height=520,
                   )
           except queue.Empty:
               continue

        worker.join()

        # Immediately switch to the existing results page.
        st.session_state.page = "results"
        st.rerun()

    st.stop()


# =========================================================
# RESULTS PAGE
# =========================================================

if not RESULTS_DIR.exists():
    st.error(f"Results directory not found: {RESULTS_DIR}")
    st.stop()


entries = []

for csv_path in RESULTS_DIR.rglob("*.csv"):

    filename = csv_path.name.lower()

    if filename in FILES:

        playlist = csv_path.parent.name

        entries.append((
            playlist,
            filename,
            csv_path.read_bytes(),
            str(csv_path)
        ))


if not entries:
    st.error("No recognized result files were found.")
    st.stop()


# =========================================================
# ORGANIZE DATA BY PLAYLIST
# =========================================================

data = {}
read_errors = []

for playlist, filename, payload, source in entries:

    try:
        frame = load_csv(payload)

        if "name" not in frame.columns and "title" in frame.columns:
            frame["name"] = frame["title"]

        if (
            "spotify_name" not in frame.columns
            and "spotify_title" in frame.columns
        ):
            frame["spotify_name"] = frame["spotify_title"]

        if (
            "youtube_name" not in frame.columns
            and "youtube_title" in frame.columns
        ):
            frame["youtube_name"] = frame["youtube_title"]

        for column in COLUMNS_BY_FILE.get(
            filename,
            BASE_COLUMNS
        ):
            if column not in frame.columns:
                frame[column] = ""

        data.setdefault(
            playlist, {}
        ).setdefault(
            filename, []
        ).append(frame)

    except Exception as exc:
        read_errors.append(f"{source}: {exc}")


if read_errors:

    with st.expander("Files that could not be read"):

        for error in read_errors:
            st.warning(error)


playlists = sorted(data)

if not playlists:
    st.error("No valid files were found.")
    st.stop()


# =========================================================
# REAL PLAYLIST NAMES
# =========================================================

playlist_names = load_playlist_names()

# Display real names, but keep normalized names internally.
playlist_options = {
    playlist_names.get(key, key): key
    for key in playlists
}

real_names = list(playlist_options.keys())

selected_real_name = st.selectbox(
    "Select a playlist",
    real_names
)

selected = playlist_options[selected_real_name]

playlist_data = data[selected]


def combined(filename):

    frames = playlist_data.get(filename, [])

    if not frames:
        return pd.DataFrame()

    return pd.concat(
        frames,
        ignore_index=True
    )


st.subheader(selected_real_name)


# =========================================================
# SUMMARY METRICS
# =========================================================

metrics = st.columns(5)

for metric, (filename, label) in zip(
    metrics,
    FILES.items()
):

    frame = combined(filename)
    metric.metric(label, len(frame))


# =========================================================
# OVERVIEW
# =========================================================

st.markdown("### Overview")

overview = pd.DataFrame([
    {
        "Category": label,
        "Records": len(combined(filename))
    }
    for filename, label in FILES.items()
])

st.dataframe(
    overview,
    hide_index=True,
    use_container_width=True
)


# =========================================================
# RESULT TABS
# =========================================================

tabs = st.tabs(list(FILES.values()))

for tab, (filename, label) in zip(
    tabs,
    FILES.items()
):

    with tab:

        frame = view_frame(
            combined(filename),
            filename
        )

        if frame.empty:

            st.info(
                f"No records found, or `{filename}` is missing."
            )

        else:

            st.caption(
                f"{len(frame)} record(s) · {filename}"
            )

            st.dataframe(
                frame,
                hide_index=True,
                use_container_width=True
            )

            st.download_button(
                f"Download {filename}",
                data=frame.to_csv(
                    index=False
                ).encode("utf-8-sig"),
                file_name=f"{selected}_{filename}",
                mime="text/csv",
                key=f"download_{selected}_{filename}"
            )


# =========================================================
# EXPORT ALL PLAYLIST RESULTS
# =========================================================

st.markdown("### Export playlist results")

bundle = io.BytesIO()

with zipfile.ZipFile(
    bundle,
    "w",
    zipfile.ZIP_DEFLATED
) as archive:

    for filename in FILES:

        frame = view_frame(
            combined(filename),
            filename
        )

        if not frame.empty:

            archive.writestr(
                filename,
                frame.to_csv(
                    index=False
                ).encode("utf-8-sig")
            )


st.download_button(
    "⬇️ Download all playlist results (ZIP)",
    data=bundle.getvalue(),
    file_name=f"{selected}_results.zip",
    mime="application/zip"
)


# =========================================================
# DETECTED FILES
# =========================================================

with st.expander("Detected files"):

    summary = []

    for filename, label in FILES.items():

        frame = combined(filename)

        summary.append({
            "Result type": label,
            "Records": len(frame),
            "File found": (
                "Yes" if filename in playlist_data else "No"
            )
        })

    st.dataframe(
        pd.DataFrame(summary),
        hide_index=True,
        use_container_width=True
    )
