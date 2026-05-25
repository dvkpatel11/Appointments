# API Reference

## Base URL

```
https://YOUR_SERVICE_URL
```

## Authentication

Most endpoints require admin authentication via session cookie. Log in via `POST /login` with the `ADMIN_PASSWORD`.

---

## Admin Endpoints

### `POST /login`

Authenticate with the admin password.

**Form Parameters:**

| Parameter | Type | Required |
|---|---|---|
| `password` | string | Yes |

**Response:** Redirects to `/` on success, re-renders login with error on failure.

---

### `GET /`

Admin dashboard (authenticated). Renders the multi-user management UI.

---

### `POST /start_automation`

Start automation for a specific user.

**Form Parameters:**

| Parameter | Type | Required | Default |
|---|---|---|---|
| `user_id` | string | No | `"default"` |
| `username` | string | Yes | — |
| `password` | string | Yes | — |
| `appointment_id` | string | Yes | — |
| `appointment_url` | string | Yes | — |
| `notification_email` | string | No | — |
| `browsers` | int | No | `1` |
| `check` | int | No | `12` |
| `reschedule` | bool | No | `false` |
| `telegram_chat_id` | string | No | — |
| `send_telegram` | bool | No | `false` |

**Response:**

```json
{"status": "ONLINE // default"}
```

---

### `POST /start_multi_automation`

Start automation for multiple users at once.

**Form Parameters:**

| Parameter | Type | Required |
|---|---|---|
| `users_data` | JSON string | Yes |

`users_data` format:

```json
{
  "user_1": {
    "username": "...",
    "password": "...",
    "appointment_id": "...",
    "appointment_url": "...",
    "notification_email": "...",
    "browsers": 1,
    "check": 12,
    "reschedule": false,
    "telegram_chat_id": "...",
    "send_telegram": true
  }
}
```

---

### `POST /stop_automation`

Stop automation for a specific user.

**Form Parameters:**

| Parameter | Type | Required | Default |
|---|---|---|---|
| `user_id` | string | No | `"default"` |

**Response:**

```json
{"status": "TERMINATED // default"}
```

---

### `POST /stop_all_automation`

Stop all running automation instances.

**Response:**

```json
{"status": "ALL_TERMINATED"}
```

---

### `GET /get_status`

Get status for a specific user.

**Query Parameters:**

| Parameter | Type | Required | Default |
|---|---|---|---|
| `user_id` | string | No | `"default"` |

**Response:**

```json
{
  "is_running": true,
  "current_action": "CHECKING",
  "action_log": [...],
  "current_appointment": "2025-06-15",
  "new_appointment": null,
  "last_checked_location": "Toronto"
}
```

---

### `GET /get_all_status`

Get status for all automation instances.

**Response:** Object keyed by `user_id` with status data.

---

### `GET /generate_client_link`

Generate a unique client submission link.

**Response:**

```json
{"link": "https://YOUR_URL/client/abc123..."}
```

---

### `GET /admin/pending_requests`

List all client requests awaiting admin approval.

**Response:** Object keyed by token with client details.

---

### `POST /admin/approve_client/<token>`

Approve a pending client request and start automation.

**Response:**

```json
{"status": "approved", "user_id": "abc123..."}
```

---

### `POST /admin/reject_client/<token>`

Reject a pending client request.

**Form Parameters:**

| Parameter | Type | Required |
|---|---|---|
| `reason` | string | No |

---

## Public Endpoints

### `GET /health`

Health check for uptime monitors.

**Response:**

```json
{"status": "ok", "timestamp": "2025-05-25T12:00:00"}
```

---

### `GET /client/<token>`

Client submission form for a specific token.

---

### `POST /client_submit`

Submit client credentials for admin approval.

**Form Parameters:**

| Parameter | Type | Required |
|---|---|---|
| `token` | string | Yes |
| `name` | string | Yes |
| `email` | string | Yes |
| `username` | string | Yes |
| `password` | string | Yes |
| `appointment_url` | string | Yes |
| `reschedule` | string | No (`"true"/"false"`) |

**Response:**

```json
{"status": "pending_approval"}
```

---

### `GET /client_status/<token>`

Check the status of a client's automation.

**Response:**

```json
{"status": "ok", "is_running": true, "last_checked_location": "Toronto"}
```

---

### `GET /client_screenshot/<user_id>`

Get the latest appointment page screenshot for a user.

**Response:**

```json
{"status": "ready", "image_url": "/screenshots/123/001_appointments_page.png"}
```

---

### `GET /settings` / `POST /save_settings`

Get or save global notification settings.

**POST Form Parameters:**

| Parameter | Type | Required |
|---|---|---|
| `default_notif_email` | string | No |
| `default_telegram_chat_id` | string | No |
| `email_enabled` | bool | No |
| `telegram_enabled` | bool | No |

---

### `POST /test_email`

Send a test email notification.

**JSON Body:**

```json
{"email": "test@example.com"}
```

---

### `POST /test_telegram`

Send a test Telegram notification.

**JSON Body:**

```json
{"chat_id": "123456789"}
```

---

### `GET /set_telegram_webhook`

Configure the Telegram bot webhook URL. Visit this URL once after deployment.

---

### `POST /telegram_webhook`

Telegram webhook endpoint. Handles `/start`, `/myid` commands.

---

### `GET /view_log/<user_id>`

View the last 500 lines of the application log for a user.

---

### `GET /download_log`

Download the full application log file.
