# Desktop-Chatbot

desktop UI chatbot based on python uiautomation.

Currently developed chatbot:

- 中移移动办公 (version: 2.2.9100)

# Quick start
## Prerequisite
1. install required packages by `pip install -r requirements.txt`
2. You should keep the app which you want the UI chatbot to control at least minimized in windows taskbar. **The app cannot be hided into windows taskbar**, otherwise `uiautomation` cannot find the app's interface, error raised.
3. compatible system: windows 10, windows 11.

## Config File
copy `.env.example` to `.env` && set the variables

## Start Methods
1. `python main.py`

This method creates a local chatbot to process message sent with prefix `ROBOT_PREFIX`.
It loads plugins from `./plugins` and create a scheduler to enqueue every task, which is created by chating with chatbot.

2. `python http_server.py`

This method creates a local chatbot and a http server. It accepts request from network and send message at local.

once started http sever, api doc can be referred to `/docs` or `/redoc`