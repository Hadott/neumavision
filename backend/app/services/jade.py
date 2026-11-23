"""Coordina el uso de una instancia de inferencia dedicada a Nina."""

import logging
from contextlib import contextmanager
from functools import cached_property
from threading import Lock, Thread
from time import monotonic, sleep

import boto3
import httpx
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.config import settings


logger = logging.getLogger(__name__)
CAPACITY_ERRORS = {"InsufficientInstanceCapacity", "InsufficientHostCapacity"}
IDLE_CHECK_SECONDS = 15
MANUAL_START_ATTEMPTS = 720
MANUAL_RETRY_SECONDS = 10


class JadeUnavailable(RuntimeError):
    pass


class MissionAlreadyRunning(RuntimeError):
    pass


class Jade:
    def __init__(self):
        self.lock = Lock()
        self.start_lock = Lock()
        self.missions: set[str] = set()
        self.stop_requested = False
        self.ready = False
        self.manual_start_phase: str | None = None
        self.manual_start_error: str | None = None
        self.idle_since: float | None = None

    @cached_property
    def ec2(self):
        return boto3.client("ec2", region_name=settings.jade_region, config=Config(
            connect_timeout=5, read_timeout=5, retries={"total_max_attempts": 2},
        ))

    def instance_state(self) -> str:
        result = self.ec2.describe_instances(InstanceIds=[settings.jade_instance_id])
        return result["Reservations"][0]["Instances"][0]["State"]["Name"]

    def service_ready(self) -> bool:
        try:
            response = httpx.get(settings.inference_url.rstrip("/") + "/health", timeout=3)
            return response.is_success and response.json().get("status") == "ok"
        except (httpx.RequestError, ValueError, AttributeError):
            return False

    def status(self) -> str:
        if settings.detector_mode != "remote":
            return "disabled"
        if not settings.jade_instance_id:
            return "up" if self.service_ready() else "unavailable"
        with self.lock:
            if self.manual_start_phase:
                return self.manual_start_phase
        try:
            state = self.instance_state()
        except (BotoCoreError, ClientError, IndexError, KeyError):
            logger.warning("No se pudo consultar el estado de Jade", exc_info=True)
            return "unknown"
        if state == "running":
            if self.service_ready():
                return "up"
            with self.lock:
                return "starting" if self.missions and not self.ready else "unavailable"
        return {
            "pending": "starting", "stopping": "stopping", "shutting-down": "stopping",
            "stopped": "down", "terminated": "down",
        }.get(state, "unknown")

    def stop_if_idle(self) -> None:
        timeout = settings.jade_idle_timeout_seconds
        if timeout == 0:
            return
        with self.lock:
            if self.missions or self.manual_start_phase:
                return
            try:
                state = self.instance_state()
                if state not in {"pending", "running"}:
                    self.idle_since = None
                    return
                now = monotonic()
                if self.idle_since is None:
                    self.idle_since = now
                if state == "running" and now - self.idle_since >= timeout:
                    self.ec2.stop_instances(InstanceIds=[settings.jade_instance_id])
                    self.stop_requested = True
                    self.idle_since = None
            except (BotoCoreError, ClientError, IndexError, KeyError):
                logger.exception("No se pudo comprobar o detener Jade por inactividad")

    def request_start(self) -> None:
        with self.lock:
            if self.manual_start_phase or self.missions:
                return
            self.manual_start_phase = "starting"
            self.manual_start_error = None
            Thread(target=self._manual_start, name="jade-start", daemon=True).start()

    def _manual_start(self) -> None:
        error_message = None
        try:
            with self.start_lock:
                self.wait_until_ready(manual=True)
        except JadeUnavailable as error:
            error_message = str(error)
        except (BotoCoreError, ClientError, IndexError, KeyError):
            logger.exception("No se pudo iniciar Jade desde la plataforma")
            error_message = "No se pudo preparar Jade en AWS."
        finally:
            with self.lock:
                self.manual_start_error = error_message
                self.manual_start_phase = None
                self.idle_since = monotonic()

    def wait_until_ready(self, *, manual: bool = False) -> None:
        deadline = monotonic() + settings.jade_start_timeout
        instance_ids = [settings.jade_instance_id]
        started = False
        capacity_failures = 0
        while monotonic() < deadline:
            state = self.instance_state()
            if state in {"shutting-down", "terminated"}:
                raise JadeUnavailable("La instancia de inferencia ya no está disponible.")
            if state == "stopped":
                self.stop_requested = False
                if not started:
                    try:
                        self.ec2.start_instances(InstanceIds=instance_ids)
                        started = True
                        if manual:
                            with self.lock:
                                self.manual_start_phase = "starting"
                            deadline = monotonic() + settings.jade_start_timeout
                    except ClientError as error:
                        if error.response["Error"]["Code"] not in CAPACITY_ERRORS:
                            raise
                        logger.warning("AWS no tiene capacidad para iniciar Jade. Se reintentará.")
                        if manual:
                            capacity_failures += 1
                            if capacity_failures >= MANUAL_START_ATTEMPTS:
                                raise JadeUnavailable(
                                    f"AWS sigue sin capacidad para encender Jade después de {MANUAL_START_ATTEMPTS} intentos."
                                ) from error
                            with self.lock:
                                self.manual_start_phase = "waiting_capacity"
                            sleep(MANUAL_RETRY_SECONDS)
                            deadline = monotonic() + settings.jade_start_timeout
                        else:
                            sleep(min(15, max(0, deadline - monotonic())))
                        continue
            if manual and state in {"pending", "running"}:
                with self.lock:
                    self.manual_start_phase = "starting"
            if state == "running" and not self.stop_requested and self.service_ready():
                return
            sleep(min(3, max(0, deadline - monotonic())))
        raise JadeUnavailable("El servicio de inferencia no estuvo listo a tiempo. Puedes reintentar el procesamiento.")

    @contextmanager
    def mission(self, mission_id: str):
        with self.lock:
            if self.manual_start_phase:
                raise JadeUnavailable("Jade está encendiéndose. Espera a que la inferencia esté lista.")
            if mission_id in self.missions:
                raise MissionAlreadyRunning("La misión ya se está procesando.")
            self.missions.add(mission_id)
            self.idle_since = None
        try:
            with self.start_lock:
                if not self.ready:
                    try:
                        self.wait_until_ready()
                    except (BotoCoreError, ClientError) as error:
                        logger.exception("No se pudo iniciar Jade")
                        raise JadeUnavailable("AWS no permitió preparar la instancia de inferencia.") from error
                    self.ready = True
            yield
        finally:
            with self.lock:
                self.missions.remove(mission_id)
                if not self.missions:
                    self.ready = False
                    self.idle_since = monotonic()


jade = Jade()
