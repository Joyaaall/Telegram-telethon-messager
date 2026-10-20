# Telethon Daily Good-Morning Sender

## 1. Purpose

This Docker service keeps an authorized Telegram user session online and sends one photo with one caption every day at exactly 09:00 in the `Asia/Kolkata` timezone.

For each scheduled message, the service independently selects:

- one random image from the local, Git-ignored `images/` directory; and
- one random non-empty line from `message.txt`.

The service also supports sending an immediate test message without disturbing the daily delivery record.

## 2. Current deployment

- Project directory: `~/telethon-good-morning`
- Compose service: `telethon-greeter`
- Container: `telethon-good-morning`
- Image: `local/telethon-good-morning:1.0.0`
- Persistent volume: `telethon-good-morning-session`
- Schedule: every day at 09:00 IST (`Asia/Kolkata`)
- Restart policy: `unless-stopped`
- Exposed network ports: none

The container is expected to remain running continuously. Docker restarts it after host reboots or process failures unless it was manually stopped.

## 3. Project files

| File | Purpose |
|---|---|
| `app.py` | Telegram client, scheduler, authorization, random selection and test-message control |
| `compose.yaml` | Container configuration, persistent volume and security settings |
| `Dockerfile` | Builds the non-root Python/Telethon image without private media or captions |
| `requirements.txt` | Pinned Python dependencies |
| `.env` | Private Telegram API credentials; never publish or commit this file |
| `.env.example` | Safe configuration template |
| `message.example.txt` | Safe caption template intended for GitHub |
| `message.txt` | Local caption list mounted at runtime and ignored by Git |
| `images/` | Local image pool; image files are ignored by Git |
| `test_app.py` | Automated tests for schedule, captions, images, QR rendering and control requests |

## 4. How it works

```text
Docker Compose
    |
    +-- loads API credentials from .env
    +-- mounts message.txt read-only
    +-- mounts images/ read-only
    +-- mounts the persistent /data volume
    |
    v
Telethon scheduler
    |
    +-- connects using the saved Telegram session
    +-- calculates the next 09:00 Asia/Kolkata occurrence
    +-- sleeps until the scheduled time
    +-- chooses one random image
    +-- chooses one random caption
    +-- sends the photo and caption
    +-- records the successful delivery date in /data
```

At startup, the service does not send a catch-up message. If the container starts after 09:00, the next scheduled delivery is 09:00 the following day.

A scheduled send is retried up to three times, with a 60-second delay between failed attempts. After a successful scheduled delivery, the date, timestamp and selected image are stored in `/data/delivery-state.json`. This prevents a second scheduled send for the same date.

Random selection allows repeats. An image or caption used today may be selected again tomorrow.

## 5. Telegram session persistence

The authorized Telethon session is stored in the Docker volume:

```text
telethon-good-morning-session
```

Rebuilding or replacing the application container does not remove this volume. Do not run `docker compose down -v` unless you intentionally want to delete the saved Telegram session and authorize again.

Keeping the session volume prevents ordinary container rebuilds and restarts from logging the account out. Telegram can still revoke a session because of account actions, security checks or server-side policy.

## 6. First-time setup

### 6.1 Create Telegram API credentials

1. Open `https://my.telegram.org`.
2. Sign in with the Telegram account that will send the messages.
3. Open **API development tools**.
4. Create an application and copy its API ID and API hash.
5. Keep the API hash private.

### 6.2 Create the private environment file

```bash
cd ~/telethon-good-morning
cp .env.example .env
cp message.example.txt message.txt
nano .env
```

Set all values:

```dotenv
TELEGRAM_API_ID=your_numeric_api_id
TELEGRAM_API_HASH=your_private_api_hash
RECIPIENT_PHONE=recipient_in_international_format
```

The `.env` and `message.txt` files are excluded by `.gitignore` and `.dockerignore`.

### 6.3 Build the image

```bash
cd ~/telethon-good-morning
docker compose build
```

### 6.4 Authorize using QR login

QR login is the recommended method:

```bash
docker compose run --rm telethon-greeter python /app/app.py --authorize-qr
```

On the phone containing the authorized Telegram account, open:

```text
Telegram > Settings > Devices > Link Desktop Device
```

Scan the terminal QR code. In tmux, use `Ctrl+B`, then `Z` to zoom the current pane if the QR code is too narrow or distorted.

The authorization container is temporary because of `--rm`. The authorized session remains in the persistent Docker volume.

### 6.5 Alternative code-based authorization

```bash
docker compose run --rm telethon-greeter python /app/app.py --authorize
```

Enter the sender account's phone number in international format, including the `+` sign. Enter login codes and two-step-verification passwords only in the local terminal; never put them in documentation or chat messages.

### 6.6 Start the service

```bash
docker compose up -d
```

### 6.7 Verify startup

```bash
docker compose ps
docker compose logs --tail=30 telethon-greeter
```

Healthy startup logs contain lines similar to:

```text
Telegram session authorized; scheduler active in Asia/Kolkata
Next message scheduled for YYYY-MM-DDT09:00:00+05:30
```

## 7. Managing captions

Edit the caption file:

```bash
nano ~/telethon-good-morning/message.txt
```

Use one caption per line:

```text
Good morning
Have a beautiful day
Wishing you a wonderful morning
```

Blank lines are ignored. At least one non-empty caption must remain.

`message.txt` is mounted into the running container read-only. Saving changes updates the available caption pool immediately; no rebuild or container restart is required.

