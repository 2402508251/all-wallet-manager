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

    def handle_upload(self, files: list[dict]) -> list[int]:
        record_ids = []

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
                with open(saved_path, 'wb') as f:
                    f.write(file_data)
            else:
                continue

            if ext == '.zip':
                zip_records = self._handle_zip(saved_path, file_name)
                record_ids.extend(zip_records)
            else:
                detection = self.detector.detect(file_name)
                record_id = self.dal.insert('collection_records', {
                    'source_type': 'upload',
                    'file_name': file_name,
                    'file_path': saved_path,
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

        new_record_ids = []
        for item in extracted:
            detection = self.detector.detect(item['file_name'])
            new_id = self.dal.insert('collection_records', {
                'source_type': 'upload',
                'file_name': item['file_name'],
                'file_path': item['file_path'],
                'channel': detection['channel'],
                'channel_source': detection['source'],
                'status': 'pending',
            })
            new_record_ids.append(new_id)

        self.dal.update(
            'collection_records',
            {'status': 'processed'},
            'id = ?',
            (record_id,),
        )

        return {
            'success': True,
            'new_record_ids': new_record_ids,
            'extracted_count': len(extracted),
        }

    def _handle_zip(self, zip_path: str, file_name: str) -> list[int]:
        record_ids = []

        encryption = self.zip_handler.detect_encryption(zip_path)
        if encryption.get('encrypted'):
            record_id = self.dal.insert('collection_records', {
                'source_type': 'upload',
                'file_name': file_name,
                'file_path': zip_path,
                'channel': 'unknown',
                'channel_source': 'auto_detect',
                'status': 'need_password',
            })
            record_ids.append(record_id)
            return record_ids

        extracted = self.zip_handler.extract(zip_path)
        for item in extracted:
            if item.get('error'):
                continue
            detection = self.detector.detect(item['file_name'])
            new_id = self.dal.insert('collection_records', {
                'source_type': 'upload',
                'file_name': item['file_name'],
                'file_path': item['file_path'],
                'channel': detection['channel'],
                'channel_source': detection['source'],
                'status': 'pending',
            })
            record_ids.append(new_id)

        return record_ids

    def _file_hash(self, file_path: str) -> str:
        h = hashlib.sha256()
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()