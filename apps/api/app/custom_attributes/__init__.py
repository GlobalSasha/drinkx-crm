"""Custom Attributes domain — Sprint 2.4 G3.

Per-workspace user-defined fields on Lead. EAV-shaped:
  - `custom_attribute_definitions` — schema (key, label, kind, options).
  - `lead_custom_values` — per-lead value, polymorphic by kind into
    one of value_text / value_number / value_date.

G3 ships the Settings-side CRUD only (admin/head edit definitions).
Rendering the values on LeadCard / pipeline filters / segments is a
2.4+ polish carryover documented in `docs/brain/04_NEXT_SPRINT.md`.
"""
