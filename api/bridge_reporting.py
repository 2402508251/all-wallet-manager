"""ApiBridge domain mixin."""
import json
import logging
import os
import uuid
from datetime import datetime, date, timedelta

from core.db_rebuild import rebuild_database
from core.trade_types import VALID_TRADE_TYPES, TRADE_TYPE_LABELS, get_trade_type_label
from modules.accounting.credit_tracker import CreditTracker
from modules.accounting.cross_platform_merger import CrossPlatformMerger
from modules.accounting.transfer_pairer import TransferPairer

from .bridge_base import DateTimeEncoder, audit_log, logger


class ReportingBridgeMixin:
    @staticmethod
    def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
        total_months = year * 12 + (month - 1) + delta
        return total_months // 12, total_months % 12 + 1

    def _month_bounds(self, year: int, month: int) -> tuple[str, str]:
        start = f"{year}-{month:02d}-01T00:00:00+08:00"
        next_year, next_month = self._shift_month(year, month, 1)
        end = f"{next_year}-{next_month:02d}-01T00:00:00+08:00"
        return start, end

    def _custom_bounds(self, start_date: str, end_date: str) -> tuple[str, str]:
        start_dt = datetime.strptime(str(start_date), '%Y-%m-%d')
        end_dt = datetime.strptime(str(end_date), '%Y-%m-%d')
        if end_dt < start_dt:
            start_dt, end_dt = end_dt, start_dt
        end_exclusive = end_dt + timedelta(days=1)
        return (
            start_dt.strftime('%Y-%m-%dT00:00:00+08:00'),
            end_exclusive.strftime('%Y-%m-%dT00:00:00+08:00'),
        )

    def _period_bounds(self, year: int, month: int | None = None, period: str = 'month') -> tuple[str, str]:
        mode = str(period or 'month')
        if mode == 'year':
            return f"{year}-01-01T00:00:00+08:00", f"{year + 1}-01-01T00:00:00+08:00"
        if mode in ('recent12', 'rolling12', 'rolling_12'):
            target_month = int(month or 1)
            start_year, start_month = self._shift_month(year, target_month, -11)
            start, _ = self._month_bounds(start_year, start_month)
            _, end = self._month_bounds(year, target_month)
            return start, end
        return self._month_bounds(year, int(month or 1))

    def _resolve_report_bounds(self, params=None) -> tuple[str, str]:
        p = params or {}
        period = str(p.get('period', 'month') or 'month')
        if period == 'custom':
            return self._custom_bounds(p.get('start_date'), p.get('end_date'))
        year = int(p.get('year'))
        month = p.get('month')
        return self._period_bounds(year, month, period)

    def _resolve_previous_report_bounds(self, params=None, current_start: str | None = None, current_end: str | None = None) -> tuple[str, str]:
        p = params or {}
        period = str(p.get('period', 'month') or 'month')
        if current_start is None or current_end is None:
            current_start, current_end = self._resolve_report_bounds(p)
        days = self._days_between(current_start, current_end)

        if period == 'year':
            year = int(p.get('year'))
            month = p.get('month')
            return self._period_bounds(year - 1, month, 'year')
        if period in ('recent12', 'rolling12', 'rolling_12'):
            year = int(p.get('year'))
            month = p.get('month')
            end_year, end_month = self._shift_month(year, int(month or 1), -12)
            return self._period_bounds(end_year, end_month, 'recent12')
        if period == 'custom':
            return self._shift_bounds(current_start, current_end, -days)

        year = int(p.get('year'))
        month = p.get('month')
        prev_year, prev_month = self._shift_month(year, int(month or 1), -1)
        return self._month_bounds(prev_year, prev_month)

    def _days_between(self, start: str, end: str) -> int:
        start_dt = datetime.strptime(start, '%Y-%m-%dT%H:%M:%S+08:00')
        end_dt = datetime.strptime(end, '%Y-%m-%dT%H:%M:%S+08:00')
        return max((end_dt - start_dt).days, 1)

    def _shift_bounds(self, start: str, end: str, delta_days: int) -> tuple[str, str]:
        start_dt = datetime.strptime(start, '%Y-%m-%dT%H:%M:%S+08:00') + timedelta(days=delta_days)
        end_dt = datetime.strptime(end, '%Y-%m-%dT%H:%M:%S+08:00') + timedelta(days=delta_days)
        return (
            start_dt.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
            end_dt.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
        )

    def _report_conditions(self, start: str, end: str, family_id=None, role_id=None, include_deleted: bool = False) -> tuple[list[str], list]:
        conditions = ["ub.trade_time >= ?", "ub.trade_time < ?"]
        sql_params = [start, end]
        if not include_deleted:
            conditions.insert(0, "ub.is_deleted = 0")
        self._append_report_scope_filters(conditions, sql_params, family_id, role_id)
        return conditions, sql_params

    def _report_where(self, start: str, end: str, family_id=None, role_id=None, hide_internal: bool = False, include_deleted: bool = False) -> tuple[str, list]:
        conditions, sql_params = self._report_conditions(start, end, family_id, role_id, include_deleted=include_deleted)
        self._append_internal_flow_filters(conditions, hide_internal)
        return " AND ".join(conditions), sql_params

    def _fetch_scalar(self, sql: str, params: tuple | list = (), key: str = 'value') -> int:
        row = self.dal.fetch_one(sql, tuple(params))
        if not row:
            return 0
        return row[key] or 0

    def _report_summary_metrics(self, start: str, end: str, family_id=None, role_id=None, hide_internal: bool = False) -> dict:
        base_query = "FROM unified_bills ub"
        where, sql_params = self._report_where(start, end, family_id, role_id, hide_internal=hide_internal)
        raw_where, raw_params = self._report_where(start, end, family_id, role_id, hide_internal=False)

        income = self._fetch_scalar(
            f"SELECT COALESCE(SUM(ub.amount_cents), 0) AS value {base_query} WHERE {where} AND ub.direction = 'income'",
            sql_params,
        )
        expense = self._fetch_scalar(
            f"SELECT COALESCE(SUM(ub.amount_cents), 0) AS value {base_query} "
            f"WHERE {where} AND ub.direction = 'expense' AND ub.trade_type != 'credit_consumption'",
            sql_params,
        )
        credit = self._fetch_scalar(
            f"SELECT COALESCE(SUM(ub.amount_cents), 0) AS value {base_query} "
            f"WHERE {raw_where} AND ub.trade_type = 'credit_consumption'",
            raw_params,
        )
        repayment = self._fetch_scalar(
            f"SELECT COALESCE(SUM(ub.amount_cents), 0) AS value {base_query} "
            f"WHERE {raw_where} AND ub.trade_type = 'repayment'",
            raw_params,
        )
        refund = self._fetch_scalar(
            f"SELECT COALESCE(SUM(ub.amount_cents), 0) AS value {base_query} "
            f"WHERE {where} AND ub.trade_type = 'refund'",
            sql_params,
        )
        bill_count = self._fetch_scalar(
            f"SELECT COUNT(*) AS value {base_query} WHERE {where}",
            sql_params,
        )
        income_count = self._fetch_scalar(
            f"SELECT COUNT(*) AS value {base_query} WHERE {where} AND ub.direction = 'income'",
            sql_params,
        )
        expense_count = self._fetch_scalar(
            f"SELECT COUNT(*) AS value {base_query} WHERE {where} AND ub.direction = 'expense'",
            sql_params,
        )
        refund_count = self._fetch_scalar(
            f"SELECT COUNT(*) AS value {base_query} WHERE {where} AND ub.trade_type = 'refund'",
            sql_params,
        )
        uncategorized_count = self._fetch_scalar(
            f"SELECT COUNT(*) AS value {base_query} "
            f"WHERE {raw_where} AND ub.direction = 'expense' AND ub.category_id IS NULL",
            raw_params,
        )
        return {
            'income': income,
            'expense': expense,
            'credit': credit,
            'repayment': repayment,
            'refund': refund,
            'net': income - expense,
            'bill_count': bill_count,
            'income_count': income_count,
            'expense_count': expense_count,
            'refund_count': refund_count,
            'uncategorized_count': uncategorized_count,
        }

    def _category_dimension_items(self, start: str, end: str, family_id=None, role_id=None, hide_internal: bool = False, direction: str = 'expense', limit: int | None = None) -> list[dict]:
        conditions, sql_params = self._report_conditions(start, end, family_id, role_id)
        self._append_internal_flow_filters(conditions, hide_internal)
        if direction:
            conditions.append("ub.direction = ?")
            sql_params.append(direction)
        where = " AND ".join(conditions)

        limit_sql = ""
        params = list(sql_params)
        if limit:
            limit_sql = " LIMIT ?"
            params.append(limit)

        rows = self.dal.fetch_all(
            "SELECT CAST(ub.category_id AS TEXT) AS item_key, "
            "COALESCE(bc.name, '未分类') AS item_label, "
            "bc.icon AS icon, "
            "COALESCE(SUM(ub.amount_cents), 0) AS total_amount, "
            "COUNT(*) AS count "
            "FROM unified_bills ub "
            "LEFT JOIN bill_categories bc ON ub.category_id = bc.id "
            f"WHERE {where} "
            "GROUP BY ub.category_id "
            "ORDER BY total_amount DESC, count DESC"
            f"{limit_sql}",
            tuple(params),
        )

        items = [dict(r) for r in rows]
        total_amount = sum(item['total_amount'] or 0 for item in items)
        total_count = sum(item['count'] or 0 for item in items)
        result = []
        for item in items:
            amount = item.get('total_amount') or 0
            count = item.get('count') or 0
            result.append({
                'key': item.get('item_key'),
                'label': item.get('item_label'),
                'icon': item.get('icon', ''),
                'total_amount': amount,
                'count': count,
                'ratio': round(amount / total_amount, 4) if total_amount else 0,
                'count_ratio': round(count / total_count, 4) if total_count else 0,
                'avg_amount': round(amount / count) if count else 0,
            })
        return result

    def _query_credit_like_records(self, trade_type: str, params=None) -> list[dict]:
        p = params or {}
        month = p.get('month')
        family_id = p.get('family_id')
        role_id = p.get('role_id')
        conditions = ["ub.is_deleted = 0", "ub.trade_type = ?"]
        sql_params = [trade_type]
        if month:
            year, month_num = [int(v) for v in str(month).split('-')]
            start = f"{year}-{month_num:02d}-01T00:00:00+08:00"
            if month_num == 12:
                end = f"{year + 1}-01-01T00:00:00+08:00"
            else:
                end = f"{year}-{month_num + 1:02d}-01T00:00:00+08:00"
            conditions.extend(["ub.trade_time >= ?", "ub.trade_time < ?"])
            sql_params.extend([start, end])
        self._append_report_scope_filters(conditions, sql_params, family_id, role_id)
        where = " AND ".join(conditions)
        rows = self.dal.fetch_all(
            "SELECT ub.*, ba.transfer_link_id, ba.is_credit, ba.credit_account_id, "
            "ca.account_name AS credit_account_name, a.account_name AS linked_account_name "
            "FROM unified_bills ub "
            "LEFT JOIN bill_accounting ba ON ub.id = ba.bill_id "
            "LEFT JOIN credit_accounts ca ON ba.credit_account_id = ca.id "
            "LEFT JOIN accounts a ON ca.linked_account_id = a.id "
            f"WHERE {where} ORDER BY ub.trade_time DESC",
            tuple(sql_params),
        )
        return [dict(r) for r in rows]

    def _append_report_scope_filters(self, conditions: list, sql_params: list, family_id=None, role_id=None) -> None:
        if family_id:
            conditions.append(
                "EXISTS (SELECT 1 FROM role_families rf WHERE rf.role_id = ub.role_id AND rf.family_id = ?)"
            )
            sql_params.append(family_id)
        if role_id:
            conditions.append("ub.role_id = ?")
            sql_params.append(role_id)

    def _append_internal_flow_filters(self, conditions: list, hide_internal: bool) -> None:
        if hide_internal:
            conditions.append(
                "ub.trade_type NOT IN ('transfer_out', 'transfer_in', 'repayment', 'repayment_mirror')"
            )

    def get_monthly_summary(self, params=None) -> dict:
        p = params or {}
        year = p.get('year')
        month = p.get('month')
        family_id = p.get('family_id')
        role_id = p.get('role_id')
        hide_internal = bool(p.get('hide_internal', False))
        start, end = self._month_bounds(year, month)
        metrics = self._report_summary_metrics(start, end, family_id, role_id, hide_internal=hide_internal)

        return self.ok({
            'income': metrics['income'],
            'expense': metrics['expense'],
            'credit': metrics['credit'],
            'repayment': metrics['repayment'],
        })

    def get_category_distribution(self, params=None) -> dict:
        p = params or {}
        year = p.get('year')
        month = p.get('month')
        family_id = p.get('family_id')
        role_id = p.get('role_id')
        direction = p.get('direction', 'expense')
        hide_internal = bool(p.get('hide_internal', False))
        start = f"{year}-{month:02d}-01T00:00:00+08:00"
        if month == 12:
            end = f"{year + 1}-01-01T00:00:00+08:00"
        else:
            end = f"{year}-{month + 1:02d}-01T00:00:00+08:00"

        conditions = [
            "ub.is_deleted = 0", "ub.trade_time >= ?", "ub.trade_time < ?",
            "ub.direction = ?",
        ]
        sql_params = [start, end, direction]
        self._append_report_scope_filters(conditions, sql_params, family_id, role_id)
        self._append_internal_flow_filters(conditions, hide_internal)

        where = " AND ".join(conditions)

        rows = self.dal.fetch_all(
            f"SELECT bc.name as category_name, bc.icon, "
            f"SUM(ub.amount_cents) as total_amount, COUNT(*) as count "
            f"FROM unified_bills ub "
            f"LEFT JOIN bill_categories bc ON ub.category_id = bc.id "
            f"WHERE {where} "
            f"GROUP BY ub.category_id ORDER BY total_amount DESC",
            tuple(sql_params),
        )

        return self.ok({'categories': [dict(r) for r in rows]})

    def get_trend_data(self, params=None) -> dict:
        p = params or {}
        start_month = p.get('start_month')
        end_month = p.get('end_month')
        family_id = p.get('family_id')
        role_id = p.get('role_id')
        hide_internal = bool(p.get('hide_internal', False))

        start_dt = datetime.strptime(start_month, '%Y-%m')
        end_dt = datetime.strptime(end_month, '%Y-%m')

        months = []
        income_list = []
        expense_list = []

        current = start_dt
        while current <= end_dt:
            year = current.year
            month = current.month
            month_str = current.strftime('%Y-%m')
            month_start, month_end = self._month_bounds(year, month)
            metrics = self._report_summary_metrics(
                month_start,
                month_end,
                family_id,
                role_id,
                hide_internal=hide_internal,
            )

            months.append(month_str)
            income_list.append(metrics['income'])
            expense_list.append(metrics['expense'])

            if month == 12:
                current = current.replace(year=year + 1, month=1)
            else:
                current = current.replace(month=month + 1)

        return self.ok({
            'months': months,
            'income': income_list,
            'expense': expense_list,
        })

    def get_report_overview(self, params=None) -> dict:
        p = params or {}
        period = p.get('period', 'month')
        family_id = p.get('family_id')
        role_id = p.get('role_id')
        hide_internal = bool(p.get('hide_internal', False))

        start, end = self._resolve_report_bounds(p)
        metrics = self._report_summary_metrics(start, end, family_id, role_id, hide_internal=hide_internal)
        days = self._days_between(start, end)

        prev_start, prev_end = self._resolve_previous_report_bounds(p, start, end)

        previous = self._report_summary_metrics(prev_start, prev_end, family_id, role_id, hide_internal=hide_internal)

        def change_ratio(current_value: int, previous_value: int):
            delta = current_value - previous_value
            if previous_value == 0:
                if current_value == 0:
                    return None
                return 1 if current_value > 0 else -1
            return round(delta / abs(previous_value), 4)

        return self.ok({
            'summary': {
                'income': metrics['income'],
                'expense': metrics['expense'],
                'net': metrics['net'],
                'credit': metrics['credit'],
                'repayment': metrics['repayment'],
                'refund': metrics['refund'],
                'avg_daily_expense': round(metrics['expense'] / days) if days else 0,
            },
            'comparison': {
                'income_previous': previous['income'],
                'expense_previous': previous['expense'],
                'net_previous': previous['net'],
                'income_change_ratio': change_ratio(metrics['income'], previous['income']),
                'expense_change_ratio': change_ratio(metrics['expense'], previous['expense']),
                'net_change_ratio': change_ratio(metrics['net'], previous['net']),
            },
            'counts': {
                'bill_count': metrics['bill_count'],
                'income_count': metrics['income_count'],
                'expense_count': metrics['expense_count'],
                'refund_count': metrics['refund_count'],
                'uncategorized_count': metrics['uncategorized_count'],
            },
        })

    def get_report_category_insights(self, params=None) -> dict:
        p = params or {}
        family_id = p.get('family_id')
        role_id = p.get('role_id')
        hide_internal = bool(p.get('hide_internal', False))

        start, end = self._resolve_report_bounds(p)
        prev_start, prev_end = self._resolve_previous_report_bounds(p, start, end)

        current_items = self._category_dimension_items(start, end, family_id, role_id, hide_internal=hide_internal, direction='expense')
        previous_items = self._category_dimension_items(prev_start, prev_end, family_id, role_id, hide_internal=hide_internal, direction='expense')
        previous_map = {str(item.get('key')): item for item in previous_items}

        total_amount = sum(item.get('total_amount') or 0 for item in current_items)
        total_count = sum(item.get('count') or 0 for item in current_items)
        top3_amount = sum((item.get('total_amount') or 0) for item in current_items[:3])

        enriched_items = []
        for item in current_items:
            previous = previous_map.get(str(item.get('key')), {})
            previous_amount = previous.get('total_amount') or 0
            previous_count = previous.get('count') or 0
            amount_delta = (item.get('total_amount') or 0) - previous_amount
            count_delta = (item.get('count') or 0) - previous_count
            amount_change_ratio = None if previous_amount == 0 else round(amount_delta / abs(previous_amount), 4)
            count_change_ratio = None if previous_count == 0 else round(count_delta / abs(previous_count), 4)
            enriched_items.append({
                **item,
                'previous_amount': previous_amount,
                'previous_count': previous_count,
                'amount_delta': amount_delta,
                'count_delta': count_delta,
                'amount_change_ratio': amount_change_ratio,
                'count_change_ratio': count_change_ratio,
            })

        uncategorized = next((item for item in enriched_items if item.get('label') == '未分类'), None)
        top_category = enriched_items[0] if enriched_items else None

        return self.ok({
            'summary': {
                'category_count': len([item for item in enriched_items if item.get('label') != '未分类']),
                'total_amount': total_amount,
                'total_count': total_count,
                'top_category_label': top_category.get('label') if top_category else '',
                'top_category_amount': top_category.get('total_amount') if top_category else 0,
                'top3_ratio': round(top3_amount / total_amount, 4) if total_amount else 0,
                'uncategorized_amount': uncategorized.get('total_amount') if uncategorized else 0,
                'uncategorized_count': uncategorized.get('count') if uncategorized else 0,
                'uncategorized_ratio': uncategorized.get('ratio') if uncategorized else 0,
            },
            'items': enriched_items,
        })

    def get_report_dimension_stats(self, params=None) -> dict:
        p = params or {}
        family_id = p.get('family_id')
        role_id = p.get('role_id')
        hide_internal = bool(p.get('hide_internal', False))
        direction = p.get('direction')
        limit = int(p.get('limit', 12))
        dimension = p.get('dimension', 'category')

        start, end = self._resolve_report_bounds(p)
        conditions, sql_params = self._report_conditions(start, end, family_id, role_id)
        self._append_internal_flow_filters(conditions, hide_internal)
        if direction:
            conditions.append("ub.direction = ?")
            sql_params.append(direction)
        where = " AND ".join(conditions)

        joins = ""
        group_expr = "ub.category_id"
        key_expr = "CAST(ub.category_id AS TEXT)"
        label_expr = "COALESCE(bc.name, '未分类')"
        extra_select = ", bc.icon AS icon"

        if dimension == 'account':
            joins = " LEFT JOIN accounts a ON ub.account_id = a.id"
            group_expr = "COALESCE(ub.account_id, 0)"
            key_expr = "CAST(COALESCE(ub.account_id, 0) AS TEXT)"
            label_expr = "COALESCE(a.account_name, '未分配账户')"
            extra_select = ""
        elif dimension == 'role':
            joins = " LEFT JOIN roles r ON ub.role_id = r.id"
            group_expr = "COALESCE(ub.role_id, 0)"
            key_expr = "CAST(COALESCE(ub.role_id, 0) AS TEXT)"
            label_expr = "COALESCE(r.name, '未分配角色')"
            extra_select = ""
        elif dimension == 'channel':
            group_expr = "ub.channel"
            key_expr = "ub.channel"
            label_expr = "ub.channel"
            extra_select = ""
        elif dimension == 'trade_type':
            group_expr = "ub.trade_type"
            key_expr = "ub.trade_type"
            label_expr = "ub.trade_type"
            extra_select = ""
        elif dimension == 'counterparty':
            group_expr = "COALESCE(NULLIF(TRIM(ub.counterparty), ''), '未填写交易对方')"
            key_expr = group_expr
            label_expr = group_expr
            extra_select = ""
        else:
            joins = " LEFT JOIN bill_categories bc ON ub.category_id = bc.id"

        rows = self.dal.fetch_all(
            f"SELECT {key_expr} AS item_key, {label_expr} AS item_label{extra_select}, "
            f"COALESCE(SUM(ub.amount_cents), 0) AS total_amount, COUNT(*) AS count "
            f"FROM unified_bills ub {joins} "
            f"WHERE {where} "
            f"GROUP BY {group_expr} "
            f"ORDER BY total_amount DESC, count DESC "
            f"LIMIT ?",
            tuple(sql_params) + (limit,),
        )
        items = [dict(r) for r in rows]
        total_amount = sum(item['total_amount'] or 0 for item in items)
        result = []
        for item in items:
            amount = item.get('total_amount') or 0
            count = item.get('count') or 0
            result.append({
                'key': item.get('item_key'),
                'label': item.get('item_label'),
                'icon': item.get('icon', ''),
                'total_amount': amount,
                'count': count,
                'ratio': round(amount / total_amount, 4) if total_amount else 0,
                'avg_amount': round(amount / count) if count else 0,
            })

        return self.ok({'items': result})

    def get_report_trend_overview(self, params=None) -> dict:
        p = params or {}
        family_id = p.get('family_id')
        role_id = p.get('role_id')
        hide_internal = bool(p.get('hide_internal', False))

        items = []
        period = str(p.get('period', '') or '')

        if period == 'custom':
            start, end = self._resolve_report_bounds(p)
            total_days = self._days_between(start, end)
            granularity = 'day' if total_days <= 62 else 'month'

            if granularity == 'day':
                current = datetime.strptime(start, '%Y-%m-%dT%H:%M:%S+08:00')
                end_dt = datetime.strptime(end, '%Y-%m-%dT%H:%M:%S+08:00')
                while current < end_dt:
                    next_day = current + timedelta(days=1)
                    metrics = self._report_summary_metrics(
                        current.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
                        next_day.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
                        family_id,
                        role_id,
                        hide_internal=hide_internal,
                    )
                    items.append({
                        'month': current.strftime('%Y-%m-%d'),
                        'income': metrics['income'],
                        'expense': metrics['expense'],
                        'net': metrics['net'],
                        'credit': metrics['credit'],
                        'repayment': metrics['repayment'],
                        'bill_count': metrics['bill_count'],
                    })
                    current = next_day
            else:
                current = datetime.strptime(start[:7], '%Y-%m')
                end_dt = datetime.strptime(end[:7], '%Y-%m')
                while current <= end_dt:
                    year = current.year
                    month = current.month
                    month_start, month_end = self._month_bounds(year, month)
                    range_start = max(month_start, start)
                    range_end = min(month_end, end)
                    if range_start < range_end:
                        metrics = self._report_summary_metrics(
                            range_start,
                            range_end,
                            family_id,
                            role_id,
                            hide_internal=hide_internal,
                        )
                        items.append({
                            'month': f"{year}-{month:02d}",
                            'income': metrics['income'],
                            'expense': metrics['expense'],
                            'net': metrics['net'],
                            'credit': metrics['credit'],
                            'repayment': metrics['repayment'],
                            'bill_count': metrics['bill_count'],
                        })
                    if month == 12:
                        current = current.replace(year=year + 1, month=1)
                    else:
                        current = current.replace(month=month + 1)
            return self.ok({'months': items, 'granularity': granularity})

        end_year = int(p.get('end_year'))
        end_month = int(p.get('end_month'))
        months = int(p.get('months', 12))
        start_year, start_month = self._shift_month(end_year, end_month, -(months - 1))
        current_year, current_month = start_year, start_month
        for _ in range(months):
            start, end = self._month_bounds(current_year, current_month)
            metrics = self._report_summary_metrics(start, end, family_id, role_id, hide_internal=hide_internal)
            items.append({
                'month': f"{current_year}-{current_month:02d}",
                'income': metrics['income'],
                'expense': metrics['expense'],
                'net': metrics['net'],
                'credit': metrics['credit'],
                'repayment': metrics['repayment'],
                'bill_count': metrics['bill_count'],
            })
            current_year, current_month = self._shift_month(current_year, current_month, 1)

        return self.ok({'months': items, 'granularity': 'month'})

    def get_report_daily_calendar(self, params=None) -> dict:
        p = params or {}
        family_id = p.get('family_id')
        role_id = p.get('role_id')
        hide_internal = bool(p.get('hide_internal', False))
        start, end = self._resolve_report_bounds(p)
        where, sql_params = self._report_where(start, end, family_id, role_id, hide_internal=hide_internal)

        rows = self.dal.fetch_all(
            "SELECT substr(ub.trade_time, 1, 10) AS date, "
            "COALESCE(SUM(CASE WHEN ub.direction = 'income' THEN ub.amount_cents ELSE 0 END), 0) AS income, "
            "COALESCE(SUM(CASE WHEN ub.direction = 'expense' AND ub.trade_type != 'credit_consumption' THEN ub.amount_cents ELSE 0 END), 0) AS expense, "
            "COUNT(*) AS bill_count "
            "FROM unified_bills ub "
            f"WHERE {where} "
            "GROUP BY substr(ub.trade_time, 1, 10) "
            "ORDER BY date ASC",
            tuple(sql_params),
        )

        days = []
        for row in rows:
            income = row['income'] or 0
            expense = row['expense'] or 0
            days.append({
                'date': row['date'],
                'income': income,
                'expense': expense,
                'net': income - expense,
                'bill_count': row['bill_count'] or 0,
            })
        return self.ok({'days': days})

    def get_report_accounting_health(self, params=None) -> dict:
        p = params or {}
        family_id = p.get('family_id')
        role_id = p.get('role_id')
        start, end = self._resolve_report_bounds(p)

        active_where, active_params = self._report_where(start, end, family_id, role_id, hide_internal=False)
        deleted_where, deleted_params = self._report_where(start, end, family_id, role_id, include_deleted=True)

        pending_assign_count = self._fetch_scalar(
            f"SELECT COUNT(*) AS value FROM unified_bills ub WHERE {active_where} AND ub.assign_status = 'pending'",
            active_params,
        )
        uncategorized_count = self._fetch_scalar(
            f"SELECT COUNT(*) AS value FROM unified_bills ub "
            f"WHERE {active_where} AND ub.direction = 'expense' AND ub.category_id IS NULL",
            active_params,
        )
        orphan_count = self._fetch_scalar(
            "SELECT COUNT(*) AS value FROM unified_bills ub "
            "LEFT JOIN bill_accounting ba ON ub.id = ba.bill_id "
            f"WHERE {active_where} AND ba.merge_status = 'orphan'",
            active_params,
        )
        credit_count = self._fetch_scalar(
            f"SELECT COUNT(*) AS value FROM unified_bills ub WHERE {active_where} AND ub.trade_type = 'credit_consumption'",
            active_params,
        )
        repayment_count = self._fetch_scalar(
            f"SELECT COUNT(*) AS value FROM unified_bills ub WHERE {active_where} AND ub.trade_type = 'repayment'",
            active_params,
        )
        internal_transfer_count = self._fetch_scalar(
            f"SELECT COUNT(*) AS value FROM unified_bills ub "
            f"WHERE {active_where} AND ub.trade_type IN ('transfer_out', 'transfer_in', 'repayment', 'repayment_mirror')",
            active_params,
        )
        deleted_count = self._fetch_scalar(
            f"SELECT COUNT(*) AS value FROM unified_bills ub WHERE {deleted_where} AND ub.is_deleted = 1",
            deleted_params,
        )

        return self.ok({
            'pending_assign_count': pending_assign_count,
            'uncategorized_count': uncategorized_count,
            'orphan_count': orphan_count,
            'credit_count': credit_count,
            'repayment_count': repayment_count,
            'internal_transfer_count': internal_transfer_count,
            'deleted_count': deleted_count,
        })
