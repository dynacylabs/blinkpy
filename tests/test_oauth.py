"""Test OAuth v2 functionality."""

import pytest
from unittest import IsolatedAsyncioTestCase
from unittest.mock import Mock, AsyncMock, patch
from blinkpy.helpers.pkce import generate_pkce_pair
from blinkpy import api
from blinkpy.auth import Auth, BlinkTwoFARequiredError


def test_pkce_generation():
    """Test PKCE pair generation."""
    verifier, challenge = generate_pkce_pair()

    # Verify length requirements
    assert len(verifier) >= 43
    assert len(challenge) > 0

    # Verify they are different
    assert verifier != challenge

    # Verify URL-safe base64 (no padding)
    assert "=" not in verifier
    assert "=" not in challenge


def test_pkce_uniqueness():
    """Test that PKCE pairs are unique."""
    verifier1, challenge1 = generate_pkce_pair()
    verifier2, challenge2 = generate_pkce_pair()

    assert verifier1 != verifier2
    assert challenge1 != challenge2


class TestOAuthAPI(IsolatedAsyncioTestCase):
    """Test OAuth v2 API functions."""

    async def test_oauth_authorize_request(self):
        """Test OAuth authorization request."""
        auth = Mock()
        auth.session = Mock()

        response = Mock()
        response.status = 200
        auth.session.get = AsyncMock(return_value=response)

        hardware_id = "TEST-HARDWARE-ID"
        code_challenge = "test_challenge"

        result = await api.oauth_authorize_request(auth, hardware_id, code_challenge)

        self.assertTrue(result)
        auth.session.get.assert_called_once()

    async def test_oauth_get_signin_page(self):
        """Test getting signin page and extracting CSRF token."""
        auth = Mock()
        auth.session = Mock()

        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <script id="oauth-args" type="application/json">
            {"csrf-token": "test_csrf_token_123"}
            </script>
        </head>
        <body></body>
        </html>
        """

        response = Mock()
        response.status = 200
        response.text = AsyncMock(return_value=html_content)
        auth.session.get = AsyncMock(return_value=response)

        csrf_token = await api.oauth_get_signin_page(auth)

        self.assertEqual(csrf_token, "test_csrf_token_123")

    async def test_oauth_signin_success(self):
        """Test successful OAuth signin without 2FA."""
        auth = Mock()
        auth.session = Mock()

        response = Mock()
        response.status = 302
        auth.session.post = AsyncMock(return_value=response)

        result = await api.oauth_signin(
            auth, "test@example.com", "password", "csrf_token"
        )

        self.assertEqual(result, "SUCCESS")

    async def test_oauth_signin_2fa_required(self):
        """Test OAuth signin when 2FA is required."""
        auth = Mock()
        auth.session = Mock()

        response = Mock()
        response.status = 412
        auth.session.post = AsyncMock(return_value=response)

        result = await api.oauth_signin(
            auth, "test@example.com", "password", "csrf_token"
        )

        self.assertEqual(result, "2FA_REQUIRED")

    async def test_oauth_verify_2fa(self):
        """Test 2FA verification."""
        auth = Mock()
        auth.session = Mock()

        response = Mock()
        response.status = 201
        response.json = AsyncMock(return_value={"status": "auth-completed"})
        auth.session.post = AsyncMock(return_value=response)

        result = await api.oauth_verify_2fa(auth, "csrf_token", "123456")

        self.assertTrue(result)

    async def test_oauth_get_authorization_code(self):
        """Test getting authorization code from redirect."""
        auth = Mock()
        auth.session = Mock()

        response = Mock()
        response.status = 302
        response.headers = {
            "Location": "https://blink.com/end?code=AUTH_CODE_123&state=STATE"
        }
        auth.session.get = AsyncMock(return_value=response)

        code = await api.oauth_get_authorization_code(auth)

        self.assertEqual(code, "AUTH_CODE_123")

    async def test_oauth_exchange_code_for_token(self):
        """Test exchanging authorization code for access token."""
        auth = Mock()
        auth.session = Mock()

        token_response = {
            "access_token": "access_token_123",
            "refresh_token": "refresh_token_456",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        response = Mock()
        response.status = 200
        response.json = AsyncMock(return_value=token_response)
        auth.session.post = AsyncMock(return_value=response)

        result = await api.oauth_exchange_code_for_token(
            auth, "AUTH_CODE", "code_verifier", "hardware_id"
        )

        self.assertEqual(result, token_response)
        self.assertEqual(result["access_token"], "access_token_123")

    async def test_oauth_refresh_token(self):
        """Test refreshing access token."""
        auth = Mock()
        auth.session = Mock()

        token_response = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        response = Mock()
        response.status = 200
        response.json = AsyncMock(return_value=token_response)
        auth.session.post = AsyncMock(return_value=response)

        result = await api.oauth_refresh_token(
            auth, "old_refresh_token", "hardware_id"
        )

        self.assertEqual(result, token_response)
        self.assertEqual(result["access_token"], "new_access_token")


class TestOAuthAuth(IsolatedAsyncioTestCase):
    """Test OAuth v2 Auth class integration."""

    async def test_auth_process_token_data(self):
        """Test processing token data in Auth class."""
        auth = Auth({"username": "test@example.com", "password": "password"})

        token_data = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 7200,
        }

        with patch.object(auth, "get_tier_info", new=AsyncMock(return_value={})):
            await auth._process_token_data(token_data)

        self.assertEqual(auth.token, "test_access_token")
        self.assertEqual(auth.refresh_token, "test_refresh_token")
        self.assertEqual(auth.expires_in, 7200)
        self.assertIsNotNone(auth.expiration_date)

    async def test_auth_hardware_id_generation(self):
        """Test that hardware_id is generated if not provided."""
        auth = Auth({"username": "test@example.com", "password": "password"})

        self.assertIsNotNone(auth.hardware_id)
        self.assertGreater(len(auth.hardware_id), 0)

    async def test_auth_hardware_id_persistence(self):
        """Test that hardware_id is preserved from login_data."""
        hardware_id = "EXISTING-HARDWARE-ID"
        auth = Auth(
            {
                "username": "test@example.com",
                "password": "password",
                "hardware_id": hardware_id,
            }
        )

        self.assertEqual(auth.hardware_id, hardware_id)

    async def test_login_attributes_includes_hardware_id(self):
        """Test that login_attributes includes hardware_id."""
        auth = Auth({"username": "test@example.com", "password": "password"})

        attributes = auth.login_attributes

        self.assertIn("hardware_id", attributes)
        self.assertEqual(attributes["hardware_id"], auth.hardware_id)

    async def test_oauth_login_flow_raises_2fa_required(self):
        """Test that OAuth login flow raises BlinkTwoFARequiredError when 2FA needed."""
        auth = Auth({"username": "test@example.com", "password": "password"})

        with patch(
            "blinkpy.api.oauth_authorize_request",
            new=AsyncMock(return_value=True),
        ):
            with patch(
                "blinkpy.api.oauth_get_signin_page",
                new=AsyncMock(return_value="csrf_token"),
            ):
                with patch(
                    "blinkpy.api.oauth_signin",
                    new=AsyncMock(return_value="2FA_REQUIRED"),
                ):
                    with self.assertRaises(BlinkTwoFARequiredError):
                        await auth._oauth_login_flow()

                    self.assertTrue(hasattr(auth, "_oauth_csrf_token"))
                    self.assertTrue(hasattr(auth, "_oauth_code_verifier"))

    async def test_complete_2fa_login(self):
        """Test completing OAuth v2 login after 2FA."""
        auth = Auth({"username": "test@example.com", "password": "password"})

        auth._oauth_csrf_token = "test_csrf_token"
        auth._oauth_code_verifier = "test_code_verifier"

        with patch(
            "blinkpy.api.oauth_verify_2fa", new=AsyncMock(return_value=True)
        ):
            with patch(
                "blinkpy.api.oauth_get_authorization_code",
                new=AsyncMock(return_value="AUTH_CODE"),
            ):
                with patch(
                    "blinkpy.api.oauth_exchange_code_for_token",
                    new=AsyncMock(
                        return_value={
                            "access_token": "token_123",
                            "refresh_token": "refresh_456",
                            "expires_in": 3600,
                        }
                    ),
                ):
                    result = await auth.complete_2fa_login("123456")

                    self.assertTrue(result)
                    self.assertEqual(auth.token, "token_123")
                    self.assertEqual(auth.refresh_token, "refresh_456")
                    self.assertFalse(hasattr(auth, "_oauth_csrf_token"))
                    self.assertFalse(hasattr(auth, "_oauth_code_verifier"))
