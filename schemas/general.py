from typing import *
from pathlib import Path
import enum
import uuid
from datetime import datetime
from pydantic import BaseModel, field_validator, model_validator


class BusinessesEnum(enum.Enum):
    low_quality="低质专线预警"
    arrears="代付欠费超逾期缴费预警"
    cmoit="CMIOT红名单到期告警"
    outage="信控停机预警"
    flexible="灵活缴费周期到期预警"
    invoice="预开发票在30天以上未按时回款"

    @classmethod
    def get_names(cls):
        return [e.name for e in cls]
    
    @classmethod
    def get_values(cls):
        return [e.value for e in cls]

    @classmethod
    def already_developed(cls):
        "已完成第一阶段开发"
        return [cls.outage, cls.low_quality]

    @classmethod
    def get_optional(cls):
        optional_list=[]
        alread_developed=[e.name for e in cls.already_developed()]
        for name,value in zip(cls.get_names(),cls.get_values()):
            if name not in alread_developed:
                optional_list.append(f"{value}（不可选，暂未完成开发）")
            else:
                optional_list.append(f"{value}（可选，已完成开发）")
        return "\n".join(optional_list)


class SendMessage(BaseModel):
    """Message to send to chatbot client."""
    Business: BusinessesEnum
    "which business the item is. Can only be one of `BusinessesEnum`"

    Content:Optional[str]=""
    "message received"
    FromWxid:Optional[str]=""
    """
    session name received. if group, then group session name.
    You can give a name which not is a session name, chatbot will search it.
    """
    ActualName: str | None = ""
    """
    Mostly FromWxid passed in is a phone number. ActualName is needed for manual and double check
    """
    Role: str | None = ""
    """
    character role. e.g.: 客户经理，分公司副总，管理员，总监/主任
    """
    SenderWxid:Optional[str]=""
    """
    member name in a group session.
    Only exists when message is about to send to group.
    """
    File:Optional[Union[str,Path]]=None #XXX goto be `str` precedes `Path`, or `str` passed in converts to Path
    "Send file. file in bytes should be encoded in base64"
    Filename:Optional[str]=None
    """filename of the file you sends.
    If None but File not None, generates randomly."""
    id: uuid.UUID
    "unique id"
    CreatedTime: datetime
    "datetime this entry is created"
    IsSent: bool = False
    """
    Whether the message is successfully sent to client and receive its 200 returns.
    `200 returns` means the client has successfully send the message to UI chatbot.
    """
    SendTime: datetime | None = None
    """
    datetime this entry is successfully sent to client and receive its 200 returns.
    `200 returns` means the client has successfully send the message to UI chatbot.
    """

    @field_validator("File")
    @classmethod
    def validate_file(cls, var):
        if isinstance(var, str):
            assert "base64" in var, "File in string only supports base64 encode!"
        elif isinstance(var, Path):
            assert var.exists(), "File in Path not exists!"
        return var


if __name__ == '__main__':
    from rich import print
    message = SendMessage(Content="hello",FromWxid="he",SenderWxid="g",
                         File="D:/workspaces/toolkit/.vimrc.txt"
                          )
    print(message)