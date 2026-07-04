"""
渠道自动检测 —— 根据文件名关键词自动识别微信/支付宝/建行渠道
"""
import re


class ChannelDetector:
    # 文件名关键词 → 渠道映射（含置信度）
    RULES = [
        (r'微信|wechat', 'wechat', 0.95),
        (r'支付宝|alipay', 'alipay', 0.95),
        (r'建设银行|建行|ccb|hqmx|CCB', 'ccb', 0.95),
    ]

    def detect(self, file_name: str) -> dict:
        """
        根据文件名关键词自动检测渠道：
        - 含"微信"/"wechat" → wechat
        - 含"支付宝"/"alipay" → alipay
        - 含"建设银行"/"建行"/"ccb"/"hqmx" → ccb
        - 无法识别 → unknown
        返回 { channel: str, confidence: float, source: 'auto_detect' }
        """
        for pattern, channel, confidence in self.RULES:
            if re.search(pattern, file_name, re.IGNORECASE):
                return {
                    'channel': channel,
                    'confidence': confidence,
                    'source': 'auto_detect',
                }

        return {
            'channel': 'unknown',
            'confidence': 0.0,
            'source': 'auto_detect',
        }
