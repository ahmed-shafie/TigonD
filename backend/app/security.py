from cryptography.fernet import Fernet


class CredentialCipher:
    def __init__(self, key: str):
        self._fernet = Fernet(key.encode()) if key else Fernet(Fernet.generate_key())

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        return self._fernet.decrypt(value.encode()).decode()

