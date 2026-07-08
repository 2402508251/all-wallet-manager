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
    INSTANT_THRESHOLD_MINUTES = 5
    CROSS_BANK_THRESHOLD_HOURS = 24

    def __init__(self, dal: DAL):
        self.dal = dal

    def auto_pair_strong(self, record: dict) -> dict | None:
        channel_trade_no = record.get('channel_trade_no', '')
        remark = record.get('remark', '')
        bill_id = record.get('id')
        if not bill_id:
            return None

        search_text = f"{channel_trade_no} {remark}"

        direction = record.get('direction', '')
        opposite_dir = 'income' if direction == 'expense' else 'expense'

        candidates = self.dal.fetch_all(
            "SELECT ub.* FROM unified_bills ub "
            "JOIN bill_accounting ba ON ub.id = ba.bill_id "
            "WHERE ub.direction = ? AND ub.amount_cents = ? "
            "AND ub.is_deleted = 0 AND ub.id != ? "
            "AND (ba.transfer_link_id IS NULL OR ba.transfer_link_id = '') "
            "AND ub.trade_type NOT IN ('fee', 'repayment_mirror')",
            (opposite_dir, record.get('amount_cents', 0), bill_id),
        )

        for candidate in candidates:
            if self._is_rejected_pair(bill_id, candidate['id']):
                continue
            candidate_no = candidate['channel_trade_no'] or ''
            candidate_remark = candidate['remark'] or ''
            candidate_text = f"{candidate_no} {candidate_remark}"

            if channel_trade_no and channel_trade_no in candidate_text:
                return self._create_pair(bill_id, candidate['id'])
            if remark and remark in candidate_text:
                return self._create_pair(bill_id, candidate['id'])

        return None

    def auto_pair_weak_candidates(self, record: dict) -> list[dict]:
        """
        弱匹配候选搜索：
        条件：金额相同 + 方向相反 + 时间差满足规则 + 对方名称语义相似
        即使只有一条候选也需用户确认，不自动配对
        """
        bill_id = record.get('id')
        if not bill_id:
            return []

        direction = record.get('direction', '')
        opposite_dir = 'income' if direction == 'expense' else 'expense'
        channel = record.get('channel', '')

        candidates = self.dal.fetch_all(
            "SELECT ub.* FROM unified_bills ub "
            "JOIN bill_accounting ba ON ub.id = ba.bill_id "
            "WHERE ub.direction = ? AND ub.amount_cents = ? "
            "AND ub.is_deleted = 0 AND ub.id != ? "
            "AND (ba.transfer_link_id IS NULL OR ba.transfer_link_id = '')",
            (opposite_dir, record.get('amount_cents', 0), bill_id),
        )

        results = []
        threshold_minutes = (
            self.INSTANT_THRESHOLD_MINUTES
            if channel in self.INSTANT_CHANNELS
            else self.CROSS_BANK_THRESHOLD_HOURS * 60
        )

        for candidate in candidates:
            if self._is_rejected_pair(bill_id, candidate['id']):
                continue
            c = dict(candidate)
            try:
                t1 = datetime.fromisoformat(record['trade_time'])
                t2 = datetime.fromisoformat(c['trade_time'])
                diff_minutes = abs((t1 - t2).total_seconds()) / 60
                if diff_minutes > threshold_minutes:
                    continue
            except (ValueError, TypeError):
                continue

            name_a = record.get('counterparty', '') or ''
            name_b = c.get('counterparty', '') or ''
            if not _is_semantically_similar(name_a, name_b):
                continue

            out_record, in_record = self._normalize_pair_records(record, c)
            results.append({
                'out_bill_id': out_record['id'],
                'in_bill_id': in_record['id'],
                'out_bill': out_record,
                'in_bill': in_record,
                'match_reason': 'amount_time_counterparty',
                'match_score': 60,
                'time_diff_minutes': round(diff_minutes, 2),
                'amount_diff_cents': abs((out_record.get('amount_cents') or 0) - (in_record.get('amount_cents') or 0)),
            })

        return results

    def confirm_pair(self, out_id: int, in_id: int,
                     fee_amount: int = 0) -> dict:
        """
        用户确认配对：
        1. 生成 transfer_link_id
        2. 在两条记录的 bill_accounting 中写入 transfer_link_id
        3. 若 fee_amount > 0，调用 generate_fee_record 生成手续费记录
        """
        out_id, in_id = self._normalize_pair_ids(out_id, in_id)
        transfer_link_id = str(uuid.uuid4())

        with self.dal.transaction():
            self.dal.delete(
                'transfer_pair_decisions',
                '(out_bill_id = ? AND in_bill_id = ?) OR (out_bill_id = ? AND in_bill_id = ?)',
                (out_id, in_id, in_id, out_id),
            )
            for bill_id in (out_id, in_id):
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
                'out_id': out_id,
                'in_id': in_id,
            }

            if fee_amount <= 0:
                out_record = self.dal.fetch_one(
                    "SELECT amount_cents FROM unified_bills WHERE id = ?", (out_id,)
                )
                in_record = self.dal.fetch_one(
                    "SELECT amount_cents FROM unified_bills WHERE id = ?", (in_id,)
                )
                if out_record and in_record:
                    diff = out_record['amount_cents'] - in_record['amount_cents']
                    if diff > 0 and diff <= out_record['amount_cents'] * 0.05:
                        fee_amount = diff

            if fee_amount > 0:
                existing_fee = self.dal.fetch_one(
                    "SELECT ub.id FROM unified_bills ub "
                    "JOIN bill_accounting ba ON ub.id = ba.bill_id "
                    "WHERE ub.trade_type = 'fee' AND ba.transfer_link_id = ?",
                    (transfer_link_id,),
                )
                if not existing_fee:
                    out_record = self.dal.fetch_one(
                        "SELECT * FROM unified_bills WHERE id = ?", (out_id,)
                    )
                    if out_record:
                        fee_record = self.generate_fee_record(dict(out_record), fee_amount)
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
        return self.confirm_pair(id1, id2)

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
