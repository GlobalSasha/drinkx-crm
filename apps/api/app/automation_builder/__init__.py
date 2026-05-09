"""Automation Builder domain — Sprint 2.5 G1.

User-defined «when X happens, run Y» rules. Distinct from the
existing `app/automation/` package, which is the stage-change rule
engine (gates + pre/post checks). Builder rules live workspace-scoped
in `automations` table; every fire appends an `automation_runs` row.

Triggers wire into existing hot paths:
  - stage_change → app/automation/stage_change.py POST_ACTIONS
  - form_submission → app/forms/lead_factory.py after-create
  - inbox_match → app/inbox/processor.py after-attach

Actions in v1: send_template / create_task / move_stage. Outbound
delivery (email / tg / sms) is a fail-open stub in v1; the
Automation Builder UX is the value, the actual send is wired in
follow-on polish (notification + email_sender already exist for the
email channel).
"""
