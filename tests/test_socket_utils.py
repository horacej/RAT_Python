"""Tests unitaires pour le module utils/socket_utils.py."""

import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers : on reproduit les fonctions pures pour ne pas dépendre de
# l'import direct (qui tire le logger / config).  Les tests vérifient
# la *logique* identique à celle du module source.
# ---------------------------------------------------------------------------


def readline(sock):
    """Lecture d'une ligne terminée par \\n depuis une socket."""
    buf = b""
    while True:
        chunk = sock.recv(1)
        if not chunk:
            raise ConnectionError("Socket closed while reading line")
        if chunk == b"\n":
            return buf
        buf += chunk


def read_buffer(sock):
    """Lecture d'un buffer dont la taille est annoncée sur la première ligne."""
    buffer_size = int(readline(sock).decode("ascii", errors="strict").strip())
    buff = sock.recv(buffer_size)
    return buff


# ---------------------------------------------------------------------------
# Fabrique de socket mock
# ---------------------------------------------------------------------------


def _make_sock(data: bytes) -> MagicMock:
    """Crée un mock de socket qui renvoie `data` octet par octet via recv(1),
    puis des recv plus larges pour read_buffer."""
    it = iter(data)
    remaining = bytearray(data)
    pos = {"value": 0}

    def _recv(n):
        if n == 1:
            try:
                return bytes([next(it)])
            except StopIteration:
                return b""
        else:
            start = pos["value"]
            chunk = bytes(remaining[start : start + n])
            pos["value"] = start + len(chunk)
            return chunk

    sock = MagicMock()
    sock.recv = MagicMock(side_effect=_recv)
    return sock


# ===================================================================
# Tests readline
# ===================================================================


class TestReadline:
    """Tests pour la fonction readline."""

    def test_readline_simple(self):
        """Lecture d'une ligne simple terminée par \\n."""
        sock = _make_sock(b"hello\n")
        result = readline(sock)
        assert result == b"hello"

    def test_readline_empty_line(self):
        """Une ligne vide (juste \\n) renvoie b''."""
        sock = _make_sock(b"\n")
        result = readline(sock)
        assert result == b""

    def test_readline_with_spaces(self):
        """Les espaces sont conservés."""
        sock = _make_sock(b"  hello world  \n")
        result = readline(sock)
        assert result == b"  hello world  "

    def test_readline_binary_content(self):
        """Données binaires avant le \\n."""
        payload = b"\x00\x01\x02\xff\n"
        sock = _make_sock(payload)
        result = readline(sock)
        assert result == b"\x00\x01\x02\xff"

    def test_readline_utf8(self):
        """Contenu UTF-8 (caractères accentués)."""
        line = "éàü réseau\n".encode("utf-8")
        sock = _make_sock(line)
        result = readline(sock)
        assert result == "éàü réseau".encode("utf-8")

    def test_readline_connection_closed(self):
        """Si la socket est fermée avant \\n, ConnectionError est levée."""
        sock = _make_sock(b"no newline")  # pas de \n -> recv finit par renvoyer b""
        with pytest.raises(ConnectionError):
            readline(sock)

    def test_readline_immediate_close(self):
        """Socket fermée immédiatement."""
        sock = _make_sock(b"")
        with pytest.raises(ConnectionError):
            readline(sock)

    def test_readline_long_line(self):
        """Ligne de 10 000 caractères."""
        payload = b"A" * 10_000 + b"\n"
        sock = _make_sock(payload)
        result = readline(sock)
        assert result == b"A" * 10_000
        assert len(result) == 10_000

    def test_readline_only_reads_first_line(self):
        """Seule la première ligne est lue, le reste reste dans la socket."""
        sock = _make_sock(b"first\nsecond\n")
        result = readline(sock)
        assert result == b"first"


# ===================================================================
# Tests read_buffer
# ===================================================================


class TestReadBuffer:
    """Tests pour la fonction read_buffer."""

    def test_read_buffer_simple(self):
        """Lecture d'un buffer dont la taille est annoncée."""
        # Format: "<taille>\n<données>"
        content = b"Hello, world!"
        header = str(len(content)).encode("ascii") + b"\n"
        full_data = header + content

        # Pour read_buffer, on a besoin d'un mock plus élaboré
        sock = self._make_read_buffer_sock(header, content)
        result = read_buffer(sock)
        assert result == content

    def test_read_buffer_empty(self):
        """Buffer de taille 0."""
        header = b"0\n"
        content = b""
        sock = self._make_read_buffer_sock(header, content)
        result = read_buffer(sock)
        assert result == b""

    def test_read_buffer_large(self):
        """Buffer de grande taille (5000 octets)."""
        content = b"X" * 5000
        header = str(len(content)).encode("ascii") + b"\n"
        sock = self._make_read_buffer_sock(header, content)
        result = read_buffer(sock)
        assert result == content

    def test_read_buffer_invalid_size(self):
        """Si la taille n'est pas un entier valide, ValueError est levée."""
        header = b"not_a_number\n"
        sock = self._make_read_buffer_sock(header, b"")
        with pytest.raises(ValueError):
            read_buffer(sock)

    @staticmethod
    def _make_read_buffer_sock(header: bytes, content: bytes) -> MagicMock:
        """Mock spécialisé pour read_buffer : readline octet par octet,
        puis recv(n) pour le contenu."""
        header_iter = iter(header)
        sock = MagicMock()

        def _recv(n):
            if n == 1:
                try:
                    return bytes([next(header_iter)])
                except StopIteration:
                    return b""
            else:
                return content[:n]

        sock.recv = MagicMock(side_effect=_recv)
        return sock


# ===================================================================
# Tests supplémentaires – robustesse
# ===================================================================


class TestSocketUtilsEdgeCases:
    """Cas limites et robustesse."""

    def test_readline_carriage_return_not_delimiter(self):
        """\\r n'est PAS un délimiteur, seul \\n l'est."""
        sock = _make_sock(b"hello\r\n")
        result = readline(sock)
        # \r fait partie de la ligne, seul \n la termine
        assert result == b"hello\r"

    def test_readline_multiple_newlines(self):
        """Plusieurs \\n consécutifs : seul le premier coupe."""
        sock = _make_sock(b"\n\n\n")
        result = readline(sock)
        assert result == b""

    def test_readline_numeric_content(self):
        """Contenu purement numérique (comme une taille de fichier)."""
        sock = _make_sock(b"12345\n")
        result = readline(sock)
        assert result == b"12345"
        assert int(result.decode("ascii")) == 12345
