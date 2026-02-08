def readline(sock):
    buf = b""

    while True:
        chunk = sock.recv(1)
        if not chunk:
            raise ConnectionError("Socket closed while reading line")

        if chunk == b"\n":
            return buf

        buf += chunk

def read_buffer(sock):
    buffer_size = int(readline(sock).decode("ascii", errors="strict").strip())
    buff = sock.recv(buffer_size)
    return buff