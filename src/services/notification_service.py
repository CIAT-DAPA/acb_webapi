from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .email_service import EmailService


class NotificationService:
    """
    Servicio encargado de construir y enviar notificaciones por correo.
    """

    def __init__(self):
        self.email_service = EmailService()

        templates_path = (
            Path(__file__)
            .resolve()
            .parent.parent
            / "templates"
            / "emails"
        )

        self.environment = Environment(
            loader=FileSystemLoader(templates_path),
            autoescape=select_autoescape(
                ["html", "xml"]
            ),
        )

    def send_notification(
        self,
        recipients: list[str],
        subject: str,
        template: str,
        context: dict[str, Any],
        text: str | None = None,
    ) -> None:
        """
        Método genérico para enviar una notificación.
        Envía una notificación utilizando una plantilla HTML.
        
                Args:
                    recipients: Destinatarios.
                    subject: Asunto.
                    template: Nombre de la plantilla.
                    context: Variables de la plantilla.
                    text: Versión en texto plano (opcional).
        """

        html = self._render_template(
            template,
            context,
        )

        self.email_service.send_email(
            recipients=recipients,
            subject=subject,
            html=html,
            text=text,
        )

    def review_requested(
        self,
        recipients: list[str],
        context: dict[str, Any],
    ) -> None:
        """
        Notifica que un boletín fue enviado a revisión.
        """

        self.send_notification(
            recipients=recipients,
            subject=f"Nuevo boletín para revisión: {context['bulletin_title']}",
            template="review_requested.html",
            context=context,
        )

    def review_approved(
        self,
        recipients: list[str],
        context: dict[str, Any],
    ) -> None:
        """
        Notifica que un boletín fue aprobado.
        """

        self.send_notification(
            recipients=recipients,
            subject=f"Boletín aprobado: {context['bulletin_title']}",
            template="review_approved.html",
            context=context,
        )

    def review_rejected(
        self,
        recipients: list[str],
        context: dict[str, Any],
    ) -> None:
        """
        Notifica que un boletín requiere cambios.
        """

        self.send_notification(
            recipients=recipients,
            subject=f"Boletín con observaciones: {context['bulletin_title']}",
            template="review_rejected.html",
            context=context,
        )

    def review_comment(
        self,
        recipients: list[str],
        context: dict[str, Any],
    ) -> None:
        """
        Notifica un nuevo comentario.
        """

        self.send_notification(
            recipients=recipients,
            subject=f"Nuevo comentario en {context['bulletin_title']}",
            template="review_comment.html",
            context=context,
        )

    def bulletin_published(
        self,
        recipients: list[str],
        context: dict[str, Any],
    ) -> None:
        """
        Notifica la publicación de un boletín.
        """

        self.send_notification(
            recipients=recipients,
            subject=f"Nuevo boletín publicado: {context['bulletin_title']}",
            template="bulletin_published.html",
            context=context,
        )

    def _render_template(
        self,
        template_name: str,
        context: dict[str, Any],
    ) -> str:
        """
        Renderiza una plantilla Jinja2.
        """

        template = self.environment.get_template(
            template_name
        )

        return template.render(**context)