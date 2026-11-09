def setup():
    import state_manager
    from config_manager import load as load_config

    webrepl_config = load_config('webrepl', {
        'ENABLED': True,
        'PASSWORD': '',
        'PORT': 8266,
        'DISABLE_ON_STA_SUCCESS': False,
        'SHOW_PASSWORD': True,
    })

    sta_connected = state_manager.wlan_sta and state_manager.wlan_sta.isconnected()
    if webrepl_config['ENABLED'] and not (sta_connected and webrepl_config['DISABLE_ON_STA_SUCCESS']):
        import webrepl
        webrepl.start(password=webrepl_config['PASSWORD'], port=webrepl_config['PORT'])
        if webrepl_config['SHOW_PASSWORD']:
            print(f'Password: {webrepl_config["PASSWORD"]}')
        print()
