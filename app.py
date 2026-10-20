import argparse
import asyncio
import getpass
import io
import json
import logging
import os
import random
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.types import InputPhoneContact

TIMEZONE = ZoneInfo("Asia/Kolkata")
SEND_TIME = time(9, 0)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
IMAGE_DIR = Path(os.getenv("IMAGE_DIR", "/app/images"))
MESSAGE_FILE = Path(os.getenv("MESSAGE_FILE", "/app/message.txt"))
CONTROL_SOCKET = Path(os.getenv("CONTROL_SOCKET", "/tmp/telethon-greeter.sock"))
SESSION_PATH = DATA_DIR / "telegram"
STATE_PATH = DATA_DIR / "delivery-state.json"

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
LOG = logging.getLogger("telegram-greeter")


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def telegram_config() -> tuple[int, str]:
    try:
        api_id = int(required_env("TELEGRAM_API_ID"))
    except ValueError as exc:
        raise RuntimeError("TELEGRAM_API_ID must be an integer") from exc
    return api_id, required_env("TELEGRAM_API_HASH")


def render_qr(url: str) -> str:
    import qrcode

    qr = qrcode.QRCode(border=2)
    qr.add_data(url)
    qr.make(fit=True)
    output = io.StringIO()
    qr.print_ascii(out=output, invert=True)
    return output.getvalue()


def code_delivery_description(sent_code) -> str:
    labels = {
        "SentCodeTypeApp": "Telegram app",
        "SentCodeTypeSms": "SMS",
        "SentCodeTypeCall": "phone call",
        "SentCodeTypeFlashCall": "flash call",
        "SentCodeTypeMissedCall": "missed call",
        "SentCodeTypeEmailCode": "email",
        "SentCodeTypeFragmentSms": "Fragment SMS",
        "CodeTypeSms": "SMS",
        "CodeTypeCall": "phone call",
        "CodeTypeFlashCall": "flash call",
        "CodeTypeMissedCall": "missed call",
        "CodeTypeFragmentSms": "Fragment SMS",
    }
    method = labels.get(type(sent_code.type).__name__, type(sent_code.type).__name__)
    if sent_code.next_type is None:
        return method
    fallback = labels.get(
        type(sent_code.next_type).__name__, type(sent_code.next_type).__name__
    )
    timeout = sent_code.timeout or 0
    return f"{method} ({fallback} fallback available after {timeout} seconds)"


