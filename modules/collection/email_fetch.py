"""
邮箱拉取 —— 通过 IMAP SSL 连接邮箱，拉取账单类邮件附件
"""
import email
import hashlib
import imaplib
import os
import uuid

from .channel_detector import ChannelDetector
from .file_upload import FileUploadHandler
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

        imap = None
        try:
            auth_code = self.encryptor.decrypt(config['auth_code_enc'])
            imap = imaplib.IMAP4_SSL(config['imap_server'], config['imap_port'])
            imap.login(config['email_addr'], auth_code)
            imap.select('INBOX')
            return {'success': True, 'message': '连接成功'}
        except imaplib.IMAP4.error as e:
            return {'success': False, 'message': f'IMAP错误: {e}'}
        except Exception as e:
            return {'success': False, 'message': f'连接失败: {e}'}
        finally:
            if imap:
                try:
                    imap.logout()
                except Exception:
                    pass

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

        imap = None
        try:
            imap = imaplib.IMAP4_SSL(config['imap_server'], config['imap_port'])
            imap.login(config['email_addr'], auth_code)
            imap.select('INBOX')

            whitelist_config = self._load_whitelist_config()
            _, data = imap.uid('search', None, 'ALL')
            uid_list = data[0].split() if data and data[0] else []
            if not uid_list:
                return {
                    'success': True,
                    'message': '无邮件',
                    'downloaded': 0,
                    'duplicate_skipped': 0,
                    'record_ids': [],
                }

            record_ids = []
            duplicate_skipped = 0
            matched_without_attachment = 0

            for uid in uid_list:
                uid_num = int(uid)
                _, msg_data = imap.uid('fetch', uid, '(RFC822)')
                if not msg_data or not msg_data[0]:
                    continue

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                from_addr = email.utils.parseaddr(msg.get('From', ''))[1]
                subject = self._decode_header_value(msg.get('Subject', ''))

                matched_channel = self._match_whitelist(from_addr, subject, whitelist_config)
                if not matched_channel:
                    continue

                attachments = []
                try:
                    for part in msg.walk():
                        content_disposition = part.get('Content-Disposition', '')
                        if 'attachment' not in content_disposition:
                            continue

                        filename = part.get_filename()
                        if not filename:
                            continue

                        filename = os.path.basename(self._decode_header_value(filename))
                        ext = os.path.splitext(filename)[1].lower()
                        if ext not in ('.xlsx', '.xls', '.csv', '.zip', '.pdf'):
                            continue

                        payload = part.get_payload(decode=True)
                        if payload is None:
                            continue

                        file_hash = self._payload_hash(payload)
                        if self._email_file_exists(config_id, file_hash):
                            duplicate_skipped += 1
                            continue

                        stored_name = self._build_unique_filename(uid_num, filename)
                        save_path = os.path.join(self.temp_dir, stored_name)
                        with open(save_path, 'wb') as f:
                            f.write(payload)

                        if ext == '.zip':
                            attachments.append({
                                'file_name': filename,
                                'file_path': save_path,
                                'file_hash': file_hash,
                                'is_zip': True,
                            })
                            continue

                        detection = self.detector.detect(filename)
                        detector_channel = detection['channel']
                        if detector_channel != 'unknown':
                            channel = detector_channel
                            channel_source = 'auto_detect'
                        else:
                            channel = matched_channel
                            channel_source = 'email_whitelist'

                        attachments.append({
                            'file_name': filename,
                            'file_path': save_path,
                            'file_hash': file_hash,
                            'channel': channel,
                            'channel_source': channel_source,
                        })

                    if not attachments:
                        matched_without_attachment += 1
                        continue

                    current_record_ids = []
                    zip_handler = FileUploadHandler(self.app_dir, self.dal)
                    with self.dal.transaction():
                        for attachment in attachments:
                            if attachment.get('is_zip'):
                                before = zip_handler.duplicate_skipped
                                zip_record_ids = zip_handler.handle_zip_file(
                                    attachment['file_path'],
                                    attachment['file_name'],
                                    source_type='email',
                                    email_config_id=config_id,
                                )
                                duplicate_skipped += zip_handler.duplicate_skipped - before
                                current_record_ids.extend(zip_record_ids)
                                continue

                            if self._email_file_exists(config_id, attachment['file_hash']):
                                duplicate_skipped += 1
                                continue
                            record_id = self.dal.insert('collection_records', {
                                'source_type': 'email',
                                'email_config_id': config_id,
                                'file_name': attachment['file_name'],
                                'file_path': attachment['file_path'],
                                'file_hash': attachment['file_hash'],
                                'channel': attachment['channel'],
                                'channel_source': attachment['channel_source'],
                                'status': 'pending',
                            })
                            current_record_ids.append(record_id)
                    record_ids.extend(current_record_ids)
                except Exception as e:
                    return {'success': False, 'message': f'处理邮件附件失败: {e}'}

            message = f"拉取完成，新增 {len(record_ids)} 个附件"
            if duplicate_skipped:
                message += f"，跳过 {duplicate_skipped} 个重复附件"
            elif not record_ids:
                message = '未发现新的账单附件'

            return {
                'success': True,
                'message': message,
                'downloaded': len(record_ids),
                'duplicate_skipped': duplicate_skipped,
                'matched_without_attachment': matched_without_attachment,
                'record_ids': record_ids,
            }
        except Exception as e:
            return {'success': False, 'message': f'连接邮箱失败: {e}'}
        finally:
            if imap:
                try:
                    imap.logout()
                except Exception:
                    pass

    def clear_credentials(self, config_id: int) -> bool:
        """清除授权凭证，保留邮箱配置（imap_server/port/last_uid 等）"""
        self.dal.update(
            'email_configs',
            {'auth_code_enc': None},
            'id = ?',
            (config_id,),
        )
        return True

    def _load_whitelist_config(self) -> dict:
        try:
            return self.config_manager.load('email_whitelist.json')
        except Exception:
            return {'whitelist': []}

    def _match_whitelist(self, from_addr: str, subject: str,
                         whitelist_config: dict | list[dict]) -> str | None:
        if isinstance(whitelist_config, list):
            rules = whitelist_config
            default_keyword_any = True
        else:
            rules = whitelist_config.get('whitelist', [])
            default_keyword_any = whitelist_config.get('subject_keyword_any', True)

        for rule in rules:
            sender_domain = rule.get('sender_domain', '')
            if sender_domain and sender_domain not in from_addr:
                continue

            keywords = rule.get('subject_keywords', [])
            if keywords:
                keyword_any = rule.get('subject_keyword_any', default_keyword_any)
                if keyword_any:
                    if not any(kw in subject for kw in keywords):
                        continue
                else:
                    if not all(kw in subject for kw in keywords):
                        continue

            return rule.get('channel')

        return None

    def _decode_header_value(self, value: str) -> str:
        try:
            from email.header import decode_header
            decoded = decode_header(value)
            return ''.join(
                part.decode(enc or 'utf-8') if isinstance(part, bytes) else part
                for part, enc in decoded
            )
        except Exception:
            return value

    def _build_unique_filename(self, uid: int, filename: str) -> str:
        safe_name = os.path.basename(filename) or 'attachment'
        return f"email_{uid}_{uuid.uuid4().hex[:8]}_{safe_name}"

    def _payload_hash(self, payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    def _email_file_exists(self, config_id: int, file_hash: str) -> bool:
        if not file_hash:
            return False
        existing = self.dal.fetch_one(
            """
            SELECT id FROM collection_records
            WHERE source_type = ? AND email_config_id = ? AND file_hash = ?
            LIMIT 1
            """,
            ('email', config_id, file_hash),
        )
        return existing is not None
