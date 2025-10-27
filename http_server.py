from typing import *
import os
import uuid
import asyncio
import traceback
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from shutil import rmtree

import uvicorn
from pydantic import create_model
from dotenv import load_dotenv
from aiofiles import open as aopen

from fastapi import FastAPI, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html

from chatbots import CmccChatClient
from logg import logger, LOGGER_DIR, WORK_DIR
from schemas import SendMessage, HttpMessageStatus, HttpMessageStatusBase
from tools import async_wrapper,send_stable,b64decode, DB_Client

load_dotenv(dotenv_path=WORK_DIR / ".env", override=True)
WAIT_BEFORE_REFRESH=os.getenv("WAIT_BEFORE_REFRESH",5)
print(f"WAIT_BEFORE_REFRESH: {WAIT_BEFORE_REFRESH}")
WAIT_BEFORE_REFRESH=float(WAIT_BEFORE_REFRESH)

chatbot_client = CmccChatClient(cache_session_map=False, wait_before_refresh=WAIT_BEFORE_REFRESH)
message_queue = asyncio.Queue()
message_semaphore = asyncio.Semaphore(1) # UI操作是不可抢占的
consumer_tasks:List[asyncio.Task] = []
temp_dir = tempfile.mkdtemp(prefix="desktop-chatbot")
db_client: DB_Client = None


async def execute_send_message():
    "consumer function"
    global db_client
    while True:
        message:SendMessage = await message_queue.get()
        message_id = str(message.id)
        send_to = message.FromWxid

        async with message_semaphore:
            #NOTE send text message if exists
            if message.Content:
                try:
                    at_list = []
                    if message.SenderWxid:
                        at_list.append(message.SenderWxid)
                    content = " ".join(["@"+i for i in at_list]) + " " +message.Content
                    await async_wrapper(
                        send_stable,
                        chatbot_client,
                        chatbot_client.send_message,
                        session_name=message.FromWxid,
                        message=message.Content,
                        from_clipboard=True,
                        at_list=at_list
                    )
                except Exception as exc:
                    logger.error(traceback.format_exc())
                    message_status = HttpMessageStatusBase(
                        message_id=message_id,
                        send_to=send_to,
                        content=content,
                        success=False, failure_reason=str(exc))
                else:
                    message_status = HttpMessageStatusBase(
                        message_id=message_id,
                        send_to=send_to,
                        content=content,
                        success=True)

                try: #NOTE needs to catch error here, else asyncio task ignores it and keeps go on.
                    result = await db_client.create(message_status, HttpMessageStatus)
                    await async_wrapper(logger.info, f"[text message sent] {message_id}")
                except Exception as e:
                    raise Exception(e) from e
            #NOTE send file if exists
            if message.File:
                try:
                    filename = message.Filename or str(uuid.uuid4())
                    content = "[file] filename: %s" % filename
                    b64decoded_bytes,mime_type = b64decode(message.File)
                    temp_filepath=Path(temp_dir) / filename
                    async with aopen(str(temp_filepath),"wb") as f:
                        await f.write(b64decoded_bytes)
                    await async_wrapper(
                        send_stable,
                        chatbot_client,
                        chatbot_client.send_file,
                        session_name=message.FromWxid,
                        filepath=temp_filepath
                    )
                except Exception as exc:
                    logger.error(traceback.format_exc())
                    message_status = HttpMessageStatusBase(
                        message_id=message_id,
                        send_to=send_to,
                        content=content,
                        success=False, failure_reason=str(exc))
                else:
                    message_status = HttpMessageStatusBase(
                        message_id=message_id,
                        send_to=send_to,
                        content=content,
                        success=True)
                try: #NOTE needs to catch error here, else asyncio task ignores it and keeps go on.
                    result = await db_client.create(message_status, HttpMessageStatus)
                    await async_wrapper(logger.info, f"[file message sent] {message_id}")
                except Exception as e:
                    raise Exception(e) from e

            #XXX mark task done
            message_queue.task_done()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global consumer_tasks, db_client
    await async_wrapper(logger.info, "create table")
    db_client = DB_Client()
    await db_client.migrate()

    #NOTE create 4 consumers, though number of processes is limited to 1 by semaphore.
    for i in range(4):
        task = asyncio.create_task(execute_send_message())
        consumer_tasks.append(task)
    yield
    # after shut down app
    # cancel all consumers
    for t in consumer_tasks:
        t.cancel()
    await asyncio.gather(*consumer_tasks, return_exceptions=True)
    rmtree(temp_dir, ignore_errors=True) #NOTE remove all files in temp dir
    await logger.complete() #NOTE complete all logs
    logger.info("[STATUS] successsfully shuting down server")


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许的域名列表
    allow_credentials=True,  # 允许在跨域请求中使用凭证（如Cookie）
    allow_methods=["*"],  # 允许的请求方法列表，这里使用通配符表示支持所有方法
    allow_headers=["*"],  # 允许的请求头列表，这里使用通配符表示支持所有头部字段
)
app.mount("/statics",StaticFiles(directory="./statics"), "statics")

@app.get("/docs", include_in_schema=False)
async def custom_swagger_docs():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title="Swagger",
        swagger_js_url="/statics/swagger-ui-bundle.js",
        swagger_css_url="/statics/swagger-ui.css"
    )

@app.get("/redoc", include_in_schema=False)
async def custom_redoc():
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title="Redoc",
        redoc_js_url="/statics/redoc.standalone.js"
    )


@app.get("/health/", response_model=create_model("PlainTextResponse", output=(str, ...)))
async def health_check():
    return "health check good."


@app.get("/check/", response_model=create_model("JSONResponse", message_status=(HttpMessageStatus|None, ...), empty=(bool, ...)))
async def check_message_status(
    message_id: str = Query(..., title="message id", description="message id"),):
    if_empty = True
    async for result in db_client.get(HttpMessageStatus, message_id=message_id):
        if_empty=False
        return JSONResponse(content=dict(message_status=result.model_dump(mode="json"), empty=if_empty))
    if if_empty:
        return JSONResponse(content=dict(message_status=None, empty=if_empty))


json_schemas_example={
    "Business": None,
    "Content": "",
    "FromWxid": "",
    "ActualName": "",
    "Role": "",
    "SenderWxid": "",
    "File": None,
    "Filename": None,
    "id": None,
    "CreatedTime": None,
    "IsSent": None,
    "SendTime": None
}

@app.post("/receive_message/",)
async def receive_message(message:SendMessage=Body(..., example=json_schemas_example)):
    message_id = message.id
    await message_queue.put(message)
    return JSONResponse(
        content={
            "status":200,
            "message":"message received. You can use message_id to check if your message is sent properly.",
            "message_id":str(message_id)},
    )


if __name__ == '__main__':
    HOST = os.getenv("HTTP_HOST", "127.0.0.1")
    PORT = int(os.getenv("HTTP_PORT", "11451"))
    uvicorn.run(app, host=HOST,port=PORT)
