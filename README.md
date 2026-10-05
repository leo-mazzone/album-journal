# Album Journal

A small desktop album journal for macOS and Linux. Browse a cover grid, search by album or artist,
filter by year added, and keep optional half-star ratings and notes. There is only one date per album:
**date added**, which you can edit to backdate an entry.

The app always uses dark mode. On macOS it uses Qt's native macOS controls, system font,
a unified title/toolbar, and attached dialog sheets. Standard shortcuts work on both platforms:
Command-N / Ctrl-N to add an album, Command-O / Ctrl-O to open a library, Command-F / Ctrl-F
to search, and Command-W / Ctrl-W to close the current window.

Use **Rating** beside the year filter to choose a range. Drag either slider handle or enter precise
**Min** and **Max** values in half-star steps, then choose **Apply**. Both bounds are included; equal
bounds select one exact rating. Unrated albums are excluded from a range. **Clear** shows them again
and removes only the rating filter. Escape or clicking outside cancels changes that haven't been
applied. Text search, year added, and rating filters work together. Rating filtering is preserved
while viewing/editing albums, and resets when you open another library or restart the app.

## Run

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run from this directory:

```sh
uv sync --python 3.12
uv run album-journal
```

The first launch asks you to choose an empty folder (create one using the folder picker) or an existing
Album Journal library. Your chosen path is remembered in local app settings. Python and dependencies
are managed by uv; the app does not require a web server or a browser.

On Linux, Qt requires a desktop session and the system's Qt/X11 libraries. For Ubuntu/Debian, missing
`xcb` dependencies can usually be resolved with:

```sh
sudo apt install libegl1 libopengl0 libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 \
  libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-xinerama0
```

## Add an album

Choose **+ Add album** and paste a public YouTube Music album link. Supported examples:

```text
https://music.youtube.com/browse/MPREb_...
https://music.youtube.com/playlist?list=OLAK5uy_...
```

Share parameters such as `si` are fine. Album playlist links shared from regular YouTube also work.
Personal playlists, individual song links, and artist links are not album imports. No account login
is required. Fetching requires internet access, but saved albums, covers, and tracklists work offline.

Review the fetched album, optionally change its date, and choose **Add album**. Adding the same album
again opens the existing entry without replacing your notes, date, or rating. If only its cover fails,
you can still add the album and use **⋯ → Retry cover** in its detail window later.

Click a cover to open its details. Dates, ratings, and notes save automatically after a short pause;
closing with **×** or Escape flushes pending edits. A save failure keeps the window open and offers
**Retry saving**, preserving your text. The album menu also offers removal, with confirmation.

YouTube Music imports use the unofficial [ytmusicapi](https://ytmusicapi.readthedocs.io/) library.
Changes to YouTube may require dependency/app updates. Spotify and whole-library imports are deferred.
There is no playback, automatic listening history, or cloud synchronization.

## Move or back up your library

Close the app and copy the entire library folder to another machine. Use **⋯ → Open another library…**
to select it there. The executable and library folder are independent.

```text
My Albums/
  library.json                # format version
  albums/<uuid>.json          # one human-readable record per album
  covers/<uuid>-<token>.jpg    # downloaded artwork
  .album-journal.lock         # advisory lock; harmless when the app is closed
```

JSON records contain album title, artists, ordered tracks (title, artists, optional duration),
source provider/ID/link, date added in `YYYY-MM-DD` format, nullable numeric rating, notes, and a
relative cover path. Ratings are 0.5–5 in half-star steps; `null` means unrated. All records and the
manifest have `schema_version: 1`. No machine-specific paths or account credentials are stored.

Writes replace JSON files atomically. Damaged records are reported under **Library warnings** and
left untouched; valid records remain available. A library can only be open in one app instance at
a time. Do not edit or synchronize the folder concurrently while the app is open. If editing JSON
by hand, close the app first and preserve record IDs, filenames, and the schema version.

## Test and package

### Download builds from GitHub Actions

The **Build desktop apps** workflow runs on pushes and pull requests, and can also be started
manually from GitHub's **Actions** tab. It checks formatting, runs the tests, builds with PyInstaller,
and smoke-tests each packaged app before uploading these artifacts:

| Artifact | Platform | Contents |
| --- | --- | --- |
| `album-journal-macos-arm64` | Apple Silicon Mac | ZIP containing `Album Journal.app` |
| `album-journal-macos-x86_64` | Intel Mac | ZIP containing `Album Journal.app` |
| `album-journal-linux-x86_64` | 64-bit Intel/AMD Linux | tar.gz containing `AlbumJournal/` |

After pushing this repository to GitHub, open a successful workflow run and download the appropriate
artifact from its **Artifacts** section. Extract the artifact download, then extract the app archive
inside it. On macOS, move `Album Journal.app` into Applications and open it. On Linux, keep the entire
`AlbumJournal` folder together and run its `AlbumJournal` executable. No Python or uv installation
is needed. Your library stays in the folder you select when launching the app.

Artifacts are retained for 14 days. These builds are unsigned; macOS may require approving the app
in **System Settings → Privacy & Security** on first launch. Linux builds use Ubuntu 22.04;
the desktop libraries listed above are still required. Native desktop behavior should also be
checked on each target machine. The workflow produces downloads without publishing GitHub releases.

### Build locally

```sh
uv run pytest
uv run ruff check .
uv run pyinstaller --noconfirm AlbumJournal.spec
```

An offline packaging check renders both screens using a temporary sample library and verifies saved
edits. It leaves your actual library and settings untouched:

```sh
QT_QPA_PLATFORM=offscreen uv run album-journal --smoke-test --screenshots preview
# After packaging, on macOS:
QT_QPA_PLATFORM=offscreen 'dist/Album Journal.app/Contents/MacOS/AlbumJournal' --smoke-test
# After packaging, on Linux:
QT_QPA_PLATFORM=offscreen dist/AlbumJournal/AlbumJournal --smoke-test
```

The optional screenshots use fictional albums with simple color placeholders, not fetched artwork.

The generated app icon is stored in `album_journal/assets/app-icon.png`, with its generation prompt
beside it. The macOS bundle uses `packaging/AlbumJournal.icns`; Linux and development runs use the PNG.

Build on each target OS: PyInstaller does not cross-compile. On macOS, open
`dist/Album Journal.app`; on Linux, run `dist/AlbumJournal/AlbumJournal` and distribute the whole
`dist/AlbumJournal` directory. Packaged apps include Python and dependencies. Builds are unsigned
and intended for personal use. Build Linux releases on the oldest distribution you intend to
support; newer glibc builds may not run on older distributions.

The test suite exercises imports with mocked service responses, download errors, duplicate imports,
portable storage, interrupted saves, malformed records, combined filters, and pending UI saves.
GUI tests use Qt's offscreen platform by default. Native packaged builds still need a desktop smoke
test on each target OS: import a real album, restart offline, edit notes/date/rating, and move the
library folder.
