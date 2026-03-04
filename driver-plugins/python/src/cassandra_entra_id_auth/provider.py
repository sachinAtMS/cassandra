# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Microsoft Entra ID AuthProvider and Authenticator for the DataStax Python
Cassandra driver.

This module provides:
  - ``EntraIdAuthProvider`` — implements ``cassandra.auth.AuthProvider``
  - ``EntraIdAuthenticator`` — implements ``cassandra.auth.Authenticator``

Supported authentication flows:
  1. Client Credentials (service principal) — via ``client_secret``
  2. Username/Password (ROPC) — via ``username`` + ``password`` (dev/test only)
  3. Managed Identity — via ``use_managed_identity=True``
  4. DefaultAzureCredential — via ``use_default_credential=True``
  5. Pre-acquired token — via ``token`` parameter

Wire format (SASL PLAIN):
  ``\\x00`` + authnId_bytes + ``\\x00`` + JWT_token_bytes
"""

import logging

try:
    import msal
except ImportError:
    msal = None

try:
    from azure.identity import (
        DefaultAzureCredential,
        ManagedIdentityCredential,
        ClientSecretCredential,
    )
except ImportError:
    DefaultAzureCredential = None
    ManagedIdentityCredential = None
    ClientSecretCredential = None

from cassandra.auth import AuthProvider, Authenticator

logger = logging.getLogger(__name__)


def _str_to_bool(value):
    """Convert string 'true'/'false' to bool (for cqlshrc config file compatibility)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', '1', 'yes')
    return bool(value)


