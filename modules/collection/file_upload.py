"""
文件上传处理 —— 接收前端上传的账单文件，保存到临时目录，创建采集记录
"""
import hashlib
import os
import shutil
import time

from .channel_detector import ChannelDetector
from .zip_handler import ZipHandler
from core.dal import DAL


class FileUploadHandler:
    ALLOWED_EXTENSIONS = {'.xlsx', '.xls', '.csv', '.zip', '.pdf'}

    def __init__(self, app_dir: str, dal: DAL):
        self.app_dir = app_dir
        self.dal = dal
        self.temp_dir = os.path.join(app_dir, 'data', 'temp')
        os.makedirs(self.temp_dir, exist_ok=True)
        self.detector = ChannelDetector()
        self.zip_handler = ZipHandler(self.temp_dir)
        self.duplicate_skipped = 0

    def handle_upload(self, files: list[dict]) -> list[int]:
        record_ids = []
        self.duplicate_skipped = 0

        for file_info in files:
            file_name = file_info.get('name', '')
            file_data = file_info.get('data')
            file_path = file_info.get('path', '')

            # 前端传递的是字节数组（JSON序列化为列表），需转换为bytes
            if isinstance(file_data, list):
                file_data = bytes(file_data)
            elif file_data is None:
                file_data = b''

            ext = os.path.splitext(file_name)[1].lower()
            if ext not in self.ALLOWED_EXTENSIONS:
                continue

            if file_path and os.path.exists(file_path):
                saved_path = os.path.join(self.temp_dir, file_name)
                if os.path.exists(saved_path):
                    base, ext_part = os.path.splitext(file_name)
                    stamp = str(int(time.time() * 1000))[-6:]
                    saved_path = os.path.join(self.temp_dir, f"{base}_{stamp}{ext_part}")
                shutil.copy2(file_path, saved_path)
            elif file_data:
                saved_path = os.path.join(self.temp_dir, file_name)
                if os.path.exists(saved_path):
                    base, ext_part = os.path.splitext(file_name)
                    stamp = str(int(time.time() * 1000))[-6:]
                    saved_path = os.path.join(self.temp_dir, f"{base}_{stamp}{ext_part}")
                with open(saved_path, 'wb') as f:
                    f.write(file_data)
            else:
                continue

            if ext == '.zip':
                zip_records = self.handle_zip_file(saved_path, file_name, source_type='upload')
                record_ids.extend(zip_records)
            else:
                file_hash = self._file_hash(saved_path)
                if self._collection_file_exists('upload', file_hash):
                    self.duplicate_skipped += 1
                    continue
                detection = self.detector.detect(file_name)
                record_id = self.dal.insert('collection_records', {
                    'source_type': 'upload',
                    'file_name': file_name,
                    'file_path': saved_path,
                    'file_hash': file_hash,
                    'channel': detection['channel'],
                    'channel_source': detection['source'],
                    'status': 'pending',
                })
                record_ids.append(record_id)

        return record_ids

    def handle_zip_password(self, record_id: int, password: str) -> dict:
        record = self.dal.fetch_one(
            "SELECT * FROM collection_records WHERE id = ?", (record_id,)
        )
        if not record:
            return {'success': False, 'message': '记录不存在'}

        file_path = record['file_path']
        if not file_path or not os.path.exists(file_path):
            return {'success': False, 'message': '文件不存在'}

        extracted = self.zip_handler.extract(file_path, password)

        if extracted and extracted[0].get('error'):
            error = extracted[0]['error']
            if error == 'need_password':
                return {'success': False, 'message': '需要密码', 'need_password': True}
            elif error == 'wrong_password':
                return {'success': False, 'message': '密码错误', 'need_password': True}
            return {'success': False, 'message': error}

        source_type = record.get('source_type') or 'upload'
        email_config_id = record.get('email_config_id') if source_type == 'email' else None

        with self.dal.transaction():
            new_record_ids, duplicate_skipped = self._insert_extracted_records(
                extracted,
                source_type=source_type,
                email_config_id=email_config_id,
            )
            self.dal.update(
                'collection_records',
                {'status': 'processed'},
                'id = ?',
                (record_id,),
            )

        return {
            'success': True,
            'new_record_ids': new_record_ids,
            'extracted_count': len(new_record_ids),
            'duplicate_skipped': duplicate_skipped,
        }

    def handle_zip_file(
        self,
        zip_path: str,
        file_name: str,
        source_type: str = 'upload',
        email_config_id: int | None = None,
    ) -> list[int]:
        record_ids = []

        encryption = self.zip_handler.detect_encryption(zip_path)
        if encryption.get('encrypted'):
            file_hash = self._file_hash(zip_path)
            if self._collection_file_exists(source_type, file_hash, email_config_id):
                self.duplicate_skipped += 1
                return record_ids
            data = {
                'source_type': source_type,
                'file_name': file_name,
                'file_path': zip_path,
                'file_hash': file_hash,
                'channel': 'unknown',
                'channel_source': 'auto_detect',
                'status': 'need_password',
            }
            if source_type == 'email':
                data['email_config_id'] = email_config_id
            record_id = self.dal.insert('collection_records', data)
            record_ids.append(record_id)
            return record_ids

        extracted = self.zip_handler.extract(zip_path)
        with self.dal.transaction():
            record_ids, duplicate_skipped = self._insert_extracted_records(
                extracted,
                source_type=source_type,
                email_config_id=email_config_id,
            )
            self.duplicate_skipped += duplicate_skipped

        return record_ids

    def _insert_extracted_records(
        self,
        extracted: list[dict],
        source_type: str,
        email_config_id: int | None = None,
    ) -> tuple[list[int], int]:
        record_ids = []
        duplicate_skipped = 0
        for item in extracted:
            if item.get('error'):
                continue
            file_hash = self._file_hash(item['file_path'])
            if self._collection_file_exists(source_type, file_hash, email_config_id):
                duplicate_skipped += 1
                continue
            detection = self.detector.detect(item['file_name'])
            data = {
                'source_type': source_type,
                'file_name': item['file_name'],
                'file_path': item['file_path'],
                'file_hash': file_hash,
                'channel': detection['channel'],
                'channel_source': detection['source'],
                'status': 'pending',
            }
            if source_type == 'email':
                data['email_config_id'] = email_config_id
            new_id = self.dal.insert('collection_records', data)
            record_ids.append(new_id)
        return record_ids, duplicate_skipped

    def _file_hash(self, file_path: str) -> str:
        h = hashlib.sha256()
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def _collection_file_exists(
        self,
        source_type: str,
        file_hash: str,
        email_config_id: int | None = None,
    ) -> bool:
        if not file_hash:
            return False
        if source_type == 'email':
            existing = self.dal.fetch_one(
                """
                SELECT id FROM collection_records
                WHERE source_type = ? AND email_config_id = ? AND file_hash = ?
                LIMIT 1
                """,
                ('email', email_config_id, file_hash),
            )
        else:
            existing = self.dal.fetch_one(
                """
                SELECT id FROM collection_records
                WHERE source_type = ? AND file_hash = ?
                LIMIT 1
                """,
                (source_type, file_hash),
            )
        return existing is not None

    def _upload_file_exists(self, file_hash: str) -> bool:
        return self._collection_file_exists('upload', file_hash)
