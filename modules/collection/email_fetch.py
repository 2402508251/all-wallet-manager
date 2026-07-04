"""
邮箱拉取 —— 通过 IMAP SSL 连接邮箱，拉取账单类邮件附件
"""
import email
import imaplib
import os
import tempfile
import threading
from datetime import datetime

from .channel_detector import ChannelDetector
from core.config_manager import ConfigManager
from core.dal import DAL
from core.crypto_utils import CredentialEncryptor


class EmailFetcher:
    def __init__(self, app_dir: str, dal: DAL, config_manager: ConfigManager):
        self.app_dir = app_dir
        self.dal = dal
        self.config_manager = config_manager
        self.encryptor = CredentialEncryptor()
        self.detector = ChannelDetector()
        self.temp_dir = os.path.join(app_dir, 'data', 'temp')
        os.makedirs(self.temp_dir, exist_ok=True)

    def test_connection(self, config_id: int) -> dict:
        config = self.dal.fetch_one(
            "SELECT * FROM email_configs WHERE id = ?", (config_id,)
        )
        if not config:
            return {'success': False, 'message': '配置不存在'}

        try:
            auth_code = self.encryptor.decrypt(config['auth_code_enc'])
            imap = imaplib.IMAP4_SSL(config['imap_server'], config['imap_port'])
            imap.login(config['email_addr'], auth_code)
            imap.select('INBOX')
            imap.logout()
            return {'success': True, 'message': '连接成功'}
        except imaplib.IMAP4.error as e:
            return {'success': False, 'message': f'IMAP错误: {e}'}
        except Exception as e:
            return {'success': False, 'message': f'连接失败: {e}'}

    def fetch_bills(self, config_id: int, task_id: str = None) -> dict:
        config = self.dal.fetch_one(
            "SELECT * FROM email_configs WHERE id = ?", (config_id,)
        )
        if not config:
            return {'success': False, 'message': '配置不存在'}

        try:
            auth_code = self.encryptor.decrypt(config['auth_code_enc'])
        except Exception as e:
            return {'success': False, 'message': f'解密授权码失败: {e}'}

        try:
            imap = imaplib.IMAP4_SSL(config['imap_server'], config['imap_port'])
            imap.login(config['email_addr'], auth_code)
            imap.select('INBOX')
        except Exception as e:
            return {'success': False, 'message': f'连接邮箱失败: {e}'}

        whitelist = self.config_manager.get_email_whitelist()
        last_uid = config['last_uid'] or 0

        if last_uid:
            _, data = imap.uid('search', None, f'UID {last_uid + 1}:*')
        else:
            last_fetch_ts = config.get('last_fetch_ts')
            if last_fetch_ts:
                try:
                    dt = datetime.fromisoformat(last_fetch_ts)
                    since_date = dt.strftime('%d-%b-%Y')
                    _, data = imap.uid('search', None, f'(SINCE {since_date})')
                except (ValueError, TypeError):
                    _, data = imap.uid('search', None, 'ALL')
            else:
                _, data = imap.uid('search', None, 'ALL')

        uid_list = data[0].split() if data[0] else []
        if not uid_list:
            imap.logout()
            return {'success': True, 'message': '无新邮件', 'downloaded': 0}

        record_ids = []
        max_uid = last_uid

        for uid in uid_list:
            _, msg_data = imap.uid('fetch', uid, '(RFC822)')
            if not msg_data or not msg_data[0]:
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            from_addr = email.utils.parseaddr(msg.get('From', ''))[1]
            subject = msg.get('Subject', '')
            try:
                from email.header import decode_header
                decoded = decode_header(subject)
                subject = ''.join(
                    part.decode(enc or 'utf-8') if isinstance(part, bytes) else part
                    for part, enc in decoded
                )
            except Exception:
                pass

            matched_channel = self._match_whitelist(from_addr, subject, whitelist)
            if not matched_channel:
                continue

            for part in msg.walk():
                content_disposition = part.get('Content-Disposition', '')
                if 'attachment' not in content_disposition:
                    continue

                filename = part.get_filename()
                if not filename:
                    continue

                try:
                    from email.header import decode_header
                    decoded = decode_header(filename)
                    filename = ''.join(
                        part.decode(enc or 'utf-8') if isinstance(part, bytes) else part
                        for part, enc in decoded
                    )
                except Exception:
                    pass

                ext = os.path.splitext(filename)[1].lower()
                if ext not in ('.xlsx', '.xls', '.csv', '.zip', '.pdf'):
                    continue

                save_path = os.path.join(self.temp_dir, filename)
                with open(save_path, 'wb') as f:
                    f.write(part.get_payload(decode=True))

                detection = self.detector.detect(filename)
                channel = detection['channel'] if detection['channel'] != 'unknown' else matched_channel

                record_id = self.dal.insert('collection_records', {
                    'source_type': 'email',
                    'email_config_id': config_id,
                    'file_name': filename,
                    'file_path': save_path,
                    'channel': channel,
                    'channel_source': 'auto_detect',
                    'status': 'pending',
                })
                record_ids.append(record_id)

            uid_num = int(uid)
            if uid_num > max_uid:
                max_uid = uid_num

        now = datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')
        self.dal.update(
            'email_configs',
            {'last_uid': max_uid, 'last_fetch_ts': now},
            'id = ?',
            (config_id,),
        )

        imap.logout()
        return {
            'success': True,
            'downloaded': len(record_ids),
            'record_ids': record_ids,
        }

    def clear_credentials(self, config_id: int) -> bool:
        """清除授权凭证，保留邮箱配置（imap_server/port/last_uid 等）"""
        self.dal.update(
            'email_configs',
            {'auth_code_enc': None},
            'id = ?',
            (config_id,),
        )
        return True

    def _match_whitelist(self, from_addr: str, subject: str,
                         whitelist: list[dict]) -> str | None:
        for rule in whitelist:
            sender_domain = rule.get('sender_domain', '')
            if sender_domain and sender_domain not in from_addr:
                continue

            keywords = rule.get('subject_keywords', [])
            if keywords:
                if rule.get('subject_keyword_any', True):
                    if not any(kw in subject for kw in keywords):
                        continue
                else:
                    if not all(kw in subject for kw in keywords):
                        continue

            return rule.get('channel')

        return None