from typing import *
from queue import Queue
from functools import partial
from apscheduler.triggers.base import BaseTrigger
from apscheduler.schedulers.base import BaseScheduler


from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from logg import logger

### construct scheduler ###
executors = {
    'default': ThreadPoolExecutor(10),  # 普通任务
    'blocking': ThreadPoolExecutor(1)  # 阻塞任务
}
# more parameters in job_defaults pls refer to scheduler.add_job
job_defaults = {
    'coalesce': False,
    #那些错过的任务在有条件执行时（有线程空闲出来/服务已恢复），
    # 如果还没有超过misfire_grace_time，就会被再次执行。如果misfire_grace_time=None，就是不论任务错过了多长时间，都会再次执行。
    'misfire_grace_time': None
}

background_scheduler=BackgroundScheduler(
    daemon=True,
    executors=executors,
    job_defaults=job_defaults
)
background_scheduler.start()
logger.debug(f"background_scheduler id: {id(background_scheduler)}")
### construct scheduler ###

blocking_queue=Queue() # queue to store blocked tasks waited to be executed


def generate_job_id(job_id,**kwargs):
    day_of_week=kwargs.get('day_of_week','null')
    day=kwargs.get('day','null')
    hour=kwargs.get('hour','null')
    minute=kwargs.get('minute','null')
    second=kwargs.get('second','null')
    job_id=f"[{job_id}]day:{day}-day_of_week:{day_of_week}-hour:{hour}-minute:{minute}-second:{second}"
    return job_id

def add_job_safe(
        scheduler:BaseScheduler,
        func:Callable,
        # bot,
        trigger:Union[BaseTrigger,str],
        func_kwargs:dict,
        **kwargs
):
    """
    job added to tasks queue safely. Will be removed from scheduler once it's executed.
    """
    debug_msg=f"""\
function accepted: {str(func)}
trigger: {str(trigger)}
func_kwargs: {str(func_kwargs)}
kwargs: {str(kwargs)}
"""
    # logger.debug(debug_msg)
    # partial_scheduled_func=partial(func,**func_kwargs)
    job_id = kwargs.pop("job_id",'empty')
    job_id=generate_job_id(job_id,**kwargs)
    def execute_scheduled_func_and_remove_safe(job_id:str):
        "execute task scheduled in plugins && remove it from scheduler"
        func(**func_kwargs)
        scheduler.remove_job(job_id=job_id)
    partial_execute_and_remove=partial(execute_scheduled_func_and_remove_safe,job_id)
    # scheduler 支持，在 trigger 中设置的时间到了后，
    # 会将定时任务添加到 blocking_queue 中顺序执行
    scheduler.add_job(
        blocking_queue.put,
        id=job_id,
        trigger=trigger,
        kwargs=dict(item=partial_execute_and_remove,block=True),
        # replace_existing=True,
        **kwargs # trigger arguments
    )
    logger.debug(f"After adding job {job_id}, current jobs: {[scheduler.get_jobs()]}")
