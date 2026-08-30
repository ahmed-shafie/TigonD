import hvac


class VaultSecretStore:
    def __init__(self, url: str, token: str, mount: str = "tigond"):
        self.client = hvac.Client(url=url, token=token)
        self.mount = mount

    def ensure_mount(self) -> None:
        mounts = self.client.sys.list_mounted_secrets_engines()["data"]
        if f"{self.mount}/" not in mounts:
            self.client.sys.enable_secrets_engine("kv", path=self.mount, options={"version": "2"})

    def put_source_password(self, source_id: str, password: str) -> str:
        path = f"sources/{source_id}"
        self.client.secrets.kv.v2.create_or_update_secret(path=path, mount_point=self.mount, secret={"password": password})
        return path

    def get_source_password(self, path: str) -> str:
        response = self.client.secrets.kv.v2.read_secret_version(path=path, mount_point=self.mount)
        return response["data"]["data"]["password"]


class MemorySecretStore:
    def __init__(self):
        self.values: dict[str, str] = {}

    def ensure_mount(self) -> None:
        return None

    def put_source_password(self, source_id: str, password: str) -> str:
        path = f"sources/{source_id}"
        self.values[path] = password
        return path

    def get_source_password(self, path: str) -> str:
        return self.values[path]
