"""Pydantic DTOs for leads endpoints."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.leads.models import ASSIGNMENT_STATUSES
from app.leads.models import (  # noqa: F401 — imported for OpenAPI clarity
    AssignmentStatus,
    CommercialModel,
    DealType,
    Priority,
)


class LeadBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company_name: str
    segment: str | None = None
    city: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    inn: str | None = None
    source: str | None = None
    # «Откуда появился лид» — FK into the lead_sources dictionary (Sprint CEO G1/G2).
    # The legacy free-text `source` above stays for form-slug parsing + backfill.
    source_id: UUID | None = None
    tags_json: list[str] = Field(default_factory=list)
    deal_type: str | None = None
    priority: str | None = None
    score: int = 0
    blocker: str | None = None
    next_step: str | None = None
    next_action_at: datetime | None = None


class LeadCreate(LeadBase):
    """Used by managers; assignment_status forced to 'assigned' to current user."""

    pipeline_id: UUID | None = None
    stage_id: UUID | None = None
    # Sprint 3.3 — optional company link. When set, the service copies
    # `companies.name` into `leads.company_name` so the snapshot stays
    # correct from creation onward.
    company_id: UUID | None = None


class LeadUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company_name: str | None = None
    segment: str | None = None
    city: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    inn: str | None = None
    source: str | None = None
    source_id: UUID | None = None
    tags_json: list[str] | None = None
    deal_type: str | None = None
    priority: str | None = None
    score: int | None = None
    blocker: str | None = None
    next_step: str | None = None
    next_action_at: datetime | None = None
    pipeline_id: UUID | None = None
    stage_id: UUID | None = None
    # Manager-editable AI brief narrative. Not a column — merged into
    # ai_data["company_profile"] by the service so AI signals survive.
    company_profile: str | None = None
    # Sprint 3.7 G4 — auto-created lead dismissal
    assignment_status: str | None = None

    @field_validator("assignment_status")
    @classmethod
    def _known_assignment_status(cls, value: str | None) -> str | None:
        """Статус — это инвариант, по которому вся система делит карточки на
        пул и закреплённые (`app/team`, `app/company`, `app/daily_plan`…).
        Раньше PATCH писал в колонку любую присланную строку, и такая
        карточка молча выпадала из обоих представлений."""
        if value is not None and value not in ASSIGNMENT_STATUSES:
            raise ValueError(
                "Недопустимое значение assignment_status: "
                f"{value!r}. Допустимы: {', '.join(ASSIGNMENT_STATUSES)}"
            )
        return value


class LeadOut(LeadBase):
    id: UUID
    workspace_id: UUID
    pipeline_id: UUID | None
    stage_id: UUID | None
    fit_score: Decimal | None = None
    assignment_status: str
    assigned_to: UUID | None
    assigned_at: datetime | None
    transferred_from: UUID | None
    transferred_at: datetime | None
    is_rotting_stage: bool
    is_rotting_next_step: bool
    last_activity_at: datetime | None
    archived_at: datetime | None
    won_at: datetime | None
    lost_at: datetime | None
    lost_reason: str | None
    # Soft-delete (Trash / restore, plan 009). Present so a restored /
    # trashed lead's card can render its Trash status.
    deleted_at: datetime | None = None
    ai_data: dict | None = None
    # Primary contact («основной ЛПР») — id from leads.primary_contact_id,
    # name resolved via LEFT JOIN in the list-query repository.
    primary_contact_id: UUID | None = None
    primary_contact_name: str | None = None
    # Sprint 3.6 G1 — landing-form attribution. Resolved at the read
    # path, never stored. `source_form_id` is the FK target so the
    # frontend chip can deep-link to `/leads-pool?form_id=<id>`.
    source_form_id: UUID | None = None
    source_form_name: str | None = None
    latest_utm: dict | None = None
    # Open work counters. Split is reminder_kind-based per Sprint pre-flight:
    #   open_tasks_count     = status != 'done' AND reminder_kind = 'manager'
    #   open_followups_count = status != 'done' AND reminder_kind IN ('auto_email', 'ai_hint')
    open_followups_count: int = 0
    open_tasks_count: int = 0
    # Deal-value strip (Lead Card v2, migration 0030)
    commercial_model: CommercialModel | None = None
    deal_amount: Decimal | None = None
    deal_quantity: int | None = None
    deal_equipment: str | None = None
    # Russian label derived from `priority` letter via
    # `app.leads.scoring.priority_label`. Frontend reads this instead
    # of the raw letter so the LeadCard never has to translate.
    priority_label: str | None = None
    # Sprint 3.7 G1 — set TRUE on AI auto-created leads, FALSE everywhere
    # else (form submissions, manual creates, CSV imports, claim-from-pool).
    needs_review: bool = False
    # Days the lead has spent on its CURRENT stage. Computed at the
    # single-lead read path from the open lead_stage_history row
    # (fallback: lead.created_at). Other LeadOut-returning endpoints
    # leave it None (default).
    current_stage_days: int | None = None
    created_at: datetime
    updated_at: datetime


class LeadListItemOut(LeadBase):
    """Slim Lead DTO for list endpoints — drops `ai_data` (AI Brief
    output, can be 50KB per lead) and `agent_state` (Lead AI Agent
    memory). Pipeline + Pool views render company name / score /
    fit_score / priority — none of those need the AI payload, so we
    skip it both on the SQL side (see `defer()` in repositories) and
    in the response model so 200-lead lists stay well under 1MB.
    Fetch the full `LeadOut` via `GET /leads/{id}` when opening a
    card."""

    id: UUID
    workspace_id: UUID
    pipeline_id: UUID | None
    stage_id: UUID | None
    fit_score: Decimal | None = None
    assignment_status: str
    assigned_to: UUID | None
    assigned_at: datetime | None
    transferred_from: UUID | None
    transferred_at: datetime | None
    is_rotting_stage: bool
    is_rotting_next_step: bool
    last_activity_at: datetime | None
    archived_at: datetime | None
    won_at: datetime | None
    lost_at: datetime | None
    lost_reason: str | None
    # Soft-delete (Trash / restore, plan 009). GET /leads/trash relies on
    # this to show "deleted N days ago" on each row.
    deleted_at: datetime | None = None
    primary_contact_id: UUID | None = None
    primary_contact_name: str | None = None
    # Sprint 3.6 G1 — landing-form attribution (same as LeadOut).
    source_form_id: UUID | None = None
    source_form_name: str | None = None
    latest_utm: dict | None = None
    open_followups_count: int = 0
    open_tasks_count: int = 0
    commercial_model: CommercialModel | None = None
    deal_amount: Decimal | None = None
    deal_quantity: int | None = None
    deal_equipment: str | None = None
    priority_label: str | None = None
    # Sprint 3.7 G1 — set TRUE on AI auto-created leads, FALSE everywhere
    # else (form submissions, manual creates, CSV imports, claim-from-pool).
    needs_review: bool = False
    created_at: datetime
    updated_at: datetime


class LeadListOut(BaseModel):
    items: list[LeadListItemOut]
    total: int
    page: int
    page_size: int


class FacetValueOut(BaseModel):
    """Одно значение фасета и его размер в серверной выборке."""

    value: str
    count: int


class PoolFacetsOut(BaseModel):
    """Значения фильтров и их размеры по всей базе лидов (аудит G6).

    Считаются по области пула (форма и needs_review), а не по уже
    выбранным фасетам, — так число рядом с «Кофейни и кафе» означает
    «столько их в пуле», как и до G6. И, в отличие от прежнего варианта,
    считаются на сервере: раньше числа описывали первые 500 загруженных
    строк.
    """

    cities: list[FacetValueOut] = Field(default_factory=list)
    segments: list[FacetValueOut] = Field(default_factory=list)
    priorities: list[FacetValueOut] = Field(default_factory=list)
    tiers: list[FacetValueOut] = Field(default_factory=list)
    deal_types: list[FacetValueOut] = Field(default_factory=list)
    sources: list[FacetValueOut] = Field(default_factory=list)
    tags: list[FacetValueOut] = Field(default_factory=list)
    total: int = 0


class SprintCreateIn(BaseModel):
    cities: list[str] = Field(default_factory=list)
    segment: str | None = None
    limit: int | None = None  # if None, falls back to workspace.sprint_capacity_per_week


class SprintCreateOut(BaseModel):
    claimed_count: int
    requested: int
    items: list[LeadOut]


class LeadAssignIn(BaseModel):
    """Body for POST /leads/assign — руководитель выдаёт лиды менеджеру.

    Режим задаётся явно полем `mode`, а не пустотой `lead_ids`:
      - mode="ids": выдать именно карточки из `lead_ids` (непустой).
        При `only_pool=False` можно перехватить и уже занятую кем-то
        карточку — прежний владелец пишется в `transferred_from`, как
        при передаче. `only_pool=True` (по умолчанию) такие карточки
        пропускает.
      - mode="filter": взять до `limit` карточек ИЗ ПУЛА по фильтру
        (нужен хотя бы один из cities/segment/fit_min/limit), тем же
        порядком, что и /leads/pool. Занятые чужие карточки в этом
        режиме не трогаются.
    """

    to_user_id: UUID
    mode: Literal["ids", "filter"]
    only_pool: bool = True
    lead_ids: list[UUID] = Field(default_factory=list, max_length=500)
    # --- filter mode only -------------------------------------------------
    # Тот же набор, что принимает GET /leads/pool. До G6 здесь было три
    # поля из тринадцати, поэтому действие «Выдать по фильтру» работало по
    # выборке, которой человек на экране не видел.
    cities: list[str] = Field(default_factory=list)
    segments: list[str] = Field(default_factory=list)
    priorities: list[str] = Field(default_factory=list)
    tiers: list[str] = Field(default_factory=list)
    deal_types: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    fit_min: float | None = None
    has_email: bool = False
    has_phone: bool = False
    form_id: UUID | None = None
    needs_review: bool | None = None
    q: str | None = Field(None, max_length=200)
    limit: int | None = Field(None, ge=1, le=500)
    comment: str | None = Field(None, max_length=500)

    def to_selection(self):
        """Каноническое описание выборки — то же, что у списка и экспорта."""
        from app.leads.selection import LeadSelection

        return LeadSelection.from_params(
            cities=self.cities,
            segments=self.segments,
            priorities=self.priorities,
            tiers=self.tiers,
            deal_types=self.deal_types,
            sources=self.sources,
            tags=self.tags,
            fit_min=self.fit_min,
            has_email=self.has_email,
            has_phone=self.has_phone,
            form_id=self.form_id,
            needs_review=self.needs_review,
            q=self.q,
            assignment_status="pool",
        )

    @model_validator(mode="after")
    def _check_mode_matches_payload(self) -> "LeadAssignIn":
        if self.mode == "ids" and not self.lead_ids:
            raise ValueError("mode=ids требует непустой lead_ids")
        if self.mode == "filter":
            selection = self.to_selection()
            has_filter = selection != selection.__class__(assignment_status="pool")
            if not has_filter and self.limit is None:
                raise ValueError("mode=filter требует хотя бы один фильтр или limit")
        return self


class LeadAssignOut(BaseModel):
    """`skipped` — сколько из запрошенных карточек не досталось:
    удалены, не найдены или уже принадлежат этому же менеджеру."""

    assigned_count: int
    requested: int
    skipped: int
    items: list[LeadOut]


class TransferIn(BaseModel):
    to_user_id: UUID
    comment: str | None = None


class MoveStageIn(BaseModel):
    stage_id: UUID
    gate_skipped: bool = False
    skip_reason: str | None = None
    lost_reason: str | None = None  # only used when entering lost stage


class PrimaryContactIn(BaseModel):
    """Body for PATCH /leads/{id}/primary-contact. Pass null to clear."""

    contact_id: UUID | None = None


class DealPatchIn(BaseModel):
    """Body for PATCH /leads/{id}/deal — partial update of the
    deal-value strip. Any subset of the four fields is accepted;
    omitted fields stay unchanged. Pass null to clear a single field."""

    commercial_model: CommercialModel | None = None
    deal_amount: Decimal | None = None
    deal_quantity: int | None = None
    deal_equipment: str | None = None

    # Whether the field was sent at all (vs. left unset). The router
    # walks model_fields_set so a `null` clears the column but a missing
    # key leaves it alone.
    model_config = ConfigDict(extra="forbid")


class ScoreDetailsPatchIn(BaseModel):
    """Body for PATCH /leads/{id}/score-details. The dict is
    whitelisted server-side against the workspace's `scoring_criteria`;
    keys outside the set are silently dropped. Each value must be
    integer 0..criterion.max_value."""

    score_details: dict[str, int] = Field(default_factory=dict)


class ScoreCriterionOut(BaseModel):
    """One row in the score-breakdown response."""

    key: str
    label: str
    weight: int
    max_value: int
    current_value: int
    contribution: float  # value/max_value * weight, useful for the bar


class ScoreBreakdownOut(BaseModel):
    total: int
    max: int
    priority: str | None
    priority_label: str | None
    criteria: list[ScoreCriterionOut]


class StageDurationOut(BaseModel):
    stage_id: UUID
    stage_name: str
    position: int
    days: int | None
    status: str  # "done" | "current" | "pending"


class GateViolationOut(BaseModel):
    """Shape of one violation returned in 409 detail.violations[]."""
    code: str
    message: str
    hard: bool = False


class MoveStageBlockedDetail(BaseModel):
    """Body of the 409 response when a stage transition is blocked by gates."""
    message: str
    violations: list[GateViolationOut]


class MergeLeadsIn(BaseModel):
    """Merge the listed duplicate leads into the path lead (the master)."""
    duplicate_ids: list[UUID] = Field(..., min_length=1)


class StageDwellOut(BaseModel):
    """One row of «где застревают сделки» — dwell stats for one active stage.

    `*_days` are None when no lead has completed the stage yet. `stuck_count`
    is leads currently in the stage past its rot_days (fallback 14d).
    """
    stage_id: UUID
    stage_name: str
    position: int
    completed_count: int
    avg_days: float | None = None
    median_days: float | None = None
    p90_days: float | None = None
    stuck_count: int


class UtmSourceStatOut(BaseModel):
    """One row of «какой канал приносит сделки» — leads grouped by UTM source.

    `source` is the dictionary name, or None for leads with no UTM source
    (direct / unattributed). `won_sum` is the revenue of won deals only.
    """
    source: str | None
    leads: int
    won: int
    won_sum: Decimal          # sale (one-off) revenue — plan 025
    won_rental_mrr: Decimal = Decimal(0)  # rental monthly recurring — plan 025


class ForecastStageBarOut(BaseModel):
    """Один столбец «воронки по сумме» — активный этап и что на нём стоит."""
    stage_id: UUID
    name: str
    total: float
    count: int


class ForecastAtRiskOut(BaseModel):
    """Сделка, стоящая на этапе дольше его `rot_days`."""
    id: UUID
    company_name: str
    amount: float
    overdue_days: int
    stage_name: str


class ForecastOut(BaseModel):
    """Прогноз по всей доступной актору выборке.

    Суммы — JSON-числа, а не строки: страница и так приводит их через
    `Number(...)`, а `Decimal` уехал бы строкой и добавил бы разбор на
    ровном месте. Точности `Numeric(12,2)` double хватает с запасом.
    """
    pipeline_total: float
    weighted_total: float
    at_risk_total: float
    won_recent: float
    stage_bars: list[ForecastStageBarOut]
    at_risk_deals: list[ForecastAtRiskOut]


class LeadPipelineChangeIn(BaseModel):
    """Перенос лида в другую воронку.

    `stage_id` необязателен: если он не указан, лид встаёт на первый этап
    (position == 0) целевой воронки.
    """

    pipeline_id: UUID
    stage_id: UUID | None = None
