from typing import *
from pydantic import BaseModel, ConfigDict
import uiautomation as uia


class ControlBaseModel(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)


TopLevelControl:TypeAlias = Union[uia.WindowControl,uia.PaneControl]
TextEditControl:TypeAlias = Union[
    uia.EditControl, uia.TextControl,
    uia.GroupControl,
]


class Session(ControlBaseModel):
    """session,
    the block in session list"""

    control:uia.Control
    """session's uiautomation control.
    You will need this when you want to click the session."""

    name:str
    "session name, displayed in session list"

    last_time:Optional[str]=None
    """last time chat in the session,
    be aware the fresher session displays week, longer displays (yy/)mm/dd.
    May be empty"""

    last_msg:Optional[str]=None
    """last message chat in the session,
    be aware last part of it is omitted if it's too long. May be empty."""

    msgs_unread:int=0
    """messages unread length.
    Fetched from the red bubble at the left bottom of the session block
    """

class EditBlock(ControlBaseModel):
    """
    contains emoji button, file transfer button, screenshot button
    and text edit box
    """

    emoji_btn: Optional[uia.Control]=None

    file_transfer_btn: Optional[uia.Control]=None

    screenshot_btn: Optional[uia.Control]=None

    text_edit_block: TextEditControl


class ChatInterface(ControlBaseModel):
    """
    This is the interface to chat with each other,
    a control revealed on the right once you click the session
    """

    top_bar: uia.Control
    """top bar in the interface,
    covers the session name and button clicked to show chat history"""

    chat_block: uia.Control
    """covers the message you chat with others"""

    edit_block: EditBlock
    """contains emoji button, file transfer button, screenshot button
    and text edit box"""


class HistoryMessage(ControlBaseModel):
    """
    Message model.
    - If member message, covers member name, message, avartar ImageControl
    - If system message, covers only message, and member_name=='_system'
    """
    member_name:str|None = None
    "if session_type==individual, `member_name` will be None"

    message_type:Literal["_system_","text","image","file"]|None = None
    "message_type==_system_ refers to the time message system sends"

    message:str | None = None
    "message could be None if message_type in [image, file]"

    filename:str | None = None
    "available when message_type==file"

    filesize: str | None = None
    "available when message_type==file"

    avartar_control:uia.ImageControl=None

    send_failure: bool = False
    "message sends failed. It must be sent by the current login user."

    read_already: str | None = None
    """read already message.
    if send_failure==True, read_already must be None;
    elif send_failure==False and read_already==None, it must be a message from others"""

class WindowsChooseFileBlock(ControlBaseModel):
    """
    General windows choosing file block.

    Compatible with windows 11
    """
    close_btn: uia.ButtonControl
    "click to close the block"

    search_bar: uia.ToolBarControl
    "bar to search the file directory.Click to send"

    filename_edit_ctrl: uia.EditControl
    "edit the filename control"

    open_btn: uia.ButtonControl
    "click to open file button"