## 8. Managing images

Supported image extensions are:

- `.jpg`
- `.jpeg`
- `.png`
- `.webp`

Place image files in:

```text
~/telethon-good-morning/images/
```

The directory is mounted into the container read-only. Adding, deleting or replacing an image takes effect immediately and does not require an image rebuild or container restart.

The image files are deliberately excluded from Git. Only `images/README.md` and `images/.gitkeep` are intended for the public repository. This avoids publishing personal media or third-party meme images whose reuse rights may be unclear.

## 9. Sending a test message

The service must already be running. Send one immediate random image and random caption with:

```bash
cd ~/telethon-good-morning
docker compose exec telethon-greeter python /app/app.py --test
```

Expected output:

```text
Test message sent.
```

The test command communicates with the already-running scheduler through a local Unix socket. This design ensures that only one process accesses the Telegram SQLite session, avoiding `sqlite3.OperationalError: database is locked`.

A test message does not update the scheduled-delivery record. Sending a test does not prevent the normal 09:00 message.

To enter the container manually:

```bash
docker compose exec telethon-greeter sh
python /app/app.py --test
exit
```

## 10. Routine operations

### Show status

```bash
cd ~/telethon-good-morning
docker compose ps
```

### Follow logs

```bash
docker compose logs -f telethon-greeter
```

Press `Ctrl+C` to stop following logs; this does not stop the container.

### Show recent logs

```bash
docker compose logs --tail=50 telethon-greeter
```

### Restart

```bash
docker compose restart telethon-greeter
```

### Stop

```bash
docker compose stop telethon-greeter
```

### Start again

```bash
docker compose start telethon-greeter
```

### Rebuild after code or dependency changes

```bash
docker compose build
docker compose up -d --force-recreate
```

The persistent Telegram session survives these operations.

## 11. Automated tests

Build the image and run all tests:

```bash
cd ~/telethon-good-morning
docker compose build
docker run --rm \
  -v "$PWD/test_app.py:/app/test_app.py:ro" \
  local/telethon-good-morning:1.0.0 \
  python -m unittest -v test_app
```

The tests cover:

- scheduling before and after 09:00 IST;
- conversion from UTC to Indian time;
- supported-image filtering;
- non-empty caption parsing;
- Telegram code-delivery descriptions;
- terminal QR generation; and
- test-message control-socket requests.

## 12. Troubleshooting

### Container repeatedly exits

Inspect the logs:

```bash
docker compose logs --tail=100 telethon-greeter
```

Common causes are missing API credentials, an unauthorized session, an empty caption file or no supported images.

### Telegram session is not authorized

Stop the service and authorize again with QR login:

```bash
docker compose stop telethon-greeter
docker compose run --rm telethon-greeter python /app/app.py --authorize-qr
docker compose start telethon-greeter
```

### Login code does not appear

Use QR login instead of repeatedly requesting codes:

```bash
docker compose run --rm telethon-greeter python /app/app.py --authorize-qr
```

### Test command says the scheduler is not ready

Check that the main container is running:

```bash
docker compose ps
docker compose logs --tail=30 telethon-greeter
```

Wait until the scheduler authorization and next-run lines appear, then retry the test command.

### Database is locked

Do not start a second Telethon client against the same session volume. Use the supported test command while the service is running:

```bash
docker compose exec telethon-greeter python /app/app.py --test
```

### No captions found

Add at least one non-empty line to `message.txt`:

```bash
nano ~/telethon-good-morning/message.txt
```

### Recipient cannot be found

Confirm the configured recipient number uses international format. Telegram may add the recipient to the sender account's contacts as `Daily Good Morning` when resolving the number for the first time.

### Message was missed while the server was down

The scheduler does not send historical catch-up messages. Restore the service and use `--test` if an immediate manual delivery is required. The normal schedule resumes at the next 09:00 IST.

## 13. Security and data handling

- The API hash stays in the local `.env` file and is not built into the image.
- Login codes and two-step-verification passwords are entered only into interactive local prompts.
- The Telegram session volume is sensitive and should not be copied to public storage.
- The service publishes no network ports.
- The application runs as a non-root user.
- Linux capabilities are dropped.
- `no-new-privileges` is enabled.
- The container root filesystem is read-only.
- Temporary runtime files use a small in-memory `/tmp` filesystem.
- `message.txt` is mounted read-only.

## 14. Public-repository safety check

After initializing Git and before every public push, run:

```bash
python3 scripts/scan_public_repo.py .
git status --short --ignored
```

The scanner checks the files Git would publish for credentials, API hashes, international phone numbers, private IP addresses, personal home paths and UUIDs. Confirm that `.env`, `message.txt` and the actual files under `images/` appear as ignored.

## 15. Removing the deployment

Stop and remove only the container while preserving the Telegram session:

```bash
docker compose down
```

Start it again later with:

```bash
docker compose up -d
```

To permanently remove the saved Telegram session as well, first log out that session from Telegram's **Settings > Devices**, then remove the Compose volume intentionally. Deleting the volume requires QR or code authorization before the service can run again.

## 16. Quick command reference

```bash
cd ~/telethon-good-morning

# Status
docker compose ps

# Recent logs
docker compose logs --tail=50 telethon-greeter

# Immediate test message
docker compose exec telethon-greeter python /app/app.py --test

# Restart
docker compose restart telethon-greeter

# Edit captions
nano message.txt

# Rebuild after changing code or dependencies
docker compose build
docker compose up -d --force-recreate
```
