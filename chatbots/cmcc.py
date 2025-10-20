from typing import *
import uiautomation as uia
from pathlib import Path
import os.path as osp
import time
from schemas import (
    TopLevelControl,
    Session,
    EditBlock,
    ChatInterface,
    HistoryMessage,

    SessionNotFound,
    AtListNotFound,
    ChatInterfaceNotEnabled,
    FileTransferError
)
from . import ChatBotClientBase
from .tools import (
    switch_to_foreground,
    get_sibling_texts,
    check_is_foreground,
    get_file_chosen_block,
)
from logg import logger

class CmccChatClient(ChatBotClientBase):
    description = "移动办公desktop chatbot"
    author = "Delius"
    version = "v1.0.0"

    # @time_consume
    def __init__(self,cache_session_map:bool=False,wait_before_refresh:float=3.5):
        """
        Args:
            cache_session_map(bool): If you want to cache current session. Ususally False.
            wait_before_refresh(float): You need to refresh after new block pop up,
                or you can't get the block you want after refreshing.
                And every computer needs different sleep time as CPU performs different.
        """
        super().__init__()
        self.cmcc_appname = "移动办公"
        self.root_control = uia.PaneControl(Name=self.cmcc_appname)
        switch_to_foreground(self.root_control) #XXX must switch to window to get Document Control
        self._doc_ctrl = self.root_control.DocumentControl()

        # 增强的重试机制等待控件可用
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 先确保DocumentControl可用
                self._doc_ctrl.Refind(maxSearchSeconds=2)
                
                # 尝试获取GroupControl
                group_ctrl = self._doc_ctrl.GroupControl()
                children = group_ctrl.GetChildren()
                
                # 确保有足够的子控件
                if len(children) > 4:
                    self._root_ctrl = (children[4].GroupControl().GroupControl())
                    # logger.debug(f"成功找到控件，尝试次数: {attempt + 1}")
                    break
                else:
                    logger.debug(f"子控件数量不足: {len(children)}，重试中...")
                    raise LookupError("子控件数量不足")
                    
            except (LookupError, IndexError) as e:
                wait_time = min(2 + attempt * 0.5, 5)  # 递增等待时间，最大5秒
                logger.debug(f"尝试 {attempt + 1}/{max_retries} 失败: {e}，等待 {wait_time} 秒后重试")
                time.sleep(wait_time)
        else:
            raise LookupError(f"Find Control Timeout({max_retries * 2}s): {{ControlType: GroupControl}}")

        children = self._root_ctrl.GetChildren()
        self.navbar_ctrl = children[1]
        self.search_ctrl = children[2]
        _whole_chat_ctrls = children[3].ListControl(Depth=3)

        self.sesslist_ctrl = _whole_chat_ctrls.ListItemControl(
        ).GetLastChildControl().GetLastChildControl().GetLastChildControl()

        self.session_map:dict[str,Session] = dict()
        if cache_session_map:
            self.session_map:dict[str, Session] = self.get_session_map

        # XXX be aware that chat control must be revealed
        # after switching to session window 
        # NOTE: 若将整个窗口分为三个部分：【导航栏】【会话列表】【会话窗口】， self._chat_ctrl 就是整个【会话窗口】
        self._chat_ctrl = _whole_chat_ctrls.ListItemControl().GetNextSiblingControl()
        self.wait_before_refresh=wait_before_refresh

    # @time_consume
    # 修改 get_session_map 方法中的相关代码
    @property
    def get_session_map(self)->dict[str, Session]:
        """fetch controls && chatnames in session list"""
        if not check_is_foreground(self.root_control):
            switch_to_foreground(self.root_control)
    
        session_map:dict[str, Session] = dict()
    
        self.sess_ctrls = self.sesslist_ctrl.GetChildren()
        for sess_ctrl in self.sess_ctrls:
            try:
                _text_group_ctrls = sess_ctrl.GetLastChildControl().GetChildren()
                # 确保至少有一个文本控件来获取会话名称
                if len(_text_group_ctrls) < 1:
                    logger.warning(f"会话控件缺少必要的文本控件: {sess_ctrl}")
                    continue
                
                sessname = _text_group_ctrls[0].TextControl().Name
    
                # 安全地获取最后时间
                sess_last_time = None
                if len(_text_group_ctrls) > 1:
                    last_time_ctrl = _text_group_ctrls[1].TextControl()
                    if last_time_ctrl.Exists(maxSearchSeconds=0.005):
                        sess_last_time = last_time_ctrl.Name
    
                # 安全地获取最后消息
                sess_last_msg = None
                if len(_text_group_ctrls) > 2:
                    sess_last_msg_ctrl = _text_group_ctrls[2].TextControl()
                    if sess_last_msg_ctrl.Exists(maxSearchSeconds=0.005):
                        sess_last_msg = sess_last_msg_ctrl.Name
    
                # 安全地获取未读消息数
                msgs_unread = 0
                if len(_text_group_ctrls) > 3:
                    try:
                        msgs_unread = int(_text_group_ctrls[3].TextControl().Name)
                    except (ValueError, AttributeError):
                        msgs_unread = 0
    
                session_map[sessname] = Session(
                    control=sess_ctrl,
                    name=sessname,
                    last_time=sess_last_time,
                    last_msg=sess_last_msg,
                    msgs_unread=msgs_unread
                )
            except Exception as e:
                logger.error(f"处理会话控件时出错: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                continue
        
        logger.debug(f"[session_map]\n{session_map.keys()}")
        return session_map

    @property
    def get_chat_interface(self)->ChatInterface:
        """
        Get the chat interface.
        a control revealed on the right once you click the session
        """

        # XXX session not clicked
        if not self._chat_ctrl.GetFirstChildControl():
            # XXX we need to refind the control to get the new control tree after clicking the session 
            self._chat_ctrl.Refind() #TODO not working
            # TODO when initializing 移动办公 pls first click any session to enable chat interface
            if not self._chat_ctrl.GetFirstChildControl():
                #TODO here needs to refresh self._chat_ctrl else raise Error when after first clicking session and get chat interface
                raise ChatInterfaceNotEnabled("You need to click a session before getting chat interface.")

        self.chat_msg_ctrl = self._chat_ctrl.GetFirstChildControl(
        ).GetFirstChildControl()
        _whole_chat_msg_ctrls = self.chat_msg_ctrl.GetChildren()

        #XXX chat_msg block preprocess
        if len(_whole_chat_msg_ctrls) < 2:
            logger.error(f"聊天控件结构异常：期望至少2个子控件，实际获得{len(_whole_chat_msg_ctrls)}个")
            raise ChatInterfaceNotEnabled("聊天界面控件结构异常，请检查会话是否正确选中")
        
        chat_block_children = _whole_chat_msg_ctrls[1].GetChildren()
        if len(chat_block_children) < 3:
            logger.error(f"聊天块子控件数量不足：期望至少3个，实际获得{len(chat_block_children)}个")
            raise ChatInterfaceNotEnabled("聊天块控件结构异常，请检查会话状态")
        
        chat_block = _whole_chat_msg_ctrls[1].DocumentControl( #NOTE 消息记录GroupCtrls的最后一个的子节点是DocumentCtrl
        ).GetParentControl().GetParentControl()
        #XXX chat_msg block preprocess.

        #XXX edit block preprocess
        if len(_whole_chat_msg_ctrls) < 3:
            logger.error(f"编辑控件结构异常：期望至少3个子控件，实际获得{len(_whole_chat_msg_ctrls)}个")
            raise ChatInterfaceNotEnabled("编辑界面控件结构异常")
        
        edit_children=_whole_chat_msg_ctrls[2].GroupControl().GetChildren()
        
        if len(edit_children) < 4:
            logger.error(f"编辑块子控件数量不足：期望至少4个，实际获得{len(edit_children)}个")
            raise ChatInterfaceNotEnabled("编辑块控件结构异常，无法获取编辑功能")
        
        edit_function_children =edit_children[2].GetChildren()
        text_edit_block = edit_children[3].GroupControl(Depth=2)
        #XXX edit block preprocess

        chat_interface = ChatInterface(
            top_bar=_whole_chat_msg_ctrls[0],
            chat_block=chat_block,
            edit_block=EditBlock(
                emoji_btn=edit_function_children[0],
                file_transfer_btn=edit_function_children[1],
                screenshot_btn=edit_function_children[2],
                text_edit_block=text_edit_block
            )
        )
        return chat_interface


    # @time_consume
    def switch_session(self, session_name:str,**kwargs):
        """
        switch the window to the foreground, search and switch to the session if get None in session_map.
        And Refresh the controls at the end.
        
        Args:
            top_bar_name(str): you may provide top_bar_name to check if the session is switched properly.
            retries(int): number of time to retry
            ignore_error(bool): ignore error if topbar name is still not top_bar_name after exceeding swtich retries.\
            default to False
        """

        if not check_is_foreground(self.root_control):
            switch_to_foreground(self.root_control)
        
        ignore_error = kwargs.pop("ignore_error", False)
        top_bar_name:str|None = kwargs.pop("top_bar_name", None)
        if top_bar_name:
            #NOTE if top_bar_name is provided, we will retry 3 times if switched topbar_name != top_bar_name
            retries=kwargs.pop("retries",3)
            top_bar_name = (top_bar_name.replace('\u3000','').replace("\xa0","")
                            .replace("\ufeff","").replace(" ","").strip())
        else:
            retries=1
        while retries!=0:
            session = self.session_map.get(session_name,None)
            if not session:
                self.search(session_name)
            else:
                control = session.control
                # switch_to_top(self.root_control)
                # XXX waitTime occurs the performance
                control.Click(simulateMove=False,waitTime=0)
            self.__refresh_ctrls() #XXX refresh to get new session history msgs
            if top_bar_name:
                current_topbar_name=self.get_chat_interface.top_bar.TextControl().Name
                if current_topbar_name==top_bar_name:
                    break
                logger.warning(
                    ("【发现切换的会话窗口名与提供名不一致】"
                     f"当前会话窗口名：{current_topbar_name}；提供名：{top_bar_name}\n"
                     f"重试。剩余重试次数：{retries-1}次"))
                if retries-1==0 and not ignore_error:
                    raise SessionNotFound(
                        (f"【切换的会话窗口与提供名不一致】"
                         f"当前会话窗口名：{current_topbar_name}；提供名：{top_bar_name}\n"
                         "经过多次重试，仍不一致"))
            retries-=1


    # @time_consume
    def get_session_history_msgs(self,only_last_msg:bool=True):
        """get session chat history.
        Args:
            only_last_msg(bool): if False, returns all history messages, else returns the last **member** history message
        Returns:
            out(List[Message]): a list contains Message
        """
        #NOTE 中移办公 is no need to refresh the tree the get history messges
        chat_interface = self.get_chat_interface
        chat_block = chat_interface.chat_block
        children = chat_block.GetChildren()
        children = children[1:-1] # drop the first && the last, useless controls
        msg_list:List[HistoryMessage] = []

        # XXX reverse children to adapt when `get_all_history_msgs`==False,
        # You can quickly get the last **member** msg nor **system** msg
        for child in reversed(children):
            msg_children = child.GetChildren()
            if len(msg_children)==2:
                # XXX has sys time message
                if not only_last_msg:
                    member_name = "_system"
                    chat_time = msg_children[0].TextControl().Name
                    msg_list.append(HistoryMessage(member_name=member_name,message=chat_time))

            sys_or_member = msg_children[-1].GetChildren()

            if len(sys_or_member)>=3:
                # XXX it's member message
                # logger.debug(f"[sys_or_member]\n{sys_or_member}")
                avartar_ctrl = sys_or_member[0].ImageControl(Depth=3)
                member_name = sys_or_member[1].Name

                # XXX message could be image message, ImageControl
                image_or_text = sys_or_member[2].GroupControl(Depth=3).GetFirstChildControl()
                if isinstance(image_or_text,uia.TextControl):
                    message = get_sibling_texts(image_or_text)
                elif isinstance(image_or_text, uia.ImageControl):
                    message = "[图像]"

                # XXX if my message, contains “已读” under message bubble
                # inducing sys_or_member.length ==4, but it's no need
                msg_list.append(HistoryMessage(
                    avartar_control=avartar_ctrl,
                    member_name=member_name,
                    message=message
                ))
                if only_last_msg:
                    break

            elif len(sys_or_member)==1:
                # XXX system message, and contains more GroupControl if sys msgs are adjacent
                if not only_last_msg:
                    member_name = "_system"
                    for group_ctrl in sys_or_member[0].GetChildren():
                        message = get_sibling_texts(group_ctrl.TextControl())
                        msg_list.append(HistoryMessage(
                            member_name=member_name,
                            message=message
                        ))
                else:
                    continue

        msg_list.reverse() #XXX reverse back

        debug_msg = [ f"{msg.member_name}:{msg.message}" for msg in msg_list ]
        # logger.debug(f"[sess_history_msgs]\n{debug_msg}")
        return msg_list


    def switch_session_and_get_history_msgs(
        self,session_name:str, only_last_msg:bool=True,**kwargs
    )->tuple[ChatInterface, List[HistoryMessage]]:
        """
        switch to the session, get chat history messages && edit controls
        Args:
            session_name(str): omit
            only_last_msg(bool): if False, returns all history messages, else returns the last **member** history message

        Returns:
            out(tuple[ChatInterface, List[Message]]):
            - tuple[0] is the chat interface, covers control of topbar, chatroom block, edit block
            - tuple[1] is the list of session history messages
        """
        self.switch_session(session_name,only_last_msg=only_last_msg)

        chat_interface = self.get_chat_interface
        sess_history_msgs = self.get_session_history_msgs(only_last_msg)

        debug_msg = [ f"{msg.member_name}:{msg.message}" for msg in sess_history_msgs ]
        logger.debug(f"[sess_history_msgs]\n{debug_msg}")
        return chat_interface, sess_history_msgs


    # @time_consume
    def send_message(
        self,
        session_name:str,
        message:str,
        from_clipboard:bool=True,
        at_list:List[str]=None,
        **kwargs
    ):
        """
        function to send message.
        Args:
            session_name(str): session name, revealed in session list.\
            It searches the session if session_name not in current session

            message(str): the message you are going to send

            from_clipboard(bool): if True, send the message from clipboard. It's quicker.

            at_list(List[str]): list of @ names. If `at_list==["*"]`, @全体成员

            top_bar_name(str): you may provide top_bar_name to check if the session is switched properly.

            retries(int): number of time to retry

            ignore_error(bool): ignore error if topbar name is still not top_bar_name after exceeding swtich retries.\
            default to False
        """

        if not check_is_foreground(self.root_control):
            switch_to_foreground(self.root_control)

        self.switch_session(session_name,
                            top_bar_name=kwargs.pop("top_bar_name",None),
                            retries=kwargs.pop("retries",3),
                            ignore_error=kwargs.pop("ignore_error", False),
                            )
        chat_interface = self.get_chat_interface

        edit_block = chat_interface.edit_block
        edit_text_block:uia.TextControl=edit_block.text_edit_block
        edit_text_block.Click(waitTime=0)
        #XXX necessary to backspace all content before sending message
        edit_text_block.SendKeys("{Ctrl}a{BACK}",waitTime=0)
        #XXX at_list type first if not empty
        if at_list:
            if "*" in at_list[0]:
                edit_text_block.SendKeys(f"@全体成员",waitTime=0)
                edit_text_block.SendKeys("{Enter}",waitTime=0)
                
            for member in at_list:
                edit_text_block.SendKeys(f"@{member}",waitTime=0)
                edit_text_block.SendKeys("{Enter}",waitTime=0)
                # _at = self.get_at_control_list
        if not from_clipboard:
            # NOTE Name has no setterz
            # edit_block.text_edit_block.Name = msg
            edit_text_block.SendKeys(message,waitTime=0)
        else:
            uia.SetClipboardText(message)
            edit_text_block.SendKeys("{Ctrl}v",waitTime=0)

        edit_text_block.SendKeys("{Enter}",waitTime=0)

    def send_file(self, session_name, filepath, **kwargs):
        """
        function to send file.
        **WARNING** Only send a file on a single process
        Args:
            session_name(str): session name. It searches the session if session_name not in current session.

            filepath(Path|str): file path.

            top_bar_name(str): you may provide top_bar_name to check if the session is switched properly.

            retries(int): number of time to retry

            ignore_error(bool): ignore error if topbar name is still not top_bar_name after exceeding swtich retries.\
            default to False
        """
        return super().send_file(session_name, filepath, **kwargs)

    def send_file_logic(
            self,
            session_name:str,
            filepath:Union[str,Path],
            **kwargs
        ):
        try:
            self.switch_session(
                session_name,
                top_bar_name=kwargs.pop("top_bar_name",None),
                retries=kwargs.pop("retries",3),
                ignore_error=kwargs.pop("ignore_error", False),
            )
            chat_interface = self.get_chat_interface
            file_transfer_btn=chat_interface.edit_block.file_transfer_btn
            file_transfer_btn.Click(waitTime=0)
            # logger.debug(f"[BEFORE REFRESH] {self.root_control.GetChildren()}")
            self.__refresh_ctrls() #XXX refresh to get the file transfer block
            # logger.debug(f"[AFTER REFRESH] {self.root_control.GetChildren()}")

            fileupload_ctrl=self.root_control.GetFirstChildControl()
            if fileupload_ctrl==None and not isinstance(fileupload_ctrl,uia.uiautomation.WindowControl):
                raise FileTransferError("[ERROR] could not find the file transfer control(选择文件的 control)!")

            file_chosen_block=get_file_chosen_block(fileupload_ctrl)
            if isinstance(filepath, str):
                directory = osp.dirname(filepath)
                filename = osp.basename(filepath)
            uia.SetClipboardText(directory)
            #XXX type directory in search bar. {Ctrl}+L could directly focus on the search bar
            file_chosen_block.search_bar.SendKeys("{Ctrl}l{Ctrl}v{Enter}",waitTime=0)
            time.sleep(0.1)
            uia.SetClipboardText(filename)
            #XXX type filename
            # file_chosen_block.filename_edit_ctrl.Click(waitTime=0)
            #XXX filename edit shortcut: alt+n
            file_chosen_block.filename_edit_ctrl.SendKeys("{Alt}n{Ctrl}v",waitTime=0)
            # file_chosen_block.filename_edit_ctrl.SendKeys(filename,waitTime=0)
            file_chosen_block.open_btn.SendKeys("{Enter}",waitTime=0)
            # file_chosen_block.open_btn.Click(waitTime=0)
        except Exception as exc:
            logger.error(f"[文件发送报错] {exc}")
            return False
        else:
            return True
    

    def search(self, search_keywords:str):

        #NOTE sometimes `search_keywords` contains special invisible characters: \ufeff, \xa0, \u3000. Replace needed
        search_keywords = search_keywords.replace('\u3000','').replace("\xa0","").replace("\ufeff","")

        switch_to_foreground(self.root_control)

        uia.SetClipboardText(search_keywords)
        search_editctrl = self.search_ctrl.EditControl()
        #XXX ctrl+f, shortcut keys to focus on search edit control;
        #XXX ctrl+a, make sure all typed keys are cleared
        self.root_control.SendKeys("{Ctrl}f{Ctrl}a{Ctrl}v",waitTime=0)

        self.__refresh_ctrls() #XXX to get the searched sessions list

        search_result:uia.GroupControl = (search_editctrl.GetParentControl().
                                          GetNextSiblingControl().GetLastChildControl())

        if "无结果 没有想找的结果？" in search_result.Name:
            raise SessionNotFound(f"{search_keywords} not found.")

        elif "最近联系人" not in search_result.Name:
                #NOTE:不是最近联系人，移动办公大多情况不会默认选择第一个搜索到的联系人，需要自动化鼠标点击
                #XXX 在search result下找到Name为${search keywords}的TextControl组件，找到后鼠标点击该组件
                try:
                    
                    # 在搜索结果中查找匹配搜索关键词的TextControl，增加等待时间
                    searched_session = search_result.TextControl(Name=search_keywords)
                    
                    if searched_session:  
                        # 找到匹配的TextControl，进行鼠标点击选择
                        searched_session.Click(waitTime=0)
                        logger.debug(f"找到并点击选择最近联系人: {search_keywords}")
                    else:
                        logger.warning(f"未找到匹配 '{search_keywords}' 的TextControl组件")
                        raise SessionNotFound(f"未找到匹配 '{search_keywords}' 的最近联系人")
                        
                except Exception as e:
                    logger.error(f"联系人搜索报错: {e}")
                    # 发生异常时抛出异常而不是使用默认行为
                    raise SessionNotFound(f"搜索联系人 '{search_keywords}' 时发生错误: {e}")
        else:
            # 处理"最新联系人"情况，也需要点击选择联系人才能进入对话框
            try:
                
                # 在搜索结果中查找匹配搜索关键词的TextControl，增加等待时间
                # searched_session = search_result.TextControl(Name=search_keywords)
                searched_session = search_result.TextControl(Name=search_keywords)
                
                if searched_session:
                    # 找到匹配的TextControl，进行鼠标点击选择
                    searched_session.Click(waitTime=0)
                    logger.debug(f"在最新联系人中找到并点击选择联系人: {search_keywords}")
                #XXX maybe no need to use Enter
                # else:
                #     logger.warning(f"在最新联系人中未找到匹配 '{search_keywords}' 的TextControl组件")
                #     # 尝试使用Enter键作为备选方案
                #     search_editctrl = self.search_ctrl.EditControl()
                #     search_editctrl.SendKeys("{Enter}",waitTime=0)
                #     logger.debug(f"使用Enter键选择默认联系人")
                    
            except Exception as e:
                logger.error(f"最新联系人搜索报错: {e}")
                # 直接跳出当前执行流程，执行下一个流程
                raise SessionNotFound(f"最新联系人搜索失败: {e}")

    @property
    def get_at_control_list(self)->List[uia.ListItemControl]:
        """
        once @, @ list control revealed in the sixth GroupControl
        under DocumentControl.GroupControl.

        CAUTION
        ---
        1. you need to input "@" before get this property
        2. you can "@name" to get an @ list contains only the one you want to @.
        Useful to position the member if @ list is too large

        Returns:
            out: a list of ListItemControl, which `Name` is member name
        
        """
        children=self._doc_ctrl.GroupControl().GetChildren()
        if len(children)<6:
            raise AtListNotFound("you need to input '@' before get this property")
        at_control_list = []

        temp = children[5].ListControl(Depth=1)
        at_control_list = temp.GetChildren()
        return at_control_list


    def __refresh_ctrls(self):
        """
        refresh all controls. Sleep `self.wait_before_refresh` before refresh.
        """
        time.sleep(self.wait_before_refresh)
        #XXX just reinitialize to refresh. 
        self.__init__(cache_session_map=False,wait_before_refresh=self.wait_before_refresh)


    def __send_file_logic(self, session_name:str, filepath:Union[str,Path]):
        try:
            self.switch_session(session_name)
            chat_interface = self.get_chat_interface
            file_transfer_btn = chat_interface.edit_block.file_transfer_btn
            file_transfer_btn.Click(waitTime=0)
            
            # 增加等待时间，确保文件对话框完全打开
            time.sleep(1.0)
            
            # 刷新控件树
            self.__refresh_ctrls()
            
            # 尝试获取文件上传对话框
            fileupload_ctrl = None
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    fileupload_ctrl = self.root_control.GetFirstChildControl()
                    if fileupload_ctrl and isinstance(fileupload_ctrl, uia.uiautomation.WindowControl):
                        logger.debug(f"[尝试 {attempt+1}] 找到文件上传对话框")
                        break
                except Exception as e:
                    logger.debug(f"[尝试 {attempt+1}] 获取文件上传对话框失败: {e}")
                time.sleep(0.5)  # 每次尝试之间的等待时间
            
            if not fileupload_ctrl or not isinstance(fileupload_ctrl, uia.uiautomation.WindowControl):
                raise FileTransferError("[ERROR] 无法找到文件传输控件(选择文件的对话框)!")
            
            # 转换文件路径为绝对路径字符串
            if isinstance(filepath, Path):
                full_path = str(filepath.absolute())
            else:
                full_path = osp.abspath(filepath)
            
            # 确保文件存在
            if not osp.exists(full_path):
                raise FileTransferError(f"[ERROR] 文件不存在: {full_path}")
            
            logger.debug(f"发送文件: 完整路径={full_path}")
            
            # 设置剪贴板内容为完整路径
            uia.SetClipboardText(full_path)
            
            # 直接操作文件名输入框，完全绕过search_bar
            try:
                # 尝试通过不同方式获取文件名输入框
                filename_edit_ctrl = None
                # 方法1：通过类名查找
                try:
                    combo_box = fileupload_ctrl.PaneControl(Depth=1, ClassName="ComboBoxEx32")
                    filename_edit_ctrl = combo_box.EditControl(Depth=2)
                except Exception:
                    # 方法2：直接查找编辑框
                    try:
                        filename_edit_ctrl = fileupload_ctrl.EditControl(Depth=2)
                    except Exception:
                        # 方法3：通过标题查找
                        filename_edit_ctrl = fileupload_ctrl.EditControl(Depth=1, Name="文件名(N):")
                
                if not filename_edit_ctrl or not filename_edit_ctrl.Exists(maxSearchSeconds=0.5):
                    raise LookupError("无法找到文件名输入框")
                
                # 直接在文件名输入框中设置完整路径
                filename_edit_ctrl.Click(waitTime=0)
                filename_edit_ctrl.SendKeys("{Ctrl}a{BACK}", waitTime=0)  # 清空现有内容
                filename_edit_ctrl.SendKeys("{Ctrl}v", waitTime=0)  # 粘贴完整路径
                filename_edit_ctrl.SendKeys("{Enter}", waitTime=0)  # 按Enter确认
                
                # 额外的等待时间确保文件选择完成
                time.sleep(0.5)
                
                # 尝试直接按Enter键确认文件选择
                fileupload_ctrl.SendKeys("{Enter}", waitTime=0)
                
            except Exception as e:
                logger.error(f"[设置文件路径时出错] {e}")
                # 终极备选方案：使用win32gui直接操作对话框
                try:
                    logger.debug("尝试终极备选方案：使用win32gui直接操作对话框")
                    import win32gui
                    import win32con
                    
                    # 获取文件名输入框句柄
                    def find_edit_handle(hwnd, result):
                        if win32gui.GetClassName(hwnd) == "Edit" and result[0] is None:
                            # 检查父窗口是否为ComboBoxEx32
                            parent_hwnd = win32gui.GetParent(hwnd)
                            if parent_hwnd and win32gui.GetClassName(parent_hwnd) == "ComboBoxEx32":
                                result[0] = hwnd
                    
                    edit_handle = [None]
                    win32gui.EnumChildWindows(fileupload_ctrl.NativeWindowHandle, find_edit_handle, edit_handle)
                    
                    if edit_handle[0]:
                        # 设置文件名
                        win32gui.SetWindowText(edit_handle[0], full_path)
                        # 按Enter键确认
                        win32gui.PostMessage(fileupload_ctrl.NativeWindowHandle, win32con.WM_COMMAND, 1, 0)  # IDOK = 1
                        return True
                    else:
                        raise LookupError("无法找到文件名输入框句柄")
                except Exception as fallback_error:
                    logger.error(f"[终极备选方案也失败] {fallback_error}")
                    raise
        except Exception as exc:
            logger.error(f"[SENDING FILE ERROR FROM CMCC] {exc}")
            return False
        else:
            return True


    def ___refresh_ctrls(self):
        """
        refresh all controls. Sleep `self.wait_before_refresh` before refresh.
        """
        time.sleep(self.wait_before_refresh)
        # 只刷新必要的控件，避免重新初始化整个对象
        try:
            switch_to_foreground(self.root_control)
            self._doc_ctrl = self.root_control.DocumentControl()
            
            # 重新获取控件树
            for _ in range(3):  # 减少重试次数
                try:
                    self._root_ctrl = (self._doc_ctrl.GroupControl().GetChildren()[4]
                                       .GroupControl().GroupControl())
                    break
                except LookupError:
                    time.sleep(0.5)  # 减少等待时间
            else:
                logger.warning("刷新控件时无法找到GroupControl，跳过刷新")
                return
                
            children = self._root_ctrl.GetChildren()
            self.navbar_ctrl = children[1]
            self.search_ctrl = children[2]
            _whole_chat_ctrls = children[3].ListControl(Depth=3)
            
            self.sesslist_ctrl = _whole_chat_ctrls.ListItemControl(
            ).GetLastChildControl().GetLastChildControl().GetLastChildControl()
            
            self._chat_ctrl = _whole_chat_ctrls.ListItemControl().GetNextSiblingControl()
        except Exception as e:
            logger.warning(f"刷新控件时出错: {e}，继续使用现有控件")

