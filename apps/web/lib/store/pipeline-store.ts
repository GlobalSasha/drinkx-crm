import { create } from "zustand";

interface PipelineFilters {
  segments: string[];
  cities: string[];
  q: string;
}

// Sprint 2.3 G2: selectedPipelineId persistence keys are namespaced
// per workspace so a user belonging to two workspaces never sees a
// stale selection bleed across the boundary. Documented as risk #2 in
// 04_NEXT_SPRINT.md.
const STORAGE_PREFIX = "drinkx:pipeline:";

function storageKey(workspaceId: string): string {
  return `${STORAGE_PREFIX}${workspaceId}`;
}

function readSelectedFromStorage(workspaceId: string): string | null {
  if (typeof window === "undefined") return null; // SSR safety
  try {
    return window.localStorage.getItem(storageKey(workspaceId));
  } catch {
    // Private-mode Safari throws on getItem — treat as «no preference».
    return null;
  }
}

function writeSelectedToStorage(
  workspaceId: string,
  pipelineId: string | null,
): void {
  if (typeof window === "undefined") return;
  try {
    if (pipelineId === null) {
      window.localStorage.removeItem(storageKey(workspaceId));
    } else {
      window.localStorage.setItem(storageKey(workspaceId), pipelineId);
    }
  } catch {
    // Quota / private mode — selection is in-memory only this session.
  }
}

interface PipelineStore {
  // Filters
  filters: PipelineFilters;
  setSegments: (segments: string[]) => void;
  setCities: (cities: string[]) => void;
  setQ: (q: string) => void;

  // Pipeline switcher (Sprint 2.3 G2). `null` means «not yet
  // resolved» — the /pipeline page falls back to the workspace
  // default until the user picks something.
  selectedPipelineId: string | null;
  /** Set + persist to `drinkx:pipeline:{workspaceId}` localStorage. */
  setSelectedPipeline: (workspaceId: string, pipelineId: string) => void;
  /** Hydrate the store from localStorage on first mount. The caller
   *  passes the available pipeline IDs so we can fall back to the
   *  default when the persisted value points at a deleted pipeline. */
  hydrateSelectedPipeline: (
    workspaceId: string,
    availablePipelineIds: string[],
    defaultPipelineId: string | null,
  ) => void;

  // Modals
  sprintModalOpen: boolean;
  openSprintModal: () => void;
  closeSprintModal: () => void;

  createLeadModalOpen: boolean;
  openCreateLeadModal: () => void;
  closeCreateLeadModal: () => void;

  importWizardOpen: boolean;
  openImportWizard: () => void;
  closeImportWizard: () => void;
}

export const usePipelineStore = create<PipelineStore>((set, get) => ({
  filters: { segments: [], cities: [], q: "" },
  setSegments: (segments) =>
    set((s) => ({ filters: { ...s.filters, segments } })),
  setCities: (cities) =>
    set((s) => ({ filters: { ...s.filters, cities } })),
  setQ: (q) => set((s) => ({ filters: { ...s.filters, q } })),

  selectedPipelineId: null,
  setSelectedPipeline: (workspaceId, pipelineId) => {
    writeSelectedToStorage(workspaceId, pipelineId);
    set({ selectedPipelineId: pipelineId });
  },
  hydrateSelectedPipeline: (
    workspaceId,
    availablePipelineIds,
    defaultPipelineId,
  ) => {
    const persisted = readSelectedFromStorage(workspaceId);
    // If the persisted value is still in the workspace's pipeline
    // list, use it. Otherwise fall back to the workspace default —
    // covers the case where the manager deleted the pipeline they
    // had selected.
    let resolved: string | null = null;
    if (persisted && availablePipelineIds.includes(persisted)) {
      resolved = persisted;
    } else if (
      defaultPipelineId &&
      availablePipelineIds.includes(defaultPipelineId)
    ) {
      resolved = defaultPipelineId;
    } else if (availablePipelineIds.length > 0) {
      resolved = availablePipelineIds[0];
    }
    if (resolved !== get().selectedPipelineId) {
      set({ selectedPipelineId: resolved });
    }
  },

  sprintModalOpen: false,
  openSprintModal: () => set({ sprintModalOpen: true }),
  closeSprintModal: () => set({ sprintModalOpen: false }),

  createLeadModalOpen: false,
  openCreateLeadModal: () => set({ createLeadModalOpen: true }),
  closeCreateLeadModal: () => set({ createLeadModalOpen: false }),

  importWizardOpen: false,
  openImportWizard: () => set({ importWizardOpen: true }),
  closeImportWizard: () => set({ importWizardOpen: false }),
}));
