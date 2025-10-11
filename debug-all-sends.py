import sys
from pathlib import Path
import time
from chatbots.cmcc import CmccChatClient
from logg import logger
import os # 导入os模块用于路径操作

input("请按任意键继续")
logger.info("[UI机器人程序测试]")
logger.info("[UI机器人初始化]")
client = CmccChatClient(cache_session_map=False,wait_before_refresh=4.0)
logger.info("[UI机器人初始化完成]")
logger.info("[测试消息发送两次]")
client.send_message(session_name="我的文件助手",message="消息发送测试",from_clipboard=True,at_list=[])
client.send_message(session_name="我的文件助手",message="消息发送测试x2",from_clipboard=True,at_list=[])

logger.info("[测试消息发送完毕]")
logger.info("[测试文件发送两次]\n")

try:
    # 修改文件路径为项目根目录下的test文件夹
    test_file_path = Path(__file__).parent.joinpath("test").joinpath("test.txt")
    # 确保test文件夹存在
    os.makedirs(test_file_path.parent, exist_ok=True)
    
    with test_file_path.open('w',encoding='utf8') as f:
        f.write("功能测试：中移移动办公发送文件")
    print(f"使用文件路径：{test_file_path}")
    client.send_file(session_name="我的文件助手",filepath=test_file_path)
    client.send_file(session_name="我的文件助手",filepath=test_file_path)
    time.sleep(1.0)
except Exception as e:
    logger.error(f"发送文件时出错：{str(e)}")
finally:
    logger.info("[测试文件发送完毕]")
    input("请任意键结束")