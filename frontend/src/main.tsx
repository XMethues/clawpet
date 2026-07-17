import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { api, AgentState, Cultivation, PetInfo, SkinInfo, Voice } from './api';
import './styles/main.css';

const STATE_ROWS: Record<string, number> = { idle: 0, run: 1, wave: 3, jump: 4, failed: 5, waiting: 6, subagent: 7, review: 8, unknown: 8 };
const SKIN_VAR_MAP: Record<string, string> = {
  bgMain: '--bg-main', panel: '--panel', panelSoft: '--panel-soft', accent: '--accent', accentSoft: '--accent-soft',
  textMain: '--text-main', textMuted: '--text-muted', gold: '--gold', border: '--border', track: '--track',
  bubbleBg: '--bubble-bg', bubbleBorder: '--bubble-border', bubbleText: '--bubble-text', qi: '--qi', demon: '--demon', glow: '--glow',
};

function pct(v: unknown, max: unknown) {
  const n = Number(v || 0), m = Number(max || 1);
  return Math.max(0, Math.min(100, Math.round(n / Math.max(1, m) * 100)));
}
function num(v: unknown) { return Math.round(Number(v || 0) * 10) / 10; }

function policyClass(name?: string) {
  const map: Record<string, string> = { '入定': 'ruding', '冲关': 'chongguan', '淬心': 'cuixin', '悟道': 'wudao', '调息': 'tiaoxi' };
  return map[name || ''] || 'default';
}

function applySkin(skin?: SkinInfo) {
  const visual = skin?.visual || {};
  const root = document.documentElement.style;
  Object.entries(SKIN_VAR_MAP).forEach(([key, cssVar]) => {
    const value = visual[key];
    if (value) root.setProperty(cssVar, value);
  });
}

function TopBar({ pet, policy, skin }: { pet?: PetInfo; policy?: Cultivation['policy']; skin?: SkinInfo }) {
  const pname = policy?.label || policy?.name || '入定';
  return <div className="topbar">
    <div className="name">{pet?.displayName || '宠物'}</div>
    <div className="top-actions">
      <span className="skin-chip">{skin?.name || '青冥道场'}</span>
      <span className={`policy-chip p-${policyClass(policy?.name)}`}>{pname}</span>
    </div>
  </div>;
}

function RealmPanel({ cultivation }: { cultivation?: Cultivation }) {
  const r = cultivation?.realm;
  const next = cultivation?.progress?.next_breakthrough;
  const pathIndex = Number(r?.path_index ?? 0) + 1;
  const pathTotal = Number(r?.path_total ?? 28);
  const kind = String(next?.type || '');
  const isTrial = kind === 'tribulation' || String(r?.label || '').includes('试炼');
  const isHuashen = String(r?.label || '').includes('化神');
  const badge = isTrial ? '试炼' : isHuashen ? '化神' : String(r?.phase || r?.label || '').slice(0, 4);
  return <>
    <div className="realm-row">
      <div>
        <div className="realm-title"><span className="realm-label">{r?.label || '炼气1层'}</span><span className={`phase-badge ${isTrial ? 'trial' : isHuashen ? 'huashen' : ''}`}>{badge}</span></div>
        <div className="realm-path">{pathIndex} / {pathTotal} · 下境：{next?.to || '炼气2层'}</div>
      </div>
    </div>
    <div className="bars">
      <Bar label="灵气" value={num(cultivation?.stats?.qi)} max={num(cultivation?.stats?.max_qi || 30)} kind="qi" />
      <Bar label="心魔" value={num(cultivation?.stats?.heart_demon)} max={100} kind="demon" />
    </div>
    <div className="stats">
      <Stat label="道心" value={num(cultivation?.stats?.dao_heart)} />
      <Stat label="悟性" value={num(cultivation?.stats?.comprehension)} />
      <Stat label="疲劳" value={num(cultivation?.stats?.fatigue)} />
      <Stat label="气运" value={num(cultivation?.stats?.fate)} />
    </div>
    {r?.breakthrough_hint ? <div className={r.breakthrough_ready ? 'hint ready' : 'hint'}>{r.breakthrough_hint}</div> : null}
  </>;
}
function Bar({ label, value, max, kind }: { label: string; value: number; max: number; kind: string }) {
  return <div className="barbox"><div className="barhead"><span>{label}</span><span>{value} / {max}</span></div><div className="track"><div className={`fill ${kind}`} style={{ width: `${pct(value, max)}%` }} /></div></div>;
}
function Stat({ label, value }: { label: string; value: number }) { return <div className="stat"><b>{label}</b><span>{value}</span></div>; }

