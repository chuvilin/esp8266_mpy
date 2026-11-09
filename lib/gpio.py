from machine import Pin as MachinePin

class Pin(MachinePin):
    """
    Pin с поддержкой логической инверсии (active-low).
    Наследует machine.Pin, перегружает value() для прозрачной инверсии.
    """

    def __init__(self, id, mode=-1, pull=-1, value=None, inverted=False):
        self._id = id
        self._inverted = bool(inverted)
        self._mode = mode

        if value is None:
            super().__init__(id, mode, pull=pull)
        else:
            super().__init__(id, mode, pull=pull, value=int(value) ^ self._inverted)

    def value(self, x=None):
        """Чтение/запись с учётом инверсии."""
        if x is None:
            return super().value() ^ self._inverted
        else:
            super().value(int(x) ^ self._inverted)

    def mode(self):
        """Вернуть режим, переданный при создании."""
        return self._mode

    def inverted(self):
        """Вернуть флаг инверсии."""
        return self._inverted

    def on(self):
        super().value(not self._inverted)

    def off(self):
        super().value(self._inverted)

    def __repr__(self):
        return f'Pin({self._id}{", inverted" if self._inverted else ""})'
