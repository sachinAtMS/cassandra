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
Tests for cassandra_entra_id_auth package.
"""

import pytest
from unittest.mock import patch, MagicMock

from cassandra_entra_id_auth import EntraIdAuthProvider, EntraIdAuthenticator


TENANT_ID = "test-tenant-id"
CLIENT_ID = "test-client-id"
CLIENT_SECRET = "test-client-secret"
USERNAME = "user@test.com"
PASSWORD = "test-password"
FAKE_TOKEN = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.fake"


class TestEntraIdAuthProvider:
    """Tests for EntraIdAuthProvider."""

    def test_constructor_client_credentials(self):
        provider = EntraIdAuthProvider(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
        )
        assert provider.tenant_id == TENANT_ID
        assert provider.client_id == CLIENT_ID
        assert provider.client_secret == CLIENT_SECRET
        assert provider.scope == f"api://{CLIENT_ID}/.default"

    def test_constructor_username_password(self):
        provider = EntraIdAuthProvider(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            username=USERNAME,
            password=PASSWORD,
        )
        assert provider.username == USERNAME
        assert provider.password == PASSWORD

    def test_constructor_custom_scope(self):
        custom_scope = "https://custom.scope/.default"
        provider = EntraIdAuthProvider(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            scope=custom_scope,
        )
        assert provider.scope == custom_scope

    def test_constructor_custom_authority(self):
        custom_authority = "https://login.microsoftonline.com/common"
        provider = EntraIdAuthProvider(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            authority=custom_authority,
        )
        assert provider.authority == custom_authority

    def test_constructor_managed_identity(self):
        provider = EntraIdAuthProvider(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            use_managed_identity=True,
        )
        assert provider.use_managed_identity is True

    def test_constructor_default_credential(self):
        provider = EntraIdAuthProvider(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            use_default_credential=True,
        )
        assert provider.use_default_credential is True

    def test_constructor_str_to_bool(self):
        """Test that string 'true'/'false' from cqlshrc is parsed correctly."""
        provider = EntraIdAuthProvider(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            use_managed_identity='true',
            use_default_credential='false',
        )
        assert provider.use_managed_identity is True
        assert provider.use_default_credential is False

    def test_constructor_pre_acquired_token(self):
        provider = EntraIdAuthProvider(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            token=FAKE_TOKEN,
        )
        assert provider.acquire_token() == FAKE_TOKEN

    def test_new_authenticator_returns_instance(self):
        provider = EntraIdAuthProvider(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
        )
        auth = provider.new_authenticator(("127.0.0.1", 9042))
        assert isinstance(auth, EntraIdAuthenticator)

    def test_no_auth_method_raises(self):
        provider = EntraIdAuthProvider(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
        )
        with pytest.raises(Exception, match="No authentication method configured"):
            provider.acquire_token()

    def test_default_authority(self):
        provider = EntraIdAuthProvider(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
        )
        assert provider.authority == f"https://login.microsoftonline.com/{TENANT_ID}"

    def test_default_scope(self):
        provider = EntraIdAuthProvider(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
        )
        assert provider.scope == f"api://{CLIENT_ID}/.default"


class TestEntraIdAuthenticator:
    """Tests for EntraIdAuthenticator SASL PLAIN formatting."""

    def test_initial_response_format_with_token(self):
        """Test SASL PLAIN response: NUL + authnId + NUL + JWT."""
        provider = EntraIdAuthProvider(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            token=FAKE_TOKEN,
            username=USERNAME,
        )
        auth = EntraIdAuthenticator(provider)
        response = auth.initial_response()

        # Parse SASL PLAIN format
        parts = response.split(b'\x00')
        assert len(parts) == 3
        assert parts[0] == b''  # authzId (empty)
        assert parts[1] == USERNAME.encode('utf-8')  # authnId
        assert parts[2] == FAKE_TOKEN.encode('utf-8')  # password (JWT)

    def test_initial_response_default_authn_id(self):
        """When no username is set, authnId should be 'entra-token'."""
        provider = EntraIdAuthProvider(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            token=FAKE_TOKEN,
        )
        auth = EntraIdAuthenticator(provider)
        response = auth.initial_response()

        parts = response.split(b'\x00')
        assert parts[1] == b'entra-token'

    def test_evaluate_challenge_returns_none(self):
        provider = EntraIdAuthProvider(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            token=FAKE_TOKEN,
        )
        auth = EntraIdAuthenticator(provider)
        assert auth.evaluate_challenge(b'challenge') is None

    def test_on_authentication_success(self):
        """on_authentication_success should not raise."""
        provider = EntraIdAuthProvider(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            token=FAKE_TOKEN,
        )
        auth = EntraIdAuthenticator(provider)
        auth.on_authentication_success(None)  # Should not raise

    @patch('cassandra_entra_id_auth.provider.msal')
    def test_client_credentials_flow(self, mock_msal):
        """Test that client credentials flow calls MSAL correctly."""
        mock_app = MagicMock()
        mock_app.acquire_token_for_client.return_value = {"access_token": FAKE_TOKEN}
        mock_msal.ConfidentialClientApplication.return_value = mock_app

        provider = EntraIdAuthProvider(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
        )
        token = provider.acquire_token()

        assert token == FAKE_TOKEN
        mock_msal.ConfidentialClientApplication.assert_called_once()
        mock_app.acquire_token_for_client.assert_called_once()

    @patch('cassandra_entra_id_auth.provider.msal')
    def test_ropc_flow(self, mock_msal):
        """Test that ROPC flow calls MSAL correctly."""
        mock_app = MagicMock()
        mock_app.acquire_token_by_username_password.return_value = {"access_token": FAKE_TOKEN}
        mock_msal.PublicClientApplication.return_value = mock_app

        provider = EntraIdAuthProvider(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            username=USERNAME,
            password=PASSWORD,
        )
        token = provider.acquire_token()

        assert token == FAKE_TOKEN
        mock_app.acquire_token_by_username_password.assert_called_once()
