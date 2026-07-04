"""
账户标识提取器 —— 从账单文件/源数据中提取账户标识信息
"""
import os
import re
import openpyxl


class AccountExtractor:
    """从各渠道账单中提取账户标识"""

    # ─── 微信账户提取 ─────────────────────────────────

    def extract_wechat_account_info(self, file_path: str) -> dict:
        """
        从微信账单元信息中提取账户标识
        返回: { 'nickname': '微信昵称', 'accounts': [{'tag': '账户标识', 'name': '账户名', 'payment_method': '支付方式'}] }
        """
        nickname = None
        accounts = []

        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.xlsx':
            nickname = self._extract_wechat_nickname_xlsx(file_path)
        elif ext == '.csv':
            nickname = self._extract_wechat_nickname_csv(file_path)

        # 从账单数据中提取所有支付方式
        payment_methods = self._extract_wechat_payment_methods(file_path)

        for pm in payment_methods:
            # 提取银行卡尾号（如"招商银行(1234)"）
            card_suffix = self._extract_card_suffix(pm)

            if card_suffix:
                tag = f"wechat-{nickname}-{card_suffix}"
                name = f"微信-{nickname}-{pm}"
            else:
                # 非银行卡支付（零钱、零钱通等）
                tag = f"wechat-{nickname}-{pm}"
                name = f"微信-{nickname}-{pm}"

            accounts.append({
                'tag': tag,
                'name': name,
                'payment_method': pm,
            })

        return {
            'nickname': nickname,
            'accounts': accounts,
        }

    def _extract_wechat_nickname_xlsx(self, file_path: str) -> str:
        """从xlsx元信息提取微信昵称"""
        try:
            wb = openpyxl.load_workbook(file_path, read_only=True)
            ws = wb.active
            # 第1行: "微信昵称：[风]"
            row1 = list(ws.iter_rows(min_row=2, max_row=2, values_only=True))[0]
            wb.close()

            if row1 and row1[0]:
                text = str(row1[0])
                match = re.search(r'微信昵称：\[([^\]]+)\]', text)
                if match:
                    return match.group(1)
        except Exception:
            pass
        return '未知用户'

    def _extract_wechat_nickname_csv(self, file_path: str) -> str:
        """从csv元信息提取微信昵称"""
        for encoding in ('utf-8-sig', 'gbk', 'utf-8'):
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    lines = f.readlines()
                    for line in lines[:5]:
                        match = re.search(r'微信昵称：\[([^\]]+)\]', line)
                        if match:
                            return match.group(1)
            except (UnicodeDecodeError, UnicodeError):
                continue
        return '未知用户'

    def _extract_wechat_payment_methods(self, file_path: str) -> list[str]:
        """从微信账单数据中提取所有支付方式"""
        payment_methods = set()
        ext = os.path.splitext(file_path)[1].lower()

        try:
            if ext == '.xlsx':
                wb = openpyxl.load_workbook(file_path, read_only=True)
                ws = wb.active
                for i, row in enumerate(ws.iter_rows(values_only=True)):
                    if i < 17:  # 跳过元信息和表头
                        continue
                    if row and len(row) >= 7:
                        pm = row[6]  # 支付方式列
                        if pm:
                            payment_methods.add(str(pm).strip())
                wb.close()
            elif ext == '.csv':
                for encoding in ('utf-8-sig', 'gbk', 'utf-8'):
                    try:
                        with open(file_path, 'r', encoding=encoding) as f:
                            lines = f.readlines()
                            for line in lines[17:]:  # 跳过元信息和表头
                                parts = self._split_csv_line(line.strip())
                                if len(parts) >= 7:
                                    pm = parts[6]
                                    if pm:
                                        payment_methods.add(pm.strip())
                        break
                    except (UnicodeDecodeError, UnicodeError):
                        continue
        except Exception:
            pass

        return list(payment_methods)

    # ─── 支付宝账户提取 ─────────────────────────────────

    def extract_alipay_account_info(self, file_path: str) -> dict:
        """
        从支付宝账单中提取账户标识
        返回: { 'accounts': [{'tag': '账户标识', 'name': '账户名', 'payment_method': '支付方式'}] }
        """
        accounts = []
        payment_methods = self._extract_alipay_payment_methods(file_path)

        for pm in payment_methods:
            # 提取银行卡尾号（如"建设银行储蓄卡(0480)"）
            card_suffix = self._extract_card_suffix(pm)

            if card_suffix:
                tag = f"alipay-{card_suffix}-{self._clean_payment_method(pm)}"
                name = f"支付宝-{pm}"
            elif '余额' in pm:
                tag = f"alipay-余额-{pm}"
                name = f"支付宝-{pm}"
            else:
                tag = f"alipay-{pm}"
                name = f"支付宝-{pm}"

            accounts.append({
                'tag': tag,
                'name': name,
                'payment_method': pm,
            })

        return {'accounts': accounts}

    def _extract_alipay_payment_methods(self, file_path: str) -> list[str]:
        """从支付宝账单数据中提取所有支付方式"""
        payment_methods = set()
        ext = os.path.splitext(file_path)[1].lower()

        try:
            if ext == '.csv':
                for encoding in ('gbk', 'utf-8-sig', 'utf-8', 'gb18030'):
                    try:
                        with open(file_path, 'r', encoding=encoding) as f:
                            lines = f.readlines()
                            header_idx = -1
                            for i, line in enumerate(lines):
                                if '交易时间' in line and '交易分类' in line:
                                    header_idx = i
                                    break
                            if header_idx >= 0:
                                for line in lines[header_idx + 1:]:
                                    parts = self._split_csv_line(line.strip())
                                    if len(parts) >= 8:
                                        pm = parts[7]  # 收/付款方式列
                                        if pm:
                                            payment_methods.add(pm.strip())
                        break
                    except (UnicodeDecodeError, UnicodeError):
                        continue
            elif ext == '.xlsx':
                wb = openpyxl.load_workbook(file_path, read_only=True)
                ws = wb.active
                header_idx = -1
                for i, row in enumerate(ws.iter_rows(values_only=True)):
                    if row and '交易时间' in str(row[0] or ''):
                        header_idx = i
                        break
                if header_idx >= 0:
                    for row in list(ws.iter_rows(min_row=header_idx + 2, values_only=True)):
                        if row and len(row) >= 8:
                            pm = row[7]
                            if pm:
                                payment_methods.add(str(pm).strip())
                wb.close()
        except Exception:
            pass

        return list(payment_methods)

    # ─── 建行账户提取 ─────────────────────────────────

    def extract_ccb_account_info(self, file_path: str) -> dict:
        """
        从建行账单中提取账户标识
        - xls: 从元信息行提取账号后4位
        - pdf: 从页面文本提取账号后4位
        """
        ext = os.path.splitext(file_path)[1].lower()
        account_tag = None

        if ext == '.xls':
            account_tag = self._extract_ccb_tag_xls(file_path)
        elif ext == '.pdf':
            account_tag = self._extract_ccb_tag_pdf(file_path)

        if account_tag:
            return {
                'accounts': [{
                    'tag': f'ccb-{account_tag}',
                    'name': f'建行卡({account_tag})',
                    'payment_method': '',
                }],
                'need_manual_assign': False,
            }

        return {
            'accounts': [],
            'need_manual_assign': True,
        }

    def _extract_ccb_tag_xls(self, file_path: str) -> str:
        try:
            import xlrd
            wb = xlrd.open_workbook(file_path)
            ws = wb.sheet_by_index(0)
            for r in range(min(ws.nrows, 5)):
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
        except Exception:
            pass
        return None

    def _extract_ccb_tag_pdf(self, file_path: str) -> str:
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text() or ''
                    match = re.search(r'账号[：:]\s*(\S+)', text)
                    if match:
                        digits = re.sub(r'\D', '', match.group(1))
                        if len(digits) >= 4:
                            return digits[-4:]
        except Exception:
            pass
        return None

    # ─── 通用辅助 ─────────────────────────────────

    def _extract_card_suffix(self, payment_method: str) -> str:
        """从支付方式中提取银行卡尾号（如(0480)）"""
        match = re.search(r'\(([0-9]{4})\)', payment_method)
        if match:
            return match.group(1)
        return ''

    def _clean_payment_method(self, payment_method: str) -> str:
        """清理支付方式名称，移除括号内容"""
        return re.sub(r'\([^)]*\)', '', payment_method).strip()

    def _split_csv_line(self, line: str) -> list[str]:
        """解析CSV行"""
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

    # ─── 统一入口 ─────────────────────────────────

    def extract(self, channel: str, file_path: str) -> dict:
        """根据渠道提取账户信息"""
        if channel == 'wechat':
            return self.extract_wechat_account_info(file_path)
        elif channel == 'alipay':
            return self.extract_alipay_account_info(file_path)
        elif channel == 'ccb':
            return self.extract_ccb_account_info(file_path)
        return {'accounts': []}