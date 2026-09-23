import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path


APP_FOLDER = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Aspiradora Xiaomi"
LOCK_PATH = APP_FOLDER / "robot-command.lock"


class RobotBusyError(RuntimeError):
    pass


class LegacyWriteBlocked(RuntimeError):
    pass


class ProcessLease:
    """Bloqueo entre GUI y Scheduler. Se libera al cerrar el proceso."""

    def __init__(self, path=LOCK_PATH):
        self.path = Path(path)
        self._fh = None
        self._locked = False

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = self.path.open("a+b")
        try:
            fh.seek(0, os.SEEK_END)
            if fh.tell() == 0:
                fh.write(b"0")
                fh.flush()
            fh.seek(0)
            if os.name == "nt":
                import msvcrt
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    raise RobotBusyError(
                        "Otro proceso de Aspiradora Xiaomi está controlando el robot."
                    ) from exc
            else:
                import fcntl
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    raise RobotBusyError(
                        "Otro proceso de Aspiradora Xiaomi está controlando el robot."
                    ) from exc
        except Exception:
            fh.close()
            raise
        self._fh = fh
        self._locked = True
        return True

    def release(self):
        fh = self._fh
        if fh is None:
            return
        try:
            fh.seek(0)
            if os.name == "nt":
                import msvcrt
                try:
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
        finally:
            self._locked = False
            self._fh = None
            try:
                fh.close()
            except Exception:
                pass


@dataclass
class CommandSession:
    purpose: str
    source: str
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: float = field(default_factory=time.monotonic)
    cancel_action: str | None = None
    finished: bool = False
    finish_reason: str | None = None


class RobotCommandArbiter:
    """Un único dueño de escritura por robot y por proceso."""

    def __init__(self):
        self._lock = threading.RLock()
        self._io_lock = threading.RLock()
        self._lease = None
        self._session = None
        self._audit = []
        self._legacy_blocks = 0
        self._last_legacy_block = None

    @property
    def active(self):
        with self._lock:
            return self._session is not None and not self._session.finished

    @property
    def session(self):
        with self._lock:
            return self._session

    def begin(self, purpose, source):
        with self._lock:
            if self.active:
                current = self._session
                raise RobotBusyError(
                    f"El robot ya está ocupado por {current.purpose} ({current.source})."
                )
            lease = ProcessLease()
            lease.acquire()
            session = CommandSession(str(purpose), str(source))
            self._lease = lease
            self._session = session
            self.record("session_begin", {
                "session": session.session_id,
                "purpose": session.purpose,
                "source": session.source,
            })
            return session

    def request_cancel(self, action="stop"):
        action = str(action or "stop")
        if action not in ("stop", "dock"):
            raise ValueError("Cancelación inválida")
        with self._lock:
            if not self.active:
                return False
            self._session.cancel_action = action
            self.record("cancel_requested", {
                "session": self._session.session_id,
                "action": action,
            })
            return True

    def finish(self, session, reason):
        with self._lock:
            if self._session is not session:
                return False
            session.finished = True
            session.finish_reason = str(reason)
            self.record("session_finish", {
                "session": session.session_id,
                "reason": str(reason),
            })
            lease = self._lease
            self._lease = None
            self._session = None
        if lease is not None:
            lease.release()
        return True

    def record(self, kind, detail=None):
        row = {
            "t": round(time.monotonic(), 3),
            "kind": str(kind),
            "detail": dict(detail or {}),
        }
        with self._lock:
            self._audit = (self._audit + [row])[-160:]
        return row

    def audit_snapshot(self):
        with self._lock:
            return list(self._audit)

    def note_legacy_block(self, kind, siid=None, iid=None, value=None):
        detail = {
            "kind": str(kind),
            "siid": siid,
            "iid": iid,
            "value": repr(value)[:180],
            "session": getattr(self._session, "session_id", None),
        }
        with self._lock:
            self._legacy_blocks += 1
            self._last_legacy_block = detail
        self.record("legacy_write_blocked", detail)

    @property
    def legacy_blocks(self):
        with self._lock:
            return int(self._legacy_blocks)

    @property
    def last_legacy_block(self):
        with self._lock:
            return dict(self._last_legacy_block or {})


