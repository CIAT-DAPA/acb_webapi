# services/keycloak_service.py
import os
import time
import requests
import tools.config as config
from typing import Optional, List, Dict

KEYCLOAK_URL = config.KEYCLOAK_URL
KEYCLOAK_REALM = config.KEYCLOAK_REALM
KEYCLOAK_CLIENT_ID = config.KEYCLOAK_CLIENT_ID
KEYCLOAK_CLIENT_SECRET = config.KEYCLOAK_CLIENT_SECRET


class KeycloakService:
    """
    Consulta datos de usuarios (como el email) directamente en Keycloak
    vía su Admin REST API, usando un client de tipo service-account.
    """

    def __init__(self):
        self._token = None
        self._token_expires_at = 0

    def _get_admin_token(self) -> str:
        # Reutiliza el token mientras siga vigente, para no pedir uno nuevo
        # en cada notificación
        if self._token and time.time() < self._token_expires_at:
            return self._token

        url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"

        response = requests.post(
            url,
            data={
                "grant_type": "client_credentials",
                "client_id": KEYCLOAK_CLIENT_ID,
                "client_secret": KEYCLOAK_CLIENT_SECRET,
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        self._token = data["access_token"]
        self._token_expires_at = time.time() + data["expires_in"] - 10  # margen
        return self._token

    @staticmethod
    def _slim_user(raw_user: dict) -> dict:
        """
        Se queda solo con los campos que realmente usamos para notificaciones.
        """
        return {
            "id": raw_user.get("id"),
            "first_name": raw_user.get("firstName"),
            "last_name": raw_user.get("lastName"),
            "email": raw_user.get("email"),
        }

    def get_all_keycloak_users(self) -> List[dict]:
        """
        Trae todos los usuarios del realm, paginando.
        Devuelve solo id, first_name, last_name, email por usuario.
        """
        token = self._get_admin_token()
        headers = {"Authorization": f"Bearer {token}"}

        all_users = []
        first = 0
        page_size = 500

        while True:
            url = f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/users"
            response = requests.get(
                url,
                headers=headers,
                params={"first": first, "max": page_size},
                timeout=15,
            )
            response.raise_for_status()
            page = response.json()

            if not page:
                break

            all_users.extend(self._slim_user(u) for u in page)
            first += page_size

            if len(page) < page_size:
                break  # última página

        return all_users

    def get_users_by_ext_ids(self, ext_ids: List[str]) -> Dict[str, dict]:
        """
        Trae todos los usuarios (una sola pasada paginada) y filtra
        localmente por ext_id. Devuelve {ext_id: {first_name, last_name, email}}.
        """
        ext_ids_set = set(ext_ids)
        all_users = self.get_all_keycloak_users()

        return {
            user["id"]: user
            for user in all_users
            if user["id"] in ext_ids_set
        }

    def get_user_by_ext_id(self, ext_id: str) -> Optional[dict]:
        return self.get_users_by_ext_ids([ext_id]).get(ext_id)

    def get_emails_by_ext_ids(self, ext_ids: List[str]) -> Dict[str, Optional[str]]:
        users = self.get_users_by_ext_ids(ext_ids)
        return {ext_id: data.get("email") for ext_id, data in users.items()}