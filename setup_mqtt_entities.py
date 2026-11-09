def setup():
    import state_manager
    from config_manager import load as load_config
    from mqtt_entity import MQTTSwitchEntity, MQTTLightEntity
    from gpio import Pin
    from machine import PWM

    state_manager.mqtt_entities = []
    entities_config = load_config('mqtt_entities')

    for key, config in entities_config.get('SWITCH', {}).items():
        try:
            gpio_id = config.get('GPIO')
            if gpio_id is None:
                print(f'Entity {key}: missing GPIO')
                continue

            gpio_id = int(gpio_id)
            gpio_obj = state_manager.gpio.get(gpio_id)

            if gpio_obj is None:
                print(f'Entity {key}: GPIO{gpio_id} not found in state_manager')
                continue

            if not isinstance(gpio_obj, Pin):
                print(f'Entity {key}: cannot use not Pin GPIO {gpio_id} for switch')
                continue

            entity = MQTTSwitchEntity(
                gpio=gpio_obj,
                key=key,
                name=config.get('NAME', key)
            )

            state_manager.mqtt_entities.append(entity)
            print(f'Entity {key}: SWITCH on GPIO {gpio_id}')

        except Exception as e:
            print(f'Entity {key} SWITCH config error: {e}')

    for key, config in entities_config.get('LIGHT', {}).items():
        try:
            gpio_id = config.get('GPIO')
            if gpio_id is None:
                print(f'Entity {key}: missing GPIO')
                continue

            gpio_id = int(gpio_id)
            gpio_obj = state_manager.gpio.get(gpio_id)

            if gpio_obj is None:
                print(f'Entity {key}: GPIO{gpio_id} not found in state_manager')
                continue

            brightness_scale = config.get('BRIGHTNESS_SCALE', 1023)
            try:
                brightness_scale = int(brightness_scale)
            except:
                brightness_scale = 1023

            entity = MQTTLightEntity(
                gpio=gpio_obj,
                key=key,
                name=config.get('NAME', key),
                brightness_scale=brightness_scale
            )

            state_manager.mqtt_entities.append(entity)

            mode = 'PWM' if isinstance(gpio_obj, PWM) else 'ON/OFF'
            print(f'Entity {key}: LIGHT ({mode}) on GPIO {gpio_id}')

        except Exception as e:
            print(f'Entity {key} LIGHT config error: {e}')