# Escrituras de navegación/limpieza que nunca deben salir de código heredado.
_NAV_ACTIONS = {
    (2, 1), (2, 2), (2, 3), (2, 5), (2, 6),
    (3, 1),
    (7, 3), (7, 7),
    (9, 1), (9, 3), (9, 6), (9, 8), (9, 9),
    (10, 11), (10, 17),
}
_NAV_PROPERTIES = {
    (2, 4),   # modo
    (2, 8),   # sweep type
    (7, 1),   # repetición
    (7, 5),   # succión
    (7, 6),   # agua
    (7, 16),  # remoto
    (8, 10),  # doble pasada
    (9, 2),   # zona
    (9, 5),   # punto
}


class ReadMostlyMiotProxy:
    """Proxy para código heredado.

    Las lecturas siempre pasan. Las escrituras de navegación quedan bloqueadas
    permanentemente; durante una sesión fresh-core se bloquea cualquier escritura.
    """

    def __init__(self, raw_device, arbiter):
        self._raw_device = raw_device
        self._arbiter = arbiter

    def get_property_by(self, *args, **kwargs):
        return self._raw_device.get_property_by(*args, **kwargs)

    def info(self, *args, **kwargs):
        return self._raw_device.info(*args, **kwargs)

    def send(self, command, *args, **kwargs):
        command = str(command or "")
        if command != "get_properties":
            self._arbiter.note_legacy_block("send", value=command)
            raise LegacyWriteBlocked(
                f"Fresh Core bloqueó transporte heredado no-lectura: send({command})."
            )
        return self._raw_device.send(command, *args, **kwargs)

    def set_property_by(self, siid, piid, value, *args, **kwargs):
        key = (int(siid), int(piid))
        if self._arbiter.active or key in _NAV_PROPERTIES:
            self._arbiter.note_legacy_block(
                "property",
                siid=key[0],
                iid=key[1],
                value=value,
            )
            raise LegacyWriteBlocked(
                f"Fresh Core bloqueó propiedad heredada {key[0]}/{key[1]}."
            )
        return self._raw_device.set_property_by(
            siid,
            piid,
            value,
            *args,
            **kwargs,
        )

    def call_action_by(self, siid, aiid, params=None, *args, **kwargs):
        key = (int(siid), int(aiid))
        if self._arbiter.active or key in _NAV_ACTIONS:
            self._arbiter.note_legacy_block(
                "action",
                siid=key[0],
                iid=key[1],
                value=params,
            )
            raise LegacyWriteBlocked(
                f"Fresh Core bloqueó acción heredada {key[0]}/{key[1]}."
            )
        if params is None:
            return self._raw_device.call_action_by(
                siid,
                aiid,
                *args,
                **kwargs,
            )
        return self._raw_device.call_action_by(
            siid,
            aiid,
            params,
            *args,
            **kwargs,
        )

    def __getattr__(self, name):
        attr = getattr(self._raw_device, name)
        if callable(attr) and str(name).lower().startswith(
            ("set", "write", "action", "call_action", "send_")
        ):
            def blocked(*args, **kwargs):
                self._arbiter.note_legacy_block(
                    "dynamic_method",
                    value=str(name),
                )
                raise LegacyWriteBlocked(
                    f"Fresh Core bloqueó método heredado de escritura: {name}."
                )
            return blocked
        return attr


def install_read_mostly_proxy(vacuum, arbiter):
    current = getattr(vacuum, "device", None)
    if current is None:
        raise RuntimeError("El controlador Xiaomi no tiene transporte MIoT.")
    if isinstance(current, ReadMostlyMiotProxy):
        return current._raw_device
    raw = current
    vacuum.device = ReadMostlyMiotProxy(raw, arbiter)
    return raw
