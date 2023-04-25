import datetime
import json
import logging


class JsonFormatter(logging.Formatter):
    def __init__(self, datefmt=None):
        super().__init__()
        self.fmt = {
            "level": "levelname",
            "time": "asctime",
            "aws-request-id": "aws_request_id",
            "message": "message",
            "request": "request",
            "response": "response",
        }
        self.datefmt = datefmt

    # Appended '_' on 'converter' because mypy doesn't approve of
    # overwriting a base class variable with another type.
    converter_ = datetime.datetime.fromtimestamp

    default_time_format = "%Y-%m-%d %H:%M:%S"
    default_msec_format = "%s.%03d"

    def formatTime(self, record, datefmt=None):
        ct = self.converter_(record.created, datetime.timezone.utc)
        if datefmt:
            s = ct.strftime(datefmt)
        else:
            s = ct.strftime(self.default_time_format)
            if self.default_msec_format:
                s = self.default_msec_format % (s, record.msecs)
        return s

    def formatMessage(self, record):
        return {k: record.__dict__.get(v) for k, v in self.fmt.items()}

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
