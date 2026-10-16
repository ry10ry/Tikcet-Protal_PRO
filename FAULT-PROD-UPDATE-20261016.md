# PROD Fault Ticket update — 16 October 2026

Approved promotion from UAT commits dabebbc and 78a19b6. Application version, image tag and /api/health remain **0.1**. The original Git tag v0.1 is preserved as the initial release snapshot; obtain this update from main or this dated update package.

## Included changes

- New Infra/TL/Manager/Admin faults default to Internal, with Public selectable. Internal is inaccessible to all Requesters through lists, detail, actions, notifications and attachment URLs. Requester-created tickets are Public. Existing tickets remain Public.
- WhatsApp messages for new faults raised by Requesters or Infra (Public and Internal) use seven lines only: New Fault Ticket, Number, Subject, Category, Domain, Raised by, Reported. Description and Portal link are removed. Existing queued payloads are trimmed on delivery; already-sent messages are not altered.
- Larger Report Issue window; Description supports safe HTML tables and Excel tab-separated paste. Table rows, columns and borders remain after submission and in future offline archives.
- Grey in-editor placeholder: “What happened? Include affected users, time, symptoms and steps to reproduce.” The previous help paragraph is removed.

## Existing PROD installation

Take a successful backup before updating. Preserve .env, SSL certificates, volumes, logs and archives. Do not rerun Setup-PROD.ps1.

If using Git, run git fetch origin, git switch main, then git pull --ff-only origin main from the existing PROD checkout. A clone of the original v0.1 tag may be in detached-HEAD state; switching to main is necessary to receive approved updates. Otherwise copy these files from the update package, retaining paths:

New: app/fault_content.py, app/static/fault-editor.js.

Replace: app/main.py, app/waha.py, app/archive.py, app/static/app.js, app/static/index.html, app/static/style.css.

Then run:

```powershell
docker compose -f compose.yaml -f compose.override.yaml -f compose.ssl.yaml up -d --build --force-recreate web scheduler
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-HTTPS.ps1
curl.exe --cacert .\ssl\certs\root-ca.crt https://192.168.3.111/api/health
```

Expected health response: {"status":"ok","environment":"PROD","version":"0.1"}.

Press Ctrl+F5 on clients. The new fault_content table is created automatically; no extra dependency or manual SQL migration is required. Existing data is retained. Do not roll back to a backend without Internal visibility checks while Internal records exist.

## Acceptance

Verify an Internal fault and its attachment are inaccessible from a Requester account; a Public fault remains visible. Test table paste, save/reopen and placeholder appearance. Test one new WAHA message using the configured PROD group. Notification delivery requires WAHA enabled and valid configuration; this update does not turn it on or replace group settings.

Source publication does not deploy automatically to the Windows PROD computer. Subsequent unapproved development remains UAT-only.

Validation: 34 SQLite and 34 isolated MySQL tests passed; Chromium checks passed for HTML/TSV paste, stored tables and borders, visibility defaults, enlarged dialog and placeholder hide/restore. PROD health/version bootstrap tests passed.
