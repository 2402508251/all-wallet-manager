"""
资产账户互转配对 —— 自动配对转出/转入记录，处理强匹配与弱匹配
"""
import uuid
from datetime import datetime

from core.dal import DAL


def _levenshtein_distance(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


def _strip_parentheses(s: str) -> str:
    import re
    return re.sub(r'[（(].*?[）)]', '', s).strip()


def _is_semantically_similar(name_a: str, name_b: str) -> bool:
    if not name_a or not name_b:
        return False

    if name_a in name_b or name_b in name_a:
        return True

    stripped_a = _strip_parentheses(name_a)
    stripped_b = _strip_parentheses(name_b)
    if stripped_a and stripped_b and stripped_a == stripped_b:
        return True

    dist = _levenshtein_distance(name_a, name_b)
    min_len = min(len(name_a), len(name_b))
    if min_len <= 2:
        return False
    threshold = max(1, int(min_len * 0.3))
    if dist <= threshold:
        return True

    return False


class TransferPairer:
    INSTANT_CHANNELS = {'wechat', 'alipay'}
    DEFAULT_CONFIG = {
        'strong_instant_minutes': 5,
        'strong_other_minutes': 120,
        'weak_instant_minutes': 10,
        'weak_other_minutes': 120,
        'fee_ratio_limit': 0.05,
    }

    def __init__(self, dal: DAL, config: dict | None = None):
        self.dal = dal
        self.config = config or self.DEFAULT_CONFIG

    @property
    def STRONG_INSTANT_MINUTES(self):
        return self.config.get('strong_instant_minutes', 5)

    @property
    def STRONG_OTHER_MINUTES(self):
        return self.config.get('strong_other_minutes', 120)

    @property
    def WEAK_INSTANT_MINUTES(self):
        return self.config.get('weak_instant_minutes', 10)

    @property
    def WEAK_OTHER_MINUTES(self):
        return self.config.get('weak_other_minutes', 120)

    @property
    def FEE_RATIO_LIMIT(self):
        return self.config.get('fee_ratio_limit', 0.05)

    def auto_pair_strong(self, record: dict) -> dict | None:
        bill_id = record.get('id')
        if not bill_id:
            return None

        current_ctx = self._load_pair_bill_context(bill_id)
        if not current_ctx or not self._is_transfer_context(current_ctx):
            return None
        if current_ctx.get('transfer_link_id'):
            return None

        expected_trade_type = 'transfer_in' if current_ctx['trade_type'] == 'transfer_out' else 'transfer_out'
        expected_direction = 'income' if current_ctx['direction'] == 'expense' else 'expense'
        candidates = self.dal.fetch_all(
            "SELECT ub.id FROM unified_bills ub "
            "JOIN bill_accounting ba ON ub.id = ba.bill_id "
            "JOIN accounts a ON ub.account_id = a.id "
            "WHERE ub.direction = ? AND ub.trade_type = ? AND ub.amount_cents = ? "
            "AND ub.account_id IS NOT NULL AND ub.is_deleted = 0 AND ub.id != ? "
            "AND (ba.transfer_link_id IS NULL OR ba.transfer_link_id = '')",
            (expected_direction, expected_trade_type, current_ctx.get('amount_cents', 0), bill_id),
        )

        channel_trade_no = str(current_ctx.get('channel_trade_no') or '')
        remark = str(current_ctx.get('remark') or '')

        for candidate in candidates:
            candidate_ctx = self._load_pair_bill_context(candidate['id'])
            if not candidate_ctx:
                continue
            out_ctx, in_ctx = self._normalize_pair_contexts(current_ctx, candidate_ctx)
            if self._is_rejected_pair(out_ctx['id'], in_ctx['id']):
                continue
            valid, _ = self._validate_pair(out_ctx, in_ctx, 'strong')
            if not valid:
                continue

            candidate_no = str(candidate_ctx.get('channel_trade_no') or '')
            candidate_remark = str(candidate_ctx.get('remark') or '')
            candidate_text = f"{candidate_no} {candidate_remark}"
            if channel_trade_no and channel_trade_no in candidate_text:
                return self.confirm_pair(out_ctx['id'], in_ctx['id'], mode='strong')
            if remark and len(remark) >= 4 and remark in candidate_text:
                return self.confirm_pair(out_ctx['id'], in_ctx['id'], mode='strong')

        return None

    def auto_pair_weak_candidates(self, record: dict) -> list[dict]:
        """
        弱匹配候选搜索：
        条件：有效内部账户 + 转出/转入成对 + 金额相同 + 时间差满足规则 + 对方名称语义相似
        即使只有一条候选也需用户确认，不自动配对
        """
        bill_id = record.get('id')
        if not bill_id:
            return []

        current_ctx = self._load_pair_bill_context(bill_id)
        if not current_ctx or not self._is_transfer_context(current_ctx):
            return []
        if current_ctx.get('transfer_link_id'):
            return []

        expected_trade_type = 'transfer_in' if current_ctx['trade_type'] == 'transfer_out' else 'transfer_out'
        expected_direction = 'income' if current_ctx['direction'] == 'expense' else 'expense'
        candidates = self.dal.fetch_all(
            "SELECT ub.id FROM unified_bills ub "
            "JOIN bill_accounting ba ON ub.id = ba.bill_id "
            "JOIN accounts a ON ub.account_id = a.id "
            "WHERE ub.direction = ? AND ub.trade_type = ? AND ub.amount_cents = ? "
            "AND ub.account_id IS NOT NULL AND ub.is_deleted = 0 AND ub.id != ? "
            "AND (ba.transfer_link_id IS NULL OR ba.transfer_link_id = '')",
            (expected_direction, expected_trade_type, current_ctx.get('amount_cents', 0), bill_id),
        )

        results = []
        for candidate in candidates:
            candidate_ctx = self._load_pair_bill_context(candidate['id'])
            if not candidate_ctx:
                continue
            out_ctx, in_ctx = self._normalize_pair_contexts(current_ctx, candidate_ctx)
            if self._is_rejected_pair(out_ctx['id'], in_ctx['id']):
                continue

            valid, _ = self._validate_pair(out_ctx, in_ctx, 'weak')
            if not valid:
                continue

            name_a = current_ctx.get('counterparty', '') or ''
            name_b = candidate_ctx.get('counterparty', '') or ''
            if not _is_semantically_similar(name_a, name_b):
                continue

            diff_minutes = self._time_diff_minutes(out_ctx, in_ctx)
            results.append({
                'out_bill_id': out_ctx['id'],
                'in_bill_id': in_ctx['id'],
                'out_bill': self._bill_payload(out_ctx),
                'in_bill': self._bill_payload(in_ctx),
                'out_account_id': out_ctx.get('account_id'),
                'out_account_name': out_ctx.get('effective_account_name') or out_ctx.get('account_name'),
                'in_account_id': in_ctx.get('account_id'),
                'in_account_name': in_ctx.get('effective_account_name') or in_ctx.get('account_name'),
                'out_counterparty': out_ctx.get('counterparty'),
                'in_counterparty': in_ctx.get('counterparty'),
                'match_reason': 'amount_time_counterparty_account',
                'match_score': 80,
                'time_diff_minutes': round(diff_minutes, 2),
                'amount_diff_cents': abs((out_ctx.get('amount_cents') or 0) - (in_ctx.get('amount_cents') or 0)),
            })

        return results

    def confirm_pair(self, out_id: int, in_id: int,
                     fee_amount: int = 0, mode: str = 'weak') -> dict:
        """
        用户确认配对：
        1. 校验两条记录是有效内部账户转出/转入
        2. 生成 transfer_link_id
        3. 在两条记录的 bill_accounting 中写入 transfer_link_id
        4. 若 fee_amount > 0，调用 generate_fee_record 生成手续费记录
        """
        out_ctx = self._load_pair_bill_context(out_id)
        in_ctx = self._load_pair_bill_context(in_id)
        if out_ctx and in_ctx:
            out_ctx, in_ctx = self._normalize_pair_contexts(out_ctx, in_ctx)
        valid, message = self._validate_pair(out_ctx, in_ctx, mode)
        if not valid:
            return {'success': False, 'message': message}

        auto_fee_amount = self._auto_fee_amount(out_ctx, in_ctx)
        if fee_amount <= 0:
            fee_amount = auto_fee_amount
        elif fee_amount != auto_fee_amount:
            return {'success': False, 'message': '手续费金额不符合转账差额'}

        transfer_link_id = str(uuid.uuid4())
        with self.dal.transaction():
            occupied = self.dal.fetch_all(
                "SELECT bill_id, transfer_link_id FROM bill_accounting "
                "WHERE bill_id IN (?, ?) AND transfer_link_id IS NOT NULL AND transfer_link_id != ''",
                (out_ctx['id'], in_ctx['id']),
            )
            if occupied:
                return {'success': False, 'message': '账单已存在转账配对'}

            self.dal.delete(
                'transfer_pair_decisions',
                '(out_bill_id = ? AND in_bill_id = ?) OR (out_bill_id = ? AND in_bill_id = ?)',
                (out_ctx['id'], in_ctx['id'], in_ctx['id'], out_ctx['id']),
            )
            for bill_id in (out_ctx['id'], in_ctx['id']):
                existing = self.dal.fetch_one(
                    "SELECT * FROM bill_accounting WHERE bill_id = ?", (bill_id,)
                )
                if existing:
                    self.dal.update(
                        'bill_accounting',
                        {'transfer_link_id': transfer_link_id},
                        'bill_id = ?',
                        (bill_id,),
                    )
                else:
                    self.dal.insert('bill_accounting', {
                        'bill_id': bill_id,
                        'transfer_link_id': transfer_link_id,
                    })

            result = {
                'success': True,
                'transfer_link_id': transfer_link_id,
                'out_id': out_ctx['id'],
                'in_id': in_ctx['id'],
            }

            if fee_amount > 0:
                existing_fee = self.dal.fetch_one(
                    "SELECT ub.id FROM unified_bills ub "
                    "JOIN bill_accounting ba ON ub.id = ba.bill_id "
                    "WHERE ub.trade_type = 'fee' AND ba.transfer_link_id = ?",
                    (transfer_link_id,),
                )
                if not existing_fee:
                    fee_record = self.generate_fee_record(out_ctx, fee_amount)
                    fee_record['is_system'] = 1
                    fee_id = self.dal.insert('unified_bills', fee_record)
                    self.dal.insert('bill_accounting', {
                        'bill_id': fee_id,
                        'transfer_link_id': transfer_link_id,
                    })
                    result['fee_bill_id'] = fee_id

        return result

    def reject_pair(self, out_id: int, in_id: int) -> dict:
        out_id, in_id = self._normalize_pair_ids(out_id, in_id)
        self.dal.insert_or_ignore('transfer_pair_decisions', {
            'out_bill_id': out_id,
            'in_bill_id': in_id,
            'decision': 'rejected',
        })
        return {'success': True, 'out_id': out_id, 'in_id': in_id}

    def generate_fee_record(self, transfer_record: dict, fee_amount: int) -> dict:
        fee_record = {
            'channel': transfer_record.get('channel', ''),
            'trade_time': transfer_record.get('trade_time', ''),
            'trade_type': 'fee',
            'direction': 'expense',
            'amount_cents': fee_amount,
            'counterparty': transfer_record.get('counterparty', ''),
            'product_desc': '转账手续费',
            'payment_method': '',
            'status': '',
            'channel_trade_no': f"{transfer_record.get('channel_trade_no', '')}_FEE",
            'remark': '',
            'batch_id': transfer_record.get('batch_id', ''),
            'account_id': transfer_record.get('account_id'),
            'role_id': transfer_record.get('role_id'),
            'assign_status': 'assigned' if transfer_record.get('role_id') else 'pending',
        }
        return fee_record

    def _create_pair(self, id1: int, id2: int) -> dict:
        return self.confirm_pair(id1, id2, mode='strong')

    def _load_pair_bill_context(self, bill_id: int) -> dict | None:
        row = self.dal.fetch_one(
            "SELECT ub.*, ba.transfer_link_id, a.account_name, a.merged_into_account_id "
            "FROM unified_bills ub "
            "LEFT JOIN bill_accounting ba ON ub.id = ba.bill_id "
            "LEFT JOIN accounts a ON ub.account_id = a.id "
            "WHERE ub.id = ?",
            (bill_id,),
        )
        if not row:
            return None
        ctx = dict(row)
        if ctx.get('account_id') and not ctx.get('account_name'):
            ctx['account_missing'] = True
            return ctx
        effective_id, effective_name = self._effective_account(ctx)
        ctx['effective_account_id'] = effective_id
        ctx['effective_account_name'] = effective_name
        return ctx

    def _effective_account(self, ctx: dict) -> tuple[int | None, str | None]:
        account_id = ctx.get('account_id')
        account_name = ctx.get('account_name')
        merged_into = ctx.get('merged_into_account_id')
        if merged_into:
            target = self.dal.fetch_one(
                "SELECT id, account_name FROM accounts WHERE id = ?", (merged_into,)
            )
            if target:
                return target['id'], target['account_name']
        return account_id, account_name

    def _is_transfer_context(self, ctx: dict) -> bool:
        return (
            ctx.get('trade_type') in ('transfer_out', 'transfer_in')
            and ctx.get('direction') in ('expense', 'income')
        )

    def _validate_transfer_bill(self, ctx: dict | None, expected_trade_type: str,
                                expected_direction: str) -> tuple[bool, str]:
        if not ctx:
            return False, '账单不存在'
        if ctx.get('is_deleted'):
            return False, '账单已删除'
        if ctx.get('trade_type') != expected_trade_type:
            return False, '两条账单不是转出/转入成对'
        if ctx.get('direction') != expected_direction:
            return False, '两条账单不是支出/收入成对'
        if (ctx.get('amount_cents') or 0) <= 0:
            return False, '转账金额无效'
        if not ctx.get('account_id') or ctx.get('account_missing'):
            return False, '账单未绑定有效账户'
        if not ctx.get('effective_account_id'):
            return False, '账单未绑定有效账户'
        if ctx.get('transfer_link_id'):
            return False, '账单已存在转账配对'
        return True, ''

    def _validate_pair(self, out_ctx: dict | None, in_ctx: dict | None,
                       mode: str) -> tuple[bool, str]:
        ok, message = self._validate_transfer_bill(out_ctx, 'transfer_out', 'expense')
        if not ok:
            return False, f'转出账单{message}'
        ok, message = self._validate_transfer_bill(in_ctx, 'transfer_in', 'income')
        if not ok:
            return False, f'转入账单{message}'
        if out_ctx['id'] == in_ctx['id']:
            return False, '不能配对同一条账单'
        if out_ctx.get('effective_account_id') == in_ctx.get('effective_account_id'):
            return False, '两条账单归属于同一账户，不能配对'

        diff_minutes = self._time_diff_minutes(out_ctx, in_ctx)
        if diff_minutes is None:
            return False, '账单时间无效'
        if diff_minutes > self._pair_window_minutes(out_ctx, in_ctx, mode):
            return False, '两条账单时间差超过允许范围'

        diff = self._amount_diff(out_ctx, in_ctx)
        if diff < 0:
            return False, '转入金额不能大于转出金额'
        if diff > 0 and diff > out_ctx['amount_cents'] * self.FEE_RATIO_LIMIT:
            return False, '转账差额超过手续费允许范围'
        return True, ''

    def _time_diff_minutes(self, out_ctx: dict, in_ctx: dict) -> float | None:
        try:
            t1 = datetime.fromisoformat(out_ctx['trade_time'])
            t2 = datetime.fromisoformat(in_ctx['trade_time'])
            return abs((t1 - t2).total_seconds()) / 60
        except (ValueError, TypeError):
            return None

    def _pair_window_minutes(self, out_ctx: dict, in_ctx: dict, mode: str) -> int:
        has_instant_channel = (
            out_ctx.get('channel') in self.INSTANT_CHANNELS
            or in_ctx.get('channel') in self.INSTANT_CHANNELS
        )
        if mode == 'strong':
            return self.STRONG_INSTANT_MINUTES if has_instant_channel else self.STRONG_OTHER_MINUTES
        return self.WEAK_INSTANT_MINUTES if has_instant_channel else self.WEAK_OTHER_MINUTES

    def _amount_diff(self, out_ctx: dict, in_ctx: dict) -> int:
        return (out_ctx.get('amount_cents') or 0) - (in_ctx.get('amount_cents') or 0)

    def _auto_fee_amount(self, out_ctx: dict, in_ctx: dict) -> int:
        diff = self._amount_diff(out_ctx, in_ctx)
        if diff > 0 and diff <= out_ctx['amount_cents'] * self.FEE_RATIO_LIMIT:
            return diff
        return 0

    def _bill_payload(self, ctx: dict) -> dict:
        data = dict(ctx)
        for key in ('transfer_link_id', 'account_missing', 'merged_into_account_id'):
            data.pop(key, None)
        return data

    def _normalize_pair_contexts(self, record_a: dict, record_b: dict) -> tuple[dict, dict]:
        if record_a.get('trade_type') == 'transfer_out' or record_a.get('direction') == 'expense':
            return dict(record_a), dict(record_b)
        return dict(record_b), dict(record_a)

    def _normalize_pair_records(self, record_a: dict, record_b: dict) -> tuple[dict, dict]:
        if record_a.get('direction') == 'expense':
            return dict(record_a), dict(record_b)
        return dict(record_b), dict(record_a)

    def _normalize_pair_ids(self, id1: int, id2: int) -> tuple[int, int]:
        bill1 = self.dal.fetch_one("SELECT id, direction FROM unified_bills WHERE id = ?", (id1,))
        bill2 = self.dal.fetch_one("SELECT id, direction FROM unified_bills WHERE id = ?", (id2,))
        if not bill1 or not bill2:
            return id1, id2
        if bill1.get('direction') == 'expense':
            return id1, id2
        return id2, id1

    def _is_rejected_pair(self, bill_id_1: int, bill_id_2: int) -> bool:
        out_id, in_id = self._normalize_pair_ids(bill_id_1, bill_id_2)
        row = self.dal.fetch_one(
            "SELECT id FROM transfer_pair_decisions WHERE out_bill_id = ? AND in_bill_id = ? AND decision = 'rejected'",
            (out_id, in_id),
        )
        return row is not None