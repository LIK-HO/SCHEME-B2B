from datetime import datetime, timedelta
from email.message import EmailMessage
import random
import smtplib

import httpx

from .airtable import AirtableClient
from .config import Settings
from .schedule import MSK


CHANNEL_EMAIL = "Email"
CHANNEL_MAX = "MAX"
STATUS_PENDING = "Ожидает"
STATUS_SENDING = STATUS_PENDING
STATUS_SENT = "Отправлено"
STATUS_ERROR = "Ошибка"


class OutboxDispatcher:
    def __init__(self, airtable: AirtableClient, settings: Settings):
        self.airtable = airtable
        self.settings = settings

    def enqueue(
        self,
        event_id: str,
        channel: str,
        profile: str,
        summary: str,
        recipient: str,
    ) -> bool:
        table = self.settings.airtable_table_notifications
        if self.airtable.find_notification(table, event_id, channel):
            return False

        self.airtable.create_record(
            table,
            {
                "Событие": "Итог поиска",
                "Идентификатор события": event_id,
                "Канал": channel,
                "Статус": STATUS_PENDING,
                "Получатель": recipient,
                "Содержание": summary,
                "Профиль поиска": profile,
                "Дата события": datetime.now(MSK).isoformat(timespec="seconds"),
                "Попытки": 0,
                "Последняя попытка": "",
                "Следующая попытка": "",
                "Ошибка": "",
                "Внешний ID": "",
            },
        )
        return True

    def dispatch(self) -> dict[str, int]:
        table = self.settings.airtable_table_notifications
        records = self.airtable.list_records(table, page_size=100)
        stats = {"sent": 0, "failed": 0, "skipped": 0}
        now = datetime.now(MSK)

        for record in records:
            fields = record.get("fields", {})
            status = str(fields.get("Статус") or STATUS_PENDING)
            if status not in (STATUS_PENDING, STATUS_ERROR, STATUS_SENDING):
                stats["skipped"] += 1
                continue

            attempts = int(fields.get("Попытки") or 0)
            if attempts >= self.settings.outbox_max_attempts:
                stats["skipped"] += 1
                continue

            next_attempt = self._parse_dt(fields.get("Следующая попытка"))
            if next_attempt and next_attempt > now:
                stats["skipped"] += 1
                continue

            record_id = record["id"]
            channel = str(fields.get("Канал") or "")
            recipient = str(fields.get("Получатель") or "")
            message = str(fields.get("Содержание") or "")
            subject = str(fields.get("Событие") or "SCHEME-B2B")

            try:
                attempt_time = datetime.now(MSK)
                lease_until = attempt_time + timedelta(seconds=self.settings.outbox_lease_seconds)
                self.airtable.update_record(
                    table,
                    record_id,
                    {
                        "Статус": STATUS_SENDING,
                        "Попытки": attempts + 1,
                        "Последняя попытка": attempt_time.isoformat(timespec="seconds"),
                        "Следующая попытка": lease_until.isoformat(timespec="seconds"),
                        "Ошибка": "",
                    },
                )

                external_id = self._deliver(channel, recipient, message, subject)

                self.airtable.update_record(
                    table,
                    record_id,
                    {
                        "Статус": STATUS_SENT,
                        "Дата отправки": datetime.now(MSK).isoformat(timespec="seconds"),
                        "Следующая попытка": "",
                        "Ошибка": "",
                        "Внешний ID": external_id,
                    },
                )
                stats["sent"] += 1

            except Exception as exc:
                base_delay = self.settings.outbox_backoff_base_seconds * (2**attempts)
                jitter = random.uniform(-self.settings.outbox_jitter_ratio, self.settings.outbox_jitter_ratio)
                next_time = datetime.now(MSK) + timedelta(seconds=max(1, base_delay * (1 + jitter)))
                self.airtable.update_record(
                    table,
                    record_id,
                    {
                        "Статус": STATUS_ERROR,
                        "Следующая попытка": next_time.isoformat(timespec="seconds"),
                        "Ошибка": str(exc)[:2000],
                    },
                )
                stats["failed"] += 1

        return stats

    def _deliver(self, channel: str, recipient: str, message: str, subject: str) -> str:
        if channel == CHANNEL_MAX:
            return self._send_max(recipient, message)
        if channel == CHANNEL_EMAIL:
            self._send_email(recipient, message, subject)
            return ""
        raise ValueError(f"Неизвестный канал уведомления: {channel}")

    def _send_max(self, recipient: str, message: str) -> str:
        if not self.settings.max_bot_token:
            raise RuntimeError("MAX бот не настроен")
        if not recipient:
            raise RuntimeError("MAX получатель не задан")

        message = message if len(message) <= 4000 else message[:3990] + "\n[сообщение сокращено]"
        target = recipient.strip()

        if target.startswith("chat:"):
            params = {"chat_id": int(target.removeprefix("chat:"))}
        else:
            params = {"user_id": int(target.removeprefix("user:"))}

        response = httpx.post(
            f"{self.settings.max_api_base.rstrip('/')}/messages",
            params=params,
            headers={"Authorization": self.settings.max_bot_token},
            json={"text": message},
            timeout=self.settings.max_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        message_obj = payload.get("message", {})
        return str(message_obj.get("id") or "")

    def _send_email(self, recipient: str, message: str, subject: str) -> None:
        if not recipient:
            raise RuntimeError("Email получатель не задан")
        if not self.settings.smtp_host or not self.settings.smtp_from:
            raise RuntimeError("SMTP не настроен")

        mail = EmailMessage()
        mail["From"] = self.settings.smtp_from
        mail["To"] = recipient
        mail["Subject"] = f"SCHEME-B2B: {subject}"
        mail.set_content(message)

        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=20) as server:
            if self.settings.smtp_starttls:
                server.starttls()
            if self.settings.smtp_username:
                server.login(self.settings.smtp_username, self.settings.smtp_password)
            server.send_message(mail)

    @staticmethod
    def _parse_dt(value: object) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=MSK)
            return parsed.astimezone(MSK)
        except ValueError:
            return None
