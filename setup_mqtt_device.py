def setup():
    import state_manager
    from mqtt_device import MQTTDevice
    from setup_wlan import ensure_wlan_connected

    mqtt_device = MQTTDevice(
        unique_id           = state_manager.device_info.get('id'),
        name                = state_manager.device_info.get('name'),
        model               = state_manager.device_info.get('model'),
        manufacturer        = state_manager.device_info.get('manufacturer'),
        client              = state_manager.mqtt_client,
    )

    mqtt_device.register_connectivity_callback(ensure_wlan_connected)
    mqtt_device.register_loop_callback(state_manager.persist_gpio)

    state_manager.mqtt_device = mqtt_device

    print('MQTT device created')

    print(f'Registering {len(state_manager.mqtt_entities)} entities...')

    registered = 0
    failed = 0

    for i, entity in enumerate(state_manager.mqtt_entities):
        try:
            mqtt_device.register_entity(entity)
            entity_name = entity.name()
            entity_key = entity.key()
            print(f' [{i+1}/{len(state_manager.mqtt_entities)}] Registered: {entity_key} ({entity_name})')
            registered += 1
        except Exception as e:
            entity_key = entity.key() if hasattr(entity, 'key') else f'entity_{i}'
            print(f' [{i+1}/{len(state_manager.mqtt_entities)}] FAILED: {entity_key} - {e}')
            failed += 1

    print(f'Registration complete: {registered} ok, {failed} failed')

    if registered == 0:
        print('WARNING: No entities registered, nothing to control!')
