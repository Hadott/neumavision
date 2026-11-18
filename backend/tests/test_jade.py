from unittest.mock import Mock

import httpx
import pytest
from botocore.exceptions import ClientError

from app.config import settings
from app.services import jade as lifecycle


@pytest.fixture
def manager(monkeypatch):
    manager = lifecycle.Jade()
    manager.ec2 = Mock()
    monkeypatch.setattr(settings, "jade_instance_id", "i-0123456789abcdef0")
    monkeypatch.setattr(settings, "detector_mode", "remote")
    monkeypatch.setattr(settings, "jade_idle_timeout_seconds", 1200)
    monkeypatch.setattr(lifecycle, "sleep", lambda _: None)
    return manager


def instance(state):
    return {"Reservations": [{"Instances": [{"State": {"Name": state}}]}]}


def test_wait_for_capacity_and_readiness_and_stop_after_idle(manager, monkeypatch):
    manager.ec2.describe_instances.side_effect = [
        instance("stopped"), instance("stopped"), instance("pending"),
        instance("running"), instance("running"),
    ]
    manager.ec2.start_instances.side_effect = [
        ClientError({"Error": {"Code": "InsufficientInstanceCapacity"}}, "StartInstances"),
        {},
    ]
    health = Mock(side_effect=[httpx.Response(503), httpx.Response(200, json={"status": "ok"})])
    monkeypatch.setattr(lifecycle.httpx, "get", health)

    with manager.mission("first"):
        with pytest.raises(lifecycle.MissionAlreadyRunning):
            with manager.mission("first"):
                pytest.fail("La misma misión no se puede procesar dos veces.")
        with manager.mission("second"):
            manager.ec2.stop_instances.assert_not_called()
        manager.ec2.stop_instances.assert_not_called()

    manager.ec2.stop_instances.assert_not_called()
    manager.ec2.describe_instances.side_effect = None
    manager.ec2.describe_instances.return_value = instance("running")
    finished = manager.idle_since
    monkeypatch.setattr(lifecycle, "monotonic", lambda: finished + 1199)
    manager.stop_if_idle()
    manager.ec2.stop_instances.assert_not_called()
    monkeypatch.setattr(lifecycle, "monotonic", lambda: finished + 1200)
    manager.stop_if_idle()

    assert manager.ec2.start_instances.call_count == 2
    assert health.call_count == 2
    manager.ec2.stop_instances.assert_called_once_with(InstanceIds=[settings.jade_instance_id])


def test_requests_arriving_after_shutdown_wait_for_fresh_boot(manager, monkeypatch):
    manager.stop_requested = True
    manager.ec2.describe_instances.side_effect = [
        instance("running"), instance("stopping"), instance("stopped"), instance("running"),
    ]
    health = Mock(return_value=httpx.Response(200, json={"status": "ok"}))
    monkeypatch.setattr(lifecycle.httpx, "get", health)

    with pytest.raises(RuntimeError, match="Falló la misión"):
        with manager.mission("failed"):
            assert manager.ec2.describe_instances.call_count == 4
            raise RuntimeError("Falló la misión")

    health.assert_called_once()
    manager.ec2.start_instances.assert_called_once()
    manager.ec2.stop_instances.assert_not_called()
    assert manager.idle_since is not None


def test_active_mission_resets_idle_window(manager, monkeypatch):
    manager.ec2.describe_instances.return_value = instance("running")
    monkeypatch.setattr(lifecycle.httpx, "get", Mock(return_value=httpx.Response(200, json={"status": "ok"})))
    clock = Mock(return_value=10)
    monkeypatch.setattr(lifecycle, "monotonic", clock)
    manager.stop_if_idle()
    with manager.mission("active"):
        clock.return_value = 1300
        manager.stop_if_idle()
        manager.ec2.stop_instances.assert_not_called()
    assert manager.idle_since == 1300
    clock.return_value = 2499
    manager.stop_if_idle()
    manager.ec2.stop_instances.assert_not_called()


def test_idle_shutdown_can_be_disabled(manager, monkeypatch):
    monkeypatch.setattr(settings, "jade_idle_timeout_seconds", 0)
    manager.idle_since = 0
    manager.stop_if_idle()
    manager.ec2.describe_instances.assert_not_called()
    manager.ec2.stop_instances.assert_not_called()


@pytest.mark.parametrize(("state", "expected"), [
    ("pending", "starting"),
    ("running", "up"),
    ("stopping", "stopping"),
    ("stopped", "down"),
])
def test_status_reports_ec2_and_readiness(manager, monkeypatch, state, expected):
    manager.ec2.describe_instances.return_value = instance(state)
    health = Mock(return_value=httpx.Response(200, json={"status": "ok"}))
    monkeypatch.setattr(lifecycle.httpx, "get", health)
    assert manager.status() == expected
    assert health.call_count == int(state == "running")


def test_running_instance_without_ready_service(manager, monkeypatch):
    manager.ec2.describe_instances.return_value = instance("running")
    monkeypatch.setattr(lifecycle.httpx, "get", Mock(return_value=httpx.Response(503)))
    assert manager.status() == "unavailable"
    manager.missions.add("starting")
    assert manager.status() == "starting"
