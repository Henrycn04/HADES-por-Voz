from __future__ import annotations

import contextlib
import os
import platform
import queue
import select
import sys
import threading
import time
try:
    import termios
    import tty
except ImportError:  # Windows
    termios = None  # type: ignore
    tty = None  # type: ignore
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class IdleInput:
    """Resultado del estado idle de HADES."""

    kind: str  # "chat" | "space_voice" | "wake_word" | "cancel"
    text: str = ""
    wake_score: float | None = None


class TerminalInputController:
    """Controla la barra de chat, activación por espacio, wake word y ESC.

    La regla central es que la barra espaciadora solo activa grabación cuando
    la línea de chat está vacía. Si el usuario ya escribió texto, el espacio se
    agrega al mensaje normalmente.
    """

    def __init__(self, enable_wake_word: bool = True):
        self.enable_wake_word = enable_wake_word
        self._is_windows = platform.system().lower() == "windows"
        if self._is_windows:
            import msvcrt  # type: ignore
            self._msvcrt = msvcrt
        else:
            self._msvcrt = None

    @contextlib.contextmanager
    def _raw_terminal(self):
        if self._is_windows or not sys.stdin.isatty():
            yield
            return
        fd = sys.stdin.fileno()
        if termios is None or tty is None:
            yield
            return
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            yield
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    def _read_key_nonblocking(self) -> str | None:
        if self._is_windows:
            if not self._msvcrt.kbhit():
                return None
            ch = self._msvcrt.getwch()
            # Teclas especiales en Windows llegan como prefijo \x00 o \xe0.
            if ch in ("\x00", "\xe0"):
                if self._msvcrt.kbhit():
                    self._msvcrt.getwch()
                return ""
            return ch

        if not sys.stdin.isatty():
            return None
        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if not ready:
            return None
        return sys.stdin.read(1)

    @staticmethod
    def _clear_line() -> None:
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    @staticmethod
    def _render_chat(buffer: str) -> None:
        sys.stdout.write("\r\033[KChat> " + buffer)
        sys.stdout.flush()

    def _start_wake_thread(self, wake_listener: Any | None, cancel_event: threading.Event) -> tuple[threading.Event, dict[str, float | None]]:
        wake_event = threading.Event()
        result: dict[str, float | None] = {"score": None}

        if not self.enable_wake_word or wake_listener is None:
            return wake_event, result

        def runner() -> None:
            try:
                score = wake_listener.wait_for_wake_word(cancel_event=cancel_event)
                if score is not None and not cancel_event.is_set():
                    result["score"] = float(score)
                    wake_event.set()
            except Exception as exc:
                # No detenemos la UI por un error de wake word; se puede seguir con chat/espacio.
                print(f"\n[WakeWord] No se pudo mantener escucha de wake word: {exc}")

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        return wake_event, result

    def wait_for_idle_input(self, wake_listener: Any | None = None) -> IdleInput:
        """Espera texto escrito, espacio en línea vacía o wake word.

        Retorna inmediatamente cuando ocurre una de las tres activaciones.
        ESC durante idle limpia la línea actual; si la línea ya está vacía, solo
        permanece en idle.
        """
        if not sys.stdin.isatty():
            text = input("Chat> ").strip()
            return IdleInput(kind="chat", text=text) if text else IdleInput(kind="cancel")

        wake_cancel = threading.Event()
        wake_event, wake_result = self._start_wake_thread(wake_listener, wake_cancel)
        buffer = ""

        print("\n[HADES] Idle: escribí y Enter | espacio en vacío = grabar | wake word | ESC cancela.")
        self._render_chat(buffer)

        try:
            with self._raw_terminal():
                while True:
                    if wake_event.is_set():
                        wake_cancel.set()
                        self._clear_line()
                        return IdleInput(kind="wake_word", wake_score=wake_result.get("score"))

                    ch = self._read_key_nonblocking()
                    if ch is None:
                        time.sleep(0.03)
                        continue
                    if ch == "":
                        continue

                    # ESC: cancela lo escrito y se queda en idle.
                    if ch == "\x1b":
                        buffer = ""
                        self._render_chat(buffer)
                        continue

                    # Enter: envía la línea si tiene contenido.
                    if ch in ("\r", "\n"):
                        text = buffer.strip()
                        if text:
                            wake_cancel.set()
                            self._clear_line()
                            print(f"Chat> {text}")
                            return IdleInput(kind="chat", text=text)
                        self._render_chat(buffer)
                        continue

                    # Backspace / delete.
                    if ch in ("\b", "\x7f"):
                        buffer = buffer[:-1]
                        self._render_chat(buffer)
                        continue

                    # Ctrl+C: se comporta como cancelación hacia menú por KeyboardInterrupt.
                    if ch == "\x03":
                        wake_cancel.set()
                        self._clear_line()
                        raise KeyboardInterrupt

                    # Espacio: solo activa voz si la barra de chat está vacía.
                    if ch == " " and not buffer:
                        wake_cancel.set()
                        self._clear_line()
                        return IdleInput(kind="space_voice")

                    # Caracter imprimible normal.
                    if ch.isprintable():
                        buffer += ch
                        self._render_chat(buffer)
        finally:
            wake_cancel.set()

    def escape_pressed(self) -> bool:
        """Revisa si se presionó ESC sin bloquear."""
        ch = self._read_key_nonblocking()
        return ch == "\x1b"

    def run_cancelable(
        self,
        label: str,
        func: Callable[[], Any],
        cancel_event: threading.Event | None = None,
        poll_interval: float = 0.05,
    ) -> tuple[Any, bool]:
        """Ejecuta una operación en background y permite cancelarla con ESC.

        Devuelve (resultado, cancelado). Algunas operaciones externas, como una
        llamada HTTP al LLM, no pueden interrumpirse físicamente de inmediato;
        en ese caso HADES ignora el resultado y vuelve a idle cuando el usuario
        presiona ESC.
        """
        cancel_event = cancel_event or threading.Event()
        done = threading.Event()
        result_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

        def runner() -> None:
            try:
                result_queue.put(("ok", func()))
            except Exception as exc:
                result_queue.put(("error", exc))
            finally:
                done.set()

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()

        print(f"[HADES] {label} en proceso. Presioná ESC para cancelar.")

        with self._raw_terminal():
            while not done.is_set():
                if self.escape_pressed():
                    cancel_event.set()
                    self._clear_line()
                    print(f"[HADES] Cancelado durante {label}. Vuelvo a idle.")
                    return None, True
                time.sleep(poll_interval)

        status, value = result_queue.get() if not result_queue.empty() else ("ok", None)
        if cancel_event.is_set():
            return None, True
        if status == "error":
            raise value
        return value, False
