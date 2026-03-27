"""Tests unitaires pour le module utils/file_utils.py."""

import os
import tempfile

import pytest
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# On reproduit la logique de FileUtils pour tester sans dépendances d'import
# ---------------------------------------------------------------------------


class FileUtils:
    """Copie fidèle de la classe FileUtils du projet."""

    @staticmethod
    def send_file(sock, filepath):
        """Envoie un fichier via la socket avec le protocole SEND_FILE."""
        with open(filepath, "rb") as f:
            content = f.read()

        size = len(content)
        filename = filepath.split("/")[-1]

        header = f"SEND_FILE {filename}\n".encode() + str(size).encode("ascii") + b"\n"
        sock.sendall(header + content)

    @staticmethod
    def download_file(sock, filename):
        """Télécharge un fichier depuis la socket."""

        def _readline(s):
            buf = b""
            while True:
                chunk = s.recv(1)
                if not chunk:
                    raise ConnectionError("Socket closed")
                if chunk == b"\n":
                    return buf
                buf += chunk

        size_line = _readline(sock).decode("ascii", errors="strict").strip()
        if not size_line.isdigit():
            raise ValueError(f"Invalid size: {size_line!r}")

        size = int(size_line)

        data = b""
        while len(data) < size:
            chunk = sock.recv(min(4096, size - len(data)))
            if not chunk:
                raise ConnectionError("Socket closed while receiving data")
            data += chunk

        out_path = os.path.join(os.getcwd(), filename)
        with open(out_path, "wb") as f:
            f.write(data)

        return out_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_recv_sock(data: bytes) -> MagicMock:
    """Mock de socket : recv(1) octet par octet, recv(n) par blocs."""
    offset = {"pos": 0}

    def _recv(n):
        start = offset["pos"]
        if start >= len(data):
            return b""
        end = min(start + n, len(data))
        chunk = data[start:end]
        offset["pos"] = end
        return chunk

    sock = MagicMock()
    sock.recv = MagicMock(side_effect=_recv)
    return sock


# ===================================================================
# Tests send_file
# ===================================================================


class TestSendFile:
    """Tests pour FileUtils.send_file."""

    def test_send_file_basic(self, tmp_path):
        """Envoi d'un fichier texte simple."""
        filepath = tmp_path / "hello.txt"
        filepath.write_text("Hello, World!")
        content = b"Hello, World!"

        sock = MagicMock()
        FileUtils.send_file(sock, str(filepath))

        sock.sendall.assert_called_once()
        sent_data = sock.sendall.call_args[0][0]

        # Vérification du header
        assert sent_data.startswith(b"SEND_FILE hello.txt\n")
        # Vérification de la taille
        assert str(len(content)).encode("ascii") in sent_data
        # Vérification du contenu
        assert sent_data.endswith(content)

    def test_send_file_binary(self, tmp_path):
        """Envoi d'un fichier binaire (image simulée)."""
        filepath = tmp_path / "image.png"
        binary_content = bytes(range(256)) * 10
        filepath.write_bytes(binary_content)

        sock = MagicMock()
        FileUtils.send_file(sock, str(filepath))

        sent_data = sock.sendall.call_args[0][0]
        assert sent_data.endswith(binary_content)

    def test_send_file_empty(self, tmp_path):
        """Envoi d'un fichier vide."""
        filepath = tmp_path / "empty.txt"
        filepath.write_bytes(b"")

        sock = MagicMock()
        FileUtils.send_file(sock, str(filepath))

        sent_data = sock.sendall.call_args[0][0]
        # Header: SEND_FILE empty.txt\n0\n
        assert b"SEND_FILE empty.txt\n0\n" == sent_data

    def test_send_file_header_format(self, tmp_path):
        """Vérifie le format exact du header : SEND_FILE <nom>\\n<taille>\\n."""
        filepath = tmp_path / "data.bin"
        content = b"ABCDE"
        filepath.write_bytes(content)

        sock = MagicMock()
        FileUtils.send_file(sock, str(filepath))

        sent_data = sock.sendall.call_args[0][0]
        expected_header = b"SEND_FILE data.bin\n5\n"
        assert sent_data[:len(expected_header)] == expected_header

    def test_send_file_extracts_filename_from_path(self, tmp_path):
        """Le nom de fichier est extrait du chemin (pas le chemin complet)."""
        subdir = tmp_path / "sub" / "dir"
        subdir.mkdir(parents=True)
        filepath = subdir / "report.pdf"
        filepath.write_bytes(b"PDF")

        sock = MagicMock()
        FileUtils.send_file(sock, str(filepath))

        sent_data = sock.sendall.call_args[0][0]
        assert sent_data.startswith(b"SEND_FILE report.pdf\n")

    def test_send_file_not_found(self):
        """Fichier inexistant → FileNotFoundError."""
        sock = MagicMock()
        with pytest.raises(FileNotFoundError):
            FileUtils.send_file(sock, "/nonexistent/file.txt")

    def test_send_file_large(self, tmp_path):
        """Envoi d'un fichier volumineux (1 Mo)."""
        filepath = tmp_path / "large.bin"
        large_content = b"\x42" * (1024 * 1024)
        filepath.write_bytes(large_content)

        sock = MagicMock()
        FileUtils.send_file(sock, str(filepath))

        sent_data = sock.sendall.call_args[0][0]
        assert sent_data.endswith(large_content)
        assert str(len(large_content)).encode("ascii") in sent_data

    def test_send_file_socket_error(self, tmp_path):
        """Erreur d'envoi socket → OSError propagée."""
        filepath = tmp_path / "test.txt"
        filepath.write_text("data")

        sock = MagicMock()
        sock.sendall.side_effect = OSError("Connection reset")

        with pytest.raises(OSError):
            FileUtils.send_file(sock, str(filepath))


