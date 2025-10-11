from typing import *
import abc

from chatbots import ChatBotClientBase

class PluginBase(abc.ABC):
    description:str=None
    author:str=None
    version:str=None

    @abc.abstractmethod
    def __init__(self, chatbot_client:ChatBotClientBase):
        """
        Args:
            chatbot_client(ChatBotClientBase): chatbot client base instance
        """
        self.chatbot_client = chatbot_client
        super().__init__()

    @abc.abstractmethod
    def handle_text(self,message:dict):
        """
        process message received
        """
        raise NotImplementedError
    
    @abc.abstractmethod
    def schedule_tasks(self,*args,**kwargs):
        """
        process scheduled tasks
        """
        raise NotImplementedError