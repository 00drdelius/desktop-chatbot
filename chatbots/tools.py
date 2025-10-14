import time
from typing import *
from functools import wraps
from deprecated import deprecated

import win32gui
import regex as re
import uiautomation as uia

from schemas import (
    TopLevelControl, WindowsChooseFileBlock,

)
from logg import logger


def check_is_foreground(ctrl:TopLevelControl)->bool:
    """check if the window is foreground.
    Which means it's not minimized && not obscured"""
    target_handler = ctrl.NativeWindowHandle
    current_foreground_handler=win32gui.GetForegroundWindow()
    return target_handler==current_foreground_handler


# @time_consume
def switch_to_foreground(ctrl:TopLevelControl):
    """switch window to foreground."""
    assert ctrl.Exists(maxSearchSeconds=0.005),f"[ERROR] control not exists"
    if check_is_foreground(ctrl):
        return
    if ctrl.IsMinimize():
        # control is minimized to taskbar
        # XXX waitTime occurs the performance cuz it's time.sleep(waitTime) in function
        ctrl.SwitchToThisWindow(waitTime=0)
    else:
        # `SwitchToThisWindow` cannot function
        # if control is not minimized
        ctrl.SetFocus()


# 修改前：
def get_file_chosen_block(root_ctrl:uia.WindowControl)->WindowsChooseFileBlock:
    #XXX necessary to sleep a bit as it cannot find close_btn_parent if too quickly.
    #    to get compatible with some slow cpu
    # all_children = root_ctrl.GetChildren()
    # logger.debug(str(all_children))
    close_btn_parent = root_ctrl.TitleBarControl(Depth=1)
    if not close_btn_parent or not isinstance(close_btn_parent,uia.uiautomation.TitleBarControl):
        #XXX we only need to raise error once, the rest no need.
        raise LookupError(
            "Cannot find close button."
            "Check if your system is compatible or file chosen block is opened."
        )
    else:
        #XXX search close btton
        close_btn = close_btn_parent.ButtonControl()
    
    search_bar_pp = root_ctrl.PaneControl(Depth=1,ClassName="WorkerW")
    #XXX search search bar
    search_bar = (search_bar_pp.ProgressBarControl(Depth=3)
                  .GetFirstChildControl().ToolBarControl(Depth=1))
    
    #XXX search filename edit control
    filename_edit_ctrl = root_ctrl.PaneControl(Depth=1,ClassName="ComboBoxEx32").EditControl(Depth=2)
    
    #XXX search open button
    open_btn = root_ctrl.ButtonControl(Depth=1,Name="打开(O)")
    return WindowsChooseFileBlock(
        close_btn=close_btn,
        search_bar=search_bar,
        filename_edit_ctrl=filename_edit_ctrl,
        open_btn=open_btn
    )

# 修改后：
@deprecated
def __get_file_chosen_block(root_ctrl:uia.WindowControl)->WindowsChooseFileBlock:
    """
    Return Windows File Chosen Control(点击上传文件后弹出的选择文件块)

    **Compatible system**:
    - windows 11
    - windows 10

    Args:
        root_ctrl(uia.WindowControl): "选择文件"对话框
    Returns:
        out(WindowsChooseFileBlock): "选择文件"对话框 Control Model
    """
    # 增加等待时间以确保对话框完全加载
    time.sleep(0.5)
    
    # 查找关闭按钮
    close_btn_parent = root_ctrl.TitleBarControl(Depth=1)
    if not close_btn_parent or not isinstance(close_btn_parent,uia.uiautomation.TitleBarControl):
        raise LookupError(
            "Cannot find close button."
            "Check if your system is compatible or file chosen block is opened."
        )
    close_btn = close_btn_parent.ButtonControl()
    
    # 灵活查找搜索栏 - 使用更通用的方法
    search_bar = None
    # 尝试不同的查找方式
    try:
        # 方法1：通过WorkerW和Toolbar查找
        worker_w = root_ctrl.PaneControl(Depth=1, ClassName="WorkerW")
        toolbars = worker_w.FindAll(TreeScope.Children, lambda x: isinstance(x, uia.ToolBarControl))
        if toolbars:
            search_bar = toolbars[0]
    except:
        try:
            # 方法2：直接查找ToolbarControl
            search_bar = root_ctrl.ToolBarControl(Depth=2)
        except:
            # 方法3：通过组合查找
            search_bar = root_ctrl.PaneControl(Depth=1).ToolBarControl(Depth=2)
    
    if not search_bar:
        raise LookupError("Cannot find search bar in file dialog")
    
    # 灵活查找文件名编辑框
    filename_edit_ctrl = None
    try:
        # 方法1：通过ComboBoxEx32查找
        filename_edit_ctrl = root_ctrl.PaneControl(Depth=1,ClassName="ComboBoxEx32").EditControl(Depth=2)
    except:
        try:
            # 方法2：直接查找EditControl
            filename_edit_ctrl = root_ctrl.EditControl(Depth=2)
        except:
            # 方法3：通过标题查找
            filename_edit_ctrl = root_ctrl.EditControl(Depth=1, Name="文件名(N):")
    
    if not filename_edit_ctrl:
        raise LookupError("Cannot find filename edit control in file dialog")
    
    # 查找打开按钮
    open_btn = root_ctrl.ButtonControl(Depth=1,Name="打开(O)")
    if not open_btn.Exists(maxSearchSeconds=0.5):
        # 尝试其他可能的名称
        open_btn = root_ctrl.ButtonControl(Depth=1,Name="打开")
    
    return WindowsChooseFileBlock(
        close_btn=close_btn,
        search_bar=search_bar,
        filename_edit_ctrl=filename_edit_ctrl,
        open_btn=open_btn
    )

# @time_consume
def get_sibling_texts(base:uia.TextControl)->str:
    """
    iterate all TextControls in the same depth to get whole text.
    Args:
        base(uia.TextControl): the first control of the TextControl Sequence.
    """
    whole_text=""
    while base and base.Exists(maxSearchSeconds=0.02):
        if isinstance(base, uia.CustomControl):
            #XXX base could be an **EMPTY** controlType, uia.CustomControl , consider it as line break.
            whole_text+="\n"
        else:
            whole_text+=base.Name
        base=base.GetNextSiblingControl()

    return whole_text


def time_consume(func:Callable):
    @wraps(func)
    def inner(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        logger.debug(f"{func.__name__} consumes {end-start} sec")

        return result
    return inner

WECHAT_MSG_EXCLUDE_PATTERN=re.compile(
    r"^(?!"
    r".*邀请.*加入了群聊|"
    r".*与群里其他人都不是朋友关系，请注意隐私安全|"
    r".*撤回了一条消息|" # 撤回消息
    r"以下为新消息|" # 以下为新消息
    r"\d{4}年\d{1,2}月\d{1,2}日 \d{1,2}:\d{1,2}|" # 2025年5月15日 12:01
    r"星期. \d{1,2}:\d{1,2}|" # 星期五 12:01
    r"昨天 \d{1,2}:\d{1,2}|" # 昨天 20:30
    r"\d{1,2}:\d{1,2})" # 12:01
    r"(.|\n)+$" # group messages
)
