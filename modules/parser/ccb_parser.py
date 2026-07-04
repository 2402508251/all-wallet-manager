"""
建设银行账单解析器 —— 解析建行 xls/pdf 账单
建行导出格式：
  - xls: 前2行为元信息，第3行为表头，第4行起为数据
  - pdf: 使用 pdfplumber 提取表格
  - 建行无唯一单号，需自动生成：CCB_{account_tag}_{YYYYMMDD}_{4位序号}
  - 复合去重策略：序号唯一 + 跨文件去重 + 复合条件兜底
  - 金额含正负号，正数=收入，负数=支出
  - 对方信息格式："账号/户名"
"""
import os
import re

from .base_parser import BaseParser, ParseResult
from ..standardizer.field_mapper import FieldMapper
from ..standardizer.time_normalizer import TimeNormalizer
from ..standardizer.amount_normalizer import AmountNormalizer
from ..standardizer.enum_mapper import EnumMapper
from core.config_manager import ConfigManager


class CCBParser(BaseParser):
    HEADER_KEYWORDS = ['交易日期', '摘要', '交易金额', '账户余额']

    def __init__(self, config_manager: ConfigManager = None):
        self.field_mapper = FieldMapper()
        self.time_normalizer = TimeNormalizer()
        self.amount_normalizer = AmountNormalizer()
        self.enum_mapper = EnumMapper(config_manager) if config_manager else None

    def get_channel(self) -> str:
        return 'ccb'

    def parse(self, file_path: str) -> ParseResult:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.xls':
            return self._parse_xls(file_path)
        elif ext == '.pdf':
            return self._parse_pdf(file_path)
        else:
            return ParseResult(errors=[f'不支持的文件格式: {ext}'])

    def _parse_xls(self, file_path: str) -> ParseResult:
        import xlrd

        result = ParseResult()
        try:
            wb = xlrd.open_workbook(file_path)
            ws = wb.sheet_by_index(0)
            self._datemode = wb.datemode
        except Exception as e:
            result.errors.append(f'打开文件失败: {e}')
            return result

        header_idx = self._find_header(ws)
        if header_idx < 0:
            result.errors.append('未找到表头行')
            return result

        headers = [str(ws.cell_value(header_idx, c)).strip()
                    for c in range(ws.ncols)]
        result.total = ws.nrows - header_idx - 1

        account_tag = self._extract_account_tag(ws, header_idx)
        date_seq = {}

        for r in range(header_idx + 1, ws.nrows):
            row_values = ws.row_values(r)
            if not row_values or all(v == '' for v in row_values):
                continue

            row_dict = {}
            for i, h in enumerate(headers):
                if i < len(row_values):
                    row_dict[h] = row_values[i]

            mapped = self.field_mapper.map(row_dict, 'ccb')
            record = self._standardize(mapped, row_dict, account_tag, date_seq)
            if record:
                result.add_record(record, {'channel': 'ccb', 'raw': row_dict})

        return result

    def _standardize(self, mapped: dict, raw: dict,
                     account_tag: str, date_seq: dict) -> dict | None:
        trade_time_raw = mapped.get('trade_time_raw')
        if not trade_time_raw:
            return None

        if isinstance(trade_time_raw, float):
            from xlrd import xldate_as_datetime
            import datetime
            try:
                datemode = getattr(self, '_datemode', 0)
                dt = xldate_as_datetime(trade_time_raw, datemode)
                trade_time_raw = dt.strftime('%Y%m%d')
            except Exception:
                trade_time_raw = str(int(trade_time_raw))

        trade_time = self.time_normalizer.normalize(
            str(trade_time_raw).strip(), 'ccb'
        )

        amount_result = self.amount_normalizer.normalize(
            mapped.get('amount_raw'), channel='ccb'
        )

        if amount_result['amount_cents'] == 0:
            return None

        date_key = trade_time[:10].replace('-', '')
        date_seq[date_key] = date_seq.get(date_key, 0) + 1
        channel_trade_no = f"CCB_{account_tag}_{date_key}_{date_seq[date_key]:04d}"

        trade_type_raw = mapped.get('trade_type_raw', '')
        trade_type = trade_type_raw
        if self.enum_mapper:
            trade_type = self.enum_mapper.map_trade_type(
                trade_type_raw, 'ccb'
            )

        counterparty_raw = mapped.get('counterparty_raw', '')
        counterparty = self._parse_counterparty(counterparty_raw)

        product_desc = mapped.get('product_desc', '')
        if product_desc:
            product_desc = str(product_desc).strip()

        return {
            'channel': 'ccb',
            'trade_time': trade_time,
            'trade_type': trade_type,
            'direction': amount_result['direction'],
            'amount_cents': amount_result['amount_cents'],
            'counterparty': counterparty,
            'product_desc': product_desc,
            'payment_method': '',
            'status': '',
            'channel_trade_no': channel_trade_no,
            'remark': '',
        }

    def _parse_counterparty(self, raw: str) -> str:
        if not raw:
            return ''
        raw = str(raw).strip()
        if '/' in raw:
            parts = raw.split('/')
            return parts[-1].strip() if parts else raw
        return raw

    def _find_header(self, ws) -> int:
        for r in range(min(ws.nrows, 10)):
            row_strs = [str(ws.cell_value(r, c)).strip()
                        for c in range(ws.ncols)]
            match_count = sum(1 for kw in self.HEADER_KEYWORDS
                              if kw in row_strs)
            if match_count >= 3:
                return r
        return -1

    def _extract_account_tag(self, ws, header_idx: int) -> str:
        for r in range(min(header_idx, 5)):
            for c in range(ws.ncols):
                val = str(ws.cell_value(r, c)).strip()
                if '账号' in val or '账户' in val:
                    for c2 in range(c + 1, ws.ncols):
                        v = str(ws.cell_value(r, c2)).strip()
                        if v and v != '账号' and v != '账户':
                            digits = re.sub(r'\D', '', v)
                            if len(digits) >= 4:
                                return digits[-4:]
                            return v
        return '0000'

    def _parse_pdf(self, file_path: str) -> ParseResult:
        """解析建行 PDF 账单（使用 pdfplumber 提取表格）"""
        result = ParseResult()
        try:
            import pdfplumber
        except ImportError:
            result.errors.append('缺少 pdfplumber 库，请安装: pip install pdfplumber')
            return result

        try:
            all_rows = []
            account_tag = '0000'
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text() or ''
                    tag_match = re.search(r'账号[：:]\s*(\S+)', text)
                    if tag_match:
                        digits = re.sub(r'\D', '', tag_match.group(1))
                        if len(digits) >= 4:
                            account_tag = digits[-4:]

                    tables = page.extract_tables()
                    for table in tables:
                        for row in table:
                            if row and any(cell and str(cell).strip() for cell in row):
                                all_rows.append([str(c).strip() if c else '' for c in row])

            if not all_rows:
                result.errors.append('PDF 中未提取到表格数据')
                return result

            header_idx = -1
            for i, row in enumerate(all_rows):
                match_count = sum(1 for kw in self.HEADER_KEYWORDS
                                  if any(kw in str(cell) for cell in row))
                if match_count >= 3:
                    header_idx = i
                    break

            if header_idx < 0:
                result.errors.append('PDF 中未找到表头行')
                return result

            headers = all_rows[header_idx]
            date_seq = {}
            result.total = len(all_rows) - header_idx - 1

            for row in all_rows[header_idx + 1:]:
                if not row or all(v == '' for v in row):
                    continue

                row_dict = {}
                for i, h in enumerate(headers):
                    if i < len(row):
                        row_dict[h] = row[i]

                mapped = self.field_mapper.map(row_dict, 'ccb')
                record = self._standardize(mapped, row_dict, account_tag, date_seq)
                if record:
                    result.add_record(record, {'channel': 'ccb', 'raw': row_dict})

        except Exception as e:
            result.errors.append(f'PDF 解析失败: {e}')

        return result