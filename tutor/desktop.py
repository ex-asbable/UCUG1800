import os
import socket
import sys
from pathlib import Path
from threading import Thread

import uvicorn

from tutor.main import create_app


def main():
    token = os.environ.pop("AI_TUTOR_DESKTOP_TOKEN")
    data_directory = Path(os.environ["AI_TUTOR_DATA_DIR"])
    application = create_app(data_directory, desktop_token=token)
    server = uvicorn.Server(uvicorn.Config(
        application, http="h11", ws="none", loop="asyncio", access_log=False, proxy_headers=False,
    ))
    with socket.socket() as listener:
        if os.name == "nt":
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        print(listener.getsockname()[1], flush=True)

        def stop_on_parent_exit():
            sys.stdin.buffer.read()
            server.should_exit = True

        Thread(target=stop_on_parent_exit, daemon=True).start()
        server.run(sockets=[listener])


if __name__ == "__main__":
    main()
