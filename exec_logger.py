"""
执行日志记录模块
用于记录程序执行过程，包括正常执行和异常报错
按业务类型和日期分类保存日志文件
"""

import os
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
from contextlib import contextmanager
from functools import wraps


class ExecutionLogger:
    """执行日志记录器"""
    
    def __init__(self, base_dir: str = None):
        """
        初始化执行日志记录器
        
        Args:
            base_dir: 基础目录，默认为当前程序目录下的execlog文件夹
        """
        if base_dir is None:
            # 获取当前程序目录
            current_dir = Path(__file__).parent
            base_dir = current_dir / "execlog"
        
        self.base_dir = Path(base_dir)
        self.current_business = None
        self.current_task_start_time = None
        self.current_log_file = None
        
        # 确保基础目录存在
        self.base_dir.mkdir(exist_ok=True)
    
    def _get_log_file_path(self, business_name: str) -> Path:
        """
        获取日志文件路径
        
        Args:
            business_name: 业务名称
            
        Returns:
            日志文件路径
        """
        # 创建业务目录
        business_dir = self.base_dir / business_name
        business_dir.mkdir(exist_ok=True)
        
        # 生成当天日期的文件名
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = business_dir / f"{today}.log"
        
        return log_file
    
    def _write_log(self, business_name: str, message: str):
        """
        写入日志到文件
        
        Args:
            business_name: 业务名称
            message: 日志消息
        """
        log_file = self._get_log_file_path(business_name)
        
        # 追加写入日志
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(message + '\n')
    
    def start_program(self, business_name: str):
        """
        记录程序启动
        
        Args:
            business_name: 业务名称
        """
        self.current_business = business_name
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        message = f"[{timestamp}] 程序启动 - 业务类型: {business_name}"
        self._write_log(business_name, message)
        self._write_log(business_name, "=" * 50)
    
    def start_task(self, task_name: str, business_name: str = None):
        """
        记录任务开始执行
        
        Args:
            task_name: 任务名称
            business_name: 业务名称，如果不提供则使用当前业务
        """
        if business_name is None:
            business_name = self.current_business
        
        if business_name is None:
            raise ValueError("业务名称不能为空，请先调用start_program或提供business_name参数")
        
        self.current_task_start_time = time.time()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        message = f"[{timestamp}] 开始执行任务: {task_name}"
        self._write_log(business_name, message)
    
    def log_step(self, step_description: str, business_name: str = None):
        """
        记录执行步骤
        
        Args:
            step_description: 步骤描述
            business_name: 业务名称，如果不提供则使用当前业务
        """
        if business_name is None:
            business_name = self.current_business
        
        if business_name is None:
            raise ValueError("业务名称不能为空，请先调用start_program或提供business_name参数")
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        message = f"[{timestamp}] 执行步骤: {step_description}"
        self._write_log(business_name, message)
    
    def log_success(self, result_description: str = None, business_name: str = None):
        """
        记录成功执行
        
        Args:
            result_description: 结果描述
            business_name: 业务名称，如果不提供则使用当前业务
        """
        if business_name is None:
            business_name = self.current_business
        
        if business_name is None:
            raise ValueError("业务名称不能为空，请先调用start_program或提供business_name参数")
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        if result_description:
            message = f"[{timestamp}] 执行成功: {result_description}"
        else:
            message = f"[{timestamp}] 执行成功"
        
        self._write_log(business_name, message)
    
    def log_error(self, error: Exception, context: str = None, business_name: str = None):
        """
        记录异常错误
        
        Args:
            error: 异常对象
            context: 错误上下文描述
            business_name: 业务名称，如果不提供则使用当前业务
        """
        if business_name is None:
            business_name = self.current_business
        
        if business_name is None:
            raise ValueError("业务名称不能为空，请先调用start_program或提供business_name参数")
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        error_message = f"[{timestamp}] 执行异常"
        if context:
            error_message += f" - {context}"
        
        error_message += f"\n错误类型: {type(error).__name__}"
        error_message += f"\n错误信息: {str(error)}"
        error_message += f"\n错误堆栈:\n{traceback.format_exc()}"
        
        self._write_log(business_name, error_message)
    
    def end_task(self, business_name: str = None):
        """
        记录任务结束，计算执行时长
        
        Args:
            business_name: 业务名称，如果不提供则使用当前业务
        """
        if business_name is None:
            business_name = self.current_business
        
        if business_name is None:
            raise ValueError("业务名称不能为空，请先调用start_program或提供business_name参数")
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # 计算执行时长
        if self.current_task_start_time:
            duration = time.time() - self.current_task_start_time
            duration_str = f"{duration:.2f}秒"
            if duration > 60:
                minutes = int(duration // 60)
                seconds = duration % 60
                duration_str = f"{minutes}分{seconds:.2f}秒"
        else:
            duration_str = "未知"
        
        message = f"[{timestamp}] 任务结束 - 总执行时长: {duration_str}"
        self._write_log(business_name, message)
        self._write_log(business_name, "-" * 30)
        
        # 重置任务开始时间
        self.current_task_start_time = None
    
    @contextmanager
    def task_context(self, task_name: str, business_name: str = None):
        """
        任务执行上下文管理器，自动记录任务开始和结束
        
        Args:
            task_name: 任务名称
            business_name: 业务名称
        """
        try:
            self.start_task(task_name, business_name)
            yield self
        except Exception as e:
            self.log_error(e, f"任务执行失败: {task_name}", business_name)
            raise
        finally:
            self.end_task(business_name)


# 创建全局执行日志记录器实例
exec_logger = ExecutionLogger()


def log_execution(business_name: str = None, task_name: str = None):
    """
    装饰器：自动记录函数执行过程
    
    Args:
        business_name: 业务名称
        task_name: 任务名称，如果不提供则使用函数名
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal task_name
            if task_name is None:
                task_name = func.__name__
            
            # 如果没有提供业务名称，尝试从全局记录器获取
            current_business = business_name or exec_logger.current_business
            
            if current_business is None:
                # 如果仍然没有业务名称，使用默认值
                current_business = "默认业务"
            
            with exec_logger.task_context(task_name, current_business):
                exec_logger.log_step(f"开始执行函数: {func.__name__}", current_business)
                try:
                    result = func(*args, **kwargs)
                    exec_logger.log_success(f"函数 {func.__name__} 执行完成", current_business)
                    return result
                except Exception as e:
                    exec_logger.log_error(e, f"函数 {func.__name__} 执行失败", current_business)
                    raise
        
        return wrapper
    return decorator


# 便捷函数
def start_program_log(business_name: str):
    """启动程序日志记录"""
    exec_logger.start_program(business_name)


def log_step(step_description: str, business_name: str = None):
    """记录执行步骤"""
    exec_logger.log_step(step_description, business_name)


def log_success(result_description: str = None, business_name: str = None):
    """记录成功执行"""
    exec_logger.log_success(result_description, business_name)


def log_error(error: Exception, context: str = None, business_name: str = None):
    """记录异常错误"""
    exec_logger.log_error(error, context, business_name)