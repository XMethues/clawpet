export type Voice = {
  speaker: string;
  mood: string;
  text: string;
  ts: number;
  event: string;
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

export type SceneInfo = {
  id: string;
  name: string;
  description?: string;
  default_skin_id: string;
  skin_ids: string[];
  active?: boolean;
};

export type Meter = {
  id: string;
  label: string;
  value: number;
  max?: number;
  tone?: string;
};

export type Experience = {
  schema_version: 1;
  scene: SceneInfo;
  pet: PetInfo;
  activity: {
    state: string;
    reason?: string;
    ts?: number;
    label?: string;
    in_flight?: Record<string, number>;
    capability?: { id: string; label: string } | null;
  };
  stage: {
    id: string;
    index: number;
    total: number;
    label: string;
    badge: string;
    kind: 'minor' | 'major' | 'gate' | 'trial';
    next_label: string;
    ready: boolean;
    hint?: string;
  };
  meters: Meter[];
  attributes: Meter[];
  strategy: {
    id: string;
    label: string;
    choices: Array<{ id: string; label: string }>;
  };
  voice: Voice;
  chronicle: {
    title: string;
    entries: Array<{ ts: number; kind: string; text: string }>;
  };
  skin: SkinInfo;
};

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, { cache: 'no-store', ...init });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return await res.json() as T;
}

export const api = {
  presentation: () => json<Experience>('/presentation'),
};
