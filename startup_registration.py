"""Register the deployed application for the current Windows user's logon."""
import os
import subprocess
import sys


def register(executable, directory):
    if (sys.platform != 'win32' or executable is None
            or os.environ.get('AUTOMATIC_ORDER_REGISTER_STARTUP', '').lower() == 'false'):
        return
    import winreg
    command = subprocess.list2cmdline([str(executable), '--data-dir', str(directory)])
    name = 'AutomaticOrder-' + executable.stem
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                         r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command)
