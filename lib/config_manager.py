import os
import sys

_CONFIG_DIR = 'config'
_STATE_DIR = 'state'

# MessagePack markers
_MP_NIL = 0xc0
_MP_FALSE = 0xc2
_MP_TRUE = 0xc3
_MP_UINT8 = 0xcc
_MP_UINT16 = 0xcd
_MP_UINT32 = 0xce
_MP_INT8 = 0xd0
_MP_INT16 = 0xd1
_MP_INT32 = 0xd2
_MP_STR8 = 0xd9
_MP_STR16 = 0xda
_MP_ARRAY16 = 0xdc
_MP_MAP16 = 0xde


def _ensure_state_dir():
    try:
        os.mkdir(_STATE_DIR)
    except OSError:
        pass


def _normalize_keys(obj):
    """Рекурсивно привести все ключи dict к строкам."""
    if isinstance(obj, dict):
        return {str(k): _normalize_keys(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_normalize_keys(v) for v in obj]
    return obj

def _deep_update(base, overlay):
    """Рекурсивно обновить base значениями из overlay. Список/кортеж перезаписываются целиком."""
    for key, value in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


def _pack_value(v, buf):
    """Упаковка значения в MessagePack"""
    if v is None:
        buf.append(_MP_NIL)
    elif v is True:
        buf.append(_MP_TRUE)
    elif v is False:
        buf.append(_MP_FALSE)
    elif isinstance(v, int):
        if 0 <= v <= 127:
            buf.append(v)
        elif -32 <= v < 0:
            buf.append(0xe0 + (v + 32))
        elif 0 <= v <= 255:
            buf.extend([_MP_UINT8, v])
        elif -128 <= v <= 127:
            buf.extend([_MP_INT8, v & 0xff])
        elif 0 <= v <= 65535:
            buf.extend([_MP_UINT16, (v >> 8) & 0xff, v & 0xff])
        elif -32768 <= v <= 32767:
            buf.extend([_MP_INT16, (v >> 8) & 0xff, v & 0xff])
        else:
            buf.extend([_MP_INT32,
                       (v >> 24) & 0xff, (v >> 16) & 0xff,
                       (v >> 8) & 0xff, v & 0xff])
    elif isinstance(v, str):
        b = v.encode('utf-8')
        l = len(b)
        if l <= 255:
            buf.extend([_MP_STR8, l])
        else:
            buf.extend([_MP_STR16, (l >> 8) & 0xff, l & 0xff])
        buf.extend(b)
    elif isinstance(v, (list, tuple)):
        l = len(v)
        if l <= 15:
            buf.append(0x90 | l)
        else:
            buf.extend([_MP_ARRAY16, (l >> 8) & 0xff, l & 0xff])
        for item in v:
            _pack_value(item, buf)
    elif isinstance(v, dict):
        l = len(v)
        if l <= 15:
            buf.append(0x80 | l)
        else:
            buf.extend([_MP_MAP16, (l >> 8) & 0xff, l & 0xff])
        for k, val in v.items():
            _pack_value(str(k), buf)
            _pack_value(val, buf)


def _unpack_value(it):
    """Распаковка значения из MessagePack"""
    try:
        b = next(it)
    except StopIteration:
        raise ValueError("unexpected end of data")

    if b <= 0x7f:
        return b
    if b >= 0xe0:
        return b - 256

    if b == _MP_NIL:
        return None
    if b == _MP_FALSE:
        return False
    if b == _MP_TRUE:
        return True

    if b == _MP_UINT8:
        return next(it)
    if b == _MP_UINT16:
        return (next(it) << 8) | next(it)
    if b == _MP_UINT32:
        return (next(it) << 24) | (next(it) << 16) | (next(it) << 8) | next(it)
    if b == _MP_INT8:
        v = next(it)
        return v - 256 if v >= 128 else v
    if b == _MP_INT16:
        v = (next(it) << 8) | next(it)
        return v - 65536 if v >= 32768 else v
    if b == _MP_INT32:
        v = (next(it) << 24) | (next(it) << 16) | (next(it) << 8) | next(it)
        return v - 4294967296 if v >= 2147483648 else v

    if (b & 0xe0) == 0xa0:
        l = b & 0x1f
        return bytes([next(it) for _ in range(l)]).decode('utf-8')
    if b == _MP_STR8:
        l = next(it)
        return bytes([next(it) for _ in range(l)]).decode('utf-8')
    if b == _MP_STR16:
        l = (next(it) << 8) | next(it)
        return bytes([next(it) for _ in range(l)]).decode('utf-8')

    if (b & 0xf0) == 0x90:
        l = b & 0x0f
        return [_unpack_value(it) for _ in range(l)]
    if b == _MP_ARRAY16:
        l = (next(it) << 8) | next(it)
        return [_unpack_value(it) for _ in range(l)]

    if (b & 0xf0) == 0x80:
        l = b & 0x0f
        d = {}
        for _ in range(l):
            k = _unpack_value(it)
            v = _unpack_value(it)
            if isinstance(k, (list, dict)):
                raise ValueError(f"invalid map key type: {type(k)}")
            if not isinstance(k, str):
                k = str(k)
            d[k] = v
        return d
    if b == _MP_MAP16:
        l = (next(it) << 8) | next(it)
        d = {}
        for _ in range(l):
            k = _unpack_value(it)
            v = _unpack_value(it)
            if isinstance(k, (list, dict)):
                # Поврежденные данные: ключ не может быть контейнером
                raise ValueError(f"invalid map key type: {type(k)}")
            if not isinstance(k, str):
                k = str(k)
            d[k] = v
        return d

    raise ValueError(f'unknown marker: 0x{b:02x}')


def _pack(data):
    """Упаковать данные в MessagePack"""
    buf = bytearray()
    _pack_value(data, buf)
    return bytes(buf)


def _unpack(data):
    """Распаковать данные из MessagePack"""
    return _unpack_value(iter(data))


def load(config_file, defaults={}, state_file=None):
    """
    Загрузка конфигурации: defaults -> config/module.py -> state/file (глубокий merge)

    Args:
        defaults: dict с дефолтами
        config_file: имя модуля в config/ (без .py), или None
        state_file: имя файла состояния (без пути и расширения), или None

    Returns:
        dict с итоговой конфигурацией
    """
    result = dict(defaults) if defaults else {}
    if state_file is None:
        state_file = config_file

    # Загружаем из config/xxx.py
    if config_file:
        try:
            full_name = f'{_CONFIG_DIR}.{config_file}'
            if full_name in sys.modules:
                del sys.modules[full_name]
            mod = __import__(full_name, None, None, ['*'])
            for attr in dir(mod):
                if not attr.startswith('_'):
                    result[attr] = getattr(mod, attr)
        except (ImportError, OSError):
            pass

    # Нормализуем ключи базового конфига перед мержем
    result = _normalize_keys(result)

    # Загружаем из state/xxx.mp и рекурсивно мержим
    if state_file:
        state_data = load_state(state_file)
        # state_data уже строки (т.к. save_state пишет str(k)),
        _deep_update(result, state_data)

    return result


def load_state(name):
    """
    Загрузить данные из state/name.mp (MessagePack)

    Args:
        name: имя файла (без пути и расширения)
    """
    state_path = f'{_STATE_DIR}/{name}.mp'
    try:
        with open(state_path, 'rb') as f:
            state_data = _unpack(f.read())
            if isinstance(state_data, dict):
                return _normalize_keys(state_data)
    except (OSError, ValueError, TypeError):
        # Ошибка чтения state: удаляем поврежденный файл, продолжаем с defaults+config
        try:
            os.remove(state_path)
        except OSError:
            pass

    return {}


def save_state(name, data):
    """
    Сохранить данные в state/name.mp (MessagePack)

    Args:
        name: имя файла (без пути и расширения)
        data: любые данные, поддерживаемые MessagePack
    """
    _ensure_state_dir()
    path = f'{_STATE_DIR}/{name}.mp'
    temp = f'{path}.tmp'
    with open(temp, 'wb') as f:
        f.write(_pack(data))
    os.rename(temp, path)


def update_state(name, key, value):
    """
    Частичное обновление: загрузить state, изменить ключ, сохранить

    Args:
        name: имя файла состояния
        key: ключ для обновления
        value: новое значение
    """
    current = load_state(name)
    current[key] = value
    save_state(name, current)
