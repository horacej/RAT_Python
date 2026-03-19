import os
from client.utils.config import logger
from utils.socket_utils import readline

class FileUtils:

    def _recv_exact(self, sock, n):
        data = b""
        while len(data) < n:
            chunk = sock.recv(n - len(data))
            if not chunk:
                raise ConnectionError("Socket closed while receiving data")
            data += chunk
        return data

    def _recv_line(self, sock):
        buf = b""
        while True:
            ch = sock.recv(1)
            if not ch:
                raise ConnectionError("Socket closed while receiving line")
            if ch == b"\n":
                return buf
            buf += ch

    @staticmethod
    def send_file(sock, filepath):
        with open(filepath, "rb") as f:
            content = f.read()

        size = len(content)
        filename = filepath.split("/")[-1]

        header = f"SEND_FILE {filename}\n".encode() + str(size).encode("ascii") + b"\n"

        try:
            sock.sendall(header + content)
        except Exception as e:
            logger.debug("[agent] Error in sending file %s", e)

    @staticmethod
    def download_file(sock, filename):
        logger.debug("Downloading File %s", filename)

        size_line = readline(sock).decode("ascii", errors="strict").strip()
        logger.debug(f"size_line: {size_line}")
        if not size_line.isdigit():
            raise ValueError(f"Invalid size: {size_line!r}")

        size = int(size_line)

        content = FileUtils()._recv_exact(sock, size)

        out_path = os.path.join(os.getcwd(), filename)
        with open(out_path, "wb") as f:
            f.write(content)

        return out_path
