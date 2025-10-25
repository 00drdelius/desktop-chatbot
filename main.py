# functions conclusion:
# initialize plugins, passively receive messages from GROUPS_MONITOR
# to execute all plugins

import os
import threading
import time
import traceback
from typing import *

from dotenv import load_dotenv

from chatbots.cmcc import CmccChatClient
from plugins import PluginBase, PLUGIN_OBJECTS
from schedulers import blocking_queue
from schemas import SendMessage
from logg import logger


load_dotenv()
chatbot_client = CmccChatClient(wait_before_refresh=os.getenv("WAIT_BEFORE_REFRESH", 2))
PLUGIN_INSTANCES:List[PluginBase]=[]


def initialize_plugins():
    global PLUGIN_INSTANCES
    logger.info(f"开始初始化插件，共 {len(PLUGIN_OBJECTS)} 个插件")
    
    for plugin_obj in PLUGIN_OBJECTS:
        try:
            logger.info(f"初始化插件: {str(plugin_obj)}")
            plugin_inst = plugin_obj(chatbot_client)
            PLUGIN_INSTANCES.append(plugin_inst)
            logger.info(f"Successfully import plugin: {str(plugin_obj)}")
            logger.info(f"插件初始化成功: {str(plugin_obj)}")
        except Exception as e:
            logger.error(f"Failed to initialize plugin {str(plugin_obj)}: {e}")
            logger.error(e, f"插件初始化失败: {str(plugin_obj)}")
    
    logger.info(f"插件初始化完成，成功加载 {len(PLUGIN_INSTANCES)} 个插件")

initialize_plugins()

ROBOT_PREFIX=os.getenv("ROBOT_PREFIX", None)
### config wechat groups should be monitored ###
GROUPS_MONITOR=os.getenv("GROUPS_MONITOR", "").split(",")
# `messages_store` stores last message in every group
# to check if it's history message
# For Example:
# {"Group1":MessageModel,"Group2":MessageModel}
messages_store:dict[str,str]=dict(
    zip(GROUPS_MONITOR,[None for _ in GROUPS_MONITOR])
)
### config wechat groups should be monitored ###


def schedule():
    try:
        while True:
            for inst_item in PLUGIN_INSTANCES:
                inst_item.schedule_tasks()
    except BaseException as exc:
        string=traceback.format_exc()
        logger.error(string)
        quit()

def receive():
    for group in GROUPS_MONITOR:
        time.sleep(0.5)
        chat_interface,session_hist_msgs=chatbot_client.switch_session_and_get_history_msgs(group,only_last_msg=True)
        last_msg = messages_store[group]

        last_sender = session_hist_msgs[0].member_name
        last_message = session_hist_msgs[0].message
        # logger.debug({"last_sender":last_sender,"last_message":last_message})
        if not last_msg:
            message = SendMessage(
                Content=last_message,
                FromWxid=group,
                SenderWxid=last_sender
            )
        elif isinstance(last_msg,SendMessage):
            # stores history message, check if it's new msg
            if last_sender==last_msg.SenderWxid and last_message==last_msg.Content:
                "when sender && content are identical to the last, we should think it's an old msg."
                #TODO: we can check by the red small circle pop up on the session list instead
                continue
            else:
                message = SendMessage(
                    Content=last_message,
                    FromWxid=group,
                    SenderWxid=last_sender
                )
        for inst_item in PLUGIN_INSTANCES:
            # execute function to process message received in plugins
            inst_item.handle_text(message.model_dump(mode="python"))
        messages_store[group]=message


def main():
    business_name = "插件系统主程序"
    
    try:
        logger.info("启动调度线程")
        schedule_thread = threading.Thread(
            target=schedule,
            name="scheduled thread",
            daemon=True
        )
        schedule_thread.start()
        logger.info("调度线程启动成功")
        
        logger.info("开始主循环，监听消息和执行调度任务")
        message_count = 0
        
        while True:
            if blocking_queue.empty():
                # logger.debug(f"scheduler all jobs: {str(background_scheduler.get_jobs())}",)
                receive()
            else:
                logger.info("执行调度任务")
                scheduled_func=blocking_queue.get(block=True)
                scheduled_func()
                logger.info("调度任务执行完成")
            time.sleep(1)
                
    except KeyboardInterrupt as exc:
        logger.info("KeyboardInterrupt detected. Quit")
        logger.info("用户手动停止程序", business_name)
        quit()
    except BaseException as exc:
        string=traceback.format_exc()
        logger.error(string)
        logger.error(exc, "主程序运行异常", business_name)
        quit()

if __name__ == '__main__':
    main()
