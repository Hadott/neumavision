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


def test_admin_controls_auto_shutdown(manager, monkeypatch):
    from fastapi.testclient import TestClient

    from app import main
    from app.models import Faena
    from app.services.auth import get_current_faena

    monkeypatch.setattr(main, "jade", manager)
    monkeypatch.setattr(settings, "jade_idle_timeout_seconds", 0)
    monkeypatch.setattr(manager.ec2.describe_instances, "return_value", instance("running"))
    clock = Mock(return_value=100)
    monkeypatch.setattr(lifecycle, "monotonic", clock)
    actor = Faena(rol="faena")
    monkeypatch.setitem(main.app.dependency_overrides, get_current_faena, lambda: actor)
    client = TestClient(main.app)
    url = f"{settings.api_prefix}/inference/auto-shutdown"

    assert client.put(url, json={"enabled": True}).status_code == 403
    instance_url = f"{settings.api_prefix}/inference/instance"
    assert client.get(instance_url).status_code == 403
    actor.rol = "admin"
    assert client.put(url, json={"enabled": "true"}).status_code == 422
    assert client.put(url, json={"enabled": True, "idle_timeout_seconds": 86401}).status_code == 422
    assert client.put(url, json={"enabled": True}).json() == {"idle_timeout_seconds": 1200}
    manager.stop_if_idle()
    clock.return_value = 1300
    assert client.put(url, json={"enabled": False}).json() == {"idle_timeout_seconds": 0}
    manager.stop_if_idle()
    manager.ec2.stop_instances.assert_not_called()

    assert client.put(url, json={"enabled": True, "idle_timeout_seconds": 180}).json() == {"idle_timeout_seconds": 180}
    manager.stop_if_idle()
    clock.return_value = 1479
    manager.stop_if_idle()
    manager.ec2.stop_instances.assert_not_called()
    clock.return_value = 1480
    manager.stop_if_idle()
    manager.ec2.stop_instances.assert_called_once_with(InstanceIds=[settings.jade_instance_id])

    response = instance("stopped")
    response["Reservations"][0]["Instances"][0].update(
        InstanceType="g6.xlarge", Placement={"AvailabilityZone": "us-east-2a"},
    )
    manager.ec2.describe_instances.return_value = response
    manager.ec2.describe_instance_types.return_value = {"InstanceTypes": [{
        "VCpuInfo": {"DefaultVCpus": 4},
        "MemoryInfo": {"SizeInMiB": 16384},
        "GpuInfo": {"Gpus": [{"Name": "L4", "Count": 1, "MemoryInfo": {"SizeInMiB": 24576}}]},
    }]}
    details = client.get(instance_url).json()
    assert details["instance_type"] == "g6.xlarge"
    assert details["vcpus"] == 4
    assert details["memory_mib"] == 16384
    assert details["gpus"] == [{"name": "L4", "count": 1, "memory_mib": 24576}]
    manager.ec2.describe_instance_types.assert_called_once_with(InstanceTypes=["g6.xlarge"])

    manager.ec2.describe_instance_types.side_effect = ClientError(
        {"Error": {"Code": "UnauthorizedOperation"}}, "DescribeInstanceTypes",
    )
    details = client.get(instance_url).json()
    assert details["instance_type"] == "g6.xlarge"
    assert details["specifications_available"] is True
    assert details["specifications_url"].startswith("https://docs.aws.amazon.com/")
    assert details["local_storage_gb"] == 250

    response["Reservations"][0]["Instances"][0]["InstanceType"] = "g6.2xlarge"
    details = client.get(instance_url).json()
    assert details["instance_type"] == "g6.2xlarge"
    assert details["specifications_available"] is False


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


def test_manual_start_retries_capacity_without_stopping_jade(manager, monkeypatch):
    manager.ec2.describe_instances.side_effect = [
        instance("stopped"), instance("stopped"), instance("running"),
    ]
    manager.ec2.start_instances.side_effect = [
        ClientError({"Error": {"Code": "InsufficientInstanceCapacity"}}, "StartInstances"),
        {},
    ]
    monkeypatch.setattr(manager, "service_ready", lambda: True)
    phases = []

    def observe_retry(seconds):
        phases.append((seconds, manager.status()))
        if seconds != lifecycle.MANUAL_RETRY_SECONDS:
            return
        manager.request_start()
        manager.stop_if_idle()
        with pytest.raises(lifecycle.JadeUnavailable):
            with manager.mission("during-start"):
                pytest.fail("La misión debe esperar a que Jade esté lista.")

    monkeypatch.setattr(lifecycle, "sleep", observe_retry)
    manager.manual_start_phase = "starting"
    manager._manual_start()

    assert phases == [(lifecycle.MANUAL_RETRY_SECONDS, "waiting_capacity"), (3, "starting")]
    assert manager.ec2.start_instances.call_count == 2
    manager.ec2.stop_instances.assert_not_called()
    assert manager.manual_start_phase is None
    assert manager.manual_start_error is None


def test_manual_start_reports_exhausted_capacity(manager, monkeypatch):
    monkeypatch.setattr(lifecycle, "MANUAL_START_ATTEMPTS", 2)
    manager.ec2.describe_instances.return_value = instance("stopped")
    manager.ec2.start_instances.side_effect = ClientError(
        {"Error": {"Code": "InsufficientInstanceCapacity"}}, "StartInstances",
    )
    manager.manual_start_phase = "starting"
    manager._manual_start()

    assert manager.ec2.start_instances.call_count == 2
    assert manager.status() == "down"
    assert "sin capacidad" in manager.manual_start_error
