from machine import PWM
from gpio import Pin

_CMD_ON = const('ON')
_CMD_OFF = const('OFF')
_STATE_ON = const('ON')
_STATE_OFF = const('OFF')

class MQTTAbstractEntity:
    def __init__(self, key=None, name=None):
        self._key = key
        self._name = name or key or ''
        self._state_callback = None

    def key(self): return self._key
    def name(self): return self._name
    def domain(self): raise NotImplementedError
    def set_state_callback(self, callback): self._state_callback = callback
    def _notify_state_changed(self):
        if self._state_callback: self._state_callback(self, self.state_updates())
    def message_handlers(self): raise NotImplementedError
    def state_updates(self): raise NotImplementedError
    def discovery_data(self): raise NotImplementedError
    def update(self): pass

class MQTTSwitchEntity(MQTTAbstractEntity):
    def __init__(self, gpio, key=None, name=None):
        super().__init__(key, name)
        if not isinstance(gpio, Pin): raise TypeError('gpio must be Pin instance')
        self._gpio = gpio
        self._state = bool(self._gpio.value())

    def domain(self): return 'switch'
    def message_handlers(self): return {'command': self._handle_command}

    def _handle_command(self, payload):
        if payload == _CMD_ON: new_state = True
        elif payload == _CMD_OFF: new_state = False
        else: return False
        if new_state != self._state:
            self._state = new_state
            self._gpio.value(1 if new_state else 0)
            self._notify_state_changed()
            return True
        return False

    def state_updates(self): return {'state': _STATE_ON if self._state else _STATE_OFF}
    def toggle(self): return self._handle_command(_CMD_ON if not self._state else _CMD_OFF)
    def discovery_data(self):
        return {
            'topic_types': ['command', 'state'],
            'properties': {'payload_on': _CMD_ON, 'payload_off': _CMD_OFF}
        }

class MQTTLightEntity(MQTTAbstractEntity):
    # FIX: Утилиты для совместимости duty/duty_u16 в разных версиях MicroPython
    @staticmethod
    def _get_pwm_duty(pwm_obj):
        if hasattr(pwm_obj, 'duty_u16'):
            return pwm_obj.duty_u16() >> 6
        return pwm_obj.duty()

    def _set_pwm_duty(self, pwm_obj, value):
        # scale 0-1023 -> 0-65535
        v16 = min(65535, int(value * 65535 / self._brightness_scale))
        if hasattr(pwm_obj, 'duty_u16'):
            pwm_obj.duty_u16(v16)
        else:
            pwm_obj.duty(value)

    def __init__(self, gpio, key=None, name=None, brightness_scale=1023):
        super().__init__(key, name)
        self._brightness_scale = brightness_scale
        if isinstance(gpio, PWM):
            self._brightness_enabled = True
            self._pwm = gpio
            self._gpio = None
            # FIX: Чтение текущего duty через совместимый метод
            self._current_brightness = self._get_pwm_duty(self._pwm)
            self._state = self._current_brightness > 0
        elif isinstance(gpio, Pin):
            self._brightness_enabled = False
            self._gpio = gpio
            self._pwm = None
            self._state = bool(self._gpio.value())
            self._current_brightness = 0
        else:
            raise TypeError('gpio must be Pin or PWM instance')

    def domain(self): return 'light'
    def message_handlers(self):
        handlers = {'command': self._handle_command}
        if self._brightness_enabled:
            handlers['brightness_command'] = self._handle_brightness_command
        return handlers

    def _handle_command(self, payload):
        new_state = None
        new_brightness = None
        if payload == _CMD_ON:
            new_state = True
            if self._brightness_enabled and self._current_brightness == 0:
                new_brightness = self._brightness_scale
        elif payload == _CMD_OFF:
            new_state = False
        else:
            try:
                import ujson
                data = ujson.loads(payload)
                if data.get('state') == _CMD_ON:
                    new_state = True
                    if 'brightness' in data:
                        new_brightness = max(0, min(data['brightness'], self._brightness_scale))
                elif data.get('state') == _CMD_OFF:
                    new_state = False
            except: return False
        return self._apply_state(new_state, new_brightness)

    def _handle_brightness_command(self, payload):
        try: brightness = int(payload)
        except ValueError: return False
        brightness = max(0, min(brightness, self._brightness_scale))
        return self._apply_state(None, brightness)

    def _apply_state(self, new_state, new_brightness):
        changed = False
        if new_state is not None and new_state != self._state:
            self._state = new_state
            changed = True
        if new_brightness is not None and new_brightness != self._current_brightness:
            self._current_brightness = new_brightness
            changed = True

        if self._brightness_enabled:
            if self._state and self._current_brightness > 0:
                # FIX: Запись через совместимый метод
                self._set_pwm_duty(self._pwm, self._current_brightness)
            else:
                self._set_pwm_duty(self._pwm, 0)
            actual_state = self._current_brightness > 0
            if actual_state != self._state:
                self._state = actual_state
                changed = True
        else:
            self._gpio.value(1 if self._state else 0)

        if changed: self._notify_state_changed()
        return changed

    def state_updates(self):
        result = {'state': _STATE_ON if self._state else _STATE_OFF}
        if self._brightness_enabled:
            result['brightness_state'] = str(self._current_brightness)
        return result

    def discovery_data(self):
        topic_types = ['command', 'state']
        properties = {'payload_on': _CMD_ON, 'payload_off': _CMD_OFF}
        if self._brightness_enabled:
            topic_types.extend(['brightness_command', 'brightness_state'])
            properties['brightness_scale'] = self._brightness_scale
            # FIX: Добавлено для поддержки слайдера яркости в современных версиях Home Assistant
            properties['supported_color_modes'] = ['brightness']
        return {
            'topic_types': topic_types,
            'properties': properties
        }
