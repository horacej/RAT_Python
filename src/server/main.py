import argparse
import server.utils.server as server
from src.server.utils.config import logger

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RAT Server Version 0.1.0"
    )

    parser.add_argument(
        "host",
        help="Host/IP to bind to (e.g. 0.0.0.0 or 127.0.0.1)."
    )
    parser.add_argument(
        "port",
        type=int,
        help="Port to listen on (e.g. 4443)."
    )
    parser.add_argument(
        "certfile",
        help="Path to the server certificate (e.g. server.crt)."
    )
    parser.add_argument(
        "keyfile",
        help="Path to the server private key (e.g. server.key)."
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server_handler = server.TLSServer(args.host, args.port, args.certfile, args.keyfile)

    # Run server
    try:
        server_handler.start()
    except KeyboardInterrupt:
        logger.debug("CTRL+C pressed, shutting down...")

if __name__ == "__main__":
    main()
