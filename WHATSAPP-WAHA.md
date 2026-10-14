> PROD v0.1 默认关闭 WhatsApp 通知。请重新填写 PROD 的 WAHA 服务、密钥及群组；以下均为占位示例。

# WAHA: new Fault Ticket to a WhatsApp group

This integration sends only new Fault Ticket notifications. Status changes, comments, CR and SR events do not enqueue WhatsApp messages. Portal notifications are unchanged. It is disabled by default. No real WhatsApp messages were sent during development; tests mock the sender. The user LAN WAHA deployment still needs an on-site end-to-end test.

WAHA URL provided by the user: http://WAHA_SERVER_IP:3000 (2026.1.3 CORE). Session name and group Chat ID must be verified in that WAHA instance. WORKING: 1 on the dashboard is a count, not the session name.

## Find the Session and group ID (read-only)

In Windows PowerShell:

```powershell
$waha = "http://WAHA_SERVER_IP:3000"
$key = Read-Host "WAHA API Key" -AsSecureString
$headers = @{ "X-Api-Key" = [System.Net.NetworkCredential]::new("", $key).Password }
Invoke-RestMethod "$waha/api/sessions" -Headers $headers | Select-Object name, status
$session = "default" # replace with the WORKING session name
Invoke-RestMethod "$waha/api/$session/groups?limit=100&offset=0" -Headers $headers | Select-Object id, subject
```

If your engine uses a different group response shape, inspect it locally with ConvertTo-Json -Depth 5. Match the target group name and copy its ID ending in @g.us. Other groups may appear on subsequent pages (increase offset). These GET requests do not send messages. Do not share the API Key.

## Portal deployment

Add app/waha.py. Replace app/main.py, app/scheduler.py and compose.yaml (or merge the WAHA environment variables into your existing shared app_env). Keep your existing external volume definitions and other local Compose customizations.

Add these values to the Portal project's .env, not only WAHA's own .env:

```dotenv
WAHA_ENABLED=true
WAHA_URL=http://WAHA_SERVER_IP:3000
WAHA_API_KEY=YOUR_WAHA_API_KEY
WAHA_SESSION=YOUR_WORKING_SESSION_NAME
WAHA_GROUP_CHAT_ID=YOUR_GROUP_ID@g.us
PORTAL_URL=https://PROD_SERVER_IP
```

PORTAL_URL is optional and must be an address reachable by group members. Docker containers on the Portal host must be able to reach the WAHA URL. It is not localhost unless WAHA runs in the same container. No API Key is included in this repository or logs.

```powershell
docker compose -f compose.yaml -f compose.override.yaml -f compose.ssl.yaml up -d --build --force-recreate web scheduler
docker compose -f compose.yaml -f compose.override.yaml -f compose.ssl.yaml logs --tail 50 scheduler
```

Application startup automatically creates the whatsapp_outbox table using the existing database initialization. No destructive migration or new Python dependency is needed.

Create one new Fault Ticket after configuration is enabled. The group receives the ticket reference, Subject, Category, Domain, requester, SGT reported time, description excerpt and optional Portal link. No files, screenshots or Severity are sent. Updates to that ticket must not produce another WhatsApp message. Normal delivery starts on the next scheduler cycle (about 10 seconds). Existing tickets created while integration was disabled are not replayed.

## Delivery and failures

Queue entries commit with ticket creation/attachments, so a failed ticket does not notify the group. The scheduler sends POST /api/sendText with X-Api-Key and session/chatId/text/linkPreview. HTTP timeouts are bounded to 10 seconds. Failure does not block ticket creation; the entry is retained and retries back off from 30 seconds to a maximum of 15 minutes. Logs include queue IDs and safe error summaries, not API keys or message content. A successful WAHA acknowledgement marks the event sent; normal polling does not resend it.

A three-minute lease and atomic claims allow recovery if a worker stops. Network ambiguity (WAHA sends but the response is lost) can cause a duplicate on retry; WAHA does not provide exactly-once guarantees here. Queue entries preserve the group and session selected at creation. If originally missing, the group uses the configured fallback. WAHA_ENABLED=false pauses delivery and stops enqueuing new events without deleting existing queue data.

Admin deletion of a Fault Ticket also removes its queue entry. The database backup includes the queue. During disaster recovery, start with WAHA_ENABLED=false and review pending entries before re-enabling to avoid replaying old messages from a backup.
