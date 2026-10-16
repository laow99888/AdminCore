"""真实 TCP 协议测试服务；不是病毒识别引擎，集成测试另跑 ClamAV。"""
from contextlib import contextmanager
import socket
import struct
import threading
import time

from config.antivirus import AntivirusConfig


def read_exact(connection, length):
    output = bytearray()
    while len(output) < length:
        chunk = connection.recv(length - len(output))
        if not chunk:
            raise EOFError()
        output.extend(chunk)
    return bytes(output)


@contextmanager
def clamd_fixture(*, response=None, delay=0, max_bytes=50 * 1024 * 1024, timeout=2):
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(8)
    listener.settimeout(0.1)
    stop, scans = threading.Event(), []
    port = listener.getsockname()[1]

    def serve():
        while not stop.is_set():
            try:
                connection, _ = listener.accept()
            except TimeoutError:
                continue
            with connection:
                connection.settimeout(2)
                try:
                    command = bytearray()
                    while not command.endswith(b'\0'):
                        command.extend(read_exact(connection, 1))
                    if command == b'zVERSION\0':
                        connection.sendall(b'ClamAV 1.5.4/test/fixture\0')
                    elif command == b'zINSTREAM\0':
                        data = bytearray()
                        while True:
                            length = struct.unpack('!I', read_exact(connection, 4))[0]
                            if length == 0:
                                break
                            if length > 65536:
                                raise ValueError()
                            data.extend(read_exact(connection, length))
                        scans.append(bytes(data))
                        if delay:
                            stop.wait(delay)
                        answer = response if response is not None else (b'stream: Fixture-Test FOUND\0'
                                 if b'fixture-infected' in data else b'stream: OK\0')
                        for value in answer:
                            connection.sendall(bytes([value]))
                    else:
                        raise ValueError()
                except (OSError, EOFError, ValueError):
                    pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield AntivirusConfig(True, port=port, timeout=timeout, max_bytes=max_bytes), scans
    finally:
        stop.set()
        thread.join(timeout=3)
        listener.close()
        assert not thread.is_alive()
