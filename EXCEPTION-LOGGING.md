# Exception handling and log files

HTTP requests now receive a server-generated X-Request-ID. Unexpected request errors are caught and return a safe JSON 500 message with a Reference ID; database connection/pool availability errors return 503. Existing 401/403/404/409/422 business responses remain unchanged. No automatic retry is added to write requests. The frontend handles connection failures and non-JSON responses without exposing raw errors.

Web logs include request ID, route template, method, status, duration, exception class, source filenames/line numbers and numeric database/OS error codes where available. Startup initialization failures and scheduler task failures are logged too. Time is Asia/Singapore with +08:00 offset. Request query strings, bodies, headers, cookies, attachment bytes and exception argument values are not logged by this middleware. SQLAlchemy hides SQL parameters. Known credential environment values are redacted in formatted output. Tracebacks intentionally omit exception values, local variables and source-code text; use the class, error code and file/line to investigate.

## Deploy on Windows

Add app/logging_support.py. Replace app/main.py, app/scheduler.py, app/static/app.js, app/static/index.html, Dockerfile and compose.yaml. If you customized Docker/Compose files, merge the changes: create /data/logs writable by desk in Dockerfile; mount ./logs:/data/logs on web and scheduler; set shared LOG_DIR=/data/logs and scheduler-only LOG_SERVICE=scheduler. Keep existing external database and attachment volumes, WAHA settings, SSL override and local customizations. No database migration or new Python dependency is required.

```powershell
New-Item -ItemType Directory -Path .\logs -Force
docker compose -f compose.yaml -f compose.override.yaml -f compose.ssl.yaml up -d --build --force-recreate web scheduler
```

Logs persist under the project directory:

- logs/web.log: API errors, request summaries, web startup/lifecycle.
- logs/scheduler.log: auto-close task, WhatsApp queue and scheduler errors.
- Rotated files: web.log.1 through web.log.5 and scheduler.log.1 through scheduler.log.5. Each file rotates at 5 MiB (a single very large entry may exceed the threshold). Each service keeps five old files plus the active file. Retention is size-based, not a guaranteed number of days.

The updated Compose file also caps web/scheduler Docker console logs to three 10 MB files per container. The host log folder is a bind mount and is not deleted by docker compose down -v. Linux deployments may need host-directory permissions adjusted for the container desk user. If opening log files fails, the application logs a warning and continues to the console; check permissions and free disk space. Do not commit or publicly share diagnostic logs; .gitignore excludes logs/.

## Read and find an error

```powershell
Get-Content .\logs\web.log -Tail 100
Get-Content .\logs\scheduler.log -Tail 100
Select-String -Path .\logs\web.log* -Pattern "PASTE_REFERENCE_ID" -Context 0,30
```

A browser Reference ID should match request_id in web.log. Startup and scheduler tasks have no browser request and use request_id=-. Existing WhatsApp logs include their queue item ID. Logs are not exposed over a Portal URL.

TLS handshake, port binding, Nginx and Docker failures happen outside the application and cannot be caught by an HTTP route's try/except. Save Proxy diagnostics separately when an HTTPS incident occurs:

```powershell
docker compose -f compose.yaml -f compose.override.yaml -f compose.ssl.yaml logs --since 30m proxy | Out-File .\logs\proxy-diagnostic.log -Encoding utf8
```

If an error occurs after a streaming response has already begun, its existing request ID and exception are logged, but the server cannot replace the already-started download with a JSON error. Logging records a failure; it does not guarantee recovery from infrastructure or disk failures.

## Warning and Error only

The application file and console handlers now use WARNING as the minimum level. INFO and DEBUG request summaries, startup-complete messages, successful WhatsApp sends and normal scheduler checks are omitted. WARNING, ERROR and CRITICAL records remain, including exception frames and request references. The log files are still created on startup even when empty. Docker/Nginx output produced outside Python logging is separate. Replace app/logging_support.py and rebuild web/scheduler; no Compose or database change is needed.
