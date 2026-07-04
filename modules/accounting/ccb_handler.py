"""
建行信用卡特殊处理 —— 生成唯一标识、区分交易/记账日期
"""
from core.dal import DAL


class CCBHandler:
    def __init__(self, dal: DAL):
        self.dal = dal

    def generate_trade_no(self, account_tag: str, trade_date: str, seq: int) -> str:
        date_part = trade_date.replace('-', '')
        seq_part = str(seq).zfill(4)
        return f"CCB_{account_tag}_{date_part}_{seq_part}"

    def distinguish_dates(self, record: dict) -> dict:
        return record

    def process_ccb_import(self, records: list[dict], account_tag: str) -> list[dict]:
        date_seq = {}
        for record in records:
            trade_time = record.get('trade_time', '')
            date_key = trade_time[:10].replace('-', '')
            date_seq[date_key] = date_seq.get(date_key, 0) + 1
            if not record.get('channel_trade_no'):
                record['channel_trade_no'] = self.generate_trade_no(
                    account_tag, date_key, date_seq[date_key]
                )
        return records