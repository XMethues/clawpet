import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { api, Experience, Meter, PetInfo, SkinInfo, Voice } from './api';
import './styles/main.css';

const STATE_ROWS: Record<string, number> = { idle: 0, run: 1, wave: 3, jump: 4, failed: 5, waiting: 6, subagent: 7, review: 8, unknown: 8 };
const SKIN_VAR_MAP: Record<string, string> = {
  bgMain: '--bg-main', panel: '--panel', panelSoft: '--panel-soft', accent: '--accent', accentSoft: '--accent-soft',
  textMain: '--text-main', textMuted: '--text-muted', gold: '--gold', border: '--border', track: '--track',
  bubbleBg: '--bubble-bg', bubbleBorder: '--bubble-border', bubbleText: '--bubble-text', qi: '--qi', demon: '--demon', glow: '--glow',
};

function pct(value: number, maximum: number) {
  return Math.max(0, Math.min(100, Math.round(value / Math.max(1, maximum) * 100)));
}
function num(value: number | undefined) { return Math.round(Number(value || 0) * 10) / 10; }

function strategyClass(id?: string) {
  const map: Record<string, string> = {
    balanced: 'ruding', advance: 'chongguan', stabilize: 'cuixin', learn: 'wudao', recover: 'tiaoxi',
  };
  return map[id || ''] || 'default';
}

function applySkin(skin?: SkinInfo) {
  const visual = skin?.visual || {};
  const root = document.documentElement.style;
  Object.entries(SKIN_VAR_MAP).forEach(([key, cssVar]) => {
    const value = visual[key];
    if (value) root.setProperty(cssVar, value);
  });
}

function TopBar({ experience }: { experience?: Experience }) {
  return <div className="topbar">
    <div className="name">{experience?.pet?.displayName || '宠物'}</div>
    <div className="top-actions">
      <span className="skin-chip">{experience?.scene?.name || '成长旅程'}</span>
      <span className={`policy-chip p-${strategyClass(experience?.strategy?.id)}`}>{experience?.strategy?.label || '平衡'}</span>
    </div>
  </div>;
}

function GrowthPanel({ experience }: { experience?: Experience }) {
  const stage = experience?.stage;
  const meters = experience?.meters || [];
  const attributes = experience?.attributes || [];
  const isTrial = stage?.kind === 'tribulation' || stage?.kind === 'gate';
  return <>
    <div className="realm-row">
      <div>
        <div className="realm-title">
          <span className="realm-label">{stage?.label || '成长起点'}</span>
          <span className={`phase-badge ${isTrial ? 'trial' : ''}`}>{stage?.badge || '启程'}</span>
        </div>
        <div className="realm-path">{Number(stage?.index || 0) + 1} / {stage?.total || 1} · 下一阶段：{stage?.next_label || '等待开启'}</div>
      </div>
    </div>
    <div className="bars">
      {meters.slice(0, 2).map(meter => <Bar key={meter.id} meter={meter} />)}
    </div>
    <div className="stats">
      {attributes.slice(0, 4).map(attribute => <Stat key={attribute.id} meter={attribute} />)}
    </div>
    {stage?.hint ? <div className={stage.ready ? 'hint ready' : 'hint'}>{stage.hint}</div> : null}
  </>;
}

function Bar({ meter }: { meter: Meter }) {
  const maximum = Number(meter.max || 1);
  return <div className="barbox">
    <div className="barhead"><span>{meter.label}</span><span>{num(meter.value)} / {num(maximum)}</span></div>
    <div className="track"><div className={`fill ${meter.tone || meter.id}`} style={{ width: `${pct(meter.value, maximum)}%` }} /></div>
  </div>;
}
function Stat({ meter }: { meter: Meter }) { return <div className="stat"><b>{meter.label}</b><span>{num(meter.value)}</span></div>; }

function SpeechBubble({ voice }: { voice?: Voice }) {
  const text = voice?.text || '我在这里。';
  return <div className={`bubble mood-${voice?.mood || 'idle'}`}><b>{voice?.speaker || '宠物'}</b><span>{text}</span></div>;
}

function PetStage({ pet, state }: { pet?: PetInfo; state: string }) {
  const [frame, setFrame] = useState(0);
  const meta = useMemo(() => {
    const rows = pet?.rows || 9;
    const row = rows >= 9 ? (STATE_ROWS[state] ?? 0) : 0;
    const frames = Math.max(1, pet?.frames?.[state] || pet?.frames?.idle || 6);
    return { row, frames, cw: pet?.cellWidth || 192, ch: pet?.cellHeight || 208, url: pet?.spriteUrl || '/assets/pets/yinyue-2.png', width: pet?.width || 1536, height: pet?.height || 1872 };
  }, [pet, state]);
  useEffect(() => {
    setFrame(0);
    const ms = Math.max(90, Math.round(1100 / meta.frames));
    const id = window.setInterval(() => setFrame(value => (value + 1) % meta.frames), ms);
    return () => window.clearInterval(id);
  }, [meta.frames, state, pet?.slug]);
  return <div className="middle"><div className="pet-area"><div className="frame" style={{ width: meta.cw, height: meta.ch }}><div className="sprite" style={{
    width: meta.cw, height: meta.ch,
    backgroundImage: `url(${meta.url})`,
    backgroundSize: `${meta.width}px ${meta.height}px`,
    backgroundPosition: `-${frame * meta.cw}px -${meta.row * meta.ch}px`,
  }} /></div></div></div>;
}

function Chronicle({ experience }: { experience?: Experience }) {
  const entries = (experience?.chronicle?.entries || []).slice(-5).reverse();
  return <div className="logbox">
    <div className="log-title"><span>{experience?.chronicle?.title || '旅程纪事'}</span><span>{experience?.stage?.ready ? '可推进' : ''}</span></div>
    <ul>{entries.length ? entries.map((entry, index) => <li key={`${entry.ts}-${index}`}>{entry.text}</li>) : <li>等待新的成长事件……</li>}</ul>
  </div>;
}

function App() {
  const [experience, setExperience] = useState<Experience>();

  useEffect(() => { applySkin(experience?.skin); }, [experience?.skin]);

  useEffect(() => {
    const refresh = () => api.presentation().then(setExperience).catch(() => {});
    refresh();
    const interval = window.setInterval(refresh, 1000);
    return () => window.clearInterval(interval);
  }, []);

  const state = experience?.activity?.state || 'idle';
  return <div className="shell" data-scene={experience?.scene?.id || 'xianxia'} data-skin={experience?.skin?.id || 'qingming'}>
    <TopBar experience={experience} />
    <GrowthPanel experience={experience} />
    <div className="bubble-wrap"><SpeechBubble voice={experience?.voice} /></div>
    <PetStage pet={experience?.pet} state={state} />
    <Chronicle experience={experience} />
  </div>;
}

createRoot(document.getElementById('root')!).render(<App />);
