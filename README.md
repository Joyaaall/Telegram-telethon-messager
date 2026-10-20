Telethon daily good-morning sender

Complete setup, operation, testing and troubleshooting documentation is available in [`DOCUMENTATION.md`](DOCUMENTATION.md).

This container keeps a persistent Telegram user session and sends one randomly selected local image with one random caption from `message.txt` every day at 09:00 Asia/Kolkata time. Put one caption on each line; blank lines are ignored. Captions and the private `images/` directory are mounted read-only, so content changes do not require rebuilding the image.

Setup

1. Create an app at https://my.telegram.org, copy `.env.example` to `.env`, and replace all placeholder values. Then create the local caption file:

   cp message.example.txt message.txt
2. Build the image:

   docker compose build

3. Authorize the Telegram account once with QR login:

   docker compose run --rm telethon-greeter python /app/app.py --authorize-qr

4. Start the 24/7 service:

   docker compose up -d

5. Verify it:

   docker compose ps
   docker compose logs --tail=30 telethon-greeter

Send a test message immediately

Enter the running container and invoke test mode:

   docker compose exec telethon-greeter sh
   python /app/app.py --test
   exit

Test messages use a random image and random caption, but do not mark the day's scheduled message as delivered.

The Telegram session and delivery record are retained in the Docker volume `telethon-good-morning-session`. Rebuilding or restarting the container does not remove them. Telegram can still revoke a session for security/account reasons; no container can guarantee that Telegram will never log a session out.

The first lookup by phone number may add the recipient to the Telegram account's contacts as `Daily Good Morning`, which is required when Telegram has not already cached that phone number.
