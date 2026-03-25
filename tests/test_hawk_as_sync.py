"""Tests camera and system functions."""

from unittest import mock
from unittest import IsolatedAsyncioTestCase
from json import dumps
import pytest
from blinkpy.blinkpy import Blink
from blinkpy.helpers.util import BlinkURLHandler
from blinkpy.sync_module import BlinkHawk
from blinkpy.camera import BlinkCameraHawk
from tests import mock_responses as mresp


@mock.patch("blinkpy.auth.Auth.query")
class TestBlinkSyncModule(IsolatedAsyncioTestCase):
    """Test BlinkSyncModule functions in blinkpy."""

    def setUp(self):
        """Set up Blink module."""
        self.blink = Blink(motion_interval=0, session=mock.AsyncMock())
        self.blink.last_refresh = 0
        self.blink.urls = BlinkURLHandler("test")
        response = {
            "name": "test",
            "id": 2,
            "serial": "foobar123",
            "enabled": True,
            "network_id": 1,
            "thumbnail": "/foo/bar",
        }
        self.blink.homescreen = {"hawks": [response]}
        self.blink.sync["test"] = BlinkHawk(self.blink, "test", "1234", response)
        self.blink.sync["test"].network_info = {"network": {"armed": True}}

    def tearDown(self):
        """Clean up after test."""
        self.blink = None

    def test_sync_attributes(self, mock_resp):
        """Test sync attributes."""
        self.assertEqual(self.blink.sync["test"].attributes["name"], "test")
        self.assertEqual(self.blink.sync["test"].attributes["network_id"], "1234")

    @pytest.mark.asyncio
    async def test_hawk_start(self, mock_resp):
        """Test hawk camera instantiation."""
        self.blink.last_refresh = None
        hawk = self.blink.sync["test"]
        self.assertTrue(await hawk.start())
        self.assertTrue("test" in hawk.cameras)
        self.assertEqual(hawk.cameras["test"].__class__, BlinkCameraHawk)

    @pytest.mark.asyncio
    async def test_hawk_camera_snooze(self, mock_resp):
        """Test hawk camera snooze."""
        self.blink.last_refresh = None
        hawk = self.blink.sync["test"]
        await hawk.start()
        camera = hawk.cameras["test"]
        
        # Test successful snooze
        mock_resp.return_value = mresp.MockResponse({}, 200)
        with mock.patch("blinkpy.api.request_camera_snooze", return_value=mock_resp.return_value) as mock_snooze:
            snooze_time = 240
            expected_data = dumps({"snooze_time": snooze_time})
            response = await camera.async_snooze(snooze_time)
            
            # Verify the API was called with correct parameters
            # Note: product_type is None because extract_config_info
            # overwrites __init__'s value with config.get("type")
            # which is absent from the homescreen hawk response.
            mock_snooze.assert_called_once_with(
                self.blink,
                camera.network_id,
                camera.camera_id,
                product_type=None,
                data=expected_data,
            )
            self.assertEqual(response.status, 200)

    @pytest.mark.asyncio
    async def test_hawk_camera_arm(self, mock_resp):
        """Test hawk camera arm and disarm."""
        self.blink.last_refresh = None
        hawk = self.blink.sync["test"]
        await hawk.start()
        camera = hawk.cameras["test"]
        with mock.patch(
            "blinkpy.api.wait_for_command", new_callable=mock.AsyncMock
        ) as mock_wait:
            mock_resp.side_effect = ["arm", "disarm"]
            mock_wait.side_effect = [True, True]
            self.assertEqual(await camera.async_arm(True), "arm")
            self.assertEqual(await camera.async_arm(False), "disarm")

    @pytest.mark.asyncio
    async def test_hawk_camera_record(self, mock_resp):
        """Test hawk camera clip recording."""
        self.blink.last_refresh = None
        hawk = self.blink.sync["test"]
        await hawk.start()
        camera = hawk.cameras["test"]
        with mock.patch(
            "blinkpy.api.wait_for_command", new_callable=mock.AsyncMock
        ) as mock_wait:
            mock_resp.return_value = "record"
            mock_wait.return_value = True
            self.assertEqual(await camera.record(), "record")

    @pytest.mark.asyncio
    async def test_hawk_camera_snap_picture(self, mock_resp):
        """Test hawk camera snap picture."""
        self.blink.last_refresh = None
        hawk = self.blink.sync["test"]
        await hawk.start()
        camera = hawk.cameras["test"]
        with mock.patch(
            "blinkpy.api.wait_for_command", new_callable=mock.AsyncMock
        ) as mock_wait:
            mock_resp.return_value = "snap"
            mock_wait.return_value = True
            self.assertEqual(await camera.snap_picture(), "snap")

    @pytest.mark.asyncio
    async def test_hawk_camera_liveview(self, mock_resp):
        """Test hawk camera liveview converts immis:// to rtsps://."""
        self.blink.last_refresh = None
        hawk = self.blink.sync["test"]
        await hawk.start()
        camera = hawk.cameras["test"]
        with mock.patch(
            "blinkpy.api.wait_for_command", new_callable=mock.AsyncMock
        ) as mock_wait:
            mock_resp.return_value = {"server": "immis://1.2.3.4:443/stream"}
            mock_wait.return_value = True
            result = await camera.get_liveview()
            self.assertEqual(result, "rtsps://1.2.3.4:443/stream")

    @pytest.mark.asyncio
    async def test_hawk_camera_liveview_rtsps(self, mock_resp):
        """Test hawk camera liveview with rtsps:// URL passthrough."""
        self.blink.last_refresh = None
        hawk = self.blink.sync["test"]
        await hawk.start()
        camera = hawk.cameras["test"]
        with mock.patch(
            "blinkpy.api.wait_for_command", new_callable=mock.AsyncMock
        ) as mock_wait:
            mock_resp.return_value = {"server": "rtsps://1.2.3.4:443/stream"}
            mock_wait.return_value = True
            result = await camera.get_liveview()
            self.assertEqual(result, "rtsps://1.2.3.4:443/stream")
