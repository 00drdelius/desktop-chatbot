from typing import *
import abc
from pathlib import Path
import os.path as osp

import uiautomation as uia
from schemas import (
    Session,
    HistoryMessage,
    ChatInterface,
)

uia.SetGlobalSearchTimeout(0.2)

class ChatBotClientBase(abc.ABC):
    description:str=None
    author:str=None
    version:str=None

    @property
    @abc.abstractmethod
    def get_session_map(self)->dict[str, Session]:
        """fetch controls && chatnames in session list"""
        raise NotImplementedError


    @property
    @abc.abstractmethod
    def get_chat_interface(self)->ChatInterface:
        """
        Get the chat interface.
        a control revealed on the right once you click the session
        """
        raise NotImplementedError

    @abc.abstractmethod
    def switch_session(
        self,
        session_name:str,
        **kwargs
    ):
        """
        switch to the session
        Args:
            session_name(str): session name. It searches the session if session_name not in current session
            kwargs: additional kwargs your can pass in
        """
        raise NotImplementedError


    @abc.abstractmethod
    def get_session_history_msgs(self,only_last_msg:bool=True)->List[HistoryMessage]:
        """get session chat history.
        Args:
            only_last_msg(bool): if False, returns all history messages, else returns the last **member** history message
        Returns:
            out(List[HistoryMessage]): a list contains Message
        """
        raise NotImplementedError

    
    @abc.abstractmethod
    def send_message(
        self,
        session_name:str,
        message:str,
        from_clipboard:bool=True,
        at_list:List[str]=None,
        **kwargs
    )->None:
        """
        function to send message.
        Args:
            session_name(str): session name, revealed in session list.\
            It searches the session if session_name not in current session

            message(str): the message you are going to send

            from_clipboard(bool): if True, send the message from clipboard. It's quicker.

            at_list(List[str]): list of @ names. If `at_list==["*"]`, @全体成员
            
            kwargs: additional kwargs your can pass in
        """
        raise NotImplementedError


    def send_file(
        self,
        session_name:str,
        filepath:Union[Path,str],
        **kwargs
    ):
        """
        function to send file.
        **WARNING** Only send a file on a single process
        Args:
            session_name(str): session name. It searches the session if session_name not in current session.
            filepath(Path|str): file path.
            kwargs: additional kwargs your can pass in
        """
        if isinstance(filepath,Path):
            filepath = str(filepath.absolute())
        assert not osp.isdir(filepath), "You cannot send directory!"
        assert osp.exists(filepath), "file does not exists!"

        self.send_file_logic(session_name,filepath,**kwargs)
    
    @abc.abstractmethod
    def send_file_logic(
        self,
        session_name:str,
        filepath:Union[Path,str]
    )->bool:
        """
        private function. Please invoke `send_file` to instead.
        Returns:
            out: returns True if file sent successfully.
        """
        raise NotImplementedError


    @abc.abstractmethod
    def search(self,search_keywords:str)->None:
        """
        search and click the session.

        **[CAUTION]** session_name needs to be full
        Args:
            search_keywords(str): string used to search.
            You can use phone number to avoid searching different users with identical names.
        """
        raise NotImplementedError


