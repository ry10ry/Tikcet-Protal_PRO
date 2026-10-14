# Admin user deletion

Users now offers Delete for other accounts, with confirmation. Only Admin can delete; deleting one's own Admin account is rejected. Active Admin rows are locked in a consistent order to protect against concurrent cross-deletions. Deleted accounts disappear from user lists, cannot sign in, lose all login sessions, cannot be selected for assignment and cannot be reactivated through Edit user.

This is archival deletion: the user row is retained with an inactive internal role so Fault Tickets, CR/SR ownership and approval/history actor identities remain intact. The original email stays reserved and cannot be registered again. Existing tickets assigned to this user are not automatically reassigned; another Infra/Admin can reassign them. No database migration is required.

Replace app/main.py, app/static/app.js and app/static/index.html, rebuild Docker and refresh with Ctrl+F5.
