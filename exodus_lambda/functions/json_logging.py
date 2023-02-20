import json
import logging


class JsonFormatter(logging.Formatter):
    def __init__(self, fmt=None, datefmt="%Y-%m-%d %H:%M:%S"):
        super().__init__()
        self._fmt = fmt or {
            "level": "levelname",
            "time": "asctime",
            "name": "name",
            "message": "message",
        }
        self.dictfmt = None
        self.datefmt = datefmt

    @property
    def fmt(self):
        # If it doesn't look like JSON, fmt will always return NoneType.
        # If it looks like JSON but is invalid, fmt will raise the appropriate error.
        if not self.dictfmt:
            if isinstance(self._fmt, dict):
                self.dictfmt = self._fmt
            elif isinstance(self._fmt, str) and "{" in self._fmt:
                try:
                    self.dictfmt = json.loads(self._fmt)
                except json.JSONDecodeError:
                    logging.getLogger().exception(
                        "Unable to load JSON format: %s", self._fmt
                    )
                    raise
        return self.dictfmt

    def formatMessage(self, record):
        return {k: record.__dict__[v] for k, v in self.fmt.items()}

    def format(self, record):
        record.message = record.getMessage()

        if "asctime" in self.fmt.values():
            record.asctime = self.formatTime(record, self.datefmt)

        d = self.formatMessage(record)

        if record.exc_info:
            record.exc_text = self.formatException(record.exc_info)

        if record.exc_text:
            d["exc_info"] = record.exc_text

        if record.stack_info:
            d["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(d)
