# SpinShare for Decky

Browse SpinShare and manage Spin Rhythm XD custom songs from a full-page view in Steam Game Mode. Open the plugin in Decky's quick-access menu, then select **Open SpinShare**.

## Features

- Native Decky tabs, standard song rows, dropdowns, and controller-friendly filter dialogs.
- New releases, weekly/monthly/yearly/all-time top songs, recently updated charts, and search.
- Easy, Normal, Hard, Extreme, or XD filtering with minimum/maximum rating sliders (0–99).
- Sort by collection order, easiest/hardest matching chart, download count, or title.
- Cover art, artist/charter details, difficulty ratings, descriptions, and download counts.
- Download progress that continues when you leave the page.
- Installed library, missing-file indicators, and confirmed local deletion.
- Automatic Proton folder detection through Steam libraryfolders.vdf, including SD cards; explicit selection when multiple prefixes exist.
- Existing custom charts appear by filename. Deleting one removes its chart file and retains audio/artwork.

## Build

Requires Node.js and Python 3.11 or later. The Python backend has no third-party dependencies.

```sh
npm ci
npm run typecheck
npm test
npm run package
```

The installable package is `release/spinshare-decky-0.2.0.zip`.

## Install on your Deck

Install Decky Loader first. Transfer the release ZIP to the Deck and use Decky's developer ZIP installer. If your Decky version only offers installation from a URL, host the ZIP at a URL the Deck can reach and use that installer.

For manual installation in Desktop Mode, extract the ZIP's `spinshare-decky` directory into `/home/deck/homebrew/plugins/`. Its `plugin.json`, `main.py`, and `dist/index.js` must be directly inside that directory. Keep the files owned by the `deck` user, then restart Decky Loader or reboot.

Launch Spin Rhythm XD at least once so Proton creates its save directory. Open SpinShare → Settings and confirm the selected path. The usual location is:

```text
/home/deck/.local/share/Steam/steamapps/compatdata/1058830/pfx/drive_c/users/steamuser/AppData/LocalLow/Super Spin Digital/Spin Rhythm XD/Custom
```

SD-card installations can use a different Steam library root. If no folder is found, create a custom chart in-game once and reopen the plugin. A custom path must end in `Custom` and its parent folder must already exist. Select the prefix actually used by the game when multiple paths are offered.

Charts go directly in `Custom`; their audio and cover assets go in `Custom/AudioClips` and `Custom/AlbumArt`. Reopen the game's Custom list after installation; restart the game if it hasn't refreshed.

## Browsing and filters

Use **Browse songs**, **Installed**, and **Settings** in the native Decky tab bar. The collection dropdown chooses newest, updated, or a top-song period. The sort dropdown orders the whole result set, not just the visible page.

Open **Filters** to choose a difficulty and adjust minimum/maximum rating with native sliders. Select **Apply filters** to update results, or Cancel to leave them unchanged. Ranges are inclusive and the two sliders cannot cross. With all difficulties selected, any chart in the range qualifies; easiest/hardest sorting uses the lowest/highest matching chart on each song. Unknown ratings sort last and are excluded by restricted filters.

**Top · This year** ranks charts uploaded this calendar year by total downloads. **Top · All time** ranks all upload dates. Weekly/monthly collections use the same upload-window meaning as SpinShare. These are not historical counts of downloads within the period. Search and difficulty filters combine with the chosen collection.

The first broad filtered search may take longer because SpinShare returns the full result set. Sort changes reuse the response for five minutes. Difficulty/rating constraints reduce the server response; an already cached broad search also serves narrower filters. Unfiltered new/updated/weekly/monthly browsing uses smaller paginated feeds.

See [UI references and filtering details](https://github.com/RealDishwash/SpinshareDecky/blob/main/docs/ui-patterns.md).

## File handling

The hidden `.spinshare-decky.json` file in Custom records installed songs and file hashes. Keep this file to retain managed deletion. Conflicting existing files are never overwritten. Identical files can be shared; modified/pre-existing files are preserved on deletion. When unknown charts exist, assets are conservatively retained because those charts may reference them. A managed song must be deleted before downloading a newer version.

Archives are staged, checked for unsafe paths/symlinks, duplicate destinations, chart presence, and size limits before installation. Limits are 256 MiB compressed, 512 MiB expanded, and 512 archive entries. Ordinary write failures roll back installation/deletion; abrupt power loss is not covered by a crash-recovery journal. Avoid editing the same library with another application while a download or deletion is running.

Only one download runs at a time. DLC charts requiring entitlement verification are not supported; use the official SpinShare client for those. No login, playlist management, preview playback, automatic updates, or store publication is included in this version.

## Privacy and attribution

Catalogue, artwork, and downloads are provided by [SpinShare](https://spinsha.re/). Search terms are sent to SpinShare's public API. The plugin stores its chosen folder and a local installation manifest. It does not request credentials or add analytics. Search results are cached for five minutes; other catalogue responses for one minute.

References: [SpinShare API](https://spinsha.re/api/docs), [official game editor guide](https://www.spinrhythmgame.com/editor-guide), [Decky plugin template and packaging](https://github.com/SteamDeckHomebrew/decky-plugin-template).

## Validation and device checklist

Automated tests cover archive layout, traversal/symlink rejection, collision protection, shared/pre-existing/modified files, missing files, rollback on manifest write failure, and SD-card library discovery. A live API/archive smoke test exercises catalogue/search/details and a real download/install/delete in a temporary directory.

The frontend is type-checked and bundled against current Decky packages. Actual Steam Game Mode rendering and gamepad navigation require a Steam Deck and have not been verified here. Before everyday use, check:

1. Open the full-page view and navigate tabs, search, song rows, and Back using the controller.
2. Open Filters, adjust both sliders with the D-pad, test Cancel/Apply, and check both difficulty sort directions.
3. Confirm Settings points to the active game's prefix.
4. Download one chart and verify chart, audio, and artwork inside the game.
5. Delete it and check the game's refreshed custom list.
6. Check an SD-card installation, network failure/retry, and returning to an active download.

## HTTPS certificates

The plugin loads the SteamOS system CA bundle explicitly because Decky’s bundled Python can have certificate paths from its build environment. HTTPS certificate and hostname verification remain enabled for both catalogue requests and downloads.