def available_images(directory: Path = IMAGE_DIR) -> list[Path]:
    return sorted(
        path for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def available_captions(path: Path = MESSAGE_FILE) -> list[str]:
    try:
        captions = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except OSError as exc:
        raise RuntimeError(f"Could not read caption file {path}: {exc}") from exc
    if not captions:
        raise RuntimeError(f"No non-empty captions found in {path}")
    return captions


def next_send_after(now: datetime) -> datetime:
    local_now = now.astimezone(TIMEZONE)
    candidate = datetime.combine(local_now.date(), SEND_TIME, tzinfo=TIMEZONE)
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate


def last_sent_date() -> str | None:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8")).get("last_sent_date")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def record_sent(now: datetime, image: Path) -> None:
    state = {
        "last_sent_date": now.astimezone(TIMEZONE).date().isoformat(),
        "sent_at": now.astimezone(TIMEZONE).isoformat(),
        "image": image.name,
    }
    temp = STATE_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temp.replace(STATE_PATH)


async def resolve_recipient(client: TelegramClient, phone: str):
    try:
        return await client.get_entity(phone)
    except ValueError:
        result = await client(
            ImportContactsRequest(
                contacts=[
                    InputPhoneContact(
                        client_id=random.getrandbits(63),
                        phone=phone,
                        first_name="Daily Good Morning",
                        last_name="",
                    )
                ]
            )
        )
        if not result.users:
            raise RuntimeError(
                "Telegram could not find a user for the configured recipient number"
            )
        return result.users[0]


async def send_daily_message(
    client: TelegramClient, *, record_delivery: bool = True
) -> None:
    images = available_images()
    if not images:
        raise RuntimeError(f"No supported images found in {IMAGE_DIR}")

    recipient = await resolve_recipient(client, required_env("RECIPIENT_PHONE"))
    image = random.SystemRandom().choice(images)
    caption = random.SystemRandom().choice(available_captions())
    await client.send_file(recipient, image, caption=caption)
    if record_delivery:
        record_sent(datetime.now(TIMEZONE), image)
    kind = "test message" if not record_delivery else "daily message"
    LOG.info("Sent %s with image %s", kind, image.name)


async def request_test_message(socket_path: Path = CONTROL_SOCKET) -> str:
    try:
        reader, writer = await asyncio.open_unix_connection(str(socket_path))
    except (FileNotFoundError, ConnectionRefusedError) as exc:
        raise RuntimeError("The scheduler container is not ready or running") from exc
    try:
        writer.write(b"test\n")
        await writer.drain()
        response = (await reader.readline()).decode().strip()
    finally:
        writer.close()
        await writer.wait_closed()
    if response.startswith("OK "):
        return response[3:]
    raise RuntimeError(response.removeprefix("ERROR ") or "No response from scheduler")


async def send_test_message() -> None:
    print(await request_test_message())


async def handle_control_request(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    client: TelegramClient,
    send_lock: asyncio.Lock,
) -> None:
    try:
        command = (await reader.readline()).decode().strip()
        if command != "test":
            response = "ERROR Unknown control command"
        else:
            async with send_lock:
                await send_daily_message(client, record_delivery=False)
            response = "OK Test message sent."
    except Exception as exc:
        LOG.exception("Control request failed")
        response = f"ERROR {type(exc).__name__}: {exc}"
    writer.write((response + "\n").encode())
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def run_service() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    api_id, api_hash = telegram_config()
    client = TelegramClient(str(SESSION_PATH), api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        raise RuntimeError(
            "Telegram session is not authorized; run the one-time authorize command"
        )

    send_lock = asyncio.Lock()
    CONTROL_SOCKET.unlink(missing_ok=True)
    control_server = await asyncio.start_unix_server(
        lambda reader, writer: handle_control_request(
            reader, writer, client, send_lock
        ),
        path=str(CONTROL_SOCKET),
    )
    LOG.info("Telegram session authorized; scheduler active in Asia/Kolkata")
    try:
        while True:
            target = next_send_after(datetime.now(TIMEZONE))
            delay = max(0.0, (target - datetime.now(TIMEZONE)).total_seconds())
            LOG.info("Next message scheduled for %s", target.isoformat())
            await asyncio.sleep(delay)

            today = datetime.now(TIMEZONE).date().isoformat()
            if last_sent_date() == today:
                LOG.info("Today's message is already recorded as sent; skipping")
                continue

            for attempt in range(1, 4):
                try:
                    async with send_lock:
                        await send_daily_message(client)
                    break
                except Exception:
                    LOG.exception("Send attempt %d of 3 failed", attempt)
                    if attempt < 3:
                        await asyncio.sleep(60)
    finally:
        control_server.close()
        await control_server.wait_closed()
        CONTROL_SOCKET.unlink(missing_ok=True)
        await client.disconnect()


async def authorize_qr() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    api_id, api_hash = telegram_config()
    client = TelegramClient(str(SESSION_PATH), api_id, api_hash)
    await client.connect()
    try:
        if await client.is_user_authorized():
            print("Telegram session is already authorized.")
            return
        while True:
            qr_login = await client.qr_login()
            print("On your phone: Telegram > Settings > Devices > Link Desktop Device")
            print("Scan this QR code within 2 minutes:\n")
            print(render_qr(qr_login.url))
            try:
                await qr_login.wait(timeout=120)
                break
            except asyncio.TimeoutError:
                print("QR code expired; generating a new one.")
            except SessionPasswordNeededError:
                password = getpass.getpass("Telegram 2-step verification password: ")
                await client.sign_in(password=password)
                break
        print("Telegram session authorized and saved in /data.")
    finally:
        await client.disconnect()


async def authorize() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    api_id, api_hash = telegram_config()
    client = TelegramClient(str(SESSION_PATH), api_id, api_hash)
    await client.connect()
    try:
        if await client.is_user_authorized():
            print("Telegram session is already authorized.")
            return
        phone = input("Your Telegram account phone number (international format): ").strip()
        sent_code = await client.send_code_request(phone)
        print(
            "Telegram reports code delivery via: "
            + code_delivery_description(sent_code)
        )
        code = getpass.getpass("Login code sent by Telegram: ").strip()
        try:
            await client.sign_in(phone=phone, code=code)
        except SessionPasswordNeededError:
            password = getpass.getpass("Telegram 2-step verification password: ")
            await client.sign_in(password=password)
        print("Telegram session authorized and saved in /data.")
    finally:
        await client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--authorize", action="store_true")
    modes.add_argument("--authorize-qr", action="store_true")
    modes.add_argument("--test", action="store_true", help="send one message immediately")
    args = parser.parse_args()
    if args.authorize:
        action = authorize()
    elif args.authorize_qr:
        action = authorize_qr()
    elif args.test:
        action = send_test_message()
    else:
        action = run_service()
    asyncio.run(action)


if __name__ == "__main__":
    main()
