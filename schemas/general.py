import enum
import uuid
from typing import *
from pathlib import Path

from pytz import timezone
from datetime import datetime
from pydantic import BaseModel, field_validator, Field
from sqlmodel import SQLModel, Field, Column, Text, Boolean, Uuid, DateTime


class BusinessesEnum(enum.Enum):
    low_quality="低质专线预警"
    arrears="代付欠费告警"
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
        return [cls.outage, cls.low_quality, cls.arrears]

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
    Business:Optional[BusinessesEnum]=None
    "which business the item is. Can only be one of `BusinessesEnum`"

    Content:Optional[str]=""
    "message received"
    FromWxid:Optional[str]=""
    """
    session name received. if group, then group session name.
    You can give a name which not is a session name, chatbot will search it.
    """
    ActualName:Optional[str] = ""
    """
    Mostly FromWxid passed in is a phone number. ActualName is needed for manual and double check
    """
    Role:Optional[str]= ""
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


class HttpMessageStatusBase(SQLModel):
    message_id: str = Field(
        title="message id",
        description="unique message id",
        sa_column=Column("message_id", Text(), nullable=False))
    "unique message id"

    send_to: str = Field(
        title="send to",
        description="session name you send to",
        sa_column=Column("send_to", Text(), nullable=False)
    )
    "session name you send to"

    content: Optional[str] = Field(
        title="message content",
        description="message content",
        sa_column=Column("content", Text(), nullable=True)
    )
    "message content"

    success: bool = Field(
        title="success signal",
        description="if the message is sent successfully",
        default=False,
        sa_column=Column("success", Boolean(), nullable=False, default=False)
    )
    "success signal. To annotate if the message is sent successfully"

    failure_reason: Optional[str] = Field(
        title="failure reason",
        description="reason why message sent failed",
        default=None,
        sa_column=Column("failure_reason", Text(), nullable=True)
    )
    "reason why message sent failed."


class HttpMessageStatus(HttpMessageStatusBase, table=True):
    __tablename__ = "http_message_status"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, 
        title="unique id",
        description="unique id",
        sa_column=Column("id", Uuid(), primary_key=True,))
    "unique id. primary key"

    created_time: datetime = Field(
        default_factory=lambda : datetime.now(),
        title="created time",
        description="entry created time",
        sa_column=Column("created_time", DateTime(timezone=False), nullable=False)
    )
    "entry created time"


if __name__ == '__main__':
    from rich import print
    message_status = HttpMessageStatus.model_validate(
        HttpMessageStatusBase(
            message_id="message_id",
            send_to="test",
            content="ewrtae"
        )
    )
    print(message_status)
