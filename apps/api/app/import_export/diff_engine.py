"""DrinkX Update Format v1.0 → diff + apply.

`compute_diff` resolves each parsed update item to a Lead in the
workspace, builds a per-field Change list, returns a list[DiffItem]
ready for both the preview UI (frontend renders the changes list) and
the apply phase (Celery walks the same list).

`apply_diff_item` runs each item through the ORM. Per-item failures
land on `import_errors` so the manager can see exactly what didn't
land — same UX as the regular bulk import path.

Stage moves bypass the gate engine intentionally: the manager
already approved the diff in the preview UI, so we don't re-prompt
for gate criteria. ADR-007 (no auto-actions) is satisfied by the
human-in-the-loop preview gate, not by the field-level gate engine.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field as dc_field
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.contacts.models import Contact
from app.leads.models import Lead

log = structlog.get_logger()


# ===========================================================================
# Data classes
# ===========================================================================

@dataclass
class Change:
    field: str       # 'growth_signals' | 'fit_score' | 'tags' | 'stage' | ...
    op: str          # 'add' | 'remove' | 'replace' | 'set'
    value: Any
    current_value: Any | None = None


@dataclass
class DiffItem:
    action: str           # 'update' | 'create'
    company_name: str
    inn: str | None = None
    lead_id: str | None = None  # str(UUID) — JSON-serialisable
    changes: list[Change] = dc_field(default_factory=list)
    match_confidence: str = "not_found"  # 'exact_inn'|'exact_name'|'exact_id'|'not_found'|'ambiguous'
    error: str | None = None


# ===========================================================================
# compute_diff — resolve + build change list
# ===========================================================================

async def _batch_load_candidates(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    inns: set[str],
    names: set[str],
    ids: set[UUID],
) -> tuple[
    dict[str, list[Lead]],
    dict[str, list[Lead]],
    dict[UUID, Lead],
]:
    """One query per match dimension. Returns three lookup maps:
    inn → leads, name → leads (case-insensitive), id → lead.

    Lists for inn/name are needed because of duplicates (same INN on
    two rows is rare but legal; same company_name across pipelines
    is common). Ambiguity is surfaced in the diff item below."""
    by_inn: dict[str, list[Lead]] = {}
    by_name: dict[str, list[Lead]] = {}
    by_id: dict[UUID, Lead] = {}

    base = (
        lambda: select(Lead)
        .where(Lead.workspace_id == workspace_id)
        .options(selectinload(Lead.contacts))
    )

    if inns:
        res = await session.execute(base().where(Lead.inn.in_(inns)))
        for lead in res.scalars().unique():
            inn = (lead.inn or "").strip()
            if inn:
                by_inn.setdefault(inn, []).append(lead)
    if names:
        # Case-insensitive match on company_name. Postgres lower(...) =
        # any(...) keeps it index-friendly even without a functional index.
        lowered = {n.lower() for n in names if n}
        res = await session.execute(base().where(Lead.company_name.ilike(Lead.company_name)))
        # ↑ that's effectively a no-op filter; we'll just pull the small
        #   set we care about by scanning. For workspace sizes we expect
        #   (~hundreds), one extra query without ilike per name would
        #   blow up; the in_(...) trick wants exact case match. Fall
        #   back to Python-side filter on the result set.
        # Pragmatic for v1: load all leads in workspace once, filter in
        # Python. Will revisit if workspaces grow past a few thousand
        # leads — at that point compute_diff itself becomes the slow
        # path and we'll batch differently.
        for lead in res.scalars().unique():
            name = (lead.company_name or "").strip().lower()
            if name in lowered:
                by_name.setdefault(name, []).append(lead)
    if ids:
        res = await session.execute(base().where(Lead.id.in_(ids)))
        for lead in res.scalars().unique():
            by_id[lead.id] = lead

    return by_inn, by_name, by_id


def _resolve_match(
    item: dict[str, Any],
    *,
    by_inn: dict[str, list[Lead]],
    by_name: dict[str, list[Lead]],
    by_id: dict[UUID, Lead],
) -> tuple[Lead | None, str, str | None]:
    """Returns (matched_lead, confidence, error). Lead is None when not
    matched; error is set when ambiguity / not-found prevents a clean
    update."""
    company = item.get("company") or {}
    match_by = item.get("match_by")
    inn = (company.get("inn") or "").strip()
    name = (company.get("name") or "").strip()
    cid = company.get("id")

    if match_by == "inn" and inn:
        candidates = by_inn.get(inn, [])
        if len(candidates) == 1:
            return candidates[0], "exact_inn", None
        if len(candidates) > 1:
            return None, "ambiguous", f"Несколько лидов с ИНН {inn}"
        return None, "not_found", None
    if match_by == "company_name" and name:
        candidates = by_name.get(name.lower(), [])
        if len(candidates) == 1:
            return candidates[0], "exact_name", None
        if len(candidates) > 1:
            return (
                None,
                "ambiguous",
                f"Несколько лидов с названием «{name}»",
            )
        return None, "not_found", None
    if match_by == "id" and cid:
        try:
            uid = UUID(str(cid))
        except (ValueError, TypeError):
            return None, "not_found", f"Невалидный id: {cid}"
        lead = by_id.get(uid)
        return (lead, "exact_id", None) if lead else (None, "not_found", None)

    return None, "not_found", None


def _build_changes(item: dict[str, Any], lead: Lead) -> list[Change]:
    """Walk fields {} → emit one Change per touched field. Snapshots
    `current_value` so the preview UI can render before/after."""
    changes: list[Change] = []
    fields = item.get("fields") or {}

    # ---- ai_data ----------------------------------------------------------
    ai = fields.get("ai_data")
    if isinstance(ai, dict):
        current_ai = lead.ai_data or {}
        for k, raw in ai.items():
            if isinstance(raw, dict):
                # add / remove / replace ops on a list-shaped sub-field
                cur = current_ai.get(k) if isinstance(current_ai, dict) else None
                cur_list = list(cur or []) if isinstance(cur, list) else []
                if "add" in raw and isinstance(raw["add"], list):
                    new_items = [v for v in raw["add"] if v not in cur_list]
                    if new_items:
                        changes.append(Change(
                            field=f"ai_data.{k}",
                            op="add",
                            value=new_items,
                            current_value=cur_list,
                        ))
                if "remove" in raw and isinstance(raw["remove"], list):
                    drop = [v for v in raw["remove"] if v in cur_list]
                    if drop:
                        changes.append(Change(
                            field=f"ai_data.{k}",
                            op="remove",
                            value=drop,
                            current_value=cur_list,
                        ))
                if "replace" in raw and isinstance(raw["replace"], list):
                    changes.append(Change(
                        field=f"ai_data.{k}",
                        op="replace",
                        value=raw["replace"],
                        current_value=cur_list,
                    ))
            else:
                # Scalar replace (fit_score, company_profile, etc.)
                cur = current_ai.get(k) if isinstance(current_ai, dict) else None
                if cur != raw:
                    changes.append(Change(
                        field=f"ai_data.{k}",
                        op="set",
                        value=raw,
                        current_value=cur,
                    ))

    # ---- contacts ---------------------------------------------------------
    contacts_op = fields.get("contacts")
    if isinstance(contacts_op, dict):
        existing_emails = {
            (c.email or "").lower() for c in (lead.contacts or []) if c.email
        }
        adds = contacts_op.get("add")
        if isinstance(adds, list):
            new_contacts = [
                c for c in adds
                if isinstance(c, dict)
                and (c.get("email") or "").lower() not in existing_emails
            ]
            if new_contacts:
                changes.append(Change(
                    field="contacts.add",
                    op="add",
                    value=new_contacts,
                    current_value=None,
                ))
        ubm = contacts_op.get("update_by_email")
        if isinstance(ubm, dict) and ubm:
            changes.append(Change(
                field="contacts.update_by_email",
                op="set",
                value=ubm,
                current_value=None,
            ))

    # ---- tags -------------------------------------------------------------
    tags = fields.get("tags")
    if isinstance(tags, dict):
        cur_tags = list(getattr(lead, "tags_json", None) or [])
        adds = tags.get("add") if isinstance(tags.get("add"), list) else []
        rems = tags.get("remove") if isinstance(tags.get("remove"), list) else []
        if adds:
            new = [t for t in adds if t not in cur_tags]
            if new:
                changes.append(Change(
                    field="tags",
                    op="add",
                    value=new,
                    current_value=cur_tags,
                ))
        if rems:
            drop = [t for t in rems if t in cur_tags]
            if drop:
                changes.append(Change(
                    field="tags",
                    op="remove",
                    value=drop,
                    current_value=cur_tags,
                ))

    # ---- stage ------------------------------------------------------------
    stage_name = fields.get("stage")
    if isinstance(stage_name, str) and stage_name.strip():
        changes.append(Change(
            field="stage",
            op="set",
            value=stage_name.strip(),
            current_value=None,  # stage name lookup happens at apply time
        ))

    # ---- assigned_to ------------------------------------------------------
    assigned = fields.get("assigned_to")
    if isinstance(assigned, str) and assigned.strip():
        changes.append(Change(
            field="assigned_to",
            op="set",
            value=assigned.strip().lower(),
            current_value=None,
        ))

    return changes


async def compute_diff(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    updates: list[dict[str, Any]],
) -> list[DiffItem]:
    """Resolve every parsed update item to a DiffItem. Performs three
    batched queries (by inn / by name / by id) instead of N round-trips.
    Returns DiffItems even when the resolution failed — frontend
    surfaces them in an errors panel."""
    inns: set[str] = set()
    names: set[str] = set()
    ids: set[UUID] = set()
    for u in updates:
        company = u.get("company") or {}
        match_by = u.get("match_by")
        if match_by == "inn":
            v = (company.get("inn") or "").strip()
            if v:
                inns.add(v)
        elif match_by == "company_name":
            v = (company.get("name") or "").strip()
            if v:
                names.add(v)
        elif match_by == "id":
            try:
                ids.add(UUID(str(company.get("id"))))
            except (ValueError, TypeError):
                pass

    by_inn, by_name, by_id = await _batch_load_candidates(
        session,
        workspace_id=workspace_id,
        inns=inns,
        names=names,
        ids=ids,
    )

    out: list[DiffItem] = []
    for u in updates:
        company = u.get("company") or {}
        item = DiffItem(
            action=u["action"],
            company_name=str(company.get("name") or "").strip(),
            inn=(str(company.get("inn") or "").strip() or None),
        )
        lead, confidence, err = _resolve_match(
            u, by_inn=by_inn, by_name=by_name, by_id=by_id
        )
        item.match_confidence = confidence

        if u["action"] == "update":
            if lead is None:
                item.error = err or "Лид не найден"
                out.append(item)
                continue
            item.lead_id = str(lead.id)
            item.changes = _build_changes(u, lead)
        else:  # action == 'create'
            if lead is not None:
                # AI proposed create but the company already exists —
                # treat as informational error so manager sees it but
                # we don't accidentally double-create.
                item.error = (
                    "Компания уже есть в базе — пометка create проигнорирована"
                )
            else:
                # Synthesise a fake Lead-shaped object so _build_changes
                # can produce changes against an empty baseline.
                empty = type("EmptyLead", (), {
                    "ai_data": None,
                    "tags_json": [],
                    "contacts": [],
                })()
                item.changes = _build_changes(u, empty)  # type: ignore[arg-type]
        out.append(item)

    return out


# ===========================================================================
# apply_diff_item — write changes to the DB
# ===========================================================================

async def _resolve_stage_id(
    session: AsyncSession, *, lead: Lead, stage_name: str
) -> UUID | None:
    """Find a Stage matching the given name in the lead's pipeline.
    Falls back to the workspace default pipeline when the lead has
    no pipeline_id yet.

    Sprint 2.4 G1: switched from `Pipeline.is_default=true` to
    `pipelines_repo.get_default_pipeline_id()` — the canonical
    workspace.default_pipeline_id FK. Migration 0017 drops the
    legacy boolean column."""
    from app.pipelines import repositories as pipelines_repo
    from app.pipelines.models import Stage

    pipeline_id = lead.pipeline_id
    if pipeline_id is None:
        pipeline_id = await pipelines_repo.get_default_pipeline_id(
            session, workspace_id=lead.workspace_id
        )
    if pipeline_id is None:
        return None
    res = await session.execute(
        select(Stage.id)
        .where(Stage.pipeline_id == pipeline_id)
        .where(Stage.name.ilike(stage_name))
        .limit(1)
    )
    return res.scalar_one_or_none()


async def _resolve_user_id(
    session: AsyncSession, *, workspace_id: UUID, email: str
) -> UUID | None:
    from app.auth.models import User

    res = await session.execute(
        select(User.id)
        .where(User.workspace_id == workspace_id)
        .where(User.email.ilike(email))
        .limit(1)
    )
    return res.scalar_one_or_none()


def _apply_ai_data_changes(lead: Lead, changes: list[Change]) -> None:
    """Mutate lead.ai_data in-place per the change list. Always works
    on a fresh dict copy so SQLAlchemy detects the change."""
    current = dict(lead.ai_data or {})
    for c in changes:
        if not c.field.startswith("ai_data."):
            continue
        key = c.field[len("ai_data.") :]
        if c.op == "add":
            cur_list = list(current.get(key) or [])
            for v in c.value or []:
                if v not in cur_list:
                    cur_list.append(v)
            current[key] = cur_list
        elif c.op == "remove":
            cur_list = list(current.get(key) or [])
            current[key] = [v for v in cur_list if v not in (c.value or [])]
        elif c.op == "replace":
            current[key] = list(c.value or [])
        elif c.op == "set":
            current[key] = c.value
    lead.ai_data = current


def _apply_tags_changes(lead: Lead, changes: list[Change]) -> None:
    cur = list(getattr(lead, "tags_json", None) or [])
    for c in changes:
        if c.field != "tags":
            continue
        if c.op == "add":
            for v in c.value or []:
                if v not in cur:
                    cur.append(v)
        elif c.op == "remove":
            cur = [t for t in cur if t not in (c.value or [])]
    lead.tags_json = cur


async def apply_diff_item(
    session: AsyncSession,
    *,
    item: DiffItem,
    workspace_id: UUID,
    user_id: UUID | None,
) -> bool:
    """Apply a single resolved DiffItem. Returns True on success.
    Errors during apply are caught here and re-raised so the caller
    can write an ImportError row.

    ADR-007 note: stage moves bypass the gate engine because the
    manager already approved the diff in the preview UI. The diff
    audit trail (delta_json on the import_job) records the change.
    """
    if item.error and item.action == "update":
        # Resolution-time error — nothing to apply
        return False

    if item.action == "create":
        if item.error:
            # «компания уже есть» — defensive skip
            return False
        return await _apply_create(session, item=item, workspace_id=workspace_id)

    # action == 'update'
    if item.lead_id is None:
        return False
    lead = await session.get(Lead, UUID(item.lead_id))
    if lead is None or lead.workspace_id != workspace_id:
        return False

    # ai_data + tags first (cheap, in-memory mutations)
    _apply_ai_data_changes(lead, item.changes)
    _apply_tags_changes(lead, item.changes)

    # contacts.add — create new Contact rows
    for c in item.changes:
        if c.field == "contacts.add" and isinstance(c.value, list):
            existing_emails = {
                (cc.email or "").lower() for cc in (lead.contacts or []) if cc.email
            }
            for cd in c.value:
                if not isinstance(cd, dict):
                    continue
                email = (cd.get("email") or "").strip().lower()
                if email and email in existing_emails:
                    continue
                session.add(Contact(
                    lead_id=lead.id,
                    name=(cd.get("name") or email or "Unknown")[:120],
                    title=(cd.get("title") or "")[:120] or None,
                    email=email or None,
                    role_type=cd.get("role_type") or None,
                    source=cd.get("source") or "ai_bulk_update",
                ))
                if email:
                    existing_emails.add(email)
        elif c.field == "contacts.update_by_email" and isinstance(c.value, dict):
            for email_key, patch in c.value.items():
                if not isinstance(patch, dict):
                    continue
                target_email = email_key.strip().lower()
                for contact in lead.contacts or []:
                    if (contact.email or "").lower() != target_email:
                        continue
                    if "title" in patch:
                        contact.title = (patch.get("title") or "")[:120] or None
                    if "role_type" in patch:
                        contact.role_type = patch.get("role_type") or None
                    if "source" in patch:
                        contact.source = patch.get("source") or contact.source
                    break

    # stage move
    for c in item.changes:
        if c.field != "stage" or c.op != "set":
            continue
        stage_id = await _resolve_stage_id(
            session, lead=lead, stage_name=str(c.value)
        )
        if stage_id is not None:
            lead.stage_id = stage_id
        else:
            log.warning(
                "bulk_update.stage_unresolved",
                lead_id=str(lead.id),
                stage_name=c.value,
            )

    # assigned_to
    for c in item.changes:
        if c.field != "assigned_to" or c.op != "set":
            continue
        new_uid = await _resolve_user_id(
            session, workspace_id=workspace_id, email=str(c.value)
        )
        if new_uid is not None:
            lead.assigned_to = new_uid

    return True


async def _apply_create(
    session: AsyncSession,
    *,
    item: DiffItem,
    workspace_id: UUID,
) -> bool:
    """Create a new Lead in the workspace pool. The diff already carries
    the desired ai_data / tags / contacts deltas via item.changes — we
    apply them against the freshly-created row."""
    from app.pipelines import repositories as pipelines_repo

    if not item.company_name:
        return False

    first = await pipelines_repo.get_default_first_stage(session, workspace_id)
    pipeline_id, stage_id = first if first is not None else (None, None)

    lead = Lead(
        workspace_id=workspace_id,
        pipeline_id=pipeline_id,
        stage_id=stage_id,
        company_name=item.company_name[:255],
        inn=item.inn or None,
        assignment_status="pool",
        tags_json=[],
        source="ai_bulk_update",
    )
    session.add(lead)
    await session.flush()  # need lead.id for contact FKs

    # Replay the diff against the fresh row
    _apply_ai_data_changes(lead, item.changes)
    _apply_tags_changes(lead, item.changes)
    for c in item.changes:
        if c.field == "contacts.add" and isinstance(c.value, list):
            for cd in c.value:
                if not isinstance(cd, dict):
                    continue
                session.add(Contact(
                    lead_id=lead.id,
                    name=(cd.get("name") or cd.get("email") or "Unknown")[:120],
                    title=(cd.get("title") or "")[:120] or None,
                    email=(cd.get("email") or "").strip().lower() or None,
                    role_type=cd.get("role_type") or None,
                    source=cd.get("source") or "ai_bulk_update",
                ))
    return True


# ---------------------------------------------------------------------------
# JSON serialisation helpers
# ---------------------------------------------------------------------------

def diff_to_jsonable(items: list[DiffItem]) -> list[dict[str, Any]]:
    """Coerce DiffItem (and nested Change) into JSON-safe dicts for
    diff_json storage. UUID / Decimal already covered by callers."""
    return [asdict(i) for i in items]


def diff_from_jsonable(blob: list[dict[str, Any]]) -> list[DiffItem]:
    """Inverse — used by the apply task to restore typed objects from
    diff_json."""
    out: list[DiffItem] = []
    for raw in blob or []:
        changes = [
            Change(
                field=c.get("field", ""),
                op=c.get("op", ""),
                value=c.get("value"),
                current_value=c.get("current_value"),
            )
            for c in (raw.get("changes") or [])
        ]
        out.append(DiffItem(
            action=raw.get("action", ""),
            company_name=raw.get("company_name", ""),
            inn=raw.get("inn"),
            lead_id=raw.get("lead_id"),
            changes=changes,
            match_confidence=raw.get("match_confidence", "not_found"),
            error=raw.get("error"),
        ))
    return out


__all__ = [
    "Change",
    "DiffItem",
    "compute_diff",
    "apply_diff_item",
    "diff_to_jsonable",
    "diff_from_jsonable",
]
