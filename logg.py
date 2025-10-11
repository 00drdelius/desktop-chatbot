#TODO: logger is copied originally from other repo, still not revised.
import sys
from loguru import logger

logger.remove()

logger.level("API", no=1, color="<cyan>")

logger.add(
    sys.stdout,
    colorize=True,
    format="[<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {file}::{function}::{line} ] {message}",
    level="TRACE",
    enqueue=True,
    backtrace=True,
    diagnose=True,
)
logger.add(
    "logs/xybot.log",
    format="[{time:YYYY-MM-DD HH:mm:ss} | {level} | {file}::{function}::{line} ] {message}",
    encoding="utf-8",
    enqueue=True,
    rotation="10mb",
    retention="2 weeks",
    backtrace=True,
    diagnose=True,
    level="DEBUG",
)
# logger.add(
#     "logs/wechatapi.log",
#     format="[{time:YYYY-MM-DD HH:mm:ss} | {level} | {file}::{function}::{line} ] {message}",
#     level="API",
#     encoding="utf-8",
#     enqueue=True,
#     rotation="10mb",
#     retention="2 weeks",
#     backtrace=True,
#     diagnose=True,
#     filter=lambda record: record["level"].name == "API",
# )