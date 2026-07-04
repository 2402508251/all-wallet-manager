"""
配置管理器 —— 加载/保存 JSON 配置文件，带内存缓存
"""
import json
import os
from typing import Optional


class ConfigManager:
    def __init__(self, config_dir: str):
        self.config_dir = config_dir
        self._cache: dict[str, dict] = {}

    def load(self, config_name: str) -> dict:
        """加载配置文件（带缓存）"""
        if config_name in self._cache:
            return self._cache[config_name]

        file_path = os.path.join(self.config_dir, config_name)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"配置文件不存在: {file_path}")

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self._cache[config_name] = data
        return data

    def save(self, config_name: str, data: dict) -> None:
        """保存配置文件（写磁盘 + 更新缓存）"""
        file_path = os.path.join(self.config_dir, config_name)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self._cache[config_name] = data

    def get_category_keywords(self) -> list[dict]:
        """获取分类关键词规则列表"""
        data = self.load('category_keywords.json')
        return data.get('rules', [])

    def get_enum_mappings(self, channel: str) -> dict:
        """获取指定渠道的枚举映射"""
        data = self.load('channel_enum_mappings.json')
        return data.get(channel, {})

    def get_email_whitelist(self) -> list[dict]:
        """获取邮箱白名单"""
        data = self.load('email_whitelist.json')
        return data.get('whitelist', [])

    def update_category_keyword(
        self, category_name: str, keyword: str,
        match_field: str, priority: int
    ) -> None:
        data = self.load('category_keywords.json')
        rules = data.get('rules', [])
        for rule in rules:
            if rule.get('category_name') == category_name:
                kws = rule.get('keywords', [])
                for kw in kws:
                    if kw.get('keyword') == keyword and kw.get('match_field') == match_field:
                        kw['priority'] = priority
                        self.save('category_keywords.json', data)
                        return
                kws.append({'keyword': keyword, 'match_field': match_field, 'priority': priority})
                self.save('category_keywords.json', data)
                return
        rules.append({
            'category_name': category_name,
            'keywords': [{'keyword': keyword, 'match_field': match_field, 'priority': priority}],
        })
        self.save('category_keywords.json', data)

    def delete_category_keyword(
        self, category_name: str, keyword: str, match_field: str
    ) -> bool:
        data = self.load('category_keywords.json')
        rules = data.get('rules', [])
        for rule in rules:
            if rule.get('category_name') == category_name:
                before = len(rule.get('keywords', []))
                rule['keywords'] = [
                    kw for kw in rule.get('keywords', [])
                    if not (kw.get('keyword') == keyword and kw.get('match_field') == match_field)
                ]
                if len(rule['keywords']) < before:
                    self.save('category_keywords.json', data)
                    return True
        return False

    def update_enum_mapping(
        self, channel: str, field: str,
        original_value: str, mapped_value: str
    ) -> None:
        data = self.load('channel_enum_mappings.json')
        channel_data = data.get(channel, {})
        field_map = channel_data.get(field, {})
        field_map[original_value] = mapped_value
        channel_data[field] = field_map
        data[channel] = channel_data
        self.save('channel_enum_mappings.json', data)

    def delete_enum_mapping(
        self, channel: str, field: str, original_value: str
    ) -> bool:
        data = self.load('channel_enum_mappings.json')
        channel_data = data.get(channel, {})
        field_map = channel_data.get(field, {})
        if original_value in field_map:
            del field_map[original_value]
            channel_data[field] = field_map
            data[channel] = channel_data
            self.save('channel_enum_mappings.json', data)
            return True
        return False