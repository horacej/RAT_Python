def readline(sock):
    buf = b""

    while True:
        chunk = sock.recv(1)
        if not chunk:
            raise ConnectionError("Socket closed while reading line")

        if chunk == b"\n":
            return buf

        buf += chunk
