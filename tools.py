import os
import time
import asyncio
import base64
from typing import *

from dotenv import load_dotenv
from sqlmodel import SQLModel, select
from sqlalchemy import URL
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from logg import logger
from chatbots import ChatBotClientBase

load_dotenv()
WAIT_BEFORE_REFRESH = os.getenv("WAIT_BEFORE_REFRESH",3)
WAIT_BEFORE_REFRESH = float(WAIT_BEFORE_REFRESH)

T = TypeVar("T")
T_Sqlmodel = TypeVar("T", bound=SQLModel)
T_ChatBotClient = TypeVar("T_ChatBotClient", bound=ChatBotClientBase)


class DB_Client:
    def __init__(
            self,
            url: Union[str, URL]="sqlite+aiosqlite:///store.db",
            debug=True):
        self.adb_engine = create_async_engine(url, echo=debug)
        self.migrated = False


    async def migrate(self):
        "you need to run this function before doing any db operation"
        async with self.adb_engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        self.migrated=True


    def detect_migrated(self):
        if not self.migrated:
            raise AttributeError("detect models haven't been migrated. You must execute `self.migrate` before doing any db operation")


    async def create(self, base_obj: Type[T_Sqlmodel], table_class: Type[T_Sqlmodel]) -> T_Sqlmodel:
        """
        Create a new record in the database.

        Args:
            base_obj(T_Sqlmodel): object of base model, table model inherits from the base model.
            table_class(T_Sqlmodel): class of table model.

        Returns:
            out(T_Sqlmodel): The created and refreshed instance.
        """
        self.detect_migrated()
        table_obj = table_class.model_validate(base_obj)
        async with AsyncSession(self.adb_engine) as asess:
            asess.add(table_obj)
            await asess.commit()
            await asess.refresh(table_obj)
            return table_obj
    
    async def get(
        self, table_class: Type[T_Sqlmodel], **kwargs)-> AsyncGenerator[T_Sqlmodel, None]:
        """
        Retrieve record(s) from the database.

        Args:
            table_class(T_Sqlmodel): class of table model.
            kwargs(dict): dict contains conditions to retrieve.
        
        Yields:
            out()
        """
        self.detect_migrated()
        statement = select(table_class)
        async with AsyncSession(self.adb_engine) as asess:
            for key, value in kwargs.items():
                statement = statement.where(getattr(table_class, key) == value)

        result_stream = await asess.stream_scalars(statement)
        async for result in result_stream:
            yield result


async def async_wrapper(callable:Callable[..., T],*args,**kwargs) -> T:
    result = await asyncio.to_thread(callable, *args, **kwargs)
    return result


def b64decode(string:str):
    string = string.removeprefix("data:")
    mime_type, file_bytes = string.split(";base64,",1)
    decoded = base64.b64decode(file_bytes)
    return decoded, mime_type


def send_stable(chatbot_client: T_ChatBotClient, send_function:Callable[...,T],**kwargs):
    retries=3
    while retries!=0:
        send_function(**kwargs)
        time.sleep(WAIT_BEFORE_REFRESH) #NOTE necessary for waiting message sent out.
        logger.debug("通过获取会话最后一条信息，检测是否发送成功（存在网络不稳定发送失败的情况）")
        last_msg = chatbot_client.get_session_history_msgs(only_last_msg=True)[0]
        if last_msg.read_already==None:
            #NOTE read_already==None: still sending, wait
            logger.info("【消息发送中】轮询等待消息发送完成")
        while last_msg.read_already==None:
            last_msg = chatbot_client.get_session_history_msgs(only_last_msg=True)[0]
            if last_msg.send_failure:
                #NOTE send_failure==True: network problem, needs retry
                logger.info(f"【消息发送失败】重新发送。剩余发送次数{retries-1}")
                retries-=1
                break

        if last_msg.send_failure==False:
            logger.info("【消息发送成功】")
            retries=0