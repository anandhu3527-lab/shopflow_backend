import logging
import json
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="")

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "name": record.name,
            "request_id": request_id_var.get(),
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)

def setup_logging(log_level: str = "INFO"):
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    
    # Remove existing handlers to avoid duplicates
    for h in logger.handlers[:]:
        logger.removeHandler(h)
        
    logger.addHandler(handler)
