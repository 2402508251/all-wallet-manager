"""
解析器工厂 —— 根据渠道标识返回对应的解析器实例
"""
from .base_parser import BaseParser
from .wechat_parser import WechatParser
from .alipay_parser import AlipayParser
from .ccb_parser import CCBParser
from .self_export_parser import SelfExportParser


class ParserFactory:
    _parsers = {
        'wechat': WechatParser,
        'alipay': AlipayParser,
        'ccb': CCBParser,
        'self_export': SelfExportParser,
    }

    @staticmethod
    def get_parser(channel: str, config_manager=None) -> BaseParser:
        parser_cls = ParserFactory._parsers.get(channel)
        if not parser_cls:
            raise ValueError(f"不支持的渠道: {channel}")
        if config_manager:
            return parser_cls(config_manager)
        return parser_cls()