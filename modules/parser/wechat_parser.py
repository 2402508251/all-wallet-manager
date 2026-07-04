"""
微信账单解析器 —— 解析微信 xlsx/csv 账单
微信导出格式：
  - xlsx: 前16行为元信息，第17行为表头，第18行起为数据
  - csv:  类似结构，BOM 头 + 元信息 + 表头 + 数据
"""
import json
import os
from datetime import datetime

from .base_parser import BaseParser, ParseResult
from ..standardizer.field_mapper import FieldMapper
from ..standardizer.time_normalizer import TimeNormalizer
from ..standardizer.amount_normalizer import AmountNormalizer
from ..standardizer.enum_mapper import EnumMapper
from core.config_manager import ConfigManager


class WechatParser(BaseParser):
    HEADER_KEYWORDS = ['交易时间', '交易类型', '交易对方', '商品', '收/支']

    def __init__(self, config_manager: ConfigManager = None):
        self.field_mapper = FieldMapper()
        self.time_normalizer = TimeNormalizer()
        self.amount_normalizer = AmountNormalizer()
        self.enum_mapper = EnumMapper(config_manager) if config_manager else None

    def get_channel(self) -> str:
        return 'wechat'

    def parse(self, file_path: str) -> ParseResult:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.xlsx':
            return self._parse_xlsx(file_path)
        elif ext == '.csv':
            return self._parse_csv(file_path)
        else:
            return ParseResult(errors=[f'不支持的文件格式: {ext}'])

    def _parse_xlsx(self, file_path: str) -> ParseResult:
        import openpyxl

        result = ParseResult()
        try:
            wb = openpyxl.load_workbook(file_path, read_only=True)
            ws = wb.active
        except Exception as e:
            result.errors.append(f'打开文件失败: {e}')
            return result

        rows = list(ws.iter_rows(values_only=True))
        wb.close()

        header_idx = self._find_header(rows)
        if header_idx < 0:
            result.errors.append('未找到表头行')
            return result

        headers = [str(h).strip() if h else '' for h in rows[header_idx]]
        result.total = len(rows) - header_idx - 1

        for row in rows[header_idx + 1:]:
            if not row or all(v is None for v in row):
                continue

            row_dict = {}
            for i, h in enumerate(headers):
                if i < len(row):
                    row_dict[h] = row[i]

            if row_dict.get('交易单号') is None:
                continue

            mapped = self.field_mapper.map(row_dict, 'wechat')
            record = self._standardize(mapped, row_dict)
            if record:
                result.add_record(record, {'channel': 'wechat', 'raw': row_dict})

        return result

    def _parse_csv(self, file_path: str) -> ParseResult:
        import csv

        result = ParseResult()
        try:
            lines, _ = self._read_csv_lines(file_path)
        except Exception as e:
            result.errors.append(f'读取CSV失败: {e}')
            return result

        header_idx = self._find_header_from_lines(lines)
        if header_idx < 0:
            result.errors.append('未找到表头行')
            return result

        headers = self._split_csv_line(lines[header_idx])
        result.total = len(lines) - header_idx - 1

        for line in lines[header_idx + 1:]:
            line = line.strip()
            if not line:
                continue

            values = self._split_csv_line(line)
            row_dict = {}
            for i, h in enumerate(headers):
                if i < len(values):
                    row_dict[h] = values[i]

            if not row_dict.get('交易单号'):
                continue

            mapped = self.field_mapper.map(row_dict, 'wechat')
            record = self._standardize(mapped, row_dict)
            if record:
                result.add_record(record, {'channel': 'wechat', 'raw': row_dict})

        return result

    def _standardize(self, mapped: dict, raw: dict) -> dict | None:
        channel_trade_no = mapped.get('channel_trade_no')
        if not channel_trade_no:
            return None

        channel_trade_no = str(channel_trade_no).strip().replace(' ', '')

        trade_time = self.time_normalizer.normalize(
            mapped.get('trade_time_raw'), 'wechat'
        )

        amount_result = self.amount_normalizer.normalize(
            mapped.get('amount_raw'),
            direction_raw=mapped.get('direction_raw'),
            channel='wechat',
        )

        trade_type_raw = mapped.get('trade_type_raw', '')
        trade_type = trade_type_raw
        if self.enum_mapper:
            trade_type = self.enum_mapper.map_trade_type(
                trade_type_raw, 'wechat',
                payment_method=mapped.get('payment_method'),
            )

        status = mapped.get('status', '')
        if status == '已退款' or status == '交易关闭':
            return None

        return {
            'channel': 'wechat',
            'trade_time': trade_time,
            'trade_type': trade_type,
            'direction': amount_result['direction'],
            'amount_cents': amount_result['amount_cents'],
            'counterparty': mapped.get('counterparty', ''),
            'product_desc': mapped.get('product_desc', ''),
            'payment_method': mapped.get('payment_method', ''),
            'status': status,
            'channel_trade_no': channel_trade_no,
            'remark': mapped.get('remark', ''),
        }

    def _find_header(self, rows: list) -> int:
        for i, row in enumerate(rows):
            row_strs = [str(v).strip() for v in row if v is not None]
            match_count = sum(1 for kw in self.HEADER_KEYWORDS if kw in row_strs)
            if match_count >= 3:
                return i
        return -1

    def _find_header_from_lines(self, lines: list[str]) -> int:
        for i, line in enumerate(lines):
            match_count = sum(1 for kw in self.HEADER_KEYWORDS if kw in line)
            if match_count >= 3:
                return i
        return -1

    def _read_csv_lines(self, file_path: str) -> tuple[list[str], str]:
        for encoding in ('utf-8-sig', 'gbk', 'utf-8'):
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                return content.splitlines(), encoding
            except (UnicodeDecodeError, UnicodeError):
                continue
        raise ValueError(f'无法识别文件编码: {file_path}')

    def _split_csv_line(self, line: str) -> list[str]:
        result = []
        current = []
        in_quotes = False
        for ch in line:
            if ch == '"':
                in_quotes = not in_quotes
            elif ch == ',' and not in_quotes:
                result.append(''.join(current).strip())
                current = []
            else:
                current.append(ch)
        result.append(''.join(current).strip())
        return result