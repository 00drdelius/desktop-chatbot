from typing import *
import os
import uuid
import asyncio
import base64
import traceback
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from shutil import rmtree

import uvicorn
from dotenv import load_dotenv
from aiofiles import open as aopen

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html

from schemas import SendMessage
from chatbots import CmccChatClient
from logg import logger, LOGGER_DIR, WORK_DIR

load_dotenv(dotenv_path=WORK_DIR / ".env")
WAIT_BEFORE_REFRESH=os.getenv("WAIT_BEFORE_REFRESH",5)
WAIT_BEFORE_REFRESH=float(WAIT_BEFORE_REFRESH)

chatbot_client = CmccChatClient(cache_session_map=False, wait_before_refresh=WAIT_BEFORE_REFRESH)
message_queue = asyncio.Queue()
message_semaphore = asyncio.Semaphore(1) # UI操作是不可抢占的
consumer_tasks:List[asyncio.Task] = []
temp_dir = tempfile.mkdtemp(prefix="desktop-chatbot")

def b64decode(string:str):
    string = string.removeprefix("data:")
    mime_type, file_bytes = string.split(";base64,",1)
    decoded = base64.b64decode(file_bytes)
    return decoded, mime_type

T = TypeVar("T")

async def async_wrapper(callable:Callable[..., T],*args,**kwargs) -> T:
    result = await asyncio.to_thread(callable, *args, **kwargs)
    return result

async def execute_send_message():
    "consumer function"
    while True:
        message:SendMessage = await message_queue.get()
        async with message_semaphore:
            try:
                if message.Content:
                    at_list = []
                    if message.SenderWxid:
                        at_list.append(message.SenderWxid)
                    await async_wrapper(
                        chatbot_client.send_message,
                        session_name=message.FromWxid,
                        message=message.Content,
                        from_clipboard=True,
                        at_list=at_list
                    )
                if message.File:
                    filename = message.Filename or str(uuid.uuid4())
                    b64decoded_bytes,mime_type = b64decode(message.File)
                    temp_filepath=Path(temp_dir) / filename
                    async with aopen(str(temp_filepath),"wb") as f:
                        await f.write(b64decoded_bytes)
                    temp_send_result=await async_wrapper(
                                                chatbot_client.send_file,
                                                session_name=message.FromWxid,
                                                filepath=temp_filepath
                                            )
            except Exception as exc:
                await async_wrapper(logger.error, f"[ERROR EXECUTING SENDING MSG] {exc}")
                await async_wrapper(logger.error, traceback.format_exc())
            finally:
                #XXX mark task done
                message_queue.task_done()

@asynccontextmanager
async def lifespan(app: FastAPI):
    global consumer_tasks
    # before initializing app
    # create 5 consumers, though number of processes is limited to 1 by semaphore.
    for i in range(5):
        task = asyncio.create_task(execute_send_message())
        consumer_tasks.append(task)
    yield
    # after shut down app
    # cancel all consumers
    for t in consumer_tasks:
        t.cancel()
    await asyncio.gather(*consumer_tasks, return_exceptions=True)
    rmtree(temp_dir, ignore_errors=True) #NOTE remove all files in temp dir
    logger.info("[STATUS] successsfullly shutdown server")

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许的域名列表
    allow_credentials=True,  # 允许在跨域请求中使用凭证（如Cookie）
    allow_methods=["*"],  # 允许的请求方法列表，这里使用通配符表示支持所有方法
    allow_headers=["*"],  # 允许的请求头列表，这里使用通配符表示支持所有头部字段
)

@app.get("/docs")
async def customized_swagger_docs():
    return get_swagger_ui_html(

    )


@app.get("/health/")
async def health_check():
    return "health check good."

@app.post("/receive_message/")
async def receive_message(message:SendMessage):
    await message_queue.put(message)

    return JSONResponse(
        content={"status":200,"message":"successfuly received message"},
        status_code=200,
    )


if __name__ == '__main__':
    uvicorn.run(app, host="127.0.0.1",port=11451)
