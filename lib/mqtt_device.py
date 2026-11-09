import time
import gc
from machine import WDT

class MQTTDevice:
    '''
    Оркестратор MQTT-устройства с WiFi-watchdog.
    '''
    # FIX: Увеличен дефолтный таймаут WDT до 15000мс для безопасности при reconnect
    def __init__(self, unique_id, name, client, model='', manufacturer='', watchdog_timeout_ms=15000):
        self._unique_id = unique_id
        self._name = name
        self._model = model
        self._manufacturer = manufacturer
        self._client = client
        self._entities = {}
        self._route_table = {}
        self._pending_states = {}
        self._reconnect_backoff = 5
        self._max_backoff = 60
        self._connectivity_callback = None
        self._loop_callbacks = []

    def unique_id(self): return self._unique_id
    def name(self): return self._name
    def model(self): return self._model
    def manufacturer(self): return self._manufacturer
    def client(self): return self._client

    def _entity_state_key(self, entity):
        key = entity.key() or 'default'
        return f"{entity.domain()}_{key}"

    def _make_topic_path(self, entity, topic_type):
        entity_key = entity.key()
        if entity_key: return f'{self._unique_id}/{entity.domain()}/{entity_key}/{topic_type}'
        return f'{self._unique_id}/{entity.domain()}/{topic_type}'

    def _availability_topic(self): return f'{self._unique_id}/availability'

    def _publish_online(self):
        if self._client.connected():
            self._client.publish(self._availability_topic(), 'online', retain=True)

    def _on_entity_state_changed(self, entity, updates):
        if not self._client.connected():
            self._pending_states[self._entity_state_key(entity)] = (entity, updates)
            return
        try:
            for topic_type, payload in updates.items():
                topic_path = self._make_topic_path(entity, topic_type)
                self._client.publish(topic_path, payload, retain=True)
        except Exception:
            self._pending_states[self._entity_state_key(entity)] = (entity, updates)

    def register_connectivity_callback(self, callback):
        self._connectivity_callback = callback

    def register_loop_callback(self, callback):
        self._loop_callbacks.append(callback)

    def _ensure_wlan(self):
        if self._connectivity_callback:
            try: return self._connectivity_callback()
            except Exception: return False
        return True

    def _register_routes(self, entity):
        handlers = entity.message_handlers()
        for topic_type, handler_method in handlers.items():
            topic_path = self._make_topic_path(entity, topic_type)
            self._route_table[topic_path] = (entity, handler_method)
            if 'command' in topic_type:
                for attempt in range(3):
                    try:
                        if not self._client.connected(): raise RuntimeError('Not connected')
                        self._client.subscribe(topic_path, self._on_mqtt_message)
                        break
                    except Exception:
                        if attempt == 2: pass
                        else: time.sleep(0.5 * (attempt + 1))

    def _on_mqtt_message(self, topic_path, payload_bytes):
        route = self._route_table.get(topic_path)
        if not route: return
        entity, handler = route
        try:
            payload_str = payload_bytes.decode('utf-8') if isinstance(payload_bytes, bytes) else payload_bytes
        except UnicodeError: return
        try: handler(payload_str)
        except: pass

    def _publish_discovery(self, entity):
        """Опубликовать discovery payload (zero-allocation friendly)."""
        import gc
        gc.collect(); gc.collect()  # Максимальная дефрагментация перед сборкой
        try:
            domain = entity.domain()
            key = entity.key() or ''
            if key:
                uid = self._unique_id + '_' + domain + '_' + key
                base = self._unique_id + '/' + domain + '/' + key + '/'
            else:
                uid = self._unique_id + '_' + domain
                base = self._unique_id + '/' + domain + '/'

            # Собираем JSON в bytearray. Это в 2-3 раза дружелюбнее к куче ESP8266, чем str.join()
            payload = bytearray()
            payload += b'{"name":"'
            payload += (entity.name() or domain).encode()
            payload += b'","unique_id":"'
            payload += uid.encode()
            payload += b'","availability_topic":"'
            payload += self._availability_topic().encode()
            payload += b'","payload_available":"online","payload_not_available":"offline"'
            payload += b',"device":{"identifiers":["'
            payload += self._unique_id.encode()
            payload += b'"],"name":"'
            payload += self._name.encode()
            payload += b'"}'

            for t in entity.discovery_data().get('topic_types', []):
                payload += (',"' + t + '_topic":"' + base + t + '"').encode()

            props = entity.discovery_data().get('properties', {})
            if 'brightness_scale' in props:
                payload += (',"brightness_scale":' + str(props['brightness_scale']).encode() +
                           ',"supported_color_modes":["brightness"]').encode()

            payload += b'}'

            config_topic = self._client.discovery_prefix() + '/' + domain + '/' + uid + '/config'
            print('📤 Discovery:', config_topic)
            # bytearray проходит в publish() без конвертации, минуя ujson
            self._client.publish(config_topic, payload, retain=True)
            time.sleep_ms(30)
        except Exception as e:
            print('ERROR: Discovery failed:', e)
            import sys
            sys.print_exception(e)

    def _publish_entity_state(self, entity):
        try:
            updates = entity.state_updates()
            self._on_entity_state_changed(entity, updates)
        except: pass

    def _flush_pending_states(self):
        if not self._pending_states: return
        pending = self._pending_states
        self._pending_states = {}
        for key, (entity, updates) in pending.items():
            try:
                for topic_type, payload in updates.items():
                    topic_path = self._make_topic_path(entity, topic_type)
                    self._client.publish(topic_path, payload, retain=True)
            except Exception:
                self._pending_states[key] = (entity, updates)

    def register_entity(self, entity):
        entity_state_key = self._entity_state_key(entity)
        if entity_state_key in self._entities: raise ValueError(f'Entity {entity.domain()}/{entity.key()} already registered')
        self._entities[entity_state_key] = entity
        entity.set_state_callback(self._on_entity_state_changed)
        if self._client.connected():
            self._register_routes(entity)
            self._publish_discovery(entity)
            self._publish_entity_state(entity)

    def setup_entities(self):
        time.sleep_ms(200)
        for entity in self._entities.values():
            self._register_routes(entity)
            self._publish_discovery(entity)
            self._publish_entity_state(entity)

    def _reconnect(self):
        if not self._ensure_wlan():
            time.sleep(1)
            return False
        try: self._client.disconnect()
        except: pass
        time.sleep(1)
        try:
            self._client.connect()
            self._publish_online()
            self.setup_entities()
            self._flush_pending_states()
            self._reconnect_backoff = 5
            return True
        except Exception:
            self._reconnect_backoff = min(self._reconnect_backoff * 2, self._max_backoff)
            return False

    def run(self, loop_delay=0.5, timeout_ms=15000):
        '''Главный цикл с WiFi-watchdog.'''
        while True:
            if self._ensure_wlan():
                try:
                    self._client.connect()
                    break
                except Exception: pass
            time.sleep(self._reconnect_backoff)

        self._publish_online()
        self.setup_entities()
        error_count = 0
        try:
            watchdog = WDT(timeout=timeout_ms)
        except (ValueError, TypeError):
            watchdog = WDT()

        while True:
            try:
                if watchdog: watchdog.feed()

                if not self._ensure_wlan():
                    error_count += 1
                    if error_count >= 3:
                        # FIX: Кормим WDT перед долгой операцией reconnect
                        if watchdog: watchdog.feed()
                        if self._reconnect(): error_count = 0
                        else: time.sleep(self._reconnect_backoff)
                    else:
                        time.sleep(1)
                    continue

                self._client.get_messages()
                for entity in self._entities.values():
                    entity.update()
                for cb in self._loop_callbacks:
                    try: cb()
                    except: pass
                if self._pending_states:
                    self._flush_pending_states()
                error_count = 0

                try:
                    # FIX: GC вызывается только при нехватке памяти (<10KB), чтобы избежать фризов
                    if gc.mem_free() < 10000:
                        gc.collect()
                except AttributeError:
                    gc.collect()
                time.sleep(loop_delay)
            except Exception:
                error_count += 1
                if error_count >= 3:
                    if watchdog: watchdog.feed()
                    if self._reconnect(): error_count = 0
                    else: time.sleep(self._reconnect_backoff)
                else:
                    time.sleep(0.5)
