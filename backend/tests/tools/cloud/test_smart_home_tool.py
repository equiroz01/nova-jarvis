"""Tests for the smart home tools (list_smart_devices, control_device)."""

from unittest.mock import patch, MagicMock

import pytest


class TestListSmartDevices:
    @patch("app.tools.cloud.smart_home_tool.requests.get")
    def test_should_ReturnDevices_when_HAResponds(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value=[
                {
                    "entity_id": "light.living_room",
                    "state": "on",
                    "attributes": {"friendly_name": "Living Room Light"},
                },
                {
                    "entity_id": "switch.bedroom_fan",
                    "state": "off",
                    "attributes": {"friendly_name": "Bedroom Fan"},
                },
                {
                    "entity_id": "sensor.temperature",
                    "state": "72",
                    "attributes": {"friendly_name": "Temp Sensor"},
                },
            ]),
        )
        mock_get.return_value.raise_for_status = MagicMock()

        from app.tools.cloud.smart_home_tool import list_smart_devices
        result = list_smart_devices.invoke({})

        assert "Living Room Light" in result
        assert "Bedroom Fan" in result
        # sensor.temperature should be filtered out (not in device_types)
        assert "Temp Sensor" not in result

    @patch("app.tools.cloud.smart_home_tool.requests.get")
    def test_should_ReturnNoDevices_when_HAHasNoMatchingDevices(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value=[
                {"entity_id": "sensor.only", "state": "42", "attributes": {}},
            ]),
        )
        mock_get.return_value.raise_for_status = MagicMock()

        from app.tools.cloud.smart_home_tool import list_smart_devices
        result = list_smart_devices.invoke({})

        assert "No smart devices" in result

    @patch("app.tools.cloud.smart_home_tool.requests.get")
    def test_should_LimitTo20_when_ManyDevicesExist(self, mock_get):
        devices = [
            {
                "entity_id": f"light.device_{i}",
                "state": "on",
                "attributes": {"friendly_name": f"Light {i}"},
            }
            for i in range(30)
        ]
        mock_get.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value=devices)
        )
        mock_get.return_value.raise_for_status = MagicMock()

        from app.tools.cloud.smart_home_tool import list_smart_devices
        result = list_smart_devices.invoke({})

        # Should contain "30 total" in the header but only 20 device lines
        assert "30 total" in result
        assert result.count("- ") == 20

    @patch("app.tools.cloud.smart_home_tool.requests.get")
    def test_should_ReturnError_when_HAUnreachable(self, mock_get):
        mock_get.side_effect = ConnectionError("connection refused")

        from app.tools.cloud.smart_home_tool import list_smart_devices
        result = list_smart_devices.invoke({})

        assert "Error" in result

    @patch("app.tools.cloud.smart_home_tool.settings")
    def test_should_ReturnConfigMessage_when_HANotConfigured(self, mock_settings):
        mock_settings.home_assistant_url = None
        mock_settings.home_assistant_token = None

        from app.tools.cloud.smart_home_tool import list_smart_devices
        result = list_smart_devices.invoke({})

        assert "not configured" in result.lower()

    @patch("app.tools.cloud.smart_home_tool.settings")
    def test_should_ReturnConfigMessage_when_TokenMissing(self, mock_settings):
        mock_settings.home_assistant_url = "http://ha.local:8123"
        mock_settings.home_assistant_token = None

        from app.tools.cloud.smart_home_tool import list_smart_devices
        result = list_smart_devices.invoke({})

        assert "not configured" in result.lower()

    @patch("app.tools.cloud.smart_home_tool.requests.get")
    def test_should_UseFriendlyName_when_Available(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value=[
                {
                    "entity_id": "light.kitchen",
                    "state": "on",
                    "attributes": {"friendly_name": "Kitchen Spotlight"},
                },
            ]),
        )
        mock_get.return_value.raise_for_status = MagicMock()

        from app.tools.cloud.smart_home_tool import list_smart_devices
        result = list_smart_devices.invoke({})

        assert "Kitchen Spotlight" in result

    @patch("app.tools.cloud.smart_home_tool.requests.get")
    def test_should_FallbackToEntityId_when_NoFriendlyName(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value=[
                {"entity_id": "light.raw_id", "state": "off", "attributes": {}},
            ]),
        )
        mock_get.return_value.raise_for_status = MagicMock()

        from app.tools.cloud.smart_home_tool import list_smart_devices
        result = list_smart_devices.invoke({})

        assert "light.raw_id" in result


class TestControlDevice:
    @patch("app.tools.cloud.smart_home_tool.requests.post")
    def test_should_ReturnDone_when_ActionSucceeds(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.raise_for_status = MagicMock()

        from app.tools.cloud.smart_home_tool import control_device
        result = control_device.invoke({
            "entity_id": "light.living_room",
            "action": "turn_on",
        })

        assert "Done" in result
        assert "turn_on" in result
        assert "light.living_room" in result

    @patch("app.tools.cloud.smart_home_tool.requests.post")
    def test_should_CallCorrectDomain_when_ActionOnSwitch(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.raise_for_status = MagicMock()

        from app.tools.cloud.smart_home_tool import control_device
        control_device.invoke({
            "entity_id": "switch.fan",
            "action": "toggle",
        })

        called_url = mock_post.call_args[0][0]
        assert "/api/services/switch/toggle" in called_url

    def test_should_ReturnInvalidAction_when_ActionNotAllowed(self):
        from app.tools.cloud.smart_home_tool import control_device
        result = control_device.invoke({
            "entity_id": "light.x",
            "action": "explode",
        })

        assert "Invalid action" in result
        assert "turn_on" in result

    @patch("app.tools.cloud.smart_home_tool.requests.post")
    def test_should_ReturnError_when_HAFails(self, mock_post):
        mock_post.side_effect = ConnectionError("timeout")

        from app.tools.cloud.smart_home_tool import control_device
        result = control_device.invoke({
            "entity_id": "light.x",
            "action": "turn_off",
        })

        assert "Error" in result

    @patch("app.tools.cloud.smart_home_tool.settings")
    def test_should_ReturnConfigMessage_when_HANotConfigured(self, mock_settings):
        mock_settings.home_assistant_url = None
        mock_settings.home_assistant_token = None

        from app.tools.cloud.smart_home_tool import control_device
        result = control_device.invoke({
            "entity_id": "light.x",
            "action": "turn_on",
        })

        assert "not configured" in result.lower()

    @patch("app.tools.cloud.smart_home_tool.requests.post")
    def test_should_AcceptTurnOff_when_ValidAction(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.raise_for_status = MagicMock()

        from app.tools.cloud.smart_home_tool import control_device
        result = control_device.invoke({
            "entity_id": "fan.ceiling",
            "action": "turn_off",
        })

        assert "Done" in result

    @patch("app.tools.cloud.smart_home_tool.requests.post")
    def test_should_AcceptToggle_when_ValidAction(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.raise_for_status = MagicMock()

        from app.tools.cloud.smart_home_tool import control_device
        result = control_device.invoke({
            "entity_id": "light.x",
            "action": "toggle",
        })

        assert "Done" in result

    @patch("app.tools.cloud.smart_home_tool.requests.post")
    def test_should_SendEntityIdInBody_when_Controlling(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.raise_for_status = MagicMock()

        from app.tools.cloud.smart_home_tool import control_device
        control_device.invoke({
            "entity_id": "light.test",
            "action": "turn_on",
        })

        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"] == {"entity_id": "light.test"}
