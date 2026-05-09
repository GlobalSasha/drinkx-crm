"""Email dispatch package — Sprint 2.6 G1.

Tri-state SMTP sender used by the Automation Builder's
`send_template` action. Distinct from `app.notifications.email_sender`
which always returns True on stub-or-success — this one separates
«stub» from «sent» so the lead's Activity Feed can show a different
chip («черновик» vs «отправлено»).
"""
