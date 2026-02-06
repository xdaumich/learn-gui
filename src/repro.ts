// Action Schema and Repro Helpers

export type Action =
  | { type: 'reset' }
  | { type: 'reset_all' }
  | { type: 'inc'; by?: number }
  | { type: 'add_item'; text: string }
  | { type: 'set_slider'; value: number }
  | { type: 'assert'; name: string; equals: any };

export interface AppState {
  count: number;
  items: string[];
  slider: number;
}

export interface ReproStep {
  action: Action;
  timestamp: number;
}

export interface ReproData {
  steps: ReproStep[];
  version: string;
}

const initialState: AppState = {
  count: 0,
  items: [],
  slider: 50,
};

export function applyAction(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'reset':
      return { ...state, count: 0 };
    case 'reset_all':
      return { ...initialState };
    case 'inc':
      return { ...state, count: state.count + (action.by ?? 1) };
    case 'add_item':
      return { ...state, items: [...state.items, action.text] };
    case 'set_slider':
      return { ...state, slider: Math.max(0, Math.min(100, action.value)) };
    case 'assert':
      // Assertions don't modify state, but can be checked during replay
      return state;
    default:
      return state;
  }
}

export function downloadJson(data: ReproData, filename: string = 'repro.json'): void {
  const json = JSON.stringify(data, null, 2);
  const blob = new Blob([json], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function parseReproJson(json: string): ReproData {
  const data = JSON.parse(json);
  if (!data.steps || !Array.isArray(data.steps)) {
    throw new Error('Invalid repro.json: missing steps array');
  }
  return data;
}

