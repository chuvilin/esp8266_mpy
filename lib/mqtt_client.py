import socket
import time

class MQTTClient:
    '''
    Инкапсуляция MQTT-протокола (реализация встроена).
    '''
    def __init__(self, client_id, broker_address, broker_port,
                 user, password, discovery_prefix,
                 keepalive=60, publish_retries=3):
        self._client_id = client_id
        self._broker_address = broker_address
        self._broker_port = broker_port
        self._user = user
        self._password = password
        self._discovery_prefix = discovery_prefix
        self._keepalive = keepalive
        self._publish_retries = publish_retries
        self._sock = None
        self._connected = False
        self._subscriptions = {}
        self._pid = 0
        self._last_activity = 0
        self._last_ping = 0
        self._will_topic = None
        self._will_payload = None
        self._will_qos = 0
        self._will_retain = False

    def set_last_will(self, topic, payload, retain=False, qos=0):
        self._will_topic = topic.encode('utf-8') if isinstance(topic, str) else topic
        self._will_payload = payload.encode('utf-8') if isinstance(payload, str) else payload
        self._will_qos = qos
        self._will_retain = retain

    # --- Геттеры/Сеттеры ---
    def client_id(self): return self._client_id
    def broker_address(self): return self._broker_address
    def broker_port(self): return self._broker_port
    def discovery_prefix(self): return self._discovery_prefix

    def keepalive(self, value=None):
        if value is None: return self._keepalive
        self._keepalive = value
        return self

    def publish_retries(self, value=None):
        if value is None: return self._publish_retries
        self._publish_retries = value
        return self

    def connected(self): return self._connected

    # --- Утилиты кодирования ---
    def _encode_uint16(self, val): return bytes([(val >> 8) & 0xFF, val & 0xFF])
    def _decode_uint16(self, data): return (data[0] << 8) | data[1]

    def _encode_remaining_length(self, length):
        result = bytearray(4)
        idx = 0
        while length > 0x7F:
            result[idx] = (length & 0x7F) | 0x80
            length >>= 7
            idx += 1
        result[idx] = length
        return bytes(result[:idx + 1])

    def _send_string(self, s):
        b = s.encode('utf-8') if isinstance(s, str) else s
        self._sock.write(self._encode_uint16(len(b)))
        self._sock.write(b)

    def _read_fully(self, n):
        '''Чтение ровно n байт. Сокет ДОЛЖЕН иметь установленный timeout.'''
        data = b''
        while len(data) < n:
            chunk = self._sock.read(n - len(data))
            if not chunk:
                raise RuntimeError('Connection closed')
            data += chunk
        return data

    def _recv_length(self):
        '''Прием переменной длины пакета. Сокет ДОЛЖЕН иметь установленный timeout.'''
        n = 0
        shift = 0
        while True:
            b = self._sock.read(1)
            if not b: raise RuntimeError('Failed to read length')
            b = b[0]
            n |= (b & 0x7F) << shift
            if not (b & 0x80): return n
            shift += 7

    def _update_activity(self):
        now = time.ticks_ms()
        self._last_activity = now
        self._last_ping = now

    def _check_keepalive(self):
        if self._keepalive == 0: return
        now = time.ticks_ms()
        interval = self._keepalive * 1000
        if time.ticks_diff(now, self._last_ping) > (interval * 7 // 10):
            self._ping()
            self._last_ping = now

    def _ping(self):
        try: self._sock.write(b'\xC0\x00')
        except: pass

    def _close_socket(self):
        if self._sock:
            try: self._sock.close()
            except: pass
        self._sock = None

    # --- Публичные методы ---
    def connect(self, clean_session=True):
        if self._connected: return
        self._close_socket()
        try:
            addr = socket.getaddrinfo(self._broker_address, self._broker_port)[0][-1]
            self._sock = socket.socket()
            self._sock.settimeout(5.0)
            self._sock.connect(addr)
        except Exception as e:
            self._close_socket()
            raise RuntimeError('Socket connect failed: ' + str(e))

        try:
            # === FIX: инициализация rem_len, не +=
            rem_len = 10 + 2 + len(self._client_id)
            if self._will_topic:
                rem_len += 2 + len(self._will_topic) + 2 + len(self._will_payload)
            has_user = bool(self._user)
            has_pass = bool(self._password)
            if has_user: rem_len += 2 + len(self._user)
            if has_pass: rem_len += 2 + len(self._password)

            self._sock.write(b'\x10')  # CONNECT
            self._sock.write(self._encode_remaining_length(rem_len))
            self._sock.write(b'\x00\x04MQTT\x04')
            flags = 0x02 if clean_session else 0x00
            if self._will_topic:
                flags |= 0x04
                flags |= (self._will_qos & 0x03) << 3
                if self._will_retain: flags |= 0x20
            if has_user: flags |= 0x80
            if has_pass: flags |= 0x40
            self._sock.write(bytes([flags]))
            self._sock.write(self._encode_uint16(self._keepalive))
            self._send_string(self._client_id)
            if self._will_topic:
                self._send_string(self._will_topic)
                self._send_string(self._will_payload)
            if has_user: self._send_string(self._user)
            if has_pass: self._send_string(self._password)

            resp = self._read_fully(4)
            if resp[0] != 0x20 or resp[1] != 0x02: raise RuntimeError('Invalid CONNACK')
            if resp[3] != 0x00: raise RuntimeError('Connection refused, code: ' + str(resp[3]))
        except Exception as e:
            self._close_socket()
            raise

        if self._sock:
            self._sock.settimeout(0)  # Вернуть в неблокирующий режим
        self._connected = True
        self._update_activity()

    def disconnect(self):
        if not self._connected: return
        try: self._sock.write(b'\xE0\x00')
        except: pass
        self._close_socket()
        self._connected = False

    def publish(self, topic, payload, retain=False, qos=0):
        if not self._connected:
            raise RuntimeError('MQTT not connected')

        # Защита от фрагментации при сериализации dict
        if isinstance(payload, dict):
            import gc, ujson
            gc.collect()
            try:
                payload = ujson.dumps(payload)
            except MemoryError:
                gc.collect()
                # Fallback: ручная сборка без ujson
                p = []
                for k, v in payload.items():
                    if v is None: continue
                    if isinstance(v, str): p.append(f'"{k}":"{v}"')
                    elif isinstance(v, bool): p.append(f'"{k}":{str(v).lower()}')
                    else: p.append(f'"{k}":{v}')
                payload = '{' + ','.join(p) + '}'

        if isinstance(payload, str):
            payload = payload.encode('utf-8')

        topic_b = topic.encode('utf-8') if isinstance(topic, str) else topic
        topic_len = len(topic_b)
        payload_len = len(payload)
        rem_len = 2 + topic_len + payload_len
        if qos > 0: rem_len += 2

        header = 0x30 | (qos << 1) | (1 if retain else 0)
        try:
            self._sock.write(bytes([header]))
            self._sock.write(self._encode_remaining_length(rem_len))
            self._sock.write(self._encode_uint16(topic_len))
            self._sock.write(topic_b)
            if qos > 0:
                self._pid += 1
                if self._pid > 0xFFFF: self._pid = 1
                self._sock.write(self._encode_uint16(self._pid))
            self._sock.write(payload)
        except Exception as e:
            self._connected = False
            self._close_socket()
            raise

        self._update_activity()
        if qos == 1:
            self._sock.setblocking(True)
            try:
                resp = self._read_fully(4)
                if resp[0] != 0x40 or resp[1] != 0x02:
                    raise RuntimeError('PUBACK expected')
            except Exception:
                self._connected = False
                raise
            finally:
                self._sock.setblocking(False)

    def _subscribe_packet(self, topic, qos=0, retries=2):
        topic_b = topic.encode('utf-8') if isinstance(topic, str) else topic
        topic_len = len(topic_b)
        for attempt in range(retries):
            try:
                rem_len = 2 + 2 + topic_len + 1
                self._sock.write(b'\x82')
                self._sock.write(self._encode_remaining_length(rem_len))
                self._pid += 1
                if self._pid > 0xFFFF: self._pid = 1
                self._sock.write(self._encode_uint16(self._pid))
                self._sock.write(self._encode_uint16(topic_len))
                self._sock.write(topic_b)
                self._sock.write(bytes([qos]))

                # FIX: Безопасное ожидание SUBACK с таймаутом
                self._sock.settimeout(5.0)
                try:
                    resp = self._read_fully(5)
                finally:
                    if self._sock:
                        self._sock.settimeout(0)

                if resp[0] != 0x90 or resp[1] != 0x03: raise RuntimeError('Invalid SUBACK')
                pkt_id = (resp[2] << 8) | resp[3]
                if pkt_id != self._pid: raise RuntimeError('SUBACK packet ID mismatch')
                if resp[4] not in (0x00, 0x01, 0x02): raise RuntimeError('SUBACK failed, code: ' + hex(resp[4]))
                return
            except Exception as e:
                if attempt == retries - 1: raise
                time.sleep(0.1)
        raise RuntimeError('SUBACK expected')

    def subscribe(self, topic, callback):
        self._subscriptions[topic] = callback
        if self._connected:
            try: self._subscribe_packet(topic)
            except Exception:
                self._connected = False
                raise

    def get_messages(self):
        if not self._connected: raise RuntimeError('MQTT not connected')
        self._check_keepalive()
        try:
            first_byte = self._sock.read(1)
        except OSError as e:
            if e.args[0] in (11, 35): return
            self._connected = False
            self._close_socket()
            raise
        except Exception:
            self._connected = False
            raise

        if not first_byte: return
        # FIX: Временный таймаут для чтения оставшейся части пакета
        self._sock.settimeout(1.0)
        try:
            pkt_type = first_byte[0] & 0xF0
            rem_len = self._recv_length()
            if rem_len > 0:
                payload_data = self._read_fully(rem_len)
            else:
                payload_data = b''
        except Exception:
            self._connected = False
            self._close_socket()
            raise
        finally:
            if self._sock:
                self._sock.settimeout(0)

        self._update_activity()
        if pkt_type == 0x30:  # PUBLISH
            topic_len = self._decode_uint16(payload_data[:2])
            topic = payload_data[2:2+topic_len].decode('utf-8')
            message = payload_data[2+topic_len:]
            callback = self._subscriptions.get(topic)
            if callback:
                try: callback(topic, message)
                except: pass
        elif pkt_type == 0xD0:  # PINGRESP
            pass
        elif pkt_type == 0x40:  # PUBACK
            pass