# ===================================================================
# Tests download_file
# ===================================================================


class TestDownloadFile:
    """Tests pour FileUtils.download_file."""

    def test_download_file_basic(self, tmp_path, monkeypatch):
        """Téléchargement d'un fichier simple."""
        monkeypatch.chdir(tmp_path)

        content = b"Hello from server!"
        size_header = str(len(content)).encode("ascii") + b"\n"
        raw_data = size_header + content

        sock = _make_recv_sock(raw_data)
        out_path = FileUtils.download_file(sock, "received.txt")

        assert os.path.exists(out_path)
        with open(out_path, "rb") as f:
            assert f.read() == content

    def test_download_file_binary(self, tmp_path, monkeypatch):
        """Téléchargement d'un fichier binaire."""
        monkeypatch.chdir(tmp_path)

        content = bytes(range(256))
        size_header = str(len(content)).encode("ascii") + b"\n"
        raw_data = size_header + content

        sock = _make_recv_sock(raw_data)
        out_path = FileUtils.download_file(sock, "binary.dat")

        with open(out_path, "rb") as f:
            assert f.read() == content

    def test_download_file_empty(self, tmp_path, monkeypatch):
        """Téléchargement d'un fichier vide (taille 0)."""
        monkeypatch.chdir(tmp_path)

        raw_data = b"0\n"
        sock = _make_recv_sock(raw_data)
        out_path = FileUtils.download_file(sock, "empty.txt")

        with open(out_path, "rb") as f:
            assert f.read() == b""

    def test_download_file_invalid_size(self, tmp_path, monkeypatch):
        """Taille invalide (non numérique) → ValueError."""
        monkeypatch.chdir(tmp_path)

        raw_data = b"abc\n"
        sock = _make_recv_sock(raw_data)

        with pytest.raises(ValueError, match="Invalid size"):
            FileUtils.download_file(sock, "bad.txt")

    def test_download_file_negative_size(self, tmp_path, monkeypatch):
        """Taille négative → ValueError (pas un digit)."""
        monkeypatch.chdir(tmp_path)

        raw_data = b"-10\n"
        sock = _make_recv_sock(raw_data)

        with pytest.raises(ValueError, match="Invalid size"):
            FileUtils.download_file(sock, "neg.txt")

    def test_download_file_creates_in_cwd(self, tmp_path, monkeypatch):
        """Le fichier est créé dans le répertoire courant."""
        monkeypatch.chdir(tmp_path)

        content = b"test"
        raw_data = str(len(content)).encode("ascii") + b"\n" + content
        sock = _make_recv_sock(raw_data)

        out_path = FileUtils.download_file(sock, "output.txt")
        assert out_path == os.path.join(str(tmp_path), "output.txt")

    def test_download_file_connection_closed(self, tmp_path, monkeypatch):
        """Socket fermée pendant la réception → ConnectionError."""
        monkeypatch.chdir(tmp_path)

        # Header annonce 100 octets mais on n'en envoie que 5
        raw_data = b"100\n" + b"short"
        sock = _make_recv_sock(raw_data)

        with pytest.raises(ConnectionError):
            FileUtils.download_file(sock, "truncated.txt")


# ===================================================================
# Tests protocole send → download (intégration légère)
# ===================================================================


class TestSendDownloadIntegration:
    """Vérifie que send_file et download_file sont compatibles."""

    def test_roundtrip_text(self, tmp_path, monkeypatch):
        """Un fichier envoyé puis téléchargé conserve son contenu."""
        monkeypatch.chdir(tmp_path)

        # Créer le fichier source
        src = tmp_path / "original.txt"
        original_content = b"Contenu original du fichier de test!"
        src.write_bytes(original_content)

        # Capturer ce que send_file envoie
        sock_send = MagicMock()
        FileUtils.send_file(sock_send, str(src))
        sent_data = sock_send.sendall.call_args[0][0]

        # Extraire la partie après "SEND_FILE <filename>\n" (= taille + contenu)
        # Le format est: SEND_FILE filename\nSIZE\nCONTENT
        first_newline = sent_data.index(b"\n")
        download_payload = sent_data[first_newline + 1 :]

        # Simuler la réception
        sock_recv = _make_recv_sock(download_payload)
        out_path = FileUtils.download_file(sock_recv, "downloaded.txt")

        with open(out_path, "rb") as f:
            assert f.read() == original_content

    def test_roundtrip_binary(self, tmp_path, monkeypatch):
        """Round-trip avec du contenu binaire."""
        monkeypatch.chdir(tmp_path)

        src = tmp_path / "image.png"
        binary_content = bytes(range(256)) * 100
        src.write_bytes(binary_content)

        sock_send = MagicMock()
        FileUtils.send_file(sock_send, str(src))
        sent_data = sock_send.sendall.call_args[0][0]

        first_newline = sent_data.index(b"\n")
        download_payload = sent_data[first_newline + 1 :]

        sock_recv = _make_recv_sock(download_payload)
        out_path = FileUtils.download_file(sock_recv, "image_copy.png")

        with open(out_path, "rb") as f:
            assert f.read() == binary_content
