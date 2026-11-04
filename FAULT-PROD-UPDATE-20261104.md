# Approved PRO Fault Ticket update — 4 November 2026

Promoted UAT commit `3263f27` after the user confirmed acceptance testing passed and explicitly approved the PRO update. PRO version remains 0.1.

## Changes

- Requesters can add notes and reply attachments to other Requesters' Public Fault Tickets. Internal tickets remain hidden and reject direct access. Only the original requester can cancel or verify/close their ticket. Comments from other Requesters do not reopen resolved tickets or clear Pending Customer; the original requester's reply keeps the existing status transitions. Closed, cancelled and archived tickets keep their existing restrictions.
- Fault Ticket filters now include Assigned To (including Unassigned) and, for staff, Visibility (Public/Internal). These combine with the existing Status filter and search. Search also matches Engineer name, raw status and configured display status. Engineer options come from the tickets visible to the signed-in user; Requesters do not gain access to the staff user directory. Pagination applies after filtering.
- Requesters cannot upload attachments while creating a Fault Ticket. The create form hides and disables that input, omits files from submission, and the API rejects nonempty attachment lists without creating a ticket. Staff creation and reply attachments remain available. Existing attachments are retained.
- Restored the base tests/test_workflow.py from the bundled original package to make the current regression suite directly runnable, updating its expectations for shared replies and creation attachment restrictions. Archive tests now add requester files through replies.

## Validation

36 SQLite integration tests passed, including the PRO bootstrap test,, including shared replies, owner-only actions, private visibility, creation rollback and reply attachment downloads. JavaScript checks passed for Status, Assigned To, Visibility, combined filters, empty results, unassigned tickets and status/Engineer text search. JavaScript syntax and git diff whitespace checks passed. Automated checks did not send real WhatsApp messages.

Commands from the repository root (Python dependencies plus pytest==8.3.5 and httpx==0.28.1 installed):

```sh
python -m pytest -q tests
node --check app/static/app.js
node tests/fault-filters-checks.cjs
```

Tests use a disposable SQLite database by default; do not set TEST_DATABASE_URL to a business database. Set UPLOAD_DIR to a writable disposable location when needed.

## Deployment and acceptance

Back up the database, then update the PRO checkout and rebuild/recreate web and scheduler with the installation's existing Compose files and .env. Preserve existing volumes and data. No database migration is required. Reload the browser to load the versioned JavaScript.

1. As Requester B, open Requester A's Public ticket and reply. A and staff should see B's name, comment and any reply file. B must not be able to cancel or close A's ticket.
2. Confirm a Requester cannot see or reply to Internal tickets, including direct URLs.
3. As staff, combine Status, Assigned To and Visibility filters. Check Unassigned and search by Engineer or status. Requesters should see only Public tickets and no Visibility control.
4. As a Requester, Report Issue must have no attachment input. Staff Report Issue and the ticket reply form retain attachments.
