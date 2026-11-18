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
    monkeypatch.setattr(lifecycle, "sleep", lambda _: None)
    return manager


def instance(state):
    return {"Reservations": [{"Instances": [{"State": {"Name": state}}]}]}


def test_wait_for_capacity_and_readiness_and_stop_after_last_job(manager, monkeypatch):
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
    manager.ec2.stop_instances.assert_called_once()
