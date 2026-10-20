import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app import (
    available_captions,
    available_images,
    code_delivery_description,
    next_send_after,
    render_qr,
    request_test_message,
)

IST = ZoneInfo("Asia/Kolkata")
UTC = ZoneInfo("UTC")


class SchedulerTests(unittest.TestCase):
    def test_before_nine_schedules_same_day(self):
        now = datetime(2026, 10, 20, 8, 59, 59, tzinfo=IST)
        self.assertEqual(
            next_send_after(now),
            datetime(2026, 10, 20, 9, 0, 0, tzinfo=IST),
        )

    def test_at_nine_schedules_next_day(self):
        now = datetime(2026, 10, 20, 9, 0, 0, tzinfo=IST)
        self.assertEqual(
            next_send_after(now),
            datetime(2026, 10, 21, 9, 0, 0, tzinfo=IST),
        )

    def test_converts_to_indian_time(self):
        now = datetime(2026, 10, 20, 2, 0, 0, tzinfo=UTC)
        self.assertEqual(
            next_send_after(now),
            datetime(2026, 10, 20, 9, 0, 0, tzinfo=IST),
        )


class ControlClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_requests_test_message_from_running_service(self):
        with tempfile.TemporaryDirectory() as directory:
            socket_path = Path(directory) / "control.sock"
            received = []

            async def handler(reader, writer):
                received.append((await reader.readline()).decode())
                writer.write(b"OK Test message sent.\n")
                await writer.drain()
                writer.close()
                await writer.wait_closed()

            server = await __import__("asyncio").start_unix_server(
                handler, path=str(socket_path)
            )
            try:
                result = await request_test_message(socket_path)
            finally:
                server.close()
                await server.wait_closed()

            self.assertEqual(received, ["test\n"])
            self.assertEqual(result, "Test message sent.")


class QrTests(unittest.TestCase):
    def test_renders_login_url_as_terminal_qr(self):
        rendered = render_qr("tg://login?token=placeholder")
        self.assertIn("█", rendered)
        self.assertGreater(len(rendered.splitlines()), 10)


class DeliveryDescriptionTests(unittest.TestCase):
    def test_reports_app_delivery_and_sms_fallback(self):
        SentCodeTypeApp = type("SentCodeTypeApp", (), {})
        CodeTypeSms = type("CodeTypeSms", (), {})
        sent = type(
            "SentCode",
            (),
            {"type": SentCodeTypeApp(), "next_type": CodeTypeSms(), "timeout": 60},
        )()
        self.assertEqual(
            code_delivery_description(sent),
            "Telegram app (SMS fallback available after 60 seconds)",
        )


class CaptionTests(unittest.TestCase):
    def test_reads_nonempty_captions_one_per_line(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "message.txt"
            path.write_text("Good morning\n\nHave a lovely day  \n", encoding="utf-8")
            self.assertEqual(
                available_captions(path),
                ["Good morning", "Have a lovely day"],
            )


class ImageTests(unittest.TestCase):
    def test_only_supported_images_are_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("a.jpeg", "b.JPG", "notes.txt"):
                (root / name).touch()
            self.assertEqual(
                [path.name for path in available_images(root)],
                ["a.jpeg", "b.JPG"],
            )


if __name__ == "__main__":
    unittest.main()
