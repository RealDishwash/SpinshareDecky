import { useEffect, useRef, useState } from 'react';
import { definePlugin, routerHook, toaster } from '@decky/api';
import {
  ButtonItem, ConfirmModal, DialogBody, DialogBodyText, DialogButton,
  DialogControlsSection, DialogControlsSectionHeader, DialogHeader, Dropdown,
  Field, Focusable, Navigation, PanelSection, PanelSectionRow,
  showModal, Tabs, TextField,
} from '@decky/ui';
import { FaCompactDisc } from 'react-icons/fa';
import * as api from './api';
import { FiltersModal } from './FiltersModal';
import { collections, defaults, difficultyText, filterSummary, Filters, orders, Song, Status } from './types';

const ROUTE = '/spinshare';
// Layout only. Steam/Decky own typography, controls, colors and focus styling.
// See docs/ui-patterns.md for the Animation Changer and CSS Loader references.
const css = `
.spinshare-content { padding: 16px 24px 32px; box-sizing: border-box; }
.spinshare-toolbar { display: flex; gap: 12px; align-items: end; margin-bottom: 16px; }
.spinshare-toolbar > * { flex: 1; min-width: 0; }
.spinshare-search { flex: 3; }
.spinshare-cover { width: 56px; height: 56px; object-fit: cover; flex-shrink: 0; }
.spinshare-details { display: flex; gap: 24px; align-items: start; margin: 20px 0; }
.spinshare-details .spinshare-cover { width: 160px; height: 160px; }
.spinshare-details > div { min-width: 0; flex: 1; }
.spinshare-wrap { overflow-wrap: anywhere; white-space: pre-wrap; }
.spinshare-footer { display: flex; align-items: center; gap: 16px; margin-top: 20px; }
.spinshare-footer > button { flex: 1; }
`;
function Cover({ song }: { song: Song }) {
  const [failed, setFailed] = useState(false);
  return song.cover && !failed
    ? <img className="spinshare-cover" src={song.cover} alt="" onError={() => setFailed(true)} />
    : <FaCompactDisc className="spinshare-cover" aria-hidden />;
}

