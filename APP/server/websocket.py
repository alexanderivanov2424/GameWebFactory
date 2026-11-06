"""Minimal WebSocket server (RFC 6455) using only the Python standard library.

Supports text messages, fragmentation, ping/pong and close. Binary messages are ignored.
"""

import asyncio
import base64
import hashlib
import logging
import struct
from urllib.parse import parse_qs, urlsplit

log = logging.getLogger("websocket")

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_MESSAGE = 64 * 1024
PING_INTERVAL = 10  # Seconds between pings to each client.
PONG_TIMEOUT = 25   # Drop a connection that has sent nothing (not even a pong) for this long.
HANDSHAKE_TIMEOUT = 10

OP_CONT, OP_TEXT, OP_BINARY, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA


class ProtocolError(Exception):
    pass


def _unmask(data, mask):
    n = len(data)
    key = (mask * (n // 4 + 1))[:n]
    return (int.from_bytes(data, "big") ^ int.from_bytes(key, "big")).to_bytes(n, "big")


class WebSocket:
    def __init__(self, reader, writer, path, query):
        self.reader = reader
        self.writer = writer
        self.path = path
        self.query = query
        self.closed = False
        self.last_seen = asyncio.get_running_loop().time()
        self._send_lock = asyncio.Lock()

    async def send(self, text):
        """Send a text message. Does nothing if the connection is closed."""
        await self._send_frame(OP_TEXT, text.encode())

    async def recv(self):
        """Return the next text message, or None once the connection is closed."""
        parts, size, message_op = [], 0, None
        while not self.closed:
            try:
                fin, opcode, payload = await self._read_frame()
            except (asyncio.IncompleteReadError, OSError):
                await self.close()
                return None
            except ProtocolError:
                await self.close(1002)
                return None

            if opcode == OP_PING:
                await self._send_frame(OP_PONG, payload)
                continue
            if opcode == OP_PONG:
                continue
            if opcode == OP_CLOSE:
                await self.close()
                return None

            if opcode in (OP_TEXT, OP_BINARY) and message_op is None:
                message_op, parts, size = opcode, [payload], len(payload)
            elif opcode == OP_CONT and message_op is not None:
                parts.append(payload)
                size += len(payload)
            else:
                await self.close(1002)
                return None

            if size > MAX_MESSAGE:
                await self.close(1009)
                return None
            if not fin:
                continue

            op, message_op = message_op, None
            if op == OP_TEXT:
                try:
                    return b"".join(parts).decode()
                except UnicodeDecodeError:
                    await self.close(1007)
                    return None
        return None

    async def close(self, code=1000):
        if self.closed:
            return
        await self._send_frame(OP_CLOSE, struct.pack("!H", code))
        self.closed = True
        self.writer.close()

    def abort(self, code=None):
        """Drop the connection immediately (for dead or replaced connections).

        If `code` is given, a close frame with that code is sent first, best effort.
        """
        if self.closed:
            return
        if code is not None:
            self.writer.write(struct.pack("!BBH", 0x80 | OP_CLOSE, 2, code))
        self.closed = True
        self.writer.transport.abort()

    async def _read_frame(self):
        b1, b2 = await self.reader.readexactly(2)
        if not b2 & 0x80:
            raise ProtocolError("client frames must be masked")
        length = b2 & 0x7F
        if length == 126:
            (length,) = struct.unpack("!H", await self.reader.readexactly(2))
        elif length == 127:
            (length,) = struct.unpack("!Q", await self.reader.readexactly(8))
        if length > MAX_MESSAGE:
            raise ProtocolError("frame too large")
        mask = await self.reader.readexactly(4)
        payload = _unmask(await self.reader.readexactly(length), mask)
        self.last_seen = asyncio.get_running_loop().time()
        return bool(b1 & 0x80), b1 & 0x0F, payload

    async def _send_frame(self, opcode, payload):
        if self.closed:
            return
        n = len(payload)
        if n < 126:
            header = struct.pack("!BB", 0x80 | opcode, n)
        elif n < 65536:
            header = struct.pack("!BBH", 0x80 | opcode, 126, n)
        else:
            header = struct.pack("!BBQ", 0x80 | opcode, 127, n)
        async with self._send_lock:
            try:
                self.writer.write(header + payload)
                await self.writer.drain()
            except OSError:
                self.closed = True


async def _read_request(reader):
    raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), HANDSHAKE_TIMEOUT)
    lines = raw.decode("latin-1").split("\r\n")
    method, target, _ = lines[0].split(" ", 2)
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()
    return method, target, headers


def _respond(writer, status):
    writer.write(f"HTTP/1.1 {status}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".encode())


async def _keepalive(ws):
    """Ping the client regularly and drop it if it stops answering."""
    loop = asyncio.get_running_loop()
    while not ws.closed:
        await asyncio.sleep(PING_INTERVAL)
        if loop.time() - ws.last_seen > PONG_TIMEOUT:
            ws.abort()
            return
        await ws._send_frame(OP_PING, b"")


async def serve(route, host, port):
    """Start a WebSocket server.

    route(path) returns an async handler(ws) for that URL path, or None for 404.
    """

    async def on_connection(reader, writer):
        try:
            try:
                method, target, headers = await _read_request(reader)
            except (ValueError, asyncio.IncompleteReadError, asyncio.LimitOverrunError,
                    asyncio.TimeoutError, OSError):
                return

            url = urlsplit(target)
            key = headers.get("sec-websocket-key")
            if method != "GET" or headers.get("upgrade", "").lower() != "websocket" or not key:
                _respond(writer, "400 Bad Request")
                return
            handler = route(url.path)
            if handler is None:
                _respond(writer, "404 Not Found")
                return

            accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
            writer.write(
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept}\r\n\r\n".encode()
            )
            await writer.drain()

            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            ws = WebSocket(reader, writer, url.path, query)
            pinger = asyncio.create_task(_keepalive(ws))
            try:
                await handler(ws)
            finally:
                pinger.cancel()
                await ws.close()
        except Exception:
            log.exception("Connection error")
        finally:
            writer.close()

    return await asyncio.start_server(on_connection, host, port)
