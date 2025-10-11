import asyncio
import os
import regex as re
from functools import partial
from datetime import datetime
from typing import *
from random import choice

from rich import print

TIME_FMAP={
    "每日": "%H-%M",
    "每周": "%d-%w-%H-%M",
    "每月": "%d-%H-%M",
    "标准": "%Y-%m-%d-%H-%M"
    #TODO
}
TIME_STRFMAP={
    "每日": "每日%H:%M",
    "每周": "每周%w %H:%M",
    "每月": "每月%d日 %H:%M",
    "标准": "%Y-%m-%d-%H-%M"
}

ACCEP_MONTHS=[i for i in range(1,13)]
ACCEP_DAYS=[i for i in range(1, 29)]
ACCEP_WEEKDAYS=[i for i in range(7)]
ACCEP_HOURS=[9,10,11,12,15,16,17,18,19]
ACCEP_MINUTES=[i for i in range(1,61)]
ACCEP_SECONDS=[i for i in range(1,61)]

async def async_wrapper(func:Callable, *args, **kwargs):
    func_call=partial(func, *args, **kwargs)
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, func_call)
    except Exception as exc:
        raise exc 
    return result


def flatten_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    """递归展开嵌套字典，使其变为深度为1的字典"""
    flattened = {}
    for key, value in d.items():
        if isinstance(value, dict):
            flattened.update(flatten_dict(value))
        else:
            flattened[key] = value
    return flattened


def _parse_field(content: str, field: str) -> str:
    """
    从多行文本中提取指定字段的值（字段名和字段内容必须在同一行）
    
    Args:
        content: 多行输入文本，每行格式为【字段名】字段值
        field: 要提取的字段名（不带括号）
    
    Returns:
        字段值的字符串（已去除首尾空格）
        
    Raises:
        ValueError: 当字段不存在时抛出
    """
    FIELD_MARKER = f"【{field}】"  # 全角字段标记
    
    # 逐行检查（跳过空行）
    for line in content.split('\n'):
        stripped_line = line.strip()
        if not stripped_line:
            continue
            
        # 匹配目标字段行
        if stripped_line.startswith(FIELD_MARKER):
            # 提取字段标记后的内容并去除空格
            field_value = stripped_line[len(FIELD_MARKER):].strip()
            return field_value
    
    # 未找到字段时抛出明确异常
    raise ValueError(f"配置消息缺少必要字段: {field}")

def _parse_people(content: str, field: str) -> list[str]:
    """
    解析人员列表字段（格式：姓名1，姓名2）
    
    Args:
        content: 多行输入文本
        field: 人员列表字段名（如"任务执行人"）
    
    Returns:
        去重且去除空值的人员名单列表
    """
    PEOPLE_SEPARATOR = "，"  # 中文逗号分隔符
    
    # 获取原始人员字符串
    people_str = _parse_field(content, field)
    
    # 分割并清理名单
    return [
        name.strip() 
        for name in people_str.split(PEOPLE_SEPARATOR) 
        if name.strip()  # 过滤空姓名
    ]

def _parse_datetime(content: str, field: str) -> datetime:
    """
    解析中文日期时间

    ### Refs:
        时间日期格式化符号参考: https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes
    """
    dt_str = _parse_field(content, field)
    cycle = _parse_field(content, "任务周期")
    time_list = re.findall(r"\d+",dt_str)
    if "周" in cycle:
        # datetime若不给出年月日，会默认初始化为 1900-1-1（周1），会替换设置的星期
        # 因此必须至少手动设置`%d`，表明是 1900-1-%w（周%w）
        # 如：你需要设置周5，可以`strptime("5-5-12-30","%d-%w-%H-%M")`
        time_list=[time_list[0]]+time_list # %d+[%w,%H,%M]

    return datetime.strptime(
        "-".join(time_list),
        TIME_FMAP[cycle]  # 匹配格式
    )

if __name__ == '__main__':
    li=[("每周4下午13时15分","每周"), ("每天下午17时30分","每日"), ("每月25日12点30","每月")]
    for i,c in li:
        time_list = re.findall(r"\d+",i)
        if "周" in c:
            time_list=[time_list[0]]+time_list
            print(time_list)
        t=datetime.strptime("-".join(time_list),TIME_FMAP[c])
        print(t.strftime(TIME_STRFMAP[c]))