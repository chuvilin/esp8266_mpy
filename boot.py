import sys

try:
    from setup_gpio import setup as setup_gpio
    setup_gpio()
    del setup_gpio
except Exception as e:
    print('⚠️ Cannot setup GPIO:', e)
    sys.print_exception(e)
print()

try:
    from setup_mqtt_entities import setup as setup_mqtt_entities
    setup_mqtt_entities()
    del setup_mqtt_entities
except Exception as e:
    print('⚠️ Cannot setup MQTT entities:', e)
    sys.print_exception(e)
print()

try:
    from setup_device_info import setup as setup_device_info
    setup_device_info()
    del setup_device_info
except Exception as e:
    print('⚠️ Cannot setup device info:', e)
    sys.print_exception(e)
print()

try:
    from setup_wlan import setup as setup_wlan
    setup_wlan()
    del setup_wlan
except Exception as e:
    print('⚠️ Cannot setup WLAN:', e)
    sys.print_exception(e)
print()

try:
    from setup_webrepl import setup as setup_webrepl
    setup_webrepl()
    del setup_webrepl
except Exception as e:
    print('⚠️ Cannot setup WebREPL:', e)
    sys.print_exception(e)
print()

import gc
gc.collect()
