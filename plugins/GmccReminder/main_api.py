import asyncio
import yaml

from random import choice
from datetime import datetime
from pytz import timezone
from functools import partial
from pathlib import Path
from loguru import logger

from WechatAPI import WechatAPIClient
from utils.decorators import add_job_safe, scheduler, on_text_message, schedule
from utils.plugin_base import PluginBase

from .database_client import DataBaseClient
from .utils import (
    TIME_STRFMAP,
    async_wrapper,
    flatten_dict,
    _parse_field,_parse_datetime,_parse_people
)
from .model import TaskItem, TaskRequirement, TaskSource, TaskDynamic

config_fpath=Path(__file__).parent.joinpath("config.yaml")
with config_fpath.open('rb') as rf:
    config:dict = yaml.safe_load(rf)
ENABLE = config["enable"]
SCAN_INTERVAL = config['scan_interval']
TZ = config['time_zone']
MANAGER_GROUPID=config['manager_groupid']
EXECUTOR_GROUPID=config['executor_groupid']
CONFIG_TASK_CMD=config['config_task']
FULFILL_TASK_CMD=config['fulfill_task']
ASSISTANT_NAME=config['assistant_name']

#TODO: 截止时间每个周期都不一样，需要固定一种规范。现在先开放出每日的
class Reminder(PluginBase):
    description = "移动任务提醒助手"
    author = "Delius,JiangshanXie"
    version = "0.0.1.dev"

    def __init__(self):
        super().__init__()
        self.enabled = ENABLE
        db_config = config['db_config']
        db_client = partial(
            DataBaseClient,
            host=db_config['host'],
            user=db_config['user'],
            password=db_config['password'],
            dbname=db_config['dbname'],
            row_factory=db_config['row_factory']
        )
        self.source_db_client = db_client(
            tablename="wechat_reminder_source",
        )
        self.dynamic_db_client = db_client(
            tablename="wechat_reminder_dynamic",
        )

        self.acceptable_months=[i for i in range(1,13)]
        self.acceptable_days=[i for i in range(1, 29)]
        self.acceptable_weekdays=[i for i in range(7)]
        self.acceptable_hours=[9,10,11,12,15,16,17,18,19]
        self.acceptable_minutes=[i for i in range(1,61)]
        self.acceptable_seconds=[i for i in range(1,61)]
        self.crontab_list=list()
        # logger.debug(f"[REMINDER INITIALIZED]")

    # @on_text_message(priority=1)
    # async def temp(self, bot:WechatAPIClient, message:dict):
    #     "测试成功"
    #     logger.debug("[REMINDER DEBUG]"+"#"*50)
    #     logger.debug(str(message))
    #     logger.debug("[REMINDER DEBUG]"+"#"*50)

    #     content = str(message["Content"]).strip()
    #     if "Delius test" in content:
    #         logger.debug("[CMD RECEIVED]")
    #         row = list(
    #             await async_wrapper(self.source_db_client.query_fields,["*"],{'index':"1"})
    #         )[0]
    #         row_str=f"[DATA FETCHED]\n{row}"
    #         logger.debug(row_str)
    #         await bot.send_at_message(wxid=EXECUTOR_GROUPID,content=str(row_str),at=["wxid_qngq1vzd8tlc21"],)

    # @schedule("date",run_date="2025-05-08 11:56:50")
    # async def temp2(self, bot:WechatAPIClient):
    #     "测试成功"
    #     await bot.send_at_message(wxid=EXECUTOR_GROUPID,content="crontab successfully returned",at=["wxid_qngq1vzd8tlc21"])


    @on_text_message(priority=1)
    async def handle_text(self, bot:WechatAPIClient, message:dict):
        """
        统一处理的被动回复接口。用于：
        - 根据定时任务管理者群的@消息配置定时任务
        - 根据执行者群回复的“具体任务索引”及“已完成”添加完成消息至数据库
        """
        content = str(message["Content"]).strip()
        if not content.startswith("@"+ASSISTANT_NAME):
            return
        else:
            logger.debug(f"[REMINDER][MSG RECEIVED] {content}")
        if CONFIG_TASK_CMD in content:
            await self.configure_tasks(bot, message)
        elif FULFILL_TASK_CMD in content:
            await self.receive_done(bot, message)
        else:
            # 机器人状态检查
            await bot.send_at_message(message['FromWxid'],"您好，我在🤗",at=[message['SenderWxid']])
            return

    async def configure_tasks(self, bot:WechatAPIClient, message:dict):
        """
        根据定时任务管理者群的@消息配置定时任务。

        配置消息样例：全角中括号、逗号，不同项内容通过\n换行符间隔
        @$ASSISTANT_NAME\u2005
        【事项名称】月度销账报表提交  
        【事项描述】每月提交月度销账报表进行审批  
        【任务调度人】张三
        【任务执行人】李四，王五，赵六  
        【任务周期】每月  
        【截止时间】2025年06月01日18时00分  
        【提前提醒次数】2

        功能流程：
        1. 解析消息内容获取任务内容
        2. 在源表`TaskSource`和动态表`TaskDynamic`创建并储存对应任务
        3. 返回TaskItem信息到管理者群与执行者群
        """

        # 接收微信群消息，insert到postgres正本表与副本表，反馈成功（TaskItem信息）/失败信号
        try:
            # 解析消息内容获取任务内容
            content = message["Content"]
            task_data = {
                "item": {
                    "name": _parse_field(content, "事项名称"),
                    "description": _parse_field(content, "事项描述")
                },
                "schedulers": _parse_people(content, "任务调度人"),
                "executors": _parse_people(content, "任务执行人"),
                "requirement": {
                    "cycle": _parse_field(content, "任务周期"),
                    "deadline": _parse_datetime(content, "截止时间"),
                    "repeat_count": int(_parse_field(content, "提前提醒次数"))
                }
            }

            # 创建并存储任务
            task = TaskSource(**task_data)
            source_data = flatten_dict(task.model_dump())

            # 存储到源表
            await async_wrapper(
                self.source_db_client.insert_item,
                source_data
            )

            # 存储到动态表（添加executors_left字段）
            source_data.pop("executors")
            dynamic_data = {
                **source_data,
                "executors_left": task.executors.copy()
            }
            await async_wrapper(
                self.dynamic_db_client.insert_item,
                dynamic_data
            )

            # 返回消息至管理者群
            await bot.send_text_message(
                message["FromWxid"], # 向配置群（消息来源群）发送消息
                (
                    f"任务配置成功！\n"
                    f"【任务名称】{task.item.name}\n"
                    f"【任务描述】{task.item.description}\n"
                    f"【任务索引号】{task.item.index}\n"
                    f"【截止日期】{task.requirement.deadline.strftime(TIME_STRFMAP[task.requirement.cycle])}"
                ),
                message["SenderWxid"] # at消息配置人
            )

            # 返回消息至执行者群
            # TODO: 修改发送至执行者群所需的信息
            await bot.send_text_message(
                message["FromWxid"], # TODO: 修改向执行群发送消息
                (
                    f"已配置新的任务：\n"
                    f"【事项名称】{task.item.name}\n"
                    f"【事项描述】{task.item.description}\n"
                    f"【事项索引】{task.item.index}\n"
                    f"【截止时间】{task.requirement.deadline.strftime(TIME_STRFMAP[task.requirement.cycle])}"
                ),
                message["SenderWxid"] # TODO: 修改at消息执行人
            )

        # 返回错误至管理者群
        except Exception as e:
            await bot.send_text_message(message['FromWxid'], f"配置失败: {str(e)}")


    async def receive_done(self, bot:WechatAPIClient, message:dict):
        """
        根据执行者群回复的“具体任务索引”及“已完成”添加完成消息至数据库

        配置消息样例：全角中括号、逗号，不同项内容通过\n换行符间隔
        
        @$ASSISTANT_NAME\u2005
        【完成人】哈吉米
        【事项索引】XZTX-20250507114813-SP0I

        功能流程：
        1. 解析消息内容获取任务索引和执行人
        2. 在`TaskDynamic`对应数据表查询动态任务记录
        3. 验证执行人是否在字段`executors_left`待完成名单中
        4. 更新数据库移除已完成执行人
        5. 发送操作结果反馈
        
        数据库操作使用database_client提供的以下方法：
        - update_item_by_conditions: 根据条件更新记录
        - query_fields: 根据索引号查询信息
        """
        try:
            content = message["Content"]
            sender = message["SenderWxid"]
            
            # 1. 解析消息内容获取任务索引和执行人
            try:
                task_index = _parse_field(content, "事项索引")
                executor_name = _parse_field(content, "完成人")
            except ValueError as e:
                await bot.send_text_message(
                    message['FromWxid'],
                    f"消息格式错误，请确保包含：【完成人】和【事项索引】字段\n错误详情: {str(e)}",
                    sender
                )
                return

            # 2. 在`TaskDynamic`对应数据表查询动态任务记录
            try:
                records = list(await async_wrapper(
                    self.dynamic_db_client.query_fields,
                        ["*"],  # 查询全部字段
                        {"index": task_index},  # 按任务索引筛选
                    )
                )
                
                if not records:
                    await bot.send_text_message(
                        message['FromWxid'],
                        (
                            f"⚠️ 未找到索引为 {task_index} 的任务\n"
                            f"请检查：\n1.索引是否正确\n2.任务是否已过期删除"
                        ),
                        sender
                    )
                    return
                    
                record = records[0]
                
            except Exception as e:
                await bot.send_text_message(
                    message['FromWxid'],
                    (
                        f"⚠️ 数据库查询失败: {str(e)}\n"
                        f"请稍后重试或联系管理员"
                    ),
                    sender
                )
                return

            # 3. 验验证执行人是否在字段`executors_left`待完成名单中
            # TODO: 通过错误抛出的形式验证执行人
            executors_left = record.get("executors_left", [])
            if not executors_left:  # 所有执行人已完成
                await bot.send_text_message(
                    message['FromWxid'],
                    f"该任务所有执行人已完成，无需重复记录",
                    sender
                )
                return
                
            if executor_name not in executors_left: # 执行人不在列表
                await bot.send_text_message(
                    message['FromWxid'],
                    (
                        f"您未在该任务执行人列表中\n"
                        f"当前待完成人员: {', '.join(executors_left)}"
                    ),
                    sender
                )
                return

            # 4. 更新数据库并反馈
            try:
                # 更新执行人列表
                await async_wrapper(
                    self.dynamic_db_client.update_item_by_conditions,
                    items={
                        "executors_left": [e for e in executors_left if e != executor_name], # 移除发送者（执行人已完成）
                        # "update_time": datetime.now(timezone("Asia/Shanghai"))  # 添加更新时间戳（数据表表没这字段）
                    },
                    condition_items={
                        "index": task_index
                    }
                )

                # 验证更新结果
                updated_records = list(await async_wrapper(
                    self.dynamic_db_client.query_fields,
                    expected_fields=["executors_left"],
                    condition_items={"index": task_index},
                    limit=1
                ))

                if not updated_records or sender in updated_records[0].get("executors_left", []):
                    raise Exception("数据库更新未生效，可能已被其他操作修改")

                # 构建反馈信息
                remaining = updated_records[0].get("executors_left", [])
                # last_update = updated_records[0].get("update_time").astimezone(timezone("Asia/Shanghai"))
                
                feedback = (
                    f"完成信息更新成功\n"
                    f"【任务索引】{task_index}\n"
                    f"【完成人】{executor_name}\n"
                    f"【剩余执行者】{'，'.join(remaining) if remaining else '所有执行人已完成！'}"
                )
                
                await bot.send_text_message(
                    message['FromWxid'],
                    feedback,
                    sender  # @操作人
                )

            except Exception as e:
                error_msg = (
                    f"更新失败\n"
                    f"错误类型: {type(e).__name__}\n"
                    f"详情: {str(e)}\n"
                    f"请检查后重试或联系管理员"
                )
                await bot.send_text_message(message['FromWxid'], error_msg)
                return
                
        except Exception as e:
            error_msg = (
                f"系统错误: {str(e)}\n"
                f"请截图并联系管理员\n"
                f"错误类型: {type(e).__name__}"
            )
            await bot.send_text_message(message['FromWxid'], error_msg)
            raise  # 保留原始异常供上层捕获


    async def delete_task(self, bot:WechatAPIClient, message:dict):
        """
        删除任务

        - 需要删除 dynamic 表中的，以及根据 job_id 删除 scheduler 中的
        """
        #TODO: 暂时不搞
        ...

    @schedule("interval",seconds=SCAN_INTERVAL)
    async def schedule_tasks(self, bot:WechatAPIClient):
        """
        配置定时任务至`ASPScheduler`的统一接口

        每 `scan_interval`s 检测一次数据库，添加、删除定时任务
        """
        for row in await async_wrapper(
            self.dynamic_db_client.query_fields,
            expected_fields=["*"],
            condition_items={}
        ):
            if row['is_scheduled']==True:
                logger.debug(f"index:{row['index']} is scheduled. skip")
                continue
            logger.debug(f"scheduling task index:{row['index']}")
            # 设置已添加 scheduler
            await async_wrapper(
                self.dynamic_db_client.update_item_by_conditions,
                items={"is_scheduled":True},
                condition_items={"index": row['index']}
            )
            current_datetime = datetime.now(timezone(TZ))
            taskDynamic = TaskDynamic(
                item=TaskItem(
                    name=row['name'],
                    description=row['description'],
                    index=row['index']
                ),
                requirement=TaskRequirement(
                    cycle=row['cycle'],
                    deadline=row['deadline'].astimezone(timezone(TZ)),
                    repeat_count=row['repeat_count']
                ),
                schedulers=row['schedulers'],
                executors_left=row['executors_left']
            )

            # 添加提醒，一次性添加完。`executors_left`会在发送消息前动态查找，这里不用关心
            partial_add_job = partial(
                add_job_safe,
                scheduler=scheduler,
                func=self.schedule_task,
                bot=bot,
                trigger="cron",
                func_kwargs={"index":taskDynamic.item.index}, # passed to func
                timezone=timezone("Asia/Shanghai") # trigger_args
            )
            # 只需要添加可接受的小时，其他的都可随机。只要在该 deadline.hour 前，每次提醒都不会延迟
            #TODO: 暂时先这样设置
            acceptable_hours = [
                i for i in self.acceptable_hours
                if i < taskDynamic.requirement.deadline.hour
            ]

            # 用于存放已经提醒的时间，随机选择时使用
            # TODO
            times_added=[]

            #TODO: self._scheduled_jobs.add(job_id) 暂未添加
            match taskDynamic.requirement.cycle:
                case "每日":
                    for i in range(1,taskDynamic.requirement.repeat_count+1):
                        partial_add_job(
                            job_id=str(taskDynamic.item.index)+f"_{i}",
                            hour=self.acceptable_hours[i-1],
                            minute=choice(self.acceptable_minutes),
                            second=choice(self.acceptable_seconds),
                        )
                    # deadline 时还需要添加一次提醒任务
                    partial_add_job(
                        job_id=str(taskDynamic.item.index)+f"_{i+1}",
                        hour=taskDynamic.requirement.deadline.hour,
                        minute=taskDynamic.requirement.deadline.minute,
                    )
                    # deadline 时需要重置 dynamic 表， deadline.hour+1 时重置
                    add_job_safe(
                        scheduler,
                        job_id=taskDynamic.item.index+"_reset",
                        func=self.reset_task,
                        bot=bot,
                        func_kwargs={"index":taskDynamic.item.index}, # passed to func
                        trigger="cron",
                        hour=sorted(acceptable_hours)[-1]+1,
                        minute=choice(self.acceptable_minutes),
                        second=choice(self.acceptable_seconds),
                    )
                case "每周":
                    for i in range(1,taskDynamic.requirement.repeat_count+1):
                        partial_add_job(
                            job_id=str(taskDynamic.item.index)+f"_{i}",
                            day_of_week=choice(self.acceptable_weekdays),
                            hour=acceptable_hours[i-1],
                            minute=choice(self.acceptable_minutes),
                            second=choice(self.acceptable_seconds),
                        )
                    # deadline 时还需要添加一次提醒任务
                    partial_add_job(
                        job_id=str(taskDynamic.item.index)+f"_{i+1}",
                        day_of_week=taskDynamic.requirement.deadline.weekday(),
                        hour=taskDynamic.requirement.deadline.hour,
                        minute=taskDynamic.requirement.deadline.minute
                    )
                    # deadline 时需要重置 dynamic 表， deadline.hour+1 时重置
                    add_job_safe(
                        scheduler,
                        job_id=taskDynamic.item.index+"_reset",
                        func=self.reset_task,
                        bot=bot,
                        func_kwargs={"index":taskDynamic.item.index}, # passed to func
                        trigger="cron",
                        day_of_week=taskDynamic.requirement.deadline.weekday(),
                        hour=sorted(acceptable_hours)[-1]+1,
                        minute=choice(self.acceptable_minutes),
                        second=choice(self.acceptable_seconds),
                    )
                case "每月":
                    for i in range(1,taskDynamic.requirement.repeat_count+1):
                        partial_add_job(
                            job_id=str(taskDynamic.item.index)+f"_{i}",
                            day=choice(self.acceptable_days),
                            hour=acceptable_hours[i-1],
                            minute=choice(self.acceptable_minutes),
                            second=choice(self.acceptable_seconds),
                        )
                    # deadline 时还需要添加一次提醒任务
                    partial_add_job(
                        job_id=str(taskDynamic.item.index)+f"_{i+1}",
                        day=taskDynamic.requirement.deadline.day,
                        hour=taskDynamic.requirement.deadline.hour,
                        minute=taskDynamic.requirement.deadline.minute
                    )
                    # deadline 时需要重置 dynamic 表， deadline.hour+1 时重置
                    add_job_safe(
                        scheduler,
                        job_id=taskDynamic.item.index+"_reset",
                        func=self.reset_task,
                        bot=bot,
                        func_kwargs={"index":taskDynamic.item.index}, # passed to func
                        trigger="cron",
                        day=taskDynamic.requirement.deadline.day,
                        hour=sorted(acceptable_hours)[-1]+1,
                        minute=choice(self.acceptable_minutes),
                        second=choice(self.acceptable_seconds),
                    )
                case _: #TODO: 每季和每年暂时不弄
                    raise AttributeError(f"cycle not supported: {taskDynamic.requirement.cycle}")


    async def schedule_task(self, bot:WechatAPIClient, **kwargs):
        """
        单个定时事项的执行函数
        - 只负责：根据`index`实时查询 dynamic 表并发送消息
        """
        index = kwargs['index']
        row = list(
            await async_wrapper(self.dynamic_db_client.query_fields,["*"],{'index':index})
        )[0]
        taskDynamic = TaskDynamic(
            item=TaskItem(
                name=row['name'],
                description=row['description'],
                index=row['index']
            ),
            requirement=TaskRequirement(
                cycle=row['cycle'],
                deadline=row['deadline'].astimezone(timezone(TZ)),
                repeat_count=row['repeat_count']
            ),
            schedulers=row['schedulers'],
            executors_left=row['executors_left']
        )

        str_content=(
            f"【事项名称】{taskDynamic.item.name}\n"
            f"【事项索引】{taskDynamic.item.index}\n"
            f"【事项描述】{taskDynamic.item.description}\n"
            f"【任务调度人】{'，'.join(taskDynamic.schedulers)}\n"
            f"【截止时间】{taskDynamic.requirement.deadline.strftime(TIME_STRFMAP[taskDynamic.requirement.cycle])}\n"
            f"【未完成执行人】{'，'.join(taskDynamic.executors_left)}\n"
            "请尽快完成。"
            "若已完成，请回复：\n"
            f"@{ASSISTANT_NAME} 任务完成"
            "【完成人】你的完成名\n"
            "【事项索引】事项索引\n"
        )
        await bot.send_text_message(EXECUTOR_GROUPID, str_content, taskDynamic.executors_left)


    async def reset_task(self,bot:WechatAPIClient,**kwargs):
        """
        重置动态更新的任务

        - 周期地重置对应`dynamic`表
        """
        index = kwargs['index']
        row = list(
            await async_wrapper(self.source_db_client.query_fields,["*"],{'index':index})
        )[0]
        source_executors:list = row['executors']

        await async_wrapper(
            self.dynamic_db_client.update_item_by_conditions,
            items={
                "executors_left": source_executors,
                "is_scheduled": False
            },
            condition_items={'index':index}
        )
        reset_feedback=(
            "事项已重置\n"
            f"【事项索引】{index}"
        )
        await bot.send_text_message(MANAGER_GROUPID, reset_feedback)


