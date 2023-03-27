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
        self.datefmt = datefmt or "%Y-%m-%d %H:%M:%S"
        self.dictfmt = None

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
