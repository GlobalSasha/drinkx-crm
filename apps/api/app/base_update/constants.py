"""String enums (as module constants) for the base_update domain.

Kept as plain strings (not Python Enum) so they serialise directly to
JSON columns / Pydantic without `.value` ceremony, matching the
import_export domain's status-string convention.
"""

# IngestJob.status lifecycle
JOB_PENDING = "pending"
JOB_EXTRACTING = "extracting"
JOB_MATCHING = "matching"
JOB_READY = "ready"        # auto-applied; conflicts await resolution
JOB_RESOLVING = "resolving"
JOB_DONE = "done"
JOB_FAILED = "failed"

# IngestRecord.action
ACTION_CREATED = "created"
ACTION_UPDATED = "updated"
ACTION_CONFLICT = "conflict"
ACTION_SKIPPED = "skipped"

# IngestConflict.type (the 6 conflict kinds from the spec)
C_COMPANY_AMBIGUOUS = "company_ambiguous"   # #1
C_FIELD_MISMATCH = "field_mismatch"         # #2
C_CONTACT_MISMATCH = "contact_mismatch"     # #3
C_LEAD_TARGET = "lead_target"               # #4
C_LOW_CONFIDENCE = "low_confidence"         # #5
C_BATCH_DUPLICATE = "batch_duplicate"       # #6

# IngestConflict.target_kind
TK_COMPANY = "company"
TK_LEAD = "lead"
TK_CONTACT = "contact"
TK_BRIEF = "brief"

# IngestConflict.status
CONFLICT_OPEN = "open"
CONFLICT_RESOLVED = "resolved"
CONFLICT_SKIPPED = "skipped"

# IngestConflict.resolution (admin's decision)
R_KEEP = "keep"                 # keep base value
R_OVERWRITE = "overwrite"       # take incoming value
R_MANUAL = "manual"             # use resolved_value
R_ADD_SEPARATE = "add_separate" # add as a new contact/lead
R_PICK = "pick"                 # pick a candidate (resolved_value = id)
R_SKIP = "skip"

# Fields eligible for auto-fill / #2 conflicts (company + lead level)
DIFFABLE_FIELDS = ("segment", "priority", "website", "inn", "city", "email", "phone")

# #5 trigger: extraction_confidence below this is held for review
MIN_EXTRACTION_CONFIDENCE = 0.55
