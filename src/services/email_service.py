import logging
import smtplib
import base64
import json
from email.message import EmailMessage
from typing import Optional
import urllib.request
import urllib.parse
import tools.config as config


logger = logging.getLogger(__name__)


class EmailService:
    """
    Servicio encargado del envío de correos electrónicos mediante SMTP.
    """

    def __init__(self):
        self.host = config.SMTP_HOST
        self.port = config.SMTP_PORT
        self.username = config.SMTP_USERNAME
        self.password = config.SMTP_PASSWORD

        self.from_email = config.SMTP_FROM
        self.from_name = config.SMTP_FROM_NAME
        self.use_tls = config.SMTP_TLS
        self.use_ssl = config.SMTP_SSL

        self.provider = config.EMAIL_PROVIDER

        # Solo necesario si provider = gmail_api
        self.gmail_client_id = config.GMAIL_CLIENT_ID
        self.gmail_client_secret = config.GMAIL_CLIENT_SECRET
        self.gmail_refresh_token = config.GMAIL_REFRESH_TOKEN

    def send_email(
        self,
        recipients: list[str],
        subject: str,
        html: str,
        text: Optional[str] = None,
    ) -> None:
        """
        Envía un correo electrónico.

        Args:
            recipients: Lista de destinatarios.
            subject: Asunto del correo.
            html: Contenido HTML.
            text: Contenido en texto plano (opcional).
        """

        recipients = [email.strip() for email in recipients if email.strip()]

        if not recipients:
            logger.warning("No valid recipients were provided.")
            return


        message = EmailMessage()

        message["Subject"] = subject
        message["From"] = f"{self.from_name} <{self.from_email}>"
        message["To"] = ", ".join(recipients)

        if text:
            message.set_content(text)
        else:
            message.set_content(
                "Este correo contiene contenido HTML. "
                "Por favor utilice un cliente compatible."
            )
        message.add_alternative(html, subtype="html")

        print(f"EmailService initialized with provider: {self.provider}")

        if self.provider == "gmail_api":
            self._send_via_gmail_api(message)
        else:
            self._send(message)

    def _get_gmail_access_token(self) -> str:
        """Obtiene un access token usando el refresh token de OAuth2."""
        data = urllib.parse.urlencode({
            "client_id": self.gmail_client_id,
            "client_secret": self.gmail_client_secret,
            "refresh_token": self.gmail_refresh_token,
            "grant_type": "refresh_token",
        }).encode()

        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=data,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read())
                return result["access_token"]
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            logger.error("Google OAuth error: %s", error_body)
            raise

    def _send_via_gmail_api(self, message: EmailMessage) -> None:
        """Envía usando la Gmail API REST (puerto 443)."""
        try:
            access_token = self._get_gmail_access_token()

            # Serializar el mensaje a bytes y encodear en base64 URL-safe
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

            body = json.dumps({"raw": raw}).encode()
            req = urllib.request.Request(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                data=body,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req) as resp:
                resp.read()

            logger.info("Email successfully sent to %s", message["To"])

        except Exception:
            logger.exception("Failed to send email to %s", message["To"])
            raise

    def _send(self, message: EmailMessage) -> None:
        """
        Envía un EmailMessage utilizando SMTP.

        Args:
            message: Mensaje previamente construido.
        """

        try:

            if self.use_ssl:

                with smtplib.SMTP_SSL(
                    self.host,
                    self.port,
                    timeout=30,
                ) as smtp:

                    smtp.login(
                        self.username,
                        self.password,
                    )

                    smtp.send_message(message)

            else:

                with smtplib.SMTP(
                    self.host,
                    self.port,
                    timeout=30
                ) as smtp:

                    smtp.ehlo()

                    if self.use_tls:
                        smtp.starttls()
                        smtp.ehlo()

                    smtp.login(
                        self.username,
                        self.password,
                    )

                    smtp.send_message(message)

            logger.info(
                "Email successfully sent to %s",
                message["To"],
            )

        except Exception:
            logger.exception(
                "Failed to send email to %s",
                message["To"],
            )
            raise
