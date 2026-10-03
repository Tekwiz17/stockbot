"""Single worker with an explicit dual-stack listener for Nest's reverse proxy."""
import socket
import uvicorn


def listener(port=8765):
    if socket.has_dualstack_ipv6():
        return socket.create_server(('::', port), family=socket.AF_INET6, dualstack_ipv6=True)
    return socket.create_server(('0.0.0.0', port), family=socket.AF_INET)


def main():
    sock=listener()
    try:
        server=uvicorn.Server(uvicorn.Config('backend.app:app', access_log=False, workers=1))
        server.run(sockets=[sock])
    finally:
        sock.close()


if __name__=='__main__':
    main()
