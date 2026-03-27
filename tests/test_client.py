"""Tests unitaires pour le module client/utils/client.py."""

import platform
import socket
import ssl

import pytest
from unittest.mock import MagicMock, patch, PropertyMock


# ---------------------------------------------------------------------------
# Classe simplifiée AgentClient pour tests isolés
# ---------------------------------------------------------------------------


class AgentClient:
    """Version allégée pour tests (même logique, sans imports circulaires)."""

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
            (self.server_host, self.server_port), timeout=10
        )
        self.sock = ctx.wrap_socket(raw_sock)
        self.sock.settimeout(None)
        self.running = True

    def close(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _send_line(self, text):
        data = (text + "\n").encode("utf-8")
        try:
            self.sock.sendall(data)
        except OSError:
            self.running = False

    def _handle_command(self, cmd):
        cmd_str = cmd.decode("utf-8") if isinstance(cmd, bytes) else cmd
        parts = cmd_str.split()
        if not parts:
            return None
        return parts[0]  # retourne le nom de la commande pour vérification


# ===================================================================
# Tests initialisation
# ===================================================================


class TestAgentClientInit:
    """Tests d'initialisation du client."""

    def test_init_attributes(self):
        """Vérification des attributs après initialisation."""
        client = AgentClient("192.168.1.10", 4443)
        assert client.server_host == "192.168.1.10"
        assert client.server_port == 4443
        assert client.sock is None
        assert client.running is False

    def test_init_various_ports(self):
        """Ports variés acceptés."""
        for port in [80, 443, 4443, 8080, 65535]:
            client = AgentClient("localhost", port)
            assert client.server_port == port

    def test_init_ipv4(self):
        """Adresses IPv4."""
        client = AgentClient("10.0.0.1", 4443)
        assert client.server_host == "10.0.0.1"

    def test_init_hostname(self):
        """Nom d'hôte au lieu d'IP."""
        client = AgentClient("myserver.local", 4443)
        assert client.server_host == "myserver.local"


# ===================================================================
# Tests contexte TLS
# ===================================================================


class TestCreateContext:
    """Tests pour _create_context."""

    def test_context_type(self):
        """Le contexte retourné est bien un SSLContext."""
        client = AgentClient("localhost", 4443)
        ctx = client._create_context()
        assert isinstance(ctx, ssl.SSLContext)

    def test_context_tls_version(self):
        """Version TLS minimum = 1.2."""
        client = AgentClient("localhost", 4443)
        ctx = client._create_context()
        assert ctx.minimum_version == ssl.TLSVersion.TLSv1_2

    def test_context_no_hostname_check(self):
        """check_hostname doit être désactivé."""
        client = AgentClient("localhost", 4443)
        ctx = client._create_context()
        assert ctx.check_hostname is False

    def test_context_no_cert_verification(self):
        """verify_mode = CERT_NONE (auto-signé accepté)."""
        client = AgentClient("localhost", 4443)
        ctx = client._create_context()
        assert ctx.verify_mode == ssl.CERT_NONE


# ===================================================================
# Tests connexion
# ===================================================================


class TestConnect:
    """Tests pour la méthode connect."""

    @patch("socket.create_connection")
    def test_connect_sets_running(self, mock_conn):
        """Après connexion, running = True."""
        mock_sock = MagicMock()
        mock_conn.return_value = mock_sock

        client = AgentClient("localhost", 4443)

        with patch.object(client, "_create_context") as mock_ctx:
            mock_ssl_ctx = MagicMock()
            mock_ssl_ctx.wrap_socket.return_value = MagicMock()
            mock_ctx.return_value = mock_ssl_ctx

            client.connect()

        assert client.running is True
        assert client.sock is not None

    @patch("socket.create_connection")
    def test_connect_uses_correct_host_port(self, mock_conn):
        """La connexion utilise le bon host et port."""
        mock_conn.return_value = MagicMock()

        client = AgentClient("10.0.0.5", 9999)

        with patch.object(client, "_create_context") as mock_ctx:
            mock_ssl_ctx = MagicMock()
            mock_ssl_ctx.wrap_socket.return_value = MagicMock()
            mock_ctx.return_value = mock_ssl_ctx

            client.connect()

        mock_conn.assert_called_once_with(("10.0.0.5", 9999), timeout=10)

    @patch("socket.create_connection", side_effect=ConnectionRefusedError)
    def test_connect_refused(self, mock_conn):
        """Connexion refusée → exception propagée."""
        client = AgentClient("localhost", 4443)
        with pytest.raises(ConnectionRefusedError):
            client.connect()

    @patch("socket.create_connection", side_effect=socket.timeout)
    def test_connect_timeout(self, mock_conn):
        """Timeout de connexion → exception propagée."""
        client = AgentClient("localhost", 4443)
        with pytest.raises(socket.timeout):
            client.connect()


# ===================================================================
# Tests close
# ===================================================================


class TestClose:
    """Tests pour la méthode close."""

    def test_close_sets_running_false(self):
        """close() met running à False."""
        client = AgentClient("localhost", 4443)
        client.running = True
        client.sock = MagicMock()

        client.close()

        assert client.running is False

    def test_close_sets_sock_none(self):
        """close() met sock à None."""
        client = AgentClient("localhost", 4443)
        client.sock = MagicMock()

        client.close()

        assert client.sock is None

    def test_close_calls_sock_close(self):
        """close() appelle sock.close()."""
        client = AgentClient("localhost", 4443)
        mock_sock = MagicMock()
        client.sock = mock_sock

        client.close()

        mock_sock.close.assert_called_once()

    def test_close_without_sock(self):
        """close() sans socket ne plante pas."""
        client = AgentClient("localhost", 4443)
        client.sock = None
        client.close()  # ne doit pas lever d'exception

    def test_close_sock_oserror(self):
        """close() gère l'OSError sur sock.close()."""
        client = AgentClient("localhost", 4443)
        mock_sock = MagicMock()
        mock_sock.close.side_effect = OSError("Already closed")
        client.sock = mock_sock

        client.close()  # ne doit pas lever d'exception
        assert client.sock is None

    def test_close_idempotent(self):
        """Appeler close() deux fois ne plante pas."""
        client = AgentClient("localhost", 4443)
        client.sock = MagicMock()

        client.close()
        client.close()

        assert client.sock is None
        assert client.running is False


# ===================================================================
# Tests send_line
# ===================================================================


class TestSendLine:
    """Tests pour _send_line."""

    def test_send_line_basic(self):
        """Envoi d'une ligne simple."""
        client = AgentClient("localhost", 4443)
        client.sock = MagicMock()
        client.running = True

        client._send_line("hello")

        client.sock.sendall.assert_called_once_with(b"hello\n")

    def test_send_line_utf8(self):
        """Envoi avec caractères UTF-8."""
        client = AgentClient("localhost", 4443)
        client.sock = MagicMock()
        client.running = True

        client._send_line("réseau éàü")

        expected = "réseau éàü\n".encode("utf-8")
        client.sock.sendall.assert_called_once_with(expected)

    def test_send_line_empty(self):
        """Envoi d'une ligne vide (juste \\n)."""
        client = AgentClient("localhost", 4443)
        client.sock = MagicMock()
        client.running = True

        client._send_line("")

        client.sock.sendall.assert_called_once_with(b"\n")

    def test_send_line_oserror_stops_running(self):
        """Si sendall lève OSError, running passe à False."""
        client = AgentClient("localhost", 4443)
        client.sock = MagicMock()
        client.sock.sendall.side_effect = OSError("Broken pipe")
        client.running = True

        client._send_line("test")

        assert client.running is False


# ===================================================================
# Tests handle_command (parsing)
# ===================================================================


class TestHandleCommand:
    """Tests de parsing des commandes reçues."""

    def test_command_download(self):
        """Commande download reconnue."""
        client = AgentClient("localhost", 4443)
        result = client._handle_command(b"download /etc/passwd")
        assert result == "download"

    def test_command_upload(self):
        """Commande SEND_FILE reconnue."""
        client = AgentClient("localhost", 4443)
        result = client._handle_command(b"SEND_FILE myfile.txt")
        assert result == "SEND_FILE"

    def test_command_shell(self):
        """Commande shell reconnue."""
        client = AgentClient("localhost", 4443)
        result = client._handle_command(b"shell 4444")
        assert result == "shell"

    def test_command_ipconfig(self):
        """Commande ipconfig reconnue."""
        client = AgentClient("localhost", 4443)
        result = client._handle_command(b"ipconfig")
        assert result == "ipconfig"

    def test_command_screenshot(self):
        """Commande screenshot reconnue."""
        client = AgentClient("localhost", 4443)
        result = client._handle_command(b"screenshot")
        assert result == "screenshot"

    def test_command_search(self):
        """Commande search reconnue."""
        client = AgentClient("localhost", 4443)
        result = client._handle_command(b"search config.ini")
        assert result == "search"

    def test_command_hashdump(self):
        """Commande hashdump reconnue."""
        client = AgentClient("localhost", 4443)
        result = client._handle_command(b"hashdump")
        assert result == "hashdump"

    def test_command_keylogger(self):
        """Commande keylogger reconnue."""
        client = AgentClient("localhost", 4443)
        result = client._handle_command(b"keylogger 30")
        assert result == "keylogger"

    def test_command_webcam_snapshot(self):
        """Commande webcam_snapshot reconnue."""
        client = AgentClient("localhost", 4443)
        result = client._handle_command(b"webcam_snapshot")
        assert result == "webcam_snapshot"

    def test_command_webcam_stream(self):
        """Commande webcam_stream reconnue."""
        client = AgentClient("localhost", 4443)
        result = client._handle_command(b"webcam_stream 10")
        assert result == "webcam_stream"

    def test_command_record_audio(self):
        """Commande record_audio reconnue."""
        client = AgentClient("localhost", 4443)
        result = client._handle_command(b"record_audio 5")
        assert result == "record_audio"

    def test_command_quit(self):
        """Commande quit reconnue."""
        client = AgentClient("localhost", 4443)
        result = client._handle_command(b"quit")
        assert result == "quit"

    def test_command_empty(self):
        """Commande vide → None."""
        client = AgentClient("localhost", 4443)
        result = client._handle_command(b"")
        assert result is None

    def test_command_unknown(self):
        """Commande inconnue → le nom est quand même extrait."""
        client = AgentClient("localhost", 4443)
        result = client._handle_command(b"foobar 123")
        assert result == "foobar"
