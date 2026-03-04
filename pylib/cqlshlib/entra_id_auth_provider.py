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
Microsoft Entra ID Authentication Provider for Apache Cassandra CQLSH and Python driver.

This module is shipped as part of CQLSH and provides an AuthProvider that acquires JWT
tokens from Microsoft Entra ID (formerly Azure AD) using MSAL for Python, then sends
them to Cassandra's EntraIdAuthenticator via SASL PLAIN mechanism.

Usage with CQLSH (via cqlshrc):
    [auth_provider]
    module = cqlshlib.entra_id_auth_provider
    classname = EntraIdAuthProvider
    tenant_id = your-tenant-id
    client_id = your-client-id
    client_secret = your-client-secret

Usage with cassandra-driver (Python):
    from cqlshlib.entra_id_auth_provider import EntraIdAuthProvider
    from cassandra.cluster import Cluster

    auth_provider = EntraIdAuthProvider(
        tenant_id='your-tenant-id',
        client_id='your-client-id',
        client_secret='your-client-secret'
    )
    cluster = Cluster(['cassandra-host'], auth_provider=auth_provider)
    session = cluster.connect()

Dependencies (install as needed based on auth flow):
    pip install msal                # For client credentials / ROPC flows
    pip install azure-identity      # For Managed Identity / DefaultAzureCredential
"""

import logging
import sys

try:
    import msal
except ImportError:
    msal = None

try:
    from azure.identity import (
        DefaultAzureCredential,
        ManagedIdentityCredential,
    )
except ImportError:
    DefaultAzureCredential = None
    ManagedIdentityCredential = None

from cassandra.auth import AuthProvider, Authenticator

logger = logging.getLogger(__name__)


def _str_to_bool(value):
    """
    Converts a value to boolean. Handles strings from cqlshrc config files
    where 'true', 'yes', '1' should be treated as True.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', 'yes', '1')
    return bool(value)


class EntraIdAuthProvider(AuthProvider):
    """
    Cassandra Python driver AuthProvider for Microsoft Entra ID authentication.

    Supports multiple authentication flows:
    1. Client Credentials (Service Principal) - via client_secret
    2. Username/Password (ROPC) - via username + password (dev/test only)
    3. Managed Identity - via use_managed_identity=True
    4. Default Azure Credential - via use_default_credential=True
    5. Pre-acquired token - via token parameter

    The provider sends a JWT access token to Cassandra's EntraIdAuthenticator
    using SASL PLAIN format where the password field contains the JWT.

    All parameters can be provided as keyword arguments from a cqlshrc
    [auth_provider] section — string values like 'true'/'false' are
    automatically coerced to booleans where needed.

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
        Password for ROPC flow (not recommended for production).
    scope : str, optional
        OAuth2 scope. Default: api://{client_id}/.default
    token : str, optional
        Pre-acquired JWT token.
    use_managed_identity : bool or str, optional
        Use Azure Managed Identity (for Azure-hosted applications).
    use_default_credential : bool or str, optional
        Use DefaultAzureCredential (auto-detects available credential).
    authority : str, optional
        Override the authority URL. Default: https://login.microsoftonline.com/{tenant_id}
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
        self.scope = scope or (("api://%s/.default" % client_id) if client_id else None)
        self.token = token
        self.use_managed_identity = _str_to_bool(use_managed_identity)
        self.use_default_credential = _str_to_bool(use_default_credential)
        self.authority = authority or (
            ("https://login.microsoftonline.com/%s" % tenant_id) if tenant_id else None
        )

        # MSAL application instances (lazy initialized)
        self._confidential_app = None
        self._public_app = None

        if kwargs:
            logger.debug("EntraIdAuthProvider: ignoring unknown kwargs: %s", list(kwargs.keys()))

    def new_authenticator(self, host):
        """Creates a new EntraIdAuthenticator for each connection."""
        return EntraIdAuthenticator(self)

    def acquire_token(self):
        """
        Acquires a JWT access token from Microsoft Entra ID.

        Returns the JWT access token string.
        Raises Exception if no auth method is configured or token acquisition fails.
        """
        # If a pre-acquired token was provided, use it directly
        if self.token:
            return self.token

        # Try DefaultAzureCredential (Azure.Identity)
        if self.use_default_credential:
            return self._acquire_with_default_credential()

        # Try Managed Identity
        if self.use_managed_identity:
            return self._acquire_with_managed_identity()

        # Try Client Credentials (MSAL)
        if self.client_secret:
            return self._acquire_with_client_credentials()

        # Try Username/Password ROPC (MSAL)
        if self.username and self.password:
            return self._acquire_with_username_password()

        raise Exception(
            "No Entra ID authentication method configured. Provide one of: "
            "client_secret, username/password, token, "
            "use_managed_identity=true, or use_default_credential=true"
        )

    def _acquire_with_client_credentials(self):
        """Client credentials flow using MSAL."""
        if msal is None:
            raise ImportError(
                "msal package is required for client credentials flow. "
                "Install with: pip install msal"
            )

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
            raise Exception("Failed to acquire Entra ID token (client credentials): %s" % error)

    def _acquire_with_username_password(self):
        """ROPC flow using MSAL. Not recommended for production."""
        if msal is None:
            raise ImportError(
                "msal package is required for username/password flow. "
                "Install with: pip install msal"
            )

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
            raise Exception("Failed to acquire Entra ID token (ROPC): %s" % error)

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

    SASL PLAIN format: authzId NUL authnId NUL password
    - authzId: empty
    - authnId: username (informational, identity is derived from JWT)
    - password: JWT access token from Entra ID
    """

    def __init__(self, provider):
        self.provider = provider

    def initial_response(self):
        """Returns the initial SASL PLAIN response containing the JWT token."""
        token = self.provider.acquire_token()
        authn_id = self.provider.username or "entra-token"

        # Build SASL PLAIN response: NUL + authnId + NUL + password(JWT)
        authn_id_bytes = authn_id.encode('utf-8')
        token_bytes = token.encode('utf-8')

        response = b'\x00' + authn_id_bytes + b'\x00' + token_bytes
        return response

    def evaluate_challenge(self, challenge):
        """SASL PLAIN has no challenge-response phase."""
        return None
