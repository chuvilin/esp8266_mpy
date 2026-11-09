def setup():
    import state_manager
    from config_manager import load as load_config
    import network
    from time import sleep

    # FIX: network.hostname() отсутствует в старых версиях MicroPython для ESP8266
    if hasattr(network, 'hostname'):
        try:
            network.hostname(state_manager.device_info['id'])
        except Exception:
            pass

    sta_config = load_config('wlan_sta', {
        'ENABLED': False, 'SSID': '', 'PASSWORD': '', 'TIMEOUT_S': 20
    })
    sta = network.WLAN(network.STA_IF)
    if sta_config['ENABLED']:
        sta.active(True)
        print(f'Connecting to {sta_config["SSID"]}...')
        sta.connect(sta_config['SSID'], sta_config['PASSWORD'])
        timeout = sta_config['TIMEOUT_S']
        while not sta.isconnected() and timeout > 0:
            sleep(1)
            timeout -= 1
            print('.', end='')
        print()
        if sta.isconnected():
            print(f'IP: {sta.ifconfig()[0]}')
        else:
            print('Cannot connect to WLAN')
    else:
        print('WLAN connection disabled')
    print()
    state_manager.wlan_sta = sta
    state_manager.wlan_sta_config = sta_config

    ap_config = load_config('wlan_ap', {
        'ENABLED': True,
        'SSID': state_manager.device_info['id'],
        'PASSWORD': '',
        'DISABLE_ON_STA_SUCCESS': True
    })
    ap = network.WLAN(network.AP_IF)
    if ap_config['ENABLED'] and not (sta.isconnected() and ap_config['DISABLE_ON_STA_SUCCESS']):
        ap.active(True)
        ssid = ap_config.get('SSID')
        if ap_config['PASSWORD']:
            ap.config(essid=ssid, password=ap_config['PASSWORD'])
        else:
            ap.config(essid=ssid, authmode=network.AUTH_OPEN)
        print(f'AP: {ssid}')
    else:
        ap.active(False)
        print('WLAN AP disabled')

def ensure_wlan_connected(timeout_s=10):
    """Проверить и восстановить STA соединение."""
    import state_manager
    from time import sleep
    if not hasattr(state_manager, 'wlan_sta') or state_manager.wlan_sta is None:
        return False
    sta = state_manager.wlan_sta
    if sta.isconnected(): return True
    if not sta.active(): sta.active(True)
    if hasattr(state_manager, 'wlan_sta_config') and state_manager.wlan_sta_config.get('ENABLED'):
        try:
            cfg = state_manager.wlan_sta_config
            sta.connect(cfg['SSID'], cfg['PASSWORD'])
        except Exception: pass
    for _ in range(timeout_s * 2):
        if sta.isconnected(): return True
        sleep(0.5)
    return False
