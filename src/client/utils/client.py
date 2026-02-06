import socket
import ssl
import time
import platform
from src.client.utils.config import logger  # reuse your logger setup


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
        self._send_line("hello from agent")

        buf = b""
        try:
            while self.running:
                chunk = self.sock.recv(4096)
                if not chunk:
                    logger.debug("[agent] Server disconnected")
                    break

                buf += chunk

                ### replace this to a single line
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    cmd = line.decode("utf-8", errors="replace").strip()
                    if cmd:
                        self._handle_command(cmd)
        except KeyboardInterrupt:
            logger.debug("[agent] CTRL+C pressed, exiting")
        except Exception as e:
            logger.debug("[agent] Unexpected error %s", e)
        finally:
            self.close()

    def _handle_command(self, cmd):
        logger.info("[agent] Received command: %r", cmd)

        # Allow-list dispatch (SAFE)
        if cmd == "help":
            self._send_line(
                "commands: help, ping, os, time, echo <text>, quit"
            )

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


#if __name__ == "__main__":
    # Example:
    # python agent.py 127.0.0.1 1337 server.crt
#    import argparse

#    parser = argparse.ArgumentParser(description="Safe TLS agent client (allow-listed commands).")
#    parser.add_argument("host")
#    parser.add_argument("port", type=int)
#    parser.add_argument("cafile", help="CA/cert file used to verify the server (e.g. server.crt for self-signed)")
#    args = parser.parse_args()

#    agent = AgentClient(args.host, args.port, args.cafile)
#    agent.connect()
#    agent.run()
