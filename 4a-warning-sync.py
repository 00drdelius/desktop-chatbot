# server cannot request computer deployed 移动办公, but can reversely connect.
# Hence we need to keep asking server to fetch messages
from typing import *
import asyncio
import json
from pathlib import Path
import base64
import traceback
import requests
import tempfile
import time

import shortuuid
from aiofiles import open as aopen

from schemas import SendMessage
from chatbots import CmccChatClient
from logg import logger
from exec_logger import exec_logger, log_step, log_success, log_error

#XXX 这里的wait_before_refresh 不能设置的太短，否则会导致移动办公的UI操作失败   
chatbot_client = CmccChatClient(cache_session_map=False,wait_before_refresh=5)
message_queue = asyncio.Queue()
message_semaphore = asyncio.Semaphore(1) # UI操作是不可抢占的
consumer_tasks:List[asyncio.Task] = []
# temp_dir=tempfile.TemporaryDirectory(prefix="中移移动办公UI机器人",delete=False)
# temp_dir=tempfile.TemporaryDirectory(prefix="中移移动办公UI机器人") #XXX delete=False  python 版本 3.10和3.11   是有区别的  需要注意

# 使用mkdtemp替代TemporaryDirectory，确保程序退出后文件不被清理
temp_dir_path = tempfile.mkdtemp(prefix="中移移动办公UI机器人")

# SERVER_API="http://127.0.0.1:12030"
SERVER_API="http://10.248.230.35:12030"

def b64decode(string:str):
    string = string.removeprefix("data:")
    mime_type, file_bytes = string.split(";base64,",1)
    decoded = base64.b64decode(file_bytes)
    return decoded, mime_type

async def async_wrapper(callable:Callable,*args,**kwargs):
    result = await asyncio.to_thread(callable, *args, **kwargs)
    return result

def execute_send_message(message:SendMessage):
    "consumer function"
    # with message_semaphore:
    try:
        log_step(f"开始处理消息 - 接收人: {message.FromWxid}")
        
        # 首先尝试切换到目标会话，如果搜索联系人失败则直接返回
        try:
            log_step(f"切换到目标会话: {message.FromWxid}")
            chatbot_client.switch_session(message.FromWxid)
        except Exception as search_exc:
            logger.error(f"搜索联系人失败，跳过消息推送: {search_exc}")
            log_error(search_exc, f"搜索联系人失败: {message.FromWxid}")
            return False
            
        if message.Content:
            log_step(f"发送文本消息，内容长度: {len(message.Content)}")
            at_list = []
            if message.SenderWxid:
                at_list.append(message.SenderWxid)
            chatbot_client.send_message(
                session_name=message.FromWxid,
                message=message.Content,
                from_clipboard=True,
                at_list=at_list
            )
            log_success(f"文本消息发送成功 - 接收人: {message.FromWxid}")
            
        if message.File:
            log_step(f"处理文件消息，文件名: {message.Filename}")
            filename = message.Filename or shortuuid.uuid()
            b64decoded_bytes,mime_type = b64decode(message.File)
            # 修改为使用我们新创建的临时目录路径
            temp_filepath=Path(temp_dir_path).joinpath(filename)
            with temp_filepath.open('wb') as temp_f:
                temp_f.write(b64decoded_bytes)

            chatbot_client.send_file(
                session_name=message.FromWxid,
                filepath=temp_filepath.absolute()
            )
            log_success(f"文件消息发送成功 - 文件: {filename}, 接收人: {message.FromWxid}")
    except Exception as exc:
        logger.error(f"[ERROR EXECUTING SENDING MSG] {exc}")
        log_error(exc, f"消息发送失败 - 接收人: {message.FromWxid}")
        traceback.print_exc()
        return False
    else:
        log_success(f"消息处理完成 - 接收人: {message.FromWxid}")
        return True

def main_oa_server(business:str):
    """
    4a-warning main function. Keep asking && receiving messages from server
    """
    log_step(f"开始连接服务器获取消息 - 业务类型: {business}")
    
    with requests.post(
        url=f"{SERVER_API}/get-messages",
        json={"business":business},
        stream=True
    ) as resp:
        if resp.status_code!=200:
            logger.info(f"/get-messages 请求报错：{resp.text}")
            log_error(Exception(f"服务器请求失败: {resp.status_code}"), f"获取消息失败: {resp.text}")
            return

        log_success("成功连接到服务器，开始接收消息")
        message_count = 0
        
        for chunk in resp.iter_lines(delimiter="\n\n",decode_unicode=True):
            if not chunk.startswith("data: "):
                continue
            chunk = chunk.removeprefix("data: ")
            if chunk=="[DONE]":
                logger.info("消息发送完毕。退出程序")
                log_success(f"所有消息处理完毕，共处理 {message_count} 条消息")
                return
            
            msg = SendMessage.model_validate_json(chunk)
            message_count += 1
            logger.info(f"收到消息:\n接收人：{msg.FromWxid}\n消息前缀：{msg.Content[:50]}...")
            log_step(f"处理第 {message_count} 条消息 - 接收人: {msg.FromWxid}")
            
            send_result = execute_send_message(msg)
            if not send_result:
                log_error(Exception("消息发送失败"), f"第 {message_count} 条消息发送失败")
                continue

            with requests.post(
                url=f"{SERVER_API}/update-msg-status",
                json={"uid":str(msg.id)}
            ) as update_resp:
                logger.debug(f"[UPDATE RESPONSE]{update_resp.json().get('msg')}")
                log_step(f"更新消息状态完成 - 消息ID: {msg.id}")

def get_businesses_available()->list:
    with requests.get(f"{SERVER_API}/businesses-available") as resp:
        businesses = resp.json().get("data",[])
        return businesses

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
    
    business = None
    try:
        available_services=get_businesses_available()
        business = input(f"请输入您想处理的业务（可选：{available_services}）：")
        
        # 启动程序日志记录
        exec_logger.start_program(business)
        
        with exec_logger.task_context(f"执行{business}业务", business):
            main_oa_server(business)
            
    except Exception as e:
        print(f"程序出错: {e}")
        if business:
            log_error(e, f"程序执行异常 - 业务: {business}", business)
        traceback.print_exc()
    else:
        print("程序执行完毕！")
        if business:
            log_success(f"程序正常结束 - 业务: {business}", business)
    finally:
        time.sleep(1.0)
        # temp_dir.cleanup() #XXX 临时文件不删除
        input("按Enter键退出...")