# Test
if __name__ == "__main__":
    # 测试配置
    test_content = """
    【事项名称】测试任务
    【事项描述】验证消息解析功能
    【任务调度人】管理员
    【任务执行人】开发A，测试B
    【任务周期】每月
    【截止时间】2025-12-31 18:00
    【提前提醒次数】3
    """

    # 模拟消息输入
    test_message = {"Content": test_content, "FromWxid": "test_wxid"}

    # 重写方法跳过数据库操作
    original_insert = Reminder.source_db_client
    Reminder.source_db_client = lambda self: type('', (), {'insert_item': lambda x: None})
    Reminder.dynamic_db_client = lambda self: type('', (), {'insert_item': lambda x: None})

    # 捕获输出
    class ResultCatcher:
        def __init__(self):
            self.result = None
        async def send_text_message(self, _, text):
            self.result = text

    # 执行测试
    async def run_test():
        catcher = ResultCatcher()
        reminder = Reminder()
        await reminder.configure_tasks(catcher, test_message)
        
        # 验证输出
        assert "任务配置成功" in catcher.result
        assert "测试任务" in catcher.result
        assert "开发A" in catcher.result
        print("✅ 测试通过！")
        print(catcher.result)

    import asyncio
    asyncio.run(run_test())

    # 恢复原始方法（可选）
    Reminder.source_db_client = original_insert
