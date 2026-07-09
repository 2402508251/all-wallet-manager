"""
PyWebView API 桥接入口。

具体业务方法按领域拆分到 bridge_* mixin 中；本文件保留 ApiBridge
稳定导入路径，确保 main.py 和前端 window.pywebview.api[method] 调用不变。
"""
from .bridge_base import BridgeBase, DateTimeEncoder, audit_log
from .bridge_collection_email import CollectionEmailBridgeMixin
from .bridge_ai import AiBridgeMixin
from .bridge_bills import BillsBridgeMixin
from .bridge_accounting import AccountingBridgeMixin
from .bridge_reporting import ReportingBridgeMixin
from .bridge_settings_masterdata import SettingsMasterDataBridgeMixin
from .bridge_admin import AdminBridgeMixin


class ApiBridge(
    CollectionEmailBridgeMixin,
    AiBridgeMixin,
    BillsBridgeMixin,
    AccountingBridgeMixin,
    ReportingBridgeMixin,
    SettingsMasterDataBridgeMixin,
    AdminBridgeMixin,
    BridgeBase,
):
    pass
