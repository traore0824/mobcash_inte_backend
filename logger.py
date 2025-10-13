import logging
import sys

class ColorFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': '\033[94m',    # Blue
        'INFO': '\033[92m',     # Green
        'WARNING': '\033[93m',  # Yellow
        'ERROR': '\033[91m',    # Red
        'CRITICAL': '\033[95m', # Magenta
        'RESET': '\033[0m',
    }

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        message = super().format(record)
        return f"{color}{message}{self.COLORS['RESET']}"

class LoggerService:
    _logger = None

    @classmethod
    def get_logger(cls):
        if cls._logger is None:
            cls._logger = logging.getLogger("BoxLogger")
            handler = logging.StreamHandler(sys.stdout)
            formatter = ColorFormatter('[%(levelname)s] %(asctime)s - %(message)s', "%Y-%m-%d %H:%M:%S")
            handler.setFormatter(formatter)
            cls._logger.addHandler(handler)
            cls._logger.setLevel(logging.DEBUG)
            cls._logger.propagate = False
        return cls._logger

    @classmethod
    def d(cls, message):
        cls.get_logger().debug(message)

    @classmethod
    def i(cls, message):
        cls.get_logger().info(message)

    @classmethod
    def w(cls, message):
        cls.get_logger().warning(message)

    @classmethod
    def e(cls, message):
        cls.get_logger().error(message)

    @classmethod
    def c(cls, message):
        cls.get_logger().critical(message) 