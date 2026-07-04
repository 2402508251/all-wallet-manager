"""
时间标准化器 —— 各渠道时间字符串 → ISO8601 格式
"""
from datetime import datetime


class TimeNormalizer:
    # 各渠道时间格式
    FORMATS = {
        'wechat': '%Y-%m-%d %H:%M:%S',
        'alipay': '%Y/%m/%d %H:%M',
        'ccb': '%Y%m%d',
    }

    TIMEZONE = '+08:00'

    def normalize(self, raw_time, channel: str) -> str:
        """
        将原始时间转为 ISO8601 格式：YYYY-MM-DDTHH:MM:SS+08:00

        Args:
            raw_time: 原始时间值（datetime对象或字符串）
            channel: 渠道标识

        Returns:
            ISO8601 格式的时间字符串
        """
        if isinstance(raw_time, datetime):
            dt = raw_time
        else:
            fmt = self.FORMATS.get(channel, '%Y-%m-%d')
            dt = datetime.strptime(str(raw_time).strip(), fmt)

        return dt.strftime('%Y-%m-%dT%H:%M:%S') + self.TIMEZONE
