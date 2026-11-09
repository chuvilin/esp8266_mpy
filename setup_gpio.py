def setup():
    import state_manager
    from config_manager import load as load_config
    from gpio import Pin
    from machine import PWM

    state_manager.gpio = {}
    gpio_config = load_config('gpio')

    for pin_id, config in gpio_config.get('OUTPUT', {}).items():
        try:
            pin_id = int(pin_id)

            if isinstance(config, dict):
                pin_value = config.get('VALUE', 0)
                try:
                    pin_inverted = bool(config.get('INVERTED', False))
                except:
                    pin_inverted = False
            else:
                pin_value = int(config)
                pin_inverted = False

            try:
                pin_value = int(pin_value)
            except:
                pin_value = 0

            pin = Pin(pin_id, Pin.OUT, value=pin_value, inverted=pin_inverted)

            if pin_id in state_manager.gpio:
                del state_manager.gpio[pin_id]
            state_manager.gpio[pin_id] = pin

            print(f'GPIO {pin_id}: OUTPUT value={pin_value} inverted={pin_inverted}')

        except Exception as e:
            print(f'GPIO {pin_id} OUTPUT config error: {e}')

    for pin_id, config in gpio_config.get('PWM', {}).items():
        try:
            pin_id = int(pin_id)

            if isinstance(config, dict):
                pwm_duty = config.get('DUTY', 0)
                try:
                    pwm_freq = int(config.get('FREQUENCY', 1000))
                except:
                    pwm_freq = 1000
            else:
                pwm_duty = config
                pwm_freq = 1000

            try:
                pwm_duty = int(pwm_duty)
            except:
                pwm_duty = 0

            pwm = PWM(Pin(pin_id, Pin.OUT), freq=pwm_freq, duty=pwm_duty)

            if pin_id in state_manager.gpio:
                del state_manager.gpio[pin_id]
            state_manager.gpio[pin_id] = pwm

            print(f'GPIO {pin_id}: PWM freq={pwm_freq} duty={pwm_duty}')

        except Exception as e:
            print(f'GPIO {pin_id} PWM config error: {e}')

    for pin_id, config in gpio_config.get('INPUT', {}).items():
        try:
            pin_id = int(pin_id)

            if isinstance(config, dict):
                pin_pull = config.get('PULL', 'UP')
                try:
                    pin_inverted = bool(config.get('INVERTED', False))
                except:
                    pin_inverted = False
            else:
                pin_pull = config
                pin_inverted = False

            if pin_pull == 'UP':
                pin_pull = Pin.PULL_UP
            elif pin_pull == 'DOWN':
                pin_pull = Pin.PULL_DOWN
            else:
                pin_pull = None

            if pin_pull is None:
                pin = Pin(pin_id, Pin.IN, inverted=pin_inverted)
            else:
                pin = Pin(pin_id, Pin.IN, pull=pin_pull, inverted=pin_inverted)

            if pin_id in state_manager.gpio:
                del state_manager.gpio[pin_id]
            state_manager.gpio[pin_id] = pin

            print(f'GPIO {pin_id}: INPUT pull={pin_pull}  inverted={pin_inverted}')

        except Exception as e:
            print(f'GPIO {pin_id} INPUT config error: {e}')

    # ToDo: parse ADC

    # ToDo: подумать, как логику переключения режимов перенести в entity

    # === Power-on reset: toggle outputs ===
    from machine import reset_cause, PWRON_RESET
    from config_manager import load_state

    # Переключаем только если это включение питания И есть предыдущее состояние.
    # Если state-файла ещё нет (первый запуск в жизни) — просто оставляем как в конфиге.
    print("Reset couse:", reset_cause())
    if reset_cause() == PWRON_RESET and load_state('gpio'):
        print("Reverse GPIO due to poweroff cause")
        toggled = False
        for pin_id, gpio_obj in state_manager.gpio.items():
            if isinstance(gpio_obj, Pin) and gpio_obj.mode() == Pin.OUT:
                # value() без аргументов возвращает логическое значение с учётом inverted
                current = gpio_obj.value()
                gpio_obj.value(not current)
                toggled = True
                print(f'GPIO {pin_id}: toggled to {not current} (PWRON_RESET)')
        if toggled:
            # Сразу сохраняем новое состояние, чтобы при быстром повторном
            # выключении/включении питания тоггл шёл от актуального значения,
            # а не от устаревшего в flash.
            state_manager.persist_gpio(force=True)
