from datetime import datetime
from pydantic import BaseModel
from typing import List, Literal, Optional
import pypinyin
import shortuuid

def generate_index(name: str) -> str:
    """通过任务名拼音首字母+8位短UUID生成任务索引号
    
    Args:
        name: 任务名称，用于生成拼音首字母
        
    Returns:
        格式为 "首字母-短UUID" 的唯一索引号
        示例: "XZTX-5Hg8Lk2P"
    """
    # 获取拼音首字母并大写
    initials = ''.join([w[0][0].upper() for w in pypinyin.pinyin(name, style=pypinyin.NORMAL)])
    # 生成8位短UUID
    unique_id = shortuuid.ShortUUID().random(length=8)
    
    return f"{initials}-{unique_id}"

class TaskItem(BaseModel):
    """任务事项的信息，包含事项名称、事项描述、事项标识码"""

    name: str
    "【事项名称】"
    description: str
    "【事项描述】"

    index: Optional[str] = None  
    "【事项索引】 ，自动生成"

    def ensure_index(self):
        "生成事项索引"
        if not self.index:
            self.index = generate_index(self.name)

class TaskRequirement(BaseModel):
    """任务时间的配置，包含配置周期、截止时间、提前提醒次数"""

    cycle: Literal['每月', '每季', '每日', '每周', '每年']
    "【任务周期】"
    deadline: datetime
    "【截止时间】"
    repeat_count: int
    "【提前提醒次数】"

class TaskSource(BaseModel):
    """
    完整的任务配置模型，作为源配置只能通过配置群进行更改。
    包含事项信息、任务调度人（负责人）、任务执行人（客户经理）、任务时间配置。
    """

    item: TaskItem
    requirement: TaskRequirement

    schedulers: list[str]
    "【任务调度人】"
    executors: list[str]
    "【任务执行人】"

    def model_post_init(self,__context):
        """初始化生成任务索引号，同一任务下Source与Copy索引应相同，分别通过配置群、发布群进行查询更改"""
        # super().__init__(**kwargs)
        self.item.ensure_index()

class TaskDynamic(BaseModel):
    """
    作为源任务的副本，用于实际任务发送和追踪的模型。
    1. 需根据周期刷新
    2. `executors_left`需要动态删减
    3. 其余结构同`TaskSource`
    """

    item: TaskItem
    requirement: TaskRequirement

    schedulers: list[str]
    "【任务调度人】"
    executors_left: list[str]
    "【任务执行人】"

    is_scheduled: bool = False

    def remove_executor(self, name: str):
        """
        移除指定的执行人
        Args:
            name(str): 需要移除的执行人姓名
        """
        if name in self.executors_left:
            self.executors_left.remove(name)

# Test
if __name__ == "__main__":

    # 示例数据
    example_data = {
        "item": {
            "name": "销账提醒",
            "description": "每月对销账进行提醒",
        },
        "schedulers": {"张三"},
        "executors": {"李四", "王五"},
        "requirement": {
            "cycle": "每月",
            "deadline": "2025-05-31 18:00",
            "repeat_count": 3
        }
    }

    # 临时查询测试，模拟任务存储字典
    task_db = {}

    def get_task_by_index(index: str) -> Optional[TaskSource]:
        return task_db.get(index)


    config = TaskSource(**example_data)
    task_db[config.item.index] = config

    print("任务索引：", config.item.index)

    active_task = TaskDynamic(**example_data)

    active_task.remove_executor("李四")
    print(active_task.executors_left) 

    active_task.remove_executor("王五")
    print("执行人移除后:", active_task.executors_left) 

    result = get_task_by_index(config.item.index)
    print("查询结果：", result)

    result = get_task_by_index("XZTX-20250507114813-SP0I")
    print("查询结果：", result)