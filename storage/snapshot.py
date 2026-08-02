# storage/snapshot.py
import os
import hashlib
import logging
import tempfile
import asyncio
from typing import Optional
import msgpack

logger = logging.getLogger("Atlas.Snapshot")

class SnapshotManager:
    def __init__(self, snapshot_dir: str, filename: str = "snapshot.latest"):
        self.snapshot_dir = snapshot_dir
        self.filename = filename
        self.snapshot_path = os.path.join(snapshot_dir, filename)
        self.temp_prefix = "snapshot.tmp."
        os.makedirs(snapshot_dir, exist_ok=True)

    async def write(self, data: dict) -> bool:
        loop = asyncio.get_running_loop()

        def _write():
            packed = msgpack.packb(data, use_bin_type=True)
            checksum = hashlib.sha256(packed).hexdigest()

            temp_fd, temp_path = tempfile.mkstemp(
                prefix=self.temp_prefix,
                dir=self.snapshot_dir
            )
            try:
                with os.fdopen(temp_fd, 'wb') as f:
                    # 写入 packed 数据后紧跟 64 字节校验和（无换行符）
                    f.write(packed)
                    f.write(checksum.encode('utf-8'))
                    f.flush()
                    os.fsync(f.fileno())
                # 原子重命名（POSIX 保证 rename 是原子的）
                os.replace(temp_path, self.snapshot_path)
                return True
            except Exception as e:
                if os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass
                logger.error(f"Snapshot write failed: {e}")
                return False

        return await loop.run_in_executor(None, _write)

    async def read(self) -> Optional[dict]:
        if not os.path.exists(self.snapshot_path):
            return None

        loop = asyncio.get_running_loop()

        def _read():
            try:
                with open(self.snapshot_path, 'rb') as f:
                    content = f.read()

                if len(content) < 64:
                    raise ValueError("Snapshot file too small")

                # 精准分割：末尾 64 字节 = SHA256 校验和
                checksum_expected = content[-64:].decode('utf-8')
                data_bytes = content[:-64]

                checksum_actual = hashlib.sha256(data_bytes).hexdigest()
                if checksum_actual != checksum_expected:
                    raise ValueError(f"Checksum mismatch: expected {checksum_expected[:8]}..., got {checksum_actual[:8]}...")

                return msgpack.unpackb(data_bytes, raw=False)

            except Exception as e:
                logger.error(f"Snapshot read failed: {e}")
                return None

        return await loop.run_in_executor(None, _read)

    async def exists(self) -> bool:
        return os.path.exists(self.snapshot_path)

    async def delete(self) -> None:
        if os.path.exists(self.snapshot_path):
            try:
                os.unlink(self.snapshot_path)
            except OSError:
                pass

    async def get_size(self) -> int:
        if os.path.exists(self.snapshot_path):
            return os.path.getsize(self.snapshot_path)
        return 0