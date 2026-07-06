"""
重新解析引擎 —— 基于源账单 + 最新配置重新解析
"""
import json

from core.db import DatabaseManager
from core.config_manager import ConfigManager
from core.snapshot import SnapshotEngine
from core.dal import DAL
from modules.parser.parser_factory import ParserFactory


class ReParser:
    def __init__(self, db_manager: DatabaseManager, config_manager: ConfigManager):
        self.db = db_manager
        self.config = config_manager
        self.dal = DAL(db_manager)
        self.snapshot = SnapshotEngine(db_manager, dal=self.dal)

    def reparse(self, scope: dict) -> dict:
        scope_type = scope.get('type', 'all')
        bill_ids = self._get_scope_bill_ids(scope)

        if not bill_ids:
            return {'success': True, 'updated': 0, 'message': '无符合条件的记录'}

        snapshot_id = self.snapshot.create_snapshot(
            snapshot_type='reparse',
            description=f'重新解析: {scope_type}',
            affected_record_ids=bill_ids,
        )

        updated = 0
        skipped = 0
        errors = []

        for bill_id in bill_ids:
            bill = self.dal.fetch_one(
                "SELECT * FROM unified_bills WHERE id = ?", (bill_id,)
            )
            if not bill:
                continue

            if bill['is_manual_edited']:
                skipped += 1
                continue

            source = self.dal.fetch_one(
                "SELECT * FROM source_bills WHERE bill_id = ?", (bill_id,)
            )
            if not source:
                skipped += 1
                continue

            try:
                raw_data = json.loads(source['raw_json'])
                channel = source['channel']

                parser = ParserFactory.get_parser(channel, self.config)
                mapped = parser.field_mapper.map(raw_data, channel)

                new_trade_type = mapped.get('trade_type_raw', '')
                if parser.enum_mapper:
                    new_trade_type = parser.enum_mapper.map_trade_type(
                        new_trade_type, channel,
                        payment_method=mapped.get('payment_method'),
                    )

                new_trade_time = parser.time_normalizer.normalize(
                    mapped.get('trade_time_raw'), channel
                )

                amount_result = parser.amount_normalizer.normalize(
                    mapped.get('amount_raw'),
                    direction_raw=mapped.get('direction_raw'),
                    channel=channel,
                )

                changes = {}
                old_values = {}

                if bill['trade_type'] != new_trade_type:
                    old_values['trade_type'] = bill['trade_type']
                    changes['trade_type'] = new_trade_type

                if bill['direction'] != amount_result['direction']:
                    old_values['direction'] = bill['direction']
                    changes['direction'] = amount_result['direction']

                if bill['amount_cents'] != amount_result['amount_cents']:
                    old_values['amount_cents'] = bill['amount_cents']
                    changes['amount_cents'] = amount_result['amount_cents']

                if changes:
                    now = self._now()
                    changes['updated_at'] = now
                    self.dal.update(
                        'unified_bills',
                        changes,
                        'id = ?',
                        (bill_id,),
                    )

                    for field, new_val in changes.items():
                        if field == 'updated_at':
                            continue
                        self.snapshot.record_changes(
                            snapshot_id, bill_id, 'unified_bills',
                            {field: (old_values.get(field), new_val)},
                        )

                    updated += 1

            except Exception as e:
                errors.append(f'bill#{bill_id}: {e}')

        return {
            'success': True,
            'snapshot_id': snapshot_id,
            'updated': updated,
            'skipped': skipped,
            'errors': errors,
        }

    def _get_scope_bill_ids(self, scope: dict) -> list[int]:
        scope_type = scope.get('type', 'all')
        base_condition = "is_deleted = 0 AND is_system = 0"

        if scope_type == 'all':
            rows = self.dal.fetch_all(
                f"SELECT id FROM unified_bills WHERE {base_condition}"
            )
        elif scope_type == 'batch':
            batch_id = scope.get('batch_id', '')
            rows = self.dal.fetch_all(
                f"SELECT id FROM unified_bills WHERE batch_id = ? AND {base_condition}",
                (batch_id,),
            )
        elif scope_type == 'channel':
            channel = scope.get('channel', '')
            rows = self.dal.fetch_all(
                f"SELECT id FROM unified_bills WHERE channel = ? AND {base_condition}",
                (channel,),
            )
        elif scope_type == 'time_range':
            start = scope.get('start_time', '')
            end = scope.get('end_time', '')
            rows = self.dal.fetch_all(
                f"SELECT id FROM unified_bills WHERE trade_time >= ? AND trade_time <= ? AND {base_condition}",
                (start, end),
            )
        elif scope_type == 'bill_ids':
            bill_ids = scope.get('bill_ids', [])
            if not bill_ids:
                return []
            placeholders = ', '.join(['?' for _ in bill_ids])
            rows = self.dal.fetch_all(
                f"SELECT id FROM unified_bills WHERE id IN ({placeholders}) AND {base_condition}",
                bill_ids,
            )
        else:
            rows = []

        return [r['id'] for r in rows]

    def _now(self) -> str:
        from datetime import datetime
        return datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')