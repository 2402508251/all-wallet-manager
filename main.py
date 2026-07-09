"""
AllWalletManager4 — 本地统一账单工具
PyWebView 入口：创建窗口、注册 API、加载前端
"""
import os
import sys
import threading
import http.server
import functools
import shutil

import webview
import webview.platforms.win32  # Nuitka hidden import for pywebview WinForms backend

from api.bridge import ApiBridge
from core.db import DatabaseManager


def _start_static_server(directory: str, port: int):
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=directory
    )
    with http.server.HTTPServer(('127.0.0.1', port), handler) as httpd:
        httpd.serve_forever()


def _copy_default_configs(resource_config_dir: str, config_dir: str):
    os.makedirs(config_dir, exist_ok=True)
    if not os.path.isdir(resource_config_dir):
        return

    for file_name in os.listdir(resource_config_dir):
        if not file_name.endswith('.json'):
            continue
        source_path = os.path.join(resource_config_dir, file_name)
        target_path = os.path.join(config_dir, file_name)
        if not os.path.exists(target_path):
            shutil.copy2(source_path, target_path)


def main():
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)
        resource_dir = os.path.dirname(os.path.abspath(__file__))
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))
        resource_dir = app_dir

    db_path = os.path.join(app_dir, 'data', 'wallet.db')
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    init_sql_path = os.path.join(resource_dir, 'scripts', 'init_db.sql')
    db_manager = DatabaseManager(db_path, init_sql_path)
    db_manager.initialize()

    from core.config_manager import ConfigManager
    config_dir = os.path.join(app_dir, 'config')
    resource_config_dir = os.path.join(resource_dir, 'config')
    _copy_default_configs(resource_config_dir, config_dir)
    config_manager = ConfigManager(config_dir)

    api = ApiBridge(db_manager, config_manager, app_dir)

    dist_dir = os.path.join(resource_dir, 'frontend', 'dist')
    dev_dir = os.path.join(resource_dir, 'frontend', 'src')

    if os.path.isfile(os.path.join(dist_dir, 'index.html')):
        frontend_dir = dist_dir
    elif os.path.isfile(os.path.join(dev_dir, 'index.html')):
        frontend_dir = dev_dir
    else:
        frontend_dir = None

    if frontend_dir:
        static_port = 18234
        server_thread = threading.Thread(
            target=_start_static_server,
            args=(frontend_dir, static_port),
            daemon=True,
        )
        server_thread.start()
        url = f'http://127.0.0.1:{static_port}/index.html'
    else:
        url = None

    if url is None:
        html_content = (
            '<!DOCTYPE html><html><head><meta charset="utf-8">'
            '<title>本地统一账单工具</title></head>'
            '<body style="display:flex;justify-content:center;align-items:center;height:100vh;'
            'font-family:sans-serif;color:#666">'
            '<div style="text-align:center">'
            '<h2>前端未构建</h2>'
            '<p>请执行: cd frontend && npm install && npm run build</p>'
            '</div></body></html>'
        )
    else:
        html_content = None

    window = webview.create_window(
        title='本地统一账单工具',
        url=url,
        html=html_content,
        js_api=api,
        width=1280,
        height=800,
        min_size=(960, 600),
    )

    webview.start(debug=not getattr(sys, 'frozen', False))


if __name__ == '__main__':
    main()