"""Optional HTTPS email transport for Railway plans without SMTP access."""
import hashlib
import json
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class ResendEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        if not settings.RESEND_API_KEY:
            raise ValueError("Falta RESEND_API_KEY")
        sent = 0
        for message in email_messages:
            payload = json.dumps({"from": message.from_email, "to": message.to, "subject": message.subject, "text": message.body}, ensure_ascii=False).encode("utf-8")
            req = Request("https://api.resend.com/emails", data=payload, headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}", "Content-Type": "application/json", "Idempotency-Key": hashlib.sha256(payload).hexdigest()}, method="POST")
            try:
                with urlopen(req, timeout=settings.EMAIL_TIMEOUT) as response:
                    if not json.load(response).get("id"):
                        raise ValueError("El proveedor no confirmó el correo")
                sent += 1
            except Exception:
                if not self.fail_silently:
                    raise
        return sent
