import logging
import smtplib
from email.message import EmailMessage
from typing import Optional
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

        message.add_alternative(
            html,
            subtype="html",
        )

        self._send(message)

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
