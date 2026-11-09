import time
from gpio import Pin
from machine import PWM
from config_manager import save_state

gpio = {}
device_info = {}
wlan_sta = None
wlan_sta_config = {}
mqtt_entities = []
mqtt_client = None
mqtt_device = None

# === GPIO persistence ===
_SAVE_INTERVAL_MS = 60000  # 1 минута
_last_gpio_save = 0
_last_gpio_states = {}

def persist_gpio(force=False):
    """Сохранить текущие OUTPUT/PWM во flash (state/gpio.mp).

    Пишет только если:
    - force=True, или
    - прошло >= 1 минуты, и
    - состояние реально изменилось с момента последней записи.

    Формат совместим с config/gpio.py для корректного deep merge.
    """
    global _last_gpio_save, _last_gpio_states

    now = time.ticks_ms()
    if not force:
        if time.ticks_diff(now, _last_gpio_save) < _SAVE_INTERVAL_MS:
            return False

    states = {}

    output = {}
    pwm = {}
    for pin_id, gpio_obj in gpio.items():
        try:
            if isinstance(gpio_obj, PWM):
                d = gpio_obj.duty()
                f = gpio_obj.freq()
                if d is not None:
                    pwm[pin_id] = {'DUTY': d, 'FREQUENCY': f}
            elif isinstance(gpio_obj, Pin) and gpio_obj.mode() == Pin.OUT:
                output[pin_id] = {'VALUE': gpio_obj.value()}
        except Exception:
            pass

    if output:
        states['OUTPUT'] = output
    if pwm:
        states['PWM'] = pwm

    if not states:
        return False

    # Дедупликация: если ничего не поменялось — не трогаем flash
    if not force and states == _last_gpio_states:
        _last_gpio_save = now
        return False

    try:
        save_state('gpio', states)
        _last_gpio_states = states
        _last_gpio_save = now
        if force:
            print('GPIO state persisted (forced)')
        return True
    except Exception as e:
        print(f'GPIO persist error: {e}')
        return False
