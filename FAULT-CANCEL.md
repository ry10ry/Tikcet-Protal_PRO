# Cancel Fault Ticket

Cancel Ticket is available to TM/TL Requesters for their own tickets, and to Infra, Infra TL, Infra Manager and Admin for any active fault ticket. A non-empty cancellation reason and browser confirmation are required. Closed and Cancelled tickets cannot be cancelled again. Pending Customer, Pending 3rd Party and Resolved, Pending Confirmation tickets can be cancelled.

Cancellation retains the ticket, attachments, assignee and history; a status entry captures the actor/time and reason. Existing fault-update notifications notify the requester and assignee (or internal staff if unassigned). It remains visible with Cancelled status and can be filtered/exported normally. CR/SR are unchanged. Admin can rename/disable Cancel Ticket separately in Requester and Infra actions. Existing saved settings receive enabled Cancel defaults automatically; the legacy New-ticket decline action remains available.

Replace app/main.py, app/static/app.js and app/static/index.html. Rebuild Docker and refresh Ctrl+F5. No database migration is required.
