# Decky UI references

This revision follows established Decky plugin structure instead of a custom visual theme.

- [Animation Changer full-page manager](https://github.com/TheLogicMaster/SDH-AnimationChanger/blob/main/src/index.tsx): native `Tabs`, separate browser/installed/settings content, and a 40-pixel top inset for Steam's chrome.
- [Animation Changer browser](https://github.com/TheLogicMaster/SDH-AnimationChanger/blob/main/src/animation-manager/AnimationBrowserPage.tsx): `Focusable` toolbar groups with native search and sorting controls.
- [CSS Loader search controls](https://github.com/DeckThemes/SDH-CssLoader/blob/main/src/components/ThemeManager/BrowserSearchFields.tsx): Decky dropdowns, text fields, and `SliderField` controls.
- [Decky's current component definitions](https://github.com/SteamDeckHomebrew/decky-frontend-lib/tree/main/src/components): current `@decky/ui` interfaces. The older reference plugins use the previous package name; this plugin uses the current package.

The implementation uses native `Field` song rows, `ConfirmModal`, dropdowns, and sliders. Custom CSS only arranges spacing, artwork sizing, and wrapping. It does not replace Steam's colors, typography, button styles, or focus rings. The reference plugins' private Steam class extraction and CSS overrides have not been copied.

## Filtering semantics

The filter dialog stages changes until Apply. Cancel preserves the previous selection. Moving minimum above maximum raises maximum; moving maximum below minimum lowers minimum. Reset restores all difficulties and 0–99 without changing the chosen sort.

A matching chart must satisfy both the selected difficulty type and the inclusive numeric range. Selecting all difficulties means any chart within the range qualifies. Low-to-high uses a song's lowest matching chart; high-to-low uses its highest. Unknown ratings sort last and do not qualify for a restricted numeric/type filter.

SpinShare's API calls the Extreme numeric rating `expertDifficulty`, with availability in `hasExtremeDifficulty`. The UI calls this difficulty Extreme, as requested.

## Rankings and API evidence

- [Discovery controller](https://github.com/SpinShare/server/blob/master/src/Controller/API/APIDiscoveryController.php)
- [Song repository](https://github.com/SpinShare/server/blob/master/src/Repository/SongRepository.php)
- [Public discovery documentation](https://spinsha.re/api/docs/open/discovery)

SpinShare's weekly/monthly lists rank songs by total downloads among charts uploaded within that period, with views as a tie-breaker. This plugin follows that meaning for its added collections: this calendar year (UTC year boundary) and all upload dates. These are not counts of downloads that occurred during the chosen period.

The documented search endpoint returns the full matching result, including download counts, dates, and ratings. The plugin uses one search response to filter and sort globally before returning a 12-song page. Difficulty and rating constraints are sent to SpinShare to reduce the response size. Changing sort reuses that query, and a cached broad search can serve narrower filters without a new request. It does not crawl song detail pages. Search responses are cached for five minutes; other API responses for one minute, with at most four cached responses. Unfiltered built-in collections still use the smaller dedicated feed requests.

The dedicated feed's parameter named `offset` is actually multiplied by 12 in the server repository. The plugin converts record offsets into page indices before calling those endpoints.

## Verification boundary

Backend tests and live API checks cover global ordering, date windows, tier/range matching, pagination, and large search responses. TypeScript checks and a Rollup build validate component interfaces and packaging. Actual native widgets are supplied by Steam at runtime: browser mocks cannot prove their rendering or controller behavior. Final visual and gamepad verification must happen in Steam Game Mode on the Deck.
