"""
ZIP 处理 —— 支持普通 ZIP 和 AES 加密 ZIP 解压
"""
import os
import tempfile
import zipfile

from .channel_detector import ChannelDetector


class ZipHandler:
    def __init__(self, temp_dir: str = None):
        self.temp_dir = temp_dir or tempfile.gettempdir()
        self.detector = ChannelDetector()

    def detect_encryption(self, file_path: str) -> dict:
        """检测 ZIP 加密类型：无加密/ZipCrypto/AES"""
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                for info in zf.infolist():
                    if info.flag_bits & 0x1:
                        if info.compress_type == 99:
                            return {
                                'encrypted': True,
                                'encryption_type': 'aes',
                            }
                        return {
                            'encrypted': True,
                            'encryption_type': 'zipcrypto',
                        }
                return {'encrypted': False, 'encryption_type': 'none'}
        except RuntimeError:
            return {'encrypted': True, 'encryption_type': 'unknown'}
        except Exception as e:
            return {'encrypted': False, 'encryption_type': 'none', 'error': str(e)}

    def extract(self, file_path: str, password: str = None) -> list[dict]:
        results = []
        extract_dir = tempfile.mkdtemp(dir=self.temp_dir)

        encryption = self.detect_encryption(file_path)

        if encryption.get('encrypted') and not password:
            return [{'error': 'need_password', 'file_path': file_path}]

        try:
            if encryption.get('encrypted'):
                try:
                    import pyzipper
                    with pyzipper.AESZipFile(file_path, 'r') as zf:
                        zf.setpassword(password.encode('utf-8'))
                        zf.extractall(extract_dir)
                except ImportError:
                    with zipfile.ZipFile(file_path, 'r') as zf:
                        zf.extractall(
                            extract_dir,
                            pwd=password.encode('utf-8') if password else None,
                        )
                except Exception:
                    with zipfile.ZipFile(file_path, 'r') as zf:
                        zf.extractall(
                            extract_dir,
                            pwd=password.encode('utf-8') if password else None,
                        )
            else:
                with zipfile.ZipFile(file_path, 'r') as zf:
                    zf.extractall(extract_dir)
        except RuntimeError as e:
            if 'password' in str(e).lower() or 'encrypt' in str(e).lower():
                return [{'error': 'wrong_password', 'file_path': file_path}]
            return [{'error': str(e), 'file_path': file_path}]
        except Exception as e:
            return [{'error': str(e), 'file_path': file_path}]

        for root, dirs, files in os.walk(extract_dir):
            for fname in files:
                fpath = os.path.join(root, fname)
                ext = os.path.splitext(fname)[1].lower()
                if ext in ('.xlsx', '.xls', '.csv', '.pdf'):
                    detection = self.detector.detect(fname)
                    results.append({
                        'file_path': fpath,
                        'file_name': fname,
                        'channel': detection['channel'],
                        'confidence': detection['confidence'],
                    })

        if not results:
            for root, dirs, files in os.walk(extract_dir):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    results.append({
                        'file_path': fpath,
                        'file_name': fname,
                        'channel': 'unknown',
                        'confidence': 0.0,
                    })

        return results

    def cleanup_temp(self, file_path: str) -> None:
        if os.path.exists(file_path):
            if os.path.isdir(file_path):
                import shutil
                shutil.rmtree(file_path, ignore_errors=True)
            else:
                os.remove(file_path)