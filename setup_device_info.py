def setup():
    import state_manager
    from binascii import hexlify
    from config_manager import load as load_config
    from machine import unique_id
    from sys import platform, implementation

    device_config = load_config('device')

    device_id = device_config.get('ID', platform + '_' + hexlify(unique_id()).decode('utf-8')[:8])
    device_name = device_config.get('NAME', device_id)
    device_model = device_config.get('MODEL', implementation._machine)
    device_manufacturer = device_config.get('MANUFACTURER', 'DIY')

    state_manager.device_info = {
        'id': device_id,
        'name': device_name,
        'model': device_model,
        'manufacturer': device_manufacturer,
    }

    print(f'Device "{device_name}", ID: {device_id}, model: {device_model} by {device_manufacturer}')
