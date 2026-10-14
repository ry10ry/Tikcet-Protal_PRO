# Fault Ticket update

Severity is removed from Report Issue, Fault Ticket table/details/actions, Admin content options and the monthly Fault CSV. Historical database values and legacy API compatibility remain; no migration is required. New UI tickets do not submit severity, and the backend assigns an internal default from existing settings.

When the ticket owner with Requester role adds a non-empty comment during Resolved, Pending Confirmation, it returns to In Progress, clears the previous resolution and resolved timestamp, records the comment/status transition and sends existing update notifications. Infra notes do not reopen it; empty comments are rejected; already Closed tickets remain closed. Existing Pending Customer replies still return to In Progress. Infra can resolve again and the Requester can verify/close after the new fix.

Replace app/main.py, app/static/app.js and app/static/index.html. Rebuild Docker using your existing Compose files and refresh Ctrl+F5. CR/SR behavior is unchanged.
