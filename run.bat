@echo off
echo 执行客响移动办公消息自动化传递助手。。。
echo Installing required packages...
pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo Failed to install requirements
    pause
    exit /b %errorlevel%
)

:input_business
set /p business="请输入您想执行的业务 (required): （请从['信控停机预警','低质专线预警','代付欠费超逾期缴费预警']中选择）"

if "%business%"=="" (
    echo 业务不能为空！
    goto input_business
)

echo Running 4a-warning.py with business="%business%"...
python 4a-warning.py --business "%business%"

if %errorlevel% neq 0 (
    echo Failed to run 4a-warning.py
    pause
    exit /b %errorlevel%
)

pause