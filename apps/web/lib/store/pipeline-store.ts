import { create } from "zustand";
import type { LeadOut } from "@/lib/types";

interface PipelineFilters {
  segment: string | null;
  city: string | null;
  q: string;
}

interface PipelineStore {
  // Filters
  filters: PipelineFilters;
  setSegment: (segment: string | null) => void;
  setCity: (city: string | null) => void;
  setQ: (q: string) => void;

  // Modals
  sprintModalOpen: boolean;
  openSprintModal: () => void;
  closeSprintModal: () => void;

  createLeadModalOpen: boolean;
  openCreateLeadModal: () => void;
  closeCreateLeadModal: () => void;

  // Brief drawer
  selectedLead: LeadOut | null;
  visibleLeads: LeadOut[]; // current ordered leads for arrow key nav
  openDrawer: (lead: LeadOut, visibleLeads: LeadOut[]) => void;
  closeDrawer: () => void;
  navigateDrawer: (dir: -1 | 1) => void;
}

export const usePipelineStore = create<PipelineStore>((set, get) => ({
  filters: { segment: null, city: null, q: "" },
  setSegment: (segment) =>
    set((s) => ({ filters: { ...s.filters, segment } })),
  setCity: (city) => set((s) => ({ filters: { ...s.filters, city } })),
  setQ: (q) => set((s) => ({ filters: { ...s.filters, q } })),

  sprintModalOpen: false,
  openSprintModal: () => set({ sprintModalOpen: true }),
  closeSprintModal: () => set({ sprintModalOpen: false }),

  createLeadModalOpen: false,
  openCreateLeadModal: () => set({ createLeadModalOpen: true }),
  closeCreateLeadModal: () => set({ createLeadModalOpen: false }),

  selectedLead: null,
  visibleLeads: [],
  openDrawer: (lead, visibleLeads) => set({ selectedLead: lead, visibleLeads }),
  closeDrawer: () => set({ selectedLead: null }),
  navigateDrawer: (dir) => {
    const { selectedLead, visibleLeads } = get();
    if (!selectedLead) return;
    const idx = visibleLeads.findIndex((l) => l.id === selectedLead.id);
    const next = visibleLeads[idx + dir];
    if (next) set({ selectedLead: next });
  },
}));
