# server cannot request computer deployed 移动办公, but can reversely connect.
# Hence we need to keep asking server to fetch messages
from typing import *
import asyncio
import shortuuid
import time
import tempfile
from pathlib import Path
from aiofiles import open as aopen
import base64
import traceback
import aiohttp

from schemas import SendMessage
from chatbots import CmccChatClient
from logg import logger

chatbot_client = CmccChatClient(cache_session_map=False)
message_queue = asyncio.Queue()
message_semaphore = asyncio.Semaphore(1) # UI操作是不可抢占的
consumer_tasks:List[asyncio.Task] = []
temp_dir=tempfile.TemporaryDirectory(prefix="中移移动办公UI机器人",delete=False)

def b64decode(string:str):
    string = string.removeprefix("data:")
    mime_type, file_bytes = string.split(";base64,",1)
    decoded = base64.b64decode(file_bytes)
    return decoded, mime_type

async def async_wrapper(callable:Callable,*args,**kwargs):
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
                    filename = message.Filename or shortuuid.uuid()
                    b64decoded_bytes,mime_type = b64decode(message.File)
                    temp_filepath=Path(temp_dir.name).joinpath(filename)
                    async with aopen(str(temp_filepath),"wb") as f:
                        await f.write(b64decoded_bytes)
                    temp_send_result=await async_wrapper(
                                                chatbot_client.send_file,
                                                session_name=message.FromWxid,
                                                filepath=temp_filepath.absolute()
                                            )
            except Exception as exc:
                await async_wrapper(logger.error, f"[ERROR EXECUTING SENDING MSG] {exc}")
                await async_wrapper(logger.error, traceback.format_exc())
            finally:
                #XXX delete temp file
                #XXX necessary to sleep a bit(0.5s checked in concurrent mode)
                await asyncio.sleep(0.5)
                #XXX mark task done
                message_queue.task_done()

async def main_oa_server(business:str):
    """
    4a-warning main function. Keep asking && receiving messages from server
    """
    global message_queue
    task=asyncio.create_task(execute_send_message())
    async with aiohttp.ClientSession(base_url="http://10.248.230.35:12030/",timeout=aiohttp.ClientTimeout(10.0)) as session:
        while True:
            if message_queue.empty():
                async with session.post(url="get-messages",json={"business":business},) as resp:
                    msg = await resp.json()
                    if "msg" in msg.keys():
                        await async_wrapper(logger.info, msg['msg'])
                        await async_wrapper(logger.info, "消息发送完毕。退出程序")
                        break
                    msg=SendMessage(**msg)
                    await async_wrapper(
                        logger.info,
                        f"message received:\nsend to {msg.FromWxid}\nbrief content :{msg.Content[:50]}"
                    )
                    await message_queue.put(msg)
            else:
                await asyncio.sleep(0.1)  # 避免空转
    await task


if __name__ == '__main__':
    import traceback
    # import argparse
    # parser=argparse.ArgumentParser()
    # parser.add_argument(
    #     "--business",
    #     type=str,
    #     choices=["信控停机预警","低质专线预警","代付欠费超逾期缴费预警"],
    #     required=True,
    #     help="选择要执行的业务类型"
    # )
    # args = parser.parse_args()
    # asyncio.run(main_oa_server(args.business))
    try:
        business = input("请输入您想处理的业务（可选：['信控停机预警','低质专线预警','代付欠费超逾期缴费预警']）：")
        asyncio.run(main_oa_server(business))
    except Exception as e:
        print(f"程序出错: {e}")
        traceback.print_exc()
    else:
        print("程序执行完毕！")
    finally:
        time.sleep(1.0)
        input("按Enter键退出...")

