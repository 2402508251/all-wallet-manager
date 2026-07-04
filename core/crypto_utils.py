"""
邮箱授权码安全存储 —— AES-256-GCM 加密，机器特征值派生密钥
"""
import base64
import os

from Crypto.Cipher import AES


class CredentialEncryptor:
    """
    邮箱授权码加密存储：
    - 使用机器特征值派生密钥（防止数据文件被复制到其他机器后解密）
    - AES-256-GCM 加密
    - 加密后 Base64 编码存入 email_configs.auth_code_enc
    """

    def __init__(self):
        self._key = self._derive_key()

    def _derive_key(self) -> bytes:
        import hashlib
        import platform
        import subprocess

        machine_id = self._get_machine_id()
        salt = b'AllWalletManager4_v1_key_derivation_salt'
        return hashlib.pbkdf2_hmac('sha256', machine_id.encode(), salt, 200_000)

    def _get_machine_id(self) -> str:
        import platform
        components = [
            platform.node(),
            platform.machine(),
            platform.processor(),
        ]

        if platform.system() == 'Windows':
            try:
                import subprocess
                result = subprocess.run(
                    ['wmic', 'csproduct', 'get', 'UUID'],
                    capture_output=True, text=True, timeout=5,
                )
                for line in result.stdout.strip().splitlines():
                    line = line.strip()
                    if line and line != 'UUID':
                        components.append(line)
                        break
            except Exception:
                pass
            try:
                import subprocess
                result = subprocess.run(
                    ['wmic', 'bios', 'get', 'SerialNumber'],
                    capture_output=True, text=True, timeout=5,
                )
                for line in result.stdout.strip().splitlines():
                    line = line.strip()
                    if line and line != 'SerialNumber':
                        components.append(line)
                        break
            except Exception:
                pass
        elif platform.system() == 'Darwin':
            try:
                import subprocess
                result = subprocess.run(
                    ['ioreg', '-rd1', '-c', 'IOPlatformExpertDevice'],
                    capture_output=True, text=True, timeout=5,
                )
                for line in result.stdout.splitlines():
                    if 'IOPlatformUUID' in line:
                        components.append(line.split('=')[-1].strip().strip('"'))
                        break
            except Exception:
                pass
        elif platform.system() == 'Linux':
            try:
                with open('/etc/machine-id', 'r') as f:
                    components.append(f.read().strip())
            except Exception:
                pass

        return '|'.join(components)

    def encrypt(self, plaintext: str) -> str:
        """加密授权码，返回 Base64 编码的密文"""
        cipher = AES.new(self._key, AES.MODE_GCM)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode('utf-8'))
        # 将 nonce + tag + ciphertext 拼接后 Base64 编码
        result = cipher.nonce + tag + ciphertext
        return base64.b64encode(result).decode('utf-8')

    def decrypt(self, encoded: str) -> str:
        """解密授权码"""
        raw = base64.b64decode(encoded)
        nonce = raw[:16]
        tag = raw[16:32]
        ciphertext = raw[32:]
        cipher = AES.new(self._key, AES.MODE_GCM, nonce=nonce)
        plaintext = cipher.decrypt_and_verify(ciphertext, tag)
        return plaintext.decode('utf-8')