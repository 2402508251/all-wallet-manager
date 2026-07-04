"""
解析器基类 —— 定义解析器接口和数据模型
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ParseResult:
    total: int = 0
    success: int = 0
    duplicate: int = 0
    records: list[dict] = field(default_factory=list)
    raw_records: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    _seen_trade_nos: set = field(default_factory=set)

    def add_record(self, record: dict, raw: dict = None) -> None:
        trade_no = record.get('channel_trade_no', '')
        if trade_no in self._seen_trade_nos:
            self.duplicate += 1
            return
        if trade_no:
            self._seen_trade_nos.add(trade_no)
        self.records.append(record)
        if raw is not None:
            self.raw_records.append(raw)
        self.success += 1


class BaseParser(ABC):
    @abstractmethod
    def parse(self, file_path: str) -> ParseResult:
        """解析账单文件，返回标准化结果"""
        ...

    @abstractmethod
    def get_channel(self) -> str:
        """返回渠道标识：wechat / alipay / ccb"""
        ...