function Page() {
  const [tab, setTab] = useState('browse');
  const [mode, setMode] = useState('new');
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState('');
  const [localSearch, setLocalSearch] = useState('');
  const [filters, setFilters] = useState<Filters>(defaults);
  const [offset, setOffset] = useState(0);
  const [songs, setSongs] = useState<Song[]>([]);
  const [more, setMore] = useState(false);
  const [total, setTotal] = useState<number | null>(null);
  const [state, setState] = useState<Status>();
  const [selected, setSelected] = useState<Song>();
  const [loading, setLoading] = useState(false);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState('');
  const [path, setPathInput] = useState('');
  const [reload, setReload] = useState(0);
  const request = useRef(0);
  const detailRequest = useRef(0);
  const busy = acting || ['downloading', 'installing'].includes(state?.job.state ?? '');

  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try { const value = await api.status(); if (live) setState(value); }
      catch (e) { if (live) setError(api.errorMessage(e)); }
      finally { if (live) timer = setTimeout(poll, 1500); }
    };
    void poll();
    return () => { live = false; clearTimeout(timer); detailRequest.current++; };
  }, []);

  useEffect(() => {
    const id = ++request.current;
    if (tab !== 'browse') { setLoading(false); return; }
    setLoading(true);
    setError('');
    api.browse(mode, search, offset, filters)
      .then(result => {
        if (id === request.current) { setSongs(result.songs); setMore(result.hasMore); setTotal(result.total); }
      })
      .catch(e => { if (id === request.current) { setSongs([]); setMore(false); setError(api.errorMessage(e)); } })
      .finally(() => { if (id === request.current) setLoading(false); });
    return () => { request.current++; };
  }, [tab, mode, search, offset, filters, reload]);

  const run = async (action: () => Promise<unknown>) => {
    setActing(true); setError('');
    try { await action(); setState(await api.status()); }
    catch (e) { setError(api.errorMessage(e)); }
    finally { setActing(false); }
  };
  const closeSong = () => { detailRequest.current++; setSelected(undefined); };
  const openSong = (song: Song) => {
    const id = ++detailRequest.current;
    setSelected(song); setError('');
    if (!song.local) {
      void api.detail(song.id).then(value => {
        if (id !== detailRequest.current) return;
        if (!value || !value.id) throw new Error('This song is no longer available on SpinShare.');
        setSelected({ ...value, key: song.key });
      }).catch(e => { if (id === detailRequest.current) setError(api.errorMessage(e)); });
    }
  };
  const installed = selected && state?.songs.find(song => selected.local ? song.key === selected.key : song.id === selected.id);
  const deleteSelected = () => {
    if (!installed) return;
    showModal(<ConfirmModal
      strTitle={`Delete ${installed.title}?`}
      strDescription={installed.local
        ? 'Remove this chart from your Deck? Its existing audio and artwork will be preserved.'
        : 'Remove this song from your Deck? Shared and modified files will be preserved.'}
      strOKButtonText="Delete song"
      onOK={() => void run(async () => {
        const result = await api.remove(installed.key!);
        toaster.toast({ title: 'SpinShare', body: result.message });
        closeSong();
      })}
    />);
  };
  const applySearch = () => { setOffset(0); setSearch(query.trim()); setReload(value => value + 1); };
  const applyFilters = (value: Filters) => { setOffset(0); setFilters(value); };
  const localSongs = (state?.songs ?? []).filter(song =>
    `${song.title} ${song.artist} ${song.charter}`.toLowerCase().includes(localSearch.toLowerCase()));

  const notices = <>
    {state?.job.message && <Field label={state.job.state === 'error' ? 'Download failed' : 'Download'}
      description={<span role="status">{state.job.message}{state.job.bytes ? ` · ${(state.job.bytes / 1048576).toFixed(1)} MB` : ''}</span>} />}
    {error && <Field label="Unable to complete request" description={<span role="alert">{error}</span>}>
      <DialogButton onClick={() => { setError(''); setReload(value => value + 1); }}>Retry</DialogButton>
    </Field>}
  </>;
  const songList = (items: Song[]) => <DialogControlsSection>
    {items.map(song => <Field
      key={song.key ?? song.id}
      label={song.title}
      description={<>{song.artist}{song.charter ? ` · ${song.charter}` : ''}<br />{difficultyText(song)}
        {song.missing && <><br />Some files are missing</>}
      </>}
      icon={<Cover key={song.cover ?? song.key ?? song.id} song={song} />}
      focusable highlightOnFocus
      onActivate={() => openSong(song)}
      onClick={() => openSong(song)}
    >
      {state?.songs.some(s => (song.key && s.key === song.key) || (song.id > 0 && s.id === song.id)) ? 'Installed' : ''}
    </Field>)}
  </DialogControlsSection>;

  const browser = <div className="spinshare-content">
    {notices}
    <Focusable className="spinshare-toolbar" flow-children="row">
      <div className="spinshare-search"><TextField label="Search songs, artists or charters" value={query}
        bShowClearAction onChange={e => setQuery(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') applySearch(); }} /></div>
      <DialogButton onClick={applySearch}>Search</DialogButton>
      <DialogButton onClick={() => showModal(<FiltersModal initial={filters} onApply={applyFilters} />)}>Filters</DialogButton>
    </Focusable>
    <Focusable className="spinshare-toolbar" flow-children="row">
      <Dropdown menuLabel="Browse collection" rgOptions={collections} selectedOption={mode}
        onChange={({ data }) => { setOffset(0); setMode(data); }} />
      <Dropdown menuLabel="Sort songs" rgOptions={orders} selectedOption={filters.sort}
        onChange={({ data }) => applyFilters({ ...filters, sort: data })} />
    </Focusable>
    <DialogBodyText>
      {filterSummary(filters)}{search ? ` · Search: ${search}` : ''}{total !== null && !loading ? ` · ${total.toLocaleString()} songs` : ''}
    </DialogBodyText>
    {['hotThisWeek', 'hotThisMonth', 'topYear', 'topAllTime'].includes(mode) && <DialogBodyText>
      Ranked by total downloads{mode === 'topAllTime' ? ' across all upload dates.' : ` among charts uploaded ${mode === 'topYear' ? 'this calendar year' : mode === 'hotThisWeek' ? 'in the last 7 days' : 'in the last month'}.`}
      {filters.sort !== 'recommended' && ' Your sort order overrides the ranking.'}
    </DialogBodyText>}
    {filters.sort.startsWith('difficulty') && filters.difficulty === 'all' && <DialogBodyText>
      {filters.sort === 'difficultyAsc' ? 'Uses each song’s lowest matching chart rating.' : 'Uses each song’s highest matching chart rating.'}
    </DialogBodyText>}
    {loading ? <DialogBodyText><span role="status">Loading songs… A broad catalogue search can take a minute or two.</span></DialogBodyText>
      : songs.length ? songList(songs) : !error && <DialogBodyText>No matching songs. Try a wider difficulty range or clear your search.</DialogBodyText>}
    <Focusable className="spinshare-footer" flow-children="row">
      <DialogButton disabled={offset === 0 || loading} onClick={() => setOffset(value => Math.max(0, value - 12))}>Previous</DialogButton>
      <span>Page {offset / 12 + 1}</span>
      <DialogButton disabled={!more || loading} onClick={() => setOffset(value => value + 12)}>Next</DialogButton>
    </Focusable>
  </div>;

  const library = <div className="spinshare-content">
    {notices}
    <TextField label="Search installed songs" value={localSearch} bShowClearAction onChange={e => setLocalSearch(e.target.value)} />
    {state?.error && <DialogBodyText>{state.error}</DialogBodyText>}
    {localSongs.length ? songList(localSongs) : <DialogBodyText>No installed songs found. Download a chart or check the game folder in Settings.</DialogBodyText>}
  </div>;

  const settings = <div className="spinshare-content">
    {notices}
    <DialogControlsSection>
      <DialogControlsSectionHeader>Song location</DialogControlsSectionHeader>
      <Field label="Current folder" description={<span className="spinshare-wrap">{state?.path || state?.error || 'Detecting game folder…'}</span>} />
      {state?.candidates.map(candidate => <Field key={candidate} label="Detected game folder" description={<span className="spinshare-wrap">{candidate}</span>}>
        <DialogButton disabled={busy} onClick={() => void run(() => api.setPath(candidate))}>Use folder</DialogButton>
      </Field>)}
      <TextField label="Custom folder path" value={path} onChange={e => setPathInput(e.target.value)} />
      <DialogButton disabled={busy || !path.trim()} onClick={() => void run(() => api.setPath(path.trim()))}>Save folder</DialogButton>
    </DialogControlsSection>
    <DialogBodyText>Launch Spin Rhythm XD once before setup. Reopen the game’s Custom list after downloading.</DialogBodyText>
    <DialogBodyText>Existing charts are listed by filename. Deleting them preserves audio and artwork.</DialogBodyText>
    <DialogBodyText>Catalogue and artwork provided by SpinShare · spinsha.re. Searches are sent to SpinShare; songs are stored locally. No account is required.</DialogBodyText>
  </div>;

  return <div style={{ marginTop: 40, height: 'calc(100% - 40px)', overflow: 'hidden' }}>
    <style>{css}</style>
    {selected ? <Focusable style={{ height: '100%', overflowY: 'auto' }} onCancel={event => { event.stopPropagation(); closeSong(); }}>
      <div className="spinshare-content">
        <DialogButton onClick={closeSong}>Back to songs</DialogButton>
        {notices}
        <DialogBody>
          <div className="spinshare-details"><Cover key={selected.cover ?? selected.id} song={selected} /><div>
            <DialogHeader>{selected.title}</DialogHeader>
            <DialogBodyText>{selected.artist}<br />Chart by {selected.charter || 'unknown'}<br />{selected.subtitle}</DialogBodyText>
            <DialogBodyText>{difficultyText(selected)}</DialogBodyText>
            {selected.downloads != null && <DialogBodyText>{selected.downloads.toLocaleString()} downloads</DialogBodyText>}
          </div></div>
          {selected.dlc && <DialogBodyText>Requires {selected.dlc.title}. Use the official SpinShare client for DLC verification.</DialogBodyText>}
          {installed ? <DialogButton disabled={busy} onClick={deleteSelected}>Delete from Deck</DialogButton>
            : <DialogButton disabled={busy || !state?.path || !!selected.dlc} onClick={() => void run(() => api.install(selected.id))}>Download song</DialogButton>}
          {installed?.missing && <DialogBodyText>Some files are missing. Delete this entry and download again to repair.</DialogBodyText>}
          {!state?.path && <DialogBodyText>Choose the game folder in Settings before downloading.</DialogBodyText>}
          <DialogBodyText><span className="spinshare-wrap">{selected.description}</span></DialogBodyText>
          <DialogBodyText>{selected.tags?.join(' · ')}</DialogBodyText>
        </DialogBody>
      </div>
    </Focusable> : <Tabs activeTab={tab} onShowTab={(value: string) => setTab(value)} tabs={[
      { id: 'browse', title: 'Browse songs', content: browser },
      { id: 'installed', title: `Installed (${state?.songs.length ?? 0})`, content: library },
      { id: 'settings', title: 'Settings', content: settings },
    ]} />}
  </div>;
}

export default definePlugin(() => {
  routerHook.addRoute(ROUTE, Page, { exact: true });
  return {
    name: 'SpinShare', titleView: <div>SpinShare</div>, icon: <FaCompactDisc />,
    content: <PanelSection title="SPIN RHYTHM XD"><PanelSectionRow>
      <ButtonItem layout="below" onClick={() => { Navigation.Navigate(ROUTE); Navigation.CloseSideMenus(); }}>Open SpinShare</ButtonItem>
    </PanelSectionRow></PanelSection>,
    onDismount() { routerHook.removeRoute(ROUTE); },
  };
});