class EntraIdAuthProvider(AuthProvider):
    """
    Cassandra Python driver AuthProvider for Microsoft Entra ID authentication.

    Acquires JWT tokens from Microsoft Entra ID using MSAL or Azure Identity
    and sends them to Cassandra's ``EntraIdAuthenticator`` using SASL PLAIN,
    where the password field contains the JWT access token.

    Parameters
    ----------
    tenant_id : str
        Microsoft Entra ID tenant ID (directory ID).
    client_id : str
        Application (client) ID registered in Entra ID.
    client_secret : str, optional
        Client secret for client credentials flow.
    username : str, optional
        Username for ROPC flow (not recommended for production).
    password : str, optional
        Password for ROPC flow.
    scope : str, optional
        OAuth2 scope. Default: ``api://{client_id}/.default``
    token : str, optional
        Pre-acquired JWT token.
    use_managed_identity : bool or str, optional
        Use Azure Managed Identity (for Azure-hosted applications).
    use_default_credential : bool or str, optional
        Use DefaultAzureCredential (auto-detects available credential).
    authority : str, optional
        Override the authority URL. Default: ``https://login.microsoftonline.com/{tenant_id}``

    Examples
    --------
    Client credentials (service principal)::

        auth_provider = EntraIdAuthProvider(
            tenant_id='your-tenant-id',
            client_id='your-client-id',
            client_secret='your-client-secret'
        )

    Managed Identity::

        auth_provider = EntraIdAuthProvider(
            tenant_id='your-tenant-id',
            client_id='your-client-id',
            use_managed_identity=True
        )

    DefaultAzureCredential::

        auth_provider = EntraIdAuthProvider(
            tenant_id='your-tenant-id',
            client_id='your-client-id',
            use_default_credential=True
        )
    """

    def __init__(self, tenant_id=None, client_id=None, client_secret=None,
                 username=None, password=None, scope=None, token=None,
                 use_managed_identity=False, use_default_credential=False,
                 authority=None, **kwargs):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.username = username
        self.password = password
        self.scope = scope or (f"api://{client_id}/.default" if client_id else None)
        self.token = token
        self.use_managed_identity = _str_to_bool(use_managed_identity)
        self.use_default_credential = _str_to_bool(use_default_credential)
        self.authority = authority or (
            f"https://login.microsoftonline.com/{tenant_id}" if tenant_id else None
        )

        # MSAL application instances (lazy initialized)
        self._confidential_app = None
        self._public_app = None

    def new_authenticator(self, host):
        """Creates a new EntraIdAuthenticator for each connection."""
        return EntraIdAuthenticator(self)

    def acquire_token(self):
        """
        Acquires a JWT access token from Microsoft Entra ID.

        Returns
        -------
        str
            The JWT access token.

        Raises
        ------
        Exception
            If token acquisition fails or no auth method is configured.
        """
        if self.token:
            return self.token

        if self.use_default_credential:
            return self._acquire_with_default_credential()

        if self.use_managed_identity:
            return self._acquire_with_managed_identity()

        if self.client_secret:
            return self._acquire_with_client_credentials()

        if self.username and self.password:
            return self._acquire_with_username_password()

        raise Exception(
            "No authentication method configured. Provide one of: "
            "client_secret, username/password, token, "
            "use_managed_identity=True, or use_default_credential=True"
        )

    def _acquire_with_client_credentials(self):
        """Client credentials flow using MSAL."""
        if msal is None:
            raise ImportError("msal package is required. Install with: pip install msal")

        if self._confidential_app is None:
            self._confidential_app = msal.ConfidentialClientApplication(
                self.client_id,
                authority=self.authority,
                client_credential=self.client_secret,
            )

        result = self._confidential_app.acquire_token_for_client(scopes=[self.scope])

        if "access_token" in result:
            logger.debug("Acquired token via client credentials flow")
            return result["access_token"]
        else:
            error = result.get("error_description", result.get("error", "Unknown error"))
            raise Exception(f"Failed to acquire token (client credentials): {error}")

    def _acquire_with_username_password(self):
        """ROPC flow using MSAL. Not recommended for production."""
        if msal is None:
            raise ImportError("msal package is required. Install with: pip install msal")

        if self._public_app is None:
            self._public_app = msal.PublicClientApplication(
                self.client_id,
                authority=self.authority,
            )

        result = self._public_app.acquire_token_by_username_password(
            username=self.username,
            password=self.password,
            scopes=[self.scope],
        )

        if "access_token" in result:
            logger.debug("Acquired token via ROPC flow for user: %s", self.username)
            return result["access_token"]
        else:
            error = result.get("error_description", result.get("error", "Unknown error"))
            raise Exception(f"Failed to acquire token (ROPC): {error}")

    def _acquire_with_managed_identity(self):
        """Managed Identity flow using azure-identity."""
        if ManagedIdentityCredential is None:
            raise ImportError(
                "azure-identity package is required for Managed Identity. "
                "Install with: pip install azure-identity"
            )
        credential = ManagedIdentityCredential(client_id=self.client_id)
        token = credential.get_token(self.scope)
        logger.debug("Acquired token via Managed Identity")
        return token.token

    def _acquire_with_default_credential(self):
        """DefaultAzureCredential flow using azure-identity."""
        if DefaultAzureCredential is None:
            raise ImportError(
                "azure-identity package is required for DefaultAzureCredential. "
                "Install with: pip install azure-identity"
            )
        credential = DefaultAzureCredential(tenant_id=self.tenant_id)
        token = credential.get_token(self.scope)
        logger.debug("Acquired token via DefaultAzureCredential")
        return token.token


class EntraIdAuthenticator(Authenticator):
    """
    SASL PLAIN authenticator that sends the Entra ID JWT as the password field.

    SASL PLAIN format::

        authzId NUL authnId NUL password

    Where:
      - authzId: empty
      - authnId: username or "entra-token" (informational; identity derived from JWT)
      - password: JWT access token from Entra ID
    """

    def __init__(self, provider):
        self.provider = provider

    def initial_response(self):
        """Returns the initial SASL PLAIN response containing the JWT token."""
        token = self.provider.acquire_token()
        authn_id = self.provider.username or "entra-token"

        authn_id_bytes = authn_id.encode('utf-8')
        token_bytes = token.encode('utf-8')

        return b'\x00' + authn_id_bytes + b'\x00' + token_bytes

    def evaluate_challenge(self, challenge):
        """SASL PLAIN has no challenge-response phase."""
        return None

    def on_authentication_success(self, token):
        """Called when authentication succeeds."""
        pass
