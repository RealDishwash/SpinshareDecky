import { useEffect, useRef, useState } from 'react';
import { callable, definePlugin, routerHook, toaster } from '@decky/api';
import { ButtonItem, ConfirmModal, DialogButton, Focusable, Navigation, PanelSection, PanelSectionRow, showModal, TextField } from '@decky/ui';
import { FaCompactDisc } from 'react-icons/fa';

interface Song { id: number; key?: string; title: string; subtitle?: string; artist: string; charter: string; cover?: string; description?: string; downloads?: number; tags?: string[]; dlc?: {title: string}; local?: boolean; missing?: boolean; [key: string]: unknown }
interface Status { path: string; candidates: string[]; songs: Song[]; error: string; job: {state: string; message: string; bytes?: number; id?: number} }
const browse = callable<[string, string, number], {songs: Song[]; hasMore: boolean}>('browse');
const detail = callable<[number], Song>('detail');
const status = callable<[], Status>('status');
const install = callable<[number], boolean>('install');
const remove = callable<[string], {message: string}>('delete_song');
const setPath = callable<[string], Status>('set_path');
const ROUTE = '/spinshare';
const modes = [['new', 'New releases'], ['hotThisWeek', 'Hot this week'], ['hotThisMonth', 'Hot this month'], ['updated', 'Recently updated'], ['installed', 'Installed'], ['settings', 'Settings']];
const difficulties = [['Easy', 'easyDifficulty', 'hasEasyDifficulty'], ['Normal', 'normalDifficulty', 'hasNormalDifficulty'], ['Hard', 'hardDifficulty', 'hasHardDifficulty'], ['Expert', 'expertDifficulty', 'hasExtremeDifficulty'], ['XD', 'XDDifficulty', 'hasXDDifficulty']];
const css = `
.ss{--ink:#eef4ff;--muted:#aebdd3;--panel:#233149;--cyan:#6ce2ed;--pink:#ff89bd;box-sizing:border-box;background:#152238;color:var(--ink);height:100%;overflow:auto;padding:30px 36px 48px;font-family:Arial,sans-serif}
.ss *{box-sizing:border-box}.ss h1{font-size:32px;letter-spacing:-1.2px;margin:0}.ss h2{font-size:24px;margin:0 0 10px}.ss p{line-height:1.45}.ss header,.ss .row{display:flex;align-items:center;gap:12px}.ss header{justify-content:space-between;margin-bottom:22px}.ss .brand{display:flex;gap:14px;align-items:center}.ss .disc{color:var(--cyan);font-size:42px}.ss .caption{color:var(--muted);font-size:13px;margin-top:5px}.ss .nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.ss button{min-width:0!important;width:auto!important;border-radius:6px!important;font-size:14px!important}.ss .nav .active{background:var(--cyan)!important;color:#152238!important}.ss .search{display:flex;gap:12px;margin-bottom:20px;align-items:center}.ss .search>div{flex:1}.ss .grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.ss .song{display:flex;align-items:center;text-align:left!important;gap:12px;background:var(--panel)!important;padding:12px!important;min-height:110px;white-space:normal!important;width:100%!important}.ss .cover{width:76px;height:76px;object-fit:cover;border-radius:4px;flex-shrink:0;background:#344560}.ss .placeholder{display:flex;align-items:center;justify-content:center;font-size:32px;color:var(--cyan)}.ss .songtext{min-width:0}.ss .title{font-size:16px;font-weight:700;display:block;overflow-wrap:anywhere}.ss .artist{font-size:13px;color:var(--muted);display:block;margin:5px 0}.ss .badges{display:flex;gap:5px;flex-wrap:wrap;margin-top:6px}.ss .badge{font-size:11px;color:var(--cyan);border:1px solid #607489;border-radius:4px;padding:3px 5px}.ss .badge:nth-child(4),.ss .badge:nth-child(5){color:var(--pink)}.ss .installed{color:var(--cyan);font-size:12px}.ss .notice{padding:12px 16px;background:#293c54;border-left:3px solid var(--cyan);margin-bottom:16px;overflow-wrap:anywhere}.ss .error{border-color:var(--pink)}.ss .pagination{justify-content:space-between;margin-top:20px}.ss .detail{display:grid;grid-template-columns:220px 1fr;gap:28px;margin-top:24px}.ss .detail .cover{width:220px;height:220px}.ss .description{white-space:pre-wrap;color:var(--muted);overflow-wrap:anywhere}.ss .path{overflow-wrap:anywhere;color:var(--muted);font-size:13px}.ss .settings{max-width:850px}.ss .settings button{margin:8px 8px 8px 0}.ss button:focus-visible{outline:3px solid var(--cyan)!important;outline-offset:3px}.ss .busy{color:var(--cyan)}@media(max-width:900px){.ss{padding:22px}.ss .grid{grid-template-columns:repeat(2,minmax(0,1fr))}.ss .nav{gap:6px}.ss .detail{grid-template-columns:170px 1fr}.ss .detail .cover{width:170px;height:170px}}@media(max-width:550px){.ss .grid{grid-template-columns:1fr}.ss .detail{grid-template-columns:1fr}}
`;
function Cover({song}: {song: Song}) {
  const [failed, setFailed] = useState(false);
  return song.cover && !failed ? <img className="cover" src={song.cover} alt="" onError={() => setFailed(true)} /> : <div className="cover placeholder"><FaCompactDisc /></div>;
}
function Badges({song}: {song: Song}) { return <div className="badges">{difficulties.filter(([, , flag]) => song[flag]).map(([label, value]) => <span className="badge" key={label}>{label} {String(song[value] ?? '—')}</span>)}</div>; }
function Page() {
  const [mode, setMode] = useState('new');
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [songs, setSongs] = useState<Song[]>([]);
  const [more, setMore] = useState(false);
  const [state, setState] = useState<Status>();
  const [selected, setSelected] = useState<Song>();
  const [loading, setLoading] = useState(false);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState('');
  const [path, setPathInput] = useState('');
  const [reload, setReload] = useState(0);
  const request = useRef(0);
  const busy = acting || ['downloading', 'installing'].includes(state?.job.state ?? '');
  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => { try { const value = await status(); if (live) setState(value); } catch (e) { if (live) setError(String(e)); } finally { if (live) timer = setTimeout(poll, 1500); } };
    void poll();
    return () => { live = false; clearTimeout(timer); };
  }, []);
  useEffect(() => {
    const id = ++request.current;
    if (mode === 'installed' || mode === 'settings') { setLoading(false); return; }
    setLoading(true); setError('');
    browse(mode, search, offset).then(result => { if (id === request.current) { setSongs(result.songs); setMore(result.hasMore); } }).catch(e => { if (id === request.current) setError(String(e)); }).finally(() => { if (id === request.current) setLoading(false); });
    return () => { request.current++; };
  }, [mode, search, offset, reload]);
  const run = async (action: () => Promise<unknown>) => { setActing(true); setError(''); try { await action(); setState(await status()); } catch (e) { setError(String(e)); } finally { setActing(false); } };
  const selectMode = (value: string) => { setMode(value); setOffset(0); setSelected(undefined); setError(''); };
  const openSong = (song: Song) => { setSelected(song); if (!song.local) void detail(song.id).then(value => setSelected(current => current?.id === song.id ? {...value, key: song.key} : current)).catch(e => setError(String(e))); };
  const installed = selected && state?.songs.find(song => selected.local ? song.key === selected.key : song.id === selected.id);
  const deleteSelected = () => { if (!installed) return; showModal(<ConfirmModal strTitle={`Delete ${installed.title}?`} strDescription={installed.local ? 'Remove this chart from your Deck? Its existing audio and artwork will be preserved.' : 'Remove this song from your Deck? Shared and modified files will be preserved.'} strOKButtonText="Delete song" onOK={() => { void run(async () => { const result = await remove(installed.key!); toaster.toast({title: 'SpinShare', body: result.message}); setSelected(undefined); }); }} />); };
  const visible = mode === 'installed' ? (state?.songs ?? []).filter(s => `${s.title} ${s.artist} ${s.charter}`.toLowerCase().includes(query.toLowerCase())) : songs;
  return <Focusable className="ss" onCancel={() => selected ? setSelected(undefined) : Navigation.NavigateBack()}>
    <style>{css}</style>
    <header><div className="brand"><FaCompactDisc className="disc"/><div><h1>SpinShare</h1><div className="caption">Custom tracks. Ready to spin.</div></div></div><DialogButton onClick={() => selected ? setSelected(undefined) : Navigation.NavigateBack()}>{selected ? 'Back to songs' : 'Close'}</DialogButton></header>
    {state?.job.message && <div role="status" className={`notice ${state.job.state === 'error' ? 'error' : ''}`}>{state.job.message}{state.job.bytes ? ` · ${(state.job.bytes / 1048576).toFixed(1)} MB` : ''}</div>}
    {error && <div role="alert" className="notice error">{error} <DialogButton onClick={() => { setError(''); setReload(x => x + 1); }}>Retry</DialogButton></div>}
    {selected ? <><div className="detail"><Cover key={selected.id} song={selected}/><div><h2>{selected.title}</h2><div>{selected.artist}</div><p className="caption">{selected.subtitle}<br/>Chart by {selected.charter || 'unknown'}</p><Badges song={selected}/><p>{selected.downloads != null ? `${selected.downloads.toLocaleString()} downloads` : ''}</p>{selected.dlc && <p>Requires {selected.dlc.title}. Use the official SpinShare client for DLC verification.</p>}<div className="row">{installed ? <DialogButton disabled={busy} onClick={deleteSelected}>Delete from Deck</DialogButton> : <DialogButton disabled={busy || !state?.path || !!selected.dlc} onClick={() => void run(() => install(selected.id))}>Download song</DialogButton>}</div>{installed?.missing && <p>Some installed files are missing. Delete this entry and download again to repair.</p>}{!state?.path && <p>Choose the game folder in Settings before downloading.</p>}</div></div><p className="description">{selected.description}</p><p className="caption">{selected.tags?.join(' · ')}</p></> : <>
    <Focusable className="nav" flow-children="row">{modes.map(([key, label]) => <DialogButton key={key} className={mode === key ? 'active' : ''} onClick={() => selectMode(key)}>{label}{key === 'installed' ? ` (${state?.songs.length ?? 0})` : ''}</DialogButton>)}</Focusable>
    {mode === 'settings' ? <div className="settings"><h2>Song location</h2><p>Choose the Custom folder used by Spin Rhythm XD. Launch the game once before setup.</p><p className="path">{state?.path || state?.error}</p>{state?.candidates.map(candidate => <div key={candidate}><p className="path">{candidate}</p><DialogButton disabled={busy} onClick={() => void run(() => setPath(candidate))}>Use this folder</DialogButton></div>)}<TextField label="Custom folder path" value={path} onChange={e => setPathInput(e.target.value)} /><DialogButton disabled={busy || !path.trim()} onClick={() => void run(() => setPath(path.trim()))}>Save folder</DialogButton><p className="caption">Catalogue and artwork provided by SpinShare · spinsha.re. Browsing sends your search query to SpinShare. Downloads are stored locally; no account or credentials are requested.</p><p className="caption">Close and reopen the game's Custom list after downloading. Existing charts are listed by filename; deleting them preserves their audio and artwork.</p></div> : <>
    <div className="search"><TextField label={mode === 'installed' ? 'Filter installed songs' : 'Search title, artist or charter'} value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && mode !== 'installed' && query.trim()) { selectMode('search'); setSearch(query.trim()); } }}/>{mode !== 'installed' && <DialogButton disabled={!query.trim()} onClick={() => { selectMode('search'); setSearch(query.trim()); }}>Search</DialogButton>}</div>
    <h2>{mode === 'search' ? `Results for “${search}”` : modes.find(([key]) => key === mode)?.[1]}</h2>
    {loading ? <p role="status">Loading songs…</p> : visible.length ? <Focusable className="grid">{visible.map(song => <DialogButton className="song" key={song.key ?? song.id} onClick={() => openSong(song)}><Cover song={song}/><span className="songtext"><span className="title">{song.title}</span><span className="artist">{song.artist}</span><span className="caption">{song.charter}</span><Badges song={song}/>{state?.songs.some(s => s.key === song.key && !!song.key || s.id === song.id && song.id > 0) && <span className="installed">✓ On your Deck</span>}</span></DialogButton>)}</Focusable> : <p>{mode === 'installed' ? 'No installed songs found. Download a chart or select your game folder in Settings.' : 'No songs found. Try another search or browse new releases.'}</p>}
    {mode !== 'installed' && <Focusable className="row pagination"><DialogButton disabled={offset === 0 || loading} onClick={() => setOffset(x => Math.max(0, x - 12))}>Previous</DialogButton><span className="caption">Page {offset / 12 + 1}</span><DialogButton disabled={!more || loading} onClick={() => setOffset(x => x + 12)}>Next</DialogButton></Focusable>}
    </>}
    </>}
  </Focusable>;
}
export default definePlugin(() => {
  routerHook.addRoute(ROUTE, Page, {exact: true});
  return {name: 'SpinShare', titleView: <div>SpinShare</div>, icon: <FaCompactDisc/>, content: <PanelSection title="SPIN RHYTHM XD"><PanelSectionRow><ButtonItem layout="below" onClick={() => { Navigation.Navigate(ROUTE); Navigation.CloseSideMenus(); }}>Open SpinShare</ButtonItem></PanelSectionRow></PanelSection>, onDismount() { routerHook.removeRoute(ROUTE); }};
});
