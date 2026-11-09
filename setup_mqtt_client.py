def setup():
    import state_manager
    from config_manager import load as load_config
    from mqtt_client import MQTTClient

    broker_config = load_config('mqtt_broker')
    broker_address = broker_config.get('ADDRESS', 'NOT SET')
    broker_port = int(broker_config.get('PORT', 1883))
    print(f'Broker: {broker_address}:{broker_port}')

    if not broker_config.get('ADDRESS'):
        raise ValueError('MQTT broker ADDRESS not configured')

    mqtt_client = MQTTClient(
        client_id        = state_manager.device_info.get('id'),
        broker_address   = broker_address,
        broker_port      = broker_port,
        user             = broker_config.get('USER', ''),
        password         = broker_config.get('PASSWORD', ''),
        discovery_prefix = broker_config.get('DISCOVERY_PREFIX', 'homeassistant'),
        publish_retries  = int(broker_config.get('PUBLISH_RETRIES', 3)),
        keepalive        = int(broker_config.get('KEEPALIVE', 60)),
    )

    mqtt_client.set_last_will(
        topic=f"{state_manager.device_info['id']}/availability",
        payload='offline',
        retain=True,
        qos=1  # или 0
    )

    state_manager.mqtt_client = mqtt_client

    print('MQTT client created')