function SpeechBubble({ voice }: { voice?: Voice }) {
  const text = voice?.text || '我在。灵息很稳。';
  return <div className={`bubble mood-${voice?.mood || 'idle'}`}><b>{voice?.speaker || '宠物'}</b><span>{text}</span></div>;
}

function PetStage({ pet, state }: { pet?: PetInfo; state: string }) {
  const [frame, setFrame] = useState(0);
  const meta = useMemo(() => {
    const rows = pet?.rows || 9;
    const row = rows >= 9 ? (STATE_ROWS[state] ?? 0) : 0;
    const frames = Math.max(1, pet?.frames?.[state] || pet?.frames?.idle || 6);
    return { row, frames, cw: pet?.cellWidth || 192, ch: pet?.cellHeight || 208, url: pet?.spriteUrl || '/api/v1/pets/yinyue-2/sprite.png', width: pet?.width || 1536, height: pet?.height || 1872 };
  }, [pet, state]);
  useEffect(() => {
    setFrame(0);
    const ms = Math.max(90, Math.round(1100 / meta.frames));
    const id = window.setInterval(() => setFrame(f => (f + 1) % meta.frames), ms);
    return () => window.clearInterval(id);
  }, [meta.frames, state, pet?.slug]);
  return <div className="middle"><div className="pet-area"><div className="frame" style={{ width: meta.cw, height: meta.ch }}><div className="sprite" style={{
    width: meta.cw, height: meta.ch,
    backgroundImage: `url(${meta.url})`,
    backgroundSize: `${meta.width}px ${meta.height}px`,
    backgroundPosition: `-${frame * meta.cw}px -${meta.row * meta.ch}px`,
  }} /></div></div></div>;
}

function EventLog({ cultivation }: { cultivation?: Cultivation }) {
  const logs = (cultivation?.event_log || []).slice(-5).reverse();
  return <div className="logbox"><div className="log-title"><span>道场纪事</span><span>{cultivation?.realm?.breakthrough_ready ? '可突破' : ''}</span></div><ul>{logs.length ? logs.map((l, i) => <li key={`${l.ts}-${i}`}>{l.text}</li>) : <li>等待道场事件……</li>}</ul></div>;
}

function App() {
  const [agentState, setAgentState] = useState<AgentState>({ state: 'idle' });
  const [cultivation, setCultivation] = useState<Cultivation>();
  const [voice, setVoice] = useState<Voice>();
  const [pet, setPet] = useState<PetInfo>();
  const [skin, setSkin] = useState<SkinInfo>();

  useEffect(() => { applySkin(skin); }, [skin]);

  useEffect(() => {
    api.currentPet().then(r => setPet(r.pet)).catch(() => {});
    api.currentSkin().then(r => setSkin(r.skin)).catch(() => {});
    const s = window.setInterval(() => api.state().then(setAgentState).catch(() => {}), 1000);
    const c = window.setInterval(() => api.cultivation().then(data => { setCultivation(data); if (data.voice) setVoice(data.voice); }).catch(() => {}), 2000);
    const p = window.setInterval(() => api.currentPet().then(r => setPet(r.pet)).catch(() => {}), 2000);
    const v = window.setInterval(() => api.voice().then(setVoice).catch(() => {}), 6000);
    const sk = window.setInterval(() => api.currentSkin().then(r => setSkin(r.skin)).catch(() => {}), 8000);
    api.state().then(setAgentState).catch(() => {});
    api.cultivation().then(data => { setCultivation(data); if (data.voice) setVoice(data.voice); }).catch(() => {});
    api.voice().then(setVoice).catch(() => {});
    return () => { window.clearInterval(s); window.clearInterval(c); window.clearInterval(p); window.clearInterval(v); window.clearInterval(sk); };
  }, []);

  const state = agentState.state || 'idle';
  return <div className="shell" data-skin={skin?.id || 'qingming'}>
    <TopBar pet={pet} policy={cultivation?.policy} skin={skin} />
    <RealmPanel cultivation={cultivation} />
    <div className="bubble-wrap"><SpeechBubble voice={voice || cultivation?.voice} /></div>
    <PetStage pet={pet} state={state} />
    <EventLog cultivation={cultivation} />
  </div>;
}

createRoot(document.getElementById('root')!).render(<App />);
