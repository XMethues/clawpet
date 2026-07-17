export type AgentState = { state: string; reason?: string; ts?: number };
export type Voice = { speaker: string; mood: string; text: string; ts: number; event: string };
export type Cultivation = {
  realm: {
    key?: string;
    label: string;
    phase?: string;
    path_index?: number;
    path_total?: number;
    breakthrough_ready?: boolean;
    breakthrough_hint?: string;
  };
  stats: Record<string, number>;
  state?: { action?: string; current_event?: string; current_tool?: string };
  policy?: {
    name: string;
    label?: string;
    set_at?: number;
    source?: string;
    day?: string;
    daily_switches?: number;
    available?: string[];
  };
  dormancy?: { idle_days?: number; phase?: string; label?: string; last_applied_stage?: number };
  voice?: Voice;
  event_log?: Array<{ ts: number; type: string; text: string }>;
  progress?: {
    next_breakthrough?: {
      to?: string;
      type?: string;
      qi_required?: number;
      heart_demon_max?: number;
      fatigue_max?: number;
      dao_heart_min?: number;
      comprehension_min?: number;
    };
  };
};
export type PetInfo = {
  slug: string;
  displayName: string;
  description?: string;
  source: string;
  assetUrl?: string;
  assetKind: string;
  cached: boolean;
  spriteUrl?: string;
  width?: number;
  height?: number;
  cellWidth: number;
  cellHeight: number;
  rows?: number;
  columns?: number;
  frames?: Record<string, number>;
};
export type SkinInfo = {
  id: string;
  name: string;
  source: string;
  description?: string;
  mood?: string[];
  suitable_policies?: string[];
  suitable_states?: string[];
  rules_effect: 'none';
  visual?: Record<string, string>;
  unlocked?: boolean;
  active?: boolean;
};

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, { cache: 'no-store', ...init });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return await res.json() as T;
}

export const api = {
  state: () => json<AgentState>('/state'),
  cultivation: () => json<Cultivation>('/cultivation'),
  voice: () => json<Voice>('/voice'),
  currentPet: () => json<{ pet: PetInfo }>('/api/v1/pets/current'),
  currentSkin: () => json<{ skin: SkinInfo }>('/api/v1/skins/current'),
};
