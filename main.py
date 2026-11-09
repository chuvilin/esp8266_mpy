import gc
import state_manager

print('Starting...')

gc.collect(); gc.collect()
try:
    from setup_mqtt_client import setup as setup_mqtt_client
    setup_mqtt_client()
    del setup_mqtt_client
except Exception as e:
    print(f'CRITICAL: MQTT client init failed: {e}')
    machine.reset()

print()

gc.collect(); gc.collect()
try:
    from setup_mqtt_device import setup as setup_mqtt_device
    setup_mqtt_device()
    del setup_mqtt_device
except Exception as e:
    print(f'CRITICAL: MQTT device init failed: {e}')
    machine.reset()

gc.collect(); gc.collect()
print('Starting device loop...')
try:
    state_manager.mqtt_device.run(loop_delay=0.5)
except KeyboardInterrupt:
    print('\nInterrupted by user')
except Exception as e:
    print(f'CRITICAL ERROR in main loop: {e}')
    import sys
    sys.print_exception(e)
    import time
    time.sleep(2)
    import machine
    state_manager.persist_gpio(force=True)
    machine.reset()
